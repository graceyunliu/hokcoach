#!/usr/bin/env node
/**
 * Browser-mediated replay capture for YouTube/Honor of Kings seed videos.
 *
 * This is intentionally a local-user workflow. It can connect to an already
 * logged-in Chrome started with --remote-debugging-port, or launch a persistent
 * Playwright Chrome profile. It never handles passwords or exports cookies.
 *
 * Usage:
 *   node tools/browser_capture_replays.js \
 *     --manifest data/source_seeds/youtube/seed_manifest.json \
 *     --out data/evaluation/replay_seeds/browser_capture \
 *     --connect-cdp http://127.0.0.1:9222
 *
 * The browser page captures the YouTube <video> element with captureStream()
 * and downloads a WebM audio/video recording. If the page exposes captions,
 * they are collected from the caption display while playback runs. Otherwise
 * the artifact is marked audio-only and can be transcribed by the companion
 * speech-to-text step.
 */

const fs = require('fs');
const path = require('path');
const process = require('process');
const { execFileSync } = require('child_process');
const { chromium } = require('playwright');

function arg(name, fallback = null) {
  const i = process.argv.indexOf(name);
  return i >= 0 && process.argv[i + 1] ? process.argv[i + 1] : fallback;
}
function has(name) { return process.argv.includes(name); }
function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }
function safe(s) { return String(s || '').replace(/[^a-zA-Z0-9._-]+/g, '_').slice(0, 150); }
function writeJson(file, value) { fs.writeFileSync(file, JSON.stringify(value, null, 2) + '\n'); }

const manifestPath = path.resolve(arg('--manifest', 'data/source_seeds/youtube/seed_manifest.json'));
const outDir = path.resolve(arg('--out', 'data/evaluation/replay_seeds/browser_capture'));
const cdp = arg('--connect-cdp');
const profile = arg('--profile-dir', path.join(outDir, 'chrome-profile'));
const limit = Number(arg('--limit', '100'));
const maxVideos = Number(arg('--max-videos', '1'));
const startAt = Number(arg('--start-at', '0'));
const dwell = Number(arg('--dwell-seconds', '0'));

fs.mkdirSync(outDir, { recursive: true });
const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
const seeds = (manifest.records || manifest).filter(r => r.seed_eligibility === 'eligible-seed').slice(startAt, startAt + limit);
const statePath = path.join(outDir, 'browser_capture_manifest.json');
let state = fs.existsSync(statePath) ? JSON.parse(fs.readFileSync(statePath, 'utf8')) : { schema_version: 'browser-capture-v1', results: {} };

async function attachBrowser() {
  if (cdp) return { browser: await chromium.connectOverCDP(cdp), owned: false };
  const context = await chromium.launchPersistentContext(path.resolve(profile), {
    channel: 'chrome', headless: false, viewport: { width: 1440, height: 900 },
    args: ['--autoplay-policy=no-user-gesture-required']
  });
  return { browser: context, context, owned: true };
}

