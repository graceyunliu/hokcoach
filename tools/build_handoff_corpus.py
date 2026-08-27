from __future__ import annotations

import argparse, hashlib, json, re
from collections import Counter
from pathlib import Path
from typing import Any

CAPABILITIES = {
    'deaths': 'implemented_partial',
    'death_location': 'implemented_partial',
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
KEYWORDS = {
    'objectives': ['龙王', '暴君', '主宰', '风暴', '开龙', '抢龙'],
    'towers': ['塔', '水晶', '高地', '二塔', '推掉'],
    'waves': ['线权', '清线', '兵线', '转线', '支援', '游走', '河道'],
    'teamfights': ['团战', '打团', '3打2', '人堆', '掉点', '救人', '换一换'],
    'cooldowns': ['闪现', '技能', '大招', '金身', '拉到', '连招', '操作'],
    'items_economy': ['装备', '复活甲', '金身', '出装', '经济', '钱'],
    'minimap_positions': ['蹲', '视野', '草', '地图', '信号', '对面不见', '位置'],
    'deaths': ['死', '死亡', '复活', '被击杀', '被融化'],
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

def sec(value: Any) -> float | None:
    if value is None: return None
    if isinstance(value, (int, float)): return float(value)
    m = re.search(r'(?:(\d+):)?(\d{1,2}):(\d{2})', str(value))
    return int(m.group(1) or 0) * 3600 + int(m.group(2)) * 60 + int(m.group(3)) if m else None

def relevant_capabilities(text: str, category: str = '') -> list[str]:
    found = [cap for cap, words in KEYWORDS.items() if any(w in text for w in words)]
    if category == 'objective_conversion' and 'objectives' not in found: found.append('objectives')
    if category == 'teamfight' and 'teamfights' not in found: found.append('teamfights')
    if category == 'wave_resource' and 'waves' not in found: found.append('waves')
    if category == 'vision' and 'minimap_positions' not in found: found.append('minimap_positions')
    if category == 'items' and 'items_economy' not in found: found.append('items_economy')
    if category == 'mechanics' and 'cooldowns' not in found: found.append('cooldowns')
    return sorted(set(found))

def claim_type(text: str, category: str) -> str:
    if any(w in text for w in KEYWORDS['objectives']) or category == 'objective_conversion': return 'objective_reference'
    if any(w in text for w in KEYWORDS['towers']): return 'tower_or_base_reference'
    if any(w in text for w in KEYWORDS['waves']) or category == 'wave_resource': return 'lane_or_rotation'
    if any(w in text for w in KEYWORDS['teamfights']) or category == 'teamfight': return 'teamfight_reference'
    if any(w in text for w in KEYWORDS['cooldowns']) or category == 'mechanics': return 'mechanics_or_cooldown'
    if any(w in text for w in KEYWORDS['items_economy']) or category == 'items': return 'item_or_economy_reference'
    if any(w in text for w in KEYWORDS['minimap_positions']) or category == 'vision': return 'vision_or_map_awareness'
    if any(w in text for w in KEYWORDS['deaths']): return 'death_reference'
    return 'reviewer_commentary'

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    return p.parse_args()

def main() -> None:
    root = parse_args().root.resolve()
    seed_path = root / 'data/source_seeds/youtube/seed_manifest.json'
    eval_path = root / 'data/evaluation/replay_seeds/labeled_evaluation_set.json'
    cap_path = root / 'data/evaluation/replay_seeds/windowed_caption_analysis/merged_burned_captions.json'
    out = root / 'data/evaluation/replay_seeds/handoff_v2'
    source = json.loads(seed_path.read_text(encoding='utf-8'))
    eval_data = json.loads(eval_path.read_text(encoding='utf-8')) if eval_path.exists() else {'events': []}
    cap_data = json.loads(cap_path.read_text(encoding='utf-8')) if cap_path.exists() else {'records': []}
    eligible = [r for r in source.get('records', []) if r.get('seed_eligibility') == 'eligible-seed']
    by_seed = {r['seed_id']: r for r in eligible}
    events_by_seed: dict[str, list[dict[str, Any]]] = {}
    for e in eval_data.get('events', []): events_by_seed.setdefault(e.get('seed_id'), []).append(e)
    commentary_by_seed: dict[str, list[dict[str, Any]]] = {}
    if cap_data.get('source_video_id'):
        target = next((r for r in eligible if r.get('video_id') == cap_data['source_video_id']), None)
        if target:
            for i, r in enumerate(cap_data.get('records', [])):
                commentary_by_seed.setdefault(target['seed_id'], []).append({'start_sec': r.get('timestamp_sec'), 'end_sec': r.get('end_sec'), 'text': r.get('text'), 'confidence': r.get('confidence'), 'source': 'windowed_multimodal_burned_caption'})
    all_segments=[]; all_claims=[]; observations=[]; fixtures=[]; missing=[]; manifests=[]
    for src in eligible:
        sid, vid = src['seed_id'], src['video_id']
        media = root / 'data/evaluation/replay_seeds/media' / f'{vid}.webm'
        segments=[]
        for e in events_by_seed.get(sid, []):
            segments.append({'start_sec': e.get('start_sec'), 'end_sec': e.get('end_sec'), 'text': e.get('coach_claim') or e.get('gameplay_event') or '', 'confidence': e.get('confidence'), 'source':'remote_multimodal_commentary'})
        segments.extend(commentary_by_seed.get(sid, []))
        stage = {'acquisition': 'complete' if media.exists() else 'blocked_missing_media', 'media_probe': 'complete' if media.exists() else 'blocked_missing_media', 'bootstrap_labels': 'available_silver_remote_multimodal' if segments else 'unavailable', 'speech_to_text': 'pending', 'caption_ocr': 'pending', 'ocr_stt_alignment': 'pending', 'gameplay_reference_alignment': 'pending', 'detectors': 'blocked_missing_media'}
        manifest={'schema_version':'seed-source-v2','seed_id':sid,'video_id':vid,'url':src.get('url'),'title':src.get('title'),'hero':src.get('hero'),'role':src.get('role'),'series':src.get('series'),'rank_profile':src.get('rank_profile'),'artifact_path':str(media.relative_to(root)) if media.exists() else None,'artifact_sha256':sha256(media),'capture_method':None,'timestamp_contract':{'captured_media_presentation_time':'unknown','normalized_derivative_time':'unknown','reviewer_speech_caption_time':'unknown','referenced_gameplay_time':'unknown'},'stage_status':stage,'terminal_status':'blocked_missing_media' if not media.exists() else 'media_ready_transcript_pending','errors':[]}
        manifests.append(manifest); dump(out/sid/'source_manifest.json', manifest)
        for i, seg in enumerate(segments):
            rid=f'{sid}_{i:04d}'; text=seg['text']; start=sec(seg.get('start_sec')); end=sec(seg.get('end_sec')) or start
            caps=relevant_capabilities(text, '')
            ctype=claim_type(text, '')
            req=['reviewer_commentary'] + caps
            seg_out={'segment_id':rid,'seed_id':sid,'video_id':vid,'commentary_start_sec':start,'commentary_end_sec':end,'speech_text_raw':text if seg.get('source')=='remote_multimodal_commentary' else None,'ocr_text_raw':text if seg.get('source')=='windowed_multimodal_burned_caption' else None,'normalized_text':text,'alignment_method':'silver_bootstrap_only','alignment_confidence':seg.get('confidence'),'candidate_gameplay_window':{'start_sec':max(0,(start or 0)-15),'end_sec':(end or start or 0)+10},'accepted_gameplay_window':None,'unresolved_reference':True,'label_tier':'silver'}
            all_segments.append(seg_out)
            claim={'claim_id':rid+'_claim','claim_type':ctype,'claim_source':'reviewer','text':text,'required_evidence_types':req,'required_capabilities':caps,'support_status':'unknown','supporting_observation_ids':[],'commentary_start_sec':start,'commentary_end_sec':end,'candidate_gameplay_window':seg_out['candidate_gameplay_window'],'atomicity_status':'single_caption_assertion'}
            all_claims.append(claim)
            observations.append({'observation_id':rid+'_reviewer_commentary','video_id':vid,'type':'reviewer_commentary','start_sec':start,'end_sec':end,'subject':'reviewer','value':text,'confidence':seg.get('confidence'),'detector':'silver_bootstrap_remote_multimodal_v1','detector_config_version':'silver','evidence_refs':[f'seed:{sid}',f'commentary_segment:{rid}'],'status':'observed_silver'})
            for cap in caps:
                expected_type={'objectives':'objective_state','towers':'tower_state','waves':'wave_state','teamfights':'teamfight_episode','cooldowns':'skill_or_spell_state','items_economy':'item_economy_state','minimap_positions':'player_position_or_vision','deaths':'player_death','death_location':'death_location','audio':'audio_event'}.get(cap,cap)
                fx={'fixture_id':rid+'_'+cap,'seed_id':sid,'video_id':vid,'capability':cap,'source_commentary_segment_id':rid,'source_claim_id':claim['claim_id'],'source_window':seg_out['candidate_gameplay_window'],'expected_observations':[{'type':expected_type,'subject':'unknown_or_player','time_range':[start,end],'label_tier':'silver','verification_status':'unverified','source':'reviewer_assertion_not_gameplay_ground_truth'}],'current_predictions':[],'implementation_status':CAPABILITIES[cap],'execution_status':'blocked_missing_media','evaluation_status':'capability_missing' if CAPABILITIES[cap]=='capability_missing' else 'unscored_blocked_missing_media'}
                fixtures.append(fx)
        dump_jsonl(out/sid/'commentary_segments.jsonl',[x for x in all_segments if x['seed_id']==sid]); dump_jsonl(out/sid/'claims.jsonl',[x for x in all_claims if x['claim_id'].startswith(sid+'_')])
    for cap in CAPABILITIES:
        rows=[f for f in fixtures if f['capability']==cap]
        dump_jsonl(out/f'fixtures/{cap}.jsonl',rows)
        if CAPABILITIES[cap]=='capability_missing': missing.append({'capability':cap,'implementation_status':'capability_missing','execution_status':'not_run_missing_detector','fixture_count':len(rows),'reason':'No production detector is present; linked event fixtures are retained for a separate detector project.'})
    dump_jsonl(out/'manifests/source_manifest.jsonl',manifests); dump_jsonl(out/'evidence_timeline.jsonl',observations); dump_jsonl(out/'commentary_segments.jsonl',all_segments); dump_jsonl(out/'claims.jsonl',all_claims); dump_jsonl(out/'missing_capability_queue.jsonl',missing)
    summary={'schema_version':'handoff-corpus-v2','eligible_seed_count':len(eligible),'seed_manifests':len(manifests),'commentary_segments':len(all_segments),'claims':len(all_claims),'observations':len(observations),'event_fixtures':len(fixtures),'capability_inventory_count':len(CAPABILITIES),'missing_capability_records':len(missing),'stage_semantics':{'bootstrap_labels':'silver only','speech_to_text':'pending','caption_ocr':'pending','ocr_stt_alignment':'pending','gameplay_reference_alignment':'pending'},'capability_fixture_counts':dict(Counter(f['capability'] for f in fixtures)),'note':'Fixtures are claim-linked and event-oriented. Reviewer assertions are silver/unverified; no detector predictions are fabricated.'}
    dump(out/'corpus_report.json',summary); print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=='__main__': main()
