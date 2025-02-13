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

from enum import Enum
from jinja2 import Template
from random import randint
from requests.compat import json
from ..GenericTest import GenericTest, NMOSTestException
from ..IS05Utils import IS05Utils
from ..IS12Utils import IS12Utils
from ..MS05Utils import NcMethodStatus, NcPropertyId
from ..TestHelper import get_default_ip, get_mocks_hostname
from .MS0501Test import MS0501Test

from .. import Config as CONFIG

NODE_API_KEY = "node"
CONN_API_KEY = "connection"
CONTROL_API_KEY = "ncp"
MS05_API_KEY = "controlframework"

RECEIVER_MONITOR_CLASS_ID = [1, 2, 2, 1]


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


class BCP0080101Test(GenericTest):
    """
    Runs Tests covering BCP-008-01
    """
    def __init__(self, apis, node, **kwargs):
        GenericTest.__init__(self, apis, **kwargs)
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

    def get_receiver_monitors(self, test):
        if len(self.receiver_monitors):
            return self.receiver_monitors

        device_model = self.is12_utils.query_device_model(test)

        self.receiver_monitors = device_model.find_members_by_class_id(RECEIVER_MONITOR_CLASS_ID, include_derived=True, recurse=True, get_objects=True)

        return self.receiver_monitors

    def test_01(self, test):
        """Check that statusReportingDelay can be set to values within the published constraints"""
        receiver_monitors = self.get_receiver_monitors(test)

        if len(receiver_monitors) == 0:
            return test.UNCLEAR("No NcReceiverMonitors found in Device Model")

        default_status_reporting_delay = 3
        for monitor in receiver_monitors:
            methodResult = self.is12_utils.set_property(test, NcReceiverMonitorProperties.STATUS_REPORTING_DELAY.value, default_status_reporting_delay, oid=monitor.oid, role_path=monitor.role_path)
            if methodResult.status != NcMethodStatus.OK:
                return test.FAIL(f"SetProperty error: Error setting statusReportingDelay on ReceiverMonitor, oid={monitor.oid}, role path={monitor.role_path}")

            methodResult = self.is12_utils.get_property(test, NcReceiverMonitorProperties.STATUS_REPORTING_DELAY.value, oid=monitor.oid, role_path=monitor.role_path)
            if methodResult.status != NcMethodStatus.OK:
                return test.FAIL(f"GetProperty error: Error getting statusReportingDelay on ReceiverMonitor, oid={monitor.oid}, role path={monitor.role_path}")

            if methodResult.value != default_status_reporting_delay:
                return test.FAIL(f"Unexpected statusReportingDelay on ReceiverMonitor. Expected={default_status_reporting_delay} actual={methodResult.value}, oid={monitor.oid}, role path={monitor.role_path}")

        return test.PASS()

    def test_02(self, test):
        """Check Receiver Monitor transition to Healthy state"""

        # For each receiver in the NuT create a sender with appopriate transport parameters

        valid, resources = self.do_request("GET", self.node_url + "receivers")
        if not valid:
            return False, "Node API did not respond as expected: {}".format(resources)

        try:
            for resource in resources.json():
                self.is04_receivers.append(resource)
        except json.JSONDecodeError:
            return False, "Non-JSON response returned from Node API"

        video_sdp = open("test_data/sdp/video.sdp").read()
        video_jxsv_sdp = open("test_data/sdp/video-jxsv.sdp").read()
        audio_sdp = open("test_data/sdp/audio.sdp").read()
        data_sdp = open("test_data/sdp/data.sdp").read()
        mux_sdp = open("test_data/sdp/mux.sdp").read()

        rtp_receivers = [receiver for receiver in self.is04_receivers
                            if receiver["transport"].startswith("urn:x-nmos:transport:rtp")]

        for receiver in rtp_receivers:
            caps = receiver["caps"]

            if receiver["format"] == "urn:x-nmos:format:video":
                media_type = caps["media_types"][0] if "media_types" in caps else "video/raw"
            elif receiver["format"] == "urn:x-nmos:format:audio":
                media_type = caps["media_types"][0] if "media_types" in caps else "audio/L24"
            elif receiver["format"] == "urn:x-nmos:format:data":
                media_type = caps["media_types"][0] if "media_types" in caps else "video/smpte291"
            elif receiver["format"] == "urn:x-nmos:format:mux":
                media_type = caps["media_types"][0] if "media_types" in caps else "video/SMPTE2022-6"
            else:
                return test.FAIL("Unexpected Receiver format: {}".format(receiver["format"]))

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
                if not warn_sdp_untested:
                    warn_sdp_untested = "Could not test Receiver {} because this test cannot generate SDP data " \
                        "for media_type '{}'".format(receiver["id"], media_type)
                continue

            media_type, media_subtype = media_type.split("/")

            if media_type == "video":
                if media_subtype == "raw":
                    template_file = video_sdp
                elif media_subtype == "jxsv":
                    template_file = video_jxsv_sdp
                elif media_subtype == "smpte291":
                    template_file = data_sdp
                elif media_subtype == "SMPTE2022-6":
                    template_file = mux_sdp
            elif media_type == "audio":
                if media_subtype in ["L16", "L24", "L32"]:
                    template_file = audio_sdp

            template = Template(template_file, keep_trailing_newline=True)

            src_ip = get_default_ip()
            dst_ip = "232.40.50.{}".format(randint(1, 254))
            dst_port = randint(5000, 5999)

            sdp_file = template.render({**CONFIG.SDP_PREFERENCES,
                                        'src_ip': src_ip,
                                        'dst_ip': dst_ip,
                                        'dst_port': dst_port,
                                        'media_subtype': media_subtype
                                        })

            url = "single/receivers/{}/staged".format(receiver["id"])
            data = {"sender_id": None, "transport_file": {"data": sdp_file, "type": "application/sdp"}}
            valid, response = self.is05_utils.checkCleanRequestJSON("PATCH", url, data)

            if valid:
                print(response)

        print(self.mock_node)
        # # Set up connection on the mock node
        # valid, response = self.do_request('GET', self.mock_node_base_url
        #                                     + 'x-nmos/connection/' + self.connection_api_version + '/single/senders/'
        #                                     + sender['id'] + '/transportfile')
        # transport_file = response.content.decode()
        # activate_json = {"activation": {"mode": "activate_immediate"},
        #                     "master_enable": True,
        #                     "sender_id": sender['id'],
        #                     "transport_file": {"data": transport_file, "type": "application/sdp"}}
        # self.node.patch_staged('receivers', receiver['id'], activate_json)