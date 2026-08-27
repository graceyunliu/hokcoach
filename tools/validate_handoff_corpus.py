from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data/evaluation/replay_seeds/handoff_v3'
CAPS = ['deaths','death_location','minimap_positions','audio','objectives','towers','lifecycle','items_economy','waves','teamfights','cooldowns']

def jsonl(path: Path):
    return [json.loads(x) for x in path.read_text(encoding='utf-8').splitlines() if x.strip()] if path.exists() else []

report=json.loads((OUT/'corpus_report.json').read_text(encoding='utf-8'))
assert report['schema_version']=='handoff-corpus-v3'
manifests=jsonl(OUT/'manifests/source_manifest.jsonl'); segments=jsonl(OUT/'commentary_segments.jsonl'); claims=jsonl(OUT/'claims.jsonl'); obs=jsonl(OUT/'evidence_timeline.jsonl')
fixtures={c:jsonl(OUT/f'fixtures/{c}.jsonl') for c in CAPS}; inventory=jsonl(OUT/'missing_capability_queue.jsonl')
assert len(manifests)==100
assert len(segments)==len(claims)==len(obs)
assert report['routing_source_categories_preserved'] is True
assert report['bilingual_keyword_routing'] is True
assert all('rank_profile' in m and 'timestamp_contract' in m for m in manifests)
assert all(m['stage_status']['speech_to_text']=='pending' and m['stage_status']['caption_ocr']=='pending' for m in manifests)
assert all(m['stage_status']['ocr_stt_alignment']=='pending' and m['stage_status']['gameplay_reference_alignment']=='pending' for m in manifests)
for m in manifests:
    st=m['stage_status']; artifact=bool(m.get('artifact_path'))
    assert st['media_probe'] in {'blocked_missing_media','complete','failed'}
    if not artifact: assert st['media_probe']=='blocked_missing_media' and st['detectors']=='blocked_missing_media'
    if artifact and st['media_probe']=='complete': assert st['detectors']=='pending_execution'
for c in claims:
    assert c['claim_id'].replace('_claim','') in {s['segment_id'] for s in segments}
    assert 'required_capabilities' in c
for cap,rows in fixtures.items():
    for f in rows:
        assert f['source_claim_id'] in {c['claim_id'] for c in claims}
        assert f['source_commentary_segment_id'] in {s['segment_id'] for s in segments}
        assert f['source_window']['end_sec']>=f['source_window']['start_sec']
        exp=f['expected_observations'][0]
        assert exp['time_range'] is None
        assert exp['time_semantics']=='unknown_gameplay_time'
        assert exp['commentary_time_range'] is not None
        assert f['current_predictions']==[]
        if f['implementation_status']=='capability_missing': assert f['execution_status']=='not_run_missing_detector'
        else: assert f['execution_status'] in {'blocked_missing_media','pending_execution','complete','failed'}
assert len(inventory)==7
print(json.dumps({'status':'pass','seeds':len(manifests),'segments':len(segments),'claims':len(claims),'observations':len(obs),'event_fixtures':sum(map(len,fixtures)),'capability_inventory':len(inventory)},ensure_ascii=False,indent=2))
