# Dragon-contest replay review simulation

**Scenario:** A high-pressure 暗影暴君 contest with incomplete enemy vision and simultaneous bottom-lane minion pressure. The player wanted to pressure the enemy through the side lane before entering the objective area, while the enemy jungler had been missing for 12 seconds.

## Final result

The replay engine classified the death as **机制死**, with confidence **0.30** and `evidence_sufficient: false`. It did not label the event `贪线死` or `探草死`.

This abstention is the correct coaching behavior. The scenario contains a bottom-lane wave candidate and a nearby tower, but minimap-object coverage is only 54%; enemy engagement is unknown; and the enemy jungler is missing. The available evidence cannot safely distinguish between a vision error, an objective-entry error, an attempted pressure play, or a direct brush ambush.

The evidence ledger recorded these observed facts:

| Observed evidence | Meaning for the coach |
|---|---|
| Death location came from the direct minimap X marker | Location is reliable: 暗影暴君坑口 |
| Death-preceding minimap context exists | The coach can inspect the information state before commitment |
| Side-lane minion pressure exists | The wave is a decision context, not proof of greed |
| Objective audio corroboration exists | Audio supports the timeline but cannot independently identify the cause |
| Player intent is recorded | The coach can compare intended pressure with actual risk |

The unresolved evidence was equally important. The ledger reported that minion/tower evidence was inconclusive at 54% coverage, enemy engagement remained unavailable, and enemy vision was incomplete. It specifically instructed the coach to confirm threat locations before committing to the dragon area.

The player’s intent was:

> 我看到下路线在推，想先逼对面回防再进龙坑，但敌方打野消失太久了

The coach-first question was:

> 我们先不急着下结论：你当时看到了什么、觉得哪里是安全的、又是根据哪条敌方信息做判断的？

The resulting coaching takeaway was:

> 龙坑投入前先补齐视野并确认敌方打野位置；边线压力是决策背景，不足以替代安全进场条件。

## Safety bug found and fixed

The first run exposed a real attribution bug: `near_brush=True` combined with `visible_enemy_engagement=None` was treated as “no visible engagement,” producing a low-confidence `探草死`. That conflated **unknown** with **false**. The classifier now requires `visible_enemy_engagement is False` before creating the brush proxy verdict. Unknown engagement remains evidence-insufficient and is surfaced to the coach instead.

## Validation

The corrected simulation passed, and the complete connected-checkout suite passed with **140 tests and 0 failures**. The new regression explicitly verifies that unknown engagement cannot create a brush-death attribution. The simulation is deterministic and does not claim real-footage accuracy; labeled dragon-contest recordings are still needed to calibrate minimap-object thresholds.
