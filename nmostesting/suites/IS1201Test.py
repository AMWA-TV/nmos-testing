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

import json
import time
from urllib.parse import urlparse

from .. import Config as CONFIG
from ..GenericTest import GenericTest, NMOSTestException
from ..IS04Utils import IS04Utils
from ..TestHelper import WebsocketWorker, is_ip_address

NODE_API_KEY = "node"
CONTROL_API_KEY = "ncp"


class IS1201Test(GenericTest):

    def __init__(self, apis, **kwargs):
        # Remove the RAML key to prevent this test suite from auto-testing IS-04 API
        apis[NODE_API_KEY].pop("raml", None)
        GenericTest.__init__(self, apis, **kwargs)
        self.apis = apis
        self.is04_utils = IS04Utils(self.apis[NODE_API_KEY]["url"])
        self.ncp_websocket = None

    def set_up_tests(self):
        # Do nothing
        pass

    def tear_down_tests(self):
        # Clean up Websocket resources
        if self.ncp_websocket:
            self.ncp_websocket.close()

    def test_01(self, test):
        """Control endpoint advertised in Node endpoint's Device controls array"""

        # Discover the NMOS Control Protocol endpoint from the Node API
        valid, response = self.do_request("GET", self.apis[NODE_API_KEY]["url"] + "devices")
        if not valid or response.status_code != 200:
            return test.FAIL("Unable to reach Node endpoint")

        ncp_endpoint = None
        found_api_match = False

        try:
            device_type = "urn:x-nmos:control:ncp/" + self.apis[CONTROL_API_KEY]["version"]
            for device in response.json():
                for control in device["controls"]:
                    if control["type"] == device_type:
                        ncp_endpoint = control["href"]
                        if self.is04_utils.compare_urls(self.apis[CONTROL_API_KEY]["url"], control["href"]) and \
                                self.authorization is control.get("authorization", False):
                            found_api_match = True

            if ncp_endpoint and not found_api_match:
                return test.FAIL("Found one or more Device controls, but no href and authorization mode matched the "
                                 "Events API under test")
            elif not found_api_match:
                return test.FAIL("Unable to find any Devices which expose the control type '{}'".format(device_type))

            if ncp_endpoint.startswith("wss://") and is_ip_address(urlparse(ncp_endpoint).hostname):
                return test.WARN("Secure NMOS Control Endpoint has an IP address not a hostname")

        except json.JSONDecodeError:
            return test.FAIL("Non-JSON response returned from Node API")
        except KeyError:
            return test.FAIL("One or more Devices were missing the 'controls' attribute")

        return test.PASS("NMOS Control Endpoint found and validated")

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
