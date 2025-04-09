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


import uuid

from enum import Enum, IntEnum
from jinja2 import Template
from random import randint
from requests.compat import json
from time import sleep, time

from ..GenericTest import GenericTest, NMOSTestException
from ..IS05Utils import IS05Utils
from ..IS12Utils import IS12Utils
from ..MS05Utils import NcMethodId, NcMethodStatus, NcObjectProperties, NcPropertyId, NcTouchpointNmos, \
    NcWorkerProperties
from ..TestHelper import get_default_ip, get_mocks_hostname

from .. import Config as CONFIG

RECEIVER_MONITOR_API_KEY = "receivermonitor"
NODE_API_KEY = "node"
CONN_API_KEY = "connection"
CONTROL_API_KEY = "ncp"
CONTROL_FRAMEWORK_API_KEY = "controlframework"

RECEIVER_MONITOR_CLASS_ID = [1, 2, 2, 1]

RECEIVER_MONITOR_SPEC_ROOT = "https://specs.amwa.tv/bcp-008-01/branches/"
CONTROL_FRAMEWORK_SPEC_ROOT = "https://specs.amwa.tv/ms-05-02/branches/"
CONTROL_PROTOCOL_SPEC_ROOT = "https://specs.amwa.tv/is-12/branches/"


class NcReceiverMonitorProperties(Enum):
    # NcStatusMonitor properties
    OVERALL_STATUS = NcPropertyId({"level": 3, "index": 1})
    OVERALL_STATUS_MESSAGE = NcPropertyId({"level": 3, "index": 2})
    STATUS_REPORTING_DELAY = NcPropertyId({"level": 3, "index": 3})

    # NcReceiverMonitor properties
    LINK_STATUS = NcPropertyId({"level": 4, "index": 1})
    LINK_STATUS_MESSAGE = NcPropertyId({"level": 4, "index": 2})
    LINK_STATUS_TRANSITION_COUNTER = NcPropertyId({"level": 4, "index": 3})
    CONNECTION_STATUS = NcPropertyId({"level": 4, "index": 4})
    CONNECTION_STATUS_MESSAGE = NcPropertyId({"level": 4, "index": 5})
    CONNECTION_STATUS_TRANSITION_COUNTER = NcPropertyId({"level": 4, "index": 6})
    EXTERNAL_SYNCHRONIZATION_STATUS = NcPropertyId({"level": 4, "index": 7})
    EXTERNAL_SYNCHRONIZATION_STATUS_MESSAGE = NcPropertyId({"level": 4, "index": 8})
    EXTERNAL_SYNCHRONIZATION_STATUS_TRANSITION_COUNTER = NcPropertyId({"level": 4, "index": 9})
    SYNCHRONIZATION_SOURCE_ID = NcPropertyId({"level": 4, "index": 10})
    STREAM_STATUS = NcPropertyId({"level": 4, "index": 11})
    STREAM_STATUS_MESSAGE = NcPropertyId({"level": 4, "index": 12})
    STREAM_STATUS_TRANSITION_COUNTER = NcPropertyId({"level": 4, "index": 13})
    AUTO_RESET_COUNTERS = NcPropertyId({"level": 4, "index": 14})


class NcReceiverMonitorMethods(Enum):
    GET_LOST_PACKET_COUNTERS = NcMethodId({"level": 4, "index": 1})
    GET_LATE_PACKET_COUNTERS = NcMethodId({"level": 4, "index": 2})
    RESET_COUNTERS = NcMethodId({"level": 4, "index": 3})


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


