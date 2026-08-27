from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.detector_stage import DetectorCache, DetectorContext, cache_key, run_detector
from core.orchestrator import Orchestrator
from core.evidence_timeline import EvidenceTimeline
from core.observations import Observation
from core.production_detectors import (
    CoarseWaveDetector,
    CooldownReadinessDetector,
    EconomyItemDetector,
    LifecycleRecallDetector,
    ObjectiveTowerFusionDetector,
    TeamfightDetector,
)


def obs(kind, start, end, value, subject="player", confidence=.9, status="observed"):
    return Observation.create(obs_type=kind, start_sec=start, end_sec=end, subject=subject, value=value, confidence=confidence if status == "observed" else 0.0, detector="fixture-v1", evidence_refs=[f"frame:{kind}:{start}"], status=status)


class ObservationTests(unittest.TestCase):
    def test_validation_and_unknown_unreadable_semantics(self):
        unknown = obs("tower_visual", 1, 2, {"state": "unknown"}, subject="tower", status="unknown")
        unreadable = obs("tower_visual", 2, 3, {"state": "unreadable"}, subject="tower", status="unreadable")
        self.assertEqual(unknown.to_dict()["status"], "unknown")
        self.assertEqual(unreadable.to_dict()["status"], "unreadable")
        with self.assertRaises(ValueError):
            Observation.create(obs_type="x", start_sec=2, end_sec=1, subject="x", value={}, confidence=.5, detector="x")

    def test_timeline_orders_and_preserves_conflicts(self):
        timeline = EvidenceTimeline()
        a = obs("objective_result", 5, 6, {"winner": "ally"}, subject="dragon")
        b = obs("objective_result", 5, 6, {"winner": "enemy"}, subject="dragon")
        timeline.extend([b, a])
        self.assertEqual(len(timeline.between(5, 6)), 2)
        self.assertEqual({x.value["winner"] for x in timeline.between(5, 6)}, {"enemy", "ally"})

    def test_observation_identity_includes_status_and_provenance(self):
        observed = obs("x", 1, 2, {"value": 1}, confidence=.9, status="observed")
        unknown = obs("x", 1, 2, {"value": 1}, confidence=0, status="unknown")
        self.assertNotEqual(observed.observation_id, unknown.observation_id)
        timeline = EvidenceTimeline([observed, unknown])
        self.assertEqual(len(timeline.observations), 2)


