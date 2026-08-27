from __future__ import annotations
import json, shutil, subprocess, sys, tempfile
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
class StableRebuildTests(unittest.TestCase):
    def test_existing_canonical_files_and_stage_status_survive_rebuild(self):
        with tempfile.TemporaryDirectory() as td:
            t=Path(td); (t/'data/source_seeds/youtube').mkdir(parents=True); (t/'data/evaluation/replay_seeds').mkdir(parents=True)
            shutil.copy(ROOT/'data/source_seeds/youtube/seed_manifest.json', t/'data/source_seeds/youtube/seed_manifest.json')
            shutil.copy(ROOT/'data/evaluation/replay_seeds/labeled_evaluation_set.json', t/'data/evaluation/replay_seeds/labeled_evaluation_set.json')
            (t/'data/evaluation/replay_seeds/windowed_caption_analysis').mkdir()
            shutil.copy(ROOT/'data/evaluation/replay_seeds/windowed_caption_analysis/merged_burned_captions.json', t/'data/evaluation/replay_seeds/windowed_caption_analysis/merged_burned_captions.json')
            # Make the imported helper available to the subprocess.
            shutil.copy(ROOT/'tools/build_handoff_corpus.py', t/'build_handoff_corpus.py')
            seed_id=json.loads((t/'data/source_seeds/youtube/seed_manifest.json').read_text())['records'][0]['seed_id']
            v=t/'data/evaluation/replay_seeds/corpus/videos'/seed_id; (v/'transcript').mkdir(parents=True)
            marker={'claim_id':'preserved_claim','source_segment_id':'preserved_segment','canonical':True,'language':'zh'}
            (v/'claims.jsonl').write_text(json.dumps(marker,ensure_ascii=False)+'\n')
            stage={'caption_ocr':'complete','speech_to_text':'complete'}
            (v/'source_manifest.json').write_text(json.dumps({'seed_id':seed_id,'stage_status':stage,'terminal_status':'complete'},ensure_ascii=False))
            subprocess.run([sys.executable,str(ROOT/'tools/build_stable_corpus.py'),'--root',str(t)],check=True,env={**__import__('os').environ,'PYTHONPATH':str(t/'data/evaluation/replay_seeds')+':'+str(t) + ':' + str(ROOT/'tools')})
            self.assertEqual((v/'claims.jsonl').read_text(),json.dumps(marker,ensure_ascii=False)+'\n')
            manifest=json.loads((v/'source_manifest.json').read_text()); self.assertEqual(manifest['stage_status']['caption_ocr'],'complete'); self.assertEqual(manifest['stage_status']['speech_to_text'],'complete')
            agg=(t/'data/evaluation/replay_seeds/corpus/aggregates/canonical_claims.jsonl').read_text(); self.assertIn('preserved_claim',agg)
if __name__=='__main__': unittest.main()
