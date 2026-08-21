# AGE-200 Research Spike：死亡前走位轨迹可视化（小地图轨迹图）

**日期：** 2026-08-21  
**性质：** 调研/范围界定，不包含前后端实现  
**结论摘要：** 当前 API 和保存的 replay JSON **没有任何路径返回原始小地图坐标**。更关键的是，当前检测结果不是“玩家走位轨迹”：`extract_minimap_positions()`只保留每个采样时刻的**敌方候选点集合**，己方只保留数量，不保留蓝方坐标，也没有跨帧身份关联。因此，AGE-197 mock 中的“玩家死亡前 15 秒移动路径”不是“把已有数组序列化出来”就能完成；它需要先补检测数据契约、玩家身份/轨迹关联、质量标记和持久化设计。完成这些后，前端画图本身较便宜。

## 先纠正一项已过时的前提

工单背景把 `extract_minimap_positions()` 的返回值概括为逐点的 `{timestamp, team, cx, cy}`。当前 `main` 上实际返回结构是：

```json
[
  {
    "ts": 123.0,
    "enemies": [
      {"cx": 237.0, "cy": 39.0, "area": 320, "region": "右上区域"}
    ],
    "enemy_visible_count": 1,
    "ally_visible_count": 3
  }
]
```

依据：`coach/utils/video_utils.py:532-578`。`detect_hero_icons()`确实同时计算 `enemies` 和 `allies`（`476-529`），但 `extract_minimap_positions()`只序列化 `icons["enemies"]`，对 allies 只保存 count（`571-575`）。因此：

- 没有 `team` 字段，而是每帧一个 `enemies` 数组；
- 没有 `timestamp` 字段，而是 `ts`；
- 没有玩家坐标；
- 没有说明某个敌方点在下一帧仍是同一个英雄的 track ID；
- 目前最多能称为“15 秒内按时间采样的敌方可见候选点”，不能称为玩家移动轨迹。

## 1. API/持久化数据流

### 当前真实调用链

1. `Orchestrator.build_replay_from_video_path()`逐个死亡事件调用 `extract_minimap_positions(video_path, around_ts=e["ts"])`（`coach/core/orchestrator.py:389-392`）。
2. 返回的 `positions` 立即传给 `summarize_minimap_context()`（`393-394`）。后者只保留首/中/尾最多三个采样点，并压成中文字符串（`coach/utils/video_utils.py:581-601`）。
3. `positions` 局部变量在本轮循环结束后丢失。传给 `replay_engine.build_replay_from_video()`的只有 `contexts: list[str|None]`（`coach/core/orchestrator.py:388, 417-418`）。
4. `build_replay_from_video()`在 death detail 中只写 `minimap_context: str|None`，另写死亡地点的粗粒度 `location` 和 `location_source`（`coach/core/replay_engine.py:140-183`）。默认 replay schema 也没有轨迹字段（`coach/utils/data_utils.py:135-148`）。
5. 后台 job 通过 `finalize_review_all()`保存这个 replay（`coach/api/jobs.py:99-108`；`coach/core/orchestrator.py:226+`）。
6. `GET /replay/{replay_id}`只是读取并原样返回保存的 JSON（`coach/api/routers/replay.py:76-82`）。`GET /replays`是摘要列表，也不含 death detail 坐标（`65-73`）。`/video`只返回原视频字节，不返回分析中间结果。

**结论：今天没有端点能够返回 raw positions，也没有可绕过的隐藏保存路径。必须新增后端序列化/持久化工作。** 单纯扩展 GET endpoint 没用，因为原始坐标在生成 replay 时已经被丢弃。

### 建议的数据契约方向

不要把当前内部数组不加版本地直接塞进 replay。建议在每个 death detail 下新增带版本和质量信息的结构，例如：

