# 王者荣耀 — Content Strategy & AI Coach: Full Discussion Summary

*Compiled August 11, 2026, from a conversation applying agentic-systems lessons (pipeline decomposition, feedback loops, eval/rubric design) to a personal domain.*

---

## 1. Why 王者荣耀 became the testbed

The exercise from the agentic AI course was to pick an audience you genuinely know and write a topic-ranking rubric for it — because the durable human role in agentic systems is defining "good," and a rubric can only be written with a precise user in mind. 王者荣耀 was the natural choice: a near-daily hobby, 10,000+ games played, deep familiarity with the player community. The immediate problem identified: with 100M+ monthly active players, "people who play the game" is a population, not an audience. A rubric written for everyone produces the same commodity tier-list content that already floods the space.

## 2. The audience discovery

The useful segmentation turned out to be motivational, not demographic — what is the viewer trying to get when they open the content? The initial instinct ("people don't come to me for advice because I still suck") flipped into the audience definition itself: **the passionate average player** — someone who has played a great deal, remains average, and loves the game for its own sake.

The critical insight about this audience: their barrier to improvement is not informational but **emotional and social**. Instructional knowledge already exists everywhere. What blocks learning is the in-game environment — being flamed for mistakes, watching the loudest player redirect blame onto quieter teammates who lack the awareness or confidence to push back, and the self-doubt that accumulates from thousands of games of that feedback. Being of this audience (rather than above it) is the credential: a top-1% creator cannot authentically make content about this experience because they have never lived it. Ten thousand games of being average is the one thing skilled creators cannot fake.

By definition, in a 100M-player game, average players are the majority — and nearly all existing content is made by elite players for people who aspire to be elite. This audience is underserved.

## 3. Content angle evolution

**Rejected: instructional content.** Teaching requires being above your audience; that positioning isn't available (yet) and would be inauthentic.

**Angle one: relatable comedy.** Funny content about one's own blunders, absurd things other players do, and the ridiculous toxic moments everyone recognizes (the 蠢萌 / 神奇宝贝 experience). Key principle: instructional content requires being above the audience, but relatable content requires being *of* it. Recognition is the product — "I'm not the only one." Comedy also serves the deeper mission better than earnest essays: a funny video about the loudest player being the actual problem deflates toxicity more effectively than instruction ever could. Precedent exists at scale — major gaming channels are built entirely on fail compilations and "things every player does" humor. If pursued, the topic-ranking rubric shifts from educational value to comedic recognition: universality of the experience, freshness (not memed to death), punching at behavior rather than at individual players, and carrying a quiet awareness point underneath the joke.

**Angle two: the AI coach + learning in public.** Build a personal AI coach, track improvement in real time, and let the journey itself be the content. This resolves the credibility problem elegantly — no need to pose as an expert when the format is "average player with 10,000 games uses an AI coach to finally improve and shares everything: wins, tilts, what worked, what was snake oil." It is simultaneously relatable (still average, still learning) and aspirational (genuinely trying), and it naturally produces both comedy and improvement content.

## 4. The official tool landscape (and why it isn't a threat)

Discovery: the game's developers have released an AI 复盘 (replay review) aid that overlaps with several features the coach idea needed. Research confirmed Tencent is investing heavily here — the 灵宝 assistant is being upgraded into a full-time in-game AI companion with real-time interaction, official AI match commentary is live, and the 王者营地 companion app already offers replay tools analyzing team economy trends and key match events.

Two reframes turned this from bad news into good news. First, **validation**: the developer just confirmed that average players reviewing their games is a need worth serious investment. Second, **structural limits**: a tool built by the game company for all 100M players will never say "your jungler was the problem; disregard the pings." Official tools provide *data*. A coach provides *judgment* — interpretation, accountability, emotional context, and a memory of one player's specific patterns across months. The official 复盘 tool effectively became a free data layer to build the judgment layer on top of. The measurement infrastructure no longer needs to be built; only the evaluation and interpretation do.

## 5. The coach's requirements (in priority order)

As articulated, what the coach must deliver:

1. **Macro confidence for self** — knowing where I should be going at any given moment, with high confidence.
2. **Blame attribution** — when someone yells at me, determining whether it was actually my fault.
3. **Macro awareness of others** — knowing where teammates/opponents should be going.
4. **Capability limits and compensation** — understanding personal mechanical ceilings (hand speed, aim, specific matchups) and what can compensate for them, individually or through the team.

