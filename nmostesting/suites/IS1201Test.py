# Copyright (C) 2023 Advanced Media Workflow Association
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

import time

from .. import Config as CONFIG
from ..GenericTest import GenericTest, NMOSTestException
from ..IS04Utils import IS04Utils
from ..TestHelper import WebsocketWorker

NODE_API_KEY = "node"
CONTROL_API_KEY = "ncp"


class IS1201Test(GenericTest):

    def __init__(self, apis, **kwargs):
        # Remove the RAML key to prevent this test suite from auto-testing IS-04 API
        apis[NODE_API_KEY].pop("raml", None)
        GenericTest.__init__(self, apis, **kwargs)
        self.node_url = self.apis[NODE_API_KEY]["url"]
        self.ncp_url = self.apis[CONTROL_API_KEY]["url"]
        self.is04_utils = IS04Utils(self.node_url)
        self.ncp_websocket = None

    def set_up_tests(self):
        # Do nothing
        pass

    def tear_down_tests(self):
        # Clean up Websocket resources
        if self.ncp_websocket:
            self.ncp_websocket.close()

    def test_01(self, test):
        """At least one Device is showing an IS-12 control advertisement matching the API under test"""

        control_type = "urn:x-nmos:control:ncp/" + self.apis[CONTROL_API_KEY]["version"]
        return self.is04_utils.do_test_device_control(
            test,
            self.node_url,
            control_type,
            self.ncp_url,
            self.authorization
        )

    def create_ncp_socket(self, test):
        # Reuse socket if connection already established
        if self.ncp_websocket:
            return True

        # Create a WebSocket connection to NMOS Control Protocol endpoint
        self.ncp_websocket = WebsocketWorker(self.apis[CONTROL_API_KEY]["url"])
        self.ncp_websocket.start()

        # Give WebSocket client a chance to start and open its connection
        start_time = time.time()
        while time.time() < start_time + CONFIG.WS_MESSAGE_TIMEOUT:
            if self.ncp_websocket.is_open():
                break
            time.sleep(0.2)

        if self.ncp_websocket.did_error_occur():
            raise NMOSTestException(test.FAIL("Error opening WebSocket connection to {}: {}"
                                              .format(self.apis[CONTROL_API_KEY]["url"],
                                                      self.ncp_websocket.get_error_message())))
        else:
            return self.ncp_websocket.is_open()

    def test_02(self, test):
        """WebSocket successfully opened on advertised urn:x-nmos:control:ncp endpoint"""

        if not self.create_ncp_socket(test):
            return test.FAIL("Failed to open WebSocket successfully")

        return test.PASS("WebSocket successfully opened")
