# AGE-239：可靠的小地图小兵/防御塔证据提取方案

作者：Manus AI  
日期：2026-08-26  
状态：技术方案，等待真实录屏标注验证

## 结论摘要

AGE-239 当前在 Linear 中仍为 **Backlog**，并保留对 AGE-235 的阻塞关系；AGE-235 实际已经完成，但 AGE-239 的方案选择仍未被真实录屏验证。当前仓库已经具备小地图裁剪、固定 UI 排除区、红蓝英雄图标检测、玩家绿色外环识别、轨迹采样和“证据不足即不下结论”的基础能力，但尚未具备可靠的小兵/防御塔对象检测。

建议不要直接把所有红蓝小色块当作小兵或防御塔，也不要把“靠近兵线”直接等同于“贪线死”。推荐采用 **分层、时间一致性、多信号门控** 的方案：先用模板/颜色/几何候选产生低承诺的对象轨迹，再用固定结构识别防御塔、用移动集群识别小兵波，最后只有在至少两个相互独立的信号同时支持时，才把 `pushing_wave` 置为 `True`。任何信号覆盖不足、对象身份冲突或团战并发场景都应返回 `None`，并把原因写入 evidence ledger。

## 当前状态与真实缺口

AGE-239 的验收描述给出了两条路线：若游戏界面存在专用的“补刀/推塔”按钮，优先检测按钮按下状态；否则使用小兵/防御塔位置、攻击方向和防御塔血条变化的组合信号。[1] 当前实现的 `extract_minimap_positions()` 只输出敌我英雄和玩家身份，`find_static_red_blue_zones()` 还会主动排除长期固定的防御塔等 UI 元素；这对英雄检测是正确的，但意味着不能直接复用排除后的英雄候选去识别防御塔。[2]

因此，AGE-239 目前不是“补一个布尔判断”的问题，而是需要新增一个独立的 **minimap object evidence layer**，并在它和死亡归因之间保留来源、时间、置信度和未知状态。

## 推荐架构

| 层 | 输入 | 输出 | 关键原则 |
|---|---|---|---|
| 原始对象候选 | 未套用英雄排除区的小地图帧 | 红/蓝对象候选、尺寸、形状、颜色、位置 | 先保留候选，不提前命名 |
| 防御塔识别 | 跨帧位置、模板/几何、固定性 | 塔对象轨迹、所属方、状态候选 | 长期固定是必要条件，不是充分条件 |
| 小兵波识别 | 小对象候选、短轨迹、 lane corridor | 波方向、集群数量区间、持续时间 | 需要连续帧和集群行为，单帧不结论 |
| 行为融合 | 玩家位置、攻击/按钮、塔状态、英雄战斗状态 | `pushing_wave: True/False/None` | 至少两个独立信号才确认 |
| 教练证据输出 | 融合结果与失败原因 | evidence ledger / coaching context | 把“为什么不能确认”告诉教练 |

### 1. 候选提取：与英雄检测分离

新增函数建议命名为 `detect_minimap_object_candidates(image, crop, exclude_zones=None)`。它应在固定 UI 排除之前保留原始红/蓝连通域，并输出：`cx`、`cy`、面积、宽高、长宽比、extent、平均 HSV、颜色侧、帧时间和原始 mask 版本。英雄检测继续使用现有 `detect_hero_icons()`，防御塔/小兵检测不应把英雄排除区当作唯一真值。

颜色阈值只能生成候选。候选要经过尺寸分层：小兵通常形成多个相近尺寸的小对象，防御塔通常较大且位置稳定；但具体阈值必须从目标录屏标定，不应写死成未经验证的“通用像素值”。

### 2. 防御塔识别：固定位置 + 外观状态

在视频开头或稳定窗口采样 6–10 个时间点，建立静态候选位置簇。只有在位置跨多个相隔时间点重复出现、空间抖动小于标定半径、且形状/颜色模板相似时，候选才进入 `tower_map`。这一步复用现有 `_cluster_positions()` 思路，但要保留“固定结构候选”而不是把它们直接删除。[2]

塔的“存在/未被摧毁”应使用时间状态序列确认：若候选在多个窗口持续存在，则标记为 `present`; 若从稳定存在变为持续消失，只能输出 `possibly_destroyed`，除非另有可靠的塔血条或系统播报证据。塔附近发生玩家死亡不应自动产生 `pushing_wave=True`。

### 3. 小兵波识别：移动集群 + 兵线走廊

对未被识别为固定结构的较小候选，使用保守的短轨迹关联。相邻采样点只接受唯一最近邻，且位移不能超过按录屏帧率标定的上限。把同方向、相近速度、位于同一条 lane corridor 的至少两个候选聚成 wave candidate；要求候选在至少三个连续采样点中可见，或者在两个采样点中伴随明确的攻击/目标证据。

输出不应伪装成精确小兵数量，建议使用区间和质量字段：

