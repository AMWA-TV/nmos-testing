# Copyright (C) 2022 Advanced Media Workflow Association
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
import re

from ..NMOSUtils import NMOSUtils
from ..GenericTest import GenericTest
from .. import TestHelper
from .. import Config as CONFIG
from ..IS04Utils import IS04Utils

COMPAT_API_KEY = "streamcompatibility"
CONTROLS = "controls"
NODE_API_KEY = "node"
CONN_API_KEY = "connection"

REF_SUPPORTED_CONSTRAINTS_VIDEO = [
    "urn:x-nmos:cap:meta:label",
    "urn:x-nmos:cap:meta:preference",
    "urn:x-nmos:cap:meta:enabled",
    "urn:x-nmos:cap:format:media_type",
    "urn:x-nmos:cap:format:grain_rate",
    "urn:x-nmos:cap:format:frame_width",
    "urn:x-nmos:cap:format:frame_height",
    "urn:x-nmos:cap:format:interlace_mode",
    "urn:x-nmos:cap:format:color_sampling",
    "urn:x-nmos:cap:format:component_depth",
]
REF_SUPPORTED_CONSTRAINTS_AUDIO = [
    "urn:x-nmos:cap:meta:label",
    "urn:x-nmos:cap:meta:preference",
    "urn:x-nmos:cap:meta:enabled",
    "urn:x-nmos:cap:format:media_type",
    "urn:x-nmos:cap:format:channel_count",
    "urn:x-nmos:cap:format:sample_rate",
    "urn:x-nmos:cap:format:sample_depth",
]


