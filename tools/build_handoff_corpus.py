from __future__ import annotations

import argparse, hashlib, json, re, subprocess
from collections import Counter
from pathlib import Path
from typing import Any

CAPABILITIES = {
    'deaths': 'implemented_partial', 'death_location': 'implemented_partial',
    'minimap_positions': 'implemented_partial', 'audio': 'implemented_partial',
    'objectives': 'capability_missing', 'towers': 'capability_missing',
    'lifecycle': 'capability_missing', 'items_economy': 'capability_missing',
    'waves': 'capability_missing', 'teamfights': 'capability_missing',
    'cooldowns': 'capability_missing',
}
KEYWORDS = {
    'objectives': ['龙王','暴君','主宰','风暴','开龙','抢龙','objective','dragon','lord','tyrant','buff'],
    'towers': ['塔','水晶','高地','二塔','推掉','tower','turret','inhibitor','base'],
    'waves': ['线权','清线','兵线','转线','支援','游走','河道','wave','lane','rotate','rotation','roam','minion'],
    'teamfights': ['团战','打团','人堆','掉点','救人','换一换','teamfight','team fight','fight','engage','follow up'],
    'cooldowns': ['闪现','技能','大招','金身','拉到','连招','操作','flash','skill','ultimate','ult','cooldown','combo','mechanic'],
    'items_economy': ['装备','复活甲','出装','经济','钱','item','build','gold','economy','farm','farming'],
    'minimap_positions': ['蹲','视野','草','地图','信号','对面不见','位置','vision','bush','brush','minimap','map awareness','position'],
    'deaths': ['死','死亡','复活','被击杀','被融化','death','died','kill','kda','respawn'],
}
CATEGORY_MAP = {
    'objective_conversion': ['objectives'], 'objective': ['objectives'],
    'tower': ['towers'], 'towers': ['towers'],
    'wave_resource': ['waves'], 'wave': ['waves'],
    'teamfight': ['teamfights'], 'team_fight': ['teamfights'],
    'mechanics': ['cooldowns'], 'skill': ['cooldowns'],
    'items': ['items_economy'], 'item': ['items_economy'],
    'vision': ['minimap_positions'], 'macro': [],
    'death': ['deaths'],
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

def category_caps(category: str) -> list[str]:
    c = (category or '').strip().lower().replace(' ', '_')
    return list(CATEGORY_MAP.get(c, []))

def relevant_capabilities(text: str, category: str = '') -> list[str]:
    found = set(category_caps(category))
    low = (text or '').lower()
    for cap, words in KEYWORDS.items():
        if any(w.lower() in low for w in words): found.add(cap)
    return sorted(found)

def claim_type(text: str, category: str) -> str:
    caps = relevant_capabilities(text, category)
    if 'objectives' in caps: return 'objective_reference'
    if 'towers' in caps: return 'tower_or_base_reference'
    if 'waves' in caps: return 'lane_or_rotation'
    if 'teamfights' in caps: return 'teamfight_reference'
    if 'cooldowns' in caps: return 'mechanics_or_cooldown'
    if 'items_economy' in caps: return 'item_or_economy_reference'
    if 'minimap_positions' in caps: return 'vision_or_map_awareness'
    if 'deaths' in caps: return 'death_reference'
    return 'reviewer_commentary'

def probe_media(path: Path) -> dict[str, Any]:
    if not path.exists(): return {'status':'blocked_missing_media'}
    try:
        raw = subprocess.run(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(path)], check=True, capture_output=True, text=True, timeout=30).stdout
        data = json.loads(raw)
        streams = data.get('streams', [])
        fmt = data.get('format', {})
        return {'status':'complete','duration_sec':float(fmt.get('duration')) if fmt.get('duration') else None,'stream_count':len(streams),'has_video':any(s.get('codec_type')=='video' for s in streams),'has_audio':any(s.get('codec_type')=='audio' for s in streams),'format_name':fmt.get('format_name')}
    except Exception as exc:
        return {'status':'failed','error':str(exc)}

