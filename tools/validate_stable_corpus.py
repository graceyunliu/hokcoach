from __future__ import annotations
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data/evaluation/replay_seeds/corpus'
def rows(p): return [json.loads(x) for x in p.read_text(encoding='utf-8').splitlines() if x.strip()] if p.exists() else []
report=json.loads((OUT/'aggregates/corpus_report.json').read_text(encoding='utf-8'))
boot=rows(OUT/'bootstrap/remote_multimodal_annotations.jsonl'); windows=rows(OUT/'bootstrap/candidate_windows.jsonl'); seg=rows(OUT/'aggregates/canonical_commentary_segments.jsonl'); claims=rows(OUT/'aggregates/canonical_claims.jsonl'); obs=rows(OUT/'aggregates/evidence_timeline.jsonl'); fixtures=rows(OUT/'aggregates/detector_fixtures.jsonl'); manifests=rows(OUT/'aggregates/manifests.jsonl')
assert report['schema_version']=='handoff-corpus-v4'
assert report['generator_version']=='claim-model-v3-stable-corpus'
assert len(boot)==920 and len(windows)==len(boot)
assert all(b['canonical'] is False and b['language']=='en' and b['source_video_language']=='zh' and b['representation']=='ai_paraphrase' for b in boot)
boot_ids={b['bootstrap_id'] for b in boot}
assert all(w['source_bootstrap_id'] in boot_ids and w['canonical'] is False for w in windows)
seg_ids={s['segment_id'] for s in seg}; claim_ids={c['claim_id'] for c in claims}
assert len(manifests)==100
assert all(s['canonical'] is True and s['language']=='zh' and s['representation']=='source_transcript' for s in seg)
assert all(o['canonical'] is True and o['language']=='zh' and o['source_segment_id'] in seg_ids for o in obs)
assert len(obs)==len(seg)
assert all(c['canonical'] is True and c['language']=='zh' and c['source_segment_id'] in seg_ids for c in claims)
assert all(f['source_claim_id'] in claim_ids and f['source_segment_id'] in seg_ids for f in fixtures)
assert not any(f.get('language')=='en' for f in fixtures)
assert report['bootstrap']['english_ai_paraphrases']==len(boot)
assert report['bootstrap']['candidate_windows']==len(windows)
assert report['canonical']['chinese_ocr_observations']==242
assert report['canonical']['chinese_commentary_segments']==len(seg)
assert report['canonical']['claims']==len(claims)
assert report['canonical']['reviewer_observations']==len(obs)
assert report['canonical']['event_fixtures']==len(fixtures)
print(json.dumps({'status':'pass','bootstrap_annotations':len(boot),'candidate_windows':len(windows),'canonical_segments':len(seg),'canonical_claims':len(claims),'canonical_observations':len(obs),'canonical_fixtures':len(fixtures)},ensure_ascii=False,indent=2))
