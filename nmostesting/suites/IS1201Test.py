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

import time

from ..Config import WS_MESSAGE_TIMEOUT
from ..GenericTest import NMOSTestException
from ..IS12Utils import IS12Utils

from ..MS05Utils import NcMethodStatus, NcBlockProperties, \
    NcObjectMethods, NcObjectProperties, \
    StandardClassIds, NcBlock, NcDatatypeType, \
    NcPropertyChangeType, NcObjectEvents

from .MS0501Test import MS0501Test


NODE_API_KEY = "node"
CONTROL_API_KEY = "ncp"
MS05_API_KEY = "controlframework"


class IS1201Test(MS0501Test):

    def __init__(self, apis, **kwargs):
        # Remove the RAML key to prevent this test suite from auto-testing IS-04 API
        apis[NODE_API_KEY].pop("raml", None)
        MS0501Test.__init__(self, apis, **kwargs)
        self.node_url = apis[NODE_API_KEY]["url"]
        self.ncp_url = apis[CONTROL_API_KEY]["url"]
        self.is12_utils = IS12Utils(apis)
        self.set_utils(self.is12_utils)
        self.is12_utils.load_reference_resources()
#        self.ms0501Test = MS0501Test(apis, self.is12_utils)

    def set_up_tests(self):
        super().set_up_tests()
        self.datatype_schemas = None
        self.unique_roles_error = False
        self.unique_oids_error = False
        self.managers_are_singletons_error = False
        self.managers_members_root_block_error = False
        self.device_model_metadata = {"checked": False, "error": False, "error_msg": ""}
        self.organization_metadata = {"checked": False, "error": False, "error_msg": ""}
        self.touchpoints_metadata = {"checked": False, "error": False, "error_msg": ""}
        self.deprecated_property_metadata = {"checked": False, "error": False, "error_msg": ""}
        self.get_sequence_item_metadata = {"checked": False, "error": False, "error_msg": ""}
        self.get_sequence_length_metadata = {"checked": False, "error": False, "error_msg": ""}
        self.validate_runtime_constraints_metadata = {"checked": False, "error": False, "error_msg": ""}
        self.validate_property_constraints_metadata = {"checked": False, "error": False, "error_msg": ""}
        self.validate_datatype_constraints_metadata = {"checked": False, "error": False, "error_msg": ""}
        self.check_constraints_hierarchy = {"checked": False, "error": False, "error_msg": ""}

        self.oid_cache = []

    def tear_down_tests(self):
        # Clean up Websocket resources
        self.is12_utils.close_ncp_websocket()

    def test_01(self, test):
        """Control Endpoint: Node under test advertises IS-12 control endpoint matching API under test"""
        # https://specs.amwa.tv/is-12/releases/v1.0.0/docs/IS-04_interactions.html

        control_type = "urn:x-nmos:control:ncp/" + self.apis[CONTROL_API_KEY]["version"]
        return self.is12_utils.do_test_device_control(
            test,
            self.node_url,
            control_type,
            self.ncp_url,
            self.authorization
        )

    def test_02(self, test):
        """WebSocket: endpoint successfully opened"""
        # https://specs.amwa.tv/is-12/releases/v1.0.0/docs/Transport_and_message_encoding.html

        self.is12_utils.open_ncp_websocket(test)

        return test.PASS()

    def test_03(self, test):
        """WebSocket: socket is kept open until client closes"""
        # https://specs.amwa.tv/is-12/releases/v1.0.0/docs/Protocol_messaging.html#control-session

        self.is12_utils.open_ncp_websocket(test)

        # Ensure WebSocket remains open
        start_time = time.time()
        while time.time() < start_time + WS_MESSAGE_TIMEOUT:
            if not self.is12_utils.ncp_websocket.is_open():
                return test.FAIL("Node failed to keep WebSocket open")
            time.sleep(0.2)

        return test.PASS()

    def do_error_test(self, test, command_json, expected_status=None):
        """Execute command with expected error status."""
        # when expected_status = None checking of the status code is skipped
        # check the syntax of the error message according to is12_error

        try:
            self.is12_utils.open_ncp_websocket(test)

            self.is12_utils.send_command(test, command_json)

            return test.FAIL("Error not handled.",
                             "https://specs.amwa.tv/is-12/branches/{}"
                             "/docs/Protocol_messaging.html#error-messages"
                             .format(self.apis[CONTROL_API_KEY]["spec_branch"]))

        except NMOSTestException as e:
            error_msg = e.args[0].detail

            # Expecting an error status dictionary
            if not isinstance(error_msg, dict):
                # It must be some other type of error so re-throw
                raise e

            if not error_msg.get('status'):
                return test.FAIL("Command error: " + str(error_msg))

            if error_msg['status'] == NcMethodStatus.OK:
                return test.FAIL("Error not handled. Expected: " + expected_status.name
                                 + " (" + str(expected_status) + ")"
                                 + ", actual: " + NcMethodStatus(error_msg['status']).name
                                 + " (" + str(error_msg['status']) + ")",
                                 "https://specs.amwa.tv/is-12/branches/{}"
                                 "/docs/Protocol_messaging.html#error-messages"
                                 .format(self.apis[CONTROL_API_KEY]["spec_branch"]))

            if expected_status and error_msg['status'] != expected_status:
                return test.WARNING("Unexpected status. Expected: " + expected_status.name
                                    + " (" + str(expected_status) + ")"
                                    + ", actual: " + NcMethodStatus(error_msg['status']).name
                                    + " (" + str(error_msg['status']) + ")",
                                    "https://specs.amwa.tv/ms-05-02/branches/{}"
                                    "/docs/Framework.html#ncmethodresult"
                                    .format(self.apis[CONTROL_API_KEY]["spec_branch"]))

            return test.PASS()

    def test_24(self, test):
        """IS-12 Protocol Error: Node handles command handle that is not in range 1 to 65535"""
        # Error messages MUST be used by devices to return general error messages when more specific
        # responses cannot be returned
        # https://specs.amwa.tv/is-12/releases/v1.0.0/docs/Protocol_messaging.html#error-messages

        command_json = self.is12_utils.create_command_JSON(self.is12_utils.ROOT_BLOCK_OID,
                                                           NcObjectMethods.GENERIC_GET.value,
                                                           {'id': NcObjectProperties.OID.value})

        # Handle should be between 1 and 65535
        illegal_command_handle = 999999999
        command_json['commands'][0]['handle'] = illegal_command_handle

        return self.do_error_test(test, command_json)

    def test_25(self, test):
        """IS-12 Protocol Error: Node handles command handle that is not a number"""
        # Error messages MUST be used by devices to return general error messages when more specific
        # responses cannot be returned
        # https://specs.amwa.tv/is-12/releases/v1.0.0/docs/Protocol_messaging.html#error-messages

        command_json = self.is12_utils.create_command_JSON(self.is12_utils.ROOT_BLOCK_OID,
                                                           NcObjectMethods.GENERIC_GET.value,
                                                           {'id': NcObjectProperties.OID.value})

        # Use invalid handle
        invalid_command_handle = "NOT A HANDLE"
        command_json['commands'][0]['handle'] = invalid_command_handle

        return self.do_error_test(test, command_json)

    def test_26(self, test):
        """IS-12 Protocol Error: Node handles invalid command type"""
        # Error messages MUST be used by devices to return general error messages when more specific
        # responses cannot be returned
        # https://specs.amwa.tv/is-12/releases/v1.0.0/docs/Protocol_messaging.html#error-messages

        command_json = \
            self.is12_utils.create_command_JSON(self.is12_utils.ROOT_BLOCK_OID,
                                                NcObjectMethods.GENERIC_GET.value,
                                                {'id': NcObjectProperties.OID.value})
        # Use invalid message type
        command_json['messageType'] = 7

        return self.do_error_test(test, command_json)

    def test_27(self, test):
        """IS-12 Protocol Error: Node handles invalid JSON"""
        # Error messages MUST be used by devices to return general error messages when more specific
        # responses cannot be returned
        # https://specs.amwa.tv/is-12/releases/v1.0.0/docs/Protocol_messaging.html#error-messages

        # Use invalid JSON
        command_json = {'not_a': 'valid_command'}

        return self.do_error_test(test, command_json)

    def test_28(self, test):
        """MS-05-02 Error: Node handles oid of object not found in Device Model"""
        # Referencing the Google sheet
        # MS-05-02 (15) Devices MUST use the exact status code from NcMethodStatus when errors are encountered
        # for the following scenarios...

        device_model = self.is12_utils.query_device_model(test)
        # Calculate invalid oid from the max oid value in device model
        oids = device_model.get_oids()
        invalid_oid = max(oids) + 1

        command_json = \
            self.is12_utils.create_command_JSON(invalid_oid,
                                                NcObjectMethods.GENERIC_GET.value,
                                                {'id': NcObjectProperties.OID.value})

        return self.do_error_test(test,
                                  command_json,
                                  expected_status=NcMethodStatus.BadOid)

    def test_29(self, test):
        """MS-05-02 Error: Node handles invalid property identifier"""
        # Devices MUST use the exact status code from NcMethodStatus when errors are encountered
        # for the following scenarios...
        # https://specs.amwa.tv/ms-05-02/releases/v1.0.0/docs/Framework.html#ncmethodresult

        # Use invalid property id
        invalid_property_identifier = {'level': 1, 'index': 999}
        command_json = \
            self.is12_utils.create_command_JSON(self.is12_utils.ROOT_BLOCK_OID,
                                                NcObjectMethods.GENERIC_GET.value,
                                                {'id': invalid_property_identifier})
        return self.do_error_test(test,
                                  command_json,
                                  expected_status=NcMethodStatus.PropertyNotImplemented)

    def test_30(self, test):
        """MS-05-02 Error: Node handles invalid method identifier"""
        # Devices MUST use the exact status code from NcMethodStatus when errors are encountered
        # for the following scenarios...
        # https://specs.amwa.tv/ms-05-02/releases/v1.0.0/docs/Framework.html#ncmethodresult

        command_json = \
            self.is12_utils.create_command_JSON(self.is12_utils.ROOT_BLOCK_OID,
                                                NcObjectMethods.GENERIC_GET.value,
                                                {'id': NcObjectProperties.OID.value})

        # Use invalid method id
        invalid_method_id = {'level': 1, 'index': 999}
        command_json['commands'][0]['methodId'] = invalid_method_id

        return self.do_error_test(test,
                                  command_json,
                                  expected_status=NcMethodStatus.MethodNotImplemented)

    def test_31(self, test):
        """MS-05-02 Error: Node handles read only error"""
        # Devices MUST use the exact status code from NcMethodStatus when errors are encountered
        # for the following scenarios...
        # https://specs.amwa.tv/ms-05-02/releases/v1.0.0/docs/Framework.html#ncmethodresult

        command_json = \
            self.is12_utils.create_command_JSON(self.is12_utils.ROOT_BLOCK_OID,
                                                NcObjectMethods.GENERIC_SET.value,
                                                {'id': NcObjectProperties.ROLE.value,
                                                 'value': "ROLE IS READ ONLY"})

        return self.do_error_test(test,
                                  command_json,
                                  expected_status=NcMethodStatus.Readonly)

    def test_32(self, test):
        """MS-05-02 Error: Node handles GetSequence index out of bounds error"""
        # Devices MUST use the exact status code from NcMethodStatus when errors are encountered
        # for the following scenarios...
        # https://specs.amwa.tv/ms-05-02/releases/v1.0.0/docs/Framework.html#ncmethodresult

        self.is12_utils.open_ncp_websocket(test)

        length = self.is12_utils.get_sequence_length(test,
                                                     NcBlockProperties.MEMBERS.value,
                                                     oid=self.is12_utils.ROOT_BLOCK_OID)
        out_of_bounds_index = length + 10

        command_json = \
            self.is12_utils.create_command_JSON(self.is12_utils.ROOT_BLOCK_OID,
                                                NcObjectMethods.GET_SEQUENCE_ITEM.value,
                                                {'id': NcBlockProperties.MEMBERS.value,
                                                 'index': out_of_bounds_index})
        return self.do_error_test(test,
                                  command_json,
                                  expected_status=NcMethodStatus.IndexOutOfBounds)

    def test_33(self, test):
        """Node implements subscription and notification mechanism"""
        # https://specs.amwa.tv/ms-05-02/releases/v1.0.0/docs/NcObject.html#propertychanged-event
        # https://specs.amwa.tv/is-12/releases/v1.0.0/docs/Protocol_messaging.html#notification-message-type
        # https://specs.amwa.tv/is-12/releases/v1.0.0/docs/Protocol_messaging.html#subscription-message-type
        # https://specs.amwa.tv/is-12/releases/v1.0.0/docs/Protocol_messaging.html#subscription-response-message-type

        device_model = self.is12_utils.query_device_model(test)

        # Get all oids for objects in this Device Model
        device_model_objects = device_model.find_members_by_class_id(class_id=StandardClassIds.NCOBJECT.value,
                                                                     include_derived=True,
                                                                     recurse=True)

        oids = dict.fromkeys([self.is12_utils.ROOT_BLOCK_OID] + [o.oid for o in device_model_objects], 0)

        self.is12_utils.update_subscritions(test, list(oids.keys()))

        error = False
        error_message = ""

        for oid in oids.keys():
            new_user_label = "NMOS Testing Tool " + str(oid)
            old_user_label = self.is12_utils.get_property_value(test, NcObjectProperties.USER_LABEL.value, oid=oid)

            context = "oid: " + str(oid) + ", "

            # Each label will be set twice; once to the new user label, and then again back to the old user label
            for label in [new_user_label, old_user_label]:
                # Set property and log notificaiton
                self.is12_utils.start_logging_notifications()
                self.is12_utils.set_property(test, NcObjectProperties.USER_LABEL.value, label, oid=oid)
                self.is12_utils.stop_logging_notifications()

                for notification in self.is12_utils.get_notifications():
                    if notification['oid'] == oid:

                        if notification['eventId'] != NcObjectEvents.PROPERTY_CHANGED.value:
                            error = True
                            error_message += context + "Unexpected event type: " + str(notification['eventId']) + ", "

                        if notification["eventData"]["propertyId"] != NcObjectProperties.USER_LABEL.value:
                            continue

                        if notification["eventData"]["changeType"] != NcPropertyChangeType.ValueChanged.value:
                            error = True
                            error_message += context + "Unexpected change type: " \
                                + str(NcPropertyChangeType(notification["eventData"]["changeType"]).name) + ", "

                        if notification["eventData"]["value"] != label:
                            error = True
                            error_message += context + "Unexpected value: " \
                                + str(notification["eventData"]["value"]) + ", "

                        if notification["eventData"]["sequenceItemIndex"] is not None:
                            error = True
                            error_message += context + "Unexpected sequence item index: " \
                                + str(notification["eventData"]["sequenceItemIndex"]) + ", "

                        oids[oid] += 1

        # We expect each object to have 2 notifications (set to new user label, set to old user label)
        if not all(v == 2 for v in oids.values()):
            error = True
            error_message += "Notifications not received for Oids " \
                + str(sorted([i for i, v in oids.items() if v != 2]))
        elif not any(v == 2 for v in oids.values()):
            error = True
            error_message += "No notifications received"

        if error:
            return test.FAIL(error_message)
        return test.PASS()

    def check_constraint(self, test, constraint, type_name, is_sequence, test_metadata, context):
        if constraint.get("defaultValue"):
            datatype_schema = self.get_datatype_schema(test, type_name)
            if isinstance(constraint.get("defaultValue"), list) is not is_sequence:
                test_metadata["error"] = True
                test_metadata["error_msg"] = context + (" a default value sequence was expected"
                                                        if is_sequence else " unexpected default value sequence.")
                return
            if is_sequence:
                for value in constraint.get("defaultValue"):
                    self.is12_utils.validate_schema(test, value, datatype_schema, context + ": defaultValue ")
            else:
                self.is12_utils.validate_schema(
                    test,
                    constraint.get("defaultValue"),
                    datatype_schema,
                    context + ": defaultValue ")

        datatype = self.is12_utils.resolve_datatype(test, type_name)
        # check NcXXXConstraintsNumber
        if constraint.get("minimum") or constraint.get("maximum") or constraint.get("step"):
            constraint_type = "NcPropertyConstraintsNumber" \
                if constraint.get("propertyId") else "NcParameterConstraintsNumber"
            if datatype not in ["NcInt16", "NcInt32", "NcInt64", "NcUint16", "NcUint32",
                                "NcUint64", "NcFloat32", "NcFloat64"]:
                test_metadata["error"] = True
                test_metadata["error_msg"] = context + ". " + datatype + \
                    " can not be constrainted by " + constraint_type + "."
        # check NcXXXConstraintsString
        if constraint.get("maxCharacters") or constraint.get("pattern"):
            constraint_type = "NcPropertyConstraintsString" \
                if constraint.get("propertyId") else "NcParameterConstraintsString"
            if datatype not in ["NcString"]:
                test_metadata["error"] = True
                test_metadata["error_msg"] = context + ". " + datatype + \
                    " can not be constrainted by " + constraint_type + "."

    def do_validate_runtime_constraints_test(self, test, nc_object, class_manager, context=""):
        if nc_object.runtime_constraints:
            self.validate_runtime_constraints_metadata["checked"] = True
            for constraint in nc_object.runtime_constraints:
                class_descriptor = class_manager.class_descriptors[".".join(map(str, nc_object.class_id))]
                for class_property in class_descriptor["properties"]:
                    if class_property["id"] == constraint["propertyId"]:
                        message_root = context + nc_object.role + ": " + class_property["name"] + \
                            ": " + class_property.get("typeName")
                        self.check_constraint(test,
                                              constraint,
                                              class_property.get("typeName"),
                                              class_property["isSequence"],
                                              self.validate_runtime_constraints_metadata,
                                              message_root)

        # Recurse through the child blocks
        if type(nc_object) is NcBlock:
            for child_object in nc_object.child_objects:
                self.do_validate_runtime_constraints_test(test,
                                                          child_object,
                                                          class_manager,
                                                          context + nc_object.role + ": ")

    def test_34(self, test):
        """Constraints: validate runtime constraints"""

        device_model = self.is12_utils.query_device_model(test)
        class_manager = self.is12_utils.get_class_manager(test)

        self.do_validate_runtime_constraints_test(test, device_model, class_manager)

        if self.validate_runtime_constraints_metadata["error"]:
            return test.FAIL(self.validate_runtime_constraints_metadata["error_msg"])

        if not self.validate_runtime_constraints_metadata["checked"]:
            return test.UNCLEAR("No runtime constraints found.")

        return test.PASS()

    def do_validate_property_constraints_test(self, test, nc_object, class_manager, context=""):
        class_descriptor = class_manager.class_descriptors[".".join(map(str, nc_object.class_id))]

        for class_property in class_descriptor["properties"]:
            if class_property["constraints"]:
                self.validate_property_constraints_metadata["checked"] = True
                message_root = context + nc_object.role + ": " + class_property["name"] + \
                    ": " + class_property.get("typeName")
                self.check_constraint(test,
                                      class_property["constraints"],
                                      class_property.get("typeName"),
                                      class_property["isSequence"],
                                      self.validate_property_constraints_metadata,
                                      message_root)
        # Recurse through the child blocks
        if type(nc_object) is NcBlock:
            for child_object in nc_object.child_objects:
                self.do_validate_property_constraints_test(test,
                                                           child_object,
                                                           class_manager,
                                                           context + nc_object.role + ": ")

    def test_35(self, test):
        """Constraints: validate property constraints"""

        device_model = self.is12_utils.query_device_model(test)
        class_manager = self.is12_utils.get_class_manager(test)

        self.do_validate_property_constraints_test(test, device_model, class_manager)

        if self.validate_property_constraints_metadata["error"]:
            return test.FAIL(self.validate_property_constraints_metadata["error_msg"])

        if not self.validate_property_constraints_metadata["checked"]:
            return test.UNCLEAR("No property constraints found.")

        return test.PASS()

    def do_validate_datatype_constraints_test(self, test, datatype, type_name, context=""):
        if datatype.get("constraints"):
            self.validate_datatype_constraints_metadata["checked"] = True
            self.check_constraint(test,
                                  datatype.get("constraints"),
                                  type_name,
                                  datatype.get("isSequence", False),
                                  self.validate_datatype_constraints_metadata,
                                  context + ": " + type_name)
        if datatype.get("type") == NcDatatypeType.Struct.value:
            for field in datatype.get("fields"):
                self.do_validate_datatype_constraints_test(test,
                                                           field,
                                                           field["typeName"],
                                                           context + ": " + type_name + ": " + field["name"])

    def test_36(self, test):
        """Constraints: validate datatype constraints"""

        class_manager = self.is12_utils.get_class_manager(test)

        for _, datatype in class_manager.datatype_descriptors.items():
            self.do_validate_datatype_constraints_test(test, datatype, datatype["name"])

        if self.validate_datatype_constraints_metadata["error"]:
            return test.FAIL(self.validate_datatype_constraints_metadata["error_msg"])

        if not self.validate_datatype_constraints_metadata["checked"]:
            return test.UNCLEAR("No datatype constraints found.")

        return test.PASS()

    def _xor_constraint(self, left, right):
        return bool(left is not None) ^ bool(right is not None)

    def _check_constraint_override(self, test, constraint, override_constraint, context):
        # Is this a number constraint
        if 'minimum' in constraint or 'maximum' in constraint or 'step' in constraint:
            self.check_constraints_hierarchy["checked"] = True

            if self._xor_constraint(constraint.get('minimum'), override_constraint.get('minimum')) \
                    or self._xor_constraint(constraint.get('maximum'), override_constraint.get('maximum')) \
                    or self._xor_constraint(constraint.get('step'), override_constraint.get('step')):
                raise NMOSTestException(
                    test.FAIL(context + "Constraints implementations MUST fully override the previous level: "
                              + "constraint: " + str(constraint) + ", override_constraint: "
                              + str(override_constraint)))
            if constraint.get('minimum') and override_constraint.get('minimum') < constraint.get('minimum'):
                raise NMOSTestException(
                    test.FAIL(context + "Constraints implementations MUST not result in widening "
                              + "the constraints defined in previous levels: "
                              + "minimum constraint: " + str(constraint.get('minimum'))
                              + ", override minimum constraint: " + str(override_constraint.get('minimum'))))
            if constraint.get('maximum') and override_constraint.get('maximum') > constraint.get('maximum'):
                raise NMOSTestException(
                    test.FAIL(context + "Constraints implementations MUST not result in widening "
                              + "the constraints defined in previous levels: "
                              + "maximum constraint: " + str(constraint.get('maximum'))
                              + ", override maximum constraint: " + str(override_constraint.get('maximum'))))
            if constraint.get('step') and override_constraint.get('step') < constraint.get('step'):
                raise NMOSTestException(
                    test.FAIL(context + "Constraints implementations MUST not result in widening "
                              + "the constraints defined in previous levels: "
                              + "step constraint: " + str(constraint.get('step'))
                              + ", override step constraint: " + str(override_constraint.get('step'))))

        # is this a string constraint
        if 'maxCharacters' in constraint or 'pattern' in constraint:
            self.check_constraints_hierarchy["checked"] = True

            if self._xor_constraint(constraint.get('maxCharacters'), override_constraint.get('maxCharacters')) \
                    or self._xor_constraint(constraint.get('pattern'), override_constraint.get('pattern')):
                raise NMOSTestException(
                    test.FAIL(context + "Constraints implementations MUST fully override the previous level: "
                              + "constraint: " + str(constraint) + ", override_constraint: "
                              + str(override_constraint)))
            if constraint.get('maxCharacters') \
                    and override_constraint.get('maxCharacters') > constraint.get('maxCharacters'):
                raise NMOSTestException(
                    test.FAIL(context + "Constraints implementations MUST not result in widening "
                              + "the constraints defined in previous levels: "
                              + "maxCharacters constraint: " + str(constraint.get('maxCharacters'))
                              + ", override maxCharacters constraint: "
                              + str(override_constraint.get('maxCharacters'))))
            # Hmm, difficult to determine whether an overridden regex pattern is widening the constraint
            # so rule of thumb here is that a shorter pattern is less constraining that a longer pattern
            if constraint.get('pattern') and len(override_constraint.get('pattern')) < len(constraint.get('pattern')):
                raise NMOSTestException(
                    test.FAIL(context + "Constraints implementations MUST not result in widening "
                              + "the constraints defined in previous levels: "
                              + "pattern constraint: " + str(constraint.get('pattern'))
                              + ", override pattern constraint: " + str(override_constraint.get('pattern'))))

    def _check_constraints_hierarchy(self, test, class_property, datatype_descriptors, object_runtime_constraints,
                                     context):
        datatype_constraints = None
        runtime_constraints = None
        # Level 0: Datatype constraints
        if class_property.get('typeName'):
            datatype_constraints = datatype_descriptors.get(class_property['typeName']).get('constraints')
        # Level 1: Property constraints
        property_constraints = class_property.get('constraints')
        # Level 3: Runtime constraints
        if object_runtime_constraints:
            for object_runtime_constraint in object_runtime_constraints:
                if object_runtime_constraint['propertyId']['level'] == class_property['id']['level'] and \
                        object_runtime_constraint['propertyId']['index'] == class_property['id']['index']:
                    runtime_constraints = object_runtime_constraint

        if datatype_constraints and property_constraints:
            self._check_constraint_override(test, datatype_constraints, property_constraints,
                                            context + "datatype constraints overridden by property constraints: ")

        if datatype_constraints and runtime_constraints:
            self._check_constraint_override(test, datatype_constraints, runtime_constraints,
                                            context + "datatype constraints overridden by runtime constraints: ")

        if property_constraints and runtime_constraints:
            self._check_constraint_override(test, property_constraints, runtime_constraints,
                                            context + "property constraints overridden by runtime constraints: ")

    def _check_constraints(self, test, block, context=""):
        context += block.role

        class_manager = self.is12_utils.get_class_manager(test)

        block_member_descriptors = self.is12_utils.get_member_descriptors(test, recurse=False,
                                                                          oid=block.oid, role_path=block.role_path)

        for descriptor in block_member_descriptors:
            class_descriptor = self.is12_utils.get_control_class(test,
                                                                 class_manager.oid,
                                                                 descriptor['classId'],
                                                                 include_inherited=True)

            # Get runtime property constraints
            # will set error on device_model_metadata on failure
            role_path = block.role_path.copy()
            role_path.append(descriptor['role'])
            object_runtime_constraints = \
                self.get_property_value(test,
                                        NcObjectProperties.RUNTIME_PROPERTY_CONSTRAINTS.value,
                                        context,
                                        oid=descriptor['oid'],
                                        role_path=role_path)

            for class_property in class_descriptor.get('properties'):
                if class_property['isReadOnly']:
                    continue
                try:
                    self._check_constraints_hierarchy(test, class_property, class_manager.datatype_descriptors,
                                                      object_runtime_constraints,
                                                      context + ": " + class_descriptor['name'] + ": "
                                                      + class_property['name'] + ": ")
                except NMOSTestException as e:
                    self.check_constraints_hierarchy["error"] = True
                    self.check_constraints_hierarchy["error_msg"] += str(e.args[0].detail) + "; "

        # Recurse through the child blocks
        for child_object in block.child_objects:
            if type(child_object) is NcBlock:
                self._check_constraints(test, child_object, context + ": ")

    def test_37(self, test):
        """Constraints: check constraints hierarchy"""

        # When using multiple levels of constraints implementations MUST fully override the previous level
        # and this MUST not result in widening the constraints defined in previous levels
        # https://specs.amwa.tv/ms-05-02/branches/v1.0.x/docs/Constraints.html

        device_model = self.is12_utils.query_device_model(test)

        self._check_constraints(test, device_model)

        if self.device_model_metadata["error"]:
            return test.FAIL(self.device_model_metadata["error_msg"])

        if self.check_constraints_hierarchy["error"]:
            return test.FAIL(self.check_constraints_hierarchy["error_msg"],
                             "https://specs.amwa.tv/ms-05-02/branches/v1.0.x/docs/Constraints.html")

        if not self.check_constraints_hierarchy["checked"]:
            return test.UNCLEAR("No constraints hierarchy found.")

        return test.PASS()
