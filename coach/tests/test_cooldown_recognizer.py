import json
import unittest
from pathlib import Path
from core.cooldown_recognizer import CooldownTemplateRecognizer, evaluate

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'data/evaluation/replay_seeds/calibration/hokclass_001/cooldowns'
MANIFEST = json.loads((BASE/'cooldown_calibration_manifest.json').read_text())

class CooldownRecognizerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.recognizer = CooldownTemplateRecognizer({slot:{state:BASE/path for state,path in states.items()} for slot,states in MANIFEST['templates'].items()}, **MANIFEST['threshold_policy'])

    def test_complete_disjoint_evaluation_matches_reported_behavior(self):
        cases = []
        for raw in MANIFEST['evaluation_cases']:
            case = dict(raw)
            case['image'] = str(BASE/case.pop('artifact'))
            cases.append(case)
        report = evaluate(self.recognizer, cases)
        self.assertEqual((report['classified_correct'], report['classified']), (5, 5))
        self.assertEqual(report['abstention_correct'], 1)
        self.assertEqual(report['coverage'], 5/6)
        self.assertEqual(report['expected_behavior_agreement'], 6)
        self.assertEqual(report['abstentions'], 1)
        self.assertEqual(report['detector_version'].split(':',1)[0], 'cooldown-template-v1')
        self.assertEqual(report['predictions'][2]['prediction'], 'abstain')
        self.assertEqual(report['predictions'][2]['status'], 'unknown')
        tuning = set(MANIFEST['tuning_timestamps_sec'])
        evaluation = set(MANIFEST['evaluation_timestamps_sec'])
        self.assertTrue(tuning.isdisjoint(evaluation))

    def test_missing_slot_is_unreadable(self):
        prediction, observation = self.recognizer.recognize(BASE/'evaluation/flash_174_on_cooldown.png', slot='missing', start_sec=174, end_sec=174)
        self.assertEqual(prediction.status, 'unreadable')
        self.assertEqual(observation.status, 'unreadable')
        self.assertEqual(observation.type, 'cooldown_ui')

if __name__ == '__main__': unittest.main()
