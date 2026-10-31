"""
Framefluence - Multi-Mode Automated 9:16 Instagram Reel Generator
Supports 3 distinct aesthetic rendering modes:
  1. 'quote': Full-bleed 9:16 or matte video + minimalist film header + dialogue subtitles + cinema color grade
  2. 'split': Stacked 50/50 comparison (top video & bottom video) for script/scene callbacks
  3. 'clean': Clean 9:16 canvas with watermark only (for trending audio & IG native text)
"""

import argparse
import os
import subprocess
import sys

# Priority fonts: Montserrat Bold/Black, falling back to Arial
MONTSERRAT_BOLD = "assets/fonts/Montserrat-Bold.ttf"
MONTSERRAT_BLACK = "assets/fonts/Montserrat-Black.ttf"
FALLBACK_FONT = "assets/fonts/arial.ttf"

def get_font_file(preferred=MONTSERRAT_BOLD):
    if os.path.exists(preferred):
        return preferred
    if os.path.exists(FALLBACK_FONT):
        return FALLBACK_FONT
    return "Arial"

def build_ffmpeg_command(
    mode="quote",
    input_file=None,
    top_file=None,
    bottom_file=None,
    output_file="reel_output.mp4",
    watermark="@framefluence",
    header_text=None,
    hook_text=None,
    quote_text=None,
    subtitle_file=None,
    framing="full_bleed",  # "full_bleed" | "matte" | "blur" | "track"
    color_grade=True,
    pan_x=0,
    pan_y=80,
    zoom=1.125,
    track_x=None,  # crop x expression for "track" framing (see reframe.py)
    watermark_align=None,  # "left" | "center" | "right"; None keeps the automatic placement
    watermark_y=None,  # top of the watermark in px on the 1920 canvas
    normalize_audio=True,  # -14 LUFS: the loudness YouTube and Instagram normalise to
    speed=1.0,  # playback speed (1.1 = 10% faster); audio keeps its natural pitch via atempo
    punch_zoom_at=None,  # seconds (original timeline) where a slow push-in on the speaker starts
    punch_zoom_amount=0.08,  # 0.08 = ends at 108%
    punch_zoom_seconds=2.0,
    fps="30",  # source frame rate (e.g. "24000/1001"), needed by the zoom
    music_file=None,  # optional licensed/royalty-free track mixed under the dialogue
    music_db=-28.0  # bed level; it is also ducked whenever someone speaks
):
    if mode not in ["quote", "split", "clean"]:
        raise ValueError(f"Invalid mode: '{mode}'. Supported modes are: quote, split, clean")

    ffmpeg_bin = "ffmpeg"
    font_bold = get_font_file(MONTSERRAT_BOLD)

    # Gentle cinema grade: subtle sharpening, a touch more contrast and colour
    grade_filter = "unsharp=3:3:0.5,eq=contrast=1.06:brightness=0.01:saturation=1.12"
    speed = float(speed or 1.0)
    if not 0.5 <= speed <= 2.0:
        raise ValueError(f"speed must be between 0.5 and 2.0, got {speed}")
    # atempo changes speed without changing pitch; then single-pass loudness normalisation,
    # with -ar pinning 48 kHz (loudnorm otherwise upsamples to 192 kHz)
    audio_filters = [f"atempo={speed:g}"] if speed != 1.0 else []
    if normalize_audio:
        audio_filters.append("loudnorm=I=-14:TP=-1.5:LRA=11")
    audio_args = ["-af", ",".join(audio_filters)] if audio_filters else []
    if normalize_audio:
        audio_args += ["-ar", "48000"]

    def audio_section(music_index):
        """
        (extra input args, filtergraph suffix, map/codec args) for the audio. Without music it is a
        plain -af chain. With music the bed is looped, lowered to music_db, ducked under the dialogue
        with sidechaincompress, mixed in, and then sped/normalised inside the filtergraph (FFmpeg
        refuses -af on a stream fed by -filter_complex).
        """
        if not music_file:
            return [], "", ["-map", "0:a?", *audio_args]
        tail = ("," + ",".join(audio_filters)) if audio_filters else ""
        graph = (f";[0:a]asplit=2[a_dlg][a_sc]"
                 f";[{music_index}:a]volume={music_db:g}dB[a_bed0]"
                 f";[a_bed0][a_sc]sidechaincompress=threshold=0.02:ratio=8:attack=20:release=400[a_bed]"
                 f";[a_dlg][a_bed]amix=inputs=2:duration=first:normalize=0{tail}[a_out]")
        rate = ["-ar", "48000"] if normalize_audio else []
        return ["-stream_loop", "-1", "-i", music_file], graph, ["-map", "[a_out]", *rate]

    if mode in ["quote", "clean"]:
        if not input_file:
            raise ValueError("Input file is required for quote and clean modes")

        filters = []

        if framing == "full_bleed":
            # Immersive 9:16 vertical crop with cinema zoom to eliminate hardcoded web/TV subtitles
            target_h = int(1920 * zoom)
            crop_expr = f"1080:1920:(in_w-1080)/2+({pan_x}):(in_h-1920)/2-({pan_y})"
            base_chain = f"[0:v]scale=-1:{target_h}:force_original_aspect_ratio=increase,crop={crop_expr}"
            if color_grade:
                filters.append(f"{base_chain},{grade_filter}[v1]")
            else:
                filters.append(f"{base_chain}[v1]")

        elif framing == "track":
            # Face-tracked crop: per-shot x offsets from reframe.py, quoted so its commas survive the filtergraph
            if not track_x:
                raise ValueError("track framing requires a track_x crop expression")
            base_chain = f"[0:v]scale=-2:1920,crop=1080:1920:x='{track_x}':y=0"
            if color_grade:
                filters.append(f"{base_chain},{grade_filter}[v1]")
            else:
                filters.append(f"{base_chain}[v1]")

        elif framing == "matte":
            # Authentic widescreen cinema box on pitch-black background (#000000)
            filters.append("color=c=black:s=1080x1920[bg]")
            if color_grade:
                filters.append(f"[0:v]scale=1080:-1,{grade_filter}[fg]")
            else:
                filters.append("[0:v]scale=1080:-1[fg]")
            filters.append("[bg][fg]overlay=(W-w)/2:(H-h)/2[v1]")

        elif framing == "blur":
            # Legacy blurred background
            filters.append("[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=25:5[bg]")
            if color_grade:
                filters.append(f"[0:v]scale=1080:-1,{grade_filter}[fg]")
            else:
                filters.append("[0:v]scale=1080:-1[fg]")
            filters.append("[bg][fg]overlay=(W-w)/2:(H-h)/2[v1]")

        else:
            raise ValueError(f"Unknown framing option: '{framing}'. Choose 'full_bleed', 'matte', 'blur', or 'track'")

        last_stream = "v1"

        # Punchline push-in: the last seconds slowly zoom 100% -> 100+amount%, eased (smoothstep),
        # toward the upper-middle where the tracked face sits. Applied before any text so captions
        # and the watermark stay still. The tail is upscaled 2x so zoompan's integer steps don't jitter.
        if punch_zoom_at is not None and float(punch_zoom_at) > 0:
            t0, secs = float(punch_zoom_at), float(punch_zoom_seconds)
            ease = f"min(1,it/{secs:g})"
            z = f"1+{float(punch_zoom_amount):g}*(3*pow({ease},2)-2*pow({ease},3))"
            filters.append(f"[{last_stream}]split[pz_a][pz_b]")
            filters.append(f"[pz_a]trim=end={t0:.3f},setpts=PTS-STARTPTS[pz_head]")
            filters.append(f"[pz_b]trim=start={t0:.3f},setpts=PTS-STARTPTS,scale=2160:3840,"
                           f"zoompan=z='{z}':x='iw/2-iw/zoom/2':y='(ih-ih/zoom)*0.4':d=1:s=1080x1920:fps={fps}[pz_tail]")
            filters.append("[pz_head][pz_tail]concat=n=2:v=1:a=0[v_pz]")
            last_stream = "v_pz"

        # Minimalist Film Header Tag (e.g., "WEDNESDAY (2022) | DIR. TIM BURTON")
        if header_text:
            safe_header = header_text.replace("'", "’").replace(":", "\\:")
            filters.append(
                f"[{last_stream}]drawtext=fontfile={font_bold}:text='{safe_header}':"
                f"fontcolor=white@0.9:fontsize=34:x=(w-text_w)/2:y=150:shadowcolor=black@0.7:shadowx=2:shadowy=2[v_hdr]"
            )
            last_stream = "v_hdr"

        # Discreet Watermark
        if watermark:
            safe_watermark = watermark.replace("'", "’").replace(":", "\\:")
            if watermark_align or watermark_y is not None:
                # Placement chosen by the user (Studio look settings)
                wx = {"left": "60", "right": "w-text_w-60"}.get(watermark_align, "(w-text_w)/2")
                wy = int(watermark_y) if watermark_y is not None else 100
                filters.append(
                    f"[{last_stream}]drawtext=fontfile={font_bold}:text='{safe_watermark}':"
                    f"fontcolor=white@0.7:fontsize=28:x={wx}:y={wy}:shadowcolor=black@0.6:shadowx=1:shadowy=1[v_wm]"
                )
            # If header is present, position watermark neatly at top-right
            elif header_text:
                filters.append(
                    f"[{last_stream}]drawtext=fontfile={font_bold}:text='{safe_watermark}':"
                    f"fontcolor=white@0.7:fontsize=28:x=w-text_w-60:y=80:shadowcolor=black@0.6:shadowx=1:shadowy=1[v_wm]"
                )
            else:
                filters.append(
                    f"[{last_stream}]drawtext=fontfile={font_bold}:text='{safe_watermark}':"
                    f"fontcolor=white@0.7:fontsize=28:x=(w-text_w)/2:y=100:shadowcolor=black@0.6:shadowx=1:shadowy=1[v_wm]"
                )
            last_stream = "v_wm"

        # Upper-third Hook Text (for Quote mode)
        if mode == "quote" and hook_text:
            safe_hook = hook_text.replace("'", "’").replace(":", "\\:")
            filters.append(
                f"[{last_stream}]drawtext=fontfile={font_bold}:text='{safe_hook}':"
                f"fontcolor=white@0.95:fontsize=32:x=(w-text_w)/2:y=280:shadowcolor=black@0.8:shadowx=2:shadowy=2[v_hook]"
            )
            last_stream = "v_hook"

        # Lower-third Quote Subtitles (if not using external subtitle file)
        if mode == "quote" and quote_text and not subtitle_file:
            safe_quote = quote_text.replace("'", "’").replace(":", "\\:")
            filters.append(
                f"[{last_stream}]drawtext=fontfile={font_bold}:text='\"{safe_quote}\"':"
                f"fontcolor=white@0.95:fontsize=34:x=(w-text_w)/2:y=1480:shadowcolor=black@0.8:shadowx=2:shadowy=2[v_quote]"
            )
            last_stream = "v_quote"

        # Subtitle file (.ass or .srt)
        if subtitle_file:
            clean_sub_path = subtitle_file.replace("\\", "/").replace(":", "\\:")
            filters.append(f"[{last_stream}]subtitles='{clean_sub_path}':fontsdir='assets/fonts'[v_sub]")
            last_stream = "v_sub"

        if speed != 1.0:
            # Last in the chain: captions and the crop expression run on the original timeline
            filters.append(f"[{last_stream}]setpts=PTS/{speed:g}[v_speed]")
            last_stream = "v_speed"
        music_inputs, audio_graph, audio_map = audio_section(1)
        filter_complex = ";".join(filters) + audio_graph

        cmd = [
            ffmpeg_bin,
            "-y",
            "-i", input_file,
            *music_inputs,
            "-filter_complex", filter_complex,
            "-map", f"[{last_stream}]",
            *audio_map,
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "19",
            "-c:a", "aac",
            "-b:a", "192k",
            output_file
        ]
        return cmd

    elif mode == "split":
        if not top_file or not bottom_file:
            raise ValueError("Both top_file and bottom_file are required for split mode")

        filters = []
        if color_grade:
            filters.append(f"[0:v]scale=1080:960:force_original_aspect_ratio=increase,crop=1080:960,{grade_filter}[v_top]")
            filters.append(f"[1:v]scale=1080:960:force_original_aspect_ratio=increase,crop=1080:960,{grade_filter}[v_bot]")
        else:
            filters.append("[0:v]scale=1080:960:force_original_aspect_ratio=increase,crop=1080:960[v_top]")
            filters.append("[1:v]scale=1080:960:force_original_aspect_ratio=increase,crop=1080:960[v_bot]")

        filters.append("[v_top][v_bot]vstack=inputs=2[v_stacked]")
        last_stream = "v_stacked"

        if watermark:
            safe_watermark = watermark.replace("'", "’").replace(":", "\\:")
            filters.append(
                f"[{last_stream}]drawtext=fontfile={font_bold}:text='{safe_watermark}':"
                f"fontcolor=white@0.75:fontsize=24:x=(w-text_w)/2:y=100:shadowcolor=black@0.6:shadowx=1:shadowy=1[v_wm]"
            )
            last_stream = "v_wm"

        if speed != 1.0:
            # Last in the chain: captions and the crop expression run on the original timeline
            filters.append(f"[{last_stream}]setpts=PTS/{speed:g}[v_speed]")
            last_stream = "v_speed"
        music_inputs, audio_graph, audio_map = audio_section(2)
        filter_complex = ";".join(filters) + audio_graph

        cmd = [
            ffmpeg_bin,
            "-y",
            "-i", top_file,
            "-i", bottom_file,
            *music_inputs,
            "-filter_complex", filter_complex,
            "-map", f"[{last_stream}]",
            *audio_map,
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "19",
            "-c:a", "aac",
            "-b:a", "192k",
            output_file
        ]
        return cmd

