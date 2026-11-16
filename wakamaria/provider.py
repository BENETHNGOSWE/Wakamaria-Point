"""Only this module contacts football-data.org. API keys never go to browsers."""
from datetime import datetime, timedelta, timezone
import requests
import frappe
from frappe import _

BASE = "https://api.football-data.org/v4"

def api_get(path, params=None):
    settings = frappe.get_single("Wakamaria Settings")
    key = settings.get_password("api_key", raise_exception=False)
    if not key:
        frappe.throw(_("Configure the football-data.org API key in Wakamaria Settings."))
    response = requests.get(BASE + path, params=params, headers={"X-Auth-Token": key}, timeout=20)
    response.raise_for_status()
    return response.json()

@frappe.whitelist()
def fixture_candidates(league, kickoff):
    if not (frappe.has_permission("Wakamaria Match", "create") or frappe.has_permission("Wakamaria Match", "write")):
        frappe.throw(_("Not permitted"), frappe.PermissionError)
    from frappe.utils import get_datetime, convert_utc_to_system_timezone
    date = get_datetime(kickoff).date()
    code = frappe.db.get_value("Wakamaria League", league, "provider_code")
    if not code or not str(code).isalnum():
        frappe.throw(_("Set the league's football-data.org competition code first."))
    data = api_get(f"/competitions/{code}/matches", {"dateFrom": str(date - timedelta(days=1)), "dateTo": str(date + timedelta(days=1))})
    out = []
    for m in data.get("matches", []):
        if not m.get("id") or not m.get("utcDate"):
            continue
        dt = datetime.fromisoformat(m["utcDate"].replace("Z", "+00:00")).replace(tzinfo=None)
        local = convert_utc_to_system_timezone(dt).replace(tzinfo=None)
        out.append({"id":str(m["id"]), "home":m["homeTeam"]["name"], "away":m["awayTeam"]["name"], "home_id":str(m["homeTeam"]["id"]), "away_id":str(m["awayTeam"]["id"]), "kickoff":str(local)})
    return out
