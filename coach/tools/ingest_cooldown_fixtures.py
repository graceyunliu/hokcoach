"""Ingest canonical cooldown candidate fixtures into evidence-safe predictions.

This tool intentionally accepts candidate windows as hints, not labels. It only
runs when the input video hash matches the canonical source hash recorded in
the manifest and it never converts rejected, unknown, or quarantined examples
into ground truth.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve()
COACH_DIR = HERE.parents[1]
PROJECT_DIR = COACH_DIR.parent
if str(COACH_DIR) not in sys.path:
    sys.path.insert(0, str(COACH_DIR))

from core.cooldown_recognizer import load_cooldown_manifest  # noqa: E402
from core.orchestrator import _cooldown_recognizer_from_config  # noqa: E402
from core.raw_video_extractors import _window_union, extract_raw_video_observations  # noqa: E402
from utils.config_utils import load_yaml  # noqa: E402


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"manifest must be an object: {path}")
    return value


def _load_jsonl(path: Path | None) -> list[dict[str, Any]]:
    if path is None or not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid annotation JSON at {path}:{line_number}") from exc
        if not isinstance(row, dict):
            raise ValueError(f"annotation must be an object at {path}:{line_number}")
        rows.append(row)
    return rows


def _cooldown_config(args: argparse.Namespace) -> dict[str, Any]:
    if args.cooldown_manifest:
        manifest_path = args.cooldown_manifest.resolve()
        manifest = load_cooldown_manifest(manifest_path)
        thresholds = manifest["threshold_policy"]
        config: dict[str, Any] = {
            "enabled": True,
            "calibration_manifest": str(manifest_path),
            "implementation_version": manifest.get("implementation_version", "cooldown-template-v1"),
            "layout_profile": manifest["layout_profile"],
            "expected_source_dimensions": manifest["expected_source_dimensions"],
            "source_compatibility": manifest["source_compatibility"],
            "rois": manifest["roi_profiles"],
            "max_error": thresholds["max_error"],
            "min_margin": thresholds["min_margin"],
            "min_mean_by_slot": thresholds["min_mean_by_slot"],
            "candidate_window_only": True,
        }
        config.update(manifest.get("sampling_policy") or {})
        return config
    if not args.config:
        raise ValueError("--cooldown-manifest or --config is required")
    config = load_yaml(args.config.resolve())
    cooldown = ((config.get("raw_video") or {}).get("cooldown_recognizer") or {})
    if not cooldown.get("enabled", False):
        raise ValueError("configured cooldown recognizer is disabled")
    return dict(cooldown)


def _candidate_windows(manifest: dict[str, Any], duration: float, max_windows: int) -> tuple[list[tuple[float, float]], list[dict[str, Any]]]:
    raw = [entry for entry in manifest.get("windows", []) if entry.get("capability") == "cooldowns"]
    usable = [entry for entry in raw if entry.get("visual_triage_status") != "out_of_range"]
    windows = [(float(entry["window"]["start_sec"]), float(entry["window"]["end_sec"])) for entry in usable]
    deduped = _window_union(windows, duration=duration, padding=0.0)[:max(0, max_windows)]
    return deduped, usable


def _validate_annotations(rows: list[dict[str, Any]], source_hash: str) -> tuple[list[dict[str, Any]], dict[str, int]]:
    accepted: list[dict[str, Any]] = []
    counts = {"accepted": 0, "rejected": 0, "source_mismatch": 0, "invalid": 0}
    seen: set[tuple[str, float, str, str]] = set()
    for row in rows:
        media = row.get("source_media") or {}
        if media.get("sha256") != source_hash:
            counts["source_mismatch"] += 1
            continue
        status = str(row.get("status", "accepted"))
        if status != "accepted":
            counts["rejected"] += 1
            continue
        if row.get("label") not in {"ready", "on_cooldown", "unknown"} or row.get("split") not in {"tuning", "evaluation"}:
            counts["invalid"] += 1
            continue
        roi = row.get("roi")
        if not isinstance(roi, dict) or not {"x", "y", "w", "h"}.issubset(roi):
            counts["invalid"] += 1
            continue
        key = (str(row.get("slot")), float(row.get("timestamp_sec", -1)), str(row.get("split")), json.dumps(roi, sort_keys=True))
        if key in seen:
            continue
        seen.add(key)
        accepted.append(row)
        counts["accepted"] += 1
    return accepted, counts


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _directory_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--candidate-manifest", type=Path, required=True)
    parser.add_argument("--cooldown-manifest", type=Path, default=None)
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--annotations", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--max-windows", type=int, default=120)
    parser.add_argument("--retain-crops", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    try:
        video = args.video.resolve()
        if not video.is_file():
            raise ValueError(f"video does not exist: {video}")
        candidate_manifest = _load_json(args.candidate_manifest.resolve())
        source_hash = _hash_file(video)
        canonical_hash = ((candidate_manifest.get("source_media") or {}).get("sha256"))
        if not canonical_hash or source_hash != canonical_hash:
            raise ValueError("source hash mismatch: candidate fixtures are quarantined and cannot be ingested")
        duration = float((candidate_manifest.get("source_media") or {}).get("duration_sec") or 0.0)
        if duration <= 0:
            raise ValueError("candidate manifest must provide a positive source duration")
        windows, entries = _candidate_windows(candidate_manifest, duration, args.max_windows)
        cooldown_config = _cooldown_config(args)
        recognizer, rois = _cooldown_recognizer_from_config(cooldown_config)
        source_layout = ((candidate_manifest.get("source_media") or {}).get("layout") or {})
        source_dimensions = tuple(source_layout.get("source") or ())
        if recognizer.expected_source_dimensions is not None and source_dimensions != recognizer.expected_source_dimensions:
            raise ValueError("candidate manifest source dimensions do not match cooldown calibration")
        annotations, annotation_counts = _validate_annotations(_load_jsonl(args.annotations.resolve() if args.annotations else None), source_hash)
        output_dir = args.output_dir.resolve()
        predictions_path = output_dir / "predictions.jsonl"
        metrics_path = output_dir / "metrics.json"
        input_fingerprint = hashlib.sha256(json.dumps({"source_hash": source_hash, "windows": windows, "detector_version": recognizer.version, "annotations": annotations}, sort_keys=True).encode("utf-8")).hexdigest()
        if not args.force and metrics_path.exists() and predictions_path.exists():
            cached = _load_json(metrics_path)
            if cached.get("input_fingerprint") == input_fingerprint and cached.get("predictions_sha256") == _hash_file(predictions_path):
                cached["cache_hit"] = True
                print(json.dumps(cached, ensure_ascii=False, sort_keys=True))
                return 0
        observations, extraction_metrics, extracted_windows = extract_raw_video_observations(
            str(video),
            candidate_windows=windows,
            max_candidate_windows=args.max_windows,
            retain_crops=args.retain_crops,
            retain_dir=output_dir / "evidence" if args.retain_crops else None,
            cooldown_recognizer=recognizer,
            cooldown_rois=rois,
            emit_cooldown_placeholders=False,
            window_padding_sec=float(cooldown_config.get("window_padding_sec", 3.0)),
            samples_before=int(cooldown_config.get("samples_before", 1)),
            samples_during=int(cooldown_config.get("samples_during", 3)),
            samples_after=int(cooldown_config.get("samples_after", 1)),
            before_sec=float(cooldown_config.get("before_sec", 2.0)),
            after_sec=float(cooldown_config.get("after_sec", 2.0)),
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        cooldown_observations = [item.to_dict() for item in observations if item.type == "cooldown_ui"]
        with predictions_path.open("w", encoding="utf-8") as handle:
            for observation in cooldown_observations:
                handle.write(json.dumps(observation, ensure_ascii=False, sort_keys=True) + "\n")
        metrics = extraction_metrics.to_dict()
        metrics.update({
            "schema_version": "cooldown-fixture-ingestion-v1",
            "source_media_sha256": source_hash,
            "candidate_windows_raw": len(entries),
            "candidate_windows_deduped": len(windows),
            "candidate_windows": windows,
            "extracted_windows": extracted_windows,
            "annotation_counts": annotation_counts,
            "accepted_annotation_count": len(annotations),
            "input_fingerprint": input_fingerprint,
            "detector_version": recognizer.version,
            "calibration_fingerprint": recognizer.calibration_fingerprint,
            "predictions_path": str(predictions_path),
            "predictions_size_bytes": predictions_path.stat().st_size,
            "predictions_sha256": _hash_file(predictions_path),
            "retained_evidence_dir": str(output_dir / "evidence") if args.retain_crops else None,
            "regenerable_cache_bytes": predictions_path.stat().st_size + _directory_bytes(output_dir / "evidence"),
            "cache_hit": False,
        })
        _write_json(metrics_path, metrics)
        print(json.dumps(metrics, ensure_ascii=False, sort_keys=True))
        return 0
    except (OSError, RuntimeError, ValueError, TypeError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
