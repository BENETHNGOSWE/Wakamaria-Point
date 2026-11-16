"""Pure 90-minute prediction evaluation; no Frappe dependency."""
TIPS = ("1", "X", "2", "1X", "X2", "12", "Over 2.5", "Under 2.5", "BTTS Yes", "BTTS No")

def evaluate(tip, home, away):
    if tip not in TIPS or home is None or away is None:
        return "Pending"
    if not isinstance(home, int) or not isinstance(away, int) or home < 0 or away < 0:
        return "Pending"
    wins = {
        "1": home > away, "X": home == away, "2": away > home,
        "1X": home >= away, "X2": away >= home, "12": home != away,
        "Over 2.5": home + away > 2, "Under 2.5": home + away < 3,
        "BTTS Yes": home > 0 and away > 0, "BTTS No": home == 0 or away == 0,
    }
    return "Win" if wins[tip] else "Lose"

def regulation_score(match):
    """Do not settle non-finished, awarded or ET games missing regulation scores."""
    if match.get("status") != "FINISHED":
        return None
    score = match.get("score") or {}
    duration = score.get("duration")
    if duration == "REGULAR":
        values = score.get("fullTime") or {}
    elif duration in ("EXTRA_TIME", "PENALTY_SHOOTOUT"):
        values = score.get("regularTime") or {}
    else:
        return None
    home, away = values.get("home"), values.get("away")
    if type(home) is not int or type(away) is not int or home < 0 or away < 0:
        return None
    return home, away
