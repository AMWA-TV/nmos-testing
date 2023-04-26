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

from .. import Config as CONFIG
from ..GenericTest import GenericTest
from ..IS04Utils import IS04Utils
from ..TestHelper import WebsocketWorker

NODE_API_KEY = "node"
CONTROL_API_KEY = "control"


class IS1201Test(GenericTest):

    def __init__(self, apis, **kwargs):
        # Remove the RAML key to prevent this test suite from auto-testing IS-04 API
        apis[NODE_API_KEY].pop("raml", None)
        GenericTest.__init__(self, apis, **kwargs)
        self.node_url = apis[NODE_API_KEY]["url"]
        self.node_api_version = apis[NODE_API_KEY]["version"]
        self.is04_utils = IS04Utils(self.node_url)
        self.ncp_endpoint = None

    def set_up_tests(self):
        # Do nothing
        pass

    def tear_down_tests(self):
        # Clean up Websocket resources
        if self.ncp_endpoint:
            self.ncp_endpoint.close()

    def get_ncp_endpoint(self, test):
        # Discover the NMOS Control Protocol endpoint from the Node API
        valid, response = self.do_request("GET", self.node_url + "devices")
        if not valid or response.status_code == 200:
            try:
                node_devices = response.json()
                for device in node_devices:
                    for control in device["controls"]:
                        href = control["href"]
                        if self.is04_utils.compare_api_version(self.node_api_version, "v1.3") >= 0 and \
                                control["type"].startswith("urn:x-nmos:control:ncp"):
                            return True, href

            except json.JSONDecodeError:
                return False, test.FAIL("Non-JSON response returned from Node API")
            except KeyError as e:
                return False, test.FAIL("Unable to find expected key: {}".format(e))
            except AttributeError:
                return False, test.DISABLED("Incorrect websocket library version")

    def test_01(self, test):
        """Control endpoint advertised in Node endpoint's Device controls array"""
        success, result = self.get_ncp_endpoint(test)

        if not success:
            return result

        return test.PASS("NMOS Control Endpoint discovered succesfully")

    def create_ncp_socket(self, test):
        # Reuse socket if connection already established
        if self.ncp_endpoint:
            return True, None

        success, result = self.get_ncp_endpoint(test)

        if not success:
            return False, result

        # Create a WebSocket connection to NMOS Control Protocol endpoint
        self.ncp_endpoint = WebsocketWorker(result)
        self.ncp_endpoint.start()
        sleep(CONFIG.WS_MESSAGE_TIMEOUT)
        if self.ncp_endpoint.did_error_occur():
            return False, test.FAIL("Error opening websocket: {}".format(self.ncp_endpoint.get_error_message()))
        else:
            return True, None

    def test_02(self, test):
        """WebSocket successfully opened on advertised urn:x-nmos:control:ncp endpoint"""
        success, error = self.create_ncp_socket(test)

        if not success:
            return error

        return test.PASS("WebSocket successfully opened")
