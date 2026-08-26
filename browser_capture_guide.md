# Browser-Mediated Replay Audio Capture

## Purpose

`tools/browser_capture_replays.js` is a local-user capture worker for the 100 replay-eligible seed videos. It opens each source in a normal Chrome context, reuses an already authenticated session when connected through Chrome DevTools Protocol, captures the audio track from the page’s HTML video element with `captureStream()`, and writes resumable per-seed artifacts. It does not request, export, or store the user’s password or cookies.

## Why this must run on the user computer

YouTube may block cloud-provider IP addresses even when the same source is playable in a normal residential browser. Running this worker locally makes the media request originate from the user’s browser/network. The browser must be logged in only if a source requires login; public videos should otherwise work in a normal session.

## Prerequisites

Install Node.js and Playwright in the local project. On macOS:

```bash
npm install --save-dev playwright
npx playwright install chromium
```

The recorder requires a Chromium/Chrome build that supports `HTMLMediaElement.captureStream()` and `MediaRecorder` for an Opus WebM audio stream. It should be run with headphones or normal playback settings; it captures the page media element, not the microphone and not arbitrary system audio.

## Recommended authenticated mode

Launch a separate Chrome instance with remote debugging enabled. Close the existing debug instance first, or use a separate profile directory. The first launch is interactive so the user can sign in normally if needed:

```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --remote-debugging-port=9222 \
  --user-data-dir="$HOME/Library/Application Support/HokCoachChrome"
```

Then run a one-video smoke test:

```bash
node tools/browser_capture_replays.js \
  --manifest data/source_seeds/youtube/seed_manifest.json \
  --out data/evaluation/replay_seeds/browser_capture \
  --connect-cdp http://127.0.0.1:9222 \
  --limit 1 \
  --max-videos 1
```

The worker writes `browser_capture_manifest.json`, an audio `.webm` file, and—only when captions are visibly rendered by the player—a `.jsonl` caption file with approximate display timestamps.

## Batch mode

After the smoke test succeeds, run the full batch in resumable chunks:

```bash
node tools/browser_capture_replays.js \
  --manifest data/source_seeds/youtube/seed_manifest.json \
  --out data/evaluation/replay_seeds/browser_capture \
  --connect-cdp http://127.0.0.1:9222 \
  --limit 100 \
  --max-videos 10
```

Repeat the same command until all seeds are processed. Existing `captured` and `skipped` records are not rerun. Use `--retry` for a deliberate retry of prior records. The default behavior plays each video to its end because audio capture must be synchronized with the media timeline. `--dwell-seconds N` can be used for a bounded smoke test, but it must not be used to create final transcripts.

## Audio-to-transcript step

The recorder intentionally produces audio files rather than assuming YouTube captions exist. A separate speech-to-text worker should consume each `.webm` file, emit segments with `start`, `end`, `text`, and `language`, and write them beside the audio artifact. The existing sandbox command `manus-speech-to-text` is not assumed to be present on the user’s Mac; use an approved local speech-to-text runtime or upload the captured audio artifacts to the sandbox for transcription. Do not compare an audio transcript’s timestamps with a browser-caption timestamp without recording the source and timestamp method.

## Output schema

Every result includes `seed_id`, `video_id`, URL, role, hero, typed `rank_profile`, series, capture status, transcript mode, file paths, duration, captions, and errors. The typed rank profile keeps `regular_rank`, `peak_score`, and `hero_power` independent.

Possible states are:

| State | Meaning |
|---|---|
| `captured` | Audio was captured successfully; transcript may still be pending |
| `failed` | Browser could not load the video or capture the media element |
| `audio-pending-stt` | Audio exists but no visible YouTube captions were captured |
| `caption-display-capture` | Visible caption segments were sampled from the player |

## Important limitations

This is a media-element capture path, not a bypass of YouTube access controls. It will fail when the browser itself cannot play the video, when the player uses a non-capturable stream, or when a source requires an interaction the worker cannot perform. A visible description claiming “English subtitles available” is not treated as proof of an actual caption track; only rendered caption segments or a separate transcript extractor count.

For final evaluation labels, speech-to-text output remains a source transcript and should not be treated as independent gameplay ground truth. Use it to align what the reviewer said with the gameplay timestamp, then keep perception ground truth separately labeled or independently verified.
