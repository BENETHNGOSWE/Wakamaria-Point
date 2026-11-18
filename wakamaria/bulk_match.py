"""Conservative fixture matching with narrowly scoped aliases; no fuzzy names."""
from datetime import datetime, timezone
import unicodedata


def canonical_name(value):
    if not isinstance(value, str):
        return ''
    return ' '.join(unicodedata.normalize('NFC', value).casefold().split())


# A verified provider name for the senior national side in UEFA Nations League.
# Aliases are explicit and competition-specific; never do general fuzzy matching.
GOAL_ALIASES = {
    'cmr77dw4800fgrx06rwmig2h8': {'ireland': 'republic of ireland'},
}


def matching_name(value, competition):
    name = canonical_name(value)
    return GOAL_ALIASES.get(competition, {}).get(name, name)


def utc_instant(value):
    if not isinstance(value, str):
        raise ValueError('Expected timestamp string')
    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if dt.tzinfo is None:
        raise ValueError('Provider timestamp has no timezone')
    return dt.astimezone(timezone.utc)


def select_unique(rows, fixtures):
    """Return {row name: fixture} only when each side has exactly one partner.

    Rows: name, competition, home, away, kickoff (aware datetime).
    Fixtures: id, competition, home, away, kickoff (aware datetime), home_id, away_id.
    Exact same kickoff is deliberate: rescheduled or rounded times need human review.
    """
    edges = {}
    by_id = {}
    # Repeated provider IDs or inconsistent data make that entire ID ineligible.
    duplicate_ids = set()
    for f in fixtures:
        ident = f.get('id')
        if not isinstance(ident, str) or not ident:
            continue
        if ident in by_id:
            if by_id[ident] != f:
                duplicate_ids.add(ident)
        else:
            by_id[ident] = f
    counts = {}
    for row in rows:
        candidates = []
        for ident, f in by_id.items():
            if ident in duplicate_ids or not f.get('home_id') or not f.get('away_id'):
                continue
            if (row['competition'] == f.get('competition')
                and canonical_name(row['home']) and canonical_name(row['away'])
                and matching_name(row['home'], row['competition']) == matching_name(f.get('home'), row['competition'])
                and matching_name(row['away'], row['competition']) == matching_name(f.get('away'), row['competition'])
                and row['kickoff'] == f.get('kickoff')):
                candidates.append(ident)
                counts[ident] = counts.get(ident, 0) + 1
        edges[row['name']] = candidates
    return {name: by_id[ids[0]] for name, ids in edges.items()
            if len(ids) == 1 and counts[ids[0]] == 1}


def goal_fixture(item, competition):
    """Parse only explicit fields; malformed or different league records are ignored."""
    if not isinstance(item, dict): return None
    league = item.get('league') or {}
    home, away = item.get('homeTeam') or {}, item.get('awayTeam') or {}
    if not all(isinstance(x, dict) for x in (league, home, away)): return None
    if str(league.get('id') or item.get('leagueId') or '') != competition: return None
    try:
        kickoff = utc_instant(item.get('kickoffUtc'))
    except (ValueError, TypeError):
        return None
    ident, hid, aid = item.get('id'), home.get('id'), away.get('id')
    if not all(isinstance(v, str) and v for v in (ident, hid, aid, home.get('name'), away.get('name'))):
        return None
    return {'id': ident, 'home_id': hid, 'away_id': aid, 'competition': competition,
            'home': home['name'], 'away': away['name'], 'kickoff': kickoff}


def local_to_utc(value, zone):
    """Reject ambiguous/nonexistent local wall times rather than guessing DST."""
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc)
    first = value.replace(tzinfo=zone, fold=0)
    second = value.replace(tzinfo=zone, fold=1)
    if first.utcoffset() != second.utcoffset():
        raise ValueError('Ambiguous or nonexistent local time')
    result = first.astimezone(timezone.utc)
    if result.astimezone(zone).replace(tzinfo=None) != value:
        raise ValueError('Nonexistent local time')
    return result


def football_data_fixture(item, competition):
    if not isinstance(item, dict): return None
    comp, home, away = item.get('competition') or {}, item.get('homeTeam') or {}, item.get('awayTeam') or {}
    if not all(isinstance(x, dict) for x in (comp, home, away)) or comp.get('code') != competition:
        return None
    ident, hid, aid = item.get('id'), home.get('id'), away.get('id')
    if any(isinstance(v, bool) or not isinstance(v, int) or v <= 0 for v in (ident, hid, aid)):
        return None
    if not all(isinstance(t.get('name'), str) and t['name'] for t in (home, away)):
        return None
    try: kickoff = utc_instant(item.get('utcDate'))
    except (ValueError, TypeError): return None
    return {'id': str(ident), 'home_id': str(hid), 'away_id': str(aid), 'competition': competition,
            'home': home['name'], 'away': away['name'], 'kickoff': kickoff}
