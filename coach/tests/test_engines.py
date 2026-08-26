# -*- coding: utf-8 -*-
"""阶段2/3引擎测试（标准库unittest，LLM全部mock/不接网）。"""

import contextlib
import io
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
        # 2026-08-21：默认从vlm切到template（真实录屏上VLM对同一帧偶发"读不出来"，
        # 见config.yaml video段注释和orchestrator.py的kda_read_warning机制）
        self.assertEqual(cfg["video"]["kda_reader"], "template")
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

    def test_from_config_none_logs_warning(self):
        # AGE-244: 配置缺失时from_config()返回None不应静默——必须打warning日志，
        # 且日志内容要点出具体缺失哪个字段(api_key)和对应的环境变量名(NOPE_KEY)，
        # 而不是只说"配置不完整"。
        with mock.patch.dict("os.environ", {}, clear=True):
            with self.assertLogs(level="WARNING") as cm:
                result = LLMClient.from_config(
                    {"llm": {"base_url": "x", "model": "y",
                             "api_key_env": "NOPE_KEY"}})
        self.assertIsNone(result)
        joined = "\n".join(cm.output)
        self.assertIn("api_key", joined)
        self.assertIn("NOPE_KEY", joined)

    def test_from_config_with_key_no_warning(self):
        # 正常配置时不应触发这条警告日志（避免正常路径也刷屏）。
        with mock.patch.dict("os.environ", {"K": "sk-test"}):
            with self.assertRaises(AssertionError):
                # assertNoLogs不是所有Python版本都有，这里用assertLogs必然
                # 抛AssertionError（因为没有日志产生）来间接断言"没有warning"。
                with self.assertLogs(level="WARNING"):
                    LLMClient.from_config(
                        {"llm": {"base_url": "https://api.x.com/v1/", "model": "m",
                                 "api_key_env": "K"}})

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

    def test_solo_in_enemy_half_classifies_as_isolation(self):
        r = replay_engine.classify_death({"solo_in_enemy_half": True})
        self.assertEqual(r["type"], "掉点死")

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
                   "location_source": "minimap_x_marker", "kill_traded": False,
                   "solo_in_enemy_half": True}]
        replay = replay_engine.build_replay_from_video(
            "dummy.mp4", events, [None], llm=None)
        detail = replay["death_analysis"]["details"][0]
        self.assertEqual(detail["location"], "河道草丛")
        self.assertEqual(detail["location_source"], "minimap_x_marker")
        self.assertTrue(detail["solo_in_enemy_half"])
        self.assertEqual(detail["type"], "掉点死")

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


@unittest.skipUnless(_HAS_CV2, "需要 opencv-python + numpy")
class TestHudFrameHopper(unittest.TestCase):
    SLOTS = ((0, 0, 10, 10), (10, 0, 20, 10), (20, 0, 30, 10))

    def _write(self, directory: str, name: str, values: tuple[int, int, int]) -> Path:
        image = np.zeros((10, 30), dtype=np.uint8)
        for i, value in enumerate(values):
            image[:, i * 10:(i + 1) * 10] = value
        path = Path(directory) / name
        cv2.imwrite(str(path), image)
        return path

    def test_unchanged_slots_reuse_previous_result(self):
        calls = []
        reader = lambda path: calls.append(path) or (1, 2, 3)
        hopper = video_utils._HudFrameHopper(reader, threshold=1.0, slots=self.SLOTS)
        with tempfile.TemporaryDirectory() as tmp:
            first = self._write(tmp, "first.png", (10, 20, 30))
            second = self._write(tmp, "second.png", (10, 20, 30))
            self.assertEqual(hopper.read(first), (1, 2, 3))
            self.assertEqual(hopper.read(second), (1, 2, 3))
        self.assertEqual(len(calls), 1)
        self.assertEqual((hopper.stats.processed, hopper.stats.skipped), (1, 1))

    def test_suspected_kda_change_forces_full_processing(self):
        calls = []
        reader = lambda path: calls.append(path) or (0, len(calls) - 1, 0)
        hopper = video_utils._HudFrameHopper(reader, threshold=1.0, slots=self.SLOTS)
        with tempfile.TemporaryDirectory() as tmp:
            first = self._write(tmp, "first.png", (10, 20, 30))
            changed = self._write(tmp, "changed.png", (10, 22, 30))
            self.assertEqual(hopper.read(first), (0, 0, 0))
            self.assertEqual(hopper.read(changed), (0, 1, 0))
        self.assertEqual(len(calls), 2)
        self.assertEqual((hopper.stats.processed, hopper.stats.skipped), (2, 0))

    def test_boundary_difference_is_reused(self):
        calls = []
        reader = lambda path: calls.append(path) or (1, 0, 0)
        hopper = video_utils._HudFrameHopper(reader, threshold=1.0, slots=self.SLOTS)
        with tempfile.TemporaryDirectory() as tmp:
            first = self._write(tmp, "first.png", (10, 20, 30))
            boundary = self._write(tmp, "boundary.png", (11, 21, 31))
            hopper.read(first)
            hopper.read(boundary)
        self.assertEqual(len(calls), 1)
        self.assertEqual(hopper.stats.skipped, 1)


