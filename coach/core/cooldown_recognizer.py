from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from core.observations import Observation


VERSION = "cooldown-template-v1"
REQUIRED_STATES = frozenset({"ready", "on_cooldown"})


class CooldownConfigurationError(ValueError):
    """Raised when cooldown calibration cannot be used safely."""


@dataclass(frozen=True)
class Prediction:
    slot: str
    state: str
    score: float
    margin: float
    status: str
    evidence_path: str


class CooldownTemplateRecognizer:
    """Deterministic, layout-bound cooldown recognizer.

    The recognizer is deliberately conservative. It classifies only a readable
    crop that matches a validated layout and clears both the error and margin
    thresholds. Everything else is represented as an explicit abstention.
    """

    def __init__(
        self,
        templates: dict[str, dict[str, Path]],
        *,
        max_error: float = 0.28,
        min_margin: float = 0.02,
        min_mean_by_slot: dict[str, float] | None = None,
        version: str = VERSION,
        layout_profile: str = "unversioned",
        expected_source_dimensions: tuple[int, int] | list[int] | None = None,
        source_compatibility: dict[str, Any] | None = None,
        rois: dict[str, dict[str, int]] | None = None,
    ):
        self.templates = {
            str(slot): {str(state): Path(path) for state, path in states.items()}
            for slot, states in (templates or {}).items()
        }
        self.max_error = float(max_error)
        self.min_margin = float(min_margin)
        self.min_mean_by_slot = {str(k): float(v) for k, v in (min_mean_by_slot or {}).items()}
        self.implementation_version = str(version)
        self.layout_profile = str(layout_profile)
        self.expected_source_dimensions = _validate_dimensions(expected_source_dimensions, required=False)
        self.source_compatibility = dict(source_compatibility or {})
        self.rois = _normalize_rois(rois or {})
        self._validate_configuration()
        self._features = {
            slot: {state: self._feature(path) for state, path in states.items()}
            for slot, states in self.templates.items()
        }
        self.calibration_fingerprint = self._fingerprint()
        self.version = f"{self.implementation_version}:{self.calibration_fingerprint}"

    def _validate_configuration(self) -> None:
        if not self.templates:
            raise CooldownConfigurationError("cooldown templates mapping is required")
        if not self.layout_profile:
            raise CooldownConfigurationError("cooldown layout_profile is required")
        if not math.isfinite(self.max_error) or self.max_error < 0:
            raise CooldownConfigurationError("cooldown max_error must be a finite nonnegative number")
        if not math.isfinite(self.min_margin) or self.min_margin < 0:
            raise CooldownConfigurationError("cooldown min_margin must be a finite nonnegative number")
        for slot, threshold in self.min_mean_by_slot.items():
            if not math.isfinite(threshold) or threshold < 0:
                raise CooldownConfigurationError(f"invalid luminance threshold for {slot}")
        if self.expected_source_dimensions is not None:
            width, height = self.expected_source_dimensions
            for slot, roi in self.rois.items():
                _validate_roi(roi, width, height, slot)
        for slot, states in self.templates.items():
            missing = REQUIRED_STATES - set(states)
            if missing:
                raise CooldownConfigurationError(
                    f"cooldown slot {slot} is missing required states: {sorted(missing)}"
                )
            for state, path in states.items():
                if not path.is_file() or not path.stat().st_size:
                    raise CooldownConfigurationError(f"missing or empty cooldown template: {path}")
                if cv2.imread(str(path), cv2.IMREAD_GRAYSCALE) is None:
                    raise CooldownConfigurationError(f"unreadable cooldown template: {path}")
        if self.rois and set(self.rois) != set(self.templates):
            raise CooldownConfigurationError("cooldown templates and rois must cover the same skills")
        rules = self.source_compatibility
        if not isinstance(rules, dict):
            raise CooldownConfigurationError("source_compatibility rules are required")
        allowed_hashes = rules.get("allowed_media_sha256") or rules.get("source_media_sha256")
        if allowed_hashes is not None and not isinstance(allowed_hashes, (str, list, tuple)):
            raise CooldownConfigurationError("allowed source media hashes must be a string or list")
        allowed_dimensions = rules.get("allowed_source_dimensions")
        if allowed_dimensions is not None:
            if not isinstance(allowed_dimensions, (list, tuple)):
                raise CooldownConfigurationError("allowed source dimensions must be a list")
            for dimensions in allowed_dimensions:
                _validate_dimensions(dimensions, required=True)
        allowed_layouts = rules.get("allowed_layout_profiles")
        if allowed_layouts is not None and not isinstance(allowed_layouts, (list, tuple, set)):
            raise CooldownConfigurationError("allowed layout profiles must be a list")

    @staticmethod
    def _feature(path: Path) -> np.ndarray:
        image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if image is None:
            raise CooldownConfigurationError(f"unreadable cooldown template: {path}")
        return cv2.resize(image, (64, 64), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0

    def _fingerprint(self) -> str:
        payload = {
            "recognizer_code_version": VERSION,
            "implementation_version": self.implementation_version,
            "layout_profile": self.layout_profile,
            "expected_source_dimensions": self.expected_source_dimensions,
            "source_compatibility": self.source_compatibility,
            "rois": self.rois,
            "supported_slots_and_states": {
                slot: sorted(states) for slot, states in sorted(self.templates.items())
            },
            "template_content_hashes": {
                slot: {
                    state: hashlib.sha256(path.read_bytes()).hexdigest()
                    for state, path in sorted(states.items())
                }
                for slot, states in sorted(self.templates.items())
            },
            "thresholds": {
                "max_error": self.max_error,
                "min_margin": self.min_margin,
                "min_mean_by_slot": self.min_mean_by_slot,
            },
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:16]

    def is_source_compatible(self, source_hash: str | None, source_dimensions: tuple[int, int] | None) -> bool:
        """Return whether a decoded source is allowed by this calibration."""
        if self.expected_source_dimensions is not None and tuple(source_dimensions or ()) != self.expected_source_dimensions:
            return False
        rules = self.source_compatibility
        allowed_hashes = rules.get("allowed_media_sha256") or rules.get("source_media_sha256")
        if isinstance(allowed_hashes, str):
            allowed_hashes = [allowed_hashes]
        if allowed_hashes and source_hash not in {str(value) for value in allowed_hashes}:
            return False
        allowed_dimensions = rules.get("allowed_source_dimensions")
        if allowed_dimensions is not None and tuple(source_dimensions or ()) not in {
            tuple(int(item) for item in dimensions) for dimensions in allowed_dimensions
        }:
            return False
        allowed_layouts = rules.get("allowed_layout_profiles")
        if allowed_layouts and self.layout_profile not in {str(value) for value in allowed_layouts}:
            return False
        return True

    def _unreadable_observation(
        self,
        slot: str,
        *,
        start_sec: float,
        end_sec: float,
        evidence_ref: str,
        status: str = "unreadable",
    ) -> Observation:
        prediction = Prediction(str(slot), "unknown", 0.0, 0.0, status, evidence_ref)
        return self._observation(prediction, start_sec, end_sec, evidence_ref)

    def recognize(
        self,
        image_path: Path,
        *,
        slot: str,
        start_sec: float,
        end_sec: float,
        evidence_ref: str | None = None,
    ) -> tuple[Prediction, Observation]:
        image = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
        if image is None or slot not in self._features:
            prediction = Prediction(str(slot), "unknown", 0.0, 0.0, "unreadable", str(image_path))
        else:
            prediction = self._predict(image, str(slot), str(image_path))
        obs = self._observation(prediction, start_sec, end_sec, evidence_ref or str(image_path))
        return prediction, obs

    def recognize_hud(
        self,
        hud_path: Path,
        *,
        slot: str,
        roi: dict[str, int],
        start_sec: float,
        end_sec: float,
        evidence_ref: str,
        source_dimensions: tuple[int, int] | None = None,
    ) -> Observation:
        slot = str(slot)
        image = cv2.imread(str(hud_path), cv2.IMREAD_GRAYSCALE)
        if image is None:
            return self._unreadable_observation(slot, start_sec=start_sec, end_sec=end_sec, evidence_ref=evidence_ref)
        if self.expected_source_dimensions is not None:
            expected_w, expected_h = self.expected_source_dimensions
            if source_dimensions is not None and tuple(source_dimensions) != (expected_w, expected_h):
                return self._unreadable_observation(slot, start_sec=start_sec, end_sec=end_sec, evidence_ref=evidence_ref)
            if image.shape[1] != expected_w or image.shape[0] != expected_h:
                return self._unreadable_observation(slot, start_sec=start_sec, end_sec=end_sec, evidence_ref=evidence_ref)
        try:
            normalized_roi = _normalize_roi(roi, slot)
            if self.expected_source_dimensions is not None:
                _validate_roi(normalized_roi, *self.expected_source_dimensions, slot)
        except CooldownConfigurationError:
            return self._unreadable_observation(slot, start_sec=start_sec, end_sec=end_sec, evidence_ref=evidence_ref)
        x, y, w, h = (normalized_roi[key] for key in ("x", "y", "w", "h"))
        if x + w > image.shape[1] or y + h > image.shape[0]:
            return self._unreadable_observation(slot, start_sec=start_sec, end_sec=end_sec, evidence_ref=evidence_ref)
        if slot not in self._features:
            return self._unreadable_observation(slot, start_sec=start_sec, end_sec=end_sec, evidence_ref=evidence_ref)
        prediction = self._predict(image[y : y + h, x : x + w], slot, str(hud_path))
        return self._observation(prediction, start_sec, end_sec, evidence_ref)

    def _predict(self, image: np.ndarray, slot: str, evidence_path: str) -> Prediction:
        if image.size == 0:
            return Prediction(slot, "unknown", 0.0, 0.0, "unreadable", evidence_path)
        feature = cv2.resize(image, (64, 64), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0
        source_mean = float(image.mean())
        scores = {
            state: float(np.mean(np.abs(feature - template)))
            for state, template in self._features[slot].items()
        }
        ordered = sorted(scores.items(), key=lambda item: item[1])
        best_state, best_error = ordered[0]
        second_error = ordered[1][1] if len(ordered) > 1 else 1.0
        margin = second_error - best_error
        valid_luminance = source_mean >= self.min_mean_by_slot.get(slot, 0.0)
        status = "observed" if valid_luminance and best_error <= self.max_error and margin >= self.min_margin else "unknown"
        return Prediction(slot, best_state if status == "observed" else "unknown", best_error, margin, status, evidence_path)

    def _observation(self, prediction: Prediction, start_sec: float, end_sec: float, evidence_ref: str) -> Observation:
        value = {"skill": prediction.slot, "state": prediction.state}
        confidence = round(max(0.0, min(1.0, 1.0 - prediction.score)), 6) if prediction.status == "observed" else 0.0
        return Observation.create(
            obs_type="cooldown_ui",
            start_sec=start_sec,
            end_sec=end_sec,
            subject="player",
            value=value,
            confidence=confidence,
            detector="cooldown_visual",
            detector_version=self.version,
            evidence_refs=(evidence_ref,),
            status=prediction.status,
        )


def _validate_dimensions(value: Any, *, required: bool) -> tuple[int, int] | None:
    if value is None:
        if required:
            raise CooldownConfigurationError("expected_source_dimensions must contain exactly two positive integers")
        return None
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise CooldownConfigurationError("expected_source_dimensions must contain exactly two positive integers")
    if any(isinstance(item, bool) or not isinstance(item, int) or item <= 0 for item in value):
        raise CooldownConfigurationError("expected_source_dimensions must contain exactly two positive integers")
    return int(value[0]), int(value[1])


def _normalize_roi(roi: Any, slot: str) -> dict[str, int]:
    if not isinstance(roi, dict):
        raise CooldownConfigurationError(f"invalid ROI for {slot}")
    try:
        values = {key: roi[key] for key in ("x", "y", "w", "h")}
    except KeyError as exc:
        raise CooldownConfigurationError(f"ROI for {slot} must contain x, y, w, h") from exc
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in values.values()):
        raise CooldownConfigurationError(f"ROI for {slot} must contain numeric coordinates")
    if any(float(value) != int(value) for value in values.values()):
        raise CooldownConfigurationError(f"ROI for {slot} must contain integer coordinates")
    return {key: int(value) for key, value in values.items()}


def _normalize_rois(rois: dict[str, dict[str, int]]) -> dict[str, dict[str, int]]:
    return {str(slot): _normalize_roi(roi, str(slot)) for slot, roi in rois.items()}


def _validate_roi(roi: dict[str, int], width: int, height: int, slot: str) -> None:
    if roi["x"] < 0 or roi["y"] < 0 or roi["w"] <= 0 or roi["h"] <= 0:
        raise CooldownConfigurationError(f"ROI for {slot} must be nonnegative with positive width and height")
    if roi["x"] + roi["w"] > width or roi["y"] + roi["h"] > height:
        raise CooldownConfigurationError(f"ROI for {slot} is outside expected source dimensions")


def load_cooldown_manifest(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CooldownConfigurationError(f"unable to load cooldown calibration manifest: {path}") from exc
    if not isinstance(data, dict):
        raise CooldownConfigurationError("cooldown calibration manifest must be an object")
    required = (
        "schema_version",
        "source_media_sha256",
        "layout_profile",
        "expected_source_dimensions",
        "source_compatibility",
        "roi_profiles",
        "threshold_policy",
        "templates",
        "candidate_window_only",
        "tuning_timestamps_sec",
        "evaluation_timestamps_sec",
        "evaluation_cases",
    )
    missing = [key for key in required if key not in data]
    if missing:
        raise CooldownConfigurationError(f"cooldown calibration manifest is missing: {', '.join(missing)}")
    _validate_dimensions(data["expected_source_dimensions"], required=True)
    if not isinstance(data["source_compatibility"], dict):
        raise CooldownConfigurationError("manifest source_compatibility must be an object")
    if not isinstance(data["roi_profiles"], dict) or not data["roi_profiles"]:
        raise CooldownConfigurationError("manifest roi_profiles are required")
    if not isinstance(data["templates"], dict) or set(data["templates"]) != set(data["roi_profiles"]):
        raise CooldownConfigurationError("manifest templates and roi_profiles must cover the same skills")
    for slot, states in data["templates"].items():
        if not isinstance(states, dict) or not REQUIRED_STATES.issubset(states):
            raise CooldownConfigurationError(f"manifest slot {slot} must define ready and on_cooldown templates")
    _normalize_rois(data["roi_profiles"])
    if data["candidate_window_only"] is not True:
        raise CooldownConfigurationError("manifest cooldown recognition must be candidate-window-only")
    if not isinstance(data["evaluation_cases"], list):
        raise CooldownConfigurationError("manifest evaluation_cases must be a list")
    return data


def evaluate(recognizer: CooldownTemplateRecognizer, cases: list[dict[str, Any]]) -> dict[str, Any]:
    confusion: dict[str, dict[str, int]] = {}
    abstentions = 0
    predictions = []
    for case in cases:
        prediction, _ = recognizer.recognize(
            Path(case["image"]),
            slot=case["slot"],
            start_sec=case.get("timestamp_sec", 0.0),
            end_sec=case.get("timestamp_sec", 0.0),
            evidence_ref=case.get("evidence_ref"),
        )
        predicted = prediction.state if prediction.status == "observed" else "abstain"
        label = case["label"]
        confusion.setdefault(label, {})[predicted] = confusion.setdefault(label, {}).get(predicted, 0) + 1
        abstentions += int(predicted == "abstain")
        predictions.append(
            {
                "image": case["image"],
                "slot": case["slot"],
                "label": label,
                "expected_prediction": case.get("expected_prediction", label),
                "prediction": predicted,
                "score_error": prediction.score,
                "margin": prediction.margin,
                "status": prediction.status,
            }
        )
    total = len(cases)
    classified = [row for row in predictions if row["prediction"] != "abstain"]
    classified_correct = sum(
        1
        for row, case in zip(predictions, cases)
        if row["prediction"] != "abstain"
        and row["prediction"] == case.get("expected_prediction", case["label"])
    )
    agreement = sum(
        1 for row, case in zip(predictions, cases) if row["prediction"] == case.get("expected_prediction", case["label"])
    )
    return {
        "total": total,
        "classified": len(classified),
        "classified_correct": classified_correct,
        "classified_accuracy": classified_correct / len(classified) if classified else None,
        "abstentions": abstentions,
        "coverage": len(classified) / total if total else None,
        "abstention_correct": sum(
            1 for row, case in zip(predictions, cases)
            if case.get("expected_prediction") == "abstain" and row["prediction"] == "abstain"
        ),
        "expected_behavior_agreement": agreement,
        "expected_behavior_agreement_rate": agreement / total if total else None,
        "confusion": confusion,
        "predictions": predictions,
        "detector_version": recognizer.version,
        "calibration_fingerprint": recognizer.calibration_fingerprint,
    }
