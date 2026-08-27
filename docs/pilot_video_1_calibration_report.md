# HokCoach Pilot Video 1 Calibration Report

## Canonical-hash provenance

Pilot Video 1 is **`Seed Videos/hokclass_001_QK9QwHo1RhY.webm`**, source layout **1280×582**, duration **390.728 seconds**, SHA-256 **`d01e7764fbbc67ac348bfb116ce0bda895120e0a802713acdcc8c8f53354d13d`**. The five local files previously treated as pilot videos are one canonical source, not five independent videos. Existing STT, claims, and fixtures whose provenance does not explicitly match this hash remain quarantined candidate hints and were not used as evaluation ground truth. Out-of-range windows were rejected rather than remapped.

## Cooldown HUD

The measured candidate ROIs are Flash/summoner skill **`x=800,y=475,w=85,h=90`** and ultimate **`x=1040,y=450,w=120,h=120`**. Tuning and evaluation timestamps were kept disjoint. Tuning examples were Flash at 37 s (`ready`), 63 s (`on_cooldown`), and 238 s (`ready`), and ultimate at 37 s (`ready`), 63 s (`ready`), and 153 s (`on_cooldown`). Evaluation examples were Flash at 174 s and 195 s (`on_cooldown`) plus 260 s (`unreadable`/ambiguous), and ultimate at 174 s, 195 s, and 250 s (`ready`). The tuning timestamps `{37, 63, 153, 238}` and evaluation timestamps `{174, 195, 250, 260}` are frame-level disjoint.

A deliberately small deterministic baseline was implemented in `coach/core/cooldown_recognizer.py`. It uses normalized grayscale template error, a score-margin abstention rule, and a slot-specific luminance validity gate. The recognizer emits explicit `observed`, `unknown`, and `unreadable` states and fingerprints template content and thresholds in its detector version.

| Evaluation result | Count |
|---|---:|
| Classified correct | 5 / 5 |
| Classified accuracy | 100% |
| Classified coverage | 5 / 6 (83.33%) |
| Expected abstention correct | 1 / 1 |
| Abstentions | 1 |
| Overall expected-behavior agreement | 6 / 6 (100%) |
| Detector version | `cooldown-template-v1:86de4f26a1425ce3` |

These metrics are **pilot-only** and not evidence of production generalization. The sample is too small for a reliable threshold claim; additional independent footage is required.

## Coarse wave evidence

Directly visible minion evidence was retained at 45 s and 60 s for tuning, and 75 s and 120 s for evaluation. Labels contain only what is directly visible: minion presence, approximate side/color when discernible, and coarse screen region. Lane identity, exact cluster size when unclear, direction, tactical intent, and other inferred semantics are explicitly `unknown`.

The four frames are heterogeneous because the camera and combat context move substantially. Therefore no generic wave recognizer was promoted from Video 1. The evidence and labels are stored in `data/evaluation/replay_seeds/calibration/hokclass_001/waves/wave_evidence_labels.json`.

## Remaining capabilities

The following capabilities are recorded as **`not independently labeled in pilot video 1`**: lifecycle/recall UI, objectives, economy/items, towers, and hero/teamfight evidence. Tower calibration is specifically **`not represented with independently verifiable labels`**; no templates or thresholds were created. Minimap tower identity and destruction transitions remain unverified.

## Validation, storage, and runtime

The complete regression suite ran **177 tests with 0 failures**. `git diff --check` passed. The cooldown calibration directory occupies approximately **316 KB**, and the wave evidence directory approximately **644 KB**. On the 390.728-second source, measured evaluation crop extraction took **0.260 s**, recognition took **0.0027 s**, and combined processing was **0.0403 s per source minute**. The focused cooldown and raw-extraction integration tests pass independently. No commit was created, and no unrelated untracked files or `Seed Videos/` were modified.

Cooldown recognition is now wired through raw extraction and emits the established `cooldown_ui` contract, but remains disabled by default in configuration. Production integration is therefore **implemented but opt-in**; normal replay processing is unchanged. Existing death-analysis behavior remains preserved. Generalization beyond this single video remains not evaluated.

## Requirements for an independent Pilot Video 2

Pilot Video 2 must be a genuinely different recording with a distinct media SHA-256, independently captured at a documented resolution and duration. Its source manifest should include the original file hash, capture layout, and timing origin. It should contain readable examples of cooldown state transitions and several directly visible minion waves across at least two contexts, with enough separation to reserve tuning and evaluation timestamps. For lifecycle, objectives, economy/items, towers, and teamfights, the recording must expose directly verifiable UI or map evidence before labels, templates, or thresholds are created. Claims and STT may nominate windows, but only hash-matched visual evidence may supply labels.
