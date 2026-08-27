from __future__ import annotations
import argparse, json, re
from collections import Counter
from pathlib import Path
from typing import Any
from build_handoff_corpus import CAPABILITIES, dump, dump_jsonl, probe_media, relevant_capabilities, sec, sha256

CONTEXT_TERMS=['老娘求复盘','第一视角进入复盘','intro screen','title screen','character selection']
PENDING={'pending','unavailable','blocked_missing_media','not_run_missing_detector',None}
def normalize(text:str)->str: return re.sub(r'\s+','',text or '').lower()
def context_only(text:str,state:str='')->bool:
    low=f'{text} {state}'.lower(); return any(x.lower() in low for x in CONTEXT_TERMS) and not relevant_capabilities(text,'')
def load(p:Path,default:Any):
    try: return json.loads(p.read_text(encoding='utf-8')) if p.exists() else default
    except (OSError, json.JSONDecodeError): return default
def read_jsonl(p:Path):
    if not p.exists(): return []
    out=[]
    for line in p.read_text(encoding='utf-8').splitlines():
        if line.strip():
            try: out.append(json.loads(line))
            except json.JSONDecodeError: pass
    return out
def preserve_jsonl(path:Path, records:list[dict[str,Any]]):
    if not path.exists(): dump_jsonl(path,records)
def preserve_or_merge_jsonl(path:Path, records:list[dict[str,Any]]):
    if not path.exists(): dump_jsonl(path,records); return records
    return read_jsonl(path)
