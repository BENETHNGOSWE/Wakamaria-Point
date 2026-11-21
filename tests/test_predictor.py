"""The selector decides what the public actually sees, so its behaviour is pinned."""
import unittest

from wakamaria.predictor import choose
from wakamaria.tips import family


def priced(probabilities, source="Model"):
    return {tip: (round(1 / p, 2), source) for tip, p in probabilities.items()}


NEUTRAL = {
    "1": 0.42, "X": 0.27, "2": 0.31,
    "1X": 0.69, "X2": 0.58, "12": 0.73,
    "Over 2.5": 0.52, "Under 2.5": 0.48, "Under 3.5": 0.72,
    "BTTS Yes": 0.49, "BTTS No": 0.51,
}


class TestChoose(unittest.TestCase):
    def test_returns_none_without_prices(self):
        self.assertIsNone(choose(NEUTRAL, {}))
        self.assertIsNone(choose({}, None))

    def test_returns_a_publishable_selection(self):
        choice = choose(NEUTRAL, priced(NEUTRAL))
        self.assertIn(choice["tip"], NEUTRAL)
        self.assertGreater(choice["odds"], 1.0)
        self.assertIn(choice["source"], ("Model", "Bookmaker"))
        self.assertEqual(choice["family"], family(choice["tip"]))

    def test_confidence_matches_the_probability(self):
        choice = choose(NEUTRAL, priced(NEUTRAL))
        self.assertAlmostEqual(choice["confidence"], NEUTRAL[choice["tip"]], places=4)

    def test_confidence_band_is_respected_when_possible(self):
        choice = choose(NEUTRAL, priced(NEUTRAL), min_confidence=0.55, max_confidence=0.75)
        self.assertGreaterEqual(choice["confidence"], 0.55)
        self.assertLessEqual(choice["confidence"], 0.75)

    def test_family_cap_pushes_to_another_market(self):
        # A very likely Under 3.5 would normally win; the cap must force another family.
        probabilities = dict(NEUTRAL)
        probabilities["Under 3.5"] = 0.80
        probabilities["1X"] = 0.78
        first = choose(probabilities, priced(probabilities), family_cap=2,
                       used_families={})
        used = {first["family"]: 2}
        second = choose(probabilities, priced(probabilities), family_cap=2,
                        used_families=used)
        self.assertNotEqual(family(second["tip"]), first["family"])

    def test_never_returns_nothing_when_prices_exist(self):
        # Everything outside a narrow band: the selector must still degrade gracefully.
        probabilities = {tip: 0.5 for tip in NEUTRAL}
        choice = choose(probabilities, priced(probabilities),
                        min_confidence=0.99, max_confidence=0.999)
        self.assertIsNotNone(choice)

    def test_all_impossible_band_still_yields_the_best_market(self):
        probabilities = {"Under 3.5": 0.90, "Over 2.5": 0.10}
        prices = {"Under 3.5": (1.10, "Model"), "Over 2.5": (9.0, "Model")}
        choice = choose(probabilities, prices, min_confidence=0.5, max_confidence=0.6)
        self.assertEqual(choice["tip"], "Under 3.5")

    def test_bookmaker_prices_are_preferred_on_edge(self):
        probabilities = {"Over 2.5": 0.55, "Under 2.5": 0.45}
        prices = {"Over 2.5": (2.40, "Bookmaker"), "Under 2.5": (2.00, "Model")}
        # 0.55 against a 2.40 price is a positive edge; 2.00 is not.
        choice = choose(probabilities, prices, min_confidence=0.4, max_confidence=0.9)
        self.assertEqual(choice["tip"], "Over 2.5")
        self.assertEqual(choice["source"], "Bookmaker")

    def test_repeated_runs_do_not_concentrate_on_one_market(self):
        """Identical probabilities must still produce a varied list.

        Before usage-first ranking, twenty neutral fixtures published seven
        copies of the same double chance and nothing else.
        """
        from collections import Counter
        used_f, used_t, picks = {}, {}, []
        for _ in range(40):
            choice = choose(NEUTRAL, priced(NEUTRAL), min_confidence=0.35,
                            max_confidence=0.80, family_cap=3,
                            used_families=used_f, used_tips=used_t)
            used_f[choice["family"]] = used_f.get(choice["family"], 0) + 1
            used_t[choice["tip"]] = used_t.get(choice["tip"], 0) + 1
            picks.append(choice)

        counts = Counter(p["tip"] for p in picks)
        # Coherence narrows the pool — a tip must sit within COHERENCE_GAP of the
        # fixture's best market — so this is variety *within what the match
        # allows*, not variety at any cost.
        self.assertGreaterEqual(len(counts), 6, f"only {len(counts)} distinct tips")
        self.assertLessEqual(max(counts.values()) / len(picks), 0.30,
                             f"one tip took {max(counts.values())}/40")

    def test_a_tip_must_be_close_to_the_best_market(self):
        """Regression: Real Madrid at home was published as "draw or away win".

        The model had no table data, treated both sides as average (P(home)
        0.43, P(X2) 0.57) and the rotation published the nonsense. With the
        table it knows better, and coherence makes the nonsense unpublishable
        even if it did not.
        """
        from wakamaria.model import predict, market_odds
        from wakamaria.predictor import COHERENCE_GAP

        probs = predict([], [], home_strength=(1.80, 0.64),
                        away_strength=(0.87, 1.16))["probabilities"]
        prices = {t: (market_odds(q, 0.06), "Model") for t, q in probs.items()}
        choice = choose(probs, prices, min_confidence=0.35, max_confidence=0.80,
                        family_cap=3, used_families={}, used_tips={})

        in_band = [p for p in probs.values() if 0.35 <= p <= 0.80]
        self.assertGreaterEqual(probs[choice["tip"]], max(in_band) - COHERENCE_GAP - 1e-9)
        self.assertNotEqual(choice["tip"], "X2")
        self.assertGreater(probs["1"], 0.75, "a table must make Madrid a strong favourite")

    def test_prices_spread_across_the_band(self):
        from collections import Counter
        used_f, used_t, odds = {}, {}, []
        for _ in range(20):
            choice = choose(NEUTRAL, priced(NEUTRAL), min_confidence=0.35,
                            max_confidence=0.80, family_cap=3,
                            used_families=used_f, used_tips=used_t)
            used_f[choice["family"]] = used_f.get(choice["family"], 0) + 1
            used_t[choice["tip"]] = used_t.get(choice["tip"], 0) + 1
            odds.append(choice["odds"])
        self.assertLess(min(odds), 1.45)
        self.assertGreater(max(odds), 2.0)

    def test_source_is_carried_through(self):
        probabilities = {"Over 2.5": 0.55, "Under 2.5": 0.45}
        prices = {"Over 2.5": (1.95, "Bookmaker"), "Under 2.5": (1.95, "Model")}
        choice = choose(probabilities, prices)
        self.assertEqual(choice["source"], "Bookmaker")


if __name__ == "__main__":
    unittest.main()