async function captureSeed(page, seed) {
  const base = `${safe(seed.seed_id)}_${safe(seed.video_id)}`;
  const result = {
    seed_id: seed.seed_id, video_id: seed.video_id, url: seed.url,
    title: seed.title || '', role: seed.role || null, hero: seed.hero || null,
    rank_profile: seed.rank_profile || null, series: seed.series || null,
    status: 'running', capture_file: null, transcript_file: null,
    transcript_mode: null, duration_sec: null, captions: [], errors: []
  };
  const capture = path.join(outDir, `${base}.webm`);
  const transcript = path.join(outDir, `${base}.jsonl`);
  try {
    await page.goto(seed.url, { waitUntil: 'domcontentloaded', timeout: 90000 });
    await page.waitForTimeout(5000);
    const setup = await page.evaluate(() => {
      const video = document.querySelector('video');
      if (!video) return { ok: false, reason: 'video-element-not-found' };
      if (!video.captureStream) return { ok: false, reason: 'captureStream-not-supported' };
      return { ok: true, duration: video.duration || null, paused: video.paused, readyState: video.readyState };
    });
    if (!setup.ok) throw new Error(setup.reason);
    result.duration_sec = setup.duration;
    const start = await page.evaluate(() => {
      const video = document.querySelector('video');
      const stream = video.captureStream();
      const audioOnly = new MediaStream(stream.getAudioTracks());
      const recorder = new MediaRecorder(audioOnly, { mimeType: 'audio/webm;codecs=opus' });
      const chunks = [];
      recorder.ondataavailable = e => { if (e.data && e.data.size) chunks.push(e.data); };
      recorder.start(1000);
      window.__hokCapture = { recorder, chunks, startedAt: performance.now(), duration: video.duration || 0 };
      video.currentTime = 0;
      video.play().catch(() => {});
      return { duration: video.duration || 0 };
    });
    const target = Math.max(1, Math.ceil(start.duration || 0));
    const deadline = Date.now() + ((dwell > 0 ? dwell : target) + 20) * 1000;
    while (Date.now() < deadline) {
      const snap = await page.evaluate(() => {
        const v = document.querySelector('video');
        const captions = Array.from(document.querySelectorAll('.ytp-caption-segment')).map(x => x.textContent.trim()).filter(Boolean);
        return { time: v ? v.currentTime : null, ended: !!v?.ended, captions };
      });
      if (snap.captions.length) {
        const t = Number(snap.time || 0);
        for (const text of snap.captions) result.captions.push({ start: t, end: t + 1, text });
      }
      if (snap.ended) break;
      await sleep(1000);
    }
    const payload = await page.evaluate(async () => {
      const c = window.__hokCapture;
      if (!c) throw new Error('capture-state-missing');
      await new Promise(resolve => { c.recorder.onstop = resolve; c.recorder.stop(); });
      const blob = new Blob(c.chunks, { type: 'audio/webm;codecs=opus' });
      const buffer = await blob.arrayBuffer();
      return Array.from(new Uint8Array(buffer));
    });
    fs.writeFileSync(capture, Buffer.from(payload));
    result.capture_file = path.relative(process.cwd(), capture);
    result.transcript_mode = result.captions.length ? 'caption-display-capture' : 'audio-pending-stt';
    if (result.captions.length) {
      const dedup = []; const seen = new Set();
      for (const row of result.captions) { const k = `${row.start.toFixed(1)}|${row.text}`; if (!seen.has(k)) { seen.add(k); dedup.push(row); } }
      result.captions = dedup;
      fs.writeFileSync(transcript, result.captions.map(x => JSON.stringify(x)).join('\n') + '\n');
      result.transcript_file = path.relative(process.cwd(), transcript);
    }
    result.status = 'captured';
  } catch (e) {
    result.status = 'failed'; result.errors.push(String(e && e.stack || e));
  }
  return result;
}

(async () => {
  const attached = await attachBrowser();
  const context = attached.context || attached.browser.contexts()[0];
  const page = await context.newPage();
  let processed = 0;
  for (const seed of seeds) {
    if (processed >= maxVideos) break;
    const prior = state.results[seed.seed_id];
    if (prior && ['captured', 'skipped'].includes(prior.status) && !has('--retry')) continue;
    const r = await captureSeed(page, seed);
    state.results[seed.seed_id] = r;
    state.updated_at = new Date().toISOString();
    writeJson(statePath, state);
    console.log(`[${processed + 1}/${Math.min(maxVideos, seeds.length)}] ${seed.seed_id}: ${r.status} ${r.transcript_mode || ''}`);
    processed++;
  }
  await page.close();
  if (attached.owned) await attached.browser.close();
  console.log(`Wrote ${statePath}`);
})().catch(e => { console.error(e.stack || e); process.exit(1); });
EOF
chmod +x /home/ubuntu/hokcoach/tools/browser_capture_replays.js
