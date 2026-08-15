# 地图机制库（Tier 1 为主）

> 河道/草丛/野区刷新/防御塔机制等可查证事实。每条带 source / valid_as_of_patch / last_reviewed。

## 防御塔机制（已核实，2026-08-15批次）

> 以下条目均已通过Claude in Chrome实际打开pvp.qq.com原文核实内容属实，
> 而非仅采信AI研究报告的转述。核实过程中发现并纠正了两处原报告错误：
> 无兵线减伤应为55%（非45%）；小兵视野应为750码（非800码，未纳入本文件因缺权威原文）。

- **[MM_ORIGIN_GUARD]** 原初守护机制（S43「陌上相逢」正式服）：前4分钟，敌方英雄在我方防御塔内降低25%伤害（单人不变），每多一个敌方英雄进入塔内额外降低3.75%伤害；4-10分钟，降低10%伤害（单人不变），每多一人额外降低1.5%。
  - tier: 1_mechanical_fact
  - tags: 越塔, 机制死, 换头死
  - applies_when: 判断多人越塔的实际承伤/劝阻单人越塔
  - requires_capability: null
  - source: 王者荣耀官方网站 S43「陌上相逢」正式服更新公告（2026-03-30发布）
  - valid_as_of_patch: S43
  - last_reviewed: 2026-08-15

- **[MM_TOWER_BASE_STATS]** 防御塔基础数值：一塔/二塔初始攻击470，每30秒+3，10分钟达上限540；高地塔初始630，每30秒+5，上限724；水晶初始580。攻击频率：塔1秒1次，水晶2秒1次。
  - tier: 2_converged_consensus
  - tags: 机制死, 越塔
  - applies_when: 判断能否抗塔/预估承伤
  - requires_capability: null
  - source: pvp.qq.com官方专栏《王者冷知识：防御塔机制揭秘》(Alex, 2021-08-09), 名侦探15号《防御塔隐藏机制完全解析》(2021-08-05)
  - valid_as_of_patch: 2021-08（未复核S43是否有变动）
  - last_reviewed: 2026-08-15

- **[MM_TOWER_DAMAGE_RAMP]** 防御塔对同一英雄连续攻击伤害递增：首次1.0AD，此后每次+0.6AD，第6次达上限4.0AD（以一塔470为例：470→752→1034→1316→1598→1880）。伤害为100%穿甲物理伤害，可被护盾/免伤技能减免，但英雄物理防御无效。
  - tier: 2_converged_consensus
  - tags: 越塔, 机制死, 换头死
  - applies_when: 越塔强杀、判断能否抗塔
  - requires_capability: null
  - source: pvp.qq.com官方专栏《王者冷知识：防御塔机制揭秘》(Alex, 2021-08-09), 名侦探15号《防御塔隐藏机制完全解析》(2021-08-05)
  - valid_as_of_patch: 2021-08（未复核S43是否有变动）
  - last_reviewed: 2026-08-15

- **[MM_TOWER_NO_MINION_REDUCTION]** 无兵线时防御塔伤害减免55%，水晶减免90%（塔伤害计算优先级：面板伤害×护甲减免×破军系数→取上限1000/2000→再乘无兵线减伤比例）。
  - tier: 2_converged_consensus
  - tags: 越塔, 机制死
  - applies_when: 判断无兵线越塔/单人点塔的实际承伤或输出
  - requires_capability: null
  - source: 名侦探15号《防御塔隐藏机制完全解析》pvp.qq.com官方专栏 (2021-08-05)
  - valid_as_of_patch: 2021-08（未复核S43是否有变动）
  - last_reviewed: 2026-08-15

- **[MM_TOWER_DAMAGE_CAP]** 英雄对防御塔单次伤害上限1000；携带强击类被动（宗师之力、刘禅/铠/孙策等强化普攻）上限提升至2000。防御塔永远无法被普攻暴击，普攻命中塔不吸血。
  - tier: 2_converged_consensus
  - tags: 推塔, 机制死
  - applies_when: 拆塔效率判断
  - requires_capability: null
  - source: 名侦探15号《防御塔隐藏机制完全解析》pvp.qq.com官方专栏 (2021-08-05)
  - valid_as_of_patch: 2021-08（未复核S43是否有变动）
  - last_reviewed: 2026-08-15

