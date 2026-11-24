"""League tables as team strength — so the model knows Real Madrid is good.

The model was estimating strength only from each team's last N results, fetched
one team at a time. With a per-run budget of eight fetches and seventy fixtures,
most teams arrived with no history at all, fell back to "average", and every
fixture looked identical. That is how Real Madrid, at home, to Celta Vigo,
acquired a tip of "draw or away win": the model had no idea which team was
which.

A league table is the cheapest possible fix. One request per competition
returns goals for, goals against and games played for every team in it — twenty
teams for the price of one call, instead of one call per team.

The conversion is the same arithmetic `model.team_rates` performs, so a table
and a run of recent results produce directly comparable numbers.

Pure: takes a payload, returns a dict. No Frappe, no network.
"""

CACHE_PREFIX = "wakamaria:standings:"
MIN_GAMES = 3.0          # fewer than this and the table means nothing yet
SHRINKAGE = 5.0          # pseudo-matches pulling a short table back to the mean


def _rates(goals_for, goals_against, played, league_avg, shrinkage=SHRINKAGE):
    """(attack, defence) multipliers, 1.0 being an average side.

    Shrunk toward the mean with exactly the arithmetic `model.team_rates` uses
    for recent results. Dividing raw goals by games played — as this did — gives
    a Champions League side with 10 goals in 4 matches an attack rating of 1.89
    with nothing to hold it back. Two such sides meet and the model expects
    eight goals, which is how a page ends up claiming 93% for "2 or more goals".
    """
    per_team = league_avg / 2.0
    if per_team <= 0 or played < MIN_GAMES:
        return None
    attack = (goals_for + per_team * shrinkage) / ((played + shrinkage) * per_team)
    defence = (goals_against + per_team * shrinkage) / ((played + shrinkage) * per_team)
    # Keep an early-season outlier from producing an absurd favourite.
    return (min(max(attack, 0.40), 2.60), min(max(defence, 0.40), 2.60))


def team_strengths(payload, league_avg=2.65):
    """{team_id: (attack, defence)} from a football-data.org standings payload.

    Only the TOTAL table is used; home/away splits exist but are thin, and a
    combined table is the more stable estimate this early in a season.
    """
    strengths = {}
    for standing in (payload or {}).get("standings") or []:
        if str(standing.get("type") or "").upper() != "TOTAL":
            continue
        for row in standing.get("table") or []:
            team = row.get("team") or {}
            team_id = team.get("id")
            if not team_id:
                continue
            try:
                played = float(row.get("playedGames") or 0)
                goals_for = float(row.get("goalsFor") or 0)
                goals_against = float(row.get("goalsAgainst") or 0)
            except (TypeError, ValueError):
                continue
            rates = _rates(goals_for, goals_against, played, league_avg)
            if rates:
                strengths[str(team_id)] = rates
    return strengths


def fetch(provider_get, competition_code, api_key=None, cache=None):
    """Team strengths for one competition, cached for six hours.

    `provider_get(path, params)` is injected so this can be tested without a
    network or a key. A failure returns {} rather than raising: strength data
    improves a prediction, it is not required to make one.
    """
    key = CACHE_PREFIX + str(competition_code).upper()
    if cache is not None:
        cached = cache.get_value(key)
        if cached is not None:
            return cached
    try:
        payload = provider_get(f"/competitions/{competition_code}/standings", {})
        strengths = team_strengths(payload)
    except Exception:
        return {}
    if cache is not None and strengths:
        cache.set_value(key, strengths, expires_in_sec=6 * 3600)
    return strengths
