"""Opt-in experimental GOAL fixture linking and result checking."""
from collections import defaultdict
from zoneinfo import ZoneInfo
import frappe
from frappe.utils import add_days, get_datetime, get_system_timezone, now_datetime
from wakamaria.bulk_match import goal_fixture, local_to_utc, select_unique
from wakamaria.goal_preview import get_pages
from wakamaria.goal_scores import regulation_score

MAX_GROUPS = 5
MAX_RECORDS = 5000


def sync_all():
    """Scheduled hook. Disabled by default; failure doesn't affect football-data.org."""
    settings = frappe.get_single('Wakamaria Settings')
    if not settings.goal_auto_link:
        return
    lock = frappe.cache().lock(frappe.cache().make_key('wakamaria:goal:sync-lock'), timeout=600)
    if not lock.acquire(blocking=False):
        return
    try:
        try:
            _sync(settings)
            frappe.db.set_single_value('Wakamaria Settings', 'goal_sync_error', '')
            frappe.db.set_single_value('Wakamaria Settings', 'goal_last_sync', now_datetime())
            # Hold the lock through commit so overlapping jobs cannot double-link.
            frappe.db.commit()
        except Exception:
            frappe.db.rollback()
            # No credential, provider payload, URL or traceback is logged.
            frappe.db.set_single_value('Wakamaria Settings', 'goal_sync_error',
                'GOAL sync failed. Check key, league IDs, response format, network and limits.')
            frappe.log_error(title='Wakamaria GOAL sync failed', message='Check settings and provider availability; credentials are not logged.')
            frappe.db.commit()
    finally:
        lock.release()


def _sync(settings):
    key = settings.get_password('goal_api_key', raise_exception=False)
    if not key: raise ValueError('Missing key')
    league_rows = frappe.get_all('Wakamaria League', fields=['name', 'goal_api_league_id'], limit_page_length=0)
    leagues = {d.name: d.goal_api_league_id for d in league_rows if d.goal_api_league_id}
    if any(str(v).lower().startswith('gapi_') or key in str(v) for v in leagues.values()):
        raise ValueError('Key in league ID')
    now = now_datetime()
    docs = frappe.get_all('Wakamaria Match',
        filters={'kickoff':['between', [add_days(now, -14), add_days(now, 30)]]},
        fields=['name','league','home_team','away_team','kickoff','provider_match_id',
                'goal_match_id','goal_home_team_id','goal_away_team_id','result_confirmed',
                'goal_result_managed','home_score','away_score'],
        limit_page_length=MAX_RECORDS+1)
    if len(docs) > MAX_RECORDS: raise ValueError('Too many matches')
    # Includes IDs outside the time window, so we cannot attach an existing link.
    linked = frappe.get_all('Wakamaria Match', filters={'goal_match_id':['is','set']},
                            fields=['name','goal_match_id'], limit_page_length=MAX_RECORDS+1)
    if len(linked) > MAX_RECORDS: raise ValueError('Too many existing links')
    owners = defaultdict(set)
    for d in linked:
        if d.goal_match_id: owners[str(d.goal_match_id)].add(d.name)
    groups = defaultdict(list)
    by_name = {}
    zone = ZoneInfo(get_system_timezone())
    utc_now = local_to_utc(now, zone)
    for d in docs:
        if d.league not in leagues: continue
        try: kickoff = local_to_utc(get_datetime(d.kickoff), zone)
        except ValueError: continue
        row={'name':d.name, 'competition':leagues[d.league], 'home':d.home_team,
             'away':d.away_team, 'kickoff':kickoff}
        groups[(row['competition'], kickoff.date().isoformat())].append(row)
        by_name[d.name] = d
    keys = sorted(groups)
    if not keys: return
    cache_key = 'wakamaria:goal:group_offset'
    start = int(frappe.cache().get_value(cache_key) or 0) % len(keys)
    selected_groups = (keys + keys)[start:start + min(MAX_GROUPS, len(keys))]
    budget = [0]
    # Fetch all selected groups before any write; failure cannot cause partial matching.
    all_rows, all_fixtures, originals = [], [], {}
    for competition, day in selected_groups:
        for item in get_pages(day, competition, key, budget):
            parsed = goal_fixture(item, competition)
            if parsed:
                all_fixtures.append(parsed)
                originals.setdefault(parsed['id'], item)
        all_rows.extend(groups[(competition, day)])
    choices = select_unique(all_rows, all_fixtures)
    for row in all_rows:
        d = by_name[row['name']]
        if d.provider_match_id or (d.result_confirmed and not d.goal_result_managed):
            continue  # Existing football-data.org link and manually owned results stay untouched.
        # Hold a row lock across re-check and save to avoid racing a human edit.
        doc = frappe.get_doc('Wakamaria Match', d.name, for_update=True)
        if (doc.league != d.league or doc.home_team != d.home_team or doc.away_team != d.away_team
            or get_datetime(doc.kickoff) != get_datetime(d.kickoff) or doc.provider_match_id
            or str(doc.goal_match_id or '') != str(d.goal_match_id or '')
            or bool(doc.result_confirmed) != bool(d.result_confirmed)
            or bool(doc.goal_result_managed) != bool(d.goal_result_managed)
            or doc.home_score != d.home_score or doc.away_score != d.away_score):
            continue
        match = choices.get(d.name)
        valid = bool(match)
        if valid and d.goal_match_id:
            valid = (str(d.goal_match_id) == match['id'] and str(d.goal_home_team_id or '') == match['home_id']
                     and str(d.goal_away_team_id or '') == match['away_id'] and owners[match['id']] == {d.name})
        elif valid:
            valid = not owners[match['id']] and not d.result_confirmed
        if not valid:
            # A complete provider response can retract or change a previously
            # linked fixture. Do not leave a GOAL-managed Win/Lose visible.
            if settings.goal_auto_results and doc.goal_result_managed and doc.result_confirmed:
                doc.result_confirmed = 0
                doc.flags.wakamaria_goal_sync = True
                doc.save(ignore_permissions=True)
            continue
        if not d.goal_match_id:
            doc.goal_match_id = match['id']
            doc.goal_home_team_id = match['home_id']
            doc.goal_away_team_id = match['away_id']
            owners[match['id']].add(d.name)
        item = originals[match['id']]
        doc.goal_last_status = str(item.get('matchStatus') or '')[:140]
        doc.goal_last_checked = now_datetime()
        if settings.goal_auto_results:
            score = regulation_score(item, utc_now)
            if score is not None:
                doc.home_score, doc.away_score = score
                doc.result_confirmed = 1
                doc.goal_result_managed = 1
            elif doc.goal_result_managed:
                doc.result_confirmed = 0
        doc.flags.wakamaria_goal_sync = True
        doc.save(ignore_permissions=True)
    frappe.cache().set_value(cache_key, (start + len(selected_groups)) % len(keys))