Pattern observed: three of the four are about *judgment*, not mechanics — and the gap between average and good players is overwhelmingly macro decision-making, which is exactly what AI can evaluate from replay data (while hand speed is what it can't fix anyway). The priorities happen to align with what is buildable.

Item 2 is the standout feature and the one Tencent will never ship: blame attribution as a checkable eval. An agent can review a lost fight, trace the sequence (who engaged without vision, who was out of position first, whose cooldowns were down), and render a verdict — "The teamfight at 8:32 was lost when your jungler face-checked without vision. Your positioning was correct. Disregard the pings." This is a mental-health intervention disguised as a stats tool, it directly attacks the audience's core emotional barrier, and it is inherently content ("I had an AI judge my flame wars — here's who was actually at fault").

## 6. The ground truth problem — what does "should" mean?

Priorities 1 and 3 both require the coach to know where a player *should* be — which demands a defined standard. Investigating how Tencent's own AI derives its standard: 绝悟 was trained first by imitation learning from real player match samples, then surpassed human play through massive self-play reinforcement learning, optimizing purely for win probability — even discovering non-human strategies (e.g., grouping heroes to share lane farm for economic efficiency). 灵宝, by contrast, is a generative-AI agent layered on live match state, offering real-time reminders — heuristics plus language model.

The flaw in Tencent's ground truth is the same one identified earlier in the conversation: self-play-optimal play assumes perfect reaction time, perfect coordination with four copies of itself, and no tilt. It knows what a superhuman would do; it cannot say what *this specific player* should do given their capability limits and their actual teammates. Optimal pro macro can be actively wrong advice for a team of average players who won't rotate with you.

Three candidate ground truths emerged, and choosing among them is a design decision, not a discovery:

- **Outcome-based**: what statistically wins from a given state (Tencent's approach — powerful, calibrated to the wrong player).
- **Descriptive**: what players one or two ranks above do in the same situation — achievably better play rather than perfect play.
- **Principle-based**: codified coaching heuristics ("don't cross the river without vision") — less precise but *explainable*, which matters because the coach's verdicts must persuade a human who just got flamed and is doubting themselves. A win-probability number convinces nobody; "you broke no principle here; your jungler broke this one" does.

## 7. The proposed solution: configurable role-model standard

The design answer: derive the coach's standard from a player the user already follows and admires — feed it that player's match VODs and coaching videos, aligning the coach to *their* standard and their stated advice. Make the role model configurable, since most players already have creators they trust.

This works on two levels. Technically, it answers the ground-truth question ("should" = what this specific respected player would do, by their own stated principles). Psychologically, it solves the persuasion problem: "your idol would have backed off here — he says exactly this in his coaching video about overextending" carries authority and motivation because the user chose whom to trust. This is inherently personal in a way Tencent's one-size-fits-all assistant cannot match.

One caveat carried forward: the idol is presumably elite, so the "calibrated to the wrong player" problem re-enters through the side door — imitating a pro's positioning assumes a pro's hands and teammates. Mitigation: coaching *videos* are better source material than raw gameplay, because good players teaching translate their play down into principles meant for people below them. The blend: **their principles as the rubric, not their exact movements as the template.**

## 8. The sports analogy and the deepest eval lesson

The sports framing surfaced independently: in sports there is no single "right" rubric — general fundamentals exist, but every coach has a different teaching style and every player a different playing style. This generalizes into perhaps the deepest lesson about evals in the whole exercise: **there is no objective rubric, only chosen ones.** A layer of agreed fundamentals, and above that, taste. Designing an eval is not discovering the right answer; it is committing to a definition of good. This is precisely why it cannot be delegated to the agent — the agent can apply any rubric flawlessly but cannot say which one to want.

## 9. The style question — reframing 蠢萌

The claim "players like me don't have a style; we're just labeled 蠢萌 / 神奇宝贝 — we're not good enough to find our style YET" was challenged with a sports counterpoint: style isn't something earned after getting good — **style forms around your limits**. The short player develops the floater; the slow boxer becomes a counterpuncher. Style is compensation, systematized — which is exactly priority #4 on the coach's list. Ten thousand games of history necessarily contain patterns of disproportionate strength (surviving ganks, vision, objective timing, particular heroes) invisible to the player because "we suck" flattens everything. An agent mining that history isn't just grading against an idol's standard; it could hand back the first draft of the player's own style. That may be the real product and the real content: not "AI coach makes me pro," but "AI coach helps a 蠢萌 player find the style hiding in 10,000 games of losing."

## 10. The confidence problem — the coach's first job

When asked to guess what the data would show as existing strengths, the honest answer was: "I'm not sure. I have very low confidence inside this game." This was identified as the most important data point in the conversation. Ten thousand games without being able to name a single strength is statistically implausible; far more likely, the self-assessment was trained by a corrupted feedback loop — thousands of games where the loudest signals were flame, defeat screens, and 蠢萌 labels. Bad data in, low confidence out — structurally identical to the clickbait-blog failure mode: a feedback loop optimizing on a garbage metric, except the miscalibrated system is the player's self-image.

This reframes the coach's first job: **before improvement, an accurate mirror.** Before "here's what to fix," it must establish "here's what the evidence shows you already do well" — from data, indifferent to who yelled. Also noted: showing up for 10,000 games despite all of it is itself evidence of a love for the game most players don't have, and the thing fellow 蠢萌 players would recognize instantly.

## 11. Baseline data (saved to memory, as of July 26, 2026)

巅峰赛 score: **1362**. Season S44, 5v5/巅峰赛 filter, all positions:

| Metric | Value |
|---|---|
| 场次 (games) | 42 |
| 胜率 (win rate) | 45.2% |
| KDA | 5.5 |
| 参战率 (fight participation) | 63% |
| 金币/分钟 (gold per minute) | 504 |
| 英雄伤害/分钟 (hero damage per minute) | 1,718 |
| 承受伤害/局 (damage taken per game) | 83,884 |
| 综合得分 (overall score) | 69.3 |
| 顶级/金/银/铜牌 (medals) | 0 / 1 / 4 / 2 |
| 全场最佳 (MVP) | 1 |
| 败方最佳 (best of losing side) | 1 |

英雄战力 (hero proficiency): 瑶 6,085 · 朵丽亚 6,065 · 蔡文姬 5,200.

## 12. What the mirror already found

The first finding arrived before any system was built: the "no style" claim is contradicted by the data. All three top-proficiency heroes are supports — a choice made thousands of times across 10,000 games, not an accident. **The style is: protector/enabler.** The stats corroborate the role played correctly: 63% fight participation (showing up for the team), 83,884 damage absorbed per game (bodying for the carries), KDA 5.5 (doing it without feeding), and low gold per minute (correctly yielding farm — the support's job done right). Noted poetry: the player who says "I'm not qualified to give anyone advice" has spent 10,000 games in the role whose essence is enabling others.

The honest half of the mirror: 45.2% win rate at 1362 is the number that hurts. Fundamentals (participation, absorption, survival) look decent, yet the record is slightly under water — for a support, that gap usually lives in decision quality rather than effort: attaching to the wrong teammate, right place at wrong time, protecting the loudest player instead of the winning one. Priority #1 ("where should I be going") translates, for a support, into "**who should I be with, and when**."

## 13. Open questions and next steps

**Open question (asked, unanswered):** Was support chosen out of love for the role, or partly because it felt safer — less blame, fewer mechanical demands, less visible failure? Both answers are legitimate, but they point the coach (and the content) in different directions.

**Next step (the instructor's philosophy, applied literally):** Don't theorize — go look. The first experiment is not building the full coach; it is pulling personal match history from 营地 and asking one question: *what am I already better at than I believe?* A weekend project with Claude, the first real artifact of the system, and — win or lose — the first piece of journey content.

---

## Appendix: How this maps back to the course's system lessons

The whole thread is the autonomous-blog architecture pointed at a person instead of a store. Signal acquisition = match data and replays. Prioritization = the rubric (idol-derived principles). Enrichment = replay analysis and blame attribution. Production = journey content and comedy. Feedback = performance data recalibrating both the coach and the player's self-image. The non-delegable human act, everywhere: defining the evaluation rubric — and the newest corollary: sometimes the system's first output isn't improvement at all, but an accurate mirror.
