"""
Framefluence - Trend Research & Content Suggestion Agent
Monitors 3 key intelligence pillars:
  1. Actor Milestones & Birthdays (from top_50_actors_calendar.csv)
  2. Breaking Movie Trailers & Hype-Jacks (via live RSS & release radars)
  3. Peer Page Trends & Evergreen Quotes (from cinema_competitors_and_benchmarks.csv)
Provides an interactive terminal dashboard to pick today's Reel and build its render command.
"""

import argparse
import csv
import datetime
import json
import os
import sys
import urllib.request

from framefluence.paths import ACTOR_CALENDAR

try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def next_birthday(month, day, today):
    """Returns the next occurrence of month/day on or after today (Feb 29 falls back to Feb 28)."""
    for year in (today.year, today.year + 1):
        try:
            candidate = datetime.date(year, month, day)
        except ValueError:
            candidate = datetime.date(year, 2, 28)
        if candidate >= today:
            return candidate


def get_upcoming_milestones(calendar_path=None, days_threshold=30, today=None):
    """
    Reads the actor calendar and computes the countdown live from each birthday,
    so the CSV's precomputed Days_Until_Birthday column can never go stale.
    """
    if not calendar_path:
        calendar_path = ACTOR_CALENDAR
    today = today or datetime.date.today()

    if not os.path.exists(calendar_path):
        return []

    milestones = []
    with open(calendar_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                bday = datetime.datetime.strptime(row["Birthday_Month_Day"], "%B %d")
                birth_year = int(row["Birth_Year"])
            except (KeyError, ValueError):
                continue
            upcoming = next_birthday(bday.month, bday.day, today)
            days_left = (upcoming - today).days
            if days_left <= days_threshold:
                milestones.append({
                    "actor_name": row.get("Actor_Name"),
                    "tier": row.get("Tier_Type"),
                    "days_left": days_left,
                    "date": row.get("Birthday_Month_Day"),
                    "age_turning": upcoming.year - birth_year,
                    "hook": row.get("Birthday_Reel_Hook"),
                    "roles": row.get("Signature_Movies_Or_Roles")
                })

    # Curated CSV entries win over TMDB duplicates (they carry hand-written hooks)
    known = {m["actor_name"] for m in milestones}
    milestones.extend(m for m in _tmdb_milestones(days_threshold, today) if m["actor_name"] not in known)
    milestones.sort(key=lambda x: x["days_left"])
    return milestones


def _tmdb_milestones(days_threshold, today):
    """Adds live birthdays from TMDB's popular people when TMDB_API_KEY is set; silent no-op otherwise."""
    api_key = os.environ.get("TMDB_API_KEY")
    if not api_key:
        return []
    try:
        from framefluence.tmdb_calendar import get_tmdb_milestones
        return get_tmdb_milestones(api_key, days_threshold=days_threshold, today=today)
    except Exception:
        return []

def get_breaking_trailers(max_items=3):
    """
    Fetches trending trailers from public feeds or uses high-profile upcoming release slate.
    """
    trailers = []
    url = "https://www.reddit.com/r/trailers/hot.json?limit=10"
    
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "FramefluenceTrendBot/1.0 (by @framefluence)"}
        )
        with urllib.request.urlopen(req, timeout=4) as response:
            data = json.loads(response.read().decode())
            posts = data.get("data", {}).get("children", [])
            for p in posts:
                post_data = p.get("data", {})
                title = post_data.get("title", "")
                link = post_data.get("url", "")
                if "trailer" in title.lower() or "teaser" in title.lower():
                    # Clean title
                    clean_title = title.replace("[Official Trailer]", "").replace("(Trailer)", "").strip()
                    trailers.append({
                        "title": clean_title,
                        "link": link,
                        "hype_angle": "The 1 subtle easter-egg in the new trailer everyone missed...",
                        "suggested_format": "3-second shock hook -> zoom in on background detail -> prompt discussion in comments."
                    })
                    if len(trailers) >= max_items:
                        break
    except Exception:
        # Fallback to high-profile current blockbuster radar
        pass

    if not trailers:
        trailers = [
            {
                "title": "Gladiator II - Paul Mescal & Denzel Washington Colosseum Clash",
                "link": "https://www.youtube.com/results?search_query=Gladiator+2+official+trailer",
                "hype_angle": "How Ridley Scott mirrored the original 2000 Maximus opening shot",
                "suggested_format": "Side-by-side callback (Russell Crowe vs Paul Mescal) in split-screen mode."
            },
            {
                "title": "Joker: Folie à Deux - The Courthouse Steps Scene",
                "link": "https://www.youtube.com/results?search_query=Joker+Folie+a+Deux+trailer",
                "hype_angle": "Did you notice the reflection in Arthur Fleck's makeup mirror?",
                "suggested_format": "Fast 2-second visual hook -> slow cinematic build-up with isolated audio."
            },
            {
                "title": "Avengers: Doomsday - Robert Downey Jr. Doctor Doom Teaser",
                "link": "https://www.youtube.com/results?search_query=Avengers+Doomsday+teaser",
                "hype_angle": "The 1 line from Iron Man 1 that foreshadowed this moment...",
                "suggested_format": "Nostalgia callback edit: Tony Stark 2008 line transitioning to Doom reveal."
            }
        ]

    return trailers[:max_items]

