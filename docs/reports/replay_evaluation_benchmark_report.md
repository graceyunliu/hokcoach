# Replay Evaluation and Perception Benchmark Report

**Date:** 2026-08-26  
**Dataset:** `data/evaluation/replay_seeds/labeled_evaluation_set.json`  
**Benchmark JSON:** `data/evaluation/replay_seeds/perception_timestamp_benchmark.json`

## Executive result

The 100 replay-eligible seeds were submitted to the available remote multimodal analysis path after direct YouTube caption and audio downloads were blocked by YouTube bot protection. The remote path completed 99 analyses. One Bilibili source, `hokclass_108`, was rejected because its URL is not accepted by the remote analyzer; it remains explicitly marked unavailable.

The completed outputs yielded **920 timestamped silver event labels across 95 seeds**. Four remote analyses completed but did not contain parseable timestamp tables, and therefore were not silently converted into labels. Every parsed event had a valid start/end interval.

| Metric | Result | Status |
|---|---:|---|
| Requested eligible seeds | 100 | Complete |
| Remote analyses completed | 99 | Complete except one unsupported Bilibili URL |
| Seeds with parseable event labels | 95 | 95% coverage |
| Timestamped events | 920 | Silver annotations |
| Invalid timestamp intervals | 0 | Parser pass |
| Median annotated event duration | 19 seconds | Consistency proxy |
| True perception precision/recall | Not computable | Requires independent ground truth |
| True timestamp error | Not computable | Requires independently labeled event timestamps |

## Event distribution

| Category | Event labels |
|---|---:|
| Macro | 205 |
| Mechanics | 192 |
| Vision / 探草 | 163 |
| Wave and resource | 136 |
| Mentality / decision discipline | 75 |
| Teamfight | 68 |
| Items | 39 |
| Objective conversion | 33 |
| Composition | 5 |
| Other | 4 |

The label distribution is already useful for taxonomy and prompt/evaluation development: the remote reviews emphasize macro, mechanics, vision, and wave/resource decisions much more frequently than item-choice or fine-grained mechanics judgments. This is a **silver-label distribution**, not a claim about the true frequency of mistakes in the underlying games.

## Typed rank integration

The event records carry the typed rank profile from the seed manifest. The dimensions remain independent: `regular_rank`, `peak_score`, and `hero_power` are copied as structured objects, never collapsed into one numeric rank. Among the 95 parseable seeds, the event-bearing records include 4 regular-rank profiles, 14 peak-score profiles, and 4 hero-power profiles. The lower counts versus the full 161-record catalog are expected because only 100 eligible seeds were analyzed and four completed analyses produced no parseable table.

## What passed

The label-ingestion and timestamp-structure checks passed. The parser recovered 920 event rows, rejected no malformed start/end intervals, and preserved category, evidence, recommended action, confidence, source artifact, role, hero, series, and typed rank profile for each event. This confirms that the remote analysis output can be converted into a stable evaluation fixture format.

## What did not pass, and why

A genuine **perception benchmark** cannot be computed honestly from these outputs alone. The remote multimodal analysis is itself the source of the silver labels. Comparing a detector against those same annotations would be circular and would overstate performance. Similarly, a genuine **timestamp-error benchmark** needs an independently labeled event time for each event. The silver timestamp cannot serve as its own ground truth.

The direct extraction attempt recorded `access-failed` for captions and audio on all 100 YouTube-oriented seeds because the command-line extractor received YouTube’s “Sign in to confirm you’re not a bot” response. The browser player also exposed a bot-check page without caption-track metadata. The remote analyzer was therefore used as a fallback for timestamped multimodal annotations, not as a substitute for verbatim transcripts.

Four completed artifacts had no parseable timestamp table: `hokclass_054`, `hokclass_055`, `hokclass_067`, and `hokclass_075`. One source, `hokclass_108`, is a Bilibili URL and was rejected as an unsupported media URL by the remote analyzer. These records remain in the manifest with explicit status and are candidates for a later authenticated or local-file extraction pass.

## Correct interpretation of the benchmark

The current result should be treated as:

> **A 95-seed, 920-event silver evaluation fixture with a passing timestamp-structure ingestion check, but not yet a valid detector precision/recall or timestamp-error benchmark.**

To unlock the true benchmark, each seed needs either a locally available video/audio file or a reliable caption track, plus independent event labels. The recommended next step is to use local replay recordings or user-exported caption/audio files for a smaller double-annotated calibration subset, then use the 920 remote labels as silver training data and hard-negative discovery—not as final ground truth.