class TestCoarseFrameSkipStride(unittest.TestCase):
    @staticmethod
    def _reader(path: Path):
        ts = float(path.stem.removeprefix("hud_"))
        return (0, int(ts >= 25.0) + int(ts >= 45.0), 0)

    def _extract(self, stride=None):
        kwargs = {} if stride is None else {"frame_skip_stride": stride}
        decoded = []

        def fake_grab(video_path, ts, out_path, crop):
            decoded.append(ts)
            return out_path

        with (mock.patch.object(video_utils, "video_duration", return_value=61.0),
              mock.patch.object(video_utils, "grab_hud_frame", side_effect=fake_grab),
              mock.patch.object(video_utils, "_load_video_config", return_value={})):
            events = video_utils.extract_death_events(
                "fixture.mp4", self._reader, coarse_interval=10.0,
                precision=1.0, **kwargs)
        return events, decoded

    def test_stride_one_is_byte_identical_to_no_skip_path(self):
        baseline, baseline_decodes = self._extract()
        stride_one, stride_one_decodes = self._extract(1)
        self.assertEqual(repr(stride_one).encode(), repr(baseline).encode())
        self.assertEqual(stride_one_decodes, baseline_decodes)

    def test_stride_skips_coarse_decodes_but_keeps_death_count(self):
        baseline, baseline_decodes = self._extract(1)
        skipped, skipped_decodes = self._extract(3)
        self.assertEqual(len(skipped), len(baseline))
        self.assertLess(len(skipped_decodes), len(baseline_decodes))
        # Refinement points are intentionally not stride-filtered.
        self.assertIn(15.0, skipped_decodes)


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


def _x_marker(img, cx: int, cy: int, r: int = 15, thickness: int = 4):
    """在img上画一个死亡"X"标记（低extent的红色交叉笔画）。"""
    cv2.line(img, (cx - r, cy - r), (cx + r, cy + r), (0, 0, 255), thickness)
    cv2.line(img, (cx - r, cy + r), (cx + r, cy - r), (0, 0, 255), thickness)
    return img


def _build_clip(out_path: Path, segments: list[tuple[Path, float]]) -> Path:
    """把[(静帧png, 时长秒), ...]拼成一段mp4。

    -g 1 让每帧都是关键帧：extract_death_location用的是 -ss 前置快速seek，
    只有全关键帧才能保证取到的确实是该时刻的画面，否则时间边界上的断言会
    随GOP对齐随机漂移。
    """
    inputs: list[str] = []
    for png, dur in segments:
        inputs += ["-loop", "1", "-t", f"{dur}", "-i", str(png)]
    chain = "".join(f"[{i}:v]" for i in range(len(segments)))
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *inputs,
         "-filter_complex", f"{chain}concat=n={len(segments)}:v=1:a=0,fps=5[v]",
         "-map", "[v]", "-g", "1", str(out_path)],
        check=True,
    )
    return out_path


class TestDeathLocationAnchorGate(unittest.TestCase):
    """AGE-131方案1：无锚点扫描必须显式opt-in，不能是默认路径。

    不需要opencv/ffmpeg——参数校验发生在任何解码之前。
    """

    def test_missing_death_window_raises(self):
        with self.assertRaises(ValueError) as ctx:
            video_utils.extract_death_location("/nonexistent.mp4", death_ts=10.0)
        self.assertIn("allow_unanchored", str(ctx.exception))

    def test_unanchored_requires_explicit_optin(self):
        # 显式opt-in后才会往下走（这里必然因为视频不存在而失败，
        # 但失败点已经不是参数校验了——证明门禁只拦默认路径）。
        with self.assertRaises(Exception) as ctx:
            video_utils.extract_death_location(
                "/nonexistent.mp4", death_ts=10.0, allow_unanchored=True)
        self.assertNotIsInstance(ctx.exception, ValueError)


class TestOrchestratorDeathWindowWiring(unittest.TestCase):
    """生产路径（orchestrator.analyze_video）必须把counter窗口原样传下来。

    这里跑的是真实调用而不是源码文本grep：grep断言在"调用被注释掉/整段
    被跳过"时同样会通过，等于没测。
    """

    def test_analyze_video_passes_counter_window(self):
        from core.orchestrator import Orchestrator

        event = {"ts": 42.0, "window": (40.0, 44.0), "kda_before": (1, 0, 2),
                 "kda_after": (1, 1, 2), "kill_traded": False}
        captured = {}

        def fake_locate(video_path, death_ts, **kwargs):
            captured["video_path"] = video_path
            captured["death_ts"] = death_ts
            captured["kwargs"] = kwargs
            return None

        orch = Orchestrator()
        orch.llm = None          # 不接网：走降级点评
        orch.vlm = mock.Mock()   # 非None即可，kda_reader整个被mock掉

        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / "clip.mp4"
            video.write_bytes(b"")
            with mock.patch.object(video_utils, "make_vlm_kda_reader",
                                   return_value=lambda p: None), \
                 mock.patch.object(video_utils, "extract_death_events",
                                   return_value=[event]), \
                 mock.patch.object(video_utils, "extract_minimap_positions",
                                   return_value=[]), \
                 mock.patch.object(video_utils, "extract_death_location",
                                   side_effect=fake_locate), \
                 mock.patch.object(Orchestrator, "review_replay",
                                   lambda self, replay, **kw: replay), \
                 contextlib.redirect_stdout(io.StringIO()):
                rc = orch.analyze_video(str(video), interactive=False)

        self.assertEqual(rc, 0)
        self.assertIn("kwargs", captured, "extract_death_location 根本没被调用")
        self.assertEqual(captured["death_ts"], event["ts"])
        self.assertEqual(captured["kwargs"]["death_window"], (40.0, 44.0))
        # 生产路径不得走无锚点扫描（AGE-131误报的来源）
        self.assertNotIn("allow_unanchored", captured["kwargs"])

    def test_template_reader_does_not_require_vlm(self):
        from core.orchestrator import Orchestrator

        orch = Orchestrator()
        orch.llm = None
        orch.vlm = None
        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / "clip.mp4"
            video.write_bytes(b"")
            with mock.patch.object(video_utils, "_load_video_config",
                                   return_value={"kda_reader": "template"}), \
                 mock.patch.object(video_utils, "make_template_kda_reader",
                                   return_value=lambda p: None) as factory, \
                 mock.patch.object(video_utils, "extract_death_events",
                                   return_value=[]), \
                 mock.patch.object(Orchestrator, "review_replay",
                                   lambda self, replay, **kw: replay), \
                 contextlib.redirect_stdout(io.StringIO()):
                rc = orch.analyze_video(str(video), interactive=False)

        self.assertEqual(rc, 0)
        factory.assert_called_once_with()


