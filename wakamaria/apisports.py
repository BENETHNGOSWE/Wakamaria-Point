"""API-Football (api-sports.io) as a second fixture source.

The agent was built against football-data.org's JSON. Rather than teach the
agent a second shape, this module translates API-Football into *that* shape, so
`wakamaria.fixtures.select` and everything downstream stay untouched.

    provider payload  ->  to_matches()  ->  football-data.org shaped dicts
                                            |
                                            +-> fixtures.select()

Why this provider: football-data.org's free plan is 12 competitions, and on a
day like 19 November 2026 — mid international break — those 12 contain two
matches. API-Football carries 1,200+ competitions, which is where the rest of
that day's football lives.

Auth differs by route:
  * api-sports.io direct  -> header  x-apisports-key
  * RapidAPI reseller     -> headers x-rapidapi-key + x-rapidapi-host
Both are handled; the operator sets the base URL in Wakamaria Settings.

Pure conversion, plus one HTTP call. No Frappe import at module level so the
translation can be tested without a site.
"""

import json

DEFAULT_BASE = "https://v3.football.api-sports.io"

# API-Football short status -> football-data.org status.
# Only not-yet-started matches are predictable; everything else is passed
# through so `fixtures.select` can count and explain the rejection.
STATUS = {
    "TBD": "SCHEDULED",
    "NS": "SCHEDULED",
    "1H": "IN_PLAY", "HT": "IN_PLAY", "2H": "IN_PLAY", "ET": "IN_PLAY",
    "BT": "IN_PLAY", "P": "IN_PLAY", "LIVE": "IN_PLAY",
    "FT": "FINISHED", "AET": "FINISHED", "PEN": "FINISHED",
    "PST": "POSTPONED", "CANC": "CANCELLED", "ABD": "ABANDONED",
    "AWD": "FINISHED", "WO": "FINISHED", "SUSP": "SUSPENDED",
    "INT": "SUSPENDED",
}


def to_matches(payload):
    """Translate an API-Football /fixtures payload into provider-shaped matches.

    Anything missing an id, a kickoff, both teams or a league is dropped rather
    than guessed at — a fixture with no kickoff cannot be scheduled and would
    poison the calendar.
    """
    matches = []
    for row in (payload or {}).get("response") or []:
        fixture = row.get("fixture") or {}
        league = row.get("league") or {}
        teams = row.get("teams") or {}
        home = teams.get("home") or {}
        away = teams.get("away") or {}

        match_id = fixture.get("id")
        kickoff = fixture.get("date")
        if not match_id or not kickoff:
            continue
        if not home.get("id") or not away.get("id"):
            continue
        if not home.get("name") or not away.get("name"):
            continue
        if not league.get("id"):
            continue

        short = ((fixture.get("status") or {}).get("short") or "NS").upper()
        matches.append({
            "id": str(match_id),
            "utcDate": kickoff,
            "status": STATUS.get(short, "SCHEDULED"),
            "competition": {
                # Synthetic code: the agent resolves this provider's fixtures by
                # league name, because Wakamaria League holds football-data
                # codes. "APIFB" can never collide with a real provider code.
                "code": "APIFB",
                "name": league.get("name") or "",
            },
            "homeTeam": {"id": str(home["id"]), "name": home["name"]},
            "awayTeam": {"id": str(away["id"]), "name": away["name"]},
            # Carried for the name/country fallback in the agent's league lookup.
            "source_country": league.get("country") or "",
            "source": "apifootball",
        })
    return matches


def fetch(api_key, date_from, date_to, base=None, timeout=25, get=None):
    """One request covering the whole window. Returns provider-shaped matches.

    `get(url, headers, params)` is injectable so the request can be exercised in
    tests without a key or a network.
    """
    if not api_key:
        return []
    base = (base or DEFAULT_BASE).rstrip("/")
    params = {"from": str(date_from), "to": str(date_to), "timezone": "UTC"}

    if "rapidapi" in base:
        headers = {"x-rapidapi-key": api_key,
                   "x-rapidapi-host": base.split("//", 1)[-1].split("/", 1)[0]}
    else:
        headers = {"x-apisports-key": api_key}

    if get is None:
        import requests
        response = requests.get(f"{base}/fixtures", headers=headers,
                                params=params, timeout=timeout)
        response.raise_for_status()
        payload = response.json()
    else:
        payload = get(f"{base}/fixtures", headers, params)
        if isinstance(payload, str):
            payload = json.loads(payload)

    errors = (payload or {}).get("errors")
    if errors:
        # API-Football reports quota and plan problems in a 200 response.
        raise RuntimeError(f"API-Football refused the request: {errors}")

    return to_matches(payload)
