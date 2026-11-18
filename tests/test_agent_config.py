"""Unset settings must not silently disable the agent.

A migrated site shows 0 in every new numeric field. If those zeros were taken
literally the agent would publish nothing and still report success, which is the
worst possible failure: silent and confident.
"""
import unittest

from wakamaria.agentconfig import DEFAULTS, resolve


class TestResolve(unittest.TestCase):
    def test_all_zero_settings_fall_back_to_defaults(self):
        settings = {
            "agent_horizon_hours": 0, "agent_max_per_run": 0,
            "agent_max_per_day": 0, "agent_min_confidence": 0.0,
            "agent_max_confidence": 0.0, "agent_family_cap": 0,
            "agent_margin": 0.0, "agent_pause_after_losses": 0,
        }
        self.assertEqual(resolve(settings), DEFAULTS)

    def test_missing_and_null_settings_fall_back(self):
        self.assertEqual(resolve({}), DEFAULTS)
        self.assertEqual(resolve({"agent_horizon_hours": None,
                                  "agent_min_confidence": ""}), DEFAULTS)

    def test_a_configured_value_wins(self):
        config = resolve({"agent_horizon_hours": 12,
                          "agent_min_confidence": 0.55,
                          "agent_max_confidence": 0.80,
                          "agent_max_per_run": 4})
        self.assertEqual(config["horizon_hours"], 12)
        self.assertEqual(config["min_confidence"], 0.55)
        self.assertEqual(config["max_confidence"], 0.80)
        self.assertEqual(config["max_per_run"], 4)

    def test_strings_from_the_web_form_are_cast(self):
        config = resolve({"agent_max_per_run": "7",
                          "agent_margin": "0.08"})
        self.assertEqual(config["max_per_run"], 7)
        self.assertAlmostEqual(config["margin"], 0.08)

    def test_garbage_falls_back_rather_than_raising(self):
        config = resolve({"agent_max_per_run": "many",
                          "agent_min_confidence": "??"})
        self.assertEqual(config["max_per_run"], DEFAULTS["max_per_run"])
        self.assertEqual(config["min_confidence"], DEFAULTS["min_confidence"])

    def test_resolved_band_spans_a_useful_range_of_prices(self):
        """Visitors combine picks themselves, so a wide spread matters.

        A narrow band collapsed the list onto three markets; the default now
        reaches from ~1.18 up to ~2.70.
        """
        from wakamaria.model import market_odds
        config = resolve({})
        shortest = market_odds(config["max_confidence"], config["margin"])
        longest = market_odds(config["min_confidence"], config["margin"])
        self.assertGreater(shortest, 1.10)
        self.assertLess(shortest, 1.30)
        self.assertGreater(longest, 2.50)
        self.assertGreater(config["max_confidence"], config["min_confidence"])


if __name__ == "__main__":
    unittest.main()
