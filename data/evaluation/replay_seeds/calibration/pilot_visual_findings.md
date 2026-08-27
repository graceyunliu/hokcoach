# Pilot visual findings

## Video 7 — hokclass_007 / 1920×872

Representative contact sheet: `frames/hokclass_007_contact.png`, sampled at 30, 90, 150, 210, and 270 seconds. The rendered sheet visibly contains one populated gameplay frame at the left edge; the remaining tile area is black because the source frame inputs were not normalized to a common tile layout by the contact-sheet filter. The visible frame shows the minimap at top-left, HUD/skills at bottom-right, active combat and burned-in Chinese text. No direct cooldown state label is asserted from this sheet alone.

## Video 8 — hokclass_008 / 1920×1080

Representative contact sheet: `frames/hokclass_008_contact.png`, sampled at 30, 90, 150, 210, and 270 seconds. As with Video 7, the visible source frame shows minimap, bottom-right HUD/skill icons, gameplay, and burned-in Chinese text; remaining contact-sheet space is black due to differing frame dimensions in the tile filter. No direct cooldown state label is asserted from this sheet alone.

## Calibration decision

The contact sheets establish that the expected HUD regions are present, but they are insufficient to label ready/on-cooldown states reliably at the displayed scale. Cooldown evaluation must remain abstaining until individual full-resolution HUD crops are visually labeled with disjoint tuning and evaluation timestamps. Claims remain navigation hints, not visual labels. No unrepresented detector is promoted.

## Direct Video 7 crop labels

At 180 seconds, the proposed Flash crop contains a clearly visible golden boot icon with the Chinese label `草丛`, not an unambiguous cooldown-state overlay. The proposed Ultimate crop contains a dark blue crossed/locked-looking icon without a visible numeric cooldown or a reliably distinguishable ready state at this crop. These samples are therefore retained as directly observed HUD crops but are **not promoted as cooldown labels**. The ROI candidates require refinement before evaluation.

## Direct Video 8 crop labels

At 180 seconds, the proposed Flash crop shows a partial golden boot/icon with Chinese text but is clipped and does not expose a reliable ready/on-cooldown state. The proposed Ultimate crop shows a dark blue crossed/locked-looking icon with no readable countdown. These samples are retained as directly visible HUD evidence but remain **unlabeled for cooldown classification**. No accuracy or coverage claim is made from them.

## Final layout check — no relabeling

### Video 7

Normalized full-frame inspection confirms a 1920×872 recording containing a gameplay viewport with the game HUD concentrated toward the lower-right portion of the gameplay image, a minimap at upper-left, and reviewer text at the bottom. The full frame also includes composition/overlay content outside the game HUD. The previous candidate crops were not reliable enough to establish skill-state semantics. No cooldown labels or templates are created.

### Video 8

Normalized full-frame inspection confirms a 1920×1080 recording with a distinct gameplay composition, minimap at upper-left, skill/HUD icons in the lower-right gameplay region, and burned-in reviewer text. Its geometry differs from Video 7. The available arbitrary samples do not provide unambiguous temporal ready/on-cooldown transitions. No cooldown labels or templates are created.

### Final disposition

Both recordings are useful for unsupported-layout rejection and composition/viewport handling. For both videos, cooldown calibration is marked `cooldown calibration unsupported by this recording`. No thresholds, templates, or recognizers are promoted.
