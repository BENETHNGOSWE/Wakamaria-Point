import json
import unittest
from datetime import date

from wakamaria import apisports, sources
from wakamaria.fixtures import select

# A trimmed but real-shaped API-Football /fixtures payload for 19 Nov 2026 —
# the day football-data.org's twelve competitions hold only Brazilian Serie A.
PAYLOAD = {"response": [
    {"fixture": {"id": 9001, "date": "2026-11-19T17:45:00+00:00",
                 "status": {"short": "NS", "long": "Not Started"}},
     "league": {"id": 44, "name": "UWCL", "country": "World"},
     "teams": {"home": {"id": 71, "name": "Austria Wien W"},
               "away": {"id": 72, "name": "Bayern Munich W"}}},
    {"fixture": {"id": 9002, "date": "2026-11-19T13:00:00+00:00",
                 "status": {"short": "NS", "long": "Not Started"}},
     "league": {"id": 45, "name": "U17 World Cup", "country": "World"},
     "teams": {"home": {"id": 73, "name": "Argentina U17"},
               "away": {"id": 74, "name": "Australia U17"}}},
    {"fixture": {"id": 9003, "date": "2026-11-19T15:30:00+00:00",
                 "status": {"short": "NS", "long": "Not Started"}},
     "league": {"id": 828, "name": "Qatar Stars League", "country": "Qatar"},
     "teams": {"home": {"id": 75, "name": "Al-Ahli Doha"},
               "away": {"id": 76, "name": "Al-Shamal"}}},
    # Not yet started: must be predictable.
    {"fixture": {"id": 9004, "date": "2026-11-19T19:30:00+00:00",
                 "status": {"short": "NS", "long": "Not Started"}},
     "league": {"id": 268, "name": "Primera Division", "country": "Uruguay"},
     "teams": {"home": {"id": 77, "name": "Boston River"},
               "away": {"id": 78, "name": "Deportivo Maldonado"}}},
]}


class TestTranslation(unittest.TestCase):

    def test_shape_matches_the_first_provider(self):
        matches = apisports.to_matches(PAYLOAD)
        self.assertEqual(len(matches), 4)
        row = matches[0]
        for key in ("id", "utcDate", "status", "competition", "homeTeam", "awayTeam"):
            self.assertIn(key, row)
        self.assertEqual(row["homeTeam"]["name"], "Austria Wien W")

    def test_status_is_translated(self):
        self.assertEqual(apisports.to_matches(PAYLOAD)[0]["status"], "SCHEDULED")

    def test_in_play_and_finished_are_not_scheduled(self):
        for short, expected in (("1H", "IN_PLAY"), ("FT", "FINISHED"), ("PST", "POSTPONED")):
            payload = {"response": [{
                "fixture": {"id": 1, "date": "2026-11-19T19:00:00+00:00",
                            "status": {"short": short}},
                "league": {"id": 2, "name": "X", "country": "Y"},
                "teams": {"home": {"id": 3, "name": "A"}, "away": {"id": 4, "name": "B"}},
            }]}
            self.assertEqual(apisports.to_matches(payload)[0]["status"], expected)

    def test_incomplete_rows_are_dropped_not_guessed(self):
        payload = {"response": [
            {"fixture": {"id": 0}, "league": {"id": 1},
             "teams": {"home": {"id": 1, "name": "A"}, "away": {"id": 2, "name": "B"}}},
            {"fixture": {"id": 5, "date": "2026-11-19T19:00:00+00:00"},
             "league": {"id": 1},
             "teams": {"home": {"id": 1, "name": "A"}, "away": {}}},
            {"fixture": {"id": 6, "date": "2026-11-19T19:00:00+00:00"},
             "league": {"id": 1},
             "teams": {"home": {"id": 1, "name": "A"}, "away": {"id": 2, "name": "B"}}},
        ]}
        self.assertEqual(len(apisports.to_matches(payload)), 1)

    def test_synthetic_code_cannot_collide(self):
        self.assertEqual(apisports.to_matches(PAYLOAD)[0]["competition"]["code"], "APIFB")

    def test_the_window_filter_still_works_on_translated_rows(self):
        from datetime import datetime
        # The agent's clock is naive local time, so the harness is too.
        now = datetime(2026, 11, 19, 0, 30)
        fixtures, stats = select(apisports.to_matches(PAYLOAD), now, horizon_hours=96)
        self.assertEqual(len(fixtures), 4)
        self.assertEqual(stats["not_predictable"], 0)


