# -*- coding: utf-8 -*-
"""AGE-136：确定性KDA模板读数器。"""

import tempfile
import sys
import unittest
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


if __name__ == "__main__":
    unittest.main()
