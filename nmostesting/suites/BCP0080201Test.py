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
from ..BCP008Utils import BCP008Utils

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

    def test_01(self, test):
        """Sender status monitoring"""
        return test.PASS()
