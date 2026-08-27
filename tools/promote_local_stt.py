from __future__ import annotations
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from process_seed_corpus import atomic_jsonl, file_hash, fp, load_stage, now, output_hashes, set_stage

root=Path(__file__).resolve().parents[1]
sid=sys.argv[1] if len(sys.argv)>1 else 'hokclass_001'
v=root/'data/evaluation/replay_seeds/corpus/videos'/sid
t=v/'transcript'; candidates=sorted((v/'evidence/.tmp_audio').glob(f'{sid}_transcription_*.json'))
if not candidates: raise SystemExit(f'no transcription JSON for {sid}')
src=candidates[-1]; data=json.loads(src.read_text(encoding='utf-8'))
stable_src=v/'evidence/stt'/f'{sid}_transcription.json'; stable_src.parent.mkdir(parents=True,exist_ok=True); stable_src.write_text(src.read_text(encoding='utf-8'),encoding='utf-8')
media_sha256=file_hash(root/'data/evaluation/replay_seeds/media'/f"{json.loads((v/'source_manifest.json').read_text()).get('video_id')}.webm")
rows=[]
for i,s in enumerate(data.get('segments',[])):
    text=str(s.get('text') or '').strip()
    if not text: continue
    rows.append({'speech_segment_id':f'{sid}_stt_{i:06d}','seed_id':sid,'video_id':json.loads((v/'source_manifest.json').read_text()).get('video_id'),'start_sec':float(s['start']),'end_sec':float(s['end']),'raw_text':text,'language':data.get('language','zho'),'representation':'source_transcript','canonical':True,'source_artifact':str(stable_src),'backend':'manus-speech-to-text','timestamp_basis':'audio_playback_time','confidence':None,'source_media_sha256':media_sha256})
out=t/'speech_segments.jsonl'; atomic_jsonl(out,rows)
smp=v/'stage_manifest.json'; sm=load_stage(smp)
set_stage(sm,'speech_to_text','complete',input_fingerprint=fp({'audio_hash':file_hash(v/'evidence/.tmp_audio'/f'{sid}.wav'),'transcription_hash':file_hash(stable_src)}),configuration_hash=fp({'backend':'manus-speech-to-text','language':'zho'}),model_version='manus-speech-to-text',started_at=now(),completed_at=now(),output_paths=[str(out)],output_hashes=output_hashes([out]),error=None,blocked_by=[])
set_stage(sm,'aggregate_participation','pending',input_fingerprint=None,output_paths=[],output_hashes={})
sm['stages']['retention_cleanup']['status']='pending'
sm['stages']['retention_cleanup']['error']='awaiting downstream canonical processing'
sm['stages']['retention_cleanup']['blocked_by']=['speech_to_text']
smp.write_text(json.dumps(sm,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'seed_id':sid,'source':str(src),'output':str(out),'segments':len(rows)},ensure_ascii=False))
