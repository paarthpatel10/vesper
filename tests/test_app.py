import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from framefluence.studio import draft_dir, parse_range, safe_filename


class TestStudioServer(unittest.TestCase):
    def test_parse_range_variants(self):
        self.assertEqual(parse_range("bytes=100-199", 1000), (100, 199))
        self.assertEqual(parse_range("bytes=900-", 1000), (900, 999))
        self.assertEqual(parse_range("bytes=-100", 1000), (900, 999))
        self.assertEqual(parse_range("bytes=990-5000", 1000), (990, 999))
        self.assertIsNone(parse_range("bytes=2000-", 1000))
        self.assertIsNone(parse_range(None, 1000))
        self.assertIsNone(parse_range("bytes=-", 1000))

    def test_safe_filename_strips_paths_and_odd_characters(self):
        self.assertEqual(safe_filename("../../evil name!.MKV"), "evil_name.mkv")
        self.assertEqual(safe_filename("notes.exe"), "notes.mp4")
        self.assertEqual(safe_filename(""), "clip.mp4")

    def test_draft_dir_refuses_traversal_and_unknown_status(self):
        self.assertIsNone(draft_dir("pending", "../app.py"))
        self.assertIsNone(draft_dir("pending", "..\\secrets"))
        self.assertIsNone(draft_dir("elsewhere", "anything"))
        self.assertIsNone(draft_dir("pending", "does_not_exist"))


if __name__ == "__main__":
    unittest.main()
