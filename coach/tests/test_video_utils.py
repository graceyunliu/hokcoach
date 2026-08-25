# -*- coding: utf-8 -*-
"""AGE-136：确定性KDA模板读数器。"""

import json
import tempfile
import sys
import unittest
import wave
from pathlib import Path
from unittest import mock

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


class TestSoloInEnemyHalf(unittest.TestCase):
    CROP = {"x": 0, "y": 0, "w": 100, "h": 100}

    @staticmethod
    def _sample(teammate_x=None):
        player = {"cx": 80.0, "cy": 10.0, "player_marker": True}
        allies = [player]
        if teammate_x is not None:
            allies.append({"cx": float(teammate_x), "cy": 10.0})
        return [{"ts": 10.0, "player": player, "allies": allies}]

    def test_isolated_enemy_half_is_true(self):
        self.assertTrue(video_utils.detect_solo_in_enemy_half(
            self._sample(20), isolation_distance_px=40, crop=self.CROP))

    def test_nearby_teammate_is_false(self):
        self.assertFalse(video_utils.detect_solo_in_enemy_half(
            self._sample(60), isolation_distance_px=40, crop=self.CROP))

    def test_boundary_distance_is_not_isolated(self):
        self.assertFalse(video_utils.detect_solo_in_enemy_half(
            self._sample(40), isolation_distance_px=40, crop=self.CROP))

    def test_missing_player_abstains(self):
        self.assertIsNone(video_utils.detect_solo_in_enemy_half(
            [{"ts": 10.0, "player": None, "allies": []}],
            isolation_distance_px=40, crop=self.CROP))

    def test_friendly_half_is_false_even_without_teammates(self):
        player = {"cx": 20.0, "cy": 90.0, "player_marker": True}
        self.assertFalse(video_utils.detect_solo_in_enemy_half(
            [{"ts": 10.0, "player": player, "allies": [player]}],
            isolation_distance_px=40, crop=self.CROP))


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

    def test_shipped_player_death_template_is_valid_pcm(self):
        template = (Path(__file__).resolve().parents[1] / "assets" /
                    "audio_templates" / "player_death_v1.wav")
        samples, rate = video_utils._read_pcm_wav(template)
        self.assertEqual(rate, 16000)
        self.assertEqual(len(samples), 12800)
        self.assertGreater(float(np.max(np.abs(samples))), 0.9)

    def test_game_voice_catalog_maps_all_65_local_templates(self):
        entries = video_utils.load_audio_template_catalog()
        self.assertEqual(len(entries), 65)
        self.assertEqual(len({entry["file"] for entry in entries}), 65)
        self.assertTrue(all(entry["usage"] == "exclude"
                            for entry in entries if entry["category"] == "draft"))
        jinchan_death = [entry for entry in entries
                         if entry["file"].endswith("金蝉播报 被击杀1.wav")]
        self.assertEqual(jinchan_death[0]["event"], "player_death")

    def test_game_voice_catalog_usage_filter(self):
        evidence = video_utils.load_audio_template_catalog(usages={"evidence"})
        self.assertTrue(evidence)
        self.assertTrue(all(entry["usage"] == "evidence" for entry in evidence))
        self.assertFalse(any(entry["category"] in {"draft", "communication"}
                             for entry in evidence))

    def test_global_timeline_preserves_intent_and_deduplicates_variants(self):
        rate = 8000
        motif = np.sin(2 * np.pi * 700 * np.arange(rate // 2) / rate)
        source_samples = np.concatenate([np.zeros(rate), motif, np.zeros(rate)])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            video = root / "clip.mp4"
            video.write_bytes(b"placeholder")
            replay_wav = root / "source.wav"
            self._wav(replay_wav, source_samples, rate)
            template_dir = root / "templates"
            template_dir.mkdir()
            for filename in ("normal.wav", "variant.wav", "ping.wav"):
                self._wav(template_dir / filename, motif, rate)
            catalog = root / "catalog.json"
            catalog.write_text(json.dumps({
                "schema_version": 1,
                "entries": [
                    {"file": "normal.wav", "event": "hero_killed",
                     "category": "combat", "perspective": "allied",
                     "usage": "evidence"},
                    {"file": "variant.wav", "event": "hero_killed",
                     "category": "combat", "perspective": "allied",
                     "usage": "evidence", "variant": "alternate"},
                    {"file": "ping.wav", "event": "ping_attack_enemy",
                     "category": "communication", "perspective": "allied",
                     "usage": "intent"},
                ],
            }), encoding="utf-8")
            with mock.patch.object(video_utils, "extract_audio_track",
                                   side_effect=lambda _v, out, sample_rate: (
                                       out.write_bytes(replay_wav.read_bytes()) or out)) as extract, \
                 mock.patch.object(video_utils, "_match_cached_features",
                                   wraps=video_utils._match_cached_features) as matcher:
                first = video_utils.build_audio_event_timeline(
                    str(video), template_dir=template_dir, catalog_path=catalog,
                    cache_dir=root / "cache", sample_rate=rate,
                    similarity_threshold=0.9)
                first_match_calls = matcher.call_count
                second = video_utils.build_audio_event_timeline(
                    str(video), template_dir=template_dir, catalog_path=catalog,
                    cache_dir=root / "cache", sample_rate=rate,
                    similarity_threshold=0.9)

        self.assertEqual(first, second)
        self.assertEqual(extract.call_count, 1, "replay audio should be extracted once")
        self.assertEqual(first_match_calls, 3)
        self.assertEqual(matcher.call_count, first_match_calls,
                         "cached timeline should skip all repeat correlations")
        self.assertEqual([event["event"] for event in first],
                         ["hero_killed", "ping_attack_enemy"])
        self.assertEqual(first[1]["usage"], "intent")
        self.assertAlmostEqual(first[0]["ts"], 1.0, delta=0.06)

    def test_death_relationships_respect_time_direction_and_identity(self):
        events = [
            {"ts": 92.0, "event": "kill_streak_3", "category": "combat",
             "perspective": "enemy", "usage": "evidence"},
            {"ts": 101.1, "event": "multi_kill_2", "category": "combat",
             "perspective": "enemy", "usage": "evidence"},
            {"ts": 105.0, "event": "ping_attack_enemy", "category": "communication",
             "perspective": "allied", "usage": "intent"},
        ]
        related = video_utils.relate_audio_events_to_death(events, 100.0)
        self.assertEqual(related[0]["relationship"], "pre_death_context")
        self.assertEqual(related[1]["relationship"], "possible_direct_relationship")
        self.assertTrue(related[1]["identity_confirmation_required"])
        self.assertEqual(related[2]["relationship"], "team_intent")

    def test_kill_feed_distinguishes_player_from_teammate_multikill_victim(self):
        audio = [{
            "ts": 101.1, "event": "multi_kill_2", "category": "combat",
            "perspective": "enemy", "identity_confirmation_required": True,
        }]
        player = video_utils.corroborate_audio_combat_identity(
            audio, [{"ts": 101.0, "victim_is_player": True,
                     "killer_hero": "妲己"}])
        teammate = video_utils.corroborate_audio_combat_identity(
            audio, [{"ts": 101.0, "victim_is_player": False}])
        unresolved = video_utils.corroborate_audio_combat_identity(audio, [])
        self.assertEqual(player[0]["identity_status"], "confirmed_player_victim")
        self.assertEqual(player[0]["killer_hero"], "妲己")
        self.assertEqual(teammate[0]["identity_status"], "confirmed_teammate_victim")
        self.assertEqual(unresolved[0]["identity_status"], "unresolved")


if __name__ == "__main__":
    unittest.main()
