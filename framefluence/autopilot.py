"""
Framefluence - Autopilot.
Daily pipeline: writes the trend briefing, then turns every clip dropped into inbox/
into a ready-to-review Reel draft in review/<date>_<slug>/ (reel.mp4 + caption.txt + meta.json).

    inbox/clip.mp4 (+ optional clip.json) -> transcribe -> pick story beat -> cut -> face-track
        -> word-by-word subtitles -> render -> review/

Optional clip.json keys: title, header, hook, quote, context, question, mode ("quote"/"clean"),
start/end (seconds; skips automatic picking).
Each smart step (cutting, tracking, subtitles) falls back gracefully if its library or detection fails.
"""

import argparse
import contextlib
import datetime
import io
import json
import logging
import os
import re
import shutil
import subprocess
import sys

from framefluence.paths import ENV_FILE, INBOX, LOGS, PROCESSED, REVIEW, ROOT
VIDEO_EXTS = (".mp4", ".mov", ".mkv", ".webm", ".m4v")

log = logging.getLogger("autopilot")


def load_env(path=ENV_FILE):
    """Minimal KEY=VALUE loader so TMDB_API_KEY etc. reach the pipeline without extra dependencies."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"'))


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:50] or "clip"


def probe_size(video_path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
         "-of", "csv=s=x:p=0", video_path],
        capture_output=True, text=True, check=True,
    )
    w, h = out.stdout.strip().split("x")[:2]
    return int(w), int(h)


def load_clip_meta(video_path):
    sidecar = os.path.splitext(video_path)[0] + ".json"
    meta = {}
    if os.path.exists(sidecar):
        with open(sidecar, encoding="utf-8") as f:
            meta = json.load(f)
    title = meta.get("title") or os.path.splitext(os.path.basename(video_path))[0].replace("_", " ").title()
    meta.setdefault("title", title)
    meta.setdefault("header", title.upper())
    meta.setdefault("mode", "quote")
    return meta, sidecar if os.path.exists(sidecar) else None


def relative_scenes(scenes, start, end):
    """Clips shot boundaries to [start, end) and shifts them so the cut clip starts at t=0."""
    out = []
    for s, e in scenes:
        s, e = max(s, start), min(e, end)
        if e > s:
            out.append((s - start, e - start))
    return out


def write_briefing(day):
    from framefluence.trend_agent import print_daily_briefing

    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        print_daily_briefing()
    path = os.path.join(REVIEW, f"{day}_briefing.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(buffer.getvalue())
    log.info("Briefing written: %s", path)
    return path


def analyse_source(video_path, use_cut, use_track, use_subs, whisper_model, need_pick=True):
    """
    Shots + a cheap full-length transcript for picking: the embedded subtitle track if present,
    else a fast Whisper pass. Returns (scenes, words, words_are_reference); embedded subtitles
    count as a reference (exact wording) for subtitle text. Precise timing comes later, per cut.
    """
    from framefluence.auto_subtitles import embedded_subtitle_words
    from framefluence.scene_cut import detect_scenes

    scenes, words = [], []
    if need_pick and (use_cut or use_track):
        try:
            scenes = detect_scenes(video_path)
            log.info("  %d shots detected", len(scenes))
        except Exception as e:
            log.warning("  Scene detection unavailable (%s); using whole clip", e)
    if use_cut or use_subs:
        words = embedded_subtitle_words(video_path)
        if words:
            log.info("  Using embedded subtitle track (%d words)", len(words))
            return scenes, words, True
        if need_pick:
            try:
                from framefluence.auto_subtitles import transcribe_words
                words = transcribe_words(video_path, model_size="tiny" if use_cut else whisper_model)
                log.info("  Transcribed %d words for picking", len(words))
            except Exception as e:
                log.warning("  Transcription unavailable (%s)", e)
    return scenes, words, False


def pick_segments(video_path, meta, scenes, words, duration, use_cut, max_len, drafts):
    """clip.json start/end wins; else the top-ranked story beats; else a clean run of shots."""
    from framefluence.scene_cut import audio_energy, choose_segment, rank_story_segments

    if "start" in meta and "end" in meta:
        log.info("  Using clip.json segment")
        return [(float(meta["start"]), float(meta["end"]))]
    if not use_cut or duration <= max_len:
        return [(0.0, duration)]
    if words:
        try:
            ranked = rank_story_segments(words, scenes, audio_energy(video_path), duration,
                                         min_len=min(60.0, max_len - 15), max_len=max_len, top_n=drafts)
            if ranked:
                log.info("  Picked %d story beat(s): %s", len(ranked),
                         ", ".join(f"{s:.0f}-{e:.0f}s" for s, e, _ in ranked))
                return [(s, e) for s, e, _ in ranked]
        except Exception as e:
            log.warning("  Story picker unavailable (%s)", e)
    log.info("  Picked shot-run segment")
    return [choose_segment(scenes, duration, max_len=max_len)]


def render_draft(video_path, work, meta, start, end, duration, scenes, pick_words, words_are_reference,
                 use_track, use_subs, whisper_model):
    from framefluence.make_reel import convert_to_reel
    from framefluence.scene_cut import cut_clip, detect_scenes
    from framefluence.trend_agent import generate_content_package

    os.makedirs(work, exist_ok=True)
    log.info("  Draft %s (%.1fs-%.1fs)", os.path.basename(work), start, end)

    # Cut so every later step works on a clip whose timestamps start at 0
    clip = video_path
    if (start, end) != (0.0, duration):
        clip = cut_clip(video_path, start, end, os.path.join(work, "source_cut.mp4"))
    if not scenes and use_track:
        try:
            shots = detect_scenes(clip)
        except Exception as e:
            log.warning("    Shot detection on cut failed (%s)", e)
            shots = []
    else:
        shots = relative_scenes(scenes, start, end)
    shots = shots or [(0.0, end - start)]

    # Face-tracked framing for landscape sources
    framing, track_x = "full_bleed", None
    width, height = probe_size(clip)
    if use_track and width / height > 1.2:
        try:
            from framefluence.reframe import crop_x_expression, sample_face_centers, shot_centers
            src_w, src_h, samples = sample_face_centers(clip)
            if any(cx is not None for _, cx in samples):
                track_x = crop_x_expression(shots, shot_centers(samples, shots), src_w, src_h)
                framing = "track"
                log.info("    Face tracking on (%d shots)", len(shots))
            else:
                log.info("    No faces found; using centre crop")
        except Exception as e:
            log.warning("    Face tracking unavailable (%s); using centre crop", e)

    # Word-by-word subtitles: Whisper timings on the cut; with an official subtitle track, its exact
    # wording is aligned onto Whisper's timings (Whisper alone mishears names and soft lines)
    words = []
    if use_subs and meta["mode"] == "quote":
        from framefluence.auto_subtitles import align_reference, shift_words, transcribe_words
        reference = shift_words(pick_words, start, end) if words_are_reference else []
        try:
            asr = transcribe_words(clip, model_size=whisper_model)
        except Exception as e:
            log.warning("    Whisper unavailable (%s)", e)
            asr = []
        if reference:
            words = align_reference(reference, asr)
            log.info("    Subtitle text from embedded track, timing from Whisper")
        else:
            words = asr or shift_words(pick_words, start, end)

    return finish_draft(work, clip, meta, words, framing, track_x, start, end, os.path.basename(video_path))


def finish_draft(work, clip, meta, words, framing, track_x, start, end, source, style=None):
    """
    Styling + render + post package. Separate from analysis so `--restyle` can re-run it from a
    draft's saved words.json and meta.json without re-transcribing or re-picking.
    """
    from framefluence.auto_subtitles import payoff_line, write_subtitles
    from framefluence.make_reel import convert_to_reel
    from framefluence.trend_agent import generate_content_package

    style = style or meta.get("caption_style", "bold")
    # Hook box and show title are off by default (they cover the picture); the hook still leads the
    # post caption. Opt back in per draft with meta "show_hook" / "show_header".
    on_video_hook = meta.get("hook") if meta.get("show_hook") else None
    on_video_header = meta.get("header") if meta.get("show_header") else None
    subtitle_file = None
    if meta["mode"] == "quote" and (words or on_video_hook):
        # When shown, the hook lives in the .ass file (boxed, wrapped, animated), not as drawtext
        subtitle_file = write_subtitles(words, os.path.join(work, "subtitles.ass"), style=style,
                                        hook=on_video_hook, hook_seconds=end - start)
        log.info("    Captions (%s): %s", style, "generated" if subtitle_file else "none")
    with open(os.path.join(work, "words.json"), "w", encoding="utf-8") as f:
        json.dump(words, f)

    reel = os.path.join(work, "reel.mp4")
    ok = convert_to_reel(
        mode=meta["mode"], input_file=clip, output_file=reel,
        header_text=on_video_header,
        hook_text=None if subtitle_file else on_video_hook,
        quote_text=meta.get("quote") if not subtitle_file else None,
        subtitle_file=os.path.relpath(subtitle_file, ROOT) if subtitle_file else None,
        framing=framing, track_x=track_x,
    )
    if not ok:
        raise RuntimeError("FFmpeg render failed")

    pkg = generate_content_package({
        "title": meta["title"],
        "hook": meta.get("hook") or meta["title"],
        # Each beat gets its own punchline as the caption quote unless clip.json sets one
        "quote": meta.get("quote") or payoff_line(words),
        "context": meta.get("context", "A legendary cinematic moment."),
        "question": meta.get("question", "What's your favourite scene from this?"),
        "recommended_mode": meta["mode"],
        "extra_hashtags": meta.get("hashtags", ""),
    })
    with open(os.path.join(work, "caption.txt"), "w", encoding="utf-8") as f:
        f.write(pkg["caption"] + "\n\n" + pkg["hashtags"] + "\n")
    derived = {"source": source, "segment": [round(start, 2), round(end, 2)], "framing": framing,
               "track_x": track_x, "subtitles": bool(words), "caption_style": style,
               "status": "pending_review", "created": datetime.datetime.now().isoformat(timespec="seconds")}
    with open(os.path.join(work, "meta.json"), "w", encoding="utf-8") as f:
        json.dump({**meta, **derived}, f, indent=2)
    log.info("    Draft ready: %s", reel)
    return work


def restyle_draft(work, style=None):
    """Re-renders an existing draft with the current caption styling, reusing its saved analysis."""
    from framefluence.auto_subtitles import align_reference, embedded_subtitle_words, shift_words, transcribe_words

    with open(os.path.join(work, "meta.json"), encoding="utf-8") as f:
        meta = json.load(f)
    start, end = meta["segment"]
    clip = os.path.join(work, "source_cut.mp4")
    words_path = os.path.join(work, "words.json")
    if os.path.exists(words_path):
        with open(words_path, encoding="utf-8") as f:
            words = json.load(f)
    else:
        # Drafts made before words.json existed: rebuild the aligned transcript once
        source = os.path.join(PROCESSED, meta["source"])
        reference = shift_words(embedded_subtitle_words(source), start, end) if os.path.exists(source) else []
        asr = transcribe_words(clip)
        words = align_reference(reference, asr) if reference else asr
    framing, track_x = meta.get("framing", "full_bleed"), meta.get("track_x")
    if framing == "track" and not track_x:
        from framefluence.reframe import build_track_expression
        track_x = build_track_expression(clip)
    log.info("Restyling %s", os.path.basename(work))
    return finish_draft(work, clip, meta, words, framing, track_x, start, end, meta["source"], style=style)


def process_clip(video_path, day, use_cut=True, use_track=True, use_subs=True, whisper_model="small",
                 max_len=118.0, drafts=3):
    """Turns one inbox clip into one or more drafts (top story beats for long sources like episodes)."""
    from framefluence.scene_cut import probe_duration

    meta, sidecar = load_clip_meta(video_path)
    log.info("Processing %s", os.path.basename(video_path))
    duration = probe_duration(video_path)
    manual = "start" in meta and "end" in meta
    scenes, words, words_are_reference = analyse_source(video_path, use_cut, use_track, use_subs,
                                                        whisper_model, need_pick=not manual)
    segments = pick_segments(video_path, meta, scenes, words, duration, use_cut, max_len, drafts)

    base = os.path.join(REVIEW, f"{day}_{slugify(meta['title'])}")
    works = []
    for k, (start, end) in enumerate(segments, 1):
        work = base if len(segments) == 1 else f"{base}_beat{k}"
        # "pick" records how the segment was chosen: editor's cut, ranked beat k, or the whole clip
        pick = "editor" if manual else (k if len(segments) > 1 else "whole")
        works.append(render_draft(video_path, work, {**meta, "pick": pick}, start, end, duration, scenes,
                                  words, words_are_reference, use_track, use_subs, whisper_model))

    # Archive the source so it is never processed twice
    os.makedirs(PROCESSED, exist_ok=True)
    for path in filter(None, [video_path, sidecar]):
        shutil.move(path, os.path.join(PROCESSED, os.path.basename(path)))
    return works


def main():
    parser = argparse.ArgumentParser(description="Framefluence Autopilot: inbox clips -> reviewed Reel drafts")
    parser.add_argument("--no-cut", action="store_true", help="Skip automatic clip cutting")
    parser.add_argument("--no-track", action="store_true", help="Skip face-tracked framing")
    parser.add_argument("--no-subs", action="store_true", help="Skip auto-subtitles")
    parser.add_argument("--no-briefing", action="store_true", help="Skip writing the daily trend briefing")
    parser.add_argument("--whisper-model", default="small", help="faster-whisper model (tiny/base/small/medium)")
    parser.add_argument("--max-len", type=float, default=118.0, help="Longest reel in seconds (Reels cap: under 2 min)")
    parser.add_argument("--drafts", type=int, default=3, help="Drafts per long source (top-ranked story beats)")
    parser.add_argument("--restyle", nargs="+", metavar="DRAFT", help="Re-render review/ drafts with current styling")
    parser.add_argument("--style", choices=["bold", "clean"], help="Caption style for --restyle (default: draft's own)")
    args = parser.parse_args()

    os.chdir(ROOT)  # make_reel's font paths are relative; Task Scheduler may start elsewhere
    for d in (INBOX, REVIEW, LOGS):
        os.makedirs(d, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(os.path.join(LOGS, "autopilot.log"), encoding="utf-8"),
                  logging.StreamHandler(sys.stdout)],
    )
    load_env()
    day = datetime.date.today().isoformat()

    if args.restyle:
        for draft in args.restyle:
            restyle_draft(os.path.abspath(draft), style=args.style)
        return 0

    if not args.no_briefing:
        try:
            write_briefing(day)
        except Exception as e:
            log.warning("Briefing failed: %s", e)

    clips = sorted(f for f in os.listdir(INBOX) if f.lower().endswith(VIDEO_EXTS))
    if not clips:
        log.info("Inbox empty - drop clips into %s", INBOX)
    failures = 0
    for name in clips:
        try:
            process_clip(os.path.join(INBOX, name), day, use_cut=not args.no_cut,
                         use_track=not args.no_track, use_subs=not args.no_subs,
                         whisper_model=args.whisper_model, max_len=args.max_len,
                         drafts=args.drafts)
        except Exception:
            failures += 1
            log.exception("Failed on %s (left in inbox)", name)
    log.info("Done: %d clip(s) processed, %d failure(s)", len(clips) - failures, failures)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
