from __future__ import annotations
import json, hashlib, time
from pathlib import Path
from PIL import Image, ImageDraw
from core.cooldown_recognizer import CooldownTemplateRecognizer, load_cooldown_manifest
ROOT=Path(__file__).resolve().parents[1]
media=ROOT/'data/evaluation/replay_seeds/media/Tq5eD3ECpyw.webm'
source_hash=hashlib.sha256(media.read_bytes()).hexdigest()
source_manifest=json.loads((ROOT/'data/evaluation/replay_seeds/corpus/videos/hokclass_007/source_manifest.json').read_text(encoding='utf-8'))
old_dir=ROOT/'data/evaluation/replay_seeds/calibration/hokclass_001/cooldowns'
old=load_cooldown_manifest(old_dir/'cooldown_calibration_manifest.json')
new_dir=ROOT/'data/evaluation/replay_seeds/calibration/hokclass_007/cooldowns'; new_dir.mkdir(parents=True,exist_ok=True)
# Old Video 1 profile is intentionally used only for the incompatibility/abstention check.
rec=CooldownTemplateRecognizer({slot:{state:old_dir/path for state,path in states.items()} for slot,states in old['templates'].items()}, **old['threshold_policy'], layout_profile=old['layout_profile'], expected_source_dimensions=tuple(old['expected_source_dimensions']), source_compatibility=old['source_compatibility'], rois=old['roi_profiles'])
report={'schema_version':'video2-layout-calibration-v1','seed_id':'hokclass_007','video_id':'Tq5eD3ECpyw','source_media_sha256':source_hash,'source_dimensions':[1920,872],'source_duration_sec':source_manifest.get('media_probe',{}).get('duration_sec'),'video1_profile':{'layout_profile':old['layout_profile'],'expected_source_dimensions':old['expected_source_dimensions'],'compatible':rec.is_source_compatible(source_hash,(1920,872)),'result':'unsupported layout / abstain'},'layout_profile':'hokcoach-hud-1920x872-v1','status':'scaffolded','roi_profiles':{'summoner_flash':{'x':1200,'y':711,'w':128,'h':135,'status':'uncalibrated_scaled_candidate'},'ultimate':{'x':1560,'y':674,'w':180,'h':180,'status':'uncalibrated_scaled_candidate'}},'templates':{},'threshold_policy':'unchanged_until_visual_labels_exist','tuning_timestamps_sec':[],'evaluation_timestamps_sec':[],'capabilities':{'recall_lifecycle':'not represented','cooldowns':'scaffolded','objective_hud':'not represented','economy_items':'not represented','towers':'not represented','waves':'not represented','hero_positions_teamfights':'not represented'},'metrics':{'classified':0,'coverage':0.0,'abstentions':0,'timestamp_error_sec':None},'notes':['Claims and fixture windows are navigation hints, not visual labels.','No recognizer is enabled from this single uncalibrated layout.','Tuning/evaluation timestamps remain empty until direct visual labels are assigned.']}
(new_dir/'layout_profile.json').write_text(json.dumps({'layout_profile':report['layout_profile'],'source_dimensions':report['source_dimensions'],'source_media_sha256':source_hash,'roi_profiles':report['roi_profiles'],'status':'scaffolded'},ensure_ascii=False,indent=2)+'\n')
(new_dir/'video2_calibration_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(report,ensure_ascii=False,indent=2))
