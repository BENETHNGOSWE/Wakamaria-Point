"""Scheduled result sync: selected provider IDs only. Scores are 90-minute scores."""
from datetime import timedelta
import time
import frappe
from frappe.utils import now_datetime, add_days
from wakamaria.provider import api_get
from wakamaria.rules import regulation_score


def sync_all():
    settings = frappe.get_single("Wakamaria Settings")
    if not settings.enabled:
        return
    try:
        # Recheck recent completed matches to pick up provider corrections. Future
        # fixtures are not queried until kickoff, and very old ones are left alone.
        rows = frappe.get_all("Wakamaria Match", filters={"provider_match_id": ["is", "set"], "kickoff": ["between", [add_days(now_datetime(), -14), now_datetime()]]}, fields=["name", "provider_match_id", "provider_home_team_id", "provider_away_team_id"])
        ids = [str(x.provider_match_id) for x in rows if str(x.provider_match_id).isdigit() and x.provider_home_team_id and x.provider_away_team_id]
        by_id = {str(x.provider_match_id): x for x in rows}
        for start in range(0, len(ids), 50):
            if start:
                time.sleep(7)
            data = api_get("/matches", {"ids": ",".join(ids[start:start+50])})
            for item in data.get("matches", []):
                row = by_id.get(str(item.get("id")))
                if not row: continue
                # A previously attached fixture ID must not silently switch teams.
                home_id = str((item.get("homeTeam") or {}).get("id") or "")
                away_id = str((item.get("awayTeam") or {}).get("id") or "")
                if row.provider_home_team_id and row.provider_home_team_id != home_id or row.provider_away_team_id and row.provider_away_team_id != away_id:
                    continue
                doc = frappe.get_doc("Wakamaria Match", row.name)
                doc.provider_status = item.get("status") or ""
                doc.last_checked = now_datetime()
                score = regulation_score(item)
                if score is not None:
                    doc.home_score, doc.away_score = score
                    doc.result_confirmed = 1
                else:
                    # Never display stale win/lose for a cancelled, corrected or
                    # incomplete provider result.
                    doc.result_confirmed = 0
                doc.save(ignore_permissions=True)
        if settings.history_enabled:
            history_rows = frappe.get_all("Wakamaria Match", filters={"published": 1, "kickoff": ["between", [add_days(now_datetime(), -14), add_days(now_datetime(), 14)]]}, fields=["provider_home_team_id", "provider_away_team_id"])
            cache_recent_team_history(history_rows)
        settings.last_sync = now_datetime()
        settings.last_error = ""
        settings.save(ignore_permissions=True)
    except Exception:
        # Do not log HTTP headers, credentials or stack trace with secrets.
        frappe.db.set_single_value("Wakamaria Settings", "last_error", "Sync failed. Check API availability, rate limit, plan coverage and configuration.")
        frappe.log_error(title="Wakamaria result sync failed", message="Check provider configuration and rate limits. No credentials logged.")


def cache_recent_team_history(rows):
    # Limit provider traffic to four missing team caches per run; reuse for all
    # website visitors. Existing cache expires after 6 hours. On a large site a
    # paid plan or a dedicated background queue may be required.
    teams = sorted({str(v) for row in rows for v in (row.provider_home_team_id, row.provider_away_team_id) if v and str(v).isdigit()})
    attempted = 0
    for team_id in teams:
        key = "wakamaria:history:" + team_id
        if frappe.cache().get_value(key) is not None:
            continue
        if attempted >= 4: break
        time.sleep(7)
        payload = api_get(f"/teams/{team_id}/matches", {"status": "FINISHED", "limit": 30})
        values = []
        for m in payload.get("matches", []):
            score = regulation_score(m)
            if score is None: continue
            values.append({"date":m.get("utcDate", ""), "home":(m.get("homeTeam") or {}).get("name", ""), "away":(m.get("awayTeam") or {}).get("name", ""), "score":list(score)})
        frappe.cache().set_value(key, values, expires_in_sec=6*3600)
        attempted += 1
