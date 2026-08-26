# -*- coding: utf-8 -*-
import unittest

from core import feedback_engine, replay_engine
from utils import data_utils


class TestFeedbackEngine(unittest.TestCase):
    def test_catalog_covers_streamer_style_capabilities(self):
        names = {item["name"] for item in feedback_engine.capability_catalog()}
        self.assertTrue({"探草意识", "装备意识", "操作技术（连招/大闪）", "团战站位与目标"} <= names)

    def test_supported_bush_feedback_is_explicitly_evidence_gated(self):
        cards = feedback_engine.feedback_for_detail({
            "type": "探草死", "confidence": 0.4, "proxy": True,
            "evidence_sufficient": True, "timestamp": "6:32",
        })
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]["evidence_quality"], "proxy")
        self.assertLessEqual(cards[0]["confidence"], 0.4)
        self.assertIn("不证明", cards[0]["feedback"])

    def test_mechanics_feedback_does_not_claim_big_flash_without_cast_data(self):
        cards = feedback_engine.feedback_for_detail({
            "type": "机制死", "confidence": 0.3,
            "evidence_sufficient": False, "proxy": False,
        })
        self.assertEqual(cards[0]["name"], "操作技术（连招/大闪）")
        self.assertIn("不自动判定大闪失败", cards[0]["feedback"])

    def test_manual_replay_gets_structured_feedback(self):
        replay = data_utils.default_replay(hero_played="海月")
        replay["death_analysis"]["details"] = [{
            "type": "贪线死", "timestamp": "4:10", "confidence": 0.6,
            "evidence_sufficient": True, "proxy": False,
        }]
        replay_engine.classify_manual_replay(replay)
        self.assertEqual(replay["coaching_feedback"][0]["capability"], "macro_resource")
        self.assertEqual(replay["coaching_feedback"][0]["source_event"], "4:10")

    def test_duplicate_same_event_is_deduplicated(self):
        replay = {"death_analysis": {"details": [
            {"type": "掉点死", "timestamp": "8:00", "confidence": 0.8},
            {"type": "掉点死", "timestamp": "8:00", "confidence": 0.8},
        ]}}
        cards = feedback_engine.build_coaching_feedback(replay)
        self.assertEqual(len(cards), 1)


if __name__ == "__main__":
    unittest.main()