class TestMerge(unittest.TestCase):

    def _match(self, home, away, day, uid, source="football-data"):
        return {"id": str(uid), "utcDate": f"{day}T19:00:00+00:00",
                "homeTeam": {"name": home}, "awayTeam": {"name": away},
                "source": source}

    def test_second_source_adds_only_new_fixtures(self):
        primary = [self._match("Vasco da Gama", "Internacional", "2026-11-19", 1)]
        secondary = [self._match("Al-Ahli Doha", "Al-Shamal", "2026-11-19", 2, "apifootball")]
        merged, added = sources.merge(primary, secondary)
        self.assertEqual(len(merged), 2)
        self.assertEqual(added, 1)

    def test_same_fixture_is_not_duplicated(self):
        """Both feeds cover the Serie A match; the first one wins."""
        primary = [self._match("Vasco da Gama", "Internacional", "2026-11-19", 1)]
        secondary = [self._match("Vasco da Gama", "Internacional", "2026-11-19", 2, "apifootball")]
        merged, added = sources.merge(primary, secondary)
        self.assertEqual(len(merged), 1)
        self.assertEqual(added, 0)
        self.assertEqual(merged[0]["id"], "1")

    def test_punctuation_and_case_do_not_create_duplicates(self):
        primary = [self._match("Paris Saint-Germain", "Bayern Munich", "2026-11-21", 1)]
        secondary = [self._match("paris saint germain", "BAYERN MUNICH", "2026-11-21", 9, "apifootball")]
        self.assertEqual(sources.merge(primary, secondary)[1], 0)

    def test_different_day_is_a_different_fixture(self):
        primary = [self._match("Arsenal", "Lyon", "2026-11-19", 1)]
        secondary = [self._match("Arsenal", "Lyon", "2026-11-20", 2, "apifootball")]
        self.assertEqual(sources.merge(primary, secondary)[1], 1)

    def test_rows_without_a_usable_identity_are_skipped(self):
        merged, added = sources.merge([{"id": "1"}], [{"id": "2", "homeTeam": {}}])
        self.assertEqual((len(merged), added), (0, 0))

    def test_empty_secondary_changes_nothing(self):
        primary = [self._match("Arsenal", "Lyon", "2026-11-19", 1)]
        merged, added = sources.merge(primary, [])
        self.assertEqual((len(merged), added), (1, 0))


class TestFetch(unittest.TestCase):

    def test_no_key_makes_no_request(self):
        called = []
        self.assertEqual(apisports.fetch("", "2026-11-19", "2026-11-23",
                                         get=lambda *a: called.append(a)), [])
        self.assertEqual(called, [])

    def test_direct_key_uses_the_apisports_header(self):
        seen = {}

        def fake_get(url, headers, params):
            seen.update(url=url, headers=headers, params=params)
            return PAYLOAD

        rows = apisports.fetch("KEY", "2026-11-19", "2026-11-23", get=fake_get)
        self.assertEqual(seen["headers"], {"x-apisports-key": "KEY"})
        self.assertEqual(seen["params"]["from"], "2026-11-19")
        self.assertEqual(seen["params"]["to"], "2026-11-23")
        self.assertEqual(len(rows), 4)

    def test_rapidapi_key_uses_both_headers(self):
        seen = {}

        def fake_get(url, headers, params):
            seen.update(headers)
            return PAYLOAD

        apisports.fetch("KEY", "2026-11-19", "2026-11-23",
                        base="https://api-football-v1.p.rapidapi.com/v3", get=fake_get)
        self.assertEqual(seen["x-rapidapi-key"], "KEY")
        self.assertEqual(seen["x-rapidapi-host"], "api-football-v1.p.rapidapi.com")

    def test_a_plan_quota_error_is_raised_not_swallowed(self):
        """API-Football reports 'free plan has no access' as a 200 body."""
        def fake_get(url, headers, params):
            return {"errors": {"plan": "Free plans do not have access to this season"},
                    "response": []}

        with self.assertRaises(RuntimeError) as caught:
            apisports.fetch("KEY", "2026-11-19", "2026-11-23", get=fake_get)
        self.assertIn("Free plans", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
