import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

from core.cooldown_recognizer import (
    CooldownConfigurationError,
    CooldownTemplateRecognizer,
    load_cooldown_manifest,
)
from core.evidence_timeline import EvidenceTimeline
from core.observations import Observation
from core.orchestrator import Orchestrator, _cooldown_recognizer_from_config
from core.production_detectors import CooldownReadinessDetector
from core.raw_video_extractors import extract_raw_video_observations
from core.detector_stage import DetectorContext, run_detector
from utils.config_utils import load_yaml

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "data/evaluation/replay_seeds/calibration/hokclass_001/cooldowns"
MANIFEST_PATH = BASE / "cooldown_calibration_manifest.json"


def atomic(start, state, *, skill="ultimate", subject="player", status="observed", source="source-a", layout="layout-a"):
    return Observation.create(
        obs_type="cooldown_ui",
        start_sec=start,
        end_sec=start,
        subject=subject,
        value={"skill": skill, "state": state, "source_hash": source, "layout_profile": layout},
        confidence=.9 if status == "observed" else 0.0,
        detector="cooldown_visual",
        detector_version="cooldown-test",
        evidence_refs=[f"source={source}|timestamp_sec={start}|layout={layout}|slot={skill}"],
        status=status,
    )


class CooldownConfigurationTests(unittest.TestCase):
    def _templates(self, directory: Path):
        ready = directory / "ready.png"
        cooldown = directory / "cooldown.png"
        cv2.imwrite(str(ready), np.zeros((8, 8), dtype=np.uint8))
        cv2.imwrite(str(cooldown), np.full((8, 8), 255, dtype=np.uint8))
        return {"ultimate": {"ready": ready, "on_cooldown": cooldown}}

    def test_shared_manifest_loads_and_stale_asset_is_absent(self):
        manifest = load_cooldown_manifest(MANIFEST_PATH)
        self.assertEqual(manifest["expected_source_dimensions"], [1280, 582])
        self.assertFalse(any(BASE.glob("evaluation/ultimate_238*")))
        config = load_yaml(ROOT / "coach/config/config.yaml")
        recognizer, rois = _cooldown_recognizer_from_config(config["raw_video"]["cooldown_recognizer"])
        self.assertEqual(recognizer.layout_profile, manifest["layout_profile"])
        self.assertEqual(set(rois), set(manifest["roi_profiles"]))

    def test_malformed_manifest_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            path.write_text(json.dumps({"templates": {}}), encoding="utf-8")
            with self.assertRaises(CooldownConfigurationError):
                load_cooldown_manifest(path)

    def test_missing_templates_invalid_roi_and_missing_state_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            templates = self._templates(directory)
            with self.assertRaises(CooldownConfigurationError):
                CooldownTemplateRecognizer({"ultimate": {"ready": templates["ultimate"]["ready"]}})
            with self.assertRaises(CooldownConfigurationError):
                CooldownTemplateRecognizer(templates, expected_source_dimensions=(10, 10), rois={"ultimate": {"x": -1, "y": 0, "w": 2, "h": 2}})
            with self.assertRaises(CooldownConfigurationError):
                CooldownTemplateRecognizer(templates, expected_source_dimensions=(10, 10), rois={"ultimate": {"x": 9, "y": 9, "w": 2, "h": 2}})
            with self.assertRaises(CooldownConfigurationError):
                CooldownTemplateRecognizer(templates, expected_source_dimensions=(10,))
            missing = {"ultimate": {"ready": directory / "missing.png", "on_cooldown": templates["ultimate"]["on_cooldown"]}}
            with self.assertRaises(CooldownConfigurationError):
                CooldownTemplateRecognizer(missing)

    def test_observed_ready_on_cooldown_unknown_and_unreadable(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            templates = self._templates(directory)
            recognizer = CooldownTemplateRecognizer(templates, max_error=.1, min_margin=.1, min_mean_by_slot={"ultimate": 0})
            _, ready = recognizer.recognize(templates["ultimate"]["ready"], slot="ultimate", start_sec=1, end_sec=1)
            _, cooldown = recognizer.recognize(templates["ultimate"]["on_cooldown"], slot="ultimate", start_sec=2, end_sec=2)
            ambiguous_path = directory / "ambiguous.png"
            cv2.imwrite(str(ambiguous_path), np.full((8, 8), 127, dtype=np.uint8))
            _, ambiguous = recognizer.recognize(ambiguous_path, slot="ultimate", start_sec=3, end_sec=3)
            unreadable = recognizer.recognize_hud(directory / "not-a-frame.png", slot="ultimate", roi={"x": 0, "y": 0, "w": 2, "h": 2}, start_sec=4, end_sec=4, evidence_ref="unreadable");
            self.assertEqual((ready.status, ready.value["state"]), ("observed", "ready"))
            self.assertEqual((cooldown.status, cooldown.value["state"]), ("observed", "on_cooldown"))
            self.assertEqual((ambiguous.status, ambiguous.value["state"], ambiguous.confidence), ("unknown", "unknown", 0.0))
            self.assertEqual((unreadable.status, unreadable.value["state"], unreadable.confidence), ("unreadable", "unknown", 0.0))

    def test_fingerprint_changes_after_template_or_config_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            templates = self._templates(directory)
            first = CooldownTemplateRecognizer(templates, min_margin=.1)
            second = CooldownTemplateRecognizer(templates, min_margin=.2)
            self.assertNotEqual(first.version, second.version)
            cv2.imwrite(str(templates["ultimate"]["ready"]), np.full((8, 8), 20, dtype=np.uint8))
            third = CooldownTemplateRecognizer(templates, min_margin=.1)
            self.assertNotEqual(first.version, third.version)


class CooldownFusionTests(unittest.TestCase):
    def run_detector(self, observations, **config):
        return run_detector(CooldownReadinessDetector(), DetectorContext("match", observations=tuple(observations), config=config))

    def test_transition_requires_two_observed_states_and_retains_both_refs(self):
        result = self.run_detector([atomic(10, "ready"), atomic(20, "on_cooldown")], max_transition_gap_sec=30)
        transition = next(item for item in result.observations if item.type == "cooldown_transition")
        self.assertEqual(transition.value["transition"], "used_transition")
        self.assertEqual(len(transition.evidence_refs), 2)
        self.assertEqual(set(transition.evidence_refs), set(transition.dependencies))
        became_ready = self.run_detector([atomic(10, "on_cooldown"), atomic(20, "ready")], max_transition_gap_sec=30)
        self.assertTrue(any(item.value.get("transition") == "became_ready" for item in became_ready.observations if item.type == "cooldown_transition"))

    def test_unknown_unreadable_gap_layout_source_skill_and_subject_do_not_transition(self):
        cases = [
            [atomic(10, "ready"), atomic(15, "unknown", status="unknown"), atomic(20, "on_cooldown")],
            [atomic(10, "ready"), atomic(15, "unreadable", status="unreadable"), atomic(20, "on_cooldown")],
            [atomic(10, "ready"), atomic(100, "on_cooldown")],
            [atomic(10, "ready", layout="a"), atomic(20, "on_cooldown", layout="b")],
            [atomic(10, "ready", source="a"), atomic(20, "on_cooldown", source="b")],
            [atomic(10, "ready", skill="ultimate"), atomic(20, "on_cooldown", skill="summoner_flash")],
            [atomic(10, "ready", subject="player-a"), atomic(20, "on_cooldown", subject="player-b")],
        ]
        for observations in cases:
            result = self.run_detector(observations, max_transition_gap_sec=30)
            self.assertFalse(any(item.type == "cooldown_transition" for item in result.observations))


class CooldownPipelineTests(unittest.TestCase):
    def test_candidate_dedup_before_during_after_sampling(self):
        calls = []

        def fake_probe(_video):
            return 60.0

        def fake_grab(_video, timestamp, target):
            calls.append(round(timestamp, 3))
            target.write_bytes(b"fixture")
            return target

        class Recognizer:
            expected_source_dimensions = None
            version = "cooldown-test"
            layout_profile = "layout-a"
            def recognize_hud(self, path, *, slot, roi, start_sec, end_sec, evidence_ref, source_dimensions=None):
                return Observation.create(obs_type="cooldown_ui", start_sec=start_sec, end_sec=end_sec, subject="player", value={"skill": slot, "state": "ready"}, confidence=.9, detector="cooldown_visual", detector_version=self.version, evidence_refs=[evidence_ref], status="observed")

        with patch("core.raw_video_extractors._probe_duration", fake_probe), patch("core.raw_video_extractors._probe_dimensions", return_value=(1280, 582)), patch("core.raw_video_extractors.video_utils.grab_minimap_frame", side_effect=fake_grab), patch("core.raw_video_extractors.video_utils.grab_hud_frame", side_effect=fake_grab):
            observations, metrics, windows = extract_raw_video_observations(
                "fixture.webm",
                seed_windows=[(10, 12), (11, 13)],
                cooldown_recognizer=Recognizer(),
                cooldown_rois={"ultimate": {"x": 0, "y": 0, "w": 1, "h": 1}},
                window_padding_sec=0,
                samples_before=1,
                samples_during=3,
                samples_after=1,
                before_sec=2,
                after_sec=2,
            )
        timestamps = sorted(set(calls))
        self.assertEqual(windows, [(10.0, 13.0)])
        self.assertEqual(timestamps, [8.0, 10.0, 11.5, 13.0, 15.0])
        self.assertEqual(metrics.frames_requested, 10)
        self.assertEqual(len([item for item in observations if item.type == "cooldown_ui"]), 5)

    def test_cooldown_fingerprint_changes_only_cooldown_identity(self):
        class Recognizer:
            def __init__(self, version):
                self.version = version
            def recognize_hud(self, _path, *, slot, roi, start_sec, end_sec, evidence_ref):
                return Observation.create(obs_type="cooldown_ui", start_sec=start_sec, end_sec=end_sec, subject="player", value={"skill": slot, "state": "ready"}, confidence=.9, detector="cooldown_visual", detector_version=self.version, evidence_refs=[evidence_ref], status="observed")

        def fake_grab(_video, _timestamp, target):
            target.write_bytes(b"fixture")
            return target

        def run(version):
            with patch("core.raw_video_extractors._probe_duration", return_value=1.0), patch("core.raw_video_extractors.video_utils.grab_minimap_frame", side_effect=fake_grab), patch("core.raw_video_extractors.video_utils.grab_hud_frame", side_effect=fake_grab):
                return extract_raw_video_observations("fixture.webm", seed_windows=[(.5, .5)], window_padding_sec=0, cooldown_recognizer=Recognizer(version), cooldown_rois={"ultimate": {"x": 0, "y": 0, "w": 1, "h": 1}})[0]
        first, second = run("cooldown-a"), run("cooldown-b")
        by_type = lambda records, kind: next(item.observation_id for item in records if item.type == kind)
        self.assertNotEqual(by_type(first, "cooldown_ui"), by_type(second, "cooldown_ui"))
        self.assertEqual(by_type(first, "inventory_snapshot"), by_type(second, "inventory_snapshot"))
        self.assertEqual(by_type(first, "minion_cluster"), by_type(second, "minion_cluster"))

    def test_timeline_and_serialization_preserve_atomic_and_derived_cooldown_observations(self):
        orch = Orchestrator.__new__(Orchestrator)
        orch.config = {"detectors": {"high_value_cooldowns": {"enabled": True, "implementation_version": "cooldowns-test", "candidate_window_only": True, "max_transition_gap_sec": 30}}, "evidence_timeline": {"output_dir": "/tmp/hokcoach-test-cache"}}
        timeline, results = orch.build_match_timeline("match", [atomic(10, "ready"), atomic(20, "on_cooldown")], windows=[(0, 30)], duration_sec=30)
        payload = json.loads("[" + ",".join(item.to_json() for item in timeline.observations) + "]")
        self.assertTrue(any(item["type"] == "cooldown_ui" for item in payload))
        self.assertTrue(any(item["type"] == "cooldown_readiness" for item in payload))
        self.assertTrue(any(item["type"] == "cooldown_transition" for item in payload))
        self.assertTrue(all(item["detector_version"] for item in payload if item["type"].startswith("cooldown")))
        self.assertIn("high_value_cooldowns", results)

    def test_disabled_by_default_and_no_cooldown_work_when_disabled(self):
        config = load_yaml(ROOT / "coach/config/config.yaml")
        self.assertFalse(config["raw_video"]["cooldown_recognizer"]["enabled"])
        with patch("core.raw_video_extractors._probe_duration", return_value=60.0), patch("core.raw_video_extractors.video_utils.grab_minimap_frame", side_effect=lambda _video, _timestamp, target: target.write_bytes(b"crop")), patch("core.raw_video_extractors.video_utils.grab_hud_frame", side_effect=lambda _video, _timestamp, target: target.write_bytes(b"crop")):
            observations, metrics, windows = extract_raw_video_observations("fixture.webm", cooldown_recognizer=None, cooldown_rois=None, seed_windows=[], emit_cooldown_placeholders=False)
        self.assertEqual(windows, [(0.0, 3.1), (27.0, 33.1), (57.0, 60.0)])
        self.assertFalse(metrics.to_dict().get("cooldown_enabled", False))
        self.assertTrue(all(item.type != "cooldown_ui" for item in observations))


if __name__ == "__main__":
    unittest.main()