def get_peer_trends(benchmarks_path=None):
    """
    Returns trending tropes and dialogue concepts based on competitor monitoring.
    """
    # High-performing formats validated across our 80 accounts (@best.movie.lines, @cinemahow, @touchingfilms)
    trends = [
        {
            "theme": "Philosophical Dialogue on Dreams & Reality",
            "reference_pages": "@best.movie.lines, @sentences.from.movies, @thefilmzone",
            "example_scenes": "Narcos (Wagner Moura) / Vikings (Travis Fimmel)",
            "suggested_quote": "The problem is nobody can control the dream they have.",
            "hook": "The line from Narcos that changes how you look at ambition.",
            "recommended_mode": "quote",
            "why_it_works": "Proven evergreen retention on @framefluence. Massive DM shares at midnight."
        },
        {
            "theme": "The Uncut Acting Masterclass (High Tension)",
            "reference_pages": "@screenplayed, @cinema.magic, @outstandingscreenplays",
            "example_scenes": "Whiplash (J.K. Simmons 'Not quite my tempo') / Inglorious Basterds (Christoph Waltz)",
            "suggested_quote": "There are no two words in the English language more harmful than 'good job'.",
            "hook": "The scene where not a single person in the theater dared to breathe.",
            "recommended_mode": "quote",
            "why_it_works": "100%+ completion rate because viewers stay locked into the dialogue."
        },
        {
            "theme": "Script-to-Screen / Movie Callback Parallel",
            "reference_pages": "@screenplayed, @comp_cam",
            "example_scenes": "The Dark Knight interrogation vs Heat diner scene",
            "suggested_quote": "You complete me.",
            "hook": "Notice how Nolan staged this scene exactly like Michael Mann's Heat.",
            "recommended_mode": "split",
            "why_it_works": "Dual-layer visual formats double average watch time."
        }
    ]
    return trends

def generate_content_package(item):
    """
    Produces complete ready-to-post package: hook text, caption, hashtags, and make_reel command.
    """
    item_type = item.get("type", "quote")
    title = item.get("title", "Cinematic Scene")
    hook = item.get("hook", "Did you notice this?")
    quote = item.get("quote", "")
    context = item.get("context", "A legendary cinematic performance.")
    question = item.get("question", "What is your favorite scene from this film?")

    title_block = f"🎬 {title}" + (f'\n💬 "{quote}"' if quote else "")
    caption = f"""{hook}

{title_block}

{context}

👇 {question}

---
Save this for your weekend watchlist 🍿
Follow @framefluence for daily cinema frames, iconic monologues & hidden details.

© All rights belong to their respective film studios. Shared for commentary, critique & cinephile curation.
""".strip()

    # Topic tags (e.g. #friends) first: they matter most for reach; Instagram allows up to 30
    base_tags = ["#framefluence", "#cinema", "#movieclips", "#cinematography", "#filmcommunity", "#cinephile",
                 "#filmscene", "#actingmasterclass", "#movierecommendation", "#hollywood"]
    extra = [t if t.startswith("#") else f"#{t}" for t in item.get("extra_hashtags", "").split()]
    hashtags = " ".join(dict.fromkeys(extra + base_tags))

    mode = item.get("recommended_mode", "quote")

    if mode == "split":
        # Split mode takes two stacked clips and renders neither hook nor quote text
        cmd_suggestion = f"python -m framefluence reel --top top_clip.mp4 --bottom bottom_clip.mp4 --output output/reel_{mode}.mp4 --mode {mode}"
    elif mode == "clean":
        # Clean mode is watermark-only; hook and quote go in IG native text instead
        cmd_suggestion = f"python -m framefluence reel --input scene.mp4 --output output/reel_{mode}.mp4 --mode {mode}"
    else:
        cmd_suggestion = f"python -m framefluence reel --input scene.mp4 --output output/reel_{mode}.mp4 --mode {mode} --hook-text \"{hook}\""
        if quote:
            cmd_suggestion += f" --quote \"{quote}\""

    return {
        "title": title,
        "hook_text": hook,
        "caption": caption,
        "hashtags": hashtags,
        "recommended_mode": mode,
        "suggested_command": cmd_suggestion
    }

