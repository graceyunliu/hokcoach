from __future__ import annotations
import json, subprocess, tempfile, time
from pathlib import Path
from core.cooldown_recognizer import CooldownTemplateRecognizer, evaluate, load_cooldown_manifest
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'data/evaluation/replay_seeds/calibration/hokclass_001/cooldowns'
VIDEO=ROOT/'Seed Videos/hokclass_001_QK9QwHo1RhY.webm'
manifest=load_cooldown_manifest(BASE/'cooldown_calibration_manifest.json')
rec=CooldownTemplateRecognizer(
    {slot:{state:BASE/path for state,path in states.items()} for slot,states in manifest['templates'].items()},
    **manifest['threshold_policy'],
    layout_profile=manifest['layout_profile'],
    expected_source_dimensions=tuple(manifest['expected_source_dimensions']),
    source_compatibility=manifest['source_compatibility'],
    rois=manifest['roi_profiles'],
)

def measure_crop_extraction() -> float | None:
    if not VIDEO.is_file(): return None
    started=time.perf_counter()
    with tempfile.TemporaryDirectory(prefix='hokcoach_cooldown_eval_') as tmp:
        for case in manifest['evaluation_cases']:
            roi=manifest['roi_profiles'][case['slot']]
            output=Path(tmp)/f"{case['slot']}_{case['timestamp_sec']}.png"
            subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-ss',str(case['timestamp_sec']),'-i',str(VIDEO),'-frames:v','1','-vf',f"crop={roi['w']}:{roi['h']}:{roi['x']}:{roi['y']}",str(output)],check=True)
    return time.perf_counter()-started

cases=[]
for raw in manifest['evaluation_cases']:
    case=dict(raw)
    case['image']=str(BASE/case.pop('artifact'))
    case['evidence_ref']=(
        f"source_sha256={manifest['source_media_sha256']}|timestamp_sec={case['timestamp_sec']}"
        f"|region=hud|roi_slot={case['slot']}|layout={manifest['layout_profile']}"
        f"|detector_version={rec.version}"
    )
    cases.append(case)
crop_seconds=measure_crop_extraction()
started=time.perf_counter(); report=evaluate(rec,cases); recognition_seconds=time.perf_counter()-started
report.update({'schema_version':'pilot-cooldown-evaluation-v1','seed_id':manifest['seed_id'],'video_id':manifest['video_id'],'source_media_sha256':manifest['source_media_sha256'],'tuning_policy':'frame-level disjoint tuning/evaluation timestamps from shared manifest','tuning_timestamps':manifest['tuning_timestamps_sec'],'evaluation_timestamps':manifest['evaluation_timestamps_sec'],'roi_profiles':manifest['roi_profiles'],'threshold_policy':manifest['threshold_policy'],'runtime':{'recognition_seconds':recognition_seconds,'crop_extraction_seconds':crop_seconds,'source_minutes':390.728/60,'processing_seconds_per_source_minute':((recognition_seconds+(crop_seconds or 0))/(390.728/60)) if crop_seconds is not None else None}})
for row in report['predictions']:
    row['image']=str(Path(row['image']).relative_to(ROOT))
(BASE/'cooldown_evaluation_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:report[k] for k in ['total','classified','classified_correct','classified_accuracy','abstentions','abstention_correct','coverage','expected_behavior_agreement','detector_version','runtime']},ensure_ascii=False))
