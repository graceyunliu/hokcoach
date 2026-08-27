from __future__ import annotations

import argparse, json, re
from collections import Counter
from pathlib import Path
from typing import Any

from build_handoff_corpus import CAPABILITIES, claim_type, dump, dump_jsonl, probe_media, relevant_capabilities, sec, sha256, split_assertions

CAPTION_CONTEXT_TERMS = ['老娘求复盘', '第一视角进入复盘', 'intro screen', 'title screen', 'character selection']

def normalize_text(text: str) -> str:
    return re.sub(r'\s+', '', (text or '').strip()).lower()

def merge_caption_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(records, key=lambda r: float(r.get('timestamp_sec') or 0))
    merged: list[dict[str, Any]] = []
    for row in ordered:
        text = (row.get('text') or '').strip()
        if not text: continue
        start = float(row.get('timestamp_sec') or 0); end = float(row.get('end_sec') or start)
        if merged and normalize_text(merged[-1]['text']) == normalize_text(text) and start <= merged[-1]['end_sec'] + 1.5:
            merged[-1]['end_sec'] = max(merged[-1]['end_sec'], end)
            merged[-1]['confidence'] = merged[-1].get('confidence') or row.get('confidence')
            continue
        merged.append({'timestamp_sec': start, 'end_sec': end, 'text': text, 'confidence': row.get('confidence'), 'gameplay_state': row.get('gameplay_state'), 'source_file': row.get('source_file'), 'source':'burned_caption_reconstructed'})
    return merged

def is_context_only(text: str, state: str = '') -> bool:
    low = f'{text} {state}'.lower()
    return any(term.lower() in low for term in CAPTION_CONTEXT_TERMS) and not relevant_capabilities(text, '')