def main() -> None:
    ap = argparse.ArgumentParser(); ap.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1]); args = ap.parse_args(); root=args.root.resolve()
    seed_path=root/'data/source_seeds/youtube/seed_manifest.json'; eval_path=root/'data/evaluation/replay_seeds/labeled_evaluation_set.json'; cap_path=root/'data/evaluation/replay_seeds/windowed_caption_analysis/merged_burned_captions.json'; out=root/'data/evaluation/replay_seeds/handoff_v3'
    source=json.loads(seed_path.read_text(encoding='utf-8')); eval_data=json.loads(eval_path.read_text(encoding='utf-8')) if eval_path.exists() else {'events':[]}; cap_data=json.loads(cap_path.read_text(encoding='utf-8')) if cap_path.exists() else {'records':[]}
    eligible=[r for r in source.get('records',[]) if r.get('seed_eligibility')=='eligible-seed']; events_by_seed:dict[str,list[dict[str,Any]]]={}
    for e in eval_data.get('events',[]): events_by_seed.setdefault(e.get('seed_id'),[]).append(e)
    commentary_by_seed:dict[str,list[dict[str,Any]]]={}
    target=next((r for r in eligible if r.get('video_id')==cap_data.get('source_video_id')),None)
    if target:
        for r in cap_data.get('records',[]): commentary_by_seed.setdefault(target['seed_id'],[]).append({'start_sec':r.get('timestamp_sec'),'end_sec':r.get('end_sec'),'text':r.get('text'),'confidence':r.get('confidence'),'source':'windowed_multimodal_burned_caption','category':r.get('category','')})
    manifests=[]; segments=[]; claims=[]; observations=[]; fixtures=[]; inventory=[]
    for src in eligible:
        sid,vid=src['seed_id'],src['video_id']; media=root/'data/evaluation/replay_seeds/media'/f'{vid}.webm'; probe=probe_media(media); media_ready=probe['status']=='complete'
        raw_segments=[]
        for e in events_by_seed.get(sid,[]): raw_segments.append({'start_sec':e.get('start_sec'),'end_sec':e.get('end_sec'),'text':e.get('coach_claim') or e.get('gameplay_event') or '','confidence':e.get('confidence'),'source':'remote_multimodal_commentary','category':e.get('category','')})
        raw_segments.extend(commentary_by_seed.get(sid,[]))
        stage={'acquisition':'complete' if media.exists() else 'blocked_missing_media','media_probe':probe['status'],'bootstrap_labels':'available_silver_remote_multimodal' if raw_segments else 'unavailable','speech_to_text':'pending','caption_ocr':'pending','ocr_stt_alignment':'pending','gameplay_reference_alignment':'pending','detectors': 'pending_execution' if media_ready else 'blocked_missing_media'}
        manifest={'schema_version':'seed-source-v3','seed_id':sid,'video_id':vid,'url':src.get('url'),'title':src.get('title'),'hero':src.get('hero'),'role':src.get('role'),'series':src.get('series'),'rank_profile':src.get('rank_profile'),'artifact_path':str(media.relative_to(root)) if media.exists() else None,'artifact_sha256':sha256(media),'media_probe':probe,'capture_method':None,'timestamp_contract':{'captured_media_presentation_time':'unknown','normalized_derivative_time':'unknown','reviewer_speech_caption_time':'unknown','referenced_gameplay_time':'unknown'},'stage_status':stage,'terminal_status':'media_ready_transcript_pending' if media_ready else ('blocked_missing_media' if not media.exists() else 'media_probe_failed'),'errors':[]}
        manifests.append(manifest); dump(out/sid/'source_manifest.json',manifest)
        for i,seg in enumerate(raw_segments):
            rid=f'{sid}_{i:04d}'; start=sec(seg.get('start_sec')); end=sec(seg.get('end_sec')) or start; text=seg.get('text') or ''; category=seg.get('category') or ''
            caps=relevant_capabilities(text,category); ctype=claim_type(text,category); candidate={'start_sec':max(0,(start or 0)-15),'end_sec':(end or start or 0)+10}
            segments.append({'segment_id':rid,'seed_id':sid,'video_id':vid,'source_category':category,'commentary_start_sec':start,'commentary_end_sec':end,'speech_text_raw':text if seg.get('source')=='remote_multimodal_commentary' else None,'ocr_text_raw':text if seg.get('source')=='windowed_multimodal_burned_caption' else None,'normalized_text':text,'alignment_method':'silver_bootstrap_only','alignment_confidence':seg.get('confidence'),'candidate_gameplay_window':candidate,'accepted_gameplay_window':None,'unresolved_reference':True,'label_tier':'silver'})
            claim={'claim_id':rid+'_claim','claim_type':ctype,'claim_source':'reviewer','text':text,'source_category':category,'required_evidence_types':['reviewer_commentary']+caps,'required_capabilities':caps,'support_status':'unknown','supporting_observation_ids':[],'commentary_start_sec':start,'commentary_end_sec':end,'candidate_gameplay_window':candidate,'atomicity_status':'single_caption_assertion'}; claims.append(claim)
            observations.append({'observation_id':rid+'_reviewer_commentary','video_id':vid,'type':'reviewer_commentary','start_sec':start,'end_sec':end,'subject':'reviewer','value':text,'confidence':seg.get('confidence'),'detector':'silver_bootstrap_remote_multimodal_v1','detector_config_version':'silver','evidence_refs':[f'seed:{sid}',f'commentary_segment:{rid}'],'status':'observed_silver'})
            for cap in caps:
                expected={'objectives':'objective_state','towers':'tower_state','waves':'wave_state','teamfights':'teamfight_episode','cooldowns':'skill_or_spell_state','items_economy':'item_economy_state','minimap_positions':'player_position_or_vision','deaths':'player_death','death_location':'death_location','audio':'audio_event'}.get(cap,cap)
                exec_status='not_run_missing_detector' if CAPABILITIES[cap]=='capability_missing' else ('pending_execution' if media_ready else 'blocked_missing_media')
                fixtures.append({'fixture_id':rid+'_'+cap,'seed_id':sid,'video_id':vid,'capability':cap,'source_commentary_segment_id':rid,'source_claim_id':claim['claim_id'],'source_window':candidate,'expected_observations':[{'type':expected,'subject':'unknown_or_player','time_range':None,'time_semantics':'unknown_gameplay_time','commentary_time_range':[start,end],'label_tier':'silver','verification_status':'unverified','source':'reviewer_assertion_not_gameplay_ground_truth'}],'current_predictions':[],'implementation_status':CAPABILITIES[cap],'execution_status':exec_status,'evaluation_status':'capability_missing' if CAPABILITIES[cap]=='capability_missing' else ('pending_execution' if media_ready else 'blocked_missing_media')})
        dump_jsonl(out/sid/'commentary_segments.jsonl',[x for x in segments if x['seed_id']==sid]); dump_jsonl(out/sid/'claims.jsonl',[x for x in claims if x['claim_id'].startswith(sid+'_')])
    for cap in CAPABILITIES: dump_jsonl(out/f'fixtures/{cap}.jsonl',[f for f in fixtures if f['capability']==cap])
    for cap,status in CAPABILITIES.items():
        if status=='capability_missing': inventory.append({'capability':cap,'implementation_status':status,'execution_status':'not_run_missing_detector','fixture_count':sum(f['capability']==cap for f in fixtures),'reason':'No production detector is present; linked fixtures are retained for a separate detector project.'})
    dump_jsonl(out/'manifests/source_manifest.jsonl',manifests); dump_jsonl(out/'evidence_timeline.jsonl',observations); dump_jsonl(out/'commentary_segments.jsonl',segments); dump_jsonl(out/'claims.jsonl',claims); dump_jsonl(out/'missing_capability_queue.jsonl',inventory)
    summary={'schema_version':'handoff-corpus-v3','eligible_seed_count':len(eligible),'seed_manifests':len(manifests),'commentary_segments':len(segments),'claims':len(claims),'observations':len(observations),'event_fixtures':len(fixtures),'capability_inventory_count':len(inventory),'capability_fixture_counts':dict(Counter(f['capability'] for f in fixtures)),'routing_source_categories_preserved':True,'bilingual_keyword_routing':True,'gameplay_time_policy':'unknown_until_gameplay_reference_alignment','stage_semantics':{'bootstrap_labels':'silver only','speech_to_text':'pending','caption_ocr':'pending','ocr_stt_alignment':'pending','gameplay_reference_alignment':'pending'},'note':'Reviewer assertions are silver/unverified. Current predictions are empty; detector status is derived from media probe and capability availability.'}
    dump(out/'corpus_report.json',summary); print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=='__main__': main()
