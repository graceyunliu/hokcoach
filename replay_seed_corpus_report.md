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
| High-end/职业 cues | 51 | 1900+, 2000+, 2100+, 2200+, 2300+, 巅峰, 国服, KPL, pro, top-ranked, or MMR cues |
| Mid-to-high rank cues | 95 | 王者/1500–1800 and equivalent high-rank cues |
| 新手/low-rank cues | 11 | 新手, 青铜–铂金, 1000–1400, low-elo, or similar cues |
| Rank unresolved | 4 | Must remain unclaimed until transcript/thumbnail/game-screen verification |

The rank counts overlap because the corpus is deliberately cataloged rather than forced into a single balanced 100-record subset at this stage. There are 161 total records and 100 replay-eligible records; the rank labels are title-derived evidence labels, not claims that every source’s exact in-game rank has been independently verified.

| Role | Cataloged records | Coverage assessment |
|---|---:|---|
| 法师 | 75 | Strong coverage, including小乔、西施、海月、安琪拉、貂蝉、女娲、奕星、扁鹊、海诺等 |
| 辅助 | 23 | Now substantive, including张飞、少司缘、朵莉亚、大乔、孙膑、元辅、辅助赵怀真等 |
| 射手 | 33 | Now substantive, including后羿、虞姬、狄仁杰、鲁班、艾琳、孙尚香、伽罗、元射等 |
| 打野 | 10 | Includes澜、孙悟空、韩信、玄策、云缨、宫本、裴擒虎、李白等 |
| 对抗 | 8 | Includes花木兰、狂铁、项羽、吕布、司空震、马超等 |
| Role unresolved | 12 | Retained but excluded from role-balance claims until metadata or visual verification |

## Rank-stratified extraction policy

The downstream extraction job should preserve the following minimum strata rather than simply taking the first 100 URLs:

| Required stratum | Minimum retained seeds | Preferred source types |
|---|---:|---|
| 新手/低段位 | 15 | 神奇宝贝TV, low-elo, 铂金/钻石, 1000–1400, low-power fan reviews |
| 中段位/高段位 | 35 | 1500–1800, 王者, ordinary peak-rank fan reviews |
| 高端巅峰/职业 | 35 | 1900–2300, 国服, 全国前百, KPL, professional or top-ranked POV reviews |
| 神奇宝贝TV similarity subset | 20 | Prefer low-to-mid-rank fan reviews across at least 8 heroes |
| Role diversity reserve | 15 | Additional对抗、打野、射手、辅助 records, used when a role falls below quota after download validation |

The current catalog meets the神奇宝贝TV target with 23 records and exceeds the high-end target with 51 title-cued records. It has 11 explicit low-rank records, so the extraction selector should promote at least four additional low-rank or low-elo records from the four currently unresolved rank cases or from the 61 context-only records if later inspection confirms full-game footage.

## Provenance and evidence-quality rules

Every record includes a canonical URL, video ID, source channel, source kind, metadata status, transcript status, download status, rank evidence, series membership, content type, and seed eligibility. A source is not treated as a verified spoken coaching example until its audio or transcript has been extracted. Titles, thumbnails, and search snippets are used only for candidate discovery and stratification.

The extraction pipeline should not redistribute downloaded video or audio. It should retain only the minimum local working copy needed for analysis and store timestamped transcript snippets, event annotations, and provenance links in the evaluation corpus. If a platform blocks download or captions, the record remains in the manifest with an explicit failure status rather than being silently removed.

## Next automated step

Run the downloader/transcript worker against `seed_manifest.json` in batches. Prefer captions first, then audio extraction and speech-to-text for sources without captions. Limit initial deep analysis to the 100 `eligible-seed` records selected by the rank/role policy above. The 61 context-only records remain useful for knowledge-base enrichment and can be promoted only when the worker discovers full-game replay evidence.
