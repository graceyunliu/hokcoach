"""Detect gameplay bounds inside composited replay frames.

The detector is deliberately conservative: it trims only confidently uniform
letterbox/pillarbox borders and otherwise returns a full-frame fallback. This
prevents coordinate drift on frames containing embedded commentary overlays.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np


@dataclass(frozen=True)
class ViewportBounds:
    x: int
    y: int
    w: int
    h: int
    source_width: int
    source_height: int
    confidence: float
    method: str

    @property
    def source_dimensions(self) -> tuple[int, int]:
        return self.source_width, self.source_height

    def to_dict(self) -> dict[str, Any]:
        return {
            "x": self.x,
            "y": self.y,
            "w": self.w,
            "h": self.h,
            "source_dimensions": [self.source_width, self.source_height],
            "confidence": self.confidence,
            "method": self.method,
        }

    def viewport_to_source(self, roi: dict[str, int | float]) -> dict[str, int]:
        """Map a viewport-relative ROI into decoded source coordinates."""
        values = {key: float(roi[key]) for key in ("x", "y", "w", "h")}
        mapped = {"x": self.x + values["x"], "y": self.y + values["y"], "w": values["w"], "h": values["h"]}
        result = {key: int(round(value)) for key, value in mapped.items()}
        _validate_roi(result, self.source_width, self.source_height)
        return result

    def source_to_viewport(self, roi: dict[str, int | float]) -> dict[str, int]:
        """Map a source-relative ROI into viewport coordinates."""
        values = {key: float(roi[key]) for key in ("x", "y", "w", "h")}
        mapped = {"x": values["x"] - self.x, "y": values["y"] - self.y, "w": values["w"], "h": values["h"]}
        result = {key: int(round(value)) for key, value in mapped.items()}
        _validate_roi(result, self.w, self.h)
        return result


def _validate_roi(roi: dict[str, int], width: int, height: int) -> None:
    if roi["x"] < 0 or roi["y"] < 0 or roi["w"] <= 0 or roi["h"] <= 0 or roi["x"] + roi["w"] > width or roi["y"] + roi["h"] > height:
        raise ValueError(f"ROI {roi} is outside {width}x{height}")


def _read_image(image: np.ndarray | Path | str) -> np.ndarray:
    if isinstance(image, np.ndarray):
        value = image
    else:
        value = cv2.imread(str(image), cv2.IMREAD_COLOR)
    if value is None or value.ndim != 3 or value.shape[0] < 2 or value.shape[1] < 2:
        raise ValueError("viewport detector received an unreadable image")
    return value


def _uniform_edge(strip: np.ndarray, tolerance: float) -> bool:
    if strip.size == 0:
        return False
    pixels = strip.reshape(-1, strip.shape[-1]).astype(np.float32)
    return float(pixels.mean()) <= tolerance and float(pixels.std()) <= tolerance


def detect_gameplay_viewport(image: np.ndarray | Path | str, *, border_tolerance: float = 10.0, min_content_ratio: float = 0.55) -> ViewportBounds:
    """Return gameplay bounds, trimming only uniform dark borders.

    A full-frame result is intentional when no strong border is found. The
    confidence is lower than a detected letterbox result so callers can decide
    whether to request operator review.
    """
    frame = _read_image(image)
    height, width = frame.shape[:2]
    if not 0.0 < min_content_ratio <= 1.0:
        raise ValueError("min_content_ratio must be in (0, 1]")
    x0, y0, x1, y1 = 0, 0, width, height
    changed = False
    max_trim_x = int(width * (1.0 - min_content_ratio) / 2.0)
    max_trim_y = int(height * (1.0 - min_content_ratio) / 2.0)
    while y0 < max_trim_y and _uniform_edge(frame[y0 : y0 + 1, x0:x1], border_tolerance):
        y0 += 1
        changed = True
    while y1 - 1 > height - max_trim_y and _uniform_edge(frame[y1 - 1 : y1, x0:x1], border_tolerance):
        y1 -= 1
        changed = True
    while x0 < max_trim_x and _uniform_edge(frame[y0:y1, x0 : x0 + 1], border_tolerance):
        x0 += 1
        changed = True
    while x1 - 1 > width - max_trim_x and _uniform_edge(frame[y0:y1, x1 - 1 : x1], border_tolerance):
        x1 -= 1
        changed = True
    if not changed:
        return ViewportBounds(0, 0, width, height, width, height, 0.55, "full_frame_fallback")
    confidence = min(0.98, 0.78 + 0.2 * ((width - (x1 - x0)) / max(width, 1) + (height - (y1 - y0)) / max(height, 1)))
    return ViewportBounds(x0, y0, x1 - x0, y1 - y0, width, height, round(confidence, 6), "uniform_border_trim")


def detect_gameplay_viewport_from_frame(path: Path) -> ViewportBounds:
    return detect_gameplay_viewport(path)
