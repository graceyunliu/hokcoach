# Audio callout template catalog (AGE-243)

The three Replay recordings all contain AAC stereo audio. Candidate windows
were anchored to the 12 deaths independently detected by the KDA counter, then
searched for short log-spectrum motifs that repeated across different fights.

## Shipped experimental template

### `player_death_v1.wav`

- Meaning: fixed player-death UI/callout motif; it does **not** identify a kill,
  multi-kill, tower event, or Flash.
- Source: `Replay/ScreenRecording_08-12-2026 02-03-33_1.MP4`, video timeline
  305.315-306.115 seconds.
- Format: 16 kHz mono, 16-bit PCM WAV, 0.800 seconds.
- SHA-256: `f38ff50d700aacb15d5d3760cc709b65994e1ba9bd0b9985d5c0672a690b3372`.
- Selection method: the segment's spectral motif repeated around independent
  KDA-confirmed deaths rather than occurring in only one fight.
- Validation at similarity threshold 0.82: four matches across the three
  recordings, all within 3.2 seconds of a KDA-confirmed death; no off-death
  matches. Against all 12 detected deaths this is observed precision 4/4
  (100%) and recall 4/12 (33%). This is a small qualitative dataset, not a
  production-quality accuracy claim.
- Limitation: no matches in the first recording and one of four deaths missed
  in each of the other two recordings. Use only as positive corroboration;
  absence must carry zero penalty.

The three kill-trade windows in the first recording were also checked. Their
best common 0.8-second motif had only 0.741 worst-case similarity and a template
from one event did not reproduce at the other two at threshold 0.82. It was
rejected rather than mislabeled as a reliable kill announcement.

No redistributed `first_blood`, `double_kill`, or `tower_destroyed` WAV is
shipped. A local collection can now supply these voices through
`game_voice_catalog.json`; only its semantic metadata is committed.

Candidate labels to capture and validate:

- `first_blood.wav`
- `double_kill.wav` (and other multi-kill callouts only if pairwise confusion is low)
- `tower_destroyed.wav`

## Local 65-voice semantic catalog

`game_voice_catalog.json` maps the 65 files in the repository-root
`Game Voices/` directory to stable semantic event IDs. Alternate announcer
wording, including the Jinchan (`金蝉`) nonviolent callouts, maps to the same
underlying event. Each record also carries perspective and one usage policy:

- `evidence`: may positively corroborate a gameplay event;
- `intent`: a player-issued tactical ping, not proof the action happened;
- `context`: match-phase context rather than a coaching event;
- `exclude`: draft/ban audio, excluded from gameplay detection.

Load metadata with `load_audio_template_catalog()` or resolve locally available
files with `resolve_audio_template_catalog()`. Consumers should normally select
`usages={"evidence"}`. The raw directory is deliberately ignored by Git: the
downloads are Tencent game audio and VoiceWiki does not establish a clear right
to redistribute third-party works.

The local collection was inspected before use: all 65 files are ordinary
RIFF/WAVE PCM, every declared RIFF size equals the physical file size, only
`fmt ` and `data` chunks are present, and every file decodes with FFmpeg. This
rules out the common disguised-file/appended-payload risks; it is not a claim
that a general-purpose malware scanner was run.

Pairwise log-spectrum confusion was also checked across the collection. The
largest observed aligned similarity was 0.667, below the matcher default of
0.78. This indicates useful separation on this dataset but is not a production
accuracy guarantee; recording mixes and future announcer variants still need
false-positive validation.

The utilities in `coach/utils/video_utils.py` extract PCM audio, perform
normalized log-spectrum template matching, and fuse a matching event into an
existing visual candidate's confidence. Audio never creates a primary event by
itself. A missing cue has zero penalty by default because recording/game audio
may be muted or mixed; configure a penalty only after recall is measured.
