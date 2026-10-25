"""
Framefluence - Subtitle & Cinema Typography Engine
Generates styled .srt and .ass subtitles for vertical reels.
"""

import math
import os

def format_timestamp_srt(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds - int(seconds)) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

def format_timestamp_ass(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    centis = int((seconds - int(seconds)) * 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{centis:02d}"

def split_quote_into_timed_chunks(quote_text, total_duration=10.0, words_per_chunk=4):
    words = quote_text.strip().split()
    if not words:
        return []

    # Group into chunks
    chunks_text = []
    for i in range(0, len(words), words_per_chunk):
        chunks_text.append(" ".join(words[i:i + words_per_chunk]))

    num_chunks = len(chunks_text)
    time_per_chunk = total_duration / max(num_chunks, 1)

    timed_chunks = []
    for idx, text in enumerate(chunks_text):
        start = idx * time_per_chunk
        end = min((idx + 1) * time_per_chunk, total_duration)
        timed_chunks.append({
            "start": round(start, 2),
            "end": round(end, 2),
            "text": text
        })

    return timed_chunks

def generate_srt(chunks, output_path):
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for idx, chunk in enumerate(chunks, 1):
            start_str = format_timestamp_srt(chunk["start"])
            end_str = format_timestamp_srt(chunk["end"])
            f.write(f"{idx}\n{start_str} --> {end_str}\n{chunk['text']}\n\n")
    return output_path

def generate_ass_subtitles(
    chunks,
    output_path,
    font_name="Montserrat-Bold",
    font_size=32,
    primary_color="&H00FFFFFF",  # Crisp Cinema White (&HAABBGGRR)
    outline_color="&H00000000",  # Sharp Black Stroke
    back_color="&H80000000",
    margin_v=240,
    highlight_color=None
):
    """
    Generates Advanced SubStation Alpha (.ass) subtitle file with cinema styling
    and karaoke word highlighting.
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    header = f"""[Script Info]
Title: Framefluence Cinema Subtitles
ScriptType: v4.00+
WrapStyle: 0
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{font_size},{primary_color},&H000000FF,{outline_color},{back_color},-1,0,0,0,100,100,1,0,1,3,2,2,60,60,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    events = []
    for chunk in chunks:
        start_str = format_timestamp_ass(chunk["start"])
        end_str = format_timestamp_ass(chunk["end"])
        text = chunk["text"]
        if highlight_color and chunk.get("highlight_word"):
            hw = chunk["highlight_word"]
            if hw in text:
                text = text.replace(hw, f"{{\\c{highlight_color}&}}{hw}{{\\c{primary_color}&}}")
        events.append(f"Dialogue: 0,{start_str},{end_str},Default,,0,0,0,,{text}")

    content = header + "\n".join(events) + "\n"

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)

    return output_path
