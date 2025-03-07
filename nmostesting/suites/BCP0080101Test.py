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

from enum import Enum
from jinja2 import Template
from random import randint
from requests.compat import json
from time import sleep, time

from ..GenericTest import GenericTest, NMOSTestException
from ..IS05Utils import IS05Utils
from ..IS12Utils import IS12Utils
from ..MS05Utils import NcMethodStatus, NcObjectProperties, NcPropertyId, NcTouchpointNmos
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
    CONNECTION_STATUS = NcPropertyId({"level": 4, "index": 3})
    CONNECTION_STATUS_MESSAGE = NcPropertyId({"level": 4, "index": 4})
    EXTERNAL_SYNCHRONIZATION_STATUS = NcPropertyId({"level": 4, "index": 5})
    EXTERNAL_SYNCHRONIZATION_STATUS_MESSAGE = NcPropertyId({"level": 4, "index": 6})
    SYNCHRONIZATION_SOURCE_ID = NcPropertyId({"level": 4, "index": 7})
    SYNCHRONIZATION_SOURCE_CHANGES = NcPropertyId({"level": 4, "index": 8})
    STREAM_STATUS = NcPropertyId({"level": 4, "index": 9})
    STREAM_STATUS_MESSAGE = NcPropertyId({"level": 4, "index": 10})
    AUTO_RESET_PACKET_COUNTERS = NcPropertyId({"level": 4, "index": 11})
    AUTO_RESET_SYNCHRONIZATION_SOURCE_CHANGES = NcPropertyId({"level": 4, "index": 12})
    UNKNOWN = NcPropertyId({"level": 9999, "index": 9999})

    @classmethod
    def _missing_(cls, _):
        return cls.UNKNOWN


class NcOverallStatus(Enum):
    Inactive = 0
    Healthy = 1
    PartiallyHealthy = 2
    Unhealthy = 3


class NcLinkStatus(Enum):
    AllUp = 1
    SomeDown = 2
    AllDown = 3


class NcConnectionStatus(Enum):
    Inactive = 0
    Healthy = 1
    PartiallyHealthy = 2
    Unhealthy = 3


class NcSynchronizationStatus(Enum):
    NotUsed = 0
    Healthy = 1
    PartiallyHealthy = 2
    Unhealthy = 3


