import unittest
from wakamaria.rules import evaluate, regulation_score

class RulesTest(unittest.TestCase):
    def test_1x2_and_double_chance(self):
        self.assertEqual(evaluate("1", 2, 1), "Win")
        self.assertEqual(evaluate("1", 1, 1), "Lose")
        self.assertEqual(evaluate("X2", 0, 0), "Win")
        self.assertEqual(evaluate("12", 0, 0), "Lose")
    def test_goals_and_btts(self):
        self.assertEqual(evaluate("Over 2.5", 2, 1), "Win")
        self.assertEqual(evaluate("Under 2.5", 0, 2), "Win")
        self.assertEqual(evaluate("Under 3.5", 2, 1), "Win")
        self.assertEqual(evaluate("Under 3.5", 2, 2), "Lose")

    def test_over_ladder(self):
        self.assertEqual(evaluate("Over 1.5", 1, 0), "Lose")
        self.assertEqual(evaluate("Over 1.5", 1, 1), "Win")
        self.assertEqual(evaluate("Over 1.5", 0, 2), "Win")
        self.assertEqual(evaluate("Over 3.5", 2, 1), "Lose")
        self.assertEqual(evaluate("Over 3.5", 3, 1), "Win")
        self.assertEqual(evaluate("Over 3.5", 2, 2), "Win")
        self.assertEqual(evaluate("BTTS No", 0, 1), "Win")
        self.assertEqual(evaluate("BTTS Yes", 0, 1), "Lose")
    def test_unconfirmed_and_invalid(self):
        self.assertEqual(evaluate("1", None, 0), "Pending")
        self.assertEqual(evaluate("unknown", 0, 0), "Pending")
        self.assertEqual(evaluate("1", -1, 0), "Pending")
    def test_settlement_regulation(self):
        self.assertEqual(regulation_score({"status":"FINISHED", "score":{"duration":"REGULAR", "fullTime":{"home":2,"away":1}}}), (2,1))
        self.assertEqual(regulation_score({"status":"FINISHED", "score":{"duration":"EXTRA_TIME", "fullTime":{"home":2,"away":1},"regularTime":{"home":1,"away":1}}}), (1,1))
        self.assertIsNone(regulation_score({"status":"FINISHED", "score":{"duration":"PENALTY_SHOOTOUT", "fullTime":{"home":5,"away":4}}}))
        self.assertIsNone(regulation_score({"status":"AWARDED", "score":{"duration":"REGULAR", "fullTime":{"home":3,"away":0}}}))
        self.assertIsNone(regulation_score({"status":"IN_PLAY", "score":{"duration":"REGULAR", "fullTime":{"home":1,"away":0}}}))
