import json
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from core.cooldown_messages import cooldown_message, cooldown_messages
from core.cooldown_recognizer import CooldownConfigurationError, CooldownTemplateRecognizer
from core.observations import Observation
from core.production_detectors import CooldownReadinessDetector
from core.detector_stage import DetectorContext, run_detector
from tools.annotate_cooldown import _evidence_ref, _validate_roi
from tools.ingest_cooldown_fixtures import _candidate_windows, _validate_annotations


def cooldown(start, state, *, source="source-a", layout="layout-a", status="observed"):
    return Observation.create(
        obs_type="cooldown_ui",
        start_sec=start,
        end_sec=start,
        subject="player",
        value={"skill": "ultimate", "state": state, "source_hash": source, "layout_profile": layout},
        confidence=.9 if status == "observed" else 0,
        detector="cooldown_visual",
        detector_version="test",
        evidence_refs=[f"source={source}|layout={layout}|timestamp_sec={start}"],
        status=status,
    )


class AnnotationAndFixtureTests(unittest.TestCase):
    def test_annotation_evidence_ref_and_roi_validation(self):
        roi = {"x": 1040, "y": 450, "w": 120, "h": 120}
        reference = _evidence_ref("a" * 64, 17.25, "ultimate", roi, "layout-a", "annotation-v1")
        self.assertIn("source_sha256=" + "a" * 64, reference)
        self.assertIn("timestamp_sec=17.250", reference)
        self.assertIn("roi_slot=ultimate", reference)
        self.assertIn('"w":120', reference)
        _validate_roi(roi, (1280, 582))
        with self.assertRaises(ValueError):
            _validate_roi({"x": 1200, "y": 450, "w": 120, "h": 120}, (1280, 582))

    def test_fixture_windows_deduplicate_and_annotation_provenance_is_strict(self):
        manifest = {
            "windows": [
                {"capability": "cooldowns", "window": {"start_sec": 10, "end_sec": 20}, "visual_triage_status": "pending_visual_triage"},
                {"capability": "cooldowns", "window": {"start_sec": 19, "end_sec": 30}, "visual_triage_status": "pending_visual_triage"},
                {"capability": "cooldowns", "window": {"start_sec": 90, "end_sec": 100}, "visual_triage_status": "out_of_range"},
            ]
        }
        windows, entries = _candidate_windows(manifest, 100, 120)
        self.assertEqual(windows, [(10.0, 30.0)])
        self.assertEqual(len(entries), 2)
        rows = [
            {"source_media": {"sha256": "canonical"}, "status": "accepted", "label": "ready", "split": "tuning", "slot": "ultimate", "timestamp_sec": 10, "roi": {"x": 0, "y": 0, "w": 1, "h": 1}},
            {"source_media": {"sha256": "other"}, "status": "accepted", "label": "ready", "split": "tuning", "slot": "ultimate", "timestamp_sec": 11, "roi": {"x": 0, "y": 0, "w": 1, "h": 1}},
            {"source_media": {"sha256": "canonical"}, "status": "rejected", "label": "unknown", "split": "evaluation", "slot": "ultimate", "timestamp_sec": 12, "roi": {"x": 0, "y": 0, "w": 1, "h": 1}},
        ]
        accepted, counts = _validate_annotations(rows, "canonical")
        self.assertEqual(len(accepted), 1)
        self.assertEqual(counts, {"accepted": 1, "rejected": 1, "source_mismatch": 1, "invalid": 0})