def stable_stage(old:dict[str,Any], new:dict[str,Any]):
    result=dict(new)
    for k,v in old.items():
        if v not in PENDING: result[k]=v
    return result

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]); root=ap.parse_args().root.resolve(); out=root/'data/evaluation/replay_seeds/corpus'
    seeds=load(root/'data/source_seeds/youtube/seed_manifest.json',{'records':[]}); ev=load(root/'data/evaluation/replay_seeds/labeled_evaluation_set.json',{'events':[]}); cap=load(root/'data/evaluation/replay_seeds/windowed_caption_analysis/merged_burned_captions.json',{'records':[]})
    eligible=[r for r in seeds.get('records',[]) if r.get('seed_eligibility')=='eligible-seed']; boot=[]; windows=[]
    for i,e in enumerate(ev.get('events',[])):
        sid=e.get('seed_id'); text=e.get('coach_claim') or e.get('gameplay_event') or ''; start=sec(e.get('start_sec')); end=sec(e.get('end_sec')) or start; cat=e.get('category') or ''; bid=f'{sid}_remote_{i:04d}'; caps=relevant_capabilities(text,cat)
        boot.append({'bootstrap_id':bid,'seed_id':sid,'video_id':e.get('video_id'),'language':'en','source_video_language':'zh','representation':'ai_paraphrase','start_sec':start,'end_sec':end,'coach_claim':e.get('coach_claim'),'gameplay_event':e.get('gameplay_event'),'text':text,'category':cat,'confidence':e.get('confidence'),'label_tier':'silver_remote_multimodal','canonical':False})
        windows.append({'candidate_window_id':bid+'_window','seed_id':sid,'video_id':e.get('video_id'),'start_sec':max(0,(start or 0)-15),'end_sec':(end or start or 0)+10,'suggested_capabilities':caps,'source_bootstrap_id':bid,'verification_status':'unverified','canonical':False})
    target=next((r for r in eligible if r.get('video_id')==cap.get('source_video_id')),None); reconstructed=[]
    for r in sorted(cap.get('records',[]),key=lambda x:float(x.get('timestamp_sec') or 0)):
        text=(r.get('text') or '').strip(); start=sec(r.get('timestamp_sec')); end=sec(r.get('end_sec')) or start
        if not text: continue
        if reconstructed and normalize(reconstructed[-1]['text'])==normalize(text) and start <= reconstructed[-1]['end_sec']+1.5: reconstructed[-1]['end_sec']=max(reconstructed[-1]['end_sec'],end); continue
        reconstructed.append({'start_sec':start,'end_sec':end,'text':text,'confidence':r.get('confidence'),'gameplay_state':r.get('gameplay_state'),'source_file':r.get('source_file'),'source':'windowed_multimodal_caption_extraction'})
    hints=[]; manifests=[]; aggregate_segments=[]; aggregate_claims=[]; aggregate_obs=[]; aggregate_fixtures=[]
    for src in eligible:
        sid,vid=src['seed_id'],src['video_id']; vdir=out/'videos'/sid; tdir=vdir/'transcript'; media=root/'data/evaluation/replay_seeds/media'/f'{vid}.webm'; old=load(vdir/'source_manifest.json',{}); probe=probe_media(media); ready=probe['status']=='complete'
        derived_stage={'acquisition':'complete' if media.exists() else 'blocked_missing_media','media_probe':probe['status'],'bootstrap_labels':'available_silver_remote_multimodal' if any(b['seed_id']==sid for b in boot) else 'unavailable','speech_to_text':'pending','caption_ocr':'pending','ocr_stt_alignment':'pending','gameplay_reference_alignment':'pending','detectors':'pending_execution' if ready else 'blocked_missing_media'}
        stage=stable_stage(old.get('stage_status',{}),derived_stage); old_probe=old.get('media_probe') or {}; media_probe=old_probe if old_probe.get('status') in {'complete','failed'} else probe
        manifest={'schema_version':'seed-source-v4','generator_version':'claim-model-v4-bootstrap-canonical','seed_id':sid,'video_id':vid,'url':src.get('url'),'title':src.get('title'),'hero':src.get('hero'),'role':src.get('role'),'series':src.get('series'),'rank_profile':src.get('rank_profile'),'artifact_path':old.get('artifact_path') or (str(media.relative_to(root)) if media.exists() else None),'artifact_sha256':old.get('artifact_sha256') or sha256(media),'media_probe':media_probe,'timestamp_contract':old.get('timestamp_contract') or {'captured_media_presentation_time':'unknown','normalized_derivative_time':'unknown','reviewer_speech_caption_time':'unknown','referenced_gameplay_time':'unknown'},'stage_status':stage,'terminal_status':old.get('terminal_status') if old.get('terminal_status') not in PENDING else ('media_ready_transcript_pending' if ready else ('blocked_missing_media' if not media.exists() else 'media_probe_failed'))}
        manifests.append(manifest); dump(vdir/'source_manifest.json',manifest)
        # Never overwrite deterministic or completed per-seed outputs. Initialize only absent files.
        for name in ('speech_segments.jsonl','ocr_observations.jsonl','commentary_segments.jsonl','claims.jsonl','fixture_candidates.jsonl'):
            preserve_jsonl(tdir/name,[])
        if target and sid==target['seed_id']:
            hint_path=tdir/'windowed_multimodal_caption_hints.jsonl'; existing_hints=read_jsonl(hint_path)
            if existing_hints: hints.extend(existing_hints)
            else:
                for i,r in enumerate(reconstructed):
                    hints.append({'hint_id':f'{sid}_zh_hint_{i:04d}','seed_id':sid,'video_id':vid,'start_sec':r['start_sec'],'end_sec':r['end_sec'],'raw_text':r['text'],'language':'zh','source_video_language':'zh','representation':'windowed_multimodal_caption_extraction','canonical':False,'label_tier':'silver_windowed_multimodal','confidence':r['confidence'],'gameplay_state':r.get('gameplay_state'),'context_only':context_only(r['text'],r.get('gameplay_state') or ''),'verification_status':'unverified','promotion_rule':'requires_deterministic_ocr_or_stt_verification'})
                dump_jsonl(hint_path,hints)
        # Canonical aggregates are rebuilt only from existing per-seed outputs.
        aggregate_segments.extend(read_jsonl(tdir/'commentary_segments.jsonl'))
        aggregate_claims.extend(read_jsonl(vdir/'claims.jsonl'))
        aggregate_obs.extend(read_jsonl(tdir/'ocr_observations.jsonl'))
        aggregate_fixtures.extend(read_jsonl(vdir/'fixture_candidates.jsonl'))
    # Bootstrap inputs may be rebuilt; canonical outputs are never synthesized from them.
    dump_jsonl(out/'bootstrap'/'remote_multimodal_annotations.jsonl',boot); dump_jsonl(out/'bootstrap'/'candidate_windows.jsonl',windows); dump_jsonl(out/'bootstrap'/'chinese_windowed_caption_hints.jsonl',hints)
    dump_jsonl(out/'aggregates'/'canonical_commentary_segments.jsonl',aggregate_segments); dump_jsonl(out/'aggregates'/'canonical_claims.jsonl',aggregate_claims); dump_jsonl(out/'aggregates'/'evidence_timeline.jsonl',aggregate_obs); dump_jsonl(out/'aggregates'/'detector_fixtures.jsonl',aggregate_fixtures); dump_jsonl(out/'aggregates'/'manifests.jsonl',manifests)
    missing=[{'capability':c,'implementation_status':s,'execution_status':'not_run_missing_detector','fixture_count':sum(f.get('capability')==c for f in aggregate_fixtures)} for c,s in CAPABILITIES.items() if s=='capability_missing']; dump_jsonl(out/'aggregates'/'missing_capability_queue.jsonl',missing)
    summary={'schema_version':'handoff-corpus-v4','generator_version':'claim-model-v4-bootstrap-canonical','eligible_seed_count':len(eligible),'bootstrap':{'english_ai_paraphrases':len(boot),'candidate_windows':len(windows),'chinese_windowed_caption_hints':len(hints),'chinese_context_only_hints':sum(h.get('context_only',False) for h in hints)},'canonical':{'chinese_ocr_observations':len(aggregate_obs),'chinese_commentary_segments':len(aggregate_segments),'claims':len(aggregate_claims),'reviewer_observations':len(aggregate_obs),'event_fixtures':len(aggregate_fixtures)},'canonical_language':'zh','bootstrap_language':'en','canonical_promotion_policy':'Only deterministic OCR/STT or fused verified intervals may enter canonical aggregates','gameplay_time_policy':'unknown_until_gameplay_reference_alignment','capability_fixture_counts':dict(Counter(f.get('capability') for f in aggregate_fixtures))}
    dump(out/'aggregates'/'corpus_report.json',summary); print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=='__main__': main()
