# Codex prompt: AGE-189 中文/English双语切换

Paste everything below the line into Codex.

---

## Context

This is `coach/` in the "王者荣耀AI教练" repo — a King of Glory (MOBA) replay-analysis coaching tool. It has a FastAPI backend (`coach/api/`) driven by `Orchestrator` (`coach/core/orchestrator.py`), and a single static frontend file `coach_prototype.html` (no build step, no framework — plain HTML/CSS/vanilla JS, keep it that way).

Today everything is Chinese-only: the UI chrome in `coach_prototype.html`, and the AI-generated coaching content (death commentary, weekly reports) produced via prompt templates in `coach/prompts/*.txt` and persona config in `coach/config/persona.yaml`. We need to support both Chinese and English audiences with a language toggle.

**Design decision already made (do not relitigate):** AI-generated content must be generated *natively* in the target language, not translated after the fact. We researched this — direct generation in the target language outperforms "generate in English then translate" in the vast majority of languages tested (Google Research comparison), and translation measurably loses tone/cultural nuance (relevant here because the Chinese coach persona is deliberately modeled on a casual Douyin replay-review streamer voice — "好，兄弟，咱不废话" — which does not survive literal translation). So: the language must be picked **before** generation, by loading a different prompt file set, not by running a translation pass on Chinese output.

Work through Linear issues AGE-189 (epic) through AGE-194 in order. Each is scoped as an independent Linear ticket; implement them in this order since later ones depend on earlier ones existing:

1. **AGE-192** — English coach persona + `coach/prompts/en/*.txt` (do this first — AGE-191 has nothing to load without it)
2. **AGE-191** — backend: thread a `lang` parameter through `Orchestrator` so it picks the right prompt-file directory before generating
3. **AGE-193** — `player_profile.json` gets a persisted `language` field
4. **AGE-190** — frontend: language toggle + UI string dictionary for static chrome
5. **AGE-194** — do NOT implement this one. It's a known follow-up (English generation will still pull Chinese text from `knowledge_base/*.md` via `knowledge_engine.retrieve_principles()`). Just leave a `# TODO(AGE-194)` comment at the call site in `comment_death()` noting this, and stop there — it needs a human decision on translation quality first.

## Task 1 — AGE-192: English coach persona + prompts

Do not translate the existing Chinese prompts line-by-line. Design a comparable but independent English-language coach persona.

