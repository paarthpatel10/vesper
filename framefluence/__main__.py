"""
One entry point for every tool:

    python -m framefluence studio      # local web UI (http://127.0.0.1:8765)
    python -m framefluence autopilot   # inbox/ -> review/ drafts (+ trend briefing)
    python -m framefluence review      # list / open / approve / reject drafts
    python -m framefluence reel        # render one reel with make_reel options
    python -m framefluence trends      # trend radar and post packages
    python -m framefluence calendar    # regenerate data/top_50_actors_calendar.csv
    python -m framefluence script <guide.md>   # cut every clip listed in a scripts guide

Anything after the command is passed to that tool, e.g. `python -m framefluence autopilot --drafts 2`.
"""

import importlib
import os
import sys

from framefluence.paths import ROOT

COMMANDS = {
    "studio": "framefluence.studio",
    "autopilot": "framefluence.autopilot",
    "review": "framefluence.review",
    "reel": "framefluence.make_reel",
    "trends": "framefluence.trend_agent",
    "calendar": "framefluence.update_actor_calendar",
    "script": "framefluence.script_clips",
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__.strip())
        return 0 if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help") else 2
    command = sys.argv[1]
    # Font, model and data paths are relative to the repo root, so always run from there
    os.chdir(ROOT)
    sys.argv = [f"framefluence {command}", *sys.argv[2:]]
    return importlib.import_module(COMMANDS[command]).main()


if __name__ == "__main__":
    sys.exit(main() or 0)
