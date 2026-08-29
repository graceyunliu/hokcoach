# Windowed Burned-In Caption Extraction Report

## Source and method

Source video: https://www.youtube.com/watch?v=TcPNUG4b6GE

The 8:01 replay-review video was analyzed in four two-minute windows plus a short tail retry: `00:00–02:00`, `02:00–04:00`, `04:00–06:00`, `06:00–08:01`, and an additional `07:20–08:01` pass because the long final window was truncated at the output boundary. Each pass requested burned-in Chinese caption text, timestamp, confidence, and concurrent gameplay/HUD/minimap state.

## Measured output

| Metric | Result |
|---|---:|
| Video duration | 481 seconds |
| Window analyses completed | 5 |
| Raw caption rows | 242 |
| Deduplicated rows | 242 |
| Readable-text rows | 242 |
| Unreadable rows | 0 |
| Coverage start | 00:00 |
| Coverage end | 08:01 |
| Timestamps with conflicting text | 1 |

The extraction reached the video endpoint and produced 242 timestamped caption/state records. Confidence was reported as `100%` for 109 rows, `High` for 86 rows, and numeric confidence from `0.95` to `0.99` for 47 rows.

## Overlap conflict

The only overlapping timestamp conflict occurs at 07:20 because the short tail retry repeats the same caption as the end of the 06:00–08:01 pass with different OCR-like spellings:

- `这个风暴龙王被对面云缨隔着墙一个燎原白斩给抢了`
- `这个风暴龙王被对面云鹰隔着墙一个燎原百斩给抢了`

Both describe the same observable event: Yunying steals the Storm Dragon King from behind the wall. This should be normalized as an alias/confidence disagreement rather than treated as two independent coaching events.

## Interpretation

This confirms that windowed multimodal extraction can cover the full video and produce a useful caption/event seed set without YouTube captions. It is especially valuable for discovering the reviewer’s language around线权、支援、死亡归因、技能命中、装备保命、推塔、龙王争夺、救人决策 and水晶防守.

The output is still not equivalent to deterministic OCR ground truth. The analyzer internally samples frames and may paraphrase or normalize visually similar Chinese characters. The 242 rows should therefore be treated as high-value silver labels. A deterministic OCR benchmark still requires the local WebM or another reproducible frame source.

## Artifacts

- `data/evaluation/replay_seeds/windowed_caption_analysis/00_02_raw.txt`
- `data/evaluation/replay_seeds/windowed_caption_analysis/02_04_raw.txt`
- `data/evaluation/replay_seeds/windowed_caption_analysis/04_06_raw.txt`
- `data/evaluation/replay_seeds/windowed_caption_analysis/06_08_raw.txt`
- `data/evaluation/replay_seeds/windowed_caption_analysis/07_20_08_01_raw.txt`
- `data/evaluation/replay_seeds/windowed_caption_analysis/merged_burned_captions.json`
- `data/evaluation/replay_seeds/windowed_caption_analysis/merged_burned_captions.jsonl`

The merge is reproducible with `python3 tools/merge_windowed_captions.py`; validation is reproducible with `python3 tools/validate_windowed_captions.py`.
