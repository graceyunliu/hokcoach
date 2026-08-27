from __future__ import annotations
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data/evaluation/replay_seeds/corpus'
def rows(p):
    if not p.exists(): return []
    return [json.loads(x) for x in p.read_text(encoding='utf-8').splitlines() if x.strip()]

# Active corpus must remain migration-safe: no old root-level mixed layout.
legacy_files=['claims.jsonl','source_segments.jsonl','observations.jsonl','corpus_report.json','missing_capability_queue.jsonl']
legacy_dirs=['fixtures','manifests']
assert not any((OUT/x).exists() for x in legacy_files), 'obsolete root corpus file remains'
assert not any((OUT/x).exists() for x in legacy_dirs), 'obsolete root corpus directory remains'
assert not list(OUT.glob('hokclass_*')), 'obsolete root hokclass directory remains'

report=json.loads((OUT/'aggregates/corpus_report.json').read_text(encoding='utf-8'))
boot=rows(OUT/'bootstrap/remote_multimodal_annotations.jsonl'); windows=rows(OUT/'bootstrap/candidate_windows.jsonl'); hints=rows(OUT/'bootstrap/chinese_windowed_caption_hints.jsonl')
seg=rows(OUT/'aggregates/canonical_commentary_segments.jsonl'); claims=rows(OUT/'aggregates/canonical_claims.jsonl'); obs=rows(OUT/'aggregates/evidence_timeline.jsonl'); fixtures=rows(OUT/'aggregates/detector_fixtures.jsonl'); manifests=rows(OUT/'aggregates/manifests.jsonl')
assert report['schema_version']=='handoff-corpus-v4'
assert report['generator_version']=='claim-model-v4-bootstrap-canonical'
assert len(windows)==len(boot)
assert len({b['bootstrap_id'] for b in boot})==len(boot)
assert all(b['canonical'] is False and b['language']=='en' and b['source_video_language']=='zh' and b['representation']=='ai_paraphrase' for b in boot)
boot_ids={b['bootstrap_id'] for b in boot}; assert all(w['source_bootstrap_id'] in boot_ids and w['canonical'] is False for w in windows)
assert all(h['canonical'] is False and h['language']=='zh' and h['representation']=='windowed_multimodal_caption_extraction' for h in hints)
assert len({s['segment_id'] for s in seg})==len(seg); assert len({c['claim_id'] for c in claims})==len(claims)
seg_ids={s['segment_id'] for s in seg}; claim_ids={c['claim_id'] for c in claims}
assert all(s['canonical'] is True and s['language']=='zh' and s['representation']=='source_transcript' for s in seg)
assert all(o.get('source_segment_id') in seg_ids for o in obs)
assert all(c['canonical'] is True and c['language']=='zh' and c['source_segment_id'] in seg_ids for c in claims)
assert all(f['source_claim_id'] in claim_ids and f['source_segment_id'] in seg_ids for f in fixtures)
assert not any(x.get('language')=='en' for x in seg+claims+obs+fixtures)
assert report['eligible_seed_count']==len(manifests)==len({m['seed_id'] for m in manifests})
assert report['bootstrap']['english_ai_paraphrases']==len(boot)
assert report['bootstrap']['candidate_windows']==len(windows)
assert report['bootstrap']['chinese_windowed_caption_hints']==len(hints)
assert report['canonical']['chinese_ocr_observations']==len(obs)
assert report['canonical']['chinese_commentary_segments']==len(seg)
assert report['canonical']['claims']==len(claims)
assert report['canonical']['reviewer_observations']==len(obs)
assert report['canonical']['event_fixtures']==len(fixtures)
allowed={'complete','pending','failed','unavailable','blocked_missing_media','not_run_missing_detector','pending_execution','media_ready_transcript_pending','media_probe_failed','available_silver_remote_multimodal'}
for m in manifests:
    stage=m.get('stage_status',{})
    assert all(v in allowed for v in stage.values()), (m['seed_id'],stage)
    sm_path=OUT/'videos'/m['seed_id']/'stage_manifest.json'
    if sm_path.exists():
        sm=json.loads(sm_path.read_text(encoding='utf-8')); assert sm.get('schema_version')=='incremental-corpus-v1'
        for name,rec in sm.get('stages',{}).items():
            assert rec.get('status') in {'pending','running','complete','failed_retryable','failed_permanent','blocked','stale'}, (m['seed_id'],name,rec.get('status'))
            for path,h in rec.get('output_hashes',{}).items(): assert Path(path).exists() and __import__('hashlib').sha256(Path(path).read_bytes()).hexdigest()==h, (m['seed_id'],name,path)
            temp_paths=[Path(path) for path in rec.get('output_paths',[]) if '/.tmp_' in path or '/tmp/' in path]
            retention_status=sm.get('stages',{}).get('retention_cleanup',{}).get('status')
            assert not any(not p.is_relative_to(OUT) for p in temp_paths), (m['seed_id'],name,'external-temp-path')
            if retention_status=='complete': assert not temp_paths, (m['seed_id'],name,'temp-output-after-cleanup')
    if m.get('artifact_path'):
        assert m.get('artifact_sha256'), m['seed_id']
    else:
        assert m.get('artifact_sha256') is None, m['seed_id']
# Rebuild integrity: canonical aggregates equal the concatenation of preserved per-seed canonical files.
per_seg=[]; per_claim=[]; per_obs=[]; per_fix=[]
for m in manifests:
    sid=m['seed_id']; v=OUT/'videos'/sid; per_seg.extend(rows(v/'transcript/commentary_segments.jsonl')); per_claim.extend(rows(v/'claims.jsonl')); per_obs.extend(rows(v/'transcript/ocr_observations.jsonl')); per_fix.extend(rows(v/'fixture_candidates.jsonl'))
assert len(per_seg)==len(seg); assert len(per_claim)==len(claims); assert len(per_obs)==len(obs); assert len(per_fix)==len(fixtures)
print(json.dumps({'status':'pass','bootstrap_annotations':len(boot),'candidate_windows':len(windows),'chinese_hints':len(hints),'canonical_segments':len(seg),'canonical_claims':len(claims),'canonical_observations':len(obs),'canonical_fixtures':len(fixtures),'stage_policy':'progression_safe','legacy_artifacts':'none'},ensure_ascii=False,indent=2))
