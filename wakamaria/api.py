"""Small, intentionally limited public interface; no admin fields or secrets."""
from datetime import timezone
from zoneinfo import ZoneInfo
import frappe
from frappe.utils import get_datetime, get_system_timezone

@frappe.whitelist(allow_guest=True)
def list_matches():
    leagues = frappe.get_all("Wakamaria League", filters={"enabled": 1}, fields=["name", "league_name", "country", "league_image"], order_by="league_name asc")
    enabled = {x.name for x in leagues}
    rows = frappe.get_all("Wakamaria Match", filters={"published": 1, "league": ["in", list(enabled) or [""]]}, fields=["name", "league", "home_team", "away_team", "kickoff", "prediction", "odds", "odds_source", "confidence", "result_confirmed", "home_score", "away_score", "outcome", "provider_status", "grace_prediction", "grace_odds", "grace_confidence", "grace_outcome"], order_by="kickoff desc", limit_page_length=500)
    return {"leagues": leagues, "matches": rows, "timezone":get_system_timezone()}

@frappe.whitelist(allow_guest=True)
def match_details(name):
    # Do not disclose existence, scores or notes of non-public entries.
    row = frappe.db.get_value("Wakamaria Match", {"name": name, "published": 1}, ["league", "kickoff", "provider_home_team_id", "provider_away_team_id"], as_dict=True)
    if not row or not frappe.db.get_value("Wakamaria League", {"name": row.league, "enabled": 1}, "name"):
        frappe.throw("Match not found", frappe.DoesNotExistError)
    cutoff = get_datetime(row.kickoff).replace(tzinfo=ZoneInfo(get_system_timezone())).astimezone(timezone.utc)
    def recent(team):
        if not team or not str(team).isdigit(): return []
        cached = frappe.cache().get_value("wakamaria:history:"+str(team)) or []
        output=[]
        for event in cached:
            try:
                date = get_datetime(event["date"])
                if date.tzinfo is None: date = date.replace(tzinfo=timezone.utc)
                if date.astimezone(timezone.utc) >= cutoff: continue
                output.append(event)
            except (ValueError, KeyError, TypeError):
                continue
        return sorted(output, key=lambda x: x["date"], reverse=True)[:3]
    return {"home":recent(row.provider_home_team_id), "away":recent(row.provider_away_team_id)}
