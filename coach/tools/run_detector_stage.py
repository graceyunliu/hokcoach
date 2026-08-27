from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Support execution as `python tools/run_detector_stage.py` from coach/.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.detector_stage import DetectorContext, run_detector
from core.observations import Observation
from core.production_detectors import PRODUCTION_DETECTORS


def load_rows(path: Path) -> list[Observation]:
    if not path.exists():
        return []
    return [Observation.from_dict(json.loads(line)) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one independent HokCoach production detector stage.")
    parser.add_argument("detector", choices=sorted(PRODUCTION_DETECTORS))
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--input-jsonl", type=Path)
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--media-hash")
    parser.add_argument("--duration-sec", type=float)
    parser.add_argument("--window", nargs=2, type=float, action="append", default=[])
    parser.add_argument("--config-json", type=Path)
    args = parser.parse_args()
    config = json.loads(args.config_json.read_text(encoding="utf-8")) if args.config_json else {}
    observations = load_rows(args.input_jsonl) if args.input_jsonl else []
    context = DetectorContext(args.source_id, args.media_hash, args.duration_sec, tuple((a, b) for a, b in args.window), tuple(observations), config)
    result = run_detector(PRODUCTION_DETECTORS[args.detector], context)
    payload = result.to_dict()
    encoded = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(encoded, encoding="utf-8")
    else:
        print(encoded, end="")
    return 0 if not result.errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
