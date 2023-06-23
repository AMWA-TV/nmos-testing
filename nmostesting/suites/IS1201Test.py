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
import os
import time

from jsonschema import ValidationError, SchemaError

from ..Config import WS_MESSAGE_TIMEOUT
from ..GenericTest import GenericTest, NMOSTestException
from ..IS12Utils import IS12Utils, NcMethodStatus, MessageTypes
from ..TestHelper import WebsocketWorker, load_resolved_schema
from ..TestResult import Test

NODE_API_KEY = "node"
CONTROL_API_KEY = "ncp"
MS05_API_KEY = "controlframework"


class IS1201Test(GenericTest):

    def __init__(self, apis, **kwargs):
        # Remove the RAML key to prevent this test suite from auto-testing IS-04 API
        apis[NODE_API_KEY].pop("raml", None)
        GenericTest.__init__(self, apis, **kwargs)
        self.node_url = self.apis[NODE_API_KEY]["url"]
        self.ncp_url = self.apis[CONTROL_API_KEY]["url"]
        self.is12_utils = IS12Utils(self.node_url)
        self.ncp_websocket = None
        self.load_validation_resources()

    def set_up_tests(self):
        # Do nothing
        pass

    def tear_down_tests(self):
        # Clean up Websocket resources
        if self.ncp_websocket:
            self.ncp_websocket.close()

    def execute_tests(self, test_names):
        """Perform tests defined within this class"""
        # Override to allow 'auto' testing of MS-05 types and classes

        for test_name in test_names:
            if test_name in ["auto", "all"] and not self.disable_auto:
                # Validate all standard datatypes and classes advertised by the Class Manager
                self.result += self.auto_tests()
            self.execute_test(test_name)

    def load_validation_resources(self):
        # Load IS-12 schemas
        self.schemas = {}
        schema_names = ["command-response-message"]
        for schema_name in schema_names:
            self.schemas[schema_name] = load_resolved_schema(self.apis[CONTROL_API_KEY]["spec_path"],
                                                             schema_name + ".json")
        # Calculate paths to MS-05 descriptors and destination for generated MS-05 schemas
        spec_path = self.apis[MS05_API_KEY]["spec_path"]
        datatype_path = os.path.join(spec_path, 'models/datatypes/')
        base_datatype_path = os.path.abspath(datatype_path)
        classes_path = os.path.join(spec_path, 'models/classes/')
        base_classes_path = os.path.abspath(classes_path)

        # Load MS-05 classes descriptors
        self.classes_descriptors = {}
        for filename in os.listdir(base_classes_path):
            name, extension = os.path.splitext(filename)
            if extension == ".json":
                with open(os.path.join(base_classes_path, filename), 'r') as json_file:
                    class_json = json.load(json_file)
                    self.classes_descriptors[class_json['name']] = class_json

        # Load MS-05 datatype descriptors
        self.datatype_descriptors = {}
        for filename in os.listdir(base_datatype_path):
            name, extension = os.path.splitext(filename)
            if extension == ".json":
                with open(os.path.join(base_datatype_path, filename), 'r') as json_file:
                    self.datatype_descriptors[name] = json.load(json_file)

        # Generate MS-05 datatype schemas from MS-05 datatype descriptors
        datatype_schema_names = []
        schema_path = os.path.join(self.apis[CONTROL_API_KEY]["spec_path"], 'APIs/schemas/')
        base_schema_path = os.path.abspath(schema_path)
        if not os.path.exists(base_schema_path):
            os.makedirs(base_schema_path)

        for name, descriptor in self.datatype_descriptors.items():
            json_schema = self.is12_utils.descriptor_to_schema(descriptor)
            with open(os.path.join(base_schema_path, name + '.json'), 'w') as output_file:
                json.dump(json_schema, output_file, indent=4)
                datatype_schema_names.append(name)

        # Load resolved MS-05 datatype schemas
        self.datatype_schemas = {}
        for name in datatype_schema_names:
            self.datatype_schemas[name] = load_resolved_schema(self.apis[CONTROL_API_KEY]["spec_path"],
                                                               name + '.json')

    def auto_tests(self):
        results = list()

        # Get Class Manager
        test = Test("Get ClassManager", "auto_ClassManager")

        if not self.create_ncp_socket(test):
            results.append(test.FAIL("Failed to open WebSocket successfully"
                                     + str(self.ncp_websocket.get_error_message())))
            return results
        try:
            class_manager = self.get_class_manager(test)
            results += self.auto_classes_validation(class_manager)
            results += self.auto_datatype_validation(class_manager)

        except NMOSTestException as e:
            results.append(e.args[0])

        return results

    def auto_classes_validation(self, class_manager):
        results = list()
        command_handle = 1002

        # Get Datatypes
        property_id = self.is12_utils.PROPERTY_IDS['NCCLASSMANAGER']['CONTROL_CLASSES']
        get_datatypes_command = \
            self.is12_utils.create_generic_get_command_JSON(command_handle,
                                                            class_manager['oid'],
                                                            property_id)
        test = Test("Send command", "auto_SendCommand")
        response = self.send_command(test, get_datatypes_command, command_handle)

        # Create classes dictionary from response array
        classes = {r['name']: r for r in response["result"]["value"]}
        classes_keys = sorted(self.classes_descriptors.keys())

        for key in classes_keys:
            if classes.get(key):
                control_class = classes[key]
                test = Test("Validate " + control_class['name'] + " definition", "auto_" + control_class['name'])

                try:
                    # Validate the JSON schema is correct
                    self.validate_schema(control_class, self.datatype_schemas['NcClassDescriptor'])
                except ValidationError as e:
                    results.append(test.FAIL(e.message))
                except SchemaError as e:
                    results.append(test.FAIL(e.message))

                # Validate the descriptor is correct
                success, message = self.validate_datatype(self.classes_descriptors[control_class['name']],
                                                          control_class)
                if success:
                    results.append(test.PASS())
                else:
                    results.append(test.FAIL(message))
            else:
                results.append(test.WARNING("Not Implemented"))

        return results

    def auto_datatype_validation(self, class_manager):
        results = list()
        command_handle = 1001

        # Get Datatypes
        property_id = self.is12_utils.PROPERTY_IDS['NCCLASSMANAGER']['DATATYPES']
        get_datatypes_command = \
            self.is12_utils.create_generic_get_command_JSON(command_handle,
                                                            class_manager['oid'],
                                                            property_id)
        test = Test("Send command", "auto_SendCommand")
        response = self.send_command(test, get_datatypes_command, command_handle)

        # Create datatype dictionary from response array
        datatypes = {r['name']: r for r in response["result"]["value"]}
        datatype_keys = sorted(self.datatype_descriptors.keys())

        for key in datatype_keys:
            if datatypes.get(key):
                datatype = datatypes[key]
                test = Test("Validate " + datatype['name'] + " definition", "auto_" + datatype['name'])

                try:
                    # Validate the JSON schema is correct
                    self.validate_schema(datatype, self.datatype_schemas['NcDatatypeDescriptor'])
                except ValidationError as e:
                    results.append(test.FAIL(e.message))
                except SchemaError as e:
                    results.append(test.FAIL(e.message))

                # Validate the descriptor is correct
                success, message = self.validate_datatype(self.datatype_descriptors[datatype['name']], datatype)
                if success:
                    results.append(test.PASS())
                else:
                    results.append(test.FAIL(message))
            else:
                results.append(test.WARNING("Not Implemented"))

        return results

    def validate_datatype(self, reference, value):
        non_normative_keys = ['description']

        if isinstance(reference, dict):
            # JRT: These two manipulation are to mitigate two issues
            # to be resolved regarding the MS-05-02 JSON descriptors.
            # Firstly the constraints property is missing from certain descriptors
            # Secondly the isConstant flag is missing from
            # the NcObject descriptor properties
            reference.pop('constraints', None)
            value.pop('constraints', None)
            if value.get('isConstant') != reference.get('isConstant'):
                if not isinstance(value.get('isConstant'), dict):
                    value.pop('isConstant', None)
            # JRT: End

            reference_keys = set(reference.keys())
            value_keys = set(value.keys())

            # compare the keys to see if any extra/missing
            key_diff = (set(reference_keys) | set(value_keys)) - (set(reference_keys) & set(value_keys))
            if len(key_diff) > 0:
                return False, 'Missing/additional keys ' + str(key_diff)

            for key in reference_keys:
                if key in non_normative_keys:
                    continue
                if key in value_keys:
                    # Check for class ID
                    if key == 'identity' and isinstance(reference[key], list):
                        if len(reference[key]) != len(value[key]):
                            return False, "Unexpected ClassId. Expected: " \
                                          + str(reference[key]) \
                                          + " actual: " + str(value[key])
                        for r, v in zip(reference[key], value[key]):
                            if r != v:
                                return False, "Unexpected ClassId. Expected: " \
                                              + str(reference[key]) \
                                              + " actual: " + str(value[key])
                    else:
                        success, message = self.validate_datatype(reference[key], value[key])
                        if not success:
                            return False, message
            return True, ""

        elif isinstance(reference, list):
            # Convert to dict and validate
            references = {item['name']: item for item in reference}
            values = {item['name']: item for item in value}

            return self.validate_datatype(references, values)
        else:
            if reference == value:
                return True, ""
            else:
                return False, 'Property ' + key + ': ' + str(value[key]) + ' not equal to ' + str(reference[key])

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
        while time.time() < start_time + WS_MESSAGE_TIMEOUT:
            if self.ncp_websocket.is_open():
                break
            time.sleep(0.2)

        if self.ncp_websocket.did_error_occur():
            return False
        else:
            return self.ncp_websocket.is_open()

    def test_02(self, test):
        """WebSocket successfully opened on advertised urn:x-nmos:control:ncp endpoint"""
        # Referencing the Google sheet
        # IS-12 (2) WebSocket successfully opened on advertised urn:x-nmos:control:ncp endpoint

        if not self.create_ncp_socket(test):
            return test.FAIL("Failed to open WebSocket successfully: " + str(self.ncp_websocket.get_error_message()))

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
        while time.time() < start_time + WS_MESSAGE_TIMEOUT:
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
            return test.FAIL("Failed to open WebSocket successfully" + str(self.ncp_websocket.get_error_message()))

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

    def get_class_manager(self, test):
        command_handle = 1000
        get_member_descriptors_command = \
            self.is12_utils.create_get_member_descriptors_JSON(command_handle, self.is12_utils.ROOT_BLOCK_OID)

        response = self.send_command(test, get_member_descriptors_command, command_handle)

        class_manager_found = False
        class_manager = None

        for value in response["result"]["value"]:
            self.validate_schema(value, self.datatype_schemas["NcBlockMemberDescriptor"])

            if value["classId"] == [1, 3, 2]:
                class_manager_found = True
                class_manager = value

                if value["role"] != 'ClassManager':
                    raise NMOSTestException(test.FAIL("Incorrect Role for Class Manager: " + value["role"],
                                                      "https://specs.amwa.tv/is-12/branches/{}"
                                                      "/docs/Managers.html"
                                                      .format(self.apis[CONTROL_API_KEY]["spec_branch"])))

        if not class_manager_found:
            raise NMOSTestException(test.FAIL("Class Manager not found in Root Block",
                                              "https://specs.amwa.tv/is-12/branches/{}"
                                              "/docs/Managers.html"
                                              .format(self.apis[CONTROL_API_KEY]["spec_branch"])))

        return class_manager

    def test_04(self, test):
        """Class Manager exists in Root Block"""
        # Referencing the Google sheet
        # MS-05-02 (40) Class manager exists in root

        if not self.create_ncp_socket(test):
            return test.FAIL("Failed to open WebSocket successfully" + str(self.ncp_websocket.get_error_message()))

        try:
            self.get_class_manager(test)
        except NMOSTestException as e:
            return e.args[0]

        return test.PASS()
