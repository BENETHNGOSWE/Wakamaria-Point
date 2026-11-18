"""Error reporting must be useful and must never carry a credential."""
import unittest

from wakamaria.diagnostics import describe_error


class FakeResponse:
    def __init__(self, status_code, text=""):
        self.status_code = status_code
        self.text = text


class FakeHTTPError(Exception):
    def __init__(self, response=None):
        super().__init__("boom")
        self.response = response


class TestDescribeError(unittest.TestCase):
    def test_http_status_and_provider_message_are_surfaced(self):
        error = FakeHTTPError(FakeResponse(403, '{"message":"You do not have access to this competition."}'))
        text = describe_error(error)
        self.assertIn("HTTP 403", text)
        self.assertIn("do not have access", text)

    def test_whitespace_is_collapsed_for_a_single_log_line(self):
        error = FakeHTTPError(FakeResponse(429, '{"message":\n  "rate limited"}'))
        self.assertNotIn("\n", describe_error(error))

    def test_long_bodies_are_truncated(self):
        error = FakeHTTPError(FakeResponse(500, "x" * 5000))
        self.assertLessEqual(len(describe_error(error)), 220)

    def test_an_error_without_a_response_still_describes_itself(self):
        self.assertIn("ValueError", describe_error(ValueError("bad input")))

    def test_headers_are_never_included(self):
        """The football-data.org key travels in X-Auth-Token; it must not leak."""
        response = FakeResponse(403, '{"message":"invalid token"}')
        text = describe_error(FakeHTTPError(response))
        self.assertNotIn("X-Auth-Token", text)
        self.assertNotIn("ghp_", text)


if __name__ == "__main__":
    unittest.main()