class NcStreamStatus(Enum):
    Inactive = 0
    Healthy = 1
    PartiallyHealthy = 2
    Unhealthy = 3


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
        GenericTest.__init__(self, apis, omit_paths, **kwargs)
        self.is12_utils = IS12Utils(apis)
        # Instantiate MS0501Tests to access automatic tests
        # Hmmm, should the automatic tests be factored into the utils to allow all
        # MS-05 based test suites to access them?
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
        self.check_initial_healthy_state_metadata = BCP0080101Test.TestMetadata()
        self.check_touchpoint_metadata = BCP0080101Test.TestMetadata()
        self.check_overall_status_metadata = BCP0080101Test.TestMetadata()

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
            "/Overview.html#touchpoints-and-is-04-receivers"

        touchpoint_resources = []

        touchpoints = self._get_property(test, NcObjectProperties.TOUCHPOINTS.value, oid, role_path)

        for touchpoint in touchpoints:
            if "contextNamespace" not in touchpoint:
                self.check_touchpoint_metadata.error = True
                self.check_touchpoint_metadata.error_msg = "Touchpoint doesn't obey MS-05-02 schema"
                self.check_touchpoint_metadata.link = f"{CONTROL_FRAMEWORK_SPEC_ROOT}" \
                    f"{self.apis[RECEIVER_MONITOR_API_KEY]['spec_branch']}/Framework.html#nctouchpoint"
                continue

            if "resource" in touchpoint:
                touchpoint_resources.append(touchpoint)

        if len(touchpoint_resources) != 1:
            self.check_touchpoint_metadata.error = True
            self.check_touchpoint_metadata.error_msg = "One and only one touchpoint MUST be of type NcTouchpointNmos"
            self.check_touchpoint_metadata.link = spec_link
            return None

        touchpoint_resource = NcTouchpointNmos(touchpoint_resources[0])

        if touchpoint_resource.resource["resourceType"] != "receiver":
            self.check_touchpoint_metadata.error = True
            self.check_touchpoint_metadata.error_msg = "Touchpoint resourceType field MUST be set to 'receiver'"
            self.check_touchpoint_metadata.link = spec_link
            return None

        self.check_touchpoint_metadata.checked = True

        return touchpoint_resource

    def _get_status_from_notifications(self, initial_status, notifications, property_id):
        # Aggregate initial status with any status change notifications
        status_notifications = [n for n in notifications if n.eventData.propertyId == property_id.value]

        return status_notifications[-1].eventData.value if len(status_notifications) else initial_status

    def _check_overall_status(self, initial_statuses, notifications):

        statuses = dict([(property_id,
                          self._get_status_from_notifications(initial_status, notifications, property_id))
                        for property_id, initial_status in initial_statuses.items()])

        # Test Inactive states
        if statuses[NcReceiverMonitorProperties.CONNECTION_STATUS] == NcConnectionStatus.Inactive.value \
                and statuses[NcReceiverMonitorProperties.OVERALL_STATUS] != NcOverallStatus.Inactive.value:
            self.check_overall_status_metadata.error = True
            self.check_overall_status_metadata.error_msg += \
                "Overall Status expected to be Inactive when Connection Status is Inactive. "

        if statuses[NcReceiverMonitorProperties.STREAM_STATUS] == NcStreamStatus.Inactive.value \
                and statuses[NcReceiverMonitorProperties.OVERALL_STATUS] != NcOverallStatus.Inactive.value:
            self.check_overall_status_metadata.error = True
            self.check_overall_status_metadata.error_msg += \
                "Overall Status expected to be Inactive when Stream Status is Inactive. "

        # Test Active states
        if statuses[NcReceiverMonitorProperties.CONNECTION_STATUS] != NcConnectionStatus.Inactive.value \
                and statuses[NcReceiverMonitorProperties.STREAM_STATUS] != NcStreamStatus.Inactive.value:
            least_healthy_state = max([status for property_id, status in statuses.items()
                                       if property_id != NcReceiverMonitorProperties.OVERALL_STATUS])
            if statuses[NcReceiverMonitorProperties.OVERALL_STATUS] != least_healthy_state:
                self.check_overall_status_metadata.error = True
                self.check_overall_status_metadata.error_msg += \
                    f"Expected Overall Status was {NcOverallStatus(least_healthy_state).name}, " \
                    f"actual {NcOverallStatus(statuses[NcReceiverMonitorProperties.OVERALL_STATUS]).name}. "

        self.check_overall_status_metadata.checked = True

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

        if self.check_initial_healthy_state_metadata.checked:
            return

        receiver_monitors = self._get_receiver_monitors(test)

        if len(receiver_monitors) > 0:
            self.testable_receivers_found = True
        else:
            return

        sdp_params = self._make_receiver_sdp_params(test)

        status_properties = [NcReceiverMonitorProperties.OVERALL_STATUS,
                             NcReceiverMonitorProperties.LINK_STATUS,
                             NcReceiverMonitorProperties.CONNECTION_STATUS,
                             NcReceiverMonitorProperties.EXTERNAL_SYNCHRONIZATION_STATUS,
                             NcReceiverMonitorProperties.STREAM_STATUS]

        for monitor in receiver_monitors:

            # Hmmmmm this is misspelled - change in the IS-12 PR and merge
            response = self.is12_utils.update_subscritions(test, [monitor.oid])

            if not isinstance(response, list):
                raise NMOSTestException(
                    test.FAIL(f"Unexpected response from subscription command: {str(response)}",
                              f"{CONTROL_PROTOCOL_SPEC_ROOT}{self.apis[CONTROL_API_KEY]['spec_branch']}"
                              "/docs/Protocol_messaging.html#subscription-response-message-type"))

            # Capture initial states of monitor statuses
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
                continue

            receiver_id = touchpoint_resource.resource["id"]

            if initial_statuses[NcReceiverMonitorProperties.OVERALL_STATUS] != NcOverallStatus.Inactive.value:
                # This test depends on the receiver being inactive in the first instance
                self._deactivate_receiver(test, receiver_id)

            # Assume that the receiver patch happens immediately after start_time
            start_time = time()

            self._patch_receiver(test, receiver_id, sdp_params[receiver_id])

            # Wait until one second more that status reporting delay to capture transition to less healthy state
            sleep(status_reporting_delay + 1.0)

            # Now process historic, time stamped, notifications
            notifications = self.is12_utils.get_notifications()

            # Check overall status before receiver patched
            status_notifications = [n for n in notifications if n.received_time < start_time]
            self._check_overall_status(initial_statuses, status_notifications)

            # Check overall status during status reporting delay
            status_notifications = \
                [n for n in notifications if n.received_time < start_time + status_reporting_delay]

            self._check_overall_status(initial_statuses, status_notifications)

            # Check overall status after status reporting delay
            status_notifications = \
                [n for n in notifications if n.received_time >= start_time + status_reporting_delay]
            self._check_overall_status(initial_statuses, status_notifications)

            connection_status_notifications = \
                [n for n in notifications
                 if n.eventData.propertyId == NcReceiverMonitorProperties.CONNECTION_STATUS.value
                 and n.received_time >= start_time]

            if len(connection_status_notifications) == 0:
                self.check_initial_healthy_state_metadata.error = True
                self.check_initial_healthy_state_metadata.error_msg += \
                    "No status notifications received for receiver monitor=" \
                    f"oid={monitor.oid}, role path={self.is12_utils.create_role_path_string(monitor.role_path)}; "

            # Check that the receiver monitor transitioned to healthy
            if len(connection_status_notifications) > 0 \
                    and connection_status_notifications[0].eventData.value != NcConnectionStatus.Healthy.value:
                self.check_initial_healthy_state_metadata.error = True
                self.check_initial_healthy_state_metadata.error_msg += \
                    "Expect status to transition to healthy for Receiver Monitor " \
                    f"oid={monitor.oid}, role path={self.is12_utils.create_role_path_string(monitor.role_path)}; "

            # Check that the receiver monitor stayed in the healthy state (unless transitioned to Inactive)
            # during the status reporting delay period
            if len(connection_status_notifications) > 1 \
                    and connection_status_notifications[1].eventData.value != NcConnectionStatus.Inactive.value \
                    and connection_status_notifications[1].received_time < start_time + status_reporting_delay:
                self.check_initial_healthy_state_metadata.error = True
                self.check_initial_healthy_state_metadata.error_msg += \
                    "Expect status to remain healthy for at least the status reporting delay for receiver monitor=" \
                    f"oid={monitor.oid}, role path={self.is12_utils.create_role_path_string(monitor.role_path)}; "

            # There is no *actual* stream so we expect connection to transition
            # to a less healthy state after the status reporting delay
            # i.e. expecting transition to healthy and then to less healthy (at least 2 transitions)
            if len(connection_status_notifications) < 2:
                self.check_initial_healthy_state_metadata.error = True
                self.check_initial_healthy_state_metadata.error_msg += \
                    "Expect status to transition to a less healthy state after " \
                    "status reporting delay for receiver monitor, " \
                    f"oid={monitor.oid}, role path={self.is12_utils.create_role_path_string(monitor.role_path)}; "

            self.check_initial_healthy_state_metadata.checked = True
            self._deactivate_receiver(test, receiver_id)

    def test_01(self, test):
        """Status reporting delay can be set to values within the published constraints"""
        receiver_monitors = self._get_receiver_monitors(test)

        if len(receiver_monitors) == 0:
            return test.UNCLEAR("No receiver monitors found in Device Model")

        default_status_reporting_delay = 3
        for monitor in receiver_monitors:
            method_result = self.is12_utils.set_property(
                test, NcReceiverMonitorProperties.STATUS_REPORTING_DELAY.value,
                default_status_reporting_delay,
                oid=monitor.oid, role_path=monitor.role_path)

            if not self._status_ok(method_result):
                return test.FAIL("SetProperty error: Error setting statusReportingDelay on receiver monitor, "
                                 f"oid={monitor.oid}, "
                                 f"role path={self.is12_utils.create_role_path_string(monitor.role_path)}")

            method_result = self.is12_utils.get_property(
                test, NcReceiverMonitorProperties.STATUS_REPORTING_DELAY.value,
                oid=monitor.oid, role_path=monitor.role_path)

            if not self._status_ok(method_result):
                return test.FAIL("GetProperty error: Error getting statusReportingDelay on receiver monitor, "
                                 f"oid={monitor.oid}, "
                                 f"role path={self.is12_utils.create_role_path_string(monitor.role_path)}")

            if method_result.value != default_status_reporting_delay:
                return test.FAIL("Unexpected statusReportingDelay on receiver monitor. "
                                 f"Expected={default_status_reporting_delay} actual={method_result.value}, "
                                 f"oid={monitor.oid}, "
                                 f"role path={self.is12_utils.create_role_path_string(monitor.role_path)}")

        return test.PASS()

    def test_02(self, test):
        """Receiver monitor transitions to Healthy state on activation"""

        self._check_monitor_status_changes(test)

        if not self.testable_receivers_found:
            return test.UNCLEAR("Unable to find any testable receiver monitors")

        if not self.check_initial_healthy_state_metadata.checked:
            return test.UNCLEAR("Unable to test receiver monitors")

        if self.check_initial_healthy_state_metadata.error:
            return test.FAIL(self.check_initial_healthy_state_metadata.error_msg)

        return test.PASS()

    def test_03(self, test):
        """Receiver monitor delays transition to more healthy states by status reporting delay"""

        return test.MANUAL("Check by manually forcing an error condition in the Receiver")

    def test_04(self, test):
        """Overall status is correctly mapped from domain statuses"""

        self._check_monitor_status_changes(test)

        if not self.testable_receivers_found:
            return test.UNCLEAR("Unable to find any testable receiver monitors")

        if not self.check_overall_status_metadata.checked:
            return test.UNCLEAR("Unable to check overall status mapping")

        if self.check_overall_status_metadata.error:
            return test.FAIL(self.check_overall_status_metadata.error_msg)

        return test.PASS()
