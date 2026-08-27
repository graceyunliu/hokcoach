from __future__ import annotations
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data/evaluation/replay_seeds/corpus'
def rows(p): return [json.loads(x) for x in p.read_text(encoding='utf-8').splitlines() if x.strip()] if p.exists() else []

legacy_files=['claims.jsonl','source_segments.jsonl','observations.jsonl','corpus_report.json','missing_capability_queue.jsonl']
legacy_dirs=['fixtures','manifests']
legacy_seed_dirs=[p for p in OUT.glob('hokclass_*') if p.is_dir()]
assert not any((OUT/x).exists() for x in legacy_files), 'obsolete root corpus file remains'
assert not any((OUT/x).exists() for x in legacy_dirs), 'obsolete root corpus directory remains'
assert not legacy_seed_dirs, 'obsolete root hokclass directory remains'

report=json.loads((OUT/'aggregates/corpus_report.json').read_text(encoding='utf-8'))
boot=rows(OUT/'bootstrap/remote_multimodal_annotations.jsonl'); windows=rows(OUT/'bootstrap/candidate_windows.jsonl'); hints=rows(OUT/'bootstrap/chinese_windowed_caption_hints.jsonl')
seg=rows(OUT/'aggregates/canonical_commentary_segments.jsonl'); claims=rows(OUT/'aggregates/canonical_claims.jsonl'); obs=rows(OUT/'aggregates/evidence_timeline.jsonl'); fixtures=rows(OUT/'aggregates/detector_fixtures.jsonl'); manifests=rows(OUT/'aggregates/manifests.jsonl')
assert report['schema_version']=='handoff-corpus-v4'
assert report['generator_version']=='claim-model-v4-bootstrap-canonical'
assert len(windows)==len(boot)
assert all(b['canonical'] is False and b['language']=='en' and b['source_video_language']=='zh' and b['representation']=='ai_paraphrase' for b in boot)
boot_ids={b['bootstrap_id'] for b in boot}; assert all(w['source_bootstrap_id'] in boot_ids and w['canonical'] is False for w in windows)
assert all(h['canonical'] is False and h['language']=='zh' and h['representation']=='windowed_multimodal_caption_extraction' and h['label_tier']=='silver_windowed_multimodal' for h in hints)
seg_ids={s['segment_id'] for s in seg}; claim_ids={c['claim_id'] for c in claims}
assert all(s['canonical'] is True and s['language']=='zh' and s['representation']=='source_transcript' for s in seg)
assert all(o['canonical'] is True and o['language']=='zh' and o['source_segment_id'] in seg_ids for o in obs)
assert all(c['canonical'] is True and c['language']=='zh' and c['source_segment_id'] in seg_ids for c in claims)
assert all(f['source_claim_id'] in claim_ids and f['source_segment_id'] in seg_ids for f in fixtures)
assert not any(f.get('language')=='en' for f in fixtures)
assert report['eligible_seed_count']==len(manifests)
assert report['bootstrap']['english_ai_paraphrases']==len(boot)
assert report['bootstrap']['candidate_windows']==len(windows)
assert report['bootstrap']['chinese_windowed_caption_hints']==len(hints)
assert report['canonical']['chinese_ocr_observations']==0
assert report['canonical']['chinese_commentary_segments']==len(seg)
assert report['canonical']['claims']==len(claims)
assert report['canonical']['reviewer_observations']==len(obs)
assert report['canonical']['event_fixtures']==len(fixtures)
assert all(m.get('stage_status',{}).get('caption_ocr')=='pending' for m in manifests)
assert all(m.get('artifact_sha256') is None if not m.get('artifact_path') else bool(m.get('artifact_sha256')) for m in manifests)
print(json.dumps({'status':'pass','bootstrap_annotations':len(boot),'candidate_windows':len(windows),'chinese_hints':len(hints),'canonical_segments':len(seg),'canonical_claims':len(claims),'canonical_observations':len(obs),'canonical_fixtures':len(fixtures),'legacy_artifacts':'none'},ensure_ascii=False,indent=2))
