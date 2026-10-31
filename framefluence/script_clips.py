"""
Framefluence - batch shorts from a scripts guide.

A guide is a Markdown file listing clips per episode. Each clip has a title, a START DIALOGUE
line (cut in) and an END DIALOGUE line (cut out), followed by its dialogue as `> **Name:** line`
quotes. For every clip this tool finds those lines in the episode's subtitle track, snaps the cut
to shot changes, and renders it through the autopilot (face tracking, word captions, post caption).

    python -m framefluence script assets/footage/friends_s08_ep1_5_shorts_scripts.md --dry-run
    python -m framefluence script <guide.md> --clips 1.7,3.5
    python -m framefluence script <guide.md> --episodes 2

Episodes are matched to video files in assets/footage by their S08E02-style code. Clips that
already have a rendered draft are skipped, so an interrupted batch can simply be re-run.
"""

import argparse
import datetime
import difflib
import glob
import json
import logging
import os
import re
import sys

from framefluence.paths import FOOTAGE, LOGS, REVIEW, ROOT

log = logging.getLogger("autopilot")
CACHE = os.path.join(ROOT, "cache")

# Character hashtags for the shows we cut most; unknown speakers are simply skipped
CHARACTER_TAGS = {
    "ross": "#rossgeller", "rachel": "#rachelgreen", "monica": "#monicageller",
    "chandler": "#chandlerbing", "joey": "#joeytribbiani", "phoebe": "#phoebebuffay",
}


# ---------------------------------------------------------------- parsing

def _field(block, label):
    m = re.search(rf"\*\*{re.escape(label)}[^*]*:\*\*\s*`?(.+?)`?\s*$", block, re.M)
    return m.group(1).strip() if m else ""


def parse_guide(text):
    """Returns (show, [clip dicts]) from a scripts guide."""
    show = "Show"
    title_line = re.search(r"^#\s+(.+)$", text, re.M)
    if title_line:
        show = re.split(r"\s+Season\b|:", title_line.group(1))[0].strip()

    clips = []
    for ep_block in re.split(r"^## (?=Episode )", text, flags=re.M)[1:]:
        head = re.match(r"Episode\s+(\d+):\s*(.+?)\s*\(Season\s+(\d+),\s*Episode\s+(\d+)\)", ep_block)
        if not head:
            continue
        episode_title, season, episode = head.group(2).strip(), int(head.group(3)), int(head.group(4))
        for clip_block in re.split(r"^### (?=Clip )", ep_block, flags=re.M)[1:]:
            m = re.match(r"Clip\s+([\d.]+):\s*(.+)", clip_block)
            if not m:
                continue
            dialogue = [(d.group(1).strip(), d.group(2).strip())
                        for d in re.finditer(r"^>\s*\*\*(.+?):\*\*\s*(.+)$", clip_block, re.M)]
            est = re.search(r"~?(\d+)\s*sec", _field(clip_block, "Estimated Duration"))
            clips.append({
                "id": m.group(1), "title": m.group(2).strip(), "season": season, "episode": episode,
                "episode_title": episode_title, "start_line": _field(clip_block, "START DIALOGUE"),
                "end_line": _field(clip_block, "END DIALOGUE"), "teaser": _field(clip_block, "0:00 Teaser Hook"),
                "why": _field(clip_block, "Why the Hook Works"), "dialogue": dialogue,
                "estimate": int(est.group(1)) if est else None,
            })
    return show, clips


# ---------------------------------------------------------------- locating lines

def _tokens(text):
    return [t for t in (re.sub(r"[^a-z0-9]", "", w.lower()) for w in text.split()) if t]


def phrase_matches(words, phrase_tokens, lo=0.0, hi=float("inf"), anchor="start", min_score=0.0):
    """
    Every fuzzy match of phrase_tokens between lo and hi seconds, best first, as [(time, score)].
    The time is the first matched word's start (anchor="start") or the last matched word's end
    (anchor="end"). Fan transcripts and subtitles differ ("y'know" vs "you know"), so windows are
    scored with difflib instead of requiring exact text. Matches closer than 5s are merged.
    """
    idx = [i for i, w in enumerate(words) if lo <= w["start"] <= hi]
    if not idx or not phrase_tokens:
        return []
    norm = [re.sub(r"[^a-z0-9]", "", w["word"].lower()) for w in words]
    n = len(phrase_tokens)
    found = []
    for size in sorted({max(1, n - 2), n, n + 2}):
        for i in idx:
            window = norm[i:i + size]
            if not window:
                continue
            m = difflib.SequenceMatcher(a=phrase_tokens, b=window, autojunk=False)
            score = m.ratio()
            blocks = [b for b in m.get_matching_blocks() if b.size]
            if score < min_score or not blocks:
                continue
            if anchor == "start":
                t = words[i + blocks[0].b]["start"]
            else:
                last = blocks[-1]
                # Trailing phrase words that didn't match ("1" vs "one") are still spoken right
                # after the match, so extend over that many closely following transcript words
                j = i + last.b + last.size - 1
                for _ in range(n - (last.a + last.size)):
                    if j + 1 < len(words) and words[j + 1]["start"] - words[j]["end"] < 1.0:
                        j += 1
                t = words[j]["end"]
            found.append((t, score))
    merged = []
    for t, score in sorted(found, key=lambda x: -x[1]):
        if all(abs(t - u) > 5 for u, _ in merged):
            merged.append((t, score))
    return merged


