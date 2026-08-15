# -*- coding: utf-8 -*-
"""数据情报管线主流程：双周巡检 → 起草知识库更新草案（不自动合并）。

流程：
    1. 检索层（GLM + web_search插件）按 sources.SOURCE_QUERIES 逐条查询，
       GLM能直接访问中文网站（官网/百科/论坛/视频平台相关页面）。
    2. 读取现有知识库条目id，避免起草层重复造重复条目。
    3. 起草层（DeepSeek）把检索到的原始材料整理成符合 macro_principles.md
       条目schema的草案，标注 status: pending_review / change_type。
    4. 写入 knowledge_base/_pending_updates/{date}_proposal.md，
       追加 CHANGELOG.md 一行摘要。绝不直接改 macro_principles.md 等正式文件
       ——由人工审核后手动合并（见 _pending_updates/README.md）。

用法：
    export ZHIPU_API_KEY=...
    export DEEPSEEK_API_KEY=...
    cd coach && python -m intake.run_intake

GitHub Actions 用法见 .github/workflows/hok-intake.yml（双周定时触发，
运行结束后把新增的 _pending_updates/*.md 提交到一个新分支并开PR）。
"""

from __future__ import annotations

import datetime as _dt
import sys
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent  # coach/
sys.path.insert(0, str(BASE_DIR))  # 允许 `python -m intake.run_intake` 之外的直接运行

from core.knowledge_engine import load_all_principles  # noqa: E402
from intake.draft_client import draft_client_from_config  # noqa: E402
from intake.glm_search import GLMSearchClient, GLMSearchError  # noqa: E402
from intake.qwen_search import QwenSearchClient, QwenSearchError  # noqa: E402
from intake.search_types import SearchResult  # noqa: E402
from intake.sources import CATEGORY_LABEL, SOURCE_QUERIES  # noqa: E402
from utils.config_utils import load_config  # noqa: E402

PENDING_DIR = BASE_DIR / "knowledge_base" / "_pending_updates"
CHANGELOG_PATH = PENDING_DIR / "CHANGELOG.md"

NO_FINDINGS_MARKER = "本次巡检未发现需要收录的变化"

DRAFT_SYSTEM_PROMPT = """\
你是王者荣耀AI教练项目的知识库情报助理。你会收到最近两周内多条搜索结果原始材料
（来自官方渠道/社区百科/社媒论坛/主播职业选手内容），任务是把其中值得收录进
知识库的内容整理成条目草案。

知识库条目格式（严格照抄这个格式，一条不少）：

- **[临时id]** 条目正文（讲清楚具体机制/原则/改动是什么，包含具体数值就写数值）
  - tier: 1_mechanical_fact | 2_converged_consensus | 3_contested_style
  - tags: 逗号分隔的标签（如 探草死, 视野 / 越塔, 机制死 等，没有合适标签可留空）
  - applies_when: 什么情况下适用（没有就填 null）
  - requires_capability: 需要的操作/沟通能力（没有就填 null）
  - source: 具体来源（人名/账号/平台+可能的话链接，如实写，不许编造）
  - valid_as_of_patch: 对应的版本号，不确定就写你判断的大致时间
  - last_reviewed: 今天的日期
  - status: pending_review
  - change_type: new | update | deprecate（分别对应：全新条目 / 建议更新某条现有条目
    / 建议废弃某条现有条目；update和deprecate必须额外写一行 `updates_id: <现有条目id>`
    并指出理由）

硬规则：
1. tier分级要严谨。tier 1 = 官方数值/机制事实（如伤害公式、冷却时间、防御塔机制）。
   tier 2 = 广泛认同的宏观打法共识（多个信源独立印证）。tier 3 = 单一主播/选手的
   个人风格化建议或存在争议的打法，仍然可以起草，但必须标 tier: 3_contested_style，
   这类条目不会进正式的 macro_principles.md（那里硬性禁止tier3），只作为素材保留。
2. 未经官方确认的传闻/爆料，在正文里明确写"（未经官方确认）"，不要写得像已实锤。
3. 只整理搜索材料里实际出现的信息，不要为了凑数编造内容。
4. 已经在"现有知识库条目"里出现过的内容不要重复起草；如果搜到的信息是对现有条目
   的补充/修正，用 change_type: update 并指出 updates_id。
5. 如果通读全部材料后确实没有任何值得收录的新内容，只输出这一行，不要输出任何条目：
   本次巡检未发现需要收录的变化
6. 除了条目本身，不要输出多余的开场白/总结语。
"""


def format_search_material(results: list[SearchResult],
                           queries: list[tuple[str, str]]) -> str:
    parts = []
    for (category, query), r in zip(queries, results):
        label = CATEGORY_LABEL.get(category, category)
        block = [f"### [{label}] 查询：{query}"]
        if r is None:
            block.append("（本条查询失败，跳过）")
        else:
            if r.engine == "qwen":
                block.append("（本条由Qwen兜底检索，GLM当次失败/无结果）")
            if r.answer:
                block.append(f"综合回答：{r.answer}")
            for h in r.hits:
                block.append(f"- 命中网页：{h.title} | {h.link} | {h.snippet}")
            if not r.answer and not r.hits:
                block.append("（未检索到相关内容）")
        parts.append("\n".join(block))
    return "\n\n".join(parts)


def format_existing_ids(config: dict[str, Any]) -> str:
    try:
        principles = load_all_principles()
    except Exception as e:  # noqa: BLE001 — 知识库暂缺不应中断情报管线
        return f"（读取现有知识库失败，忽略去重: {e}）"
    if not principles:
        return "（知识库当前为空）"
    lines = [f"- {p.id}: {p.text[:60]}" for p in principles]
    return "\n".join(lines)


