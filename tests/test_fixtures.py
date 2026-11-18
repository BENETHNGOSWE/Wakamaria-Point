"""Fixture selection decides what the agent can ever see, so it is pinned.

The window rules are the difference between "the agent is broken" and "there
are no matches in the next 36 hours" — the support question this codebase
generated three times before `stats` existed.
"""
import unittest
from datetime import datetime, timedelta

from wakamaria.fixtures import group_by_competition, kickoff_local, select, window

NOW = datetime(2026, 11, 18, 21, 40)      # naive local, as the agent passes it


def match(mid, utc, status="SCHEDULED", code="PL", home=1, away=2):
    return {
        "id": mid, "utcDate": utc, "status": status,
        "competition": {"code": code, "name": "Competition " + (code or "")},
        "homeTeam": {"id": home, "name": "Home"}, "awayTeam": {"id": away, "name": "Away"},
    }


class TestSelect(unittest.TestCase):
    def test_a_fixture_inside_the_window_is_selected(self):
        utc = (NOW + timedelta(hours=20)).strftime("%Y-%m-%dT%H:%M:%SZ")
        fixtures, stats = select([match(1, utc)], NOW, 36)
        self.assertEqual(len(fixtures), 1)
        self.assertEqual(fixtures[0]["competition_code"], "PL")
        self.assertEqual(stats["returned"], 1)

    def test_a_started_match_is_never_predicted(self):
        utc = (NOW - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        fixtures, stats = select([match(1, utc)], NOW, 36)
        self.assertEqual(fixtures, [])
        self.assertEqual(stats["past"], 1)

    def test_a_match_beyond_the_horizon_is_counted_not_dropped(self):
        utc = (NOW + timedelta(hours=60)).strftime("%Y-%m-%dT%H:%M:%SZ")
        fixtures, stats = select([match(1, utc)], NOW, 36)
        self.assertEqual(fixtures, [])
        self.assertEqual(stats["beyond_horizon"], 1)

    def test_unplayable_statuses_are_excluded(self):
        utc = (NOW + timedelta(hours=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
        fixtures, stats = select([match(1, utc, status="FINISHED")], NOW, 36)
        self.assertEqual(fixtures, [])
        self.assertEqual(stats["not_predictable"], 1)

    def test_a_fixture_without_both_teams_is_excluded(self):
        utc = (NOW + timedelta(hours=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
        fixtures, stats = select([match(1, utc, away=None)], NOW, 36)
        self.assertEqual(fixtures, [])
        self.assertEqual(stats["incomplete"], 1)

    def test_results_are_sorted_by_kickoff_across_competitions(self):
        later = (NOW + timedelta(hours=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
        sooner = (NOW + timedelta(hours=4)).strftime("%Y-%m-%dT%H:%M:%SZ")
        fixtures, _ = select([match(1, later, code="BL1"),
                              match(2, sooner, code="PL")], NOW, 36)
        self.assertEqual([f["id"] for f in fixtures], ["2", "1"])

    def test_competition_code_is_upper_cased(self):
        utc = (NOW + timedelta(hours=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
        fixtures, _ = select([match(1, utc, code="pl")], NOW, 36)
        self.assertEqual(fixtures[0]["competition_code"], "PL")

    def test_garbage_payload_does_not_raise(self):
        fixtures, stats = select([{}, {"id": 1}, {"id": 2, "utcDate": "not-a-date"}], NOW, 36)
        self.assertEqual(fixtures, [])
        self.assertEqual(stats["returned"], 1)

    def test_empty_payload_is_an_honest_zero(self):
        fixtures, stats = select([], NOW, 36)
        self.assertEqual(fixtures, [])
        self.assertEqual(stats["returned"], 0)


class TestWindow(unittest.TestCase):
    def test_window_covers_the_horizon(self):
        start, end = window(NOW, 36)
        self.assertEqual(start, NOW.date() - timedelta(days=1))
        self.assertGreaterEqual(end, NOW.date() + timedelta(days=1))

    def test_a_four_day_horizon_reaches_four_days_out(self):
        _, end = window(NOW, 96)
        self.assertEqual(end, NOW.date() + timedelta(days=6))

    def test_a_huge_horizon_is_clamped_to_the_plan_limit(self):
        _, end = window(NOW, 24 * 30)
        self.assertEqual(end, NOW.date() + timedelta(days=8))


class TestKickoff(unittest.TestCase):
    def test_utc_is_parsed(self):
        self.assertEqual(kickoff_local("2026-11-18T18:30:00Z"),
                         datetime(2026, 11, 18, 18, 30))

    def test_a_converter_shifts_to_local(self):
        """Frappe's convert_utc_to_system_timezone returns a naive local time."""
        shifted = kickoff_local(
            "2026-11-18T18:30:00Z",
            to_local=lambda d: (d + timedelta(hours=3)).replace(tzinfo=None),
        )
        self.assertEqual(shifted, datetime(2026, 11, 18, 21, 30))
        self.assertIsNone(shifted.tzinfo)

    def test_an_aware_converter_result_is_normalised(self):
        shifted = kickoff_local(
            "2026-11-18T18:30:00Z",
            to_local=lambda d: d + timedelta(hours=3),
        )
        self.assertIsNone(shifted.tzinfo)

    def test_bad_input_returns_none(self):
        self.assertIsNone(kickoff_local("nope"))
        self.assertIsNone(kickoff_local(None))


class TestGrouping(unittest.TestCase):
    def test_fixtures_group_by_competition(self):
        fixtures = [{"competition_code": "PL"}, {"competition_code": "PL"},
                    {"competition_code": "BL1"}]
        grouped = group_by_competition(fixtures)
        self.assertEqual(len(grouped["PL"]), 2)
        self.assertEqual(len(grouped["BL1"]), 1)


if __name__ == "__main__":
    unittest.main()
