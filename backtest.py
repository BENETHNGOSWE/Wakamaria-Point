"""Chronological backtester for the prediction model.

Every match is predicted using only matches that finished before it. Nothing
from the future is visible, so a number that comes out of here is an honest
estimate of what the site would have published on that day.

Run it directly for a comparison table:

    python3 backtest.py

The variants are stacked, cheapest first, so each row shows what that one
change actually bought:

    v0  what the site does today
    v1  + per-competition goal baselines
    v2  + opponent-adjusted attack and defence
    v3  + time decay on recent form
    v4  + Dixon-Coles low-score correction
"""

from __future__ import annotations

import csv
import datetime as dt
import glob
import math
import os
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "backtest_data")

HOME_SHARE = 0.55
SHRINKAGE = 5.0
HALF_LIFE_DAYS = 90.0
RHO = -0.08
MAX_GOALS = 10
GRID = range(MAX_GOALS + 1)

# Fallback when a competition has no usable history yet.
DEFAULT_LEAGUE_AVG = 2.65

MARKETS = [
    "1", "X", "2", "1X", "X2", "12",
    "Over 1.5", "Over 2.5", "Over 3.5", "Over 4.5",
    "Under 1.5", "Under 2.5", "Under 3.5", "Under 4.5",
    "BTTS Yes", "BTTS No",
    "Home Over 1.5", "Away Over 1.5",
    "1 & BTTS Yes",
]


def outcome(market: str, hg: int, ag: int) -> bool:
    total = hg + ag
    return {
        "1": hg > ag,
        "X": hg == ag,
        "2": ag > hg,
        "1X": hg >= ag,
        "X2": ag >= hg,
        "12": hg != ag,
        "Over 1.5": total > 1,
        "Over 2.5": total > 2,
        "Over 3.5": total > 3,
        "Over 4.5": total > 4,
        "Under 1.5": total < 2,
        "Under 2.5": total < 3,
        "Under 3.5": total < 4,
        "Under 4.5": total < 5,
        "BTTS Yes": hg > 0 and ag > 0,
        "BTTS No": hg == 0 or ag == 0,
        "Home Over 1.5": hg > 1,
        "Away Over 1.5": ag > 1,
        "1 & BTTS Yes": hg > ag and hg > 0 and ag > 0,
    }[market]


# --------------------------------------------------------------------------
# data
# --------------------------------------------------------------------------

def load_matches(paths=None):
    """Read football-data.co.uk season files into one chronological list."""
    if paths is None:
        paths = sorted(glob.glob(os.path.join(DATA, "*.csv")))
    matches = []
    for path in paths:
        country = os.path.basename(path).split("_")[0]
        season = os.path.basename(path).split("_")[1].split(".")[0]
        with open(path, encoding="utf-8-sig") as fh:
            for row in csv.DictReader(fh):
                try:
                    hg, ag = int(row["FTHG"]), int(row["FTAG"])
                    date = dt.datetime.strptime(row["Date"].strip(), "%d/%m/%Y").date()
                except (KeyError, ValueError, TypeError, AttributeError):
                    continue
                matches.append({
                    "date": date,
                    "league": country,
                    "season": season,
                    "home": row["HomeTeam"].strip(),
                    "away": row["AwayTeam"].strip(),
                    "hg": hg,
                    "ag": ag,
                })
    matches.sort(key=lambda m: (m["date"], m["league"]))
    return matches


# --------------------------------------------------------------------------
# rating engine
# --------------------------------------------------------------------------

