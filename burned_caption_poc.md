# Burned-in Caption Proof of Concept

## Source

The proof of concept used the supplied replay-review video: https://www.youtube.com/watch?v=TcPNUG4b6GE

The video is an 8:01 Honor of Kings Xishi fan replay review from HonorofKings王者提升班. The YouTube player did not expose a caption track, but the review’s Chinese commentary appears as burned-in text inside the video frames.

## Result

A focused multimodal frame/audio analysis successfully read the visible burned-in commentary at the beginning of the video and aligned it with gameplay states. The extracted examples include:

| Time | Burned-in text | Visible context |
|---|---|---|
| 00:00–00:08 | 老娘求复盘，玩西施场均死10次怎么解决这个死亡率过高的原因呀，每次玩西施的时候游戏思路都很混乱嗷吗 | Intro screen and user question about excessive deaths and confused game planning |
| 00:09 | 场均死10次吗 | MVP/defeat screen showing Xishi with a 3/13/10 KDA |
| 00:10–00:11 | 那很贪睡了 | Same defeat screen; commentary frames the death count as repeated overextension or “sleeping” deaths |
| 00:12 | 我们第一视角进入复盘 | Transition into the in-game first-person replay at mid lane |

The analysis confirmed the core hypothesis: **a review video can supply both a timestamped gameplay frame and the reviewer’s exact on-screen wording even when YouTube captions are unavailable**.

## Important limitation

This proof of concept did not create a deterministic one-frame-per-second image archive. The remote video-analysis service sampled the video internally and returned a concise table; it is not guaranteed to emit every second, every caption transition, or the exact OCR text for the full duration. Its output is therefore a feasibility result and seed annotation, not a complete benchmark dataset.

## Deterministic production path

For production-quality extraction, the system should first obtain the media bytes through the local browser-mediated capture path, then run:

```text
video/audio source
  → ffmpeg: one frame per second
  → caption-region crop and preprocessing
  → Chinese OCR with confidence
  → caption deduplication and interval reconstruction
  → gameplay/HUD/minimap frame record
  → optional audio STT alignment
```

Each output record should contain `video_id`, `frame_timestamp`, `frame_path`, `ocr_text`, `ocr_confidence`, `caption_interval`, `gameplay_observations`, `typed_rank_profile`, and `evidence_source`. Consecutive frames with the same OCR text should be merged into one caption interval, while uncertain OCR should remain `[unreadable]` rather than being silently corrected.

## Conclusion

The strategy is viable and likely more valuable than relying on YouTube’s caption API for this channel. The next engineering step is to run the deterministic ffmpeg/OCR stage over a locally captured smoke-test WebM, then compare OCR text and caption-transition timestamps against the multimodal seed annotations. Only after that comparison passes should the process be scaled to all 100 videos.
