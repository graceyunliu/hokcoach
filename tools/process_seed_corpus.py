from __future__ import annotations
import argparse, hashlib, json, os, shutil, subprocess, tempfile, time, difflib, re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STAGES=['media_probe','audio_extraction','speech_to_text','caption_sampling','caption_ocr','ocr_interval_reconstruction','commentary_fusion','claim_extraction','fixture_generation','detectors','aggregate_participation','retention_cleanup']
DESC={'media_probe':[],'audio_extraction':['media_probe'],'speech_to_text':['audio_extraction'],'caption_sampling':['media_probe'],'caption_ocr':['caption_sampling'],'ocr_interval_reconstruction':['caption_ocr'],'commentary_fusion':['speech_to_text','ocr_interval_reconstruction'],'claim_extraction':['commentary_fusion'],'fixture_generation':['claim_extraction','detectors'],'detectors':['media_probe'],'aggregate_participation':[],'retention_cleanup':[]}
DESCENDANTS={s:[] for s in STAGES}
for child,deps in DESC.items():
    for dep in deps: DESCENDANTS[dep].append(child)
def descendants(stage):
    out=[]
    for child in DESCENDANTS.get(stage,[]): out += [child]+descendants(child)
    return list(dict.fromkeys(out))
ALLOWED={'pending','running','complete','failed_retryable','failed_permanent','blocked','stale'}
SCHEMA='incremental-corpus-v1'; IMPLEMENTATION='process-seed-corpus-v1'

def now(): return datetime.now(timezone.utc).isoformat()
def cjson(x): return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def fp(x): return hashlib.sha256(cjson(x).encode()).hexdigest()
def file_hash(p):
    if not p.exists() or not p.is_file(): return None
    h=hashlib.sha256();
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()
def read_json(p, default):
    try: return json.loads(p.read_text(encoding='utf-8')) if p.exists() else default
    except (OSError,json.JSONDecodeError): return default
def rows(p):
    if not p.exists(): return []
    out=[]
    for line in p.read_text(encoding='utf-8').splitlines():
        if line.strip():
            try: out.append(json.loads(line))
            except json.JSONDecodeError: pass
    return out
def atomic_text(p,text):
    p.parent.mkdir(parents=True,exist_ok=True); fd,tmp=tempfile.mkstemp(prefix=f'.{p.name}.',dir=p.parent); os.close(fd)
    try:
        Path(tmp).write_text(text,encoding='utf-8'); os.replace(tmp,p)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)
def atomic_json(p,obj): atomic_text(p,json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
def atomic_jsonl(p,items): atomic_text(p,''.join(json.dumps(x,ensure_ascii=False,sort_keys=True)+'\n' for x in items))
def run(cmd): return subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
def probe(media):
    if not media.exists(): return {'status':'blocked_missing_media','expected_path':str(media),'duration_sec':None,'video_stream':False}
    r=run(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(media)])
    if r.returncode: return {'status':'failed','error':r.stderr[-1000:],'video_stream':False}
    try: data=json.loads(r.stdout); streams=data.get('streams',[]); vs=next((s for s in streams if s.get('codec_type')=='video'),None); duration=float((data.get('format') or {}).get('duration') or 0)
    except (ValueError,json.JSONDecodeError): return {'status':'failed','error':'invalid_ffprobe_json','video_stream':False}
    if not vs or duration<=0: return {'status':'failed','error':'no_usable_video_stream_or_duration','video_stream':bool(vs),'duration_sec':duration}
    return {'status':'complete','duration_sec':duration,'video_stream':True,'width':vs.get('width'),'height':vs.get('height'),'frame_rate':vs.get('r_frame_rate'),'codec':vs.get('codec_name'),'audio_stream':any(s.get('codec_type')=='audio' for s in streams)}
def default_stage(): return {'status':'pending','input_fingerprint':None,'implementation_version':IMPLEMENTATION,'configuration_hash':None,'model_version':None,'started_at':None,'completed_at':None,'output_paths':[],'output_hashes':{},'error':None,'blocked_by':[]}
def load_stage(p):
    old=read_json(p,{}); stages=old.get('stages',{})
    for s in STAGES: stages.setdefault(s,default_stage())
    return {'schema_version':SCHEMA,'seed_id':old.get('seed_id'),'updated_at':old.get('updated_at'), 'stages':stages}
