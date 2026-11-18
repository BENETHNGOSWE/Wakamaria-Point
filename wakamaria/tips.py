"""Single source of truth for the markets Wakamaria publishes.

`rules.py` settles these, `model.py` prices them, the Doctype form offers them
and the website labels them. Adding a market here is the only edit required —
`tests/test_tips.py` fails the build if the form or the site drifts.

No Frappe import: this module is safe to load anywhere.
"""

# tip code -> the plain-English line shown under it on the site
LABELS = {
    "1": "Home win",
    "X": "Draw",
    "2": "Away win",
    "1X": "Home win or draw",
    "X2": "Draw or away win",
    "12": "Either team wins",
    "Over 2.5": "3 or more goals",
    "Under 2.5": "Fewer than 3 goals",
    "Under 3.5": "Fewer than 4 goals",
    "BTTS Yes": "Both teams score",
    "BTTS No": "At least one team does not score",
}

# Grouping used by the agent so one day's list is not six variations of the
# same idea. Keep every tip in exactly one family.
FAMILIES = {
    "1": "1X2",
    "X": "1X2",
    "2": "1X2",
    "1X": "Double chance",
    "X2": "Double chance",
    "12": "Double chance",
    "Over 2.5": "Total goals",
    "Under 2.5": "Total goals",
    "Under 3.5": "Total goals",
    "BTTS Yes": "Both teams to score",
    "BTTS No": "Both teams to score",
}

TIPS = tuple(LABELS)


def label(tip):
    return LABELS.get(tip, "")


def family(tip):
    return FAMILIES.get(tip, "Other")
