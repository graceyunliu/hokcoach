import json
from collections import Counter, defaultdict
from pathlib import Path

p = Path('/home/ubuntu/hokcoach/data/evaluation/replay_seeds/windowed_caption_analysis/merged_burned_captions.json')
d = json.loads(p.read_text(encoding='utf-8'))
rows = d['records']
by_start = defaultdict(list)
for r in rows:
    by_start[r['timestamp_sec']].append(r)
conf = Counter(r.get('confidence','') for r in rows)
conflicts = [v for v in by_start.values() if len({r['text'] for r in v}) > 1]
covered = sum(1 for r in rows if r['text'] and r['text'] != '[unreadable]')
print(json.dumps({
    'records': len(rows),
    'covered_start_sec': d['coverage_start_sec'],
    'covered_end_sec': d['coverage_end_sec'],
    'expected_video_end_sec': 481,
    'reaches_video_end': d['coverage_end_sec'] >= 481,
    'readable_text_records': covered,
    'unreadable_records': len(rows)-covered,
    'confidence_distribution': dict(conf),
    'timestamps_with_multiple_texts': len(conflicts),
    'max_records_at_same_start': max((len(v) for v in by_start.values()), default=0),
    'source_file_counts': dict(Counter(r['source_file'] for r in rows)),
}, ensure_ascii=False, indent=2))
if conflicts:
    print('CONFLICT_EXAMPLES')
    for group in conflicts[:10]:
        print(json.dumps(group, ensure_ascii=False))