def save_stage(p,m): m['updated_at']=now(); atomic_json(p,m)
def output_hashes(paths): return {str(p):file_hash(Path(p)) for p in paths if Path(p).exists()}
def valid_hit(rec,input_fp):
    return rec.get('status')=='complete' and rec.get('input_fingerprint')==input_fp and bool(rec.get('output_paths')) and all(file_hash(Path(p))==h for p,h in rec.get('output_hashes',{}).items())
def set_stage(m,name,status,**kw):
    r=m['stages'][name]; r.update(status=status,**kw); return r
def invalidate(m,start):
    for s in [start]+descendants(start): set_stage(m,s,'stale',error=None,blocked_by=[])
def ensure_empty(p):
    if not p.exists(): atomic_jsonl(p,[])
def norm(s): return re.sub(r'\s+','',str(s or '')).lower()
def reconstruct_intervals(observations):
    out=[]
    for o in sorted(observations,key=lambda x:float(x.get('start_sec') or 0)):
        text=o.get('text') or o.get('ocr_text') or ''; start=float(o.get('start_sec') or o.get('timestamp_sec') or 0); end=float(o.get('end_sec') or start)
        if not text: continue
        if out and start-out[-1]['end_sec']<=1.5 and (norm(out[-1]['raw_text'])==norm(text) or difflib.SequenceMatcher(None,norm(out[-1]['raw_text']),norm(text)).ratio()>=0.92):
            x=out[-1]; x['end_sec']=max(x['end_sec'],end); x['source_observation_ids'].append(o.get('observation_id')); x['raw_text_variants']=sorted(set(x['raw_text_variants']+[text])); x['observation_count']+=1; x['merge_reason']='normalized_match_or_high_character_similarity_short_gap'; x['confidence_min']=min(x['confidence_min'],float(o.get('confidence') or 0) if str(o.get('confidence') or '').replace('.','',1).isdigit() else x['confidence_min']); continue
        out.append({'interval_id':f"ocr_interval_{len(out):06d}",'seed_id':o.get('seed_id'),'video_id':o.get('video_id'),'start_sec':start,'end_sec':end,'raw_text':text,'raw_text_variants':[text],'source_observation_ids':[o.get('observation_id')],'observation_count':1,'confidence_min':float(o.get('confidence') or 0) if str(o.get('confidence') or '').replace('.','',1).isdigit() else None,'stability_score':1.0,'merge_reason':'new_interval','language':'zh','representation':'source_transcript','canonical':True})
    return out
def fuse_records(speech, intervals):
    out=[]; used=set()
    for s in sorted(speech,key=lambda x:float(x.get('start_sec') or 0)):
        ss=float(s.get('start_sec') or 0); se=float(s.get('end_sec') or ss); matches=[o for o in intervals if o.get('interval_id') not in used and float(o.get('end_sec') or 0)>=ss-1 and float(o.get('start_sec') or 0)<=se+1]
        if matches:
            o=matches[0]; used.add(o['interval_id']); text=s.get('raw_text') or s.get('text') or o.get('raw_text'); relation='semantic_agreement' if norm(text)==norm(o.get('raw_text')) else 'variant'; refs={'speech_segment_ids':[s.get('speech_segment_id') or s.get('segment_id')],'ocr_interval_ids':[o['interval_id']]}
        else: text=s.get('raw_text') or s.get('text') or ''; relation='speech_only'; refs={'speech_segment_ids':[s.get('speech_segment_id') or s.get('segment_id')],'ocr_interval_ids':[]}
        if text: out.append({'segment_id':f"commentary_{len(out):06d}",'seed_id':s.get('seed_id'),'video_id':s.get('video_id'),'start_sec':ss,'end_sec':se,'raw_text':text,'language':'zh','representation':'source_transcript','canonical':True,'fusion_relationship':relation,'source_record_ids':refs,'source_media_sha256':s.get('source_media_sha256')})
    for o in intervals:
        if o['interval_id'] not in used: out.append({'segment_id':f"commentary_{len(out):06d}",'seed_id':o.get('seed_id'),'video_id':o.get('video_id'),'start_sec':o['start_sec'],'end_sec':o['end_sec'],'raw_text':o['raw_text'],'language':'zh','representation':'source_transcript','canonical':True,'fusion_relationship':'ocr_only','source_record_ids':{'speech_segment_ids':[],'ocr_interval_ids':[o['interval_id']]}})
    return out
