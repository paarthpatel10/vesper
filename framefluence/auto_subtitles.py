"""
Framefluence - Automatic word-by-word subtitles.
Transcribes a clip with faster-whisper (local, free) and writes an .ass file where
each word turns gold as it is spoken, reusing subtitle_engine's cinema styling.
"""

import difflib
import os
import re
import subprocess

from framefluence.subtitle_engine import generate_ass_subtitles

GOLD = "&H0000D7FF"  # #FFD700 in &HAABBGGRR


def transcribe_words(video_path, model_size="small", language="en"):
    """Returns [{"word", "start", "end"}, ...]. Requires `faster-whisper`; model downloads on first use."""
    from faster_whisper import WhisperModel

    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments, _ = model.transcribe(video_path, language=language, word_timestamps=True, vad_filter=True)
    words = []
    for segment in segments:
        for w in segment.words or []:
            text = w.word.strip()
            if text:
                words.append({"word": text, "start": w.start, "end": w.end})
    return words


def parse_srt_words(srt_text):
    """
    Turns SRT cues into approximate per-word timings (each cue's duration split evenly across its
    words). Good enough for picking a segment; precise subtitles still come from Whisper.
    Drops sound cues ([MUSIC]), speaker labels (PHOEBE:), HTML tags and dialogue dashes.
    """
    words = []
    for block in re.split(r"\n\s*\n", srt_text.strip()):
        lines = block.strip().splitlines()
        timing = next((l for l in lines if "-->" in l), None)
        if not timing:
            continue
        start, end = (_srt_seconds(t) for t in timing.split("-->"))
        text = " ".join(lines[lines.index(timing) + 1:])
        text = re.sub(r"<[^>]+>", "", text)
        text = re.sub(r"\[[^\]]*\]|\([^)]*\)|\b[A-Z]{2,}(?: [A-Z]{2,})*:", " ", text)
        tokens = [t for t in text.replace(" - ", " ").split() if t not in ("-", "...")]
        if not tokens:
            continue
        step = (end - start) / len(tokens)
        for i, token in enumerate(tokens):
            words.append({"word": token.lstrip("-"), "start": start + i * step, "end": start + (i + 1) * step})
    return words


def _srt_seconds(stamp):
    h, m, rest = stamp.strip().split(":")
    s, ms = rest.replace(".", ",").split(",")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def embedded_subtitle_words(video_path):
    """Reads the first embedded subtitle track (e.g. MKV SRT) as approximate words; [] if there is none."""
    result = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", video_path, "-map", "0:s:0", "-f", "srt", "-"],
        capture_output=True,
    )
    if result.returncode != 0:
        return []
    return parse_srt_words(result.stdout.decode("utf-8", errors="ignore"))


def _norm(token):
    return re.sub(r"[^a-z0-9']", "", token.lower())


def align_reference(reference, asr):
    """
    Best of both: the *text* of a reference transcript (official subtitles - exact wording, names)
    with the *timing* of Whisper's words. Matching words copy Whisper's timestamps; unmatched
    reference words are spread evenly between the nearest matched neighbours, or keep their own
    approximate timing when no anchor is near.
    """
    if not asr:
        return [dict(w) for w in reference]
    matcher = difflib.SequenceMatcher(a=[_norm(w["word"]) for w in reference],
                                      b=[_norm(w["word"]) for w in asr], autojunk=False)
    timed = [None] * len(reference)
    for block in matcher.get_matching_blocks():
        for k in range(block.size):
            src = asr[block.b + k]
            timed[block.a + k] = (src["start"], src["end"])

    out, i = [], 0
    while i < len(reference):
        if timed[i]:
            out.append({**reference[i], "start": timed[i][0], "end": timed[i][1]})
            i += 1
            continue
        j = i
        while j < len(reference) and not timed[j]:
            j += 1
        lo = timed[i - 1][1] if i > 0 and timed[i - 1] else None
        hi = timed[j][0] if j < len(reference) else None
        run = reference[i:j]
        # Only interpolate inside a tight gap; otherwise the reference's own timing is more honest
        if lo is not None and hi is not None and 0 < hi - lo <= 1.5 * len(run) + 1:
            step = (hi - lo) / len(run)
            out.extend({**w, "start": lo + k * step, "end": lo + (k + 1) * step} for k, w in enumerate(run))
        else:
            out.extend(dict(w) for w in run)
        i = j
    return out


def group_words(words, max_words=3, max_gap=0.6):
    """Groups words into short on-screen phrases, breaking on pauses and sentence ends."""
    groups, current = [], []
    for w in words:
        if current and (
            len(current) >= max_words
            or w["start"] - current[-1]["end"] > max_gap
            or current[-1]["word"][-1] in ".?!"
        ):
            groups.append(current)
            current = []
        current.append(w)
    if current:
        groups.append(current)
    return groups


def words_to_karaoke_chunks(words, max_words=3):
    """
    One subtitle event per spoken word: the whole phrase is shown, with the current word
    highlighted. Each event lasts until the next word starts so the phrase never flickers.
    """
    chunks = []
    for group in group_words(words, max_words=max_words):
        for i, w in enumerate(group):
            # Tag by position, not by text, so repeated words ("knock knock knock") light up one at a time
            text = " ".join(
                f"{{\\c{GOLD}&}}{g['word']}{{\\c&H00FFFFFF&}}" if j == i else g["word"]
                for j, g in enumerate(group)
            )
            end = group[i + 1]["start"] if i + 1 < len(group) else w["end"]
            chunks.append({"start": w["start"], "end": max(end, w["start"] + 0.05), "text": text})
    return chunks


