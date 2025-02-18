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
from .MS0501Test import MS0501Test

from .. import Config as CONFIG

NODE_API_KEY = "node"
CONN_API_KEY = "connection"
CONTROL_API_KEY = "ncp"
MS05_API_KEY = "controlframework"

RECEIVER_MONITOR_CLASS_ID = [1, 2, 2, 1]

bcp_008_01_spec_root = "https://specs.amwa.tv/bcp-008-01/branches/v1.0-dev/docs/"
ms_05_02_spec_root = "https://specs.amwa.tv/ms-05-02/branches/v1.0.x/docs/"


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


class NcConnectionStatus(Enum):
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
        GenericTest.__init__(self, apis, omit_paths, **kwargs)
        self.is12_utils = IS12Utils(apis)
        # Instantiate MS0501Tests to access automatic tests
        # Hmmm, should the automatic tests be factored into the utils to allow all
        # MS-05 based test suites to access them?
        self.ms0502Test = MS0501Test(apis, self.is12_utils, **kwargs)
        self.is05_utils = IS05Utils(self.apis[CONN_API_KEY]["url"])
        self.node_url = apis[NODE_API_KEY]["url"]
        self.ncp_url = apis[CONTROL_API_KEY]["url"]
        self.is04_receivers = []
        self.receiver_monitors = []
        self.mock_node = node
        self.mock_node_base_url = ""

    def set_up_tests(self):
        self.ms0502Test.set_up_tests()
        self.is12_utils.open_ncp_websocket()
        super().set_up_tests()

        # Configure mock node url
        host = get_mocks_hostname() if CONFIG.ENABLE_HTTPS else get_default_ip()
        self.mock_node_base_url = self.protocol + '://' + host + ':' + str(self.mock_node.port) + '/'

        # Initialize cached test results
        self.check_touchpoint_metadata = BCP0080101Test.TestMetadata()

    # Override basics to include the MS-05 auto tests
    def basics(self):
        results = super().basics()
        try:
            results += self.ms0502Test._auto_tests()
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

    def test_01(self, test):
        """Check that statusReportingDelay can be set to values within the published constraints"""
        receiver_monitors = self._get_receiver_monitors(test)

        if len(receiver_monitors) == 0:
            return test.UNCLEAR("No NcReceiverMonitors found in Device Model")

        default_status_reporting_delay = 3
        for monitor in receiver_monitors:
            method_result = self.is12_utils.set_property(
                test, NcReceiverMonitorProperties.STATUS_REPORTING_DELAY.value,
                default_status_reporting_delay,
                oid=monitor.oid, role_path=monitor.role_path)

            if not self._status_ok(method_result):
                return test.FAIL("SetProperty error: Error setting statusReportingDelay on ReceiverMonitor, "
                                 f"oid={monitor.oid}, role path={monitor.role_path}")

            method_result = self.is12_utils.get_property(
                test, NcReceiverMonitorProperties.STATUS_REPORTING_DELAY.value,
                oid=monitor.oid, role_path=monitor.role_path)

            if not self._status_ok(method_result):
                return test.FAIL("GetProperty error: Error getting statusReportingDelay on ReceiverMonitor, "
                                 f"oid={monitor.oid}, role path={monitor.role_path}")

            if method_result.value != default_status_reporting_delay:
                return test.FAIL("Unexpected statusReportingDelay on ReceiverMonitor. "
                                 f"Expected={default_status_reporting_delay} actual={method_result.value}, "
                                 f"oid={monitor.oid}, role path={monitor.role_path}")

        return test.PASS()

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
        # the resourceType field MUST be set to “receiver” and
        # the id field MUST be set to the associated IS-04 receiver UUID.
        spec_link = f"{bcp_008_01_spec_root}Overview.html#touchpoints-and-is-04-receivers"

        touchpoint_resources = []

        touchpoints = self._get_property(test, NcObjectProperties.TOUCHPOINTS.value, oid, role_path)

        for touchpoint in touchpoints:
            if "contextNamespace" not in touchpoint:
                self.check_touchpoint_metadata.error = True
                self.check_touchpoint_metadata.error_msg = "Touchpoint doesn't obey MS-05-02 schema"
                self.check_touchpoint_metadata.link = f"{ms_05_02_spec_root}Framework.html#nctouchpoint"
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

    def test_02(self, test):
        """Check Receiver Monitor transition to Healthy state"""

        checked = False

        sdp_params = self._make_receiver_sdp_params(test)

        for receiver_monitor in self._get_receiver_monitors(test):

            touchpoint_resource = self._get_touchpoint_resource(test,
                                                                receiver_monitor.oid,
                                                                receiver_monitor.role_path)

            if touchpoint_resource is None or touchpoint_resource.resource["id"] not in sdp_params:
                continue

            # Check initial connection status
            connection_status = self._get_property(test, NcReceiverMonitorProperties.CONNECTION_STATUS.value,
                                                   receiver_monitor.oid, receiver_monitor.role_path)

            if connection_status != NcConnectionStatus.Inactive.value:
                continue

            # Set status reporting delay to 3 seconds
            status_reporting_delay = 3
            self._set_property(test, NcReceiverMonitorProperties.STATUS_REPORTING_DELAY.value,
                               status_reporting_delay,
                               receiver_monitor.oid, receiver_monitor.role_path)
            # Start timer
            start_time = time()

            # Patch receiver
            receiver_id = touchpoint_resource.resource["id"]
            url = "single/receivers/{}/staged".format(receiver_id)
            activate_json = {"activation": {"mode": "activate_immediate"},
                             "master_enable": True,
                             "sender_id": str(uuid.uuid4()),
                             "transport_file": {"data": sdp_params[receiver_id], "type": "application/sdp"}
                             }

            valid, response = self.is05_utils.checkCleanRequestJSON("PATCH", url, activate_json)
            if not valid:
                return test.FAIL("Error patching Receiver " + str(response))

            # Status should stay healthy for status_reporting_delay minus one second
            while (time() - start_time) < (status_reporting_delay - 1.0):

                # Check connection status
                connection_status = self._get_property(test, NcReceiverMonitorProperties.CONNECTION_STATUS.value,
                                                       receiver_monitor.oid, receiver_monitor.role_path)

                if connection_status != NcConnectionStatus.Healthy.value:
                    return test.FAIL("Expect the status to stay healthy")

                sleep(0.2)

            # There is no actual stream so expect the connection status to become less healthy
            sleep(2.0)

            # Check connection status
            connection_status = self._get_property(test, NcReceiverMonitorProperties.CONNECTION_STATUS.value,
                                                   receiver_monitor.oid, receiver_monitor.role_path)

            if connection_status == NcConnectionStatus.Healthy.value:
                return test.FAIL("Not expecting healthy connection")

            checked = True

        if checked:
            return test.PASS()

        return test.UNCLEAR("Unable to find any testable Receiver Monitors")
