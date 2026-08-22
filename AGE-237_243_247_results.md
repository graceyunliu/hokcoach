# AGE-237 / AGE-243 / AGE-247 implementation results

Date: 2026-08-21

## AGE-247: minimap geometry and player identity

### Orientation and river geometry

Official Honor of Kings competition rules allow a team to select red or blue
side, so draft side is not a safe proxy for a fixed raw-world orientation.
However, all three local player recordings render the player-facing minimap in
the same normalized orientation: friendly structures/base toward bottom-left,
enemy structures/base toward top-right. The displayed minimap orientation is
therefore fixed for this capture pipeline even though competitive side
selection can vary between games.

The river centerline was hand-annotated across representative frames from all
three Replay recordings in the calibrated 420x320 `minimap_crop`. It is stored
as a normalized polyline in `coach/config/config.yaml`, not scattered through
detection code. `river_side()` interpolates the polyline and returns
`friendly`, `enemy`, `river`, or `not_determinable`; it does not extrapolate
outside the annotated x range.

### Player icon identity

Result: option 1 from the ticket. The player's portrait has a bright green
outer ring; teammates use cyan/blue rings. The marker is visually present in
all three recordings. `detect_hero_icons()` now attaches
`player_marker=true`/`player_marker_source=green_outer_ring`, and
`identify_player_icon()` returns an icon only when exactly one marked candidate
exists. No marker or multiple markers returns `None`.

The first broad green threshold also detected scenery and green pixels inside
portraits. It was rejected during real-frame validation and replaced with a
ring-shape gate (roughly 50px, near-square, low filled extent). On nine
representative frames, the final detector uniquely identified one in-match
player frame from each recording and abstained where the player icon was
off-crop, obscured, or the recording was in a pregame screen. It never selected
an arbitrary blue teammate.

## AGE-237: anomalous displacement

`detect_anomalous_displacements()` implements the cheap kinematic detector. It
uses mutual-nearest-neighbor association between adjacent enemy icon sets and
flags distances above:

`max move speed * elapsed time * minimap pixels/world unit * 1.5 + jitter`

The output is explicitly `anomalous_displacement`, with a limitation noting it
may be a dash or tracking error; it never labels the result as Flash. Replay
context wiring is present and exposes findings to the LLM context.

The real recordings do not contain a calibrated world-unit-to-minimap-pixel
scale or ground-truth-labelled Flash timestamps. Those two config values remain
`null`, so the production pipeline abstains instead of inventing a scale. A
real-footage false-positive rate cannot honestly be reported yet. Unit tests
cover normal motion, a clear jump, and the exact boundary. To activate this
signal, calibrate `minimap_pixels_per_world_unit`, enter the applicable maximum
hero movement speed, and label several Flash/non-Flash windows for the requested
false-positive check.

## AGE-243: audio matching and fusion

`extract_audio_track()` successfully extracted the full 834-second
`ScreenRecording_08-12-2026 01-16-28_1.MP4` audio track as 16 kHz mono PCM
(26,690,720 bytes). `match_audio_template()` performs normalized log-spectrum
correlation and returns video-timeline timestamps. `fuse_visual_audio_confidence()`
can boost an existing visual candidate when a matching cue is nearby; audio
does not create primary events. Missing audio has zero penalty by default.

No production sound templates are shipped. The available death windows contain
combat, voice, and UI mixtures, and the repository has no isolated or labelled
callout clips. Treating one mixed fight as a fixed callout template would cause
fight-specific false matches. The catalog README documents this abstention and
the clean samples still needed (`first_blood`, `double_kill`, and
`tower_destroyed`) plus the required pairwise confusion check. A synthetic-tone
unit test verifies timestamp alignment and confidence fusion without claiming
that the real callout catalog has been validated.

## Verification

- Focused suite: 83 tests passed.
- Full suite: 102 tests passed.
- Full-recording ffmpeg audio extraction: passed.
- Python syntax compilation with an isolated bytecode cache: passed.
- `git diff --check`: passed.