class Ratings:
    """Running attack/defence ratings for one competition.

    `weight()` decays old matches so current form counts more. `rate()`
    shrinks toward the mean so a short season cannot invent an extreme team,
    and divides goals by the strength of the opponents faced so beating weak
    sides does not pay as much as beating strong ones.
    """

    WINDOW_DAYS = 540  # older matches are below 1.6% weight; drop them

    def __init__(self, opponent_adjusted=True, decay=True, shrinkage=SHRINKAGE,
                 last_n=None):
        self.opponent_adjusted = opponent_adjusted
        self.decay = decay
        self.shrinkage = shrinkage
        self.last_n = last_n  # production only sees the last 20 results
        self.history = defaultdict(list)  # team -> [(date, gf, ga, opponent, home)]
        self._cache_date = None
        self._cache = None

    def add(self, match):
        d = match["date"]
        self.history[match["home"]].append((d, match["hg"], match["ag"], match["away"], True))
        self.history[match["away"]].append((d, match["ag"], match["hg"], match["home"], False))
        if self.last_n:
            for team in (match["home"], match["away"]):
                if len(self.history[team]) > self.last_n:
                    del self.history[team][0]

    def league_averages(self, as_of):
        """Home and away goals per game in this competition, decayed."""
        fh = fa = w = 0.0
        for team_matches in self.history.values():
            for d, gf, ga, _opp, home in team_matches:
                weight = self.weight(d, as_of)
                fh += gf * weight
                fa += ga * weight
                w += weight
        if not w:
            return DEFAULT_LEAGUE_AVG * 0.55, DEFAULT_LEAGUE_AVG * 0.45
        # every match appears twice (once per team), so halve the weight
        return fh / w, fa / w

    def weight(self, date, as_of):
        if not self.decay:
            return 1.0
        age = (as_of - date).days
        return 0.5 ** (max(age, 0) / HALF_LIFE_DAYS)

    def rate(self, as_of):
        """Return {team: (attack, defence)} with 1.0 meaning an average side."""
        if self._cache_date == as_of and self._cache is not None:
            return self._cache
        rated = self._rate(as_of)
        self._cache_date, self._cache = as_of, rated
        return rated

    def _prune(self, as_of):
        cutoff = as_of - dt.timedelta(days=self.WINDOW_DAYS)
        for team, team_matches in list(self.history.items()):
            if team_matches and team_matches[0][0] < cutoff:
                self.history[team] = [m for m in team_matches if m[0] >= cutoff]

    def _rate(self, as_of):
        self._prune(as_of)
        avg_h, avg_a = self.league_averages(as_of)
        league_avg = avg_h + avg_a
        per_team = league_avg / 2.0
        if per_team <= 0:
            return {}

        attack = {t: 1.0 for t in self.history}
        defence = {t: 1.0 for t in self.history}

        passes = 3 if self.opponent_adjusted else 1
        for _ in range(passes):
            for team, team_matches in self.history.items():
                f, a, w = 0.0, 0.0, 0.0
                for d, gf, ga, opp, home in team_matches:
                    weight = self.weight(d, as_of)
                    scale_for = (avg_h if home else avg_a) / per_team
                    scale_ag = (avg_a if home else avg_h) / per_team
                    if self.opponent_adjusted:
                        f += weight * gf / max(defence[opp] * scale_for, 0.25)
                        a += weight * ga / max(attack[opp] * scale_ag, 0.25)
                    else:
                        f += weight * gf
                        a += weight * ga
                    w += weight
                if not w:
                    continue
                s = self.shrinkage
                if self.opponent_adjusted:
                    raw_f, raw_a = f / w, a / w
                else:
                    # exactly what model.team_rates does: goals per game,
                    # divided by the average goals a side scores per game
                    raw_f, raw_a = (f / w) / per_team, (a / w) / per_team
                attack[team] = (raw_f * w + 1.0 * s) / (w + s)
                defence[team] = (raw_a * w + 1.0 * s) / (w + s)
            # keep the competition centred on 1.0
            fa_mean = sum(attack.values()) / len(attack)
            fd_mean = sum(defence.values()) / len(defence)
            if fa_mean > 0 and fd_mean > 0:
                for t in attack:
                    attack[t] /= math.hypot(fa_mean, fd_mean)
                    defence[t] /= math.hypot(fa_mean, fd_mean)
        return {t: (attack[t], defence[t]) for t in attack}


# --------------------------------------------------------------------------
# scoreline model
# --------------------------------------------------------------------------

def _poisson(k, lam):
    return math.exp(-lam) * lam ** k / math.factorial(k)


def score_grid(home_goals, away_goals, rho=0.0):
    """Poisson grid, optionally with the Dixon-Coles low-score correction."""
    grid = {}
    for h in GRID:
        for a in GRID:
            grid[(h, a)] = _poisson(h, home_goals) * _poisson(a, away_goals)
    if rho:
        for (h, a) in [(0, 0), (0, 1), (1, 0), (1, 1)]:
            if h == 0 and a == 0:
                tau = 1 - home_goals * away_goals * rho
            elif h == 0 and a == 1:
                tau = 1 + home_goals * rho
            elif h == 1 and a == 0:
                tau = 1 + away_goals * rho
            else:
                tau = 1 - rho
            grid[(h, a)] = max(grid[(h, a)] * tau, 0.0)
    total = sum(grid.values())
    return {k: v / total for k, v in grid.items()}


def market_probabilities(grid):
    probs = {m: 0.0 for m in MARKETS}
    for (h, a), p in grid.items():
        for m in MARKETS:
            if outcome(m, h, a):
                probs[m] += p
    return probs


def expected_goals(home_rating, away_rating, league_avg, home_share=HOME_SHARE):
    ha, hd = home_rating
    aa, ad = away_rating
    lam_h = ha * ad * league_avg * home_share
    lam_a = aa * hd * league_avg * (1 - home_share)
    clamp = lambda v: min(max(v, 0.40), 2.80)
    return clamp(lam_h), clamp(lam_a)


# --------------------------------------------------------------------------
# walk-forward
# --------------------------------------------------------------------------

VARIANTS = [
    {"name": "v0 current", "per_league": False, "opponent_adjusted": False,
     "decay": False, "rho": 0.0, "last_n": 20},
    {"name": "v1 per-league", "per_league": True, "opponent_adjusted": False,
     "decay": False, "rho": 0.0, "last_n": 20},
    {"name": "v2 +opponent", "per_league": True, "opponent_adjusted": True,
     "decay": False, "rho": 0.0},
    {"name": "v3 +decay", "per_league": True, "opponent_adjusted": True,
     "decay": True, "rho": 0.0},
    {"name": "v4 +dixon-coles", "per_league": True, "opponent_adjusted": True,
     "decay": True, "rho": RHO},
]


