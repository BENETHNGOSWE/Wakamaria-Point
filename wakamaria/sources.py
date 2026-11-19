"""Merge fixture lists from more than one provider.

Two providers will disagree about everything except, usually, the match itself.
football-data.org calls it "Manchester United", API-Football calls it
"Manchester United"; but one may say "Man United", "Sheffield Wednesday" or
"Paris Saint-Germain" where the other says "Paris SG". Kickoff times differ by
seconds. Competition names differ by country prefixes.

So merging is done on a deliberately loose identity — both team names,
casefolded and stripped of punctuation, plus the kickoff rounded to the day —
and the first provider to supply a fixture wins. The second provider therefore
adds *new* fixtures and never rewrites ones already covered, which keeps the
result stable from run to run.

Pure: no Frappe, no network, no clock.
"""

import re

from wakamaria.fixtures import parse_utc

_NOISE = re.compile(r"[^a-z0-9]+")


def normalise(name):
    """A team name reduced to something two providers can agree on."""
    return _NOISE.sub("", (name or "").casefold())


def identity(match):
    """(home, away, day) — the loosest key that still identifies one match."""
    home = normalise((match.get("homeTeam") or {}).get("name"))
    away = normalise((match.get("awayTeam") or {}).get("name"))
    kickoff = parse_utc(match.get("utcDate"))
    day = kickoff.date().isoformat() if kickoff else (match.get("utcDate") or "")[:10]
    return (home, away, day)


def merge(primary, secondary):
    """Primary fixtures first, then any from secondary not already covered.

    Returns (fixtures, added) where added is how many came from secondary.
    Order is primary then secondary; the caller sorts by kickoff afterwards.
    """
    seen = set()
    merged = []
    for match in primary or []:
        key = identity(match)
        if key in seen or not all(key):
            continue
        seen.add(key)
        merged.append(match)

    added = 0
    for match in secondary or []:
        key = identity(match)
        if not all(key) or key in seen:
            continue
        seen.add(key)
        merged.append(match)
        added += 1

    return merged, added
