import unittest

from wakamaria import ownership


class TestDecide(unittest.TestCase):
    """The agent's rule: create, adopt, or skip."""

    def test_free_fixture_is_created(self):
        self.assertEqual(ownership.decide(None), "create")

    def test_linked_row_is_skipped(self):
        row = {"name": "M1", "provider_match_id": "12345", "predicted_by": "Agent"}
        self.assertEqual(ownership.decide(row), "skip")

    def test_agent_row_is_skipped(self):
        row = {"name": "M1", "provider_match_id": None, "predicted_by": "Agent"}
        self.assertEqual(ownership.decide(row), "skip")

    def test_hand_entered_row_is_adopted(self):
        """A typed row has no provider id, so it can never settle on its own."""
        row = {"name": "M1", "provider_match_id": None, "predicted_by": ""}
        self.assertEqual(ownership.decide(row), "adopt")

    def test_imported_row_is_adopted(self):
        row = {"name": "M1", "provider_match_id": None, "predicted_by": "Manual"}
        self.assertEqual(ownership.decide(row), "adopt")


class TestUploadDecision(unittest.TestCase):
    """The import's rule: create, skip, or block."""

    def test_free_fixture_is_created(self):
        self.assertEqual(ownership.upload_decision(None), "create")

    def test_agent_prediction_is_left_alone(self):
        row = {"name": "M1", "provider_match_id": "12345", "predicted_by": "Agent"}
        self.assertEqual(ownership.upload_decision(row), "skip")

    def test_unlinked_agent_row_is_still_skipped(self):
        row = {"name": "M1", "provider_match_id": None, "predicted_by": "Agent"}
        self.assertEqual(ownership.upload_decision(row), "skip")

    def test_hand_entered_row_blocks_a_second_copy(self):
        row = {"name": "M1", "provider_match_id": None, "predicted_by": ""}
        self.assertEqual(ownership.upload_decision(row), "block")

    def test_the_two_rules_never_both_skip(self):
        """Adoption must remain reachable, or manual rows never settle."""
        manual = {"name": "M1", "provider_match_id": None, "predicted_by": ""}
        self.assertEqual(ownership.decide(manual), "adopt")
        self.assertEqual(ownership.upload_decision(manual), "block")


if __name__ == "__main__":
    unittest.main()