def split_claims(segments):
    out=[]
    for s in segments:
        parts=[x.strip() for x in re.split(r'[。！？!?；;]',s.get('raw_text','')) if x.strip() and re.search(r'[\u4e00-\u9fffA-Za-z0-9]',x)]
        for i,text in enumerate(parts or [s.get('raw_text','').strip()]):
            if not text: continue
            out.append({'claim_id':f"{s.get('segment_id')}_claim_{i:02d}",'seed_id':s.get('seed_id'),'video_id':s.get('video_id'),'source_segment_id':s.get('segment_id'),'raw_text':text,'language':'zh','source_media_sha256':s.get('source_media_sha256'),'canonical':True,'split_status':'sentence_split_unverified' if len(parts)>1 else 'unsplit'})
    return out
def process_one(root,sid,force_from=None):
    out=root/'data/evaluation/replay_seeds/corpus'; v=out/'videos'/sid; t=v/'transcript'; media_dir=root/'data/evaluation/replay_seeds/media'; manifest=read_json(v/'source_manifest.json',{}); media=media_dir/f"{manifest.get('video_id',sid)}.webm"; smp=v/'stage_manifest.json'; sm=load_stage(smp); sm['seed_id']=sid
    if force_from: invalidate(sm,force_from)
    for n in ('speech_segments.jsonl','ocr_observations.jsonl','ocr_intervals.jsonl','commentary_segments.jsonl'): ensure_empty(t/n)
    ensure_empty(v/'claims.jsonl'); ensure_empty(v/'fixture_candidates.jsonl')
    p=probe(media); media_fp=fp({'media_sha256':file_hash(media),'probe':p,'schema':SCHEMA})
    r=sm['stages']['media_probe']
    if not valid_hit(r,media_fp):
        set_stage(sm,'media_probe','complete' if p['status']=='complete' else ('blocked' if p['status']=='blocked_missing_media' else 'failed_permanent'),input_fingerprint=media_fp,configuration_hash=fp({'ffprobe':'json'}),started_at=now(),completed_at=now(),output_paths=[],output_hashes={},error=p.get('error'),blocked_by=[] if p['status']=='complete' else ['media'])
    if p['status']!='complete':
        for s in ['audio_extraction','speech_to_text','caption_sampling','caption_ocr','ocr_interval_reconstruction','commentary_fusion','claim_extraction','fixture_generation','detectors']:
            set_stage(sm,s,'blocked',blocked_by=['media_probe'],error='missing_or_invalid_webm')
        save_stage(smp,sm); return {'seed_id':sid,'status':'blocked','media_probe':p}
    # Existing raw/canonical files remain authoritative. These stages are cacheable even when no optional backend exists.
    audio_tmp=v/'evidence'/'.tmp_audio'/f'{sid}.wav'; audio_fp=fp({'media_sha256':file_hash(media),'audio_config':{'sample_rate':16000,'channels':1},'implementation':IMPLEMENTATION})
    ar=sm['stages']['audio_extraction']
    if not valid_hit(ar,audio_fp):
        audio_tmp.parent.mkdir(parents=True,exist_ok=True); rr=run(['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(media),'-vn','-ac','1','-ar','16000','-c:a','pcm_s16le',str(audio_tmp)])
        if rr.returncode==0 and audio_tmp.exists(): set_stage(sm,'audio_extraction','complete',input_fingerprint=audio_fp,configuration_hash=fp({'sample_rate':16000,'channels':1}),started_at=now(),completed_at=now(),output_paths=[str(audio_tmp)],output_hashes=output_hashes([audio_tmp]),error=None,blocked_by=[])
        else: set_stage(sm,'audio_extraction','failed_retryable',input_fingerprint=audio_fp,started_at=now(),completed_at=now(),output_paths=[],output_hashes={},error=rr.stderr[-1000:],blocked_by=[])
    # No STT engine is assumed; preserve existing output and mark honest blockage rather than fabricate transcript.
    st=sm['stages']['speech_to_text']; st_fp=fp({'audio_hashes':st.get('output_hashes',{}),'backend':'deterministic-stt-unconfigured','schema':SCHEMA})
    if not valid_hit(st,st_fp) and not rows(t/'speech_segments.jsonl'):
        set_stage(sm,'speech_to_text','blocked',input_fingerprint=st_fp,configuration_hash=fp({'backend':'deterministic-stt-unconfigured'}),started_at=now(),completed_at=now(),output_paths=[str(t/'speech_segments.jsonl')],output_hashes=output_hashes([t/'speech_segments.jsonl']),error='no deterministic STT backend configured',blocked_by=['stt_backend'])
    # Caption sampling is deterministic ffmpeg extraction; OCR itself is not fabricated without a local OCR backend.
    sample_dir=v/'evidence'/'selected_frames'; sample_fp=fp({'media_sha256':file_hash(media),'sampling':{'interval_sec':1},'schema':SCHEMA}); cr=sm['stages']['caption_sampling']
    if not valid_hit(cr,sample_fp):
        sample_dir.mkdir(parents=True,exist_ok=True); rr=run(['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(media),'-vf','fps=1','-frames:v','1',str(sample_dir/'sample-%04d.jpg')])
        paths=list(sample_dir.glob('sample-*.jpg'))
        set_stage(sm,'caption_sampling','complete' if rr.returncode==0 else 'failed_retryable',input_fingerprint=sample_fp,configuration_hash=fp({'interval_sec':1}),started_at=now(),completed_at=now(),output_paths=[str(x) for x in paths],output_hashes=output_hashes(paths),error=None if rr.returncode==0 else rr.stderr[-1000:],blocked_by=[])
    oc=sm['stages']['caption_ocr']; oc_fp=fp({'sampling_hashes':sm['stages']['caption_sampling'].get('output_hashes',{}),'backend':'deterministic-ocr-unconfigured','schema':SCHEMA})
    if not valid_hit(oc,oc_fp) and not rows(t/'ocr_observations.jsonl'):
        set_stage(sm,'caption_ocr','blocked',input_fingerprint=oc_fp,configuration_hash=fp({'backend':'deterministic-ocr-unconfigured'}),started_at=now(),completed_at=now(),output_paths=[str(t/'ocr_observations.jsonl')],output_hashes=output_hashes([t/'ocr_observations.jsonl']),error='no deterministic OCR backend configured',blocked_by=['ocr_backend'])
    # Canonical downstream stages consume only deterministic per-seed outputs. Existing files remain authoritative.
    ocr=rows(t/'ocr_observations.jsonl'); speech=rows(t/'speech_segments.jsonl'); intervals=rows(t/'ocr_intervals.jsonl'); commentary=rows(t/'commentary_segments.jsonl'); claims=rows(v/'claims.jsonl'); fixtures=rows(v/'fixture_candidates.jsonl')
    if ocr:
        xfp=fp({'ocr_hash':file_hash(t/'ocr_observations.jsonl'),'implementation':IMPLEMENTATION,'schema':SCHEMA})
        if not valid_hit(sm['stages']['ocr_interval_reconstruction'],xfp): intervals=reconstruct_intervals(ocr); atomic_jsonl(t/'ocr_intervals.jsonl',intervals); set_stage(sm,'ocr_interval_reconstruction','complete',input_fingerprint=xfp,configuration_hash=fp({'merge':'normalized_match_similarity_gap_region'}),started_at=now(),completed_at=now(),output_paths=[str(t/'ocr_intervals.jsonl')],output_hashes=output_hashes([t/'ocr_intervals.jsonl']),error=None,blocked_by=[])
    else: set_stage(sm,'ocr_interval_reconstruction','blocked',error='no canonical OCR observations',blocked_by=['caption_ocr'])
    if speech or intervals:
        xfp=fp({'speech_hash':file_hash(t/'speech_segments.jsonl'),'interval_hash':file_hash(t/'ocr_intervals.jsonl'),'implementation':IMPLEMENTATION,'schema':SCHEMA})
        if not valid_hit(sm['stages']['commentary_fusion'],xfp): commentary=fuse_records(speech,intervals); atomic_jsonl(t/'commentary_segments.jsonl',commentary); set_stage(sm,'commentary_fusion','complete',input_fingerprint=xfp,configuration_hash=fp({'relationships':['verbatim','semantic_agreement','partial','variant','conflict','ocr_only','speech_only']}),started_at=now(),completed_at=now(),output_paths=[str(t/'commentary_segments.jsonl')],output_hashes=output_hashes([t/'commentary_segments.jsonl']),error=None,blocked_by=[])
    else: set_stage(sm,'commentary_fusion','blocked',error='no deterministic OCR/STT inputs',blocked_by=['speech_to_text','ocr_interval_reconstruction'])
    commentary=rows(t/'commentary_segments.jsonl')
    if commentary:
        xfp=fp({'commentary_hash':file_hash(t/'commentary_segments.jsonl'),'implementation':IMPLEMENTATION,'schema':SCHEMA})
        if not valid_hit(sm['stages']['claim_extraction'],xfp): claims=split_claims(commentary); atomic_jsonl(v/'claims.jsonl',claims); set_stage(sm,'claim_extraction','complete',input_fingerprint=xfp,configuration_hash=fp({'split':'sentence_delimiters_only'}),started_at=now(),completed_at=now(),output_paths=[str(v/'claims.jsonl')],output_hashes=output_hashes([v/'claims.jsonl']),error=None,blocked_by=[])
    else: set_stage(sm,'claim_extraction','blocked',error='no canonical commentary segments',blocked_by=['commentary_fusion'])
    claims=rows(v/'claims.jsonl')
    if claims:
        fixture_rows=[{'fixture_id':f"{c['claim_id']}_fixture",'seed_id':c.get('seed_id'),'video_id':c.get('video_id'),'source_media_sha256':c.get('source_media_sha256'),'source_segment_id':c.get('source_segment_id'),'source_claim_id':c.get('claim_id'),'capability':c.get('capability','unknown'),'time_range':None,'time_semantics':'unknown_gameplay_time','verification_status':'unverified','label_tier':'silver'} for c in claims]
        xfp=fp({'claims_hash':file_hash(v/'claims.jsonl'),'implementation':IMPLEMENTATION,'schema':SCHEMA})
        if not valid_hit(sm['stages']['fixture_generation'],xfp): atomic_jsonl(v/'fixture_candidates.jsonl',fixture_rows); set_stage(sm,'fixture_generation','complete',input_fingerprint=xfp,configuration_hash=fp({'time_semantics':'unknown_gameplay_time'}),started_at=now(),completed_at=now(),output_paths=[str(v/'fixture_candidates.jsonl')],output_hashes=output_hashes([v/'fixture_candidates.jsonl']),error=None,blocked_by=[])
    else: set_stage(sm,'fixture_generation','blocked',error='no canonical claims',blocked_by=['claim_extraction'])
    dr=sm['stages']['detectors']; d_fp=fp({'media_sha256':file_hash(media),'detectors':'existing-detectors-only','schema':SCHEMA})
    if dr.get('status') not in {'complete','blocked'}: set_stage(sm,'detectors','blocked',input_fingerprint=d_fp,configuration_hash=fp({'detectors':'existing-detectors-only'}),started_at=now(),completed_at=now(),output_paths=[],output_hashes={},error='no existing corpus detector runner configured',blocked_by=['detector_backend'])
    set_stage(sm,'aggregate_participation','pending',input_fingerprint=None,output_paths=[],output_hashes={})
    cleanup_paths=[]
    owned_present=audio_tmp.exists()
    if owned_present and sm['stages']['speech_to_text']['status']=='complete': cleanup_paths.append(audio_tmp.parent)
    for owned in cleanup_paths:
        shutil.rmtree(owned,ignore_errors=True)
        for rec in sm.get('stages',{}).values():
            kept=[(p,h) for p,h in rec.get('output_hashes',{}).items() if not Path(p).is_relative_to(owned)]
            rec['output_paths']=[p for p,_ in kept]
            rec['output_hashes']={p:h for p,h in kept}
    remaining_owned=audio_tmp.exists()
    retention_status='complete' if not remaining_owned else 'pending'
    set_stage(sm,'retention_cleanup',retention_status,input_fingerprint=fp({'owned_paths':[str(audio_tmp)]}),configuration_hash=fp({'owned_paths_only':True}),started_at=now(),completed_at=now() if retention_status=='complete' else None,output_paths=[],output_hashes={},error=None if retention_status=='complete' else 'awaiting successful STT completion before deleting owned temporary audio',blocked_by=[] if retention_status=='complete' else ['speech_to_text'])
    manifest['artifact_path']=str(media); manifest['artifact_sha256']=file_hash(media); manifest['media_probe']=p
    manifest.setdefault('stage_status',{})['acquisition']='complete'; manifest['stage_status']['media_probe']='complete'
    status_map={'speech_to_text':'speech_to_text','caption_ocr':'caption_ocr','ocr_interval_reconstruction':'ocr_stt_alignment','detectors':'detectors'}
    for stage,key in status_map.items():
        st=sm['stages'][stage]['status']; manifest['stage_status'][key]='complete' if st=='complete' else ('blocked_missing_media' if st=='blocked' and p['status']!='complete' else 'pending')
    manifest['terminal_status']='complete' if sm['stages']['speech_to_text']['status']=='complete' else 'media_ready_transcript_pending'
    (v/'source_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    save_stage(smp,sm)
    return {'seed_id':sid,'status':'processed','media_probe':p,'stage_manifest':str(smp)}
def rebuild(root):
    out=root/'data/evaluation/replay_seeds/corpus'; manifests=[]; seg=[]; claims=[]; obs=[]; fixtures=[]
    for v in sorted((out/'videos').glob('*')):
        if not v.is_dir(): continue
        m=read_json(v/'source_manifest.json',{}); sm=read_json(v/'stage_manifest.json',{}); 
        if not m: continue
        manifests.append(m)
        seg += rows(v/'transcript/commentary_segments.jsonl'); claims += rows(v/'claims.jsonl'); obs += rows(v/'transcript/ocr_observations.jsonl'); fixtures += rows(v/'fixture_candidates.jsonl')
    key=lambda x:(x.get('seed_id',''),float(x.get('start_sec') or 0),x.get('record_type',''),x.get('segment_id') or x.get('claim_id') or x.get('observation_id') or x.get('fixture_id') or '')
    for p,data in [('canonical_commentary_segments.jsonl',seg),('canonical_claims.jsonl',claims),('evidence_timeline.jsonl',obs),('detector_fixtures.jsonl',fixtures),('manifests.jsonl',manifests)]: atomic_jsonl(out/'aggregates'/p,sorted(data,key=key))
    atomic_jsonl(out/'aggregates/missing_capability_queue.jsonl',[])
    report=read_json(out/'aggregates/corpus_report.json',{}); report.update({'schema_version':'handoff-corpus-v4','canonical':{'chinese_ocr_observations':len(obs),'chinese_commentary_segments':len(seg),'claims':len(claims),'reviewer_observations':len(obs),'event_fixtures':len(fixtures)}}); atomic_json(out/'aggregates/corpus_report.json',report); return {'manifests':len(manifests),'canonical_observations':len(obs),'canonical_segments':len(seg),'claims':len(claims),'fixtures':len(fixtures)}
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]); ap.add_argument('--seed-id'); ap.add_argument('--all',action='store_true'); ap.add_argument('--pilot',type=int); ap.add_argument('--stale-only',action='store_true'); ap.add_argument('--from-stage',choices=STAGES); ap.add_argument('--rebuild-aggregates',action='store_true'); args=ap.parse_args(); root=args.root.resolve()
    if args.rebuild_aggregates: print(json.dumps({'aggregate_rebuild':rebuild(root)},ensure_ascii=False,indent=2)); return
    seeds=read_json(root/'data/source_seeds/youtube/seed_manifest.json',{'records':[]}); ids=[r['seed_id'] for r in seeds.get('records',[]) if r.get('seed_eligibility')=='eligible-seed']
    if args.seed_id: ids=[args.seed_id]
    elif args.pilot: ids=ids[:args.pilot]
    elif not args.all: ap.error('use --seed-id, --all, --pilot, or --rebuild-aggregates')
    results=[]
    for sid in ids:
        if args.stale_only and not args.from_stage:
            sm=read_json(root/'data/evaluation/replay_seeds/corpus/videos'/sid/'stage_manifest.json',{})
            statuses=[x.get('status') for x in sm.get('stages',{}).values()]
            if statuses and not any(x in {'pending','running','stale','failed_retryable'} for x in statuses):
                results.append({'seed_id':sid,'status':'cache_hit'}); continue
        try: results.append(process_one(root,sid,args.from_stage))
        except Exception as e: results.append({'seed_id':sid,'status':'failed_retryable','error':str(e)})
    print(json.dumps({'processed':len(results),'results':results,'aggregate_rebuild':rebuild(root)},ensure_ascii=False,indent=2))
if __name__=='__main__': main()
