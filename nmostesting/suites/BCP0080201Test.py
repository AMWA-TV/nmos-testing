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
from .BCP008Test import BCP008Test, NcLinkStatus, NcOverallStatus, NcStatusMonitorProperties, NcSynchronizationStatus
from ..GenericTest import NMOSTestException
from ..MS05Utils import NcMethodId, NcPropertyId

SENDER_MONITOR_API_KEY = "sendermonitor"
SENDER_MONITOR_SPEC_ROOT = "https://specs.amwa.tv/bcp-008-02/branches/"
SENDER_MONITOR_CLASS_ID = [1, 2, 2, 2]


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


class NcTransmissionStatus(IntEnum):
    Inactive = 0
    Healthy = 1
    PartiallyHealthy = 2
    Unhealthy = 3
    UNKNOWN = 9999

    @classmethod
    def _missing_(cls, _):
        return cls.UNKNOWN


class NcEssenceStatus(IntEnum):
    Inactive = 0
    Healthy = 1
    PartiallyHealthy = 2
    Unhealthy = 3
    UNKNOWN = 9999

    @classmethod
    def _missing_(cls, _):
        return cls.UNKNOWN


class BCP0080201Test(BCP008Test):
    """
    Runs Tests covering BCP-008-02
    """

    def __init__(self, apis, **kwargs):
        BCP008Test.__init__(self, apis, **kwargs)

    # Overloaded function to get Sender Monitors
    # Spec link getters
    def get_touchpoint_spec_link(self):
        return f"{SENDER_MONITOR_SPEC_ROOT}{self.apis[SENDER_MONITOR_API_KEY]['spec_branch']}" \
            "/docs/Overview.html#touchpoints-and-is-04-receivers"

    def get_transition_counters_spec_link(self):
        return f"{SENDER_MONITOR_SPEC_ROOT}{self.apis[SENDER_MONITOR_API_KEY]['spec_branch']}" \
            "/docs/Overview.html#sender-status-transition-counters"

    def get_status_messages_spec_link(self):
        return f"{SENDER_MONITOR_SPEC_ROOT}{self.apis[SENDER_MONITOR_API_KEY]['spec_branch']}" \
            "/docs/Overview.html#sender-status-messages"

    def get_reporting_delay_spec_link(self):
        return f"{SENDER_MONITOR_SPEC_ROOT}{self.apis[SENDER_MONITOR_API_KEY]['spec_branch']}" \
            "/docs/Overview.html#sender-status-reporting-delay"

    def get_deactivating_monitor_spec_link(self):
        return f"{SENDER_MONITOR_SPEC_ROOT}{self.apis[SENDER_MONITOR_API_KEY]['spec_branch']}" \
            "/docs/Overview.html#deactivating-a-sender"

    def get_sync_source_change_spec_link(self):
        return f"{SENDER_MONITOR_SPEC_ROOT}{self.apis[SENDER_MONITOR_API_KEY]['spec_branch']}" \
            "/docs/Overview.html#synchronization-source-change"

    def get_counter_method_spec_link(self):
        return f"{SENDER_MONITOR_SPEC_ROOT}{self.apis[SENDER_MONITOR_API_KEY]['spec_branch']}" \
            "/docs/Overview.html#transmission-error-counters"

    # Status property and method IDs
    def get_domain_statuses(self):
        return [NcStatusMonitorProperties.OVERALL_STATUS,
                NcSenderMonitorProperties.LINK_STATUS,
                NcSenderMonitorProperties.TRANSMISSION_STATUS,
                NcSenderMonitorProperties.EXTERNAL_SYNCHRONIZATION_STATUS,
                NcSenderMonitorProperties.ESSENCE_STATUS]

    def get_stream_status_property_id(self):
        return NcSenderMonitorProperties.TRANSMISSION_STATUS.value

    def get_stream_status_transition_counter_property_id(self):
        return NcSenderMonitorProperties.TRANSMISSION_STATUS_TRANSITION_COUNTER.value

    def get_inactiveable_status_property_ids(self):
        return [NcStatusMonitorProperties.OVERALL_STATUS.value,
                NcSenderMonitorProperties.TRANSMISSION_STATUS.value,
                NcSenderMonitorProperties.ESSENCE_STATUS.value]

    def get_auto_reset_counter_property_id(self):
        return NcSenderMonitorProperties.AUTO_RESET_COUNTERS.value

    def get_sync_source_id_property_id(self):
        return NcSenderMonitorProperties.SYNCHRONIZATION_SOURCE_ID.value

    def get_healthy_statuses_dict(self):
        return {NcStatusMonitorProperties.OVERALL_STATUS.value: NcOverallStatus.Healthy,
                NcSenderMonitorProperties.TRANSMISSION_STATUS.value: NcTransmissionStatus.Healthy,
                NcSenderMonitorProperties.ESSENCE_STATUS.value: NcEssenceStatus.Healthy}

    def get_inactive_statuses_dict(self):
        return {NcStatusMonitorProperties.OVERALL_STATUS.value: NcOverallStatus.Inactive,
                NcSenderMonitorProperties.TRANSMISSION_STATUS.value: NcTransmissionStatus.Inactive,
                NcSenderMonitorProperties.ESSENCE_STATUS.value: NcEssenceStatus.Inactive}

    def get_transition_counter_property_dict(self):
        # Ignore tranmission error counter in this check:
        # tranmission error counter increments independantly of these tests and therefore
        # cannot be predicted or its value guaranteed at any given time
        return {"LinkStatusTransitionCounter":
                NcSenderMonitorProperties.LINK_STATUS_TRANSITION_COUNTER.value,
                "TransmissionStatusTransitionCounter":
                NcSenderMonitorProperties.TRANSMISSION_STATUS_TRANSITION_COUNTER.value,
                "ExternalSynchronizationStatusTransitionCounter":
                NcSenderMonitorProperties.EXTERNAL_SYNCHRONIZATION_STATUS_TRANSITION_COUNTER.value,
                "EssenceStatusTransitionCounter":
                NcSenderMonitorProperties.ESSENCE_STATUS_TRANSITION_COUNTER.value}

    def get_status_message_property_dict(self):
        return {"OverallStatusMessage":
                NcStatusMonitorProperties.OVERALL_STATUS_MESSAGE.value,
                "LinkStatusMessage":
                NcSenderMonitorProperties.LINK_STATUS_MESSAGE.value,
                "TransmissionStatusMessage":
                NcSenderMonitorProperties.TRANSMISSION_STATUS_MESSAGE.value,
                "ExternalSynchronizationStatusMessage":
                NcSenderMonitorProperties.EXTERNAL_SYNCHRONIZATION_STATUS_MESSAGE.value,
                "EssenceStatusMessage":
                NcSenderMonitorProperties.ESSENCE_STATUS_MESSAGE.value}

    def get_counter_method_ids(self):
        return [NcSenderMonitorMethods.GET_TRANSMISSION_ERROR_COUNTERS]

    def get_reset_counter_method_id(self):
        return NcSenderMonitorMethods.RESET_COUNTERS

    # Resource
    def get_monitors(self, test):
        if len(self.resource_monitors):
            return self.resource_monitors

        device_model = self.is12_utils.query_device_model(test)

        self.resource_monitors = device_model.find_members_by_class_id(SENDER_MONITOR_CLASS_ID,
                                                                       include_derived=True,
                                                                       recurse=True,
                                                                       get_objects=True)

        return self.resource_monitors

    def get_touchpoint_resource_type(self):
        return "sender"

    def activate_resource(self, test, sender_id):
        activate_json = {
            "receiver_id": None,
            "master_enable": True,
            "activation": {
                "mode": "activate_immediate",
                "requested_time": None
            }
        }

        url = f"single/senders/{sender_id}/staged"

        valid, response = self.is05_utils.checkCleanRequestJSON("PATCH", url, activate_json)
        if not valid:
            raise NMOSTestException(test.FAIL(f"Error patching Sender. {str(response)}"))

    def deactivate_resource(self, test, resource_id):
        url = "single/senders/{}/staged".format(resource_id)
        deactivate_json = {"master_enable": False, 'receiver_id': None,
                           "activation": {"mode": "activate_immediate"}}

        valid, response = self.is05_utils.checkCleanRequestJSON("PATCH", url, deactivate_json)
        if not valid:
            raise NMOSTestException(test.FAIL(f"Error patching Receiver {str(response)}"))

    # Validation
    def is_valid_resource(self, test, touchpoint_resource):
        # Check it's an RTP resource
        if touchpoint_resource is not None:
            url = f"single/senders/{touchpoint_resource.resource['id']}/transporttype"

            valid, response = self.is05_utils.checkCleanRequestJSON("GET", url)
            if not valid:
                return False

            return response == "urn:x-nmos:transport:rtp"

        return False

    def check_overall_status(self, monitor, statuses):
        # Devices MUST follow the rules listed below when mapping specific domain statuses
        # in the combined overallStatus:
        # * When the Sender is Inactive the overallStatus uses the Inactive option
        # * When the Sedner is Active the overallStatus takes the least healthy state of all domain statuses
        #   (if one status is PartiallyHealthy (or equivalent) and another is Unhealthy (or equivalent)
        #   then the overallStatus would be Unhealthy)
        # * The overallStatus is Healthy only when all domain statuses are either Healthy or a neutral state
        #   (e.g. Not used, Inactive)
        self.check_overall_status_metadata.link = \
            f"{SENDER_MONITOR_SPEC_ROOT}{self.apis[SENDER_MONITOR_API_KEY]['spec_branch']}" \
            "/docs/Overview.html#sender-overall-status"

        # Test Inactive states
        if statuses[NcSenderMonitorProperties.TRANSMISSION_STATUS] == NcTransmissionStatus.Inactive.value \
                and statuses[NcStatusMonitorProperties.OVERALL_STATUS] != NcOverallStatus.Inactive.value:
            self.check_overall_status_metadata.error = True
            self.check_overall_status_metadata.error_msg += \
                "Overall Status expected to be Inactive when Connection Status is Inactive, " \
                f"actual Overall Status {NcOverallStatus(statuses[NcStatusMonitorProperties.OVERALL_STATUS]).name}" \
                " for Monitor, " \
                f"oid={monitor.oid}, role path={monitor.role_path}; "

        if statuses[NcSenderMonitorProperties.ESSENCE_STATUS] == NcEssenceStatus.Inactive.value \
                and statuses[NcStatusMonitorProperties.OVERALL_STATUS] != NcOverallStatus.Inactive.value:
            self.check_overall_status_metadata.error = True
            self.check_overall_status_metadata.error_msg += \
                "Overall Status expected to be Inactive when Stream Status is Inactive, " \
                f"actual Overall Status {NcOverallStatus(statuses[NcStatusMonitorProperties.OVERALL_STATUS]).name}" \
                " for Monitor, " \
                f"oid={monitor.oid}, role path={monitor.role_path}; "

        # Test Active states
        if statuses[NcSenderMonitorProperties.TRANSMISSION_STATUS] != NcTransmissionStatus.Inactive.value \
                and statuses[NcSenderMonitorProperties.ESSENCE_STATUS] != NcEssenceStatus.Inactive.value:
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
        spec_link_root = f"{SENDER_MONITOR_SPEC_ROOT}{self.apis[SENDER_MONITOR_API_KEY]['spec_branch']}" \
            "/docs/Overview.html#"
        invalid_statuses = []
        for property_id, status in statuses.items():
            if property_id == NcStatusMonitorProperties.OVERALL_STATUS:
                if NcOverallStatus(status) == NcOverallStatus.UNKNOWN:
                    invalid_statuses.append("overallStatus")
                    spec_section = "receiver-overall-status"
            elif property_id == NcSenderMonitorProperties.LINK_STATUS:
                if NcLinkStatus(status) == NcLinkStatus.UNKNOWN:
                    invalid_statuses.append("linkStatus")
                    spec_section = "link-status"
            elif property_id == NcSenderMonitorProperties.TRANSMISSION_STATUS:
                if NcTransmissionStatus(status) == NcTransmissionStatus.UNKNOWN:
                    invalid_statuses.append("transmissionStatus")
                    spec_section = "transmission-status"
            elif property_id == NcSenderMonitorProperties.EXTERNAL_SYNCHRONIZATION_STATUS:
                if NcSynchronizationStatus(status) == NcSynchronizationStatus.UNKNOWN:
                    invalid_statuses.append("externalSynchronizationStatus")
                    spec_section = "external-synchronization-status"
            elif property_id == NcSenderMonitorProperties.ESSENCE_STATUS:
                if NcEssenceStatus(status) == NcEssenceStatus.UNKNOWN:
                    invalid_statuses.append("essenceStatus")
                    spec_section = "essence-status"
        if len(invalid_statuses) > 0:
            self.check_status_values_valid_metadata.error = True
            self.check_status_values_valid_metadata.error_msg += \
                f"Invalid status found in following properties: {', '.join(invalid_statuses)} " \
                f"for Monitor, oid={monitor.oid}, " \
                f"role path={monitor.role_path}; "
            self.check_status_values_valid_metadata.link = f"{spec_link_root}{spec_section}"
        else:
            self.check_status_values_valid_metadata.checked = True

    # BCP-008-02

    def test_15(self, test):
        """Transmission error counter is reset when a client invokes the ResetCounters method"""

        return test.MANUAL("Check manually")
