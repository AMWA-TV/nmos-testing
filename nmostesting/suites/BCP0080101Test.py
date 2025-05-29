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
from jinja2 import Template
from random import randint
from requests.compat import json
from uuid import uuid4
from .BCP008Test import BCP008Test, NcLinkStatus, NcOverallStatus, NcStatusMonitorProperties, NcSynchronizationStatus
from ..GenericTest import NMOSTestException
from ..TestHelper import get_default_ip
from ..MS05Utils import NcMethodId, NcPropertyId
from .. import Config as CONFIG

RECEIVER_MONITOR_API_KEY = "receivermonitor"
RECEIVER_MONITOR_CLASS_ID = [1, 2, 2, 1]
RECEIVER_MONITOR_SPEC_ROOT = "https://specs.amwa.tv/bcp-008-01/branches/"


class NcReceiverMonitorProperties(Enum):
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


class NcConnectionStatus(IntEnum):
    Inactive = 0
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


class BCP0080101Test(BCP008Test):
    """
    Runs Tests covering BCP-008-01
    """

    def __init__(self, apis, **kwargs):
        BCP008Test.__init__(self, apis, **kwargs)
        self.sdp_params = None

    def _make_receiver_sdp_params(self, test):
        rtp_receivers = []
        # For each receiver in the NuT make appropriate SDP params
        valid, resources = self.do_request("GET", self.node_url + "receivers")
        if not valid:
            return False, f"Node API did not respond as expected: {resources}"

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
            dst_ip = f"232.40.50.{randint(1, 254)}"
            dst_port = (randint(5000, 5999) >> 1) << 1  # Choose a random even port

            sdp_params[receiver["id"]] = template.render({**CONFIG.SDP_PREFERENCES,
                                                          'src_ip': src_ip,
                                                          'dst_ip': dst_ip,
                                                          'dst_port': dst_port,
                                                          'media_subtype': media_subtype
                                                          }
                                                         )

        return sdp_params

    # Overloaded function to get Receiver Monitors
    # Spec link getters
    def get_touchpoint_spec_link(self):
        return f"{RECEIVER_MONITOR_SPEC_ROOT}{self.apis[RECEIVER_MONITOR_API_KEY]['spec_branch']}" \
            "/docs/Overview.html#touchpoints-and-is-04-receivers"

    def get_transition_counters_spec_link(self):
        return f"{RECEIVER_MONITOR_SPEC_ROOT}{self.apis[RECEIVER_MONITOR_API_KEY]['spec_branch']}" \
            "/docs/Overview.html#receiver-status-transition-counters"

    def get_reporting_delay_spec_link(self):
        return f"{RECEIVER_MONITOR_SPEC_ROOT}{self.apis[RECEIVER_MONITOR_API_KEY]['spec_branch']}" \
            "/docs/Overview.html#receiver-status-reporting-delay"

    def get_deactivating_monitor_spec_link(self):
        return f"{RECEIVER_MONITOR_SPEC_ROOT}{self.apis[RECEIVER_MONITOR_API_KEY]['spec_branch']}" \
            "/docs/Overview.html#deactivating-a-receiver"

    def get_sync_source_change_spec_link(self):
        return f"{RECEIVER_MONITOR_SPEC_ROOT}{self.apis[RECEIVER_MONITOR_API_KEY]['spec_branch']}" \
            "/docs/Overview.html#synchronization-source-change"

    def get_worker_inheritance_spec_link(self):
        return f"{RECEIVER_MONITOR_SPEC_ROOT}{self.apis[RECEIVER_MONITOR_API_KEY]['spec_branch']}" \
            "/docs/Overview.html#ncworker-inheritance"

    def get_counter_method_spec_link(self):
        return f"{RECEIVER_MONITOR_SPEC_ROOT}{self.apis[RECEIVER_MONITOR_API_KEY]['spec_branch']}" \
            "/docs/Overview.html#late-and-lost-packets"

    # Status property and method IDs
    def get_domain_statuses(self):
        return [NcStatusMonitorProperties.OVERALL_STATUS,
                NcReceiverMonitorProperties.LINK_STATUS,
                NcReceiverMonitorProperties.CONNECTION_STATUS,
                NcReceiverMonitorProperties.EXTERNAL_SYNCHRONIZATION_STATUS,
                NcReceiverMonitorProperties.STREAM_STATUS]

    def get_connection_status_property_id(self):
        return NcReceiverMonitorProperties.CONNECTION_STATUS.value

    def get_connection_status_transition_counter_property_id(self):
        return NcReceiverMonitorProperties.CONNECTION_STATUS_TRANSITION_COUNTER.value

    def get_inactiveable_status_property_ids(self):
        return [NcStatusMonitorProperties.OVERALL_STATUS.value,
                NcReceiverMonitorProperties.CONNECTION_STATUS.value,
                NcReceiverMonitorProperties.STREAM_STATUS.value]

    def get_auto_reset_counter_property_id(self):
        return NcReceiverMonitorProperties.AUTO_RESET_COUNTERS.value

    def get_sync_source_id_property_id(self):
        return NcReceiverMonitorProperties.SYNCHRONIZATION_SOURCE_ID.value

    def get_healthy_statuses_dict(self):
        return {NcStatusMonitorProperties.OVERALL_STATUS.value: NcOverallStatus.Healthy,
                NcReceiverMonitorProperties.CONNECTION_STATUS.value: NcConnectionStatus.Healthy,
                NcReceiverMonitorProperties.STREAM_STATUS.value: NcStreamStatus.Healthy}

    def get_inactive_statuses_dict(self):
        return {NcStatusMonitorProperties.OVERALL_STATUS.value: NcOverallStatus.Inactive,
                NcReceiverMonitorProperties.CONNECTION_STATUS.value: NcConnectionStatus.Inactive,
                NcReceiverMonitorProperties.STREAM_STATUS.value: NcStreamStatus.Inactive}

    def get_transition_counter_property_map(self):
        # Ignore late and lost packets in this check:
        # late and lost packet counters increment independantly of these tests and therefore
        # cannot be predicted or their value guaranteed at any given time
        return {"LinkStatusTransitionCounter":
                NcReceiverMonitorProperties.LINK_STATUS_TRANSITION_COUNTER,
                "ConnectionStatusTransitionCounter":
                NcReceiverMonitorProperties.CONNECTION_STATUS_TRANSITION_COUNTER,
                "ExternalSynchronizationStatusTransitionCounter":
                NcReceiverMonitorProperties.EXTERNAL_SYNCHRONIZATION_STATUS_TRANSITION_COUNTER,
                "StreamStatusTransitionCounter":
                NcReceiverMonitorProperties.STREAM_STATUS_TRANSITION_COUNTER}

    def get_counter_method_ids(self):
        return [NcReceiverMonitorMethods.GET_LOST_PACKET_COUNTERS,
                NcReceiverMonitorMethods.GET_LATE_PACKET_COUNTERS]

    def get_auto_reset_counter_method_id(self):
        return NcReceiverMonitorMethods.RESET_COUNTERS

    # Resource
    def get_monitors(self, test):
        if len(self.resource_monitors):
            return self.resource_monitors

        device_model = self.is12_utils.query_device_model(test)

        self.resource_monitors = device_model.find_members_by_class_id(RECEIVER_MONITOR_CLASS_ID,
                                                                       include_derived=True,
                                                                       recurse=True,
                                                                       get_objects=True)

        return self.resource_monitors

    def get_touchpoint_resource_type(self):
        return "receiver"

    def patch_resource(self, test, receiver_id):
        if not self.sdp_params:
            self.sdp_params = self._make_receiver_sdp_params(test)

        url = f"single/receivers/{receiver_id}/staged"
        activate_json = {"activation": {"mode": "activate_immediate"},
                         "master_enable": True,
                         "sender_id": str(uuid4()),
                         "transport_file": {"data": self.sdp_params[receiver_id], "type": "application/sdp"}}

        valid, response = self.is05_utils.checkCleanRequestJSON("PATCH", url, activate_json)
        if not valid:
            raise NMOSTestException(test.FAIL(f"Error patching Receiver {str(response)}"))

    def deactivate_resource(self, test, resource_id):
        url = f"single/receivers/{resource_id}/staged"
        deactivate_json = {"master_enable": False, 'sender_id': None,
                           "activation": {"mode": "activate_immediate"}}

        valid, response = self.is05_utils.checkCleanRequestJSON("PATCH", url, deactivate_json)
        if not valid:
            raise NMOSTestException(test.FAIL(f"Error patching Receiver {str(response)}"))

    # Validation
    def is_valid_resource(self, test, touchpoint_resource):
        if not self.sdp_params:
            self.sdp_params = self._make_receiver_sdp_params(test)

        if touchpoint_resource is None or touchpoint_resource.resource["id"] not in self.sdp_params:
            return False

        return True

    def check_overall_status(self, monitor, statuses):
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
                and statuses[NcStatusMonitorProperties.OVERALL_STATUS] != NcOverallStatus.Inactive.value:
            self.check_overall_status_metadata.error = True
            self.check_overall_status_metadata.error_msg += \
                "Overall Status expected to be Inactive when Connection Status is Inactive, " \
                f"actual Overall Status {NcOverallStatus(statuses[NcStatusMonitorProperties.OVERALL_STATUS]).name}" \
                " for Monitor, " \
                f"oid={monitor.oid}, role path={monitor.role_path}; "

        if statuses[NcReceiverMonitorProperties.STREAM_STATUS] == NcStreamStatus.Inactive.value \
                and statuses[NcStatusMonitorProperties.OVERALL_STATUS] != NcOverallStatus.Inactive.value:
            self.check_overall_status_metadata.error = True
            self.check_overall_status_metadata.error_msg += \
                "Overall Status expected to be Inactive when Stream Status is Inactive, " \
                f"actual Overall Status {NcOverallStatus(statuses[NcStatusMonitorProperties.OVERALL_STATUS]).name}" \
                " for Monitor, " \
                f"oid={monitor.oid}, role path={monitor.role_path}; "

        # Test Active states
        if statuses[NcReceiverMonitorProperties.CONNECTION_STATUS] != NcConnectionStatus.Inactive.value \
                and statuses[NcReceiverMonitorProperties.STREAM_STATUS] != NcStreamStatus.Inactive.value:
            least_healthy_state = max([status for property_id, status in statuses.items()
                                       if property_id != NcStatusMonitorProperties.OVERALL_STATUS])
            if statuses[NcStatusMonitorProperties.OVERALL_STATUS] != least_healthy_state:
                self.check_overall_status_metadata.error = True
                self.check_overall_status_metadata.error_msg += \
                    f"Expected Overall Status was {NcOverallStatus(least_healthy_state).name}, " \
                    f"actual {NcOverallStatus(statuses[NcStatusMonitorProperties.OVERALL_STATUS]).name} " \
                    f"for Monitor, oid={monitor.oid}, " \
                    f"role path={monitor.role_path}; "

        self.check_overall_status_metadata.checked = True

    def validate_status_values(self, monitor, statuses):
        spec_link_root = f"{RECEIVER_MONITOR_SPEC_ROOT}{self.apis[RECEIVER_MONITOR_API_KEY]['spec_branch']}" \
            "/docs/Overview.html#"
        invalid_statuses = []
        for property_id, status in statuses.items():
            if property_id == NcStatusMonitorProperties.OVERALL_STATUS:
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
                f"for Monitor, oid={monitor.oid}, " \
                f"role path={monitor.role_path}; "
            self.check_status_values_valid_metadata.link = f"{spec_link_root}{spec_section}"
        else:
            self.check_status_values_valid_metadata.checked = True

    # BCP-008-01 only tests

    def test_16(self, test):
        """Late packet counter increment when presentation is affected by packet arrival errors"""
        # For implementations which cannot measure individual late packets the late counters
        # MUST at the very least increment every time the presentation is affected due to late packet arrival.

        return test.MANUAL("Check by manually forcing an error condition")

    def test_17(self, test):
        """Late and lost packet counters are reset when a client invokes the ResetCounters method"""

        return test.MANUAL("Check manually")
