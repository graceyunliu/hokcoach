# -*- coding: utf-8 -*-
"""FastAPI层测试（AGE-178/179/180/181）。

全部用mock.patch.object把data_utils的路径常量/Orchestrator的管线方法
换成临时目录/假实现——绝不能碰真实的coach/data/*.json（教训：手测时
不小心通过真实API调用往data/weekly_training.json里写了条测试打卡记录，
这里的隔离就是为了不再犯）。
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

try:
    from fastapi.testclient import TestClient
    _HAS_FASTAPI = True
except ImportError:
    _HAS_FASTAPI = False

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils import data_utils  # noqa: E402


@unittest.skipUnless(_HAS_FASTAPI, "需要 fastapi + httpx（pip install fastapi uvicorn python-multipart httpx）")
class TestApiSmoke(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self._tmp.name)
        (self.data_dir / "replays").mkdir()

        self._patches = [
            mock.patch.object(data_utils, "DATA_DIR", self.data_dir),
            mock.patch.object(data_utils, "REPLAYS_DIR", self.data_dir / "replays"),
            mock.patch.object(data_utils, "PLAYER_PROFILE_PATH",
                              self.data_dir / "player_profile.json"),
            mock.patch.object(data_utils, "WEEKLY_TRAINING_PATH",
                              self.data_dir / "weekly_training.json"),
            mock.patch.object(data_utils, "PROGRESS_PATH",
                              self.data_dir / "progress.json"),
        ]
        for p in self._patches:
            p.start()

        from api.main import app
        self.client = TestClient(app)

    def tearDown(self):
        for p in self._patches:
            p.stop()
        self._tmp.cleanup()

    def test_health(self):
        r = self.client.get("/health")
        self.assertEqual(r.status_code, 200)

    def test_progress_and_profile_default_to_empty_shapes(self):
        r = self.client.get("/progress")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["weekly_snapshots"], [])

        r = self.client.get("/player/profile")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["player"]["language"], "zh")

    def test_training_current_auto_assigns_task(self):
        r = self.client.get("/training/current")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["task"]["description"])

    def test_checkin_validates_rate_range(self):
        r = self.client.post("/training/checkin", json={"rate": 150})
        self.assertEqual(r.status_code, 422)  # pydantic字段级校验，先于业务逻辑

    def test_checkin_then_history_and_current_reflect_it(self):
        r = self.client.post("/training/checkin",
                             json={"rate": 90, "note": "test"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["task"]["current_streak"], 1)

        r = self.client.get("/training/current")
        self.assertEqual(len(r.json()["daily_checkins"]), 1)

    def test_replays_list_empty_then_replay_detail_404(self):
        r = self.client.get("/replays")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["replays"], [])

        r = self.client.get("/replay/does-not-exist")
        self.assertEqual(r.status_code, 404)

    def test_replay_upload_starts_job_and_status_reaches_done(self):
        """不跑真实视频管线：mock掉Orchestrator.build_replay_from_video_path，
        只验证job生命周期（queued→running→done）能通过HTTP轮询观察到，
        且完成后replay_id能通过/replay/{id}读回来。"""
        from core.orchestrator import Orchestrator

        fake_replay = data_utils.default_replay(hero_played="瑶")

        def fake_build(self, video_path, progress_cb=None, lang="zh"):
            if progress_cb:
                progress_cb("检测死亡事件")
            fake_replay["language"] = lang
            return fake_replay

        with mock.patch.object(Orchestrator, "build_replay_from_video_path",
                               fake_build), \
             mock.patch.object(Orchestrator, "comment_death",
                               return_value="test comment"):
            r = self.client.post(
                "/replay",
                files={"file": ("clip.mp4", b"fake-bytes", "video/mp4")},
            )
            self.assertEqual(r.status_code, 200)
            job_id = r.json()["job_id"]

            # TestClient跑BackgroundTasks是同步的（请求返回时任务已经跑完），
            # 不需要真的轮询等待。
            r = self.client.get(f"/replay/{job_id}/status")
            self.assertEqual(r.status_code, 200)
            body = r.json()
            self.assertEqual(body["status"], "done")
            self.assertIsNotNone(body["replay_id"])

            r = self.client.get(f"/replay/{body['replay_id']}")
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.json()["hero_played"], "瑶")
            self.assertEqual(r.json()["language"], "zh")

    def test_language_validation_and_english_replay_persistence(self):
        """API边界拒绝未知语言，合法英文值必须一路进入job并写入replay。"""
        from core.orchestrator import Orchestrator

        bad = self.client.post(
            "/replay", files={"file": ("clip.mp4", b"x", "video/mp4")},
            data={"lang": "fr"})
        self.assertEqual(bad.status_code, 422)

        fake_replay = data_utils.default_replay(hero_played="瑶")

        def fake_build(self, video_path, progress_cb=None, lang="zh"):
            fake_replay["language"] = lang
            return fake_replay

        with mock.patch.object(Orchestrator, "build_replay_from_video_path", fake_build):
            response = self.client.post(
                "/replay", files={"file": ("clip.mp4", b"x", "video/mp4")},
                data={"lang": "en"})
        status = self.client.get(f"/replay/{response.json()['job_id']}/status").json()
        saved = self.client.get(f"/replay/{status['replay_id']}").json()
        self.assertEqual(saved["language"], "en")

        invalid_checkin = self.client.post("/training/checkin", json={"rate": 80, "lang": "fr"})
        self.assertEqual(invalid_checkin.status_code, 422)

    def test_profile_language_can_be_persisted(self):
        response = self.client.patch("/player/profile", json={"language": "en"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["player"]["language"], "en")
        self.assertEqual(self.client.get("/player/profile").json()["player"]["language"], "en")

    def test_replay_video_404_when_no_source_path(self):
        """手动录入的复盘没有source.path（不是视频来源），/video端点要给出
        明确的404，而不是让前端<video>元素卡在加载圈里。"""
        replay = data_utils.default_replay(hero_played="瑶")
        data_utils.save_replay(replay)
        r = self.client.get(f"/replay/{replay['replay_id']}/video")
        self.assertEqual(r.status_code, 404)

    def test_replay_video_404_when_file_missing_on_disk(self):
        """source.path存在于replay JSON里，但磁盘上的文件已经不在了（临时
        目录被系统清理）——这是"跟教练一起看回放"功能最可能踩的坑，必须
        给明确错误而不是500。"""
        replay = data_utils.default_replay(hero_played="瑶")
        replay["source"] = {"type": "video", "path": "/tmp/does-not-exist-xyz.mp4"}
        data_utils.save_replay(replay)
        r = self.client.get(f"/replay/{replay['replay_id']}/video")
        self.assertEqual(r.status_code, 404)

    def test_replay_video_serves_full_file_and_range_requests(self):
        with tempfile.TemporaryDirectory() as tmp:
            video_path = Path(tmp) / "clip.mp4"
            payload = b"0123456789" * 100  # 1000 bytes，够切几个Range测试
            video_path.write_bytes(payload)

            replay = data_utils.default_replay(hero_played="瑶")
            replay["source"] = {"type": "video", "path": str(video_path)}
            data_utils.save_replay(replay)
            replay_id = replay["replay_id"]

            r = self.client.get(f"/replay/{replay_id}/video")
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.content, payload)
            self.assertEqual(r.headers.get("accept-ranges"), "bytes")

            r = self.client.get(
                f"/replay/{replay_id}/video",
                headers={"Range": "bytes=10-19"})
            self.assertEqual(r.status_code, 206)
            self.assertEqual(r.content, payload[10:20])
            self.assertEqual(r.headers.get("content-range"), f"bytes 10-19/{len(payload)}")

            r = self.client.get(
                f"/replay/{replay_id}/video",
                headers={"Range": "bytes=990-"})
            self.assertEqual(r.status_code, 206)
            self.assertEqual(r.content, payload[990:])

            r = self.client.get(
                f"/replay/{replay_id}/video",
                headers={"Range": "bytes=abc-def"})
            self.assertEqual(r.status_code, 416)

    def test_replay_upload_job_fails_gracefully_on_missing_video(self):
        from core.orchestrator import Orchestrator, OrchestratorError

        with mock.patch.object(Orchestrator, "build_replay_from_video_path",
                               side_effect=OrchestratorError("找不到视频文件: x")):
            r = self.client.post(
                "/replay",
                files={"file": ("clip.mp4", b"fake-bytes", "video/mp4")},
            )
            job_id = r.json()["job_id"]
            r = self.client.get(f"/replay/{job_id}/status")
            self.assertEqual(r.json()["status"], "failed")
            self.assertIn("找不到视频文件", r.json()["error"])


if __name__ == "__main__":
    unittest.main()
