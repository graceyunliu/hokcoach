#!/usr/bin/env python3
"""Build a compact operator package for kill-feed visual confirmation labels."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path


def render(rows: list[dict]) -> str:
    payload = json.dumps(rows, ensure_ascii=False).replace("</", "<\\/")
    package_id = hashlib.sha256("\n".join(
        row["sample_id"] for row in rows).encode()).hexdigest()[:16]
    return f"""<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width\"><title>击杀栏视觉标注</title><style>
body{{font-family:-apple-system,BlinkMacSystemFont,sans-serif;max-width:1050px;margin:22px auto;padding:0 16px;background:#111;color:#eee}}video{{width:100%;max-height:62vh;background:#000}}button,select{{font-size:16px;margin:5px;padding:9px 13px}}.yes{{background:#287a50;color:white;border:0}}.no{{background:#9b3939;color:white;border:0}}.muted{{color:#aaa}}input,textarea{{width:100%;box-sizing:border-box;font-size:16px;padding:9px;background:#222;color:#eee;border:1px solid #555}}textarea{{height:70px}}.target{{color:#ffd45b;font-weight:700}}
</style></head><body><h1>击杀栏视觉标注</h1><p>目标时间是短片内 <span class=\"target\" id=\"target\"></span>。播放前后约 2 秒，观察屏幕上方的英雄头像和“击败”文字。</p><video id=\"video\" controls></video><h2 id=\"progress\"></h2><div id=\"meta\" class=\"muted\"></div>
<p><button onclick=\"seekTarget()\">跳到目标前 1 秒</button><button class=\"yes\" onclick=\"save('confirmed')\">1 击杀栏确认事件</button><button class=\"no\" onclick=\"save('no_event')\">2 击杀栏可见但无事件</button><button onclick=\"save('unreadable')\">3 击杀栏不可读/被遮挡</button><button onclick=\"save('multiple_ambiguous')\">4 多个连续事件，无法对应</button><button onclick=\"next()\">S 跳过</button></p>
<label>关系（可选）</label><select id=\"relation\"><option value=\"unknown\">未知</option><option value=\"player_killed_enemy\">玩家击杀敌人</option><option value=\"player_was_killed\">玩家被击杀</option><option value=\"ally_killed_enemy\">队友击杀敌人</option><option value=\"ally_was_killed\">队友被击杀</option><option value=\"enemy_vs_ally_unknown_player\">敌我英雄击杀，玩家关系不明</option></select>
<p><input id=\"heroes\" placeholder=\"可选：击杀者英雄 -> 被击杀英雄，例如 安其拉 -> 六耳\"></p><p><textarea id=\"note\" placeholder=\"可选备注\"></textarea></p><button onclick=\"back()\">上一条</button><button onclick=\"download()\">导出 kill-feed-labels.jsonl</button>
<script>const rows={payload},storageKey='hokKillFeed:{package_id}',indexKey='hokKillFeedIndex:{package_id}';let i=Number(localStorage.getItem(indexKey)||0),labels=JSON.parse(localStorage.getItem(storageKey)||'{{}}');
function persist(){{localStorage.setItem(storageKey,JSON.stringify(labels));localStorage.setItem(indexKey,String(i))}}function show(){{if(i>=rows.length)i=rows.length-1;const r=rows[i],old=labels[r.sample_id]||{{}};video.src=r.clip;target.textContent=r.target_offset_sec.toFixed(2)+' 秒';progress.textContent=`${{i+1}}/${{rows.length}} · 已标 ${{Object.keys(labels).length}}`;meta.textContent=`${{r.source_name}} · 原视频 ${{r.center_sec.toFixed(2)}} 秒 · 音频人工标签：${{r.audio_target?'有击杀播报':'无击杀播报'}} · 模型概率 ${{r.audio_probability.toFixed(3)}}`;relation.value=old.relation||'unknown';heroes.value=old.heroes||'';note.value=old.note||'';video.onloadedmetadata=seekTarget}}
function seekTarget(){{const r=rows[i];video.currentTime=Math.max(0,r.target_offset_sec-1)}}function save(verdict){{const r=rows[i];labels[r.sample_id]={{schema_version:'hokcoach-kill-feed-label-v1',sample_id:r.sample_id,source_sha256:r.source_sha256,center_sec:r.center_sec,verdict,relation:relation.value,heroes:heroes.value,note:note.value,created_at:new Date().toISOString()}};persist();next()}}function next(){{if(i<rows.length-1)i++;persist();show()}}function back(){{if(i>0)i--;persist();show()}}function download(){{const text=Object.values(labels).map(JSON.stringify).join('\\n')+'\\n',a=document.createElement('a');a.href=URL.createObjectURL(new Blob([text],{{type:'application/jsonl'}}));a.download='kill-feed-labels.jsonl';a.click()}}document.addEventListener('keydown',e=>{{if(['INPUT','TEXTAREA','SELECT'].includes(document.activeElement.tagName))return;if(e.key==='1')save('confirmed');else if(e.key==='2')save('no_event');else if(e.key==='3')save('unreadable');else if(e.key==='4')save('multiple_ambiguous');else if(e.key.toLowerCase()==='s')next();else if(e.key==='ArrowLeft')back()}});show();</script></body></html>"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evaluation", type=Path, required=True)
    parser.add_argument("--labeling-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--split", choices=("tuning", "evaluation", "all"), default="evaluation")
    args = parser.parse_args()
    report = json.loads(args.evaluation.resolve().read_text(encoding="utf-8"))
    source_rows = report["predictions"]
    if args.split != "all":
        source_rows = [row for row in source_rows if row["split"] == args.split]
    lookup: dict[str, dict] = {}
    for folder in args.labeling_root.resolve().iterdir():
        manifest = folder / "candidates.json"
        if not manifest.is_file():
            continue
        for row in json.loads(manifest.read_text(encoding="utf-8")):
            lookup.setdefault(row["candidate_id"], {**row, "folder": str(folder)})
    out = args.output_dir.resolve(); (out / "clips").mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    for index, source in enumerate(source_rows, 1):
        candidate = lookup[source["candidate_id"]]
        original_clip = Path(candidate["folder"]) / candidate["clip"]
        clip_name = f"feed_{index:02d}_{source['candidate_id']}.mp4"
        shutil.copy2(original_clip, out / "clips" / clip_name)
        start = float(candidate.get("clip_start_sec", source["center_sec"] - 3.0))
        rows.append({
            "schema_version": "hokcoach-kill-feed-sample-v1",
            "sample_id": f"feed_{source['candidate_id']}",
            "candidate_id": source["candidate_id"],
            "source_name": source["source_name"],
            "source_sha256": source["source_sha256"],
            "center_sec": float(source["center_sec"]),
            "target_offset_sec": round(float(source["center_sec"]) - start, 3),
            "clip": f"clips/{clip_name}",
            "audio_target": int(source["target"]),
            "audio_probability": float(source["probability"]),
            "audio_predicted": int(source["predicted"]),
            "split": source["split"],
        })
    (out / "samples.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out / "index.html").write_text(render(rows), encoding="utf-8")
    summary = {"schema_version":"hokcoach-kill-feed-package-v1","samples":len(rows),"split":args.split,"index":str(out/'index.html')}
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__": raise SystemExit(main())
