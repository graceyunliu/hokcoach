from __future__ import annotations

import hashlib, json, re
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path('/home/ubuntu/hokcoach')
SEED_MANIFEST = ROOT / 'data/source_seeds/youtube/seed_manifest.json'
EVAL_SET = ROOT / 'data/evaluation/replay_seeds/labeled_evaluation_set.json'
CAPTION_SET = ROOT / 'data/evaluation/replay_seeds/windowed_caption_analysis/merged_burned_captions.json'
OUT = ROOT / 'data/evaluation/replay_seeds/handoff_v1'
CAPABILITIES = {
    'deaths': 'implemented_partial',
    'minimap_positions': 'implemented_partial',
    'audio': 'implemented_partial',
    'objectives': 'capability_missing',
    'towers': 'capability_missing',
    'lifecycle': 'capability_missing',
    'items_economy': 'capability_missing',
    'waves': 'capability_missing',
    'teamfights': 'capability_missing',
    'cooldowns': 'capability_missing',
}

def dump(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

def dump_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows), encoding='utf-8')

def sha256(path: Path) -> str | None:
    if not path.exists() or not path.is_file(): return None
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''): h.update(chunk)
    return h.hexdigest()

def sec(s: str | int | float | None) -> float | None:
    if s is None: return None
    if isinstance(s, (int, float)): return float(s)
    m = re.search(r'(?:(\d+):)?(\d{1,2}):(\d{2})', str(s))
    return int(m.group(1) or 0) * 3600 + int(m.group(2)) * 60 + int(m.group(3)) if m else None

def atomic_claim(text: str, category: str, start: float | None, end: float | None, record_id: str) -> dict[str, Any]:
    lower = text.lower()
    claim_type = 'reviewer_commentary'
    if any(k in text for k in ['龙王', '暴君', '主宰', '风暴']): claim_type = 'objective_reference'
    elif any(k in text for k in ['塔', '水晶', '高地']): claim_type = 'tower_or_base_reference'
    elif any(k in text for k in ['线权', '清线', '兵线', '转']): claim_type = 'lane_or_rotation'
    elif any(k in text for k in ['闪现', '技能', '拉到', '大招', '金身']): claim_type = 'mechanics_or_cooldown'
    elif any(k in text for k in ['蹲', '视野', '草', '地图', '信号']): claim_type = 'vision_or_map_awareness'
    return {
        'claim_id': f'{record_id}_claim', 'claim_type': claim_type,
        'claim_source': 'reviewer', 'text': text,
        'required_evidence_types': ['reviewer_commentary'],
        'support_status': 'unknown', 'supporting_observation_ids': [],
        'commentary_start_sec': start, 'commentary_end_sec': end,
        'atomicity_status': 'single_caption_assertion'
    }

