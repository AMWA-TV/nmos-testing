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

from .. import Config as CONFIG
from ..GenericTest import GenericTest, NMOSTestException
from ..IS12Utils import IS12Utils, NcMethodStatus, MessageTypes
from ..TestHelper import WebsocketWorker, load_resolved_schema

NODE_API_KEY = "node"
CONTROL_API_KEY = "ncp"


class IS1201Test(GenericTest):

    def __init__(self, apis, **kwargs):
        # Remove the RAML key to prevent this test suite from auto-testing IS-04 API
        apis[NODE_API_KEY].pop("raml", None)
        GenericTest.__init__(self, apis, **kwargs)
        self.node_url = self.apis[NODE_API_KEY]["url"]
        self.ncp_url = self.apis[CONTROL_API_KEY]["url"]
        self.is12_utils = IS12Utils(self.node_url)
        self.ncp_websocket = None
        self.load_schemas()

    def load_schemas(self):
        self.schemas = {}
        schema_names = ["command-response-message"]

        for schema_name in schema_names:
            self.schemas[schema_name] = load_resolved_schema(self.apis[CONTROL_API_KEY]["spec_path"],
                                                             schema_name + ".json")

    def set_up_tests(self):
        # Do nothing
        pass

    def tear_down_tests(self):
        # Clean up Websocket resources
        if self.ncp_websocket:
            self.ncp_websocket.close()

    def test_01(self, test):
        """At least one Device is showing an IS-12 control advertisement matching the API under test"""
        # Referencing the Google sheet
        # IS-12 (1) Control endpoint advertised in Node endpoint's Device controls array

        control_type = "urn:x-nmos:control:ncp/" + self.apis[CONTROL_API_KEY]["version"].rstrip("-dev")
        return self.is12_utils.do_test_device_control(
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
        # Referencing the Google sheet
        # IS-12 (2) WebSocket successfully opened on advertised urn:x-nmos:control:ncp endpoint

        if not self.create_ncp_socket(test):
            return test.FAIL("Failed to open WebSocket successfully")

        return test.PASS()

    def send_command(self, test, command_json, command_handle):
        # Referencing the Google sheet
        # IS-12 (9)  Check protocol version and message type
        # IS-12 (10) Check handle numeric identifier
        # https://specs.amwa.tv/is-12/branches/v1.0-dev/docs/Protocol_messaging.html
        # IS-12 (11) Check Command message type
        # https://specs.amwa.tv/is-12/branches/v1.0-dev/docs/Protocol_messaging.html#command-message-type

        results = []

        self.ncp_websocket.send(json.dumps(command_json))

        # Wait for server to respond
        start_time = time.time()
        while time.time() < start_time + CONFIG.WS_MESSAGE_TIMEOUT:
            if self.ncp_websocket.is_messages_received():
                break
            time.sleep(0.2)

        messages = self.ncp_websocket.get_messages()

        # find the response to our request
        for message in messages:
            parsed_message = json.loads(message)

            if parsed_message["messageType"] == MessageTypes.CommandResponse:
                self.validate_schema(parsed_message, self.schemas["command-response-message"])

                if parsed_message["protocolVersion"] != self.is12_utils.DEFAULT_PROTOCOL_VERSION:
                    raise NMOSTestException(test.FAIL("Incorrect protocol version. Expected "
                                                      + self.is12_utils.DEFAULT_PROTOCOL_VERSION
                                                      + ", received " + parsed_message["protocolVersion"],
                                                      "https://specs.amwa.tv/is-12/branches/{}"
                                                      "/docs/Protocol_messaging.html"
                                                      .format(self.apis[CONTROL_API_KEY]["spec_branch"])))

                responses = parsed_message["responses"]

                for response in responses:
                    # here it is!
                    if response["handle"] == command_handle:
                        if response["result"]["status"] != NcMethodStatus.OK:
                            raise NMOSTestException(test.FAIL("Message status not OK: "
                                                    + NcMethodStatus(response["result"]["status"]).name))
                        results.append(response)

        if len(results) == 0:
            raise NMOSTestException(test.FAIL("No Command Message Response received. ",
                                              "https://specs.amwa.tv/is-12/branches/{}"
                                              "/docs/Protocol_messaging.html#command-message-type"
                                              .format(self.apis[CONTROL_API_KEY]["spec_branch"])))

        if len(results) > 1:
            raise NMOSTestException(test.FAIL("Received multiple responses : " + len(responses)))

        return results[0]

    def test_03(self, test):
        """Root Block Exists with correct OID and Role"""
        # Referencing the Google sheet
        # MS-05-02 (44)	Root block must exist
        # MS-05-02 (45) Verify oID and role of root block
        # https://github.com/AMWA-TV/ms-05-02/blob/v1.0-dev/docs/Blocks.md#blocks

        if not self.create_ncp_socket(test):
            return test.FAIL("Failed to open WebSocket successfully")

        command_handle = 1001
        get_role_command = \
            self.is12_utils.create_generic_get_command_JSON(command_handle,
                                                            self.is12_utils.ROOT_BLOCK_OID,
                                                            self.is12_utils.PROPERTY_IDS['NCOBJECT']['ROLE'])

        response = self.send_command(test, get_role_command, command_handle)

        if response["result"]["value"] != "root":
            return test.FAIL("Unexpected role in root block: " + response["result"]["value"],
                             "https://specs.amwa.tv/is-12/branches/{}"
                             "/docs/Blocks.html"
                             .format(self.apis[CONTROL_API_KEY]["spec_branch"]))

        return test.PASS()

    def test_04(self, test):
        """Class Manager exists in Root Block"""
        # Referencing the Google sheet
        # MS-05-02 (40) Class manager exists in root

        if not self.create_ncp_socket(test):
            return test.FAIL("Failed to open WebSocket successfully")

        command_handle = 1000
        get_member_descriptors_command = \
            self.is12_utils.create_get_member_descriptors_JSON(command_handle, self.is12_utils.ROOT_BLOCK_OID)

        response = self.send_command(test, get_member_descriptors_command, command_handle)

        class_manager_found = False

        for value in response["result"]["value"]:
            if value["classId"] == [1, 3, 2]:
                class_manager_found = True

                if value["role"] != 'ClassManager':
                    return test.FAIL("Incorrect Role for Class Manager: " + value["role"],
                                     "https://specs.amwa.tv/is-12/branches/{}"
                                     "/docs/Managers.html"
                                     .format(self.apis[CONTROL_API_KEY]["spec_branch"]))

        if not class_manager_found:
            return test.FAIL("Class Manager not found in Root Block",
                             "https://specs.amwa.tv/is-12/branches/{}"
                             "/docs/Managers.html"
                             .format(self.apis[CONTROL_API_KEY]["spec_branch"]))

        return test.PASS()
