"""The prediction agent.

Fixtures in, published predictions out, no human required. Runs on the Frappe
scheduler, so once it is deployed the site keeps filling itself whether or not
anyone has a laptop open.

Design rules, because this thing publishes under the operator's name:

  * A bad competition, a dead fixture or a rate limit must never take the run
    down or leave a half-built prediction behind. Every fixture is isolated.
  * A fixture that has already kicked off is never predicted. Publishing a tip
    for a match in progress is the fastest way to lose a reader.
  * Publishing the same fixture twice is never allowed, whether the first copy
    came from the agent, from OCR or from a human.
  * The kill switch (`agent_paused`) stops creation immediately but keeps
    settlement running, because results must still resolve while it is off.
  * Fixtures are fetched in ONE request for every competition the plan allows,
    not one request per league. See `wakamaria.fixtures`.
"""

import time
from datetime import timezone

import frappe
from frappe.utils import convert_utc_to_system_timezone, now_datetime

from wakamaria import ownership

from wakamaria import fixtures as fixture_rules
from wakamaria import model, odds
from wakamaria.agentconfig import resolve as resolve_config
from wakamaria.diagnostics import describe_error as _describe_error
from wakamaria.predictor import choose
from wakamaria.provider import api_get

HISTORY_PREFIX = "wakamaria:history:"
HISTORY_TTL = 6 * 3600
HISTORY_LIMIT = 20
HISTORY_FETCH_BUDGET = 8      # new provider calls per run, spread 7s apart
PROVIDER_PAUSE = 7


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


def _to_local(aware):
    return convert_utc_to_system_timezone(
        aware.astimezone(timezone.utc).replace(tzinfo=None))


def _all_fixtures(horizon, stats=None):
    """Every predictable fixture in the look-ahead, in one provider request."""
    now = now_datetime()
    date_from, date_to = fixture_rules.window(now, horizon)
    data = api_get("/matches", {"dateFrom": str(date_from), "dateTo": str(date_to)})
    selected, counters = fixture_rules.select(
        data.get("matches"), now, horizon, to_local=_to_local)
    if stats is not None:
        stats.update(counters)
    return selected


def _run(settings):
    config = resolve_config(settings)
    horizon = config["horizon_hours"]
    max_per_run = config["max_per_run"]
    min_confidence = config["min_confidence"]
    max_confidence = config["max_confidence"]
    family_cap = config["family_cap"]
    margin = config["margin"]

    created = skipped = unconfigured = adopted = 0
    used_families = {}
    used_tips = {}
    budget = {"fetches": 0}
    today_used = _created_today()
    failed = []

    leagues = {
        str(league.provider_code).upper(): league
        for league in frappe.get_all(
            "Wakamaria League",
            filters={"enabled": 1, "provider_code": ["is", "set"]},
            fields=["name", "league_name", "provider_code"],
        )
    }

    try:
        upcoming = _all_fixtures(horizon)
    except Exception as error:
        return (f"Fixture fetch failed: {_describe_error(error)}. "
                f"horizon={horizon}h")

    stop_reason = ""
    if not upcoming:
        stop_reason = "no fixtures in the look-ahead window"

    for fixture in upcoming:
        if created >= max_per_run:
            stop_reason = f"run cap reached ({max_per_run}/run)"
            break
        if today_used + created >= config["max_per_day"]:
            stop_reason = (f"daily cap reached "
                           f"({today_used} already created today, "
                           f"limit {config['max_per_day']})")
            break

        league = leagues.get(fixture["competition_code"])
        if not league:
            # The competition has fixtures but no enabled League record. The
            # diagnostic names these so the operator can add them.
            unconfigured += 1
            continue

        try:
            published = _publish_fixture(
                settings, league, fixture, budget,
                min_confidence=min_confidence,
                max_confidence=max_confidence,
                family_cap=family_cap,
                used_families=used_families,
                used_tips=used_tips,
                margin=margin,
            )
        except Exception as error:
            frappe.log_error(
                title="Wakamaria agent fixture skipped",
                message=f"{league.name}: fixture {fixture.get('id')}. "
                        f"{_describe_error(error)}",
            )
            failed.append(f"{fixture['competition_code']}: {_describe_error(error)}")
            skipped += 1
            continue

        if published:
            created += 1
            if published.get("adopted"):
                adopted += 1
        else:
            skipped += 1

    frappe.db.commit()
    summary = (f"Created {created} prediction(s), skipped {skipped}, "
               f"unconfigured {unconfigured}"
               + (f", adopted {adopted} hand-entered row(s)" if adopted else "")
               + ". "
               f"horizon={horizon}h band={min_confidence:.2f}-{max_confidence:.2f} "
               f"cap={max_per_run}/run,{config['max_per_day']}/day,"
               f"{today_used} already today "
               f"margin={margin:.2f}"
               f" | stop: {stop_reason or 'all fixtures handled'}")
    if failed:
        summary += " | errors: " + "; ".join(failed)[:250]
    return summary