class DetectorTests(unittest.TestCase):
    def test_objective_tower_fusion_has_provenance_and_transition(self):
        context = DetectorContext("match", observations=(obs("objective_audio", 10, 12, {"identity": "dragon"}, subject="dragon"), obs("objective_visual", 11, 12, {"identity": "dragon", "winner": "ally"}, subject="dragon"), obs("tower_visual", 20, 20, {"state": "present"}, subject="mid_outer"), obs("tower_visual", 40, 40, {"state": "destroyed"}, subject="mid_outer")))
        result = run_detector(ObjectiveTowerFusionDetector(), context)
        self.assertTrue(any(x.type == "objective_result" for x in result.observations))
        transition = next(x for x in result.observations if x.type == "tower_state_transition")
        self.assertEqual(len(transition.evidence_refs), 2)
        self.assertTrue(all(x.evidence_refs for x in result.observations))

    def test_tower_evidence_is_processed_without_objective_evidence(self):
        context = DetectorContext("match", observations=(obs("tower_visual", 20, 20, {"state": "present"}, subject="mid_outer"), obs("tower_visual", 40, 40, {"state": "destroyed"}, subject="mid_outer")))
        result = run_detector(ObjectiveTowerFusionDetector(), context)
        self.assertTrue(any(x.type == "objective_state" and x.status == "unknown" for x in result.observations))
        self.assertTrue(any(x.type == "tower_state" for x in result.observations))
        self.assertTrue(any(x.type == "tower_state_transition" for x in result.observations))

    def test_unknown_tower_state_cannot_create_observed_transition(self):
        context = DetectorContext("match", observations=(obs("tower_visual", 20, 20, {"state": "unknown"}, subject="mid_outer", status="unknown"), obs("tower_visual", 40, 40, {"state": "destroyed"}, subject="mid_outer")))
        result = run_detector(ObjectiveTowerFusionDetector(), context)
        self.assertFalse(any(x.type == "tower_state_transition" for x in result.observations))

    def test_lifecycle_unknown_does_not_become_alive(self):
        result = run_detector(LifecycleRecallDetector(), DetectorContext("match", duration_sec=90))
        self.assertEqual(result.observations[0].status, "unknown")
        self.assertEqual(result.observations[0].value["state"], "unknown")

    def test_lifecycle_state_isolated_by_subject(self):
        context = DetectorContext("match", observations=(obs("lifecycle_state", 1, 1, {"state": "dead"}, subject="a"), obs("lifecycle_state", 2, 2, {"state": "alive"}, subject="b")))
        result = run_detector(LifecycleRecallDetector(), context)
        b_state = [x for x in result.observations if x.subject == "b"][-1]
        self.assertEqual(b_state.value["state"], "alive")

    def test_economy_items_emit_event_driven_diff(self):
        context = DetectorContext("match", observations=(obs("inventory_snapshot", 10, 10, {"items": {"1": "boots"}}), obs("inventory_snapshot", 30, 30, {"items": {"1": "sword"}})))
        result = run_detector(EconomyItemDetector(), context)
        self.assertTrue(any(x.type == "item_replaced" for x in result.observations))

    def test_economy_history_does_not_cross_subjects(self):
        context = DetectorContext("match", observations=(obs("inventory_snapshot", 10, 10, {"items": {"1": "boots"}}, subject="a"), obs("inventory_snapshot", 20, 20, {"items": {"1": "sword"}}, subject="b")))
        result = run_detector(EconomyItemDetector(), context)
        self.assertFalse(any(x.type == "item_replaced" for x in result.observations))

    def test_item_diff_references_prior_and_current_snapshots(self):
        context = DetectorContext("match", observations=(obs("inventory_snapshot", 10, 10, {"items": {"1": "boots"}}, subject="a"), obs("inventory_snapshot", 20, 20, {"items": {"1": "sword"}}, subject="a")))
        result = run_detector(EconomyItemDetector(), context)
        diff = next(x for x in result.observations if x.type == "item_replaced")
        self.assertEqual(len(diff.evidence_refs), 2)
        self.assertEqual(set(diff.evidence_refs), set(diff.dependencies))

    def test_wave_preserves_occlusion(self):
        result = run_detector(CoarseWaveDetector(), DetectorContext("match", observations=(obs("minion_cluster", 10, 12, {}, subject="mid", status="unreadable"),)))
        self.assertEqual(result.observations[0].status, "unreadable")
        self.assertNotEqual(result.observations[0].value.get("pressure"), "none")

    def test_isolated_cluster_does_not_create_teamfight(self):
        result = run_detector(TeamfightDetector(), DetectorContext("match", observations=(obs("hero_cluster", 10, 15, {"count": 4}),)))
        self.assertFalse(any(x.type == "teamfight_episode" for x in result.observations))

    def test_teamfight_requires_more_than_one_signal_and_links_membership(self):
        context = DetectorContext("match", observations=(obs("hero_cluster", 10, 15, {"count": 4}), obs("combat_audio", 12, 14, {"event": "fight"}), obs("player_position", 11, 13, {"x": 1, "y": 2})))
        result = run_detector(TeamfightDetector(), context)
        episode = next(x for x in result.observations if x.type == "teamfight_episode")
        membership = next(x for x in result.observations if x.type == "teamfight_membership")
        self.assertIn(episode.observation_id, membership.dependencies)

    def test_cooldown_transitions_are_explicit(self):
        context = DetectorContext("match", observations=(obs("cooldown_ui", 10, 10, {"skill": "ultimate", "state": "ready"}), obs("cooldown_ui", 20, 20, {"skill": "ultimate", "state": "on_cooldown"})))
        result = run_detector(CooldownReadinessDetector(), context)
        self.assertTrue(any(x.type == "cooldown_transition" and x.value["transition"] == "used_transition" for x in result.observations))

    def test_candidate_window_only_excludes_out_of_window_inputs(self):
        context = DetectorContext("match", windows=((10, 20),), config={"candidate_window_only": True}, observations=(obs("cooldown_ui", 5, 5, {"skill": "ultimate", "state": "ready"}), obs("cooldown_ui", 12, 12, {"skill": "ultimate", "state": "on_cooldown"})))
        result = run_detector(CooldownReadinessDetector(), context)
        self.assertEqual(len([x for x in result.observations if x.type == "cooldown_readiness"]), 1)
        self.assertEqual(result.observations[0].start_sec, 12)

    def test_orchestrator_honors_disabled_stage_and_configured_version(self):
        orch = Orchestrator.__new__(Orchestrator)
        orch.config = {"detectors": {"objective_tower_fusion": {"enabled": False, "implementation_version": "custom-v2"}}, "evidence_timeline": {"output_dir": "/tmp/hokcoach-test-cache"}}
        disabled = orch.run_detector_stage("objective_tower_fusion", "match")
        self.assertIn("detector_disabled_by_configuration", disabled.warnings)
        result = orch.run_detector_stage("objective_tower_fusion", "match", config={"enabled": True, "implementation_version": "custom-v2"}, cache_dir=Path(tempfile.mkdtemp()))
        self.assertEqual(result.detector_version, "custom-v2")

    def test_cache_key_changes_only_with_relevant_inputs(self):
        ctx = DetectorContext("match", media_hash="abc", config={"threshold": .8})
        self.assertEqual(cache_key("x", "v1", ctx), cache_key("x", "v1", ctx))
        self.assertNotEqual(cache_key("x", "v1", ctx), cache_key("x", "v2", ctx))

    def test_configured_detector_version_reaches_observation_identity(self):
        context = DetectorContext("match", observations=(obs("objective_visual", 1, 2, {"identity": "dragon"}, subject="dragon"),))
        result_v1 = run_detector(ObjectiveTowerFusionDetector(), context)
        result_v2 = run_detector(ObjectiveTowerFusionDetector(), context, version_override="custom-v2")
        self.assertEqual({x.detector_version for x in result_v2.observations}, {"custom-v2"})
        self.assertNotEqual(result_v1.observations[0].observation_id, result_v2.observations[0].observation_id)

    def test_persistent_cache_reuses_one_detector_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = DetectorCache(Path(tmp))
            context = DetectorContext("match", observations=(obs("objective_visual", 1, 2, {"identity": "dragon", "winner": "ally"}, subject="dragon"),))
            first = run_detector(ObjectiveTowerFusionDetector(), context, cache=cache)
            second = run_detector(ObjectiveTowerFusionDetector(), context, cache=cache)
            changed = DetectorContext("match", observations=(obs("objective_visual", 1, 2, {"identity": "dragon", "winner": "enemy"}, subject="dragon"),))
            third = run_detector(ObjectiveTowerFusionDetector(), changed, cache=cache)
            self.assertEqual(first.to_dict(), second.to_dict())
            self.assertNotEqual(first.cache_key, third.cache_key)
            self.assertEqual(len(list(Path(tmp).glob("*.json"))), 2)


class PersistenceTests(unittest.TestCase):
    def test_timeline_round_trip_is_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "timeline.jsonl"
            timeline = EvidenceTimeline([obs("player_death", 4, 5, {"confirmed": True})])
            timeline.save(path)
            first = path.read_bytes()
            self.assertEqual(EvidenceTimeline.load(path).to_jsonl().encode(), first)


if __name__ == "__main__":
    unittest.main()
