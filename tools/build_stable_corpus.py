from __future__ import annotations

import argparse, json, re
from collections import Counter
from pathlib import Path
from typing import Any

from build_handoff_corpus import CAPABILITIES, claim_type, dump, dump_jsonl, probe_media, relevant_capabilities, sec, sha256, split_assertions

CONTEXT_TERMS=['老娘求复盘','第一视角进入复盘','intro screen','title screen','character selection']

def normalize(text:str)->str: return re.sub(r'\s+','',text or '').lower()
def context_only(text:str,state:str='')->bool:
    low=f'{text} {state}'.lower()
    return any(x.lower() in low for x in CONTEXT_TERMS) and not relevant_capabilities(text,'')

def load_json(p:Path, default:Any): return json.loads(p.read_text(encoding='utf-8')) if p.exists() else default

def build() -> None:
    ap=argparse.ArgumentParser(); ap.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]); args=ap.parse_args(); root=args.root.resolve()
    seed=load_json(root/'data/source_seeds/youtube/seed_manifest.json',{'records':[]})
    evaluation=load_json(root/'data/evaluation/replay_seeds/labeled_evaluation_set.json',{'events':[]})
    cap=load_json(root/'data/evaluation/replay_seeds/windowed_caption_analysis/merged_burned_captions.json',{'records':[]})
    out=root/'data/evaluation/replay_seeds/corpus'; eligible=[r for r in seed.get('records',[]) if r.get('seed_eligibility')=='eligible-seed']
    # English remote multimodal records are bootstrap-only annotations.
    boot=[]; windows=[]
    for i,e in enumerate(evaluation.get('events',[])):
        sid=e.get('seed_id'); text=e.get('coach_claim') or e.get('gameplay_event') or ''; start=sec(e.get('start_sec')); end=sec(e.get('end_sec')) or start; cat=e.get('category') or ''
        bid=f'{sid}_remote_{i:04d}'; caps=relevant_capabilities(text,cat); boot.append({'bootstrap_id':bid,'seed_id':sid,'video_id':e.get('video_id'),'language':'en','source_video_language':'zh','representation':'ai_paraphrase','start_sec':start,'end_sec':end,'coach_claim':e.get('coach_claim'),'gameplay_event':e.get('gameplay_event'),'text':text,'category':cat,'confidence':e.get('confidence'),'label_tier':'silver_remote_multimodal','canonical':False})
        windows.append({'candidate_window_id':bid+'_window','seed_id':sid,'video_id':e.get('video_id'),'start_sec':max(0,(start or 0)-15),'end_sec':(end or start or 0)+10,'suggested_capabilities':caps,'source_bootstrap_id':bid,'verification_status':'unverified','canonical':False})
    # Canonical evidence currently comes only from the reconstructed Chinese burned captions.
    target=next((r for r in eligible if r.get('video_id')==cap.get('source_video_id')),None); reconstructed=[]
    for r in sorted(cap.get('records',[]),key=lambda x:float(x.get('timestamp_sec') or 0)):
        text=(r.get('text') or '').strip(); start=sec(r.get('timestamp_sec')); end=sec(r.get('end_sec')) or start
        if not text: continue
        if reconstructed and normalize(reconstructed[-1]['raw_text'])==normalize(text) and start <= reconstructed[-1]['end_sec']+1.5:
            reconstructed[-1]['end_sec']=max(reconstructed[-1]['end_sec'],end); continue
        reconstructed.append({'start_sec':start,'end_sec':end,'raw_text':text,'ocr_text':text,'confidence':r.get('confidence'),'gameplay_state':r.get('gameplay_state'),'source_file':r.get('source_file'),'source':'burned_caption_reconstructed'})
    canonical_segments=[]; canonical_claims=[]; canonical_obs=[]; fixtures=[]; inventory=[]; manifests=[]
    per_seed_ocr:dict[str,list[dict[str,Any]]]={}; per_seed_intervals:dict[str,list[dict[str,Any]]]={}; per_seed_segments:dict[str,list[dict[str,Any]]]={}; per_seed_claims:dict[str,list[dict[str,Any]]]={}; per_seed_fixtures:dict[str,list[dict[str,Any]]]={}
    by_seed_boot=Counter(b['seed_id'] for b in boot); by_seed_can=Counter()
    for src in eligible:
        sid,vid=src['seed_id'],src['video_id']; media=root/'data/evaluation/replay_seeds/media'/f'{vid}.webm'; probe=probe_media(media); ready=probe['status']=='complete'
        stage={'acquisition':'complete' if media.exists() else 'blocked_missing_media','media_probe':probe['status'],'bootstrap_labels':'available_silver_remote_multimodal' if by_seed_boot[sid] else 'unavailable','speech_to_text':'pending','caption_ocr':'pending','ocr_stt_alignment':'pending','gameplay_reference_alignment':'pending','detectors':'pending_execution' if ready else 'blocked_missing_media'}
        manifest={'schema_version':'seed-source-v4','generator_version':'claim-model-v3-stable-corpus','seed_id':sid,'video_id':vid,'url':src.get('url'),'title':src.get('title'),'hero':src.get('hero'),'role':src.get('role'),'series':src.get('series'),'rank_profile':src.get('rank_profile'),'artifact_path':str(media.relative_to(root)) if media.exists() else None,'artifact_sha256':sha256(media),'media_probe':probe,'timestamp_contract':{'captured_media_presentation_time':'unknown','normalized_derivative_time':'unknown','reviewer_speech_caption_time':'unknown','referenced_gameplay_time':'unknown'},'stage_status':stage,'terminal_status':'media_ready_transcript_pending' if ready else ('blocked_missing_media' if not media.exists() else 'media_probe_failed')}
        manifests.append(manifest); dump(out/'videos'/sid/'source_manifest.json',manifest); dump_jsonl(out/'videos'/sid/'transcript'/'speech_segments.jsonl',[])
        if target and sid==target['seed_id']:
            for i,r in enumerate(reconstructed):
                context=context_only(r['raw_text'],r.get('gameplay_state') or ''); oid=f'{sid}_zh_{i:04d}'; by_seed_can[sid]+=0 if context else 1
                ocr={'ocr_observation_id':oid+'_ocr','source_segment_id':oid,'seed_id':sid,'video_id':vid,'start_sec':r['start_sec'],'end_sec':r['end_sec'],'text':r['ocr_text'],'confidence':r['confidence'],'language':'zh','representation':'source_transcript','canonical':True,'source':r['source'],'gameplay_state':r.get('gameplay_state'),'context_only':context,'verification_status':'silver_unverified'}
                per_seed_ocr.setdefault(sid,[]).append(ocr)
                if context: continue
                candidate={'start_sec':max(0,(r['start_sec'] or 0)-15),'end_sec':(r['end_sec'] or r['start_sec'] or 0)+10}; seg={'segment_id':oid,'seed_id':sid,'video_id':vid,'start_sec':r['start_sec'],'end_sec':r['end_sec'],'raw_text':r['raw_text'],'language':'zh','representation':'source_transcript','canonical':True,'source':'burned_caption_reconstructed','label_tier':'silver','candidate_gameplay_window':candidate,'segment_kind':'coaching_candidate'}; canonical_segments.append(seg); canonical_obs.append({'observation_id':oid+'_reviewer_commentary','source_segment_id':oid,'video_id':vid,'type':'reviewer_commentary','start_sec':r['start_sec'],'end_sec':r['end_sec'],'value':r['raw_text'],'language':'zh','canonical':True,'status':'observed_silver'})
                pieces=split_assertions(r['raw_text'])
                for j,piece in enumerate(pieces):
                    caps=relevant_capabilities(piece,''); ctype=claim_type(piece,''); cid=f'{oid}_claim_{j:02d}'; atom='sentence_split_unverified' if len(pieces)>1 else ('needs_atomic_review' if len(caps)>1 or re.search(r'\b(and|but|so|because|led to)\b|而且|但是|所以|因为|导致|并且',piece,re.I) else 'single_sentence_unverified')
                    cl={'claim_id':cid,'source_segment_id':oid,'claim_type':ctype,'text':piece,'language':'zh','canonical':True,'source_category':'','required_capabilities':caps,'required_evidence_types':['canonical_chinese_commentary']+caps,'support_status':'unknown','commentary_start_sec':r['start_sec'],'commentary_end_sec':r['end_sec'],'candidate_gameplay_window':candidate,'atomicity_status':atom,'label_tier':'silver'}; canonical_claims.append(cl)
                    for cap_name in caps:
                        expected={'objectives':'objective_state','towers':'tower_state','waves':'wave_state','teamfights':'teamfight_episode','cooldowns':'skill_or_spell_state','items_economy':'item_economy_state','minimap_positions':'player_position_or_vision','deaths':'player_death'}.get(cap_name,cap_name); impl=CAPABILITIES[cap_name]; ex='not_run_missing_detector' if impl=='capability_missing' else ('pending_execution' if ready else 'blocked_missing_media'); fixtures.append({'fixture_id':cid+'_'+cap_name,'source_segment_id':oid,'source_claim_id':cid,'seed_id':sid,'video_id':vid,'capability':cap_name,'source_window':candidate,'expected_observations':[{'type':expected,'time_range':None,'time_semantics':'unknown_gameplay_time','commentary_time_range':[r['start_sec'],r['end_sec']],'language':'zh','canonical':True,'label_tier':'silver','verification_status':'unverified'}],'current_predictions':[],'implementation_status':impl,'execution_status':ex,'evaluation_status':'capability_missing' if impl=='capability_missing' else ('pending_execution' if ready else 'blocked_missing_media')})
                per_seed_intervals.setdefault(sid,[]).append(r)
                per_seed_segments.setdefault(sid,[]).append(seg)
                per_seed_claims.setdefault(sid,[]).extend([x for x in canonical_claims if x['source_segment_id']==oid])
                per_seed_fixtures.setdefault(sid,[]).extend([x for x in fixtures if x['source_segment_id']==oid])
    for src in eligible:
        sid=src['seed_id']
        dump_jsonl(out/'videos'/sid/'transcript'/'ocr_observations.jsonl',per_seed_ocr.get(sid,[]))
        dump_jsonl(out/'videos'/sid/'transcript'/'ocr_intervals.jsonl',per_seed_intervals.get(sid,[]))
        dump_jsonl(out/'videos'/sid/'transcript'/'commentary_segments.jsonl',per_seed_segments.get(sid,[]))
        dump_jsonl(out/'videos'/sid/'claims.jsonl',per_seed_claims.get(sid,[]))
        dump_jsonl(out/'videos'/sid/'fixture_candidates.jsonl',per_seed_fixtures.get(sid,[]))
    dump_jsonl(out/'bootstrap'/'remote_multimodal_annotations.jsonl',boot); dump_jsonl(out/'bootstrap'/'candidate_windows.jsonl',windows)
    dump_jsonl(out/'aggregates'/'canonical_commentary_segments.jsonl',canonical_segments); dump_jsonl(out/'aggregates'/'canonical_claims.jsonl',canonical_claims); dump_jsonl(out/'aggregates'/'evidence_timeline.jsonl',canonical_obs); dump_jsonl(out/'aggregates'/'detector_fixtures.jsonl',fixtures); dump_jsonl(out/'aggregates'/'manifests.jsonl',manifests)
    missing=[{'capability':c,'implementation_status':s,'execution_status':'not_run_missing_detector','fixture_count':sum(f['capability']==c for f in fixtures)} for c,s in CAPABILITIES.items() if s=='capability_missing']; dump_jsonl(out/'aggregates'/'missing_capability_queue.jsonl',missing)
    summary={'schema_version':'handoff-corpus-v4','generator_version':'claim-model-v3-stable-corpus','eligible_seed_count':len(eligible),'bootstrap':{'english_ai_paraphrases':len(boot),'candidate_windows':len(windows)},'canonical':{'chinese_ocr_observations':len(reconstructed),'chinese_commentary_segments':len(canonical_segments),'claims':len(canonical_claims),'reviewer_observations':len(canonical_obs),'event_fixtures':len(fixtures)},'canonical_context_only_intervals':sum(context_only(r['raw_text'],r.get('gameplay_state') or '') for r in reconstructed),'canonical_language':'zh','bootstrap_language':'en','source_segment_model':'one_canonical_source_segment_to_one_reviewer_observation_to_one_or_more_child_claims','gameplay_time_policy':'unknown_until_gameplay_reference_alignment','stage_semantics':{'bootstrap_labels':'silver only','speech_to_text':'pending','caption_ocr':'pending','ocr_stt_alignment':'pending','gameplay_reference_alignment':'pending'},'capability_fixture_counts':dict(Counter(f['capability'] for f in fixtures))}
    dump(out/'aggregates'/'corpus_report.json',summary); print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=='__main__': build()
