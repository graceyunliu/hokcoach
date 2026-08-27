# Cooldown Operator Workflow

This workflow prepares **candidate evidence** for cooldown calibration without treating corpus commentary as visual ground truth. It is intentionally bounded to a canonical source hash and does not enable the production detector.

## Annotate a frame

Capture one timestamp, assign a supported slot and split, and save a provenance record plus an overlay image:

```bash
PYTHONPATH=coach coach/.venv/bin/python coach/tools/annotate_cooldown.py \
  "Seed Videos/hokclass_001_QK9QwHo1RhY.webm" \
  --timestamp 174 \
  --slot ultimate \
  --label ready \
  --split evaluation \
  --roi 1040 450 120 120 \
  --frame-output /tmp/ultimate_174_overlay.png \
  --output /tmp/cooldown_annotations.jsonl
```

Use `--interactive` instead of `--roi` to open an OpenCV ROI selector. Use `--reject` for an ambiguous or otherwise unusable example. Rejected records remain in the annotation log for auditability and are never passed to evaluation as labels.

Each accepted record contains the canonical media SHA-256, source dimensions, timestamp, slot, ROI, label, split, layout profile, detector version, and a self-describing evidence reference. Unknown labels are valid abstentions; they do not imply a ready or on-cooldown state.

## Ingest candidate windows

Candidate windows come from the corpus calibration manifest. Ingestion verifies that the actual video hash matches the manifest, removes out-of-range candidates, merges overlapping windows, extracts only selected frames, runs the configured recognizer, and writes JSONL predictions plus metrics:

```bash
PYTHONPATH=coach coach/.venv/bin/python coach/tools/ingest_cooldown_fixtures.py \
  --video "Seed Videos/hokclass_001_QK9QwHo1RhY.webm" \
  --candidate-manifest data/evaluation/replay_seeds/calibration/hokclass_001_calibration_manifest.json \
  --cooldown-manifest data/evaluation/replay_seeds/calibration/hokclass_001/cooldowns/cooldown_calibration_manifest.json \
  --annotations /tmp/cooldown_annotations.jsonl \
  --output-dir /tmp/cooldown_fixture_run
```

The output directory contains `predictions.jsonl`, `metrics.json`, and an optional `evidence/` directory when `--retain-crops` is supplied. Re-running with the same source, windows, annotations, and detector fingerprint reports `cache_hit: true` and avoids re-decoding.

## Safety rules

> Candidate windows are hints, not labels. A source-hash mismatch quarantines the input and stops ingestion.

The recognizer rejects malformed manifests, missing or corrupt templates, unsupported dimensions, invalid ROIs, missing ready/on-cooldown states, incompatible layouts, and overlapping tuning/evaluation timestamps. Temporal fusion preserves unknown and unreadable states as boundaries and rejects implausible one-second flicker. Production cooldown recognition remains disabled by default until independent Video 2 validation is available.