def main() -> None:
    ap=argparse.ArgumentParser(); ap.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1]); args=ap.parse_args(); root=args.root.resolve()
    seed=json.loads((root/'data/source_seeds/youtube/seed_manifest.json').read_text(encoding='utf-8'))
    ev=json.loads((root/'data/evaluation/replay_seeds/labeled_evaluation_set.json').read_text(encoding='utf-8'))
    cap=json.loads((root/'data/evaluation/replay_seeds/windowed_caption_analysis/merged_burned_captions.json').read_text(encoding='utf-8'))
    out=root/'data/evaluation/replay_seeds/corpus'; eligible=[r for r in seed.get('records',[]) if r.get('seed_eligibility')=='eligible-seed']; by_id={r['seed_id']:r for r in eligible}
    raw_by_seed:dict[str,list[dict[str,Any]]]={}
    for e in ev.get('events',[]):
        raw_by_seed.setdefault(e.get('seed_id'),[]).append({'start_sec':e.get('start_sec'),'end_sec':e.get('end_sec'),'text':e.get('coach_claim') or e.get('gameplay_event') or '','category':e.get('category',''),'source':'remote_multimodal_commentary','confidence':e.get('confidence')})
    target=next((r for r in eligible if r.get('video_id')==cap.get('source_video_id')),None)
    reconstructed=merge_caption_records(cap.get('records',[]))
    if target:
        for r in reconstructed:
            raw_by_seed.setdefault(target['seed_id'],[]).append({'start_sec':r['timestamp_sec'],'end_sec':r['end_sec'],'text':r['text'],'category':'','source':'burned_caption_reconstructed','confidence':r.get('confidence'),'gameplay_state':r.get('gameplay_state')})
    manifests=[]; source_segments=[]; claims=[]; observations=[]; fixtures=[]; inventory=[]; source_segment_count=0
    for src in eligible:
        sid,vid=src['seed_id'],src['video_id']; media=root/'data/evaluation/replay_seeds/media'/f'{vid}.webm'; probe=probe_media(media); ready=probe['status']=='complete'
        stage={'acquisition':'complete' if media.exists() else 'blocked_missing_media','media_probe':probe['status'],'bootstrap_labels':'available_silver_remote_multimodal' if raw_by_seed.get(sid) else 'unavailable','speech_to_text':'pending','caption_ocr':'pending','ocr_stt_alignment':'pending','gameplay_reference_alignment':'pending','detectors':'pending_execution' if ready else 'blocked_missing_media'}
        terminal='media_ready_transcript_pending' if ready else ('blocked_missing_media' if not media.exists() else 'media_probe_failed')
        manifest={'schema_version':'seed-source-v4','seed_id':sid,'video_id':vid,'url':src.get('url'),'title':src.get('title'),'hero':src.get('hero'),'role':src.get('role'),'series':src.get('series'),'rank_profile':src.get('rank_profile'),'artifact_path':str(media.relative_to(root)) if media.exists() else None,'artifact_sha256':sha256(media),'media_probe':probe,'timestamp_contract':{'captured_media_presentation_time':'unknown','normalized_derivative_time':'unknown','reviewer_speech_caption_time':'unknown','referenced_gameplay_time':'unknown'},'stage_status':stage,'terminal_status':terminal}
        manifests.append(manifest); dump(out/sid/'source_manifest.json',manifest)
        seed_sources=[]
        for raw in raw_by_seed.get(sid,[]):
            text=(raw.get('text') or '').strip(); start=sec(raw.get('start_sec')); end=sec(raw.get('end_sec')) or start
            if not text: continue
            seed_sources.append({'start_sec':start,'end_sec':end,'text':text,'category':raw.get('category') or '','source':raw.get('source'),'confidence':raw.get('confidence'),'gameplay_state':raw.get('gameplay_state')})
        for i,raw in enumerate(seed_sources):
            source_id=f'{sid}_{i:04d}'; text=raw['text']; category=raw['category']; context_only=is_context_only(text,raw.get('gameplay_state') or '')
            candidate={'start_sec':max(0,(raw.get('start_sec') or 0)-15),'end_sec':(raw.get('end_sec') or raw.get('start_sec') or 0)+10}
            source_seg={'segment_id':source_id,'seed_id':sid,'video_id':vid,'start_sec':raw.get('start_sec'),'end_sec':raw.get('end_sec'),'raw_text':text,'source':raw.get('source'),'source_category':category,'gameplay_state':raw.get('gameplay_state'),'candidate_gameplay_window':candidate,'label_tier':'silver','segment_kind':'context_only' if context_only else 'coaching_candidate','interval_status':'reconstructed' if raw.get('source')=='burned_caption_reconstructed' else 'source_interval'}
            source_segments.append(source_seg)
            observations.append({'observation_id':source_id+'_reviewer_commentary','source_segment_id':source_id,'video_id':vid,'type':'reviewer_commentary','start_sec':raw.get('start_sec'),'end_sec':raw.get('end_sec'),'subject':'reviewer','value':text,'confidence':raw.get('confidence'),'detector':'silver_bootstrap_remote_multimodal_v1','status':'observed_silver','evidence_refs':[f'seed:{sid}',f'source_segment:{source_id}']})
            pieces=split_assertions(text) if not context_only else []
            for j,piece in enumerate(pieces):
                claim_id=f'{source_id}_claim_{j:02d}'; caps=relevant_capabilities(piece,category); ctype=claim_type(piece,category)
                atomicity = 'sentence_split_unverified' if len(pieces)>1 else ('needs_atomic_review' if len(caps)>1 or re.search(r'\b(and|but|so|because|led to)\b|而且|但是|所以|因为|导致|并且', piece, re.I) else 'single_sentence_unverified')
                claim={'claim_id':claim_id,'source_segment_id':source_id,'claim_type':ctype,'claim_source':'reviewer','text':piece,'source_category':category,'required_evidence_types':['reviewer_commentary']+caps,'required_capabilities':caps,'support_status':'unknown','supporting_observation_ids':[],'commentary_start_sec':raw.get('start_sec'),'commentary_end_sec':raw.get('end_sec'),'candidate_gameplay_window':candidate,'atomicity_status':atomicity,'label_tier':'silver'}; claims.append(claim)
                for cap_name in caps:
                    expected={'objectives':'objective_state','towers':'tower_state','waves':'wave_state','teamfights':'teamfight_episode','cooldowns':'skill_or_spell_state','items_economy':'item_economy_state','minimap_positions':'player_position_or_vision','deaths':'player_death','death_location':'death_location','audio':'audio_event'}.get(cap_name,cap_name)
                    impl=CAPABILITIES[cap_name]; exec_status='not_run_missing_detector' if impl=='capability_missing' else ('pending_execution' if ready else 'blocked_missing_media')
                    fixtures.append({'fixture_id':claim_id+'_'+cap_name,'seed_id':sid,'video_id':vid,'capability':cap_name,'source_segment_id':source_id,'source_claim_id':claim_id,'source_window':candidate,'expected_observations':[{'type':expected,'subject':'unknown_or_player','time_range':None,'time_semantics':'unknown_gameplay_time','commentary_time_range':[raw.get('start_sec'),raw.get('end_sec')],'label_tier':'silver','verification_status':'unverified','source':'reviewer_assertion_not_gameplay_ground_truth'}],'current_predictions':[],'implementation_status':impl,'execution_status':exec_status,'evaluation_status':'capability_missing' if impl=='capability_missing' else ('pending_execution' if ready else 'blocked_missing_media')})
        dump_jsonl(out/sid/'source_segments.jsonl',[x for x in source_segments if x['seed_id']==sid]); dump_jsonl(out/sid/'observations.jsonl',[x for x in observations if x['source_segment_id'].startswith(sid+'_')]); dump_jsonl(out/sid/'claims.jsonl',[x for x in claims if x['source_segment_id'].startswith(sid+'_')])
    for cap_name in CAPABILITIES: dump_jsonl(out/f'fixtures/{cap_name}.jsonl',[f for f in fixtures if f['capability']==cap_name])
    for cap_name,impl in CAPABILITIES.items():
        if impl=='capability_missing': inventory.append({'capability':cap_name,'implementation_status':impl,'execution_status':'not_run_missing_detector','fixture_count':sum(f['capability']==cap_name for f in fixtures),'reason':'No production detector is present; linked claim fixtures remain backlog inputs.'})
    dump_jsonl(out/'manifests/source_manifest.jsonl',manifests); dump_jsonl(out/'source_segments.jsonl',source_segments); dump_jsonl(out/'observations.jsonl',observations); dump_jsonl(out/'claims.jsonl',claims); dump_jsonl(out/'missing_capability_queue.jsonl',inventory)
    summary={'schema_version':'handoff-corpus-v4','generator_version':'claim-model-v3-stable-corpus','eligible_seed_count':len(eligible),'source_segments':len(source_segments),'reviewer_observations':len(observations),'claims':len(claims),'event_fixtures':len(fixtures),'capability_inventory_count':len(inventory),'source_segment_model':'one_source_segment_to_one_reviewer_observation_to_one_or_more_child_claims','caption_records_raw':len(cap.get('records',[])),'caption_intervals_reconstructed':len(reconstructed),'caption_context_only_intervals':sum(is_context_only(r.get('text',''),r.get('gameplay_state','')) for r in reconstructed),'capability_fixture_counts':dict(Counter(f['capability'] for f in fixtures)),'gameplay_time_policy':'unknown_until_gameplay_reference_alignment','stage_semantics':{'bootstrap_labels':'silver only','speech_to_text':'pending','caption_ocr':'pending','ocr_stt_alignment':'pending','gameplay_reference_alignment':'pending'}}
    dump(out/'corpus_report.json',summary); print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=='__main__': main()