def run(matches, variant, warmup_per_league=1):
    """Walk forward through history, predicting each match from the past only."""
    engines = defaultdict(lambda: Ratings(
        opponent_adjusted=variant["opponent_adjusted"], decay=variant["decay"],
        last_n=variant.get("last_n")))
    played = defaultdict(int)
    records = []

    for match in matches:
        league = match["league"]
        impl = engines[league] if variant["per_league"] else engines["ALL"]
        key = league if variant["per_league"] else "ALL"

        # a new competition starts its own history
        if variant["per_league"]:
            impl, key = engines[league], league
        else:
            impl = engines["ALL"]

        if played[key] >= warmup_per_league:
            ratings = impl.rate(match["date"])
            home = ratings.get(match["home"], (1.0, 1.0))
            away = ratings.get(match["away"], (1.0, 1.0))
            avg_h, avg_a = impl.league_averages(match["date"])
            league_avg = avg_h + avg_a
            if not variant["per_league"]:
                league_avg = DEFAULT_LEAGUE_AVG
            share = avg_h / (avg_h + avg_a) if (avg_h + avg_a) else HOME_SHARE
            if not variant["per_league"]:
                share = HOME_SHARE
            lam_h, lam_a = expected_goals(home, away, league_avg, share)
            probs = market_probabilities(score_grid(lam_h, lam_a, variant["rho"]))

            tip = max(probs, key=probs.get)
            confidence = probs[tip]
            hit = outcome(tip, match["hg"], match["ag"])
            rps = _rps(probs, match["hg"], match["ag"])
            records.append({
                "league": league, "season": match["season"], "date": match["date"],
                "tip": tip, "confidence": confidence, "hit": hit,
                "lam_h": lam_h, "lam_a": lam_a, "rps": rps,
                "probs": probs, "hg": match["hg"], "ag": match["ag"],
            })

        impl.add(match)
        played[key] += 1

    return records


def _rps(probs, hg, ag):
    """Ranked probability score over the three-way result."""
    actual = [1.0 if hg > ag else 0.0, 1.0 if hg == ag else 0.0, 1.0 if ag > hg else 0.0]
    predicted = [probs["1"], probs["X"], probs["2"]]
    cumulative_p = cumulative_a = total = 0.0
    for i in range(2):
        cumulative_p += predicted[i]
        cumulative_a += actual[i]
        total += (cumulative_p - cumulative_a) ** 2
    return total / 2


def summarise(records):
    n = len(records)
    if not n:
        return {}
    hits = sum(r["hit"] for r in records)
    conf = sum(r["confidence"] for r in records) / n
    logloss = -sum(
        math.log(max(r["probs"][r["tip"]], 1e-9)) if r["hit"]
        else math.log(max(1 - r["probs"][r["tip"]], 1e-9))
        for r in records) / n
    # Brier over the chosen market
    brier = sum((r["probs"][r["tip"]] - (1.0 if r["hit"] else 0.0)) ** 2
                for r in records) / n
    return {
        "n": n,
        "hit": hits,
        "accuracy": hits / n,
        "claimed": conf,
        "gap": conf - hits / n,
        "logloss": logloss,
        "brier": brier,
        "rps": sum(r["rps"] for r in records) / n,
    }


def compare(matches):
    print(f"{'variant':<20}{'picks':>7}{'correct':>9}{'hit rate':>10}"
          f"{'claimed':>9}{'gap':>7}{'logloss':>9}{'RPS':>8}")
    print("-" * 79)
    results = {}
    for variant in VARIANTS:
        records = run(matches, variant)
        stats = summarise(records)
        results[variant["name"]] = (stats, records)
        print(f"{variant['name']:<20}{stats['n']:>7}{stats['hit']:>9}"
              f"{stats['accuracy']:>9.1%}{stats['claimed']:>9.1%}"
              f"{stats['gap']:>+7.1%}{stats['logloss']:>9.4f}{stats['rps']:>8.4f}")
    return results


def breakdown(records, by="league"):
    groups = defaultdict(list)
    for r in records:
        groups[r[by]].append(r)
    print(f"\n{'group':<10}{'picks':>7}{'hit rate':>10}{'claimed':>9}")
    print("-" * 36)
    for name in sorted(groups):
        stats = summarise(groups[name])
        print(f"{name:<10}{stats['n']:>7}{stats['accuracy']:>9.1%}{stats['claimed']:>9.1%}")


def per_market(records):
    groups = defaultdict(list)
    for r in records:
        groups[r["tip"]].append(r)
    print(f"\n{'market':<16}{'picks':>7}{'hit rate':>10}{'claimed':>9}")
    print("-" * 42)
    for name, rs in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        stats = summarise(rs)
        print(f"{name:<16}{stats['n']:>7}{stats['accuracy']:>9.1%}{stats['claimed']:>9.1%}")


if __name__ == "__main__":
    matches = load_matches()
    print(f"{len(matches)} matches, "
          f"{matches[0]['date']} to {matches[-1]['date']}\n")
    results = compare(matches)
    best = results[VARIANTS[-1]["name"]][1]
    breakdown(best, "league")
    per_market(best)
