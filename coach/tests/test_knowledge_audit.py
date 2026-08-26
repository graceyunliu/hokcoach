from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.audit_knowledge_base import build_report, main, render_text


class TestKnowledgeBaseAudit(unittest.TestCase):
    def _fixture_dir(self, *, translated: bool) -> Path:
        tmp = Path(tempfile.mkdtemp())
        (tmp / "macro_principles.md").write_text(
            """- **[vision_001]** 打野消失后，经过未插眼草丛前应假设其可能在附近
  - tier: 2_converged_consensus
  - tags: 探草死, 视野
  - text_en: Assume the jungler may be nearby before crossing an unwarded bush after they disappear.
""" if translated else """- **[vision_001]** 打野消失后，经过未插眼草丛前应假设其可能在附近
  - tier: 2_converged_consensus
  - tags: 探草死, 视野
""", encoding="utf-8"
        )
        (tmp / "map_mechanics.md").write_text("", encoding="utf-8")
        (tmp / "hero_mechanics.json").write_text('{"entries": []}', encoding="utf-8")
        return tmp

    def test_report_identifies_missing_human_reviewed_translation(self):
        report = build_report(self._fixture_dir(translated=False))
        self.assertEqual(report["total_loaded"], 1)
        self.assertEqual(report["english_translated"], 0)
        self.assertEqual(report["missing_english_ids"], ["vision_001"])
        self.assertEqual(report["english_coverage"], 0.0)

    def test_report_counts_translated_entry(self):
        report = build_report(self._fixture_dir(translated=True))
        self.assertEqual(report["english_coverage"], 1.0)
        self.assertEqual(report["missing_english_ids"], [])
        self.assertIn("English coverage: 1/1 (100.0%)", render_text(report))

    def test_json_output_and_strict_mode(self):
        untranslated = self._fixture_dir(translated=False)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = main(["--knowledge-dir", str(untranslated), "--json", "--strict-en"])
        self.assertEqual(result, 1)
        self.assertEqual(json.loads(output.getvalue())["missing_english_ids"], ["vision_001"])

        translated = self._fixture_dir(translated=True)
        self.assertEqual(main(["--knowledge-dir", str(translated), "--strict-en"]), 0)
        # Ensure the JSON mode remains parseable for CI consumers.
        report = build_report(translated)
        self.assertEqual(json.loads(json.dumps(report))["total_loaded"], 1)


if __name__ == "__main__":
    unittest.main()
