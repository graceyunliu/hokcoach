#!/usr/bin/env python3
"""Benchmark coarse FrameHopper stride on a generated short fixture video."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils import video_utils  # noqa: E402


def _make_fixture(path: Path, duration: float) -> None:
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", f"testsrc2=size=160x90:rate=12:duration={duration}",
        "-c:v", "mpeg4", str(path),
    ], check=True)


def _run(video: Path, stride: int, interval: float) -> tuple[float, int]:
    reads = 0

    def reader(_path: Path):
        nonlocal reads
        reads += 1
        return (0, 0, 0)

    started = time.perf_counter()
    video_utils.extract_death_events(
        str(video), reader, coarse_interval=interval,
        hud_crop={"x": 0, "y": 0, "w": 160, "h": 90},
        frame_skip_enabled=False, frame_skip_stride=stride,
    )
    return time.perf_counter() - started, reads


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stride", type=int, default=4)
    parser.add_argument("--duration", type=float, default=6.0)
    parser.add_argument("--interval", type=float, default=0.5)
    args = parser.parse_args()
    if args.stride < 2:
        parser.error("--stride must be at least 2")

    with tempfile.TemporaryDirectory(prefix="framehopper_bench_") as tmp:
        fixture = Path(tmp) / "fixture.mp4"
        _make_fixture(fixture, args.duration)
        baseline_sec, baseline_reads = _run(fixture, 1, args.interval)
        skipped_sec, skipped_reads = _run(fixture, args.stride, args.interval)

    print(json.dumps({
        "fixture_duration_sec": args.duration,
        "coarse_interval_sec": args.interval,
        "stride": args.stride,
        "stride_1": {"seconds": round(baseline_sec, 4), "decoded": baseline_reads},
        "stride_n": {"seconds": round(skipped_sec, 4), "decoded": skipped_reads},
        "speedup": round(baseline_sec / skipped_sec, 2),
    }, indent=2))


if __name__ == "__main__":
    main()