def convert_to_reel(**kwargs):
    """
    Renders to "<name>.part.mp4" and renames it into place only when FFmpeg succeeds, so an
    interrupted render (a closed session, a crash) never leaves a truncated, unplayable reel.
    """
    final = kwargs.get("output_file", "reel_output.mp4")
    stem, ext = os.path.splitext(final)
    partial = f"{stem}.part{ext or '.mp4'}"
    cmd = build_ffmpeg_command(**{**kwargs, "output_file": partial})
    print(f"[*] Executing FFmpeg command...")
    try:
        subprocess.run(cmd, check=True)
        os.replace(partial, final)
        print(f"[+] Reel successfully generated: {final}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"[-] FFmpeg error: {e}")
        if os.path.exists(partial):
            os.remove(partial)
        return False

def main():
    parser = argparse.ArgumentParser(description="Framefluence Multi-Mode Reel Generator")
    parser.add_argument("--mode", choices=["quote", "split", "clean"], default="quote", help="Rendering mode")
    parser.add_argument("--input", "-i", dest="input_file", help="Input video file (for quote/clean mode)")
    parser.add_argument("--top", dest="top_file", help="Top video file (for split mode)")
    parser.add_argument("--bottom", dest="bottom_file", help="Bottom video file (for split mode)")
    parser.add_argument("--output", "-o", dest="output_file", default="output/reel_output.mp4", help="Output file path")
    parser.add_argument("--watermark", default="@framefluence", help="Watermark text")
    parser.add_argument("--header", dest="header_text", help="Header text for top cinema tag (e.g. WEDNESDAY (2022) | DIR. TIM BURTON)")
    parser.add_argument("--hook-text", help="Top-third hook text (for quote mode)")
    parser.add_argument("--quote", dest="quote_text", help="Quote text for lower-third cinema subtitles")
    parser.add_argument("--subtitles", dest="subtitle_file", help="Path to custom subtitle (.srt/.ass) file")
    parser.add_argument("--framing", choices=["full_bleed", "matte", "blur", "track"], default="full_bleed", help="Framing aesthetic (track = face-tracked crop, needs opencv)")
    parser.add_argument("--no-color-grade", dest="color_grade", action="store_false", help="Disable cinema color grading")
    parser.add_argument("--pan-x", type=int, default=0, help="Horizontal crop offset in pixels")
    parser.add_argument("--pan-y", type=int, default=80, help="Vertical crop offset in pixels")
    parser.add_argument("--zoom", type=float, default=1.125, help="Cinema zoom factor for full_bleed framing")
    parser.add_argument("--watermark-align", choices=["left", "center", "right"], help="Watermark horizontal placement")
    parser.add_argument("--watermark-y", type=int, help="Watermark top edge in px (0-1920)")
    parser.add_argument("--speed", type=float, default=1.1, help="Playback speed, 0.5-2.0 (default 1.1; 1 = original); pitch is preserved")
    parser.add_argument("--punch-zoom-at", type=float, help="Start a 2s 100->108%% push-in at this time (seconds)")
    parser.add_argument("--fps", default="30", help="Source frame rate for the zoom, e.g. 24000/1001")
    parser.add_argument("--music", dest="music_file", help="Licensed/royalty-free track to mix under the dialogue")
    parser.add_argument("--music-db", type=float, default=-28.0, help="Music bed level in dB (default -28)")
    parser.add_argument("--no-loudnorm", dest="normalize_audio", action="store_false",
                        help="Keep the original audio level (default: normalise to -14 LUFS)")

    args = parser.parse_args()

    out_dir = os.path.dirname(args.output_file)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    track_x = None
    if args.framing == "track":
        from framefluence.reframe import build_track_expression
        track_x = build_track_expression(args.input_file)

    convert_to_reel(
        mode=args.mode,
        input_file=args.input_file,
        top_file=args.top_file,
        bottom_file=args.bottom_file,
        output_file=args.output_file,
        watermark=args.watermark,
        header_text=args.header_text,
        hook_text=args.hook_text,
        quote_text=args.quote_text,
        subtitle_file=args.subtitle_file,
        framing=args.framing,
        color_grade=args.color_grade,
        pan_x=args.pan_x,
        pan_y=args.pan_y,
        zoom=args.zoom,
        track_x=track_x,
        watermark_align=args.watermark_align,
        watermark_y=args.watermark_y,
        normalize_audio=args.normalize_audio,
        speed=args.speed,
        punch_zoom_at=args.punch_zoom_at,
        fps=args.fps,
        music_file=args.music_file,
        music_db=args.music_db
    )

if __name__ == "__main__":
    main()