def find_phrase(words, phrase_tokens, lo=0.0, hi=float("inf"), anchor="start"):
    """The single best match as (time, score), or (None, 0.0)."""
    matches = phrase_matches(words, phrase_tokens, lo, hi, anchor)
    return matches[0] if matches else (None, 0.0)


def locate_clip(clip, words, max_len=150.0):
    """
    (start, end, start_score, end_score) of a clip in the transcript, or None if not found.
    A START line can recur in an episode (Joey proposes with the same words twice), so every
    strong start candidate is tried and the one with the best-matching END after it wins.
    """
    start_tokens = _tokens(clip["start_line"])
    if len(start_tokens) < 6 and len(clip["dialogue"]) > 1:
        start_tokens += _tokens(clip["dialogue"][1][1])  # short openers need the next line too
    starts = phrase_matches(words, start_tokens[:12], anchor="start", min_score=0.5)
    if not starts:
        return None
    top = starts[0][1]
    # The clip's last ~12 words (its final lines) pin the end more reliably than a lone "What?!"
    closing = " ".join(line for _, line in clip["dialogue"][-3:]) or clip["end_line"]
    end_tokens = _tokens(closing)[-12:]
    best = None
    for start, s_score in starts:
        if s_score < top - 0.15:
            break
        end, e_score = find_phrase(words, end_tokens, lo=start + 5, hi=start + max_len, anchor="end")
        if end is None or e_score < 0.45:
            continue
        if best is None or s_score + e_score > best[2] + best[3]:
            best = (start, end, s_score, e_score)
    return best


def snap_to_shots(start, end, shots, words):
    """Moves the cut-in back to a nearby shot change and lets the punchline breathe before cut-out."""
    cuts = [s for s, _ in shots]
    before = [c for c in cuts if start - 1.2 <= c <= start + 0.15]
    new_start = before[-1] if before else max(0.0, start - 0.25)
    later = [w["start"] for w in words if w["start"] > end + 0.05]
    limit = min(end + 1.5, (later[0] - 0.1) if later else end + 1.5)
    after = [c for c in cuts if end - 0.2 <= c <= limit]
    new_end = after[0] if after else min(end + 0.8, limit)
    return round(new_start, 3), round(max(new_end, end), 3)


# ---------------------------------------------------------------- per-episode data

def episode_file(season, episode, folder=FOOTAGE):
    code = f"s{season:02d}e{episode:02d}"
    for path in sorted(glob.glob(os.path.join(folder, "*"))):
        name = os.path.basename(path).lower().replace(".", "_")
        if code in name and path.lower().endswith((".mkv", ".mp4", ".mov", ".webm", ".m4v")):
            return path
    return None


def cached(name, build):
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, name)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    data = build()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    return data


def episode_data(video):
    """Subtitle words and shot list for an episode, cached under cache/ (git-ignored)."""
    from framefluence.auto_subtitles import embedded_subtitle_words
    from framefluence.scene_cut import detect_scenes

    key = re.sub(r"[^\w]+", "_", os.path.basename(video))[:80]
    words = cached(f"{key}.words.json", lambda: embedded_subtitle_words(video))
    shots = cached(f"{key}.shots.json", lambda: [list(s) for s in detect_scenes(video)])
    return words, [tuple(s) for s in shots]


# ---------------------------------------------------------------- rendering

def clip_meta(show, clip):
    code = f"S{clip['season']:02d}E{clip['episode']:02d}"
    speakers = []
    for name, _ in clip["dialogue"]:
        for part in re.split(r"\s+and\s+|,", name.lower()):
            tag = CHARACTER_TAGS.get(part.strip())
            if tag and tag not in speakers:
                speakers.append(tag)
    show_tag = "#" + re.sub(r"[^a-z0-9]", "", show.lower())
    from framefluence.look import load_defaults
    # Start from the user's saved look (font, speed, watermark...) like autopilot drafts do
    return {
        **load_defaults(),
        "title": f"{show} {code} - {clip['title']}",
        "header": f"{show.upper()} | {code}",
        "hook": re.sub(r"\s*\(.*?\)\s*$", "", clip["title"]),
        "context": clip["why"] or f"From {show} {code}, {clip['episode_title']}.",
        "question": f"Which {show} moment do you still quote?",
        "hashtags": " ".join([show_tag, f"{show_tag}tvshow", *speakers[:3], "#sitcom"]),
        "mode": "quote", "pick": "script", "script_clip": clip["id"],
    }


