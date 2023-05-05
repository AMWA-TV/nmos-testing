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
from time import sleep
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
        self.node_url = apis[NODE_API_KEY]["url"]
        self.node_api_version = apis[NODE_API_KEY]["version"]
        self.is04_utils = IS04Utils(self.node_url)
        self.ncp_url = apis[CONTROL_API_KEY]["url"]
        self.ncp_websocket = None
        self.ncp_ip_address = apis[CONTROL_API_KEY]["ip"]
        self.ncp_hostname = apis[CONTROL_API_KEY]["hostname"]
        self.ncp_port = apis[CONTROL_API_KEY]["port"]
        self.ncp_api_version = apis[CONTROL_API_KEY]["version"]
        self.ncp_api_selector = apis[CONTROL_API_KEY]["selector"]

    def set_up_tests(self):
        # Do nothing
        pass

    def tear_down_tests(self):
        # Clean up Websocket resources
        if self.ncp_websocket:
            self.ncp_websocket.close()

    def test_01(self, test):
        """Control endpoint advertised in Node endpoint's Device controls array"""
        ncp_endpoint = None

        # Discover the NMOS Control Protocol endpoint from the Node API
        valid, response = self.do_request("GET", self.node_url + "devices")
        if not valid or response.status_code != 200:
            return test.FAIL("Unable to reach Node endpoint")
        try:
            node_devices = response.json()
            for device in node_devices:
                for control in device["controls"]:
                    href = control["href"]
                    if self.is04_utils.compare_api_version(self.node_api_version, "v1.3") >= 0 and \
                            control["type"].startswith("urn:x-nmos:control:ncp"):
                        ncp_endpoint = href
                        break

            if not ncp_endpoint:
                return test.FAIL("Control endpoint not found in Node endpoint's Device controls array")

            if not self.is04_utils.compare_urls(ncp_endpoint, "{}://{}:{}/x-nmos/{}/{}/{}"
                                          .format(self.ws_protocol, self.ncp_hostname, self.ncp_port, CONTROL_API_KEY, self.ncp_api_version, self.ncp_api_selector)):
                return test.FAIL("None of the Control endpoints match the Control Protocol API under test")

            if ncp_endpoint.startswith("wss://") and is_ip_address(urlparse(ncp_endpoint).hostname):
                return test.WARN("Secure NMOS Control Endpoint has an IP address not a hostname")

        except json.JSONDecodeError:
            raise NMOSTestException(test.FAIL("Non-JSON response returned from Node API"))
        except KeyError as e:
            raise NMOSTestException(test.FAIL("Unable to find expected key: {}".format(e)))

        return test.PASS("NMOS Control Endpoint found and validated")

    def create_ncp_socket(self, test):
        # Reuse socket if connection already established
        if self.ncp_websocket:
            return True, None

        # Create a WebSocket connection to NMOS Control Protocol endpoint
        self.ncp_websocket = WebsocketWorker(self.ncp_url)
        self.ncp_websocket.start()
        sleep(CONFIG.WS_MESSAGE_TIMEOUT)
        if self.ncp_websocket.did_error_occur():
            raise NMOSTestException(test.FAIL("Error opening websocket: {}".format(
                self.ncp_websocket.get_error_message())))
        else:
            return True, None

    def test_02(self, test):
        """WebSocket successfully opened on advertised urn:x-nmos:control:ncp endpoint"""
        success, error = self.create_ncp_socket(test)

        if not success:
            return error

        return test.PASS("WebSocket successfully opened")
