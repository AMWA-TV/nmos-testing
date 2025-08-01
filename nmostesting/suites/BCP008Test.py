# Copyright (C) 2025 Advanced Media Workflow Association
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


from enum import Enum, IntEnum
from time import sleep
from typing import Dict, List, Optional

from ..GenericTest import GenericTest, NMOSTestException
from ..IS05Utils import IS05Utils
from ..IS12Utils import IS12Utils, IS12Notification
from ..MS05Utils import NcMethodId, NcMethodResult, NcMethodStatus, NcObject, NcObjectProperties, \
    NcPropertyId, NcTouchpointNmos
from ..TestResult import TestStates

NODE_API_KEY = "node"
CONN_API_KEY = "connection"
CONTROL_API_KEY = "ncp"
CONTROL_FRAMEWORK_API_KEY = "controlframework"
CONTROL_FEATURE_SETS_API_KEY = "featuresets"
MONITORING_FEATURE_SETS_KEY = "monitoring"

CONTROL_FRAMEWORK_SPEC_ROOT = "https://specs.amwa.tv/ms-05-02/branches/"
CONTROL_PROTOCOL_SPEC_ROOT = "https://specs.amwa.tv/is-12/branches/"


class NcStatusMonitorProperties(Enum):
    OVERALL_STATUS = NcPropertyId({"level": 3, "index": 1})
    OVERALL_STATUS_MESSAGE = NcPropertyId({"level": 3, "index": 2})
    STATUS_REPORTING_DELAY = NcPropertyId({"level": 3, "index": 3})


class NcOverallStatus(IntEnum):
    Inactive = 0
    Healthy = 1
    PartiallyHealthy = 2
    Unhealthy = 3
    UNKNOWN = 9999

    @classmethod
    def _missing_(cls, _):
        return cls.UNKNOWN


class NcLinkStatus(IntEnum):
    AllUp = 1
    SomeDown = 2
    AllDown = 3
    UNKNOWN = 9999

    @classmethod
    def _missing_(cls, _):
        return cls.UNKNOWN


class NcSynchronizationStatus(IntEnum):
    NotUsed = 0
    Healthy = 1
    PartiallyHealthy = 2
    Unhealthy = 3
    UNKNOWN = 9999

    @classmethod
    def _missing_(cls, _):
        return cls.UNKNOWN


