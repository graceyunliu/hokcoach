#!/usr/bin/env python3
"""Evaluate AGE-248/249 audio timelines against small local annotations.

Annotation JSON schema::

  {"recordings": [{"video": "Replay/match.MP4", "events": [
    {"ts": 101.1, "event": "multi_kill_2", "perspective": "enemy",
     "death_ts": 100.0, "relationship": "possible_direct_relationship"}
  ]}]}

The annotations and copyrighted recordings remain local; only this evaluator and its
synthetic regression tests are shipped.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.video_utils import build_audio_event_timeline, relate_audio_events_to_death


def score_events(predicted: list[dict[str, Any]], expected: list[dict[str, Any]],
                 tolerance_sec: float = 1.5) -> dict[str, Any]:
    """Greedy deterministic matching by semantic event, perspective, and time."""
    used: set[int] = set()
    counts: dict[str, dict[str, int]] = defaultdict(
        lambda: {"tp": 0, "fp": 0, "fn": 0})
    relationship_correct = relationship_total = 0
    for truth in sorted(expected, key=lambda item: float(item["ts"])):
        candidates = [
            (abs(float(item["ts"]) - float(truth["ts"])), index, item)
            for index, item in enumerate(predicted)
            if index not in used and item.get("event") == truth.get("event")
            and item.get("perspective") == truth.get("perspective")
            and abs(float(item["ts"]) - float(truth["ts"])) <= tolerance_sec
        ]
        label = str(truth["event"])
        if not candidates:
            counts[label]["fn"] += 1
            continue
        _, index, matched = min(candidates, key=lambda row: (row[0], row[1]))
        used.add(index)
        counts[label]["tp"] += 1
        if truth.get("relationship") and truth.get("death_ts") is not None:
            relationship_total += 1
            related = relate_audio_events_to_death(
                [matched], float(truth["death_ts"]))
            if related and related[0]["relationship"] == truth["relationship"]:
                relationship_correct += 1
    for index, item in enumerate(predicted):
        if index not in used:
            counts[str(item["event"])]["fp"] += 1
    per_class = {}
    for label, row in sorted(counts.items()):
        tp, fp, fn = row["tp"], row["fp"], row["fn"]
        per_class[label] = {
            **row,
            "precision": tp / (tp + fp) if tp + fp else None,
            "recall": tp / (tp + fn) if tp + fn else None,
        }
    return {
        "per_class": per_class,
        "relationship_accuracy": (
            relationship_correct / relationship_total if relationship_total else None),
        "relationship_samples": relationship_total,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("annotations", type=Path)
    parser.add_argument("--threshold", type=float, default=0.78)
    parser.add_argument("--tolerance", type=float, default=1.5)
    args = parser.parse_args()
    payload = json.loads(args.annotations.read_text(encoding="utf-8"))
    output = []
    for recording in payload.get("recordings", []):
        started = time.monotonic()
        predicted = build_audio_event_timeline(
            recording["video"], similarity_threshold=args.threshold)
        elapsed = time.monotonic() - started
        metrics = score_events(predicted, recording.get("events", []), args.tolerance)
        output.append({"video": recording["video"], "runtime_sec": elapsed,
                       "predicted_events": len(predicted), **metrics})
    print(json.dumps({"recordings": output}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
