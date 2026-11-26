"""Guards the browser bundle against the class of bug that emptied the site.

A scripted edit replaced the tipText map and, because the map had lost its
trailing semicolon on an earlier pass, swallowed the line beneath it —
deleting `fmtOdds`. `node --check` still passed (the file was valid JavaScript),
the page still loaded, the league sidebar still filled, and the match list sat
on "Loading matches..." forever because the renderer threw on the first row.

Every helper the renderer calls must be defined in the same file.
"""
import pathlib
import re
import unittest

JS = pathlib.Path(__file__).resolve().parents[1] / "wakamaria" / "public" / "js" / "website.js"

HELPERS = ("esc", "image", "badge", "dateParts", "safeImage", "fmtOdds",
           "ruleOf", "ruleStats")


class TestWebsiteBundle(unittest.TestCase):

    def setUp(self):
        self.source = JS.read_text(encoding="utf-8")

    def test_helpers_are_defined(self):
        for name in HELPERS:
            pattern = rf"\bconst {name}\s*=|function {name}\s*\("
            self.assertRegex(self.source, pattern,
                             f"{name} is used by the renderer but never defined")

    def test_the_two_rules_are_switchable(self):
        """Ben Rule and Grace Rule share a row, so both field sets must exist."""
        self.assertIn("grace_prediction", self.source)
        self.assertIn("grace_odds", self.source)
        self.assertIn("grace_outcome", self.source)
        self.assertIn("data-rule", pathlib.Path(str(JS)).parents[3]
                      .joinpath("wakamaria", "www", "wakamaria.html").read_text(encoding="utf-8"))

    def test_every_market_has_a_label(self):
        """A missing tipText entry renders an empty subtitle, not an error."""
        import sys
        sys.path.insert(0, str(JS.parents[3]))
        from wakamaria.tips import TIPS
        for tip in TIPS:
            self.assertIn(f"'{tip}':", self.source,
                          f"website.js has no label for {tip!r}")

    def test_no_stray_python_artefacts(self):
        for marker in ("\\n", "None,", "True,"):
            self.assertNotIn(marker, self.source)


if __name__ == "__main__":
    unittest.main()
