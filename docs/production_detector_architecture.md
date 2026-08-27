# HokCoach Production Detector Architecture

## Purpose and boundary

The production detector layer extends the existing death-centered replay pipeline into a match-wide evidence timeline. It does not acquire or process the 100-seed corpus. Corpus windows and fixtures are consumed as ordinary input observations or time windows; reviewer speech, captions, seed metadata, and corpus labels never enter production extraction.

## Normalized observation contract

Every detector emits `core.observations.Observation` with the version `observation-v1`. An observation contains a stable deterministic ID, type, ordered time range, subject, structured value, optional confidence, detector/version, evidence references, status, and dependency IDs.

`observed` means the detector has evidence for the value. `unknown` means the relevant evidence is absent or insufficient. `unreadable` means the relevant region or signal was expected but could not be decoded. Unknown and unreadable observations cannot carry positive confidence and must not be converted to false, zero, or an empty event.

## Timeline and detector stages

`core.evidence_timeline.EvidenceTimeline` stores heterogeneous observations, preserves conflicting observations, supports range/type queries, deduplicates only equivalent records, and serializes deterministically as JSONL. `core.detector_stage` defines `DetectorContext`, `DetectorResult`, deterministic cache keys, stage metadata, warnings, runtime, and graceful exception handling.

The orchestrator exposes `run_detector_stage()` for one independent detector execution and `build_match_timeline()` for a complete match-wide pass. Existing `build_replay_from_video_path()` behavior remains intact; it additionally adapts legacy death and audio outputs into timeline observations and stores the resulting timeline and detector-stage results in optional replay fields.

## Production workstreams

| Workstream | Module/class | Output types | Evidence policy |
|---|---|---|---|
| #4 Objective/tower fusion | `ObjectiveTowerFusionDetector` | `objective_activity`, `objective_result`, `tower_state`, `tower_state_transition` | Audio is context only; results retain component references and temporal transitions. |
| #5 Lifecycle/recall | `LifecycleRecallDetector` | `lifecycle_state` | Death, respawn, and recall transitions are explicit; absent lifecycle evidence emits `unknown`. |
| #6 Economy/items | `EconomyItemDetector` | `economy_snapshot`, `item_snapshot`, `item_added`, `item_removed`, `item_replaced` | Snapshots are event-driven; changes are emitted only between observed snapshots. |
| #7 Coarse wave | `CoarseWaveDetector` | `wave_state` | Visibility limits remain explicit; wave evidence does not become tactical intent. |
| #8 Teamfights/membership | `TeamfightDetector` | `teamfight_episode`, `teamfight_membership` | Episodes require multiple or direct visual signals and retain all atomic dependencies. |
| #9 Cooldowns | `CooldownReadinessDetector` | `cooldown_readiness`, `cooldown_transition` | Scope is ultimate and summoner readiness; transitions are based on observed UI states. |

These are deterministic production implementations over normalized atomic evidence. They are deliberately conservative and abstain where inputs are missing, unreadable, or conflicting. They do not claim raw pixels were extracted when an upstream media-specific extractor has not supplied an observation.

## Cache and rerun semantics

Cache keys include schema version, source ID, media hash, detector name/version, complete detector configuration, model version, execution windows, and relevant upstream input identities. Calling `run_detector_stage()` for a detector is independent from unrelated detector stages. Derived detectors receive explicit dependency IDs in their observations. A production persistence layer can use `DetectorResult.to_dict()` as its cache payload without coupling the replay engine to detector-specific formats.

## Corpus fixture adapter

The corpus may provide a list of normalized observations and candidate windows. Pass them to `Orchestrator.build_match_timeline(source_id, observations, windows=..., detector_names=...)`. Evaluation code can compare `DetectorResult.observations` by stable observation type, time range, value, status, detector version, and evidence references. Corpus labels remain evaluation-owned; production code only emits predictions and diagnostics.

## Configuration and calibration

Conservative defaults and feature flags live under `detectors` and `evidence_timeline` in `coach/config/config.yaml`. Thresholds involving map movement or layout-specific pixels must remain disabled until calibrated on real recordings. The existing KDA, death-location, minimap, respawn-HUD, and audio configuration remains unchanged.

## Storage and metrics

Persist the compact JSONL timeline and selected evidence references, not every sampled frame. `EvidenceTimeline.metrics()` reports total, observed, unknown, unreadable, and detector counts. `DetectorResult.runtime_ms`, warnings, and errors provide stage-level instrumentation. Persistent storage and source-minute metrics should be added by the caller that owns media execution and cache storage.

## Adding a detector

Implement a class with `name`, `version`, `dependencies`, and `run(context) -> DetectorResult`. Construct outputs only with `Observation.create()`, attach every supporting observation ID in `evidence_refs` and `dependencies`, return explicit unknown/unreadable observations when appropriate, register the class in `PRODUCTION_DETECTORS`, add configuration defaults, and add positive, negative, unknown, unreadable, ambiguity, transition, provenance, and cache tests.

## Known limitations

The new workstreams operate on structured atomic evidence supplied by existing or future media-specific extractors. They do not replace the validated KDA/template, death-marker, minimap, or audio extractors, and they do not pretend that simulations are real-footage accuracy validation. Layout calibration, richer visual extraction, corpus fixture evaluation, and precision/recall measurement remain dependent on real labeled recordings.
