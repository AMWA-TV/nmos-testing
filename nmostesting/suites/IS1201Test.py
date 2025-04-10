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
from ..IS12Utils import IS12Utils, IS12Error
from ..MS05Utils import NcMethodResult, NcMethodResultError, NcMethodStatus, NcObjectMethods, NcObjectEvents, \
    NcObjectProperties, StandardClassIds, NcPropertyChangeType

from .MS0501Test import MS0501Test

NODE_API_KEY = "node"
CONTROL_API_KEY = "ncp"
MS05_API_KEY = "controlframework"


class IS1201Test(MS0501Test):
    """
    Runs Tests covering MS-05 and IS-12
    """
    def __init__(self, apis, **kwargs):
        self.is12_utils = IS12Utils(apis)
        MS0501Test.__init__(self, apis, self.is12_utils, **kwargs)
        self.node_url = apis[NODE_API_KEY]["url"]
        self.ncp_url = apis[CONTROL_API_KEY]["url"]

    def set_up_tests(self):
        self.is12_utils.open_ncp_websocket()
        super().set_up_tests()

    def tear_down_tests(self):
        # Clean up Websocket resources
        self.is12_utils.close_ncp_websocket()

    def test_01(self, test):
        """Control Endpoint: Node under test advertises IS-12 control endpoint matching API under test"""
        # https://specs.amwa.tv/is-12/releases/v1.0.0/docs/IS-04_interactions.html

        control_type = f"urn:x-nmos:control:ncp/{self.apis[CONTROL_API_KEY]['version']}"
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

        return test.PASS()

    def test_03(self, test):
        """WebSocket: socket is kept open until client closes"""
        # https://specs.amwa.tv/is-12/releases/v1.0.0/docs/Protocol_messaging.html#control-session

        # Ensure WebSocket remains open
        start_time = time.time()
        while time.time() < start_time + WS_MESSAGE_TIMEOUT:
            if not self.is12_utils.ncp_websocket.is_open():
                return test.FAIL("Node failed to keep WebSocket open",
                                 f"https://specs.amwa.tv/is-12/branches/{self.apis[CONTROL_API_KEY]['spec_branch']}"
                                 "/docs/Protocol_messaging.html#control-session")
            time.sleep(0.2)

        return test.PASS()

    def _do_is12_error_test(self, test, command_json):
        """Execute command with expected error status."""
        # check the syntax of the error message according to is12_error

        try:
            self.is12_utils.send_command(test, command_json)

            return test.FAIL("Error not handled.",
                             f"https://specs.amwa.tv/is-12/branches/{self.apis[CONTROL_API_KEY]['spec_branch']}"
                             "/docs/Protocol_messaging.html#error-messages")

        except NMOSTestException as e:
            # Expecting an error status dictionary
            if len(e.args) < 2:
                # It must be some other type of error so re-throw
                raise e

            error_msg = e.args[1]  # IS12Error is apended on failure of IS12 command (see IS12Utils::send_command)

            if not isinstance(error_msg, IS12Error):
                # It must be some other type of error so re-throw
                raise e

            if error_msg.status is None:
                return test.FAIL(f"Command error: {str(error_msg)}",
                                 f"https://specs.amwa.tv/is-12/branches/{self.apis[CONTROL_API_KEY]['spec_branch']}"
                                 "/docs/Protocol_messaging.html#command-response-message-type")
            if error_msg.status == NcMethodStatus.OK:
                return test.FAIL("Expected error status, Actual status OK.",
                                 f"https://specs.amwa.tv/is-12/branches/{self.apis[CONTROL_API_KEY]['spec_branch']}"
                                 "/docs/Protocol_messaging.html#error-messages")

            return test.PASS()

    def test_04(self, test):
        """IS-12 Protocol Error: Node handles command handle that is not in range 1 to 65535"""
        # Error messages MUST be used by devices to return general error messages when more specific
        # responses cannot be returned
        # https://specs.amwa.tv/is-12/releases/v1.0.0/docs/Protocol_messaging.html#error-messages

        command_json = self.is12_utils.create_command_JSON(self.is12_utils.ROOT_BLOCK_OID,
                                                           NcObjectMethods.GENERIC_GET.value,
                                                           {"id": NcObjectProperties.OID.value.__dict__})

        # Handle should be between 1 and 65535
        illegal_command_handle = 999999999
        command_json["commands"][0]["handle"] = illegal_command_handle

        return self._do_is12_error_test(test, command_json)

    def test_05(self, test):
        """IS-12 Protocol Error: Node handles command handle that is not a number"""
        # Error messages MUST be used by devices to return general error messages when more specific
        # responses cannot be returned
        # https://specs.amwa.tv/is-12/releases/v1.0.0/docs/Protocol_messaging.html#error-messages

        command_json = self.is12_utils.create_command_JSON(self.is12_utils.ROOT_BLOCK_OID,
                                                           NcObjectMethods.GENERIC_GET.value,
                                                           {"id": NcObjectProperties.OID.value.__dict__})

        # Use invalid handle
        invalid_command_handle = "NOT A HANDLE"
        command_json["commands"][0]["handle"] = invalid_command_handle

        return self._do_is12_error_test(test, command_json)

    def test_06(self, test):
        """IS-12 Protocol Error: Node handles invalid command type"""
        # Error messages MUST be used by devices to return general error messages when more specific
        # responses cannot be returned
        # https://specs.amwa.tv/is-12/releases/v1.0.0/docs/Protocol_messaging.html#error-messages

        command_json = \
            self.is12_utils.create_command_JSON(self.is12_utils.ROOT_BLOCK_OID,
                                                NcObjectMethods.GENERIC_GET.value,
                                                {"id": NcObjectProperties.OID.value.__dict__})
        # Use invalid message type
        command_json["messageType"] = 7

        return self._do_is12_error_test(test, command_json)

    def test_07(self, test):
        """IS-12 Protocol Error: Node handles invalid JSON"""
        # Error messages MUST be used by devices to return general error messages when more specific
        # responses cannot be returned
        # https://specs.amwa.tv/is-12/releases/v1.0.0/docs/Protocol_messaging.html#error-messages

        # Use invalid JSON
        command_json = {"not_a": "valid_command"}

        return self._do_is12_error_test(test, command_json)

    def _do_ms05_error_test(self, test, command_json, expected_status):
        """Execute command with expected error status."""
        # when expected_status = None checking of the status code is skipped
        # check the syntax of the error message according to is12_error

        response = self.is12_utils.send_command(test, command_json)

        self.ms05_utils.reference_datatype_schema_validate(test, response.result, NcMethodResult.__name__)
        method_result = NcMethodResult.factory(response.result)

        if not isinstance(method_result, NcMethodResultError):
            return test.FAIL("Error not handled.",
                             f"https://specs.amwa.tv/is-12/branches/{self.apis[CONTROL_API_KEY]['spec_branch']}"
                             "/docs/Protocol_messaging.html#error-messages")

        if method_result.status == NcMethodStatus.OK:
            return test.FAIL(f"Error not handled. Expected: {expected_status.name}"
                             f" ({str(expected_status)}), "
                             f"actual: {method_result.status.name} "
                             f"({str(method_result.status)})",
                             f"https://specs.amwa.tv/is-12/branches/{self.apis[CONTROL_API_KEY]['spec_branch']}"
                             "/docs/Protocol_messaging.html#error-messages")

        if expected_status and method_result.status != expected_status:
            return test.WARNING(f"Unexpected status. Expected: {expected_status.name} "
                                f"({str(expected_status)}), "
                                f"actual: {NcMethodStatus(method_result.status).name} "
                                f"({str(method_result.status)})",
                                f"https://specs.amwa.tv/ms-05-02/branches/{self.apis[MS05_API_KEY]['spec_branch']}"
                                "/docs/Framework.html#ncmethodresult")

        return test.PASS()

    def test_08(self, test):
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
                                                {"id": NcObjectProperties.OID.value.__dict__})

        return self._do_ms05_error_test(test,
                                        command_json,
                                        expected_status=NcMethodStatus.BadOid)

    def test_09(self, test):
        """MS-05-02 Error: Node handles invalid property identifier"""
        # Devices MUST use the exact status code from NcMethodStatus when errors are encountered
        # for the following scenarios...
        # https://specs.amwa.tv/ms-05-02/releases/v1.0.0/docs/Framework.html#ncmethodresult

        # Use invalid property id
        invalid_property_identifier = {"level": 1, "index": 999}
        command_json = \
            self.is12_utils.create_command_JSON(self.is12_utils.ROOT_BLOCK_OID,
                                                NcObjectMethods.GENERIC_GET.value,
                                                {"id": invalid_property_identifier})
        return self._do_ms05_error_test(test,
                                        command_json,
                                        expected_status=NcMethodStatus.PropertyNotImplemented)

    def test_10(self, test):
        """MS-05-02 Error: Node handles invalid method identifier"""
        # Devices MUST use the exact status code from NcMethodStatus when errors are encountered
        # for the following scenarios...
        # https://specs.amwa.tv/ms-05-02/releases/v1.0.0/docs/Framework.html#ncmethodresult

        command_json = \
            self.is12_utils.create_command_JSON(self.is12_utils.ROOT_BLOCK_OID,
                                                NcObjectMethods.GENERIC_GET.value,
                                                {"id": NcObjectProperties.OID.value.__dict__})

        # Use invalid method id
        invalid_method_id = {"level": 1, "index": 999}
        command_json["commands"][0]["methodId"] = invalid_method_id

        return self._do_ms05_error_test(test,
                                        command_json,
                                        expected_status=NcMethodStatus.MethodNotImplemented)

    def test_11(self, test):
        """Node implements subscription and notification mechanism"""
        # https://specs.amwa.tv/ms-05-02/releases/v1.0.0/docs/NcObject.html#propertychanged-event
        # https://specs.amwa.tv/is-12/releases/v1.0.0/docs/Protocol_messaging.html#notification-message-type
        # https://specs.amwa.tv/is-12/releases/v1.0.0/docs/Protocol_messaging.html#subscription-message-type
        # https://specs.amwa.tv/is-12/releases/v1.0.0/docs/Protocol_messaging.html#subscription-response-message-type

        device_model = self.is12_utils.query_device_model(test)

        # Get all oids for objects in this Device Model
        device_model_objects = device_model.find_members_by_class_id(class_id=StandardClassIds.NCOBJECT.value,
                                                                     include_derived=True,
                                                                     recurse=True,
                                                                     get_objects=True)

        oids = dict.fromkeys([self.is12_utils.ROOT_BLOCK_OID] + [o.oid for o in device_model_objects], 0)

        error = False
        error_message = ""

        response = self.is12_utils.update_subscriptions(test, list(oids.keys()))

        if not isinstance(response, list):
            return test.FAIL(f"Unexpected response from subscription command: {str(response)}",
                             f"https://specs.amwa.tv/is-12/branches/{self.apis[CONTROL_API_KEY]['spec_branch']}"
                             "/docs/Protocol_messaging.html#subscription-response-message-type")
        for oid in oids.keys():
            if oid not in response:
                return test.FAIL(f"Unexpected response from subscription command: {str(response)}",
                                 f"https://specs.amwa.tv/is-12/branches/{self.apis[CONTROL_API_KEY]['spec_branch']}"
                                 "/docs/Protocol_messaging.html#subscription-response-message-type")
            method_result = self.is12_utils.get_property(test, NcObjectProperties.USER_LABEL.value, oid=oid)

            error_msg_base = f"oid: {str(oid)}, "

            if isinstance(method_result, NcMethodResultError):
                error = True
                error_message += f"{error_msg_base}GetProperty error: Unable to get userLabel property for object " \
                    f"{str(method_result.errorMessage)}; "
                continue

            old_user_label = method_result.value
            new_user_label = f"modified: {old_user_label}"

            # Each label will be set twice; once to the new user label, and then again back to the old user label
            for label in [new_user_label, old_user_label]:
                # Set property and log notificaiton
                self.is12_utils.start_logging_notifications(oid, NcObjectProperties.USER_LABEL.value)
                method_result = self.is12_utils.set_property(test, NcObjectProperties.USER_LABEL.value, label, oid=oid)
                self.is12_utils.stop_logging_notifications()

                if isinstance(method_result, NcMethodResultError):
                    error = True
                    error_message += f"{error_msg_base}SetProperty error: " \
                        "Unable to set userLabel property for object: " \
                        f"{str(method_result.errorMessage)}; "
                    continue

                for notification in self.is12_utils.get_notifications():
                    if notification.oid == oid:

                        if notification.eventId != NcObjectEvents.PROPERTY_CHANGED.value:
                            error = True
                            error_message += f"{error_msg_base}Unexpected event type: {str(notification.eventId)}; "

                        if notification.eventData.propertyId != NcObjectProperties.USER_LABEL.value:
                            continue

                        if notification.eventData.changeType != NcPropertyChangeType.ValueChanged.value:
                            error = True
                            error_message += f"{error_msg_base}Unexpected change type: " \
                                f"{str(notification.eventData.changeType.name)}; "

                        if notification.eventData.value != label:
                            error = True
                            error_message += f"{error_msg_base}Unexpected value: " \
                                f"{str(notification.eventData.value)}; "

                        if notification.eventData.sequenceItemIndex is not None:
                            error = True
                            error_message += f"{error_msg_base}Unexpected sequence item index: " \
                                f"{str(notification.eventData.sequenceItemIndex)}; "

                        oids[oid] += 1

        # We expect each object to have 2 notifications (set to new user label, set to old user label)
        if not all(v == 2 for v in oids.values()):
            error = True
            error_message += "Notifications not received for Oids " \
                f"{str(sorted([i for i, v in oids.items() if v != 2]))}"
        elif not any(v == 2 for v in oids.values()):
            error = True
            error_message += "No notifications received"

        if error:
            return test.FAIL(error_message)
        return test.PASS()
