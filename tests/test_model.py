"""The pricing model has to be internally consistent before it can be trusted.

Tolerances are 1e-5 rather than exact: the scoreline grid stops at MAX_GOALS,
so every distribution sums to 1 minus a negligible tail.
"""
import unittest

from wakamaria import model
from wakamaria.tips import TIPS


class TestProbabilities(unittest.TestCase):
    def setUp(self):
        self.p = model.probabilities(model.score_matrix(1.45, 1.15))

    def test_every_market_is_priced(self):
        self.assertEqual(set(self.p), set(TIPS))

    def test_1x2_is_a_complete_distribution(self):
        self.assertAlmostEqual(self.p["1"] + self.p["X"] + self.p["2"], 1.0, delta=1e-5)   # grid truncates above 10 goals

    def test_double_chance_agrees_with_1x2(self):
        self.assertAlmostEqual(self.p["1X"], self.p["1"] + self.p["X"], delta=1e-5)   # grid truncates above 10 goals
        self.assertAlmostEqual(self.p["X2"], self.p["X"] + self.p["2"], delta=1e-5)   # grid truncates above 10 goals
        self.assertAlmostEqual(self.p["12"], self.p["1"] + self.p["2"], delta=1e-5)   # grid truncates above 10 goals

    def test_goal_markets_are_complementary(self):
        self.assertAlmostEqual(self.p["Over 2.5"] + self.p["Under 2.5"], 1.0, delta=1e-5)   # grid truncates above 10 goals

    def test_btts_is_complementary(self):
        self.assertAlmostEqual(self.p["BTTS Yes"] + self.p["BTTS No"], 1.0, delta=1e-5)   # grid truncates above 10 goals

    def test_under_3_5_is_more_likely_than_under_2_5(self):
        self.assertGreater(self.p["Under 3.5"], self.p["Under 2.5"])

    def test_probabilities_are_sane(self):
        for tip, value in self.p.items():
            self.assertGreaterEqual(value, 0.0, tip)
            self.assertLessEqual(value, 1.0 + 1e-9, tip)


class TestTeamRates(unittest.TestCase):
    def test_no_history_is_average(self):
        self.assertEqual(model.team_rates([]), (1.0, 1.0))

    def test_a_free_scoring_side_gets_attack_above_one(self):
        entries = [{"home": "A", "away": "B", "score": [4, 0]} for _ in range(10)]
        attack, defence = model.team_rates(entries, team_name="A")
        self.assertGreater(attack, 1.5)
        self.assertLess(defence, 0.6)

    def test_away_side_goals_are_read_from_the_right_columns(self):
        entries = [{"home": "B", "away": "A", "score": [0, 4]} for _ in range(10)]
        attack, _ = model.team_rates(entries, team_name="A")
        self.assertGreater(attack, 1.5)

    def test_provider_ids_beat_names(self):
        # Names deliberately do not match; the ID must still identify the side.
        entries = [{"home": "X", "away": "Y", "home_id": "1", "away_id": "2",
                    "score": [3, 0]} for _ in range(10)]
        attack, _ = model.team_rates(entries, team_id="1")
        self.assertGreater(attack, 1.5)

    def test_unrelated_fixtures_are_ignored(self):
        entries = [{"home": "C", "away": "D", "score": [5, 0]}]
        self.assertEqual(model.team_rates(entries, team_name="A"), (1.0, 1.0))

    def test_malformed_rows_are_not_counted_as_goalless(self):
        entries = [
            {"home": "A", "away": "B", "score": [1, 1]},
            {"home": "A", "away": "B", "score": []},
            {"home": "A", "away": "B", "score": [None, 2]},
            {"home": "A", "away": "B", "score": [True, 2]},
            {"home": "A", "away": "B"},
        ]
        # Only the first row is real, so the sample is one honest game.
        attack, defence = model.team_rates(entries, team_name="A", shrinkage=0.0001)
        self.assertAlmostEqual(attack, 1 / (model.DEFAULT_LEAGUE_AVG / 2) / 1, delta=0.5)
        self.assertGreater(attack, 0)

    def test_bool_is_not_read_as_a_goal(self):
        entries = [{"home": "A", "away": "B", "score": [True, True]}]
        self.assertEqual(model.team_rates(entries, team_name="A"), (1.0, 1.0))


class TestExpectedGoals(unittest.TestCase):
    def test_two_average_sides_produce_average_lambdas(self):
        home, away = model.expected_goals((1.0, 1.0), (1.0, 1.0))
        self.assertAlmostEqual(home, model.DEFAULT_LEAGUE_AVG * model.HOME_SHARE, places=6)
        self.assertAlmostEqual(away, model.DEFAULT_LEAGUE_AVG * (1 - model.HOME_SHARE), places=6)

    def test_home_side_is_given_an_advantage(self):
        home, away = model.expected_goals((1.0, 1.0), (1.0, 1.0))
        self.assertGreater(home, away)

    def test_lambdas_are_clamped(self):
        home, away = model.expected_goals((50.0, 50.0), (50.0, 0.01))
        self.assertLessEqual(home, model.LAMBDA_CEIL)
        self.assertGreaterEqual(away, model.LAMBDA_FLOOR)


class TestOdds(unittest.TestCase):
    def test_fair_odds_are_the_reciprocal(self):
        self.assertEqual(model.fair_odds(0.5), 2.0)
        self.assertEqual(model.fair_odds(0.25), 4.0)

    def test_market_odds_are_shorter_than_fair(self):
        for p in (0.2, 0.35, 0.5, 0.72, 0.9):
            self.assertLess(model.market_odds(p), model.fair_odds(p), p)

    def test_a_bigger_margin_pays_less(self):
        self.assertLess(model.market_odds(0.5, 0.10), model.market_odds(0.5, 0.02))

    def test_odds_never_fall_below_one(self):
        self.assertGreaterEqual(model.market_odds(0.999, 0.06), 1.01)

    def test_zero_probability_has_no_price(self):
        self.assertIsNone(model.market_odds(0.0))
        self.assertIsNone(model.fair_odds(0.0))


class TestPredict(unittest.TestCase):
    def test_predict_returns_a_full_distribution(self):
        home = [{"home": "A", "away": "X", "score": [2, 0]} for _ in range(6)]
        away = [{"home": "Y", "away": "B", "score": [1, 1]} for _ in range(6)]
        result = model.predict(home, away, home_name="A", away_name="B")
        self.assertIn("probabilities", result)
        self.assertAlmostEqual(result["probabilities"]["1"] + result["probabilities"]["X"]
                               + result["probabilities"]["2"], 1.0, delta=1e-5)   # grid truncates above 10 goals

    def test_a_strong_home_side_is_favoured(self):
        # A wins 3-0 at home every week; B loses 0-3 at home every week.
        strong = [{"home": "A", "away": "X", "score": [3, 0]} for _ in range(8)]
        weak = [{"home": "B", "away": "Y", "score": [0, 3]} for _ in range(8)]
        result = model.predict(strong, weak, home_name="A", away_name="B")
        self.assertGreater(result["probabilities"]["1"], 0.6)

    def test_no_history_still_produces_a_prediction(self):
        result = model.predict([], [], home_name="A", away_name="B")
        self.assertAlmostEqual(result["probabilities"]["1"] + result["probabilities"]["X"]
                               + result["probabilities"]["2"], 1.0, delta=1e-5)   # grid truncates above 10 goals


if __name__ == "__main__":
    unittest.main()
