import frappe
from frappe import _
from frappe.model.document import Document
from wakamaria.rules import evaluate

class WakamariaMatch(Document):
    def validate(self):
        if self.home_team and self.away_team and self.home_team.strip().casefold() == self.away_team.strip().casefold():
            frappe.throw(_("Home and away teams must be different."))
        if self.home_score is not None and self.home_score < 0 or self.away_score is not None and self.away_score < 0:
            frappe.throw(_("Scores cannot be negative."))
        if self.provider_match_id and not str(self.provider_match_id).isdigit():
            frappe.throw(_("Provider match ID must be numeric."))
        if self.provider_match_id and frappe.db.exists("Wakamaria Match", {"provider_match_id": self.provider_match_id, "name": ["!=", self.name or ""]}):
            frappe.throw(_("This provider fixture is already linked to another Wakamaria Match."))
        self.outcome = evaluate(self.prediction, self.home_score, self.away_score) if self.result_confirmed else "Pending"
