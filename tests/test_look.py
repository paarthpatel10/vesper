import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from framefluence.auto_subtitles import FONTS, build_caption_events, caption_style_line, resolve_look
from framefluence.look import full_look, resolve_watermark, sanitize
from framefluence.make_reel import build_ffmpeg_command
from framefluence.paths import FONTS as FONT_DIR

WORDS = [{"word": "we", "start": 0.0, "end": 0.2}, {"word": "were", "start": 0.3, "end": 0.5},
         {"word": "on", "start": 0.6, "end": 0.8}]


class TestLook(unittest.TestCase):
    def test_every_registered_font_file_is_present(self):
        for key, font in FONTS.items():
            self.assertTrue(os.path.isfile(os.path.join(FONT_DIR, font["file"])), key)

    def test_sanitize_drops_unknown_values_and_clamps_positions(self):
        clean = sanitize({"caption_font": "comic-sans", "caption_style": "karaoke", "caption_color": "cyan",
                          "caption_position": 5, "watermark_position": -1, "watermark_align": "middle",
                          "show_watermark": 0, "evil": "x"})
        self.assertEqual(clean, {"caption_style": "karaoke", "caption_color": "cyan", "caption_position": 0.95,
                                 "watermark_position": 0.0, "show_watermark": False})

    def test_style_line_uses_font_family_size_and_position(self):
        line = caption_style_line(resolve_look({"caption_font": "bebas", "caption_size": "l", "caption_position": 0.5}))
        # Bebas Neue, 96 * 1.3 * 1.2 = 150, baseline at half height -> margin 960
        self.assertTrue(line.startswith("Style: Caption,Bebas Neue,150,"))
        self.assertTrue(line.endswith(",2,70,70,960,1"))

    def test_boxed_style_draws_an_opaque_box(self):
        line = caption_style_line(resolve_look({"caption_style": "boxed"}))
        self.assertIn(",3,14,0,2,", line)  # BorderStyle 3, padding 14, no shadow, bottom-centre

    def test_karaoke_keeps_spoken_words_coloured(self):
        events = build_caption_events(WORDS, style="karaoke", color="green")
        self.assertEqual([e[3].count("84DC3D") for e in events], [1, 2, 3])

    def test_minimal_has_no_highlight(self):
        events = build_caption_events(WORDS, style="minimal", color="red")
        self.assertTrue(all("303BFF" not in e[3] for e in events))

    def test_watermark_placement(self):
        self.assertEqual(resolve_watermark({}), ("@framefluence", None, None))  # legacy drafts: automatic
        self.assertEqual(resolve_watermark({"watermark_align": "right", "watermark_position": 0.9}),
                         ("@framefluence", "right", 1728))
        self.assertEqual(resolve_watermark({"show_watermark": False}), (None, None, None))
        cmd = " ".join(build_ffmpeg_command(mode="quote", input_file="in.mp4", watermark="@framefluence",
                                            watermark_align="left", watermark_y=1700))
        self.assertIn("x=60:y=1700", cmd)

    def test_full_look_fills_defaults(self):
        look = full_look({"caption_font": "anton"})
        self.assertEqual((look["caption_font"], look["caption_style"], look["watermark_align"]),
                         ("anton", "bold", "center"))


if __name__ == "__main__":
    unittest.main()
