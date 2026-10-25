import unittest
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from framefluence.subtitle_engine import generate_srt, generate_ass_subtitles, split_quote_into_timed_chunks

class TestSubtitleEngine(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_split_quote_into_timed_chunks(self):
        quote = "The problem is nobody can control the dream they have"
        chunks = split_quote_into_timed_chunks(quote, total_duration=8.0)
        self.assertTrue(len(chunks) >= 2)
        self.assertEqual(chunks[0]["start"], 0.0)
        self.assertAlmostEqual(chunks[-1]["end"], 8.0, delta=0.5)
        self.assertIn("The problem is", chunks[0]["text"])

    def test_generate_srt_file(self):
        chunks = [
            {"start": 0.0, "end": 2.5, "text": "In my dreams,"},
            {"start": 2.5, "end": 5.0, "text": "we are always together."}
        ]
        out_srt = os.path.join(self.temp_dir.name, "test.srt")
        generate_srt(chunks, out_srt)

        self.assertTrue(os.path.exists(out_srt))
        with open(out_srt, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("00:00:00,000 --> 00:00:02,500", content)
        self.assertIn("In my dreams,", content)

    def test_generate_ass_file_has_cinema_styling(self):
        chunks = [
            {"start": 0.0, "end": 3.0, "text": "Why so serious?"}
        ]
        out_ass = os.path.join(self.temp_dir.name, "test.ass")
        generate_ass_subtitles(chunks, out_ass)

        self.assertTrue(os.path.exists(out_ass))
        with open(out_ass, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("[Script Info]", content)
        self.assertIn("[V4+ Styles]", content)
        self.assertIn("Why so serious?", content)
        self.assertIn("Montserrat", content)

    def test_generate_karaoke_highlighted_ass(self):
        chunks = [
            {"start": 0.0, "end": 2.0, "text": "Emphasis on dead.", "highlight_word": "dead."}
        ]
        out_ass = os.path.join(self.temp_dir.name, "test_karaoke.ass")
        generate_ass_subtitles(chunks, out_ass, highlight_color="&H0018C5F5")

        self.assertTrue(os.path.exists(out_ass))
        with open(out_ass, "r", encoding="utf-8") as f:
            content = f.read()
        # Should contain color override tag for the highlighted word
        self.assertIn(r"\c&H0018C5F5&", content)
        self.assertIn("dead.", content)

if __name__ == "__main__":
    unittest.main()
