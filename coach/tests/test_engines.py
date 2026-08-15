# -*- coding: utf-8 -*-
"""阶段2/3引擎测试（标准库unittest，LLM全部mock/不接网）。"""

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import constraints_engine, knowledge_engine, replay_engine, training_engine  # noqa: E402
from core.knowledge_engine import Principle  # noqa: E402
from core.llm_client import LLMClient, extract_json  # noqa: E402
from utils import config_utils, data_utils, video_utils  # noqa: E402

try:
    import cv2  # type: ignore
    import numpy as np  # type: ignore
    _HAS_CV2 = True
except ImportError:
    _HAS_CV2 = False

_HAS_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


# ---------------------------------------------------------------------------
# config_utils
# ---------------------------------------------------------------------------

class TestMiniYaml(unittest.TestCase):
    def test_parses_project_config_without_pyyaml(self):
        text = config_utils.CONFIG_PATH.read_text(encoding="utf-8")
        cfg = config_utils._mini_yaml(text)
        self.assertEqual(cfg["llm"]["api_key_env"], "COACH_LLM_API_KEY")
        self.assertEqual(cfg["llm"]["vision"]["model"], "qwen3-vl-plus")
        self.assertEqual(cfg["video"]["coarse_interval_sec"], 75)
        self.assertFalse(cfg["voice"]["enabled"])

    def test_parses_persona_lists(self):
        text = config_utils.PERSONA_PATH.read_text(encoding="utf-8")
        cfg = config_utils._mini_yaml(text)
        self.assertIn("老娘", cfg["persona"]["style_reference"])
        self.assertTrue(any("如果-那么" in p for p in cfg["persona"]["principles"]))


# ---------------------------------------------------------------------------
# llm_client.extract_json
# ---------------------------------------------------------------------------

