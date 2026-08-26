import json, os, subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
ROOT=Path('/home/ubuntu/hokcoach'); manifest=json.loads((ROOT/'data/source_seeds/youtube/seed_manifest.json').read_text())
OUT=ROOT/'data/evaluation/replay_seeds/remote_analysis'; OUT.mkdir(parents=True,exist_ok=True)
rows=[r for r in manifest['records'] if r.get('seed_eligibility')=='eligible-seed']
workers=int(os.environ.get('HOKCOACH_ANALYSIS_WORKERS','3'))
prompt='''Analyze this Honor of Kings full-game replay-review video as an evaluation seed. Use both spoken commentary and visible gameplay. Return a concise timestamped table with: timestamp_start, timestamp_end, quoted_or_paraphrased_coach_claim, gameplay_event, category (vision, macro, wave_resource, items, mechanics, teamfight, objective_conversion, composition, mentality), visible_or_audio_evidence, recommended_action, confidence. Preserve uncertainty and say when speech is inaudible. Do not invent exact quotes. Focus on coachable decisions, not generic hero descriptions.'''
def one(r):
    out=OUT/f"{r['seed_id']}_{r['video_id']}.md"
    if out.exists() and out.stat().st_size>200: return r['seed_id'],'cached',str(out.relative_to(ROOT))
    try:
        p=subprocess.run(['manus-analyze-video',r['url'],prompt],text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=420)
        out.write_text(p.stdout,encoding='utf-8')
        return r['seed_id'],'completed' if p.returncode==0 else 'failed',str(out.relative_to(ROOT))
    except Exception as e:
        out.write_text(f'ERROR: {e!r}\n',encoding='utf-8'); return r['seed_id'],'error',str(out.relative_to(ROOT))
results=[]
with ThreadPoolExecutor(max_workers=workers) as ex:
    fs=[ex.submit(one,r) for r in rows]
    for i,f in enumerate(as_completed(fs),1):
        x=f.result(); results.append(x); print(f'[{i}/{len(rows)}] {x[0]} {x[1]}',flush=True)
results.sort()
summary={}
for _,status,_ in results: summary[status]=summary.get(status,0)+1
(OUT/'remote_analysis_manifest.json').write_text(json.dumps({'requested':len(rows),'summary':summary,'results':[{'seed_id':a,'status':b,'file':c} for a,b,c in results]},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False,indent=2))
