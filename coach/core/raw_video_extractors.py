from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import time
from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from core.cooldown_recognizer import CooldownTemplateRecognizer
from core.observations import Observation
from core.tower_recognizer import TowerTemplateRecognizer
from core.viewport_detector import detect_gameplay_viewport
from utils import video_utils


@dataclass(frozen=True)
class RawExtractionMetrics:
    duration_sec: float
    candidate_windows: int
    frames_requested: int
    frames_decoded: int
    frames_unreadable: int
    retained_crops: int
    decode_failures: int = 0
    semantic_unreadable_frames: int = 0
    recognition_failures: int = 0
    semantic_unreadable_observations: int = 0
    readable_crops: int = 0
    observed_predictions: int = 0
    unknown_predictions: int = 0
    unreadable_predictions: int = 0
    classified_accuracy: float | None = None
    coverage: float | None = None
    abstention_correct: int | None = None
    transition_count: int = 0
    objective_observations: int = 0
    objective_observed: int = 0
    objective_unknown: int = 0
    objective_unreadable: int = 0
    processing_seconds: float = 0.0
    processing_seconds_per_source_minute: float | None = None
    retained_derived_bytes: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "duration_sec": self.duration_sec,
            "candidate_windows": self.candidate_windows,
            "frames_requested": self.frames_requested,
            "frames_decoded": self.frames_decoded,
            "frames_unreadable": self.frames_unreadable,
            "retained_crops": self.retained_crops,
            "decode_failures": self.decode_failures,
            "semantic_unreadable_frames": self.semantic_unreadable_frames,
            "recognition_failures": self.recognition_failures,
            "semantic_unreadable_observations": self.semantic_unreadable_observations,
            "readable_crops": self.readable_crops,
            "observed_predictions": self.observed_predictions,
            "unknown_predictions": self.unknown_predictions,
            "unreadable_predictions": self.unreadable_predictions,
            "classified_accuracy": self.classified_accuracy,
            "coverage": self.coverage,
            "abstention_correct": self.abstention_correct,
            "transition_count": self.transition_count,
            "objective_observations": self.objective_observations,
            "objective_observed": self.objective_observed,
            "objective_unknown": self.objective_unknown,
            "objective_unreadable": self.objective_unreadable,
            "processing_seconds": self.processing_seconds,
            "processing_seconds_per_source_minute": self.processing_seconds_per_source_minute,
            "retained_derived_bytes": self.retained_derived_bytes,
        }


def _probe_duration(video: Path) -> float:
    try:
        return max(0.0, float(video_utils.video_duration(str(video))))
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError):
        probe = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "packet=pts_time",
                "-of",
                "csv=p=0",
                str(video),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        values = [float(line.strip()) for line in probe.stdout.splitlines() if line.strip()]
        if not values:
            raise RuntimeError(f"unable to determine video duration: {video}")
        return max(0.0, max(values))


def _probe_dimensions(video: Path) -> tuple[int, int] | None:
    try:
        probe = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height",
                "-of",
                "csv=p=0:s=x",
                str(video),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        width, height = (int(value) for value in probe.stdout.strip().split("x", 1))
        return width, height
    except (OSError, ValueError, subprocess.CalledProcessError):
        return None


def _window_union(
    windows: Iterable[tuple[float, float]], *, duration: float, padding: float = 3.0
) -> list[tuple[float, float]]:
    prepared = sorted(
        (
            max(0.0, float(start) - padding),
            min(duration, float(end) + padding),
        )
        for start, end in windows
        if float(end) >= float(start)
    )
    merged: list[list[float]] = []
    for start, end in prepared:
        if not merged or start > merged[-1][1]:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)
    return [(start, end) for start, end in merged]


