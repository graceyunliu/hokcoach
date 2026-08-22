import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from evaluate_audio_timeline import score_events


class TestAudioTimelineEvaluation(unittest.TestCase):
    def test_metrics_and_relationship_accuracy(self):
        predicted = [
            {"ts": 92.1, "event": "kill_streak_3", "perspective": "enemy",
             "category": "combat", "usage": "evidence"},
            {"ts": 120.0, "event": "hero_killed", "perspective": "allied",
             "category": "combat", "usage": "evidence"},
        ]
        expected = [{
            "ts": 92.0, "event": "kill_streak_3", "perspective": "enemy",
            "death_ts": 100.0, "relationship": "pre_death_context",
        }]
        result = score_events(predicted, expected)
        self.assertEqual(result["per_class"]["kill_streak_3"]["tp"], 1)
        self.assertEqual(result["per_class"]["hero_killed"]["fp"], 1)
        self.assertEqual(result["relationship_accuracy"], 1.0)


if __name__ == "__main__":
    unittest.main()
