"""Deterministic, calibration-backed tower-state recognition.

Each configured tower has its own minimap ROI and present/destroyed references.
No global whole-minimap classification is used for production tower identities.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageOps, ImageStat


@dataclass(frozen=True)
class TowerRecognition:
    state: str
    status: str
    confidence: float
    margin: float
    template: str | None
    reason: str
    tower_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"state": self.state, "status": self.status, "confidence": self.confidence, "margin": self.margin, "template": self.template, "reason": self.reason, "tower_id": self.tower_id}


class TowerTemplateRecognizer:
    def __init__(self, present_template: Path | None = None, destroyed_template: Path | None = None, *, tower_templates: dict[str, dict[str, Any]] | None = None, max_error: float = 0.16, min_margin: float = 0.03, size: tuple[int, int] = (96, 96), layout_profile: str = "unversioned", expected_minimap_size: tuple[int, int] | None = None) -> None:
        self.max_error = float(max_error)
        self.min_margin = float(min_margin)
        self.size = size
        self.layout_profile = str(layout_profile)
        self.expected_minimap_size = expected_minimap_size
        self._entries: dict[str, tuple[Path, Path, dict[str, int]]] = {}
        if tower_templates:
            for tower_id, raw in tower_templates.items():
                roi = raw.get("roi") if isinstance(raw, dict) else None
                if not isinstance(roi, dict) or not {"x", "y", "w", "h"} <= roi.keys():
                    raise ValueError(f"tower ROI missing for {tower_id}")
                present = Path(raw["present_template"])
                destroyed = Path(raw["destroyed_template"])
                if not present.is_file() or not destroyed.is_file():
                    raise FileNotFoundError(f"calibrated templates missing for {tower_id}")
                parsed_roi = {key: int(roi[key]) for key in ("x", "y", "w", "h")}
                if parsed_roi["x"] < 0 or parsed_roi["y"] < 0 or parsed_roi["w"] <= 0 or parsed_roi["h"] <= 0:
                    raise ValueError(f"invalid non-positive or negative tower ROI for {tower_id}")
                self._entries[str(tower_id)] = (present, destroyed, parsed_roi)
        elif present_template is not None and destroyed_template is not None:
            if not Path(present_template).is_file() or not Path(destroyed_template).is_file():
                raise FileNotFoundError("both calibrated tower templates are required")
            self._entries["tower"] = (Path(present_template), Path(destroyed_template), {"x": 0, "y": 0, "w": 0, "h": 0})
        else:
            raise ValueError("tower-specific templates are required")
        fingerprint = {"recognizer_code": "tower-template-v2", "layout_profile": self.layout_profile, "expected_minimap_size": self.expected_minimap_size, "max_error": self.max_error, "min_margin": self.min_margin, "size": self.size, "towers": {tower_id: {"roi": roi, "present_sha256": hashlib.sha256(present.read_bytes()).hexdigest(), "destroyed_sha256": hashlib.sha256(destroyed.read_bytes()).hexdigest()} for tower_id, (present, destroyed, roi) in sorted(self._entries.items())}}
        self.calibration_version = "cal-" + hashlib.sha256(json.dumps(fingerprint, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()[:20]

    def _normalize(self, image: Image.Image) -> Image.Image:
        return ImageOps.autocontrast(ImageOps.grayscale(image)).resize(self.size)

    def _error(self, image: Image.Image, template: Image.Image) -> float:
        diff = ImageChops.difference(image, template)
        return float(ImageStat.Stat(diff).mean[0]) / 255.0

    def _recognize_image(self, image: Image.Image, present_path: Path, destroyed_path: Path, tower_id: str) -> TowerRecognition:
        normalized = self._normalize(image)
        with Image.open(present_path) as present, Image.open(destroyed_path) as destroyed:
            scored = sorted(((self._error(normalized, self._normalize(present)), "present"), (self._error(normalized, self._normalize(destroyed)), "destroyed")))
        best_error, state = scored[0]
        margin = scored[1][0] - best_error
        confidence = max(0.0, min(1.0, 1.0 - best_error))
        if best_error > self.max_error:
            return TowerRecognition("unknown", "unknown", 0.0, margin, None, "template_error_above_threshold", tower_id)
        if margin < self.min_margin:
            return TowerRecognition("unknown", "unknown", 0.0, margin, None, "template_margin_below_threshold", tower_id)
        return TowerRecognition(state, "observed", confidence, margin, state, "calibrated_roi_template_match", tower_id)

    def recognize_all(self, minimap_path: Path) -> dict[str, TowerRecognition]:
        results: dict[str, TowerRecognition] = {}
        with Image.open(minimap_path) as minimap:
            width, height = minimap.size
            if self.expected_minimap_size is not None and (width, height) != tuple(self.expected_minimap_size):
                return {tower_id: TowerRecognition("unknown", "unknown", 0.0, 0.0, None, "layout_dimension_mismatch", tower_id) for tower_id in self._entries}
            for tower_id, (present, destroyed, roi) in self._entries.items():
                if roi["x"] + roi["w"] > width or roi["y"] + roi["h"] > height:
                    results[tower_id] = TowerRecognition("unknown", "unknown", 0.0, 0.0, None, "roi_out_of_bounds", tower_id)
                    continue
                crop = minimap.crop((roi["x"], roi["y"], roi["x"] + roi["w"], roi["y"] + roi["h"]))
                try:
                    results[tower_id] = self._recognize_image(crop, present, destroyed, tower_id)
                finally:
                    crop.close()
        return results

    def recognize(self, crop_path: Path) -> TowerRecognition:
        """Backward-compatible single-template call; use ``recognize_all`` for production."""
        if len(self._entries) != 1:
            raise ValueError("recognize() is only valid for one configured tower")
        tower_id, (present, destroyed, roi) = next(iter(self._entries.items()))
        with Image.open(crop_path) as image:
            return self._recognize_image(image, present, destroyed, tower_id)
