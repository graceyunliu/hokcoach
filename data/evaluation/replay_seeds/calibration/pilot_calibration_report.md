# Video 7 and Video 8 bounded calibration report

## Scope and stop condition

This report covers only the two locally available pilot recordings. No additional pilot video was processed. No unrepresented detector was promoted, and the Video 1 cooldown profile was not modified.

## Integrated test audit

The integrated checkout contains the reviewed annotation, ingestion, cooldown integration, raw extractor, tower recognizer, and safe-message coverage. Annotation provenance and deduplication are covered in `coach/tests/test_cooldown_milestone.py`; cooldown integration and shared-manifest loading are covered in `coach/tests/test_cooldown_integration.py`; deterministic raw extraction is covered in `coach/tests/test_raw_video_extractors.py`; tower integration is exercised through the raw-extractor/production architecture tests; and safe cooldown messaging is covered by `test_safe_messages_never_promote_unknown_or_unsupported` in `test_cooldown_milestone.py`.

One combined discovery from the integrated tree ran **191 tests**, with **1 skipped**, and passed. The earlier 206 count was from a different worktree state and could not be reproduced after integration. The category-level reviewed tests listed above are present; no reviewed test file in those categories is absent from the integrated tree. The lower total is therefore a discovery-set difference rather than a failure of the integrated suite.

## Source media

| Pilot | Video ID | SHA-256 | Dimensions | Duration | Retained calibration bytes |
|---|---|---|---:|---:|---:|
| Video 7 | `Tq5eD3ECpyw` | `44f26786b2709957ad7499162b7d04b811903ca82f175d2cdcfe7fc07ef88af7` | 1920×872 | 325.338 s | 9,627,436 |
| Video 8 | `KkFUSKztLBA` | `49439862f0d6de11cc42ca898398affd39cfdaea30c7b3f43dcd59ca8bcf9668` | 1920×1080 | 482.018 s | 6,922,791 |

The media files remain local and are not committed to Git. Source manifests and derived canonical records carry the corresponding media hash.

## Video 7 — 1920×872

The existing Video 1 profile `hokcoach-hud-1280x582-v1` was preserved unchanged. Its source compatibility check correctly returns **unsupported layout / abstain** for Video 7 because both the dimensions and source hash differ.

A separate scaffold named `hokcoach-hud-1920x872-v1` was created. The final layout check identified the actual gameplay composition and skill/HUD region, but reviewer composition/overlay content and the available temporal samples did not expose unambiguous ready/on-cooldown transitions. Cooldown calibration is therefore marked **unsupported by this recording**; no direct cooldown labels were promoted.

| Metric | Result |
|---|---:|
| Existing Video 1 profile result | unsupported layout / abstain |
| New profile status | scaffolded, disabled; calibration unsupported by recording |
| Labeled cooldown cases | 0 |
| Classified accuracy | not applicable |
| Coverage | 0.0 |
| New-profile abstentions | 100% by policy; recognizer not enabled |
| Thresholds/templates changed | No |

Directly visible evidence includes gameplay, minimap, HUD/skill icons, and burned-in Chinese reviewer text. Recall/lifecycle, objectives, economy/items, towers, waves, and hero/teamfight labels were not independently established. Claims and fixture windows remain navigation hints, not visual labels.

## Video 8 — 1920×1080

The existing Video 1 profile was run in compatibility-only mode and correctly requires **unsupported layout / abstain** for Video 8. The profile was not copied or altered.

A separate `hokcoach-hud-1920x1080-v1` scaffold was created. The final layout check identified the distinct gameplay composition and skill/HUD region, but reviewer composition/overlay content and the available temporal samples did not expose unambiguous ready/on-cooldown transitions. Cooldown calibration is therefore marked **unsupported by this recording**; no cooldown label was promoted.

| Metric | Result |
|---|---:|
| Existing Video 1 profile result | unsupported layout / abstain |
| New profile status | scaffolded, disabled; calibration unsupported by recording |
| Labeled cooldown cases | 0 |
| Classified accuracy | not applicable |
| Coverage | 0.0 |
| New-profile abstentions | 100% by policy; recognizer not enabled |
| Thresholds/templates changed | No |

Wave evidence is conservatively recorded as **visible but unlabeled** at 180 seconds. Other objective, recall, economy/item, tower, and hero/teamfight capabilities were not independently labeled. No detector was promoted.

## Runtime and retention

The local frame extraction and crop inspection were completed without reopening YouTube. The retained calibration derivatives occupy 9,627,436 bytes for Video 7 and 6,922,791 bytes for Video 8. No temporary audio cache was retained after successful STT promotion. No full media file was added to Git.

## Final status

The safe integration gate is closed successfully: the required modules and reviewed tests coexist, the combined integrated discovery passes, existing profiles abstain safely on incompatible layouts, and both new layout profiles remain disabled. Both recordings are marked `cooldown calibration unsupported by this recording`. No unsupported visual capability has been promoted, and no further labeling or infrastructure work should be performed on these recordings.
