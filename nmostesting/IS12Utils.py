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

from .MS05Utils import MS05Utils

import json
import os
import time

from copy import deepcopy
from enum import IntEnum, Enum
from itertools import takewhile, dropwhile
from jsonschema import FormatChecker, SchemaError, validate, ValidationError
from .Config import WS_MESSAGE_TIMEOUT
from .GenericTest import NMOSTestException
from .TestHelper import WebsocketWorker, load_resolved_schema
from .MS05Utils import NcMethodStatus, NcObjectMethods, NcBlockMethods, NcClassManagerMethods, NcClassManagerProperties, NcDatatypeType, StandardClassIds, NcObjectProperties, NcBlockProperties,  NcObject, NcBlock, NcClassManager

CONTROL_API_KEY = "ncp"
MS05_API_KEY = "controlframework"
FEATURE_SETS_KEY = "featuresets"


class MessageTypes(IntEnum):
    Command = 0
    CommandResponse = 1
    Notification = 2
    Subscription = 3
    SubscriptionResponse = 4
    Error = 5


class IS12Utils(MS05Utils):
    def __init__(self, apis):
        MS05Utils.__init__(self, apis)
        self.apis = apis
        self.spec_path = self.apis[CONTROL_API_KEY]["spec_path"]
        self.spec_branch = self.apis[CONTROL_API_KEY]["spec_branch"]
        self._load_is12_schemas()
        self.ROOT_BLOCK_OID = 1
        self.ncp_websocket = None
        self.command_handle = 0
        self.expect_notifications = False
        self.notifications = []
        self.device_model = None
        self.class_manager = None

    def _load_is12_schemas(self):
        """Load datatype and control class decriptors and create datatype JSON schemas"""
        # Load IS-12 schemas
        self.schemas = {}
        schema_names = ["error-message",
                        "command-response-message",
                        "subscription-response-message",
                        "notification-message"]
        for schema_name in schema_names:
            self.schemas[schema_name] = load_resolved_schema(self.apis[CONTROL_API_KEY]["spec_path"],
                                                             schema_name + ".json")

    def open_ncp_websocket(self, test):
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

    def close_ncp_websocket(self):
        # Clean up Websocket resources
        if self.ncp_websocket:
            self.ncp_websocket.close()

    def validate_reference_datatype_schema(self, test, payload, datatype_name, context=""):
        """Validate payload against reference datatype schema"""
        self.validate_schema(test, payload, self.reference_datatype_schemas[datatype_name])

    def validate_schema(self, test, payload, schema, context=""):
        """Delegates to validate_schema. Raises NMOSTestExceptions on error"""
        if not schema:
            raise NMOSTestException(test.FAIL(context + "Missing schema. "))
        try:
            # Validate the JSON schema is correct
            checker = FormatChecker(["ipv4", "ipv6", "uri"])
            validate(payload, schema, format_checker=checker)
        except ValidationError as e:
            raise NMOSTestException(test.FAIL(context + "Schema validation error: " + e.message))
        except SchemaError as e:
            raise NMOSTestException(test.FAIL(context + "Schema error: " + e.message))

        return

    def _validate_is12_schema(self, test, payload, schema_name, context=""):
        """Delegates to validate_schema. Raises NMOSTestExceptions on error"""
        try:
            # Validate the JSON schema is correct
            checker = FormatChecker(["ipv4", "ipv6", "uri"])
            validate(payload, self.schemas[schema_name], format_checker=checker)
        except ValidationError as e:
            raise NMOSTestException(test.FAIL(context + "Schema validation error: " + e.message))
        except SchemaError as e:
            raise NMOSTestException(test.FAIL(context + "Schema error: " + e.message))

        return

    def message_type_to_schema_name(self, type):
        """Convert MessageType to corresponding JSON schema name"""

        types = {
            MessageTypes.CommandResponse: "command-response-message",
            MessageTypes.Notification: "notification-message",
            MessageTypes.SubscriptionResponse: "subscription-response-message",
            MessageTypes.Error: "error-message",
        }

        return types.get(type, False)

    def send_command(self, test, command_json):
        """Send command to Node under test. Returns [command response]. Raises NMOSTestException on error"""
        # IS-12 Check message type, check handle numeric identifier
        # https://specs.amwa.tv/is-12/branches/v1.0/docs/Protocol_messaging.html#command-message-type
        # MS-05-02 All methods MUST return a datatype which inherits from NcMethodResult.
        # When a method call encounters an error the return MUST be NcMethodResultError
        # or a derived datatype.
        # https://specs.amwa.tv/ms-05-02/branches/v1.0/docs/Framework.html#ncmethodresult

        # Assume single command
        command_handle = command_json['commands'][0]['handle'] if command_json.get('commands') else 0

        self.ncp_websocket.send(json.dumps(command_json))

        results = []
        start_time = time.time()
        while time.time() < start_time + WS_MESSAGE_TIMEOUT:
            if not self.ncp_websocket.is_messages_received():
                time.sleep(0.2)
                continue

            # find the response to our request
            for message in self.ncp_websocket.get_messages():
                parsed_message = json.loads(message)

                if self.message_type_to_schema_name(parsed_message.get("messageType")):
                    self._validate_is12_schema(
                        test,
                        parsed_message,
                        self.message_type_to_schema_name(parsed_message["messageType"]),
                        context=self.message_type_to_schema_name(parsed_message["messageType"]) + ": ")
                else:
                    raise NMOSTestException(test.FAIL("Unrecognised message type: " + parsed_message.get("messageType"),
                                                      "https://specs.amwa.tv/is-12/branches/{}"
                                                      "/docs/Protocol_messaging.html#command-message-type"
                                                      .format(self.spec_branch)))

                if parsed_message["messageType"] == MessageTypes.CommandResponse:
                    responses = parsed_message["responses"]
                    for response in responses:
                        if response["handle"] == command_handle:
                            # Make sure 2xx return code
                            if response["result"]["status"] != NcMethodStatus.OK and \
                                    response["result"]["status"] != NcMethodStatus.PropertyDeprecated and \
                                    response["result"]["status"] != NcMethodStatus.MethodDeprecated:
                                # The response["result"] is used in negative tests
                                # to ensure command fail when expected to
                                raise NMOSTestException(test.FAIL(response["result"]))
                            results.append(response)
                if parsed_message["messageType"] == MessageTypes.SubscriptionResponse:
                    results.append(parsed_message["subscriptions"])
                if parsed_message["messageType"] == MessageTypes.Notification:
                    self.notifications += parsed_message["notifications"]
                if parsed_message["messageType"] == MessageTypes.Error:
                    raise NMOSTestException(test.FAIL(parsed_message, "https://specs.amwa.tv/is-12/branches/{}"
                                                      "/docs/Protocol_messaging.html#error-messages"
                                                      .format(self.spec_branch)))

            if not self.expect_notifications and len(results) != 0:
                break
            if self.expect_notifications and len(results) != 0 and len(self.notifications) != 0:
                break

        if len(results) == 0:
            raise NMOSTestException(test.FAIL("No Message Response received.",
                                              "https://specs.amwa.tv/is-12/branches/{}"
                                              "/docs/Protocol_messaging.html#command-message-type"
                                              .format(self.spec_branch)))

        if len(results) > 1:
            raise NMOSTestException(test.FAIL("Received multiple responses : " + len(responses)))

        return results[0]

    def get_notifications(self):
        return self.notifications

    def start_logging_notifications(self):
        self.expect_notifications = True
        self.notifications = []

    def stop_logging_notifications(self):
        self.expect_notifications = False

    def create_command_JSON(self, oid, method_id, arguments):
        """for sending over websocket"""
        self.command_handle += 1
        return {
            'messageType': MessageTypes.Command,
            'commands': [
                {
                    'handle': self.command_handle,
                    'oid': oid,
                    'methodId': method_id,
                    'arguments': arguments
                }
            ],
        }

    def execute_command(self, test, oid, method_id, arguments):
        command_JSON = self.create_command_JSON(oid, method_id, arguments)
        response = self.send_command(test, command_JSON)
        return response["result"]

    def get_property_value(self, test, oid, property_id):
        """Get value of property from object. Raises NMOSTestException on error"""
        return self.execute_command(test, oid,
                                    NcObjectMethods.GENERIC_GET.value,
                                    {'id': property_id})["value"]

    def get_property(self, test, oid, property_id):
        """Get property from object. Raises NMOSTestException on error"""
        return self.execute_command(test, oid,
                                    NcObjectMethods.GENERIC_GET.value,
                                    {'id': property_id})

    def set_property(self, test, oid, property_id, argument):
        """Get property from object. Raises NMOSTestException on error"""
        return self.execute_command(test, oid,
                                    NcObjectMethods.GENERIC_SET.value,
                                    {'id': property_id, 'value': argument})

    def get_sequence_item(self, test, oid, property_id, index):
        """Get value from sequence property. Raises NMOSTestException on error"""
        return self.execute_command(test, oid,
                                    NcObjectMethods.GET_SEQUENCE_ITEM.value,
                                    {'id': property_id, 'index': index})["value"]

    def set_sequence_item(self, test, oid, property_id, index, value):
        """Add value to a sequence property. Raises NMOSTestException on error"""
        return self.execute_command(test, oid,
                                    NcObjectMethods.SET_SEQUENCE_ITEM.value,
                                    {'id': property_id, 'index': index, 'value': value})

    def add_sequence_item(self, test, oid, property_id, value):
        """Add value to a sequence property. Raises NMOSTestException on error"""
        return self.execute_command(test, oid,
                                    NcObjectMethods.ADD_SEQUENCE_ITEM.value,
                                    {'id': property_id, 'value': value})

    def remove_sequence_item(self, test, oid, property_id, index):
        """Get value from sequence property. Raises NMOSTestException on error"""
        return self.execute_command(test, oid,
                                    NcObjectMethods.REMOVE_SEQUENCE_ITEM.value,
                                    {'id': property_id, 'index': index})

    def get_sequence_length(self, test, oid, property_id):
        """Get value from sequence property. Raises NMOSTestException on error"""
        return self.execute_command(test, oid,
                                    NcObjectMethods.GET_SEQUENCE_LENGTH.value,
                                    {'id': property_id})["value"]

    def get_member_descriptors(self, test, oid, recurse):
        """Get BlockMemberDescritors for this block. Raises NMOSTestException on error"""
        return self.execute_command(test, oid,
                                    NcBlockMethods.GET_MEMBERS_DESCRIPTOR.value,
                                    {'recurse': recurse})["value"]

    def find_members_by_path(self, test, oid, role_path):
        """Query members based on role path. Raises NMOSTestException on error"""
        return self.execute_command(test, oid,
                                    NcBlockMethods.FIND_MEMBERS_BY_PATH.value,
                                    {'path': role_path})["value"]

    def find_members_by_role(self, test, oid, role, case_sensitive, match_whole_string, recurse):
        """Query members based on role. Raises NMOSTestException on error"""
        return self.execute_command(test, oid,
                                    NcBlockMethods.FIND_MEMBERS_BY_ROLE.value,
                                    {'role': role,
                                     'caseSensitive': case_sensitive,
                                     'matchWholeString': match_whole_string,
                                     'recurse': recurse})["value"]

    def find_members_by_class_id(self, test, oid, class_id, include_derived, recurse):
        """Query members based on class id. Raises NMOSTestException on error"""
        return self.execute_command(test, oid,
                                    NcBlockMethods.FIND_MEMBERS_BY_CLASS_ID.value,
                                    {'classId': class_id,
                                     'includeDerived': include_derived,
                                     'recurse': recurse})["value"]

    def get_control_class(self, test, oid, class_id, include_inherited):
        """Query Class Manager for control class. Raises NMOSTestException on error"""
        return self.execute_command(test, oid,
                                    NcClassManagerMethods.GET_CONTROL_CLASS.value,
                                    {'classId': class_id,
                                     'includeInherited': include_inherited})["value"]

    def get_datatype(self, test, oid, name, include_inherited):
        """Query Class Manager for datatype. Raises NMOSTestException on error"""
        return self.execute_command(test, oid,
                                    NcClassManagerMethods.GET_DATATYPE.value,
                                    {'name': name,
                                     'includeInherited': include_inherited})["value"]

    def create_subscription_JSON(self, subscriptions):
        """for sending over websocket"""
        return {
            'messageType': MessageTypes.Subscription,
            'subscriptions': subscriptions
        }

    def update_subscritions(self, test, subscriptions):
        """update Nodes subscriptions"""
        command_JSON = self.create_subscription_JSON(subscriptions)
        response = self.send_command(test, command_JSON)
        return response

    def _primitive_to_JSON(self, type):
        """Convert MS-05 primitive type to corresponding JSON type"""

        types = {
            "NcBoolean": "boolean",
            "NcInt16": "number",
            "NcInt32": "number",
            "NcInt64": "number",
            "NcUint16": "number",
            "NcUint32": "number",
            "NcUint64": "number",
            "NcFloat32": "number",
            "NcFloat64":  "number",
            "NcString": "string"
        }

        return types.get(type, False)

    def primitive_to_python_type(self, type):
        """Convert MS-05 primitive type to corresponding Python type"""

        types = {
            "NcBoolean": bool,
            "NcInt16": int,
            "NcInt32": int,
            "NcInt64": int,
            "NcUint16": int,
            "NcUint32": int,
            "NcUint64": int,
            "NcFloat32": float,
            "NcFloat64":  float,
            "NcString": str
        }

        return types.get(type, False)

    def descriptor_to_schema(self, descriptor):
        variant_type = ['number', 'string', 'boolean', 'object', 'array', 'null']

        json_schema = {}
        json_schema['$schema'] = 'http://json-schema.org/draft-07/schema#'

        json_schema['title'] = descriptor['name']
        json_schema['description'] = descriptor['description'] if descriptor['description'] else ""

        # Inheritance of datatype
        if descriptor.get('parentType'):
            if descriptor.get('isSequence'):
                json_schema['type'] = 'array'
                json_schema['items'] = {'$ref': descriptor['parentType'] + '.json'}
            else:
                json_schema['allOf'] = []
                json_schema['allOf'].append({'$ref': descriptor['parentType'] + '.json'})
        # Primitive datatype
        elif descriptor['type'] == NcDatatypeType.Primitive:
            json_schema['type'] = self._primitive_to_JSON(descriptor['name'])

        # Struct datatype
        if descriptor['type'] == NcDatatypeType.Struct and descriptor.get('fields'):
            json_schema['type'] = 'object'

            required = []
            properties = {}
            for field in descriptor['fields']:
                required.append(field['name'])

                property_type = {}
                if self._primitive_to_JSON(field['typeName']):
                    if field['isNullable']:
                        property_type = {'type': [self._primitive_to_JSON(field['typeName']), 'null']}
                    else:
                        property_type = {'type': self._primitive_to_JSON(field['typeName'])}
                else:
                    if field.get('typeName'):
                        if field['isNullable']:
                            property_type['anyOf'] = []
                            property_type['anyOf'].append({'$ref': field['typeName'] + '.json'})
                            property_type['anyOf'].append({'type': 'null'})
                        else:
                            property_type = {'$ref': field['typeName'] + '.json'}
                    else:
                        # variant
                        property_type = {'type': variant_type}

                if field.get('isSequence'):
                    property_type = {'type': 'array', 'items': property_type}

                property_type['description'] = field['description'] if descriptor['description'] else ""
                properties[field['name']] = property_type

            json_schema['required'] = required
            json_schema['properties'] = properties

        # Enum datatype
        if descriptor['type'] == NcDatatypeType.Enum and descriptor.get('items'):
            json_schema['enum'] = []
            for item in descriptor['items']:
                json_schema['enum'].append(int(item['value']))
            json_schema['type'] = 'integer'

        return json_schema

    def get_base_class_id(self, class_id):
        """ Given a class_id returns the standard base class id as a string"""
        return '.'.join([str(v) for v in takewhile(lambda x: x > 0, class_id)])

    def is_non_standard_class(self, class_id):
        """ Check class_id to determine if it is for a non-standard class """
        # Assumes at least one value follows the authority key
        return len([v for v in dropwhile(lambda x: x > 0, class_id)]) > 1

    def is_manager(self, class_id):
        """ Check class id to determine if this is a manager """
        return len(class_id) > 1 and class_id[0] == 1 and class_id[1] == 3

    def load_reference_resources(self):
        """Load datatype and control class decriptors and create datatype JSON schemas"""
        # Calculate paths to MS-05 descriptors
        # including Feature Sets specified as additional_paths in test definition
        spec_paths = [os.path.join(self.apis[FEATURE_SETS_KEY]["spec_path"], path)
                      for path in self.apis[FEATURE_SETS_KEY]["repo_paths"]]
        spec_paths.append(self.apis[MS05_API_KEY]["spec_path"])
        # Root path for primitive datatypes
        spec_paths.append('test_data/IS1201')

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
        self.reference_class_descriptors = self._load_model_descriptors(classes_paths)

        # Load MS-05 datatype descriptors
        self.reference_datatype_descriptors = self._load_model_descriptors(datatype_paths)

        # Generate MS-05 datatype schemas from MS-05 datatype descriptors
        self.reference_datatype_schemas = self.generate_json_schemas(
            datatype_descriptors=self.reference_datatype_descriptors,
            schema_path=os.path.join(self.apis[CONTROL_API_KEY]["spec_path"], 'APIs/schemas/'))

    def _load_model_descriptors(self, descriptor_paths):
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
            json_schema = self.descriptor_to_schema(descriptor)
            with open(os.path.join(base_schema_path, name + '.json'), 'w') as output_file:
                json.dump(json_schema, output_file, indent=4)
                datatype_schema_names.append(name)

        # Load resolved MS-05 datatype schemas
        datatype_schemas = {}
        for name in datatype_schema_names:
            datatype_schemas[name] = load_resolved_schema(schema_path, name + '.json', path_prefix=False)

        return datatype_schemas

    def validate_descriptor(self, test, reference, descriptor, context=""):
        """Validate descriptor against reference descriptor. Raises NMOSTestException on error"""
        non_normative_keys = ['description']

        if isinstance(reference, dict):
            reference_keys = set(reference.keys())
            descriptor_keys = set(descriptor.keys())

            # compare the keys to see if any extra/missing
            key_diff = (set(reference_keys) | set(descriptor_keys)) - (set(reference_keys) & set(descriptor_keys))
            if len(key_diff) > 0:
                error_description = "Missing keys " if set(key_diff) <= set(reference_keys) else "Additional keys "
                raise NMOSTestException(test.FAIL(context + error_description + str(key_diff)))
            for key in reference_keys:
                if key in non_normative_keys and not isinstance(reference[key], dict):
                    continue
                # Check for class ID
                if key == 'classId' and isinstance(reference[key], list):
                    if reference[key] != descriptor[key]:
                        raise NMOSTestException(test.FAIL(context + "Unexpected ClassId. Expected: "
                                                          + str(reference[key])
                                                          + " actual: " + str(descriptor[key])))
                else:
                    self.validate_descriptor(test, reference[key], descriptor[key], context=context + key + "->")
        elif isinstance(reference, list):
            if len(reference) > 0 and isinstance(reference[0], dict):
                # Convert to dict and validate
                references = {item['name']: item for item in reference}
                descriptors = {item['name']: item for item in descriptor}

                self.validate_descriptor(test, references, descriptors, context)
            elif reference != descriptor:
                raise NMOSTestException(test.FAIL(context + "Unexpected sequence. Expected: "
                                                  + str(reference)
                                                  + " actual: " + str(descriptor)))
        else:
            if reference != descriptor:
                raise NMOSTestException(test.FAIL(context + 'Expected value: '
                                                  + str(reference)
                                                  + ', actual value: '
                                                  + str(descriptor)))
        return

    def _get_class_manager_descriptors(self, test, class_manager_oid, property_id):
        response = self.get_property_value(test, class_manager_oid, property_id)

        if not response:
            return None

        # Create descriptor dictionary from response array
        # Use classId as key if present, otherwise use name
        def key_lambda(classId, name): return ".".join(map(str, classId)) if classId else name
        descriptors = {key_lambda(r.get('classId'), r['name']): r for r in response}

        return descriptors

    def query_device_model(self, test):
        """ Query Device Model from the Node under test.
            self.device_model_metadata set on Device Model validation error.
            NMOSTestException raised if unable to query Device Model """
        self.open_ncp_websocket(test)
        if not self.device_model:
            self.device_model = self._nc_object_factory(
                test,
                StandardClassIds.NCBLOCK.value,
                self.ROOT_BLOCK_OID,
                "root")

            if not self.device_model:
                raise NMOSTestException(test.FAIL("Unable to query Device Model"))
        return self.device_model

    def get_class_manager(self, test):
        """Get the Class Manager queried from the Node under test's Device Model"""
        if not self.class_manager:
            self.class_manager = self._get_manager(test, StandardClassIds.NCCLASSMANAGER.value)

        return self.class_manager

    def get_device_manager(self, test):
        """Get the Device Manager queried from the Node under test's Device Model"""
        return self._get_manager(test, StandardClassIds.NCDEVICEMANAGER.value)

    def _get_manager(self, test, class_id):
        self.open_ncp_websocket(test)
        device_model = self.query_device_model(test)
        members = device_model.find_members_by_class_id(class_id, include_derived=True)

        spec_link = "https://specs.amwa.tv/ms-05-02/branches/{}/docs/Managers.html".format(self.spec_branch)

        if len(members) == 0:
            raise NMOSTestException(test.FAIL("Manager not found in Root Block.", spec_link))

        if len(members) > 1:
            raise NMOSTestException(test.FAIL("Manager MUST be a singleton.", spec_link))

        return members[0]

    def _nc_object_factory(self, test, class_id, oid, role):
        """Create NcObject or NcBlock based on class_id"""
        # will set self.device_model_error to True if problems encountered
        try:
            runtime_constraints = self.get_property_value(
                    test,
                    oid,
                    NcObjectProperties.RUNTIME_PROPERTY_CONSTRAINTS.value)

            # Check class id to determine if this is a block
            if len(class_id) > 1 and class_id[0] == 1 and class_id[1] == 1:
                member_descriptors = self.get_property_value(
                    test,
                    oid,
                    NcBlockProperties.MEMBERS.value)

                nc_block = NcBlock(class_id, oid, role, member_descriptors, runtime_constraints)

                for m in member_descriptors:
                    child_object = self._nc_object_factory(test, m["classId"], m["oid"], m["role"])
                    if child_object:
                        nc_block.add_child_object(child_object)

                return nc_block
            else:
                # Check to determine if this is a Class Manager
                if len(class_id) > 2 and class_id[0] == 1 and class_id[1] == 3 and class_id[2] == 2:
                    class_descriptors = self._get_class_manager_descriptors(
                        test,
                        oid,
                        NcClassManagerProperties.CONTROL_CLASSES.value)

                    datatype_descriptors = self._get_class_manager_descriptors(
                        test,
                        oid,
                        NcClassManagerProperties.DATATYPES.value)

                    if not class_descriptors or not datatype_descriptors:
                        # An error has likely occured
                        return None

                    return NcClassManager(class_id,
                                          oid,
                                          role,
                                          class_descriptors,
                                          datatype_descriptors,
                                          runtime_constraints)

                return NcObject(class_id, oid, role, runtime_constraints)

        except NMOSTestException as e:
            raise NMOSTestException(test.FAIL("Error in Device Model " + role + ": " + str(e.args[0].detail)))

    def resolve_datatype(self, test, datatype):
        """Resolve datatype to its base type"""
        class_manager = self.get_class_manager(test)
        if class_manager.datatype_descriptors[datatype].get("parentType"):
            return self.resolve_datatype(test, class_manager.datatype_descriptors[datatype].get("parentType"))
        return datatype