- Read `coach/config/persona.yaml` and all three files in `coach/prompts/` (`replay_analysis.txt`, `weekly_report.txt`, `death_classifier.txt`) to understand the current Chinese persona: casual, opinionated, second-person, structured around "what went wrong / what should you have thought / what to do next time / this week's training task."
- Create `coach/prompts/en/` with English versions: `replay_analysis.txt`, `weekly_report.txt`, `death_classifier.txt`. Same structural sections and same level of directness/bluntness as the Chinese version, but written as an English-speaking coach would actually talk — not a stiff translation. Keep all `{placeholder}` format-string variable names byte-identical to the Chinese templates (`Orchestrator` fills them positionally by name — check `orchestrator.py`'s `comment_death()` and `weekly_report()` for the exact `.format(...)` kwargs used, and match them exactly).
- Move the existing Chinese files into `coach/prompts/zh/` (same filenames), so the final layout is `coach/prompts/zh/*.txt` and `coach/prompts/en/*.txt`. Update any hardcoded `PROMPTS_DIR / "replay_analysis.txt"`-style paths in `orchestrator.py` accordingly (this will also be touched by task 2 below — fine to do both in the same pass).
- Death-type category names (`探草死`/`掉点死`/`换头死`/`贪线死`/`机制死`) need English equivalents that read naturally to an English-speaking MOBA player, not literal word-for-word translations. Look at `coach/core/replay_engine.py` (`DEATH_TYPES`, the classify_death rules) to see what each category actually means before naming it in English — pick names that communicate the same concept (e.g. "died to an unscouted ambush," "got caught overextended," "traded a kill 1-for-1," "died pushing/farming past safety," "unclear — insufficient evidence") rather than inventing new categories or renaming beyond recognition, since `death_analysis.categories` keys are used elsewhere in the codebase (check `replay_engine.py`, `training_engine.py`, and `coach_prototype.html` for every place these five Chinese strings appear as dict keys before deciding whether the *data model* keys change or only *display* labels change — recommend keeping the internal category keys as the existing Chinese strings for backward compatibility with saved replay JSON files, and only translating the *display* label in the English prompt output/UI, unless you have a clean migration path for existing `data/replays/*.json` files).
- `persona.yaml`: decide whether to add an `principles_en` list alongside the existing `principles`, or restructure into `principles: {zh: [...], en: [...]}`. Either is fine — pick whichever requires the smaller diff to `orchestrator.py`'s `_chat_system_prompt()` and `persona` loading code, and document the choice in a comment.
- Test with real saved replay data: run the new English prompt against at least one real `coach/data/replays/*.json` record's death detail (or a synthetic equivalent if none exists) through `Orchestrator.comment_death()` with a real or mocked LLM, and sanity check the tone/terminology reads naturally, not machine-translated.

## Task 2 — AGE-191: thread `lang` through the backend

- `Orchestrator.comment_death()`, `weekly_report()`, `_chat_system_prompt()`/`chat()`: add a `lang: str = "zh"` parameter (or read it from an instance attribute set at construction — pick whichever fits the existing call patterns better, but every entry point needs a way to specify language per-call, not just per-process). Use it to pick `PROMPTS_DIR / lang / "<file>.txt"` instead of the current hardcoded `PROMPTS_DIR / "<file>.txt"`.
- `build_replay_from_video_path()`, `finalize_review()`, `finalize_review_all()`, `analyze_manual()`, `weekly_report()`: add `lang: str = "zh"` and pass it through to wherever `comment_death()` gets called.
- FastAPI layer (`coach/api/routers/replay.py`, `coach/api/routers/training.py`, `coach/api/jobs.py`): accept an optional `lang` form field / query param on `POST /replay` and `POST /training/checkin` (and anywhere else that triggers generation), default `"zh"`, thread it through to the `Orchestrator` calls. For `POST /replay`, this means `Job` needs to carry the requested language through to `run_replay_job` → `build_replay_from_video_path(..., lang=...)` → `finalize_review_all(..., lang=...)`.
- Persist which language a saved replay/weekly-report was generated in — add a `"language": lang` field to the saved JSON (`replay["language"] = lang` before `data_utils.save_replay()`; same idea for weekly training snapshots) so historical records are self-describing.
- Validate `lang` is one of `"zh"`/`"en"` at the API boundary (422 on anything else — follow the existing pydantic validation pattern used for `CheckinRequest.rate` in `coach/api/routers/training.py`).
- Update/add tests in `coach/tests/test_engines.py` and `coach/tests/test_api.py` mirroring the existing patterns (see `TestOrchestratorStructuredReview` and `TestApiSmoke` — both already establish the mock/isolation conventions this codebase uses; follow them, including the `mock.patch.object(data_utils, ...)` isolation so tests never touch real user data files). Cover at minimum: default `lang="zh"` behavior is unchanged (regression), `lang="en"` loads the English prompt directory, an invalid `lang` value is rejected at the API layer, and the saved replay JSON records which language was used.

## Task 3 — AGE-193: persisted default language

- `coach/utils/data_utils.py`: add `"language": "zh"` to the `player` dict in `default_player_profile()`.
- Anywhere `load_player_profile()` result is read, make sure `.get("language", "zh")` (or equivalent) is used defensively — existing saved profiles won't have this key and must not crash.
- `GET /player/profile` (`coach/api/routers/progress.py` or wherever that route lives — check `coach/api/routers/`) should return the field as-is (no special handling needed if it's just part of the profile dict already).
- Decide whether to add a `PATCH /player/profile` (or extend an existing update endpoint) so the frontend can persist a language change back to the profile — if you add one, follow the existing FastAPI router conventions in this codebase (pydantic request model, mounted in `coach/api/main.py`). If you judge this out of scope for a first pass (frontend-only localStorage override is enough for now), leave a comment explaining that decision instead of silently skipping it.

## Task 4 — AGE-190: frontend toggle

- In `coach_prototype.html`, add a language toggle button in the header (near where `headerTag`/`profileWho` already render — search for those element IDs).
- Extract all static UI copy (tab labels, button text, section headings, empty-state messages, etc.) into a JS object: `const STRINGS = { zh: {...}, en: {...} }`. Do this incrementally file-wide — there is a lot of Chinese text in this file (5 tabs), don't skip tabs v1/v4 just because they're stubs; their static labels still need the same dictionary treatment for consistency even though their *data* is mocked.
- On toggle click: swap the active language, re-render all text bound to the dictionary (simplest approach: give translatable elements a `data-i18n="key"` attribute and a small `applyLanguage(lang)` function that walks `document.querySelectorAll('[data-i18n]')` and sets `textContent` from `STRINGS[lang][el.dataset.i18n]`; use `data-i18n-attr="placeholder"`-style variants for non-text-content cases like input placeholders if needed).
- Persist the chosen language in `localStorage` (e.g. key `coach_lang`), and read it on page load with this priority: `localStorage` value if present, else `/player/profile`'s `language` field (fetched via the existing `api()` helper — see how `profileWho` is populated for the pattern), else `"zh"`.
- When triggering AI generation (video upload `POST /replay`, training checkin `POST /training/checkin`), include the currently active language as a form field/query param matching whatever AGE-191 implemented server-side (check that task's actual param name/location before wiring this — do not guess a different contract).
- Do not touch AI-generated content rendering logic to do any client-side translation — the content itself already arrives in the correct language because of AGE-191/192; the frontend's only job re: AI content is *sending* the right `lang` param when it kicks off generation, not translating what comes back.

## General constraints for all tasks

- Follow this repo's existing conventions: extensive Chinese code comments explaining *why*, not just *what* (see any file in `coach/core/` or `coach/api/` for the style — keep writing comments in Chinese to match, English code/identifiers are fine). Every non-obvious design decision in this codebase has a comment justifying it; keep that habit.
- Run the full test suite before considering any task done: `cd coach && python3 -m pytest tests -q` (repo currently at 86/86 passing — should stay green, plus your new tests on top).
- Do not modify anything under `coach/data/` (real user data) as a side effect of tests — every existing test in `test_api.py`/`test_engines.py` mocks `data_utils`'s path constants via `mock.patch.object`; follow that pattern exactly for any new test, there was a real incident earlier where an unmocked test call wrote into a real user's data file.
- Git commits: this environment's `.git` directory is on a FUSE filesystem that sometimes leaves stale `index.lock`/`HEAD.lock` files and prints `warning: unable to unlink ...` on commit — these warnings are harmless (the commit still succeeds), don't try to "fix" them.
- Do not start AGE-194 (knowledge base translation) — leave the TODO comment as specified above and stop.
- When done, summarize what changed per-ticket (AGE-192/191/193/190) so it can be posted back to each Linear issue as a completion comment — don't post to Linear yourself, just produce the summary text.
