# HokCoach

HokCoach is an experimental AI replay coach for **Honor of Kings (王者荣耀)**. It turns replay evidence into conservative, evidence-linked coaching feedback instead of guessing when the video does not support a conclusion.

The repository contains the runnable coaching application, deterministic replay-analysis components, match-wide evidence timelines, detector calibration/evaluation tools, and a replay corpus pipeline.

## What works today

- Player profile, manual replay review, training check-ins, progress tracking, and weekly reports.
- Rule-based coaching and knowledge retrieval when no LLM is configured.
- Video replay analysis with calibrated KDA/death extraction for supported layouts.
- Audio-event timeline extraction from the bundled Honor of Kings voice templates.
- Normalized, provenance-preserving match timelines with explicit `observed`, `unknown`, and `unreadable` states.
- Deterministic detector stages for objective/tower fusion, lifecycle, economy/items, coarse waves, teamfights, and high-value cooldowns when suitable upstream observations exist.
- Operator workflows for visual labeling, cooldown calibration, kill-audio evaluation, and kill-feed fusion evaluation.

## Detector maturity

HokCoach separates a detector's architecture from its real-video calibration. A stage existing in code does **not** mean it is enabled or validated for every recording layout.

| Capability | Current status |
|---|---|
| KDA and death-centered analysis | Implemented for calibrated layouts |
| Game-voice template timeline | Implemented; conservative supporting evidence |
| Kill-announcement audio baseline | Evaluated experimental baseline; not production-enabled |
| Kill-feed visual confirmation | Human-labeled fusion result available; automatic visual recognizer pending |
| Objective outcomes | End-to-end scaffold; disabled pending direct held-out labels |
| Cooldown readiness | Opt-in calibrated pilot support; unsupported layouts abstain |
| Towers, recall, items/economy, waves, teamfight participation | Fusion/state stages implemented; raw-video recognizers remain calibration-dependent |

Unknown, unreadable, incompatible-layout, and conflicting evidence must remain abstentions. Reviewer speech, transcripts, and corpus hints are candidate-window navigation aids—not visual ground truth.

## Quick start

Requirements:

- Python 3.10+
- `ffmpeg` and `ffprobe` for video analysis
- Optional Python packages listed in `coach/requirements.txt`

```bash
git clone https://github.com/graceyunliu/hokcoach.git
cd hokcoach/coach
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create a player profile and run the application:

```bash
python coach.py --init
python coach.py --replay --manual
python coach.py --replay /path/to/replay.mp4
python coach.py --checkin --rate 90
python coach.py --weekly-report
python coach.py --progress --chart
python coach.py --chat
```

Automatic video results depend on the recording layout and configured extractors. Unsupported evidence is reported as unavailable rather than inferred.

## Optional model configuration

The manual workflow and deterministic rule layer can run without an LLM. For AI-written feedback or visual-model fallback, configure the environment variables referenced by `coach/config/config.yaml`, for example:

```bash
export COACH_LLM_API_KEY="..."
export COACH_VLM_API_KEY="..."
```

Do not commit API keys. Without a configured provider, HokCoach uses its documented degraded mode where possible.

## Tests

Run the offline application and detector regression suite:

```bash
cd coach
python3 -m unittest discover -s tests -p 'test_*.py'
```

Validate the stable replay corpus:

```bash
python3 tools/validate_stable_corpus.py
```

## Repository map

```text
coach/
  coach.py                 CLI entry point
  core/                    orchestration, replay engine, observations, detectors
  tools/                   extraction, calibration, annotation, and evaluation CLIs
  tests/                   offline regression suite
  config/config.yaml       feature flags, layouts, thresholds, and providers
  knowledge_base/          reviewed coaching principles
data/evaluation/           corpus manifests, compact labels, and evaluation reports
tools/                     corpus and experimental detector workflows
docs/                      detector architecture and operator documentation
```

Large replay media, generated labeling clips, caches, and API secrets are intentionally kept out of Git.

## Evaluation highlights

The committed kill-event stress evaluation demonstrates why multimodal confirmation is necessary:

- Audio baseline: 70% precision and 87.5% recall on the labeled stress split.
- Human-reviewed kill-feed decisions removed all three audio false positives in that split.
- Automatic kill-feed recognition is still pending, so this result is evidence for the fusion design—not a production accuracy claim.

The associated compact labels and reports live under `data/evaluation/operator_labeling/`.

## Documentation

- [Coach application guide](coach/README.md)
- [Production detector architecture](docs/production_detector_architecture.md)
- [Replay corpus system design](seed_corpus_system_design.md)

## Development principles

1. Preserve the source hash, timestamp, detector version, and evidence dependencies for every observation.
2. Keep tuning and held-out evaluation events separate.
3. Never treat missing evidence as a negative event.
4. Keep new recognizers disabled until their supported layouts and failure behavior are measured.
5. Commit compact, reproducible metadata—not source replay videos or regenerable caches.

HokCoach is under active development. Current detector metrics are pilot or stress-set measurements unless explicitly described as held-out multi-video results.
