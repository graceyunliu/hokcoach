# -*- coding: utf-8 -*-
"""核心调度器（阶段2/3，tech spec 4.1.4流程）。

串联：replay_engine（归因）→ knowledge_engine（检索）→ constraints_engine
（兼容性检查）→ 组装 prompts/*.txt → LLM生成，并驱动：
- --replay <video> 全自动复盘（阶段0检测管线）
- --replay --manual 手动录入后的AI点评
- --chat 自由对话
- --weekly-report 周报（阶段3）

降级模式：未配置LLM API key时，输出规则层结果（归因+检索到的原则原文），
明确说明AI点评不可用——绝不编造点评。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional

from core import constraints_engine, knowledge_engine, replay_engine, training_engine
from core.llm_client import LLMClient, LLMError, VisionClient
from utils import config_utils, data_utils

BASE_DIR = Path(__file__).resolve().parent.parent
PROMPTS_DIR = BASE_DIR / "prompts"


def _interactive_possible() -> bool:
    try:
        return sys.stdin.isatty()
    except Exception:
        return False


def _ask_user(prompt: str) -> str:
    try:
        return input(f"{prompt}\nYou> ").strip()
    except EOFError:
        return ""


class Orchestrator:
    def __init__(self) -> None:
        self.config = config_utils.load_config()
        self.persona = config_utils.load_persona()
        self.llm: Optional[LLMClient] = LLMClient.from_config(self.config)
        self.vlm: Optional[VisionClient] = VisionClient.from_config(self.config)
        self.principles = knowledge_engine.load_all_principles()
        self.profile = data_utils.load_player_profile()

    # ------------------------------------------------------------------
    # 公共工具
    # ------------------------------------------------------------------

    def segment(self) -> str:
        p = (self.profile or {}).get("player") or {}
        if p.get("rank_type") and p.get("current_rank") is not None:
            return f"{p['rank_type']}{p['current_rank']}分"
        return "未知段位"

    def _constraints(self) -> dict[str, Any]:
        return ((self.profile or {}).get("player") or {}).get("constraints") or {}

    def llm_status_line(self) -> str:
        if self.llm is None:
            return ("[降级模式] 未配置LLM（config.yaml llm段 + 环境变量API key），"
                    "只输出规则层归因与知识库原文，无AI点评。")
        return f"[LLM] {self.llm.model}"

    # ------------------------------------------------------------------
    # 复盘点评（4.1.4步骤2-4）
    # ------------------------------------------------------------------

    def comment_death(self, detail: dict[str, Any],
                      user_intent: str | None = None) -> str:
        """对单次死亡生成教练点评：检索→约束检查→组prompt→LLM。"""
        death_type = detail.get("type") or "机制死"
        context_parts = []
        if detail.get("location"):
            if detail.get("location_source") == "minimap_x_marker":
                context_parts.append(f"死亡地点：{detail['location']}（系统死亡X标记直接读取）")
            else:
                context_parts.append(f"死亡地点：{detail['location']}")
        if detail.get("minimap_context"):
            context_parts.append(f"小地图：{detail['minimap_context']}")
        if detail.get("self_attribution"):
            context_parts.append(f"玩家自述：{detail['self_attribution']}")
        if user_intent:
            context_parts.append(f"玩家当时的意图：{user_intent}")
        if detail.get("classify_reason"):
            context_parts.append(f"归因依据：{detail['classify_reason']}")
        if not detail.get("evidence_sufficient", True):
            context_parts.append("注意：本次死亡的画面证据不足，归因置信度低。")
        context = "；".join(context_parts) or "（无额外上下文）"

        retrieved = knowledge_engine.retrieve_principles(
            death_type, context, principles=self.principles)
        compat = constraints_engine.check_compatibility(
            retrieved, self._constraints())

        prompt = (PROMPTS_DIR / "replay_analysis.txt").read_text(encoding="utf-8")
        filled = prompt.format(
            segment=self.segment(),
            death_time=detail.get("timestamp") or "未知",
            death_type=death_type,
            context_before=context,
            retrieved_principles=knowledge_engine.format_principles(retrieved),
            player_constraints=constraints_engine.format_constraints(
                self._constraints(), compat),
        )

        if self.llm is None:
            return self._fallback_comment(detail, retrieved)
        try:
            return self.llm.chat_text(system="", user=filled, temperature=0.7)
        except LLMError as e:
            print(f"[LLM调用失败，降级输出] {e}", file=sys.stderr)
            return self._fallback_comment(detail, retrieved)

    def _fallback_comment(self, detail: dict[str, Any],
                          retrieved: list[knowledge_engine.Principle]) -> str:
        lines = [
            f"归因：{detail.get('type')}（置信度{detail.get('confidence', 0):.0%}，"
            f"{detail.get('classify_reason', '')}）",
        ]
        if retrieved:
            lines.append("相关原则（知识库原文，非AI生成）：")
            lines += [f"  {p.format_for_prompt()}" for p in retrieved]
        else:
            lines.append("知识库暂无匹配原则条目。")
        lines.append("（AI点评不可用：未配置LLM。规则层结果如上，不做进一步推演。）")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # 复盘对话流程（5.2交互示例的文本版）
    # ------------------------------------------------------------------

    def review_replay(self, replay: dict[str, Any],
                      interactive: bool = True,
                      output: str | None = None) -> dict[str, Any]:
        """对一份replay记录跑复盘对话：只深入点评第一次死亡（persona原则：
        一次只说一个问题），其余死亡列出归因。落盘并可选导出报告。"""
        details = replay["death_analysis"]["details"]
        print(f"\nCoach> 这局你死了{replay['deaths']}次。", end="")
        if not details:
            print("零死亡——这局我们没什么好挑的，保持。")
            path = data_utils.save_replay(replay)
            print(f"Coach> [复盘记录已保存: {path.name}]")
            return replay
        print("我们只看第一次。")

        first = details[0]
        where = f"，地点{first['location']}" if first.get("location") else ""
        print(f"Coach> {first.get('timestamp', '?')}{where}，"
              f"初步归因是「{first.get('type')}」。")

        user_intent = None
        if interactive and _interactive_possible():
            user_intent = _ask_user("Coach> 你当时是想去干嘛？") or None

        comment = self.comment_death(first, user_intent=user_intent)
        first["ai_comment"] = comment
        if user_intent:
            first["user_intent"] = user_intent
        print(f"\nCoach> {comment}\n")

        if len(details) > 1:
            print("Coach> 其余死亡的归因（本次不展开）：")
            for d in details[1:]:
                print(f"  - {d.get('timestamp', '?')} {d.get('type')}"
                      f"（{d.get('classify_reason', '')}）")

        path = data_utils.save_replay(replay)
        print(f"\nCoach> [复盘记录已保存: {path.name}]")

        if output:
            self._write_report(replay, output)
            print(f"Coach> [复盘报告已导出: {output}]")
        return replay

    def _write_report(self, replay: dict[str, Any], output: str) -> None:
        lines = [
            f"# 复盘报告 {replay['replay_id']}",
            "",
            f"- 英雄：{replay.get('hero_played') or '未知'}",
            f"- 结果：{replay.get('game_result') or '未知'}",
            f"- 死亡：{replay.get('deaths', 0)}次",
            "",
        ]
        cats = replay["death_analysis"]["categories"]
        dist = "、".join(f"{k}×{v}" for k, v in cats.items() if v)
        if dist:
            lines.append(f"死亡分布：{dist}\n")
        for i, d in enumerate(replay["death_analysis"]["details"], 1):
            lines.append(f"## 第{i}次死亡 {d.get('timestamp', '?')}")
            lines.append(f"- 归因：{d.get('type')}（{d.get('classify_reason', '')}）")
            if d.get("location"):
                tag = "系统X标记" if d.get("location_source") == "minimap_x_marker" else "推断"
                lines.append(f"- 死亡地点：{d['location']}（{tag}）")
            if d.get("minimap_context"):
                lines.append(f"- 小地图：{d['minimap_context']}")
            if d.get("ai_comment"):
                lines.append(f"\n{d['ai_comment']}\n")
        Path(output).write_text("\n".join(lines) + "\n", encoding="utf-8")

    # ------------------------------------------------------------------
    # 入口1：视频全自动复盘
    # ------------------------------------------------------------------

    def analyze_video(self, video_path: str, interactive: bool = True,
                      output: str | None = None) -> int:
        from utils import video_utils

        if not Path(video_path).exists():
            print(f"找不到视频文件: {video_path}")
            return 1
        if self.vlm is None:
            print("视频自动复盘需要视觉模型读取HUD计数器（config.yaml llm.vision段"
                  "+ API key）。当前未配置，请先用 --replay --manual 手动录入。")
            return 1

        print("Coach> 正在分析你的回放...（HUD粗采样+二分定位，会有一会儿）")
        kda_reader = video_utils.make_vlm_kda_reader(self.vlm)
        events = video_utils.extract_death_events(video_path, kda_reader)
        print(f"Coach> 检测到{len(events)}次死亡。提取死亡前小地图轨迹...")

        contexts: list[str | None] = []
        for e in events:
            try:
                positions = video_utils.extract_minimap_positions(
                    video_path, around_ts=e["ts"])
                contexts.append(
                    video_utils.summarize_minimap_context(positions, e["ts"]))
            except RuntimeError as err:  # 缺opencv
                print(f"[minimap检测不可用] {err}", file=sys.stderr)
                contexts.append(None)

            # AGE-46: 死亡"X"标记是死亡地点的首选数据源（系统直接标注，
            # 优先级高于从敌方轨迹反推），与上面的敌方轨迹上下文互补。
            try:
                marker = video_utils.extract_death_location(video_path, e["ts"])
            except RuntimeError as err:  # 缺opencv
                print(f"[死亡标记检测不可用] {err}", file=sys.stderr)
                marker = None
            if marker is not None:
                e["location"] = marker["region"]
                e["location_source"] = marker["source"]
            else:
                e["location"] = None
                e["location_source"] = None

        replay = replay_engine.build_replay_from_video(
            video_path, events, contexts, llm=self.llm)
        p = (self.profile or {}).get("player") or {}
        replay["hero_played"] = p.get("target_hero")
        self.review_replay(replay, interactive=interactive, output=output)
        return 0

    # ------------------------------------------------------------------
    # 入口2：手动录入后的AI点评
    # ------------------------------------------------------------------

    def analyze_manual(self, replay: dict[str, Any], interactive: bool = True,
                       output: str | None = None) -> int:
        replay = replay_engine.classify_manual_replay(replay, llm=self.llm)
        self.review_replay(replay, interactive=interactive, output=output)
        return 0

    # ------------------------------------------------------------------
    # 入口3：自由对话（--chat）
    # ------------------------------------------------------------------

    def _chat_system_prompt(self) -> str:
        persona = (self.persona or {}).get("persona") or {}
        principles = persona.get("principles") or []
        p = (self.profile or {}).get("player") or {}
        recent = [data_utils.load_json(f) for f in data_utils.list_replays()[-3:]]
        recent_lines = []
        for r in recent:
            if not r:
                continue
            cats = r.get("death_analysis", {}).get("categories", {})
            dist = "、".join(f"{k}×{v}" for k, v in cats.items() if v)
            recent_lines.append(
                f"- {r.get('timestamp', '')[:10]} {r.get('hero_played') or '?'} "
                f"{'胜' if r.get('game_result') == 'victory' else '负'} "
                f"死亡{r.get('deaths', 0)}次 {dist}")
        return (
            "你是王者荣耀决策思维教练，风格对标抖音复盘博主「老娘」「打萌」。\n"
            "核心原则：\n" + "\n".join(f"- {x}" for x in principles) + "\n\n"
            f"学员档案：主玩{('/'.join(p.get('main_heroes') or [])) or '未知'}，"
            f"{self.segment()}，重点练{p.get('target_hero') or '未定'}。\n"
            "最近复盘：\n" + ("\n".join(recent_lines) or "（暂无复盘记录）") + "\n\n"
            "对话要求：口语化、一次只聊一个问题；判断要锚定事实，"
            "没有依据时明确说需要看回放确认，不编造。"
        )

    def chat(self, topic: str | None = None) -> int:
        if self.llm is None:
            print(self.llm_status_line())
            print("自由对话需要LLM，请在config.yaml配置后重试。")
            return 1
        print("Coach> 来了。想聊什么？（输入 exit 结束）")
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self._chat_system_prompt()}]
        if topic:
            messages.append({"role": "user", "content": f"我想聊聊：{topic}"})
            try:
                reply = self.llm.chat(messages)
            except LLMError as e:
                print(f"LLM调用失败：{e}")
                return 1
            messages.append({"role": "assistant", "content": reply})
            print(f"Coach> {reply}")
        while True:
            user = _ask_user("")
            if not user or user.lower() in ("exit", "quit", "退出"):
                print("Coach> 下次打完随时来找我。")
                return 0
            messages.append({"role": "user", "content": user})
            try:
                reply = self.llm.chat(messages)
            except LLMError as e:
                print(f"LLM调用失败：{e}")
                return 1
            messages.append({"role": "assistant", "content": reply})
            print(f"Coach> {reply}")

    # ------------------------------------------------------------------
    # 入口4：周报（--weekly-report，阶段3）
    # ------------------------------------------------------------------

    def weekly_report(self, output: str | None = None) -> int:
        wd = training_engine.collect_week_data()
        week = wd["week"]
        task = week.get("task") or {}
        if not task.get("description"):
            week = training_engine.assign_task_for_week()
            print(f"Coach> 本周还没有训练任务，先安排：{week['task']['description']}")
            wd = training_engine.collect_week_data()
            week, task = wd["week"], wd["week"]["task"]

        action, message = training_engine.weekly_assessment(wd)

        rank_change = "未知"
        if wd.get("rank") is not None and wd.get("last_week_rank") is not None:
            diff = wd["rank"] - wd["last_week_rank"]
            rank_change = f"{wd['last_week_rank']} → {wd['rank']}（{diff:+d}）"
        checkins = week.get("daily_checkins", [])
        checkin_str = "；".join(
            f"{c['date']} 执行率{c.get('rate', '-')}%"
            + (f"（{c['note']}）" if c.get("note") else "")
            for c in checkins) or "本周无打卡记录"

        report: str
        if self.llm is not None:
            template = (PROMPTS_DIR / "weekly_report.txt").read_text(encoding="utf-8")
            filled = template.format(
                task_description=task.get("description"),
                skill_tag=task.get("skill_tag"),
                daily_checkins=checkin_str,
                replay_summaries="；".join(wd["replay_summaries"]) or "本周无复盘",
                rank_change=rank_change,
                execution_rate_trend=(
                    f"{wd['execution_rate_last_week']:.0%} → "
                    f"{wd['habit_execution_rate']:.0%}"),
            )
            try:
                report = self.llm.chat_text(system="", user=filled)
            except LLMError as e:
                print(f"[LLM调用失败，输出数据版周报] {e}", file=sys.stderr)
                report = self._fallback_weekly(wd, action, message, checkin_str,
                                               rank_change)
        else:
            report = self._fallback_weekly(wd, action, message, checkin_str,
                                           rank_change)

        print(f"\n===== 周报 {week.get('week')} =====\n")
        print(report)
        print(f"\n[评估结论] {action}: {message}")

        snapshot = training_engine.finalize_week(wd, action, ai_note=report)

        # 按评估结论安排下周任务
        skill = task.get("skill_tag")
        if action == "advance":
            new_week = training_engine.assign_task_for_week()
            print(f"[下周任务] 进阶：{new_week['task']['description']}")
        elif action == "compensate":
            progress = data_utils.load_progress() or {}
            nxt = training_engine.pick_next_weakness(
                progress, exclude={skill} if skill else set())
            new_week = training_engine.assign_task_for_week(weakness=nxt)
            print(f"[下周任务] 「{skill}」转补偿策略（找教练--chat聊补偿打法），"
                  f"训练重心换到：{new_week['task']['description']}")
        elif action == "change_method":
            print(f"[下周任务] 继续「{task.get('description')}」，"
                  f"但换个练法——用--chat和教练商量新的角度。")
        else:
            print(f"[下周任务] 继续：{task.get('description')} "
                  f"（{task.get('current_streak', 0)}/{task.get('target_streak', 5)}）")

        if output:
            Path(output).write_text(
                f"# 周报 {snapshot.get('week')}\n\n{report}\n\n"
                f"评估结论：{action} — {message}\n", encoding="utf-8")
            print(f"[周报已导出: {output}]")
        return 0

    def _fallback_weekly(self, wd: dict[str, Any], action: str, message: str,
                         checkin_str: str, rank_change: str) -> str:
        return (
            f"本周执行率：{wd['habit_execution_rate']:.0%}"
            f"（上周{wd['execution_rate_last_week']:.0%}）\n"
            f"打卡：{checkin_str}\n"
            f"复盘：{'；'.join(wd['replay_summaries']) or '本周无复盘'}\n"
            f"分数：{rank_change}\n"
            f"（AI周报不可用：未配置LLM，以上为数据版摘要。）"
        )
