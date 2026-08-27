from __future__ import annotations
import json
from pathlib import Path

ROOT=Path('/home/ubuntu/hokcoach')
OUT=ROOT/'data/evaluation/replay_seeds/handoff_v1'
CAPS=['deaths','minimap_positions','audio','objectives','towers','lifecycle','items_economy','waves','teamfights','cooldowns']

def read_jsonl(p):
    return [json.loads(x) for x in p.read_text(encoding='utf-8').splitlines() if x.strip()] if p.exists() else []

report=json.loads((OUT/'corpus_report.json').read_text(encoding='utf-8'))
manifests=read_jsonl(OUT/'manifests/source_manifest.jsonl')
obs=read_jsonl(OUT/'evidence_timeline.jsonl')
claims=read_jsonl(OUT/'claims.jsonl')
fixtures={c:read_jsonl(OUT/f'fixtures/{c}.jsonl') for c in CAPS}
missing=read_jsonl(OUT/'missing_capability_queue.jsonl')
assert report['eligible_seed_count']==100
assert len(manifests)==100
assert len(fixtures['deaths'])==100
assert all(len(fixtures[c])==100 for c in CAPS)
assert len(missing)==700
assert all('rank_profile' in m for m in manifests)
assert all('timestamp_contract' in m for m in manifests)
assert all(o.get('status')=='observed_silver' for o in obs)
assert all(c.get('support_status')=='unknown' for c in claims)
assert all(f['implementation_status']=='capability_missing' for c in CAPS[3:] for f in fixtures[c])
print(json.dumps({'status':'pass','seeds':len(manifests),'observations':len(obs),'claims':len(claims),'fixtures':sum(map(len,fixtures.values())),'missing_capabilities':len(missing)},ensure_ascii=False,indent=2))
