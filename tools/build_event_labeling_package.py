#!/usr/bin/env python3
"""Build a compact, browser-based labeling package from local replay videos."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import subprocess
import sys
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        check=True, capture_output=True, text=True,
    )
    return float(result.stdout.strip())


def grouped(events: list[dict], gap: float = 2.0) -> list[list[dict]]:
    groups: list[list[dict]] = []
    for event in sorted(events, key=lambda row: float(row["ts"])):
        if groups and float(event["ts"]) - float(groups[-1][-1]["ts"]) <= gap:
            groups[-1].append(event)
        else:
            groups.append([event])
    return groups


def render_html(rows: list[dict]) -> str:
    payload = json.dumps(rows, ensure_ascii=False).replace("</", "<\\/")
    package_id = hashlib.sha256("\n".join(
        row["candidate_id"] for row in rows).encode("utf-8")).hexdigest()[:16]
    return f"""<!doctype html>
<html lang=\"zh-CN\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width\">
<title>HokCoach 事件标注</title><style>
body{{font-family:-apple-system,BlinkMacSystemFont,sans-serif;max-width:1040px;margin:24px auto;padding:0 16px;background:#111;color:#eee}}
video{{width:100%;max-height:62vh;background:#000}} button{{font-size:17px;margin:5px;padding:10px 16px}}
.primary{{background:#2d8cff;color:white;border:0}} .bad{{background:#963838;color:white;border:0}} .muted{{color:#aaa}}
.bar{{display:flex;justify-content:space-between;gap:12px;align-items:center}} #events button{{font-size:14px;padding:7px 10px}}
code{{color:#8fd}} textarea{{width:100%;height:90px;background:#222;color:#eee}}
</style></head><body>
<div class=\"bar\"><h1>HokCoach 事件标注</h1><strong id=\"progress\"></strong></div>
<video id=\"video\" controls autoplay></video><h2 id=\"candidate\"></h2><div id=\"meta\" class=\"muted\"></div>
<p>主判断（快捷键：1 正确、2 错误、3 看不清、4 不是击杀事件、S 跳过）</p>
<button class=\"primary\" onclick=\"save('correct')\">1 正确</button><button class=\"bad\" onclick=\"save('incorrect')\">2 错误</button>
<button onclick=\"save('unreadable')\">3 看不清</button><button onclick=\"save('not_combat_event')\">4 不是击杀事件</button><button onclick=\"next()\">S 跳过</button>
<h3>若预测类别不精确，可先选择正确类别</h3><div id=\"events\"></div>
<p><textarea id=\"note\" placeholder=\"可选备注，例如：播报被解说遮住、实际是队友死亡\"></textarea></p>
<button onclick=\"back()\">上一条</button><button onclick=\"download()\">导出 labels.jsonl</button><button onclick=\"clearAll()\">清空本机标注</button>
<script>
const rows={payload}; const storageKey='hokLabels:{package_id}', indexKey='hokLabelIndex:{package_id}'; let i=Number(localStorage.getItem(indexKey)||0); let override=null;
let labels=JSON.parse(localStorage.getItem(storageKey)||'{{}}'); const kinds=['hero_killed','player_death','multi_kill_2','multi_kill_3','multi_kill_4','multi_kill_5','first_blood','shutdown','ace','critical_kill','kill_streak_3','kill_streak_4','kill_streak_5','kill_streak_6','kill_streak_7_plus','other'];
function show(){{if(i>=rows.length)i=Math.max(0,rows.length-1);const r=rows[i];video.src=r.clip;candidate.textContent='候选：'+r.predictions.map(x=>x.event+' / '+x.perspective).join('，');meta.textContent=`${{i+1}}/${{rows.length}} · ${{r.source_name}} · 原视频 ${{r.center_sec.toFixed(2)}} 秒 · 最高分 ${{r.max_score.toFixed(3)}}`;progress.textContent=`已标 ${{Object.keys(labels).length}} / ${{rows.length}}`;events.innerHTML=kinds.map(k=>`<button onclick=\"override='${{k}}';document.querySelectorAll('#events button').forEach(b=>b.style.outline='');this.style.outline='3px solid #2d8cff'\">${{k}}</button>`).join('');note.value=labels[r.candidate_id]?.note||'';override=labels[r.candidate_id]?.operator_event||null;}}
function persist(){{localStorage.setItem(storageKey,JSON.stringify(labels));localStorage.setItem(indexKey,String(i))}}
function save(verdict){{const r=rows[i];labels[r.candidate_id]={{schema_version:'hokcoach-event-label-v1',candidate_id:r.candidate_id,source_sha256:r.source_sha256,center_sec:r.center_sec,verdict,operator_event:override,note:note.value,created_at:new Date().toISOString()}};persist();next()}}
function next(){{if(i<rows.length-1)i++;persist();show()}} function back(){{if(i>0)i--;persist();show()}}
function download(){{const text=Object.values(labels).map(x=>JSON.stringify(x)).join('\\n')+'\\n';const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([text],{{type:'application/jsonl'}}));a.download='labels.jsonl';a.click()}}
function clearAll(){{if(confirm('确定清空所有本机标注？')){{labels={{}};i=0;persist();show()}}}}
document.addEventListener('keydown',e=>{{if(document.activeElement===note)return;if(e.key==='1')save('correct');else if(e.key==='2')save('incorrect');else if(e.key==='3')save('unreadable');else if(e.key==='4')save('not_combat_event');else if(e.key.toLowerCase()==='s')next();else if(e.key==='ArrowLeft')back();}});show();
</script></body></html>"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--video", type=Path, action="append", required=True)
    parser.add_argument("--threshold", type=float, default=0.78)
    parser.add_argument("--max-candidates-per-video", type=int, default=80)
    parser.add_argument("--cache-dir", type=Path, default=None)
    parser.add_argument("--exclude-manifest", type=Path, default=None)
    args = parser.parse_args()
    repo = args.repo_root.resolve()
    sys.path.insert(0, str(repo / "coach"))
    from utils.video_utils import build_audio_event_timeline

    out = args.output_dir.resolve()
    clips = out / "clips"
    clips.mkdir(parents=True, exist_ok=True)
    cache = args.cache_dir.resolve() if args.cache_dir else out / ".cache"
    excluded: dict[str, list[float]] = {}
    if args.exclude_manifest:
        prior = json.loads(args.exclude_manifest.resolve().read_text(encoding="utf-8"))
        for candidate in prior:
            excluded.setdefault(candidate["source_sha256"], []).append(float(candidate["center_sec"]))
    rows: list[dict] = []
    for video_index, raw_video in enumerate(args.video, 1):
        video = raw_video.resolve()
        source_hash = sha256(video)
        source_duration = duration(video)
        events = build_audio_event_timeline(
            str(video), template_dir=repo / "Game Voices",
            catalog_path=repo / "coach/assets/audio_templates/game_voice_catalog.json",
            cache_dir=cache, usages={"evidence"},
            similarity_threshold=args.threshold,
        )
        combat = [event for event in events if event.get("category") in {"combat", "highlight"}]
        groups = grouped(combat)[:args.max_candidates_per_video]
        for group_index, group in enumerate(groups, 1):
            center = min(float(event["ts"]) for event in group)
            if any(abs(center - old) <= 3.0 for old in excluded.get(source_hash, [])):
                continue
            start = max(0.0, center - 3.0)
            length = min(8.0, source_duration - start)
            candidate_id = f"v{video_index:02d}_{group_index:03d}_{center:.2f}".replace(".", "_")
            clip_name = f"{candidate_id}.mp4"
            target = clips / clip_name
            if not target.is_file():
                subprocess.run([
                    "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-ss", f"{start:.3f}", "-i", str(video), "-t", f"{length:.3f}",
                    "-vf", "scale='min(960,iw)':-2", "-c:v", "libx264", "-preset", "veryfast",
                    "-crf", "25", "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", str(target),
                ], check=True)
            rows.append({
                "schema_version": "hokcoach-event-candidate-v1",
                "candidate_id": candidate_id,
                "source_name": video.name,
                "source_path": str(video),
                "source_sha256": source_hash,
                "source_duration_sec": round(source_duration, 3),
                "center_sec": round(center, 3),
                "clip_start_sec": round(start, 3),
                "clip_end_sec": round(start + length, 3),
                "clip": f"clips/{clip_name}",
                "max_score": max(float(event["score"]) for event in group),
                "predictions": group,
                "label_status": "unlabeled",
            })
    (out / "candidates.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out / "index.html").write_text(render_html(rows), encoding="utf-8")
    summary = {"sources": len(args.video), "candidates": len(rows), "output_dir": str(out), "index": str(out / "index.html")}
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