```json
{
  "lane": "top|mid|bottom|unknown",
  "side": "ally|enemy|unknown",
  "count_estimate": {"min": 2, "max": 5},
  "direction": "toward_enemy|toward_ally|unknown",
  "persistence_samples": 3,
  "confidence": 0.72,
  "source": "minimap_cluster_track",
  "limitations": []
}
```

### 4. `pushing_wave` 的多信号门控

建议新增 `infer_pushing_wave(evidence)`，但返回值必须是三态布尔：`True`、`False`、`None`。推荐门控如下：

| 支持信号 | 权重/性质 | 说明 |
|---|---:|---|
| 补刀/推塔按钮按下且模板匹配稳定 | 强独立信号 | 若 AGE-235 真实核实存在，应优先采用 |
| 小兵波在同一 lane corridor 连续出现 | 中强 | 仅代表附近存在兵线，不代表玩家正在清线 |
| 玩家位置与小兵波/塔距离稳定 | 中 | 需要连续时间窗口，不能只用死亡瞬间一帧 |
| 塔状态或血条持续变化 | 强独立信号 | 需要排除队友/其他单位造成的变化 |
| 攻击方向指向小兵/塔 | 中 | 团战中容易与英雄目标冲突 |
| 同时存在可见英雄交战 | 反向/降级 | 产生“团战中顺便清兵”边界状态 |

只有“强信号”或“两项以上中强信号”同时成立时才返回 `True`。若仅有小地图附近小兵，返回 `None`；若覆盖充分且明确没有兵线/塔目标，才允许返回 `False`。团战窗口若同时检测到英雄交战和兵线候选，返回 `None` 并记录 `mixed_combat_and_wave`，不要强行归类为贪线死。

### 5. 与现有 replay/evidence contract 的接入

建议将结果放进死亡 detail，而不是只写一个布尔值：

```json
{
  "pushing_wave": null,
  "minimap_object_evidence": {
    "towers": [],
    "wave_candidates": [],
    "decision": "unknown",
    "reason_codes": ["mixed_combat_and_wave"],
    "coverage": 0.67,
    "source": "minimap_object_layer"
  }
}
```

`build_evidence_ledger()` 应将其呈现为“检测到兵线候选，但团战同时发生，无法确认玩家死亡是否由贪线导致”，而不是显示一个没有解释的“贪线死”。只有 `pushing_wave=True` 才允许现有分类器使用“贪线死”规则；`None` 继续进入其他规则或证据不足分支。

## 真实录屏验证计划

当前仓库没有足以验证小兵/防御塔阈值的真实标注数据，因此不能诚实地声称方案 B 已完成。需要准备至少三类短片段：纯清线、纯推塔、团战中顺便清线；每类至少包含一个死亡窗口和一个非死亡窗口。每个片段标注玩家目标、兵线 lane、塔状态、是否发生英雄交战和最终 `pushing_wave` 标签。

验收指标应分开统计“对象检测”和“教练归因”：对象层报告 tower precision/recall、wave precision/recall、轨迹连续性；教练层报告 `贪线死` precision、unknown abstention rate、团战误报率。宁可让 unknown rate 偏高，也不要把团战误报为贪线死，因为错误的训练任务会直接把玩家带向错误的练习方向。

## 建议实施顺序

第一步是把原始 minimap object candidates 从英雄排除逻辑中独立出来，并增加可视化 debug overlay。第二步是实现静态塔候选和小兵短轨迹关联，但只输出候选证据。第三步是实现三态多信号门控和 evidence ledger 接口。第四步才是接入死亡分类器和训练选择。每一步都应有合成图像单元测试，并在真实录屏标注集上做离线评估；没有真实录屏时，不应关闭 AGE-239。

## 参考资料

[1]: https://linear.app/agentjuanjuan/issue/AGE-239/实现贪线死推塔清兵检测依赖ui核实含降级方案 "Linear AGE-239：实现贪线死/推塔清兵检测"
[2]: https://github.com/graceyunliu/hokcoach/blob/main/coach/utils/video_utils.py "hokcoach video_utils.py"
[3]: https://github.com/graceyunliu/hokcoach/blob/main/coach/core/replay_engine.py "hokcoach replay_engine.py"
[4]: https://linear.app/agentjuanjuan/issue/AGE-235/人工核实三个ui假设阻塞多张检测实现票 "Linear AGE-235：人工核实三个 UI 假设"

## References

[1] [AGE-239](https://linear.app/agentjuanjuan/issue/AGE-239/实现贪线死推塔清兵检测依赖ui核实含降级方案)  
[2] [video_utils.py](https://github.com/graceyunliu/hokcoach/blob/main/coach/utils/video_utils.py)  
[3] [replay_engine.py](https://github.com/graceyunliu/hokcoach/blob/main/coach/core/replay_engine.py)  
[4] [AGE-235](https://linear.app/agentjuanjuan/issue/AGE-235/人工核实三个ui假设阻塞多张检测实现票)