def main() -> None:
    source = json.loads(SEED_MANIFEST.read_text(encoding='utf-8'))
    eval_data = json.loads(EVAL_SET.read_text(encoding='utf-8')) if EVAL_SET.exists() else {'records': [], 'events': []}
    caption_data = json.loads(CAPTION_SET.read_text(encoding='utf-8')) if CAPTION_SET.exists() else {'records': []}
    by_seed = {r.get('seed_id'): r for r in source.get('records', [])}
    eval_events = eval_data.get('events', [])
    rows_by_seed: dict[str, list[dict[str, Any]]] = {}
    for e in eval_events: rows_by_seed.setdefault(e.get('seed_id'), []).append(e)
    # The single full-video caption POC is keyed by video_id, not seed_id.
    caption_records = caption_data.get('records', [])
    records=[]; observations=[]; commentary=[]; claims=[]; fixtures=[]; missing=[]
    eligible = [r for r in source.get('records', []) if r.get('seed_eligibility') == 'eligible-seed']
    for src in eligible:
        sid, vid = src['seed_id'], src['video_id']
        seed_dir = OUT / sid
        media_path = ROOT / 'data/evaluation/replay_seeds/media' / f'{vid}.webm'
        events = rows_by_seed.get(sid, [])
        stage = {'acquisition': 'pending', 'media_probe': 'pending', 'speech_to_text': 'pending', 'caption_ocr': 'pending', 'alignment': 'pending', 'detectors': 'pending'}
        if media_path.exists(): stage.update({'acquisition':'complete','media_probe':'pending'})
        if events: stage.update({'speech_to_text':'silver_remote_multimodal','alignment':'silver_remote_multimodal'})
        if vid == 'TcPNUG4b6GE' and caption_records: stage['caption_ocr'] = 'silver_windowed_multimodal'
        src_manifest = {
            'schema_version':'seed-source-v1', 'seed_id':sid, 'video_id':vid, 'url':src.get('url'),
            'title':src.get('title'), 'hero':src.get('hero'), 'role':src.get('role'), 'series':src.get('series'),
            'rank_profile':src.get('rank_profile'), 'artifact_path':str(media_path.relative_to(ROOT)) if media_path.exists() else None,
            'artifact_sha256':sha256(media_path), 'capture_method':None, 'timestamp_contract':{
                'captured_media_presentation_time':'unknown', 'normalized_derivative_time':'unknown',
                'reviewer_speech_caption_time':'unknown', 'referenced_gameplay_time':'unknown'},
            'stage_status':stage, 'terminal_status':'labeled_silver' if events else 'pending_media_or_transcript',
            'errors':[]
        }
        dump(seed_dir/'source_manifest.json', src_manifest)
        records.append(src_manifest)
        for i,e in enumerate(events):
            rid=f'{sid}_{i:04d}'
            start=e.get('start_sec'); end=e.get('end_sec')
            obs_id=f'{rid}_reviewer_commentary'
            observations.append({'observation_id':obs_id,'video_id':vid,'type':'reviewer_commentary','start_sec':start,'end_sec':end,'subject':'reviewer','value':e.get('coach_claim') or e.get('gameplay_event'),'confidence':e.get('confidence'),'detector':'remote_multimodal_seed_v1','detector_config_version':'silver','evidence_refs':[f'source_artifact:{e.get("source_artifact")}'],'status':'observed_silver'})
            text=e.get('coach_claim') or e.get('gameplay_event') or ''
            seg={'segment_id':rid,'video_id':vid,'seed_id':sid,'commentary_start_sec':start,'commentary_end_sec':end,'speech_text_raw':text,'ocr_text_raw':None,'normalized_text':text,'alignment_method':'remote_multimodal','alignment_confidence':e.get('confidence'),'referenced_gameplay_windows':[],'unresolved_reference':True,'label_tier':'silver'}
            commentary.append(seg); claims.append(atomic_claim(text,e.get('category','other'),start,end,rid))
        for cap,status in CAPABILITIES.items():
            fixture={'fixture_id':f'{sid}_{cap}','seed_id':sid,'video_id':vid,'capability':cap,'implementation_status':status,'expected_observations':[],'current_predictions':[],'evaluation_status':'capability_missing' if status=='capability_missing' else 'unscored'}
            fixtures.append(fixture)
            if status == 'capability_missing': missing.append({'seed_id':sid,'video_id':vid,'capability':cap,'implementation_status':'capability_missing','reason':'No production detector is present in current hokcoach; fixture retained for future detector project.'})
        dump_jsonl(seed_dir/'commentary_segments.jsonl', [x for x in commentary if x['seed_id']==sid])
        dump_jsonl(seed_dir/'claims.jsonl', [x for x in claims if x['claim_id'].startswith(sid+'_')])
    dump_jsonl(OUT/'manifests/source_manifest.jsonl', records)
    dump_jsonl(OUT/'evidence_timeline.jsonl', observations)
    dump_jsonl(OUT/'commentary_segments.jsonl', commentary)
    dump_jsonl(OUT/'claims.jsonl', claims)
    for cap in CAPABILITIES:
        dump_jsonl(OUT/f'fixtures/{cap}.jsonl', [f for f in fixtures if f['capability']==cap])
    dump_jsonl(OUT/'missing_capability_queue.jsonl', missing)
    summary={'schema_version':'handoff-corpus-v1','eligible_seed_count':len(eligible),'seed_manifests':len(records),'commentary_segments':len(commentary),'claims':len(claims),'observations':len(observations),'fixtures':len(fixtures),'missing_capability_records':len(missing),'capability_status':CAPABILITIES,'typed_rank_dimensions':{'regular_rank':'preserved','peak_score':'preserved','hero_power':'preserved'},'note':'Reviewer-derived silver labels are not gameplay ground truth; missing detectors remain explicit.'}
    dump(OUT/'corpus_report.json',summary)
    print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=='__main__': main()
