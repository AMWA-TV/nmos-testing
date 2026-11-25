import unittest

from nmostesting.IS05Utils import IMMEDIATE_ACTIVATION, IS05Utils, SCHEDULED_ABSOLUTE_ACTIVATION


class RequestedTimeTests(unittest.TestCase):
    def test_immediate_activation_accepts_requested_time_at_or_before_activation(self):
        self.assertTrue(IS05Utils.check_requested_time(IMMEDIATE_ACTIVATION,
                                                       "100:50", None, "100:50"))
        self.assertTrue(IS05Utils.check_requested_time(IMMEDIATE_ACTIVATION,
                                                       "100:49", None, "100:50"))

    def test_immediate_activation_rejects_missing_or_malformed_requested_time(self):
        for requested_time in (None, "", "100", "100:not-nanoseconds"):
            with self.subTest(requested_time=requested_time):
                self.assertFalse(IS05Utils.check_requested_time(IMMEDIATE_ACTIVATION,
                                                                requested_time, None, "100:50"))

    def test_immediate_activation_rejects_requested_time_after_activation(self):
        self.assertFalse(IS05Utils.check_requested_time(IMMEDIATE_ACTIVATION,
                                                        "100:51", None, "100:50"))

    def test_immediate_activation_rejects_missing_activation_time(self):
        self.assertFalse(IS05Utils.check_requested_time(IMMEDIATE_ACTIVATION,
                                                        "100:50", None, None))

    def test_scheduled_activation_requires_the_requested_time(self):
        self.assertTrue(IS05Utils.check_requested_time(SCHEDULED_ABSOLUTE_ACTIVATION,
                                                       "100:50", "100:50", "100:51"))
        self.assertFalse(IS05Utils.check_requested_time(SCHEDULED_ABSOLUTE_ACTIVATION,
                                                        "100:49", "100:50", "100:51"))


if __name__ == "__main__":
    unittest.main()
