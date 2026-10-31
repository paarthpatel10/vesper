"""
Reel look settings: caption font/style/colour/size/position and watermark placement.

A draft's look lives in its meta.json. New drafts start from the user's saved defaults
(settings.json at the repo root, git-ignored), which the Studio writes with "Use as my default".
"""

import json
import os

from framefluence.auto_subtitles import COLORS, DEFAULT_LOOK, FONTS, SIZES, STYLES, resolve_look
from framefluence.paths import MUSIC, SETTINGS

WATERMARK_ALIGNS = ("left", "center", "right")
DEFAULT_WATERMARK = {"show_watermark": True, "watermark_align": "center", "watermark_position": 0.05}
# Playback speed: pacing only (pitch is preserved); it does not stop Content ID matching
SPEEDS = (1.0, 1.05, 1.1, 1.15, 1.2, 1.25)
# House defaults for every new reel: 10% faster pacing and the punchline push-in
DEFAULT_PLAYBACK = {"playback_speed": 1.1, "punch_zoom": True, "music_track": ""}
MUSIC_EXTS = (".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac")
# Render switches, per reel: the gentle grade, -14 LUFS loudness and how far the punchline zooms
DEFAULT_RENDER = {"color_grade": True, "normalize_audio": True, "punch_zoom_amount": 0.08}
# Pipeline defaults, settings-only: how long new reels may be and how many come from one video
LENGTHS = (30, 45, 60, 90, 118)
DRAFT_COUNTS = (1, 2, 3, 4, 5)
DEFAULT_PIPELINE = {"max_len": 60, "drafts": 3}
LOOK_KEYS = tuple(DEFAULT_LOOK) + tuple(DEFAULT_WATERMARK) + tuple(DEFAULT_PLAYBACK) + tuple(DEFAULT_RENDER)


def music_tracks():
    """Files the user has put in assets/music (only these can be chosen as a bed)."""
    if not os.path.isdir(MUSIC):
        return []
    return sorted(f for f in os.listdir(MUSIC) if f.lower().endswith(MUSIC_EXTS))


def _fraction(value, low, high):
    return min(high, max(low, float(value)))


def sanitize(fields):
    """Keeps only valid look keys from user input (Studio form, settings file); drops the rest."""
    clean = {}
    for key, registry in (("caption_style", STYLES), ("caption_font", FONTS),
                          ("caption_color", COLORS), ("caption_size", SIZES)):
        if fields.get(key) in registry:
            clean[key] = fields[key]
    if fields.get("watermark_align") in WATERMARK_ALIGNS:
        clean["watermark_align"] = fields["watermark_align"]
    if "show_watermark" in fields:
        clean["show_watermark"] = bool(fields["show_watermark"])
    for key in ("punch_zoom", "color_grade", "normalize_audio"):
        if key in fields:
            clean[key] = bool(fields[key])
    try:
        if "max_len" in fields and int(float(fields["max_len"])) in LENGTHS:
            clean["max_len"] = int(float(fields["max_len"]))
        if "drafts" in fields and int(float(fields["drafts"])) in DRAFT_COUNTS:
            clean["drafts"] = int(float(fields["drafts"]))
    except (TypeError, ValueError):
        pass
    if "music_track" in fields and (fields["music_track"] in music_tracks() or fields["music_track"] in ("", None)):
        clean["music_track"] = fields["music_track"] or ""
    for key, low, high in (("caption_position", 0.1, 0.95), ("watermark_position", 0.0, 0.97),
                           ("playback_speed", 0.75, 1.5), ("punch_zoom_amount", 0.02, 0.2)):
        try:
            if key in fields:
                clean[key] = round(_fraction(fields[key], low, high), 3)
        except (TypeError, ValueError):
            pass
    return clean


def resolve_watermark(meta):
    """(text or None, align, y_px) for make_reel. Drafts made before these settings keep auto placement."""
    if not meta.get("show_watermark", True):
        return None, None, None
    if "watermark_align" not in meta and "watermark_position" not in meta:
        return "@framefluence", None, None
    align = meta.get("watermark_align") if meta.get("watermark_align") in WATERMARK_ALIGNS else "center"
    try:
        position = _fraction(meta.get("watermark_position", DEFAULT_WATERMARK["watermark_position"]), 0.0, 0.97)
    except (TypeError, ValueError):
        position = DEFAULT_WATERMARK["watermark_position"]
    return "@framefluence", align, round(position * 1920)


def full_look(meta):
    """Every look key with defaults filled in: what the Studio shows and the render uses."""
    look = resolve_look(meta)
    for key, value in {**DEFAULT_WATERMARK, **DEFAULT_PLAYBACK, **DEFAULT_RENDER}.items():
        look[key] = meta.get(key, value)
    return {**look, **sanitize(meta)}


def load_defaults():
    """The user's saved default look ({} if none saved yet)."""
    try:
        with open(SETTINGS, encoding="utf-8") as f:
            return sanitize(json.load(f))
    except (OSError, ValueError):
        return {}


def pipeline_defaults():
    """Default reel length and reels per video: house values overridden by the saved settings."""
    saved = load_defaults()
    return {k: saved.get(k, v) for k, v in DEFAULT_PIPELINE.items()}


def reset_defaults():
    """Forgets the user's saved settings, so everything falls back to the house defaults."""
    if os.path.exists(SETTINGS):
        os.remove(SETTINGS)
    return options()["defaults"]


def save_defaults(fields):
    settings = {**load_defaults(), **sanitize(fields)}
    with open(SETTINGS, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)
    return settings


def options():
    """Choices for the Studio's look controls, straight from the registries."""
    return {
        "fonts": [{"id": k, "label": v["label"], "family": v["family"], "file": v["file"], "scale": v["scale"]}
                  for k, v in FONTS.items()],
        "styles": [{"id": k, "label": v["label"], "upper": v["upper"], "box": v["box"], "size": v["size"],
                    "outline": v["outline"], "highlight": v["highlight"]} for k, v in STYLES.items()],
        "colors": [{"id": k, "label": v["label"], "hex": v["hex"]} for k, v in COLORS.items()],
        "sizes": SIZES,
        "speeds": SPEEDS,
        "lengths": LENGTHS,
        "draft_counts": DRAFT_COUNTS,
        "music": music_tracks(),
        "defaults": {**DEFAULT_LOOK, **DEFAULT_WATERMARK, **DEFAULT_PLAYBACK, **DEFAULT_RENDER,
                     **DEFAULT_PIPELINE, **load_defaults()},
    }