class BCP0080101Test(GenericTest):
    """
    Runs Tests covering BCP-008-01
    """
    class TestMetadata():
        def __init__(self, checked=False, error=False, error_msg="", link=""):
            self.checked = checked
            self.error = error
            self.error_msg = error_msg
            self.link = link

    def __init__(self, apis, node, **kwargs):
        # Don't auto-test /transportfile as it is permitted to generate a 404 when master_enable is false
        omit_paths = [
            "/single/senders/{senderId}/transportfile"
        ]
        # Prevent auto testing of IS-04 and IS-05 APIs
        apis[NODE_API_KEY].pop("raml", None)
        apis[CONN_API_KEY].pop("raml", None)
        GenericTest.__init__(self, apis, omit_paths, **kwargs)
        self.is12_utils = IS12Utils(apis)
        self.is05_utils = IS05Utils(self.apis[CONN_API_KEY]["url"])
        self.node_url = apis[NODE_API_KEY]["url"]
        self.ncp_url = apis[CONTROL_API_KEY]["url"]
        self.is04_receivers = []
        self.receiver_monitors = []
        self.mock_node = node
        self.mock_node_base_url = ""

    def set_up_tests(self):
        self.is12_utils.reset()
        self.is12_utils.open_ncp_websocket()
        super().set_up_tests()

        # Configure mock node url
        host = get_mocks_hostname() if CONFIG.ENABLE_HTTPS else get_default_ip()
        self.mock_node_base_url = self.protocol + '://' + host + ':' + str(self.mock_node.port) + '/'

        self.testable_receivers_found = False
        # Initialize cached test results
        self.check_connection_status_metadata = BCP0080101Test.TestMetadata()
        self.check_touchpoint_metadata = BCP0080101Test.TestMetadata()
        self.check_overall_status_metadata = BCP0080101Test.TestMetadata()
        self.check_status_values_valid_metadata = BCP0080101Test.TestMetadata()
        self.check_deactivate_receiver_metadata = BCP0080101Test.TestMetadata()
        self.check_reset_counters_metadata = BCP0080101Test.TestMetadata()
        self.check_transitions_counted_metadata = BCP0080101Test.TestMetadata()
        self.check_auto_reset_counters_metadata = BCP0080101Test.TestMetadata()

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

    def _get_receiver_monitors(self, test):
        if len(self.receiver_monitors):
            return self.receiver_monitors

        device_model = self.is12_utils.query_device_model(test)

        self.receiver_monitors = device_model.find_members_by_class_id(RECEIVER_MONITOR_CLASS_ID,
                                                                       include_derived=True,
                                                                       recurse=True,
                                                                       get_objects=True)

        return self.receiver_monitors

    def _make_receiver_sdp_params(self, test):

        rtp_receivers = []
        # For each receiver in the NuT make appropriate SDP params
        valid, resources = self.do_request("GET", self.node_url + "receivers")
        if not valid:
            return False, "Node API did not respond as expected: {}".format(resources)

        try:
            for resource in resources.json():
                if resource["transport"].startswith("urn:x-nmos:transport:rtp"):
                    rtp_receivers.append(resource)
        except json.JSONDecodeError:
            raise NMOSTestException(test.FAIL("Non-JSON response returned from Node API"))

        sdp_templates = {}
        sdp_templates["raw"] = open("test_data/sdp/video-2022-7.sdp").read()
        sdp_templates["jxsv"] = open("test_data/sdp/video-jxsv.sdp").read()
        sdp_templates["audio"] = open("test_data/sdp/audio.sdp").read()
        sdp_templates["smpte291"] = open("test_data/sdp/data.sdp").read()
        sdp_templates["SMPTE2022-6"] = open("test_data/sdp/mux.sdp").read()

        default_media_types = {}
        default_media_types["urn:x-nmos:format:video"] = "video/raw"
        default_media_types["urn:x-nmos:format:audio"] = "audio/L24"
        default_media_types["urn:x-nmos:format:data"] = "video/smpte291"
        default_media_types["urn:x-nmos:format:mux"] = "video/SMPTE2022-6"

        sdp_params = {}

        for receiver in rtp_receivers:
            caps = receiver["caps"]

            if receiver["format"] in default_media_types.keys():
                media_type = caps["media_types"][0] \
                    if "media_types" in caps else default_media_types[receiver["format"]]
            else:
                continue

            supported_media_types = [
                "video/raw",
                "video/jxsv",
                "audio/L16",
                "audio/L24",
                "audio/L32",
                "video/smpte291",
                "video/SMPTE2022-6"
            ]
            if media_type not in supported_media_types:
                continue

            media_type, media_subtype = media_type.split("/")

            if media_type == "video" and media_subtype in sdp_templates.keys():
                template_file = sdp_templates[media_subtype]
            elif media_type == "audio" and media_subtype in ["L16", "L24", "L32"]:
                template_file = sdp_templates["audio"]
            else:
                continue

            template = Template(template_file, keep_trailing_newline=True)

            src_ip = get_default_ip()
            dst_ip = "232.40.50.{}".format(randint(1, 254))
            dst_port = randint(5000, 5999)

            sdp_params[receiver["id"]] = template.render({**CONFIG.SDP_PREFERENCES,
                                                          'src_ip': src_ip,
                                                          'dst_ip': dst_ip,
                                                          'dst_port': dst_port,
                                                          'media_subtype': media_subtype
                                                          }
                                                         )

        return sdp_params

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
        # The touchpoints property of any NcReceiverMonitor MUST have one or more touchpoints of which
        # one and only one entry MUST be of type NcTouchpointNmos where
        # the resourceType field MUST be set to "receiver" and
        # the id field MUST be set to the associated IS-04 receiver UUID.
        spec_link = f"{RECEIVER_MONITOR_SPEC_ROOT}{self.apis[RECEIVER_MONITOR_API_KEY]['spec_branch']}" \
            "/docs/Overview.html#touchpoints-and-is-04-receivers"

        touchpoint_resources = []

        touchpoints = self._get_property(test, NcObjectProperties.TOUCHPOINTS.value, oid, role_path)

        for touchpoint in touchpoints:
            if "contextNamespace" not in touchpoint:
                self.check_touchpoint_metadata.error = True
                self.check_touchpoint_metadata.error_msg = "Touchpoint doesn't obey MS-05-02 schema " \
                    f"for Receiver Monitor, oid={oid}, " \
                    f"role path={role_path}; "
                self.check_touchpoint_metadata.link = f"{CONTROL_FRAMEWORK_SPEC_ROOT}" \
                    f"{self.apis[RECEIVER_MONITOR_API_KEY]['spec_branch']}/Framework.html#nctouchpoint"
                continue

            if "resource" in touchpoint:
                touchpoint_resources.append(touchpoint)

        if len(touchpoint_resources) != 1:
            self.check_touchpoint_metadata.error = True
            self.check_touchpoint_metadata.error_msg = "One and only one touchpoint MUST be of type NcTouchpointNmos " \
                f"for Receiver Monitor, oid={oid}, " \
                f"role path={role_path}; "
            self.check_touchpoint_metadata.link = spec_link
            return None

        touchpoint_resource = NcTouchpointNmos(touchpoint_resources[0])

        if touchpoint_resource.resource["resourceType"] != "receiver":
            self.check_touchpoint_metadata.error = True
            self.check_touchpoint_metadata.error_msg = "Touchpoint resourceType field MUST be set to 'receiver' " \
                f"for Receiver Monitor, oid={oid}, " \
                f"role path={role_path}; "
            self.check_touchpoint_metadata.link = spec_link
            return None

        self.check_touchpoint_metadata.checked = True

        return touchpoint_resource

    def _validate_status_values(self, statuses, oid, role_path):

        spec_link_root = f"{RECEIVER_MONITOR_SPEC_ROOT}{self.apis[RECEIVER_MONITOR_API_KEY]['spec_branch']}" \
            "/docs/Overview.html#"
        invalid_statuses = []
        for property_id, status in statuses.items():
            if property_id == NcReceiverMonitorProperties.OVERALL_STATUS:
                if NcOverallStatus(status) == NcOverallStatus.UNKNOWN:
                    invalid_statuses.append("overallStatus")
                    spec_section = "receiver-overall-status"
            elif property_id == NcReceiverMonitorProperties.LINK_STATUS:
                if NcLinkStatus(status) == NcLinkStatus.UNKNOWN:
                    invalid_statuses.append("linkStatus")
                    spec_section = "link-status"
            elif property_id == NcReceiverMonitorProperties.CONNECTION_STATUS:
                if NcConnectionStatus(status) == NcConnectionStatus.UNKNOWN:
                    invalid_statuses.append("connectionStatus")
                    spec_section = "connection-status"
            elif property_id == NcReceiverMonitorProperties.EXTERNAL_SYNCHRONIZATION_STATUS:
                if NcSynchronizationStatus(status) == NcSynchronizationStatus.UNKNOWN:
                    invalid_statuses.append("externalSynchronizationStatus")
                    spec_section = "external-synchronization-status"
            elif property_id == NcReceiverMonitorProperties.STREAM_STATUS:
                if NcStreamStatus(status) == NcStreamStatus.UNKNOWN:
                    invalid_statuses.append("streamStatus")
                    spec_section = "stream-status"
        if len(invalid_statuses) > 0:
            self.check_status_values_valid_metadata.error = True
            self.check_status_values_valid_metadata.error_msg = \
                f"Invalid status found in following properties: {', '.join(invalid_statuses)} " \
                f"for Receiver Monitor, oid={oid}, " \
                f"role path={role_path}; "
            self.check_status_values_valid_metadata.link = f"{spec_link_root}{spec_section}"
        else:
            self.check_status_values_valid_metadata.checked = True

    def _check_overall_status(self, statuses, oid, role_path):
        # Devices MUST follow the rules listed below when mapping specific domain statuses
        # in the combined overallStatus:
        # * When the Receiver is Inactive the overallStatus uses the Inactive option
        # * When the Receiver is Active the overallStatus takes the least healthy state of all domain statuses
        #   (if one status is PartiallyHealthy (or equivalent) and another is Unhealthy (or equivalent)
        #   then the overallStatus would be Unhealthy)
        # * The overallStatus is Healthy only when all domain statuses are either Healthy or a neutral state
        #   (e.g. Not used, Inactive)
        self.check_overall_status_metadata.link = \
            f"{RECEIVER_MONITOR_SPEC_ROOT}{self.apis[RECEIVER_MONITOR_API_KEY]['spec_branch']}" \
            "/docs/Overview.html#receiver-overall-status"

        # Test Inactive states
        if statuses[NcReceiverMonitorProperties.CONNECTION_STATUS] == NcConnectionStatus.Inactive.value \
                and statuses[NcReceiverMonitorProperties.OVERALL_STATUS] != NcOverallStatus.Inactive.value:
            self.check_overall_status_metadata.error = True
            self.check_overall_status_metadata.error_msg += \
                "Overall Status expected to be Inactive when Connection Status is Inactive, " \
                f"actual Overall Status {NcOverallStatus(statuses[NcReceiverMonitorProperties.OVERALL_STATUS]).name}" \
                " for Receiver Monitor, " \
                f"oid={oid}, role path={role_path}; "

        if statuses[NcReceiverMonitorProperties.STREAM_STATUS] == NcStreamStatus.Inactive.value \
                and statuses[NcReceiverMonitorProperties.OVERALL_STATUS] != NcOverallStatus.Inactive.value:
            self.check_overall_status_metadata.error = True
            self.check_overall_status_metadata.error_msg += \
                "Overall Status expected to be Inactive when Stream Status is Inactive, " \
                f"actual Overall Status {NcOverallStatus(statuses[NcReceiverMonitorProperties.OVERALL_STATUS]).name}" \
                " for Receiver Monitor, " \
                f"oid={oid}, role path={role_path}; "

        # Test Active states
        if statuses[NcReceiverMonitorProperties.CONNECTION_STATUS] != NcConnectionStatus.Inactive.value \
                and statuses[NcReceiverMonitorProperties.STREAM_STATUS] != NcStreamStatus.Inactive.value:
            least_healthy_state = max([status for property_id, status in statuses.items()
                                       if property_id != NcReceiverMonitorProperties.OVERALL_STATUS])
            if statuses[NcReceiverMonitorProperties.OVERALL_STATUS] != least_healthy_state:
                self.check_overall_status_metadata.error = True
                self.check_overall_status_metadata.error_msg += \
                    f"Expected Overall Status was {NcOverallStatus(least_healthy_state).name}, " \
                    f"actual {NcOverallStatus(statuses[NcReceiverMonitorProperties.OVERALL_STATUS]).name} " \
                    f"for Receiver Monitor, oid={oid}, " \
                    f"role path={role_path}; "

        self.check_overall_status_metadata.checked = True

    def _check_statuses(self, initial_statuses, notifications, oid, role_path):

        def _get_status_from_notifications(initial_status, notifications, property_id):
            # Aggregate initial status with any status change notifications
            status_notifications = [n for n in notifications if n.eventData.propertyId == property_id.value]

            return status_notifications[-1].eventData.value if len(status_notifications) else initial_status

        # Get statuses from notifications, using the initial_status as a default
        statuses = dict([(property_id,
                          _get_status_from_notifications(initial_status, notifications, property_id))
                        for property_id, initial_status in initial_statuses.items()])

        self._check_overall_status(statuses, oid, role_path)
        self._validate_status_values(statuses, oid, role_path)

    def _check_connection_status(self, monitor, start_time, status_reporting_delay, notifications):
        # A receiver is expected to go through a period of instability upon activation.
        # Therefore, on Receiver activation domain specific statuses offering an Inactive option
        # MUST transition immediately to the Healthy state. Furthermore, after activation,
        # as long as the Receiver isn’t being deactivated, it MUST delay the reporting of
        # non Healthy states for the duration specified by statusReportingDelay, and then
        # transition to any other appropriate state.
        connection_status_notifications = \
            [n for n in notifications
                if n.eventData.propertyId == NcReceiverMonitorProperties.CONNECTION_STATUS.value
                and n.received_time >= start_time]

        self.check_connection_status_metadata.link = \
            f"{RECEIVER_MONITOR_SPEC_ROOT}{self.apis[RECEIVER_MONITOR_API_KEY]['spec_branch']}" \
            "/docs/Overview.html#receiver-status-reporting-delay"

        if len(connection_status_notifications) == 0:
            self.check_connection_status_metadata.error = True
            self.check_connection_status_metadata.error_msg += \
                "No status notifications received for Receiver Monitor, " \
                f"oid={monitor.oid}, role path={monitor.role_path}; "
            return

        # Check that the receiver monitor transitioned to healthy
        if len(connection_status_notifications) > 0 \
                and connection_status_notifications[0].eventData.value != NcConnectionStatus.Healthy.value:
            self.check_connection_status_metadata.error = True
            self.check_connection_status_metadata.error_msg += \
                "Expect status to transition to healthy for Receiver Monitor, " \
                f"oid={monitor.oid}, role path={monitor.role_path}; "

        # Check that the receiver monitor stayed in the healthy state (unless transitioned to Inactive)
        # during the status reporting delay period
        if len(connection_status_notifications) > 1 \
                and connection_status_notifications[1].eventData.value != NcConnectionStatus.Inactive.value \
                and connection_status_notifications[1].received_time < start_time + status_reporting_delay:
            self.check_connection_status_metadata.error = True
            self.check_connection_status_metadata.error_msg += \
                "Expect status to remain healthy for at least the status reporting delay for Receiver Monitor, " \
                f"oid={monitor.oid}, role path={monitor.role_path}; "

        # There is no *actual* stream so we expect connection to transition
        # to a less healthy state after the status reporting delay
        # i.e. expecting transition to healthy and then to less healthy (at least 2 transitions)
        if len(connection_status_notifications) < 2:
            self.check_connection_status_metadata.error = True
            self.check_connection_status_metadata.error_msg += \
                "Expect status to transition to a less healthy state after " \
                "status reporting delay for Receiver Monitor, " \
                f"oid={monitor.oid}, role path={monitor.role_path}; "

        self.check_connection_status_metadata.checked = True

    def _check_connection_status_transition_counter(self, monitor, start_time, notifications):

        connection_status_transition_counter_notifications = \
            [n for n in notifications
                if n.eventData.propertyId == NcReceiverMonitorProperties.CONNECTION_STATUS_TRANSITION_COUNTER.value
                and n.eventData.value > 0]

        # Given the transition to a less healthy state we expect the transition counter to increment
        if len(connection_status_transition_counter_notifications) == 0:
            self.check_transitions_counted_metadata.error = True
            self.check_transitions_counted_metadata.error_msg += \
                "Expect transition counter to increment on less healthy state transition " \
                "for Receiver Monitor, " \
                f"oid={monitor.oid}, role path={monitor.role_path}; "

        self.check_transitions_counted_metadata.checked = True

    def _check_deactivate_receiver(self, test, monitor_oid, monitor_role_path, receiver_id, sdp_params):
        # When a receiver is being deactivated it MUST cleanly disconnect from the current stream by not
        # generating intermediate unhealthy states (PartiallyHealthy or Unhealthy) and instead transition
        # directly and immediately (without being delayed by the statusReportingDelay)
        # to Inactive for the following statuses:
        # * overallStatus
        # * connectionStatus
        # * streamStatus

        # Check deactivation of receiver during status replorting delay
        start_time = time()

        self._patch_receiver(test, receiver_id, sdp_params)

        # Deactivate before the status reporting delay expires
        sleep(1.0)
        self._deactivate_receiver(test, receiver_id)
        sleep(1.0)  # Let receiver settle

        # Process time stamped notifications
        notifications = self.is12_utils.get_notifications()

        deactivate_receiver_notifications = [n for n in notifications if n.received_time >= start_time]

        self.check_deactivate_receiver_metadata.link = \
            f"{RECEIVER_MONITOR_SPEC_ROOT}{self.apis[RECEIVER_MONITOR_API_KEY]['spec_branch']}" \
            "/docs/Overview.html#deactivating-a-receiver"

        status_properties = [NcReceiverMonitorProperties.OVERALL_STATUS,
                             NcReceiverMonitorProperties.CONNECTION_STATUS,
                             NcReceiverMonitorProperties.STREAM_STATUS]

        for status in status_properties:
            filtered_notifications = \
                    [n for n in deactivate_receiver_notifications
                     if n.eventData.propertyId == status.value]

            self.check_deactivate_receiver_metadata.link = \
                f"{RECEIVER_MONITOR_SPEC_ROOT}{self.apis[RECEIVER_MONITOR_API_KEY]['spec_branch']}" \
                "/docs/Overview.html#deactivating-a-receiver"

            if len(filtered_notifications) == 0:
                self.check_deactivate_receiver_metadata.error = True
                self.check_deactivate_receiver_metadata.error_msg += \
                    "No status notifications received for Receiver Monitor, " \
                    f"oid={monitor_oid}, role path={monitor_role_path}; "

            # Check that the receiver monitor transitioned to inactive
            if len(filtered_notifications) > 0 \
                    and filtered_notifications[-1].eventData.value != NcConnectionStatus.Inactive.value:
                self.check_deactivate_receiver_metadata.error = True
                self.check_deactivate_receiver_metadata.error_msg += \
                    "Expect status to transition to Inactive for Receiver Monitor, " \
                    f"oid={monitor_oid}, role path={monitor_role_path}; "

            self.check_deactivate_receiver_metadata.checked = True

    def _get_non_zero_counters(self, test, monitor):
        # Ignore late and lost packets in this check:
        # late and lost packet counters increment independantly of these tests and therefore
        # cannot be predicted or their value guaranteed at any given time
        transition_counters = {"LinkStatusTransitionCounter":
                               NcReceiverMonitorProperties.LINK_STATUS_TRANSITION_COUNTER,
                               "ConnectionStatusTransitionCounter":
                               NcReceiverMonitorProperties.CONNECTION_STATUS_TRANSITION_COUNTER,
                               "ExternalSynchronizationStatusTransitionCounter":
                               NcReceiverMonitorProperties.EXTERNAL_SYNCHRONIZATION_STATUS_TRANSITION_COUNTER,
                               "StreamStatusTransitionCounter":
                               NcReceiverMonitorProperties.STREAM_STATUS_TRANSITION_COUNTER}
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
        self.check_reset_counters_metadata.link = \
            f"{RECEIVER_MONITOR_SPEC_ROOT}{self.apis[RECEIVER_MONITOR_API_KEY]['spec_branch']}" \
            "/docs/Overview.html#receiver-status-transition-counters"

        non_zero_counters = self._get_non_zero_counters(test, monitor)

        if len(non_zero_counters) == 0:
            return  # No transitions, so can't test

        arguments = {}

        # Invoke ResetCounters
        method_result = self.is12_utils.invoke_method(
            test,
            NcReceiverMonitorMethods.RESET_COUNTERS.value,
            arguments,
            oid=monitor.oid,
            role_path=monitor.role_path)

        if not self._status_ok(method_result):
            self.check_reset_counters_metadata.error = True
            self.check_reset_counters_metadata.error_msg = \
                "Method invokation ResetCounters failed for Receiver Monitor, " \
                f"oid={monitor.oid}, role path={monitor.role_path}: " \
                f"{method_result.errorMessage}. "
            return

        non_zero_counters = self._get_non_zero_counters(test, monitor)

        if len(non_zero_counters) > 0:
            self.check_reset_counters_metadata.error = True
            self.check_reset_counters_metadata.error_msg = \
                f"Transition counters {', '.join(non_zero_counters)} not reset for Receiver Monitor, " \
                f"oid={monitor.oid}, role path={monitor.role_path}: "

        self.check_reset_counters_metadata.checked = True

    def _check_auto_reset_counters(self, test, monitor, receiver_id, sdp_params):
        # Devices MUST be able to reset ALL status transition counter properties
        # when a receiver activation occurs if autoResetCounters is set to true
        self.check_auto_reset_counters_metadata.link = \
            f"{RECEIVER_MONITOR_SPEC_ROOT}{self.apis[RECEIVER_MONITOR_API_KEY]['spec_branch']}" \
            "/docs/Overview.html#receiver-status-transition-counters"

        # Make sure autoResetCounters enabled
        self._set_property(test,
                           NcReceiverMonitorProperties.AUTO_RESET_COUNTERS.value,
                           True,
                           oid=monitor.oid,
                           role_path=monitor.role_path)

        # generate status transitions
        status_reporting_delay = \
            self._get_property(test,
                               NcReceiverMonitorProperties.STATUS_REPORTING_DELAY.value,
                               oid=monitor.oid,
                               role_path=monitor.role_path)
        self._patch_receiver(test, receiver_id, sdp_params)
        sleep(status_reporting_delay + 1.0)  # This assumes the connection status becomes unhealty
        self._deactivate_receiver(test, receiver_id)

        # check for status transitions
        non_zero_counters = self._get_non_zero_counters(test, monitor)

        if len(non_zero_counters) == 0:
            return  # No transitions, so can't test

        # force auto reset
        self._patch_receiver(test, receiver_id, sdp_params)
        sleep(1.0)  # Settling time

        non_zero_counters = self._get_non_zero_counters(test, monitor)

        if len(non_zero_counters) > 0:
            self.check_auto_reset_counters_metadata.error = True
            self.check_auto_reset_counters_metadata.error_msg = \
                f"Transition counters {', '.join(non_zero_counters)} not reset for Receiver Monitor, " \
                f"oid={monitor.oid}, " \
                f"role path={monitor.role_path}: "

        self.check_auto_reset_counters_metadata.checked = True

        self._deactivate_receiver(test, receiver_id)

    def _patch_receiver(self, test, receiver_id, sdp_params):
        url = "single/receivers/{}/staged".format(receiver_id)
        activate_json = {"activation": {"mode": "activate_immediate"},
                         "master_enable": True,
                         "sender_id": str(uuid.uuid4()),
                         "transport_file": {"data": sdp_params, "type": "application/sdp"}}

        valid, response = self.is05_utils.checkCleanRequestJSON("PATCH", url, activate_json)
        if not valid:
            raise NMOSTestException(test.FAIL("Error patching Receiver " + str(response)))

    def _deactivate_receiver(self, test, receiver_id):
        url = "single/receivers/{}/staged".format(receiver_id)
        deactivate_json = {"master_enable": False, 'sender_id': None,
                           "activation": {"mode": "activate_immediate"}}

        valid, response = self.is05_utils.checkCleanRequestJSON("PATCH", url, deactivate_json)
        if not valid:
            raise NMOSTestException(test.FAIL("Error patching Receiver " + str(response)))

    def _check_monitor_status_changes(self, test):

        if self.check_connection_status_metadata.checked:
            return

        all_receiver_monitors = self._get_receiver_monitors(test)

        if len(all_receiver_monitors) > 0:
            self.testable_receivers_found = True
        else:
            return

        receiver_monitors = IS12Utils.sampled_list(all_receiver_monitors)

        sdp_params = self._make_receiver_sdp_params(test)

        status_properties = [NcReceiverMonitorProperties.OVERALL_STATUS,
                             NcReceiverMonitorProperties.LINK_STATUS,
                             NcReceiverMonitorProperties.CONNECTION_STATUS,
                             NcReceiverMonitorProperties.EXTERNAL_SYNCHRONIZATION_STATUS,
                             NcReceiverMonitorProperties.STREAM_STATUS]

        for monitor in receiver_monitors:

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
                               NcReceiverMonitorProperties.STATUS_REPORTING_DELAY.value,
                               status_reporting_delay,
                               oid=monitor.oid,
                               role_path=monitor.role_path)

            # Get associated receiver for this receiver monitor
            touchpoint_resource = self._get_touchpoint_resource(test,
                                                                monitor.oid,
                                                                monitor.role_path)

            if touchpoint_resource is None or touchpoint_resource.resource["id"] not in sdp_params:
                # Can't find the resource
                continue

            receiver_id = touchpoint_resource.resource["id"]

            if initial_statuses[NcReceiverMonitorProperties.OVERALL_STATUS] != NcOverallStatus.Inactive.value:
                # This test depends on the receiver being inactive in the first instance
                self._deactivate_receiver(test, receiver_id)
                sleep(2.0)  # settling time
                initial_statuses = dict([(property_id,
                                          self._get_property(test,
                                                             property_id.value,
                                                             role_path=monitor.role_path,
                                                             oid=monitor.oid))
                                         for property_id in status_properties])

            # Assume that the receiver patch happens immediately after start_time
            start_time = time()

            self._patch_receiver(test, receiver_id, sdp_params[receiver_id])

            # Wait until one second more that status reporting delay to capture transition to less healthy state
            sleep(status_reporting_delay + 2.0)

            # Ensure ResetCounter method resets counters to zero
            self._check_reset_counters(test, monitor)

            # Now process historic, time stamped, notifications
            notifications = self.is12_utils.get_notifications()

            # Check statuses before receiver patched
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

            self._check_connection_status_transition_counter(monitor, start_time, notifications)

            self._deactivate_receiver(test, receiver_id)
            sleep(2.0)  # Let receiver settle

            self._check_deactivate_receiver(test, monitor.oid, monitor.role_path, receiver_id, sdp_params[receiver_id])

            self._check_auto_reset_counters(test, monitor, receiver_id, sdp_params[receiver_id])

    def test_01(self, test):
        """Status reporting delay can be set to values within the published constraints"""
        receiver_monitors = self._get_receiver_monitors(test)

        if len(receiver_monitors) == 0:
            return test.UNCLEAR("No Receiver Monitors found in Device Model")

        default_status_reporting_delay = 3
        for monitor in receiver_monitors:
            method_result = self.is12_utils.set_property(
                test, NcReceiverMonitorProperties.STATUS_REPORTING_DELAY.value,
                default_status_reporting_delay,
                oid=monitor.oid, role_path=monitor.role_path)

            if not self._status_ok(method_result):
                return test.FAIL("SetProperty error: Error setting statusReportingDelay on receiver monitor, "
                                 f"oid={monitor.oid}, "
                                 f"role path={monitor.role_path}")

            method_result = self.is12_utils.get_property(
                test, NcReceiverMonitorProperties.STATUS_REPORTING_DELAY.value,
                oid=monitor.oid, role_path=monitor.role_path)

            if not self._status_ok(method_result):
                return test.FAIL("GetProperty error: Error getting statusReportingDelay on receiver monitor, "
                                 f"oid={monitor.oid}, "
                                 f"role path={monitor.role_path}")

            if method_result.value != default_status_reporting_delay:
                return test.FAIL("Unexpected status reporting delay on receiver monitor. "
                                 f"Expected={default_status_reporting_delay} actual={method_result.value}, "
                                 f"oid={monitor.oid}, "
                                 f"role path={monitor.role_path}")

        return test.PASS()

    def test_02(self, test):
        """Receiver monitor transitions to Healthy state on activation"""

        self._check_monitor_status_changes(test)

        if not self.testable_receivers_found:
            return test.UNCLEAR("Unable to find any testable Receiver Monitors")

        if not self.check_connection_status_metadata.checked:
            return test.UNCLEAR("Unable to test")

        if self.check_connection_status_metadata.error:
            return test.FAIL(self.check_connection_status_metadata.error_msg,
                             self.check_connection_status_metadata.link)

        return test.PASS()

    def test_03(self, test):
        """Receiver monitor delays transition to more healthy states by status reporting delay"""

        return test.MANUAL("Check by manually forcing an error condition in the Receiver")

    def test_04(self, test):
        """Transitions to less healthy states are counted"""

        self._check_monitor_status_changes(test)

        if not self.testable_receivers_found:
            return test.UNCLEAR("Unable to find any testable Receiver Monitors")

        if not self.check_transitions_counted_metadata.checked:
            return test.UNCLEAR("Unable to test")

        if self.check_transitions_counted_metadata.error:
            return test.FAIL(self.check_transitions_counted_metadata.error_msg,
                             self.check_transitions_counted_metadata.link)

        return test.PASS()

    def test_05(self, test):
        """ResetCounters method resets status transition counters"""

        self._check_monitor_status_changes(test)

        if not self.testable_receivers_found:
            return test.UNCLEAR("Unable to find any testable Receiver Monitors")

        if not self.check_reset_counters_metadata.checked:
            return test.UNCLEAR("Unable to test")

        if self.check_reset_counters_metadata.error:
            return test.FAIL(self.check_reset_counters_metadata.error_msg,
                             self.check_reset_counters_metadata.link)

        return test.PASS()

    def test_06(self, test):
        """autoResetCounters property set to TRUE resets status transition counters on activation"""

        self._check_monitor_status_changes(test)

        if not self.testable_receivers_found:
            return test.UNCLEAR("Unable to find any testable Receiver Monitors")

        if not self.check_auto_reset_counters_metadata.checked:
            return test.UNCLEAR("Unable to test")

        if self.check_auto_reset_counters_metadata.error:
            return test.FAIL(self.check_auto_reset_counters_metadata.error_msg,
                             self.check_auto_reset_counters_metadata.link)

        return test.PASS()

    def test_07(self, test):
        """Overall status is correctly mapped from domain statuses"""

        self._check_monitor_status_changes(test)

        if not self.testable_receivers_found:
            return test.UNCLEAR("Unable to find any testable Receiver Monitors")

        if not self.check_overall_status_metadata.checked:
            return test.UNCLEAR("Unable to test")

        if self.check_overall_status_metadata.error:
            return test.FAIL(self.check_overall_status_metadata.error_msg,
                             self.check_overall_status_metadata.link)

        return test.PASS()

    def test_08(self, test):
        """Status values are valid"""

        self._check_monitor_status_changes(test)

        if not self.testable_receivers_found:
            return test.UNCLEAR("Unable to find any testable Receiver Monitors")

        if not self.check_status_values_valid_metadata.checked:
            return test.UNCLEAR("Unable to test")

        if self.check_status_values_valid_metadata.error:
            return test.FAIL(self.check_status_values_valid_metadata.error_msg,
                             self.check_status_values_valid_metadata.link)

        return test.PASS()

    def _check_late_lost_packet_method(self, test, method_id):
        """Check late or lost packet method depending on method_id"""
        spec_link = \
            f"{RECEIVER_MONITOR_SPEC_ROOT}{self.apis[RECEIVER_MONITOR_API_KEY]['spec_branch']}" \
            "/docs/Overview.html#late-and-lost-packets"

        receiver_monitors = self._get_receiver_monitors(test)

        if len(receiver_monitors) == 0:
            return test.UNCLEAR("No Receiver Monitors found in Device Model")

        arguments = {}  # empty arguments

        for monitor in receiver_monitors:
            method_result = self.is12_utils.invoke_method(
                test,
                method_id,
                arguments,
                oid=monitor.oid,
                role_path=monitor.role_path)

            if not self._status_ok(method_result):
                return test.FAIL("Method invokation GetLostPacketCounters failed for Receiver Monitor, "
                                 f"oid={monitor.oid}, "
                                 f"role path={monitor.role_path}: "
                                 f"{method_result.errorMessage}", spec_link)

            if method_result.value is None or not isinstance(method_result.value, list):
                return test.FAIL(f"Expected an array, got {str(method_result.value)} for Receiver Monitor, "
                                 f"oid={monitor.oid}, "
                                 f"role path={monitor.role_path}: ", spec_link)

            for counter in method_result.value:
                self.is12_utils.reference_datatype_schema_validate(test, counter, "NcCounter")

        return test.PASS()

    def test_09(self, test):
        """GetLostPacketCounters method is implemented"""
        return self._check_late_lost_packet_method(test, NcReceiverMonitorMethods.GET_LOST_PACKET_COUNTERS.value)

    def test_10(self, test):
        """GetLatePacketCounters method is implemented"""
        return self._check_late_lost_packet_method(test, NcReceiverMonitorMethods.GET_LATE_PACKET_COUNTERS.value)

    def test_11(self, test):
        """Late packet counter increments when presentation is affected by late packet arrival"""
        # For implementations which cannot measure individual late packets the late counters
        # MUST at the very least increment every time the presentation is affected due to late packet arrival.

        return test.MANUAL("Check by manually forcing an error condition in the Receiver")

    def test_12(self, test):
        """Receiver transitions to PartiallyHealthy on synchronization source change"""
        # Receivers MUST temporarily transition to PartiallyHealthy when detecting a synchronization source change

        return test.MANUAL("Check by manually forcing a synchronization source change in the Receiver")

    def test_13(self, test):
        """synchronizationSourceID property has a valid value"""
        # When devices intend to use external synchronization they MUST publish the synchronization source id
        # currently being used in the synchronizationSourceId property and update the externalSynchronizationStatus
        # property whenever it changes, setting the synchronizationSourceId to null if a synchronization source
        # cannot be discovered. Devices which are not intending to use external synchronization MUST populate
        # this property with 'internal' or their own id if they themselves are the synchronization source
        # (e.g. the device is a grandmaster).
        receiver_monitors = self._get_receiver_monitors(test)
        spec_link = \
            f"{RECEIVER_MONITOR_SPEC_ROOT}{self.apis[RECEIVER_MONITOR_API_KEY]['spec_branch']}" \
            "/docs/Overview.html#synchronization-source-change"

        if len(receiver_monitors) == 0:
            return test.UNCLEAR("No Receiver Monitors found in Device Model")

        for monitor in receiver_monitors:
            syncSourceId = self._get_property(test,
                                              NcReceiverMonitorProperties.SYNCHRONIZATION_SOURCE_ID.value,
                                              oid=monitor.oid,
                                              role_path=monitor.role_path)

            # Synchronization source id can be null, "internal" or some identifier, but it can't be empty
            if syncSourceId == "":
                return test.FAIL("Synchronization source id MUST be either null, 'internal' "
                                 "or an identifer for Receiver Monitor, "
                                 f"oid={monitor.oid}, "
                                 f"role path={monitor.role_path}.", spec_link)

        return test.PASS()

    def test_14(self, test):
        """Receiver cleanly disconnects from the current stream on deactivation"""

        self._check_monitor_status_changes(test)

        if not self.testable_receivers_found:
            return test.UNCLEAR("Unable to find any testable Receiver Monitors")

        if not self.check_deactivate_receiver_metadata.checked:
            return test.UNCLEAR("Unable to test")

        if self.check_deactivate_receiver_metadata.error:
            return test.FAIL(self.check_deactivate_receiver_metadata.error_msg,
                             self.check_deactivate_receiver_metadata.link)

        return test.PASS()

    def test_15(self, test):
        """Receiver monitor has a valid touchpoint resource"""

        self._check_monitor_status_changes(test)

        if not self.testable_receivers_found:
            return test.UNCLEAR("Unable to find any testable Receiver Monitors")

        if not self.check_touchpoint_metadata.checked:
            return test.UNCLEAR("Unable to test")

        if self.check_touchpoint_metadata.error:
            return test.FAIL(self.check_touchpoint_metadata.error_msg,
                             self.check_touchpoint_metadata.link)

        return test.PASS()

    def test_16(self, test):
        """enabled property is TRUE by default, and cannot be set to FALSE"""
        spec_link = \
            f"{RECEIVER_MONITOR_SPEC_ROOT}{self.apis[RECEIVER_MONITOR_API_KEY]['spec_branch']}" \
            "/docs/Overview.html#ncworker-inheritance"

        receiver_monitors = self._get_receiver_monitors(test)

        if len(receiver_monitors) == 0:
            return test.UNCLEAR("No Receiver Monitors found in Device Model")

        for monitor in receiver_monitors:
            enabled = self._get_property(test,
                                         NcWorkerProperties.ENABLED.value,
                                         oid=monitor.oid,
                                         role_path=monitor.role_path)

            if enabled is not True:
                return test.FAIL("Receiver Monitors MUST always have the enabled property set to true "
                                 f"for Receiver Monitor, oid={monitor.oid}, "
                                 f"role path={monitor.role_path}.", spec_link)

            method_result = self.is12_utils.set_property(test,
                                                         NcWorkerProperties.ENABLED.value,
                                                         False,
                                                         oid=monitor.oid,
                                                         role_path=monitor.role_path)

            if method_result.status == NcMethodStatus.OK:
                return test.FAIL("Receiver Monitors MUST NOT allow changes to the enabled property "
                                 f"for Receiver Monitor, oid={monitor.oid}, "
                                 f"role path={monitor.role_path}.", spec_link)

            if method_result.status != NcMethodStatus.InvalidRequest:
                return test.FAIL("Receiver Monitors MUST return InvalidRequest "
                                 "to Set method invocations for this property "
                                 f"for Receiver Monitor, oid={monitor.oid}, "
                                 f"role path={monitor.role_path}.", spec_link)
        return test.PASS()
