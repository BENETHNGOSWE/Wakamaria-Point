"""Pick the one market Wakamaria publishes for a fixture, and justify it.

A football site that publishes the highest-probability market every time
publishes the same thing on every row, which is useless to a reader and makes
the list look broken. Worse, when two teams have no history the model returns
identical probabilities for every fixture, so the *same* selection wins every
time and the page becomes one tip repeated forty times.

This module exists to prevent that. Three rules, in order:

  1. Stay inside a probability band, so every pick is worth publishing.
  2. Spread across market families, so a day is not six near-copies.
  3. Break ties by least-used tip, so identical probabilities still rotate.

Pure: no Frappe, no network.
"""

from wakamaria import calibration, model
from wakamaria.tips import TIPS, family

MIN_CONFIDENCE_FLOOR = 0.30

# Every option above this is a candidate. Among those, the one with the best
# price wins: if two outcomes are both near-certain, there is no reason to
# publish the one that returns less. This is not a value bet — nothing below
# the floor can ever be chosen, so a long price alone buys nothing.
CERTAINTY_FLOOR = 0.80

# A tip may not be more than this far below the fixture's single most likely
# market. Variety is worth having; "Real Madrid to not win at home" is not a
# matter of taste and must be impossible to publish.
COHERENCE_GAP = 0.12


def _rank_key(tip, probability, prices, used_tips):
    """Rank a candidate. Higher is better.

    Least-used comes FIRST. Ranking by probability alone concentrates the whole
    run on the single most likely market — forty rows of "Over 1.5" — which is
    the failure this module exists to prevent. Usage first turns the run into a
    round-robin across every eligible market, and probability decides only
    among markets that have been published equally often.

    A bookmaker price can additionally be judged on edge; a model price cannot,
    because it is derived from the same probability and its edge is always
    exactly -margin. That is why the edge is a separate tier and not mixed into
    the probability scale.
    """
    usage = -((used_tips or {}).get(tip, 0))
    entry = (prices or {}).get(tip)
    if entry and entry[1] == "Bookmaker" and entry[0] and entry[0] > 1.0:
        return (usage, 1, probability - 1.0 / entry[0])
    return (usage, 0, probability)


def choose(probabilities, prices=None, *, min_confidence=0.35,
           max_confidence=0.97, family_cap=3, used_families=None,
           used_tips=None, mode="accuracy"):
    """Return {"tip", "confidence", "odds", "source", "family"} or None.

    Degrades in stages rather than ever returning nothing:
      1. inside the band, inside the family cap
      2. inside the band, family cap lifted
      3. band widened upward to 1.0
      4. simply the most probable market we can price
    """
    if not probabilities:
        return None
    # The model's own probabilities are systematically overconfident on goals
    # (see wakamaria/calibration.py). Rank and publish on the corrected ones,
    # because the corrected ones are the only version that matches reality.
    real = calibration.calibrate_all(probabilities)
    used_families = used_families or {}
    used_tips = used_tips or {}
    floor = max(min_confidence, MIN_CONFIDENCE_FLOOR)

    def priced(tip):
        entry = (prices or {}).get(tip)
        return entry if entry and entry[0] and entry[0] > 1.0 else None

    def pick(lo, hi, cap):
        candidates = []
        for tip in TIPS:
            probability = probabilities.get(tip)
            if probability is None or not (lo <= probability <= hi):
                continue
            if not priced(tip):
                continue
            if cap is not None and used_families.get(family(tip), 0) >= cap:
                continue
            candidates.append((tip, probability))
        if not candidates:
            return None

        # Coherence: a tip must be close to the fixture's best market. Rotation
        # spreads the run across markets, but it must never manufacture a tip
        # the match itself argues against.
        top = max(p for _, p in candidates)
        candidates = [(t, p) for t, p in candidates if p >= top - COHERENCE_GAP]
        return max((t for t, _ in candidates),
                   key=lambda t: _rank_key(t, probabilities[t], prices, used_tips))

    if mode == "accuracy":
        # Rule 1: anything at CERTAINTY_FLOOR or better is a candidate, and the
        # best price among those candidates is published. Among equals, the
        # higher probability wins.
        candidates = []
        for tip in TIPS:
            probability = real.get(tip)
            if probability is None or probability < CERTAINTY_FLOOR:
                continue
            entry = priced(tip)
            if not entry:
                continue
            candidates.append((tip, probability, entry[0]))
        if candidates:
            candidates.sort(key=lambda row: (row[2], row[1]), reverse=True)
            return _describe(candidates[0][0], probabilities, prices)

        # Rule 2: nothing is that certain, so the most likely market wins,
        # however cheap it is. No price floor exists.
        best = None
        for tip in TIPS:
            probability = real.get(tip)
            if probability is None or not priced(tip):
                continue
            key = (probability, -used_tips.get(tip, 0))
            if best is None or key > best[0]:
                best = (key, tip)
        return _describe(best[1], probabilities, prices) if best else None

    for lo, hi, cap in (
        (floor, max_confidence, family_cap),
        (floor, max_confidence, None),
        (floor, 1.0, None),
    ):
        tip = pick(lo, hi, cap)
        if tip:
            return _describe(tip, probabilities, prices)

    tip = max((t for t in TIPS if priced(t)),
              key=lambda t: (probabilities.get(t, 0.0), -used_tips.get(t, 0)),
              default=None)
    return _describe(tip, probabilities, prices) if tip else None


def _describe(tip, probabilities, prices):
    price, source = prices[tip]
    confidence = calibration.calibrate(tip, probabilities.get(tip, 0.0)) or 0.0
    if source == "Model":
        # Keep our own price consistent with the honest probability, so a 75%
        # chance is never posted at the price of a 40% one.
        price = model.market_odds(confidence) or price
    return {
        "tip": tip,
        "confidence": round(confidence, 4),
        "odds": price,
        "source": source,
        "family": family(tip),
    }
