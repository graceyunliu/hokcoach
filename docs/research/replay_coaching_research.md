# 王者荣耀 Replay-Coaching Research and hokcoach Gap Analysis

**Author:** Manus AI  
**Date:** 2026-08-26  
**Repository baseline:** `graceyunliu/hokcoach`, commit `5e33b09`

## Executive conclusion

High-level王者荣耀 replay reviewers do not restrict feedback to “why did you die?”. Their distinctive value is a **continuous decision narrative**: what information was available, what the player believed, what the next objective should have been, whether the action matched the team’s timing, and whether the result was converted into tower, wave, invade, or reset value. The most consistently evidenced themes are **vision and information discipline**, **farm-versus-rotation trade-offs**, **composition and power-spike timing**, **wave/tempo control**, **teamfight entry and target selection**, and **mechanical execution**.

The current hokcoach repository already has a strong rule-first foundation for death attribution, minimap evidence, audio corroboration, knowledge retrieval, constraint checks, and training tasks. Its primary limitation is not lack of coaching ideas; it is the mismatch between the breadth of human commentary and the narrowness of automatically provable replay signals. The adopted improvement therefore adds an **evidence-gated structured feedback layer** rather than pretending to solve unobservable skills. It emits cards for supported categories and explicitly labels proxy or missing-evidence cases.

## Evidence and method

The sample was assembled from directly readable official pages, a Bilibili page for a花海 first-person teaching course, public video metadata, and the repository’s own prior capability matrix. The official运营 analysis says decisions should be organized around towers, lane rotation, position and vision control rather than merely asking whether a fight is possible; it also describes composition timing and wave control as the basis for creating numbers advantages and tower pressure [1]. The Bilibili page is titled “花海第一视角复盘，来学影的实战细节” and its visible course description calls out flexible basic attacks, early-versus-late rotation priorities, farming discipline, hidden/false vision, and using a skill to flank the backline [2]. Search-discovered public titles show the same review format across 05最强海月, 无畏, high-rank jungle, mid, and support content, but the Douyin page for 05最强海月 timed out and several repost pages exposed no transcript. Those items are therefore treated as **format and topic leads**, not verbatim quotations [3] [4] [5] [6].

> “所有的决策都要围绕‘塔’来做。转线、换线、卡位置、占视野等等，你的每一步决策都要有极强的目的性。” — 王者荣耀官方赛事运营分析 [1]

The analysis intentionally distinguishes **verified evidence** from **topic inference**. A video title is enough to establish that the creator presents first-person full-game replay teaching, but not enough to establish a particular spoken judgment. This prevents the research from laundering search snippets into false transcripts.

## Taxonomy of replay feedback

| Category | Chinese coaching labels and examples | What the reviewer is actually diagnosing | Minimum evidence for reliable automation | Current hokcoach status |
|---|---|---|---|---|
| Information and vision | 探草意识、藏视野、给假视野、敌方消失后的危险区、听声辨位 | Whether the player entered a low-information area, exposed a predictable route, or failed to convert known enemy absence into a safer plan | Player/minimap coordinates, brush/map geometry, enemy visibility intervals, ward/vision signals, audio cues | **Partial**: death proxy and minimap context exist; full ten-hero identity and brush truth do not |
| Macro tempo | 转线、支援优先级、发育路线、前中后期节奏、优势扩大、逆风止损 | Whether the player traded farm, pressure, and time for the right next action given composition power spikes | Wave state, lane-clear timestamps, ten-player trajectories, composition phase, tower state, economy/experience timeline | **Partial/Gap**: static knowledge and death categories exist; continuous temporal state is missing |
| Wave and resource economy | 兵线运营、卡线、贪线死、反野、龙/主宰资源交换 | Whether a wave or neutral objective was worth the exposure and whether the team converted priority into something durable | Wave spawn/clear/last-hit events, gold/XP timeline, objective spawn/secure, tower damage, enemy rotation | **Gap** except for coarse `pushing_wave` signal and knowledge entries |
| Equipment awareness | 出装意识、克制装、节奏装、终局装备、何时补防装/穿透/续航 | Whether the build responds to enemy damage, control, healing, armor, and the game’s actual timing | Item purchase timeline, gold, enemy threat tags, patch-valid item data, role/hero build context | **Gap**: repository matrix correctly identifies terminal-only as P1 and purchase sequencing as P2 |
| Mechanics | 操作技术、技能前后摇、连招、拉扯、普攻/蓄力、精准度 | Whether a mechanically feasible action was executed with correct timing, target, range, and sequence | Skill/icon OCR or game telemetry, cast timestamps, target positions, hit/miss, cooldowns, frame-level input proxy | **Gap**: current classifier intentionally refuses to turn a death into “操作失误”; `大闪` is not provable without cast/telemetry evidence |
| Teamfight | 团战站位、进场时机、切后排、先手/后手、目标选择、撤退窗口、换头价值 | Whether the player entered when allies could follow, respected enemy threat range, chose the correct target, and exited after value was secured | Teamfight window, all-hero positions, HP, cooldowns, threat/CC, damage/kill events, target identity | **Partial**: `掉点死`/`换头死` support direction-only feedback; full causal review is missing |
| Conversion and objectives | 打赢团后推塔/拿龙/入侵/回城、推塔优先、优势压制 | Whether a local win became map advantage rather than a low-value chase | Fight result, wave position, tower/objective state, travel time, remaining HP and enemy death timers | **Gap**: official guidance makes this central, but current pipeline does not link fights to outcomes |
| Composition and matchup | 阵容合理性、英雄克制、伤害类型、控制链、强势期、BP | Whether the plan is consistent with both compositions and each hero’s timing | Structured hero role/damage/CC/power-spike data, patch version, selected heroes, lane assignments | **Content + P1**: knowledge base can carry facts, but schema and aggregation need expansion |
| Attribution and mentality | 谁的问题、可控失误、队友依赖、抗压、不上头、固定约束 | Whether feedback is actionable, evidence-calibrated, and adapted to the player’s constraints rather than blame-oriented | Evidence quality, repeated patterns, player constraints, optional self-report; never infer hidden intent without proof | **Partial**: constraints and evidence-weighted training exist; emotion itself is not observable |

