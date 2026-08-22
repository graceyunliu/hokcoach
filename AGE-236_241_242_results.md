# AGE-236 / AGE-241 / AGE-242 implementation and evaluation results

Date: 2026-08-21

## AGE-236: blocked on missing calibrated inputs

The repository has a calibrated minimap crop (`video.minimap_crop`) but no
river/center-line geometry, base orientation, or equivalent map transform.
`detect_hero_icons()` also returns undifferentiated blue `allies`; it does not
identify the player's own icon. Those are both required to decide whether the
player is in the enemy half and measure player-to-nearest-ally distance.

Guessing a diagonal or treating an arbitrary blue component as the player
would turn this into a plausible-looking but ungrounded production signal. Per
the ticket's explicit blocker rule, detection was not fabricated. The replay
assembly layer now preserves `event["solo_in_enemy_half"]` when an upstream
detector can legitimately produce it, and unit coverage confirms it reaches
the existing 掉点死 rule.

Required unblock inputs:

1. Calibrated river line in normalized minimap coordinates and which side is
   the enemy half (or a reliable per-match base-orientation signal).
2. A player-icon identity signal, distinct from the other blue ally icons.

## AGE-242: conservative HUD frame reuse

Implemented a switchable frame-hopper inside the existing coarse-sampling and
bisection path. Every scheduled HUD frame is still decoded. The three KDA digit
slots are compared using mean absolute grayscale difference; only when all
three are unchanged is the prior reader result reused. Any suspected slot
change forces full processing, so the death-event trigger cannot be skipped.

Real-video A/B input:
`Replay/ScreenRecording_08-12-2026 02-03-33_1.MP4` (933.9 seconds), production
template reader, 75-second coarse interval, 3-second bisection precision.

| Mode | Wall time | Full reader calls | Reused | Death events |
|---|---:|---:|---:|---:|
| Off | 14.794 s | 73 | 0 | 4 |
| On, threshold 1.0 | 16.512 s | 71 | 2 | 4 |

The four event timestamps, windows, before/after KDA values, and `kill_traded`
values were identical. Reader-call savings were **2.74%**. Wall time regressed
by **11.61%** in this run because ffmpeg still decodes every scheduled frame and
the local template reader is cheaper than the added image comparison. Thresholds
2, 3, and 5 preserved all four events but skipped only 2, 3, and 3 reads,
respectively, so loosening the threshold does not change the conclusion.

Verdict: the safety-preserving implementation is valid, but it is not a useful
default optimization for the current sparse + local-template pipeline. It may
still save substantial cost when the injected reader is a remote VLM. Keep it
switchable; do not claim overall compute savings from the template benchmark.
The learned FrameHopper policy remains a possible future experiment, not part
of this change.

## AGE-241: XFeat evaluation

Official implementation and pretrained `xfeat.pt` weights were used from the
[VERLab XFeat repository](https://github.com/verlab/accelerated_features). The
authors describe sparse CPU inference as real-time at VGA resolution; the
model is designed for scene correspondence and returns learned local features,
not digit classes. See the [CVPR 2024 paper](https://openaccess.thecvf.com/content/CVPR2024/papers/Potje_XFeat_Accelerated_Features_for_Lightweight_Image_Matching_CVPR_2024_paper.pdf).

The original 14 held-out HUD frame files cited by the AGE-131/136 case study no
longer exist as a reproducible set in the repository. Only two illustrative
crops remain, so reproducing the historical 14/14 claim apples-to-apples was
not possible. A replacement stress set of 14 deterministic variants was built
from the remaining labeled `(1, 3, 0)` slot crop: five scales, five JPEG quality
levels, two blur levels, and two brightness levels. This is a robustness probe,
not a substitute for 14 independently labeled gameplay frames.

For XFeat, every production glyph exemplar was embedded with the official
pretrained sparse model; a query digit was assigned to the class with the best
descriptor-similarity score across its exemplars. Both methods used the same
production glyph library.

| Method | Exact KDA accuracy | Mean time / three-slot frame |
|---|---:|---:|
| Production `matchTemplate` reader | 11/14 (78.6%) | 5.50 ms |
| XFeat descriptor classifier | 2/14 (14.3%) | 22.66 ms |

The template reader rejected the three severe scale transforms (`None`) rather
than returning a wrong KDA. XFeat returned a digit tuple for every case but was
usually wrong, including the unmodified scale-1.0 crop. It was approximately
**4.12x slower** in this CPU test. This is consistent with a task mismatch:
32x32-ish monochrome HUD glyphs contain little stable local geometry, whereas
XFeat is built for image correspondence across larger scenes.

Verdict: **do not adopt XFeat for KDA digit reading**. It is less accurate,
slower, adds PyTorch/model-weight operational cost, and converts safe rejection
into confident-looking wrong digits. The ticket's conditional AGE-238 follow-up
was not run because XFeat showed no clear advantage in the primary evaluation.
No production migration occurred, so no rollback plan is needed.
