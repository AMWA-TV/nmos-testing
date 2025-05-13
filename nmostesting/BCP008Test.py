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
from time import sleep, time

from .TestResult import TestStates

from .GenericTest import GenericTest, NMOSTestException
from .IS05Utils import IS05Utils
from .IS12Utils import IS12Utils
from .MS05Utils import NcMethodStatus, NcObjectProperties, NcTouchpointNmos, NcWorkerProperties, \
    NcMethodId, NcPropertyId

NODE_API_KEY = "node"
CONN_API_KEY = "connection"
CONTROL_API_KEY = "ncp"
CONTROL_FRAMEWORK_API_KEY = "controlframework"

CONTROL_FRAMEWORK_SPEC_ROOT = "https://specs.amwa.tv/ms-05-02/branches/"
CONTROL_PROTOCOL_SPEC_ROOT = "https://specs.amwa.tv/is-12/branches/"


class NcStatusMonitorProperties(Enum):
    OVERALL_STATUS = NcPropertyId({"level": 3, "index": 1})
    OVERALL_STATUS_MESSAGE = NcPropertyId({"level": 3, "index": 2})
    STATUS_REPORTING_DELAY = NcPropertyId({"level": 3, "index": 3})


class NcSenderMonitorProperties(Enum):
    LINK_STATUS = NcPropertyId({"level": 4, "index": 1})
    LINK_STATUS_MESSAGE = NcPropertyId({"level": 4, "index": 2})
    LINK_STATUS_TRANSITION_COUNTER = NcPropertyId({"level": 4, "index": 3})
    TRANSMISSION_STATUS = NcPropertyId({"level": 4, "index": 4})
    TRANSMISSION_STATUS_MESSAGE = NcPropertyId({"level": 4, "index": 5})
    TRANSMISSION_STATUS_TRANSITION_COUNTER = NcPropertyId({"level": 4, "index": 6})
    EXTERNAL_SYNCHRONIZATION_STATUS = NcPropertyId({"level": 4, "index": 7})
    EXTERNAL_SYNCHRONIZATION_STATUS_MESSAGE = NcPropertyId({"level": 4, "index": 8})
    EXTERNAL_SYNCHRONIZATION_STATUS_TRANSITION_COUNTER = NcPropertyId({"level": 4, "index": 9})
    SYNCHRONIZATION_SOURCE_ID = NcPropertyId({"level": 4, "index": 10})
    ESSENCE_STATUS = NcPropertyId({"level": 4, "index": 11})
    ESSENCE_STATUS_MESSAGE = NcPropertyId({"level": 4, "index": 12})
    ESSENCE_STATUS_TRANSITION_COUNTER = NcPropertyId({"level": 4, "index": 13})
    AUTO_RESET_COUNTERS = NcPropertyId({"level": 4, "index": 14})


class NcSenderMonitorMethods(Enum):
    GET_TRANSMISSION_ERROR_COUNTERS = NcMethodId({"level": 4, "index": 1})
    RESET_COUNTERS = NcMethodId({"level": 4, "index": 2})


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


class NcConnectionStatus(IntEnum):
    Inactive = 0
    Healthy = 1
    PartiallyHealthy = 2
    Unhealthy = 3
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


