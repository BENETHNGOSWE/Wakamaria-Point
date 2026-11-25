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
# Home advantage is NOT a constant. It is measured from the two teams' own
# results for every fixture (see `league_split` and `team_venue_rates`).
# HOME_SHARE survives only as the fallback when neither side has any result.
HOME_SHARE = 0.55
SHRINKAGE = 5.0         # pseudo-matches pulling a short sample back to the mean
LAMBDA_FLOOR = 0.15     # never price a side at less than this expected goals
LAMBDA_CEIL = 4.50      # nor more than this, however lopsided the table
RATING_FLOOR = 0.30     # a side cannot be weaker than this against the average
RATING_CEIL = 3.20      # nor stronger. Wide on purpose: a real mismatch must be
                        # expressible, or the model can never fancy an away win
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
            if total > 4:
                out["Over 4.5"] += q
            if total < 2:
                out["Under 1.5"] += q
            if total < 3:
                out["Under 2.5"] += q
            if total < 4:
                out["Under 3.5"] += q
            if h > 1:
                out["Home Over 1.5"] += q
            if a > 1:
                out["Away Over 1.5"] += q
            if h > 0 and a > 0:
                out["BTTS Yes"] += q
            if h > a and h > 0 and a > 0:
                out["1 & BTTS Yes"] += q
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


def _clamp_rating(value):
    return min(max(value, RATING_FLOOR), RATING_CEIL)


def _venue_totals(entries):
    """(home goals, away goals, matches) across a set of result entries."""
    home_goals = away_goals = 0.0
    matches = 0
    for entry in entries or []:
        score = entry.get("score") or []
        if len(score) != 2:
            continue
        hg, ag = score
        if type(hg) is not int or type(ag) is not int or hg < 0 or ag < 0:
            continue
        home_goals += hg
        away_goals += ag
        matches += 1
    return home_goals, away_goals, matches


def league_split(*entry_groups, fallback_share=HOME_SHARE):
    """Average home and away goals, measured from the teams in this fixture.

    This is where home advantage now comes from. Two sides whose recent
    matches averaged 1.6 goals at home and 1.1 away produce a bigger home edge
    than two sides that averaged 1.3 and 1.25. In a league that scores evenly
    the edge nearly vanishes, and a strong away side faces no preset handicap.
    """
    home_goals = away_goals = 0.0
    matches = 0
    for entries in entry_groups:
        hg, ag, n = _venue_totals(entries)
        home_goals += hg
        away_goals += ag
        matches += n
    if matches < 2:
        total = DEFAULT_LEAGUE_AVG
        return total * fallback_share, total * (1.0 - fallback_share)
    seen_home = home_goals / matches
    seen_away = away_goals / matches
    if seen_home + seen_away <= 0:
        return DEFAULT_LEAGUE_AVG * fallback_share, DEFAULT_LEAGUE_AVG * (1 - fallback_share)
    # Keep the observed home/away RATIO, but rescale to the league average so a
    # run of unusually high or low scoring does not move the goal level.
    share = seen_home / (seen_home + seen_away)
    avg_home = DEFAULT_LEAGUE_AVG * share
    return max(avg_home, 0.35), max(DEFAULT_LEAGUE_AVG - avg_home, 0.35)