```json
{
  "minimap_trajectory": {
    "schema_version": 1,
    "coordinate_space": {"kind": "minimap_crop_px", "width": 420, "height": 320},
    "window": {"start_ts": 123.0, "end_ts": 138.0, "sample_interval_sec": 3.0},
    "player_track": null,
    "enemy_observations": [],
    "death_marker": {"cx": 100.0, "cy": 240.0, "source": "minimap_x_marker"},
    "quality": {"status": "insufficient", "warnings": ["player_not_identified"]}
  }
}
```

实际 build ticket 需要先决定产品到底画“玩家路径”“敌方可见轨迹”还是两者。三者的数据要求不同。若目标坚持为玩家路径，必须让检测层保留 allies 并识别哪个蓝色图标是玩家本人；当前代码不具备该能力。

## 2. 坐标系统与静态地图映射

### 当前坐标含义

- `config.yaml video.minimap_crop` 当前为 `{x: 0, y: 0, w: 420, h: 320}`（`coach/config/config.yaml:51-52`）。fallback 相同（`coach/utils/video_utils.py:42-44`）。
- ffmpeg 先从已按视频 rotate 元数据归一化的完整帧裁出这个区域；`detect_hero_icons()`返回的 `cx/cy`是**裁剪图内部像素坐标**，原点是 crop 左上角，不是完整视频坐标，也不是游戏地图的世界坐标。
- 若需要还原到完整帧坐标，公式是 `frame_x = crop.x + cx`、`frame_y = crop.y + cy`。当前 crop 的 x/y 恰好都是 0，但不能把这个偶然值固化为协议。
- 若只是映射到一个与 crop 完全同投影、同边界的前端图片，先归一化：`u = cx / crop.w`、`v = cy / crop.h`，再映射为 `display_x = u * rendered_width`、`display_y = v * rendered_height`。

### 不能只按 420×320 拉伸一张“标准地图”

420×320 是**屏幕裁剪矩形**，不等于可玩地图的规范宽高比。裁剪可能包含透明边距、圆角/遮罩、UI装饰；一张第三方或不同版本的静态地图也可能有不同留白、旋转或透视。仓库内目前没有可复用的静态 minimap 底图资产。

前端要可靠叠加，需要 build ticket 明确以下之一：

1. **同源裁剪底图方案（最低错位风险）：** 保存/生成一个与检测帧同尺寸的 minimap crop 作为底图，并在 420×320 坐标系直接叠加。缺点是底图含实时战争迷雾/UI，且增加图片持久化和隐私/存储设计。
2. **规范静态图方案：** 提供版本化地图 asset，并标定 crop 中“有效地图矩形/多边形”到 asset 的仿射或透视变换。至少需要可验证的地标对应点；不能默认整张 crop 等比例缩放。

无论哪种方案，API 都应把 `width/height`（最好还包括 crop/asset version）与点一起保存。不要让前端读取它自己的硬编码 `420×320`，因为阶段0结论已明确不同设备分辨率/UI版本需要重新标定（`阶段0验证结论.md:62`）。

## 3. 敌方观测与死亡 X 标记如何组合

两个检测器共享 crop 像素坐标系，但语义、时段和数据形状不同：

| 信号 | 时段 | 当前形状 | 含义 |
|---|---|---|---|
| `extract_minimap_positions()` | 死亡前 15 秒，默认每 3 秒 | 每帧多个 `enemies` 候选 | 当时视野内的敌方可见点；不是已关联轨迹 |
| `extract_death_location()` | HUD counter 确认死亡后的窗口 | 单个 `{region,cx,cy,ts_offset,source}` 或 `None` | 游戏自己画出的死亡 X 候选 |

推荐视觉语义：

- X-marker 单独画成“死亡点”，不要把它作为运动折线的最后一个普通点；它是死亡后 UI 标记，时间语义不同。
- 移动路径只连接同一 `track_id` 的、按时间排序且通过质量门槛的观测；不可把每帧“最近的红点”直接串起来。
- 视野缺失/检测缺失应显示为路径断点或虚线间隙，不要插值成确定路径。
- 没有可靠 X-marker 时不画精确死亡点，只显示粗粒度 `location` 文案或“死亡点未确认”。不要用最后一个敌方位置冒充玩家死亡位置。

