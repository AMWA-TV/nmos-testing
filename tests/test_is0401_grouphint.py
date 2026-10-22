import unittest

from nmostesting.TestResult import Test, TestStates
from nmostesting.suites.IS0401Test import GROUPHINT_KEY, IS0401Test


GROUPHINT = "urn:x-nmos:tag:grouphint/v1.0"


class Response:
    status_code = 200

    def __init__(self, resources):
        self.resources = resources

    def json(self):
        return self.resources


class GrouphintTestCase(unittest.TestCase):
    def run_test_23(self, senders, receivers):
        test_suite = IS0401Test.__new__(IS0401Test)
        test_suite.apis = {GROUPHINT_KEY: {"spec_branch": "main"}}
        test_suite.node_url = "http://example.test/x-nmos/node/v1.3/"
        resources = {
            "senders": Response(senders),
            "receivers": Response(receivers)
        }
        test_suite.do_request = lambda method, url: (True, resources[url.rsplit("/", 1)[-1]])
        return test_suite.test_23(Test("test grouphint roles"))

    def resource(self, resource_id):
        return {
            "id": resource_id,
            "device_id": "device-a",
            "tags": {GROUPHINT: ["studio-a:program:device"]}
        }

    def test_role_may_be_shared_by_sender_and_receiver(self):
        result = self.run_test_23(
            [self.resource("sender-a")],
            [self.resource("receiver-a")]
        )

        self.assertEqual(TestStates.PASS, result.state)

    def test_role_must_remain_unique_within_resource_type(self):
        result = self.run_test_23(
            [self.resource("sender-a"), self.resource("sender-b")],
            []
        )

        self.assertEqual(TestStates.FAIL, result.state)

    def test_role_must_remain_unique_within_receivers(self):
        result = self.run_test_23(
            [],
            [self.resource("receiver-a"), self.resource("receiver-b")]
        )

        self.assertEqual(TestStates.FAIL, result.state)


if __name__ == "__main__":
    unittest.main()
