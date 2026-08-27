"""Create provenance-safe cooldown annotations from a replay frame.

The non-interactive form is deterministic and scriptable. ``--interactive``
opens the selected frame in an OpenCV ROI selector so an operator can adjust
coordinates before saving the annotation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2

HERE = Path(__file__).resolve()
COACH_DIR = HERE.parents[1]
PROJECT_DIR = COACH_DIR.parent

LABELS = {"ready", "on_cooldown", "unknown"}
SPLITS = {"tuning", "evaluation"}


def _source_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _probe_dimensions(video: Path) -> tuple[int, int]:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x", str(video)],
        capture_output=True,
        text=True,
        check=True,
    )
    try:
        width, height = (int(value) for value in result.stdout.strip().split("x", 1))
    except (ValueError, TypeError) as exc:
        raise ValueError(f"unable to determine source dimensions for {video}") from exc
    return width, height


def _capture(video: Path, timestamp: float, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{max(0.0, timestamp):.3f}", "-i", str(video), "-frames:v", "1", str(output)],
        check=True,
    )


def _validate_roi(roi: dict[str, int], dimensions: tuple[int, int]) -> None:
    required = {"x", "y", "w", "h"}
    if set(roi) != required:
        raise ValueError("ROI must contain exactly x, y, w, and h")
    if any(not isinstance(roi[key], int) for key in required):
        raise ValueError("ROI coordinates must be integers")
    if roi["x"] < 0 or roi["y"] < 0 or roi["w"] <= 0 or roi["h"] <= 0:
        raise ValueError("ROI must have non-negative origin and positive size")
    width, height = dimensions
    if roi["x"] + roi["w"] > width or roi["y"] + roi["h"] > height:
        raise ValueError(f"ROI {roi} is outside source dimensions {dimensions}")


def _evidence_ref(source_hash: str, timestamp: float, slot: str, roi: dict[str, int], layout: str, detector_version: str) -> str:
    token = "|".join([source_hash, f"{timestamp:.3f}", slot, layout, detector_version, json.dumps(roi, sort_keys=True, separators=(",", ":"))])
    frame_id = hashlib.sha256(token.encode("utf-8")).hexdigest()[:20]
    roi_token = json.dumps(roi, sort_keys=True, separators=(",", ":"))
    return f"frame:{frame_id}|source_sha256={source_hash}|timestamp_sec={timestamp:.3f}|region=hud|roi_slot={slot}|roi={roi_token}|layout={layout}|detector_version={detector_version}"


def _append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("--timestamp", type=float, required=True)
    parser.add_argument("--output", type=Path, required=True, help="annotation JSONL output")
    parser.add_argument("--slot", required=True, help="cooldown slot, for example ultimate or summoner_flash")
    parser.add_argument("--label", choices=sorted(LABELS), default="unknown")
    parser.add_argument("--split", choices=sorted(SPLITS), required=True)
    parser.add_argument("--roi", nargs=4, type=int, metavar=("X", "Y", "W", "H"), help="HUD ROI")
    parser.add_argument("--layout-profile", default="hokcoach-hud-1280x582-v1")
    parser.add_argument("--detector-version", default="cooldown-annotation-v1")
    parser.add_argument("--frame-output", type=Path, default=None)
    parser.add_argument("--interactive", action="store_true", help="open an ROI selector before saving")
    parser.add_argument("--reject", action="store_true", help="save the example as rejected/ambiguous")
    parser.add_argument("--note", default="")
    args = parser.parse_args()

    video = args.video.resolve()
    if not video.is_file():
        parser.error(f"video does not exist: {video}")
    if args.timestamp < 0:
        parser.error("timestamp must be non-negative")
    try:
        dimensions = _probe_dimensions(video)
        source_hash = _source_hash(video)
        roi = dict(zip(("x", "y", "w", "h"), args.roi)) if args.roi else None
        with tempfile.TemporaryDirectory(prefix="hokcoach_annotation_") as tmp:
            frame_path = Path(tmp) / "frame.png"
            _capture(video, args.timestamp, frame_path)
            image = cv2.imread(str(frame_path), cv2.IMREAD_COLOR)
            if image is None:
                raise ValueError("captured frame is unreadable")
            if args.interactive:
                selected = cv2.selectROI("Cooldown annotation", image, showCrosshair=True, fromCenter=False)
                cv2.destroyAllWindows()
                x, y, width, height = (int(value) for value in selected)
                if width <= 0 or height <= 0:
                    raise ValueError("annotation was cancelled or ROI is empty")
                roi = {"x": x, "y": y, "w": width, "h": height}
            if roi is None:
                raise ValueError("--roi is required unless --interactive is used")
            _validate_roi(roi, dimensions)
            if args.frame_output:
                annotated = image.copy()
                x, y, width, height = (roi[key] for key in ("x", "y", "w", "h"))
                color = (0, 200, 0) if not args.reject and args.label != "unknown" else (0, 165, 255)
                cv2.rectangle(annotated, (x, y), (x + width, y + height), color, 3)
                cv2.putText(annotated, f"{args.slot}: {args.label}{' [REJECTED]' if args.reject else ''}", (x, max(20, y - 8)), cv2.FONT_HERSHEY_SIMPLEX, .7, color, 2, cv2.LINE_AA)
                args.frame_output.parent.mkdir(parents=True, exist_ok=True)
                cv2.imwrite(str(args.frame_output), annotated)
                frame_reference = str(args.frame_output)
            else:
                frame_reference = None
        status = "rejected" if args.reject or args.label == "unknown" and args.note.lower().startswith("ambiguous") else "accepted"
        record = {
            "schema_version": "cooldown-annotation-v1",
            "annotation_id": f"ann_{uuid.uuid4().hex[:16]}",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source_media": {"path": str(video), "sha256": source_hash, "dimensions": list(dimensions)},
            "timestamp_sec": round(args.timestamp, 3),
            "roi": roi,
            "slot": args.slot,
            "label": args.label,
            "split": args.split,
            "status": status,
            "layout_profile": args.layout_profile,
            "detector_version": args.detector_version,
            "evidence_ref": _evidence_ref(source_hash, args.timestamp, args.slot, roi, args.layout_profile, args.detector_version),
            "frame_path": frame_reference,
            "note": args.note,
        }
        _append_jsonl(args.output, record)
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as exc:
        parser.error(str(exc))
    print(json.dumps(record, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
