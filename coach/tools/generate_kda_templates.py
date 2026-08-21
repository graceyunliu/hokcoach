#!/usr/bin/env python3
"""从人工核对过的真实回放帧重建 AGE-136 KDA 字形库。

在仓库根目录运行：
    python coach/tools/generate_kda_templates.py

Replay/*.MP4 是本地素材、不进 git；生成的 32x32 PNG 会进 git。
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import cv2  # type: ignore

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "coach"))

from utils import video_utils  # noqa: E402

# (replay index, timestamp seconds, visually verified K/D/A).
# Each anchor is sampled at five nearby moments to capture compression/background variants.
GROUND_TRUTH = (
    (0, 240, (0, 0, 0)),
    (0, 360, (1, 0, 0)),
    (0, 420, (2, 0, 2)),
    (0, 480, (2, 0, 3)),
    (0, 540, (3, 1, 4)),
    (0, 600, (4, 1, 6)),
    (0, 660, (4, 1, 7)),
    (0, 680, (4, 1, 7)),
    (0, 720, (6, 2, 9)),
    (0, 780, (6, 3, 9)),
    (0, 960, (8, 4, 9)),
    (1, 600, (2, 2, 2)),
    (1, 780, (2, 4, 3)),
    (2, 840, (3, 5, 5)),
)
# Anchors are visually verified at exactly ``timestamp``. Sample just after them:
# sampling before an anchor can cross the stat transition that produced its label.
OFFSETS = (0, 1, 2, 3, 4)
def main() -> int:
    videos = sorted((ROOT / "Replay").glob("*.MP4"))
    if len(videos) < 3:
        raise SystemExit("need the three local Replay/*.MP4 recordings")
    output = ROOT / "coach" / "assets" / "kda_templates"
    output.mkdir(parents=True, exist_ok=True)
    for old in output.glob("[0-9]_*.png"):
        old.unlink()

    counts = {digit: 0 for digit in range(10)}
    with tempfile.TemporaryDirectory(prefix="age136_templates_") as tmp:
        frame = Path(tmp) / "hud.png"
        for video_idx, anchor, kda in GROUND_TRUTH:
            for offset in OFFSETS:
                subprocess.run([
                    "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-ss", str(anchor + offset), "-i", str(videos[video_idx]),
                    "-frames:v", "1", "-vf", "crop=650:140:1650:0", str(frame),
                ], check=True)
                image = cv2.imread(str(frame))
                for slot, digit in zip(video_utils.DEFAULT_KDA_SLOTS, kda):
                    x0, y0, x1, y1 = slot
                    glyphs = video_utils._extract_slot_glyphs(image[y0:y1, x0:x1])
                    if len(glyphs) != 1:
                        continue
                    name = f"{digit}_{counts[digit]:02d}_v{video_idx}_{anchor + offset}.png"
                    cv2.imwrite(str(output / name), glyphs[0])
                    counts[digit] += 1

    if min(counts.values()) < 5:
        raise SystemExit(f"insufficient exemplars (need >=5 each): {counts}")
    print("generated", counts, "in", output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
