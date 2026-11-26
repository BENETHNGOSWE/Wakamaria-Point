import frappe
from frappe import _
from frappe.model.document import Document
from wakamaria.rules import evaluate

class WakamariaMatch(Document):
    def validate(self):
        old = self.get_doc_before_save()
        if old and not self.flags.get('wakamaria_goal_sync'):
            identity = ('league', 'home_team', 'away_team', 'kickoff')
            if old.goal_match_id and any(getattr(old, field) != getattr(self, field) for field in identity):
                # Editing a linked fixture invalidates its provider identity.
                self.goal_match_id = self.goal_home_team_id = self.goal_away_team_id = ''
                self.goal_last_status = ''
                self.goal_last_checked = None
                self.result_confirmed = 0
                self.goal_result_managed = 0
            elif old.goal_result_managed and any(getattr(old, field) != getattr(self, field) for field in ('home_score', 'away_score', 'result_confirmed')):
                # Human corrections take ownership and are not replaced by sync.
                self.goal_result_managed = 0
        if self.home_team and self.away_team and self.home_team.strip().casefold() == self.away_team.strip().casefold():
            frappe.throw(_("Home and away teams must be different."))
        if self.home_score is not None and self.home_score < 0 or self.away_score is not None and self.away_score < 0:
            frappe.throw(_("Scores cannot be negative."))
        if self.provider_match_id and not str(self.provider_match_id).isdigit():
            frappe.throw(_("Provider match ID must be numeric."))
        if self.provider_match_id and frappe.db.exists("Wakamaria Match", {"provider_match_id": self.provider_match_id, "name": ["!=", self.name or ""]}):
            frappe.throw(_("This provider fixture is already linked to another Wakamaria Match."))
        self.outcome = evaluate(self.prediction, self.home_score, self.away_score) if self.result_confirmed else "Pending"
        # Both rules ride the same fixture, so they settle from the same score.
        grace_tip = getattr(self, "grace_prediction", None)
        self.grace_outcome = (evaluate(grace_tip, self.home_score, self.away_score)
                              if self.result_confirmed and grace_tip else "Pending")
