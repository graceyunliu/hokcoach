import json, os, re, subprocess, sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path('/home/ubuntu/hokcoach')
MANIFEST = ROOT / 'data/source_seeds/youtube/seed_manifest.json'
OUT = ROOT / 'data/evaluation/replay_seeds'
OUT.mkdir(parents=True, exist_ok=True)
WORKERS = int(os.environ.get('HOKCOACH_EXTRACT_WORKERS', '4'))

def safe_name(row):
    return f"{row['seed_id']}_{row['video_id']}"

def run(cmd):
    p = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=180)
    return p.returncode, p.stdout[-4000:]

def extract(row):
    base = safe_name(row)
    stem = OUT / base
    result = {'seed_id': row['seed_id'], 'video_id': row['video_id'], 'url': row['url'], 'title': row.get('title',''), 'role': row.get('role'), 'hero': row.get('hero'), 'rank_stratum': row.get('rank_stratum'), 'series': row.get('series'), 'caption_status': 'not_run', 'audio_status': 'not_run', 'stt_status': 'not_run', 'files': [], 'errors': []}
    # Captions first: do not download media when a subtitle track is available.
    cap_cmd = ['yt-dlp', '--skip-download', '--write-auto-subs', '--write-subs', '--sub-langs', 'zh.*,en.*', '--sub-format', 'vtt', '--no-playlist', '--no-warnings', '-o', str(stem)+'.%(ext)s', row['url']]
    try:
        code, out = run(cap_cmd)
        caps = list(OUT.glob(base + '*.vtt'))
        if caps:
            result['caption_status'] = 'extracted'
            result['files'].extend(str(p.relative_to(ROOT)) for p in caps)
        elif code == 0:
            result['caption_status'] = 'none-exposed'
        else:
            result['caption_status'] = 'access-failed'
            result['errors'].append(out)
    except Exception as e:
        result['caption_status'] = 'error'
        result['errors'].append(repr(e))
    # Audio fallback. Keep compressed audio to limit disk use; STT is attempted only if audio exists.
    if result['caption_status'] != 'extracted':
        audio_cmd = ['yt-dlp', '--no-playlist', '--no-warnings', '-f', 'bestaudio/best', '-x', '--audio-format', 'mp3', '--audio-quality', '5', '-o', str(stem)+'.%(ext)s', row['url']]
        try:
            code, out = run(audio_cmd)
            audios = list(OUT.glob(base + '.mp3'))
            if audios:
                result['audio_status'] = 'extracted'
                result['files'].extend(str(p.relative_to(ROOT)) for p in audios)
            else:
                result['audio_status'] = 'access-failed'
                result['errors'].append(out)
        except Exception as e:
            result['audio_status'] = 'error'
            result['errors'].append(repr(e))
    # STT is delegated to the local utility and is only attempted on successfully downloaded audio.
    audios = list(OUT.glob(base + '.mp3'))
    if audios:
        txt = OUT / (base + '.txt')
        try:
            p = subprocess.run(['manus-speech-to-text', str(audios[0])], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=300)
            txt.write_text(p.stdout, encoding='utf-8')
            result['stt_status'] = 'extracted' if p.returncode == 0 else 'failed'
            result['files'].append(str(txt.relative_to(ROOT)))
            if p.returncode != 0: result['errors'].append(p.stdout[-4000:])
        except Exception as e:
            result['stt_status'] = 'error'
            result['errors'].append(repr(e))
    result['extraction_outcome'] = 'caption' if result['caption_status']=='extracted' else ('audio_stt' if result['stt_status']=='extracted' else 'unavailable')
    return result

def main():
    data = json.loads(MANIFEST.read_text(encoding='utf-8'))
    rows = [r for r in data['records'] if r.get('seed_eligibility') == 'eligible-seed']
    results = []
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(extract, row): row for row in rows}
        for i, f in enumerate(as_completed(futures), 1):
            r = f.result(); results.append(r)
            print(f"[{i}/{len(rows)}] {r['seed_id']} {r['extraction_outcome']}", flush=True)
    results.sort(key=lambda x: x['seed_id'])
    out = {'source_manifest': str(MANIFEST.relative_to(ROOT)), 'requested': len(rows), 'results': results, 'summary': {}}
    for key in ['caption_status','audio_status','stt_status','extraction_outcome']:
        out['summary'][key] = {}
        for r in results: out['summary'][key][r[key]] = out['summary'][key].get(r[key], 0) + 1
    (OUT / 'extraction_manifest.json').write_text(json.dumps(out, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(out['summary'], ensure_ascii=False, indent=2))

if __name__ == '__main__': main()
