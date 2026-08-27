from __future__ import annotations
import json, os, tempfile, unittest
from pathlib import Path
from unittest.mock import patch

from process_seed_corpus import DESCENDANTS, descendants, fp, invalidate, load_stage, rebuild, default_stage

class IncrementalCorpusTests(unittest.TestCase):
    def test_dependency_invalidation_is_downstream_only(self):
        self.assertIn('commentary_fusion', descendants('caption_ocr'))
        self.assertIn('claim_extraction', descendants('caption_ocr'))
        self.assertNotIn('speech_to_text', descendants('caption_ocr'))
        self.assertNotIn('detectors', descendants('caption_ocr'))
        self.assertIn('commentary_fusion', descendants('speech_to_text'))
        self.assertNotIn('caption_ocr', descendants('speech_to_text'))

    def test_fingerprint_is_reproducible_and_order_independent(self):
        self.assertEqual(fp({'b':2,'a':1}),fp({'a':1,'b':2}))
        self.assertNotEqual(fp({'a':1}),fp({'a':2}))

    def test_aggregate_rebuild_does_not_access_media(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); v=root/'data/evaluation/replay_seeds/corpus/videos/s1'; (v/'transcript').mkdir(parents=True)
            (v/'source_manifest.json').write_text(json.dumps({'seed_id':'s1','video_id':'v1'}))
            (v/'transcript/ocr_observations.jsonl').write_text(json.dumps({'observation_id':'o1','seed_id':'s1','start_sec':1})+'\n')
            for p in ['commentary_segments.jsonl','speech_segments.jsonl','ocr_intervals.jsonl']:(v/'transcript'/p).write_text('')
            (v/'claims.jsonl').write_text(''); (v/'fixture_candidates.jsonl').write_text('')
            with patch('process_seed_corpus.probe',side_effect=AssertionError('media was accessed')):
                result=rebuild(root)
            self.assertEqual(result['canonical_observations'],1)

    def test_stage_manifest_has_independent_stage_records(self):
        with tempfile.TemporaryDirectory() as td:
            m=load_stage(Path(td)/'stage_manifest.json')
            self.assertEqual(set(m['stages']),set(['media_probe','audio_extraction','speech_to_text','caption_sampling','caption_ocr','ocr_interval_reconstruction','commentary_fusion','claim_extraction','fixture_generation','detectors','aggregate_participation','retention_cleanup']))
            self.assertTrue(all(set(default_stage()).issubset(x) for x in m['stages'].values()))

if __name__=='__main__': unittest.main()
