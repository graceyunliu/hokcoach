from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data/evaluation/replay_seeds/handoff_v2'
CAPS = ['deaths','death_location','minimap_positions','audio','objectives','towers','lifecycle','items_economy','waves','teamfights','cooldowns']

def jsonl(path: Path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()] if path.exists() else []

report = json.loads((OUT/'corpus_report.json').read_text(encoding='utf-8'))
assert report['schema_version'] == 'handoff-corpus-v2'
manifests = jsonl(OUT/'manifests/source_manifest.jsonl')
claims = jsonl(OUT/'claims.jsonl')
segments = jsonl(OUT/'commentary_segments.jsonl')
observations = jsonl(OUT/'evidence_timeline.jsonl')
fixtures = {c: jsonl(OUT/f'fixtures/{c}.jsonl') for c in CAPS}
missing = jsonl(OUT/'missing_capability_queue.jsonl')
assert len(manifests) == 100
assert len(segments) == len(claims) == len(observations)
assert all(m['stage_status']['bootstrap_labels'] in {'available_silver_remote_multimodal','unavailable'} for m in manifests)
assert all(m['stage_status']['speech_to_text'] == 'pending' for m in manifests)
assert all(m['stage_status']['caption_ocr'] == 'pending' for m in manifests)
assert all(m['stage_status']['ocr_stt_alignment'] == 'pending' for m in manifests)
assert all(m['stage_status']['gameplay_reference_alignment'] == 'pending' for m in manifests)
assert all(m['stage_status']['detectors'] == 'blocked_missing_media' for m in manifests)
claim_ids = {c['claim_id'] for c in claims}
segment_ids = {s['segment_id'] for s in segments}
assert all(c['claim_id'].replace('_claim','') in segment_ids for c in claims)
for cap, rows in fixtures.items():
    for f in rows:
        assert f['source_claim_id'] in claim_ids
        assert f['source_commentary_segment_id'] in segment_ids
        assert f['source_window']['end_sec'] >= f['source_window']['start_sec']
        assert f['expected_observations']
        assert f['current_predictions'] == []
        assert f['execution_status'] == 'blocked_missing_media'
assert all(x['implementation_status'] == 'capability_missing' for x in missing)
assert len(missing) == 7
print(json.dumps({'status':'pass','seeds':len(manifests),'segments':len(segments),'claims':len(claims),'observations':len(observations),'event_fixtures':sum(map(len,fixtures.values())),'capability_inventory':len(missing)},ensure_ascii=False,indent=2))