class BCP008Test(GenericTest):
    """
    Template class for BCP-008-XX tests
    """
    class TestMetadata():
        def __init__(self, checked=False, error=False, error_msg="", link="", manual=False):
            self.checked = checked
            self.error = error
            self.error_msg = error_msg
            self.link = link
            self.manual = manual

    def __init__(self, apis, **kwargs):
        # Don't auto-test /transportfile as it is permitted to generate a 404 when master_enable is false
        omit_paths = [
            "/single/senders/{senderId}/transportfile"
        ]
        # Prevent auto testing of IS-04 and IS-05 APIs
        apis[NODE_API_KEY].pop("raml", None)
        apis[CONN_API_KEY].pop("raml", None)
        # override the control feature sets repos to only test against the monitoring feature set
        apis[CONTROL_FEATURE_SETS_API_KEY]['repo_paths'] = [MONITORING_FEATURE_SETS_KEY]
        GenericTest.__init__(self, apis, omit_paths, **kwargs)
        self.is05_utils = IS05Utils(self.apis[CONN_API_KEY]["url"])
        self.is12_utils = IS12Utils(self.apis)
        self.node_url = apis[NODE_API_KEY]["url"]
        self.resource_monitors = []

    def set_up_tests(self):
        self.is12_utils.reset()
        self.is12_utils.open_ncp_websocket()
        super().set_up_tests()

        self.testable_resources_found = False
        # Initialize cached test results
        self.check_activation_metadata = BCP008Test.TestMetadata()
        self.check_transition_to_unhealthy_metadata = BCP008Test.TestMetadata()
        self.check_touchpoint_metadata = BCP008Test.TestMetadata()
        self.check_overall_status_metadata = BCP008Test.TestMetadata()
        self.check_status_values_valid_metadata = BCP008Test.TestMetadata()
        self.check_deactivate_monitor_metadata = BCP008Test.TestMetadata()
        self.check_reset_counters_and_messages_metadata = BCP008Test.TestMetadata()
        self.check_transitions_counted_metadata = BCP008Test.TestMetadata()
        self.check_auto_reset_counters_metadata = BCP008Test.TestMetadata()

        self.check_activation_metadata.link = self.get_reporting_delay_spec_link()
        self.check_deactivate_monitor_metadata.link = self.get_deactivating_monitor_spec_link()
        self.check_touchpoint_metadata.link = self.get_touchpoint_spec_link()

    # Override basics to include auto tests
    def basics(self):
        results = super().basics()
        try:
            results += self.is12_utils.auto_tests()
        except NMOSTestException as e:
            results.append(e.args[0])
        except Exception as e:
            results.append(self.uncaught_exception("auto_tests", e))
        return results

    def tear_down_tests(self):
        # Clean up Websocket resources
        self.is12_utils.close_ncp_websocket()

    def _status_ok(self, method_result: NcMethodResult) -> bool:
        """Does method_result have an OK or PropertyDeprecated status"""
        if not hasattr(method_result, 'status'):
            return False
        return method_result.status == NcMethodStatus.OK \
            or method_result.status == NcMethodStatus.PropertyDeprecated

    # Overridden functions specialized in derived classes
    # Spec link getters
    def get_touchpoint_spec_link(self) -> str:
        """Returns URL to section of specification"""
        pass

    def get_transition_counters_spec_link(self) -> str:
        """Returns URL to section of specification"""
        pass

    def get_status_messages_spec_link(self) -> str:
        """Returns URL to section of specification"""
        pass

    def get_reporting_delay_spec_link(self) -> str:
        """Returns URL to section of specification"""
        pass

    def get_deactivating_monitor_spec_link(self) -> str:
        """Returns URL to section of specification"""
        pass

    def get_sync_source_change_spec_link(self) -> str:
        """Returns URL to section of specification"""
        pass

    def get_counter_method_spec_link(self) -> str:
        """Returns URL to section of specification"""
        pass

    # Status property and method IDs
    def get_domain_status_property_ids(self) -> List[NcPropertyId]:
        """Return list of all domain status properties, plus overall status, for this resource type"""
        pass

    def get_stream_status_property_id(self) -> NcPropertyId:
        """Returns the property modelling stream status for this resource type"""
        pass

    def get_stream_status_transition_counter_property_id(self) -> NcPropertyId:
        """Returns the property modelling stream status transition counter for this resource type"""
        pass

    def get_inactiveable_status_property_ids(self) -> List[NcPropertyId]:
        """Returns list of all properties capable of an Inactive status for this rsource type"""
        pass

    def get_auto_reset_counter_property_id(self) -> NcPropertyId:
        """Returns auto reset counter property for this resource type"""
        pass

    def get_sync_source_id_property_id(self) -> NcPropertyId:
        """Returns synchronization source counter property for this resource type"""
        pass

    def get_healthy_statuses_dict(self) -> Dict[NcPropertyId, int]:
        """On activation these properties MUST be healthy; dict of property id: healthy status enum"""
        pass

    def get_inactive_statuses_dict(self) -> Dict[NcPropertyId, int]:
        """On deactivation these properties MUST be inactive; dict of property id: healthy status enum"""
        pass

    def get_transition_counter_property_dict(self) -> Dict[str, NcPropertyId]:
        """Returns dict of transition counter properties for this resource; property name: property id"""
        pass

    def get_status_message_property_dict(self) -> Dict[str, NcPropertyId]:
        """Returns dict of transition counter properties for this resource; property name: property id"""
        pass

    def get_counter_method_ids(self) -> List[NcMethodId]:
        """Return list of counter method ids for this resource"""
        pass

    def get_reset_counter_method_id(self) -> NcMethodId:
        """Return reset method id for this resource"""
        pass

    # Resource
    def get_monitors(self, test: GenericTest) -> List[NcObject]:
        """Returns list of status monitor device model objects"""
        pass

    def get_touchpoint_resource_type(self) -> str:
        """Returns string indicating the type of resource being monitored"""
        pass

    def activate_resource(self, test: GenericTest, resource_id: str):
        """Activate the resource being monitored"""
        pass

    def deactivate_resource(self, test: GenericTest, resource_id: str):
        """Deactivates the resource being monitored"""
        pass

    # Validation
    def is_valid_resource(self, touchpoint_resource: Optional[NcTouchpointNmos]) -> bool:
        """Check the resource being monitored can be PATCHed"""
        pass

    def check_overall_status(self, monitor: NcObject, statuses: Dict[NcPropertyId, int]):
        """Check the overall status is consistent with domain statuses"""
        pass

    def validate_status_values(self, monitor: NcObject, statuses: Dict[NcPropertyId, int]):
        """Check that domain status values are legal"""
        pass

    def _get_property(self, test: GenericTest, monitor: NcObject, property_id: NcPropertyId) -> any:
        """Get a property and handle any error"""
        method_result = self.is12_utils.get_property(test, property_id,
                                                     oid=monitor.oid, role_path=monitor.role_path)

        if not self._status_ok(method_result):
            raise NMOSTestException(test.FAIL(method_result.errorMessage))

        return method_result.value

    def _set_property(self,
                      test: GenericTest,
                      monitor: NcObject,
                      property_id: NcPropertyId,
                      value: any) -> NcMethodResult:
        """Set a property and handle any error"""
        method_result = self.is12_utils.set_property(test, property_id, value,
                                                     oid=monitor.oid, role_path=monitor.role_path)

        if not self._status_ok(method_result):
            raise NMOSTestException(test.FAIL(method_result.errorMessage))

        return method_result

    def _get_touchpoint_resource(self, test: GenericTest, monitor: NcObject) -> Optional[NcTouchpointNmos]:
        """Checks touchpoint for monitor and returns associated NMOS resource id"""
        # The touchpoints property of any Monitor MUST have one or more touchpoints of which
        # one and only one entry MUST be of type NcTouchpointNmos where
        # the resourceType field MUST be set to correct resource type and
        # the id field MUST be set to the associated IS-04 resource UUID.
        touchpoint_resources = []

        touchpoints = self._get_property(test, monitor, NcObjectProperties.TOUCHPOINTS.value)

        for touchpoint in touchpoints:
            if "contextNamespace" not in touchpoint:
                self.check_touchpoint_metadata.error = True
                self.check_touchpoint_metadata.error_msg += "Touchpoint doesn't obey MS-05-02 schema " \
                    f"for Monitor: {monitor}; "
                # Override spec link to link to MS-05-02 specification
                self.check_touchpoint_metadata.link = f"{CONTROL_FRAMEWORK_SPEC_ROOT}" \
                    f"{self.apis[CONTROL_API_KEY]['spec_branch']}/Framework.html#nctouchpoint"
                continue

            if "resource" in touchpoint:  # the resource key is particular to the NcTouchpointNmos datatype
                touchpoint_resources.append(touchpoint)

        if len(touchpoint_resources) != 1:
            self.check_touchpoint_metadata.error = True
            self.check_touchpoint_metadata.error_msg += "One and only one touchpoint MUST be of type " \
                f"NcTouchpointNmos for Monitor: {monitor}; "
            return None

        touchpoint_resource = NcTouchpointNmos(touchpoint_resources[0])

        expected_resource_type = self.get_touchpoint_resource_type()

        if touchpoint_resource.resource["resourceType"] != expected_resource_type:
            self.check_touchpoint_metadata.error = True
            self.check_touchpoint_metadata.error_msg += \
                f"Touchpoint resourceType field MUST be set to '{expected_resource_type}' " \
                f"for Monitor: {monitor}; "
            return None

        self.check_touchpoint_metadata.checked = True

        return touchpoint_resource

    def _check_statuses(self,
                        monitor: NcObject,
                        initial_statuses: Dict[NcPropertyId, int],
                        notifications: List[IS12Notification]):
        """Check statuses are consistent and have legal values"""
        def _get_status_from_notifications(initial_status, notifications, property_id) -> int:
            # Aggregate initial status with any status change notifications
            status_notifications = [n for n in notifications if n.eventData.propertyId == property_id.value]
            return status_notifications[-1].eventData.value if len(status_notifications) else initial_status

        # Get statuses from notifications, using the initial_status as a default
        statuses = dict([(property_id,
                          _get_status_from_notifications(initial_status, notifications, property_id))
                        for property_id, initial_status in initial_statuses.items()])

        self.check_overall_status(monitor, statuses)
        self.validate_status_values(monitor, statuses)

    def _check_stream_status(self,
                             monitor: NcObject,
                             activation_time: int,
                             status_reporting_delay: int,
                             notifications: List[IS12Notification]):
        """Check stream status after activation and during the status reporting delay period"""
        # A resource is expected to go through a period of instability upon activation.
        # Therefore, on resource activation domain specific statuses offering an Inactive option
        # MUST transition immediately to the Healthy state. Furthermore, after activation,
        # as long as the resource isn’t being deactivated, it MUST delay the reporting of
        # non Healthy states for the duration specified by statusReportingDelay, and then
        # transition to any other appropriate state.
        tolerance = 0.2  # Allow for delays in notifications after activation
        connection_status_property = self.get_stream_status_property_id()

        connection_status_notifications = \
            [n for n in notifications
                if n.eventData.propertyId == connection_status_property
                and n.received_time >= activation_time]

        if len(connection_status_notifications) == 0:
            self.check_activation_metadata.error = True
            self.check_activation_metadata.error_msg += \
                f"No status notifications received for Monitor: {monitor}"
            return

        # Check that the monitor transitioned to healthy
        healthy_statuses_dict = self.get_healthy_statuses_dict()
        if len(connection_status_notifications) > 0 \
                and connection_status_notifications[0].eventData.value \
                != healthy_statuses_dict[connection_status_notifications[0].eventData.propertyId]:
            self.check_activation_metadata.error = True
            self.check_activation_metadata.error_msg += \
                f"Expect status to transition to healthy for Monitor: {monitor}"

        # Check that the monitor stayed in the healthy state (unless transitioned to Inactive)
        # during the status reporting delay period
        inactive_statuses_dict = self.get_inactive_statuses_dict()
        end_of_reporting_delay_period = activation_time + status_reporting_delay - tolerance
        if len(connection_status_notifications) > 1 \
                and connection_status_notifications[1].eventData.value \
                != inactive_statuses_dict[connection_status_notifications[1].eventData.propertyId]  \
                and connection_status_notifications[1].received_time < end_of_reporting_delay_period:
            self.check_activation_metadata.error = True
            self.check_activation_metadata.error_msg += \
                f"Expect status to remain healthy for at least the status reporting delay for Monitor: {monitor}; "

        # There is no *actual* stream so we expect connection to transition
        # to a less healthy state after the status reporting delay
        # i.e. expecting transition to healthy and then to less healthy (at least 2 transitions)
        if len(connection_status_notifications) > 1:
            self.check_transition_to_unhealthy_metadata.checked = True

        self.check_activation_metadata.checked = True

    def _check_stream_status_transition_counter(self, notifications: List[IS12Notification]):
        """Check whether stream status transition counter incremented"""
        connection_status_transition_counter_property = self.get_stream_status_transition_counter_property_id()

        connection_status_transition_counter_notifications = \
            [n for n in notifications
                if n.eventData.propertyId == connection_status_transition_counter_property
                and n.eventData.value > 0]

        # Given the transition to a less healthy state we expect the transition counter to increment
        # However, if it didn't transition then the counter won't increment
        if len(connection_status_transition_counter_notifications) > 0:
            self.check_transitions_counted_metadata.checked = True

    def _check_deactivate_resource(self, test: GenericTest, monitor: NcObject, resource_id: str):
        """Check resource being monitored deactivates correctly"""
        # When a resource is being deactivated it MUST cleanly disconnect from the current stream by not
        # generating intermediate unhealthy states (PartiallyHealthy or Unhealthy) and instead transition
        # directly and immediately (without being delayed by the statusReportingDelay)
        # to Inactive for all "inactiveable" statuses:

        # This value is common across NcConnectionStatus (Receivers) and NcTransmissionStatus (Senders)
        CONNECTION_STATUS_INACTIVE = 0

        # Check deactivation of resource during status replorting delay
        # Assume that resource is inactive before this check
        notifications = self.is12_utils.reset_notifications()

        self.activate_resource(test, resource_id)

        # Deactivate before the status reporting delay expires
        sleep(2.0)
        self.deactivate_resource(test, resource_id)
        sleep(2.0)  # Settling time

        # Process time stamped notifications
        notifications = self.is12_utils.get_notifications()

        activation_time = self._get_activation_time(test, monitor, notifications)

        deactivate_resource_notifications = [n for n in notifications if n.received_time >= activation_time]

        status_property_ids = self.get_inactiveable_status_property_ids()

        for property_id in status_property_ids:
            filtered_notifications = \
                    [n for n in deactivate_resource_notifications
                     if n.eventData.propertyId == property_id]

            if len(filtered_notifications) == 0:
                self.check_deactivate_monitor_metadata.error = True
                self.check_deactivate_monitor_metadata.error_msg += \
                    f"No status notifications received for Monitor: {monitor}; "

            # Check that the monitor transitioned to inactive
            if len(filtered_notifications) > 0 \
                    and filtered_notifications[-1].eventData.value != CONNECTION_STATUS_INACTIVE:
                self.check_deactivate_monitor_metadata.error = True
                self.check_deactivate_monitor_metadata.error_msg += \
                    f"Expect status to transition to Inactive for Monitor: {monitor}; "

            self.check_deactivate_monitor_metadata.checked = True

    def _check_auto_reset_counters_and_status_messages(self, test: GenericTest, monitor: NcObject, resource_id: str):
        """Check auto reset counters property functions correctly"""
        # Devices MUST be able to reset ALL status transition counter properties
        # when a resource activation occurs if autoResetCounters is set to true
        try:
            auto_reset_counter_property = self.get_auto_reset_counter_property_id()

            # Make sure autoResetCounters enabled
            self._set_property(test,
                               monitor,
                               auto_reset_counter_property,
                               True)

            # generate status transitions
            status_reporting_delay = \
                self._get_property(test,
                                   monitor,
                                   NcStatusMonitorProperties.STATUS_REPORTING_DELAY.value)
            self.activate_resource(test, resource_id)
            sleep(status_reporting_delay + 1.0)  # This assumes the connection status becomes unhealty
            self.deactivate_resource(test, resource_id)
            sleep(2.0)  # Settling time

            # check for status transitions
            non_zero_counters = self._get_non_zero_counters(test, monitor)
            status_messages = self._get_all_status_messages(test, monitor)

            if len(non_zero_counters) == 0 and len(status_messages) == 0:
                return  # No transitions or messages, so can't test

            # force auto reset
            self.activate_resource(test, resource_id)
            sleep(1.0)  # Settling time

            if len(non_zero_counters) > 0:
                non_zero_counters = self._get_non_zero_counters(test, monitor)

                if len(non_zero_counters) > 0:
                    self.check_auto_reset_counters_metadata.manual = True
                    self.check_auto_reset_counters_metadata.error_msg += \
                        f"Manually check transition counters {', '.join(non_zero_counters)} reset for Monitor: "\
                        f"{monitor} on activation; "
                    self.check_auto_reset_counters_metadata.link = self.get_transition_counters_spec_link()
                self.check_auto_reset_counters_metadata.checked = True

            if len(status_messages) > 0:
                # Check the messages are now cleared
                status_messages = self._get_all_status_messages(test, monitor)

                if len(status_messages) > 0:
                    self.check_auto_reset_counters_metadata.manual = True
                    self.check_auto_reset_counters_metadata.error_msg += \
                        f"Manually check status messages {', '.join(status_messages)} reset for Monitor: "\
                        f"{monitor} on activation; "
                    self.check_auto_reset_counters_metadata.link = self.get_status_messages_spec_link()
                self.check_auto_reset_counters_metadata.checked = True
        except NMOSTestException as e:
            self.check_auto_reset_counters_metadata.error = True
            self.check_auto_reset_counters_metadata.error_msg += f"{e.args[0].detail}; "

        self.deactivate_resource(test, resource_id)
        sleep(2.0)  # Settling time

    def _get_activation_time(self, test: GenericTest, monitor: NcObject, notifications: List[IS12Notification]) -> int:
        """Get activation time of receiver based off notifications received"""
        # On activation the overall status MUST transition from inactive
        inactivable_statuses_dict = self.get_inactive_statuses_dict()

        activation_notification = [n for n in notifications if
                                   n.eventData.propertyId in inactivable_statuses_dict.keys()
                                   and n.eventData.value != inactivable_statuses_dict[n.eventData.propertyId]]

        if len(activation_notification) == 0:
            self.check_activation_metadata.error = True
            self.check_activation_metadata.error_msg += \
                f"No transition to Healthy on activation for Monitor: {monitor}; "
            return 0

        # The received time of the first transition to Healthy is assumed to be the activation time
        return activation_notification[0].received_time

    def _get_non_zero_counters(self, test: GenericTest, monitor: NcObject) -> List[str]:
        """Returns list of all non zero transition counters"""
        transition_counters = self.get_transition_counter_property_dict()

        counter_values = dict([(key,
                                self._get_property(test,
                                                   monitor,
                                                   property_id))
                               for key, property_id in transition_counters.items()])

        return [c for c, v in counter_values.items() if v > 0]

    def _get_all_status_messages(self, test: GenericTest, monitor: NcObject) -> List[str]:
        """Returns list of all status messages which are not null or of zero length"""
        status_messages = self.get_status_message_property_dict()

        message_values = dict([(key,
                                self._get_property(test,
                                                   monitor,
                                                   property_id))
                               for key, property_id in status_messages.items()])

        return [c for c, v in message_values.items() if v and len(v) > 0]

    def _check_reset_counters_and_status_messages(self, test: GenericTest, monitor: NcObject):
        """Check reset counters and messages method functions correctly"""
        # Devices MUST be able to reset ALL status transition counter properties
        # when a client invokes the ResetCounters method

        non_zero_counters = self._get_non_zero_counters(test, monitor)
        status_messages = self._get_all_status_messages(test, monitor)

        if len(non_zero_counters) == 0 and len(status_messages) == 0:
            return  # No transitions or messages, so can't test

        # Invoke ResetCounters
        reset_counters_method = self.get_reset_counter_method_id()

        method_result = self.is12_utils.invoke_method(
            test,
            reset_counters_method,
            {},
            oid=monitor.oid,
            role_path=monitor.role_path)

        if not self._status_ok(method_result):
            self.check_reset_counters_and_messages_metadata.error = True
            self.check_reset_counters_and_messages_metadata.error_msg += \
                f"Method invokation ResetCountersAndMessages failed for Monitor: {monitor}: " \
                f"{method_result.errorMessage}. "
            return

        if len(non_zero_counters) > 0:
            # Check the counters are now zero
            non_zero_counters = self._get_non_zero_counters(test, monitor)

            if len(non_zero_counters) > 0:
                self.check_reset_counters_and_messages_metadata.manual = True
                self.check_reset_counters_and_messages_metadata.error_msg += \
                    f"Manually check transition counters {', '.join(non_zero_counters)} are reset for Monitor: " \
                    f"{monitor} on ResetCountersAndMessages method call; "
                self.check_reset_counters_and_messages_metadata.link = self.get_transition_counters_spec_link()
            self.check_reset_counters_and_messages_metadata.checked = True

        if len(status_messages) > 0:
            # Check the messages are now cleared
            status_messages = self._get_all_status_messages(test, monitor)

            if len(status_messages) > 0:
                self.check_reset_counters_and_messages_metadata.manual = True
                self.check_reset_counters_and_messages_metadata.error_msg += \
                    f"Manually check status messages {', '.join(status_messages)} reset for Monitor: "\
                    f"{monitor} on ResetCountersAndMessages method call; "
                self.check_reset_counters_and_messages_metadata.link = self.get_status_messages_spec_link()
            self.check_reset_counters_and_messages_metadata.checked = True

    def _get_testable_monitors(self, test: GenericTest) -> List[NcObject]:
        """Returns list of status monitor device model objects that can be tested"""
        def is_monitor_valid(test, monitor):
            touchpoint_resource = self._get_touchpoint_resource(test, monitor)
            return self.is_valid_resource(test, touchpoint_resource)

        return IS12Utils.sampled_list([m for m in self.get_monitors(test) if is_monitor_valid(test, m)])

    def _check_monitor_status_changes(self, test: GenericTest):
        """Perform set of checks on status monitor"""
        if self.check_activation_metadata.checked:
            return

        testable_monitors = self._get_testable_monitors(test)

        if len(testable_monitors) > 0:
            self.testable_resources_found = True
        else:
            return

        for monitor in testable_monitors:
            # Subscribe to the status monitor under test
            response = self.is12_utils.update_subscriptions(test, [monitor.oid])

            if not isinstance(response, list):
                raise NMOSTestException(
                    test.FAIL(f"Unexpected response from subscription command: {str(response)}",
                              f"{CONTROL_PROTOCOL_SPEC_ROOT}{self.apis[CONTROL_API_KEY]['spec_branch']}"
                              "/docs/Protocol_messaging.html#subscription-response-message-type"))

            # Set status reporting delay to the specification default
            status_reporting_delay = 3
            self._set_property(test,
                               monitor,
                               NcStatusMonitorProperties.STATUS_REPORTING_DELAY.value,
                               status_reporting_delay)

            # Get associated NMOS resource id for this monitor
            touchpoint_resource = self._get_touchpoint_resource(test, monitor)
            resource_id = touchpoint_resource.resource["id"]

            # Ensure resource being monitored is deactivated
            overall_status = self._get_property(test,
                                                monitor,
                                                NcStatusMonitorProperties.OVERALL_STATUS.value)

            if overall_status != NcOverallStatus.Inactive.value:
                # This test depends on the resource being inactive in the first instance
                self.deactivate_resource(test, resource_id)
                sleep(2.0)  # Settling time

            # Reset the notifications capture store
            self.is12_utils.reset_notifications()
            # Capture initial states of domain statuses
            initial_statuses = dict([(property_id,
                                      self._get_property(test,
                                                         monitor,
                                                         property_id.value))
                                     for property_id in self.get_domain_status_property_ids()])

            # Activate resource being monitored
            self.activate_resource(test, resource_id)

            # Wait until slightly more that status reporting delay to
            # capture any transitions to less healthy state after status_reporting_delay period
            sleep(status_reporting_delay + 2.0)

            # Get historic, time stamped, notifications from capture store
            notifications = self.is12_utils.get_notifications()

            # Determine the actual activation time based on the notifications
            activation_time = self._get_activation_time(test, monitor, notifications)

            # Check statuses before resource activated
            status_notifications = [n for n in notifications if n.received_time < activation_time]
            self._check_statuses(monitor, initial_statuses, status_notifications)

            # Check statuses during status reporting delay
            status_notifications = \
                [n for n in notifications if n.received_time < activation_time + status_reporting_delay]
            self._check_statuses(monitor, initial_statuses, status_notifications)

            # Check latest statuses, after reporting delay
            self._check_statuses(monitor, initial_statuses, notifications)

            # Check the stream status stayed healthy during status reporting delay
            # and transitioned to unhealthy afterwards (assuming not deactivated during delay)
            self._check_stream_status(monitor, activation_time, status_reporting_delay, notifications)

            self._check_stream_status_transition_counter(notifications)

            self.deactivate_resource(test, resource_id)
            sleep(2.0)  # Settling time

            # Ensure ResetCounter method resets counters to zero and clears status messages
            self._check_reset_counters_and_status_messages(test, monitor)

            self._check_deactivate_resource(test, monitor, resource_id)

            self._check_auto_reset_counters_and_status_messages(test, monitor, resource_id)

    def test_01(self, test):
        """Status reporting delay can be set to values within the published constraints"""
        monitors = self.get_monitors(test)

        if len(monitors) == 0:
            return test.UNCLEAR("Unable to find any testable Monitors")

        default_status_reporting_delay = 3
        for monitor in monitors:
            method_result = self.is12_utils.set_property(
                test, NcStatusMonitorProperties.STATUS_REPORTING_DELAY.value,
                default_status_reporting_delay,
                oid=monitor.oid, role_path=monitor.role_path)

            if not self._status_ok(method_result):
                return test.FAIL(f"SetProperty error: Error setting statusReportingDelay on Monitor: {monitor}")

            method_result = self.is12_utils.get_property(
                test, NcStatusMonitorProperties.STATUS_REPORTING_DELAY.value,
                oid=monitor.oid, role_path=monitor.role_path)

            if not self._status_ok(method_result):
                return test.FAIL(f"GetProperty error: Error getting statusReportingDelay on Monitor: {monitor}")

            if method_result.value != default_status_reporting_delay:
                return test.FAIL("Unexpected status reporting delay on Monitor. "
                                 f"Expected={default_status_reporting_delay} "
                                 f"actual={method_result.value} for Monitor: {monitor}")

        return test.PASS()

    def test_02(self, test):
        """Monitor transitions to Healthy state on activation"""
        self._check_monitor_status_changes(test)

        if not self.testable_resources_found:
            return test.UNCLEAR("Unable to find any testable Monitors")

        if self.check_activation_metadata.error:
            return test.FAIL(self.check_activation_metadata.error_msg,
                             self.check_activation_metadata.link)

        if not self.check_activation_metadata.checked:
            return test.UNCLEAR("Unable to test")

        return test.PASS()

    def test_03(self, test):
        """Transition to non-healthy states delayed until status reporting delay period passed"""
        self._check_monitor_status_changes(test)

        if not self.testable_resources_found:
            return test.UNCLEAR("Unable to find any testable Monitors")

        if not self.check_transition_to_unhealthy_metadata.checked:
            return test.MANUAL("Check by manually forcing an error condition")

        return test.PASS()

    def test_04(self, test):
        """Monitor delays transition to more healthy states by status reporting delay"""
        return test.MANUAL("Check by manually forcing an error condition")

    def test_05(self, test):
        """Transitions to less healthy states are counted"""
        self._check_monitor_status_changes(test)

        if not self.testable_resources_found:
            return test.UNCLEAR("Unable to find any testable Monitors")

        if not self.check_transitions_counted_metadata.checked:
            return test.MANUAL("Check by manually forcing an error condition")

        return test.PASS()

    def test_06(self, test):
        """ResetCounters method resets status transition counters and status messages"""
        self._check_monitor_status_changes(test)

        if not self.testable_resources_found:
            return test.UNCLEAR("Unable to find any testable Monitors")

        if self.check_reset_counters_and_messages_metadata.error:
            return test.FAIL(self.check_reset_counters_and_messages_metadata.error_msg,
                             self.check_reset_counters_and_messages_metadata.link)

        if not self.check_reset_counters_and_messages_metadata.checked:
            return test.MANUAL("Check ResetCounters method manually")

        # If unable to prove behaviour fall back to a manual test
        if self.check_reset_counters_and_messages_metadata.manual:
            return test.MANUAL(self.check_reset_counters_and_messages_metadata.error_msg,
                               self.check_reset_counters_and_messages_metadata.link)

        return test.PASS()

    def test_07(self, test):
        """autoResetCounters property set to TRUE resets status transition counters on activation"""
        self._check_monitor_status_changes(test)

        if not self.testable_resources_found:
            return test.UNCLEAR("Unable to find any testable Monitors")

        if self.check_auto_reset_counters_metadata.error:
            return test.FAIL(self.check_auto_reset_counters_metadata.error_msg)

        if not self.check_auto_reset_counters_metadata.checked:
            return test.MANUAL("Check autoResetCounters property manually")

        # If unable to prove behaviour fall back to a manual test
        if self.check_auto_reset_counters_metadata.manual:
            return test.MANUAL(self.check_auto_reset_counters_metadata.error_msg,
                               self.check_auto_reset_counters_metadata.link)

        return test.PASS()

    def test_08(self, test):
        """Overall status is correctly mapped from domain statuses"""
        self._check_monitor_status_changes(test)

        if not self.testable_resources_found:
            return test.UNCLEAR("Unable to find any testable Monitors")

        if self.check_overall_status_metadata.error:
            return test.FAIL(self.check_overall_status_metadata.error_msg,
                             self.check_overall_status_metadata.link)

        if not self.check_overall_status_metadata.checked:
            return test.UNCLEAR("Unable to test")

        return test.PASS()

    def test_09(self, test):
        """Status values are valid"""
        self._check_monitor_status_changes(test)

        if not self.testable_resources_found:
            return test.UNCLEAR("Unable to find any testable Monitors")

        if self.check_status_values_valid_metadata.error:
            return test.FAIL(self.check_status_values_valid_metadata.error_msg,
                             self.check_status_values_valid_metadata.link)

        if not self.check_status_values_valid_metadata.checked:
            return test.UNCLEAR("Unable to test")

        return test.PASS()

    def _check_counter_method(self, test: GenericTest, method_id: NcMethodId, spec_link: str):
        """Check counter methods for this status monitor"""
        monitors = self._get_testable_monitors(test)

        if len(monitors) == 0:
            return test.UNCLEAR("Unable to find any testable Monitors")

        for monitor in monitors:
            method_result = self.is12_utils.invoke_method(
                test,
                method_id,
                {},
                oid=monitor.oid,
                role_path=monitor.role_path)

            if not self._status_ok(method_result):
                return test.FAIL(f"Method invokation failed for Monitor: {monitor}: "
                                 f"{method_result.errorMessage}", spec_link)

            if method_result.value is None or not isinstance(method_result.value, list):
                return test.FAIL(f"Expected an array, got {str(method_result.value)} for Monitor: {monitor}", spec_link)

            for counter in method_result.value:
                self.is12_utils.reference_datatype_schema_validate(test, counter, "NcCounter")

        return test.PASS()

    def test_10(self, test):
        """Counter methods are implemented"""
        spec_link = self.get_counter_method_spec_link()

        method_ids = self.get_counter_method_ids()

        for method_id in method_ids:
            result = self._check_counter_method(
                test,
                method_id,
                spec_link)

            if result.state != TestStates.PASS:
                break

        return result

    def test_11(self, test):
        """Monitor transitions to PartiallyHealthy on synchronization source change"""
        # Monitors MUST temporarily transition to PartiallyHealthy when detecting a synchronization source change
        return test.MANUAL("Check by manually forcing a synchronization source change")

    def test_12(self, test):
        """synchronizationSourceID property has a valid value"""
        # When devices intend to use external synchronization they MUST publish the synchronization source id
        # currently being used in the synchronizationSourceId property and update the externalSynchronizationStatus
        # property whenever it changes, setting the synchronizationSourceId to null if a synchronization source
        # cannot be discovered. Devices which are not intending to use external synchronization MUST populate
        # this property with 'internal' or their own id if they themselves are the synchronization source
        # (e.g. the device is a grandmaster).
        monitors = self.get_monitors(test)

        spec_link = self.get_sync_source_change_spec_link()

        if len(monitors) == 0:
            return test.UNCLEAR("Unable to find any testable Monitors")

        sync_source_id_property = self.get_sync_source_id_property_id()

        for monitor in monitors:
            syncSourceId = self._get_property(test,
                                              monitor,
                                              sync_source_id_property)

            # Synchronization source id can be null, "internal" or some identifier, but it can't be empty
            if syncSourceId == "":
                return test.FAIL("Synchronization source id MUST be either null, 'internal' "
                                 f"or an identifer for Monitor: {monitor}", spec_link)

        return test.PASS()

    def test_13(self, test):
        """Resource cleanly disconnects from the current stream on deactivation"""
        self._check_monitor_status_changes(test)

        if not self.testable_resources_found:
            return test.UNCLEAR("Unable to find any testable Monitors")

        if self.check_deactivate_monitor_metadata.error:
            return test.FAIL(self.check_deactivate_monitor_metadata.error_msg,
                             self.check_deactivate_monitor_metadata.link)

        if not self.check_deactivate_monitor_metadata.checked:
            return test.UNCLEAR("Unable to test")

        return test.PASS()

    def test_14(self, test):
        """Monitor has a valid touchpoint resource"""
        self._check_monitor_status_changes(test)

        if not self.testable_resources_found:
            return test.UNCLEAR("Unable to find any testable Monitors")

        if self.check_touchpoint_metadata.error:
            return test.FAIL(self.check_touchpoint_metadata.error_msg,
                             self.check_touchpoint_metadata.link)

        if not self.check_touchpoint_metadata.checked:
            return test.UNCLEAR("Unable to test")

        return test.PASS()
