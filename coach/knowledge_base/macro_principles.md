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

## 已核实条目（2026-08-15批次）

- **[MP_TOWER_ROTATE_DAMAGE]** 越塔强杀时应轮流吸引防御塔仇恨，而非让同一人一直待在塔下：防御塔对同一目标连续攻击伤害递增（1.0→4.0AD，6次内翻近4倍），由一人先手引仇恨、伤害升高前主动走出塔外，换下一人接手，可显著降低团队总承伤，是低干扰配置下越塔的核心操作细节。
  - tier: 2_converged_consensus
  - tags: 越塔, 机制死, 换头死
  - applies_when: 组队越塔且干扰技能不足/在冷却时
  - requires_capability: 团队沟通/走位配合
  - source: 名侦探15号《防御塔隐藏机制完全解析》pvp.qq.com官方专栏 (2021-08-05，含eStarPro战队轮流抗塔实战案例)
  - valid_as_of_patch: 2021-08（未复核S43是否有变动）
  - last_reviewed: 2026-08-15

- **[MP_WAVE_CLEAR_FAKE_DIRECTION]** 清完兵线后会有短暂的视野留存，若立刻直接走向目标分路，敌方可从残留视野看出你的游走意图并提前示警，导致gank落空。应反方向走位一段距离迷惑对手，再绕路前往真实目标。
  - tier: 2_converged_consensus
  - tags: 探草死, 视野
  - applies_when: 清线后准备游走gank
  - requires_capability: null
  - source: 《视野篇(一)：掌握视野才能掌握战场》pvp.qq.com官方专栏 (2020-04-28)
  - valid_as_of_patch: 2020-04（未复核S43是否有变动）
  - last_reviewed: 2026-08-15

- **[MP_BUSH_BAIT_TURN_BACK]** 疲劳期警惕性下降、担心草丛有埋伏时，可在距草丛2-3个身位处突然反向走位/回头，观察草内是否有敌人追出来试探；若无人追出可再次靠近，若有人追出则根据情况反打或撤退——比直接贴脸探草更安全。
  - tier: 2_converged_consensus
  - tags: 探草死
  - applies_when: 不确定草丛是否有埋伏、无法用技能探草时
  - requires_capability: null
  - source: 丹青解说《在草丛中被蹲了N次以后，我含泪总结了四个技巧防止被抓》pvp.qq.com官方专栏 (2020-08-31)
  - valid_as_of_patch: 2020-08（未复核S43是否有变动）
  - last_reviewed: 2026-08-15

- **[MP_BUSH_SKILL_SCOUT_FIRST]** 脆皮英雄（法师/射手）在没有辅助探草时不应贸然靠近草丛，应优先用自带探草技能确认（如孙尚香/鲁班七号/后羿/蒙犽的技能），法师可利用回响之杖被动判断草内是否有人；没有以上手段时，靠近草丛前先在小地图确认关键威胁英雄的位置和动向。
  - tier: 2_converged_consensus
  - tags: 探草死
  - applies_when: 脆皮英雄单独经过草丛
  - requires_capability: 探草技能或对应装备
  - source: 丹青解说《在草丛中被蹲了N次以后，我含泪总结了四个技巧防止被抓》pvp.qq.com官方专栏 (2020-08-31)
  - valid_as_of_patch: 2020-08（未复核S43是否有变动）
  - last_reviewed: 2026-08-15

- **[MP_GANK_OPPORTUNITY_COST]** 主动去抓人，放弃的是原本稳定的约300经济收益（半片野区：一个人头150+一个buff120+一个野怪90量级），换取的是约150金币且不确定能否拿到的人头收益：蹲到了大致打平（300-150），蹲不到损失约300稳定经济，被反杀则损失600以上（自身死亡经济+对面借机反野的双倍效应）。前期若不能在约15秒内拿到人头，通常已经在亏钱（每秒流失约10金币的时间成本）；只有蹲到人后能进一步抢野区/推塔/开资源，才算真正赚到。
  - tier: 2_converged_consensus
  - tags: 掉点死, 贪线死
  - applies_when: 权衡是否值得主动脱线去抓人/是否该继续蹲一个不确定的机会
  - requires_capability: null
  - source: 国服路人豪《想成为高手的进阶之路（1）》pvp.qq.com官方专栏 (2023-01-03)
  - valid_as_of_patch: 2023-01（未复核S43是否有变动）
  - last_reviewed: 2026-08-15

