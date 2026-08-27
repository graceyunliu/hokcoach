from __future__ import annotations
import sys, tempfile
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from build_handoff_corpus import relevant_capabilities, sha256
from build_handoff_corpus_v4 import split_assertions

class CorpusCorrectionTests(unittest.TestCase):
    def test_skill_does_not_route_to_deaths(self):
        caps=relevant_capabilities('use skill 1')
        self.assertIn('cooldowns',caps)
        self.assertNotIn('deaths',caps)
        self.assertNotIn('items_economy',caps)

    def test_death_words_route_to_deaths(self):
        for text in ('kill the enemy','the player died','death near tower'):
            self.assertIn('deaths', relevant_capabilities(text))

    def test_whole_word_english_routes(self):
        self.assertIn('towers',relevant_capabilities('the tower fell'))
        self.assertIn('towers',relevant_capabilities('turret pressure'))
        self.assertIn('waves',relevant_capabilities('clear the wave and minion'))
        self.assertIn('cooldowns',relevant_capabilities('wait for the ultimate cooldown'))
        self.assertIn('teamfights',relevant_capabilities('win the team fight'))
        self.assertIn('minimap_positions',relevant_capabilities('use map awareness'))

    def test_webm_fingerprint_changes_with_content(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'sample.webm'; p.write_bytes(b'webm-content-a'); first=sha256(p)
            p.write_bytes(b'webm-content-b'); second=sha256(p)
            self.assertTrue(first and second and first != second)
            self.assertNotEqual(f'{first}:frames-v1',f'{second}:frames-v1')

    def test_sentence_split_preserves_source_and_splits_claim_candidates(self):
        pieces=split_assertions('You rotated too late. The enemy secured the dragon.')
        self.assertEqual(pieces,['You rotated too late','The enemy secured the dragon'])

if __name__=='__main__': unittest.main()