## Base capability required to provide each feedback type

A human streamer compresses several hidden capabilities into one sentence. For implementation, those capabilities should be separated into six layers.

| Capability layer | Questions it must answer | Typical technology |
|---|---|---|
| Perception | Where are the ten heroes, towers, waves, objectives, brushes, UI states, and damage events? | Video decoding, HUD OCR, minimap detection, icon/template matching, object tracking, audio event detection |
| Temporal reconstruction | What happened first, how long was the enemy missing, and what changed after the decision? | Timestamped event store, track association, interval reasoning, confidence propagation |
| Game-state knowledge | What does a hero, item, map mechanic, power spike, or objective mean in this patch? | Versioned structured knowledge base, patch validity, hero/item ontology, source review workflow |
| Decision evaluation | What alternatives were available, and which one maximized tower/wave/objective value under uncertainty? | Rule engine plus state evaluator, counterfactual candidate actions, utility scoring, risk model |
| Communication | Can the result be expressed as a short, specific, non-blaming next action? | Feedback templates, confidence labels, evidence snippets, LLM only as a language layer |
| Personalization | Is the action compatible with the player’s constraints and training history? | Constraint profile, repeated-pattern tracker, spaced training tasks, progress model |

The most important architectural principle is **separation of observation, evaluation, and narration**. The model should not use language fluency to fill missing observations. For example, a `机制死` label can trigger “collect skill timeline evidence”, but it cannot support the claim “your大闪 was late” unless a blink cast and target geometry are observed.

## Detailed gap map against hokcoach

| Gap | Why streamer feedback needs it | Existing repository capability | Severity | Proposed solution and test |
|---|---|---|---|---|
| Full ten-hero identity and trajectories | Needed for支援、跟团、人数差、团战站位 and teammate intent | Minimap HSV/connected components and enemy-context summaries; identity tracking is explicitly absent | High | Add role/color/template tracking with calibration; test precision/recall on labeled minimap clips |
| Wave/economy/objective timeline | Needed for兵线运营、贪线价值、推塔/拿龙转换 | Coarse `pushing_wave`, static map/economy knowledge, death timestamps | High | Detect wave/objective/tower events and calculate exposure-vs-value; test event timestamp tolerance and decision precision |
| Item purchase timing and patch-aware item ontology | Needed for装备意识 | No timeline; matrix identifies terminal-only as P1 and sequencing as P2 | High | OCR item slots at purchase moments plus versioned item facts; test slot recognition under HUD scale/contrast variants |
| Skill/cooldown/target timeline | Needed for大闪、连招、技能前后摇 and fine attribution | No robust skill-state reader; classifier deliberately avoids unsupported mechanics claims | High | Template/icon recognition + cast/hit windows + optional telemetry; test false-positive rate before exposing coaching claims |
| Teamfight detection and causal linking | Needed for进场、拉扯、切后、撤退、换头价值 | Planned/v2-style heuristic exists in matrix, but not a causal pipeline | High | Detect 6+ hero proximity plus combat/audio/kill corroboration; test event precision and lead/lag around fights |
| Composition ontology | Needed for阵容强势期、伤害/控制链 and BP | Hero JSON exists but role/damage/CC fields are incomplete | Medium | Extend schema with reviewed facts and patch validity; test retrieval and tier-3 exclusion |
| Version refresh | Needed because builds and strong periods are patch-sensitive | Knowledge process is largely manual | Medium | Add source manifest, patch version, review date, and diff-based refresh job; test stale-entry warnings |
| Training coverage | Needed to turn review into repeatable behavior | Four weakness tasks exist, with evidence-weighted scoring | Medium | Add category-to-task mappings for macro/equipment/mechanics/objective after perception signals are trustworthy |

