"""
Framefluence - Review queue for autopilot drafts.

    python -m framefluence review                  # list drafts waiting for review
    python -m framefluence review open <name>      # play the reel and show the caption
    python -m framefluence review approve <name>   # move to approved/ (ready to post)
    python -m framefluence review reject <name>    # move to rejected/
"""

import argparse
import json
import os
import shutil
import sys

from framefluence.paths import ROOT
FOLDERS = {"pending": "review", "approved": "approved", "rejected": "rejected"}

try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def drafts(status="pending"):
    base = os.path.join(ROOT, FOLDERS[status])
    if not os.path.isdir(base):
        return []
    return sorted(d for d in os.listdir(base) if os.path.isfile(os.path.join(base, d, "reel.mp4")))


def move(name, status):
    src = os.path.join(ROOT, FOLDERS["pending"], name)
    if not os.path.isdir(src):
        sys.exit(f"No pending draft named '{name}'. Run `python -m framefluence review` to list them.")
    dest_dir = os.path.join(ROOT, FOLDERS[status])
    os.makedirs(dest_dir, exist_ok=True)
    meta_path = os.path.join(src, "meta.json")
    if os.path.exists(meta_path):
        with open(meta_path, encoding="utf-8") as f:
            meta = json.load(f)
        meta["status"] = status
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)
    shutil.move(src, os.path.join(dest_dir, name))
    print(f"{name} -> {FOLDERS[status]}/")


def main():
    parser = argparse.ArgumentParser(description="Review Framefluence autopilot drafts")
    parser.add_argument("action", nargs="?", choices=["list", "open", "approve", "reject"], default="list")
    parser.add_argument("name", nargs="?", help="Draft folder name (from the list)")
    args = parser.parse_args()

    if args.action == "list":
        pending = drafts()
        print(f"{len(pending)} draft(s) waiting for review:" if pending else "No drafts waiting for review.")
        for name in pending:
            with open(os.path.join(ROOT, "review", name, "meta.json"), encoding="utf-8") as f:
                meta = json.load(f)
            print(f"  {name}   [{meta.get('framing')}, subtitles={'yes' if meta.get('subtitles') else 'no'}]")
        print(f"\nApproved & ready to post: {len(drafts('approved'))}")
        return

    if not args.name:
        sys.exit(f"Usage: python -m framefluence review {args.action} <name>")
    if args.action == "open":
        folder = os.path.join(ROOT, "review", args.name)
        with open(os.path.join(folder, "caption.txt"), encoding="utf-8") as f:
            print(f.read())
        os.startfile(os.path.join(folder, "reel.mp4"))
    else:
        move(args.name, "approved" if args.action == "approve" else "rejected")


if __name__ == "__main__":
    main()
