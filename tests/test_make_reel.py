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


if __name__ == "__main__":
    unittest.main()