- **[MP_FARM_MARGINAL_VALUE_DECLINE]** 刷经济的边际收益会递减：出核心装备（如无尽战刃/暗影战斧/巫术法杖等对应位置核心件）后，继续刷野的收益开始明显下降；出到神装、进入后期后，继续刷经济对团队几乎没有增量价值，此时应主动把资源让给经济更低的队友，而不是闷头继续发育。
  - tier: 2_converged_consensus
  - tags: 贪线死
  - applies_when: 判断"这波资源该不该让/该不该继续自己吃"
  - requires_capability: null
  - source: 国服路人豪《想成为高手的进阶之路（1）》pvp.qq.com官方专栏 (2023-01-03)
  - valid_as_of_patch: 2023-01（未复核S43是否有变动）
  - last_reviewed: 2026-08-15

- **[MP_LOWER_ELO_FARM_PRIORITY]** 中低分段（该来源以"王者70星以下"为参照）玩家普遍缺乏"先发育再打架"的意识，倾向于全程主动交战消耗时间成本；在这一分段，单纯稳定刷经济、克制主动出击的冲动，通常足以带来明显更高的胜率——先把发育做扎实，比频繁尝试越塔/抓人更稳，风险判断应偏保守。
  - tier: 2_converged_consensus
  - tags: 掉点死, 贪线死
  - applies_when: 面向中低分段玩家给出"要不要主动出击"的建议时
  - requires_capability: null
  - source: 国服路人豪《想成为高手的进阶之路（1）》pvp.qq.com官方专栏 (2023-01-03)
  - valid_as_of_patch: 2023-01（未复核S43是否有变动）
  - last_reviewed: 2026-08-15

- **[MP_COMEBACK_ECONOMY_MECHANIC]** 原初试炼团队经济追赶系数（S29赛季引入）：当双方经济差超过一定幅度后（随时间成长），优势方击杀英雄获取的经济会减少10%，劣势方击杀英雄获取的经济会提升10%。这意味着即使己方大幅领先，掉点/贪线被劣势方反杀的代价也会被这套机制放大——领先局不能因为"经济够用"就放松对单带/贪线风险的判断，一次被追分的死亡换算价值比看起来更高。
  - tier: 1_mechanical_fact
  - tags: 掉点死, 贪线死
  - applies_when: 己方经济大幅领先时评估是否可以承担单带/贪线风险
  - requires_capability: null
  - source: 雷电模拟器官网转载《王者荣耀》9月22日正式服版本更新公告（S29赛季「幻海映月」，2022-09-21）
  - valid_as_of_patch: S29（未复核S43是否有变动，机制名称"原初试炼"在S43仍作为经验加成体系被提及，具体追赶系数需留意后续版本是否调整）
  - last_reviewed: 2026-08-15

- **[MP_FAKE_VISION_REROUTE]** 当自己的视野已经暴露（如刚击杀一名敌方英雄，或走出草丛被兵线/塔看到），应利用视野残留的窗口反向走位制造假信号，再绕路前往真实目的地。例如在中路兵线交汇处击杀敌方中单后想去敌方红buff区，可先明显地朝蓝buff方向走一小段，再绕路折返到红区——传递给敌方的视野信号是"去了蓝区"，而非真实目的地，可显著降低被预判/包夹的概率。
  - tier: 2_converged_consensus
  - tags: 探草死, 掉点死
  - applies_when: 完成一次可见的击杀/暴露后决定下一步动向
  - requires_capability: null
  - source: 丹青解说《详解峡谷视野玄机》pvp.qq.com官方专栏 (2021-08-04)
  - valid_as_of_patch: 2021-08（未复核S43是否有变动）
  - last_reviewed: 2026-08-15

