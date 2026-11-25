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

    def test_values_outside_the_curve_are_clamped(self):
        for tip, knots in calibration.CURVES.items():
            self.assertEqual(calibration.calibrate(tip, -0.5), knots[0][1])
            self.assertEqual(calibration.calibrate(tip, 5.0), knots[-1][1])

    def test_the_known_bias_is_corrected(self):
        """The bug this table exists for.

        The model said "Over 1.5" was a 22% shot in matches where it happened
        71% of the time, which is why the site kept picking Under 3.5 instead.
        """
        self.assertGreater(calibration.calibrate("Over 1.5", 0.22), 0.65)

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
