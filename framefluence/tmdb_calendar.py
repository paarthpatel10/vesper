"""
Framefluence - Live actor birthdays from TMDB (themoviedb.org).
Scans TMDB's popular people and returns upcoming birthdays in the same shape as
trend_agent.get_upcoming_milestones(). Needs a free TMDB API key (v3 key or v4 read token).
"""

import datetime
import json
import urllib.parse
import urllib.request

API_ROOT = "https://api.themoviedb.org/3"


def _get(path, api_key, **params):
    headers = {"Accept": "application/json"}
    # v4 read access tokens are JWTs (start with "eyJ") and go in the header; v3 keys go in the query
    if api_key.startswith("eyJ"):
        headers["Authorization"] = f"Bearer {api_key}"
    else:
        params["api_key"] = api_key
    url = f"{API_ROOT}{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=8) as response:
        return json.loads(response.read().decode("utf-8"))


def person_to_milestone(person, today, days_threshold):
    """Converts a TMDB person-details dict into a milestone dict, or None if outside the window."""
    from framefluence.trend_agent import next_birthday

    birthday = person.get("birthday")
    if not birthday or person.get("deathday"):
        return None
    try:
        born = datetime.date.fromisoformat(birthday)
    except ValueError:
        return None

    upcoming = next_birthday(born.month, born.day, today)
    days_left = (upcoming - today).days
    if days_left > days_threshold:
        return None

    roles = ", ".join(
        k.get("title") or k.get("name")
        for k in person.get("known_for", [])
        if k.get("title") or k.get("name")
    )
    name = person.get("name")
    return {
        "actor_name": name,
        "tier": "TMDB Popular",
        "days_left": days_left,
        "date": upcoming.strftime("%B %d"),
        "age_turning": upcoming.year - born.year,
        "hook": f"Happy Birthday {name}. Which role is your favourite?",
        "roles": roles,
    }


def get_tmdb_milestones(api_key, days_threshold=30, pages=3, today=None):
    """Fetches `pages` pages (20 people each) of TMDB popular people and returns upcoming birthdays."""
    today = today or datetime.date.today()
    milestones = []
    for page in range(1, pages + 1):
        popular = _get("/person/popular", api_key, page=page)
        for summary in popular.get("results", []):
            if summary.get("known_for_department") != "Acting":
                continue
            details = _get(f"/person/{summary['id']}", api_key)
            details["known_for"] = summary.get("known_for", [])
            milestone = person_to_milestone(details, today, days_threshold)
            if milestone:
                milestones.append(milestone)
    return milestones
