"""Decode a replay into evidence-safe normalized observations."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve()
COACH_DIR = HERE.parents[1]
PROJECT_DIR = COACH_DIR.parent
if str(COACH_DIR) not in sys.path:
    sys.path.insert(0, str(COACH_DIR))

from core.cooldown_recognizer import CooldownConfigurationError, load_cooldown_manifest  # noqa: E402
from core.orchestrator import _cooldown_recognizer_from_config  # noqa: E402
from core.raw_video_extractors import extract_raw_video_observations  # noqa: E402
from utils.config_utils import load_yaml  # noqa: E402


def _resolve(path: str | Path, *, base: Path = PROJECT_DIR) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return base / candidate


def _cooldown_config(args: argparse.Namespace) -> dict[str, Any] | None:
    config: dict[str, Any] = {}
    if args.config:
        config = load_yaml(_resolve(args.config))
    raw_video = config.get("raw_video") or {}
    cooldown = dict(raw_video.get("cooldown_recognizer") or {})
    if args.calibration_manifest:
        manifest_path = _resolve(args.calibration_manifest)
        manifest = load_cooldown_manifest(manifest_path)
        cooldown.update(
            {
                "enabled": True,
                "calibration_manifest": str(manifest_path),
                "implementation_version": str(manifest.get("implementation_version", "cooldown-template-v1")),
                "layout_profile": str(manifest.get("layout_profile", "unversioned")),
                "expected_source_dimensions": manifest.get("expected_source_dimensions"),
                "source_compatibility": manifest.get("source_compatibility", {}),
                "rois": manifest.get("roi_profiles", {}),
                "max_error": (manifest.get("threshold_policy") or {}).get("max_error", .28),
                "min_margin": (manifest.get("threshold_policy") or {}).get("min_margin", .005),
                "min_mean_by_slot": (manifest.get("threshold_policy") or {}).get("min_mean_by_slot", {}),
                "candidate_window_only": manifest.get("candidate_window_only", True),
            }
        )
        sampling = manifest.get("sampling_policy") or {}
        for key in ("window_padding_sec", "samples_before", "samples_during", "samples_after", "before_sec", "after_sec"):
            if key in sampling:
                cooldown[key] = sampling[key]
    if not cooldown or not cooldown.get("enabled", False):
        return None
    return cooldown


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("--output", type=Path, required=True, help="JSONL observations output")
    parser.add_argument("--window", nargs=2, type=float, action="append", metavar=("START", "END"), help="candidate time window; repeatable")
    parser.add_argument("--config", type=Path, default=None, help="YAML config containing raw_video.cooldown_recognizer")
    parser.add_argument("--calibration-manifest", type=Path, default=None, help="shared cooldown calibration manifest")
    parser.add_argument("--sample-interval", type=float, default=30.0)
    parser.add_argument("--max-windows", type=int, default=120)
    parser.add_argument("--retain-dir", type=Path, default=None)
    parser.add_argument("--metrics-output", type=Path, default=None, help="write metrics and candidate windows as JSON")
    parser.add_argument("--cooldown-only", action="store_true", help="emit only cooldown_ui atomic observations")
    parser.add_argument("--calibration-debug", action="store_true", help="allow sparse fallback cadence when no windows are supplied")
    parser.add_argument("--samples-before", type=int, default=None)
    parser.add_argument("--samples-during", type=int, default=None)
    parser.add_argument("--samples-after", type=int, default=None)
    parser.add_argument("--before-sec", type=float, default=None)
    parser.add_argument("--after-sec", type=float, default=None)
    args = parser.parse_args()

    try:
        cooldown_cfg = _cooldown_config(args)
        cooldown_recognizer = None
        cooldown_rois = None
        if cooldown_cfg is not None:
            cooldown_recognizer, cooldown_rois = _cooldown_recognizer_from_config(cooldown_cfg)
        sampling = cooldown_cfg or {}
        observations, metrics, windows = extract_raw_video_observations(
            str(args.video),
            candidate_windows=args.window or [],
            sample_interval_sec=args.sample_interval,
            max_candidate_windows=args.max_windows,
            retain_crops=args.retain_dir is not None,
            retain_dir=args.retain_dir,
            cooldown_recognizer=cooldown_recognizer,
            cooldown_rois=cooldown_rois,
            calibration_debug=args.calibration_debug,
            window_padding_sec=float(sampling.get("window_padding_sec", 3.0)),
            samples_before=int(args.samples_before if args.samples_before is not None else sampling.get("samples_before", 1)),
            samples_during=int(args.samples_during if args.samples_during is not None else sampling.get("samples_during", 3)),
            samples_after=int(args.samples_after if args.samples_after is not None else sampling.get("samples_after", 1)),
            before_sec=float(args.before_sec if args.before_sec is not None else sampling.get("before_sec", 2.0)),
            after_sec=float(args.after_sec if args.after_sec is not None else sampling.get("after_sec", 2.0)),
        )
    except (CooldownConfigurationError, OSError, RuntimeError, ValueError) as err:
        parser.error(str(err))

    if args.cooldown_only:
        observations = [observation for observation in observations if observation.type == "cooldown_ui"]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        for observation in observations:
            handle.write(json.dumps(observation.to_dict(), ensure_ascii=False, sort_keys=True) + "\n")

    metrics_payload = metrics.to_dict()
    metrics_payload.update({"candidate_windows": windows, "output": str(args.output)})
    if cooldown_recognizer is not None:
        metrics_payload.update(
            {
                "cooldown_detector_version": cooldown_recognizer.version,
                "cooldown_calibration_fingerprint": cooldown_recognizer.calibration_fingerprint,
            }
        )
    if args.metrics_output:
        _write_json(args.metrics_output, metrics_payload)
    print(json.dumps(metrics_payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
