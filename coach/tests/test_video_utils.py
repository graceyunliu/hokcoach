# -*- coding: utf-8 -*-
"""AGE-136：确定性KDA模板读数器。"""

import tempfile
import sys
import unittest
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils import video_utils  # noqa: E402

try:
    import cv2  # type: ignore
    import numpy as np  # type: ignore
    _HAS_CV2 = True
except ImportError:
    _HAS_CV2 = False


@unittest.skipUnless(_HAS_CV2, "需要 opencv-python + numpy")
class TestTemplateKdaReader(unittest.TestCase):
    ROOT = Path(__file__).resolve().parents[2]
    ISOLATED_SLOTS = ((5, 0, 45, 45), (90, 0, 135, 45), (175, 0, 220, 45))

    def test_same_frame_is_deterministic(self):
        reader = video_utils.make_template_kda_reader(slots=self.ISOLATED_SLOTS)
        frame = self.ROOT / "assets" / "age131_kda_slots_crop.png"
        results = [reader(frame) for _ in range(5)]
        self.assertEqual(results, [(1, 3, 0)] * 5)

    def test_digit_one_has_multiple_real_exemplars(self):
        library = video_utils._load_kda_templates(
            video_utils._DEFAULT_KDA_TEMPLATE_DIR)
        self.assertGreaterEqual(len(library[1]), 5)
        reader = video_utils.make_template_kda_reader(slots=self.ISOLATED_SLOTS)
        self.assertEqual(
            reader(self.ROOT / "assets" / "age131_kda_slots_crop.png"),
            (1, 3, 0),
        )

    def test_otsu_reads_low_contrast_digit(self):
        source = cv2.imread(str(
            self.ROOT / "assets" / "age131_kda_low_contrast_example.png"))
        fixture = np.hstack([source, source, source])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "low_contrast.png"
            cv2.imwrite(str(path), fixture)
            h, w = source.shape[:2]
            slots = tuple((i * w, 0, (i + 1) * w, h) for i in range(3))
            reader = video_utils.make_template_kda_reader(slots=slots)
            self.assertEqual(reader(path), (1, 1, 1))

    def test_segments_multi_digit_value(self):
        library = video_utils._load_kda_templates(
            video_utils._DEFAULT_KDA_TEMPLATE_DIR)

        def raw_glyph(digit):
            image = library[digit][0]
            ys, xs = np.where(image > 0)
            glyph = image[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
            height = 28
            width = max(2, round(glyph.shape[1] * height / glyph.shape[0]))
            return cv2.resize(glyph, (width, height), interpolation=cv2.INTER_NEAREST)

        def render_slot(value):
            slot = np.zeros((40, 70), dtype=np.uint8)
            glyphs = [raw_glyph(int(ch)) for ch in str(value)]
            total = sum(g.shape[1] for g in glyphs) + 3 * (len(glyphs) - 1)
            x = 65 - total
            for glyph in glyphs:
                slot[6:6 + glyph.shape[0], x:x + glyph.shape[1]] = glyph
                x += glyph.shape[1] + 3
            return cv2.cvtColor(slot, cv2.COLOR_GRAY2BGR)

        fixture = np.hstack([render_slot(10), render_slot(0), render_slot(1)])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "multi_digit.png"
            cv2.imwrite(str(path), fixture)
            slots = ((0, 0, 70, 40), (70, 0, 140, 40), (140, 0, 210, 40))
            reader = video_utils.make_template_kda_reader(slots=slots)
            self.assertEqual(reader(path), (10, 0, 1))

    def test_rejects_unreadable_frame_instead_of_guessing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "blank.png"
            cv2.imwrite(str(path), np.zeros((140, 650, 3), dtype=np.uint8))
            self.assertIsNone(video_utils.make_template_kda_reader()(path))


class TestRiverGeometry(unittest.TestCase):
    LINE = ((0.0, 1.0), (1.0, 0.0))

    def test_enemy_friendly_and_boundary(self):
        crop = {"x": 0, "y": 0, "w": 100, "h": 100}
        self.assertEqual(video_utils.river_side((80, 10), crop, self.LINE), "enemy")
        self.assertEqual(video_utils.river_side((20, 90), crop, self.LINE), "friendly")
        self.assertEqual(video_utils.river_side((50, 50), crop, self.LINE), "river")

    def test_outside_calibration_abstains(self):
        crop = {"x": 0, "y": 0, "w": 100, "h": 100}
        short = ((0.2, 0.8), (0.8, 0.2))
        self.assertEqual(video_utils.river_side((5, 50), crop, short),
                         "not_determinable")


@unittest.skipUnless(_HAS_CV2, "需要 opencv-python + numpy")
class TestPlayerIconIdentity(unittest.TestCase):
    def test_unique_green_outer_ring_identifies_player(self):
        image = np.zeros((320, 420, 3), dtype=np.uint8)
        cv2.circle(image, (100, 100), 14, (255, 0, 0), -1)
        cv2.circle(image, (200, 120), 27, (0, 255, 0), 4)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "icons.png"
            cv2.imwrite(str(path), image)
            icons = video_utils.detect_hero_icons(path)
        player = video_utils.identify_player_icon(icons["allies"])
        self.assertIsNotNone(player)
        self.assertAlmostEqual(player["cx"], 200, delta=1)
        self.assertEqual(player["player_marker_source"], "green_outer_ring")

    def test_ambiguous_or_unmarked_abstains(self):
        self.assertIsNone(video_utils.identify_player_icon([{"cx": 1, "cy": 1}]))
        self.assertIsNone(video_utils.identify_player_icon([
            {"player_marker": True}, {"player_marker": True}]))


class TestAnomalousDisplacement(unittest.TestCase):
    def _detect(self, distance):
        samples = [
            {"ts": 0.0, "enemies": [{"cx": 0.0, "cy": 0.0}]},
            {"ts": 1.0, "enemies": [{"cx": distance, "cy": 0.0}]},
        ]
        return video_utils.detect_anomalous_displacements(
            samples, max_move_speed_world_units_sec=10,
            pixels_per_world_unit=1, threshold_multiplier=1.5,
            jitter_tolerance_px=0)

    def test_normal_movement_does_not_trigger(self):
        self.assertEqual(self._detect(10), [])

    def test_clear_jump_triggers(self):
        findings = self._detect(25)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["kind"], "anomalous_displacement")

    def test_boundary_speed_does_not_trigger(self):
        self.assertEqual(self._detect(15), [])