当前数据形状有两处必须补齐：

1. `extract_death_location()`实际返回精确 `cx/cy`（`coach/utils/video_utils.py:937-944`），但 orchestrator 只抄 `region` 和 `source` 到 event（`coach/core/orchestrator.py:409-411`），所以精确死亡点也在保存前被丢弃。
2. 轨迹侧是一帧多点、无身份；marker 侧是一个点。必须先生成 track/observation 模型，不能让前端猜关联。

还应让一次视频的轨迹检测和 marker 检测复用同一份 `static_zones`。当前 `extract_minimap_positions()`未传时会自己计算一次（`video_utils.py:543-555`），而 orchestrator 调用 `extract_death_location()`时没有传 `static_zones`（`orchestrator.py:403-405`），既重复/缺失过滤语义，也增加不一致风险。

## 4. 原始坐标的可靠性与误导风险

**直接绘制当前 raw points 有较高概率给出“看起来很确定、实际关联错误”的战术图，不建议。**

已有证据：

- 阶段0只在少量时间点验证了红/蓝可见性和大致连通域检测，明确把连续坐标追踪列为未覆盖问题，并说明 crop 对设备/UI版本敏感（`阶段0验证结论.md:23-32, 60-62`）。
- 后续 AGE-47 真实录屏验证证明坐标信号可提取：一条候选从 `(237,39)`移动到`(239,122)`，方向与已知事件吻合（`阶段2补充验证结论_AGE47_AGE48.md:20-24`）。所以“完全不可做”不是结论。
- 同一验证也发现敌方塔/水晶会因相同红色圆环生成长而稳定的**假轨迹**；单帧图标可能拆成两个邻近分量，贪心关联会产生大量 3–8 点“幽灵轨迹”（同文档 `26-29`）。
- 当前代码后来增加了 `find_static_red_blue_zones()`和 `exclude_zones`，会用跨视频采样的固定位置过滤塔/buff/UI（`video_utils.py:407-468, 485-487, 554-555`），因此 AGE-47 的“完全没有静态过滤”结论已部分过时。不过它仍不是轨迹关联算法，也没有同帧去重、track ID、速度/跳变约束或玩家身份识别。
- `detect_hero_icons()`在一方候选超过 5 个时把整方结果清空（`video_utils.py:523-526`）。下游目前无法区分“真实无视野”和“这一帧因异常被质量门禁丢弃”，但可视化对两者应有不同表达。
- 隐身、草丛、战争迷雾导致敌方图标不可见是预期行为（`video_utils.py:480-487, 547-552`）。因此即使检测完美，敌方路径天然是不连续的观测，不是完整真实运动。
- X-marker 是独立问题。AGE-131 旧案例在第二份录屏上把无锚点扫描从约 44/62 误报降到 8/62，仍残留静态噪声（`AGE-131_AGE-136_case_study.md:11`）。当前代码已经落地更强的 counter-window 锚定、多帧基线、位置持续性和黑名单上限，并在 docstring 诚实记录约 7% crop 黑名单覆盖可能造成漏检（`video_utils.py:724-786`）。但生产 orchestrator 目前没有传 `respawn_reader`，所以已标定的复活倒计时共现特征并未在该调用链启用；函数仍退化为特征 1+2。

### 建议的质量门槛

实际 build ticket 至少应定义：

- 每帧检测状态：`observed | no_vision | rejected | decode_failed`；
- 同帧邻近分量去重；
- track association（最近邻不够，至少要有最大速度/跳变门槛；多目标可考虑匈牙利匹配）；
- track 置信度、最少连续点数、最大允许空档；
- player identity 的来源与置信度；
- marker 的验证层级（counter anchored、baseline confirmed、persistence confirmed、respawn confirmed）；
- UI 明确区分“检测到的观测”与“插值/推断”，低质量时宁可不画折线。

不建议首次实现就把所有红点画成 spaghetti lines；它会把检测候选包装成高置信度战术事实。