- **[MM_TOWER_AGGRO_RULES]** 防御塔仇恨优先级（无干扰情况下）：第一个无兵线越塔者 ＞ 第一个对塔下敌方英雄造成伤害者 ＞ 兵线。仇恨锁定后对同一目标连续伤害递增，目标走出攻击范围后仇恨立即清零；干扰技能不会清空已锁定的仇恨。
  - tier: 2_converged_consensus
  - tags: 越塔, 机制死, 换头死
  - applies_when: 组队越塔时判断塔在打谁/如何分摊塔伤
  - requires_capability: null
  - source: 名侦探15号《防御塔隐藏机制完全解析》pvp.qq.com官方专栏 (2021-08-05)
  - valid_as_of_patch: 2021-08（未复核S43是否有变动）
  - last_reviewed: 2026-08-15

- **[MM_TOWER_AGGRO_CLEAR_SKILLS]** 部分无法被选中的效果可清空已锁定的防御塔仇恨：芈月/貂蝉/李白/宫本武藏/瑶的位移或隐身状态、携带辉月时的无法选中效果、曜大招、镜的飞雷神效果，以及死亡复活。
  - tier: 2_converged_consensus
  - tags: 越塔, 机制死
  - applies_when: 利用无法选中技能规避塔伤越塔
  - requires_capability: 特定英雄/装备
  - source: 名侦探15号《防御塔隐藏机制完全解析》pvp.qq.com官方专栏 (2021-08-05)
  - valid_as_of_patch: 2021-08（未复核S43是否有变动）
  - last_reviewed: 2026-08-15

## 视野机制（已核实，2026-08-15第二批）

- **[MM_BUSH_HIDDEN_FROM_OUTSIDE]** 草丛遮蔽视野基本原则：提前潜伏在草丛内、未与草外敌人发生任何交互时，草内一方可看见草外靠近的敌人，但草外敌人看不见草内的自己；一旦草内一方对草外目标发起攻击，视野立即对敌方暴露。
  - tier: 2_converged_consensus
  - tags: 探草死
  - applies_when: 判断蹲草时机/草内先手时机
  - requires_capability: null
  - source: 丹青解说《在草丛中被蹲了N次以后，我含泪总结了四个技巧防止被抓》pvp.qq.com官方专栏 (2020-08-31)
  - valid_as_of_patch: 2020-08（未复核S43是否有变动）
  - last_reviewed: 2026-08-15

- **[MM_BUSH_ENTER_RESIDUAL_TIME]** 进入草丛后的视野残留规则：若进草前未发生任何攻击行为，视野仍会保留0.5秒（非立即消失）——这一点两篇文章一致。**"攻击敌人后立即进草"这一具体场景的残留时长存在未解决的矛盾：同一作者2020-08-31的文章称2.5秒，2021-08-04的文章描述几乎相同的场景（"在草丛外边攻击了敌人，然后扭头就钻进了草丛"）却称0.5秒。** 在明确哪个数值对应当前版本前，只能确认"打完架立刻进草不会立即安全"这一定性结论，不应引用具体秒数（2.5或0.5）作为确定值。
  - tier: 2_converged_consensus
  - tags: 探草死, 换头死
  - applies_when: 战斗后撤入草丛/判断对手打完架进草是否已安全
  - requires_capability: null
  - source: 丹青解说《在草丛中被蹲了N次以后，我含泪总结了四个技巧防止被抓》pvp.qq.com官方专栏 (2020-08-31)；同作者《详解峡谷视野玄机》pvp.qq.com官方专栏 (2021-08-04，数值与前文冲突)
  - valid_as_of_patch: 2020-08/2021-08（两篇文章互相矛盾，均未复核S43是否有变动）
  - last_reviewed: 2026-08-15

