from __future__ import annotations
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data/evaluation/replay_seeds/handoff_v4'
CAPS=['deaths','death_location','minimap_positions','audio','objectives','towers','lifecycle','items_economy','waves','teamfights','cooldowns']
def rows(p): return [json.loads(x) for x in p.read_text(encoding='utf-8').splitlines() if x.strip()] if p.exists() else []
report=json.loads((OUT/'corpus_report.json').read_text(encoding='utf-8'))
assert report['schema_version']=='handoff-corpus-v4'
segments=rows(OUT/'source_segments.jsonl'); obs=rows(OUT/'observations.jsonl'); claims=rows(OUT/'claims.jsonl'); manifests=rows(OUT/'manifests/source_manifest.jsonl')
fixtures={c:rows(OUT/f'fixtures/{c}.jsonl') for c in CAPS}; inventory=rows(OUT/'missing_capability_queue.jsonl')
segment_ids={s['segment_id'] for s in segments}; claim_ids={c['claim_id'] for c in claims}; obs_by_seg={}
for o in obs: obs_by_seg.setdefault(o['source_segment_id'],[]).append(o)
claims_by_seg={}
for c in claims: claims_by_seg.setdefault(c['source_segment_id'],[]).append(c)
assert len(manifests)==100
assert len(obs)==len(segments)
assert all(len(obs_by_seg[sid])==1 for sid in segment_ids)
assert all(c['source_segment_id'] in segment_ids for c in claims)
assert all((len(claims_by_seg.get(s['segment_id'],[]))>=1) or s['segment_kind']=='context_only' for s in segments)
assert all(c['claim_id'].startswith(c['source_segment_id']+'_claim_') for c in claims)
fixture_total=sum(len(v) for v in fixtures.values())
assert fixture_total==report['event_fixtures']
assert fixture_total!=len(fixtures)
for cap,items in fixtures.items():
    for f in items:
        assert f['source_claim_id'] in claim_ids
        assert f['source_segment_id'] in segment_ids
        assert f['expected_observations']
        expected=f['expected_observations'][0]
        assert expected['time_range'] is None
        assert expected['time_semantics']=='unknown_gameplay_time'
        assert f['current_predictions']==[]
        if f['implementation_status']=='capability_missing': assert f['execution_status']=='not_run_missing_detector'
        else: assert f['execution_status'] in {'blocked_missing_media','pending_execution','complete','failed'}
assert len(inventory)==7
print(json.dumps({'status':'pass','source_segments':len(segments),'reviewer_observations':len(obs),'claims':len(claims),'event_fixtures':fixture_total,'capability_inventory':len(inventory)},ensure_ascii=False,indent=2))
