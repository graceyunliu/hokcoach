# -*- coding: utf-8 -*-
"""AI王者荣耀决策思维教练（Coach）— CLI入口。

已接通全部MVP命令（实现计划v1.0阶段1-3）：
- --init / --update-profile          玩家档案
- --replay <video> / --replay --manual  复盘（视频自动 / 手动录入）
- --chat                              自由对话
- --checkin / --weekly-report / --progress  训练闭环
语音层（--voice）已整体移出MVP，v1.1+再加。

LLM未配置时进入降级模式：规则归因+知识库原文可用，AI点评/对话不可用。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from utils import data_utils


# ---------------------------------------------------------------------------
# 交互工具
# ---------------------------------------------------------------------------

def _ask(prompt: str, hint: str = "回车跳过") -> str:
    """交互式输入。不预填任何默认数据——新用户的档案只能来自本人输入。"""
    try:
        value = input(f"{prompt}（{hint}）\n> ").strip()
    except EOFError:  # 管道/无输入环境
        value = ""
    return value


def _ask_list(prompt: str) -> list[str]:
    raw = _ask(prompt + "，逗号分隔")
    return [x.strip() for x in raw.replace("，", ",").split(",") if x.strip()]


def _ask_int(prompt: str) -> int | None:
    raw = _ask(prompt)
    try:
        return int(raw)
    except ValueError:
        if raw:
            print("  （无法解析为数字，先留空，之后可用 --update-profile 补）")
        return None


# ---------------------------------------------------------------------------
# 命令实现
# ---------------------------------------------------------------------------

def cmd_init(force: bool = False) -> int:
    """--init：交互式创建玩家档案（里程碑1）。"""
    existing = data_utils.load_player_profile()
    if existing and not force:
        print("已存在玩家档案 data/player_profile.json。")
        print("如需修改请用 --update-profile，或 --init --force 重新创建。")
        return 1

    print("Coach> 你好，我是你的复盘教练。先建个档案，不确定的项回车跳过，")
    print("Coach> 之后随时可用 --update-profile 补充。\n")
    profile = data_utils.default_player_profile()
    p = profile["player"]

    p["main_heroes"] = _ask_list("主玩英雄")
    p["secondary_heroes"] = _ask_list("次选英雄")
    p["rank_type"] = _ask("排位类型（如 巅峰赛/王者段位）") or None
    p["current_rank"] = _ask_int("当前分数/段位星数")
    p["target_hero"] = _ask("最想练好的英雄") or None
    p["target_power"] = _ask_int("目标战力")
    p["total_games"] = _ask_int("总场次（大约）")

    # 基线快照跟随初次输入
    p["baseline"]["rank"] = p["current_rank"]

    # 约束画像（tech spec 4.6，全部可选）
    latency = _ask("网络延迟ms（可选约束画像）")
    if latency.isdigit():
        p["constraints"]["network_latency_ms"] = int(latency)

    data_utils.save_player_profile(profile)
    print(f"\nCoach> 档案建好了：{data_utils.PLAYER_PROFILE_PATH}")
    summary = []
    if p["main_heroes"]:
        summary.append(f"主玩 {'/'.join(p['main_heroes'])}")
    if p["rank_type"] and p["current_rank"] is not None:
        summary.append(f"{p['rank_type']}{p['current_rank']}分")
    if p["target_hero"]:
        summary.append(f"重点练{p['target_hero']}")
    if summary:
        print(f"Coach> {'，'.join(summary)}。")
    print("Coach> 打完一局随时来找我：python coach.py --replay <video>")
    return 0


def cmd_update_profile() -> int:
    """--update-profile：更新已有档案（复用init交互，保留join_date/baseline）。"""
    existing = data_utils.load_player_profile()
    if existing is None:
        print("尚无玩家档案，请先运行 python coach.py --init")
        return 1
    print("Coach> 逐项更新，回车保留当前值。\n")
    p = existing["player"]
    # 更新场景下显示当前值是合理的——那是用户自己已保存的数据
    heroes = _ask_list(f"主玩英雄（当前：{', '.join(p['main_heroes']) or '未填'}）")
    if heroes:
        p["main_heroes"] = heroes
    rank = _ask_int(f"当前分数（当前：{p['current_rank']}）")
    if rank is not None:
        p["current_rank"] = rank
    hero = _ask(f"重点培养英雄（当前：{p['target_hero']}）")
    if hero:
        p["target_hero"] = hero
    power = _ask_int(f"目标战力（当前：{p['target_power']}）")
    if power is not None:
        p["target_power"] = power
    games = _ask_int(f"总场次（当前：{p['total_games']}）")
    if games is not None:
        p["total_games"] = games
    data_utils.save_player_profile(existing)
    print("\nCoach> 档案已更新。")
    return 0


def _orchestrator():
    from core.orchestrator import Orchestrator

    orch = Orchestrator()
    print(orch.llm_status_line())
    return orch


def cmd_replay(video: str | None, manual: bool, output: str | None = None) -> int:
    if manual:
        from adapters.manual_adapter import ManualInputAdapter

        adapter = ManualInputAdapter()
        try:
            adapter.get_player_profile()
        except FileNotFoundError as e:
            print(e)
            return 1
        replay = adapter.get_match_data()
        return _orchestrator().analyze_manual(replay, output=output)
    if not video:
        print("用法：--replay <video>（视频自动复盘）或 --replay --manual（手动录入）")
        return 1
    return _orchestrator().analyze_video(video, output=output)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="coach.py",
        description="AI王者荣耀决策思维教练（纯文本MVP，语音为v1.1+增强）",
    )
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--init", action="store_true", help="初始化玩家档案")
    g.add_argument("--update-profile", action="store_true", help="更新玩家数据")
    g.add_argument("--replay", nargs="?", const="", metavar="VIDEO",
                   help="复盘一局（视频自动分析；--manual 手动录入）")
    g.add_argument("--checkin", action="store_true", help="训练打卡")
    g.add_argument("--weekly-report", action="store_true", help="周报")
    g.add_argument("--progress", action="store_true", help="查看进度")
    g.add_argument("--chat", action="store_true", help="自由对话")

    parser.add_argument("--force", action="store_true", help="配合--init强制重建档案")
    parser.add_argument("--manual", action="store_true", help="配合--replay手动录入")
    parser.add_argument("--output", metavar="FILE", help="导出报告文件")
    parser.add_argument("--date", metavar="DATE", help="配合--checkin指定日期(YYYY-MM-DD)")
    parser.add_argument("--rate", type=int, metavar="0-100", help="配合--checkin执行率")
    parser.add_argument("--note", metavar="TEXT", help="配合--checkin备注")
    parser.add_argument("--detail", action="store_true", help="配合--progress详细模式")
    parser.add_argument("--chart", action="store_true", help="配合--progress ASCII图表")
    parser.add_argument("--topic", metavar="TOPIC", help="配合--chat指定话题")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.init:
        return cmd_init(force=args.force)
    if args.update_profile:
        return cmd_update_profile()
    if args.replay is not None:
        return cmd_replay(args.replay or None, manual=args.manual,
                          output=args.output)
    if args.checkin:
        return cmd_checkin(args.date, args.rate, args.note)
    if args.weekly_report:
        return _orchestrator().weekly_report(output=args.output)
    if args.progress:
        from core import training_engine

        print(training_engine.render_progress(detail=args.detail,
                                              chart=args.chart))
        return 0
    if args.chat:
        return _orchestrator().chat(topic=args.topic)
    return 0


def cmd_checkin(when: str | None, rate: int | None, note: str | None) -> int:
    from core import training_engine

    if rate is None:
        raw = _ask("今天的任务执行率（0-100）")
        rate = int(raw) if raw.isdigit() else None
    if rate is None:
        print("Coach> 没有执行率就没法记，明天再来。（--rate 0-100）")
        return 1
    try:
        week = training_engine.checkin(rate=rate, note=note, when=when)
    except ValueError as e:
        print(f"Coach> {e}")
        return 1
    task = week["task"]
    print(f"Coach> 打卡完成：{task['description']} "
          f"进度 {task['current_streak']}/{task['target_streak']}"
          f"（{'达成！' if task['status'] == 'done' else '坚持住'}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
