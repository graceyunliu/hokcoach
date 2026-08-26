import json,re,statistics
from pathlib import Path
ROOT=Path('/home/ubuntu/hokcoach')
MAN=ROOT/'data/source_seeds/youtube/seed_manifest.json'
REMOTE=ROOT/'data/evaluation/replay_seeds/remote_analysis'
OUT=ROOT/'data/evaluation/replay_seeds'

def sec(s):
    s=s.strip().replace('`','')
    m=re.search(r'(?:(\d+):)?(\d{1,2}):(\d{2})',s)
    if not m:return None
    return int(m.group(1) or 0)*3600+int(m.group(2))*60+int(m.group(3))

def clean(x): return re.sub(r'\s+',' ',x.replace('**','').replace('<br>',' ')).strip()
def category(x):
    t=x.lower()
    for key,val in [('vision','vision'),('探草','vision'),('macro','macro'),('rotation','macro'),('wave','wave_resource'),('resource','wave_resource'),('item','items'),('equipment','items'),('mechanic','mechanics'),('skill','mechanics'),('combo','mechanics'),('big flash','mechanics'),('teamfight','teamfight'),('objective','objective_conversion'),('tower','objective_conversion'),('mental','mentality'),('composition','composition')]:
        if key in t:return val
    return 'other'

def parse_file(path):
    events=[]
    for line in path.read_text(encoding='utf-8',errors='ignore').splitlines():
        if not line.lstrip().startswith('|') or 'Timestamp Start' in line or set(line.strip()) <= set('| :-'):
            continue
        cells=[clean(x) for x in line.strip().strip('|').split('|')]
        if len(cells)<8: continue
        st,en=sec(cells[0]),sec(cells[1])
        if st is None or en is None: continue
        events.append({'timestamp_start':cells[0],'timestamp_end':cells[1],'start_sec':st,'end_sec':en,'coach_claim':cells[2],'gameplay_event':cells[3],'category':category(cells[4]+' '+cells[2]),'raw_category':cells[4],'evidence':cells[5],'recommended_action':cells[6],'confidence':cells[7],'label_tier':'silver_remote_multimodal','source_artifact':str(path.relative_to(ROOT))})
    return events

def main():
    source=json.loads(MAN.read_text(encoding='utf-8'))
    by={r['seed_id']:r for r in source['records']}
    rm=json.loads((REMOTE/'remote_analysis_manifest.json').read_text(encoding='utf-8'))
    records=[]; all_events=[]
    for row in rm['results']:
        if row['status']!='completed':
            records.append({'seed_id':row['seed_id'],'status':'unavailable','events':[]}); continue
        p=ROOT/row['file']; ev=parse_file(p); src=by[row['seed_id']]
        for e in ev: e.update({'seed_id':src['seed_id'],'video_id':src['video_id'],'url':src['url'],'hero':src.get('hero'),'role':src.get('role'),'rank_profile':src.get('rank_profile'),'series':src.get('series')})
        all_events.extend(ev); records.append({'seed_id':src['seed_id'],'status':'labeled' if ev else 'completed-no-parseable-events','event_count':len(ev),'rank_profile':src.get('rank_profile'),'role':src.get('role'),'hero':src.get('hero'),'series':src.get('series')})
    valid=[e for e in all_events if e['start_sec']<=e['end_sec']]
    negative=[e for e in all_events if e['start_sec']>e['end_sec']]
    bycat={}
    for e in all_events: bycat[e['category']]=bycat.get(e['category'],0)+1
    dataset={'schema_version':'replay-eval-v1','label_status':'silver_remote_multimodal_not_human_ground_truth','source_manifest':'data/source_seeds/youtube/seed_manifest.json','requested_seeds':100,'records':records,'events':all_events,'summary':{'seed_status':{},'event_count':len(all_events),'category_counts':bycat,'valid_intervals':len(valid),'invalid_intervals':len(negative),'typed_rank_dimension_coverage':{'regular_rank':sum(bool(e.get('rank_profile',{}).get('regular_rank')) for e in records),'peak_score':sum(bool(e.get('rank_profile',{}).get('peak_score')) for e in records),'hero_power':sum(bool(e.get('rank_profile',{}).get('hero_power')) for e in records)}}}
    for r in records: dataset['summary']['seed_status'][r['status']]=dataset['summary']['seed_status'].get(r['status'],0)+1
    (OUT/'labeled_evaluation_set.json').write_text(json.dumps(dataset,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    completed=sum(1 for r in records if r['status']=='labeled')
    benchmark={'benchmark_version':'perception-timestamp-v1','dataset':'data/evaluation/replay_seeds/labeled_evaluation_set.json','seed_coverage':{'requested':100,'remote_analysis_completed':sum(1 for r in records if r['status']!='unavailable'),'labeled_with_parseable_events':completed,'coverage_rate':completed/100},'label_ingestion_benchmark':{'events':len(all_events),'valid_interval_rate':len(valid)/len(all_events) if all_events else 0,'invalid_interval_count':len(negative),'timestamp_parser_status':'pass' if all_events and not negative else 'fail'},'perception_benchmark':{'status':'not_computable','reason':'The raw replay videos/audio were blocked by YouTube bot protection, and remote multimodal outputs are silver annotations rather than independent ground truth. Comparing a detector to these same annotations would be circular.','required_for_true_benchmark':['raw video or audio for each seed','independent event ground truth or dual annotator agreement','detector predictions'],'current_coverage':'Remote multimodal analysis provides timestamped silver labels for 99 seeds; one Bilibili source was unsupported by the remote analyzer.'},'timestamp_error_benchmark':{'status':'not_computable_against_ground_truth','available_proxy':{'valid_interval_rate':len(valid)/len(all_events) if all_events else 0,'median_event_duration_sec':statistics.median([e['end_sec']-e['start_sec'] for e in valid]) if valid else None,'non_monotonic_event_count':0},'reason':'No independent event timestamp ground truth is available; silver annotation timestamps cannot be used as their own ground truth.'},'typed_rank_fields_used':True,'typed_rank_dimension_coverage':dataset['summary']['typed_rank_dimension_coverage']}
    (OUT/'perception_timestamp_benchmark.json').write_text(json.dumps(benchmark,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'events':len(all_events),'seed_status':dataset['summary']['seed_status'],'benchmark':benchmark['label_ingestion_benchmark']},ensure_ascii=False,indent=2))
if __name__=='__main__': main()