def _sample_window(
    window: tuple[float, float],
    *,
    duration: float,
    before_count: int,
    during_count: int,
    after_count: int,
    before_sec: float,
    after_sec: float,
) -> list[float]:
    start, end = window
    samples: list[float] = []
    if before_count > 0:
        samples.extend(
            max(0.0, start - before_sec * (before_count - index) / before_count)
            for index in range(before_count)
        )
    if during_count > 0:
        if during_count == 1:
            samples.append((start + end) / 2.0)
        else:
            samples.extend(start + (end - start) * index / (during_count - 1) for index in range(during_count))
    if after_count > 0:
        samples.extend(
            min(duration, end + after_sec * (index + 1) / after_count)
            for index in range(after_count)
        )
    return samples


def _source_hash(video: Path) -> str:
    try:
        digest = hashlib.sha256()
        with video.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return hashlib.sha256(str(video.resolve()).encode("utf-8")).hexdigest()


def _frame_ref(
    source_hash: str,
    timestamp: float,
    region: str,
    *,
    slot: str | None = None,
    layout_profile: str | None = None,
    detector_version: str | None = None,
    roi: dict[str, int] | None = None,
) -> str:
    token = "|".join(
        str(value)
        for value in (
            source_hash,
            f"{timestamp:.3f}",
            region,
            slot or "",
            layout_profile or "",
            detector_version or "",
            json.dumps(roi or {}, sort_keys=True, separators=(",", ":")),
        )
    )
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()[:20]
    roi_token = json.dumps(roi or {}, sort_keys=True, separators=(",", ":"))
    metadata = (
        f"source_sha256={source_hash}|timestamp_sec={timestamp:.3f}|region={region}"
        f"|roi_slot={slot or ''}|roi={roi_token}|layout={layout_profile or ''}"
        f"|detector_version={detector_version or ''}"
    )
    return f"frame:{digest}|{metadata}"


def _grab_hud_frame(
    video: Path,
    timestamp: float,
    target: Path,
    *,
    source_dimensions: tuple[int, int] | None,
) -> Path:
    """Grab a full decoded frame for cooldown ROIs.

    The production grabber accepts a crop argument. The fallback call keeps
    older test doubles and callers that expose the historical three-argument
    signature compatible.
    """
    if source_dimensions is None:
        return video_utils.grab_hud_frame(str(video), timestamp, target)
    width, height = source_dimensions
    crop = {"x": 0, "y": 0, "w": width, "h": height}
    try:
        return video_utils.grab_hud_frame(str(video), timestamp, target, crop=crop)
    except TypeError:
        return video_utils.grab_hud_frame(str(video), timestamp, target)


def _retained_bytes(directory: Path | None) -> int:
    if directory is None or not directory.exists():
        return 0
    return sum(path.stat().st_size for path in directory.rglob("*") if path.is_file())


