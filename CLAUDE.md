# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

Framefluence turns TV and film footage into Instagram Reels for the `@framefluence` cinema page. All code lives in the `framefluence/` package, and there is one entry point: `python -m framefluence <command>` (`framefluence/__main__.py` dispatches to each module's `main()` after `chdir`-ing to the repo root).
- **`autopilot.py`** is the daily pipeline. It turns clips dropped in `inbox/` into Reel drafts in `review/` (transcribe → pick story beat → cut → face-track → word-by-word subtitles → render → caption), plus a trend briefing. Humans approve drafts in the Studio or with `review.py` and post manually.
- **`make_reel.py`** renders footage into 1080x1920 Reels by building a single FFmpeg `filter_complex` command.
- **`trend_agent.py`** suggests daily Reel ideas and builds post packages: hook, caption, hashtags, and a `python -m framefluence reel` command.
- **`studio.py` + `ui/index.html`** form Framefluence Studio, the local web UI (`python -m framefluence studio`, then open http://127.0.0.1:8765). You upload to `inbox/`, run the autopilot, review drafts on a film strip, edit the hook, hashtags and caption style (which triggers `--restyle`), and approve or reject.

`docs/superpowers/specs/` holds the original design spec. yt-dlp ingestion was never built; footage comes only from the user via `inbox/`. Trust the code over the spec.

## Layout and paths

- **`framefluence/paths.py` is the single source of folder locations** (`ROOT`, `DATA`, `FONTS`, `MODELS`, `UI`, `INBOX`, `REVIEW`, `LOGS`, the CSV paths, and so on). Never derive paths from a module's `__file__`; the package sits one level below the root.
- **Imports are absolute package imports** (`from framefluence.scene_cut import ...`), including the lazy ones inside functions. Tests insert the repo root into `sys.path` and import the same way.
- **Folders:** `data/` holds the two CSVs, `assets/fonts/` holds Montserrat (OFL), `assets/footage/` holds the user's videos (git-ignored), `models/` holds the YuNet ONNX, `scripts/` holds the Windows scheduler, and `tests/` and `docs/`.
- **Git-ignored** (see `.gitignore`): `.env`, `.venv/`, all runtime folders, every video file (`*.mp4`, `*.mkv`, ...), `assets/fonts/arial.ttf` (Microsoft-licensed; `make_reel` falls back without it), and `.agents/`. Never commit footage or renders; they're copyrighted. `.env.example` documents the variables.

## Environment

- **Two tiers.** The core tools (`make_reel`, `trend_agent`, `subtitle_engine`) use only the standard library, and the whole test suite runs on plain `python`. The autopilot's smart steps need `.venv` (`requirements.txt`: faster-whisper, scenedetect, opencv). Heavy imports are **lazy, inside functions**, and every smart step catches its own failure and falls back. Keep it that way, so a missing package degrades a step instead of crashing the run.
- Run the pipeline with `.venv/Scripts/python -m framefluence ...`. `ffmpeg`/`ffprobe` must be on PATH. The Studio's `JobRunner` launches `-m framefluence.autopilot` with the `.venv` interpreter when it exists.
- **pip on this machine needs the Windows certificate store** (HTTPS is intercepted). `truststore` is installed in `.venv`, and pip ≥24 uses it automatically.
- **Run from the project root.** Font paths (`assets/fonts/...`) and the subtitle `fontsdir` are relative to the working directory. `__main__`, `autopilot` and `studio` all `chdir` to `ROOT`.
- **Face detection uses OpenCV YuNet** via `models/face_detection_yunet_2023mar.onnx` (from opencv_zoo, 232 KB; keep it). mediapipe 1.x removed `mp.solutions`, and OpenCV 5 wheels no longer ship the Haar XMLs, so without the ONNX file face tracking fails and falls back to a centre crop.

## Commands

```bash
python -m unittest discover tests                      # all tests, plain python (~5s); end-to-end test runs ffmpeg
python -m unittest tests.test_autopilot.TestStoryPicker # one class / append .test_name for one test

python -m framefluence studio                          # Studio web UI at http://127.0.0.1:8765
.venv/Scripts/python -m framefluence autopilot         # briefing + process everything in inbox/
.venv/Scripts/python -m framefluence autopilot --no-briefing --drafts 3 --max-len 90 --whisper-model base
.venv/Scripts/python -m framefluence autopilot --restyle review/<draft> [--style bold|clean]
python -m framefluence review                          # list drafts; then: open|approve|reject <name>
python -m framefluence reel --mode quote -i clip.mp4 -o output/reel.mp4 --subtitles subs.ass
python -m framefluence reel --mode quote -i clip.mp4 --framing track   # face-tracked crop (needs .venv)
python -m framefluence trends --briefing-only          # without the flag it waits for input()
python -m framefluence calendar                        # regenerate data/top_50_actors_calendar.csv
powershell -ExecutionPolicy Bypass -File scripts/schedule_autopilot.ps1 -Time 09:00   # daily Task Scheduler job
```

## Architecture

### Autopilot: `framefluence/autopilot.py` and its step modules
- **Inbox contract:** `inbox/<clip>.mp4|mkv|...` plus an optional `<clip>.json` sidecar with `title`, `header`, `hook`, `quote`, `context`, `question`, `mode`, and `start`/`end` (manual segment, skips picking). After success, the source and sidecar move to `inbox/processed/`. Failures stay in the inbox and are logged to `logs/autopilot.log`.
- **Draft layout:** `review/<date>_<slug>/` holds `reel.mp4`, `caption.txt`, `meta.json` (status, segment, framing, `track_x`, `caption_style`, plus the sidecar fields), `words.json` (the final aligned words), and intermediates (`source_cut.mp4`, `subtitles.ass`). `review.py` moves folders to `approved/` or `rejected/` and updates `meta.json` status.
- **`render_draft` vs `finish_draft`:** `render_draft` does the analysis (cut, track, transcribe). `finish_draft` does styling, render and the post package, and it's all that `--restyle` re-runs, from `words.json` and `meta.json`. To change a draft's hook or hashtags, edit its `meta.json` and restyle.
- **No hook box or show title on the video by default** (the user found they cover the picture). `finish_draft` passes the hook and header to the render only when the draft's `meta.json` has `show_hook` / `show_header` set to true (the Studio editor checkbox sets both). The hook always leads the post caption, and `header` is still used to group strips in the Studio. Only captions and the `@framefluence` watermark (centred at y=100 when there's no header) appear on the video.
- **Post caption:** the quote is the sidecar `quote`, else `payoff_line()` (the beat's last sentence, so each automatic beat gets its own punchline). Sidecar `hashtags` are put before the base tags. Automatic beats get no per-scene hook; a person writes it in `meta.json`.
- **Flow:** `process_clip` calls `analyse_source` (shots plus a cheap *picking* transcript), then `pick_segments`, then `render_draft` once per segment.
  - **Picking transcript:** the embedded subtitle track (`embedded_subtitle_words`, instant, approximate per-word times) if the file has one, else Whisper `tiny`.
  - **Segments and drafts:** a long source such as an episode becomes the top `--drafts` (default 3) non-overlapping story beats, as `review/<date>_<slug>_beat<k>/`. A sidecar `start`/`end` gives exactly one draft.
  - **Per draft:** cut to `source_cut.mp4` (timestamps restart at 0; shots shifted by `relative_scenes`), then Whisper `--whisper-model` on **the cut only**.
    - **Embedded subtitles present:** `align_reference()` keeps the subtitle track's exact wording and borrows Whisper's word timings (difflib match; unmatched words are interpolated between neighbours). Whisper alone mishears names ("Rach" → "reach"), and its VAD drops soft emotional lines.
    - **No embedded track:** Whisper's words are used as-is.
  - **Sidecar `start`/`end`:** full-source shot detection is skipped, and shots are detected on the cut instead.
- **`scene_cut.py`:**
  - `rank_story_segments()` scores windows between `speech_breaks()` (pauses landing on a shot cut, plus the first cut after the final line).
    - Score: laughter (loudness while nobody speaks), dialogue density, and payoff (a big reaction in the last 6s).
    - Loud wordless runs longer than 6s are treated as music, not laughter.
    - Windows with any wordless stretch over 8s, **including at the edges**, are rejected as theme songs or transitions.
  - `choose_story_segment()` is the top-1 wrapper, and `choose_segment()` is the no-transcript fallback (the longest run of whole shots). These are pure; `detect_scenes`/`audio_energy`/`cut_clip` do the I/O.
- **Known picker limits** (found on Friends S08E01):
  - The heuristic favours comedy over emotional beats, so the human review step and sidecar `start`/`end` "editor's cuts" exist for that.
  - It can't see scene changes that have no long pause. Colour-histogram scene grouping was tried and failed, because single-location episodes look the same throughout.
- **`reframe.py`:** one constant crop per shot (the median of the largest face's centre), hard-cutting between shots. The output is an FFmpeg `if(lt(t,..),x,...)` expression for the source scaled to 1920px high, passed to `make_reel` as `track_x`.
- **`auto_subtitles.py`:** faster-whisper word timestamps, then phrases of ≤3 words broken on pauses and sentence ends, then one `.ass` event per word.
  - **The caption-look registries live here:** `FONTS` (id, label, internal `family` libass matches, `file` in `assets/fonts`, size `scale`), `COLORS` (`hex` for the UI, `ass` &HAABBGGRR), `STYLES` (`bold`, `karaoke`, `boxed`, `clean`, `minimal`; `highlight` is `"word"`, `"fill"` or `None`, and `box` means `BorderStyle 3`), `SIZES` and `DEFAULT_LOOK`. Adding a font or style is a registry entry; the Studio picks it up via `/api/options`.
  - `write_subtitles(..., look=...)` builds its own multi-style `.ass` file (it doesn't use `subtitle_engine`). `caption_style_line()` turns a look into the `Caption` style: size = style size × font scale × size factor, and `margin_v = (1 - caption_position) × 1920`. The `Hook` style is black on a white box, wrapped by `wrap_hook()`.
  - Font `family` must be the font's internal name-table family (for example `"Montserrat Black"`, `"Bebas Neue"`), or libass silently falls back. Check libass's `fontselect:` lines with `-loglevel verbose`.
  - The highlight is tagged **by position**; `subtitle_engine`'s `highlight_word` uses `str.replace` and would light up every repeated word.
  - Write ASS override tags as raw strings (`r"{\fscx80}"`). In plain strings, `\f` is a form-feed and `\N` is a syntax error.
  - Caption styling costs almost no render time; benchmarks run at about 1x realtime with or without captions.

### Studio UI: `framefluence/studio.py` and `framefluence/ui/index.html`
- **Server:** standard-library `ThreadingHTTPServer`, bound to `127.0.0.1` only, with no framework and no build step. The UI is one vanilla HTML/CSS/JS file, and Montserrat is served from `assets/fonts` via `/fonts/`.
- **Jobs:** `JobRunner` allows **one pipeline subprocess at a time** (renders are memory-hungry), using `.venv` Python if present, and returns HTTP 409 if another job is running. Output goes to `logs/studio_job.log`; `/api/job` returns only the INFO/WARNING/ERROR lines as progress steps.
- **Safety:** every draft path goes through `draft_dir()`, which takes a status whitelist and a `[\w.-]+` name and requires `reel.mp4` to exist. Uploads go through `safe_filename()`. Keep new routes behind these checks.
- **Upload:** a raw request body, not multipart. The filename and sidecar fields arrive in the query string, and the file is written as `.part` and renamed, so the autopilot never sees half-written files. Scene start/end typed as `mm:ss` are converted to seconds in the browser.
- **Video:** `send_file` supports HTTP `Range`, which the `<video>` element needs for seeking. Thumbnails are generated once per draft by ffmpeg (`thumb.jpg`, regenerated when `reel.mp4` is newer).
- **Draft data:** `meta.json` `pick` (`"editor"`, a beat rank `1..n`, or `"whole"`) drives the card badge. Strips are grouped by `header`.
- **UI design:** a projection-booth umber palette with the reels' caption gold (`#FFD700`) as the accent, and drafts shown as frames on a sprocketed film strip. `#open=<status>/<name>` deep-links into the editor, which is handy for headless screenshots. Headless Edge enforces a ~500px minimum viewport, so screenshots narrower than that are cropped.

### Look settings: `framefluence/look.py`
- A draft's look is flat keys in `meta.json`: `caption_style`, `caption_font`, `caption_color`, `caption_size`, `caption_position` (0.1–0.95, the caption baseline as a share of height), `show_watermark`, `watermark_align` (`left`/`center`/`right`), and `watermark_position` (0–0.97, the top of the watermark).
- `sanitize()` is the only gate for user input (Studio edits, `settings.json`). `full_look()` fills in defaults. `resolve_watermark()` returns `(text, align, y_px)` for `make_reel`; drafts with no watermark keys keep the legacy automatic placement.
- **Defaults:** the Studio's "Use as my default" writes `settings.json` at the repo root (git-ignored). `autopilot.load_clip_meta` starts every new draft from it, and a `clip.json` overrides.
- **Studio editor:** a Look tab and a Post tab. The live **Layout preview** draws the caption and watermark over `clean.jpg` (a caption-free frame cut from `source_cut.mp4` with the same crop) using the same maths as `caption_style_line()`. Keep the two in sync when changing caption sizing or positioning.
- **Browser fonts:** caption fonts are loaded with `FontFace` in parallel and never block the editor. Montserrat reuses the page's own `@font-face` (weight 900): loading the same file twice made Chrome fail one request with "NetworkError".

### Video engine: `framefluence/make_reel.py`
- `build_ffmpeg_command(...)` is a **pure function** returning the argv list; `convert_to_reel()` just runs it. Tests check substrings of `" ".join(cmd)`.
- **Pipeline:** framing produces `[v1]`. Each overlay (`v_hdr`, `v_wm`, `v_hook`, `v_quote`, `v_sub`) reads `[{last_stream}]` and outputs a new label. New overlays must follow this pattern.
- **Framing** (`quote`/`clean`):
  - `full_bleed`: zoom + fixed crop via `pan_x`/`pan_y`
  - `track`: `scale=-2:1920,crop=1080:1920:x='<track_x>'`. The single quotes protect the expression's commas inside the filtergraph.
  - `matte`
  - `blur`
- **Split mode:** two 1080x960 halves `vstack`ed, watermark only, audio from the top clip.
- **Mode rules:** hook and quote render only in `quote` mode, and `--quote` is skipped when `--subtitles` is given.
- **Layout (y on 1920):** header 150 (34px), watermark 100 (or top-right 80 with a header, 28px), quote 1480. The hook box top is at 240, from the `.ass` file; the drawtext hook at 280 is used only when there are no subtitles. Captions sit at `margin_v` 560 from the bottom, above Instagram's UI.
- **Watermark placement:** `watermark_align`/`watermark_y` (CLI `--watermark-align`/`--watermark-y`) override the automatic spot (centre y=100, or top-right with a header).
- **Escaping:** `drawtext` text has `'` replaced with `’` and `:` escaped to `\:`. Subtitle paths change `\` to `/` and escape `:`.
- **Adding a CLI option:** update the signature, `argparse`, the explicit `convert_to_reel(...)` kwargs, `autopilot.process_clip` if relevant, and `trend_agent.generate_content_package`'s `suggested_command`, which must stay valid per mode.

### Trend agent: `framefluence/trend_agent.py`
- `get_upcoming_milestones()` computes countdowns **live** from `Birthday_Month_Day` + `Birth_Year` (it takes a `today=` argument for tests). The CSV's `Days_Until_Birthday`/`Age_Turning` columns are ignored.
- If `TMDB_API_KEY` is set (`.env`, loaded by `autopilot.load_env`), it merges popular-people birthdays from `tmdb_calendar.py`. CSV entries win on duplicate names.
- `get_breaking_trailers()` uses Reddit JSON with a hardcoded fallback, so it always returns items offline.
- `get_peer_trends()` reads `data/cinema_competitors_and_benchmarks.csv`.

## Notes
- `.env` holds credentials (`username`, `password`, optional `TMDB_API_KEY`). Don't print or commit it.
- `inbox/`, `review/`, `approved/`, `rejected/`, `logs/`, and `output/` are runtime data. User footage goes in `assets/footage/`.
- `.agents/plugins/superpowers/` is a vendored plugin. Don't edit it.
- The repo is meant for GitHub; check `git status` before committing so nothing ignored-but-sensitive is force-added.