- **[MP_BUSH_BAIT_ASYMMETRIC_EXPOSURE]** 草丛诱捕战术：让一名队友提前悄悄潜伏在草丛中，自己站在草丛外攻击敌人后再钻入草丛——此时只有自己的视野会短暂暴露，草内提前埋伏的队友不会暴露。敌方会误判草内只有一人在逃跑，从而放心追击，实际会遭遇两人埋伏。此战术依赖上面"进草视野残留"的具体秒数（存在分歧，见MM_BUSH_ENTER_RESIDUAL_TIME），但"单人暴露、队友不暴露"这一非对称效果本身是可靠的。
  - tier: 2_converged_consensus
  - tags: 探草死, 换头死
  - applies_when: 计划利用草丛设伏/反打追击者
  - requires_capability: 队友配合提前埋伏
  - source: 丹青解说《详解峡谷视野玄机》pvp.qq.com官方专栏 (2021-08-04)
  - valid_as_of_patch: 2021-08（未复核S43是否有变动）
  - last_reviewed: 2026-08-15

## 已核实条目（2026-08-21批次 · AGE-201定向补空，DeepSeek+GLM交叉核实后人工合并）

- **[MP_NO_TRADE_THREE_RULES]** 三个"绝对不换血"信号：①技能不全（缺核心控制/位移/保命技能）；②兵线劣势（敌方兵线多时小兵伤害前期远超英雄伤害）；③视野缺失（河道/关键区域黑屏，大概率有敌方打野埋伏）。三者任一命中都应该放弃这波换血机会，猥琐发育。
  - tier: 2_converged_consensus
  - tags: 换头死
  - applies_when: 对线期判断该不该主动换血
  - requires_capability: null
  - source: 王者荣耀官方攻略《对抗路必修课思路》pvp.qq.com tid=587102（2022-11-27，作者"肥猫"，四要素：对面队友在不在/我方兵线多不多/双方血蓝技能CD谁占优/回复能力强不强）；搜狐游戏《对线换血完整教学》game.sohu.com/a/1045199940_122739691（2026-07-03）
  - valid_as_of_patch: 非版本敏感
  - last_reviewed: 2026-08-21

- **[MP_SKILL_VACUUM_TRADE_WINDOW]** 对抗路战士类英雄核心技能CD普遍在10秒上下，打满一套技能后会有至少3秒的"真空期"（核心技能不在手）。应该专挑对手处于真空期的时间窗口主动换血/上前施压，而不是对方技能满配时贸然对拼。
  - tier: 2_converged_consensus
  - tags: 换头死
  - applies_when: 对抗路对线期判断换血时机
  - requires_capability: null
  - source: 今日头条《战士边路对线换血实用核心技巧》（2026-06-23）
  - valid_as_of_patch: 非版本敏感
  - last_reviewed: 2026-08-21

- **[MP_EXECUTE_LINE_RETREAT]** "斩杀线"：对手一套操作能把自己秒掉的最高血量阈值。一旦自身血量进入对方斩杀线、且没有反打/逃生机会，即使这波要亏一些兵线经济，也应该主动回城补给，而不是硬留在线上继续对拼——这个阈值没有统一数值公式，需要玩家对具体对位英雄的伤害有实战体感积累。
  - tier: 2_converged_consensus
  - tags: 换头死, 掉点死
  - applies_when: 判断"这波该不该继续对线/该不该先回城"
  - requires_capability: null
  - source: 多篇署名攻略独立提及此概念（属广泛共识术语）
  - valid_as_of_patch: 非版本敏感
  - last_reviewed: 2026-08-21

