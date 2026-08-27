"""Deterministic objective-banner/HUD recognizer.

The recognizer emits activity and direct visual-result evidence only. It never
uses reviewer text, expected game timing, or audio to invent visual labels.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import cv2
import numpy as np

from core.observations import Observation


VERSION = "objective-visual-baseline-v1"


class ObjectiveConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class ObjectivePrediction:
    identity: str
    state: str
    winner: str
    visual_form: str
    score: float
    margin: float
    status: str
    reason: str


class ObjectiveVisualRecognizer:
    def __init__(self, *, roi: dict[str, int], templates: dict[str, str | Path] | None = None, layout_profile: str, expected_source_dimensions: tuple[int, int] | list[int], change_threshold: float = 18.0, max_template_error: float = .22, min_margin: float = .02, min_persistence: int = 2, visual_form: str = "announcement_banner", roi_coordinate_space: str = "viewport_relative", allowed_source_hashes: Iterable[str] = ()):
        self.roi = self._normalize_roi(roi)
        self.layout_profile = str(layout_profile)
        self.expected_source_dimensions = tuple(int(value) for value in expected_source_dimensions)
        self.change_threshold = float(change_threshold)
        self.max_template_error = float(max_template_error)
        self.min_margin = float(min_margin)
        self.min_persistence = max(1, int(min_persistence))
        self.visual_form = str(visual_form)
        self.roi_coordinate_space = str(roi_coordinate_space)
        self.allowed_source_hashes = frozenset(str(value) for value in allowed_source_hashes if value)
        self.templates = {str(identity): Path(path) for identity, path in (templates or {}).items()}
        self._validate()
        self._features = {identity: self._feature(path) for identity, path in self.templates.items()}
        payload = {"implementation": VERSION, "layout_profile": self.layout_profile, "dimensions": self.expected_source_dimensions, "roi": self.roi, "roi_coordinate_space": self.roi_coordinate_space, "allowed_source_hashes": sorted(self.allowed_source_hashes), "templates": {identity: hashlib.sha256(path.read_bytes()).hexdigest() for identity, path in sorted(self.templates.items())}, "thresholds": [self.change_threshold, self.max_template_error, self.min_margin, self.min_persistence]}
        self.calibration_fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:16]
        self.version = f"{VERSION}:{self.calibration_fingerprint}"

    def _normalize_roi(self, roi: dict[str, int]) -> dict[str, int]:
        if not isinstance(roi, dict) or not {"x", "y", "w", "h"}.issubset(roi):
            raise ObjectiveConfigurationError("objective ROI must contain x, y, w, h")
        try:
            result = {key: int(roi[key]) for key in ("x", "y", "w", "h")}
        except (TypeError, ValueError, KeyError) as exc:
            raise ObjectiveConfigurationError("objective ROI coordinates must be integers") from exc
        return result

    def _validate(self) -> None:
        if len(self.expected_source_dimensions) != 2 or any(value <= 0 for value in self.expected_source_dimensions):
            raise ObjectiveConfigurationError("objective source dimensions must be positive")
        width, height = self.expected_source_dimensions
        if self.roi["x"] < 0 or self.roi["y"] < 0 or self.roi["w"] <= 0 or self.roi["h"] <= 0 or self.roi["x"] + self.roi["w"] > width or self.roi["y"] + self.roi["h"] > height:
            raise ObjectiveConfigurationError("objective ROI is outside source dimensions")
        if self.change_threshold < 0 or self.max_template_error < 0 or self.min_margin < 0:
            raise ObjectiveConfigurationError("objective thresholds must be nonnegative")
        if not self.layout_profile:
            raise ObjectiveConfigurationError("objective layout_profile is required")
        if self.roi_coordinate_space not in {"viewport_relative", "source_relative"}:
            raise ObjectiveConfigurationError("objective ROI coordinate space must be viewport_relative or source_relative")

    @staticmethod
    def _feature(path: Path) -> np.ndarray:
        image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if image is None:
            raise ObjectiveConfigurationError(f"unreadable objective template: {path}")
        return cv2.resize(image, (96, 48), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0

    def _read_crop(self, image_path: Path, viewport: dict[str, int] | None = None) -> np.ndarray | None:
        image = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
        if image is None or tuple(reversed(image.shape[:2])) != self.expected_source_dimensions:
            return None
        x, y, w, h = (self.roi[key] for key in ("x", "y", "w", "h"))
        if self.roi_coordinate_space == "viewport_relative":
            if viewport is None:
                return None
            try:
                x += int(viewport["x"])
                y += int(viewport["y"])
            except (KeyError, TypeError, ValueError):
                return None
        if x < 0 or y < 0 or x + w > image.shape[1] or y + h > image.shape[0]:
            return None
        crop = image[y:y + h, x:x + w]
        return crop if crop.size else None

    def _predict_template(self, crop: np.ndarray) -> tuple[str, float, float] | None:
        if not self._features:
            return None
        feature = cv2.resize(crop, (96, 48), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0
        scores = {identity: float(np.mean(np.abs(feature - template))) for identity, template in self._features.items()}
        ordered = sorted(scores.items(), key=lambda item: item[1])
        best_identity, best_error = ordered[0]
        second_error = ordered[1][1] if len(ordered) > 1 else 1.0
        return best_identity, best_error, second_error - best_error

    def _observation(self, prediction: ObjectivePrediction, start: float, end: float, evidence: str) -> Observation:
        value = {"identity": prediction.identity, "state": prediction.state, "winner": prediction.winner, "visual_form": prediction.visual_form, "reason": prediction.reason, "layout_profile": self.layout_profile}
        confidence = max(0.0, min(1.0, 1.0 - prediction.score)) if prediction.status == "observed" else 0.0
        return Observation.create(obs_type="objective_visual", start_sec=start, end_sec=end, subject=prediction.identity, value=value, confidence=confidence, detector="objective_visual_recognizer", detector_version=self.version, evidence_refs=(evidence,), status=prediction.status)

    def recognize_sequence(self, frames: Iterable[tuple[Path, float, str]], *, source_hash: str) -> list[Observation]:
        entries = list(frames)
        normalized_entries = []
        for entry in entries:
            if len(entry) == 3:
                normalized_entries.append((*entry, None))
            elif len(entry) == 4:
                normalized_entries.append(tuple(entry))
            else:
                raise ValueError("objective frame entries must contain path, timestamp, evidence, and optional viewport")
        if self.allowed_source_hashes and source_hash not in self.allowed_source_hashes:
            return [self._observation(ObjectivePrediction("unknown", "unknown", "unknown", self.visual_form, 0.0, 0.0, "unreadable", "unsupported_source"), timestamp, timestamp, f"{evidence}|source_sha256={source_hash}") for _, timestamp, evidence, _ in normalized_entries]
        crops: list[np.ndarray | None] = [self._read_crop(path, viewport) for path, _, _, viewport in normalized_entries]
        template_hits: list[tuple[str, float, float] | None] = [self._predict_template(crop) if crop is not None else None for crop in crops]
        observations: list[Observation] = []
        for index, ((path, timestamp, evidence, viewport), crop, hit) in enumerate(zip(normalized_entries, crops, template_hits)):
            if crop is None:
                prediction = ObjectivePrediction("unknown", "unknown", "unknown", self.visual_form, 0.0, 0.0, "unreadable", "unreadable_or_unsupported_layout")
            else:
                previous = crops[index - 1] if index else None
                change = float(np.mean(np.abs(crop.astype(np.float32) - previous.astype(np.float32)))) if previous is not None and previous.shape == crop.shape else 0.0
                if hit is not None and hit[1] <= self.max_template_error and hit[2] >= self.min_margin:
                    identity, error, margin = hit
                    consecutive = 1
                    for prior in reversed(template_hits[:index]):
                        if prior is not None and prior[0] == identity and prior[1] <= self.max_template_error and prior[2] >= self.min_margin:
                            consecutive += 1
                        else:
                            break
                    if consecutive >= self.min_persistence:
                        prediction = ObjectivePrediction(identity, "result", "unknown", self.visual_form, error, margin, "observed", "template_match_temporally_confirmed")
                    else:
                        prediction = ObjectivePrediction(identity, "activity", "unknown", self.visual_form, error, margin, "observed", "template_match_not_yet_persistent")
                elif change >= self.change_threshold:
                    prediction = ObjectivePrediction("unknown", "activity", "unknown", self.visual_form, min(1.0, change / 255.0), 0.0, "observed", "banner_region_change")
                else:
                    prediction = ObjectivePrediction("unknown", "unknown", "unknown", self.visual_form, 0.0, 0.0, "unknown", "no_direct_objective_evidence")
            if "source_sha256=" not in str(evidence):
                evidence = f"{evidence}|source_sha256={source_hash}"
            observations.append(self._observation(prediction, timestamp, timestamp, evidence))
        return observations
