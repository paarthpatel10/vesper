import datetime
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from framefluence.autopilot import relative_scenes, slugify
from framefluence.auto_subtitles import (align_reference, build_caption_events, group_words, parse_srt_words, payoff_line,
                            shift_words, words_to_karaoke_chunks, wrap_hook)
from framefluence.make_reel import build_ffmpeg_command
from framefluence.reframe import crop_x_expression, shot_centers
from framefluence.scene_cut import choose_segment, choose_story_segment, speech_breaks
from framefluence.tmdb_calendar import person_to_milestone
from framefluence.trend_agent import get_upcoming_milestones, next_birthday

CSV = os.path.join(os.path.dirname(__file__), "..", "data", "top_50_actors_calendar.csv")


class TestChooseSegment(unittest.TestCase):
    def test_short_clip_kept_whole(self):
        self.assertEqual(choose_segment([(0, 10), (10, 30)], 30.0), (0.0, 30.0))

    def test_picks_longest_run_of_whole_shots_within_limit(self):
        scenes = [(0, 25), (25, 50), (50, 70), (70, 75), (75, 140)]
        # 0-50 and 25-75 are both 50s (the max that fits under 60s); ties go to the earliest
        self.assertEqual(choose_segment(scenes, 140.0), (0, 50))

    def test_single_long_take_falls_back_to_first_max_len(self):
        self.assertEqual(choose_segment([(0, 300)], 300.0), (0.0, 60.0))

    def test_relative_scenes_shift_and_clip(self):
        self.assertEqual(relative_scenes([(0, 25), (25, 50), (50, 70)], 25, 60), [(0, 25), (25, 35)])


class TestStoryPicker(unittest.TestCase):
    @staticmethod
    def talk(start, end, step=1.0):
        """One word per `step` seconds between start and end."""
        words, t = [], start
        while t < end:
            words.append({"word": "line", "start": t, "end": t + step * 0.8})
            t += step
        return words

    def test_speech_breaks_need_pause_on_a_shot_cut(self):
        words = [{"word": "a", "start": 0, "end": 1}, {"word": "b", "start": 3, "end": 4},
                 {"word": "c", "start": 6, "end": 7}]
        self.assertEqual(speech_breaks(words, [(0, 2.2), (2.2, 10)]), [(2.2, 2)])

    def test_picks_beat_with_laughs_and_skips_transition(self):
        # Scene A 0-70s with no laughs; 20s theme gap; scene B 90-170s with laugh bursts in pauses
        words = self.talk(0, 70) + self.talk(90, 170, step=2.0)
        shots = [(0, 35), (35, 70.5), (70.5, 89.5), (89.5, 130), (130, 170.5), (170.5, 180)]
        energy = [100.0] * int(180 / 0.25)
        for t in range(90, 170, 2):  # laughter fills each 1.2s pause in scene B
            for i in range(int((t + 1.7) / 0.25), int((t + 2.0) / 0.25)):
                energy[i] = 2000.0
        start, end = choose_story_segment(words, shots, energy, 180.0, min_len=40, max_len=100)
        self.assertGreaterEqual(start, 89.5)
        self.assertLessEqual(end, 180.0)

    def test_no_transcript_returns_none(self):
        self.assertIsNone(choose_story_segment([], [(0, 10)], [1.0], 10.0))

    def test_shift_words_retimes_to_cut(self):
        words = [{"word": "a", "start": 5, "end": 6}, {"word": "b", "start": 12, "end": 13},
                 {"word": "c", "start": 19.5, "end": 21}]
        self.assertEqual(shift_words(words, 10, 20), [{"word": "b", "start": 2, "end": 3},
                                                      {"word": "c", "start": 9.5, "end": 10}])


