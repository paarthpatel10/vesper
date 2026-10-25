import os
import subprocess
import sys
import unittest

class TestEndToEnd(unittest.TestCase):
    def test_full_video_pipeline_generation(self):
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        output_dir = os.path.join(project_root, "output")
        os.makedirs(output_dir, exist_ok=True)

        raw_input = os.path.join(output_dir, "test_synth_input.mp4")
        reel_output = os.path.join(output_dir, "sample_reel.mp4")

        # Step 1: Generate a 4-second 1280x720 synthetic test clip with audio tone
        synth_cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "testsrc=duration=4:size=1280x720:rate=30",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=4",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            raw_input
        ]
        res = subprocess.run(synth_cmd, capture_output=True)
        self.assertEqual(res.returncode, 0, f"Synthetic video creation failed: {res.stderr.decode('utf-8', errors='ignore')}")
        self.assertTrue(os.path.exists(raw_input))

        # Step 2: Run make_reel.py with quote mode, hook text, quote subtitles, and watermark
        make_cmd = [
            sys.executable,
            "-m", "framefluence.make_reel",
            "--input", raw_input,
            "--output", reel_output,
            "--mode", "quote",
            "--hook-text", "The problem is nobody can control",
            "--quote", "The problem is nobody can control the dream they have",
            "--watermark", "@framefluence"
        ]
        res2 = subprocess.run(make_cmd, capture_output=True, cwd=project_root)
        self.assertEqual(res2.returncode, 0, f"make_reel failed: {res2.stderr.decode('utf-8', errors='ignore')}")
        self.assertTrue(os.path.exists(reel_output))

        # Step 3: Verify output video metadata with ffprobe
        probe_cmd = [
            "ffprobe",
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "csv=s=x:p=0",
            reel_output
        ]
        probe_res = subprocess.run(probe_cmd, capture_output=True, text=True)
        dimensions = probe_res.stdout.strip()
        self.assertEqual(dimensions, "1080x1920", f"Expected 1080x1920, got {dimensions}")

        # Check filesize
        filesize = os.path.getsize(reel_output)
        self.assertTrue(filesize > 50000, f"File size too small: {filesize} bytes")
        print(f"\n[+] Verified sample reel created at: {reel_output} ({dimensions}, {filesize} bytes)")

if __name__ == "__main__":
    unittest.main()
