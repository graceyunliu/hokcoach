# 宏观基本功原则库（Tier 1/2 专用）

> 规则：Tier 3（风格化/有争议）条目**禁止**写入本文件，只能进偶像标准层并标注归属创作者。
> 每条需带：tier / source / valid_as_of_patch / last_reviewed。
> 冷启动目标：30-50条起步；里程碑2前至少备好10-20条（实现计划v1.0第三节）。

## 示例条目

- **[vision_001]** 打野在小地图消失超过15秒后，路过任何未插眼草丛前应假设其可能在附近
  - tier: 2_converged_consensus
  - tags: 探草死, 视野
  - applies_when: jungler_missing_duration_sec > 15
  - requires_capability: null
  - source: 老娘_vod_23, 打萌_vod_08, 社区共识
  - valid_as_of_patch: 3.85
  - last_reviewed: 2026-08-12

<!-- 待冷启动填充：转录管线（utils/transcript_utils.py）+ 用户人工tier判定 -->
