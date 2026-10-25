import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from framefluence.script_clips import clip_meta, episode_file, find_phrase, locate_clip, parse_guide, snap_to_shots

GUIDE = """# Friends Season 8 (Episodes 1-5): Shorts

## Episode 3: The One Where Rachel Tells... (Season 8, Episode 3)

### Clip 3.5: "Condoms Only Work 97% of the Time?"
* **Estimated Duration:** ~48 seconds
* **Why the Hook Works:** Ross's meltdown over the 97% condom rate.
* **0:00 Teaser Hook (Optional 1.5s Pre-Roll):** `Ross: "Well they should put that on the box!!!"`
* **START DIALOGUE (Cut In):** `We used a condom.`
* **END DIALOGUE (Cut Out):** `Yeah I'll press 1!`

> **Ross:** We used a condom.
> **Rachel:** I know, but y'know condoms only work like 97% of the time.
> **Ross and Rachel:** Shh!
> **Ross:** Yeah I'll press 1!
"""


def words_from(text, start=0.0, step=0.5):
    return [{"word": w, "start": start + i * step, "end": start + i * step + 0.4} for i, w in enumerate(text.split())]


class TestScriptClips(unittest.TestCase):
    def test_parse_guide(self):
        show, clips = parse_guide(GUIDE)
        self.assertEqual(show, "Friends")
        c = clips[0]
        self.assertEqual((c["id"], c["season"], c["episode"], c["estimate"]), ("3.5", 8, 3, 48))
        self.assertEqual(c["start_line"], "We used a condom.")
        self.assertEqual(c["end_line"], "Yeah I'll press 1!")
        self.assertEqual(c["dialogue"][2], ("Ross and Rachel", "Shh!"))

    def test_find_phrase_tolerates_wording_differences(self):
        words = words_from("so anyway we used a condom I know but you know condoms only work like 97 percent")
        t, score = find_phrase(words, ["we", "used", "a", "condom"], anchor="start")
        self.assertEqual(t, 1.0)
        self.assertGreater(score, 0.9)
        t, score = find_phrase(words, ["yknow", "condoms", "only", "work"], anchor="end")
        self.assertAlmostEqual(t, 6.9)  # "work" (word 13) ends; "y'know" vs "you know" still matches

    def test_locate_clip_uses_closing_lines_for_the_end(self):
        _, clips = parse_guide(GUIDE)
        transcript = ("hey there everyone " + "filler " * 20 +
                      "we used a condom I know but you know condoms only work like 97 % of the time " +
                      "shh yeah I'll press one " + "later scene words " * 10)
        start, end, s_score, e_score = locate_clip(clips[0], words_from(transcript))
        self.assertEqual(start, 11.5)                    # "we" is word 23
        self.assertAlmostEqual(end, 22.9, places=3)  # "one" (word 45) ends the clip although the guide says "1"

    def test_repeated_start_line_picks_the_one_followed_by_the_ending(self):
        _, clips = parse_guide(GUIDE)
        # The opening line is said twice; only the second is followed by the clip's real ending
        transcript = ("we used a condom " + "unrelated talk " * 40 +
                      "we used a condom I know but you know condoms only work like 97 % of the time "
                      "shh yeah I'll press one " + "later words " * 5)
        start, end, _, _ = locate_clip(clips[0], words_from(transcript), max_len=30)
        self.assertEqual(start, 42.0)  # second "we" (word 84), not the first at 0.0

    def test_snap_to_shots(self):
        words = words_from("a b c d e", start=10.0)
        start, end = snap_to_shots(10.0, 12.4, [(0, 9.3), (9.3, 12.6), (12.6, 20)], words)
        self.assertEqual((start, end), (9.3, 12.6))       # cut-in at the shot change, cut-out at the next
        start, end = snap_to_shots(10.0, 12.4, [(0, 5.0)], words)
        self.assertEqual(start, 9.75)                      # no nearby cut: a small lead-in instead
        self.assertEqual(end, 13.2)                        # no nearby cut: a short tail after the line
        busy = words_from("a b c d e f g h", start=10.0)    # next word starts at 12.5
        self.assertEqual(snap_to_shots(10.0, 12.4, [(0, 9.3), (9.3, 12.6)], busy)[1], 12.4)  # never cuts into it

    def test_episode_file_matches_release_names(self):
        folder = tempfile.mkdtemp()
        try:
            for name in ("Friends.S08E02.720p.BluRay.mkv", "Friends_S08E01_The_One.mkv", "notes.md"):
                open(os.path.join(folder, name), "w").close()
            self.assertTrue(episode_file(8, 2, folder).endswith("Friends.S08E02.720p.BluRay.mkv"))
            self.assertTrue(episode_file(8, 1, folder).endswith("Friends_S08E01_The_One.mkv"))
            self.assertIsNone(episode_file(8, 5, folder))
        finally:
            for f in os.listdir(folder):
                os.remove(os.path.join(folder, f))
            os.rmdir(folder)

    def test_clip_meta(self):
        show, clips = parse_guide(GUIDE)
        meta = clip_meta(show, clips[0])
        self.assertEqual(meta["header"], "FRIENDS | S08E03")
        self.assertEqual(meta["hook"], '"Condoms Only Work 97% of the Time?"')
        self.assertIn("#rossgeller #rachelgreen", meta["hashtags"])
        self.assertTrue(meta["hashtags"].startswith("#friends #friendstvshow"))


if __name__ == "__main__":
    unittest.main()
