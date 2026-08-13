# -*- coding: utf-8 -*-
"""data_utils 与 --init 的基本测试（标准库unittest，无三方依赖）。"""

import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils import data_utils  # noqa: E402


class TestDataUtils(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        tmp = Path(self._tmp.name)
        # 重定向数据路径到临时目录
        self._patches = [
            mock.patch.object(data_utils, "DATA_DIR", tmp),
            mock.patch.object(data_utils, "REPLAYS_DIR", tmp / "replays"),
            mock.patch.object(data_utils, "PLAYER_PROFILE_PATH", tmp / "player_profile.json"),
            mock.patch.object(data_utils, "WEEKLY_TRAINING_PATH", tmp / "weekly_training.json"),
            mock.patch.object(data_utils, "PROGRESS_PATH", tmp / "progress.json"),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()
        self._tmp.cleanup()

    def test_profile_roundtrip(self):
        profile = data_utils.default_player_profile()
        data_utils.save_player_profile(profile)
        loaded = data_utils.load_player_profile()
        self.assertEqual(loaded, profile)
        self.assertIn("constraints", loaded["player"])
        self.assertIn("baseline", loaded["player"])

    def test_default_schemas_match_tech_spec(self):
        wt = data_utils.default_weekly_training("2026-W33")
        self.assertEqual(wt["week"], "2026-W33")
        self.assertIn("daily_checkins", wt)

        prog = data_utils.default_progress()
        self.assertIn("探草意识", prog["weakness_tracker"])

        replay = data_utils.default_replay("蔡文姬")
        self.assertEqual(replay["hero_played"], "蔡文姬")
        self.assertEqual(
            set(replay["death_analysis"]["categories"]),
            {"探草死", "掉点死", "换头死", "机制死", "贪线死"},
        )

    def test_save_and_list_replays(self):
        r = data_utils.default_replay()
        path = data_utils.save_replay(r)
        self.assertTrue(path.exists())
        self.assertEqual(len(data_utils.list_replays()), 1)
        with open(path, encoding="utf-8") as f:
            self.assertEqual(json.load(f)["replay_id"], r["replay_id"])

    def test_cmd_init_all_skipped(self):
        """里程碑1：--init 全部跳过也能创建空档案（不预填任何个人数据）。"""
        import coach as coach_mod

        with mock.patch("sys.stdin", io.StringIO("")):  # EOF → 全部跳过
            rc = coach_mod.cmd_init()
        self.assertEqual(rc, 0)
        profile = data_utils.load_player_profile()
        self.assertIsNotNone(profile)
        self.assertIsNone(profile["player"]["current_rank"])
        self.assertEqual(profile["player"]["main_heroes"], [])

    def test_cmd_init_with_user_input(self):
        """--init 输入的值被正确写入档案。"""
        import coach as coach_mod

        answers = "\n".join([
            "瑶, 蔡文姬",   # 主玩英雄
            "",              # 次选英雄
            "巅峰赛",        # 排位类型
            "1362",          # 当前分数
            "蔡文姬",        # 最想练好的英雄
            "10000",         # 目标战力
            "6327",          # 总场次
            "",              # 网络延迟
        ]) + "\n"
        with mock.patch("sys.stdin", io.StringIO(answers)):
            rc = coach_mod.cmd_init()
        self.assertEqual(rc, 0)
        p = data_utils.load_player_profile()["player"]
        self.assertEqual(p["main_heroes"], ["瑶", "蔡文姬"])
        self.assertEqual(p["current_rank"], 1362)
        self.assertEqual(p["baseline"]["rank"], 1362)

    def test_cmd_init_refuses_overwrite(self):
        import coach as coach_mod

        data_utils.save_player_profile(data_utils.default_player_profile())
        rc = coach_mod.cmd_init()
        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