- **[MP_FLASH_VACUUM_PUNISH]** 敌方刚交出闪现或位移类技能后，会有一段明显的"虚弱期"（接下来一段时间只能靠平砍/普通移动）。应在对手交完闪现/位移的瞬间主动施压或用范围技能封锁其落脚点，而不是等对方状态恢复后再动手。
  - tier: 2_converged_consensus
  - tags: 换头死
  - applies_when: 敌方刚使用闪现或位移类技能
  - requires_capability: null
  - source: 多篇署名攻略独立提及（王者荣耀官方及第三方攻略均有类似表述）
  - valid_as_of_patch: 非版本敏感
  - last_reviewed: 2026-08-21

- **[MP_COUNTER_FLASH]** 被敌方闪现欺近、判断对方是想"一套秒掉自己"时，可以在对方闪现的瞬间反向闪现——对手往往是判断能秒杀才会交闪现，这个时间点反闪比直线逃跑存活率更高。
  - tier: 2_converged_consensus
  - tags: 换头死
  - applies_when: 被敌方闪现欺近、判断对方有斩杀意图
  - requires_capability: 自身闪现可用
  - source: 多篇署名攻略独立提及
  - valid_as_of_patch: 非版本敏感
  - last_reviewed: 2026-08-21

- **[MP_PURIFY_PREEMPTIVE]** 看到敌方控制英雄出现明显的技能前摇动作（起手动画/技能音效）时，应提前按下净化或自带解控技能，而不是等被控制命中之后才反应——按下净化后仍有极短反应窗口能规避伤害型持续施法技能被打断。
  - tier: 2_converged_consensus
  - tags: 机制死, 换头死
  - applies_when: 判断敌方即将释放控制技能
  - requires_capability: 净化或自带解控技能
  - source: 王者荣耀官方攻略《召唤师技能净化六大作用》pvp.qq.com tid=560584（作者"预谋"）
  - valid_as_of_patch: 非版本敏感
  - last_reviewed: 2026-08-21

- **[MP_CONTROL_CHAIN_TIMING]** 己方多个控制技能衔接时，不要在队友已经控住敌人的窗口期再叠加自己的控制（会造成"无效控制浪费"）；应该等队友的控制快结束、或者已经骗出敌方净化之后，再补上自己的控制技能延长控制链。
  - tier: 2_converged_consensus
  - tags: 换头死, 机制死
  - applies_when: 团战/遭遇战中己方多人有控制技能可用
  - requires_capability: 团队沟通/控制链意识
  - source: 王者荣耀官方攻略《怎么避免无效控制浪费技能》pvp.qq.com tid=580525（2022-09-14）
  - valid_as_of_patch: 非版本敏感
  - last_reviewed: 2026-08-21

- **[MP_DONT_DIVE_WITHOUT_ESCAPE]** 自己没有净化/位移/保命装备时，不要强行冲进去救被压制类控制（东皇大招/张良大招等）命中的队友——压制类控制无法被净化解除，强行去救大概率只是把自己也搭进去，变成送双杀。没有保命手段时优先保命撤退，而不是本能地去救人。
  - tier: 2_converged_consensus
  - tags: 换头死, 掉点死
  - applies_when: 队友被压制类控制命中，自己没有解控/位移/保命装备
  - requires_capability: null
  - source: 王者荣耀官方攻略《最稀缺的3种属性》pvp.qq.com tid=598060
  - valid_as_of_patch: 非版本敏感
  - last_reviewed: 2026-08-21

## 待核实（AI研究报告提及但未独立核实来源，暂不计入检索）

以下宏观原则来自DeepSeek/GLM研究报告，因来源为个人博主（如"北斗"小红书账号）、
无法定位的媒体（如"《澳门日报》"）、或未逐条打开核实的pvp.qq.com链接，暂不写成正式条目：

- 视野优先/追踪敌方打野消失位置/反蹲优于主动gank/转线顺序/龙团前视野优先/资源取舍优先级
  等一系列宏观判断原则——内容本身符合常识性MOBA共识，但报告给出的具体来源（个人博主、
  未具名媒体）未能逐条核实，需重新寻找可核实来源或改为团队自行整理后归档。
- 1换1价值判断、越塔换头亏损判断——同上，待寻找可核实来源。

