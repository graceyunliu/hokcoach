# -*- coding: utf-8 -*-
"""视频复盘的后台任务/内存job状态（AGE-178）。

单用户本地工具，不需要Celery/Redis这类外部队列——一个进程内的dict足够。
不做持久化：进程重启job状态就没了（正在跑的分析任务本来也没法恢复到
中间状态，重启就是重新上传重新跑）。
"""

from __future__ import annotations

import threading
import traceback
import uuid
from datetime import datetime, timezone
from typing import Any, Literal

JobStatus = Literal["queued", "running", "done", "failed"]


class Job:
    def __init__(self, job_id: str, video_path: str) -> None:
        self.id = job_id
        self.video_path = video_path
        self.status: JobStatus = "queued"
        self.stage: str | None = None
        self.error: str | None = None
        self.replay_id: str | None = None
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.updated_at = self.created_at
        self._lock = threading.Lock()

    def to_dict(self) -> dict[str, Any]:
        with self._lock:
            return {
                "job_id": self.id,
                "status": self.status,
                "stage": self.stage,
                "error": self.error,
                "replay_id": self.replay_id,
                "created_at": self.created_at,
                "updated_at": self.updated_at,
            }

    def set_stage(self, stage: str) -> None:
        with self._lock:
            self.status = "running"
            self.stage = stage
            self.updated_at = datetime.now(timezone.utc).isoformat()

    def set_done(self, replay_id: str) -> None:
        with self._lock:
            self.status = "done"
            self.stage = "完成"
            self.replay_id = replay_id
            self.updated_at = datetime.now(timezone.utc).isoformat()

    def set_failed(self, error: str) -> None:
        with self._lock:
            self.status = "failed"
            self.error = error
            self.updated_at = datetime.now(timezone.utc).isoformat()


class JobStore:
    """进程内job注册表，线程安全。"""

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def create(self, video_path: str) -> Job:
        job = Job(job_id=str(uuid.uuid4()), video_path=video_path)
        with self._lock:
            self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)


# 模块级单例：FastAPI app本身是单进程单worker假设下的单例（本地工具，
# 不考虑多worker部署；多worker需要换成Redis等外部存储，超出本epic范围）。
job_store = JobStore()


def run_replay_job(job: Job, orchestrator_factory) -> None:
    """在后台线程里跑视频管线：build_replay_from_video_path→存盘。

    orchestrator_factory: 每次调用返回一个新Orchestrator实例（不复用同一个
    实例跨线程——Orchestrator持有的LLM/VLM client未声明线程安全，稳妥起见
    每个job用自己的实例）。
    """
    from utils import data_utils
    from core.orchestrator import OrchestratorError

    try:
        orch = orchestrator_factory()
        replay = orch.build_replay_from_video_path(
            job.video_path, progress_cb=job.set_stage)
        job.set_stage("生成AI点评")
        # 复盘页是一次性看完整分析的场景（不是对话），全部死亡都要有点评，
        # 不能像CLI/--chat那样只讲第一条——见orchestrator.finalize_review_all
        # 的说明。
        result = orch.finalize_review_all(replay)
        job.set_done(replay_id=result["replay"]["replay_id"])
    except OrchestratorError as err:
        job.set_failed(str(err))
    except Exception:  # noqa: BLE001 — 后台线程里任何异常都必须落到job状态，
        # 否则前端轮询永远卡在running，且异常会被线程默默吞掉，排查不到。
        job.set_failed(f"内部错误：{traceback.format_exc(limit=3)}")
