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

from .NMOSUtils import NMOSUtils

import json
import time

from copy import deepcopy
from enum import IntEnum, Enum
from itertools import takewhile, dropwhile
from jsonschema import FormatChecker, SchemaError, validate, ValidationError
from .Config import WS_MESSAGE_TIMEOUT
from .GenericTest import NMOSTestException
from .TestHelper import WebsocketWorker, load_resolved_schema


class MessageTypes(IntEnum):
    Command = 0
    CommandResponse = 1
    Notification = 2
    Subscription = 3
    SubscriptionResponse = 4
    Error = 5


class NcMethodStatus(IntEnum):
    OK = 200
    BadCommandFormat = 400
    Unauthorized = 401
    BadOid = 404
    Readonly = 405
    InvalidRequest = 406
    Conflict = 409
    BufferOverflow = 413
    IndexOutOfBounds = 414
    ParameterError = 417
    Locked = 423
    DeviceError = 500
    MethodNotImplemented = 501
    PropertyNotImplemented = 502
    NotReady = 503
    Timeout = 504
    UNKNOWN = 9999

    @classmethod
    def _missing_(cls, _):
        return cls.UNKNOWN


class NcDatatypeType(IntEnum):
    Primitive = 0  # Primitive datatype
    Typedef = 1  # Simple alias of another datatype
    Struct = 2  # Data structure
    Enum = 3  # Enum datatype


class NcPropertyChangeType(IntEnum):
    ValueChanged = 0  # Current value changed
    SequenceItemAdded = 1  # Sequence item added
    SequenceItemChanged = 2  # Sequence item changed
    SequenceItemRemoved = 3  # Sequence item removed
    UNKNOWN = 9999

    @classmethod
    def _missing_(cls, _):
        return cls.UNKNOWN


class NcObjectProperties(Enum):
    CLASS_ID = {'level': 1, 'index': 1}
    OID = {'level': 1, 'index': 2}
    CONSTANT_OID = {'level': 1, 'index': 3}
    OWNER = {'level': 1, 'index': 4}
    ROLE = {'level': 1, 'index': 5}
    USER_LABEL = {'level': 1, 'index': 6}
    TOUCHPOINTS = {'level': 1, 'index': 7}
    RUNTIME_PROPERTY_CONSTRAINTS = {'level': 1, 'index': 8}
    UNKNOWN = {'level': 9999, 'index': 9999}

    @classmethod
    def _missing_(cls, _):
        return cls.UNKNOWN


class NcObjectMethods(Enum):
    GENERIC_GET = {'level': 1, 'index': 1}
    GENERIC_SET = {'level': 1, 'index': 2}
    GET_SEQUENCE_ITEM = {'level': 1, 'index': 3}
    SET_SEQUENCE_ITEM = {'level': 1, 'index': 4}
    ADD_SEQUENCE_ITEM = {'level': 1, 'index': 5}
    REMOVE_SEQUENCE_ITEM = {'level': 1, 'index': 6}
    GET_SEQUENCE_LENGTH = {'level': 1, 'index': 7}


class NcObjectEvents(Enum):
    PROPERTY_CHANGED = {'level': 1, 'index': 1}


class NcBlockProperties(Enum):
    ENABLED = {'level': 2, 'index': 1}
    MEMBERS = {'level': 2, 'index': 2}


class NcBlockMethods(Enum):
    GET_MEMBERS_DESCRIPTOR = {'level': 2, 'index': 1}
    FIND_MEMBERS_BY_PATH = {'level': 2, 'index': 2}
    FIND_MEMBERS_BY_ROLE = {'level': 2, 'index': 3}
    FIND_MEMBERS_BY_CLASS_ID = {'level': 2, 'index': 4}


class NcClassManagerProperties(Enum):
    CONTROL_CLASSES = {'level': 3, 'index': 1}
    DATATYPES = {'level': 3, 'index': 2}


class NcClassManagerMethods(Enum):
    GET_CONTROL_CLASS = {'level': 3, 'index': 1}
    GET_DATATYPE = {'level': 3, 'index': 2}