class TestExtractJson(unittest.TestCase):
    def test_plain_and_fenced(self):
        self.assertEqual(extract_json('{"a": 1}'), {"a": 1})
        self.assertEqual(extract_json('```json\n[1, 2, 3]\n```'), [1, 2, 3])
        self.assertEqual(
            extract_json('好的，结果是：{"type": "探草死", "confidence": 0.8} 以上'),
            {"type": "探草死", "confidence": 0.8})

    def test_invalid_raises(self):
        with self.assertRaises(ValueError):
            extract_json("完全没有json")

    def test_from_config_none_without_key(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            self.assertIsNone(LLMClient.from_config(
                {"llm": {"base_url": "x", "model": "y",
                         "api_key_env": "NOPE_KEY"}}))

    def test_from_config_with_key(self):
        with mock.patch.dict("os.environ", {"K": "sk-test"}):
            c = LLMClient.from_config(
                {"llm": {"base_url": "https://api.x.com/v1/", "model": "m",
                         "api_key_env": "K"}})
            self.assertIsNotNone(c)
            self.assertEqual(c.base_url, "https://api.x.com/v1")


# ---------------------------------------------------------------------------
# knowledge_engine
# ---------------------------------------------------------------------------

_KB_MD = """# 测试库

- **[vision_001]** 打野消失超过15秒，过未插眼草丛前应假设其在附近
  - tier: 2_converged_consensus
  - tags: 探草死, 视野
  - source: 测试源A, 测试源B
  - valid_as_of_patch: 3.85

- **[style_001]** 一级必须反野
  - tier: 3_contested_style
  - tags: 探草死
  - source: 某主播

- **[lane_001]** 兵线劣势时不接对拼，一换一也亏
  - tier: 2_converged_consensus
  - source: 测试源C
"""


class TestKnowledgeEngine(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        kb = Path(self._tmp.name)
        (kb / "macro_principles.md").write_text(_KB_MD, encoding="utf-8")
        (kb / "hero_mechanics.json").write_text(
            '{"entries": [{"id": "hero_001", "text": "兰陵王隐身持续时间为固定值",'
            '"tier": "1_mechanical_fact", "tags": ["机制死"], "source": ["官方"],'
            '"valid_as_of_patch": "3.85"}]}', encoding="utf-8")
        self.kb = kb

    def tearDown(self):
        self._tmp.cleanup()

    def test_load_filters_tier3(self):
        entries = knowledge_engine.load_all_principles(self.kb)
        ids = {e.id for e in entries}
        self.assertIn("vision_001", ids)
        self.assertIn("hero_001", ids)
        self.assertNotIn("style_001", ids, "tier 3必须被过滤（4.5.2硬规则）")

    def test_retrieve_by_tag_and_keyword(self):
        entries = knowledge_engine.load_all_principles(self.kb)
        got = knowledge_engine.retrieve_principles("探草死", principles=entries)
        self.assertEqual(got[0].id, "vision_001")  # 显式tag优先
        got2 = knowledge_engine.retrieve_principles("换头死", principles=entries)
        self.assertIn("lane_001", [p.id for p in got2])  # 关键词"一换一/兵线"命中

    def test_retrieve_empty_is_honest(self):
        txt = knowledge_engine.format_principles([])
        self.assertIn("证据不足", txt)

    def test_parse_fields(self):
        entries = {e.id: e for e in knowledge_engine.load_all_principles(self.kb)}
        v = entries["vision_001"]
        self.assertEqual(v.tags, ["探草死", "视野"])
        self.assertEqual(v.valid_as_of_patch, "3.85")


# ---------------------------------------------------------------------------
# constraints_engine
# ---------------------------------------------------------------------------

class TestConstraintsEngine(unittest.TestCase):
    def test_latency_incompatible(self):
        p = Principle(id="x", text="看到就闪", requires_capability="反应时间<150ms")
        res = constraints_engine.check_compatibility(
            [p], {"network_latency_ms": 200})
        self.assertFalse(res[0]["compatible"])
        self.assertIn("补偿", res[0]["note"])

    def test_no_constraints_compatible(self):
        p = Principle(id="x", text="看到就闪", requires_capability="反应时间<150ms")
        res = constraints_engine.check_compatibility([p], {})
        self.assertTrue(res[0]["compatible"])

    def test_format_constraints_empty(self):
        self.assertIn("未提供", constraints_engine.format_constraints({}))

    def test_detect_fixed_constraint(self):
        entry = {  # 3周执行率达标但level不动 → 固定约束
            "weeks_trained": 3,
            "execution_history": [0.85, 0.9, 0.85],
            "level_history": [0.5, 0.5, 0.5, 0.51],
        }
        self.assertTrue(constraints_engine.detect_fixed_constraint(entry))
        # 执行率不达标 → 是执行问题，不是固定约束
        entry2 = dict(entry, execution_history=[0.4, 0.9, 0.85])
        self.assertFalse(constraints_engine.detect_fixed_constraint(entry2))
        # level在涨 → 正常训练中
        entry3 = dict(entry, level_history=[0.3, 0.4, 0.5, 0.6])
        self.assertFalse(constraints_engine.detect_fixed_constraint(entry3))


# ---------------------------------------------------------------------------
# replay_engine
# ---------------------------------------------------------------------------

class TestReplayEngine(unittest.TestCase):
    def test_rule_priority(self):
        # 4.1.2优先级：探草 > 掉点 > 换头 > 贪线
        r = replay_engine.classify_death(
            {"near_brush": True, "kill_traded": True})
        self.assertEqual(r["type"], "探草死")
        r = replay_engine.classify_death({"kill_traded": True})
        self.assertEqual(r["type"], "换头死")

    def test_self_attribution_keywords(self):
        r = replay_engine.classify_death({"self_attribution": "贪了一波兵线被抓"})
        self.assertEqual(r["type"], "贪线死")
        r = replay_engine.classify_death({"self_attribution": "队友都走了我一个人在塔下"})
        self.assertEqual(r["type"], "掉点死")

    def test_insufficient_evidence(self):
        r = replay_engine.classify_death({})
        self.assertEqual(r["type"], "机制死")
        self.assertFalse(r["evidence_sufficient"])

    def test_format_ts(self):
        self.assertEqual(replay_engine.format_ts(392), "6:32")
        self.assertEqual(replay_engine.format_ts(None), "?")

    def test_format_death_location_prioritizes_x_marker(self):
        # AGE-46: 系统X标记应明确标注为高可靠度，与推断值区分开
        marker_text = replay_engine._format_death_location(
            {"death_location": "河道草丛", "death_location_source": "minimap_x_marker"})
        self.assertIn("河道草丛", marker_text)
        self.assertIn("高可靠度", marker_text)

        inferred_text = replay_engine._format_death_location(
            {"death_location": "河道草丛", "death_location_source": None})
        self.assertIn("推断值", inferred_text)

        unknown_text = replay_engine._format_death_location({})
        self.assertIn("未知", unknown_text)

    def test_build_replay_from_video_carries_location_source(self):
        events = [{"ts": 30.0, "location": "河道草丛",
                   "location_source": "minimap_x_marker", "kill_traded": False}]
        replay = replay_engine.build_replay_from_video(
            "dummy.mp4", events, [None], llm=None)
        detail = replay["death_analysis"]["details"][0]
        self.assertEqual(detail["location"], "河道草丛")
        self.assertEqual(detail["location_source"], "minimap_x_marker")

    def test_classify_manual_replay(self):
        replay = data_utils.default_replay("瑶")
        replay["deaths"] = 1
        replay["death_analysis"]["total"] = 1
        replay["death_analysis"]["details"].append({
            "timestamp": "6:32", "type": None, "location": "河道草丛",
            "self_attribution": "脸探草被蹲了", "ai_comment": None,
        })
        out = replay_engine.classify_manual_replay(replay, llm=None)
        self.assertEqual(out["death_analysis"]["details"][0]["type"], "探草死")
        self.assertEqual(out["death_analysis"]["categories"]["探草死"], 1)


# ---------------------------------------------------------------------------
# video_utils: 死亡"X"标记检测 (AGE-46)
# ---------------------------------------------------------------------------

@unittest.skipUnless(_HAS_CV2, "需要 opencv-python + numpy")
class TestDeathMarkerDetection(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _write(self, name: str, img) -> Path:
        p = self.dir / name
        cv2.imwrite(str(p), img)
        return p

    def test_x_marker_detected_hero_icon_ignored(self):
        img = np.zeros((320, 420, 3), dtype=np.uint8)
        # 实心圆形英雄头像（红环敌方）：extent高，不应被识别为死亡标记
        cv2.circle(img, (100, 100), 15, (0, 0, 255), -1)
        # 死亡"X"标记：两条交叉细线，extent低
        cv2.line(img, (250, 150), (280, 180), (0, 0, 255), 3)
        cv2.line(img, (250, 180), (280, 150), (0, 0, 255), 3)
        frame = self._write("mixed.png", img)

        marker = video_utils.detect_death_marker(frame)
        self.assertIsNotNone(marker)
        self.assertLess(marker["extent"], video_utils._MARKER_MAX_EXTENT)
        # 命中的应该是X（靠近250,150-280,180），不是圆形图标（100,100附近）
        self.assertGreater(marker["cx"], 200)

        icons = video_utils.detect_hero_icons(frame)
        self.assertEqual(len(icons["enemies"]), 2)  # 圆形+X都落入红色连通域

    def test_no_marker_returns_none(self):
        img = np.zeros((320, 420, 3), dtype=np.uint8)
        cv2.circle(img, (100, 100), 15, (0, 0, 255), -1)  # 只有实心图标，没有X
        frame = self._write("no_marker.png", img)
        self.assertIsNone(video_utils.detect_death_marker(frame))

    def test_empty_frame_returns_none(self):
        img = np.zeros((320, 420, 3), dtype=np.uint8)
        frame = self._write("empty.png", img)
        self.assertIsNone(video_utils.detect_death_marker(frame))


@unittest.skipUnless(_HAS_CV2 and _HAS_FFMPEG, "需要 opencv-python + numpy + ffmpeg")
class TestExtractDeathLocation(unittest.TestCase):
    """端到端：合成一个短视频（前2秒无标记，之后出现X），验证向后搜索定位。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

        blank = np.zeros((320, 420, 3), dtype=np.uint8)
        marked = np.zeros((320, 420, 3), dtype=np.uint8)
        cv2.line(marked, (60, 60), (90, 90), (0, 0, 255), 4)
        cv2.line(marked, (60, 90), (90, 60), (0, 0, 255), 4)
        f0, f1 = self.dir / "f0.png", self.dir / "f1.png"
        cv2.imwrite(str(f0), blank)
        cv2.imwrite(str(f1), marked)

        self.video = self.dir / "clip.mp4"
        subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
             "-loop", "1", "-t", "2", "-i", str(f0),
             "-loop", "1", "-t", "3", "-i", str(f1),
             "-filter_complex",
             "[0:v][1:v]concat=n=2:v=1:a=0,fps=5[v]", "-map", "[v]",
             str(self.video)],
            check=True,
        )

    def tearDown(self):
        self._tmp.cleanup()

    def test_finds_marker_after_death_ts(self):
        result = video_utils.extract_death_location(
            str(self.video), death_ts=0.0, search_window=4.0,
            sample_interval=1.0)
        self.assertIsNotNone(result)
        self.assertEqual(result["source"], "minimap_x_marker")
        self.assertGreaterEqual(result["ts_offset"], 1.0)  # 出现在黑屏2秒之后

    def test_returns_none_when_outside_window(self):
        result = video_utils.extract_death_location(
            str(self.video), death_ts=0.0, search_window=0.5,
            sample_interval=1.0)
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# training_engine
# ---------------------------------------------------------------------------

class TestTrainingEngine(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        tmp = Path(self._tmp.name)
        self._patches = [
            mock.patch.object(data_utils, "DATA_DIR", tmp),
            mock.patch.object(data_utils, "REPLAYS_DIR", tmp / "replays"),
            mock.patch.object(data_utils, "PLAYER_PROFILE_PATH", tmp / "p.json"),
            mock.patch.object(data_utils, "WEEKLY_TRAINING_PATH", tmp / "w.json"),
            mock.patch.object(data_utils, "PROGRESS_PATH", tmp / "pr.json"),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()
        self._tmp.cleanup()

    def test_weekly_assessment_branches(self):
        wa = training_engine.weekly_assessment
        self.assertEqual(wa({"habit_execution_rate": 0.9})[0], "advance")
        self.assertEqual(
            wa({"habit_execution_rate": 0.3, "weeks_on_current_task": 3})[0],
            "change_method")
        self.assertEqual(
            wa({"habit_execution_rate": 0.6, "execution_rate_last_week": 0.4,
                "rank": 1300, "last_week_rank": 1330})[0],
            "encourage")
        self.assertEqual(wa({"habit_execution_rate": 0.6})[0], "continue")

    def test_weekly_assessment_compensate_first(self):
        # 固定约束优先于advance：执行率高但多周指标不动
        wd = {
            "habit_execution_rate": 0.9,
            "weakness_entry": {
                "weeks_trained": 3,
                "execution_history": [0.85, 0.9, 0.9],
                "level_history": [0.5, 0.5, 0.5, 0.5],
            },
        }
        self.assertEqual(training_engine.weekly_assessment(wd)[0], "compensate")

    def test_task_templates_valid(self):
        for w in training_engine.WEAKNESS_ORDER:
            t = training_engine.generate_task(w)
            self.assertLessEqual(len(t["description"]), 20)
            self.assertIn("checkin_method", t)
            self.assertEqual(t["status"], "in_progress")

    def test_pick_next_weakness_from_replays(self):
        progress = data_utils.default_progress()
        replays = [{"death_analysis": {"categories": {"贪线死": 3, "探草死": 1}}}]
        self.assertEqual(
            training_engine.pick_next_weakness(progress, replays), "优势期决策")
        # 无复盘数据 → 基础→进阶顺序
        self.assertEqual(
            training_engine.pick_next_weakness(progress, []), "探草意识")

    def test_checkin_and_streak(self):
        training_engine.assign_task_for_week()
        week = training_engine.checkin(rate=90, when="2026-08-10")
        week = training_engine.checkin(rate=85, when="2026-08-11")
        self.assertEqual(week["task"]["current_streak"], 2)
        week = training_engine.checkin(rate=40, when="2026-08-12")
        self.assertEqual(week["task"]["current_streak"], 0)
        # 同日覆盖：失败日改为达标后，三天连续达标
        week = training_engine.checkin(rate=95, when="2026-08-12")
        self.assertEqual(week["task"]["current_streak"], 3)
        self.assertEqual(len(week["daily_checkins"]), 3)
        self.assertAlmostEqual(
            training_engine.week_execution_rate(week), (90 + 85 + 95) / 300)

    def test_checkin_validation(self):
        training_engine.assign_task_for_week()
        with self.assertRaises(ValueError):
            training_engine.checkin(rate=90, when="08-10")
        with self.assertRaises(ValueError):
            training_engine.checkin(rate=150)

    def test_finalize_week_updates_tracker(self):
        training_engine.assign_task_for_week(weakness="探草意识")
        training_engine.checkin(rate=90)
        wd = training_engine.collect_week_data()
        training_engine.finalize_week(wd, "advance")
        progress = data_utils.load_progress()
        entry = progress["weakness_tracker"]["探草意识"]
        self.assertEqual(entry["status"], "done")
        self.assertEqual(entry["weeks_trained"], 1)
        self.assertEqual(len(progress["weekly_snapshots"]), 1)

    def test_ascii_chart(self):
        chart = training_engine.ascii_chart([50, 100], ["W1", "W2"], width=10)
        self.assertIn("█" * 10, chart)
        self.assertIn("W1", chart)

    def test_render_progress_smoke(self):
        out = training_engine.render_progress(detail=True, chart=True)
        self.assertIn("弱点追踪", out)


if __name__ == "__main__":
    unittest.main()