def _search_with_fallback(query: str, category: str, *, recency_days: int,
                          glm_client: GLMSearchClient,
                          qwen_client: QwenSearchClient | None) -> SearchResult | None:
    """先用GLM检索；GLM报错或返回空结果时，有配置Qwen就兜底重试一次。

    GLM的web_search插件是主检索源（返回结构化命中网页列表，信息更丰富）；
    Qwen只在GLM"挂了"或"这条查完全没找到东西"时才顶上，且顶上的结果也
    会在草案里如实标注是Qwen查到的，不冒充GLM结果。
    """
    try:
        r = glm_client.search(query, recency_days=recency_days)
        if not r.is_empty():
            print(f"  ✓ [{category}][glm] {query} — 命中{len(r.hits)}条网页")
            return r
        glm_failed_reason = "GLM返回空结果"
    except GLMSearchError as e:
        glm_failed_reason = str(e)

    if qwen_client is None:
        print(f"  ✗ [{category}][glm] {query} — {glm_failed_reason}（未配置Qwen兜底）",
              file=sys.stderr)
        return None

    try:
        r = qwen_client.search(query, recency_days=recency_days)
        if r.is_empty():
            print(f"  ✗ [{category}][glm→qwen] {query} — GLM({glm_failed_reason})"
                  f"和Qwen兜底均无结果", file=sys.stderr)
            return None
        print(f"  ⚠ [{category}][qwen兜底] {query} — GLM失败({glm_failed_reason})，"
              f"Qwen兜底命中{len(r.hits)}条网页")
        return r
    except QwenSearchError as e:
        print(f"  ✗ [{category}][glm→qwen] {query} — GLM({glm_failed_reason})和"
              f"Qwen兜底({e})均失败", file=sys.stderr)
        return None


def run(config: dict[str, Any] | None = None) -> int:
    config = config if config is not None else load_config()
    lookback_days = int(((config.get("intake") or {}).get("lookback_days")) or 14)

    search_client = GLMSearchClient.from_config(config)
    if search_client is None:
        print("[intake] 缺少检索层配置（ZHIPU_API_KEY未设置或config.yaml intake.search"
              "不完整），中止。", file=sys.stderr)
        return 1
    qwen_fallback_client = QwenSearchClient.from_config(config)
    if qwen_fallback_client is None:
        print("[intake] 未配置Qwen兜底（DASHSCOPE_API_KEY/视觉层key均未设置），"
              "GLM单条查询失败时将直接跳过该查询，不影响正常运行。")
    draft_client = draft_client_from_config(config)
    if draft_client is None:
        print("[intake] 缺少起草层配置（DEEPSEEK_API_KEY未设置或config.yaml intake.draft"
              "不完整），中止。", file=sys.stderr)
        return 1

    print(f"[intake] 开始检索，共{len(SOURCE_QUERIES)}条查询，回看{lookback_days}天……")
    results: list[SearchResult | None] = []
    ok_count = 0
    fallback_count = 0
    for category, query in SOURCE_QUERIES:
        r = _search_with_fallback(query, category, recency_days=lookback_days,
                                  glm_client=search_client,
                                  qwen_client=qwen_fallback_client)
        results.append(r)
        if r is not None:
            ok_count += 1
            if r.engine == "qwen":
                fallback_count += 1

    if ok_count == 0:
        print("[intake] 所有查询均失败，中止（不生成草案，避免用空结果误导起草层）。",
              file=sys.stderr)
        return 1
    if fallback_count:
        print(f"[intake] 其中{fallback_count}条查询由Qwen兜底完成。")

    material = format_search_material(results, SOURCE_QUERIES)
    existing = format_existing_ids(config)

    user_prompt = (
        f"现有知识库条目（避免重复起草）：\n{existing}\n\n"
        f"本次搜索到的原始材料：\n{material}\n\n"
        "请按系统提示的格式和规则输出草案。"
    )

    print("[intake] 检索完成，交给起草层整理草案……")
    try:
        draft_text = draft_client.chat_text(DRAFT_SYSTEM_PROMPT, user_prompt,
                                            temperature=0.3)
    except Exception as e:  # noqa: BLE001
        print(f"[intake] 起草层调用失败: {e}", file=sys.stderr)
        return 1

    today = _dt.date.today().isoformat()
    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    proposal_path = PENDING_DIR / f"{today}_proposal.md"

    sources_consulted = "、".join(
        f"{CATEGORY_LABEL.get(c, c)}«{q}»" for c, q in SOURCE_QUERIES
    )
    header = (
        f"# {today} 版本情报草案\n\n"
        f"> 由 intake/run_intake.py 自动生成，**未经人工审核，不会被知识引擎加载**。\n"
        f"> 检索范围：回看{lookback_days}天。\n"
        f"> 本次核查过的信源查询：{sources_consulted}\n\n"
        "---\n\n"
    )
    proposal_path.write_text(header + draft_text.strip() + "\n", encoding="utf-8")
    print(f"[intake] 草案已写入 {proposal_path}")

    has_findings = NO_FINDINGS_MARKER not in draft_text
    new_count = draft_text.count("- **[")
    summary = (
        f"发现约{new_count}条待审内容" if has_findings else "未发现需要收录的变化"
    )

    changelog_line = (
        f"\n## {today}\n"
        f"- 信源: {sources_consulted}\n"
        f"- 检索成功: {ok_count}/{len(SOURCE_QUERIES)} 条查询\n"
        f"- 发现: {summary}\n"
        f"- 草案文件: {proposal_path.name}\n"
    )
    with open(CHANGELOG_PATH, "a", encoding="utf-8") as f:
        f.write(changelog_line)
    print(f"[intake] CHANGELOG已更新: {summary}")

    return 0


def main() -> int:
    return run()


if __name__ == "__main__":
    sys.exit(main())
