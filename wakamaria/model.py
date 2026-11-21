"""Poisson scoreline model used to price every market.

Pure Python: no Frappe, no network, no clock, no database. Everything here is a
function of its arguments, which is what makes the 11 market prices testable.

The idea is the standard one. Estimate each side's attack and defence strength
from recent results, turn the pair into an expected-goals figure per team,
then read every market off the resulting scoreline distribution. Small samples
are pulled toward the league mean so that two lucky games do not produce a
4.20 favourite.
"""

from math import exp, factorial

from wakamaria.tips import TIPS

MAX_GOALS = 10          # scoreline grid is 0..10 for each side
DEFAULT_LEAGUE_AVG = 2.65
HOME_SHARE = 0.55       # home side scores ~55% of the goals in an average game
SHRINKAGE = 5.0         # pseudo-matches pulling a short sample back to the mean
LAMBDA_FLOOR = 0.15     # never price a side at less than this expected goals
LAMBDA_CEIL = 4.50
DEFAULT_MARGIN = 0.06   # 6% theoretical bookmaker margin on model prices


def _poisson(k, lam):
    return exp(-lam) * lam ** k / factorial(k)


def score_matrix(home_lambda, away_lambda, max_goals=MAX_GOALS):
    """matrix[home_goals][away_goals] -> probability."""
    home = [_poisson(i, home_lambda) for i in range(max_goals + 1)]
    away = [_poisson(i, away_lambda) for i in range(max_goals + 1)]
    return [[home[h] * away[a] for a in range(max_goals + 1)]
            for h in range(max_goals + 1)]


def probabilities(matrix):
    """Turn a scoreline grid into a probability for every supported market."""
    size = len(matrix)
    out = {tip: 0.0 for tip in TIPS}
    for h in range(size):
        for a in range(size):
            q = matrix[h][a]
            total = h + a
            if h > a:
                out["1"] += q
            if h == a:
                out["X"] += q
            if a > h:
                out["2"] += q
            if h >= a:
                out["1X"] += q
            if a >= h:
                out["X2"] += q
            if h != a:
                out["12"] += q
            if total > 1:
                out["Over 1.5"] += q
            if total > 2:
                out["Over 2.5"] += q
            if total > 3:
                out["Over 3.5"] += q
            if total < 3:
                out["Under 2.5"] += q
            if total < 4:
                out["Under 3.5"] += q
            if h > 0 and a > 0:
                out["BTTS Yes"] += q
            if h == 0 or a == 0:
                out["BTTS No"] += q
    return out


def _is_home(entry, team_id, team_name):
    """Prefer provider IDs; fall back to the team name when an old cache has none."""
    home_id, away_id = entry.get("home_id"), entry.get("away_id")
    if team_id and home_id and away_id:
        return str(home_id) == str(team_id)
    return bool(team_name) and entry.get("home") == team_name


def team_rates(entries, team_id=None, team_name=None,
               league_avg=DEFAULT_LEAGUE_AVG, shrinkage=SHRINKAGE):
    """(attack, defence) multipliers where 1.0 is an average side.

    Each entry is {"home", "away", "score": [h, a]} plus optional home_id /
    away_id. Unplayed, abandoned or malformed rows are skipped rather than
    counted as 0-0.
    """
    scored = conceded = 0.0
    played = 0
    for entry in entries or []:
        score = entry.get("score") or []
        if len(score) != 2:
            continue
        home_goals, away_goals = score
        # bool is a subclass of int; a stray True must not be read as one goal.
        if type(home_goals) is not int or type(away_goals) is not int:
            continue
        if home_goals < 0 or away_goals < 0:
            continue
        if _is_home(entry, team_id, team_name):
            scored += home_goals
            conceded += away_goals
        elif _is_home({"home": entry.get("away"), "home_id": entry.get("away_id"),
                       "away_id": entry.get("home_id")}, team_id, team_name):
            scored += away_goals
            conceded += home_goals
        else:
            continue
        played += 1

    per_team = league_avg / 2.0
    if per_team <= 0:
        return 1.0, 1.0
    attack = (scored + per_team * shrinkage) / ((played + shrinkage) * per_team)
    defence = (conceded + per_team * shrinkage) / ((played + shrinkage) * per_team)
    return attack, defence


def _clamp(value):
    return min(max(value, LAMBDA_FLOOR), LAMBDA_CEIL)


def expected_goals(home_rates, away_rates, league_avg=DEFAULT_LEAGUE_AVG,
                   home_share=HOME_SHARE):
    home_attack, home_defence = home_rates
    away_attack, away_defence = away_rates
    home_lambda = home_attack * away_defence * league_avg * home_share
    away_lambda = away_attack * home_defence * league_avg * (1.0 - home_share)
    return _clamp(home_lambda), _clamp(away_lambda)


def predict(home_entries, away_entries, *, home_id=None, home_name=None,
            away_id=None, away_name=None, league_avg=DEFAULT_LEAGUE_AVG,
            home_strength=None, away_strength=None):
    """Full prediction for one fixture.

    Returns {"probabilities": {...}, "home_lambda": float, "away_lambda": float}.

    `home_strength` / `away_strength` are (attack, defence) multipliers taken
    from the league table, used only when a side has no recent results. Without
    them a team with an empty cache is indistinguishable from every other team,
    which is how Real Madrid at home ended up tipped to "draw or lose".
    """
    home_rates = (team_rates(home_entries, home_id, home_name, league_avg)
                  if home_entries else (home_strength or (1.0, 1.0)))
    away_rates = (team_rates(away_entries, away_id, away_name, league_avg)
                  if away_entries else (away_strength or (1.0, 1.0)))
    home_lambda, away_lambda = expected_goals(home_rates, away_rates, league_avg)
    return {
        "probabilities": probabilities(score_matrix(home_lambda, away_lambda)),
        "home_lambda": home_lambda,
        "away_lambda": away_lambda,
    }


def fair_odds(probability):
    """The break-even price for a probability: no margin, no edge."""
    if not probability or probability <= 0:
        return None
    return round(1.0 / probability, 2)


def market_odds(probability, margin=DEFAULT_MARGIN):
    """A price shorter than fair by `margin`, the way a bookmaker would post it.

    These are Wakamaria's own estimates. They are labelled as such on the site
    and never presented as a bookmaker's live board.
    """
    if not probability or probability <= 0:
        return None
    price = 1.0 / (probability * (1.0 + margin))
    return round(max(price, 1.01), 2)
