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
import time

from enum import IntEnum
from itertools import takewhile, dropwhile
from jsonschema import FormatChecker, SchemaError, validate, ValidationError
from .Config import WS_MESSAGE_TIMEOUT
from .GenericTest import NMOSTestException
from .TestHelper import WebsocketWorker, load_resolved_schema
from .MS05Utils import NcMethodStatus, NcObjectMethods, NcBlockMethods, NcClassManagerMethods, StandardClassIds

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
        self.ncp_websocket = None
        self.command_handle = 0
        self.expect_notifications = False
        self.notifications = []

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

    def get_property_value_polymorphic(self, test, property_id, oid, **kwargs):
        return self.get_property_value(test, oid, property_id)

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

    def resolve_datatype(self, test, datatype):
        """Resolve datatype to its base type"""
        class_manager = self.get_class_manager(test)
        if class_manager.datatype_descriptors[datatype].get("parentType"):
            return self.resolve_datatype(test, class_manager.datatype_descriptors[datatype].get("parentType"))
        return datatype
