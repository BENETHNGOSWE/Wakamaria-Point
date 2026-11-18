"""Select predictable fixtures from a football-data.org /matches payload.

Pure: no Frappe, no network, no clock. `now` and the timezone converter are
passed in, which is what makes the window logic testable.

The agent reads the bulk /matches endpoint rather than one request per
competition. football-data.org allows 10 requests a minute, so a site with
twenty leagues would spend its entire budget on fixture lookups before pricing
a single match.
"""

from datetime import datetime, timedelta, timezone

PREDICTABLE = {"SCHEDULED", "TIMED"}
MAX_WINDOW_DAYS = 8   # dateFrom is today-1, so this keeps the span at 10 days


def parse_utc(value):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def window(now, horizon_hours, max_window_days=MAX_WINDOW_DAYS):
    """(dateFrom, dateTo) covering the look-ahead, clamped to the plan's limit."""
    wanted = now.date() + timedelta(days=(horizon_hours // 24) + 2)
    limit = now.date() + timedelta(days=max_window_days)
    return now.date() - timedelta(days=1), min(wanted, limit)


def kickoff_local(iso, to_local=None):
    """Parse a provider UTC timestamp into naive local time."""
    aware = parse_utc(iso)
    if aware is None:
        return None
    if aware.tzinfo is None:
        aware = aware.replace(tzinfo=timezone.utc)
    if to_local is None:
        return aware.astimezone(timezone.utc).replace(tzinfo=None)
    local = to_local(aware)
    # Everything downstream compares against a naive "now", so a converter that
    # hands back an aware datetime would raise TypeError mid-run.
    if local is not None and local.tzinfo is not None:
        local = local.replace(tzinfo=None)
    return local


def select(matches, now, horizon_hours, to_local=None, predictable=None):
    """Return (fixtures, stats).

    fixtures is sorted by kickoff across every competition, so the soonest
    matches win the agent's per-run cap regardless of which league they are in.

    stats explains why each provider match was rejected. Without it, "0
    fixtures" is indistinguishable from "the provider returned nothing".
    """
    predictable = predictable or PREDICTABLE
    horizon_end = now + timedelta(hours=horizon_hours)
    counters = {"returned": 0, "not_predictable": 0, "past": 0,
                "beyond_horizon": 0, "incomplete": 0}
    fixtures = []

    for match in matches or []:
        if not match.get("id") or not match.get("utcDate"):
            continue
        counters["returned"] += 1

        if str(match.get("status") or "").upper() not in predictable:
            counters["not_predictable"] += 1
            continue

        kickoff = kickoff_local(match.get("utcDate"), to_local)
        if kickoff is None:
            counters["incomplete"] += 1
            continue
        if kickoff <= now:
            counters["past"] += 1
            continue
        if kickoff > horizon_end:
            counters["beyond_horizon"] += 1
            continue

        home = match.get("homeTeam") or {}
        away = match.get("awayTeam") or {}
        if not home.get("id") or not away.get("id"):
            counters["incomplete"] += 1
            continue

        competition = match.get("competition") or {}
        fixtures.append({
            "id": str(match["id"]),
            "kickoff": kickoff,
            "status": match.get("status"),
            "competition_code": str(competition.get("code") or "").upper(),
            "competition_name": competition.get("name") or "",
            "home_name": home.get("name") or "",
            "away_name": away.get("name") or "",
            "home_id": str(home["id"]),
            "away_id": str(away["id"]),
        })

    fixtures.sort(key=lambda row: row["kickoff"])
    return fixtures, counters


def group_by_competition(fixtures):
    """{competition_code: [fixtures]} — used by the diagnostic report."""
    grouped = {}
    for fixture in fixtures:
        grouped.setdefault(fixture["competition_code"], []).append(fixture)
    return grouped
