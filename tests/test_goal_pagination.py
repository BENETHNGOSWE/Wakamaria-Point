import importlib
import sys
import types
import unittest
from unittest.mock import patch

# Test the network parser without needing an installed Frappe bench.
class PaginationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        frappe = types.ModuleType('frappe')
        frappe._ = lambda x: x
        frappe.whitelist = lambda **kwargs: lambda f: f
        utils = types.ModuleType('frappe.utils')
        utils.get_datetime = lambda x: x
        utils.get_system_timezone = lambda: 'UTC'
        with patch.dict(sys.modules, {'frappe': frappe, 'frappe.utils': utils}):
            cls.mod = importlib.import_module('wakamaria.goal_preview')

    def response(self, data, more):
        return types.SimpleNamespace(raise_for_status=lambda: None,
            json=lambda: {'success': True, 'data': data, 'pagination': {'hasMore': more}})

    def test_pages_and_offsets(self):
        pages=[self.response([{'id':'a'}], True), self.response([{'id':'b'}], False)]
        with patch.object(self.mod.requests, 'get', side_effect=pages) as get, patch.object(self.mod.time, 'sleep'):
            result=self.mod.get_pages('2026-11-17','league','secret',[0])
        self.assertEqual([x['id'] for x in result], ['a','b'])
        self.assertEqual(get.call_args_list[1].kwargs['params']['offset'], 100)
    def test_repeated_or_missing_pagination_fails(self):
        page=self.response([{'id':'a'}], True)
        with patch.object(self.mod.requests, 'get', return_value=page), patch.object(self.mod.time, 'sleep'):
            with self.assertRaises(ValueError): self.mod.get_pages('2026-11-17','league','secret',[0])
        bad=types.SimpleNamespace(raise_for_status=lambda: None, json=lambda: {'success':True, 'data':[]})
        with patch.object(self.mod.requests, 'get', return_value=bad):
            with self.assertRaises(ValueError): self.mod.get_pages('2026-11-17','league','secret',[0])
    def test_budget_stops_before_request(self):
        with patch.object(self.mod.requests, 'get') as get:
            with self.assertRaises(ValueError): self.mod.get_pages('2026-11-17','league','secret',[self.mod.MAX_REQUESTS])
            get.assert_not_called()

if __name__ == '__main__': unittest.main()