def _publish_fixture(settings, league, fixture, budget, *, min_confidence,
                     max_confidence, family_cap, used_families, used_tips,
                     margin):
    """Publish the agent's prediction for one fixture.

    Returns {"name", "adopted"} or None when there is nothing to publish.
    A hand-entered row is *adopted*, not duplicated: its prediction is replaced
    and it gains a provider id, which is what finally lets its result settle.
    Two rows for one fixture is the bug this prevents.
    """
    action = ownership.decide(_existing_row(league, fixture))
    if action == "skip":
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
        used_tips=used_tips,
    )
    if not choice or not choice.get("odds"):
        return None

    fields = {
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
    }

    if action == "adopt":
        row = _existing_row(league, fixture)
        doc = frappe.get_doc("Wakamaria Match", row["name"])
        doc.update(fields)
        doc.save(ignore_permissions=True)
    else:
        doc = frappe.get_doc({"doctype": "Wakamaria Match", **fields})
        doc.insert(ignore_permissions=True)
    used_families[choice["family"]] = used_families.get(choice["family"], 0) + 1
    used_tips[choice["tip"]] = used_tips.get(choice["tip"], 0) + 1
    return {"name": doc.name, "adopted": action == "adopt"}


def _existing_row(league, fixture):
    """The row already on the site for this fixture, as a dict, or None.

    Two identities are checked because the site holds two kinds of row: ones the
    agent created (provider id present) and ones typed or imported by hand (no
    provider id, matched loosely on league, teams and kickoff).
    """
    fields = ["name", "provider_match_id", "predicted_by"]

    linked = frappe.db.get_value(
        "Wakamaria Match", {"provider_match_id": fixture["id"]}, fields, as_dict=True)
    if linked:
        return linked

    return frappe.db.get_value("Wakamaria Match", {
        "league": league.name,
        "home_team": fixture["home_name"],
        "away_team": fixture["away_name"],
        "kickoff": fixture["kickoff"],
    }, fields, as_dict=True)


def _history(team_id, budget):
    """Recent finished matches for a team, read from the cache `sync.py` fills."""
    key = HISTORY_PREFIX + str(team_id)
    cached = frappe.cache().get_value(key)
    if cached is not None:
        return cached
    if budget["fetches"] >= HISTORY_FETCH_BUDGET:
        return []

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
    """How many agent predictions already exist today.

    Compared as "YYYY-MM-DD 00:00:00", not as a datetime object: the object
    form did not reliably match the stored column, which let the daily cap
    overshoot (24 published against a limit of 20).
    """
    start = f"{now_datetime().date()} 00:00:00"
    return frappe.db.count("Wakamaria Match", {
        "predicted_by": "Agent",
        "creation": [">=", start],
    })


