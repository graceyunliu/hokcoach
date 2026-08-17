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


    def test_orchestrator_passes_counter_window(self):
        """生产路径（orchestrator）必须把counter窗口传下来，否则会撞门禁。"""
        src = Path(video_utils.__file__).parent.parent / "core" / "orchestrator.py"
        text = src.read_text(encoding="utf-8")
        self.assertIn("death_window=e[\"window\"]", text)
        self.assertNotIn("allow_unanchored", text)


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

    def test_baseline_anchored_on_window_lo_not_midpoint(self):
        """基线必须锚在窗口下界之前：真死亡发生在lo、而窗口较宽时，
        按中点-2秒取基线会落在死亡之后，把真X自己拉黑。"""
        video = _build_clip(self.dir / "wide.mp4",
                            [(self.f_noise, 8), (self.f_both, 8)])
        # counter窗口(8,14)，中点11 → 旧的"中点-2秒"基线会落在10秒（已在
        # 死亡之后，真X已出现）；新实现锚在8秒之前，基线取6/4/2秒。
        result = video_utils.extract_death_location(
            str(video), death_ts=11.0, death_window=(8.0, 14.0),
            search_window=1.0, sample_interval=1.0)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result["cx"], self.REAL[0], delta=6)


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

    def test_config_default_crop_is_still_uncalibrated(self):
        """config.yaml目前声明未标定 → 端到端也确实走跳过分支。"""
        self.assertFalse(
            video_utils.respawn_crop_is_calibrated(video_utils.DEFAULT_RESPAWN_CROP))
        result = self._locate(respawn_reader=self._reader(None))
        self.assertIsNotNone(result)
        self.assertEqual(self.calls, [])

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

    def test_respawn_frame_grab_failure_does_not_veto(self):
        """取不到复活HUD帧是"取证失败"而非"倒计时没出现"，不能据此否决——
        否则一个裁剪区越界的配置问题会重新变成召回崩塌。"""
        def boom(*a, **kw):
            raise subprocess.CalledProcessError(1, "ffmpeg")

        with _calibrated_flag(True), \
             mock.patch.object(video_utils, "grab_respawn_frame", boom):
            result = self._locate(respawn_reader=self._reader(None),
                                  respawn_crop=self.CALIBRATED_CROP)
        self.assertIsNotNone(result)
        self.assertEqual(self.calls, [])  # reader没机会被调用


class TestRespawnCropCalibrationGate(unittest.TestCase):
    """AGE-131复查：标定状态改由config显式开关声明，不再靠坐标比对推断。

    坐标启发式太脆——把占位坐标随手挪一个像素就会被判成"已标定"，静默
    打开那条把所有真实死亡X标记都拒掉的召回崩塌路径。
    """

    def test_config_declares_uncalibrated(self):
        """config.yaml当前显式声明未标定 → 判定为未标定。

        标定完成后（开关改true）本断言会失败，那正是提醒：该重跑方案3的
        端到端验证了。
        """
        cfg = config_utils.load_config()["video"]
        self.assertFalse(cfg["respawn_crop_calibrated"])
        self.assertFalse(
            video_utils.respawn_crop_is_calibrated(video_utils._FALLBACK_RESPAWN_CROP))
        self.assertFalse(
            video_utils.respawn_crop_is_calibrated(video_utils.DEFAULT_RESPAWN_CROP))

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
