"""The market list exists in four places. This test is what stops them drifting.

Adding a market to tips.py without updating the Doctype form or the website's
label map used to fail silently: the tip settles as Pending forever, or renders
with a blank description. Now it fails the build instead.
"""
import json
import pathlib
import re
import unittest

from wakamaria.tips import FAMILIES, LABELS, TIPS

ROOT = pathlib.Path(__file__).resolve().parent.parent
MATCH_JSON = ROOT / "wakamaria/wakamaria/doctype/wakamaria_match/wakamaria_match.json"
WEBSITE_JS = ROOT / "wakamaria/public/js/website.js"


class TestTipRegistry(unittest.TestCase):
    def test_every_tip_has_a_label(self):
        for tip in TIPS:
            self.assertTrue(LABELS.get(tip), tip)

    def test_every_tip_has_a_family(self):
        for tip in TIPS:
            self.assertTrue(FAMILIES.get(tip), tip)

    def test_families_are_known(self):
        self.assertEqual(set(FAMILIES), set(TIPS))

    def test_doctype_select_options_match_tips(self):
        """A mismatch means staff cannot choose a market the rules can settle."""
        doc = json.loads(MATCH_JSON.read_text())
        field = next(f for f in doc["fields"] if f["fieldname"] == "prediction")
        options = [line.strip() for line in field["options"].splitlines() if line.strip()]
        self.assertEqual(options, list(TIPS),
                         "prediction Select options have drifted from tips.TIPS")

    def test_website_labels_cover_every_tip(self):
        """A missing key renders a blank line under the prediction on the site."""
        source = WEBSITE_JS.read_text()
        start = source.index("const tipText=")
        block = source[start:source.index("};", start)]
        labels = dict(re.findall(r"'([^']+)'\s*:\s*'([^']*)'", block))
        for tip in TIPS:
            self.assertIn(tip, labels, f"website.js tipText is missing {tip!r}")
            self.assertEqual(labels[tip], LABELS[tip], f"label drifted for {tip!r}")


if __name__ == "__main__":
    unittest.main()
