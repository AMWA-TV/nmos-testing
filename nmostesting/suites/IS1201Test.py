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
from ..GenericTest import GenericTest
from ..IS12Utils import IS12Utils, NcMethodStatus, MessageTypes
from ..NMOSUtils import NMOSUtils
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
        self.command_handle = 0

    def set_up_tests(self):
        self.unique_roles_error = False
        self.unique_oids_error = False
        self.managers_are_singletons_error = False
        self.managers_members_root_block_error = False
        self.organization_id_detected = False
        self.organization_id_error = False
        self.organization_id_error_msg = ""
        self.device_model_validated = False
        self.oid_cache = []

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
        """Load datatype and control class decriptors and create datatype JSON schemas"""
        # Load IS-12 schemas
        self.schemas = {}
        schema_names = ['error-message', 'command-response-message']
        for schema_name in schema_names:
            self.schemas[schema_name] = load_resolved_schema(self.apis[CONTROL_API_KEY]["spec_path"],
                                                             schema_name + ".json")
        # Calculate paths to MS-05 descriptors and destination for generated MS-05 schemas
        spec_path = self.apis[MS05_API_KEY]["spec_path"]
        datatype_path = os.path.join(spec_path, 'models/datatypes/')
        base_datatype_path = os.path.abspath(datatype_path)
        classes_path = os.path.join(spec_path, 'models/classes/')
        base_classes_path = os.path.abspath(classes_path)

        # Load MS-05 class descriptors
        self.classes_descriptors = {}
        self.class_id_to_name = {}
        for filename in os.listdir(base_classes_path):
            name, extension = os.path.splitext(filename)
            if extension == ".json":
                with open(os.path.join(base_classes_path, filename), 'r') as json_file:
                    class_json = json.load(json_file)
                    self.classes_descriptors[class_json['name']] = class_json
                    self.class_id_to_name[name] = class_json['name']

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

    def create_ncp_socket(self):
        """Create a WebSocket client connection to Node under test. Returns [success, error message]"""
        # Reuse socket if connection already established
        if self.ncp_websocket and self.ncp_websocket.is_open():
            return True, None

        # Create a WebSocket connection to NMOS Control Protocol endpoint
        self.ncp_websocket = WebsocketWorker(self.apis[CONTROL_API_KEY]["url"])
        self.ncp_websocket.start()

        # Give WebSocket client a chance to start and open its connection
        start_time = time.time()
        while time.time() < start_time + WS_MESSAGE_TIMEOUT:
            if self.ncp_websocket.is_open():
                break
            time.sleep(0.2)

        if self.ncp_websocket.did_error_occur() or not self.ncp_websocket.is_open():
            return False, "Failed to open WebSocket successfully" \
                          + (": " + str(self.ncp_websocket.get_error_message())
                             if self.ncp_websocket.did_error_occur() else ".")
        else:
            return True, None

    def get_command_handle(self):
        """Get unique command handle"""
        self.command_handle += 1
        return self.command_handle

    def send_command(self, command_handle, command_json):
        """Send command to Node under test. Returns [command response, error message, spec link]"""
        # Referencing the Google sheet
        # IS-12 (9)  Check protocol version and message type
        # IS-12 (10) Check handle numeric identifier
        # https://specs.amwa.tv/is-12/branches/v1.0-dev/docs/Protocol_messaging.html
        # IS-12 (11) Check Command message type
        # https://specs.amwa.tv/is-12/branches/v1.0-dev/docs/Protocol_messaging.html#command-message-type
        # MS-05-02 (74) All methods MUST return a datatype which inherits from NcMethodResult.
        #               When a method call encounters an error the return MUST be NcMethodResultError
        #               or a derived datatype.
        # https://specs.amwa.tv/ms-05-02/branches/v1.0-dev/docs/Framework.md#ncmethodresult

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
                if NMOSUtils.compare_api_version(parsed_message["protocolVersion"],
                                                 self.apis[CONTROL_API_KEY]["version"]):
                    return False, "Incorrect protocol version. Expected " \
                                  + self.apis[CONTROL_API_KEY]["version"] \
                                  + ", received " + parsed_message["protocolVersion"], \
                                  "https://specs.amwa.tv/is-12/branches/{}" \
                                  "/docs/Protocol_messaging.html" \
                                  .format(self.apis[CONTROL_API_KEY]["spec_branch"])

                responses = parsed_message["responses"]
                for response in responses:
                    if response["handle"] == command_handle:
                        if response["result"]["status"] != NcMethodStatus.OK:
                            return False, response["result"], None
                        results.append(response)
            if parsed_message["messageType"] == MessageTypes.Error:
                self.validate_schema(parsed_message, self.schemas["error-message"])
                return False, parsed_message, "https://specs.amwa.tv/is-12/branches/{}" \
                                              "/docs/Protocol_messaging.html#error-messages" \
                                              .format(self.apis[CONTROL_API_KEY]["spec_branch"])
        if len(results) == 0:
            return False, "No Command Message Response received.", \
                          "https://specs.amwa.tv/is-12/branches/{}" \
                          "/docs/Protocol_messaging.html#command-message-type" \
                          .format(self.apis[CONTROL_API_KEY]["spec_branch"])

        if len(results) > 1:
            return False, "Received multiple responses : " + len(responses), None

        return results[0], None, None

    def get_class_manager(self):
        """Get ClassManager from Root Block. Returns [ClassManager, error message, spec link]"""
        command_handle = self.get_command_handle()
        version = self.is12_utils.format_version(self.apis[CONTROL_API_KEY]["version"])
        get_member_descriptors_command = \
            self.is12_utils.create_get_member_descriptors_JSON(version, command_handle, self.is12_utils.ROOT_BLOCK_OID)

        response, errorMsg, link = self.send_command(command_handle, get_member_descriptors_command)

        if not response:
            return False, errorMsg, link

        class_manager_found = False
        class_manager = None

        for value in response["result"]["value"]:
            self.validate_schema(value, self.datatype_schemas["NcBlockMemberDescriptor"])

            if value["classId"] == [1, 3, 2]:
                class_manager_found = True
                class_manager = value

                if value["role"] != 'ClassManager':
                    return False, "Incorrect Role for Class Manager: " + value["role"], \
                                  "https://specs.amwa.tv/ms-05-02/branches/{}" \
                                  "/docs/Managers.html" \
                                  .format(self.apis[CONTROL_API_KEY]["spec_branch"])

        if not class_manager_found:
            return False, "Class Manager not found in Root Block", \
                          "https://specs.amwa.tv/ms-05-02/branches/{}" \
                          "/docs/Managers.html" \
                          .format(self.apis[CONTROL_API_KEY]["spec_branch"])

        return class_manager, None, None

    def get_manager(self, type):
        """Get Manager from Root Block. Returns [Manager, error message, spec link]"""
        command_handle = self.get_command_handle()
        version = self.is12_utils.format_version(self.apis[CONTROL_API_KEY]["version"])
        get_member_descriptors_command = \
            self.is12_utils.create_get_member_descriptors_JSON(version, command_handle, self.is12_utils.ROOT_BLOCK_OID)

        response, errorMsg, link = self.send_command(command_handle, get_member_descriptors_command)

        if not response:
            return False, errorMsg, link

        manager_found = False
        manager = None

        class_descriptor = self.classes_descriptors[type]

        for value in response["result"]["value"]:
            self.validate_schema(value, self.datatype_schemas["NcBlockMemberDescriptor"])

            if value["classId"] == class_descriptor["identity"]:
                manager_found = True
                manager = value

                if value["role"] != class_descriptor["fixedRole"]:
                    return False, "Incorrect Role for Class Manager: " + value["role"], \
                                  "https://specs.amwa.tv/ms-05-02/branches/{}" \
                                  "/docs/Managers.html" \
                                  .format(self.apis[CONTROL_API_KEY]["spec_branch"])

        if not manager_found:
            return False, str(type) + " Manager not found in Root Block", \
                          "https://specs.amwa.tv/ms-05-02/branches/{}" \
                          "/docs/Managers.html" \
                          .format(self.apis[CONTROL_API_KEY]["spec_branch"])

        return manager, None, None

    def validate_descriptor(self, reference, descriptor):
        """Compare descriptor to reference descriptor. Returns [success, error message]"""
        non_normative_keys = ['description']

        if isinstance(reference, dict):
            # JRT: These two manipulation are to mitigate two issues
            # to be resolved regarding the MS-05-02 JSON descriptors.
            # Firstly the constraints property is missing from certain descriptors
            # Secondly the isConstant flag is missing from
            # the NcObject descriptor properties
            reference.pop('constraints', None)
            descriptor.pop('constraints', None)
            reference.pop('isConstant', None)
            descriptor.pop('isConstant', None)
            # JRT: End

            reference_keys = set(reference.keys())
            descriptor_keys = set(descriptor.keys())

            # compare the keys to see if any extra/missing
            key_diff = (set(reference_keys) | set(descriptor_keys)) - (set(reference_keys) & set(descriptor_keys))
            if len(key_diff) > 0:
                return False, 'Missing/additional keys ' + str(key_diff)

            for key in reference_keys:
                if key in non_normative_keys:
                    continue
                # Check for class ID
                if key == 'identity' and isinstance(reference[key], list):
                    if reference[key] != descriptor[key]:
                        return False, "Unexpected ClassId. Expected: " \
                                      + str(reference[key]) \
                                      + " actual: " + str(descriptor[key])
                else:
                    success, message = self.validate_descriptor(reference[key], descriptor[key])
                    if not success:
                        return False, key + "->" + message
            return True, None

        elif isinstance(reference, list):
            # Convert to dict and validate
            references = {item['name']: item for item in reference}
            descriptors = {item['name']: item for item in descriptor}

            return self.validate_descriptor(references, descriptors)
        else:
            if reference == descriptor:
                return True, None
            else:
                return False, 'Expected value: ' + str(reference) + ', actual value: ' + str(descriptor)

    def _validate_schema(self, payload, schema):
        """ Delegates to validate_schema but handles any exceptions: Returns [success, error message] """
        try:
            # Validate the JSON schema is correct
            self.validate_schema(payload, schema)
        except ValidationError as e:
            return False, e.message
        except SchemaError as e:
            return False, e.message

        return True, None

    def validate_model_definitions(self, class_manager_oid, property_id, schema_name, reference_descriptors):
        """Validate class manager model definitions against MS-05-02 model descriptors. Returns [test result array]"""
        results = list()
        command_handle = self.get_command_handle()
        version = self.is12_utils.format_version(self.apis[CONTROL_API_KEY]["version"])

        get_descriptors_command = \
            self.is12_utils.create_generic_get_command_JSON(version,
                                                            command_handle,
                                                            class_manager_oid,
                                                            property_id)
        test = Test("Send command", "auto_SendCommand")
        response, errorMsg, link = self.send_command(command_handle, get_descriptors_command)

        if not response:
            results.append(test.FAIL(errorMsg, link))
            return results

        # Create descriptor dictionary from response array
        descriptors = {r['name']: r for r in response["result"]["value"]}
        reference_descriptor_keys = sorted(reference_descriptors.keys())

        for key in reference_descriptor_keys:
            test = Test("Validate " + str(key) + " definition", "auto_" + str(key))

            if descriptors.get(key):
                descriptor = descriptors[key]

                # Validate the JSON schema is correct
                success, errorMsg = self._validate_schema(descriptor, self.datatype_schemas[schema_name])
                if not success:
                    results.append(test.FAIL(errorMsg))
                    continue

                # Validate the descriptor is correct
                success, errorMsg = self.validate_descriptor(reference_descriptors[descriptor['name']], descriptor)
                if not success:
                    results.append(test.FAIL(errorMsg))
                    continue

                results.append(test.PASS())
            else:
                results.append(test.WARNING("Not Implemented"))

        return results

    def auto_tests(self):
        """Automatically validate all standard datatypes and control classes. Returns [test result array]"""
        # Referencing the Google sheet
        # MS-05-02 (75)  Model definitions
        results = list()
        test = Test("Get ClassManager", "auto_ClassManager")

        success, errorMsg = self.create_ncp_socket()
        if not success:
            results.append(test.FAIL(errorMsg))
            return results

        class_manager, errorMsg, link = self.get_manager("NcClassManager")

        if not class_manager:
            results.append(test.FAIL(errorMsg, link))
            return results

        results += self.validate_model_definitions(class_manager['oid'],
                                                   self.is12_utils.PROPERTY_IDS['NCCLASSMANAGER']['CONTROL_CLASSES'],
                                                   'NcClassDescriptor',
                                                   self.classes_descriptors)

        results += self.validate_model_definitions(class_manager['oid'],
                                                   self.is12_utils.PROPERTY_IDS['NCCLASSMANAGER']['DATATYPES'],
                                                   'NcDatatypeDescriptor',
                                                   self.datatype_descriptors)
        return results

    def test_01(self, test):
        """At least one Device is showing an IS-12 control advertisement matching the API under test"""
        # Referencing the Google sheet
        # IS-12 (1) Control endpoint advertised in Node endpoint's Device controls array

        control_type = "urn:x-nmos:control:ncp/" + self.apis[CONTROL_API_KEY]["version"]
        return self.is12_utils.do_test_device_control(
            test,
            self.node_url,
            control_type,
            self.ncp_url,
            self.authorization
        )

    def test_02(self, test):
        """WebSocket successfully opened on advertised urn:x-nmos:control:ncp endpoint"""
        # Referencing the Google sheet
        # IS-12 (2) WebSocket successfully opened on advertised urn:x-nmos:control:ncp endpoint

        success, errorMsg = self.create_ncp_socket()
        if not success:
            return test.FAIL(errorMsg)

        return test.PASS()

    def test_03(self, test):
        """Root Block Exists with correct oid and Role"""
        # Referencing the Google sheet
        # MS-05-02 (44)	Root Block must exist
        # MS-05-02 (45) Verify oID and role of Root Block
        # https://github.com/AMWA-TV/ms-05-02/blob/v1.0-dev/docs/Blocks.md#Blocks

        try:
            success, errorMsg = self.create_ncp_socket()
            if not success:
                return test.FAIL(errorMsg)

            command_handle = self.get_command_handle()
            version = self.is12_utils.format_version(self.apis[CONTROL_API_KEY]["version"])
            get_role_command = \
                self.is12_utils.create_generic_get_command_JSON(version,
                                                                command_handle,
                                                                self.is12_utils.ROOT_BLOCK_OID,
                                                                self.is12_utils.PROPERTY_IDS['NCOBJECT']['ROLE'])

            response, errorMsg, link = self.send_command(command_handle, get_role_command)
            if not response:
                return test.FAIL(errorMsg, link)

            if response["result"]["value"] != "root":
                return test.FAIL("Unexpected role in Root Block: " + response["result"]["value"],
                                 "https://specs.amwa.tv/ms-05-02/branches/{}"
                                 "/docs/Blocks.html"
                                 .format(self.apis[CONTROL_API_KEY]["spec_branch"]))

            return test.PASS()
        except ValidationError as e:
            return test.FAIL("JSON schema validation error: " + e.message)
        except SchemaError as e:
            return test.FAIL("JSON schema error: " + e.message)

    def test_04(self, test):
        """Class Manager exists in Root Block"""
        # Referencing the Google sheet
        # MS-05-02 (40) Class manager exists in root

        success, errorMsg = self.create_ncp_socket()
        if not success:
            return test.FAIL(errorMsg)

        class_manager, errorMsg, link = self.get_manager("NcClassManager")

        if not class_manager:
            return test.FAIL(errorMsg, link)

        return test.PASS()

    def do_error_test(self, test, command_handle, command_json, expected_status=None, is12_error=True):
        """Execute command with expected error status."""
        # when expected_status = None checking of the status code is skipped
        # check the syntax of the error message according to is12_error

        try:
            success, errorMsg = self.create_ncp_socket()
            if not success:
                return test.FAIL(errorMsg)

            response, errorMsg, link = self.send_command(command_handle, command_json)

            if response:
                return test.FAIL("Protocol error not handled")

            # 'protocolVersion' key is found in IS-12 protocol errors, but not in MS-05-02 errors
            if is12_error != ('protocolVersion' in errorMsg):
                spec = "IS-12 protocol" if is12_error else "MS-05-02"
                return test.FAIL(spec + " error expected", link)

            if not errorMsg.get('status'):
                return test.FAIL("Command error: " + str(errorMsg))

            if errorMsg['status'] == NcMethodStatus.OK:
                return test.FAIL("Error not handled. Expected: " + expected_status.name
                                 + " (" + str(expected_status) + ")"
                                 + ", actual: " + NcMethodStatus(errorMsg['status']).name
                                 + " (" + str(errorMsg['status']) + ")", link)

            if expected_status and errorMsg['status'] != expected_status:
                return test.WARNING("Unexpected status. Expected: " + expected_status.name
                                    + " (" + str(expected_status) + ")"
                                    + ", actual: " + NcMethodStatus(errorMsg['status']).name
                                    + " (" + str(errorMsg['status']) + ")", link)

            return test.PASS()
        except ValidationError as e:
            return test.FAIL("JSON schema validation error: " + e.message)
        except SchemaError as e:
            return test.FAIL("JSON schema error: " + e.message)

    def test_05(self, test):
        """IS-12 Protocol Error: Node handles incorrect IS-12 protocol version"""

        command_handle = self.get_command_handle()
        # Use incorrect protocol version
        version = 'DOES.NOT.EXIST'
        command_json = \
            self.is12_utils.create_generic_get_command_JSON(version,
                                                            command_handle,
                                                            self.is12_utils.ROOT_BLOCK_OID,
                                                            self.is12_utils.PROPERTY_IDS['NCOBJECT']['OID'])

        return self.do_error_test(test,
                                  command_handle,
                                  command_json,
                                  expected_status=NcMethodStatus.ProtocolVersionError)

    def test_06(self, test):
        """IS-12 Protocol Error: Node handles invalid command handle"""

        # Use invalid handle
        invalid_command_handle = "NOT A HANDLE"
        version = self.is12_utils.format_version(self.apis[CONTROL_API_KEY]["version"])
        command_json = \
            self.is12_utils.create_generic_get_command_JSON(version,
                                                            invalid_command_handle,
                                                            self.is12_utils.ROOT_BLOCK_OID,
                                                            self.is12_utils.PROPERTY_IDS['NCOBJECT']['OID'])

        return self.do_error_test(test,
                                  invalid_command_handle,
                                  command_json)

    def test_07(self, test):
        """IS-12 Protocol Error: Node handles invalid command type"""
        command_handle = self.get_command_handle()
        version = self.is12_utils.format_version(self.apis[CONTROL_API_KEY]["version"])
        command_json = \
            self.is12_utils.create_generic_get_command_JSON(version,
                                                            command_handle,
                                                            self.is12_utils.ROOT_BLOCK_OID,
                                                            self.is12_utils.PROPERTY_IDS['NCOBJECT']['OID'])
        # Use invalid message type
        command_json['messageType'] = 7

        return self.do_error_test(test,
                                  command_handle,
                                  command_json)

    def test_08(self, test):
        """IS-12 Protocol Error: Node handles invalid JSON"""
        command_handle = self.get_command_handle()
        # Use invalid JSON
        command_json = {'not_a': 'valid_command'}

        return self.do_error_test(test,
                                  command_handle,
                                  command_json)

    def test_09(self, test):
        """MS-05-02 Error: Node handles invalid oid"""

        command_handle = self.get_command_handle()
        version = self.is12_utils.format_version(self.apis[CONTROL_API_KEY]["version"])
        # Use invalid oid
        invalid_oid = 999999999
        command_json = \
            self.is12_utils.create_generic_get_command_JSON(version,
                                                            command_handle,
                                                            invalid_oid,
                                                            self.is12_utils.PROPERTY_IDS['NCOBJECT']['OID'])

        return self.do_error_test(test,
                                  command_handle,
                                  command_json,
                                  expected_status=NcMethodStatus.BadOid,
                                  is12_error=False)

    def test_10(self, test):
        """MS-05-02 Error: Node handles invalid property identifier"""
        command_handle = self.get_command_handle()
        version = self.is12_utils.format_version(self.apis[CONTROL_API_KEY]["version"])
        # Use invalid property id
        invalid_property_identifier = {'level': 1, 'index': 999}
        command_json = \
            self.is12_utils.create_generic_get_command_JSON(version,
                                                            command_handle,
                                                            self.is12_utils.ROOT_BLOCK_OID,
                                                            invalid_property_identifier)

        return self.do_error_test(test,
                                  command_handle,
                                  command_json,
                                  expected_status=NcMethodStatus.PropertyNotImplemented,
                                  is12_error=False)

    def test_11(self, test):
        """MS-05-02 Error: Node handles invalid method identifier"""
        command_handle = self.get_command_handle()
        version = self.is12_utils.format_version(self.apis[CONTROL_API_KEY]["version"])
        command_json = \
            self.is12_utils.create_generic_get_command_JSON(version,
                                                            command_handle,
                                                            self.is12_utils.ROOT_BLOCK_OID,
                                                            self.is12_utils.PROPERTY_IDS['NCOBJECT']['OID'])
        # Use invalid method id
        invalid_method_id = {'level': 1, 'index': 999}
        command_json['commands'][0]['methodId'] = invalid_method_id

        return self.do_error_test(test,
                                  command_handle,
                                  command_json,
                                  expected_status=NcMethodStatus.MethodNotImplemented,
                                  is12_error=False)

    def test_12(self, test):
        """MS-05-02 Error: Node handles read only error"""
        command_handle = self.get_command_handle()
        version = self.is12_utils.format_version(self.apis[CONTROL_API_KEY]["version"])
        # Try to set a read only property
        command_json = \
            self.is12_utils.create_generic_set_command_JSON(version,
                                                            command_handle,
                                                            self.is12_utils.ROOT_BLOCK_OID,
                                                            self.is12_utils.PROPERTY_IDS['NCOBJECT']['ROLE'],
                                                            "ROLE IS READ ONLY")

        return self.do_error_test(test,
                                  command_handle,
                                  command_json,
                                  expected_status=NcMethodStatus.Readonly,
                                  is12_error=False)

    def validate_property_type(self, value, type, is_nullable):
        if is_nullable and value is None:
            return True, None

        if self.is12_utils.primitive_to_python_type(type):
            if not isinstance(value, self.is12_utils.primitive_to_python_type(type)):
                return False, str(value) + " not of type " + str(type)
        else:
            valid, errorMsg = self._validate_schema(value, self.datatype_schemas[type])
            if not valid:
                return False, errorMsg

        return True, None

    def validate_object_properties(self, class_name, oid):
        version = self.is12_utils.format_version(self.apis[CONTROL_API_KEY]["version"])
        reference_class_descriptor = self.classes_descriptors[class_name]

        for class_property in reference_class_descriptor['properties']:
            command_handle = self.get_command_handle()
            get_property_command = \
                self.is12_utils.create_generic_get_command_JSON(version,
                                                                command_handle,
                                                                oid,
                                                                class_property['id'])
            # get property
            response, errorMsg, link = self.send_command(command_handle, get_property_command)
            if not response:
                return False, errorMsg, link

            # validate property type
            if class_property['isSequence']:
                for property_value in response["result"]["value"]:
                    success, errorMsg = self.validate_property_type(property_value,
                                                                    class_property['typeName'],
                                                                    class_property['isNullable'])
                    if not success:
                        return False, errorMsg, None
            else:
                success, errorMsg = self.validate_property_type(response["result"]["value"],
                                                                class_property['typeName'],
                                                                class_property['isNullable'])
                if not success:
                    return False, errorMsg, None

        return True, None, None

    def validate_block(self, block_id):
        command_handle = self.get_command_handle()
        version = self.is12_utils.format_version(self.apis[CONTROL_API_KEY]["version"])

        get_member_descriptors_command = \
            self.is12_utils.create_get_member_descriptors_JSON(version, command_handle, block_id)

        response, errorMsg, link = self.send_command(command_handle, get_member_descriptors_command)
        if not response:
            return False, errorMsg, None

        role_cache = []
        manager_cache = []

        for child_object in response["result"]["value"]:
            valid, errorMsg = self._validate_schema(child_object, self.datatype_schemas["NcBlockMemberDescriptor"])
            if not valid:
                return False, errorMsg, None

            # Check role is unique within containing Block
            if child_object['role'] in role_cache:
                self.unique_roles_error = True
            else:
                role_cache.append(child_object['role'])

            # Check oid is globally unique
            if child_object['oid'] in self.oid_cache:
                self.unique_oids_error = True
            else:
                self.oid_cache.append(child_object['oid'])

            # check for non-standard classes
            if self.is12_utils.is_non_standard_class(child_object['classId']):
                self.organization_id_detected = True

            # detemine the standard base class name
            base_id = self.is12_utils.get_base_class_id(child_object['classId'])
            class_name = self.class_id_to_name.get(base_id, None)

            # manager checks
            if self.is12_utils.is_manager(child_object['classId']):
                if child_object["owner"] != self.is12_utils.ROOT_BLOCK_OID:
                    self.managers_members_root_block_error = True
                if class_name in manager_cache:
                    self.managers_are_singletons_error = True
                else:
                    manager_cache.append(class_name)

            if class_name:
                success, errorMsg, link = self.validate_object_properties(class_name, child_object['oid'])
                if not success:
                    return False, errorMsg, None
            else:
                # Not a standard or non-standard class
                self.organization_id_error = True
                self.organization_id_error_msg = "Non-standard class id does not contain authority key: " \
                                                 + str(child_object['classId']) + ". "

            # If this child object is a Block, recurse
            if self.is12_utils.is_block(child_object['classId']):
                success, errorMsg, link = self.validate_block(child_object['oid'])

                if not success:
                    return False, errorMsg, link

        return True, None, None

    def validate_device_model(self):
        if not self.device_model_validated:
            success, errorMsg = self.create_ncp_socket()
            if not success:
                return False, errorMsg, None

            success, errorMsg, link = self.validate_block(self.is12_utils.ROOT_BLOCK_OID)
            if not success:
                return False, errorMsg, link

            self.device_model_validated = True

        return True, None, None

    def test_13(self, test):
        """Validate device model property types"""
        # Referencing the Google sheet
        # MS-05-02 (34) All workers MUST inherit from NcWorker
        # MS-05-02 (35) All managers MUST inherit from NcManager

        success, errorMsg, link = self.validate_device_model()
        if not success:
            return test.FAIL(errorMsg, link)

        return test.PASS()

    def test_14(self, test):
        """Device model roles are unique within a containing Block"""
        # Referencing the Google sheet
        # MS-05-02 (59) The role of an object MUST be unique within its containing Block.
        # https://specs.amwa.tv/ms-05-02/branches/v1.0-dev/docs/NcObject.html

        success, errorMsg, link = self.validate_device_model()
        if not success:
            return test.UNCLEAR(errorMsg, link)

        if self.unique_roles_error:
            return test.FAIL("Roles must be unique. ",
                             "https://specs.amwa.tv/ms-05-02/branches/{}"
                             "/docs/NcObject.html"
                             .format(self.apis[MS05_API_KEY]["spec_branch"]))

        return test.PASS()

    def test_15(self, test):
        """Device model oids are globally unique"""
        # Referencing the Google sheet
        # MS-05-02 (60) Object ids (oid property) MUST uniquely identity objects in the device model.
        # https://specs.amwa.tv/ms-05-02/branches/v1.0-dev/docs/NcObject.html

        success, errorMsg, link = self.validate_device_model()
        if not success:
            return test.UNCLEAR(errorMsg, link)

        if self.unique_oids_error:
            return test.FAIL("Oids must be unique. ",
                             "https://specs.amwa.tv/ms-05-02/branches/{}"
                             "/docs/NcObject.html"
                             .format(self.apis[MS05_API_KEY]["spec_branch"]))

        return test.PASS()

    def test_16(self, test):
        """Managers must be members of the Root Block"""
        # Referencing the Google sheet
        # MS-05-02 (36) All managers MUST always exist as members in the Root Block and have a fixed role.
        # https://specs.amwa.tv/ms-05-02/branches/v1.0-dev/docs/Managers.html

        success, errorMsg, link = self.validate_device_model()
        if not success:
            return test.UNCLEAR(errorMsg, link)

        if self.managers_members_root_block_error:
            return test.FAIL("Managers must be members of Root Block. ",
                             "https://specs.amwa.tv/ms-05-02/branches/{}"
                             "/docs/Managers.html"
                             .format(self.apis[MS05_API_KEY]["spec_branch"]))

        return test.PASS()

    def test_17(self, test):
        """Managers are singletons"""
        # Referencing the Google sheet
        # MS-05-02 (63) Managers are singleton (MUST only be instantiated once) classes.
        # https://specs.amwa.tv/ms-05-02/branches/v1.0-dev/docs/Managers.html

        success, errorMsg, link = self.validate_device_model()
        if not success:
            return test.UNCLEAR(errorMsg, link)

        if self.managers_members_root_block_error:
            return test.FAIL("Managers must be singleton classes. ",
                             "https://specs.amwa.tv/ms-05-02/branches/{}"
                             "/docs/Managers.html"
                             .format(self.apis[MS05_API_KEY]["spec_branch"]))

        return test.PASS()

    def test_18(self, test):
        """Device Manager exists in Root Block"""
        # Referencing the Google sheet
        # MS-05-02 (37) A minimal device implementation MUST have a device manager in the Root Block.

        success, errorMsg = self.create_ncp_socket()
        if not success:
            return test.FAIL(errorMsg)

        device_manager, errorMsg, link = self.get_manager("NcDeviceManager")

        if not device_manager:
            return test.FAIL(errorMsg, link)

        # Check MS-05-02 Version
        command_handle = self.get_command_handle()
        version = self.is12_utils.format_version(self.apis[CONTROL_API_KEY]["version"])
        property_id = self.is12_utils.PROPERTY_IDS['NCDEVICEMANAGER']['NCVERSION']

        get_descriptors_command = \
            self.is12_utils.create_generic_get_command_JSON(version,
                                                            command_handle,
                                                            device_manager['oid'],
                                                            property_id)
        response, errorMsg, link = self.send_command(command_handle, get_descriptors_command)

        if not response:
            return test.FAIL(errorMsg, link)

        if self.is12_utils.compare_api_version(response['result']['value'], self.apis[MS05_API_KEY]["version"]):
            return test.FAIL("Unexpected version. Expected: "
                             + self.apis[MS05_API_KEY]["version"]
                             + ". Actual: " + str(response['result']['value']))

        return test.PASS()

    def test_19(self, test):
        """Non-standard classes contain an authority key"""
        # Referencing the Google sheet
        # MS-05-02 (72) Non-standard Classes NcClassId
        # MS-05-02 (73) Organization Identifier
        # For organizations which own a unique CID or OUI the authority key MUST be the organization
        # identifier as an integer which MUST be negated.
        # For organizations which do not own a unique CID or OUI the authority key MUST be 0
        # https://specs.amwa.tv/ms-05-02/branches/v1.0-dev/docs/Managers.html

        success, errorMsg, link = self.validate_device_model()
        if not success:
            return test.UNCLEAR(errorMsg, link)

        if self.organization_id_error:
            return test.FAIL(self.organization_id_error_msg,
                             "https://specs.amwa.tv/ms-05-02/branches/{}"
                             "/docs/Framework.html#ncclassid"
                             .format(self.apis[MS05_API_KEY]["spec_branch"]))

        if not self.organization_id_detected:
            return test.UNCLEAR("No non-standard classes found.")

        return test.PASS()