def team_venue_rates(entries, team_id=None, team_name=None,
                     avg_home=None, avg_away=None, shrinkage=SHRINKAGE):
    """(attack_home, defence_home, attack_away, defence_away).

    Home and away records are rated separately, so a side that wins at home and
    loses on the road is not treated as the same team in both. 1.0 is an
    average side in that venue.
    """
    if avg_home is None or avg_away is None:
        avg_home, avg_away = league_split(entries)

    totals = {"home": [0.0, 0.0, 0.0], "away": [0.0, 0.0, 0.0]}
    for entry in entries or []:
        score = entry.get("score") or []
        if len(score) != 2:
            continue
        hg, ag = score
        if type(hg) is not int or type(ag) is not int or hg < 0 or ag < 0:
            continue
        if _is_home(entry, team_id, team_name):
            for_goals, against = hg, ag
            venue = "home"
        elif _is_home({"home": entry.get("away"), "home_id": entry.get("away_id"),
                       "away_id": entry.get("home_id")}, team_id, team_name):
            for_goals, against = ag, hg
            venue = "away"
        else:
            continue
        totals[venue][0] += for_goals
        totals[venue][1] += against
        totals[venue][2] += 1

    def rate(scored, conceded, played, scoring_avg, conceding_avg, prior):
        if played <= 0:
            # No results in this venue: the team's overall form is a far better
            # guess than "exactly average", which would throw its quality away.
            return prior
        attack = (scored + scoring_avg * shrinkage) / ((played + shrinkage) * scoring_avg)
        defence = ((conceded + conceding_avg * shrinkage)
                   / ((played + shrinkage) * conceding_avg))
        return _clamp_rating(attack), _clamp_rating(defence)

    prior = team_rates(entries, team_id, team_name,
                       league_avg=avg_home + avg_away, shrinkage=shrinkage)
    atk_h, def_h = rate(totals["home"][0], totals["home"][1], totals["home"][2],
                        avg_home, avg_away, prior)
    atk_a, def_a = rate(totals["away"][0], totals["away"][1], totals["away"][2],
                        avg_away, avg_home, prior)
    return atk_h, def_h, atk_a, def_a


def expected_goals(home_rates, away_rates, league_avg=DEFAULT_LEAGUE_AVG,
                   home_share=HOME_SHARE):
    """Expected goals for each side.

    `*_rates` may be either the old two-tuple (attack, defence), in which case
    the league-wide home share applies, or the four-tuple produced by
    `team_venue_rates`, in which case the split comes from the teams
    themselves and `home_share` is ignored.
    """
    if len(home_rates) == 4 or len(away_rates) == 4:
        atk_h, def_h = home_rates[0], home_rates[1]
        atk_a, def_a = away_rates[2], away_rates[3]
        avg_home, avg_away = league_split_of(home_rates, away_rates, league_avg)
        return _clamp(atk_h * def_a * avg_home), _clamp(atk_a * def_h * avg_away)

    home_attack, home_defence = home_rates
    away_attack, away_defence = away_rates
    home_lambda = home_attack * away_defence * league_avg * home_share
    away_lambda = away_attack * home_defence * league_avg * (1.0 - home_share)
    return _clamp(home_lambda), _clamp(away_lambda)


def league_split_of(home_rates, away_rates, league_avg=DEFAULT_LEAGUE_AVG):
    """The home/away split carried alongside a venue-rate pair."""
    split = getattr(home_rates, "split", None)
    if split:
        return split
    return league_avg * HOME_SHARE, league_avg * (1.0 - HOME_SHARE)


def predict(home_entries, away_entries, *, home_id=None, home_name=None,
            away_id=None, away_name=None, league_avg=DEFAULT_LEAGUE_AVG,
            home_strength=None, away_strength=None):
    """Full prediction for one fixture.

    Returns {"probabilities": {...}, "home_lambda": float, "away_lambda": float}.

    Home advantage is measured here, per fixture, from the two teams' own home
    and away records (`league_split`). There is no preset 55/45 and therefore
    no preset home edge: a side that is strong away from home, against a host
    with a poor home record, is priced as the favourite.

    `home_strength` / `away_strength` are (attack, defence) multipliers taken
    from the league table, used when a side has no recent results.
    """
    avg_home, avg_away = league_split(home_entries, away_entries,
                                      fallback_share=(avg_home_share(league_avg)))

    def rates(entries, team_id, team_name, strength):
        if entries:
            return team_venue_rates(entries, team_id, team_name,
                                    avg_home=avg_home, avg_away=avg_away)
        attack, defence = strength or (1.0, 1.0)
        return attack, defence, attack, defence

    home_rates = rates(home_entries, home_id, home_name, home_strength)
    away_rates = rates(away_entries, away_id, away_name, away_strength)

    home_lambda = _clamp(home_rates[0] * away_rates[3] * avg_home)
    away_lambda = _clamp(away_rates[2] * home_rates[1] * avg_away)
    return {
        "probabilities": probabilities(score_matrix(home_lambda, away_lambda)),
        "home_lambda": home_lambda,
        "away_lambda": away_lambda,
        "home_share": avg_home / (avg_home + avg_away),
    }


def avg_home_share(league_avg=DEFAULT_LEAGUE_AVG):
    return HOME_SHARE


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