def draft_dir(show, clip, day):
    from framefluence.autopilot import slugify
    slug = slugify(f"{show} s{clip['season']:02d}e{clip['episode']:02d} clip {clip['id']} {clip['title']}")
    return os.path.join(REVIEW, f"{day}_{slug}")


def existing_draft(show, clip):
    """Any earlier render of this clip (any date), so re-runs skip finished work."""
    pattern = os.path.basename(draft_dir(show, clip, "*"))
    for folder in (REVIEW, os.path.join(ROOT, "approved"), os.path.join(ROOT, "rejected")):
        for path in glob.glob(os.path.join(folder, pattern)):
            if all(os.path.exists(os.path.join(path, f)) for f in ("reel.mp4", "meta.json")):
                return path
    return None


def plan(show, clips, wanted_clips=None, wanted_episodes=None, max_span=150.0):
    """Locates every requested clip. Returns [(clip, video, start, end, note)]."""
    from framefluence.scene_cut import probe_duration

    rows = []
    for ep in sorted({c["episode"] for c in clips}):
        if wanted_episodes and ep not in wanted_episodes:
            continue
        ep_clips = [c for c in clips if c["episode"] == ep and (not wanted_clips or c["id"] in wanted_clips)]
        if not ep_clips:
            continue
        video = episode_file(ep_clips[0]["season"], ep)
        if not video:
            rows += [(c, None, None, None, "episode file not found in assets/footage") for c in ep_clips]
            continue
        log.info("Episode %d: %s", ep, os.path.basename(video))
        words, shots = episode_data(video)
        duration = probe_duration(video)
        for c in ep_clips:
            found = locate_clip(c, words, max_len=max_span)
            if not found:
                rows.append((c, video, None, None, "lines not found in subtitles"))
                continue
            start, end, s_score, e_score = found
            start, end = snap_to_shots(start, end, shots, words)
            end = min(end, duration)
            note = f"match {s_score:.2f}/{e_score:.2f}"
            if c["estimate"] and abs((end - start) - c["estimate"]) > 20:
                note += f", length differs from guide (~{c['estimate']}s)"
            rows.append((c, video, start, end, note))
    return rows


def render(show, rows, whisper_model="small"):
    from framefluence.autopilot import render_draft
    from framefluence.scene_cut import probe_duration

    day = datetime.date.today().isoformat()
    done = failed = skipped = 0
    for clip, video, start, end, note in rows:
        if start is None:
            log.warning("Clip %s skipped: %s", clip["id"], note)
            failed += 1
            continue
        if existing_draft(show, clip):
            log.info("Clip %s already rendered, skipping", clip["id"])
            skipped += 1
            continue
        words, shots = episode_data(video)
        try:
            render_draft(video, draft_dir(show, clip, day), clip_meta(show, clip), start, end,
                         probe_duration(video), shots, words, True, True, True, whisper_model)
            done += 1
        except Exception:
            log.exception("Clip %s failed", clip["id"])
            failed += 1
    log.info("Script batch done: %d rendered, %d skipped (already done), %d failed", done, skipped, failed)
    return failed


def main():
    parser = argparse.ArgumentParser(description="Cut shorts listed in a scripts guide (Markdown)")
    parser.add_argument("guide", help="Path to the Markdown scripts guide")
    parser.add_argument("--clips", help="Comma-separated clip ids, e.g. 1.7,3.5")
    parser.add_argument("--episodes", help="Comma-separated episode numbers, e.g. 2,3")
    parser.add_argument("--dry-run", action="store_true", help="Only locate the clips and print the plan")
    parser.add_argument("--whisper-model", default="small")
    parser.add_argument("--max-span", type=float, default=150.0,
                        help="Furthest the END line may be from the START line, in seconds")
    args = parser.parse_args()

    os.chdir(ROOT)
    os.makedirs(LOGS, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.FileHandler(os.path.join(LOGS, "autopilot.log"), encoding="utf-8"),
                                  logging.StreamHandler(sys.stdout)])
    with open(args.guide, encoding="utf-8") as f:
        show, clips = parse_guide(f.read())
    wanted_clips = set(args.clips.split(",")) if args.clips else None
    wanted_eps = {int(e) for e in args.episodes.split(",")} if args.episodes else None
    log.info("%s: %d clips in guide", show, len(clips))

    rows = plan(show, clips, wanted_clips, wanted_eps, args.max_span)
    for clip, _, start, end, note in rows:
        span = f"{start // 60:.0f}:{start % 60:05.2f}-{end // 60:.0f}:{end % 60:05.2f} ({end - start:4.1f}s)" if start is not None else "-"
        print(f"  {clip['id']:>4}  {span:30}  {clip['title'][:55]:55}  {note}")
    if args.dry_run:
        return 0
    return 1 if render(show, rows, args.whisper_model) else 0


if __name__ == "__main__":
    sys.exit(main())