class TestOrchestratorVideoPipelineExtraction(unittest.TestCase):
    """AGE-178准备工作：build_replay_from_video_path必须是纯数据管线（不print、
    不生成AI点评、不落盘），CLI和未来的FastAPI后台任务才能共用同一份实现。"""

    def test_missing_video_raises_orchestrator_error(self):
        from core.orchestrator import Orchestrator, OrchestratorError

        orch = Orchestrator()
        with self.assertRaises(OrchestratorError):
            orch.build_replay_from_video_path("/nonexistent/clip.mp4")

    def test_progress_cb_called_without_printing(self):
        from core.orchestrator import Orchestrator

        event = {"ts": 10.0, "window": (8.0, 12.0), "kda_before": (0, 0, 0),
                 "kda_after": (0, 1, 0), "kill_traded": False}
        orch = Orchestrator()
        orch.llm = None
        orch.vlm = mock.Mock()
        stages: list[str] = []

        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / "clip.mp4"
            video.write_bytes(b"")
            with mock.patch.object(video_utils, "make_vlm_kda_reader",
                                   return_value=lambda p: None), \
                 mock.patch.object(video_utils, "extract_death_events",
                                   return_value=[event]), \
                 mock.patch.object(video_utils, "extract_minimap_positions",
                                   return_value=[]), \
                 mock.patch.object(video_utils, "extract_death_location",
                                   return_value=None), \
                 contextlib.redirect_stdout(io.StringIO()) as buf:
                replay = orch.build_replay_from_video_path(
                    str(video), progress_cb=stages.append)

        self.assertEqual(replay["deaths"], 1)
        self.assertTrue(stages, "progress_cb从没被调用")
        self.assertEqual(buf.getvalue(), "", "纯数据管线不应该自己print")

    def test_real_solo_signal_is_wired_into_replay(self):
        """AGE-236: production extraction must calculate, not merely preserve, it."""
        from core.orchestrator import Orchestrator

        event = {"ts": 10.0, "window": (8.0, 12.0), "kda_before": (0, 0, 0),
                 "kda_after": (0, 1, 0), "kill_traded": False}
        player = {"cx": 300.0, "cy": 20.0, "player_marker": True}
        positions = [{"ts": 9.0, "player": player, "allies": [player],
                      "enemies": [], "enemy_visible_count": 0,
                      "ally_visible_count": 1}]
        orch = Orchestrator()
        orch.llm = None
        orch.vlm = None

        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / "clip.mp4"
            video.write_bytes(b"")
            with mock.patch.object(video_utils, "_load_video_config", return_value={
                    "kda_reader": "template", "ally_isolation_distance_px": 90,
                    "minimap_pixels_per_world_unit": None,
                    "hero_max_move_speed_world_units_sec": None,
                 }), \
                 mock.patch.object(video_utils, "make_template_kda_reader",
                                   return_value=lambda p: None), \
                 mock.patch.object(video_utils, "extract_death_events",
                                   return_value=[event]), \
                 mock.patch.object(video_utils, "extract_minimap_positions",
                                   return_value=positions), \
                 mock.patch.object(video_utils, "extract_death_location",
                                   return_value=None):
                replay = orch.build_replay_from_video_path(str(video))

        detail = replay["death_analysis"]["details"][0]
        self.assertTrue(detail["solo_in_enemy_half"])
        self.assertEqual(detail["type"], "掉点死")

    def test_low_kda_read_coverage_adds_replay_warning(self):
        """AGE-187：少于一半HUD采样可读时，结果必须显式标为不可信。"""
        from core.orchestrator import Orchestrator

        orch = Orchestrator()
        orch.llm = None
        orch.vlm = None

        def low_coverage_events(video_path, reader, coverage_cb=None):
            self.assertIsNotNone(coverage_cb)
            coverage_cb(2, 5)
            return []

        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / "clip.mp4"
            video.write_bytes(b"")
            with mock.patch.object(video_utils, "_load_video_config",
                                   return_value={"kda_reader": "template"}), \
                 mock.patch.object(video_utils, "make_template_kda_reader",
                                   return_value=lambda p: None), \
                 mock.patch.object(video_utils, "extract_death_events",
                                   side_effect=low_coverage_events):
                replay = orch.build_replay_from_video_path(str(video))

        warning = replay["death_analysis"].get("kda_read_warning", "")
        self.assertIn("2/5", warning)
        self.assertIn("40%", warning)
        self.assertIn("可能不可信", warning)