class NcStreamStatus(IntEnum):
    Inactive = 0
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
        def __init__(self, checked=False, error=False, error_msg="", link=""):
            self.checked = checked
            self.error = error
            self.error_msg = error_msg
            self.link = link

    def __init__(self, apis, **kwargs):
        # Don't auto-test /transportfile as it is permitted to generate a 404 when master_enable is false
        omit_paths = [
            "/single/senders/{senderId}/transportfile"
        ]
        # Prevent auto testing of IS-04 and IS-05 APIs
        apis[NODE_API_KEY].pop("raml", None)
        apis[CONN_API_KEY].pop("raml", None)
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
        self.check_reset_counters_metadata = BCP008Test.TestMetadata()
        self.check_transitions_counted_metadata = BCP008Test.TestMetadata()
        self.check_auto_reset_counters_metadata = BCP008Test.TestMetadata()

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

    def _status_ok(self, method_result):
        if not hasattr(method_result, 'status'):
            return False
        return method_result.status == NcMethodStatus.OK \
            or method_result.status == NcMethodStatus.PropertyDeprecated

    # Overridden functions specialized in derived classes
    # Spec link getters
    def get_touchpoint_spec_link(self):
        pass

    def get_transition_counters_spec_link(self):
        pass

    def get_reporting_delay_spec_link(self):
        pass

    def get_deactivating_monitor_spec_link(self):
        pass

    def get_sync_source_change_spec_link(self):
        pass

    def get_woker_inheritance_spec_link(self):
        pass

    def get_counter_method_spec_link(self):
        pass

    # Status property and method IDs
    def get_status_property_ids(self):
        pass

    def get_connection_status_property_id(self):
        pass

    def get_connection_status_transition_counter_property_id(self):
        pass

    def get_inactiveable_status_property_ids(self):
        pass

    def get_auto_reset_counter_property_id(self):
        pass

    def get_sync_source_id_property_id(self):
        pass

    def get_transition_counter_property_map(self):
        pass

    def get_counter_method_ids(self):
        pass

    def get_auto_reset_counter_method_id(self):
        pass

    # Resource
    def get_monitors(self, test):
        pass

    def get_touchpoint_resource_type(self):
        pass

    def patch_resource(self, test, resource_id):
        pass

    def deactivate_resource(self, test, resource_id):
        pass

    # Validation
    def is_valid_resource(self, touchpoint_resource):
        pass

    def check_overall_status(self, statuses, oid, role_path):
        pass

    def validate_status_values(self, statuses, oid, role_path):
        pass

    def _get_property(self, test, property_id, oid, role_path):
        """Get a property and handle any error"""
        method_result = self.is12_utils.get_property(test, property_id, oid=oid, role_path=role_path)

        if not self._status_ok(method_result):
            raise NMOSTestException(test.FAIL(method_result.errorMessage))

        return method_result.value

    def _set_property(self, test, property_id, value, oid, role_path):
        """Set a property and handle any error"""
        method_result = self.is12_utils.set_property(test, property_id, value, oid=oid, role_path=role_path)

        if not self._status_ok(method_result):
            raise NMOSTestException(test.FAIL(method_result.errorMessage))

        return method_result

    def _get_touchpoint_resource(self, test, oid, role_path):
        # The touchpoints property of any Monitor MUST have one or more touchpoints of which
        # one and only one entry MUST be of type NcTouchpointNmos where
        # the resourceType field MUST be set to correct resource type and
        # the id field MUST be set to the associated IS-04 resource UUID.
        spec_link = self.get_touchpoint_spec_link()

        touchpoint_resources = []

        touchpoints = self._get_property(test, NcObjectProperties.TOUCHPOINTS.value, oid, role_path)

        for touchpoint in touchpoints:
            if "contextNamespace" not in touchpoint:
                self.check_touchpoint_metadata.error = True
                self.check_touchpoint_metadata.error_msg = "Touchpoint doesn't obey MS-05-02 schema " \
                    f"for Monitor, oid={oid}, " \
                    f"role path={role_path}; "
                self.check_touchpoint_metadata.link = f"{CONTROL_FRAMEWORK_SPEC_ROOT}" \
                    f"{self.apis[CONTROL_API_KEY]['spec_branch']}/Framework.html#nctouchpoint"
                continue

            if "resource" in touchpoint:
                touchpoint_resources.append(touchpoint)

        if len(touchpoint_resources) != 1:
            self.check_touchpoint_metadata.error = True
            self.check_touchpoint_metadata.error_msg = "One and only one touchpoint MUST be of type NcTouchpointNmos " \
                f"for Monitor, oid={oid}, " \
                f"role path={role_path}; "
            self.check_touchpoint_metadata.link = spec_link
            return None

        touchpoint_resource = NcTouchpointNmos(touchpoint_resources[0])

        expected_resource_type = self.get_touchpoint_resource_type()

        if touchpoint_resource.resource["resourceType"] != expected_resource_type:
            self.check_touchpoint_metadata.error = True
            self.check_touchpoint_metadata.error_msg = \
                f"Touchpoint resourceType field MUST be set to '{expected_resource_type}' " \
                f"for Monitor, oid={oid}, " \
                f"role path={role_path}; "
            self.check_touchpoint_metadata.link = spec_link
            return None

        self.check_touchpoint_metadata.checked = True

        return touchpoint_resource

    def _check_statuses(self, initial_statuses, notifications, oid, role_path):

        def _get_status_from_notifications(initial_status, notifications, property_id):
            # Aggregate initial status with any status change notifications
            status_notifications = [n for n in notifications if n.eventData.propertyId == property_id.value]

            return status_notifications[-1].eventData.value if len(status_notifications) else initial_status

        # Get statuses from notifications, using the initial_status as a default
        statuses = dict([(property_id,
                          _get_status_from_notifications(initial_status, notifications, property_id))
                        for property_id, initial_status in initial_statuses.items()])

        self.check_overall_status(statuses, oid, role_path)
        self.validate_status_values(statuses, oid, role_path)

    def _check_connection_status(self, monitor, start_time, status_reporting_delay, notifications):
        # A resource is expected to go through a period of instability upon activation.
        # Therefore, on resource activation domain specific statuses offering an Inactive option
        # MUST transition immediately to the Healthy state. Furthermore, after activation,
        # as long as the resource isn’t being deactivated, it MUST delay the reporting of
        # non Healthy states for the duration specified by statusReportingDelay, and then
        # transition to any other appropriate state.
        connection_status_property = self.get_connection_status_property_id()

        connection_status_notifications = \
            [n for n in notifications
                if n.eventData.propertyId == connection_status_property.value
                and n.received_time >= start_time]

        self.check_activation_metadata.link = self.get_reporting_delay_spec_link()

        if len(connection_status_notifications) == 0:
            self.check_activation_metadata.error = True
            self.check_activation_metadata.error_msg += \
                "No status notifications received for Monitor, " \
                f"oid={monitor.oid}, role path={monitor.role_path}; "
            return

        # Check that the monitor transitioned to healthy
        if len(connection_status_notifications) > 0 \
                and connection_status_notifications[0].eventData.value != NcConnectionStatus.Healthy.value:
            self.check_activation_metadata.error = True
            self.check_activation_metadata.error_msg += \
                "Expect status to transition to healthy for Monitor, " \
                f"oid={monitor.oid}, role path={monitor.role_path}; "

        # Check that the monitor stayed in the healthy state (unless transitioned to Inactive)
        # during the status reporting delay period
        if len(connection_status_notifications) > 1 \
                and connection_status_notifications[1].eventData.value != NcConnectionStatus.Inactive.value \
                and connection_status_notifications[1].received_time < start_time + status_reporting_delay:
            self.check_activation_metadata.error = True
            self.check_activation_metadata.error_msg += \
                "Expect status to remain healthy for at least the status reporting delay for Monitor, " \
                f"oid={monitor.oid}, role path={monitor.role_path}; "

        # There is no *actual* stream so we expect connection to transition
        # to a less healthy state after the status reporting delay
        # i.e. expecting transition to healthy and then to less healthy (at least 2 transitions)
        if len(connection_status_notifications) > 1:
            self.check_transition_to_unhealthy_metadata.checked = True

        self.check_activation_metadata.checked = True

    def _check_connection_status_transition_counter(self, notifications):

        connection_status_transition_counter_property = self.get_connection_status_transition_counter_property_id()

        connection_status_transition_counter_notifications = \
            [n for n in notifications
                if n.eventData.propertyId == connection_status_transition_counter_property.value
                and n.eventData.value > 0]

        # Given the transition to a less healthy state we expect the transition counter to increment
        # However, if it didn't transition then the counter won't increment
        if len(connection_status_transition_counter_notifications) > 0:
            self.check_transitions_counted_metadata.checked = True

    def _check_deactivate_resource(self, test, monitor_oid, monitor_role_path, resource_id):
        # When a resource is being deactivated it MUST cleanly disconnect from the current stream by not
        # generating intermediate unhealthy states (PartiallyHealthy or Unhealthy) and instead transition
        # directly and immediately (without being delayed by the statusReportingDelay)
        # to Inactive for the following statuses:
        # * overallStatus
        # * connectionStatus
        # * streamStatus

        # Check deactivation of resource during status replorting delay
        start_time = time()

        self.patch_resource(test, resource_id)

        # Deactivate before the status reporting delay expires
        sleep(1.0)
        self.deactivate_resource(test, resource_id)
        sleep(1.0)  # Let resource settle

        # Process time stamped notifications
        notifications = self.is12_utils.get_notifications()

        deactivate_resource_notifications = [n for n in notifications if n.received_time >= start_time]

        self.check_deactivate_monitor_metadata.link = self.get_deactivating_monitor_spec_link()

        status_property_ids = self.get_inactiveable_status_property_ids()

        for property_id in status_property_ids:
            filtered_notifications = \
                    [n for n in deactivate_resource_notifications
                     if n.eventData.propertyId == property_id.value]

            if len(filtered_notifications) == 0:
                self.check_deactivate_monitor_metadata.error = True
                self.check_deactivate_monitor_metadata.error_msg += \
                    "No status notifications received for Monitor, " \
                    f"oid={monitor_oid}, role path={monitor_role_path}; "

            # Check that the monitor transitioned to inactive
            if len(filtered_notifications) > 0 \
                    and filtered_notifications[-1].eventData.value != NcConnectionStatus.Inactive.value:
                self.check_deactivate_monitor_metadata.error = True
                self.check_deactivate_monitor_metadata.error_msg += \
                    "Expect status to transition to Inactive for Monitor, " \
                    f"oid={monitor_oid}, role path={monitor_role_path}; "

            self.check_deactivate_monitor_metadata.checked = True

    def _check_auto_reset_counters(self, test, monitor, resource_id):
        # Devices MUST be able to reset ALL status transition counter properties
        # when a resource activation occurs if autoResetCounters is set to true
        self.check_auto_reset_counters_metadata.link = self.get_transition_counters_spec_link()

        auto_reset_counter_property = self.get_auto_reset_counter_property_id()

        # Make sure autoResetCounters enabled
        self._set_property(test,
                           auto_reset_counter_property.value,
                           True,
                           oid=monitor.oid,
                           role_path=monitor.role_path)

        # generate status transitions
        status_reporting_delay = \
            self._get_property(test,
                               NcStatusMonitorProperties.STATUS_REPORTING_DELAY.value,
                               oid=monitor.oid,
                               role_path=monitor.role_path)
        self.patch_resource(test, resource_id)
        sleep(status_reporting_delay + 1.0)  # This assumes the connection status becomes unhealty
        self.deactivate_resource(test, resource_id)

        # check for status transitions
        non_zero_counters = self._get_non_zero_counters(test, monitor)

        if len(non_zero_counters) == 0:
            return  # No transitions, so can't test

        # force auto reset
        self.patch_resource(test, resource_id)
        sleep(1.0)  # Settling time

        non_zero_counters = self._get_non_zero_counters(test, monitor)

        if len(non_zero_counters) > 0:
            self.check_auto_reset_counters_metadata.error = True
            self.check_auto_reset_counters_metadata.error_msg = \
                f"Transition counters {', '.join(non_zero_counters)} not reset for Monitor, " \
                f"oid={monitor.oid}, " \
                f"role path={monitor.role_path}: "

        self.check_auto_reset_counters_metadata.checked = True

        self.deactivate_resource(test, resource_id)

    def _check_monitor_status_changes(self, test):

        if self.check_activation_metadata.checked:
            return

        all_monitors = self.get_monitors(test)

        if len(all_monitors) > 0:
            self.testable_resources_found = True
        else:
            return

        monitors = IS12Utils.sampled_list(all_monitors)

        status_properties = self.get_status_property_ids()

        for monitor in monitors:

            response = self.is12_utils.update_subscriptions(test, [monitor.oid])

            if not isinstance(response, list):
                raise NMOSTestException(
                    test.FAIL(f"Unexpected response from subscription command: {str(response)}",
                              f"{CONTROL_PROTOCOL_SPEC_ROOT}{self.apis[CONTROL_API_KEY]['spec_branch']}"
                              "/docs/Protocol_messaging.html#subscription-response-message-type"))

            # Capture initial states of domain statuses
            initial_statuses = dict([(property_id,
                                      self._get_property(test,
                                                         property_id.value,
                                                         role_path=monitor.role_path,
                                                         oid=monitor.oid))
                                     for property_id in status_properties])

            self.is12_utils.reset_notifications()

            # Set status reporting delay to the specification default
            status_reporting_delay = 3
            self._set_property(test,
                               NcStatusMonitorProperties.STATUS_REPORTING_DELAY.value,
                               status_reporting_delay,
                               oid=monitor.oid,
                               role_path=monitor.role_path)

            # Get associated resource for this monitor
            touchpoint_resource = self._get_touchpoint_resource(test,
                                                                monitor.oid,
                                                                monitor.role_path)

            if not self.is_valid_resource(test, touchpoint_resource):
                # Can't find the resource
                continue

            resource_id = touchpoint_resource.resource["id"]

            if initial_statuses[NcStatusMonitorProperties.OVERALL_STATUS] != NcOverallStatus.Inactive.value:
                # This test depends on the resource being inactive in the first instance
                self.deactivate_resource(test, resource_id)
                sleep(2.0)  # settling time
                initial_statuses = dict([(property_id,
                                          self._get_property(test,
                                                             property_id.value,
                                                             role_path=monitor.role_path,
                                                             oid=monitor.oid))
                                         for property_id in status_properties])

            # Assume that the resource patch happens immediately after start_time
            start_time = time()

            self.patch_resource(test, resource_id)

            # Wait until one second more that status reporting delay to capture transition to less healthy state
            sleep(status_reporting_delay + 2.0)

            # Ensure ResetCounter method resets counters to zero
            self._check_reset_counters(test, monitor)

            # Now process historic, time stamped, notifications
            notifications = self.is12_utils.get_notifications()

            # Check statuses before resource patched
            status_notifications = [n for n in notifications if n.received_time < start_time]
            self._check_statuses(initial_statuses, status_notifications, monitor.oid, monitor.role_path)

            # Check statuses during status reporting delay
            status_notifications = \
                [n for n in notifications if n.received_time < start_time + status_reporting_delay]
            self._check_statuses(initial_statuses, status_notifications, monitor.oid, monitor.role_path)

            # Check statuses after status reporting delay
            status_notifications = \
                [n for n in notifications if n.received_time >= start_time + status_reporting_delay]
            self._check_statuses(initial_statuses, status_notifications, monitor.oid, monitor.role_path)

            # Check the Connection Status stayed healthy during status reporting delay
            # and transitioned to unhealthy afterwards (assuming not deactivated during delay)
            self._check_connection_status(monitor, start_time, status_reporting_delay, notifications)

            self._check_connection_status_transition_counter(notifications)

            self.deactivate_resource(test, resource_id)
            sleep(2.0)  # Let resource settle

            self._check_deactivate_resource(test, monitor.oid, monitor.role_path, resource_id)

            self._check_auto_reset_counters(test, monitor, resource_id)

    def _check_late_lost_packet_method(self, test, method_id, spec_link):
        """Check late or lost packet method depending on method_id"""
        monitors = self.get_monitors(test)

        if len(monitors) == 0:
            return test.UNCLEAR("Unable to find any testable Monitors")

        arguments = {}  # empty arguments

        for monitor in monitors:
            method_result = self.is12_utils.invoke_method(
                test,
                method_id,
                arguments,
                oid=monitor.oid,
                role_path=monitor.role_path)

            if not self._status_ok(method_result):
                return test.FAIL("Method invokation GetLostPacketCounters failed for Monitor, "
                                 f"oid={monitor.oid}, "
                                 f"role path={monitor.role_path}: "
                                 f"{method_result.errorMessage}", spec_link)

            if method_result.value is None or not isinstance(method_result.value, list):
                return test.FAIL(f"Expected an array, got {str(method_result.value)} for Monitor, "
                                 f"oid={monitor.oid}, "
                                 f"role path={monitor.role_path}: ", spec_link)

            for counter in method_result.value:
                self.is12_utils.reference_datatype_schema_validate(test, counter, "NcCounter")

        return test.PASS()

    def _get_non_zero_counters(self, test, monitor):

        transition_counters = self.get_transition_counter_property_map()

        counter_values = dict([(key,
                                self._get_property(test,
                                                   property_id.value,
                                                   role_path=monitor.role_path,
                                                   oid=monitor.oid))
                               for key, property_id in transition_counters.items()])

        return [c for c, v in counter_values.items() if v > 0]

    def _check_reset_counters(self, test, monitor):
        # Devices MUST be able to reset ALL status transition counter properties
        # when a client invokes the ResetCounters method

        self.check_reset_counters_metadata.link = self.get_transition_counters_spec_link()

        non_zero_counters = self._get_non_zero_counters(test, monitor)

        if len(non_zero_counters) == 0:
            return  # No transitions, so can't test

        arguments = {}

        # Invoke ResetCounters
        reset_counters_method = self.get_auto_reset_counter_method_id()

        method_result = self.is12_utils.invoke_method(
            test,
            reset_counters_method.value,
            arguments,
            oid=monitor.oid,
            role_path=monitor.role_path)

        if not self._status_ok(method_result):
            self.check_reset_counters_metadata.error = True
            self.check_reset_counters_metadata.error_msg = \
                "Method invokation ResetCounters failed for Monitor, " \
                f"oid={monitor.oid}, role path={monitor.role_path}: " \
                f"{method_result.errorMessage}. "
            return

        non_zero_counters = self._get_non_zero_counters(test, monitor)

        if len(non_zero_counters) > 0:
            self.check_reset_counters_metadata.error = True
            self.check_reset_counters_metadata.error_msg = \
                f"Transition counters {', '.join(non_zero_counters)} not reset for Monitor, " \
                f"oid={monitor.oid}, role path={monitor.role_path}: "

        self.check_reset_counters_metadata.checked = True

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
                return test.FAIL("SetProperty error: Error setting statusReportingDelay on Monitor, "
                                 f"oid={monitor.oid}, "
                                 f"role path={monitor.role_path}")

            method_result = self.is12_utils.get_property(
                test, NcStatusMonitorProperties.STATUS_REPORTING_DELAY.value,
                oid=monitor.oid, role_path=monitor.role_path)

            if not self._status_ok(method_result):
                return test.FAIL("GetProperty error: Error getting statusReportingDelay on Monitor, "
                                 f"oid={monitor.oid}, "
                                 f"role path={monitor.role_path}")

            if method_result.value != default_status_reporting_delay:
                return test.FAIL("Unexpected status reporting delay on Monitor. "
                                 f"Expected={default_status_reporting_delay} actual={method_result.value}, "
                                 f"oid={monitor.oid}, "
                                 f"role path={monitor.role_path}")

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
        """Transition to Non-healthy states at activation"""

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
        """ResetCounters method resets status transition counters"""

        self._check_monitor_status_changes(test)

        if not self.testable_resources_found:
            return test.UNCLEAR("Unable to find any testable Monitors")

        if self.check_reset_counters_metadata.error:
            return test.FAIL(self.check_reset_counters_metadata.error_msg,
                             self.check_reset_counters_metadata.link)

        if not self.check_reset_counters_metadata.checked:
            return test.MANUAL("Check ResetCounters method manually")

        return test.PASS()

    def test_07(self, test):
        """autoResetCounters property set to TRUE resets status transition counters on activation"""

        self._check_monitor_status_changes(test)

        if not self.testable_resources_found:
            return test.UNCLEAR("Unable to find any testable Monitors")

        if self.check_auto_reset_counters_metadata.error:
            return test.FAIL(self.check_auto_reset_counters_metadata.error_msg,
                             self.check_auto_reset_counters_metadata.link)

        if not self.check_auto_reset_counters_metadata.checked:
            return test.MANUAL("Check autoResetCounters property manually")

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

    def test_10(self, test):
        """Counter methods are implemented"""
        spec_link = self.get_counter_method_spec_link()

        method_ids = self.get_counter_method_ids()

        for method_id in method_ids:
            result = self._check_late_lost_packet_method(
                test,
                method_id.value,
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
                                              sync_source_id_property.value,
                                              oid=monitor.oid,
                                              role_path=monitor.role_path)

            # Synchronization source id can be null, "internal" or some identifier, but it can't be empty
            if syncSourceId == "":
                return test.FAIL("Synchronization source id MUST be either null, 'internal' "
                                 "or an identifer for Monitor, "
                                 f"oid={monitor.oid}, "
                                 f"role path={monitor.role_path}.", spec_link)

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

    def test_15(self, test):
        """enabled property is TRUE by default, and cannot be set to FALSE"""
        spec_link = self.get_woker_inheritance_spec_link()

        monitors = self.get_monitors(test)

        if len(monitors) == 0:
            return test.UNCLEAR("Unable to find any testable Monitors")

        for monitor in monitors:
            enabled = self._get_property(test,
                                         NcWorkerProperties.ENABLED.value,
                                         oid=monitor.oid,
                                         role_path=monitor.role_path)

            if enabled is not True:
                return test.FAIL("Monitors MUST always have the enabled property set to true "
                                 f"for Monitor, oid={monitor.oid}, "
                                 f"role path={monitor.role_path}.", spec_link)

            method_result = self.is12_utils.set_property(test,
                                                         NcWorkerProperties.ENABLED.value,
                                                         False,
                                                         oid=monitor.oid,
                                                         role_path=monitor.role_path)

            if method_result.status == NcMethodStatus.OK:
                return test.FAIL("Monitors MUST NOT allow changes to the enabled property "
                                 f"for Monitor, oid={monitor.oid}, "
                                 f"role path={monitor.role_path}.", spec_link)

            if method_result.status != NcMethodStatus.InvalidRequest:
                return test.FAIL("Monitors MUST return InvalidRequest "
                                 "to Set method invocations for this property "
                                 f"for Monitor, oid={monitor.oid}, "
                                 f"role path={monitor.role_path}.", spec_link)
        return test.PASS()