- **[MM_BUSH_ATTACK_FROM_INSIDE_RESIDUAL]** 站在草丛内攻击草外敌人（与上一条"草外攻击后进草"是不同场景）：只要持续对拼，视野会一直暴露；即使停止攻击安静待在草内，视野仍会滞留约4秒才消失——不要误以为在草内打一下就能立刻恢复隐蔽。若草丛内有另一名队友与你保持一定距离（如中路两侧的长草丛分居两端），你攻击草外敌人只会暴露你自己的视野，不会暴露距离较远的队友。
  - tier: 2_converged_consensus
  - tags: 探草死, 换头死
  - applies_when: 蹲草时是否可以对外先手试探/判断草内队友是否会被连带暴露
  - requires_capability: null
  - source: 丹青解说《详解峡谷视野玄机》pvp.qq.com官方专栏 (2021-08-04)
  - valid_as_of_patch: 2021-08（未复核S43是否有变动）
  - last_reviewed: 2026-08-15

- **[MM_VISION_PERSISTS_INTO_BUSH]** 若在进入草丛之前，自己的视野已经暴露给敌方（如敌方头像已出现在锁敌显示中），那么进入草丛也无法让视野立即消失——已经暴露的视野不会因为进草而重置。正确做法是发现即将暴露时先绕路，确认敌方头像不再显示后再进草，而不是先暴露再指望进草补救。同理，若敌方英雄正在清理交汇处的兵线，直接从草丛冲出去也会先被兵线视野暴露，需绕开兵线视野范围再行动。
  - tier: 2_converged_consensus
  - tags: 探草死
  - applies_when: 判断"已经被兵线/塔/英雄看到"之后能否靠进草挽回
  - requires_capability: 锁敌头像显示设置
  - source: 丹青解说《详解峡谷视野玄机》pvp.qq.com官方专栏 (2021-08-04)
  - valid_as_of_patch: 2021-08（未复核S43是否有变动）
  - last_reviewed: 2026-08-15

- **[MM_BUSH_SKILL_DETECTION_EXCEPTIONS]** 部分侦查/命中效果对蹲草单位的视野影响不一致，属于英雄机制特例而非通用规则：张良一技能命中蹲草目标不会暴露其视野；王昭君一技能命中会暴露目标周围一小片视野（可用于反隐身）；花木兰轻剑二技能命中不会暴露蹲草目标视野；鲁班七号一技能（手雷）扔进草丛即可直接获得草内视野；司马懿被动会侦测2000码内草丛中释放技能的单位。
  - tier: 2_converged_consensus
  - tags: 探草死
  - applies_when: 判断特定英雄技能能否用于探草/反隐藏
  - requires_capability: 对应英雄
  - source: 丹青解说《详解峡谷视野玄机》pvp.qq.com官方专栏 (2021-08-04)
  - valid_as_of_patch: 2021-08（未复核S43是否有变动）
  - last_reviewed: 2026-08-15

- **[MM_TOWER_VISION_YELLOW_CIRCLE]** 靠近防御塔时，塔下攻击圈变黄即代表视野已暴露给敌方（此为视野暴露信号，与是否进入攻击范围是两回事）。
  - tier: 2_converged_consensus
  - tags: 探草死, 掉点死, 机制死
  - applies_when: 绕塔/借塔视野判断敌方动向前，先确认自己是否已暴露
  - requires_capability: null
  - source: 丹青解说《在草丛中被蹲了N次以后，我含泪总结了四个技巧防止被抓》pvp.qq.com官方专栏 (2020-08-31)
  - valid_as_of_patch: 2020-08（未复核S43是否有变动）
  - last_reviewed: 2026-08-15

- **[MM_MINION_VISION_ON_ATTACK]** 靠近小兵且被小兵攻击（即进入小兵仇恨/攻击范围）时，视野会暴露给敌我双方，与防御塔视野规则类似；单带线玩家常误以为自己神不知鬼不觉，实际上兵线早已暴露行踪。
  - tier: 2_converged_consensus
  - tags: 贪线死, 掉点死
  - applies_when: 单带/清线时判断自己是否已被暴露
  - requires_capability: null
  - source: 丹青解说《在草丛中被蹲了N次以后，我含泪总结了四个技巧防止被抓》pvp.qq.com官方专栏 (2020-08-31)
  - valid_as_of_patch: 2020-08（未复核S43是否有变动）
  - last_reviewed: 2026-08-15