@unittest.skipUnless(_HAS_CV2, "需要numpy")
class TestAudioFusion(unittest.TestCase):
    @staticmethod
    def _wav(path: Path, samples, rate=8000):
        values = np.clip(samples * 32767, -32768, 32767).astype("<i2")
        with wave.open(str(path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(rate)
            wav.writeframes(values.tobytes())

    def test_template_match_and_confidence_boost(self):
        rate = 8000
        tone = np.sin(2 * np.pi * 700 * np.arange(rate // 2) / rate)
        audio = np.concatenate([np.zeros(rate), tone, np.zeros(rate)])
        with tempfile.TemporaryDirectory() as tmp:
            source, template = Path(tmp) / "source.wav", Path(tmp) / "kill.wav"
            self._wav(source, audio, rate)
            self._wav(template, tone, rate)
            hits = video_utils.match_audio_template(
                source, template, similarity_threshold=0.9)
        self.assertTrue(hits)
        self.assertAlmostEqual(hits[0]["ts"], 1.0, delta=0.06)
        fused = video_utils.fuse_visual_audio_confidence(
            0.6, 1.0, hits, matching_templates={"kill"})
        self.assertTrue(fused["audio_corroborated"])
        self.assertGreater(fused["confidence"], 0.6)


if __name__ == "__main__":
    unittest.main()
