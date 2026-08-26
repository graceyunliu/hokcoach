# Replay-Review Seed Corpus Coverage Report

**Date:** 2026-08-26  
**Primary source:** [HonorofKings王者提升班](https://www.youtube.com/@HonorofKings%E7%8E%8B%E8%80%85%E6%8F%90%E5%8D%87%E7%8F%AD) and its [神奇宝贝TV replay playlist](https://www.youtube.com/playlist?list=PLK78_awGVR4MPZc-8Mr_P26NnLtKvzyfg)  
**Manifest:** `data/source_seeds/youtube/seed_manifest.json`

## Result

The corpus now contains **161 cataloged sources**. Of these, **100 are classified as eligible full-game or replay-review seeds**, while 61 are retained as context-only material such as tier lists, item guides, hero tutorials, and role-format videos. This is intentionally larger than the requested minimum so that later transcript and audio extraction can reject inaccessible, duplicate, short, or non-replay items without dropping below 100.

The seed set is anchored in a 175-video神奇宝贝TV playlist and expanded with channel role searches plus a small cross-platform search batch. The playlist is especially valuable because its titles and screenshots repeatedly expose ordinary-player rank/power situations rather than only professional gameplay. The user-provided screenshots show西施 at approximately 1400→1700,海月 around 1200/14000 power,安琪拉 near 2000 matches and roughly 8000 power,朵莉亚 low-rank/low-power framing,小乔 with 2600 matches and万战 discussion, and海诺 with a 40% win-rate framing. These are required similarity seeds for the product’s target user.

## Coverage summary

| Dimension | Count | Interpretation |
|---|---:|---|
| Total catalog records | 161 | All discovered source candidates with canonical URLs and provenance |
| Replay-eligible records | 100 | Full-game, POV, VOD, fan-review, replay, or explicit full-game-analysis cues |
| Context-only records | 61 | Retained for strategic knowledge but excluded from the initial replay-evaluation set |
| YouTube metadata-verified | 157 | Titles/authors resolved through public metadata enrichment |
| 神奇宝贝TV records | 23 | Required similarity subset from the channel’s fan-review series |
| Regular排位段位 evidence | 5 | Explicit regular ranked cues such as百星、荣耀王者, or tier language tied to排位/赛季; never inferred from generic“王者荣耀” text |
| 巅峰分数 evidence | 16 | Explicit巅峰/巅峰赛 numeric cues such as1200、1500、1800、2100; these are peak scores, not regular段位 or英雄战力 |
| 英雄战力 evidence | 5 | Explicit战力/省标/国标/combat-power cues such as7000战力、1.3w战力; these are hero-specific and independent of巅峰分数 |
| Regular/peak/power unresolved | Remaining records | No typed rank claim is made until transcript, thumbnail, or game-screen evidence resolves the dimension |

The typed-rank counts are intentionally independent and may overlap. There are 161 total records and 100 replay-eligible records. A numeric value is never copied between段位、巅峰分数 and英雄战力: for example, `2000巅峰分` is stored only as `peak_score=2000`, while `2000英雄战力` is stored only as `hero_power=2000` with an associated hero. All labels remain title-cued until transcript, thumbnail, or in-game-screen verification.

| Role | Cataloged records | Coverage assessment |
|---|---:|---|
| 法师 | 75 | Strong coverage, including小乔、西施、海月、安琪拉、貂蝉、女娲、奕星、扁鹊、海诺等 |
| 辅助 | 23 | Now substantive, including张飞、少司缘、朵莉亚、大乔、孙膑、元辅、辅助赵怀真等 |
| 射手 | 33 | Now substantive, including后羿、虞姬、狄仁杰、鲁班、艾琳、孙尚香、伽罗、元射等 |
| 打野 | 10 | Includes澜、孙悟空、韩信、玄策、云缨、宫本、裴擒虎、李白等 |
| 对抗 | 8 | Includes花木兰、狂铁、项羽、吕布、司空震、马超等 |
| Role unresolved | 12 | Retained but excluded from role-balance claims until metadata or visual verification |

## Typed rank extraction policy

The downstream extraction job must preserve three independent dimensions rather than simply taking the first 100 URLs. A single record may have more than one dimension, for example regular排位百星 plus巅峰1200 plus西施7000战力.

| Required dimension | Minimum retained seeds | Interpretation |
|---|---:|---|
| Regular排位段位 | 15 | Regular ranked ladder evidence, such as铂金、钻石、星耀、王者、百星; do not treat a peak-score number as段位 |
| 巅峰分数 | 35 | Peak-tournament score evidence, such as巅峰1200、巅峰1500、巅峰2100; do not treat hero power as peak score |
| 英雄战力 | 20 | Hero-specific evidence, such as7000战力、1.3w战力、万战; store the associated hero |
| 神奇宝贝TV similarity subset | 20 | Prefer low-to-mid-rank fan reviews across at least 8 heroes and preserve all three typed fields when present |
| Role diversity reserve | 15 | Additional对抗、打野、射手、辅助 records, used when a role falls below quota after download validation |

The current catalog meets the神奇宝贝TV target with 23 records and exceeds the high-end target with 51 title-cued records. It has 11 explicit low-rank records, so the extraction selector should promote at least four additional low-rank or low-elo records from the four currently unresolved rank cases or from the 61 context-only records if later inspection confirms full-game footage.

## Provenance and evidence-quality rules

Every record includes a canonical URL, video ID, source channel, source kind, metadata status, transcript status, download status, rank evidence, series membership, content type, and seed eligibility. A source is not treated as a verified spoken coaching example until its audio or transcript has been extracted. Titles, thumbnails, and search snippets are used only for candidate discovery and stratification.

The extraction pipeline should not redistribute downloaded video or audio. It should retain only the minimum local working copy needed for analysis and store timestamped transcript snippets, event annotations, and provenance links in the evaluation corpus. If a platform blocks download or captions, the record remains in the manifest with an explicit failure status rather than being silently removed.

## Next automated step

Run the downloader/transcript worker against `seed_manifest.json` in batches. Prefer captions first, then audio extraction and speech-to-text for sources without captions. Limit initial deep analysis to the 100 `eligible-seed` records selected by the rank/role policy above. The 61 context-only records remain useful for knowledge-base enrichment and can be promoted only when the worker discovers full-game replay evidence.
