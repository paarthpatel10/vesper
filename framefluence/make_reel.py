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
    track_x=None  # crop x expression for "track" framing (see reframe.py)
):
    if mode not in ["quote", "split", "clean"]:
        raise ValueError(f"Invalid mode: '{mode}'. Supported modes are: quote, split, clean")

    ffmpeg_bin = "ffmpeg"
    font_bold = get_font_file(MONTSERRAT_BOLD)

    # Cinema color grading filter string
    grade_filter = "unsharp=lx=5:ly=5:la=1.2:cx=5:cy=5:ca=0.0,eq=contrast=1.12:brightness=-0.02:saturation=1.15"

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
            # If header is present, position watermark neatly at top-right
            if header_text:
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

        filter_complex = ";".join(filters)

        cmd = [
            ffmpeg_bin,
            "-y",
            "-i", input_file,
            "-filter_complex", filter_complex,
            "-map", f"[{last_stream}]",
            "-map", "0:a?",
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

        filter_complex = ";".join(filters)

        cmd = [
            ffmpeg_bin,
            "-y",
            "-i", top_file,
            "-i", bottom_file,
            "-filter_complex", filter_complex,
            "-map", f"[{last_stream}]",
            "-map", "0:a?",
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "19",
            "-c:a", "aac",
            "-b:a", "192k",
            output_file
        ]
        return cmd

def convert_to_reel(**kwargs):
    cmd = build_ffmpeg_command(**kwargs)
    print(f"[*] Executing FFmpeg command...")
    try:
        subprocess.run(cmd, check=True)
        print(f"[+] Reel successfully generated: {kwargs.get('output_file', 'output.mp4')}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"[-] FFmpeg error: {e}")
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
        track_x=track_x
    )

if __name__ == "__main__":
    main()
