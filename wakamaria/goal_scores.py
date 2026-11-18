"""Experimental GOAL regulation score selection. Fails closed on contradictions."""
from datetime import timedelta, timezone
from wakamaria.bulk_match import utc_instant


def _integer(value):
    if isinstance(value, bool): return None
    if type(value) is int: number = value
    elif isinstance(value, str) and value.isascii() and value.isdigit(): number = int(value)
    else: return None
    return number if 0 <= number <= 50 else None


def regulation_score(item, now):
    """Candidate FT score for a normally finished game, else None.

    FtScore's 90-minute meaning is based on third-party observations, not official
    GOAL field documentation. The feature must be opt-in and tested on staging.
    """
    if not isinstance(item, dict) or item.get('matchStatus') != 'FINISHED': return None
    if now.tzinfo is None: return None
    try: kickoff = utc_instant(item.get('kickoffUtc'))
    except (ValueError, TypeError): return None
    if now.astimezone(timezone.utc) < kickoff + timedelta(hours=2): return None
    if item.get('matchPeriod') in ('EXTRA_TIME', 'PENALTIES'): return None
    # Avoid all extra time and shootout results, even 0-0 extra time.
    for key in ('homeTeamExtraScore','awayTeamExtraScore','homeTeamPenaltyScore','awayTeamPenaltyScore'):
        if item.get(key) not in (None, ''): return None
    home, away = _integer(item.get('homeTeamFtScore')), _integer(item.get('awayTeamFtScore'))
    if home is None or away is None: return None
    # Requiring both totals to agree avoids ambiguous resets and extra-time totals.
    if _integer(item.get('homeTeamScore')) != home or _integer(item.get('awayTeamScore')) != away:
        return None
    for key, final in (('homeTeamHtScore', home), ('awayTeamHtScore', away)):
        value = item.get(key)
        if value not in (None, ''):
            half = _integer(value)
            if half is None or half > final: return None
    return home, away