## Hypotheses and verification plan

**H1 — Evidence-gated feedback is safer and immediately useful.** If each replay event yields a structured card containing capability, feedback, next action, evidence quality, and confidence, then the system can expand coaching coverage without hallucinating. This was implemented and verified offline: supported categories produce cards, proxy cases are capped at low confidence, and unsupported `大闪` claims explicitly request cast evidence.

**H2 — Death categories are a useful bootstrap, not a complete replay model.** They provide high-value anchors for探草、掉点、换头、贪线 and机制, but cannot explain successful decisions or objective conversion. The research supports promoting them to “event anchors” while building continuous timeline detectors around them. The current implementation adopts the anchor-to-card layer but intentionally does not claim full conversion analysis.

**H3 — High-confidence mechanics coaching requires a different data contract.** Adding stronger wording to the LLM prompt will not solve missing skill/cooldown/target observations. A prototype should first benchmark icon/cast detection on real recorded HUD clips; only if precision is high enough should the product expose “大闪时机” as an automatic conclusion. Until then, the adopted code uses a planned capability entry and evidence-gated language.

**H4 — Objective-centered evaluation should be the next major product increment.** Official coaching guidance consistently frames tower, wave, rotation, vision, and composition timing as the purpose of decisions [1]. A state evaluator that scores candidate outcomes—tower, wave, neutral objective, invade, safe reset—would better reproduce streamer value than adding more death labels. This is the highest-leverage next engineering track after perception validation.

## Adopted repository changes

The repository now includes `coach/core/feedback_engine.py`. It defines eight structured capabilities and their signal contracts: `探草意识`, `兵线与资源意识`, `转线与节奏`, `装备意识`, `操作技术（连招/大闪）`, `团战站位与目标`, `团战转化与推塔`, and `归因与心态`.

`build_replay_from_video()` and `classify_manual_replay()` now populate `replay["coaching_feedback"]`. Cards are deterministic and evidence-gated. They include `capability`, `name`, `title`, `feedback`, `next_step`, `evidence_quality`, `confidence`, `source_event`, and an evidence excerpt. `探草死` remains a proxy; `机制死` does not become an automatic“大闪失败” diagnosis; `装备意识`, `转线`, and `推塔转化` are represented in the capability catalog but do not emit unsupported conclusions from death-only data.

The canonical replay schema now initializes `coaching_feedback: []`. The README documents the new contract and the boundaries of automation. Five offline tests cover catalog presence, proxy confidence, mechanics evidence gating, manual replay integration, and duplicate-event de-duplication.

## Validation results

After installing the repository’s missing local test dependencies (`python-multipart` and `opencv-python-headless`), the complete offline suite passed:

| Validation | Result |
|---|---|
| New feedback tests | 5 passed |
| Existing targeted replay tests | 17 passed |
| Full repository suite | **144 passed, 0 failed** |
| Network/LLM dependence | Not required for the adopted change |
| Real streamer video transcript | Partially available; public metadata and official descriptions were accessible, while Douyin timed out and several video pages exposed no transcript |

## Recommended next sequence

The next implementation should not begin with more free-form prompting. First create a small, labeled evaluation set containing minimap clips, HUD item snapshots, skill-icon states, objective/tower states, and teamfight windows. Then benchmark perception and timestamp error. If the measurements pass explicit thresholds, add one capability at a time—teamfight windows and objective conversion before fine-grained“大闪” judgments—because those capabilities most directly explain the objective-centered coaching observed in the strongest sources.

## References

[1]: https://pvp.qq.com/gicp/news/600/570395.html "运营思路教学丨浅析游戏中的大局观理解，助你掌控全局节奏！ — 王者荣耀官方资讯团"
[2]: https://www.bilibili.com/video/BV1BDm1YpEgy/ "王者荣耀：影国服教学课程（实战复盘）：花海第一视角复盘，来学影的实战细节 — Bilibili"
[3]: https://jingxuan.douyin.com/m/video/7558851453407022382 "05最强海月全局思路打法教学（搜索发现；页面访问超时）"
[4]: https://www.youtube.com/watch?v=QHVOZlII7VE "峰赛1770分打野第一视角复盘教学全局讲解 — YouTube"
[5]: https://www.youtube.com/watch?v=jjlhUhB_znU "无畏辅助第一视角复盘 — YouTube"
[6]: https://www.youtube.com/watch?v=h3WcqAUkn_0 "120把上王者求复盘：小乔第一视角保姆级复盘教学 — YouTube"
