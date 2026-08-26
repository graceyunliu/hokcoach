# XFeat evaluation spike (AGE-320)

## Scope and current path

This spike does not change production code. The repository has one
`cv2.matchTemplate` call, in `make_template_kda_reader` in
`coach/utils/video_utils.py`. It compares normalized 32×32 KDA glyphs with normalized
KDA exemplars. The death-X path does not use template matching; it uses HSV masks and
connected components.

## Method

`coach/tools/evaluate_xfeat.py` loads one existing KDA exemplar per digit, embeds each
in a reproducible synthetic 160×120 region at 0.5×, 0.75×, 1.0×, 1.5×, and 2.0×, and
compares predicted top-left coordinates with known coordinates. It reports localization
accuracy (within a scale-adjusted 2 px minimum tolerance) and mean pixel error.

The baseline uses `TM_CCOEFF_NORMED` with the exemplar at its native size. The second
backend, `xfeat_stub`, is an offline multi-scale template-search test double behind the
same matcher interface. Neither `xfeat` nor `kornia` is installed in the evaluation
environment. The stub result verifies the harness and illustrates the benefit a
scale-aware matcher could provide; it is **not an XFeat benchmark or parity result**.

Run locally with:

```sh
python3 coach/tools/evaluate_xfeat.py
python3 -m unittest coach.tests.test_xfeat_eval -v
```

## Synthetic result

| Scale | matchTemplate accuracy | mean error (px) | stub accuracy | mean error (px) |
| ---: | ---: | ---: | ---: | ---: |
| 0.50× | 0% | 10.76 | 100% | 0.00 |
| 0.75× | 0% | 6.50 | 100% | 0.00 |
| 1.00× | 100% | 0.00 | 100% | 0.00 |
| 1.50× | 0% | 16.81 | 100% | 0.00 |
| 2.00× | 0% | 28.98 | 100% | 0.00 |

Fixed-size template localization is resolution-sensitive in this controlled test. This
does not establish that the production KDA reader fails similarly: production first
segments and normalizes each glyph to 32×32. Synthetic scaling also omits compression,
HUD layout changes, aspect-ratio changes, interpolation differences, occlusion, motion,
and phone-specific rendering.

## Recommendation: no-go for migration

XFeat parity is not met because real XFeat was not executed and no labeled multi-phone
footage was available. Keep `matchTemplate` as the production default. A follow-up may
integrate a pinned XFeat implementation into this interface, cache model weights for
offline evaluation, and run both matchers on labeled crops from representative phones,
resolutions, recording bitrates, and HUD layouts. Gate adoption on per-device accuracy,
localization error, false-positive rate, latency, and memory at least matching the
current end-to-end reader.

## Rollback plan

If a later change adopts XFeat, leave `make_template_kda_reader` and its assets intact
and default configuration to `video.kda_matcher: template`. Enable XFeat only through
the explicit value `xfeat`; instantiate it only in that branch and fall back to the
template reader with a warning on import or model-load failure. Rollback is changing
the flag to `template`, requiring no data migration. Removal of the template path or
assets requires a separate reviewed change after a successful real-footage rollout.
