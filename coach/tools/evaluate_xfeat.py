#!/usr/bin/env python3
"""Compare the current fixed-scale template matcher with an XFeat-shaped backend.

The shipped fixture evaluator is deliberately offline.  It embeds real KDA template
glyphs in synthetic region images at several scales, then measures detection accuracy
and top-left localization error.  ``xfeat_stub`` is a deterministic, scale-searching
test double: it validates the matcher interface and evaluation plumbing, but its
numbers MUST NOT be presented as XFeat measurements.

Rollback plan
-------------
If XFeat is later integrated, keep ``make_template_kda_reader`` and its current call
sites unchanged and default.  Add a new reader selected only by an explicit config
flag such as ``video.kda_matcher: xfeat`` (default: ``template``).  Construct the
XFeat reader only inside that branch; on import/model-load failure, log the failure
and construct the template reader.  Reverting the flag to ``template`` must restore
the existing path without a code or asset migration.  Do not remove template assets
until a separately reviewed, real-footage rollout has met its acceptance gates.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import cv2  # type: ignore
import numpy as np  # type: ignore


DEFAULT_TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "assets/kda_templates"
DEFAULT_SCALES = (0.5, 0.75, 1.0, 1.5, 2.0)


@dataclass(frozen=True)
class Match:
    location: tuple[int, int]
    score: float


class RegionMatcher(Protocol):
    name: str
    is_real_xfeat: bool

    def match(self, region: np.ndarray, template: np.ndarray) -> Match: ...


class TemplateMatcher:
    """The fixed-template operation currently used by the KDA classifier."""

    name = "match_template"
    is_real_xfeat = False

    def match(self, region: np.ndarray, template: np.ndarray) -> Match:
        response = cv2.matchTemplate(region, template, cv2.TM_CCOEFF_NORMED)
        _, score, _, location = cv2.minMaxLoc(response)
        return Match(location, float(score))


class XFeatStubMatcher:
    """Offline scale-search test double; not an implementation of XFeat."""

    name = "xfeat_stub"
    is_real_xfeat = False

    def __init__(self, scales: tuple[float, ...] = DEFAULT_SCALES) -> None:
        self.scales = scales

    def match(self, region: np.ndarray, template: np.ndarray) -> Match:
        best = Match((0, 0), -1.0)
        for scale in self.scales:
            width = max(2, round(template.shape[1] * scale))
            height = max(2, round(template.shape[0] * scale))
            if width > region.shape[1] or height > region.shape[0]:
                continue
            candidate = cv2.resize(template, (width, height), interpolation=cv2.INTER_AREA)
            response = cv2.matchTemplate(region, candidate, cv2.TM_CCOEFF_NORMED)
            _, score, _, location = cv2.minMaxLoc(response)
            if score > best.score:
                best = Match(location, float(score))
        return best


def _load_templates(template_dir: Path, limit: int) -> list[tuple[str, np.ndarray]]:
    templates: list[tuple[str, np.ndarray]] = []
    # One exemplar per digit prevents near-duplicate fixture variants dominating.
    for digit in range(10):
        paths = sorted(template_dir.glob(f"{digit}_*.png"))
        if not paths:
            continue
        image = cv2.imread(str(paths[0]), cv2.IMREAD_GRAYSCALE)
        if image is not None:
            templates.append((paths[0].name, image))
        if len(templates) >= limit:
            break
    if not templates:
        raise RuntimeError(f"No readable PNG templates in {template_dir}")
    return templates


def _fixture_region(template: np.ndarray, scale: float) -> tuple[np.ndarray, tuple[int, int]]:
    """Place a scaled glyph on a reproducible, mildly textured 160x120 region."""
    rng = np.random.default_rng(320)
    region = rng.integers(0, 18, size=(120, 160), dtype=np.uint8)
    width = max(2, round(template.shape[1] * scale))
    height = max(2, round(template.shape[0] * scale))
    glyph = cv2.resize(template, (width, height), interpolation=cv2.INTER_AREA)
    location = (53, 37)
    x, y = location
    region[y:y + height, x:x + width] = np.maximum(
        region[y:y + height, x:x + width], glyph)
    return region, location


def evaluate(
    template_dir: Path = DEFAULT_TEMPLATE_DIR,
    scales: tuple[float, ...] = DEFAULT_SCALES,
    limit: int = 10,
) -> dict[str, object]:
    """Run both backends on identical fixtures and return JSON-serializable metrics."""
    matchers: list[RegionMatcher] = [TemplateMatcher(), XFeatStubMatcher(scales)]
    templates = _load_templates(template_dir, limit)
    rows: list[dict[str, object]] = []
    for scale in scales:
        accum = {matcher.name: {"correct": 0, "errors": []} for matcher in matchers}
        for _, template in templates:
            region, truth = _fixture_region(template, scale)
            tolerance = max(2.0, 2.0 * scale)
            for matcher in matchers:
                match = matcher.match(region, template)
                error = float(np.hypot(
                    match.location[0] - truth[0], match.location[1] - truth[1]))
                accum[matcher.name]["errors"].append(error)
                accum[matcher.name]["correct"] += int(error <= tolerance)
        metrics = {}
        for matcher in matchers:
            values = accum[matcher.name]
            errors = values["errors"]
            metrics[matcher.name] = {
                "accuracy": values["correct"] / len(templates),
                "mean_localization_error_px": sum(errors) / len(errors),
            }
        rows.append({"scale": scale, "samples": len(templates), "matchers": metrics})
    return {
        "fixture_source": str(template_dir),
        "backend_note": "xfeat_stub is a scale-search test double, not real XFeat",
        "real_xfeat_executed": False,
        "results": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template-dir", type=Path, default=DEFAULT_TEMPLATE_DIR)
    parser.add_argument("--scales", type=float, nargs="+", default=DEFAULT_SCALES)
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()
    print(json.dumps(evaluate(args.template_dir, tuple(args.scales), args.limit), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
