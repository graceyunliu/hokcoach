# 待审核更新（Pending Updates）

本目录存放数据情报管线每两周生成的知识库更新草案，**不会被 `knowledge_engine.py`
加载**（`load_all_principles()` 只读取上一级目录的 `macro_principles.md` /
`map_mechanics.md` / `hero_mechanics.json`），因此这里的内容在你审核合并之前
不会影响教练的实际输出。

## 工作流程

1. `coach/intake/run_intake.py` 每两周由 GitHub Actions（`.github/workflows/hok-intake.yml`，
   1号/15号各跑一次，近似双周）自动运行一次，也可以本地手动跑（见下方"本地运行"）。
   分两层：
   - **检索层**：智谱GLM（`glm-4-plus` + 内置 `web_search` 插件），能直接访问中文
     网站，按 `coach/intake/sources.py` 里配置的查询清单检索：
     官方渠道（pvp.qq.com版本说明）、社区百科/攻略聚合站、社媒/论坛动态
     （微博/TapTap/NGA）、B站/抖音/快手/虎牙/小红书上主播·职业教练·职业选手的
     版本解读内容。
   - **起草层**：DeepSeek，把检索到的原始材料整理成符合知识库schema的条目草案。
2. 每次运行会在本目录生成一个新文件：`YYYY-MM-DD_proposal.md`，其中每条草案
   都按 `macro_principles.md` 的条目格式书写（含 tier / tags / source /
   valid_as_of_patch / last_reviewed），并额外标注：
   - `status: pending_review`
   - `change_type: new | update | deprecate`（新增 / 修改现有条目 / 建议废弃）
   - 若是 `update`/`deprecate`，会指出对应的现有条目 id
3. GitHub Actions运行结束后会自动开一个PR（分支 `intake/auto-update`），只包含
   本目录下新增的草案文件。**你来审核PR**：确认信息属实、tier 分级正确（尤其
   注意 Tier 3 风格化/有争议内容不能进 macro_principles.md，只能进偶像标准层）
   后，手动把条目剪切/合并进 `../macro_principles.md`、`../map_mechanics.md` 或
   `../hero_mechanics.json`，再删除或归档本目录里的草案文件，合并PR。
4. 每次运行也会更新 `_pending_updates/CHANGELOG.md`，记录本次抓取到的信源
   和摘要，方便你快速判断是否需要精读全文。

## 本地运行

```bash
cd coach
export ZHIPU_API_KEY=你的智谱API Key      # 检索层，需要web_search权限
export DEEPSEEK_API_KEY=你的DeepSeek API Key  # 起草层
python -m intake.run_intake
```

## GitHub Actions配置

在仓库 Settings → Secrets and variables → Actions 里添加两个secret：
`ZHIPU_API_KEY`、`DEEPSEEK_API_KEY`。工作流默认双周（1号/15号 09:00北京时间）
自动运行，也可以在Actions页面手动点 "Run workflow" 触发。

## 为什么不自动合并

游戏机制类知识错误会直接误导训练建议，且信源可靠度参差不齐（主播解说 ≠
官方数值）。因此管线只负责"发现变化 + 起草条目"，合并决策始终由人工完成。
