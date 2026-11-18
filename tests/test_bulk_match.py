import unittest
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from wakamaria.bulk_match import canonical_name, select_unique, utc_instant, local_to_utc, goal_fixture, football_data_fixture

T = datetime(2026,11,17,19,45,tzinfo=timezone.utc)

def row(name='a', home='Denmark', away='Norway', comp='UNL', kickoff=T):
    return {'name': name, 'home': home, 'away': away, 'competition': comp, 'kickoff': kickoff}

def fixture(ident='1', home='Denmark', away='Norway', comp='UNL', kickoff=T):
    return {'id': ident, 'home': home, 'away': away, 'competition': comp, 'kickoff': kickoff, 'home_id':'h', 'away_id':'a'}

class BulkMatchTest(unittest.TestCase):
    def test_unique_names_and_timezone(self):
        r = row(home=' Denmark ', away='NORWAY')
        self.assertEqual(select_unique([r], [fixture()])['a']['id'], '1')
        self.assertEqual(local_to_utc(datetime(2026,11,17,22,45), ZoneInfo('Africa/Dar_es_Salaam')), T)
    def test_exact_not_fuzzy_and_no_reversal(self):
        for r in (row(home='Denmark U21'), row(home='Norway', away='Denmark'), row(comp='OTHER'), row(kickoff=T.replace(minute=44))):
            self.assertEqual(select_unique([r], [fixture()]), {})
    def test_ambiguous_and_duplicate_rows(self):
        self.assertEqual(select_unique([row()], [fixture('1'), fixture('2')]), {})
        self.assertEqual(select_unique([row('a'), row('b')], [fixture()]), {})
        self.assertEqual(select_unique([row()], [fixture(), fixture(home='Other')]), {})
        self.assertEqual(select_unique([row()], [fixture(), fixture()])['a']['id'], '1')
    def test_ireland_alias_is_scoped_and_remains_unique(self):
        league='cmr77dw4800fgrx06rwmig2h8'
        r=row(home='Ireland', away='Kosovo', comp=league)
        f=fixture(home='Republic of Ireland', away='Kosovo', comp=league)
        self.assertEqual(select_unique([r], [f])['a']['id'], '1')
        self.assertEqual(select_unique([row(home='Ireland', away='Kosovo')], [fixture(home='Republic of Ireland', away='Kosovo')]), {})
        self.assertEqual(select_unique([r, row('b', home='Republic of Ireland', away='Kosovo', comp=league)], [f]), {})
        self.assertEqual(select_unique([r], [fixture(home='Northern Ireland', away='Kosovo', comp=league)]), {})

    def test_missing_ids_and_zones(self):
        f = fixture(); f['away_id'] = ''
        self.assertEqual(select_unique([row()], [f]), {})
        with self.assertRaises(ValueError): utc_instant('2026-11-17T19:45:00')
        for date in (datetime(2026,11,1,1,30), datetime(2026,3,8,2,30)):
            with self.assertRaises(ValueError): local_to_utc(date, ZoneInfo('America/New_York'))
    def test_goal_schema_strict(self):
        item={'id':'c1','kickoffUtc':'2026-11-17T19:45:00Z','league':{'id':'UNL'}, 'homeTeam':{'id':'h','name':'Denmark'},'awayTeam':{'id':'a','name':'Norway'}}
        self.assertEqual(goal_fixture(item,'UNL')['kickoff'],T)
        self.assertIsNone(goal_fixture(item,'OTHER'))
        item['kickoffUtc']='2026-11-17T19:45:00'
        self.assertIsNone(goal_fixture(item,'UNL'))
    def test_football_schema_strict(self):
        item={'id':42,'utcDate':'2026-11-17T19:45:00Z','competition':{'code':'PL'},'homeTeam':{'id':10,'name':'A'},'awayTeam':{'id':20,'name':'B'}}
        self.assertEqual(football_data_fixture(item,'PL')['id'],'42')
        self.assertIsNone(football_data_fixture(item,'PD'))
        item['homeTeam']['id']=True
        self.assertIsNone(football_data_fixture(item,'PL'))

if __name__ == '__main__': unittest.main()
