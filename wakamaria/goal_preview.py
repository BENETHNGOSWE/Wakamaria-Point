"""GOAL API diagnostic only; it never changes links, results, or predictions."""
from collections import defaultdict
from datetime import timezone
from zoneinfo import ZoneInfo
import requests
import time
import frappe
from frappe import _
from frappe.utils import get_datetime, get_system_timezone
from wakamaria.bulk_match import goal_fixture, select_unique, local_to_utc

BASE = 'https://api.goal-api.com/v1'
MAX_GROUPS = 10
MAX_PAGES = 10
MAX_REQUESTS = 12


def safe_example(item):
    """Only public fixture fields, never request headers, credentials or account details."""
    if not isinstance(item, dict):
        return {}
    fields = ('id', 'leagueId', 'kickoffUtc', 'matchDate', 'matchTime', 'matchStatus',
              'status', 'score', 'homeTeamScore', 'awayTeamScore', 'homeTeamFtScore', 'awayTeamFtScore')
    out = {k: item[k] for k in fields if k in item and isinstance(item[k], (str, int, float, type(None)))}
    for key in ('league', 'homeTeam', 'awayTeam'):
        val = item.get(key)
        if isinstance(val, dict):
            out[key] = {k: val[k] for k in ('id', 'name') if k in val and isinstance(val[k], (str, int))}
    return out


def get_pages(day, league_id, key, budget):
    """Fail closed on missing pagination, repeated pages, or excessive results."""
    offset, limit, result, seen = 0, 100, [], set()
    for _ in range(MAX_PAGES):
        if budget[0] >= MAX_REQUESTS:
            raise ValueError('Preview request budget exceeded')
        if budget[0]:
            time.sleep(1)
        budget[0] += 1
        response = requests.get(BASE + '/fixtures/date/' + day,
            params={'leagueId': league_id, 'limit': limit, 'offset': offset},
            headers={'Authorization': 'Bearer ' + key}, timeout=20)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or payload.get('success') is not True:
            raise ValueError('Invalid provider response')
        data, pagination = payload.get('data'), payload.get('pagination')
        if not isinstance(data, list) or not isinstance(pagination, dict) or not isinstance(pagination.get('hasMore'), bool):
            raise ValueError('Invalid provider pagination')
        signature = tuple(str(x.get('id')) for x in data if isinstance(x, dict))
        if signature in seen and pagination['hasMore']:
            raise ValueError('Repeated provider page')
        seen.add(signature)
        result.extend(data)
        if not pagination['hasMore']:
            return result
        if not data:
            raise ValueError('Empty provider page')
        offset += limit
    raise ValueError('Provider page limit exceeded')


@frappe.whitelist()
def preview():
    if not frappe.has_permission('Wakamaria Settings', 'write'):
        frappe.throw(_('Not permitted'), frappe.PermissionError)
    settings = frappe.get_single('Wakamaria Settings')
    key = settings.get_password('goal_api_key', raise_exception=False)
    if not key:
        frappe.throw(_('Save your GOAL API key in Wakamaria Settings first.'))
    leagues = {x.name: x.goal_api_league_id for x in frappe.get_all('Wakamaria League', fields=['name', 'goal_api_league_id']) if x.goal_api_league_id}
    # A key in a normal league field can leak into provider query logs.
    if any(str(value).lower().startswith('gapi_') or key in str(value) for value in leagues.values()):
        frappe.throw(_('An API key appears to be in a GOAL league ID field. Remove it, revoke the key and store the replacement only in the password field.'))
    # Include all unlinked, unconfirmed rows, including drafts; never expose publicly.
    docs = frappe.get_all('Wakamaria Match', filters={'result_confirmed': 0}, fields=['name', 'league', 'home_team', 'away_team', 'kickoff', 'provider_match_id'], limit_page_length=501)
    if len(docs) > 500:
        frappe.throw(_('More than 500 unconfirmed matches: reduce the batch before previewing.'))
    zone = ZoneInfo(get_system_timezone())
    rows, groups, no_league = [], defaultdict(list), []
    for d in docs:
        if d.provider_match_id:
            continue
        league_id = leagues.get(d.league)
        if not league_id:
            no_league.append(d.name)
            continue
        # A local datetime is interpreted in the Frappe site timezone.
        local = get_datetime(d.kickoff)
        try:
            kickoff = local_to_utc(local, zone)
        except ValueError:
            no_league.append(d.name)  # deliberately skipped: ambiguous local time
            continue
        row = {'name': d.name, 'competition': league_id, 'home': d.home_team, 'away': d.away_team, 'kickoff': kickoff}
        rows.append(row)
        groups[(league_id, kickoff.date().isoformat())].append(row)
    if len(groups) > MAX_GROUPS:
        frappe.throw(_('More than 10 competition/date groups; reduce the batch before previewing.'))
    fixtures = []
    examples = []
    unparsed = 0
    budget = [0]
    try:
        for (competition, day) in groups:
            for item in get_pages(day, competition, key, budget):
                if len(examples) < 3:
                    examples.append(safe_example(item))
                parsed = goal_fixture(item, competition)
                if parsed:
                    fixtures.append(parsed)
                else:
                    unparsed += 1
    except Exception:
        # requests exception strings may contain URLs; never expose headers or key.
        frappe.throw(_('GOAL API preview failed. Check the key, network, provider limits and response format. No matches were changed.'))
    selected = select_unique(rows, fixtures)
    report = []
    for row in rows:
        fixture = selected.get(row['name'])
        report.append({'match': row['name'], 'home': row['home'], 'away': row['away'],
                       'kickoff_utc': row['kickoff'].isoformat(),
                       'status': 'Exact candidate' if fixture else 'No unique exact candidate',
                       'fixture_id': fixture['id'] if fixture else ''})
    return {'matches': report, 'skipped': len(no_league), 'groups': len(groups), 'examples': examples, 'unparsed': unparsed,
            'note': 'Preview only: no fixture links or results were changed.'}