## 5. 与 AGE-46 的依赖和推荐顺序

### 当前状态判断

AGE-46 的核心实现已经在当前 `main`：

- `detect_death_marker()`和窗口化 `extract_death_location()`存在；
- 生产调用传入 counter 确认的 `death_window`；
- AGE-131/140 的锚定、基线、位置复核、crop 标定和回归测试已经合入（Git 历史包含 `ed8cee2` merge 及相关 commits）。

所以 AGE-200 **不需要等待“AGE-46 代码首次落地”**。可以并行开展数据 schema、坐标归一化/地图 asset 标定、轨迹关联和质量协议。

但发布一个把 X 画成“精确死亡点”的用户功能前，建议先完成/确认 AGE-46 的生产稳定化：

- orchestrator 是否应传入 `make_vlm_respawn_reader(self.vlm)`，或改用更确定的共现读数；
- 精确 marker `cx/cy`的持久化与置信度字段；
- 至少跨现有真实录屏复核当前**生产调用参数**的 precision/recall，而不是复用旧的无锚点扫描数据。

换言之：**工程可以并行，精确死亡点的产品承诺应依赖稳定化结果。** 即使 marker 暂不可用，轨迹面板也可以降级为“路径/观测 + 无精确死亡点”；两者不应互相硬阻塞。

## 粗略成本判断与建议拆票

### 判断

**前端画图：便宜。数据先做到可信：不是便宜的序列化改动，需要真实后端设计工作。**

如果产品目标改成“显示死亡前每 3 秒看到的敌方候选散点”，暴露数据后很便宜，但价值和 mock 不一致，且容易误导。若保持“玩家走位路径 + 死亡点”的原目标，主要工作在后端/视觉数据层：保留蓝方坐标、识别玩家、跨帧关联、质量状态、marker 精确点、版本化坐标系、持久化迁移与真实素材验证。

### 推荐后续实现票顺序

1. **数据契约/产品语义票：** 明确画玩家、敌方还是两者；定义 versioned schema、质量和降级状态。
2. **检测与轨迹票：** 保留 ally observations，完成 player identification、去重、关联和真实素材验证。建议复用 AGE-48 的身份研究，但先核实相关实现是否已落地；当前路径没有使用它。
3. **marker 稳定化/序列化票：** 保存 `cx/cy`与验证层级；和 AGE-46/131 生产接线收尾协调。
4. **地图 asset/标定票：** 选择同源 crop 或规范静态地图，定义 transform/version。
5. **API/持久化票：** 在 replay 生成时保存轨迹，历史 replay 无字段时自然降级；GET detail 原样返回即可。
6. **前端可视化票：** 时间排序折线、视野断点、死亡 X、质量提示和无数据 empty state。

## 可直接贴到 Linear 的短结论

当前 `/replay/{replay_id}` 没有 raw minimap coordinates；`Orchestrator`在生成 replay 时把 `extract_minimap_positions()`结果立即压成 `minimap_context`字符串，原数组随后丢失。并且当前函数只保留每帧的敌方候选集合，ally 只有 count，没有玩家坐标，也没有跨帧 track ID，因此不支持 AGE-197 mock 所表达的“玩家死亡前 15 秒移动路径”。X-marker 的 `cx/cy`虽然由 `extract_death_location()`算出，也在 orchestrator 中被降成 `region/source`后丢弃。坐标是 420×320 minimap crop 内像素，可归一化映射，但仓库没有规范静态地图 asset，不能假设任意底图与 crop 无偏移等比例对应。已有 AGE-47/131 验证表明 raw 点存在静态建筑误报、分量拆分、幽灵轨迹和 marker 噪声风险；当前静态 zone/窗口锚定已缓解一部分，但仍缺身份关联和质量模型。建议 schema/轨迹设计可与 AGE-46 稳定化并行，精确死亡点发布前再以生产参数完成 AGE-46 复核。总体判断：前端绘制便宜，可信数据暴露不是；需要先做后端数据模型、玩家识别/track association、质量标记和坐标标定。
