# Team-fight replay review simulation

**Scenario:** Mid-lane team fight at 6:52 while an allied wave moves toward the enemy mid second tower. The player intended to clear the wave before joining, but the enemy engaged during the transition.

**Command:** `cd coach && python3 tools/simulate_teamfight_review.py`

## Result

The replay engine classified the event as `机制死` with confidence `0.30` and `evidence_sufficient: false`, rather than incorrectly labeling it `贪线死`. That abstention is intentional: a wave candidate was visible, but the same window contained confirmed enemy engagement and an audio combat corroboration.

The evidence ledger reported that the direct minimap X marker supplied the death location, death-preceding minimap context was available, visible enemy engagement was present, audio events were available as corroboration only, and player intent was recorded: “我想先把中路线清掉再接团，但看到对面开团后反应慢了”。

The unresolved evidence was explicit: minimap wave/tower evidence was inconclusive at 78% coverage; team-fight and wave-clearing signals overlapped, so the event must not be labeled greedily; and enemy displacement remained unavailable.

The coach-first question was:

> 我们先不急着下结论：你当时看到了什么、觉得哪里是安全的、又是根据哪条敌方信息做判断的？

The player-facing takeaway was:

> 先判断开团与人数优势，再决定是否清线；本次不把同时出现的兵线候选误判成贪线死。

## Interpretation

This simulation validates the intended real-coach sequence: recover player perception and intent, display verified evidence, identify what remains uncertain, and only then assign a correction. It also validates the AGE-239 safety requirement that “wave present” is not equivalent to “greedy wave death,” especially during a team fight.

This is a deterministic contract simulation, not real-footage accuracy validation. Real minion/tower thresholds still require labeled recordings covering pure clear, pure tower push, and mixed team-fight-plus-wave cases.

## Validation

The simulation assertions passed, and the complete connected-checkout suite passed with **139 tests and 0 failures**. The AGE-239-related changes preserve `minimap_object_evidence` through replay assembly and expose mixed-combat uncertainty in the evidence ledger.