def shift_words(words, start, end):
    """Keeps words inside [start, end) and re-times them so a cut clip's subtitles start at t=0."""
    return [{**w, "start": w["start"] - start, "end": min(w["end"], end) - start}
            for w in words if start <= w["start"] < end]


# Caption looks. Colours are &HAABBGGRR; sizes are for the 1080x1920 canvas.
STYLES = {
    # Short-form "viral" look: huge uppercase Montserrat Black, thick outline, gold active word that pops
    "bold": {"font": "Montserrat Black", "size": 96, "outline": 7, "shadow": 3, "upper": True,
             "active_scale": 115, "pop": True, "margin_v": 560},
    # Calmer look for emotional scenes: sentence case, smaller, no pop
    "clean": {"font": "Montserrat", "size": 74, "outline": 5, "shadow": 2, "upper": False,
              "active_scale": 100, "pop": False, "margin_v": 520},
}


def _greedy_lines(words, width):
    lines, line = [], ""
    for word in words:
        if line and len(line) + 1 + len(word) > width:
            lines.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    return lines + ([line] if line else [])


def wrap_hook(text, width=20):
    """
    Balanced word wrap with ASS hard breaks: as few lines as a `width`-char wrap needs, but with
    even line lengths, so the boxed hook never leaves a lonely last word ("... wait for / it").
    """
    words = text.split()
    count = len(_greedy_lines(words, width))
    target = max(len(text) // count, max(map(len, words), default=1))
    while len(_greedy_lines(words, target)) > count:
        target += 1
    return r"\N".join(_greedy_lines(words, target))


def build_caption_events(words, style="bold", max_words=3):
    """One Dialogue line per spoken word: the phrase with that word gold (and enlarged in 'bold')."""
    cfg = STYLES[style]
    events = []
    for group in group_words(words, max_words=max_words):
        texts = [g["word"].upper() if cfg["upper"] else g["word"] for g in group]
        for i, w in enumerate(group):
            # The phrase pops in (each word scales up from 80%) on its first word only, so later
            # words in the same phrase don't jitter
            pop = cfg["pop"] and i == 0
            tokens = []
            for j, t in enumerate(texts):
                colour = GOLD if j == i else "&H00FFFFFF"
                scale = cfg["active_scale"] if j == i else 100
                grow = rf"\fscx{scale * 4 // 5}\fscy{scale * 4 // 5}\t(0,90,\fscx{scale}\fscy{scale})" if pop \
                    else rf"\fscx{scale}\fscy{scale}"
                tokens.append("{" + rf"\c{colour}&" + grow + "}" + t)
            line = " ".join(tokens)
            end = group[i + 1]["start"] if i + 1 < len(group) else w["end"]
            events.append((w["start"], max(end, w["start"] + 0.05), "Caption", line))
    return events


def write_subtitles(words, output_path, style="bold", hook=None, hook_seconds=None):
    """
    Writes the styled .ass file: word-by-word captions plus (optionally) the hook as a white box
    with black text at the top, fading in. Returns the path, or None if there is nothing to draw.
    """
    from framefluence.subtitle_engine import format_timestamp_ass as ts

    cfg = STYLES[style]
    events = build_caption_events(words, style) if words else []
    if hook:
        end = hook_seconds or (max((e[1] for e in events), default=0.0) + 1.0)
        events.insert(0, (0.0, end, "Hook", r"{\fad(250,0)}" + wrap_hook(hook)))
    if not events:
        return None

    header = f"""[Script Info]
Title: Framefluence Captions
ScriptType: v4.00+
WrapStyle: 2
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,{cfg['font']},{cfg['size']},&H00FFFFFF,&H000000FF,&H00000000,&H90000000,-1,0,0,0,100,100,1,0,1,{cfg['outline']},{cfg['shadow']},2,70,70,{cfg['margin_v']},1
Style: Hook,Montserrat Black,66,&H00000000,&H000000FF,&H00FFFFFF,&H00FFFFFF,-1,0,0,0,100,100,0,0,3,18,0,8,80,80,240,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [f"Dialogue: {1 if name == 'Hook' else 0},{ts(a)},{ts(b)},{name},,0,0,0,,{text}"
             for a, b, name, text in events]
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(header + "\n".join(lines) + "\n")
    return output_path


def payoff_line(words, max_words=14):
    """The last full sentence in a segment - usually the punchline - for use as the caption quote."""
    sentence = []
    for w in reversed(words):
        if sentence and w["word"][-1] in ".?!":
            break
        sentence.insert(0, w["word"])
    text = " ".join(sentence).strip()
    return text if 2 <= len(sentence) <= max_words else ""


def generate_auto_subtitles(video_path, output_path, model_size="small"):
    """Transcribes and writes the .ass file. Returns the path, or None if no speech was found."""
    return write_subtitles(transcribe_words(video_path, model_size=model_size), output_path)
