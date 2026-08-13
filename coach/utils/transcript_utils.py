# -*- coding: utf-8 -*-
"""知识库冷启动转录管线（实现计划v1.0第三节）。

流程：视频 → 转录文本 → LLM初筛候选原则条目 → 写入候选文件，
由用户人工判定tier（1机制事实/2多源趋同/3个人风格）后才允许进入
knowledge_base/ ——tier判定是知识库可信度的核心防线，不自动化。

信源策略：
1. YouTube优先（官方transcript API拿字幕，零ASR成本）
   依赖：pip install youtube-transcript-api
2. 抖音其次（需本地Whisper做ASR，v1.x再接，本模块预留接口）

用法（命令行）：
    python -m utils.transcript_utils <youtube_video_id> [--source 博主名]
输出：knowledge_base/candidates/<video_id>.md（待人工tier判定）
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from typing import Any, Optional

BASE_DIR = Path(__file__).resolve().parent.parent
CANDIDATES_DIR = BASE_DIR / "knowledge_base" / "candidates"

_EXTRACT_PROMPT = """\
以下是一段王者荣耀复盘/教学视频的转录文本。请从中提取"可复用的决策原则"候选条目。

要求：
1. 只提取有明确判断依据的原则（"什么情况下应该怎么做"），不提取主播的情绪表达、\
广告、闲聊。
2. 每条原则一句话，附上你对其性质的初步猜测：
   - 疑似tier1：可查证的机制事实（数值/技能/刷新时间）
   - 疑似tier2：普适决策原则（需多信源独立趋同才能确认）
   - 疑似tier3：个人风格/有争议打法
3. 你的tier猜测只是初筛参考，最终判定由人工完成。
4. 没有可提取的内容就输出空数组。

输出JSON数组，每项：
{{"text": "原则一句话", "tier_guess": "1|2|3", "quote": "原文依据片段(≤50字)"}}

转录文本：
{transcript}
"""


def fetch_youtube_transcript(video_id: str,
                             languages: tuple[str, ...] = ("zh-Hans", "zh-Hant", "zh", "en")
                             ) -> str:
    """拉取YouTube字幕全文。依赖 youtube-transcript-api。"""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi  # type: ignore
    except ImportError as e:
        raise RuntimeError(
            "需要安装 youtube-transcript-api：pip install youtube-transcript-api"
        ) from e
    api = YouTubeTranscriptApi()
    fetched = api.fetch(video_id, languages=list(languages))
    return " ".join(snippet.text for snippet in fetched)


def transcribe_douyin(video_path: str) -> str:
    """抖音视频本地ASR（v1.x：Whisper）。当前未实现，见实现计划第三节。"""
    raise NotImplementedError(
        "抖音管线需本地Whisper ASR，按实现计划排在YouTube管线跑顺之后（v1.x）")


def _chunk(text: str, size: int = 6000) -> list[str]:
    return [text[i:i + size] for i in range(0, len(text), size)]


def extract_candidates(transcript: str, llm: Any) -> list[dict[str, Any]]:
    """LLM初筛候选原则条目。llm为core.llm_client.LLMClient实例。"""
    from core.llm_client import LLMError, extract_json

    out: list[dict[str, Any]] = []
    for chunk in _chunk(transcript):
        try:
            raw = llm.chat_text(system="",
                                user=_EXTRACT_PROMPT.format(transcript=chunk),
                                temperature=0.2)
            data = extract_json(raw)
        except (LLMError, ValueError) as e:
            print(f"[初筛失败，跳过一段] {e}", file=sys.stderr)
            continue
        if isinstance(data, list):
            out.extend(d for d in data if isinstance(d, dict) and d.get("text"))
    return out


def write_candidates_file(video_id: str, candidates: list[dict[str, Any]],
                          source: str = "") -> Path:
    """把候选条目写成待人工判定的markdown文件。"""
    CANDIDATES_DIR.mkdir(parents=True, exist_ok=True)
    path = CANDIDATES_DIR / f"{video_id}.md"
    lines = [
        f"# 候选原则条目：{video_id}",
        "",
        f"- 信源：{source or '未标'}（YouTube video_id: {video_id}）",
        f"- 生成日期：{date.today().isoformat()}",
        "- 状态：**待人工tier判定**。逐条确认后按库内格式移入",
        "  macro_principles.md / map_mechanics.md / hero_mechanics.json；",
        "  tier 3只能进偶像标准层，禁止进基本功库。",
        "",
    ]
    for i, c in enumerate(candidates, 1):
        lines += [
            f"## {i}. {c.get('text', '')}",
            f"- LLM初筛tier猜测：{c.get('tier_guess', '?')}（仅供参考）",
            f"- 原文依据：{c.get('quote', '')}",
            "- [ ] 人工判定tier：__",
            "- [ ] 多源独立趋同确认（tier 2必填）：__",
            "",
        ]
    if not candidates:
        lines.append("（本视频未提取到候选条目）")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def run_pipeline(video_id: str, source: str = "",
                 llm: Optional[Any] = None) -> Path:
    """完整管线：字幕 → 初筛 → 候选文件。"""
    if llm is None:
        from core.llm_client import LLMClient
        from utils import config_utils

        llm = LLMClient.from_config(config_utils.load_config())
    if llm is None:
        raise RuntimeError("初筛需要LLM，请先在config.yaml配置并设置API key")
    transcript = fetch_youtube_transcript(video_id)
    print(f"[转录] 拿到{len(transcript)}字")
    candidates = extract_candidates(transcript, llm)
    print(f"[初筛] 提取到{len(candidates)}条候选")
    path = write_candidates_file(video_id, candidates, source)
    print(f"[输出] {path}（请人工逐条判定tier后移入知识库）")
    return path


if __name__ == "__main__":
    import argparse

    sys.path.insert(0, str(BASE_DIR))
    ap = argparse.ArgumentParser(description="YouTube转录→候选原则初筛管线")
    ap.add_argument("video_id", help="YouTube视频ID")
    ap.add_argument("--source", default="", help="信源标注（博主名等）")
    a = ap.parse_args()
    raise SystemExit(0 if run_pipeline(a.video_id, a.source) else 1)