class TestAutoSubtitles(unittest.TestCase):
    WORDS = [
        {"word": "knock", "start": 0.0, "end": 0.3},
        {"word": "knock", "start": 0.4, "end": 0.7},
        {"word": "knock", "start": 0.8, "end": 1.1},
        {"word": "Penny.", "start": 1.3, "end": 1.8},
        {"word": "Bazinga!", "start": 3.0, "end": 3.6},
    ]

    def test_groups_break_on_size_and_sentence_end(self):
        groups = group_words(self.WORDS, max_words=3)
        self.assertEqual([len(g) for g in groups], [3, 1, 1])

    def test_repeated_words_highlight_one_at_a_time(self):
        chunks = words_to_karaoke_chunks(self.WORDS)
        self.assertEqual(len(chunks), 5)
        for i in range(3):
            self.assertEqual(chunks[i]["text"].count("D7FF"), 1)
        second = chunks[1]["text"]
        self.assertTrue(second.startswith("knock {\\c&H0000D7FF&}knock"))

    def test_parse_srt_words_strips_labels_and_sound_cues(self):
        srt = ("1\n00:00:10,000 --> 00:00:12,000\nPHOEBE: It's <i>negative</i>.\n\n"
               "2\n00:00:13,000 --> 00:00:14,000\n[BIG BAND MUSIC PLAYING]\n\n"
               "3\n00:00:15,000 --> 00:00:16,000\n- What?\n- Yeah.\n")
        words = parse_srt_words(srt)
        self.assertEqual([w["word"] for w in words], ["It's", "negative.", "What?", "Yeah."])
        self.assertEqual((words[0]["start"], words[1]["end"]), (10.0, 12.0))

    def test_align_reference_keeps_official_text_with_whisper_timing(self):
        reference = [{"word": w, "start": 10.0 + i, "end": 10.5 + i}
                     for i, w in enumerate(["Go", "ahead,", "Rach.", "It's", "negative."])]
        asr = [{"word": "Go", "start": 2.0, "end": 2.2}, {"word": "ahead", "start": 2.3, "end": 2.5},
               {"word": "reach", "start": 2.6, "end": 3.0}, {"word": "It's", "start": 3.4, "end": 3.6},
               {"word": "negative", "start": 3.7, "end": 4.2}]
        out = align_reference(reference, asr)
        self.assertEqual([w["word"] for w in out], ["Go", "ahead,", "Rach.", "It's", "negative."])
        self.assertEqual((out[0]["start"], out[4]["end"]), (2.0, 4.2))
        # "Rach." was misheard as "reach": it is placed in the gap between its matched neighbours
        self.assertEqual((out[2]["start"], out[2]["end"]), (2.5, 3.4))

    def test_align_reference_without_asr_returns_reference(self):
        ref = [{"word": "Hi", "start": 1.0, "end": 1.5}]
        self.assertEqual(align_reference(ref, []), ref)

    def test_wrap_hook_balances_lines(self):
        self.assertEqual(wrap_hook("Ross used the kids to impress a girl... it backfired"),
                         r"Ross used the kids\Nto impress a girl...\Nit backfired")
        self.assertEqual(wrap_hook("Short hook"), "Short hook")

    def test_payoff_line_is_last_sentence(self):
        words = [{"word": w, "start": 0, "end": 0} for w in "Okay. Maybe I should stand on your feet!".split()]
        self.assertEqual(payoff_line(words), "Maybe I should stand on your feet!")

    def test_bold_captions_are_uppercase_with_one_gold_word(self):
        events = build_caption_events(self.WORDS[:3], style="bold")
        self.assertTrue(all(e[3].count("D7FF") == 1 and "KNOCK" in e[3] for e in events))
        self.assertIn(r"\t(0,90,", events[0][3])  # first word of a phrase pops in
        self.assertNotIn(r"\t(", events[1][3])

    def test_events_hold_until_next_word(self):
        chunks = words_to_karaoke_chunks(self.WORDS)
        self.assertEqual(chunks[0]["end"], 0.4)
        self.assertEqual(chunks[2]["end"], 1.1)


class TestReframe(unittest.TestCase):
    def test_shot_centers_use_median_and_carry_forward(self):
        samples = [(0.5, 0.2), (1.0, 0.3), (1.5, 0.25), (2.5, None), (3.5, 0.8)]
        self.assertEqual(shot_centers(samples, [(0, 2), (2, 3), (3, 4)]), [0.25, 0.25, 0.8])

    def test_expression_switches_per_shot_and_clamps(self):
        # 1920x1080 scaled to 1920 high -> 3413px wide; max x = 2333
        expr = crop_x_expression([(0, 2), (2, 4)], [0.0, 1.0], 1920, 1080)
        self.assertEqual(expr, "if(lt(t,2.000),0,2333)")

    def test_track_framing_command(self):
        cmd = build_ffmpeg_command(mode="quote", input_file="in.mp4", output_file="out.mp4",
                                   framing="track", track_x="if(lt(t,2.000),0,2333)")
        joined = " ".join(cmd)
        self.assertIn("scale=-2:1920,crop=1080:1920:x='if(lt(t,2.000),0,2333)':y=0", joined)

    def test_track_framing_requires_expression(self):
        with self.assertRaises(ValueError):
            build_ffmpeg_command(mode="quote", input_file="in.mp4", framing="track")


class TestLiveCalendar(unittest.TestCase):
    def test_countdown_is_computed_from_today_not_csv(self):
        # Christoph Waltz: October 04, 1956
        milestones = get_upcoming_milestones(CSV, days_threshold=3, today=datetime.date(2027, 10, 2))
        waltz = [m for m in milestones if m["actor_name"] == "Christoph Waltz"]
        self.assertEqual(len(waltz), 1)
        self.assertEqual(waltz[0]["days_left"], 2)
        self.assertEqual(waltz[0]["age_turning"], 71)

    def test_next_birthday_wraps_year(self):
        self.assertEqual(next_birthday(1, 3, datetime.date(2026, 12, 30)), datetime.date(2027, 1, 3))

    def test_tmdb_person_to_milestone(self):
        person = {"name": "Test Actor", "birthday": "1990-10-20",
                  "known_for": [{"title": "Film A"}, {"name": "Show B"}]}
        m = person_to_milestone(person, datetime.date(2026, 10, 11), days_threshold=30)
        self.assertEqual((m["days_left"], m["age_turning"], m["roles"]), (9, 36, "Film A, Show B"))
        self.assertIsNone(person_to_milestone({**person, "deathday": "2020-01-01"}, datetime.date(2026, 10, 11), 30))

    def test_slugify(self):
        self.assertEqual(slugify("Sheldon's Spot! (S01E02)"), "sheldon_s_spot_s01e02")


if __name__ == "__main__":
    unittest.main()
