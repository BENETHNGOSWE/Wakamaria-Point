import frappe

def after_install():
    """Create a small editable set of leagues (do not create sample matches)."""
    leagues = [
        ("Premier League", "England", "PL"), ("La Liga", "Spain", "PD"),
        ("Champions League", "Europe", "CL"), ("Bundesliga", "Germany", "BL1"),
        ("Serie A", "Italy", "SA"), ("Ligue 1", "France", "FL1"),
    ]
    for name, country, code in leagues:
        if not frappe.db.exists("Wakamaria League", name):
            frappe.get_doc({"doctype":"Wakamaria League", "league_name":name, "country":country, "provider_code":code, "enabled":1}).insert(ignore_permissions=True)
