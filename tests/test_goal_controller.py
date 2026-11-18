import importlib
import sys
import types
import unittest
from unittest.mock import patch

class StubDocument:
    def get_doc_before_save(self): return self.old

class ControllerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        f=types.ModuleType('frappe');f._=lambda x:x;f.throw=lambda x:(_ for _ in ()).throw(ValueError(x))
        f.db=types.SimpleNamespace(exists=lambda *a:False)
        model=types.ModuleType('frappe.model');document=types.ModuleType('frappe.model.document');document.Document=StubDocument
        sys.modules.pop('wakamaria.wakamaria.doctype.wakamaria_match.wakamaria_match',None)
        with patch.dict(sys.modules, {'frappe':f,'frappe.model':model,'frappe.model.document':document}):
            cls.controller=importlib.import_module('wakamaria.wakamaria.doctype.wakamaria_match.wakamaria_match').WakamariaMatch
    def make(self):
        base={'name':'x','home_team':'A','away_team':'B','league':'L','kickoff':'date',
              'goal_match_id':'id','goal_home_team_id':'h','goal_away_team_id':'a',
              'goal_last_status':'FINISHED','goal_last_checked':'date','goal_result_managed':1,
              'home_score':3,'away_score':0,'result_confirmed':1,'prediction':'1','provider_match_id':''}
        obj=self.controller();obj.__dict__.update(base);obj.old=types.SimpleNamespace(**base);obj.flags={};return obj
    def test_manual_result_change_takes_ownership(self):
        d=self.make();d.home_score=2;d.validate()
        self.assertEqual((d.goal_result_managed,d.result_confirmed,d.outcome),(0,1,'Win'))
    def test_edit_identity_unlinks_and_unconfirms(self):
        d=self.make();d.home_team='C';d.validate()
        self.assertEqual((d.goal_match_id,d.result_confirmed,d.outcome),('',0,'Pending'))
    def test_sync_update_preserves_goal_ownership(self):
        d=self.make();d.flags['wakamaria_goal_sync']=True;d.home_score=2;d.validate()
        self.assertEqual((d.goal_result_managed,d.result_confirmed),(1,1))

if __name__ == '__main__': unittest.main()
