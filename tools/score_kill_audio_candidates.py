#!/usr/bin/env python3
"""Score an existing clip manifest with the experimental binary audio model."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

import numpy as np


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--trainer", type=Path, required=True)
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location("kill_audio_trainer", args.trainer.resolve())
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    model = np.load(args.model.resolve())
    root = args.candidates.resolve().parent
    rows = json.loads(args.candidates.read_text(encoding="utf-8"))
    for row in rows:
        feature = module.audio_features(root / row["clip"])
        normalized = np.clip((feature - model["mean"]) / model["scale"], -8.0, 8.0)
        logit = float(np.einsum("j,j->", normalized, model["weights"]) + model["bias"][0])
        row["binary_kill_probability"] = round(float(module.sigmoid(np.array([logit]))[0]), 6)
        row["binary_model_id"] = args.model.stem
    rows.sort(key=lambda row: (-row["binary_kill_probability"], row["candidate_id"]))
    args.output.resolve().write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"candidates": len(rows), "highest_probability": rows[0]["binary_kill_probability"] if rows else None}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