class NcDeviceManagerProperties(Enum):
    NCVERSION = {'level': 3, 'index': 1}


class StandardClassIds(Enum):
    NCOBJECT = [1]
    NCBLOCK = [1, 1]
    NCWORKER = [1, 2]
    NCMANAGER = [1, 3]
    NCDEVICEMANAGER = [1, 3, 1]
    NCCLASSMANAGER = [1, 3, 2]


class IS12Utils(NMOSUtils):
    def __init__(self, url, spec_path, spec_branch):
        NMOSUtils.__init__(self, url)
        self.spec_branch = spec_branch
        self.load_is12_schemas(spec_path)
        self.ROOT_BLOCK_OID = 1
        self.ncp_websocket = None
        self.command_handle = 0
        self.expect_notifications = False
        self.notifications = []

    def load_is12_schemas(self, spec_path):
        """Load datatype and control class decriptors and create datatype JSON schemas"""
        # Load IS-12 schemas
        self.schemas = {}
        schema_names = ["error-message",
                        "command-response-message",
                        "subscription-response-message",
                        "notification-message"]
        for schema_name in schema_names:
            self.schemas[schema_name] = load_resolved_schema(spec_path, schema_name + ".json")

    def open_ncp_websocket(self, test, url):
        """Create a WebSocket client connection to Node under test. Raises NMOSTestException on error"""
        # Reuse socket if connection already established
        if self.ncp_websocket and self.ncp_websocket.is_open():
            return

        # Create a WebSocket connection to NMOS Control Protocol endpoint
        self.ncp_websocket = WebsocketWorker(url)
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

    def validate_is12_schema(self, test, payload, schema_name, context=""):
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
                    self.validate_is12_schema(
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
                            if response["result"]["status"] != NcMethodStatus.OK:
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

    def _execute_command(self, test, oid, method_id, arguments):
        command_JSON = self.create_command_JSON(oid, method_id, arguments)
        response = self.send_command(test, command_JSON)
        return response["result"]

    def get_property(self, test, oid, property_id):
        """Get property from object. Raises NMOSTestException on error"""
        return self._execute_command(test, oid,
                                     NcObjectMethods.GENERIC_GET.value,
                                     {'id': property_id})["value"]

    def set_property(self, test, oid, property_id, argument):
        """Get property from object. Raises NMOSTestException on error"""
        return self._execute_command(test, oid,
                                     NcObjectMethods.GENERIC_SET.value,
                                     {'id': property_id, 'value': argument})

    def get_sequence_item(self, test, oid, property_id, index):
        """Get value from sequence property. Raises NMOSTestException on error"""
        return self._execute_command(test, oid,
                                     NcObjectMethods.GET_SEQUENCE_ITEM.value,
                                     {'id': property_id, 'index': index})["value"]

    def set_sequence_item(self, test, oid, property_id, index, value):
        """Add value to a sequence property. Raises NMOSTestException on error"""
        return self._execute_command(test, oid,
                                     NcObjectMethods.SET_SEQUENCE_ITEM.value,
                                     {'id': property_id, 'index': index, 'value': value})

    def add_sequence_item(self, test, oid, property_id, value):
        """Add value to a sequence property. Raises NMOSTestException on error"""
        return self._execute_command(test, oid,
                                     NcObjectMethods.ADD_SEQUENCE_ITEM.value,
                                     {'id': property_id, 'value': value})

    def remove_sequence_item(self, test, oid, property_id, index):
        """Get value from sequence property. Raises NMOSTestException on error"""
        return self._execute_command(test, oid,
                                     NcObjectMethods.REMOVE_SEQUENCE_ITEM.value,
                                     {'id': property_id, 'index': index})

    def get_sequence_length(self, test, oid, property_id):
        """Get value from sequence property. Raises NMOSTestException on error"""
        return self._execute_command(test, oid,
                                     NcObjectMethods.GET_SEQUENCE_LENGTH.value,
                                     {'id': property_id})["value"]

    def get_member_descriptors(self, test, oid, recurse):
        """Get BlockMemberDescritors for this block. Raises NMOSTestException on error"""
        return self._execute_command(test, oid,
                                     NcBlockMethods.GET_MEMBERS_DESCRIPTOR.value,
                                     {'recurse': recurse})["value"]

    def find_members_by_path(self, test, oid, role_path):
        """Query members based on role path. Raises NMOSTestException on error"""
        return self._execute_command(test, oid,
                                     NcBlockMethods.FIND_MEMBERS_BY_PATH.value,
                                     {'path': role_path})["value"]

    def find_members_by_role(self, test, oid, role, case_sensitive, match_whole_string, recurse):
        """Query members based on role. Raises NMOSTestException on error"""
        return self._execute_command(test, oid,
                                     NcBlockMethods.FIND_MEMBERS_BY_ROLE.value,
                                     {'role': role,
                                      'caseSensitive': case_sensitive,
                                      'matchWholeString': match_whole_string,
                                      'recurse': recurse})["value"]

    def find_members_by_class_id(self, test, oid, class_id, include_derived, recurse):
        """Query members based on class id. Raises NMOSTestException on error"""
        return self._execute_command(test, oid,
                                     NcBlockMethods.FIND_MEMBERS_BY_CLASS_ID.value,
                                     {'classId': class_id,
                                      'includeDerived': include_derived,
                                      'recurse': recurse})["value"]

    def get_control_class(self, test, oid, class_id, include_inherited):
        """Query Class Manager for control class. Raises NMOSTestException on error"""
        return self._execute_command(test, oid,
                                     NcClassManagerMethods.GET_CONTROL_CLASS.value,
                                     {'classId': class_id,
                                      'includeInherited': include_inherited})["value"]

    def get_datatype(self, test, oid, name, include_inherited):
        """Query Class Manager for datatype. Raises NMOSTestException on error"""
        return self._execute_command(test, oid,
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
            json_primitive_type = self._primitive_to_JSON(descriptor['parentType'])
            if json_primitive_type:
                if descriptor['isSequence']:
                    json_schema['type'] = 'array'
                    json_schema['items'] = {'type': json_primitive_type}
                else:
                    json_schema['type'] = json_primitive_type
            else:
                json_schema['allOf'] = []
                json_schema['allOf'].append({'$ref': descriptor['parentType'] + '.json'})

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

    def upcast_parameter_constraint(self, constraint):
        if constraint.get('minimum') or constraint.get('maximum') or constraint.get('step'):
            return NcParameterConstraintsNumber(constraint.get('defaultValue'), constraint.get('minimum'), constraint.get('maximum'), constraint.get('step'))
        
        if constraint.get('maxCharacters') or constraint.get('pattern'):
            return NcParameterConstraintsString(constraint.get('defaultValue'), constraint.get('maxCharacters'), constraint.get('pattern'))
        
        return NcParameterConstraints(constraint.get('defaultValue'))
            

class NcObject():
    def __init__(self, class_id, oid, role):
        self.class_id = class_id
        self.oid = oid
        self.role = role


class NcBlock(NcObject):
    def __init__(self, class_id, oid, role, descriptors):
        NcObject.__init__(self, class_id, oid, role)
        self.child_objects = []
        self.member_descriptors = descriptors

    # Utility Methods
    def add_child_object(self, nc_object):
        self.child_objects.append(nc_object)

    def get_role_paths(self):
        role_paths = []
        for child_object in self.child_objects:
            role_paths.append([child_object.role])
            if type(child_object) is NcBlock:
                child_paths = child_object.get_role_paths()
                for child_path in child_paths:
                    role_path = [child_object.role]
                    role_path += child_path
                    role_paths.append(role_path)
        return role_paths

    def get_oids(self, root=True):
        oids = [self.oid] if root else []
        for child_object in self.child_objects:
            oids.append(child_object.oid)
            if type(child_object) is NcBlock:
                oids += child_object.get_oids(False)
        return oids

    # NcBlock Methods
    def get_member_descriptors(self, recurse=False):
        query_results = []
        query_results += self.member_descriptors
        if recurse:
            for child_object in self.child_objects:
                if type(child_object) is NcBlock:
                    query_results += child_object.get_member_descriptors(recurse)
        return query_results

    def find_members_by_path(self, role_path):
        query_role = role_path[0]
        for child_object in self.child_objects:
            if child_object.role == query_role:
                if len(role_path[1:]) and type(child_object) is NcBlock:
                    return child_object.find_members_by_path(role_path[1:])
                else:
                    return child_object
        return None

    def find_members_by_role(self, role, case_sensitive=False, match_whole_string=False, recurse=False):
        def match(query_role, role, case_sensitive, match_whole_string):
            if case_sensitive:
                return query_role == role if match_whole_string else query_role in role
            return query_role.lower() == role.lower() if match_whole_string else query_role.lower() in role.lower()

        query_results = []
        for child_object in self.child_objects:
            if match(role, child_object.role, case_sensitive, match_whole_string):
                query_results.append(child_object)
            if recurse and type(child_object) is NcBlock:
                query_results += child_object.find_members_by_role(role,
                                                                   case_sensitive,
                                                                   match_whole_string,
                                                                   recurse)
        return query_results

    def find_members_by_class_id(self, class_id, include_derived=False, recurse=False):
        def match(query_class_id, class_id, include_derived):
            if query_class_id == (class_id[:len(query_class_id)] if include_derived else class_id):
                return True
            return False

        query_results = []
        for child_object in self.child_objects:
            if match(class_id, child_object.class_id, include_derived):
                query_results.append(child_object)
            if recurse and type(child_object) is NcBlock:
                query_results += child_object.find_members_by_class_id(class_id,
                                                                       include_derived,
                                                                       recurse)
        return query_results


class NcManager(NcObject):
    def __init__(self, class_id, oid, role):
        NcObject.__init__(self, class_id, oid, role)


class NcClassManager(NcManager):
    def __init__(self, class_id, oid, role, class_descriptors, datatype_descriptors):
        NcObject.__init__(self, class_id, oid, role)
        self.class_descriptors = class_descriptors
        self.datatype_descriptors = datatype_descriptors

    def get_control_class(self, class_id, include_inherited):
        class_id_str = ".".join(map(str, class_id))
        descriptor = self.class_descriptors[class_id_str]

        if not include_inherited:
            return descriptor

        parent_class = class_id[:-1]
        inherited_descriptor = deepcopy(descriptor)

        # add inherited classes
        while len(parent_class) > 0:
            if parent_class[-1] > 0:  # Ignore Authority Keys
                class_id_str = ".".join(map(str, parent_class))
                parent_descriptor = self.class_descriptors[class_id_str]
                inherited_descriptor["properties"] += parent_descriptor["properties"]
                inherited_descriptor["methods"] += parent_descriptor["methods"]
                inherited_descriptor["events"] += parent_descriptor["events"]
            parent_class.pop()

        return inherited_descriptor

    def get_datatype(self, name, include_inherited):
        descriptor = self.datatype_descriptors[name]

        if not include_inherited or descriptor["type"] != NcDatatypeType.Struct:
            return descriptor

        inherited_descriptor = deepcopy(descriptor)

        while descriptor.get("parentType"):
            parent_type = descriptor.get("parentType")
            descriptor = self.datatype_descriptors[parent_type]
            inherited_descriptor["fields"] += descriptor["fields"]

        return inherited_descriptor


class NcParameterConstraints:
    def __init__(self, default_value, constraint_type="NcParameterConstraints"):
        self.constraint_type = constraint_type
        self.default_value = default_value
        

class NcParameterConstraintsNumber:
    def __init__(self, default_value, minimum, maximum, step):
        NcParameterConstraints.__init__(self, default_value, constraint_type="NcParameterConstraintsNumber")
        self.minimum = minimum
        self.maximum = maximum
        self.step = step
        

class NcParameterConstraintsString:
    def __init__(self, default_value, max_characters, pattern):
        NcParameterConstraints.__init__(self, default_value, constraint_type="NcParameterConstraintsString")
        self.max_characters = max_characters
        self.pattern = pattern
