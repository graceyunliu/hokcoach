# KDA digit templates (AGE-136)

These 32×32 binary glyphs are deterministic template-matching references for the
personal K/D/A HUD row. Each digit 0–9 has eight exemplars from the three real local
`Replay/*.MP4` recordings. Every digit has at least five exemplars (and common digits
have more). The source timestamps and visually verified K/D/A labels
are recorded in `coach/tools/generate_kda_templates.py`.

Regenerate from the repository root with:

```bash
python coach/tools/generate_kda_templates.py
```

The generator extracts five nearby frames around each hand-labelled anchor, uses the
same Otsu/connected-component/center-pad pipeline as production, and refuses to
succeed unless every digit has at least five exemplars. The replay files themselves
are intentionally gitignored; the small generated PNG references are committed.

Coverage note: digits 6–9 are real late-game HUD glyphs from replay 0. No recording
contains a personal K/D/A value of 10 or more, so multi-digit composition is covered
by synthetic unit tests rather than claimed as real-footage validation.

## Validation (2026-08-20)

- 13 visually checked frames outside the generator's timestamp/offset set: 12 exact
  K/D/A reads, one low-confidence abstention, and zero wrong returned values (92.3%
  coverage; 100% accuracy among returned reads).
- Full `extract_death_events` smoke run on all three recordings: four monotonic death
  transitions found in each recording (12 total), consistent with the visible K/D/A
  progression.
- Digits 6–9 occur in real replay 0 frames. Multi-digit `10` is a synthetic regression
  fixture because none of the recordings reaches a personal two-digit stat.

The retained abstention is a frame where the narrow digit `1` is joined to bright
underlying HUD text after thresholding. Returning `None` lets the caller's existing
nearby-frame resampling recover without converting low confidence into a false digit.