class TestOrchestratorStructuredReview(unittest.TestCase):
    """AGE-177：review_replay拆成的两段函数必须在无stdin/无终端环境下可直接
    调用并返回结构化结果——这是FastAPI层能接进来的前提，不能是CLI专属。"""

    def _replay_with_deaths(self, n: int) -> dict:
        replay = data_utils.default_replay(hero_played="瑶")
        replay["deaths"] = n
        replay["death_analysis"]["details"] = [
            {"timestamp": f"{i}:00", "type": "探草死", "location": "中路草",
             "location_source": None, "classify_reason": "test",
             "evidence_sufficient": True, "confidence": 0.6}
            for i in range(n)
        ]
        return replay

    def test_analyze_first_death_no_llm_call_and_no_stdin(self):
        from core.orchestrator import Orchestrator

        orch = Orchestrator()
        orch.llm = None
        replay = self._replay_with_deaths(2)

        # 不依赖stdin（EOFError场景下input()会炸，这里的函数干脆不调用input）
        with mock.patch("builtins.input", side_effect=EOFError):
            analysis = orch.analyze_first_death(replay)

        self.assertEqual(analysis["deaths"], 2)
        self.assertIsNotNone(analysis["first_death"])
        self.assertIsNone(analysis["first_death"].get("ai_comment"))
        self.assertEqual(len(analysis["other_deaths"]), 1)

    def test_comment_prompt_includes_bounded_audio_context_with_caveat(self):
        from core.orchestrator import Orchestrator

        orch = Orchestrator()
        orch.llm = mock.Mock()
        orch.llm.chat_text.return_value = "coach output"
        detail = {
            "timestamp": "1:40", "type": "掉点死", "confidence": 0.8,
            "classify_reason": "test", "evidence_sufficient": True,
            "audio_context": [{
                "offset_from_death_sec": 1.1, "event": "multi_kill_2",
                "relationship": "possible_direct_relationship",
                "identity_confirmation_required": True,
            }],
        }
        orch.comment_death(detail, lang="en")
        prompt = orch.llm.chat_text.call_args.kwargs["user"]
        self.assertIn("Audio timeline (corroboration only)", prompt)
        self.assertIn("identity unconfirmed", prompt)

    def test_finalize_review_returns_structured_result_and_saves(self):
        from core.orchestrator import Orchestrator

        orch = Orchestrator()
        orch.llm = None  # 降级模式：走_fallback_comment，不接网
        replay = self._replay_with_deaths(1)
        analysis = orch.analyze_first_death(replay)

        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(data_utils, "REPLAYS_DIR", Path(tmp)):
            result = orch.finalize_review(
                replay, analysis["first_death"], user_intent="去支援")
            self.assertTrue(Path(result["saved_path"]).exists())

        self.assertIsInstance(result["comment"], str)
        self.assertTrue(result["comment"])
        self.assertEqual(
            replay["death_analysis"]["details"][0]["user_intent"], "去支援")
        self.assertIsNone(result["report_path"])
        self.assertEqual(replay["language"], "zh")

    def test_english_comment_uses_native_english_prompt(self):
        """用mock LLM跑真实死亡详情，确认加载en目录且语气指令不是中译英。"""
        from core.orchestrator import Orchestrator

        class FakeLLM:
            def __init__(self):
                self.user = ""

            def chat_text(self, system, user, temperature=0.7):
                self.user = user
                return "The thought in your head should've been: bush first, rotation second."

        orch = Orchestrator()
        orch.llm = FakeLLM()
        detail = self._replay_with_deaths(1)["death_analysis"]["details"][0]
        result = orch.comment_death(detail, user_intent="rotate bot", lang="en")
        self.assertIn("sharp English-speaking MOBA review streamer", orch.llm.user)
        self.assertIn("The thought in your head should've been", result)
        self.assertNotIn("你脑子里应该闪过", orch.llm.user)

    def test_finalize_review_zero_deaths_does_not_crash(self):
        from core.orchestrator import Orchestrator

        orch = Orchestrator()
        orch.llm = None
        replay = self._replay_with_deaths(0)
        analysis = orch.analyze_first_death(replay)
        self.assertIsNone(analysis["first_death"])

        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(data_utils, "REPLAYS_DIR", Path(tmp)):
            result = orch.finalize_review(replay, analysis["first_death"])
            self.assertTrue(Path(result["saved_path"]).exists())

        self.assertIsNone(result["comment"])

    def test_finalize_review_all_comments_every_death(self):
        """视频复盘页（AGE-178后台job）场景：不是对话，用户一次性看完整
        分析，所以全部死亡都要有点评，不能像CLI/--chat那样只讲第一条。"""
        from core.orchestrator import Orchestrator

        orch = Orchestrator()
        orch.llm = None  # 降级模式：走_fallback_comment，不接网
        replay = self._replay_with_deaths(3)

        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(data_utils, "REPLAYS_DIR", Path(tmp)):
            result = orch.finalize_review_all(replay)
            self.assertTrue(Path(result["saved_path"]).exists())

        self.assertEqual(len(result["comments"]), 3)
        for comment in result["comments"]:
            self.assertIsInstance(comment, str)
            self.assertTrue(comment)
        for detail in replay["death_analysis"]["details"]:
            self.assertIsInstance(detail.get("ai_comment"), str)
            self.assertTrue(detail["ai_comment"])

    def test_finalize_review_all_zero_deaths_does_not_crash(self):
        from core.orchestrator import Orchestrator

        orch = Orchestrator()
        orch.llm = None
        replay = self._replay_with_deaths(0)

        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(data_utils, "REPLAYS_DIR", Path(tmp)):
            result = orch.finalize_review_all(replay)
            self.assertTrue(Path(result["saved_path"]).exists())

        self.assertEqual(result["comments"], [])

    def test_review_replay_cli_wrapper_still_prints(self):
        """CLI薄封装向后兼容：终端体验（print输出）不变。"""
        from core.orchestrator import Orchestrator

        orch = Orchestrator()
        orch.llm = None
        replay = self._replay_with_deaths(1)

        buf = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(data_utils, "REPLAYS_DIR", Path(tmp)), \
             contextlib.redirect_stdout(buf):
            orch.review_replay(replay, interactive=False)

        out = buf.getvalue()
        self.assertIn("这局你死了1次", out)
        self.assertIn("复盘记录已保存", out)


