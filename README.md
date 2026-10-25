# vesper

Turn long videos into polished Shorts and Reels, automatically.

Vesper powers the [@framefluence](https://instagram.com/framefluence) cinema page, and its Python package is named `framefluence`. Drop in an episode and it finds the strongest scenes, cuts each one into a 9:16 reel under two minutes, keeps the speaker in frame, adds bold word-by-word captions, and writes the post caption. You review the drafts in a local web studio and post the ones you like.

## What it does

- **Finds scenes worth posting.** It scores stretches of dialogue on audience laughter, how much is being said, and whether the moment lands at the end. Theme songs and scene transitions are skipped.
- **Cuts on clean breaks.** Clips start and end on a pause that falls on a shot change, never mid-sentence.
- **Follows faces.** Each shot gets a 9:16 crop centred on the main face (OpenCV YuNet).
- **Captions every word.** Pick from six fonts (Montserrat, Anton, Bebas Neue, Archivo Black, Bangers, Luckiest Guy), five caption styles (bold, karaoke, boxed, clean, minimal), a highlight colour, a size and a position on screen. When the video has its own subtitle track, its exact wording is used with Whisper's timing.
- **Places your watermark.** Show or hide `@framefluence` and put it left, centre or right, anywhere from top to bottom.
- **Writes the post.** A caption with the hook, the scene's punchline, a question for comments and hashtags.
- **Suggests what to post.** Upcoming actor birthdays, trending trailers and proven formats from similar pages.

## Requirements

- Python 3.10 or newer
- [FFmpeg](https://ffmpeg.org/) (`ffmpeg` and `ffprobe` on your PATH)
- Windows, macOS or Linux (the optional scheduler script is Windows-only)

## Setup

```bash
git clone <this repo> framefluence
cd framefluence

python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt

copy .env.example .env          # macOS/Linux: cp .env.example .env   (optional: add a TMDB key)
```

The rendering tools work with plain Python. The packages in `requirements.txt` power transcription, scene detection and face tracking, and each of those steps falls back gracefully if its package is missing.

## Use it

Always run commands from the repository root.

```bash
python -m framefluence studio       # web studio at http://127.0.0.1:8765
```

In the studio, drop a video on the left, press **Make reels**, then open a draft. The **Look** tab sets the font, caption style, colour, size and position, and where the watermark goes, with a live layout preview before you re-render. **Use as my default** makes new reels start with that look. The **Post** tab edits the hook, hashtags and caption text.

Or from the command line:

```bash
python -m framefluence autopilot                 # every video in inbox/ becomes drafts in review/
python -m framefluence autopilot --drafts 2 --max-len 90
python -m framefluence autopilot --restyle review/<draft>   # re-render one draft with current styling
python -m framefluence review                    # list drafts, then: open | approve | reject <name>
python -m framefluence reel --help               # render a single reel by hand
python -m framefluence trends --briefing-only    # today's post ideas
python -m framefluence calendar                  # rebuild data/top_50_actors_calendar.csv
```

To pick an exact scene instead of letting the autopilot choose, put a JSON file next to the video in `inbox/` with the same name:

```json
{
  "title": "Friends - Rachel's pregnancy test",
  "header": "FRIENDS | S08E01",
  "hook": "Rachel's test result... wait for it",
  "hashtags": "#friends #friendstvshow",
  "start": 1164.95,
  "end": 1283.24
}
```

Run it daily on Windows with `powershell -ExecutionPolicy Bypass -File scripts\schedule_autopilot.ps1 -Time 09:00`.

## Project layout

```
framefluence/        the Python package
  __main__.py        `python -m framefluence <command>`
  autopilot.py       inbox -> drafts pipeline
  scene_cut.py       scene picking and cutting
  reframe.py         face-tracked 9:16 crop
  auto_subtitles.py  transcription, caption styling
  make_reel.py       FFmpeg renderer
  studio.py, ui/     local web studio
  trend_agent.py     post ideas and captions
data/                actor calendar and peer benchmarks
assets/fonts/        caption fonts (SIL Open Font License / Apache 2.0; licences in assets/fonts/licenses/)
models/              YuNet face detection model (OpenCV Zoo)
scripts/             Windows scheduler
tests/               python -m unittest discover tests
docs/                design notes
```

Runtime folders (`inbox/`, `review/`, `approved/`, `rejected/`, `logs/`, `output/`) and your footage in `assets/footage/` are created locally and are not committed.

## Tests

```bash
python -m unittest discover tests
```

The end-to-end test renders a short synthetic clip, so it needs FFmpeg.

## A note on footage

This repository contains no film or TV footage, and `.gitignore` keeps video files out of it. Use clips you have the rights to share. Reposting copyrighted scenes can get posts removed or muted.