- **[MM_VISION_RECIPROCITY]** 视野互见基本原则：你看到对方，对方就同时看到了你（英雄视野的双向性）；进入草丛前若已在敌方视野内，即使随后进草，敌方也已知晓你的走向。可在设置中开启"锁敌头像显示"，当技能栏旁突然出现敌方头像即代表双方已互获视野，用于自查是否暴露。
  - tier: 2_converged_consensus
  - tags: 探草死, 掉点死
  - applies_when: 进草前自查是否已暴露/判断gank为何被察觉
  - requires_capability: 开启锁敌头像显示设置
  - source: 《视野篇(一)：掌握视野才能掌握战场》pvp.qq.com官方专栏 (2020-04-28)
  - valid_as_of_patch: 2020-04（未复核S43是否有变动）
  - last_reviewed: 2026-08-15

- **[MM_TOWER_VISION_EXCEEDS_CIRCLE]** 防御塔实际视野探测范围大于显示的黄色警戒圈——尚未看到黄圈亮起，不代表尚未暴露视野；反野（尤其蓝buff区域）时应额外留出安全边际，而非仅以黄圈是否出现为唯一判断依据。
  - tier: 2_converged_consensus
  - tags: 探草死, 掉点死, 机制死
  - applies_when: 反野/绕塔路线规划
  - requires_capability: null
  - source: 《视野篇(一)：掌握视野才能掌握战场》pvp.qq.com官方专栏 (2020-04-28)
  - valid_as_of_patch: 2020-04（未复核S43是否有变动）
  - last_reviewed: 2026-08-15

## 经济数值（已核实，2026-08-15第三批）

- **[MM_WAVE_ECONOMY]** 补兵（小兵最后一击由英雄补刀）金币收益从41涨到61，约+33%；一波三个兵线约多60金币；兵线约每33秒刷新一波，10分钟内坚持补刀与完全不补刀的经济差约1200金币，相当于大半件装备。
  - tier: 2_converged_consensus
  - tags: 贪线死, 机制死
  - applies_when: 判断补刀价值/是否值得为了对线而多留一波兵
  - requires_capability: null
  - source: 秋豆《五大快速刷钱技巧》pvp.qq.com官方专栏 (2022-05-22)
  - valid_as_of_patch: 2022-05（未复核S43是否有变动）
  - last_reviewed: 2026-08-15

- **[MM_KILL_ECONOMY]** 击杀一个人头基础收益约150金币，敌方连续死亡次数越多单次收益越低（原初惩罚机制随对方连续死亡而降低击杀收益）；助攻根据队友数量分摊收益。
  - tier: 2_converged_consensus
  - tags: 换头死, 贪线死
  - applies_when: 权衡是否值得为了一个人头脱线/换血
  - requires_capability: null
  - source: 秋豆《五大快速刷钱技巧》pvp.qq.com官方专栏 (2022-05-22)
  - valid_as_of_patch: 2022-05（未复核S43是否有变动）
  - last_reviewed: 2026-08-15

- **[MM_JUNGLE_ECONOMY]** 小野怪单只约50金币，刷新周期70秒；红蓝buff刷新周期90秒（红buff增伤+减速，蓝buff减少技能冷却，两者都能间接加快清线获取兵线经济）。打野资源具有"双倍经济差"效应——己方拿到的同时相当于让对方少拿到同等数量。
  - tier: 2_converged_consensus
  - tags: 贪线死, 掉点死
  - applies_when: 判断反野/入侵野区的经济价值
  - requires_capability: null
  - source: 秋豆《五大快速刷钱技巧》pvp.qq.com官方专栏 (2022-05-22)
  - valid_as_of_patch: 2022-05（未复核S43是否有变动）
  - last_reviewed: 2026-08-15