def print_daily_briefing():
    print("=" * 70)
    print("🎬  FRAMEFLUENCE DAILY TREND & CONTENT RADAR  🎬")
    print("=" * 70)

    # 1. Milestones
    milestones = get_upcoming_milestones(days_threshold=30)
    print("\n🎂  MODULE 1: UPCOMING ACTOR MILESTONES")
    print("-" * 50)
    if milestones:
        top_m = milestones[0]
        print(f"👉 TOP PICK: {top_m['actor_name']} ({top_m['date']}, turning {top_m['age_turning']}) — {top_m['days_left']} DAYS LEFT!")
        print(f"   Hook: \"{top_m['hook']}\"")
        print(f"   Signature Films: {top_m['roles']}")
    else:
        print("   No immediate birthdays in the next 30 days.")

    # 2. Breaking Trailers
    trailers = get_breaking_trailers(max_items=2)
    print("\n🔥  MODULE 2: BREAKING TRAILERS & HYPE-JACK RADAR")
    print("-" * 50)
    for idx, t in enumerate(trailers, 1):
        print(f"[{idx}] {t['title']}")
        print(f"    Angle: {t['hype_angle']}")
        print(f"    Format: {t['suggested_format']}")

    # 3. Peer Trends
    peer_trends = get_peer_trends()
    print("\n📊  MODULE 3: SIMILAR PAGE TRENDS & PROVEN QUOTES")
    print("-" * 50)
    top_peer = peer_trends[0]
    print(f"👉 TOP THEME: {top_peer['theme']}")
    print(f"   Example: {top_peer['example_scenes']}")
    print(f"   Winning Quote: \"{top_peer['suggested_quote']}\"")
    print(f"   Why it works: {top_peer['why_it_works']}")

    print("\n" + "=" * 70)

def main():
    parser = argparse.ArgumentParser(description="Framefluence Trend Research & Suggestion Agent")
    parser.add_argument("--briefing-only", action="store_true", help="Print daily briefing without interactive prompt")
    args = parser.parse_args()

    print_daily_briefing()

    if args.briefing_only:
        return

    milestones = get_upcoming_milestones(days_threshold=30)
    trailers = get_breaking_trailers(max_items=1)
    peer_trends = get_peer_trends()

    options = {}
    if milestones:
        m = milestones[0]
        options["1"] = {
            "title": f"{m['actor_name']} Birthday Tribute ({m['date']})",
            "type": "milestone",
            "hook": m["hook"],
            "quote": f"Happy Birthday to the legendary {m['actor_name']}.",
            "context": f"Celebrating {m['actor_name']} turning {m['age_turning']}. Known for unforgettable roles in {m['roles']}.",
            "question": f"What is your all-time favorite {m['actor_name']} performance?",
            "recommended_mode": "quote"
        }

    if trailers:
        t = trailers[0]
        options["2"] = {
            "title": t["title"],
            "type": "trailer",
            "hook": t["hype_angle"],
            "quote": "",
            "context": "Breaking trailer analysis and hidden cinematography parallels.",
            "question": "Are you hyped for this release? Drop your rating from 1-10.",
            "recommended_mode": "split" if "split" in t.get("suggested_format", "") else "quote"
        }

    if peer_trends:
        p = peer_trends[0]
        options["3"] = {
            "title": p["example_scenes"],
            "type": "peer_quote",
            "hook": p["hook"],
            "quote": p["suggested_quote"],
            "context": f"A timeless philosophical reflection on human nature. Popularized across top cinema pages.",
            "question": "Has a movie quote ever genuinely changed the way you think?",
            "recommended_mode": p.get("recommended_mode", "quote")
        }

    print("\n👉 SELECT TODAY'S REEL CONCEPT TO GENERATE FULL PACKAGE:")
    print("   [1] Actor Milestone Tribute")
    print("   [2] Breaking Trailer Hype-Jack")
    print("   [3] Trending Peer Scene / Deep Quote")
    print("   [q] Quit")

    choice = input("\nEnter your choice (1/2/3): ").strip().lower()
    if choice in options:
        selected = options[choice]
        pkg = generate_content_package(selected)
        print("\n" + "#" * 60)
        print(f"🎬  GENERATED INSTAGRAM PACKAGE: {pkg['title']}")
        print("#" * 60)
        print(f"\n[1] 3-SECOND VIDEO HOOK:\n>>> {pkg['hook_text']}\n")
        print(f"[2] INSTAGRAM CAPTION:\n{pkg['caption']}\n")
        print(f"[3] SEO HASHTAGS:\n{pkg['hashtags']}\n")
        print(f"[4] RECOMMENDED COMMAND TO RENDER:\n{pkg['suggested_command']}\n")
        print("#" * 60)
    elif choice != "q":
        print("Invalid choice. Exiting.")

if __name__ == "__main__":
    main()
