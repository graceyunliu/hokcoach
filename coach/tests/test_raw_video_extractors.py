from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.raw_video_extractors import _probe_duration, _window_union, extract_raw_video_observations


ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / "Seed Videos" / "hokclass_001_QK9QwHo1RhY.webm"


class RawVideoExtractorTests(unittest.TestCase):
    def test_window_union_merges_overlaps_and_applies_padding(self):
        result = _window_union([(10, 12), (11, 15), (30, 31)], duration=40, padding=1)
        self.assertEqual(result, [(9, 16), (29, 32)])

    def test_non_retained_workspace_is_removed_and_semantic_unreadable_is_counted(self):
        targets = []
        def fake_grab(_video, _timestamp, target):
            target.write_bytes(b"crop")
            targets.append(target)
            return target
        with tempfile.TemporaryDirectory() as tmp:
            with patch("core.raw_video_extractors._probe_duration", return_value=1.0), patch("core.raw_video_extractors.video_utils.grab_minimap_frame", side_effect=fake_grab), patch("core.raw_video_extractors.video_utils.grab_hud_frame", side_effect=fake_grab):
                _, metrics, _ = extract_raw_video_observations("fixture.webm", sample_interval_sec=10, max_candidate_windows=1)
        self.assertEqual(metrics.decode_failures, 0)
        self.assertEqual(metrics.semantic_unreadable_frames, 2)
        self.assertEqual(metrics.semantic_unreadable_observations, 4)
        self.assertEqual(metrics.frames_unreadable, 2)
        self.assertTrue(all(not path.exists() for path in targets))

    def test_tower_and_minion_statuses_are_independent(self):
        class Recognizer:
            def recognize_all(self, _path):
                from core.tower_recognizer import TowerRecognition
                return {"ally_mid_outer": TowerRecognition("present", "observed", .9, .2, "present", "fixture", "ally_mid_outer")}
        def fake_grab(_video, _timestamp, target):
            target.write_bytes(b"crop")
            return target
        with patch("core.raw_video_extractors._probe_duration", return_value=1.0), patch("core.raw_video_extractors.video_utils.grab_minimap_frame", side_effect=fake_grab), patch("core.raw_video_extractors.video_utils.grab_hud_frame", side_effect=fake_grab):
            observations, _, _ = extract_raw_video_observations("fixture.webm", sample_interval_sec=10, max_candidate_windows=1, tower_recognizer=Recognizer())
        tower = next(item for item in observations if item.type == "tower_visual")
        minion = next(item for item in observations if item.type == "minion_cluster")
        self.assertEqual(tower.status, "observed")
        self.assertEqual(tower.subject, "ally_mid_outer")
        self.assertEqual(minion.status, "unreadable")

    def test_cooldown_recognizer_emits_established_cooldown_ui_contract(self):
        from core.observations import Observation
        class Recognizer:
            version = 'cooldown-template-test'
            def recognize_hud(self, _path, *, slot, roi, start_sec, end_sec, evidence_ref):
                return Observation.create(obs_type='cooldown_ui', start_sec=start_sec, end_sec=end_sec, subject=slot, value={'skill': slot, 'state': 'ready'}, confidence=.9, detector='cooldown_visual', detector_version=self.version, evidence_refs=[evidence_ref], status='observed')
        def fake_grab(_video, _timestamp, target):
            target.write_bytes(b'crop')
            return target
        with patch('core.raw_video_extractors._probe_duration', return_value=1.0), patch('core.raw_video_extractors.video_utils.grab_minimap_frame', side_effect=fake_grab), patch('core.raw_video_extractors.video_utils.grab_hud_frame', side_effect=fake_grab):
            observations, _, _ = extract_raw_video_observations('fixture.webm', sample_interval_sec=10, max_candidate_windows=1, cooldown_recognizer=Recognizer(), cooldown_rois={'ultimate': {'x': 0, 'y': 0, 'w': 1, 'h': 1}})
        cooldown = [item for item in observations if item.type == 'cooldown_ui']
        self.assertEqual(len(cooldown), 1)
        self.assertEqual(cooldown[0].value['skill'], 'ultimate')
        self.assertEqual(cooldown[0].value['state'], 'ready')
        self.assertEqual(cooldown[0].status, 'observed')

    def test_tower_calibration_identity_isolated_from_other_capabilities(self):
        from core.tower_recognizer import TowerRecognition
        class Recognizer:
            def __init__(self, version):
                self.calibration_version = version
                self.layout_profile = "profile"
            def recognize_all(self, _path):
                return {"ally_mid_outer": TowerRecognition("present", "observed", .9, .2, "present", "fixture", "ally_mid_outer")}
        def fake_grab(_video, _timestamp, target):
            target.write_bytes(b"crop")
            return target
        def run(version):
            with patch("core.raw_video_extractors._probe_duration", return_value=1.0), patch("core.raw_video_extractors.video_utils.grab_minimap_frame", side_effect=fake_grab), patch("core.raw_video_extractors.video_utils.grab_hud_frame", side_effect=fake_grab):
                return extract_raw_video_observations("fixture.webm", sample_interval_sec=10, max_candidate_windows=1, tower_recognizer=Recognizer(version))[0]
        first = run("cal-first")
        second = run("cal-second")
        by_type = lambda records, kind: next(item.observation_id for item in records if item.type == kind)
        self.assertNotEqual(by_type(first, "tower_visual"), by_type(second, "tower_visual"))
        for kind in ("minion_cluster", "inventory_snapshot", "cooldown_ui"):
            self.assertEqual(by_type(first, kind), by_type(second, kind))

    @unittest.skipUnless(SAMPLE.is_file(), "repository-local WebM fixture is unavailable")
    def test_browser_webm_packet_duration_and_safe_observations(self):
        duration = _probe_duration(SAMPLE)
        self.assertGreater(duration, 300)
        observations, metrics, windows = extract_raw_video_observations(SAMPLE, sample_interval_sec=1000, max_candidate_windows=1)
        self.assertEqual(len(windows), 1)
        self.assertGreater(metrics.frames_requested, 0)
        self.assertTrue(observations)
        self.assertTrue(all(item.status in {"unreadable", "observed"} for item in observations))
        self.assertTrue(any(item.status == "unreadable" for item in observations))


if __name__ == "__main__":
    unittest.main()
