"""The prediction agent.

Fixtures in, published predictions out, no human required. Runs on the Frappe
scheduler, so once it is deployed the site keeps filling itself whether or not
anyone has a laptop open.

Design rules, because this thing publishes under the operator's name:

  * One bad league, one dead fixture or one rate limit must never take the run
    down or leave a half-built prediction behind — every fixture is isolated.
  * A fixture that has already kicked off is never predicted. Publishing a tip
    for a match in progress is the single fastest way to lose a reader.
  * Publishing the same fixture twice is never allowed, whether the first copy
    came from the agent, from OCR or from a human.
  * The kill switch (`agent_paused`) stops creation immediately but keeps
    settlement running, because results must still resolve while the agent is
    switched off.
"""

from datetime import datetime, timedelta

import frappe
from frappe.utils import (add_days, add_to_date, convert_utc_to_system_timezone,
                          get_datetime, now_datetime)

from wakamaria import model, odds
from wakamaria.predictor import choose
from wakamaria.provider import api_get
from wakamaria.tips import family

HISTORY_PREFIX = "wakamaria:history:"
HISTORY_TTL = 6 * 3600
HISTORY_LIMIT = 20
HISTORY_FETCH_BUDGET = 8      # new provider calls per run, spread 7s apart
PROVIDER_PAUSE = 7
PREDICTABLE = {"SCHEDULED", "TIMED"}


def run_agent():
    """Scheduler entry point. Never raises into the scheduler."""
    settings = frappe.get_single("Wakamaria Settings")
    if not settings.get("agent_enabled"):
        return _finish(settings, "Agent disabled.")

    if _tripped(settings):
        return _finish(settings, "Agent paused automatically after a losing run.")

    if settings.get("agent_paused"):
        return _finish(settings, "Agent paused by the kill switch.")

    try:
        summary = _run(settings)
    except Exception:
        frappe.log_error(title="Wakamaria agent run failed",
                         message="Prediction agent aborted. No credentials logged.")
        return _finish(settings, "Run failed; see Error Log.")

    return _finish(settings, summary)


def _run(settings):
    horizon = int(settings.get("agent_horizon_hours") or 36)
    max_per_run = int(settings.get("agent_max_per_run") or 12)
    min_confidence = float(settings.get("agent_min_confidence") or 0.45)
    max_confidence = float(settings.get("agent_max_confidence") or 0.66)
    family_cap = int(settings.get("agent_family_cap") or 2)
    margin = float(settings.get("agent_margin") or model.DEFAULT_MARGIN)

    created = skipped = 0
    used_families = {}
    budget = {"fetches": 0}
    today_used = _created_today()

    leagues = frappe.get_all(
        "Wakamaria League",
        filters={"enabled": 1, "provider_code": ["is", "set"]},
        fields=["name", "league_name", "provider_code"],
    )

    for league in leagues:
        if created >= max_per_run:
            break
        if today_used + created >= int(settings.get("agent_max_per_day") or 20):
            break
        try:
            fixtures = _fixtures(league.provider_code, horizon)
        except Exception:
            # One unreadable competition must not cost us the rest of the card.
            continue

        for fixture in fixtures:
            if created >= max_per_run:
                break
            try:
                outcome = _publish_fixture(
                    settings, league, fixture, budget,
                    min_confidence=min_confidence,
                    max_confidence=max_confidence,
                    family_cap=family_cap,
                    used_families=used_families,
                    margin=margin,
                )
            except Exception:
                frappe.log_error(
                    title="Wakamaria agent fixture skipped",
                    message=f"{league.name}: fixture {fixture.get('id')} could not be priced.",
                )
                skipped += 1
                continue
            if outcome:
                created += 1
            else:
                skipped += 1

    frappe.db.commit()
    return (f"Created {created} prediction(s), skipped {skipped}. "
            f"Horizon {horizon}h, cap {max_per_run}/run.")


