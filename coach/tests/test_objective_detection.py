import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from core.detector_stage import DetectorContext
from core.objective_visual_recognizer import ObjectiveVisualRecognizer
from core.observations import Observation
from core.production_detectors import ObjectiveTowerFusionDetector


def obs(kind, start, end, value, *, subject="match", status="observed", confidence=0.8):
    return Observation.create(
        obs_type=kind,
        start_sec=start,
        end_sec=end,
        subject=subject,
        value=value,
        confidence=confidence if status == "observed" else 0.0,
        detector="test",
        evidence_refs=[f"test:{kind}:{start}"],
        status=status,
    )


class ObjectiveVisualRecognizerTests(unittest.TestCase):
    def _frames(self, root: Path):
        template = np.zeros((10, 20), dtype=np.uint8)
        template[:, :] = 220
        template_path = root / "dragon.png"
        cv2.imwrite(str(template_path), template)
        paths = []
        for index in range(2):
            image = np.zeros((60, 100), dtype=np.uint8)
            image[10:20, 20:40] = 220
            path = root / f"frame-{index}.png"
            cv2.imwrite(str(path), image)
            paths.append(path)
        return template_path, paths

    def test_temporal_template_confirmation_emits_activity_then_result(self):
        with tempfile.TemporaryDirectory() as directory:
            template, paths = self._frames(Path(directory))
            recognizer = ObjectiveVisualRecognizer(
                roi={"x": 20, "y": 10, "w": 20, "h": 10},
                templates={"dragon": template},
                layout_profile="test-layout-v1",
                expected_source_dimensions=(100, 60),
                roi_coordinate_space="source_relative",
                min_persistence=2,
            )
            result = recognizer.recognize_sequence(
                [(paths[0], 10.0, "frame-0"), (paths[1], 11.0, "frame-1")],
                source_hash="source-a",
            )
            self.assertEqual([item.status for item in result], ["observed", "observed"])
            self.assertEqual(result[0].value["state"], "activity")
            self.assertEqual(result[1].value["state"], "result")
            self.assertIn(recognizer.calibration_fingerprint, result[1].detector_version)

    def test_missing_viewport_for_viewport_relative_roi_abstains(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = np.zeros((60, 100), dtype=np.uint8)
            path = root / "frame.png"
            cv2.imwrite(str(path), image)
            recognizer = ObjectiveVisualRecognizer(
                roi={"x": 20, "y": 10, "w": 20, "h": 10},
                layout_profile="test-layout-v1",
                expected_source_dimensions=(100, 60),
            )
            result = recognizer.recognize_sequence([(path, 1.0, "frame")], source_hash="source-a")
            self.assertEqual(result[0].status, "unreadable")
            self.assertEqual(result[0].confidence, 0.0)

    def test_wrong_layout_dimensions_are_unreadable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "frame.png"
            cv2.imwrite(str(path), np.zeros((50, 90), dtype=np.uint8))
            recognizer = ObjectiveVisualRecognizer(
                roi={"x": 20, "y": 10, "w": 20, "h": 10},
                layout_profile="test-layout-v1",
                expected_source_dimensions=(100, 60),
            )
            result = recognizer.recognize_sequence([(path, 1.0, "frame", {"x": 0, "y": 0})], source_hash="source-a")
            self.assertEqual(result[0].status, "unreadable")


class ObjectiveFusionTests(unittest.TestCase):
    def test_audio_only_emits_activity_not_result(self):
        context = DetectorContext("match", observations=(obs("objective_audio", 10, 11, {"identity": "dragon"}),))
        result = ObjectiveTowerFusionDetector().run(context)
        self.assertTrue(any(item.type == "objective_activity" for item in result.observations))
        self.assertFalse(any(item.type == "objective_result" for item in result.observations))

    def test_visual_result_is_audio_corroborated_and_preserves_both_refs(self):
        audio = obs("objective_audio", 10, 12, {"identity": "dragon"})
        visual = obs("objective_visual", 11, 12, {"identity": "dragon", "state": "result", "winner": "ally"})
        context = DetectorContext("match", observations=(audio, visual))
        result = ObjectiveTowerFusionDetector().run(context)
        fused = next(item for item in result.observations if item.type == "objective_result")
        self.assertTrue(fused.value["audio_corroborated"])
        self.assertEqual(set(fused.dependencies), {audio.observation_id, visual.observation_id})

    def test_audio_visual_identity_disagreement_abstains(self):
        audio = obs("objective_audio", 10, 12, {"identity": "dragon"})
        visual = obs("objective_visual", 11, 12, {"identity": "tower", "state": "result"})
        result = ObjectiveTowerFusionDetector().run(DetectorContext("match", observations=(audio, visual)))
        conflict = next(item for item in result.observations if item.type == "objective_state")
        self.assertEqual(conflict.status, "unknown")
        self.assertEqual(conflict.value["reason"], "audio_visual_identity_conflict")


if __name__ == "__main__":
    unittest.main()


    def test_source_hash_mismatch_abstains_without_visual_positive(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "frame.png"
            cv2.imwrite(str(path), np.full((60, 100), 220, dtype=np.uint8))
            recognizer = ObjectiveVisualRecognizer(
                roi={"x": 20, "y": 10, "w": 20, "h": 10},
                layout_profile="test-layout-v1",
                expected_source_dimensions=(100, 60),
                roi_coordinate_space="source_relative",
                allowed_source_hashes=["canonical-source"],
            )
            result = recognizer.recognize_sequence([(path, 1.0, "frame")], source_hash="untrusted-source")
            self.assertEqual(result[0].status, "unreadable")
            self.assertEqual(result[0].value["reason"], "unsupported_source")
            self.assertEqual(result[0].confidence, 0.0)
