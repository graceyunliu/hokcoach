# -*- coding: utf-8 -*-
"""训练引擎（阶段3，tech spec 4.2）。

- weekly_assessment()：advance / change_method / encourage / continue（4.2.1）
  + v1.1扩展：固定约束识别（4.6.3"努力兑现但结果不变"→ compensate）
- 训练任务生成（4.2.2）：可量化目标+完成标准+打卡方式，一句话≤20字
- 打卡、进步追踪、ASCII图表
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from core import constraints_engine
from utils import data_utils

# 4.2.2规则2：新弱点按"基础→进阶"顺序
WEAKNESS_ORDER = ["探草意识", "大招时机", "团战站位", "优势期决策"]

# 死亡类型 → 对应弱点（复盘数据驱动弱点优先级）
DEATH_TYPE_TO_WEAKNESS = {
    "探草死": "探草意识",
    "掉点死": "团战站位",
    "换头死": "团战站位",
    "贪线死": "优势期决策",
}

# 4.2.2规则3/4：每个任务含可量化目标、完成标准、打卡方式；描述≤20字
TASK_TEMPLATES: dict[str, dict[str, Any]] = {
    "探草意识": {
        "description": "连续5局零探草死亡",
        "skill_tag": "探草意识",
        "target_streak": 5,
        "checkin_method": "每局结束记录是否有探草死亡",
    },
    "大招时机": {
        "description": "每局大招命中2人以上再放",
        "skill_tag": "大招时机",
        "target_streak": 5,
        "checkin_method": "每局记录大招是否命中≥2人",
    },
    "团战站位": {
        "description": "团战全程站在前排身后",
        "skill_tag": "团战站位",
        "target_streak": 5,
        "checkin_method": "每局记录是否有站位失误死亡",
    },
    "优势期决策": {
        "description": "优势时只拿塔不追残血",
        "skill_tag": "优势期决策",
        "target_streak": 5,
        "checkin_method": "每局优势期记录是否贪击杀",
    },
}


# ---------------------------------------------------------------------------
# 每周评估（4.2.1 + 4.6.3）
# ---------------------------------------------------------------------------

def weekly_assessment(week_data: dict[str, Any]) -> tuple[str, str]:
    """每周评估逻辑。

    week_data: {
      "habit_execution_rate": float,        # 本周执行率 0-1
      "execution_rate_last_week": float,    # 上周执行率
      "weeks_on_current_task": int,
      "rank": int|None, "last_week_rank": int|None,
      "weakness_entry": dict|None,          # progress.weakness_tracker当前项
    }
    Returns: (action, message)
      action ∈ advance / change_method / encourage / continue / compensate
    """
    rate = week_data.get("habit_execution_rate") or 0.0
    rate_last = week_data.get("execution_rate_last_week") or 0.0
    weeks = week_data.get("weeks_on_current_task") or 0
    rank = week_data.get("rank")
    last_rank = week_data.get("last_week_rank")
    rank_change = (rank - last_rank) if (rank is not None and last_rank is not None) else 0

    # v1.1扩展（4.6.3）：先判固定约束——执行率达标但指标多周不动，
    # 继续布置同一任务大概率无效，应转补偿策略
    weakness = week_data.get("weakness_entry")
    if weakness and constraints_engine.detect_fixed_constraint(weakness):
        return ("compensate",
                "这项你已经连续几周认真练了、执行也到位，但指标没动。"
                "这更像是固定约束而不是练得不够——我们不再重复这个任务，"
                "换成绕开它的补偿打法。")

    if rate > 0.8:
        return "advance", "习惯执行率达标，进入下一训练任务"
    if weeks >= 3 and rate < 0.5:
        return "change_method", "这个方法可能不适合你，我们换一个角度试试"
    if rank_change < -20 and rate > rate_last:
        return "encourage", "分数回落是正常的适应期。你在新习惯上进步明显，坚持住。"
    return "continue", "继续保持当前训练任务"


# ---------------------------------------------------------------------------
# 任务生成（4.2.2）
# ---------------------------------------------------------------------------

def pick_next_weakness(progress: dict[str, Any],
                       recent_replays: list[dict[str, Any]] | None = None,
                       exclude: set[str] | None = None) -> str:
    """选择下一个训练弱点。

    规则1：优先当前in_progress的弱点；
    否则按复盘死亡分布找最高频死因对应弱点；
    否则按基础→进阶顺序取第一个pending。
    """
    exclude = exclude or set()
    tracker = progress.get("weakness_tracker", {})

    for name, entry in tracker.items():
        if entry.get("status") == "in_progress" and name not in exclude:
            return name

    # 复盘数据驱动
    counts: dict[str, int] = {}
    for r in recent_replays or []:
        for dtype, n in r.get("death_analysis", {}).get("categories", {}).items():
            w = DEATH_TYPE_TO_WEAKNESS.get(dtype)
            if w and n:
                counts[w] = counts.get(w, 0) + n
    for w, _ in sorted(counts.items(), key=lambda x: -x[1]):
        if w in tracker and tracker[w].get("status") != "done" and w not in exclude:
            return w

    for w in WEAKNESS_ORDER:
        if tracker.get(w, {}).get("status") == "pending" and w not in exclude:
            return w
    return WEAKNESS_ORDER[0]


def generate_task(weakness: str) -> dict[str, Any]:
    """按模板生成训练任务（含可量化目标/完成标准/打卡方式）。"""
    t = dict(TASK_TEMPLATES.get(weakness) or TASK_TEMPLATES["探草意识"])
    assert len(t["description"]) <= 20, "任务描述必须≤20字（4.2.2规则4）"
    return {
        "description": t["description"],
        "skill_tag": t["skill_tag"],
        "target_streak": t["target_streak"],
        "checkin_method": t["checkin_method"],
        "current_streak": 0,
        "start_date": date.today().isoformat(),
        "status": "in_progress",
    }


def assign_task_for_week(weakness: str | None = None) -> dict[str, Any]:
    """给本周设置训练任务并落盘，返回weekly_training数据。"""
    progress = data_utils.load_progress() or data_utils.default_progress()
    replays = [data_utils.load_json(p) for p in data_utils.list_replays()[-10:]]
    w = weakness or pick_next_weakness(progress, [r for r in replays if r])

    week = data_utils.load_weekly_training()
    current_week = data_utils.default_weekly_training()["week"]
    if week is None or week.get("week") != current_week:
        week = data_utils.default_weekly_training()
    week["task"] = generate_task(w)

    tracker = progress.setdefault("weakness_tracker", {})
    entry = tracker.setdefault(w, {"status": "pending", "weeks_trained": 0,
                                   "current_level": 0.0})
    entry["status"] = "in_progress"

    data_utils.save_weekly_training(week)
    data_utils.save_progress(progress)
    return week


# ---------------------------------------------------------------------------
# 打卡
# ---------------------------------------------------------------------------

def checkin(rate: int | None = None, note: str | None = None,
            when: str | None = None) -> dict[str, Any]:
    """记录一次每日打卡。rate: 0-100执行率。同一天重复打卡则覆盖。"""
    week = data_utils.load_weekly_training()
    if week is None or not week.get("task", {}).get("description"):
        week = assign_task_for_week()
        print(f"Coach> 本周还没有训练任务，先给你安排上：{week['task']['description']}")

    day = when or date.today().isoformat()
    try:
        datetime.strptime(day, "%Y-%m-%d")
    except ValueError:
        raise ValueError(f"日期格式应为YYYY-MM-DD：{day}")
    if rate is not None and not (0 <= rate <= 100):
        raise ValueError("执行率应在0-100之间")

    entry = {"date": day, "rate": rate, "note": note or ""}
    checkins = week.setdefault("daily_checkins", [])
    checkins[:] = [c for c in checkins if c.get("date") != day]
    checkins.append(entry)
    checkins.sort(key=lambda c: c["date"])

    # 连续达标天数：执行率≥80视为当日达标
    task = week["task"]
    streak = 0
    for c in reversed(checkins):
        if (c.get("rate") or 0) >= 80:
            streak += 1
        else:
            break
    task["current_streak"] = streak
    task["status"] = "done" if streak >= task.get("target_streak", 5) else "in_progress"

    data_utils.save_weekly_training(week)
    return week


def week_execution_rate(week: dict[str, Any]) -> float:
    """本周平均执行率（0-1）。无打卡返回0。"""
    rates = [c.get("rate") for c in week.get("daily_checkins", [])
             if c.get("rate") is not None]
    return (sum(rates) / len(rates) / 100.0) if rates else 0.0


# ---------------------------------------------------------------------------
# 周报数据组装 + 快照
# ---------------------------------------------------------------------------

def collect_week_data() -> dict[str, Any]:
    """汇总本周数据，供周报prompt与评估逻辑使用。"""
    week = data_utils.load_weekly_training() or data_utils.default_weekly_training()
    progress = data_utils.load_progress() or data_utils.default_progress()
    profile = data_utils.load_player_profile() or {}
    snapshots = progress.get("weekly_snapshots", [])
    last = snapshots[-1] if snapshots else {}

    rank = (profile.get("player") or {}).get("current_rank")
    # 本周复盘摘要
    replays = [data_utils.load_json(p) for p in data_utils.list_replays()]
    week_str = week.get("week", "")
    summaries = []
    for r in replays:
        if not r:
            continue
        ts = r.get("timestamp", "")
        try:
            iso = datetime.fromisoformat(ts).isocalendar()
            r_week = f"{iso[0]}-W{iso[1]:02d}"
        except ValueError:
            r_week = ""
        if r_week == week_str:
            cats = r.get("death_analysis", {}).get("categories", {})
            top = "、".join(f"{k}×{v}" for k, v in cats.items() if v)
            summaries.append(
                f"{r.get('hero_played') or '?'}"
                f"（{'胜' if r.get('game_result') == 'victory' else '负'}，"
                f"死亡{r.get('deaths', 0)}次{'：' + top if top else ''}）")

    skill = week.get("task", {}).get("skill_tag")
    weakness_entry = (progress.get("weakness_tracker") or {}).get(
        _skill_to_weakness(skill)) if skill else None

    return {
        "week": week,
        "progress": progress,
        "habit_execution_rate": week_execution_rate(week),
        "execution_rate_last_week": last.get("execution_rate", 0.0),
        "weeks_on_current_task": _weeks_on_task(snapshots, skill) + 1,
        "rank": rank,
        "last_week_rank": last.get("rank"),
        "replay_summaries": summaries,
        "weakness_entry": weakness_entry,
    }


def _skill_to_weakness(skill_tag: str | None) -> str:
    return skill_tag or ""


def _weeks_on_task(snapshots: list[dict[str, Any]], skill_tag: str | None) -> int:
    """已完成快照里，连续同一skill_tag的周数。"""
    n = 0
    for s in reversed(snapshots):
        if skill_tag and s.get("skill_tag") == skill_tag:
            n += 1
        else:
            break
    return n


def finalize_week(week_data: dict[str, Any], action: str,
                  ai_note: str | None = None) -> dict[str, Any]:
    """把本周结果写入progress快照与weakness_tracker，落盘。"""
    week = week_data["week"]
    progress = week_data["progress"]
    skill = week.get("task", {}).get("skill_tag")
    rate = week_data["habit_execution_rate"]

    snapshot = {
        "week": week.get("week"),
        "date": date.today().isoformat(),
        "skill_tag": skill,
        "execution_rate": round(rate, 3),
        "rank": week_data.get("rank"),
        "action": action,
    }
    progress.setdefault("weekly_snapshots", []).append(snapshot)

    weakness = _skill_to_weakness(skill)
    tracker = progress.setdefault("weakness_tracker", {})
    if weakness in tracker:
        entry = tracker[weakness]
        entry["weeks_trained"] = entry.get("weeks_trained", 0) + 1
        entry.setdefault("execution_history", []).append(round(rate, 3))
        # current_level：以执行率为v1.0的习惯养成度代理指标
        entry.setdefault("level_history", []).append(entry.get("current_level", 0.0))
        if action == "advance":
            entry["status"] = "done"
            entry["current_level"] = 1.0
        elif action == "compensate":
            entry["status"] = "compensate"
        else:
            entry["current_level"] = round(
                max(entry.get("current_level", 0.0), rate), 3)
        entry["level_history"][-1] = entry["current_level"]

    week["ai_weekly_note"] = ai_note
    data_utils.save_weekly_training(week)
    data_utils.save_progress(progress)
    return snapshot


# ---------------------------------------------------------------------------
# 进度展示（--progress）
# ---------------------------------------------------------------------------

def ascii_chart(values: list[float], labels: list[str],
                width: int = 40, title: str = "") -> str:
    """横向条形ASCII图。"""
    if not values:
        return "（暂无数据）"
    lines = [title] if title else []
    vmax = max(values) or 1.0
    for label, v in zip(labels, values):
        bar = "█" * max(int(v / vmax * width), 1 if v > 0 else 0)
        lines.append(f"{label:>10} | {bar} {v:g}")
    return "\n".join(lines)


def render_progress(detail: bool = False, chart: bool = False) -> str:
    progress = data_utils.load_progress() or data_utils.default_progress()
    week = data_utils.load_weekly_training()
    out: list[str] = []

    task = (week or {}).get("task") or {}
    if task.get("description"):
        out.append(f"本周任务：{task['description']} "
                   f"（{task.get('current_streak', 0)}/{task.get('target_streak', 5)}，"
                   f"{task.get('status')}）")
    else:
        out.append("本周任务：未设置（--weekly-report 或 --checkin 会自动生成）")

    out.append("\n弱点追踪：")
    status_names = {"pending": "待训练", "in_progress": "训练中",
                    "done": "已养成", "compensate": "转补偿策略"}
    for name, e in progress.get("weakness_tracker", {}).items():
        out.append(f"  {name}: {status_names.get(e.get('status'), e.get('status'))}"
                   f"，已训练{e.get('weeks_trained', 0)}周"
                   f"，习惯养成度{e.get('current_level', 0.0):.0%}")

    snapshots = progress.get("weekly_snapshots", [])
    if chart and snapshots:
        rates = [s.get("execution_rate", 0.0) * 100 for s in snapshots]
        weeks = [s.get("week", "?") for s in snapshots]
        out.append("\n" + ascii_chart(rates, weeks, title="每周执行率（%）"))
        ranks = [s.get("rank") for s in snapshots]
        if any(r is not None for r in ranks):
            pairs = [(w, r) for w, r in zip(weeks, ranks) if r is not None]
            out.append("\n" + ascii_chart([r for _, r in pairs],
                                          [w for w, _ in pairs], title="分数走势"))
    if detail and snapshots:
        out.append("\n历史快照：")
        for s in snapshots:
            out.append(f"  {s.get('week')} [{s.get('skill_tag') or '-'}] "
                       f"执行率{s.get('execution_rate', 0):.0%} "
                       f"分数{s.get('rank') if s.get('rank') is not None else '-'} "
                       f"→ {s.get('action')}")
    return "\n".join(out)