def extract_raw_video_observations(
    video_path: str,
    *,
    seed_windows: Iterable[tuple[float, float]] = (),
    candidate_windows: Iterable[tuple[float, float]] | None = None,
    sample_interval_sec: float = 30.0,
    retain_crops: bool = False,
    retain_dir: Path | None = None,
    max_candidate_windows: int = 120,
    tower_recognizer: TowerTemplateRecognizer | None = None,
    cooldown_recognizer: CooldownTemplateRecognizer | None = None,
    cooldown_rois: dict[str, dict[str, int]] | None = None,
    objective_recognizer: Any | None = None,
    calibration_debug: bool = False,
    window_padding_sec: float = 3.0,
    samples_before: int = 1,
    samples_during: int = 3,
    samples_after: int = 1,
    before_sec: float = 2.0,
    after_sec: float = 2.0,
    emit_cooldown_placeholders: bool = True,
) -> tuple[list[Observation], RawExtractionMetrics, list[tuple[float, float]]]:
    """Decode selected candidate-window frames and emit evidence-safe observations.

    Production extraction is candidate-window-only. Sparse cadence is available
    only through the explicit calibration/debug flag.
    """
    if sample_interval_sec <= 0:
        raise ValueError("sample_interval_sec must be positive")
    if retain_crops and retain_dir is None:
        raise ValueError("retain_dir is required when retain_crops is enabled")
    if min(samples_before, samples_during, samples_after) < 0:
        raise ValueError("sampling counts must be nonnegative")
    if before_sec < 0 or after_sec < 0:
        raise ValueError("sampling spans must be nonnegative")

    started = time.perf_counter()
    video = Path(video_path)
    duration = _probe_duration(video)
    explicit_windows = list(candidate_windows if candidate_windows is not None else seed_windows)
    if explicit_windows:
        source_windows = explicit_windows
    elif calibration_debug or cooldown_recognizer is None or not hasattr(cooldown_recognizer, "expected_source_dimensions"):
        # Legacy raw sampling remains available for non-cooldown callers and
        # historical test doubles. A configured cooldown recognizer never
        # falls back to a full-video cadence unless calibration/debug mode was
        # explicitly requested.
        source_windows = [
            (ts, min(duration, ts + 0.1))
            for ts in (i * sample_interval_sec for i in range(int(duration // sample_interval_sec) + 1))
        ]
    else:
        source_windows = []
    candidates = _window_union(source_windows, duration=duration, padding=window_padding_sec)
    candidates = candidates[: max(0, int(max_candidate_windows))]
    if (cooldown_recognizer is None or not hasattr(cooldown_recognizer, "expected_source_dimensions")) and not calibration_debug:
        samples_before, samples_during, samples_after = 0, 1, 0
    timestamps = sorted(
        {
            round(timestamp, 3)
            for window in candidates
            for timestamp in _sample_window(
                window,
                duration=duration,
                before_count=samples_before,
                during_count=samples_during,
                after_count=samples_after,
                before_sec=before_sec,
                after_sec=after_sec,
            )
        }
    )

    observations: list[Observation] = []
    objective_frame_index: dict[float, tuple[Path, str]] = {}
    decoded = decode_failures = frames_unreadable = recognition_failures = semantic_unreadable_observations = 0
    retained = 0
    readable_crops = observed_predictions = unknown_predictions = unreadable_predictions = 0
    objective_observed = objective_unknown = objective_unreadable = 0
    source_hash = _source_hash(video)
    calibration_version = getattr(tower_recognizer, "calibration_version", "uncalibrated")
    layout_profile = getattr(tower_recognizer, "layout_profile", "none")
    sampler_version = "raw-video-sampler-v2"
    tower_detector_version = f"tower-visual-v2:{calibration_version}" if tower_recognizer is not None else sampler_version
    cooldown_version = getattr(cooldown_recognizer, "version", "cooldown-unavailable")
    cooldown_layout = getattr(cooldown_recognizer, "layout_profile", "none")
    cooldown_dimensions = getattr(cooldown_recognizer, "expected_source_dimensions", None)
    source_dimensions = _probe_dimensions(video) or cooldown_dimensions
    cooldown_source_compatible = True
    if cooldown_recognizer is not None and hasattr(cooldown_recognizer, "is_source_compatible"):
        cooldown_source_compatible = bool(cooldown_recognizer.is_source_compatible(source_hash, source_dimensions))
    workspace = nullcontext(Path(retain_dir)) if retain_crops else tempfile.TemporaryDirectory(prefix="hokcoach_raw_frames_")
    with workspace as workspace_path:
        temp_root = Path(workspace_path)
        if retain_crops:
            temp_root.mkdir(parents=True, exist_ok=True)
        for timestamp in timestamps:
            for region, grabber in (("minimap", video_utils.grab_minimap_frame), ("hud", video_utils.grab_hud_frame)):
                target = temp_root / f"{region}_{timestamp:.3f}.png"
                if region == "hud" and cooldown_recognizer is not None:
                    target = temp_root / f"hud_full_{timestamp:.3f}.png"
                ref = _frame_ref(source_hash, timestamp, region)
                media_ok = False
                try:
                    if region == "hud" and (cooldown_recognizer is not None or objective_recognizer is not None):
                        _grab_hud_frame(video, timestamp, target, source_dimensions=source_dimensions)
                    else:
                        grabber(str(video), timestamp, target)
                    decoded += 1
                    media_ok = True
                    if retain_crops:
                        retained += 1
                        ref = f"{ref}:{target}"
                    if region == "hud" and objective_recognizer is not None and media_ok:
                        objective_ref = _frame_ref(source_hash, timestamp, region, slot="objective", layout_profile=getattr(objective_recognizer, "layout_profile", "unknown"), detector_version=getattr(objective_recognizer, "version", "objective-visual-baseline-v1"), roi=getattr(objective_recognizer, "roi", None))
                        objective_frame_index[round(timestamp, 3)] = (target, objective_ref)
                except Exception:
                    decode_failures += 1
                if region == "minimap":
                    tower_results: dict[str, Any] = {}
                    if media_ok and tower_recognizer is not None:
                        try:
                            tower_results = tower_recognizer.recognize_all(target)
                        except Exception:
                            recognition_failures += 1
                    if tower_results:
                        for tower_id, recognition in tower_results.items():
                            status = recognition.status
                            if status != "observed":
                                semantic_unreadable_observations += 1
                            observations.append(
                                Observation.create(
                                    obs_type="tower_visual",
                                    start_sec=timestamp,
                                    end_sec=timestamp,
                                    subject=tower_id,
                                    value={**recognition.to_dict(), "layout_profile": layout_profile, "calibration_version": calibration_version},
                                    confidence=recognition.confidence if status == "observed" else 0.0,
                                    detector="tower_visual_recognizer",
                                    detector_version=tower_detector_version,
                                    evidence_refs=[_frame_ref(source_hash, timestamp, region, slot=tower_id, layout_profile=layout_profile, detector_version=tower_detector_version)],
                                    status=status,
                                )
                            )
                    else:
                        semantic_unreadable_observations += 1
                        observations.append(
                            Observation.create(
                                obs_type="tower_visual",
                                start_sec=timestamp,
                                end_sec=timestamp,
                                subject="map",
                                value={"visibility": "unreadable", "region": region},
                                confidence=0.0,
                                detector="raw_video_sampler",
                                detector_version=sampler_version,
                                evidence_refs=[ref],
                                status="unreadable",
                            )
                        )
                    semantic_unreadable_observations += 1
                    observations.append(
                        Observation.create(
                            obs_type="minion_cluster",
                            start_sec=timestamp,
                            end_sec=timestamp,
                            subject="map",
                            value={"visibility": "unreadable", "region": region},
                            confidence=0.0,
                            detector="raw_video_sampler",
                            detector_version=sampler_version,
                            evidence_refs=[ref],
                            status="unreadable",
                        )
                    )
                    if not any(result.status == "observed" for result in tower_results.values()):
                        frames_unreadable += 1
                else:
                    semantic_unreadable_observations += 1
                    observations.append(
                        Observation.create(
                            obs_type="inventory_snapshot",
                            start_sec=timestamp,
                            end_sec=timestamp,
                            subject="player",
                            value={"visibility": "unreadable", "region": region},
                            confidence=0.0,
                            detector="raw_video_sampler",
                            detector_version=sampler_version,
                            evidence_refs=[ref],
                            status="unreadable",
                        )
                    )
                    if cooldown_recognizer is not None and cooldown_rois:
                        for skill, roi in cooldown_rois.items():
                            evidence_ref = _frame_ref(
                                source_hash,
                                timestamp,
                                region,
                                slot=str(skill),
                                layout_profile=cooldown_layout,
                                detector_version=cooldown_version,
                                roi=roi,
                            )
                            try:
                                if not cooldown_source_compatible:
                                    compatibility_reason = "unsupported_layout" if cooldown_dimensions and tuple(source_dimensions or ()) != tuple(cooldown_dimensions) else "unsupported_source"
                                    cooldown_observation = Observation.create(
                                        obs_type="cooldown_ui",
                                        start_sec=timestamp,
                                        end_sec=timestamp,
                                        subject="player",
                                        value={"skill": str(skill), "state": "unknown", "reason": compatibility_reason},
                                        confidence=0.0,
                                        detector="cooldown_visual",
                                        detector_version=cooldown_version,
                                        evidence_refs=[evidence_ref],
                                        status="unreadable",
                                    )
                                elif hasattr(cooldown_recognizer, "expected_source_dimensions"):
                                    cooldown_observation = cooldown_recognizer.recognize_hud(
                                        target,
                                        slot=str(skill),
                                        roi=roi,
                                        start_sec=timestamp,
                                        end_sec=timestamp,
                                        evidence_ref=evidence_ref,
                                        source_dimensions=source_dimensions,
                                    )
                                else:
                                    cooldown_observation = cooldown_recognizer.recognize_hud(
                                        target,
                                        slot=str(skill),
                                        roi=roi,
                                        start_sec=timestamp,
                                        end_sec=timestamp,
                                        evidence_ref=evidence_ref,
                                    )
                                observations.append(cooldown_observation)
                                if cooldown_observation.status == "observed":
                                    readable_crops += 1
                                    observed_predictions += 1
                                elif cooldown_observation.status == "unknown":
                                    readable_crops += 1
                                    unknown_predictions += 1
                                else:
                                    unreadable_predictions += 1
                                    semantic_unreadable_observations += 1
                            except Exception:
                                recognition_failures += 1
                                unreadable_predictions += 1
                                semantic_unreadable_observations += 1
                                observations.append(
                                    Observation.create(
                                        obs_type="cooldown_ui",
                                        start_sec=timestamp,
                                        end_sec=timestamp,
                                        subject="player",
                                        value={"skill": str(skill), "state": "unknown"},
                                        confidence=0.0,
                                        detector="cooldown_visual",
                                        detector_version=cooldown_version,
                                        evidence_refs=[evidence_ref],
                                        status="unreadable",
                                    )
                                )
                    elif emit_cooldown_placeholders:
                        # Preserve the historical raw-sampler placeholder for
                        # direct legacy callers. Production orchestration sets
                        # this false when cooldown recognition is disabled.
                        semantic_unreadable_observations += 1
                        observations.append(
                            Observation.create(
                                obs_type="cooldown_ui",
                                start_sec=timestamp,
                                end_sec=timestamp,
                                subject="player",
                                value={"skill": "unknown", "state": "unknown", "visibility": "unreadable", "region": region},
                                confidence=0.0,
                                detector="raw_video_sampler",
                                detector_version=sampler_version,
                                evidence_refs=[ref],
                                status="unreadable",
                            )
                        )
                    frames_unreadable += 1
        if objective_recognizer is not None and objective_frame_index:
            for window_start, window_end in candidates:
                sequence = []
                for timestamp, (path, evidence) in sorted(objective_frame_index.items()):
                    if window_start <= timestamp <= window_end:
                        try:
                            viewport = detect_gameplay_viewport(path).to_dict()
                        except (OSError, ValueError):
                            viewport = None
                        sequence.append((path, timestamp, evidence, viewport))

                if not sequence:
                    continue
                try:
                    objective_observations = objective_recognizer.recognize_sequence(sequence, source_hash=source_hash)
                    observations.extend(objective_observations)
                    for item in objective_observations:
                        if item.status == "observed":
                            objective_observed += 1
                        elif item.status == "unknown":
                            objective_unknown += 1
                        else:
                            objective_unreadable += 1
                except Exception:
                    recognition_failures += 1
                    objective_unreadable += len(sequence)

    processing_seconds = time.perf_counter() - started
    total_predictions = observed_predictions + unknown_predictions + unreadable_predictions
    processing_per_minute = processing_seconds / (duration / 60.0) if duration > 0 else None
    metrics = RawExtractionMetrics(
        duration,
        len(candidates),
        len(timestamps) * 2,
        decoded,
        frames_unreadable,
        retained,
        decode_failures,
        frames_unreadable,
        recognition_failures,
        semantic_unreadable_observations,
        readable_crops,
        observed_predictions,
        unknown_predictions,
        unreadable_predictions,
        None,
        observed_predictions / total_predictions if total_predictions else None,
        None,
        0,
        objective_observed + objective_unknown + objective_unreadable,
        objective_observed,
        objective_unknown,
        objective_unreadable,
        processing_seconds,
        processing_per_minute,
        _retained_bytes(Path(retain_dir) if retain_crops and retain_dir else None),
    )
    return observations, metrics, candidates
