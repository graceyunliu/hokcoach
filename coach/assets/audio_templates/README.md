# Audio callout template catalog (AGE-243)

The three Replay recordings all contain AAC stereo audio, but no isolated,
ground-truth-labelled callout clips are available in the repository. Candidate
death windows also contain combat, voice, and UI sounds. Those mixtures are not
safe templates: accepting them would make the matcher learn a particular fight
rather than the fixed announcement.

Accordingly, no production templates are shipped yet. This is an explicit
abstention, not an empty catalog accidentally treated as configured. Add only
clean PCM WAV clips (16 kHz mono, ideally captured from the game's sound test or
a manually verified quiet segment) and document each item here with source
recording, exact time range, label, and confusion checks against every other
template.

Candidate labels to capture and validate:

- `first_blood.wav`
- `double_kill.wav` (and other multi-kill callouts only if pairwise confusion is low)
- `tower_destroyed.wav`

The utilities in `coach/utils/video_utils.py` extract PCM audio, perform
normalized log-spectrum template matching, and fuse a matching event into an
existing visual candidate's confidence. Audio never creates a primary event by
itself. A missing cue has zero penalty by default because recording/game audio
may be muted or mixed; configure a penalty only after recall is measured.
