import unittest
from unittest.mock import MagicMock

from nmostesting.IS05Utils import IS05Utils


class TransportParamTests(unittest.TestCase):
    def make_utils(self, staged):
        utils = IS05Utils("http://node.example/x-nmos/connection/v1.1/")
        utils.get_num_paths = MagicMock(return_value=2)
        utils.checkCleanRequestJSON = MagicMock(side_effect=[
            (True, {}),
            (True, {"transport_params": staged}),
        ])
        return utils

    def test_accepts_one_matching_value_per_constraint(self):
        utils = self.make_utils([
            {"destination_port": 5004},
            {"destination_port": 5006},
        ])

        valid, message = utils.check_change_transport_param(
            "sender", [], "destination_port", [5004, 5006], "sender-id")

        self.assertTrue(valid)
        self.assertEqual(message, "")

    def test_reports_missing_transport_param_leg(self):
        utils = self.make_utils([{"destination_port": 5004}])

        valid, message = utils.check_change_transport_param(
            "sender", [], "destination_port", [5004, 5006], "sender-id")

        self.assertFalse(valid)
        self.assertIn("does not match the advertised constraints", message)
        self.assertIn("(1)", message)
        self.assertIn("(2)", message)

    def test_reports_extra_transport_param_leg(self):
        utils = self.make_utils([
            {"destination_port": 5004},
            {"destination_port": 5006},
            {"destination_port": 5008},
        ])

        valid, message = utils.check_change_transport_param(
            "sender", [], "destination_port", [5004, 5006], "sender-id")

        self.assertFalse(valid)
        self.assertIn("does not match the advertised constraints", message)

    def test_empty_constraints_do_not_raise_index_error(self):
        utils = IS05Utils("http://node.example/x-nmos/connection/v1.1/")
        utils.get_num_paths = MagicMock(return_value=0)
        utils.checkCleanRequestJSON = MagicMock(side_effect=[
            (True, {}),
            (True, {"transport_params": []}),
        ])

        valid, message = utils.check_change_transport_param(
            "sender", [], "destination_port", [], "sender-id")

        self.assertTrue(valid)
        self.assertEqual(message, "")


if __name__ == "__main__":
    unittest.main()
