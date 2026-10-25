"""Every folder the project uses, resolved from the repository root (the parent of this package)."""

import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE = os.path.join(ROOT, "framefluence")

DATA = os.path.join(ROOT, "data")
ASSETS = os.path.join(ROOT, "assets")
FONTS = os.path.join(ASSETS, "fonts")
FOOTAGE = os.path.join(ASSETS, "footage")
MODELS = os.path.join(ROOT, "models")
UI = os.path.join(PACKAGE, "ui")

# Runtime folders (git-ignored)
INBOX = os.path.join(ROOT, "inbox")
PROCESSED = os.path.join(INBOX, "processed")
REVIEW = os.path.join(ROOT, "review")
APPROVED = os.path.join(ROOT, "approved")
REJECTED = os.path.join(ROOT, "rejected")
LOGS = os.path.join(ROOT, "logs")
OUTPUT = os.path.join(ROOT, "output")

ACTOR_CALENDAR = os.path.join(DATA, "top_50_actors_calendar.csv")
PEER_BENCHMARKS = os.path.join(DATA, "cinema_competitors_and_benchmarks.csv")
ENV_FILE = os.path.join(ROOT, ".env")
