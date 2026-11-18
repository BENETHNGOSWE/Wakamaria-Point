"""Offline dry run: what would the agent publish for a given card?

No Frappe, no network. Builds synthetic team histories, runs the real model and
the real selector, and prints the result. Use it to sanity-check the pricing
before letting the scheduler publish anything.
"""
import sys, json
sys.path.insert(0, ".")
from wakamaria import model  # noqa: E402
from wakamaria.tips import label  # noqa: E402
from wakamaria.predictor import choose  # noqa: E402

# team -> (goals for, goals against) per game, roughly Premier League shaped
FORM = {
    "Arsenal":      (2.2, 0.8), "Chelsea":  (1.7, 1.3),
    "Liverpool":    (2.4, 1.0), "Everton":  (1.0, 1.6),
    "Man City":     (2.5, 0.9), "Newcastle":(1.5, 1.2),
    "Brighton":     (1.6, 1.5), "Wolves":   (0.9, 1.9),
    "Aston Villa":  (1.8, 1.2), "Fulham":   (1.2, 1.4),
    "Tottenham":    (1.9, 1.6), "Brentford":(1.3, 1.5),
}
CARDS = [
    ("Arsenal", "Chelsea"), ("Liverpool", "Everton"),
    ("Man City", "Newcastle"), ("Brighton", "Wolves"),
    ("Aston Villa", "Fulham"), ("Tottenham", "Brentford"),
]


def history(team, matches=12):
    """A plausible recent record: alternating home/away, goals near the form rate."""
    gf, ga = FORM[team]
    rows = []
    for i in range(matches):
        home = i % 2 == 0
        # deterministic spread around the mean so the sample looks like real form
        swing = [0.0, 0.6, -0.4, 0.9, -0.7][i % 5]
        scored = max(0, round(gf + swing if home else gf - 0.2 + swing))
        conceded = max(0, round(ga - swing if home else ga + 0.2 - swing))
        rows.append({
            "home": team if home else f"Opp{i}", "away": f"Opp{i}" if home else team,
            "home_id": "1" if home else str(100 + i),
            "away_id": str(100 + i) if home else "1",
            "score": [scored, conceded] if home else [conceded, scored],
        })
    return rows


def dry_run():
    out = []
    used = {}
    for home, away in CARDS:
        p = model.predict(history(home), history(away),
                          home_id="1", away_id="2", home_name=home, away_name=away)
        # No bookmaker feed offline, so every price is the model estimate.
        prices = {tip: (model.market_odds(q, 0.06), "Model")
                  for tip, q in p["probabilities"].items()}
        pick = choose(p["probabilities"], prices, min_confidence=0.45,
                      max_confidence=0.66, family_cap=2, used_families=used)
        if not pick:
            continue
        used[pick["family"]] = used.get(pick["family"], 0) + 1
        out.append({
            "home": home, "away": away,
            "lambda": (round(p["home_lambda"], 2), round(p["away_lambda"], 2)),
            "tip": pick["tip"], "label": label(pick["tip"]),
            "odds": pick["odds"], "confidence": pick["confidence"],
            "source": pick["source"], "family": pick["family"],
            "alternatives": sorted(
                ((q, model.market_odds(q, 0.06)) for q in p["probabilities"].values()),
                reverse=True)[:3],
        })
    return out


if __name__ == "__main__":
    rows = dry_run()
    print(f"{'FIXTURE':<28}{'TIP':<12}{'P':>6}{'PRICE':>7}  {'FAMILY':<16}LAMBDAS")
    print("-" * 88)
    for r in rows:
        print(f"{r['home']+' v '+r['away']:<28}{r['tip']:<12}{r['confidence']:>6.2f}"
              f"{r['odds']:>7.2f}  {r['family']:<16}{r['lambda'][0]:.2f}/{r['lambda'][1]:.2f}")
    print()
    families = {}
    for r in rows:
        families[r["family"]] = families.get(r["family"], 0) + 1
    print("family spread:", families)
    print("avg price:", round(sum(r["odds"] for r in rows) / len(rows), 2))
    json.dump(rows, open("/home/user/agent-dryrun.json", "w"), indent=1)
