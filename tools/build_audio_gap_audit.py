#!/usr/bin/env python3
"""Create deterministic no-match clips for auditing missed combat announcements."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def media_duration(path: Path) -> float:
    result = subprocess.run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(path),
    ], check=True, capture_output=True, text=True)
    return float(result.stdout.strip())


def page(rows: list[dict]) -> str:
    payload = json.dumps(rows, ensure_ascii=False).replace("</", "<\\/")
    package_id = hashlib.sha256("\n".join(
        row["candidate_id"] for row in rows).encode()).hexdigest()[:16]
    return f"""<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width\"><title>击杀播报漏报审计</title><style>
body{{font-family:-apple-system,BlinkMacSystemFont,sans-serif;max-width:1040px;margin:24px auto;padding:0 16px;background:#111;color:#eee}}video{{width:100%;max-height:62vh;background:#000}}button{{font-size:17px;margin:5px;padding:10px 16px}}.good{{background:#26734d;color:white;border:0}}.bad{{background:#a33;color:white;border:0}}.muted{{color:#aaa}}textarea{{width:100%;height:80px;background:#222;color:#eee}}
</style></head><body><h1>击杀播报漏报审计</h1><p>这些片段没有被 0.74 阈值命中。请判断片段内是否仍有击杀类系统播报。</p><video id=\"video\" controls autoplay></video><h2 id=\"progress\"></h2><div id=\"meta\" class=\"muted\"></div>
<button class=\"good\" onclick=\"save('no_kill_announcement')\">1 没有击杀播报</button><button class=\"bad\" onclick=\"save('missed_kill_announcement')\">2 有，检测漏报</button><button onclick=\"save('unreadable')\">3 听不清</button><button onclick=\"save('other_announcement')\">4 只有其他播报</button><button onclick=\"next()\">S 跳过</button>
<p><textarea id=\"note\" placeholder=\"若有漏报，请写实际播报，例如：敌方双杀、我方击杀敌人\"></textarea></p><button onclick=\"back()\">上一条</button><button onclick=\"download()\">导出 labels.jsonl</button>
<script>const rows={payload},storageKey='hokGapLabels:{package_id}',indexKey='hokGapIndex:{package_id}';let i=Number(localStorage.getItem(indexKey)||0),labels=JSON.parse(localStorage.getItem(storageKey)||'{{}}');
function persist(){{localStorage.setItem(storageKey,JSON.stringify(labels));localStorage.setItem(indexKey,String(i))}}function show(){{if(i>=rows.length)i=rows.length-1;const r=rows[i];video.src=r.clip;progress.textContent=`${{i+1}}/${{rows.length}} · 已标 ${{Object.keys(labels).length}}`;meta.textContent=`${{r.source_name}} · 原视频 ${{r.center_sec.toFixed(2)}} 秒 · 目标点位于短片 6 秒处`;note.value=labels[r.candidate_id]?.note||''}}
function save(verdict){{const r=rows[i];labels[r.candidate_id]={{schema_version:'hokcoach-audio-gap-label-v1',candidate_id:r.candidate_id,source_sha256:r.source_sha256,center_sec:r.center_sec,verdict,note:note.value,created_at:new Date().toISOString()}};persist();next()}}function next(){{if(i<rows.length-1)i++;persist();show()}}function back(){{if(i>0)i--;persist();show()}}function download(){{const text=Object.values(labels).map(JSON.stringify).join('\\n')+'\\n',a=document.createElement('a');a.href=URL.createObjectURL(new Blob([text],{{type:'application/jsonl'}}));a.download='gap-audit-labels.jsonl';a.click()}}document.addEventListener('keydown',e=>{{if(document.activeElement===note)return;if(e.key==='1')save('no_kill_announcement');else if(e.key==='2')save('missed_kill_announcement');else if(e.key==='3')save('unreadable');else if(e.key==='4')save('other_announcement');else if(e.key.toLowerCase()==='s')next();else if(e.key==='ArrowLeft')back()}});show();</script></body></html>"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--candidate-manifest", type=Path, action="append", required=True)
    parser.add_argument("--video", type=Path, action="append", required=True)
    parser.add_argument("--samples-per-video", type=int, default=4)
    parser.add_argument("--exclusion-sec", type=float, default=15.0)
    args = parser.parse_args()
    known: dict[str, list[float]] = {}
    for manifest in args.candidate_manifest:
        for row in json.loads(manifest.read_text(encoding="utf-8")):
            known.setdefault(row["source_sha256"], []).append(float(row["center_sec"]))
    out = args.output_dir.resolve(); (out / "clips").mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    for video_index, video in enumerate(args.video, 1):
        video = video.resolve(); source_hash = file_hash(video); total = media_duration(video)
        selected: list[float] = []
        for slot in range(1, args.samples_per_video + 1):
            center = total * slot / (args.samples_per_video + 1)
            attempts = 0
            while (any(abs(center - hit) < args.exclusion_sec for hit in known.get(source_hash, [])) or
                   any(abs(center - old) < 24.0 for old in selected)) and attempts < 20:
                center = (center + 17.0) % max(30.0, total - 15.0)
                center = max(8.0, center)
                attempts += 1
            selected.append(center)
        for sample_index, center in enumerate(selected, 1):
            start = max(0.0, center - 6.0); length = min(12.0, total - start)
            candidate_id = f"gap_v{video_index:02d}_{sample_index:02d}_{center:.2f}".replace(".", "_")
            clip = out / "clips" / f"{candidate_id}.mp4"
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{start:.3f}", "-i", str(video), "-t", f"{length:.3f}", "-vf", "scale='min(960,iw)':-2", "-c:v", "libx264", "-preset", "veryfast", "-crf", "25", "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", str(clip)], check=True)
            rows.append({"schema_version":"hokcoach-audio-gap-candidate-v1","candidate_id":candidate_id,"source_name":video.name,"source_path":str(video),"source_sha256":source_hash,"center_sec":round(center,3),"clip_start_sec":round(start,3),"clip_end_sec":round(start+length,3),"clip":f"clips/{clip.name}","selection":"deterministic_gap_excluding_0.74_candidates"})
    (out / "candidates.json").write_text(json.dumps(rows,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    (out / "index.html").write_text(page(rows),encoding="utf-8")
    (out / "summary.json").write_text(json.dumps({"sources":len(args.video),"candidates":len(rows),"index":str(out/'index.html')},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"sources":len(args.video),"candidates":len(rows),"index":str(out/'index.html')},ensure_ascii=False))
    return 0


if __name__ == "__main__": raise SystemExit(main())