def seed_leagues(enable=1):
    """Create a League for every competition your plan can access.

        bench --site <site> execute wakamaria.agent.seed_leagues

    Idempotent: a competition whose code already exists is left untouched, so
    re-running never overwrites a name, image or enabled flag you set by hand.

    football-data.org only lists competitions your token is entitled to, so this
    cannot import a league you would then get 403 on.
    """
    data = api_get("/competitions", {})
    existing = {
        str(row.provider_code).upper(): row
        for row in frappe.get_all("Wakamaria League",
                                  fields=["name", "provider_code"])
        if row.provider_code
    }

    created, skipped = 0, 0
    for competition in data.get("competitions") or []:
        code = str(competition.get("code") or "").upper()
        name = competition.get("name") or ""
        if not code or not name:
            # Cups and one-off competitions often carry no stable code.
            skipped += 1
            continue
        if code in existing:
            skipped += 1
            continue
        frappe.get_doc({
            "doctype": "Wakamaria League",
            "league_name": name,
            "country": (competition.get("area") or {}).get("name") or "",
            "provider_code": code,
            "enabled": 1 if int(enable) else 0,
        }).insert(ignore_permissions=True)
        created += 1

    frappe.db.commit()
    print(f"Created {created} league(s), skipped {skipped} "
          f"(already present or had no code).")
    print("Run wakamaria.agent.diagnose next to see which now have fixtures.")


def diagnose():
    """Explain why the agent is, or is not, creating predictions.

        bench --site <site> execute wakamaria.agent.diagnose

    Prints line by line rather than returning one joined string, because
    `bench execute` renders a returned string with escaped newlines.
    """
    settings = frappe.get_single("Wakamaria Settings")
    config = resolve_config(settings)
    key = settings.get_password("api_key", raise_exception=False)

    def say(text=""):
        print(text)

    say(f"result sync enabled : {bool(settings.get('enabled'))}")
    say(f"football-data key   : {'set' if key else 'MISSING'}")
    say(f"agent enabled       : {bool(settings.get('agent_enabled'))}")
    say(f"agent paused        : {bool(settings.get('agent_paused'))}")
    say(f"resolved config     : horizon={config['horizon_hours']}h "
        f"band={config['min_confidence']}-{config['max_confidence']} "
        f"cap={config['max_per_run']}/run")
    used_today = _created_today()
    say(f"agent picks today   : {used_today} of {config['max_per_day']} allowed"
        + ("  <-- at the cap, nothing more will publish today"
           if used_today >= config["max_per_day"] else ""))
    say()

    leagues = frappe.get_all(
        "Wakamaria League", filters={"enabled": 1},
        fields=["name", "league_name", "provider_code"], order_by="league_name asc",
    )
    coded = {str(le.provider_code).upper(): le for le in leagues if le.provider_code}
    say(f"enabled leagues     : {len(leagues)}")
    say(f"with provider_code  : {len(coded)}")
    for league in leagues:
        if not league.provider_code:
            say(f"  - {league.league_name}: no provider_code, invisible to the agent")
    say()

    stats = {}
    try:
        upcoming = _all_fixtures(config["horizon_hours"], stats)
    except Exception as error:
        say(f"fixture fetch failed: {_describe_error(error)}")
        return

    say(f"provider returned   : {stats.get('returned', 0)} match(es), "
        f"usable {len(upcoming)} "
        f"(started {stats.get('past', 0)}, "
        f"beyond {config['horizon_hours']}h {stats.get('beyond_horizon', 0)}, "
        f"wrong status {stats.get('not_predictable', 0)})")
    say()

    grouped = fixture_rules.group_by_competition(upcoming)
    if not grouped:
        say("No competition has a fixture inside the look-ahead window.")
        say("Raise Look-ahead (hours) if you expected some.")
        return

    say("competitions with usable fixtures:")
    for code, rows in sorted(grouped.items(), key=lambda kv: -len(kv[1])):
        league = coded.get(code)
        if league:
            say(f"  OK   {code:<5} {league.league_name}: {len(rows)} fixture(s)")
        else:
            name = rows[0].get("competition_name") or code
            say(f"  MISS {code:<5} {name}: {len(rows)} fixture(s) "
                f"-> no enabled League record, add one")

    missing = sorted(set(coded) - set(grouped))
    if missing:
        say()
        say("configured but nothing in the window: " + ", ".join(missing))


def _tripped(settings):
    """Optional circuit breaker. Zero means off — the agent keeps publishing."""
    threshold = resolve_config(settings)["pause_after_losses"]
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
