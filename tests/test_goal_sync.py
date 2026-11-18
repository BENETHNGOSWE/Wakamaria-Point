import importlib
import sys
import types
import unittest
from datetime import datetime
from unittest.mock import patch

from wakamaria.bulk_match import goal_fixture

LEAGUE = 'cmr77dw4800fgrx06rwmig2h8'
KICKOFF = datetime(2026, 11, 17, 22, 45)
NOW = datetime(2026, 11, 18, 11, 23)

class Dict(types.SimpleNamespace): pass

class FakeDoc(Dict):
    def save(self, ignore_permissions=False):
        from wakamaria.rules import evaluate
        self.outcome = evaluate(self.prediction, self.home_score, self.away_score) if self.result_confirmed else "Pending"
        self.saved = True

class FakeCache:
    def __init__(self): self.d = {}
    def get_value(self, k): return self.d.get(k)
    def set_value(self, k, v): self.d[k] = v

class SyncTest(unittest.TestCase):
    def fixture(self, ident, home, away):
        return {'id':ident, 'leagueId':LEAGUE, 'kickoffUtc':'2026-11-17T19:45:00Z', 'matchStatus':'FINISHED',
                'homeTeam':{'id':'h'+ident,'name':home}, 'awayTeam':{'id':'a'+ident,'name':away},
                'homeTeamFtScore':'3', 'awayTeamFtScore':'0', 'homeTeamScore':'3', 'awayTeamScore':'0'}
    def row(self, name, home, away, confirmed=0):
        return Dict(name=name,league='NL',home_team=home,away_team=away,kickoff=KICKOFF,
            provider_match_id='',goal_match_id='',goal_home_team_id='',goal_away_team_id='',result_confirmed=confirmed, goal_result_managed=0, home_score=0, away_score=0, prediction='12')
    def run_sync(self, rows, fixtures, existing=(), auto_results=0):
        f=types.ModuleType('frappe'); utils=types.ModuleType('frappe.utils')
        utils.now_datetime=lambda:NOW
        utils.get_system_timezone=lambda:'Africa/Dar_es_Salaam'
        utils.get_datetime=lambda d:d
        utils.add_days=lambda d,n:d
        cache=FakeCache();f.cache=lambda:cache
        documents={r.name:FakeDoc(**r.__dict__, outcome='Pending', flags=Dict()) for r in rows}
        f.get_doc=lambda doctype,name,**kwargs:documents[name]
        def get_all(doctype, **kwargs):
            if doctype == 'Wakamaria League': return [Dict(name='NL',goal_api_league_id=LEAGUE)]
            if kwargs.get('filters',{}).get('goal_match_id'): return list(existing)
            return rows
        f.get_all=get_all
        preview=types.ModuleType('wakamaria.goal_preview')
        preview.get_pages=lambda day,comp,key,budget:fixtures
        settings=Dict(goal_auto_results=auto_results, get_password=lambda *a,**kw:'private-key')
        sys.modules.pop('wakamaria.goal_sync',None)
        with patch.dict(sys.modules, {'frappe':f,'frappe.utils':utils,'wakamaria.goal_preview':preview}):
            mod=importlib.import_module('wakamaria.goal_sync')
            mod._sync(settings)
        sys.modules.pop('wakamaria.goal_sync',None)
        return documents
    def test_unique_links_and_scoped_ireland_alias_without_results(self):
        rows=[self.row('one','Denmark','Norway'),self.row('two','Ireland','Kosovo')]
        fixtures=[self.fixture('1','Denmark','Norway'),self.fixture('2','Republic of Ireland','Kosovo')]
        docs=self.run_sync(rows,fixtures)
        self.assertEqual(docs['one'].goal_match_id,'1'); self.assertEqual(docs['two'].goal_match_id,'2')
        for doc in docs.values():
            self.assertEqual((doc.home_score,doc.away_score,doc.result_confirmed,doc.outcome),(0,0,0,'Pending'))
    def test_duplicates_and_manual_results_not_touched(self):
        rows=[self.row('one','Denmark','Norway'),self.row('duplicate','Denmark','Norway'),self.row('manual','Ireland','Kosovo',1)]
        docs=self.run_sync(rows,[self.fixture('1','Denmark','Norway'),self.fixture('2','Republic of Ireland','Kosovo')])
        self.assertTrue(all(not getattr(d,'saved',False) for d in docs.values()))
    def test_enabled_settles_only_after_safe_finish_and_never_manual(self):
        rows=[self.row('auto','Denmark','Norway'), self.row('manual','Ireland','Kosovo',1)]
        fixtures=[self.fixture('1','Denmark','Norway'),self.fixture('2','Republic of Ireland','Kosovo')]
        docs=self.run_sync(rows,fixtures,auto_results=1)
        self.assertEqual((docs['auto'].home_score,docs['auto'].away_score,docs['auto'].outcome,docs['auto'].goal_result_managed),(3,0,'Win',1))
        self.assertFalse(getattr(docs['manual'],'saved',False))
    def test_linked_managed_result_is_cleared_when_fixture_disappears(self):
        r=self.row('auto','Denmark','Norway',1)
        r.goal_match_id='1';r.goal_home_team_id='h1';r.goal_away_team_id='a1';r.goal_result_managed=1;r.home_score=3
        docs=self.run_sync([r],[],existing=[Dict(name='auto',goal_match_id='1')],auto_results=1)
        self.assertEqual((docs['auto'].result_confirmed,docs['auto'].outcome),(0,'Pending'))
    def test_provider_score_correction_recalculates_outcome(self):
        r=self.row('auto','Denmark','Norway',1)
        r.goal_match_id='1';r.goal_home_team_id='h1';r.goal_away_team_id='a1';r.goal_result_managed=1;r.home_score=3
        f=self.fixture('1','Denmark','Norway');f.update(homeTeamFtScore='1',awayTeamFtScore='1',homeTeamScore='1',awayTeamScore='1')
        docs=self.run_sync([r],[f],existing=[Dict(name='auto',goal_match_id='1')],auto_results=1)
        self.assertEqual((docs['auto'].home_score,docs['auto'].away_score,docs['auto'].outcome),(1,1,'Lose'))
    def test_incomplete_score_unconfirms_managed_result(self):
        r=self.row('auto','Denmark','Norway',1)
        r.goal_match_id='1';r.goal_home_team_id='h1';r.goal_away_team_id='a1';r.goal_result_managed=1;r.home_score=3
        f=self.fixture('1','Denmark','Norway');f['awayTeamFtScore']=None
        docs=self.run_sync([r],[f],existing=[Dict(name='auto',goal_match_id='1')],auto_results=1)
        self.assertEqual((docs['auto'].result_confirmed,docs['auto'].outcome),(0,'Pending'))

    def test_inconsistent_result_stays_pending(self):
        f=self.fixture('1','Denmark','Norway');f['homeTeamScore']='0'
        docs=self.run_sync([self.row('one','Denmark','Norway')],[f],auto_results=1)
        self.assertEqual((docs['one'].goal_match_id,docs['one'].result_confirmed,docs['one'].outcome),('1',0,'Pending'))

    def test_already_linked_elsewhere_not_attached(self):
        docs=self.run_sync([self.row('one','Denmark','Norway')], [self.fixture('1','Denmark','Norway')], [Dict(name='elsewhere',goal_match_id='1')])
        self.assertFalse(getattr(docs['one'],'saved',False))

if __name__ == '__main__': unittest.main()
