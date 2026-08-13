# Coach — AI王者荣耀决策思维教练

用对话教玩家像高手一样思考，而非死记硬背操作。纯文本MVP（语音为v1.1+增强）。

## 快速开始

```bash
cd coach
pip install -r requirements.txt      # 可选依赖，纯标准库也能跑降级模式
export COACH_LLM_API_KEY=sk-...      # DeepSeek/通义 API key（AI点评/对话/周报）
export COACH_VLM_API_KEY=sk-...      # 视觉模型key（视频自动复盘；缺省回落上者）

python coach.py --init               # 创建玩家档案
python coach.py --replay --manual    # 手动录入一局 + AI点评
python coach.py --replay 回放.mp4    # 视频全自动复盘（需ffmpeg+opencv+视觉模型）
python coach.py --checkin --rate 90  # 训练打卡
python coach.py --weekly-report      # 周报 + 每周评估 + 下周任务
python coach.py --progress --chart   # 进度与ASCII图表
python coach.py --chat               # 自由对话
```

## 命令总览

| 命令 | 状态 |
|------|------|
| `--init` / `--update-profile` | ✅ |
| `--replay --manual` 手动录入+归因+AI点评 | ✅ |
| `--replay <video>` 视频自动复盘（阶段0管线：HUD粗采样+二分定位、minimap颜色阈值检测） | ✅（需视觉模型配置） |
| `--chat [--topic]` 自由对话 | ✅（需LLM配置） |
| `--checkin` / `--weekly-report` / `--progress` | ✅ |
| `--voice` 语音层 | v1.1+，移出MVP |

**降级模式：** 未配置LLM时仍可用——输出规则层死亡归因 + 知识库检索原文，
明确声明AI点评不可用，绝不编造。

## 架构（tech spec v1.1 / 实现计划v1.0）

- `core/orchestrator.py` 调度：归因 → 知识检索 → 约束检查 → prompt → LLM
- `core/replay_engine.py` 死亡归因分类器（规则优先，LLM兜底，证据不足时诚实降级）
- `core/knowledge_engine.py` RAG检索（标签+关键词匹配；tier 3条目加载时强制过滤）
- `core/constraints_engine.py` 约束画像兼容性检查 + 4.6.3固定约束识别
- `core/training_engine.py` 每周评估（advance/change_method/encourage/continue/compensate）、任务生成、打卡
- `utils/video_utils.py` 死亡检测（KDA粗采样+二分）+ minimap检测（HSV阈值+连通域）
- `utils/transcript_utils.py` 知识库冷启动：`python -m utils.transcript_utils <yt_video_id>` → 候选条目文件，人工tier判定后入库

## 知识库

`knowledge_base/` 条目格式见 `macro_principles.md` 头部说明。铁律：
tier 3（风格化/有争议）禁止进入基本功库，引擎加载时会过滤并告警。
冷启动目标30-50条，人工tier判定不可自动化。

## 测试

```bash
python -m unittest discover tests    # 34项，全部离线（LLM mock）
```