def _fixtures(provider_code, horizon):
    """Upcoming fixtures inside the horizon, local time, kickoff not yet passed."""
    now = now_datetime()
    today = now.date()
    data = api_get(
        f"/competitions/{provider_code}/matches",
        {"dateFrom": str(today - timedelta(days=1)),
         "dateTo": str(today + timedelta(days=(horizon // 24) + 2))},
    )

    fixtures = []
    for match in data.get("matches") or []:
        if not match.get("id") or not match.get("utcDate"):
            continue
        if str(match.get("status") or "").upper() not in PREDICTABLE:
            continue
        kickoff = _local(match["utcDate"])
        if kickoff is None:
            continue
        if kickoff <= now or kickoff > add_to_date(now, hours=horizon):
            continue
        home = (match.get("homeTeam") or {})
        away = (match.get("awayTeam") or {})
        if not home.get("id") or not away.get("id"):
            continue
        fixtures.append({
            "id": str(match["id"]),
            "kickoff": kickoff,
            "status": match.get("status"),
            "home_name": home.get("name") or "",
            "away_name": away.get("name") or "",
            "home_id": str(home["id"]),
            "away_id": str(away["id"]),
        })
    fixtures.sort(key=lambda f: f["kickoff"])
    return fixtures


def _local(utc_iso):
    try:
        moment = datetime.fromisoformat(str(utc_iso).replace("Z", "+00:00"))
        return convert_utc_to_system_timezone(moment.replace(tzinfo=None)).replace(tzinfo=None)
    except (ValueError, TypeError):
        return None


def _publish_fixture(settings, league, fixture, budget, *, min_confidence,
                     max_confidence, family_cap, used_families, margin):
    """Create one published prediction, or return None if nothing was published."""
    if _already_known(league.name, fixture):
        return None

    home_history = _history(fixture["home_id"], budget)
    away_history = _history(fixture["away_id"], budget)

    prediction = model.predict(
        home_history, away_history,
        home_id=fixture["home_id"], home_name=fixture["home_name"],
        away_id=fixture["away_id"], away_name=fixture["away_name"],
    )

    prices = odds.resolve(
        prediction["probabilities"],
        home_team=fixture["home_name"],
        away_team=fixture["away_name"],
        provider_code=league.provider_code,
        margin=margin,
    )

    choice = choose(
        prediction["probabilities"], prices,
        min_confidence=min_confidence,
        max_confidence=max_confidence,
        family_cap=family_cap,
        used_families=used_families,
    )
    if not choice or not choice.get("odds"):
        return None

    doc = frappe.get_doc({
        "doctype": "Wakamaria Match",
        "league": league.name,
        "home_team": fixture["home_name"],
        "away_team": fixture["away_name"],
        "kickoff": fixture["kickoff"],
        "prediction": choice["tip"],
        "odds": choice["odds"],
        "odds_source": choice["source"],
        "confidence": choice["confidence"],
        "predicted_by": "Agent",
        "published": 1,
        "provider_match_id": fixture["id"],
        "provider_home_team_id": fixture["home_id"],
        "provider_away_team_id": fixture["away_id"],
        "provider_status": fixture["status"],
        "notes": (f"Agent: lambda {prediction['home_lambda']:.2f}"
                  f"/{prediction['away_lambda']:.2f}, "
                  f"p={choice['confidence']:.3f}, price={choice['odds']}"
                  f" ({choice['source']})"),
    })
    doc.insert(ignore_permissions=True)
    used_families[choice["family"]] = used_families.get(choice["family"], 0) + 1
    return doc.name


def _already_known(league, fixture):
    """Three ways a fixture can already be on the site. All of them block."""
    if frappe.db.exists("Wakamaria Match", {"provider_match_id": fixture["id"]}):
        return True
    return bool(frappe.db.exists("Wakamaria Match", {
        "league": league,
        "home_team": fixture["home_name"],
        "away_team": fixture["away_name"],
        "kickoff": fixture["kickoff"],
    }))


def _history(team_id, budget):
    """Recent finished matches for a team, read from the cache `sync.py` fills."""
    key = HISTORY_PREFIX + str(team_id)
    cached = frappe.cache().get_value(key)
    if cached is not None:
        return cached
    if budget["fetches"] >= HISTORY_FETCH_BUDGET:
        return []

    import time
    time.sleep(PROVIDER_PAUSE)
    try:
        payload = api_get(f"/teams/{team_id}/matches",
                          {"status": "FINISHED", "limit": HISTORY_LIMIT})
    except Exception:
        return []

    entries = []
    for match in payload.get("matches") or []:
        score = match.get("score") or {}
        full = score.get("fullTime") or {}
        home_goals, away_goals = full.get("home"), full.get("away")
        if type(home_goals) is not int or type(away_goals) is not int:
            continue
        if score.get("duration") not in (None, "REGULAR"):
            continue
        entries.append({
            "date": match.get("utcDate", ""),
            "home": (match.get("homeTeam") or {}).get("name", ""),
            "away": (match.get("awayTeam") or {}).get("name", ""),
            "home_id": str((match.get("homeTeam") or {}).get("id") or ""),
            "away_id": str((match.get("awayTeam") or {}).get("id") or ""),
            "score": [home_goals, away_goals],
        })

    frappe.cache().set_value(key, entries, expires_in_sec=HISTORY_TTL)
    budget["fetches"] += 1
    return entries


def _created_today():
    start = get_datetime(now_datetime()).replace(hour=0, minute=0, second=0, microsecond=0)
    return frappe.db.count("Wakamaria Match", {
        "predicted_by": "Agent",
        "creation": [">=", start],
    })


def _tripped(settings):
    """Optional circuit breaker. Zero means off — the agent keeps publishing."""
    threshold = int(settings.get("agent_pause_after_losses") or 0)
    if threshold <= 0:
        return False
    recent = frappe.get_all(
        "Wakamaria Match",
        filters={"predicted_by": "Agent", "result_confirmed": 1},
        fields=["outcome"],
        order_by="kickoff desc",
        limit_page_length=threshold,
    )
    if len(recent) < threshold:
        return False
    if all(row.outcome == "Lose" for row in recent):
        frappe.db.set_single_value("Wakamaria Settings", "agent_paused", 1)
        frappe.log_error(
            title="Wakamaria agent auto-paused",
            message=f"Last {threshold} agent predictions all lost. Review before resuming.",
        )
        return True
    return False


def _finish(settings, summary):
    frappe.db.set_single_value("Wakamaria Settings", "agent_last_run", now_datetime())
    frappe.db.set_single_value("Wakamaria Settings", "agent_last_result", summary[:500])
    frappe.db.commit()
    return summary