class SyntheticRobustnessTests(unittest.TestCase):
    def _recognizer(self, directory: Path):
        ready = np.full((32, 32), 80, dtype=np.uint8)
        cooldown = np.full((32, 32), 180, dtype=np.uint8)
        ready_path, cooldown_path = directory / "ready.png", directory / "cooldown.png"
        cv2.imwrite(str(ready_path), ready)
        cv2.imwrite(str(cooldown_path), cooldown)
        return CooldownTemplateRecognizer(
            {"ultimate": {"ready": ready_path, "on_cooldown": cooldown_path}},
            min_mean_by_slot={"ultimate": 1},
            max_error=.2,
            min_margin=.02,
        ), ready

    def test_brightness_blur_scale_and_compression_mutations_remain_observed(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            recognizer, base = self._recognizer(directory)
            mutations = [
                np.clip(base.astype(np.int16) + 12, 0, 255).astype(np.uint8),
                cv2.GaussianBlur(base, (3, 3), 0),
                cv2.resize(cv2.resize(base, (16, 16)), (32, 32)),
            ]
            encoded = cv2.imencode(".jpg", base, [int(cv2.IMWRITE_JPEG_QUALITY), 65])[1]
            mutations.append(cv2.imdecode(encoded, cv2.IMREAD_GRAYSCALE))
            for index, image in enumerate(mutations):
                path = directory / f"mutation-{index}.png"
                cv2.imwrite(str(path), image)
                prediction, observation = recognizer.recognize(path, slot="ultimate", start_sec=index, end_sec=index)
                self.assertEqual(prediction.state, "ready")
                self.assertEqual(observation.status, "observed")

    def test_shift_occlusion_black_missing_and_corrupt_template_abstain(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            recognizer, base = self._recognizer(directory)
            shifted = np.roll(base, 2, axis=1)
            shifted[0:8, 0:8] = 0
            shifted_path = directory / "shifted.png"
            cv2.imwrite(str(shifted_path), shifted)
            _, shifted_observation = recognizer.recognize(shifted_path, slot="ultimate", start_sec=1, end_sec=1)
            self.assertEqual(shifted_observation.status, "observed")
            black_path = directory / "black.png"
            cv2.imwrite(str(black_path), np.zeros((32, 32), dtype=np.uint8))
            _, black_observation = recognizer.recognize(black_path, slot="ultimate", start_sec=2, end_sec=2)
            self.assertEqual(black_observation.status, "unknown")
            _, missing_observation = recognizer.recognize(directory / "missing.png", slot="ultimate", start_sec=3, end_sec=3)
            self.assertEqual(missing_observation.status, "unreadable")
            corrupt = directory / "corrupt.png"
            corrupt.write_bytes(b"not an image")
            with self.assertRaises(CooldownConfigurationError):
                CooldownTemplateRecognizer({"ultimate": {"ready": corrupt, "on_cooldown": directory / "cooldown.png"}})


class TemporalAndSafeMessageTests(unittest.TestCase):
    def _run(self, records, **config):
        return run_detector(CooldownReadinessDetector(), DetectorContext("match", observations=tuple(records), config=config))

    def test_valid_sequence_and_one_second_flicker_guard(self):
        valid = self._run([cooldown(10, "ready"), cooldown(12, "on_cooldown"), cooldown(15, "on_cooldown"), cooldown(20, "ready")], min_transition_gap_sec=1, max_transition_gap_sec=30)
        transitions = [item for item in valid.observations if item.type == "cooldown_transition"]
        self.assertEqual([item.value["transition"] for item in transitions], ["used_transition", "became_ready"])
        flicker = self._run([cooldown(10, "on_cooldown"), cooldown(10.5, "ready"), cooldown(11, "on_cooldown")], min_transition_gap_sec=1, max_transition_gap_sec=30)
        self.assertFalse(any(item.type == "cooldown_transition" for item in flicker.observations))

    def test_safe_messages_never_promote_unknown_or_unsupported(self):
        ready = cooldown(1, "ready")
        unknown = cooldown(2, "unknown", status="unknown")
        unsupported = Observation.create(obs_type="cooldown_ui", start_sec=3, end_sec=3, subject="player", value={"skill": "ultimate", "state": "unknown", "reason": "unsupported_layout"}, confidence=0, detector="cooldown_visual", detector_version="test", evidence_refs=["ref"], status="unreadable")
        self.assertEqual(cooldown_message(ready), "Ultimate appeared ready")
        self.assertEqual(cooldown_message(unknown), "Cooldown state could not be read")
        self.assertEqual(cooldown_message(unsupported), "This replay layout is not yet supported")
        messages = cooldown_messages([ready, unknown, unsupported])
        self.assertEqual(len(messages), 3)
        self.assertEqual(messages[1]["status"], "unknown")


if __name__ == "__main__":
    unittest.main()
