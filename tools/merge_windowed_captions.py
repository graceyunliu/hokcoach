import json, re
from pathlib import Path

ROOT = Path('/home/ubuntu/hokcoach')
SRC = ROOT / 'data/evaluation/replay_seeds/windowed_caption_analysis'
OUT = SRC / 'merged_burned_captions.json'
JSONL = SRC / 'merged_burned_captions.jsonl'

TIME_RE = re.compile(r'^(\d{1,2}:\d{2})(?:\s*[–-]\s*(\d{1,2}:\d{2}))?$')
def sec(s):
    m, ss = s.split(':'); return int(m)*60 + int(ss)
def clean(s): return re.sub(r'\s+', ' ', s.replace('\\|','|')).strip()
def parse_line(line, source):
    if not line.startswith('|') or line.count('|') < 4: return None
    cells = [clean(x) for x in line.strip().strip('|').split('|')]
    if not cells or cells[0].lower().startswith(':') or not TIME_RE.match(cells[0]): return None
    tm = TIME_RE.match(cells[0]); start = sec(tm.group(1)); end = sec(tm.group(2)) if tm.group(2) else None
    # Window outputs vary: timestamp|text|confidence|state or timestamp|text|confidence|start/end|state.
    text = cells[1] if len(cells) > 1 else ''
    confidence = cells[2] if len(cells) > 2 else ''
    embedded = cells[3] if len(cells) > 3 else ''
    state = cells[4] if len(cells) > 4 else (cells[3] if len(cells) == 4 else '')
    if end is None and re.match(r'^\d{1,2}:\d{2}\s*/\s*\d{1,2}:\d{2}$', embedded):
        a,b = [x.strip() for x in embedded.split('/')]; start, end = sec(a), sec(b)
        state = cells[4] if len(cells) > 4 else ''
    return {'timestamp_sec': start, 'end_sec': end, 'timestamp': cells[0], 'text': text, 'confidence': confidence, 'gameplay_state': state, 'source_file': source}

rows=[]
for f in sorted(SRC.glob('*_raw.txt')):
    for line in f.read_text(encoding='utf-8', errors='replace').splitlines():
        r=parse_line(line, f.name)
        if r and r['text'] and r['text'] not in ('Visible Caption Text (Exact)',): rows.append(r)
# Deduplicate exact repeats from overlapping/resubmitted interval boundaries; retain provenance.
rows.sort(key=lambda r:(r['timestamp_sec'], r['text'], r['source_file']))
merged=[]
for r in rows:
    if merged and r['timestamp_sec'] == merged[-1]['timestamp_sec'] and r['text'] == merged[-1]['text']:
        merged[-1]['source_file'] += ';' + r['source_file']
        if r.get('end_sec') and (not merged[-1].get('end_sec') or r['end_sec'] > merged[-1]['end_sec']): merged[-1]['end_sec']=r['end_sec']
    else: merged.append(r)
summary = {
    'source_video_id':'TcPNUG4b6GE', 'source_url':'https://www.youtube.com/watch?v=TcPNUG4b6GE',
    'window_files':[f.name for f in sorted(SRC.glob('*_raw.txt'))],
    'raw_rows':len(rows), 'deduplicated_rows':len(merged),
    'coverage_start_sec':min((x['timestamp_sec'] for x in merged), default=None),
    'coverage_end_sec':max((x.get('end_sec') or x['timestamp_sec'] for x in merged), default=None),
    'records':merged
}
OUT.write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
JSONL.write_text('\n'.join(json.dumps(x, ensure_ascii=False) for x in merged)+'\n', encoding='utf-8')
print(json.dumps({k:summary[k] for k in summary if k != 'records'}, ensure_ascii=False, indent=2))
