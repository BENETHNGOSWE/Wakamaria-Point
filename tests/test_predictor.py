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

    def test_source_is_carried_through(self):
        probabilities = {"Over 2.5": 0.55, "Under 2.5": 0.45}
        prices = {"Over 2.5": (1.95, "Bookmaker"), "Under 2.5": (1.95, "Model")}
        choice = choose(probabilities, prices)
        self.assertEqual(choice["source"], "Bookmaker")


if __name__ == "__main__":
    unittest.main()
