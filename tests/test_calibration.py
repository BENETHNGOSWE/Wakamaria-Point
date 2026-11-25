"""The calibration table must stay sane, or the site starts lying again."""

import unittest

from wakamaria import calibration
from wakamaria.tips import TIPS


class TestCurves(unittest.TestCase):
    def test_every_market_has_a_curve(self):
        for tip in TIPS:
            self.assertIn(tip, calibration.CURVES, f"{tip} has no calibration curve")

    def test_curves_never_decrease(self):
        """A higher stated probability must never mean a lower real one."""
        for tip, knots in calibration.CURVES.items():
            values = [real for _, real in knots]
            self.assertEqual(values, sorted(values), f"{tip} curve is not monotone")

    def test_every_value_is_a_probability(self):
        for tip, knots in calibration.CURVES.items():
            for stated, real in knots:
                self.assertTrue(0.0 <= stated <= 1.0, f"{tip} stated {stated}")
                self.assertTrue(0.0 <= real <= 1.0, f"{tip} real {real}")

    def test_values_outside_the_curve_extend_to_the_corners(self):
        """Holding the curve flat at the ends was a bug.

        The fitted range stops where ordinary league matches stop, so an
        88%-to-happen mismatch market was being reported as 64%. Outside the
        range the curve now runs on to (0, 0) and (1, 1) instead of clamping.
        """
        for tip, knots in calibration.CURVES.items():
            self.assertEqual(calibration.calibrate(tip, 0.0), 0.0)
            self.assertAlmostEqual(calibration.calibrate(tip, 1.0), 1.0, places=6)
            self.assertGreater(calibration.calibrate(tip, 1.0),
                               knots[-1][1], f"{tip} does not extend past its last knot")
            self.assertLess(calibration.calibrate(tip, 0.0), knots[0][1])

    def test_a_near_certainty_can_be_stated(self):
        """The Sabah v Barcelona bug, in one assertion.

        Over 2.5 goals in that fixture is roughly 88%. The table used to top
        out at 64% and report it as such, so the agent skipped it.
        """
        self.assertGreater(calibration.calibrate("Over 2.5", 0.95), 0.80)

    def test_the_known_bias_is_corrected(self):
        """The bug this table exists for.

        The model's own "Over 1.5" figure sits far below what actually happens:
        it says 50% where reality is above 70%, which is why the agent kept
        picking something else instead.
        """
        self.assertGreater(calibration.calibrate("Over 1.5", 0.50), 0.70)

    def test_an_unknown_market_is_left_alone(self):
        self.assertAlmostEqual(calibration.calibrate("Not A Market", 0.42), 0.42)

    def test_calibrate_all_keeps_every_key(self):
        raw = {"Over 1.5": 0.60, "X2": 0.70}
        self.assertEqual(set(calibration.calibrate_all(raw)), set(raw))

    def test_empty_input_is_harmless(self):
        self.assertEqual(calibration.calibrate_all({}), {})
        self.assertIsNone(calibration.calibrate("Over 1.5", None))


if __name__ == "__main__":
    unittest.main()