@unittest.skipUnless(_HAS_CV2 and _HAS_FFMPEG, "需要 opencv-python + numpy + ffmpeg")
class TestExtractDeathLocation(unittest.TestCase):
    """端到端：合成一个短视频（前2秒无标记，之后出现X），验证向后搜索定位。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

        blank = np.zeros((320, 420, 3), dtype=np.uint8)
        marked = _x_marker(np.zeros((320, 420, 3), dtype=np.uint8), 75, 75)
        f0, f1 = self.dir / "f0.png", self.dir / "f1.png"
        cv2.imwrite(str(f0), blank)
        cv2.imwrite(str(f1), marked)
        self.video = _build_clip(self.dir / "clip.mp4", [(f0, 2), (f1, 3)])

    def tearDown(self):
        self._tmp.cleanup()

    def test_finds_marker_after_death_ts(self):
        result = video_utils.extract_death_location(
            str(self.video), death_ts=0.0, death_window=(0.0, 0.0),
            search_window=4.0, sample_interval=1.0)
        self.assertIsNotNone(result)
        self.assertEqual(result["source"], "minimap_x_marker")
        self.assertGreaterEqual(result["ts_offset"], 1.0)  # 出现在黑屏2秒之后

    def test_returns_none_when_outside_window(self):
        result = video_utils.extract_death_location(
            str(self.video), death_ts=0.0, death_window=(0.0, 0.0),
            search_window=0.5, sample_interval=1.0)
        self.assertIsNone(result)


@unittest.skipUnless(_HAS_CV2 and _HAS_FFMPEG, "需要 opencv-python + numpy + ffmpeg")
class TestDeathLocationWindowedSearch(unittest.TestCase):
    """AGE-131残留误报场景：搜索窗口正好盖住一个长期存在的静态噪点源。

    合成素材复刻真实录屏里那个"整局都在同一位置、且能通过+1秒位置持续性
    复核"的噪点（案例研究里残留的8/62误报源）：它同时出现在死亡前基线帧
    和窗口内，只有死亡前基线排除能把它拦掉。
    """

    NOISE = (350, 40)   # 长期存在的噪点位置（minimap右上，形状同样满足X特征）
    REAL = (100, 240)   # 本次死亡真正的X标记位置

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

        noise_only = _x_marker(np.zeros((320, 420, 3), dtype=np.uint8), *self.NOISE)
        noise_and_real = _x_marker(noise_only.copy(), *self.REAL)
        self.f_noise = self.dir / "noise.png"
        self.f_both = self.dir / "both.png"
        cv2.imwrite(str(self.f_noise), noise_only)
        cv2.imwrite(str(self.f_both), noise_and_real)

    def tearDown(self):
        self._tmp.cleanup()

    def test_static_noise_in_window_is_excluded_by_baseline(self):
        """噪点贯穿全片、真X在死亡后出现：应命中真X而非噪点。"""
        video = _build_clip(self.dir / "hit.mp4",
                            [(self.f_noise, 8), (self.f_both, 4)])
        result = video_utils.extract_death_location(
            str(video), death_ts=8.25, death_window=(8.0, 8.5),
            search_window=3.0, sample_interval=1.0)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result["cx"], self.REAL[0], delta=6)
        self.assertAlmostEqual(result["cy"], self.REAL[1], delta=6)

    def test_window_covering_only_noise_returns_none(self):
        """窗口内只有静态噪点、没有真X：必须返回None，不能把噪点当死亡地点。

        这是原实现在无锚点全扫描下产生44/62误报的那一类候选：它能通过
        +1秒位置持续性复核（因为它确实一直在那儿），只有"死亡前它就已经
        存在"这个证据能否掉它。
        """
        video = _build_clip(self.dir / "noise.mp4", [(self.f_noise, 14)])
        result = video_utils.extract_death_location(
            str(video), death_ts=8.25, death_window=(8.0, 8.5),
            search_window=3.0, sample_interval=1.0)
        self.assertIsNone(result)

    def test_unanchored_scan_still_reports_the_same_noise(self):
        """对照：同一段素材走无锚点路径就会误报——证明锚定是有效那一环，
        也说明为什么无锚点路径不能是默认路径。

        无锚点时基线帧按death_ts往前取，噪点当然也在里面，所以这里选一个
        视频开头的death_ts（前面没有基线可取）来复刻真实全扫描的处境。
        """
        video = _build_clip(self.dir / "noise2.mp4", [(self.f_noise, 8)])
        result = video_utils.extract_death_location(
            str(video), death_ts=0.0, search_window=3.0, sample_interval=1.0,
            allow_unanchored=True)
        self.assertIsNotNone(result)  # 误报：噪点被当成死亡X标记
        self.assertAlmostEqual(result["cx"], self.NOISE[0], delta=6)

    def test_baseline_anchored_before_window_lo_not_midpoint(self):
        """基线必须锚在窗口下界lo之前：真死亡最早可能就发生在lo，窗口较宽
        时按"中点-2秒"取基线会落在死亡之后，把真X自己拉黑。

        搜索则从窗口上界hi开始（见test_search_rejects_pre_death_candidate）：
        X标记至少持续8秒，所以哪怕死亡发生在窗口最左端，hi时它仍在。
        """
        video = _build_clip(self.dir / "wide.mp4",
                            [(self.f_noise, 8), (self.f_both, 8)])
        # counter窗口(8,14)，中点11 → 旧的"中点-2秒"基线会落在10秒（已在
        # 死亡之后，真X已出现）；新实现锚在8秒之前，基线取6/4/2秒。
        result = video_utils.extract_death_location(
            str(video), death_ts=11.0, death_window=(8.0, 14.0),
            search_window=1.0, sample_interval=1.0)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result["cx"], self.REAL[0], delta=6)
        self.assertAlmostEqual(result["cy"], self.REAL[1], delta=6)

    def test_search_rejects_pre_death_candidate(self):
        """AGE-131复查blocker的回归测试：搜索起点必须是hi而不是lo。

        window=(lo, hi] 的语义是 read(lo).deaths < 本次死亡数 <= read(hi)，
        所以**lo是已知的死亡之前**——那一刻画面上任何"像X"的东西按定义都
        不是本次死亡的标记。素材里那个噪点只在[lo, hi)之间出现（持续到能
        通过+1秒位置持续性复核），基线偏移2/4/6秒处和hi之后都没有它，也
        没有任何真实X标记：从lo起搜会把它当成死亡地点采信（修复前的行为），
        从hi起搜则必须返回None。
        """
        blank = self.dir / "blank.png"
        cv2.imwrite(str(blank), np.zeros((320, 420, 3), dtype=np.uint8))
        # [0,8) 空白（基线2/4/6秒全干净）→ [8,10) 只有噪点 → [10,14) 空白
        video = _build_clip(self.dir / "pre_death.mp4",
                            [(blank, 8), (self.f_noise, 2), (blank, 4)])
        result = video_utils.extract_death_location(
            str(video), death_ts=9.25, death_window=(8.0, 10.5),
            search_window=3.0, sample_interval=1.0)
        self.assertIsNone(result)

    def test_multi_frame_baseline_union_catches_jittering_noise(self):
        """基线取_BASELINE_OFFSETS多帧并集（而非单帧）才拦得住抖动噪点。

        素材里的噪点在anchor-2处**不出现**，只出现在anchor-4/anchor-6，且
        两帧之间位置有抖动——旧的单帧基线（只取anchor-2）完全看不到它，
        会在窗口内把它当成本次死亡的X标记（它extent更低，排在真X前面）。
        多帧并集能覆盖到，于是命中的是真X而不是噪点。
        """
        def _frame(*marks):
            img = np.zeros((320, 420, 3), dtype=np.uint8)
            for (cx, cy), r, th in marks:
                _x_marker(img, cx, cy, r=r, thickness=th)
            return img

        noise_a = self.dir / "jit_a.png"    # anchor-6 处的噪点位置
        noise_b = self.dir / "jit_b.png"    # anchor-4 处（抖动了几个像素）
        clean = self.dir / "jit_clean.png"  # anchor-2 处：噪点缺席
        window = self.dir / "jit_window.png"
        # 噪点画得更大更细（extent≈0.22）→ 比真X（≈0.34）排得更前，
        # detect_death_marker会优先选它：没被基线拉黑就一定是误报。
        cv2.imwrite(str(noise_a), _frame(((350, 40), 20, 2)))
        cv2.imwrite(str(noise_b), _frame(((356, 45), 20, 2)))
        cv2.imwrite(str(clean), np.zeros((320, 420, 3), dtype=np.uint8))
        cv2.imwrite(str(window), _frame(((353, 42), 20, 2), (self.REAL, 10, 4)))

        # 时间轴：[0,3) noise_a（含基线2秒？不——见下）……按锚点8秒排布：
        #   [0,3)=noise_a 覆盖 anchor-6=2秒
        #   [3,5)=noise_b 覆盖 anchor-4=4秒
        #   [5,8)=clean   覆盖 anchor-2=6秒（单帧基线就是在这里瞎的）
        #   [8,14)=window 搜索窗口
        video = _build_clip(self.dir / "jitter.mp4",
                            [(noise_a, 3), (noise_b, 2), (clean, 3), (window, 6)])

        # 对照：只用anchor-2那一帧做基线时，命中的是噪点而不是真X
        with mock.patch.object(video_utils, "_BASELINE_OFFSETS", (2.0,)):
            single = video_utils.extract_death_location(
                str(video), death_ts=8.25, death_window=(8.0, 8.5),
                search_window=3.0, sample_interval=1.0)
        self.assertIsNotNone(single)
        self.assertAlmostEqual(single["cx"], 353, delta=6)  # 误报：噪点

        result = video_utils.extract_death_location(
            str(video), death_ts=8.25, death_window=(8.0, 8.5),
            search_window=3.0, sample_interval=1.0)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result["cx"], self.REAL[0], delta=6)
        self.assertAlmostEqual(result["cy"], self.REAL[1], delta=6)

    def test_candidate_at_last_sample_must_still_confirm(self):
        """搜索窗口最后一个采样点上的候选也必须做+1秒位置持续性复核。

        复核帧允许越过窗口末尾——否则"命中在最后一个采样点"这一格永远
        无条件采信，正好是噪点最容易漏过去的地方。
        """
        blank = self.dir / "blank2.png"
        cv2.imwrite(str(blank), np.zeros((320, 420, 3), dtype=np.uint8))
        # 窗口(8,8.5]，search_window=3 → 采样 8.5/9.5/10.5/11.5，末点11.5。
        # 噪点只在[11,12)出现：末点采到它，+1秒(12.5)已消失 → 必须拒绝。
        video = _build_clip(self.dir / "last_sample.mp4",
                            [(blank, 11), (self.f_noise, 1), (blank, 3)])
        result = video_utils.extract_death_location(
            str(video), death_ts=8.25, death_window=(8.0, 8.5),
            search_window=3.0, sample_interval=1.0)
        self.assertIsNone(result)

    def test_excessive_baseline_candidates_rejected(self):
        """基线帧异常杂乱时整体弃用基线黑名单，而不是把minimap全拉黑。

        无上限时这份基线会产生上百个排除圆、覆盖大半个裁剪区，真实X标记
        必然落在某个圈里 → 函数静默返回None（召回清零）。加了上限后基线
        被整体放弃、退回static_zones+特征2/3，仍能定位到标记，并留warning。
        """
        clutter = np.zeros((320, 420, 3), dtype=np.uint8)
        spots = [(20 + 40 * i, 20 + 40 * j) for i in range(10) for j in range(6)]
        for cx, cy in spots:
            _x_marker(clutter, cx, cy, r=8, thickness=3)
        f_clutter = self.dir / "clutter.png"
        cv2.imwrite(str(f_clutter), clutter)

        real = np.zeros((320, 420, 3), dtype=np.uint8)
        _x_marker(real, *spots[13], r=8, thickness=3)  # 真X落在某个杂乱位置上
        f_real = self.dir / "clutter_real.png"
        cv2.imwrite(str(f_real), real)

        video = _build_clip(self.dir / "clutter.mp4",
                            [(f_clutter, 8), (f_real, 4)])
        with mock.patch.object(video_utils, "logging") as log:
            result = video_utils.extract_death_location(
                str(video), death_ts=8.25, death_window=(8.0, 8.5),
                search_window=3.0, sample_interval=1.0)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result["cx"], spots[13][0], delta=6)
        self.assertAlmostEqual(result["cy"], spots[13][1], delta=6)
        log.warning.assert_called()  # 弃用基线必须留痕，不能静默降级


def _calibrated_flag(value):
    """把config.yaml的video节替换成只含标定开关的一份（None=键不存在）。"""
    cfg = {} if value is None else {"respawn_crop_calibrated": value}
    return mock.patch.object(video_utils, "_load_video_config", lambda: cfg)


@unittest.skipUnless(_HAS_CV2 and _HAS_FFMPEG, "需要 opencv-python + numpy + ffmpeg")
class TestRespawnCoOccurrence(unittest.TestCase):
    """AGE-131方案3（复活HUD共现）的标定门禁回归测试。

    守住80582f5那次修复的核心行为：respawn_crop还是未标定占位值时，该特征
    必须**整体跳过**而不是恒不通过——后者会把所有真实死亡X标记都拒掉，
    召回率归零（而不是注释里原本以为的"等价于禁用"）。
    """

    # 一个能在合成素材上裁出画面的区域；是否"已标定"由config开关决定
    # （见_calibrated_flag / respawn_crop_is_calibrated），与坐标无关。
    CALIBRATED_CROP = {"x": 0, "y": 0, "w": 100, "h": 50}

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        blank = np.zeros((320, 420, 3), dtype=np.uint8)
        marked = _x_marker(np.zeros((320, 420, 3), dtype=np.uint8), 100, 240)
        f0, f1 = self.dir / "f0.png", self.dir / "f1.png"
        cv2.imwrite(str(f0), blank)
        cv2.imwrite(str(f1), marked)
        self.video = _build_clip(self.dir / "clip.mp4", [(f0, 8), (f1, 4)])
        self.calls: list[Path] = []

    def tearDown(self):
        self._tmp.cleanup()

    def _locate(self, **kw):
        return video_utils.extract_death_location(
            str(self.video), death_ts=8.25, death_window=(8.0, 8.5),
            search_window=3.0, sample_interval=1.0, **kw)

    def _reader(self, value):
        def reader(path: Path):
            self.calls.append(path)
            return value
        return reader

    def test_uncalibrated_crop_skips_feature_and_keeps_recall(self):
        """未标定：特征跳过，reader根本不被调用，真实死亡照常命中。"""
        result = self._locate(respawn_reader=self._reader(None),
                              respawn_crop=video_utils._FALLBACK_RESPAWN_CROP)
        self.assertIsNotNone(result)
        self.assertEqual(self.calls, [])

    def test_config_default_crop_is_now_calibrated(self):
        """AGE-140标定完成：config.yaml声明已标定 → 端到端不再走跳过分支。

        合成测试素材帧远小于真实录屏（2796x1290），标定后的裁剪区在合成帧
        上落不到任何真实倒计时数字，reader读不到值也在预期内——已标定后
        该特征会真的执行并把"读不到倒计时"当噪点拒绝（与
        test_calibrated_crop_enforces_countdown同一行为，这里只是确认
        默认配置本身现在确实被判定为已标定、reader确实被调用了）。
        """
        self.assertTrue(
            video_utils.respawn_crop_is_calibrated(video_utils.DEFAULT_RESPAWN_CROP))
        result = self._locate(respawn_reader=self._reader(None))
        self.assertIsNone(result)
        self.assertTrue(self.calls)

    def test_calibrated_crop_enforces_countdown(self):
        """已标定 + 倒计时读不到 → 判为噪点，不采信。"""
        with _calibrated_flag(True):
            result = self._locate(respawn_reader=self._reader(None),
                                  respawn_crop=self.CALIBRATED_CROP)
        self.assertIsNone(result)
        self.assertTrue(self.calls)  # 特征真的跑了

    def test_calibrated_crop_confirms_with_countdown(self):
        """已标定 + 读到倒计时秒数 → 采信。"""
        with _calibrated_flag(True):
            result = self._locate(respawn_reader=self._reader(8),
                                  respawn_crop=self.CALIBRATED_CROP)
        self.assertIsNotNone(result)
        self.assertTrue(self.calls)

    def test_respawn_frame_grab_failure_does_not_veto_but_warns(self):
        """取不到复活HUD帧是"取证失败"而非"倒计时没出现"，不能据此否决——
        否则一个裁剪区越界的配置问题会重新变成召回崩塌。

        但"最强的那层判别特征被静默关掉"必须留痕：只保持不否决而不告警，
        线上只会看到误报率悄悄回升，查不到根因是裁剪区/丢帧。
        """
        def boom(*a, **kw):
            raise subprocess.CalledProcessError(1, "ffmpeg")

        with _calibrated_flag(True), \
             mock.patch.object(video_utils, "grab_respawn_frame", boom), \
             mock.patch.object(video_utils, "logging") as log:
            result = self._locate(respawn_reader=self._reader(None),
                                  respawn_crop=self.CALIBRATED_CROP)
        self.assertIsNotNone(result)
        self.assertEqual(self.calls, [])  # reader没机会被调用
        log.warning.assert_called()


class TestRespawnCropCalibrationGate(unittest.TestCase):
    """AGE-131复查：标定状态改由config显式开关声明，不再靠坐标比对推断。

    坐标启发式太脆——把占位坐标随手挪一个像素就会被判成"已标定"，静默
    打开那条把所有真实死亡X标记都拒掉的召回崩塌路径。
    """

    def test_config_declares_calibrated(self):
        """AGE-140标定完成后：config.yaml显式声明已标定 → 判定为已标定。

        占位坐标（_FALLBACK_RESPAWN_CROP）本身依然不能被判定为已标定——
        开关是唯一权威依据，不是"坐标不再是占位值"这件事本身。
        """
        cfg = config_utils.load_config()["video"]
        self.assertTrue(cfg["respawn_crop_calibrated"])
        self.assertTrue(
            video_utils.respawn_crop_is_calibrated(video_utils.DEFAULT_RESPAWN_CROP))
        with _calibrated_flag(False):
            self.assertFalse(
                video_utils.respawn_crop_is_calibrated(video_utils._FALLBACK_RESPAWN_CROP))

    def test_flag_true_calibrates_even_with_placeholder_coords(self):
        """开关是权威状态：置true后坐标仍是占位值也算已标定。"""
        with _calibrated_flag(True):
            self.assertTrue(video_utils.respawn_crop_is_calibrated(
                dict(video_utils._FALLBACK_RESPAWN_CROP)))

    def test_flag_false_overrides_drifted_coords(self):
        """开关为false时，坐标漂了一个像素也不会被当成"已标定"。"""
        crop = dict(video_utils._FALLBACK_RESPAWN_CROP)
        crop["y"] += 1
        with _calibrated_flag(False):
            self.assertFalse(video_utils.respawn_crop_is_calibrated(crop))

    def test_missing_flag_falls_back_to_coord_heuristic(self):
        """老配置（没有这个键）回落到旧的坐标比对行为，向后兼容。"""
        crop = dict(video_utils._FALLBACK_RESPAWN_CROP)
        crop["y"] += 200
        with _calibrated_flag(None):
            self.assertTrue(video_utils.respawn_crop_is_calibrated(crop))
            self.assertFalse(video_utils.respawn_crop_is_calibrated(
                dict(video_utils._FALLBACK_RESPAWN_CROP)))


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
