"""Pick the one market Wakamaria publishes for a fixture, and justify it.

A football site that publishes the highest-probability market every time
publishes "Under 3.5" every time, which is useless to a reader and makes the
list look broken. This module picks a *credible* selection instead: probable
enough to be worth reading, long enough to be worth combining, and spread
across market families so one day's page is not six versions of the same bet.

Pure: no Frappe, no network.
"""

from wakamaria.tips import TIPS, family

# A selection outside this band is either a near-certainty nobody will back or
# a coin flip that adds nothing.
MIN_CONFIDENCE_FLOOR = 0.50


def _rank_key(tip, probability, prices):
    """Bookmaker prices can be judged on edge; model prices cannot.

    A model price is derived from the same probability, so its "edge" is always
    exactly -margin and tells us nothing. Rank by confidence in that case.
    """
    entry = (prices or {}).get(tip)
    if entry:
        price, source = entry[0], entry[1]
        if source == "Bookmaker" and price and price > 1.0:
            return (1, probability - 1.0 / price)
    return (0, probability)


def choose(probabilities, prices=None, *, min_confidence=0.45,
           max_confidence=0.66, family_cap=2, used_families=None):
    """Return {"tip", "confidence", "odds", "source", "family"} or None.

    Degrades in stages rather than ever returning nothing:
      1. inside the confidence band, inside the family cap
      2. inside the band, family cap lifted
      3. band widened to (min_confidence, 1.0)
      4. simply the most probable market we can price
    """
    if not probabilities:
        return None
    used_families = used_families or {}
    floor = max(min_confidence, MIN_CONFIDENCE_FLOOR)

    def priced(tip):
        entry = (prices or {}).get(tip)
        return entry if entry and entry[0] and entry[0] > 1.0 else None

    def pick(lo, hi, cap):
        best = None
        best_key = None
        for tip in TIPS:
            probability = probabilities.get(tip)
            if probability is None or not (lo <= probability <= hi):
                continue
            if not priced(tip):
                continue
            if cap is not None and used_families.get(family(tip), 0) >= cap:
                continue
            key = _rank_key(tip, probability, prices)
            if best_key is None or key > best_key:
                best, best_key = tip, key
        return best

    for lo, hi, cap in (
        (floor, max_confidence, family_cap),
        (floor, max_confidence, None),
        (floor, 1.0, None),
    ):
        tip = pick(lo, hi, cap)
        if tip:
            return _describe(tip, probabilities, prices)

    tip = max((t for t in TIPS if priced(t)),
              key=lambda t: probabilities.get(t, 0.0), default=None)
    return _describe(tip, probabilities, prices) if tip else None


def _describe(tip, probabilities, prices):
    price, source = prices[tip]
    return {
        "tip": tip,
        "confidence": round(probabilities.get(tip, 0.0), 4),
        "odds": price,
        "source": source,
        "family": family(tip),
    }
