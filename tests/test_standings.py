import unittest

from wakamaria import model, standings

PAYLOAD = {"standings": [
    {"type": "TOTAL", "table": [
        {"position": 2, "team": {"id": 86, "name": "Real Madrid"},
         "playedGames": 13, "goalsFor": 31, "goalsAgainst": 11},
        {"position": 13, "team": {"id": 558, "name": "Celta Vigo"},
         "playedGames": 13, "goalsFor": 15, "goalsAgainst": 20},
    ]},
    {"type": "HOME", "table": [
        {"position": 1, "team": {"id": 86, "name": "Real Madrid"},
         "playedGames": 6, "goalsFor": 20, "goalsAgainst": 3},
    ]},
]}


class TestParse(unittest.TestCase):

    def test_total_table_only(self):
        """Home/away splits are thin in November; the combined table is stable."""
        strengths = standings.team_strengths(PAYLOAD)
        self.assertEqual(set(strengths), {"86", "558"})

    def test_strong_team_gets_attack_above_one(self):
        attack, defence = standings.team_strengths(PAYLOAD)["86"]
        self.assertGreater(attack, 1.2)
        self.assertLess(defence, 1.0)          # concedes fewer than average

    def test_weak_team_gets_attack_below_one(self):
        attack, defence = standings.team_strengths(PAYLOAD)["558"]
        self.assertLess(attack, 1.0)
        self.assertGreater(defence, 1.0)

    def test_teams_with_too_few_games_are_ignored(self):
        payload = {"standings": [{"type": "TOTAL", "table": [
            {"team": {"id": 1}, "playedGames": 1, "goalsFor": 5, "goalsAgainst": 0}]}]}
        self.assertEqual(standings.team_strengths(payload), {})

    def test_absurd_early_season_ratios_are_clamped(self):
        payload = {"standings": [{"type": "TOTAL", "table": [
            {"team": {"id": 1}, "playedGames": 3, "goalsFor": 30, "goalsAgainst": 0}]}]}
        attack, defence = standings.team_strengths(payload)["1"]
        self.assertLessEqual(attack, 2.60)
        self.assertGreaterEqual(defence, 0.40)

    def test_missing_fields_do_not_raise(self):
        payload = {"standings": [{"type": "TOTAL", "table": [
            {"team": {"id": 1}}, {"playedGames": 10}, {}]}]}
        self.assertEqual(standings.team_strengths(payload), {})

    def test_empty_payload_is_empty(self):
        self.assertEqual(standings.team_strengths({}), {})
        self.assertEqual(standings.team_strengths(None), {})


class TestEffectOnPrediction(unittest.TestCase):

    def test_table_makes_a_favourite_of_the_better_side(self):
        strengths = standings.team_strengths(PAYLOAD)
        probs = model.predict([], [], home_strength=strengths["86"],
                              away_strength=strengths["558"])["probabilities"]
        self.assertGreater(probs["1"], 0.75)
        self.assertLess(probs["X2"], 0.20)

    def test_without_a_table_every_fixture_looks_the_same(self):
        """The bug: no history and no table means 'two average teams'."""
        probs = model.predict([], [])["probabilities"]
        self.assertAlmostEqual(probs["1"], 0.432, places=2)

    def test_recent_results_still_beat_the_table(self):
        """A team with real matches uses them, not the table."""
        entries = [{"home": "Real Madrid", "home_id": "86", "away": "X",
                    "away_id": "9", "score": [5, 0]}] * 8
        with_history = model.predict(entries, [], home_id="86",
                                     home_strength=(0.50, 2.00))
        self.assertGreater(with_history["home_lambda"], 2.0)


class TestFetch(unittest.TestCase):

    def test_a_failing_provider_returns_empty_not_an_exception(self):
        def boom(path, params):
            raise RuntimeError("503")
        self.assertEqual(standings.fetch(boom, "PL"), {})

    def test_cached_values_skip_the_network(self):
        class Cache:
            def __init__(self): self.store = {}
            def get_value(self, k): return self.store.get(k)
            def set_value(self, k, v, expires_in_sec=None): self.store[k] = v

        calls = []
        cache = Cache()
        first = standings.fetch(lambda p, q: (calls.append(1), PAYLOAD)[1], "PD", cache=cache)
        second = standings.fetch(lambda p, q: (calls.append(1), PAYLOAD)[1], "PD", cache=cache)
        self.assertEqual(first, second)
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
