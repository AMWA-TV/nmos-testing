# Copyright (C) 2025 Advanced Media Workflow Association
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


from ..GenericTest import GenericTest, NMOSTestException
from ..BCP008Utils import BCP008Utils, NcStatusMonitorProperties
from ..MS05Utils import NcMethodStatus

SENDER_MONITOR_API_KEY = "sendermonitor"
NODE_API_KEY = "node"
CONN_API_KEY = "connection"
CONTROL_API_KEY = "ncp"
CONTROL_FRAMEWORK_API_KEY = "controlframework"

SENDER_MONITOR_CLASS_ID = [1, 2, 2, 2]

SENDER_MONITOR_SPEC_ROOT = "https://specs.amwa.tv/bcp-008-02/branches/"
CONTROL_FRAMEWORK_SPEC_ROOT = "https://specs.amwa.tv/ms-05-02/branches/"
CONTROL_PROTOCOL_SPEC_ROOT = "https://specs.amwa.tv/is-12/branches/"


class BCP0080201Test(GenericTest):
    """
    Runs Tests covering BCP-008-01
    """
    class TestMetadata():
        def __init__(self, checked=False, error=False, error_msg="", link=""):
            self.checked = checked
            self.error = error
            self.error_msg = error_msg
            self.link = link

    def __init__(self, apis, node, **kwargs):
        # Don't auto-test /transportfile as it is permitted to generate a 404 when master_enable is false
        omit_paths = [
            "/single/senders/{senderId}/transportfile"
        ]
        # Prevent auto testing of IS-04 and IS-05 APIs
        apis[NODE_API_KEY].pop("raml", None)
        apis[CONN_API_KEY].pop("raml", None)
        GenericTest.__init__(self, apis, omit_paths, **kwargs)
        self.bcp008_utils = BCP008Utils(apis)
        self.sender_monitors = []

    def set_up_tests(self):
        self.bcp008_utils.reset()
        self.bcp008_utils.open_ncp_websocket()
        super().set_up_tests()

    # Override basics to include auto tests
    def basics(self):
        results = super().basics()
        try:
            results += self.bcp008_utils.auto_tests()
        except NMOSTestException as e:
            results.append(e.args[0])
        except Exception as e:
            results.append(self.uncaught_exception("auto_tests", e))
        return results

    def tear_down_tests(self):
        # Clean up Websocket resources
        self.bcp008_utils.close_ncp_websocket()

    def _status_ok(self, method_result):
        if not hasattr(method_result, 'status'):
            return False
        return method_result.status == NcMethodStatus.OK \
            or method_result.status == NcMethodStatus.PropertyDeprecated

    def _get_sender_monitors(self, test):
        if len(self.sender_monitors):
            return self.sender_monitors

        device_model = self.bcp008_utils.query_device_model(test)

        self.sender_monitors = device_model.find_members_by_class_id(SENDER_MONITOR_CLASS_ID,
                                                                     include_derived=True,
                                                                     recurse=True,
                                                                     get_objects=True)

        return self.sender_monitors

    def test_01(self, test):
        """Status reporting delay can be set to values within the published constraints"""
        sender_monitors = self._get_sender_monitors(test)

        if len(sender_monitors) == 0:
            return test.UNCLEAR("No Receiver Monitors found in Device Model")

        default_status_reporting_delay = 3
        for monitor in sender_monitors:
            method_result = self.bcp008_utils.set_property(
                test, NcStatusMonitorProperties.STATUS_REPORTING_DELAY.value,
                default_status_reporting_delay,
                oid=monitor.oid, role_path=monitor.role_path)

            if not self._status_ok(method_result):
                return test.FAIL("SetProperty error: Error setting statusReportingDelay on monitor, "
                                 f"oid={monitor.oid}, "
                                 f"role path={monitor.role_path}")

            method_result = self.bcp008_utils.get_property(
                test, NcStatusMonitorProperties.STATUS_REPORTING_DELAY.value,
                oid=monitor.oid, role_path=monitor.role_path)

            if not self._status_ok(method_result):
                return test.FAIL("GetProperty error: Error getting statusReportingDelay on monitor, "
                                 f"oid={monitor.oid}, "
                                 f"role path={monitor.role_path}")

            if method_result.value != default_status_reporting_delay:
                return test.FAIL("Unexpected status reporting delay on receiver monitor. "
                                 f"Expected={default_status_reporting_delay} actual={method_result.value}, "
                                 f"oid={monitor.oid}, "
                                 f"role path={monitor.role_path}")

        return test.PASS()
