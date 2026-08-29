#!/usr/bin/env python3
"""Train and evaluate a small replay-mix kill-announcement audio baseline."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections import Counter
from pathlib import Path

import numpy as np


def decode_audio(path: Path, rate: int = 16000) -> np.ndarray:
    result = subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(path),
        "-vn", "-ac", "1", "-ar", str(rate), "-f", "f32le", "pipe:1",
    ], check=True, capture_output=True)
    return np.frombuffer(result.stdout, dtype="<f4").astype(np.float64)


def audio_features(path: Path, rate: int = 16000) -> np.ndarray:
    samples = decode_audio(path, rate)
    if samples.size < rate // 2:
        raise ValueError(f"audio too short: {path}")
    peak = float(np.max(np.abs(samples)))
    if peak > 0:
        samples = samples / peak
    win, hop = 640, 320
    frames = np.stack([
        samples[start:start + win]
        for start in range(0, len(samples) - win + 1, hop)
    ])
    spectrum = np.log1p(np.abs(np.fft.rfft(frames * np.hanning(win), axis=1)))
    freqs = np.fft.rfftfreq(win, 1.0 / rate)
    edges = np.geomspace(80.0, 7000.0, 33)
    bands = []
    for low, high in zip(edges[:-1], edges[1:]):
        mask = (freqs >= low) & (freqs < high)
        bands.append(spectrum[:, mask].mean(axis=1) if mask.any() else np.zeros(len(frames)))
    band_frames = np.stack(bands, axis=1)
    energy = np.sqrt(np.mean(frames * frames, axis=1) + 1e-10)[:, None]
    values = np.concatenate([band_frames, np.log1p(energy)], axis=1)
    return np.concatenate([
        values.mean(axis=0), values.std(axis=0),
        np.quantile(values, 0.10, axis=0), np.quantile(values, 0.90, axis=0),
    ]).astype(np.float64)


def sigmoid(value: np.ndarray) -> np.ndarray:
    value = np.clip(value, -30.0, 30.0)
    return 1.0 / (1.0 + np.exp(-value))


def fit_logistic(x: np.ndarray, y: np.ndarray, steps: int = 4000,
                 learning_rate: float = 0.01, l2: float = 0.05) -> tuple[np.ndarray, float]:
    weights = np.zeros(x.shape[1], dtype=np.float64)
    bias = 0.0
    positives, negatives = max(1, int(y.sum())), max(1, int((1 - y).sum()))
    sample_weights = np.where(y == 1, len(y) / (2 * positives), len(y) / (2 * negatives))
    for _ in range(steps):
        predicted = sigmoid(np.einsum("ij,j->i", x, weights) + bias)
        error = (predicted - y) * sample_weights
        gradient = np.einsum("ij,i->j", x, error) / len(y) + l2 * weights
        weights -= learning_rate * gradient
        bias -= learning_rate * float(error.mean())
    return weights, bias


def metrics(y: np.ndarray, predicted: np.ndarray) -> dict:
    tp = int(np.sum((y == 1) & (predicted == 1)))
    tn = int(np.sum((y == 0) & (predicted == 0)))
    fp = int(np.sum((y == 0) & (predicted == 1)))
    fn = int(np.sum((y == 1) & (predicted == 0)))
    return {
        "tp": tp, "tn": tn, "fp": fp, "fn": fn,
        "precision": tp / (tp + fp) if tp + fp else None,
        "recall": tp / (tp + fn) if tp + fn else None,
        "accuracy": (tp + tn) / len(y) if len(y) else None,
        "coverage": 1.0,
    }


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_rows(root: Path) -> list[dict]:
    rows: list[dict] = []
    for package, labels_name, mode in [
        ("kill_audio_batch_001", "reviewed_labels.jsonl", "candidate"),
        ("kill_audio_batch_002_boundary", "reviewed_labels.jsonl", "candidate"),
        ("kill_audio_gap_audit_001", "reviewed_labels.jsonl", "gap"),
        ("kill_audio_hard_negative_batch_001", "reviewed_labels.jsonl", "gap"),
    ]:
        folder = root / package
        candidates = {row["candidate_id"]: row for row in json.loads(
            (folder / "candidates.json").read_text(encoding="utf-8"))}
        for label in read_jsonl(folder / labels_name):
            candidate = candidates[label["candidate_id"]]
            if label["verdict"] == "unreadable":
                continue
            if mode == "candidate":
                target = 1  # Exact-class errors still contain a kill announcement.
            else:
                target = int(label["verdict"] == "missed_kill_announcement")
            rows.append({
                "candidate_id": label["candidate_id"],
                "source_name": candidate["source_name"],
                "source_sha256": candidate["source_sha256"],
                "center_sec": float(candidate["center_sec"]),
                "clip": str((folder / candidate["clip"]).resolve()),
                "target": target,
                "operator_verdict": label["verdict"],
                "operator_note": label.get("note", ""),
            })
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--labeling-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--evaluation-source-contains", default="02-03-33")
    args = parser.parse_args()
    rows = load_rows(args.labeling_root.resolve())
    features = np.stack([audio_features(Path(row["clip"])) for row in rows])
    targets = np.array([row["target"] for row in rows], dtype=np.float64)
    evaluation = np.array([
        args.evaluation_source_contains in row["source_name"] for row in rows
    ], dtype=bool)
    tuning = ~evaluation
    mean = features[tuning].mean(axis=0)
    scale = features[tuning].std(axis=0)
    scale[scale < 1e-4] = 1.0
    normalized = np.clip((features - mean) / scale, -8.0, 8.0)
    weights, bias = fit_logistic(normalized[tuning], targets[tuning])
    probability = sigmoid(np.einsum("ij,j->i", normalized, weights) + bias)
    predicted = (probability >= 0.5).astype(np.float64)
    for index, row in enumerate(rows):
        row["split"] = "evaluation" if evaluation[index] else "tuning"
        row["probability"] = round(float(probability[index]), 6)
        row["predicted"] = int(predicted[index])
    out = args.output_dir.resolve(); out.mkdir(parents=True, exist_ok=True)
    model_id = hashlib.sha256(json.dumps([
        [row["candidate_id"], row["source_sha256"], row["target"]] for row in rows
    ], sort_keys=True).encode()).hexdigest()[:16]
    np.savez_compressed(out / "kill_audio_binary_v1.npz", mean=mean, scale=scale,
                        weights=weights, bias=np.array([bias]))
    report = {
        "schema_version": "hokcoach-kill-audio-binary-baseline-v1",
        "model_id": model_id,
        "feature_version": "log-spectrum-band-statistics-v1",
        "threshold": 0.5,
        "dataset": {
            "samples": len(rows),
            "labels": dict(Counter("positive" if row["target"] else "negative" for row in rows)),
            "tuning_samples": int(tuning.sum()),
            "evaluation_samples": int(evaluation.sum()),
            "evaluation_source_rule": args.evaluation_source_contains,
        },
        "tuning_metrics": metrics(targets[tuning], predicted[tuning]),
        "evaluation_metrics": metrics(targets[evaluation], predicted[evaluation]),
        "production_enabled": False,
        "limitations": [
            "three source recordings only", "binary presence only; no semantic class",
            "candidate clips contain variable event position and sometimes multiple announcements",
            "single held-out source is insufficient for production generalization",
        ],
        "predictions": rows,
    }
    (out / "evaluation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("model_id", "dataset", "tuning_metrics", "evaluation_metrics", "production_enabled")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