- **[MM_OBJECTIVE_ECONOMY]** 十分钟前，击杀主宰为全队每人提供40金币，击杀暴君提供20金币（不含buff本身的战力加成）；一条主宰的经济价值（含补兵口径）约180金币，接近一波兵线（约250金币）；控一条龙叠加全队分成，可形成较大经济差。
  - tier: 2_converged_consensus
  - tags: 掉点死, 贪线死
  - applies_when: 权衡去打龙/暴君 vs. 留在线上清兵
  - requires_capability: null
  - source: 秋豆《五大快速刷钱技巧》pvp.qq.com官方专栏 (2022-05-22)
  - valid_as_of_patch: 2022-05, S27赛季数据（未复核S43是否有变动）
  - last_reviewed: 2026-08-15

- **[MM_TOWER_PUSH_ECONOMY]** 摧毁一塔奖励75金币，二塔97金币，另外摧毁防御塔时全队每人各获得100金币；推掉一座一塔可为双方制造约575经济差（含直接奖励与团队分成）。
  - tier: 2_converged_consensus
  - tags: 推塔, 机制死
  - applies_when: 判断推塔相对清线/打野的经济优先级
  - requires_capability: null
  - source: 秋豆《五大快速刷钱技巧》pvp.qq.com官方专栏 (2022-05-22)
  - valid_as_of_patch: 2022-05（未复核S43是否有变动）
  - last_reviewed: 2026-08-15

- **[MM_VISION_SPIRIT_MECHANICS]** 视野之灵机制（S24赛季调整，2021-06-22确认，取代此前"仅己方可见"的旧规则——该旧规则已过时，不应再引用）：可见性调整为**敌方也可见**，但视野之灵本体会藏在草丛中，敌方需要进入该草丛才能发现并靠近将其摧毁（摧毁者获得1金币）。机制同时调整为不再持续绕野区巡逻，而是躲进草丛为友军持续提供该草丛的视野；持续时间由55秒延长至60秒，冷却时间由180秒缩短至120秒。（触发条件本身未变：边路二塔被摧毁后，英雄在残骸处停留2秒即可激活。）
  - tier: 2_converged_consensus
  - tags: 探草死, 掉点死
  - applies_when: 判断二塔已破后视野之灵能否被敌方摧毁/是否可依赖其提供隐蔽支援视野
  - requires_capability: null
  - source: 《S24赛季到来，英雄/装备/游戏环境调整分析》pvp.qq.com王者营地移动端 (作者"王者不废话攻略", 2021-06-22)
  - valid_as_of_patch: S24（2021-06，未复核S43是否有进一步变动）
  - last_reviewed: 2026-08-15

## 待核实（AI研究报告提及但未独立核实来源，暂不计入检索）

以下内容来自DeepSeek/GLM研究报告，因来源为拼接的搜索引用ID、低权重聚合站，
或未能实际打开原文核实，暂不写成正式条目，仅作后续核实候补：

- 视野之灵机制细节（触发条件、巡逻规则、S24可见性调整）——报告给出的pvp.qq.com链接尚未逐一打开确认。
- 传送阵/空间之灵跨赛季演变（S22原初法阵→S35冷却缩短→S36空间之灵→S43/S44传送人数调整）——同上，未逐条核实。
- 防御塔视野范围（1000码）、草丛视野残留时间（0.5秒/2.5秒）——尚未找到可核实的权威原文，9game转载文章不含具体数值。
- 野怪/红蓝buff/河道之灵/暴君主宰/风暴龙王的具体刷新时间与数值——未核实。
- 英雄视野1200码、小兵视野750码——已通过独立网络搜索交叉确认（注：GLM报告中"小兵视野800码"经核实有误，正确数值为750码），可视为可信但未逐字核对pvp.qq.com原文表述。
- ~~视野之灵是否对敌方可见~~ ——**已于2026-08-15核实并解决**，见上方 MM_VISION_SPIRIT_MECHANICS。2020年"仅己方可见"的描述已被S24赛季（2021-06）的调整取代，当前应以"敌方可见但需进草丛发现"为准。（此条目保留作为核实过程记录：期间曾收到多轮引用不实/无法验证的"确认"，包括复用无关网页的知乎链接、匿名小红书/虎扑帖子，均未采信，最终通过找到实际的S24赛季官方分析文章原文解决。）
