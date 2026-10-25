import unittest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from framefluence.trend_agent import (
    get_upcoming_milestones,
    get_breaking_trailers,
    get_peer_trends,
    generate_content_package
)

class TestTrendAgent(unittest.TestCase):
    def test_get_upcoming_milestones_from_calendar(self):
        csv_path = os.path.join(os.path.dirname(__file__), "..", "data", "top_50_actors_calendar.csv")
        self.assertTrue(os.path.exists(csv_path), "top_50_actors_calendar.csv should exist")

        milestones = get_upcoming_milestones(csv_path, days_threshold=45)
        self.assertTrue(len(milestones) >= 1)
        first = milestones[0]
        self.assertIn("actor_name", first)
        self.assertIn("days_left", first)
        self.assertIn("age_turning", first)
        self.assertIn("hook", first)

    def test_get_breaking_trailers_returns_list(self):
        # Even if offline, should return structured list (with fallback data if network unavailable)
        trailers = get_breaking_trailers(max_items=3)
        self.assertIsInstance(trailers, list)
        self.assertTrue(len(trailers) >= 1)
        self.assertIn("title", trailers[0])
        self.assertIn("hype_angle", trailers[0])

    def test_get_peer_trends_from_benchmarks(self):
        csv_path = os.path.join(os.path.dirname(__file__), "..", "data", "cinema_competitors_and_benchmarks.csv")
        self.assertTrue(os.path.exists(csv_path), "cinema_competitors_and_benchmarks.csv should exist")

        trends = get_peer_trends(csv_path)
        self.assertTrue(len(trends) >= 1)
        self.assertIn("theme", trends[0])
        self.assertIn("example_scenes", trends[0])
        self.assertIn("suggested_quote", trends[0])

    def test_generate_content_package_formatting(self):
        sample_item = {
            "title": "Interstellar - Cooper watching 23 years of video messages",
            "type": "milestone",
            "actor": "Matthew McConaughey",
            "hook": "The video message scene in Interstellar.",
            "quote": "Today's my birthday too. And he said you'd be back...",
            "context": "Christopher Nolan didn't show Matthew McConaughey the recorded tapes until filming began.",
            "question": "What's the one movie scene that makes you tear up every single time?"
        }

        pkg = generate_content_package(sample_item)
        self.assertIn("hook_text", pkg)
        self.assertIn("caption", pkg)
        self.assertIn("hashtags", pkg)
        self.assertIn("#framefluence", pkg["hashtags"])
        self.assertIn(sample_item["question"], pkg["caption"])

    def test_split_mode_suggested_command_uses_top_and_bottom(self):
        pkg = generate_content_package({
            "title": "Dune: Part Three - Official Trailer",
            "hook": "Villeneuve just hid a callback in this trailer.",
            "recommended_mode": "split"
        })
        cmd = pkg["suggested_command"]
        self.assertIn("--mode split", cmd)
        self.assertIn("--top ", cmd)
        self.assertIn("--bottom ", cmd)
        self.assertNotIn("--input", cmd)

    def test_clean_mode_suggested_command_omits_text_overlays(self):
        pkg = generate_content_package({
            "hook": "Watch his eyes.",
            "quote": "Why so serious?",
            "recommended_mode": "clean"
        })
        cmd = pkg["suggested_command"]
        self.assertIn("--input scene.mp4", cmd)
        self.assertIn("--mode clean", cmd)
        self.assertNotIn("--hook-text", cmd)
        self.assertNotIn("--quote", cmd)

    def test_quote_mode_suggested_command_uses_input(self):
        pkg = generate_content_package({
            "hook": "Watch his eyes.",
            "quote": "Why so serious?",
            "recommended_mode": "quote"
        })
        cmd = pkg["suggested_command"]
        self.assertIn("--input scene.mp4", cmd)
        self.assertIn('--quote "Why so serious?"', cmd)
        self.assertNotIn("--top", cmd)

if __name__ == "__main__":
    unittest.main()
