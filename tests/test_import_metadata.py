import json
import unittest
from pathlib import Path

class ImportMetadataTest(unittest.TestCase):
    def test_system_manager_can_import_match_and_league(self):
        for slug in ('wakamaria_match', 'wakamaria_league'):
            path=Path(__file__).resolve().parents[1]/'wakamaria'/'wakamaria'/'doctype'/slug/(slug+'.json')
            meta=json.loads(path.read_text())
            self.assertEqual(meta.get('allow_import'),1)
            self.assertTrue(any(p.get('role')=='System Manager' and p.get('import') and p.get('create') for p in meta['permissions']))
