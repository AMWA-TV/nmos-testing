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

from itertools import product
from jsonschema import ValidationError, SchemaError

from ..Config import WS_MESSAGE_TIMEOUT
from ..GenericTest import GenericTest, NMOSTestException
from ..IS12Utils import IS12Utils, NcMethodStatus, MessageTypes, NcObject
from ..TestHelper import WebsocketWorker, load_resolved_schema
from ..TestResult import Test

NODE_API_KEY = "node"
CONTROL_API_KEY = "ncp"
MS05_API_KEY = "controlframework"
FEATURE_SETS_KEY = "featuresets"

CLASS_MANAGER_CLS_ID = "1.3.2"
DEVICE_MANAGER_CLS_ID = "1.3.1"


class IS1201Test(GenericTest):

    def __init__(self, apis, **kwargs):
        # Remove the RAML key to prevent this test suite from auto-testing IS-04 API
        apis[NODE_API_KEY].pop("raml", None)
        GenericTest.__init__(self, apis, **kwargs)
        self.node_url = self.apis[NODE_API_KEY]["url"]
        self.ncp_url = self.apis[CONTROL_API_KEY]["url"]
        self.is12_utils = IS12Utils(self.node_url)
        self.ncp_websocket = None
        self.load_reference_resources()
        self.command_handle = 0
        self.root_block = None

    def set_up_tests(self):
        self.unique_roles_error = False
        self.unique_oids_error = False
        self.managers_are_singletons_error = False
        self.managers_members_root_block_error = False
        self.device_model_validated = False
        self.organization_metadata = {"checked": False, "error": False, "error_msg": ""}
        self.touchpoints_metadata = {"checked": False, "error": False, "error_msg": ""}
        self.get_sequence_item_metadata = {"checked": False, "error": False, "error_msg": ""}
        self.set_sequence_item_metadata = {"checked": False, "error": False, "error_msg": ""}
        self.add_sequence_item_metadata = {"checked": False, "error": False, "error_msg": ""}
        self.remove_sequence_item_metadata = {"checked": False, "error": False, "error_msg": ""}

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
                try:
                    self.result += self.auto_tests()
                except NMOSTestException as e:
                    self.result.append(e.args[0])
            self.execute_test(test_name)

    def load_model_descriptors(self, descriptor_paths):
        descriptors = {}
        for descriptor_path in descriptor_paths:
            for filename in os.listdir(descriptor_path):
                name, extension = os.path.splitext(filename)
                if extension == ".json":
                    with open(os.path.join(descriptor_path, filename), 'r') as json_file:
                        descriptors[name] = json.load(json_file)

        return descriptors

    def generate_json_schemas(self, datatype_descriptors, schema_path):
        """Generate datatype schemas from datatype descriptors"""
        datatype_schema_names = []
        base_schema_path = os.path.abspath(schema_path)
        if not os.path.exists(base_schema_path):
            os.makedirs(base_schema_path)

        for name, descriptor in datatype_descriptors.items():
            json_schema = self.is12_utils.descriptor_to_schema(descriptor)
            with open(os.path.join(base_schema_path, name + '.json'), 'w') as output_file:
                json.dump(json_schema, output_file, indent=4)
                datatype_schema_names.append(name)

        # Load resolved MS-05 datatype schemas
        datatype_schemas = {}
        for name in datatype_schema_names:
            datatype_schemas[name] = load_resolved_schema(schema_path, name + '.json', path_prefix=False)

        return datatype_schemas

    def load_reference_resources(self):
        """Load datatype and control class decriptors and create datatype JSON schemas"""
        # Load IS-12 schemas
        self.schemas = {}
        schema_names = ['error-message', 'command-response-message']
        for schema_name in schema_names:
            self.schemas[schema_name] = load_resolved_schema(self.apis[CONTROL_API_KEY]["spec_path"],
                                                             schema_name + ".json")
        # Calculate paths to MS-05 descriptors
        # including Feature Sets specified as additional_paths in test definition
        spec_paths = [os.path.join(self.apis[FEATURE_SETS_KEY]["spec_path"], path)
                      for path in self.apis[FEATURE_SETS_KEY]["repo_paths"]]
        spec_paths.append(self.apis[MS05_API_KEY]["spec_path"])

        datatype_paths = []
        classes_paths = []
        for spec_path in spec_paths:
            datatype_path = os.path.abspath(os.path.join(spec_path, 'models/datatypes/'))
            if os.path.exists(datatype_path):
                datatype_paths.append(datatype_path)
            classes_path = os.path.abspath(os.path.join(spec_path, 'models/classes/'))
            if os.path.exists(classes_path):
                classes_paths.append(classes_path)

        # Load class and datatype descriptors
        self.classes_descriptors = self.load_model_descriptors(classes_paths)

        # Load MS-05 datatype descriptors
        self.datatype_descriptors = self.load_model_descriptors(datatype_paths)

        # Generate MS-05 datatype schemas from MS-05 datatype descriptors
        self.datatype_schemas = self.generate_json_schemas(
            datatype_descriptors=self.datatype_descriptors,
            schema_path=os.path.join(self.apis[CONTROL_API_KEY]["spec_path"], 'APIs/schemas/'))

    def create_ncp_socket(self, test):
        """Create a WebSocket client connection to Node under test. Raises NMOSTestException on error"""
        # Reuse socket if connection already established
        if self.ncp_websocket and self.ncp_websocket.is_open():
            return

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
            raise NMOSTestException(test.FAIL("Failed to open WebSocket successfully"
                                    + (": " + str(self.ncp_websocket.get_error_message())
                                       if self.ncp_websocket.did_error_occur() else ".")))

    def get_command_handle(self):
        """Get unique command handle"""
        self.command_handle += 1
        return self.command_handle

    def send_command(self, test, command_handle, command_json):
        """Send command to Node under test. Returns [command response]. Raises NMOSTestException on error"""
        # Referencing the Google sheet
        # IS-12 (9)  Check protocol version and message type
        # IS-12 (10) Check handle numeric identifier
        # https://specs.amwa.tv/is-12/branches/v1.0-dev/docs/Protocol_messaging.html
        # IS-12 (11) Check Command message type
        # https://specs.amwa.tv/is-12/branches/v1.0-dev/docs/Protocol_messaging.html#command-message-type
        # MS-05-02 (74) All methods MUST return a datatype which inherits from NcMethodResult.
        #               When a method call encounters an error the return MUST be NcMethodResultError
        #               or a derived datatype.
        # https://specs.amwa.tv/ms-05-02/branches/v1.0-dev/docs/Framework.html#ncmethodresult

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
                self._validate_schema(test,
                                      parsed_message,
                                      self.schemas["command-response-message"],
                                      context="command-response-message: ")
                if IS12Utils.compare_api_version(parsed_message["protocolVersion"],
                                                 self.apis[CONTROL_API_KEY]["version"]):
                    raise NMOSTestException(test.FAIL("Incorrect protocol version. Expected "
                                                      + self.apis[CONTROL_API_KEY]["version"]
                                                      + ", received " + parsed_message["protocolVersion"],
                                                      "https://specs.amwa.tv/is-12/branches/{}"
                                                      "/docs/Protocol_messaging.html"
                                                      .format(self.apis[CONTROL_API_KEY]["spec_branch"])))

                responses = parsed_message["responses"]
                for response in responses:
                    if response["handle"] == command_handle:
                        if response["result"]["status"] != NcMethodStatus.OK:
                            raise NMOSTestException(test.FAIL(response["result"]))
                        results.append(response)
            if parsed_message["messageType"] == MessageTypes.Error:
                self._validate_schema(test,
                                      parsed_message,
                                      self.schemas["error-message"],
                                      context="error-message: ")
                raise NMOSTestException(test.FAIL(parsed_message, "https://specs.amwa.tv/is-12/branches/{}"
                                                  "/docs/Protocol_messaging.html#error-messages"
                                                  .format(self.apis[CONTROL_API_KEY]["spec_branch"])))
        if len(results) == 0:
            raise NMOSTestException(test.FAIL("No Command Message Response received.",
                                              "https://specs.amwa.tv/is-12/branches/{}"
                                              "/docs/Protocol_messaging.html#command-message-type"
                                              .format(self.apis[CONTROL_API_KEY]["spec_branch"])))

        if len(results) > 1:
            raise NMOSTestException(test.FAIL("Received multiple responses : " + len(responses)))

        return results[0]

    def get_manager(self, test, class_id_str):
        """Get Manager from Root Block. Returns [Manager]. Raises NMOSTestException on error"""
        command_handle = self.get_command_handle()
        version = self.is12_utils.format_version(self.apis[CONTROL_API_KEY]["version"])
        get_member_descriptors_command = \
            self.is12_utils.create_get_member_descriptors_JSON(version, command_handle, self.is12_utils.ROOT_BLOCK_OID)

        response = self.send_command(test, command_handle, get_member_descriptors_command)

        manager_found = False
        manager = None

        class_descriptor = self.classes_descriptors[class_id_str]

        for value in response["result"]["value"]:
            self._validate_schema(test,
                                  value,
                                  self.datatype_schemas["NcBlockMemberDescriptor"],
                                  context="NcBlockMemberDescriptor: ")

            if value["classId"] == class_descriptor["identity"]:
                manager_found = True
                manager = value

                if value["role"] != class_descriptor["fixedRole"]:
                    raise NMOSTestException(test.FAIL("Incorrect Role for Manager " + class_id_str + ": "
                                                      + value["role"],
                                                      "https://specs.amwa.tv/ms-05-02/branches/{}"
                                                      "/docs/Managers.html"
                                                      .format(self.apis[CONTROL_API_KEY]["spec_branch"])))

        if not manager_found:
            raise NMOSTestException(test.FAIL(str(class_id_str) + " Manager "
                                              + class_id_str + " not found in Root Block",
                                              "https://specs.amwa.tv/ms-05-02/branches/{}"
                                              "/docs/Managers.html"
                                              .format(self.apis[CONTROL_API_KEY]["spec_branch"])))

        return manager

    def validate_descriptor(self, test, reference, descriptor, context=""):
        """Validate descriptor against reference descriptor. Raises NMOSTestException on error"""
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
                raise NMOSTestException(test.FAIL(context + 'Missing/additional keys ' + str(key_diff)))

            for key in reference_keys:
                if key in non_normative_keys:
                    continue
                # Check for class ID
                if key == 'identity' and isinstance(reference[key], list):
                    if reference[key] != descriptor[key]:
                        raise NMOSTestException(test.FAIL(context + "Unexpected ClassId. Expected: "
                                                          + str(reference[key])
                                                          + " actual: " + str(descriptor[key])))
                else:
                    self.validate_descriptor(test, reference[key], descriptor[key], context=context + key + "->")
        elif isinstance(reference, list):
            # Convert to dict and validate
            references = {item['name']: item for item in reference}
            descriptors = {item['name']: item for item in descriptor}

            return self.validate_descriptor(test, references, descriptors, context)
        else:
            if reference != descriptor:
                raise NMOSTestException(test.FAIL(context + 'Expected value: '
                                                  + str(reference)
                                                  + ', actual value: '
                                                  + str(descriptor)))
        return

    def _validate_schema(self, test, payload, schema, context=""):
        """Delegates to validate_schema. Raises NMOSTestExceptions on error"""
        try:
            # Validate the JSON schema is correct
            self.validate_schema(payload, schema)
        except ValidationError as e:
            raise NMOSTestException(test.FAIL(context + "Schema validation error: " + e.message))
        except SchemaError as e:
            raise NMOSTestException(test.FAIL(context + "Schema error: " + e.message))

        return

    def _get_property(self, test, oid, property_id):
        """Get property from object. Raises NMOSTestException on error"""
        command_handle = self.get_command_handle()
        version = self.is12_utils.format_version(self.apis[CONTROL_API_KEY]["version"])

        get_property_command = \
            self.is12_utils.create_generic_get_command_JSON(version,
                                                            command_handle,
                                                            oid,
                                                            property_id)
        response = self.send_command(test, command_handle, get_property_command)

        return response["result"]["value"]

    def _set_property(self, test, oid, property_id, argument):
        """Get property from object. Raises NMOSTestException on error"""
        command_handle = self.get_command_handle()
        version = self.is12_utils.format_version(self.apis[CONTROL_API_KEY]["version"])

        set_property_command = \
            self.is12_utils.create_generic_set_command_JSON(version,
                                                            command_handle,
                                                            oid,
                                                            property_id,
                                                            argument)
        response = self.send_command(test, command_handle, set_property_command)

        return response["result"]

    def _get_sequence_item(self, test, oid, property_id, index):
        """Get value from sequence property. Raises NMOSTestException on error"""
        command_handle = self.get_command_handle()
        version = self.is12_utils.format_version(self.apis[CONTROL_API_KEY]["version"])

        get_sequence_item_command = \
            self.is12_utils.create_get_sequence_item_command_JSON(version,
                                                                  command_handle,
                                                                  oid,
                                                                  property_id,
                                                                  index)
        response = self.send_command(test, command_handle, get_sequence_item_command)

        return response["result"]["value"]

    def _set_sequence_item(self, test, oid, property_id, index, value):
        """Add value to a sequence property. Raises NMOSTestException on error"""
        command_handle = self.get_command_handle()
        version = self.is12_utils.format_version(self.apis[CONTROL_API_KEY]["version"])

        add_sequence_item_command = \
            self.is12_utils.create_set_sequence_item_command_JSON(version,
                                                                  command_handle,
                                                                  oid,
                                                                  property_id,
                                                                  index,
                                                                  value)
        response = self.send_command(test, command_handle, add_sequence_item_command)

        return response["result"]

    def _add_sequence_item(self, test, oid, property_id, value):
        """Add value to a sequence property. Raises NMOSTestException on error"""
        command_handle = self.get_command_handle()
        version = self.is12_utils.format_version(self.apis[CONTROL_API_KEY]["version"])

        add_sequence_item_command = \
            self.is12_utils.create_add_sequence_item_command_JSON(version,
                                                                  command_handle,
                                                                  oid,
                                                                  property_id,
                                                                  value)
        response = self.send_command(test, command_handle, add_sequence_item_command)

        return response["result"]

    def _remove_sequence_item(self, test, oid, property_id, index):
        """Get value from sequence property. Raises NMOSTestException on error"""
        command_handle = self.get_command_handle()
        version = self.is12_utils.format_version(self.apis[CONTROL_API_KEY]["version"])

        get_sequence_item_command = \
            self.is12_utils.create_remove_sequence_item_command_JSON(version,
                                                                     command_handle,
                                                                     oid,
                                                                     property_id,
                                                                     index)
        response = self.send_command(test, command_handle, get_sequence_item_command)

        return response["result"]

    def _find_members_by_path(self, test, oid, role_path):
        """Query members based on role path. Raises NMOSTestException on error"""
        command_handle = self.get_command_handle()
        version = self.is12_utils.format_version(self.apis[CONTROL_API_KEY]["version"])

        find_members_by_path_command = \
            self.is12_utils.create_find_members_by_path_command_JSON(version,
                                                                     command_handle,
                                                                     oid,
                                                                     role_path)
        response = self.send_command(test, command_handle, find_members_by_path_command)

        return response["result"]["value"]

    def _find_members_by_role(self, test, oid, role, case_sensitive, match_whole_string, recurse):
        """Query members based on role. Raises NMOSTestException on error"""
        command_handle = self.get_command_handle()
        version = self.is12_utils.format_version(self.apis[CONTROL_API_KEY]["version"])

        find_members_by_role_command = \
            self.is12_utils.create_find_members_by_role_command_JSON(version,
                                                                     command_handle,
                                                                     oid,
                                                                     role,
                                                                     case_sensitive,
                                                                     match_whole_string,
                                                                     recurse)
        response = self.send_command(test, command_handle, find_members_by_role_command)

        return response["result"]["value"]

    def get_class_manager_descriptors(self, test, class_manager_oid, property_id):
        response = self._get_property(test, class_manager_oid, property_id)

        # Create descriptor dictionary from response array
        # Use identity as key if present, otherwise use name
        def key_lambda(identity, name): return ".".join(map(str, identity)) if identity else name
        descriptors = {key_lambda(r.get('identity'), r['name']): r for r in response}

        return descriptors

    def validate_model_definitions(self, class_manager_oid, property_id, schema_name, reference_descriptors):
        """Validate class manager model definitions against reference model descriptors. Returns [test result array]"""
        results = list()

        test = Test("Validate model definitions", "auto_ValidateModel")
        descriptors = self.get_class_manager_descriptors(test, class_manager_oid, property_id)

        reference_descriptor_keys = sorted(reference_descriptors.keys())

        for key in reference_descriptor_keys:
            test = Test("Validate " + str(key) + " definition", "auto_" + str(key))
            try:
                if descriptors.get(key):
                    descriptor = descriptors[key]

                    # Validate the JSON schema is correct
                    self._validate_schema(test, descriptor, self.datatype_schemas[schema_name])

                    # Validate the descriptor is correct
                    self.validate_descriptor(test, reference_descriptors[key], descriptor)

                    results.append(test.PASS())
                else:
                    results.append(test.UNCLEAR("Not Implemented"))
            except NMOSTestException as e:
                results.append(e.args[0])

        return results

    def auto_tests(self):
        """Automatically validate all standard datatypes and control classes. Returns [test result array]"""
        # Referencing the Google sheet
        # MS-05-02 (75)  Model definitions
        results = list()
        test = Test("Initialize auto tests", "auto_init")

        self.create_ncp_socket(test)

        class_manager = self.get_manager(test, CLASS_MANAGER_CLS_ID)

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

        self.create_ncp_socket(test)

        return test.PASS()

    def test_03(self, test):
        """Root Block Exists with correct oid and Role"""
        # Referencing the Google sheet
        # MS-05-02 (44)	Root Block must exist
        # MS-05-02 (45) Verify oID and role of Root Block
        # https://specs.amwa.tv/ms-05-02/branches/v1.0-dev/docs/Blocks.html

        self.create_ncp_socket(test)

        role = self._get_property(test,
                                  self.is12_utils.ROOT_BLOCK_OID,
                                  self.is12_utils.PROPERTY_IDS['NCOBJECT']['ROLE'])

        if role != "root":
            return test.FAIL("Unexpected role in Root Block: " + role,
                             "https://specs.amwa.tv/ms-05-02/branches/{}"
                             "/docs/Blocks.html"
                             .format(self.apis[CONTROL_API_KEY]["spec_branch"]))

        return test.PASS()

    def test_04(self, test):
        """Class Manager exists in Root Block"""
        # Referencing the Google sheet
        # MS-05-02 (40) Class manager exists in root

        self.create_ncp_socket(test)

        self.get_manager(test, CLASS_MANAGER_CLS_ID)

        return test.PASS()

    def do_error_test(self, test, command_handle, command_json, expected_status=None, is12_error=True):
        """Execute command with expected error status."""
        # when expected_status = None checking of the status code is skipped
        # check the syntax of the error message according to is12_error

        try:
            self.create_ncp_socket(test)

            self.send_command(test, command_handle, command_json)

            return test.FAIL("Error expected")

        except NMOSTestException as e:
            error_msg = e.args[0].detail

            # Expecting an error status dictionary
            if not isinstance(error_msg, dict):
                # It must be some other type of error so re-throw
                raise e

            # 'protocolVersion' key is found in IS-12 protocol errors, but not in MS-05-02 errors
            if is12_error != ('protocolVersion' in error_msg):
                spec = "IS-12 protocol" if is12_error else "MS-05-02"
                return test.FAIL(spec + " error expected")

            if not error_msg.get('status'):
                return test.FAIL("Command error: " + str(error_msg))

            if error_msg['status'] == NcMethodStatus.OK:
                return test.FAIL("Error not handled. Expected: " + expected_status.name
                                 + " (" + str(expected_status) + ")"
                                 + ", actual: " + NcMethodStatus(error_msg['status']).name
                                 + " (" + str(error_msg['status']) + ")")

            if expected_status and error_msg['status'] != expected_status:
                return test.WARNING("Unexpected status. Expected: " + expected_status.name
                                    + " (" + str(expected_status) + ")"
                                    + ", actual: " + NcMethodStatus(error_msg['status']).name
                                    + " (" + str(error_msg['status']) + ")")

            return test.PASS()

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

    def validate_property_type(self, test, value, type, is_nullable, datatype_schemas, context=""):
        if value is None:
            if is_nullable:
                return
            else:
                raise NMOSTestException(test.FAIL(context + "Non-nullable property set to null."))

        if self.is12_utils.primitive_to_python_type(type):
            # Special case: if this is a floating point value it
            # can be intepreted as an int in the case of whole numbers
            # e.g. 0.0 -> 0, 1.0 -> 1
            if self.is12_utils.primitive_to_python_type(type) == float and isinstance(value, int):
                return

            if not isinstance(value, self.is12_utils.primitive_to_python_type(type)):
                raise NMOSTestException(test.FAIL(context + str(value) + " is not of type " + str(type)))
        else:
            self._validate_schema(test, value, datatype_schemas[type], context)

        return

    def check_get_sequence_item(self, test, oid, sequence_values, property_metadata, context=""):
        try:
            # GetSequenceItem
            self.get_sequence_item_metadata["checked"] = True
            sequence_index = 0
            for property_value in sequence_values:
                value = self._get_sequence_item(test, oid, property_metadata['id'], sequence_index)
                if property_value != value:
                    self.get_sequence_item_metadata["error"] = True
                    self.get_sequence_item_metadata["error_msg"] += \
                        context + property_metadata["name"] \
                        + ": Expected: " + str(property_value) + ", Actual: " + str(value) \
                        + " at index " + sequence_index + ", "
                sequence_index += 1
            return True
        except NMOSTestException as e:
            self.get_sequence_item_metadata["error"] = True
            self.get_sequence_item_metadata["error_msg"] += \
                context + property_metadata["name"] + ": " + str(e.args[0].detail) + ", "
        return False

    def check_add_sequence_item(self, test, oid, property_metadata, sequence_length, context=""):
        try:
            self.add_sequence_item_metadata["checked"] = True
            # Add a value to the end of the sequence
            new_item = self._get_sequence_item(test, oid, property_metadata['id'], index=0)

            self._add_sequence_item(test, oid, property_metadata['id'], new_item)

            # check the value
            value = self._get_sequence_item(test, oid, property_metadata['id'], index=sequence_length)
            if value != new_item:
                self.add_sequence_item_metadata["error"] = True
                self.add_sequence_item_metadata["error_msg"] += \
                    context + property_metadata["name"] \
                    + ": Expected: " + str(new_item) + ", Actual: " + str(value) + ", "
            return True
        except NMOSTestException as e:
            self.add_sequence_item_metadata["error"] = True
            self.add_sequence_item_metadata["error_msg"] += \
                context + property_metadata["name"] + ": " + str(e.args[0].detail) + ", "
        return False

    def check_set_sequence_item(self, test, oid, property_metadata, sequence_length, context=""):
        try:
            self.set_sequence_item_metadata["checked"] = True
            new_value = self._get_sequence_item(test, oid, property_metadata['id'], index=sequence_length - 1)

            # set to another value
            self._set_sequence_item(test, oid, property_metadata['id'], index=sequence_length, value=new_value)

            # check the value
            value = self._get_sequence_item(test, oid, property_metadata['id'], index=sequence_length)
            if value != new_value:
                self.set_sequence_item_metadata["error"] = True
                self.set_sequence_item_metadata["error_msg"] += \
                    context + property_metadata["name"] \
                    + ": Expected: " + str(new_value) + ", Actual: " + str(value) + ", "
            return True
        except NMOSTestException as e:
            self.set_sequence_item_metadata["error"] = True
            self.set_sequence_item_metadata["error_msg"] += \
                context + property_metadata["name"] + ": " + str(e.args[0].detail) + ", "
        return False

    def check_remove_sequence_item(self, test, oid, property_metadata, sequence_length, context=""):
        try:
            # remove item
            self.remove_sequence_item_metadata["checked"] = True
            self._remove_sequence_item(test, oid, property_metadata['id'], index=sequence_length)
            return True
        except NMOSTestException as e:
            self.remove_sequence_item_metadata["error"] = True
            self.remove_sequence_item_metadata["error_msg"] += \
                context + property_metadata["name"] + ": " + str(e.args[0].detail) + ", "
        return False

    def check_sequence_methods(self, test, oid, sequence_values, property_metadata, context=""):
        """Check that sequence manipulation methods work correctly"""
        self.check_get_sequence_item(test, oid, sequence_values, property_metadata, context)

        if not property_metadata['isReadOnly']:
            sequence_length = len(sequence_values)

            if not self.check_add_sequence_item(test, oid, property_metadata, sequence_length, context=context):
                return

            self.check_set_sequence_item(test, oid, property_metadata, sequence_length, context=context)

            self.check_remove_sequence_item(test, oid, property_metadata, sequence_length, context)

    def validate_object_properties(self, test, reference_class_descriptor, oid, datatype_schemas, context):
        for class_property in reference_class_descriptor['properties']:
            response = self._get_property(test, oid, class_property['id'])

            # validate property type
            if class_property['isSequence']:
                for property_value in response:
                    self.validate_property_type(test,
                                                property_value,
                                                class_property['typeName'],
                                                class_property['isNullable'],
                                                datatype_schemas,
                                                context=context + class_property["name"] + ": ")
                self.check_sequence_methods(test, oid, response, class_property, context=context)
            else:
                self.validate_property_type(test,
                                            response,
                                            class_property['typeName'],
                                            class_property['isNullable'],
                                            datatype_schemas,
                                            context=context + class_property["name"] + ": ")
        return

    def check_unique_roles(self, role, role_cache):
        """Check role is unique within containing Block"""
        if role in role_cache:
            self.unique_roles_error = True
        else:
            role_cache.append(role)

    def check_unique_oid(self, oid):
        """Check oid is globally unique"""
        if oid in self.oid_cache:
            self.unique_oids_error = True
        else:
            self.oid_cache.append(oid)

    def check_manager(self, class_id, owner, class_descriptors, manager_cache):
        """Check manager is singleton and that it inherits from NcManager"""
        # detemine the standard base class name
        base_id = self.is12_utils.get_base_class_id(class_id)
        base_class_name = class_descriptors[base_id]["name"]

        # manager checks
        if self.is12_utils.is_manager(class_id):
            if owner != self.is12_utils.ROOT_BLOCK_OID:
                self.managers_members_root_block_error = True
            if base_class_name in manager_cache:
                self.managers_are_singletons_error = True
            else:
                manager_cache.append(base_class_name)

    def check_touchpoints(self, test, oid, datatype_schemas, context):
        """Touchpoint checks"""
        touchpoints = self._get_property(test,
                                         oid,
                                         self.is12_utils.PROPERTY_IDS["NCOBJECT"]["TOUCHPOINTS"])
        if touchpoints is not None:
            self.touchpoints_metadata["checked"] = True
            try:
                for touchpoint in touchpoints:
                    schema = datatype_schemas["NcTouchpointNmos"] \
                        if touchpoint["contextNamespace"] == "x-nmos" \
                        else datatype_schemas["NcTouchpointNmosChannelMapping"]
                    self._validate_schema(test,
                                          touchpoint,
                                          schema,
                                          context=context + schema["title"] + ": ")
            except NMOSTestException as e:
                self.touchpoints_metadata["error"] = True
                self.touchpoints_metadata["error_msg"] = context + str(e.args[0].detail)

    def validate_block(self, test, block_id, class_descriptors, datatype_schemas, block, context=""):
        command_handle = self.get_command_handle()
        version = self.is12_utils.format_version(self.apis[CONTROL_API_KEY]["version"])

        get_member_descriptors_command = \
            self.is12_utils.create_get_member_descriptors_JSON(version, command_handle, block_id)

        response = self.send_command(test, command_handle, get_member_descriptors_command)

        role_cache = []
        manager_cache = []

        for child_object in response["result"]["value"]:
            child_block = NcObject(child_object['classId'], child_object['oid'], child_object['role'])

            self._validate_schema(test,
                                  child_object,
                                  datatype_schemas["NcBlockMemberDescriptor"],
                                  context="NcBlockMemberDescriptor: ")

            self.check_unique_roles(child_object['role'], role_cache)

            self.check_unique_oid(child_object['oid'])

            # check for non-standard classes
            if self.is12_utils.is_non_standard_class(child_object['classId']):
                self.organization_metadata["checked"] = True

            self.check_manager(child_object['classId'], child_object["owner"], class_descriptors, manager_cache)

            self.check_touchpoints(test, child_object['oid'], datatype_schemas,
                                   context=context + child_object['role'] + ': ')

            class_identifier = ".".join(map(str, child_object['classId']))

            if class_identifier:
                self.validate_object_properties(test,
                                                class_descriptors[class_identifier],
                                                child_object['oid'],
                                                datatype_schemas,
                                                context=context + child_object['role'] + ': ')
            else:
                # Not a standard or non-standard class
                self.organization_metadata["error"] = True
                self.organization_metadata["error_msg"] = child_object['role'] + ': ' \
                    + "Non-standard class id does not contain authority key: " \
                    + str(child_object['classId']) + ". "

            # If this child object is a Block, recurse
            if self.is12_utils.is_block(child_object['classId']):
                self.validate_block(test,
                                    child_object['oid'],
                                    class_descriptors,
                                    datatype_schemas,
                                    child_block,
                                    context=context + child_object['role'] + ': ')

            block.add_child_object(child_block)
        return

    def validate_device_model(self, test):
        if not self.device_model_validated:
            self.create_ncp_socket(test)

            class_manager = self.get_manager(test, CLASS_MANAGER_CLS_ID)

            class_descriptors = \
                self.get_class_manager_descriptors(test, class_manager['oid'],
                                                   self.is12_utils.PROPERTY_IDS['NCCLASSMANAGER']['CONTROL_CLASSES'])
            datatype_descriptors = \
                self.get_class_manager_descriptors(test, class_manager['oid'],
                                                   self.is12_utils.PROPERTY_IDS['NCCLASSMANAGER']['DATATYPES'])

            # Create JSON schemas for the queried datatypes
            datatype_schemas = self.generate_json_schemas(
                datatype_descriptors=datatype_descriptors,
                schema_path=os.path.join(self.apis[CONTROL_API_KEY]["spec_path"], 'APIs/tmp_schemas/'))

            self.root_block = NcObject(self.is12_utils.CLASS_IDS["NCBLOCK"], self.is12_utils.ROOT_BLOCK_OID, "root")

            self.validate_block(test,
                                self.is12_utils.ROOT_BLOCK_OID,
                                class_descriptors,
                                datatype_schemas,
                                self.root_block)

            self.device_model_validated = True
        return

    def test_13(self, test):
        """Validate device model properties against discovered classes and datatypes"""
        # Referencing the Google sheet
        # MS-05-02 (34) All workers MUST inherit from NcWorker
        # MS-05-02 (35) All managers MUST inherit from NcManager
        self.validate_device_model(test)

        return test.PASS()

    def test_14(self, test):
        """Device model roles are unique within a containing Block"""
        # Referencing the Google sheet
        # MS-05-02 (59) The role of an object MUST be unique within its containing Block.
        # https://specs.amwa.tv/ms-05-02/branches/v1.0-dev/docs/NcObject.html

        try:
            self.validate_device_model(test)
        except NMOSTestException as e:
            # Couldn't validate model so can't perform test
            return test.UNCLEAR(e.args[0].detail, e.args[0].link)

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

        try:
            self.validate_device_model(test)
        except NMOSTestException as e:
            # Couldn't validate model so can't perform test
            return test.UNCLEAR(e.args[0].detail, e.args[0].link)

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

        try:
            self.validate_device_model(test)
        except NMOSTestException as e:
            # Couldn't validate model so can't perform test
            return test.UNCLEAR(e.args[0].detail, e.args[0].link)

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

        try:
            self.validate_device_model(test)
        except NMOSTestException as e:
            # Couldn't validate model so can't perform test
            return test.UNCLEAR(e.args[0].detail, e.args[0].link)

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

        self.create_ncp_socket(test)

        device_manager = self.get_manager(test, DEVICE_MANAGER_CLS_ID)

        # Check MS-05-02 Version
        property_id = self.is12_utils.PROPERTY_IDS['NCDEVICEMANAGER']['NCVERSION']

        version = self._get_property(test, device_manager['oid'], property_id)

        if self.is12_utils.compare_api_version(version, self.apis[MS05_API_KEY]["version"]):
            return test.FAIL("Unexpected version. Expected: "
                             + self.apis[MS05_API_KEY]["version"]
                             + ". Actual: " + str(version))

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

        try:
            self.validate_device_model(test)
        except NMOSTestException as e:
            # Couldn't validate model so can't perform test
            return test.UNCLEAR(e.args[0].detail, e.args[0].link)

        if self.organization_metadata["error"]:
            return test.FAIL(self.organization_metadata["error_msg"],
                             "https://specs.amwa.tv/ms-05-02/branches/{}"
                             "/docs/Framework.html#ncclassid"
                             .format(self.apis[MS05_API_KEY]["spec_branch"]))

        if not self.organization_metadata["checked"]:
            return test.UNCLEAR("No non-standard classes found.")

        return test.PASS()

    def test_20(self, test):
        """Get/Set properties on Root Block"""
        # Referencing the Google sheet
        # MS-05-02 (39) Generic getter and setter
        # https://specs.amwa.tv/ms-05-02/branches/v1.0-dev/docs/NcObject.html#generic-getter-and-setter

        link = "https://specs.amwa.tv/ms-05-02/branches/{}" \
               "/docs/NcObject.html#generic-getter-and-setter" \
               .format(self.apis[MS05_API_KEY]["spec_branch"])

        # Attempt to set labels
        self.create_ncp_socket(test)

        property_id = self.is12_utils.PROPERTY_IDS['NCOBJECT']['USER_LABEL']

        old_user_label = self._get_property(test, self.is12_utils.ROOT_BLOCK_OID, property_id)

        # Set user label
        new_user_label = "NMOS Testing Tool"
        self._set_property(test, self.is12_utils.ROOT_BLOCK_OID, property_id, new_user_label)

        # Check user label
        label = self._get_property(test, self.is12_utils.ROOT_BLOCK_OID, property_id)
        if label != new_user_label:
            if label == old_user_label:
                return test.FAIL("Unable to set user label", link)
            else:
                return test.FAIL("Unexpected user label: " + str(label), link)

        # Reset user label
        self._set_property(test, self.is12_utils.ROOT_BLOCK_OID, property_id, old_user_label)

        # Check user label
        label = self._get_property(test, self.is12_utils.ROOT_BLOCK_OID, property_id)
        if label != old_user_label:
            if label == new_user_label:
                return test.FAIL("Unable to set user label", link)
            else:
                return test.FAIL("Unexpected user label: " + str(label), link)

        return test.PASS()

    def test_21(self, test):
        """Validate touchpoints"""
        # Referencing the Google sheet
        # MS-05-02 (39) For general NMOS contexts (IS-04, IS-05 and IS-07) the NcTouchpointNmos datatype MUST be used
        # which has a resource of type NcTouchpointResourceNmos.
        # For IS-08 Audio Channel Mapping the NcTouchpointResourceNmosChannelMapping datatype MUST be used
        # https://specs.amwa.tv/ms-05-02/branches/v1.0-dev/docs/NcObject.html#touchpoints
        try:
            self.validate_device_model(test)
        except NMOSTestException as e:
            # Couldn't validate model so can't perform test
            return test.UNCLEAR(e.args[0].detail, e.args[0].link)

        if self.touchpoints_metadata["error"]:
            return test.FAIL(self.touchpoints_metadata["error_msg"],
                             "https://specs.amwa.tv/ms-05-02/branches/{}"
                             "/docs/NcObject.html#touchpoints"
                             .format(self.apis[MS05_API_KEY]["spec_branch"]))

        if not self.touchpoints_metadata["checked"]:
            return test.UNCLEAR("No Touchpoints found.")
        return test.PASS()

    def test_22(self, test):
        """Get Sequence Item"""
        try:
            self.validate_device_model(test)
        except NMOSTestException as e:
            # Couldn't validate model so can't perform test
            return test.UNCLEAR(e.args[0].detail, e.args[0].link)

        if self.get_sequence_item_metadata["error"]:
            return test.FAIL(self.get_sequence_item_metadata["error_msg"])

        if not self.get_sequence_item_metadata["checked"]:
            return test.UNCLEAR("GetSequenceItem not tested.")

        return test.PASS()

    def test_23(self, test):
        """Set Sequence Item"""
        try:
            self.validate_device_model(test)
        except NMOSTestException as e:
            # Couldn't validate model so can't perform test
            return test.UNCLEAR(e.args[0].detail, e.args[0].link)

        if self.set_sequence_item_metadata["error"]:
            return test.FAIL(self.set_sequence_item_metadata["error_msg"])

        if not self.set_sequence_item_metadata["checked"]:
            return test.UNCLEAR("SetSequenceItem not tested.")

        return test.PASS()

    def test_24(self, test):
        """Add Sequence Item"""
        try:
            self.validate_device_model(test)
        except NMOSTestException as e:
            # Couldn't validate model so can't perform test
            return test.UNCLEAR(e.args[0].detail, e.args[0].link)

        if self.add_sequence_item_metadata["error"]:
            return test.FAIL(self.add_sequence_item_metadata["error_msg"])

        if not self.add_sequence_item_metadata["checked"]:
            return test.UNCLEAR("AddSequenceItem not tested.")

        return test.PASS()

    def test_25(self, test):
        """Remove Sequence Item"""
        try:
            self.validate_device_model(test)
        except NMOSTestException as e:
            # Couldn't validate model so can't perform test
            return test.UNCLEAR(e.args[0].detail, e.args[0].link)

        if self.remove_sequence_item_metadata["error"]:
            return test.FAIL(self.remove_sequence_item_metadata["error_msg"])

        if not self.remove_sequence_item_metadata["checked"]:
            return test.UNCLEAR("RemoveSequenceItem not tested.")

        return test.PASS()

    def do_role_path_test(self, test, block):
        # Recurse through the child blocks
        for child_object in block.child_objects:
            if self.is12_utils.is_block(child_object.class_id):
                self.do_role_path_test(test, child_object)

        # Get ground truth role paths
        role_paths = block.get_role_paths()

        for role_path in role_paths:
            # Get ground truth data from local device model object tree
            expected_member = block.find_members_by_path(role_path)

            queried_members = self._find_members_by_path(test, block.oid, role_path)

            for queried_member in queried_members:
                self._validate_schema(test,
                                      queried_member,
                                      self.datatype_schemas["NcBlockMemberDescriptor"],
                                      context="NcBlockMemberDescriptor: ")

            if len(queried_members) != 1:
                raise NMOSTestException(test.FAIL("Incorrect member found by role path: " + str(role_path)))

            queried_member_oids = [m['oid'] for m in queried_members]

            if expected_member.oid not in queried_member_oids:
                raise NMOSTestException(test.FAIL("Unsuccessful attempt to find member by role path: "
                                                  + str(role_path)))

    def test_26(self, test):
        """Find member by path"""
        try:
            self.validate_device_model(test)
        except NMOSTestException as e:
            # Couldn't validate model so can't perform test
            return test.UNCLEAR(e.args[0].detail, e.args[0].link)

        # Recursively check each block in Device Model
        self.do_role_path_test(test, self.root_block)

        return test.PASS()

    def do_role_test(self, test, block):
        # Recurse through the child blocks
        for child_object in block.child_objects:
            if self.is12_utils.is_block(child_object.class_id):
                self.do_role_test(test, child_object)

        role_paths = IS12Utils.sampled_list(block.get_role_paths())
        # Generate every combination of case_sensitive, match_whole_string and recurse
        truth_table = IS12Utils.sampled_list(list(product([False, True], repeat=3)))
        search_conditions = []
        for state in truth_table:
            search_conditions += [{"case_sensitive": state[0], "match_whole_string": state[1], "recurse": state[2]}]

        for role_path in role_paths:
            role = role_path[-1]
            # Case sensitive role, case insensitive role, CS role substring and CI role substring
            query_strings = [role, role.upper(), role[-4:], role[-4:].upper()]

            for condition in search_conditions:
                for query_string in query_strings:
                    # Get ground truth result
                    expected_results = \
                        block.find_members_by_role(query_string,
                                                   case_sensitive=condition["case_sensitive"],
                                                   match_whole_string=condition["match_whole_string"],
                                                   recurse=condition["recurse"])
                    actual_results = self._find_members_by_role(test,
                                                                block.oid,
                                                                query_string,
                                                                case_sensitive=condition["case_sensitive"],
                                                                match_whole_string=condition["match_whole_string"],
                                                                recurse=condition["recurse"])

                    expected_results_oids = [m.oid for m in expected_results]

                    if len(actual_results) != len(expected_results):
                        raise NMOSTestException(test.FAIL("Expected "
                                                          + str(len(expected_results))
                                                          + ", but got "
                                                          + str(len(actual_results))))

                    for actual_result in actual_results:
                        if actual_result["oid"] not in expected_results_oids:
                            raise NMOSTestException(test.FAIL("Unexpected search result. " + str(actual_result)))

    def test_27(self, test):
        """Find member by role"""
        try:
            self.validate_device_model(test)
        except NMOSTestException as e:
            # Couldn't validate model so can't perform test
            return test.UNCLEAR(e.args[0].detail, e.args[0].link)

        # Recursively check each block in Device Model
        self.do_role_test(test, self.root_block)

        return test.PASS()
