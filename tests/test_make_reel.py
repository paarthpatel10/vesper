import unittest
import os
import sys

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from framefluence.make_reel import build_ffmpeg_command

class TestMakeReel(unittest.TestCase):
    def test_quote_mode_command_structure(self):
        cmd = build_ffmpeg_command(
            mode="quote",
            input_file="input.mp4",
            output_file="output.mp4",
            watermark="@framefluence",
            hook_text="Did you notice this detail?"
        )
        cmd_str = " ".join(cmd)
        self.assertIn("ffmpeg", cmd_str)
        self.assertIn("-i input.mp4", cmd_str)
        self.assertIn("1080:1920", cmd_str)
        self.assertIn("crop=1080:1920", cmd_str)
        self.assertIn("@framefluence", cmd_str)
        self.assertIn("Did you notice this detail?", cmd_str)
        self.assertIn("output.mp4", cmd_str)

    def test_split_mode_command_structure(self):
        cmd = build_ffmpeg_command(
            mode="split",
            top_file="top.mp4",
            bottom_file="bottom.mp4",
            output_file="split_output.mp4",
            watermark="@framefluence"
        )
        cmd_str = " ".join(cmd)
        self.assertIn("ffmpeg", cmd_str)
        self.assertIn("-i top.mp4", cmd_str)
        self.assertIn("-i bottom.mp4", cmd_str)
        self.assertIn("1080:960", cmd_str) # Each video scaled to half of 1920
        self.assertIn("split_output.mp4", cmd_str)

    def test_clean_mode_command_structure(self):
        cmd = build_ffmpeg_command(
            mode="clean",
            input_file="input.mp4",
            output_file="clean_output.mp4",
            watermark="@framefluence"
        )
        cmd_str = " ".join(cmd)
        self.assertIn("ffmpeg", cmd_str)
        self.assertIn("-i input.mp4", cmd_str)
        self.assertIn("crop=1080:1920", cmd_str)
        self.assertIn("@framefluence", cmd_str)
        self.assertIn("clean_output.mp4", cmd_str)

    def test_blur_framing(self):
        cmd = build_ffmpeg_command(
            mode="quote",
            input_file="input.mp4",
            output_file="blur_output.mp4",
            framing="blur"
        )
        cmd_str = " ".join(cmd)
        self.assertIn("boxblur", cmd_str)

    def test_invalid_mode_raises_value_error(self):
        with self.assertRaises(ValueError):
            build_ffmpeg_command(
                mode="unsupported_mode",
                input_file="input.mp4",
                output_file="output.mp4"
            )

    def test_quote_with_subtitle_file_filter(self):
        cmd = build_ffmpeg_command(
            mode="quote",
            input_file="input.mp4",
            output_file="output.mp4",
            subtitle_file="subs.ass"
        )
        cmd_str = " ".join(cmd)
        self.assertIn("subtitles=", cmd_str)

    def test_full_bleed_framing_default(self):
        cmd = build_ffmpeg_command(
            mode="quote",
            input_file="input.mp4",
            output_file="output.mp4",
            framing="full_bleed"
        )
        cmd_str = " ".join(cmd)
        # full_bleed should NOT have boxblur
        self.assertNotIn("boxblur", cmd_str)
        # full_bleed should crop to 1080:1920
        self.assertIn("crop=1080:1920", cmd_str)

    def test_matte_framing(self):
        cmd = build_ffmpeg_command(
            mode="quote",
            input_file="input.mp4",
            output_file="output.mp4",
            framing="matte"
        )
        cmd_str = " ".join(cmd)
        self.assertNotIn("boxblur", cmd_str)
        self.assertIn("color=c=black:s=1080x1920", cmd_str)

    def test_cinema_color_grade(self):
        cmd = build_ffmpeg_command(
            mode="quote",
            input_file="input.mp4",
            output_file="output.mp4",
            color_grade=True
        )
        cmd_str = " ".join(cmd)
        self.assertIn("unsharp=", cmd_str)
        self.assertIn("eq=contrast=", cmd_str)

    def test_minimalist_header_tag(self):
        cmd = build_ffmpeg_command(
            mode="quote",
            input_file="input.mp4",
            output_file="output.mp4",
            header_text="WEDNESDAY (2022) | DIR. TIM BURTON"
        )
        cmd_str = " ".join(cmd)
        self.assertIn("WEDNESDAY (2022) | DIR. TIM BURTON", cmd_str)
        self.assertIn("Montserrat", cmd_str)

    def test_audio_is_loudness_normalised_by_default(self):
        cmd = " ".join(build_ffmpeg_command(mode="quote", input_file="in.mp4", output_file="out.mp4"))
        self.assertIn("-af loudnorm=I=-14:TP=-1.5:LRA=11 -ar 48000", cmd)
        cmd = " ".join(build_ffmpeg_command(mode="split", top_file="a.mp4", bottom_file="b.mp4"))
        self.assertIn("loudnorm=I=-14", cmd)
        cmd = " ".join(build_ffmpeg_command(mode="quote", input_file="in.mp4", normalize_audio=False))
        self.assertNotIn("loudnorm", cmd)

    def test_gentle_colour_grade(self):
        cmd = " ".join(build_ffmpeg_command(mode="quote", input_file="in.mp4"))
        self.assertIn("eq=contrast=1.06:brightness=0.01:saturation=1.12", cmd)

    def test_playback_speed_is_applied_last_and_keeps_pitch(self):
        cmd = build_ffmpeg_command(mode="quote", input_file="in.mp4", subtitle_file="s.ass", speed=1.1)
        graph = cmd[cmd.index("-filter_complex") + 1]
        self.assertTrue(graph.endswith("setpts=PTS/1.1[v_speed]"))  # after captions, so they stay in sync
        self.assertIn("[v_speed]", cmd)
        self.assertIn("atempo=1.1,loudnorm=I=-14", " ".join(cmd))    # tempo change without pitch change
        split = " ".join(build_ffmpeg_command(mode="split", top_file="a.mp4", bottom_file="b.mp4", speed=1.1))
        self.assertIn("setpts=PTS/1.1", split)

    def test_normal_speed_adds_nothing(self):
        cmd = " ".join(build_ffmpeg_command(mode="quote", input_file="in.mp4"))
        self.assertNotIn("setpts", cmd)
        self.assertNotIn("atempo", cmd)

    def test_speed_out_of_range_is_rejected(self):
        with self.assertRaises(ValueError):
            build_ffmpeg_command(mode="quote", input_file="in.mp4", speed=3)

    def test_punchline_zoom_runs_before_captions(self):
        cmd = build_ffmpeg_command(mode="quote", input_file="in.mp4", subtitle_file="s.ass",
                                   punch_zoom_at=30.0, fps="24000/1001")
        graph = cmd[cmd.index("-filter_complex") + 1]
        self.assertIn("[pz_a]trim=end=30.000", graph)
        self.assertIn("zoompan=z='1+0.08*", graph)
        self.assertIn("fps=24000/1001", graph)
        self.assertLess(graph.index("concat=n=2"), graph.index("subtitles="))  # captions don't zoom

    def test_music_bed_is_ducked_under_dialogue(self):
        cmd = build_ffmpeg_command(mode="quote", input_file="in.mp4", music_file="bed.mp3", speed=1.1)
        joined = " ".join(cmd)
        self.assertIn("-stream_loop -1 -i bed.mp3", joined)
        graph = cmd[cmd.index("-filter_complex") + 1]
        self.assertIn("[1:a]volume=-28dB", graph)
        self.assertIn("sidechaincompress", graph)
        self.assertIn("amix=inputs=2:duration=first:normalize=0,atempo=1.1,loudnorm", graph)
        self.assertIn("[a_out]", cmd)
        self.assertNotIn("-af", cmd)  # audio is filtered inside the graph instead

    def test_subtle_sharpening(self):
        self.assertIn("unsharp=3:3:0.5,eq=", " ".join(build_ffmpeg_command(mode="quote", input_file="in.mp4")))


if __name__ == "__main__":
    unittest.main()