class IS1101Test(GenericTest):
    """
    Runs Node Tests covering IS-11
    """
    def __init__(self, apis, **kwargs):
        # Don't auto-test paths responding with an EDID binary as they don't have a JSON Schema
        omit_paths = [
            "/single/senders/{senderId}/transportfile",
            "/inputs/{inputId}/edid",
            "/inputs/{inputId}/edid/base",
            "/inputs/{inputId}/edid/effective",
            "/outputs/{outputId}/edid"
        ]
        GenericTest.__init__(self, apis, omit_paths, **kwargs)
        self.compat_url = self.apis[COMPAT_API_KEY]["url"]
        self.node_url = self.apis[NODE_API_KEY]["url"]
        self.conn_url = self.apis[CONN_API_KEY]["url"]
        self.connected_outputs = []
        self.edid_connected_outputs = []
        self.not_edid_connected_outputs = []
        self.outputs = []
        self.active_connected_outputs = []
        self.receivers = ""
        self.senders = ""
        self.reference_sender_id = ""
        self.receivers_outputs = ""
        self.no_output_receivers = []
        self.sdp_transport_file = ""
        self.caps = ""
        self.senders = ""
        self.senders_2 = ""
        self.flow_format = {}
        self.flow_format_audio = []
        self.flow_format_video = []
        self.flow_width = {}
        self.flow_height = {}
        self.flow_grain_rate = {}
        self.flow_sample_rate = {}
        self.version = {}
        self.grain_rate_constraints = {}
        self.empty_constraints = {}
        self.sample_rate_constraints = {}
        self.constraints = {}

    def remove_last_slash(self, id):
        """
        Check if the id comes with a slash at the end or not. If yes, the slash will be remove.
        """
        if (id[-1] == '/'):
            return id[:-1]
        return id

    # GENERAL TESTS
    def test_00_01(self, test):
        """At least one Device is showing an IS-11 control advertisement matching the API under test"""

        control_type = "urn:x-nmos:control:stream-compat/" + self.apis[COMPAT_API_KEY]["version"]
        return NMOSUtils.do_test_device_control(
            test,
            self.node_url,
            control_type,
            self.compat_url,
            self.authorization
        )

    def test_00_02(self, test):
        "Put all senders into inactive state"
        senders_url = self.conn_url + "single/senders/"
        valid, response = TestHelper.do_request("GET", senders_url)
        if not valid:
            return test.FAIL("Unexpected response from the Connection API: {}".format(response))
        if response.status_code != 200:
            return test.FAIL("The request {} has failed {}".format(senders_url, response.json()))
        senders = response.json()
        if len(senders) > 0:
            for sender in senders:
                url = senders_url + sender + "staged/"
                deactivate_json = {
                    "master_enable": False,
                    "activation": {"mode": "activate_immediate"},
                }

                valid_patch, response = TestHelper.do_request("PATCH", url, json=deactivate_json)
                if not valid_patch:
                    return test.FAIL("Unexpected response from the Connection API: {}".format(response))
                if (
                    response.status_code != 200
                    or response.json()["master_enable"]
                    or response.json()["activation"]["mode"] != "activate_immediate"
                ):
                    return test.FAIL("The patch request to {} has failed: {}".format(url, response.json()))
            return test.PASS()
        return test.UNCLEAR("Could not find any senders to test")

    def test_00_03(self, test):
        "Put all the receivers into inactive state"
        receivers_url = self.conn_url + "single/receivers/"
        valid, response = TestHelper.do_request("GET", receivers_url)
        if not valid:
            return test.FAIL("Unexpected response from the connection API: {}".format(response))
        if response.status_code != 200:
            return test.FAIL("The connection request {} has failed: {}".format(receivers_url, response.json()))
        receivers = response.json()
        if len(receivers) > 0:
            for receiver in receivers:
                url = receivers_url + receiver + "staged/"
                deactivate_json = {
                    "master_enable": False,
                    "activation": {"mode": "activate_immediate"},
                }
                valid_patch, response = TestHelper.do_request("PATCH", url, json=deactivate_json)
                if not valid_patch:
                    return test.FAIL("Unexpected response from the Connection API: {}".format(response))
                if (
                    response.status_code != 200
                    or response.json()["master_enable"]
                    or response.json()["activation"]["mode"] != "activate_immediate"
                ):
                    return test.FAIL("The patch request to {} has failed: {}".format(url, response.json()))

            return test.PASS()

        return test.UNCLEAR("Could not find any receivers to test")

    # SENDERS TESTS
    """
    Runs Node Tests covering IS-11 for Senders
    """

    def get_another_grain_rate(self, grain_rate):
        numerator = grain_rate["numerator"]
        denominator = grain_rate["denominator"]
        if (numerator == 30 or numerator == 25) and denominator == 1:
            return {"numerator": numerator * 2, "denominator": 1}
        if (numerator == 60 or numerator == 50) and denominator == 1:
            return {"numerator": numerator / 2, "denominator": 1}
        if numerator == 24 and denominator == 1:
            return {"numerator": 30, "denominator": 1}
        if (numerator == 30000 or numerator == 25000) and denominator == 1001:
            return {"numerator": numerator * 2, "denominator": 1001}
        if (numerator == 60000 or numerator == 50000) and denominator == 1001:
            return {"numerator": numerator / 2, "denominator": 1001}
        return "grain_rate not valid"

    def get_another_sample_rate(self, sample_rate):
        numerator = sample_rate["numerator"]
        if numerator == 0:
            return {"numerator": 48000}
        if numerator == 48000:
            return {"numerator": 44100}
        if numerator == 44100:
            return {"numerator": 48000}
        if numerator == 96000:
            return {"numerator": 48000}
        if numerator == 88200:
            return {"numerator": 44100}
        return "sample_rate not valid"

    def test_02_00(self, test):
        "Reset active constraints of all senders"
        url = self.compat_url + "senders/"
        valid, response = TestHelper.do_request("GET", url)
        if not valid:
            return test.FAIL("Unexpected response from the Connection API: {}".format(response))
        if response.status_code != 200:
            return test.FAIL(
                "The sender's streamcompatibility request {} has failed: {}".format(url, response.json())
            )
        self.senders = response.json()
        if len(self.senders) != 0:
            for sender in self.senders:
                valid, response = TestHelper.do_request(
                    "DELETE",
                    self.compat_url + "senders/" + sender + "constraints/active/",
                )
                if not valid:
                    return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
                if response.status_code != 200:
                    return test.FAIL("The sender {} constraints cannot be deleted".format(sender))
            return test.PASS()
        return test.UNCLEAR("There are no IS-11 senders")

    def test_02_01(self, test):
        "Verify that the device supports the concept of IS-11 Sender"
        valid, response = TestHelper.do_request("GET", self.compat_url + "senders/")
        if not valid:
            return test.FAIL("Unexpected response from the Streamcompatibility API: {}".format(response))
        if response.status_code != 200:
            return test.FAIL(
                "The sender's streamcompatibility request has failed: {}".format(response.json())
            )
        self.senders = response.json()
        if len(self.senders) == 0:
            return test.UNCLEAR("There are no IS-11 senders")
        return test.PASS()

    def test_02_01_01(self, test):
        "Verify that the device supports the concept of IS-11 Sender"
        if len(self.senders) != 0:
            for sender_id in self.senders:
                valid, response = TestHelper.do_request("GET", self.node_url + "senders/" + sender_id)
                if not valid:
                    return test.FAIL("Unexpected response from the Node API: {}".format(response))
                if response.status_code != 200:
                    return test.FAIL(
                        "The sender {} is not available in the Node API response: {}".format(sender_id, response.json())
                    )
                sender_node_id = response.json()["id"]
                if sender_id[:-1] != sender_node_id:
                    return test.FAIL("Senders {} and {} are different".format(sender_id[:-1], sender_node_id))
            return test.PASS()
        return test.UNCLEAR("There are no IS-11 senders")

    def test_02_02(self, test):
        "Verify senders (generic with/without inputs)"
        valid, response = TestHelper.do_request("GET", self.compat_url + "senders/")
        if not valid:
            return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
        if response.status_code != 200:
            return test.FAIL(
                "The sender's streamcompatibility request has failed: {}".format(response.json())
            )
        self.senders_2 = response.json()
        if len(self.senders_2) == 0:
            return test.UNCLEAR("There are no IS-11 senders")
        return test.PASS()

    def test_02_02_01(self, test):
        "Verify that the status is unconstrained as per our pre-conditions"
        if len(self.senders_2) != 0:
            for sender_id in self.senders_2:
                valid, response = TestHelper.do_request(
                    "GET", self.compat_url + "senders/" + sender_id + "status/"
                )
                if not valid:
                    return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
                if response.status_code != 200:
                    return test.FAIL(
                        "The streamcompatibility request for sender {} status has failed: {}"
                        .format(sender_id, response.json())
                    )
                state = response.json()["state"]
                if state in ["awating_essence", "no_essence"]:
                    for i in range(0, 5):
                        valid, response = TestHelper.do_request(
                            "GET", self.compat_url + "senders/" + sender_id + "status/"
                        )
                        if not valid:
                            return test.FAIL("Unexpected response from the streamcompatibility API: {}"
                                             .format(response))
                        if response.status_code != 200:
                            return test.FAIL(
                                "The streamcompatibility request for sender {} status has failed: {}"
                                .format(sender_id, response.json())
                            )
                        state = response.json()["state"]
                        if state in ["awating_essence", "no_essence"]:
                            time.sleep(CONFIG.STABLE_STATE_DELAY)
                        else:
                            break
                if state != "unconstrained":
                    return test.FAIL("Inputs are unstable")
            return test.PASS()
        return test.UNCLEAR("There are no IS-11 senders")

    def test_02_02_03(self, test):
        """
        Verify that the sender is available in the node API,
        has an associated flow and is inactive
        """
        if len(self.senders_2) != 0:
            for sender_id in self.senders_2:
                valid, response = TestHelper.do_request(
                    "GET", self.node_url + "senders/" + sender_id
                )
                if not valid:
                    return test.FAIL("Unexpected response from the Node API: {}".format(response))
                if response.status_code != 200:
                    return test.FAIL(
                        "The sender {} is not available in the Node API response: {}".format(sender_id, response.json())
                    )
                sender_node_id = response.json()["id"]
                if sender_id[:-1] != sender_node_id:
                    return test.FAIL("Senders {} and {} are different".format(sender_id[:-1], sender_node_id))
                sender_flow_id = response.json()["flow_id"]
                if sender_flow_id is None:
                    return test.FAIL("The sender {} must have a flow".format(sender_id))
                sender_subscription_active = response.json()["subscription"]["active"]
                if sender_subscription_active:
                    return test.FAIL(
                        "The sender {} must be inactive ".format(sender_id)
                    )
                valid, response = TestHelper.do_request(
                    "GET", self.node_url + "flows/" + sender_flow_id
                )
                if not valid:
                    return test.FAIL("Unexpected response from the Node API: {}".format(response))
                if response.status_code != 200:
                    return test.FAIL(
                        "The sender {} is not available in the Node API has an associated flow: {}"
                        .format(sender_flow_id, response.json())
                    )
                flow_format = response.json()["format"]
                self.flow_format[sender_id] = flow_format
                if flow_format == "urn:x-nmos:format:video":
                    self.flow_format_video.append(sender_id)
                    self.flow_width[sender_id] = response.json()["frame_width"]
                    self.flow_height[sender_id] = response.json()["frame_height"]
                    self.flow_grain_rate[sender_id] = response.json()["grain_rate"]
                if flow_format == "urn:x-nmos:format:audio":
                    self.flow_format_audio.append(sender_id)
                    self.flow_sample_rate[sender_id] = response.json()["sample_rate"]
                if (
                    flow_format != "urn:x-nmos:format:video"
                    and flow_format != "urn:x-nmos:format:audio"
                ):
                    print("Only audio and video senders are tested at this time")
            return test.PASS()
        return test.UNCLEAR("There are no IS-11 senders")

    def test_02_02_03_01(self, test):
        "Verify that the video sender supports the minimum set of video constraints"

        sample = "^urn:x-nmos:cap:"

        if len(self.flow_format_video) == 0:
            return test.UNCLEAR("There is no video format")

        for sender_id in self.flow_format_video:
            valid, response = TestHelper.do_request(
                "GET",
                self.compat_url + "senders/" + sender_id + "constraints/supported/",
            )
            if not valid:
                return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
            if response.status_code != 200:
                return test.FAIL(
                    "The streamcompatibility request for sender {} constraints supported has failed: {}"
                    .format(sender_id, response.json())
                )
            supportedConstraints = response.json()["parameter_constraints"]
            for item in supportedConstraints:
                if not re.search(sample, item):
                    return test.FAIL("Only x-nmos:cap constraints are allowed")
            for item in REF_SUPPORTED_CONSTRAINTS_VIDEO:
                if item not in supportedConstraints:
                    return test.FAIL(item + " is not in supportedConstraints ")
        return test.PASS()

    def test_02_02_03_02(self, test):
        "Verify that the video sender supports the minimum set of video constraints"

        sample = "^urn:x-nmos:cap:"

        if len(self.flow_format_audio) == 0:
            return test.UNCLEAR("There is no audio format")

        for sender_id in self.flow_format_audio:
            valid, response = TestHelper.do_request(
                "GET",
                self.compat_url + "senders/" + sender_id + "constraints/supported/",
            )
            if not valid:
                return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
            if response.status_code != 200:
                return test.FAIL(
                    "The streamcompatibility request for sender {} constraints supported has failed: {}"
                    .format(sender_id, response.json())
                )
            supportedConstraints = response.json()["parameter_constraints"]
            for item in supportedConstraints:
                if not re.search(sample, item):
                    return test.FAIL("Only x-nmos:cap constraints are allowed")
            for item in REF_SUPPORTED_CONSTRAINTS_AUDIO:
                if item not in supportedConstraints:
                    return test.FAIL(item + "is not in supportedConstraints")
        return test.PASS()

    def test_02_02_04_01(self, test):
        """
        Verify that changing the constraints of an
        IS-11 sender(video) changes the version of
        the associated IS-04 sender.
        """
        if len(self.flow_format_video) == 0:
            return test.UNCLEAR("There is no video format")

        for sender_id in self.flow_format_video:
            valid, response = TestHelper.do_request(
                "GET", self.node_url + "senders/" + sender_id
            )
            if not valid:
                return test.FAIL("Unexpected response from the Node API: {}".format(response))
            if response.status_code != 200:
                return test.FAIL(
                    "The sender {} is not available in the Node API response: {}".format(sender_id, response.json())
                )
            version = response.json()["version"]
            self.version[sender_id] = version
            self.grain_rate_constraints[sender_id] = {
                "constraint_sets": [
                    {
                        "urn:x-nmos:cap:format:grain_rate": {
                            "enum": [self.flow_grain_rate[sender_id]]
                        }
                    }
                ]
            }
            self.empty_constraints[sender_id] = {"constraint_sets": []}
            valid, response = TestHelper.do_request(
                "PUT",
                self.compat_url + "senders/" + sender_id + "constraints/active/",
                json=self.grain_rate_constraints[sender_id],
            )
            if not valid:
                return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
            if response.status_code != 200:
                return test.FAIL(
                    "The sender {} constraints change has failed: {}".format(sender_id, response.json())
                )
            valid, response = TestHelper.do_request(
                "GET", self.node_url + "senders/" + sender_id
            )
            if not valid:
                return test.FAIL("Unexpected response from the Node API: {}".format(response))
            if response.status_code != 200:
                return test.FAIL(
                    "The sender {} is not available in the Node API response: {}".format(sender_id, response.json())
                )
            version = response.json()["version"]
            if version == self.version[sender_id]:
                return test.FAIL("Versions {} and {} are different".format(version, self.version[sender_id]))
            self.version[sender_id] = version
            valid, response = TestHelper.do_request(
                "GET", self.compat_url + "senders/" + sender_id + "constraints/active/"
            )
            if not valid:
                return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
            if response.status_code != 200:
                return test.FAIL(
                    "Contraints active request sender {} has failed: {}".format(sender_id, response.json())
                )
            constraints = response.json()
            if not IS04Utils.compare_constraint_sets(
                constraints["constraint_sets"],
                self.grain_rate_constraints[sender_id]["constraint_sets"],
            ):
                return test.FAIL("The sender {} contraints are different".format(sender_id))
            valid, response = TestHelper.do_request(
                "DELETE",
                self.compat_url + "senders/" + sender_id + "constraints/active/",
            )
            if not valid:
                return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
            if response.status_code != 200:
                return test.FAIL(
                   "The sender {} constraints cannot be deleted".format(sender_id)
                )
            valid, response = TestHelper.do_request(
                "GET", self.node_url + "senders/" + sender_id
            )
            if not valid:
                return test.FAIL("Unexpected response from the Node API: {}".format(response))
            if response.status_code != 200:
                return test.FAIL(
                    "The sender {} is not available in the Node API response: {}".format(sender_id, response.json())
                )
            version = response.json()["version"]
            if version == self.version[sender_id]:
                return test.FAIL("Versions {} and {} are different".format(version, self.version[sender_id]))
            self.version[sender_id] = version
            valid, response = TestHelper.do_request(
                "GET", self.compat_url + "senders/" + sender_id + "constraints/active/"
            )
            if not valid:
                return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
            if response.status_code != 200:
                return test.FAIL(
                     "Contraints active request for sender {} has failed: {}".format(sender_id, response.json())
                )
            constraints = response.json()
            if constraints != self.empty_constraints[sender_id]:
                return test.FAIL("Contraints are different")
        return test.PASS()

    def test_02_02_04_02(self, test):
        """
        Verify that changing the constraints of an IS-11
        sender(audio) changes the version of the associated IS-04 sender.
        """
        if len(self.flow_format_audio) == 0:
            return test.UNCLEAR("There is no audio format")
        for sender_id in self.flow_format_audio:
            valid, response = TestHelper.do_request(
                "GET", self.node_url + "senders/" + sender_id
            )
            if not valid:
                return test.FAIL("Unexpected response from the Node API: {}".format(response))
            if response.status_code != 200:
                return test.FAIL(
                    "The sender {} is not available in the Node API response: {}".format(sender_id, response.json())
                )
            version = response.json()["version"]
            self.version[sender_id] = version
            self.sample_rate_constraints[sender_id] = {
                "constraint_sets": [
                    {
                        "urn:x-nmos:cap:format:sample_rate": {
                            "enum": [self.flow_sample_rate[sender_id]]
                        }
                    }
                ]
            }
            self.empty_constraints[sender_id] = {"constraint_sets": []}
            valid, response = TestHelper.do_request(
                "PUT",
                self.compat_url + "senders/" + sender_id + "constraints/active/",
                json=self.sample_rate_constraints[sender_id],
            )
            if not valid:
                return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
            if response.status_code != 200:
                return test.FAIL(
                    "The sender {} constraints change has failed: {}".format(sender_id, response.json())
                )
            valid, response = TestHelper.do_request(
                "GET", self.node_url + "senders/" + sender_id
            )
            if not valid:
                return test.FAIL("Unexpected response from the Node API: {}".format(response))
            if response.status_code != 200:
                return test.FAIL(
                    "The sender {} is not available in the Node API response: {}".format(sender_id, response.json())
                )
            version = response.json()["version"]
            if version == self.version[sender_id]:
                return test.FAIL("Versions {} and {} are different".format(version, self.version[sender_id]))
            self.version[sender_id] = version

            valid, response = TestHelper.do_request(
                "GET", self.compat_url + "senders/" + sender_id + "constraints/active/"
            )
            if not valid:
                return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
            if response.status_code != 200:
                return test.FAIL(
                    "Contraints active request for sender {} has failed: {}".format(sender_id, response.json())
                )
            constraints = response.json()

            if not IS04Utils.compare_constraint_sets(
                constraints["constraint_sets"],
                self.sample_rate_constraints[sender_id]["constraint_sets"],
            ):
                return test.FAIL("The constraint applied does not match the active"
                                 "constraint retrieved from the sender {}".format(sender_id))

            valid, response = TestHelper.do_request(
                "DELETE",
                self.compat_url + "senders/" + sender_id + "constraints/active/",
            )
            if not valid:
                return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
            if response.status_code != 200:
                return test.FAIL(
                    "The sender {} constraints cannot be deleted".format(sender_id)
                )

            valid, response = TestHelper.do_request(
                "GET", self.node_url + "senders/" + sender_id
            )
            if not valid:
                return test.FAIL("Unexpected response from the Node API: {}".format(response))
            if response.status_code != 200:
                return test.FAIL(
                    "The sender {} is not available in the Node API response: {}".format(sender_id, response.json())
                )
            version = response.json()["version"]
            if version == self.version[sender_id]:
                return test.FAIL("Versions {} and {} are different".format(version, self.version[sender_id]))
            self.version[sender_id] = version

            valid, response = TestHelper.do_request(
                "GET", self.compat_url + "senders/" + sender_id + "constraints/active/"
            )
            if not valid:
                return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
            if response.status_code != 200:
                return test.FAIL(
                    "Contraints active request for sender {} has failed: {}".format(sender_id, response.json())
                )
            constraints = response.json()
            if constraints != self.empty_constraints[sender_id]:
                return test.FAIL("Contraints are different")
        return test.PASS()

    def test_02_02_05_01(self, test):
        """
        Verify that setting no-op constraints for frame(width,height),
        grain_rate doesn't change the flow of a sender(video).
        """
        if len(self.flow_format_video) == 0:
            return test.UNCLEAR("There is no video format")

        for sender_id in self.flow_format_video:
            valid, response = TestHelper.do_request(
                "GET", self.compat_url + "senders/" + sender_id + "status/"
            )
            if not valid:
                return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
            if response.status_code != 200:
                return test.FAIL(
                    "The streamcompatibility request for sender {} status has failed: {}"
                    .format(sender_id, response.json())
                )
            state = response.json()["state"]
            if state in ["awating_essence", "no_essence"]:
                for i in range(0, 5):
                    valid, response = TestHelper.do_request(
                        "GET", self.compat_url + "senders/" + sender_id + "status/"
                    )
                    if not valid:
                        return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
                    if response.status_code != 200:
                        return test.FAIL(
                            "The streamcompatibility request for sender {} status has failed: {}"
                            .format(sender_id, response.json())
                        )
                    state = response.json()["state"]
                    if state in ["awating_essence", "no_essence"]:
                        time.sleep(CONFIG.STABLE_STATE_DELAY)
                    else:
                        break
            if state != "unconstrained":
                return test.FAIL("Inputs are unstable")

            self.constraints[sender_id] = {
                "constraint_sets": [
                    {
                        "urn:x-nmos:cap:format:grain_rate": {
                            "enum": [self.flow_grain_rate[sender_id]]
                        }
                    },
                    {
                        "urn:x-nmos:cap:format:frame_width": {
                            "enum": [self.flow_width[sender_id]]
                        }
                    },
                    {
                        "urn:x-nmos:cap:format:frame_height": {
                            "enum": [self.flow_height[sender_id]]
                        }
                    },
                ]
            }

            valid, response = TestHelper.do_request(
                "PUT",
                self.compat_url + "senders/" + sender_id + "constraints/active/",
                json=self.constraints[sender_id],
            )
            if not valid:
                return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
            if response.status_code != 200:
                return test.FAIL(
                    "The sender {} constraints change has failed: {}"
                    .format(sender_id, response.json())
                )

            valid, response = TestHelper.do_request(
                "GET", self.compat_url + "senders/" + sender_id + "status/"
            )
            if not valid:
                return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
            if response.status_code != 200:
                return test.FAIL(
                    "The streamcompatibility request for sender {} status has failed: {}"
                    .format(sender_id, response.json())
                )
            state = response.json()["state"]

            if state in ["awating_essence", "no_essence"]:
                for i in range(0, 5):
                    valid, response = TestHelper.do_request(
                        "GET", self.compat_url + "senders/" + sender_id + "status/"
                    )
                    if not valid:
                        return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
                    if response.status_code != 200:
                        return test.FAIL(
                            "The streamcompatibility request for sender {} status has failed: {}"
                            .format(sender_id, response.json())
                        )
                    state = response.json()["state"]
                    if state in ["awating_essence", "no_essence"]:
                        time.sleep(CONFIG.STABLE_STATE_DELAY)
                    else:
                        break
            if state != "constrained":
                return test.FAIL("Inputs are unstable")

            valid, response = TestHelper.do_request(
                "GET", self.node_url + "senders/" + sender_id
            )
            if not valid:
                return test.FAIL("Unexpected response from the Node API: {}".format(response))
            if response.status_code != 200:
                return test.FAIL(
                    "The sender {} is not available in the Node API response: {}".format(sender_id, response.json())
                )
            sender_flow_id = response.json()["flow_id"]
            if sender_flow_id is None:
                return test.FAIL("The sender {} must have a flow".format(sender_id))

            valid, response = TestHelper.do_request(
                "GET", self.node_url + "flows/" + sender_flow_id
            )
            if not valid:
                return test.FAIL("Unexpected response from the Node API: {}".format(response))
            if response.status_code != 200:
                return test.FAIL(
                    "The sender {} is not available in the Node API has an associated flow: {}"
                    .format(sender_flow_id, response.json())
                )

            if (
                self.flow_grain_rate[sender_id] != response.json()["grain_rate"]
                or self.flow_width[sender_id] != response.json()["frame_width"]
                or self.flow_height[sender_id] != response.json()["frame_height"]
            ):
                return test.FAIL(
                    "The constraints on frame_width, frame_height\
                    and grain_rate were not expected to change the flow of sender(video) {}"
                    .format(sender_id)
                )

            valid, response = TestHelper.do_request(
                "DELETE",
                self.compat_url + "senders/" + sender_id + "constraints/active/",
            )
            if not valid:
                return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
            if response.status_code != 200:
                return test.FAIL(
                    "The sender {} constraints cannot be deleted".format(sender_id)
                )

        return test.PASS()

    def test_02_02_05_02(self, test):
        """
        Verify that setting no-op constraints for sample_rate doesn't change the flow of a sender(audio).
        """

        if len(self.flow_format_audio) == 0:
            return test.UNCLEAR("There is no audio format")

        for sender_id in self.flow_format_audio:
            valid, response = TestHelper.do_request(
                "GET", self.compat_url + "senders/" + sender_id + "status/"
            )
            if not valid:
                return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
            if response.status_code != 200:
                return test.FAIL(
                    "The streamcompatibility request for sender {} status has failed: {}"
                    .format(sender_id, response.json())
                )
            state = response.json()["state"]

            if state in ["awating_essence", "no_essence"]:
                for i in range(0, 5):
                    valid, response = TestHelper.do_request(
                        "GET", self.compat_url + "senders/" + sender_id + "status/"
                    )
                    if not valid:
                        return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
                    if response.status_code != 200:
                        return test.FAIL(
                            "The streamcompatibility request for sender {} status has failed: {}"
                            .format(sender_id, response.json())
                        )
                    state = response.json()["state"]
                    if state in ["awating_essence", "no_essence"]:
                        time.sleep(CONFIG.STABLE_STATE_DELAY)
                    else:
                        break
            if state != "unconstrained":
                return test.FAIL("Inputs are unstable")

            self.constraints[sender_id] = {
                "constraint_sets": [
                    {
                        "urn:x-nmos:cap:format:sample_rate": {
                            "enum": [self.flow_sample_rate[sender_id]]
                        }
                    }
                ]
            }
            valid, response = TestHelper.do_request(
                "PUT",
                self.compat_url + "senders/" + sender_id + "constraints/active/",
                json=self.constraints[sender_id],
            )
            if not valid:
                return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
            if response.status_code != 200:
                return test.FAIL(
                    "The sender {} constraints change has failed: {}"
                    .format(sender_id, response.json())
                )

            valid, response = TestHelper.do_request(
                "GET", self.compat_url + "senders/" + sender_id + "status/"
            )
            if not valid:
                return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
            if response.status_code != 200:
                return test.FAIL(
                    "The streamcompatibility request for sender {} status has failed: {}"
                    .format(sender_id, response.json())
                )
            state = response.json()["state"]

            if state in ["awating_essence", "no_essence"]:
                for i in range(0, 5):
                    valid, response = TestHelper.do_request(
                        "GET", self.compat_url + "senders/" + sender_id + "status/"
                    )
                    if not valid:
                        return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
                    if response.status_code != 200:
                        return test.FAIL(
                            "The streamcompatibility request for sender {} status has failed: {}"
                            .format(sender_id, response.json())
                        )
                    state = response.json()["state"]
                    if state in ["awating_essence", "no_essence"]:
                        time.sleep(CONFIG.STABLE_STATE_DELAY)
                    else:
                        break
            if state != "constrained":
                return test.FAIL("Inputs are unstable")

            valid, response = TestHelper.do_request(
                "GET", self.node_url + "senders/" + sender_id
            )
            if not valid:
                return test.FAIL("Unexpected response from the Node API: {}".format(response))
            if response.status_code != 200:
                return test.FAIL(
                    "The sender {} is not available in the Node API response: {}"
                    .format(sender_id, response.json())
                )
            sender_flow_id = response.json()["flow_id"]
            if sender_flow_id is None:
                return test.FAIL("The sender {} must have a flow".format(sender_id))

            valid, response = TestHelper.do_request(
                "GET", self.node_url + "flows/" + sender_flow_id
            )
            if not valid:
                return test.FAIL("Unexpected response from the Node API: {}".format(response))
            if response.status_code != 200:
                return test.FAIL(
                    "The sender {} is not available in the Node API has an associated flow: {}"
                    .format(sender_flow_id, response.json())
                )
            flow_sample_rate = response.json()["sample_rate"]
            if self.flow_sample_rate[sender_id] != flow_sample_rate:
                return test.FAIL("Different sample rate")

            valid, response = TestHelper.do_request(
                "DELETE",
                self.compat_url + "senders/" + sender_id + "constraints/active/",
            )
            if not valid:
                return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
            if response.status_code != 200:
                return test.FAIL(
                    "The sender {} constraints cannot be deleted".format(sender_id)
                )
        return test.PASS()

    def test_02_02_06_01(self, test):
        """
        Verify that setting no-op constraints for supported constraints
        doesn't change the flow of a sender(video).
        """
        if len(self.flow_format_video) == 0:
            return test.UNCLEAR("There is no video format")

        for sender_id in self.flow_format_video:
            valid, response = TestHelper.do_request(
                "GET", self.compat_url + "senders/" + sender_id + "status/"
            )
            if not valid:
                return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
            if response.status_code != 200:
                return test.FAIL(
                    "The streamcompatibility request for sender {} status has failed: {}"
                    .format(sender_id, response.json())
                )
            state = response.json()["state"]
            if state in ["awating_essence", "no_essence"]:
                for i in range(0, 5):
                    valid, response = TestHelper.do_request(
                        "GET", self.compat_url + "senders/" + sender_id + "status/"
                    )
                    if not valid:
                        return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
                    if response.status_code != 200:
                        return test.FAIL(
                            "The streamcompatibility request for sender {} status has failed: {}"
                            .format(sender_id, response.json())
                        )
                    state = response.json()["state"]
                    if state in ["awating_essence", "no_essence"]:
                        time.sleep(CONFIG.STABLE_STATE_DELAY)
                    else:
                        break
            if state != "unconstrained":
                return test.FAIL("Inputs are unstable")

            valid, response = TestHelper.do_request(
                "GET", self.node_url + "senders/" + sender_id
            )
            if not valid:
                return test.FAIL("Unexpected response from the Node API: {}".format(response))
            if response.status_code != 200:
                return test.FAIL(
                    "The sender {} is not available in the Node API response: {}"
                    .format(sender_id, response.json())
                )
            sender = response.json()

            valid, response = TestHelper.do_request(
                "GET", self.node_url + "flows/" + sender["flow_id"]
            )
            if not valid:
                return test.FAIL("Unexpected response from the valid API: {}".format(response))
            if response.status_code != 200:
                return test.FAIL(
                    "The sender {} is not available in the Node API has an associated flow: {}"
                    .format(sender["flow_id"], response.json())
                )
            flow = response.json()
            color_sampling = IS04Utils.make_sampling(flow["components"])
            if color_sampling is None:
                return test.FAIL("Invalid array of video components")
            constraint_set = {}

            for item in REF_SUPPORTED_CONSTRAINTS_VIDEO:
                try:
                    if item == "urn:x-nmos:cap:meta:label":
                        constraint_set["urn:x-nmos:cap:meta:label"] = "video constraint"
                    if item == "urn:x-nmos:cap:meta:preference":
                        constraint_set["urn:x-nmos:cap:meta:preference"] = 0
                    if item == "urn:x-nmos:cap:meta:enabled":
                        constraint_set["urn:x-nmos:cap:meta:enabled"] = True
                    if item == "urn:x-nmos:cap:format:media_type":
                        constraint_set["urn:x-nmos:cap:format:media_type"] = {
                            "enum": [flow["media_type"]]
                        }
                    if item == "urn:x-nmos:cap:format:grain_rate":
                        constraint_set["urn:x-nmos:cap:format:grain_rate"] = {
                            "enum": [flow["grain_rate"]]
                        }
                    if item == "urn:x-nmos:cap:format:frame_width":
                        constraint_set["urn:x-nmos:cap:format:frame_width"] = {
                            "enum": [flow["frame_width"]]
                        }
                    if item == "urn:x-nmos:cap:format:frame_height":
                        constraint_set["urn:x-nmos:cap:format:frame_height"] = {
                            "enum": [flow["frame_height"]]
                        }
                    if item == "urn:x-nmos:cap:format:interlace_mode":
                        constraint_set["urn:x-nmos:cap:format:interlace_mode"] = {
                            "enum": [flow["interlace_mode"]]
                        }
                    if item == "urn:x-nmos:cap:format:color_sampling":
                        constraint_set["urn:x-nmos:cap:format:color_sampling"] = {
                            "enum": [color_sampling]
                        }
                    if item == "urn:x-nmos:cap:format:component_depth":
                        constraint_set["urn:x-nmos:cap:format:component_depth"] = {
                            "enum": [flow["components"][0]["bit_depth"]]
                        }
                except Exception:
                    pass

            self.constraints[sender_id] = {"constraint_sets": [constraint_set]}

            valid, response = TestHelper.do_request(
                "PUT",
                self.compat_url + "senders/" + sender_id + "constraints/active/",
                json=self.constraints[sender_id],
            )
            if not valid:
                return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
            if response.status_code != 200:
                return test.FAIL(
                    "The sender {} constraints change has failed: {}"
                    .format(sender_id, response.json())
                )

            valid, response = TestHelper.do_request(
                "GET", self.node_url + "flows/" + sender["flow_id"]
            )
            if not valid:
                return test.FAIL("Unexpected response from the Node API: {}".format(response))
            if response.status_code != 200:
                return test.FAIL(
                    "The sender {} is not available in the Node API has an associated flow: {}"
                    .format(sender["flow_id"], response.json())
                )
            new_flow = response.json()

            new_color_sampling = IS04Utils.make_sampling(new_flow["components"])
            if new_color_sampling is None:
                return test.FAIL("Invalid array of video components")

            for item in REF_SUPPORTED_CONSTRAINTS_VIDEO:
                try:
                    if item == "urn:x-nmos:cap:format:media_type":
                        if flow["media_type"] != new_flow["media_type"]:
                            return test.FAIL("Different media_type")
                    if item == "urn:x-nmos:cap:format:grain_rate":
                        if flow["grain_rate"] != new_flow["grain_rate"]:
                            return test.FAIL("Different grain_rate")
                    if item == "urn:x-nmos:cap:format:frame_width":
                        if flow["frame_width"] != new_flow["frame_width"]:
                            return test.FAIL("Different frame_width")
                    if item == "urn:x-nmos:cap:format:frame_height":
                        if flow["frame_height"] != new_flow["frame_height"]:
                            return test.FAIL("Different frame_height")
                    if item == "urn:x-nmos:cap:format:interlace_mode":
                        if flow["interlace_mode"] != new_flow["interlace_mode"]:
                            return test.FAIL("Different interlace_mode")
                    if item == "urn:x-nmos:cap:format:color_sampling":
                        if color_sampling != new_color_sampling:
                            return test.FAIL("Different color_sampling")
                    if item == "urn:x-nmos:cap:format:component_depth":
                        if (
                            flow["components"][0]["bit_depth"]
                            != new_flow["components"][0]["bit_depth"]
                        ):
                            return test.FAIL("Different component_depth")
                except Exception:
                    pass
            valid, response = TestHelper.do_request(
                "DELETE",
                self.compat_url + "senders/" + sender_id + "constraints/active/",
            )
            if not valid:
                return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
            if response.status_code != 200:
                return test.FAIL(
                    "The sender {} constraints cannot be deleted".format(sender_id)
                )
        return test.PASS()

    def test_02_02_06_02(self, test):
        """
        Verify that setting no-op constraints for supported
        constraints doesn't change the flow of a sender(audio).
        """
        if len(self.flow_format_audio) == 0:
            return test.UNCLEAR("There is no audio format")
        for sender_id in self.flow_format_audio:
            valid, response = TestHelper.do_request(
                "GET", self.compat_url + "senders/" + sender_id + "status/"
            )
            if not valid:
                return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
            if response.status_code != 200:
                test.FAIL("The streamcompatibility request for sender {} status has failed: {}"
                          .format(sender_id, response.json()))
            state = response.json()["state"]
            if state in ["awating_essence", "no_essence"]:
                for i in range(0, 5):
                    valid, response = TestHelper.do_request(
                        "GET", self.compat_url + "senders/" + sender_id + "status/"
                    )
                    if not valid:
                        return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
                    if response.status_code != 200:
                        return test.FAIL(
                            "The streamcompatibility request for sender {} status has failed: {}"
                            .format(sender_id, response.json())
                        )
                    state = response.json()["state"]
                    if state in ["awating_essence", "no_essence"]:
                        time.sleep(CONFIG.STABLE_STATE_DELAY)
                    else:
                        break
            if state != "unconstrained":
                return test.FAIL("Inputs are unstable")
            valid, response = TestHelper.do_request(
                "GET", self.node_url + "senders/" + sender_id
            )
            if not valid:
                return test.FAIL("Unexpected response from the Node API: {}".format(response))
            if response.status_code != 200:
                return test.FAIL(
                    "The sender {} is not available in the Node API response: {}"
                    .format(sender_id, response.json())
                )
            sender = response.json()

            valid, response = TestHelper.do_request(
                "GET", self.node_url + "flows/" + sender["flow_id"]
            )
            if not valid:
                return test.FAIL("Unexpected response from the Node API: {}".format(response))
            if response.status_code != 200:
                return test.FAIL(
                    "The sender {} is not available in the Node API has an associated flow: {}"
                    .format(sender["flow_id"], response.json())
                )
            flow = response.json()
            constraint_set = {}

            valid, response = TestHelper.do_request(
                "GET", self.node_url + "sources/" + flow["source_id"]
            )
            if not valid:
                return test.FAIL("Unexpected response from the Node API: {}".format(response))
            if response.status_code != 200:
                return test.FAIL(
                    "The source {} is not available in the Node API: {}"
                    .format(flow["source_id"], response.json())
                )
            source = response.json()

            for item in REF_SUPPORTED_CONSTRAINTS_AUDIO:
                try:

                    if item == "urn:x-nmos:cap:meta:label":
                        constraint_set["urn:x-nmos:cap:meta:label"] = "audio constraint"
                    if item == "urn:x-nmos:cap:meta:preference":
                        constraint_set["urn:x-nmos:cap:meta:preference"] = 0
                    if item == "urn:x-nmos:cap:meta:enabled":
                        constraint_set["urn:x-nmos:cap:meta:enabled"] = True
                    if item == "urn:x-nmos:cap:format:media_type":
                        constraint_set["urn:x-nmos:cap:format:media_type"] = {
                            "enum": [flow["media_type"]]
                        }
                    if item == "urn:x-nmos:cap:format:sample_rate":
                        constraint_set["urn:x-nmos:cap:format:sample_rate"] = {
                            "enum": [flow["sample_rate"]]
                        }
                    if item == "urn:x-nmos:cap:format:channel_count":
                        constraint_set["urn:x-nmos:cap:format:channel_count"] = {
                            "enum": [len(source["channels"])]
                        }
                    if item == "urn:x-nmos:cap:format:sample_depth":
                        constraint_set["urn:x-nmos:cap:format:sample_depth"] = {
                            "enum": [flow["bit_depth"]]
                        }
                except Exception:
                    pass
            self.constraints[sender_id] = {"constraint_sets": [constraint_set]}
            valid, response = TestHelper.do_request(
                "PUT",
                self.compat_url + "senders/" + sender_id + "constraints/active/",
                json=self.constraints[sender_id],
            )
            if not valid:
                return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
            if response.status_code != 200:
                return test.FAIL(
                    "The sender {} constraints change has failed: {}"
                    .format(sender_id, response.json())
                )

            valid, response = TestHelper.do_request(
                "GET", self.node_url + "flows/" + sender["flow_id"]
            )
            if not valid:
                return test.FAIL("Unexpected response from the Node API: {}".format(response))
            if response.status_code != 200:
                return test.FAIL(
                    "The sender {} is not available in the Node API has an associated flow: {}"
                    .format(sender["flow_id"], response.json())
                )
            new_flow = response.json()

            valid, response = TestHelper.do_request(
                "GET", self.node_url + "sources/" + flow["source_id"]
            )
            if not valid:
                return test.FAIL("Unexpected response from the Node API: {}".format(response))
            if response.status_code != 200:
                return test.FAIL(
                    "The source {} is not available in the Node API: {}"
                    .format(flow["source_id"], response.json())
                )
            new_source = response.json()

            for item in REF_SUPPORTED_CONSTRAINTS_AUDIO:
                try:
                    if item == "urn:x-nmos:cap:format:media_type":
                        if flow["media_type"] != new_flow["media_type"]:
                            return test.FAIL("Different media_type")
                    if item == "urn:x-nmos:cap:format:sample_rate":
                        if flow["sample_rate"] != new_flow["sample_rate"]:
                            return test.FAIL("Different sample_rate")
                    if item == "urn:x-nmos:cap:format:channel_count":
                        if len(source["channels"]) != len(new_source["channels"]):
                            return test.FAIL("Different channel_count")
                    if item == "urn:x-nmos:cap:format:sample_depth":
                        if flow["bit_depth"] != new_flow["bit_depth"]:
                            return test.FAIL("Different sample_depth")
                except Exception:
                    pass
            valid, response = TestHelper.do_request(
                "DELETE",
                self.compat_url + "senders/" + sender_id + "constraints/active/",
            )
            if not valid:
                return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
            if response.status_code != 200:
                return test.FAIL(
                    "The sender {} constraints cannot be deleted".format(sender_id)
                )
        return test.PASS()

    def test_02_02_07_01(self, test):
        "Verify that the device adhere to the preference of the constraint_set."
        if len(self.flow_format_video) == 0:
            return test.UNCLEAR("There is no video format")

        for sender_id in self.flow_format_video:
            valid, response = TestHelper.do_request(
                "GET", self.compat_url + "senders/" + sender_id + "status/"
            )
            if not valid:
                return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
            if response.status_code != 200:
                return test.FAIL(
                    "The streamcompatibility request for sender {} status has failed: {}"
                    .format(sender_id, response.json())
                )
            state = response.json()["state"]
            if state in ["awating_essence", "no_essence"]:
                for i in range(0, 5):
                    valid, response = TestHelper.do_request(
                        "GET", self.compat_url + "senders/" + sender_id + "status/"
                    )
                    if not valid:
                        return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
                    if response.status_code != 200:
                        return test.FAIL(
                            "The streamcompatibility request for sender {} status has failed: {}"
                            .format(sender_id, response.json())
                        )
                    state = response.json()["state"]

                    if state in ["awating_essence", "no_essence"]:
                        time.sleep(CONFIG.STABLE_STATE_DELAY)
                    else:
                        break
            if state != "unconstrained":
                return test.FAIL("inputs are unstable")

            valid, response = TestHelper.do_request(
                "GET", self.node_url + "senders/" + sender_id
            )
            if not valid:
                return test.FAIL("Unexpected response from the Node API: {}".format(response))
            if response.status_code != 200:
                return test.FAIL(
                    "The sender {} is not available in the Node API response: {}"
                    .format(sender_id, response.json())
                )
            sender = response.json()

            valid, response = TestHelper.do_request(
                "GET", self.node_url + "flows/" + sender["flow_id"]
            )
            if not valid:
                return test.FAIL("Unexpected response from the Node API: {}".format(response))
            if response.status_code != 200:
                return test.FAIL(
                    "The sender {} is not available in the Node API has an associated flow: {}"
                    .format(sender["flow_id"], response.json())
                )
            flow = response.json()
            color_sampling = IS04Utils.make_sampling(flow["components"])
            if color_sampling is None:
                return test.FAIL("Invalid array of video components")
            constraint_set0 = {}
            constraint_set1 = {}

            for item in REF_SUPPORTED_CONSTRAINTS_VIDEO:
                try:

                    if item == "urn:x-nmos:cap:meta:label":
                        constraint_set0[
                            "urn:x-nmos:cap:meta:label"
                        ] = "video constraint"
                    if item == "urn:x-nmos:cap:meta:preference":
                        constraint_set0["urn:x-nmos:cap:meta:preference"] = 0
                    if item == "urn:x-nmos:cap:meta:enabled":
                        constraint_set0["urn:x-nmos:cap:meta:enabled"] = True
                    if item == "urn:x-nmos:cap:format:media_type":
                        constraint_set0["urn:x-nmos:cap:format:media_type"] = {
                            "enum": [flow["media_type"]]
                        }
                    if item == "urn:x-nmos:cap:format:grain_rate":
                        constraint_set0["urn:x-nmos:cap:format:grain_rate"] = {
                            "enum": [flow["grain_rate"]]
                        }
                    if item == "urn:x-nmos:cap:format:frame_width":
                        constraint_set0["urn:x-nmos:cap:format:frame_width"] = {
                            "enum": [flow["frame_width"]]
                        }
                    if item == "urn:x-nmos:cap:format:frame_height":
                        constraint_set0["urn:x-nmos:cap:format:frame_height"] = {
                            "enum": [flow["frame_height"]]
                        }
                    if item == "urn:x-nmos:cap:format:interlace_mode":
                        constraint_set0["urn:x-nmos:cap:format:interlace_mode"] = {
                            "enum": [flow["interlace_mode"]]
                        }
                    if item == "urn:x-nmos:cap:format:color_sampling":
                        constraint_set0["urn:x-nmos:cap:format:color_sampling"] = {
                            "enum": [color_sampling]
                        }
                    if item == "urn:x-nmos:cap:format:component_depth":
                        constraint_set0["urn:x-nmos:cap:format:component_depth"] = {
                            "enum": [flow["components"][0]["bit_depth"]]
                        }
                except Exception:
                    pass

            for item in REF_SUPPORTED_CONSTRAINTS_VIDEO:
                try:
                    if item == "urn:x-nmos:cap:meta:label":
                        constraint_set1[
                            "urn:x-nmos:cap:meta:label"
                        ] = "video constraint"
                    if item == "urn:x-nmos:cap:meta:preference":
                        constraint_set1["urn:x-nmos:cap:meta:preference"] = -100
                    if item == "urn:x-nmos:cap:meta:enabled":
                        constraint_set1["urn:x-nmos:cap:meta:enabled"] = True
                    if item == "urn:x-nmos:cap:format:media_type":
                        constraint_set1["urn:x-nmos:cap:format:media_type"] = {
                            "enum": [flow["media_type"]]
                        }
                    if item == "urn:x-nmos:cap:format:grain_rate":
                        constraint_set1["urn:x-nmos:cap:format:grain_rate"] = {
                            "enum": [self.get_another_grain_rate(flow["grain_rate"])]
                        }
                    if item == "urn:x-nmos:cap:format:frame_width":
                        constraint_set1["urn:x-nmos:cap:format:frame_width"] = {
                            "enum": [flow["frame_width"]]
                        }
                    if item == "urn:x-nmos:cap:format:frame_height":
                        constraint_set1["urn:x-nmos:cap:format:frame_height"] = {
                            "enum": [flow["frame_height"]]
                        }
                    if item == "urn:x-nmos:cap:format:interlace_mode":
                        constraint_set1["urn:x-nmos:cap:format:interlace_mode"] = {
                            "enum": [flow["interlace_mode"]]
                        }
                    if item == "urn:x-nmos:cap:format:color_sampling":
                        constraint_set1["urn:x-nmos:cap:format:color_sampling"] = {
                            "enum": [color_sampling]
                        }
                    if item == "urn:x-nmos:cap:format:component_depth":
                        constraint_set1["urn:x-nmos:cap:format:component_depth"] = {
                            "enum": [flow["components"][0]["bit_depth"]]
                        }
                except Exception:
                    pass

            self.constraints[sender_id] = {
                "constraint_sets": [constraint_set0, constraint_set0]
            }
            valid, response = TestHelper.do_request(
                "PUT",
                self.compat_url + "senders/" + sender_id + "constraints/active/",
                json=self.constraints[sender_id],
            )
            if not valid:
                return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
            if response.status_code != 200:
                return test.FAIL(
                    "The sender {} constraints change has failed: {}"
                    .format(sender_id, response.json())
                )

            valid, response = TestHelper.do_request(
                "GET", self.node_url + "flows/" + sender["flow_id"]
            )
            if not valid:
                return test.FAIL("Unexpected response from the Node API: {}".format(response))
            if response.status_code != 200:
                return test.FAIL(
                    "The sender {} is not available in the Node API has an associated flow: {}"
                    .format(sender["flow_id"], response.json())
                )
            new_flow = response.json()

            new_color_sampling = IS04Utils.make_sampling(new_flow["components"])
            if new_color_sampling is None:
                return test.FAIL("invalid array of video components")

            for item in REF_SUPPORTED_CONSTRAINTS_VIDEO:
                try:
                    if item == "urn:x-nmos:cap:format:media_type":
                        if flow["media_type"] != new_flow["media_type"]:
                            return test.FAIL("Different media_type")
                    if item == "urn:x-nmos:cap:format:grain_rate":
                        if flow["grain_rate"] != new_flow["grain_rate"]:
                            return test.FAIL("Different grain_rate")
                    if item == "urn:x-nmos:cap:format:frame_width":
                        if flow["frame_width"] != new_flow["frame_width"]:
                            return test.FAIL("Different frame_width")
                    if item == "urn:x-nmos:cap:format:frame_height":
                        if flow["frame_height"] != new_flow["frame_height"]:
                            return test.FAIL("Different frame_height")
                    if item == "urn:x-nmos:cap:format:interlace_mode":
                        if flow["interlace_mode"] != new_flow["interlace_mode"]:
                            return test.FAIL("Different interlace_mode")
                    if item == "urn:x-nmos:cap:format:color_sampling":
                        if color_sampling != new_color_sampling:
                            return test.FAIL("Different color_sampling")
                    if item == "urn:x-nmos:cap:format:component_depth":
                        if (
                            flow["components"][0]["bit_depth"]
                            != new_flow["components"][0]["bit_depth"]
                        ):
                            return test.FAIL("Different component_depth")
                except Exception:
                    pass

            valid, response = TestHelper.do_request(
                "DELETE",
                self.compat_url + "senders/" + sender_id + "constraints/active/",
            )
            if not valid:
                return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
            if response.status_code != 200:
                return test.FAIL(
                    "The sender {} constraints cannot be deleted".format(sender_id)
                )
        return test.PASS()

    def test_02_02_07_02(self, test):
        "Verify that the device adhere to the preference of the constraint_set."
        if len(self.flow_format_audio) == 0:
            return test.UNCLEAR("There is no audio format")

        for sender_id in self.flow_format_audio:
            valid, response = TestHelper.do_request(
                "GET", self.compat_url + "senders/" + sender_id + "status/"
            )
            if not valid:
                return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
            if response.status_code != 200:
                return test.FAIL("The streamcompatibility request for sender {} status has failed: {}"
                                 .format(sender_id, response.json()))
            state = response.json()["state"]
            if state in ["awating_essence", "no_essence"]:
                for i in range(0, 5):
                    valid, response = TestHelper.do_request(
                        "GET", self.compat_url + "senders/" + sender_id + "status/"
                    )
                    if not valid:
                        return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
                    if response.status_code != 200:
                        return test.FAIL(
                            "The streamcompatibility request for sender {} status has failed: {}"
                            .format(sender_id, response.json())
                        )
                    state = response.json()["state"]
                    if state in ["awating_essence", "no_essence"]:
                        time.sleep(CONFIG.STABLE_STATE_DELAY)
                    else:
                        break
            if state != "unconstrained":
                return test.FAIL("inputs are unstable")

            valid, response = TestHelper.do_request(
                "GET", self.node_url + "senders/" + sender_id
            )
            if not valid:
                return test.FAIL("Unexpected response from the Node API: {}".format(response))
            if response.status_code != 200:
                return test.FAIL(
                    "The sender {} is not available in the Node API response: {}"
                    .format(sender_id, response.json())
                )
            sender = response.json()

            valid, response = TestHelper.do_request(
                "GET", self.node_url + "flows/" + sender["flow_id"]
            )
            if not valid:
                return test.FAIL("Unexpected response from the Node API: {}".format(response))
            if response.status_code != 200:
                return test.FAIL(
                    "The sender {} is not available in the Node API has an associated flow: {}"
                    .format(sender["flow_id"], response.json())
                )
            flow = response.json()
            valid, response = TestHelper.do_request(
                "GET", self.node_url + "sources/" + flow["source_id"]
            )
            if not valid:
                return test.FAIL("Unexpected response from the Node API: {}".format(response))
            if response.status_code != 200:
                return test.FAIL(
                    "The source {} is not available in the Node API: {}"
                    .format(flow["source_id"], response.json())
                )
            source = response.json()

            constraint_set0 = {}
            constraint_set1 = {}

            for item in REF_SUPPORTED_CONSTRAINTS_AUDIO:
                try:
                    if item == "urn:x-nmos:cap:meta:label":
                        constraint_set0[
                            "urn:x-nmos:cap:meta:label"
                        ] = "audio constraint"
                    if item == "urn:x-nmos:cap:meta:preference":
                        constraint_set0["urn:x-nmos:cap:meta:preference"] = 0
                    if item == "urn:x-nmos:cap:meta:enabled":
                        constraint_set0["urn:x-nmos:cap:meta:enabled"] = True
                    if item == "urn:x-nmos:cap:format:media_type":
                        constraint_set0["urn:x-nmos:cap:format:media_type"] = {
                            "enum": [flow["media_type"]]
                        }
                    if item == "urn:x-nmos:cap:format:sample_rate":
                        constraint_set0["urn:x-nmos:cap:format:sample_rate"] = {
                            "enum": [flow["sample_rate"]]
                        }
                    if item == "urn:x-nmos:cap:format:channel_count":
                        constraint_set0["urn:x-nmos:cap:format:channel_count"] = {
                            "enum": [len(source["channels"])]
                        }
                    if item == "urn:x-nmos:cap:format:sample_depth":
                        constraint_set0["urn:x-nmos:cap:format:sample_depth"] = {
                            "enum": [flow["bit_depth"]]
                        }
                except Exception:
                    pass

            for item in REF_SUPPORTED_CONSTRAINTS_AUDIO:
                try:
                    if item == "urn:x-nmos:cap:meta:label":
                        constraint_set1[
                            "urn:x-nmos:cap:meta:label"
                        ] = "video constraint"
                    if item == "urn:x-nmos:cap:meta:preference":
                        constraint_set1["urn:x-nmos:cap:meta:preference"] = -100
                    if item == "urn:x-nmos:cap:meta:enabled":
                        constraint_set1["urn:x-nmos:cap:meta:enabled"] = True
                    if item == "urn:x-nmos:cap:format:media_type":
                        constraint_set1["urn:x-nmos:cap:format:media_type"] = {
                            "enum": [flow["media_type"]]
                        }
                    if item == "urn:x-nmos:cap:format:sample_rate":
                        constraint_set1["urn:x-nmos:cap:format:sample_rate"] = {
                            "enum": [self.get_another_sample_rate(flow["sample_rate"])]
                        }
                    if item == "urn:x-nmos:cap:format:channel_count":
                        constraint_set1["urn:x-nmos:cap:format:channel_count"] = {
                            "enum": [len(source["channels"])]
                        }
                    if item == "urn:x-nmos:cap:format:sample_depth":
                        constraint_set1["urn:x-nmos:cap:format:sample_depth"] = {
                            "enum": [flow["bit_depth"]]
                        }
                except Exception:
                    pass

            self.constraints[sender_id] = {
                "constraint_sets": [constraint_set0, constraint_set1]
            }

            valid, response = TestHelper.do_request(
                "PUT",
                self.compat_url + "senders/" + sender_id + "constraints/active/",
                json=self.constraints[sender_id],
            )
            if not valid:
                return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
            if response.status_code != 200:
                return test.FAIL(
                    "The sender {} constraints change has failed: {}"
                    .format(sender_id, response.json())
                )
            valid, response = TestHelper.do_request(
                "GET", self.node_url + "flows/" + sender["flow_id"]
            )
            if not valid:
                return test.FAIL("Unexpected response from the Node API: {}".format(response))
            if response.status_code != 200:
                return test.FAIL(
                    "The sender {} is not available in the Node API has an associated flow: {}"
                    .format(sender["flow_id"], response.json())
                )
            new_flow = response.json()

            valid, response = TestHelper.do_request(
                "GET", self.node_url + "sources/" + flow["source_id"]
            )
            if not valid:
                return test.FAIL("Unexpected response from the Node API: {}".format(response))
            if response.status_code != 200:
                return test.FAIL(
                    "The source {} is not available in the Node API: {}"
                    .format(flow["source_id"], response.json())
                )
            new_source = response.json()

            for item in REF_SUPPORTED_CONSTRAINTS_AUDIO:
                try:
                    if item == "urn:x-nmos:cap:format:media_type":
                        if flow["media_type"] != new_flow["media_type"]:
                            return test.FAIL("Different media_type")
                    if item == "urn:x-nmos:cap:format:sample_rate":
                        if flow["sample_rate"] != new_flow["sample_rate"]:
                            return test.FAIL("Different sample_rate")
                    if item == "urn:x-nmos:cap:format:channel_count":
                        if len(source["channels"]) != len(new_source["channels"]):
                            return test.FAIL("Different channel_count")
                    if item == "urn:x-nmos:cap:format:sample_depth":
                        if flow["bit_depth"] != new_flow["bit_depth"]:
                            return test.FAIL("Different sample_depth")
                except Exception:
                    pass
            valid, response = TestHelper.do_request(
                "DELETE",
                self.compat_url + "senders/" + sender_id + "constraints/active/",
            )
            if not valid:
                return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
            if response.status_code != 200:
                return test.FAIL(
                    "The sender {} constraints cannot be deleted".format(sender_id)
                )
        return test.PASS()

    # OUTPUTS TESTS
    def test_03_01(self, test):
        """
        Verify that the device supports the concept of Output.
        """
        valid, response = TestHelper.do_request("GET", self.compat_url + "outputs/")
        if not valid:
            return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
        if response.status_code == 200:
            if len(response.json()) != 0:
                self.outputs.append(response.json()[0])
            if len(self.outputs) == 0:
                return test.UNCLEAR("No outputs")
            return test.PASS()
        return test.FAIL("The outputs streamcompatibility request has failed: {}"
                         .format(response.json()))

    def test_03_02(self, test):
        """
        Verify that some of the outputs of the device are connected.
        """
        if len(self.outputs) == 0:
            return test.UNCLEAR("No IS-11 outputs")
        for output in self.outputs:
            valid, response = TestHelper.do_request(
                "GET", self.compat_url + "outputs/" + output + "properties/"
            )
            if not valid:
                return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
            if response.status_code == 200:
                outputs_properties_json = []
                outputs_properties_json.append(response.json())
                for output in outputs_properties_json:
                    if output["connected"]:
                        self.connected_outputs.append(output["id"])
            else:
                return test.FAIL("The output {} properties streamcompatibility request has failed: {}"
                                 .format(output, response.json()))
        if len(self.connected_outputs) == 0:
            return test.UNCLEAR("No connected outputs")
        return test.PASS()

    def test_03_03(self, test):
        """
        Verify that all connected outputs do not have
        a signal as test 0 put all of the receivers inactive.
        """
        if len(self.connected_outputs) == 0:
            return test.UNCLEAR("No connected outputs")
        for output_id in self.connected_outputs:
            valid, response = TestHelper.do_request(
                "GET", self.compat_url + "outputs/" + output_id + "/properties/"
            )
            if not valid:
                return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
            if response.status_code == 200:
                if response.json()["status"]["state"] == "signal_present":
                    self.active_connected_outputs.append(response.json())
            else:
                return test.FAIL("The output {} properties streamcompatibility request has failed: {}"
                                 .format(output_id, response.json()))
        if len(self.active_connected_outputs) != 0:
            return test.UNCLEAR(
                "Connected output have a signal while all receivers are inactive."
            )
        return test.PASS()

    def test_03_04(self, test):
        """
        Verify that connected outputs supporting EDID behave according to the RAML file.
        """
        if len(self.connected_outputs) == 0:
            return test.UNCLEAR("No connected outputs")
        for output_id in self.connected_outputs:
            valid, response = TestHelper.do_request(
                "GET", self.compat_url + "outputs/" + output_id + "/properties/"
            )
            if not valid:
                return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
            if response.status_code == 200:
                if response.json()["edid_support"]:
                    self.edid_connected_outputs.append(response.json()["id"])
            else:
                return test.FAIL("The output {} properties streamcompatibility request has failed: {}"
                                 .format(output_id, response.json()))
        if self.edid_connected_outputs == 0:
            return test.UNCLEAR("Outputs not supporting edid")
        return test.PASS()

    def test_03_04_01(self, test):
        """
        Verify that an output indicating EDID support behaves according to the RAML file.
        """
        if len(self.edid_connected_outputs) == 0:
            return test.UNCLEAR("No edid connected outputs")
        for output_id in self.edid_connected_outputs:
            valid, response = TestHelper.do_request(
                "GET", self.compat_url + "outputs/" + output_id
            )
            if not valid:
                return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
            if response.status_code != 200:
                return test.FAIL("The streamcompatibility request for output {} has failed: {}"
                                 .format(output_id, response.json()))
        return test.PASS()

    def test_03_04_02(self, test):
        """
        Verify that a valid EDID can be retrieved from the device;
        this EDID represents the default EDID of the device.
        """
        is_valid_response = True
        if len(self.edid_connected_outputs) == 0:
            return test.UNCLEAR("No edid connected outputs")
        for output_id in self.edid_connected_outputs:
            valid, response = TestHelper.do_request(
                "GET", self.compat_url + "outputs/" + output_id + "/edid/"
            )
            if not valid:
                return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
            if (
                response.status_code != 200
                or response.headers["Content-Type"] != "application/octet-stream"
            ):
                is_valid_response = False
            break
        if is_valid_response:
            return test.PASS()
        return test.FAIL("The output {} edid streamcompatibility request has failed: {}"
                         .format(output_id, response.json()))

    def test_03_05(self, test):
        """
        Verify that connected outputs not supporting EDID behave according to the RAML file.
        """
        if len(self.connected_outputs) == 0:
            return test.UNCLEAR("No connected outputs")
        for output_id in self.connected_outputs:
            valid, response = TestHelper.do_request(
                "GET", self.compat_url + "outputs/" + output_id + "/properties/"
            )
            if not valid:
                return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
            if response.status_code == 200:
                if not response.json()["edid_support"]:
                    self.not_edid_connected_outputs.append(response.json()["id"])
            else:
                return test.FAIL("The output {} properties streamcompatibility request has failed: {}"
                                 .format(output_id, response.json()))
        if len(self.not_edid_connected_outputs) == 0:
            return test.UNCLEAR("Outputs supporting edid")
        return test.PASS()

    def test_03_05_01(self, test):
        """
        Verify that there is no EDID support.
        """
        if len(self.not_edid_connected_outputs) == 0:
            return test.UNCLEAR("None of not edid connected outputs")
        for output_id in self.not_edid_connected_outputs:
            valid, response = TestHelper.do_request(
                "GET", self.compat_url + "outputs/" + output_id + "/edid/"
            )
            if not valid:
                return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
            if response.status_code != 204:
                return test.FAIL("Status code should be 204")
        return test.PASS()

    # RECEIVERS TESTS
    def test_04_01(self, test):
        """
        Verify that the device supports the concept of IS-11 Receiver.
        """
        valid, response = TestHelper.do_request("GET", self.compat_url + "receivers/")
        if not valid:
            return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
        if response.status_code != 200:
            return test.FAIL("The receiver's streamcompatibility request has failed: {}"
                             .format(response.json()))
        self.receivers = response.json()
        if len(self.receivers) == 0:
            return test.UNCLEAR("No IS-11 receivers")
        return test.PASS()

    def test_04_01_01(self, test):
        """
        Verify that IS-11 Receivers exist on the Node API as Receivers.
        """
        if len(self.receivers) == 0:
            return test.UNCLEAR("No IS-11 receivers")
        for receiver_id in self.receivers:
            valid, response = TestHelper.do_request(
                "GET", self.node_url + "receivers/" + receiver_id
            )
            if not valid:
                return test.FAIL("Unexpected response from the Node API: {}".format(response))
            if response.status_code != 200:
                return test.FAIL("The Node API request for receiver {} has failed: {}"
                                 .format(receiver_id, response.json()))
            if response.json()["id"] != receiver_id[:-1]:
                return test.UNCLEAR(
                    "The IS-11 Receiver doesn't exist on the Node API as receiver."
                )
        return test.PASS()

    def test_04_02(self, test):
        """
        Verify receivers (generic with/without outputs)
        """
        valid, response = TestHelper.do_request("GET", self.compat_url + "receivers/")
        if not valid:
            return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
        if response.status_code != 200:
            return test.FAIL("The receiver's streamcompatibility request has failed: {}"
                             .format(response.json()))
        self.receivers = response.json()
        if len(self.receivers) == 0:
            return test.UNCLEAR("No IS-11 receivers")
        return test.PASS()

    def test_04_02_01(self, test):
        """
        Verify that the status is "unknown" or "non_compliant_stream"
        as per our pre-conditions of not being master_enabled.
        """
        if len(self.receivers) == 0:
            return test.UNCLEAR("No IS-11 receivers")
        for receiver_id in self.receivers:
            valid, response = TestHelper.do_request(
                "GET", self.compat_url + "receivers/" + receiver_id + "status/"
            )
            if not valid:
                return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
            if response.status_code != 200:
                return test.FAIL("The streamcompatibility request for receiver {} has failed: {}"
                                 .format(receiver_id, response.json()))
            if response.json()["state"] not in ["unknown", "non_compliant_stream"]:
                return test.FAIL("The state is not unknown or non_compliant_stream")
        return test.PASS()

    def test_04_02_02(self, test):
        """
        Verify that the Receiver supports Receiver Capabilities.
        """
        if len(self.receivers) == 0:
            return test.UNCLEAR("No IS-11 receivers")
        for receiver_id in self.receivers:
            valid, response = TestHelper.do_request(
                "GET", self.node_url + "receivers/" + receiver_id
            )
            if not valid:
                return test.FAIL("Unexpected response from the Node API: {}".format(response))
            if response.status_code != 200:
                return test.FAIL("The Node API request for receiver {} has failed: {}"
                                 .format(receiver_id, response.json()))
            self.caps = response.json()["caps"]
            if "constraint_sets" not in self.caps:
                return test.UNCLEAR("The receiver does not have constraint_sets in caps")
            if len(self.caps["constraint_sets"]) == 0:
                return test.WARNING("The receiver does not support BCP-004-01.")
        return test.PASS()
