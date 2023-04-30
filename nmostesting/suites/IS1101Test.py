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

from requests.compat import json
import time
import re

from ..NMOSUtils import NMOSUtils
from ..GenericTest import GenericTest
from .. import TestHelper
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
        self.receivers_outputs = ""
        self.caps = ""
        self.node_url = self.apis[NODE_API_KEY]["url"]
        self.compat_url = self.apis[COMPAT_API_KEY]["url"]
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

    # GENERAL TESTS
    def test_00_01(self, test):
        """At least one Device is showing an IS-11 control advertisement matching the API under test"""

        valid, devices = self.do_request("GET", self.node_url + "devices")
        if not valid:
            return test.FAIL("Node API did not respond as expected: {}".format(devices))

        is11_devices = []
        found_api_match = False
        try:
            device_type = "urn:x-nmos:control:stream-compat/" + self.apis[COMPAT_API_KEY]["version"]
            for device in devices.json():
                controls = device["controls"]
                for control in controls:
                    if control["type"] == device_type:
                        is11_devices.append(control["href"])
                        if NMOSUtils.compare_urls(self.compat_url, control["href"]) and \
                                self.authorization is control.get("authorization", False):
                            found_api_match = True
        except json.JSONDecodeError:
            return test.FAIL("Non-JSON response returned from Node API")
        except KeyError:
            return test.FAIL("One or more Devices were missing the 'controls' attribute")

        if len(is11_devices) > 0 and found_api_match:
            return test.PASS()
        elif len(is11_devices) > 0:
            return test.FAIL("Found one or more Device controls, but no href and authorization mode matched the "
                             "Stream Compatibility Management API under test")
        else:
            return test.FAIL("Unable to find any Devices which expose the control type '{}'".format(device_type))


    def test_00_02(self, test):
        "Put all senders into inactive state"
        senders_url = self.conn_url + "single/senders/"
        _, response = TestHelper.do_request("GET", senders_url)
        if response.status_code != 200:
            return test.FAIL("The request has not succeeded: {}".format(response.json()))
        senders = response.json()
        if len(senders) > 0:
            for sender in senders:
                url = senders_url + sender + "staged/"
                deactivate_json = {
                    "master_enable": False,
                    "activation": {"mode": "activate_immediate"},
                }

                _, response = TestHelper.do_request("PATCH", url, json=deactivate_json)
                if (
                    response.status_code != 200
                    or response.json()["master_enable"]
                    or response.json()["activation"]["mode"] != "activate_immediate"
                ):
                    return test.FAIL("The request has not succeeded: {}".format(response.json()))
            return test.PASS()
        return test.UNCLEAR("Could not find any senders to test")

    def test_00_03(self, test):
        "Put all the receivers into inactive state"
        receivers_url = self.conn_url + "single/receivers/"
        _, response = TestHelper.do_request("GET", receivers_url)
        if response.status_code != 200:
            return test.FAIL("The request has not succeeded: {}".format(response.json()))
        receivers = response.json()
        if len(receivers) > 0:
            for receiver in receivers:
                url = receivers_url + receiver + "staged/"
                deactivate_json = {
                    "master_enable": False,
                    "activation": {"mode": "activate_immediate"},
                }
                _, response = TestHelper.do_request("PATCH", url, json=deactivate_json)
                if (
                    response.status_code != 200
                    or response.json()["master_enable"]
                    or response.json()["activation"]["mode"] != "activate_immediate"
                ):
                    return test.FAIL("The request has not succeeded: {}".format(response.json()))

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
        _, response = TestHelper.do_request("GET", self.compat_url + "senders/")
        if response.status_code != 200:
            return test.FAIL(
                "The request has not succeeded: {}".format(response.json())
            )
        self.senders = response.json()
        if len(self.senders) != 0:
            for sender in self.senders:
                _, response = TestHelper.do_request(
                    "DELETE",
                    self.compat_url + "senders/" + sender + "constraints/active/",
                )
                if response.status_code != 200:
                    return test.FAIL("senders constraints cannot be deleted")
            return test.PASS()
        return test.UNCLEAR("There is no IS-11 senders.")

    def test_02_01(self, test):
        "Verify that the device supports the concept of IS-11 Sender"
        _, response = TestHelper.do_request("GET", self.compat_url + "senders/")
        if response.status_code != 200:
            return test.FAIL(
                "The request has not succeeded: {}".format(response.json())
            )
        self.senders = response.json()
        if len(self.senders) == 0:
            return test.UNCLEAR("There is no IS-11 senders.")
        return test.PASS()

    def test_02_01_01(self, test):
        "Verify that the device supports the concept of IS-11 Sender"
        if len(self.senders) != 0:
            for sender_id in self.senders:
                _, response = TestHelper.do_request(
                    "GET", self.node_url + "senders/" + sender_id
                )
                if response.status_code != 200:
                    return test.FAIL(
                        "The request has not succeeded: {}".format(response.json())
                    )
                sender_node = response.json()["id"]
                if sender_id[:-1] != sender_node:
                    return test.FAIL("Senders are different")
            return test.PASS()
        return test.UNCLEAR("There is no IS-11 senders.")

    def test_02_02(self, test):
        "Verify senders (generic with/without inputs)"
        _, response = TestHelper.do_request("GET", self.compat_url + "senders/")
        if response.status_code != 200:
            return test.FAIL(
                "The request has not succeeded: {}".format(response.json())
            )
        self.senders_2 = response.json()
        if len(self.senders_2) == 0:
            return test.UNCLEAR("There is no IS-11 senders.")
        return test.PASS()

    def test_02_02_01(self, test):
        "Verify that the status is unconstrained as per our pre-conditions"
        if len(self.senders_2) != 0:
            for sender_id in self.senders_2:
                _, response = TestHelper.do_request(
                    "GET", self.compat_url + "senders/" + sender_id + "status/"
                )
                if response.status_code != 200:
                    return test.FAIL(
                        "The request has not succeeded: {}".format(response.json())
                    )
                state = response.json()["state"]
                if state in ["awating_essence", "no_essence"]:
                    for i in range(0, 5):
                        _, response = TestHelper.do_request(
                            "GET", self.compat_url + "senders/" + sender_id + "status/"
                        )
                        if response.status_code != 200:
                            return test.FAIL(
                                "The request has not succeeded: {}".format(
                                    response.json()
                                )
                            )
                        state = response.json()["state"]
                        if state in ["awating_essence", "no_essence"]:
                            time.sleep(3)
                        else:
                            break
                if state != "unconstrained":
                    return test.FAIL("inputs are unstable.")
            return test.PASS()
        return test.UNCLEAR("There is no IS-11 senders.")

    def test_02_02_03(self, test):
        """
        Verify that the sender is available in the node API,
        has an associated flow and is inactive
        """
        if len(self.senders_2) != 0:
            for sender_id in self.senders_2:
                _, response = TestHelper.do_request(
                    "GET", self.node_url + "senders/" + sender_id
                )
                if response.status_code != 200:
                    return test.FAIL(
                        "The request has not succeeded: {}".format(response.json())
                    )
                sender_node = response.json()["id"]
                if sender_id[:-1] != sender_node:
                    return test.FAIL("Senders are different")
                sender_flow_id = response.json()["flow_id"]
                if sender_flow_id is None:
                    return test.FAIL("the sender {} must have a flow".format(sender_id))
                sender_subscription_active = response.json()["subscription"]["active"]
                if sender_subscription_active:
                    return test.FAIL(
                        "the sender {} must be inactive ".format(sender_id)
                    )
                _, response = TestHelper.do_request(
                    "GET", self.node_url + "flows/" + sender_flow_id
                )
                if response.status_code != 200:
                    return test.FAIL(
                        "The request has not succeeded: {}".format(response.json())
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
                    print("only audio and video senders are tested at this time.")
            return test.PASS()
        return test.UNCLEAR("There is no IS-11 senders.")

    def test_02_02_03_01(self, test):
        "Verify that the video sender supports the minimum set of video constraints"

        pattern = "^urn:x-nmos:cap:"

        if len(self.flow_format_video) == 0:
            return test.UNCLEAR("There is no video format.")

        for sender_id in self.flow_format_video:
            _, response = TestHelper.do_request(
                "GET",
                self.compat_url + "senders/" + sender_id + "constraints/supported/",
            )
            if response.status_code != 200:
                return test.FAIL(
                    "The request has not succeeded: {}".format(response.json())
                )
            supportedConstraints = response.json()["parameter_constraints"]
            for item in supportedConstraints:
                if not re.search(pattern, item):
                    return test.FAIL("only x-nmos:cap constraints are allowed")
            for item in REF_SUPPORTED_CONSTRAINTS_VIDEO:
                if item not in supportedConstraints:
                    return test.FAIL(item + " is not in supportedConstraints ")
        return test.PASS()

    def test_02_02_03_02(self, test):
        "Verify that the video sender supports the minimum set of video constraints"

        pattern = "^urn:x-nmos:cap:"

        if len(self.flow_format_audio) == 0:
            return test.UNCLEAR("There is no audio format.")

        for sender_id in self.flow_format_audio:
            _, response = TestHelper.do_request(
                "GET",
                self.compat_url + "senders/" + sender_id + "constraints/supported/",
            )
            if response.status_code != 200:
                return test.FAIL(
                    "The request has not succeeded: {}".format(response.json())
                )
            supportedConstraints = response.json()["parameter_constraints"]
            for item in supportedConstraints:
                if not re.search(pattern, item):
                    return test.FAIL("only x-nmos:cap constraints are allowed")
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
            return test.UNCLEAR("There is no video format.")

        for sender_id in self.flow_format_video:
            _, response = TestHelper.do_request(
                "GET", self.node_url + "senders/" + sender_id
            )
            if response.status_code != 200:
                return test.FAIL(
                    "The request has not succeeded: {}".format(response.json())
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
            _, response = TestHelper.do_request(
                "PUT",
                self.compat_url + "senders/" + sender_id + "constraints/active/",
                json=self.grain_rate_constraints[sender_id],
            )
            if response.status_code != 200:
                return test.FAIL(
                    "The request has not succeeded: {}".format(response.json())
                )
            _, response = TestHelper.do_request(
                "GET", self.node_url + "senders/" + sender_id
            )
            if response.status_code != 200:
                return test.FAIL(
                    "The request has not succeeded: {}".format(response.json())
                )
            version = response.json()["version"]
            if version == self.version[sender_id]:
                return test.FAIL("Version are different")
            self.version[sender_id] = version
            _, response = TestHelper.do_request(
                "GET", self.compat_url + "senders/" + sender_id + "constraints/active/"
            )
            if response.status_code != 200:
                return test.FAIL(
                    "The request has not succeeded: {}".format(response.json())
                )
            constraints = response.json()
            if not IS04Utils.compare_constraint_sets(
                constraints["constraint_sets"],
                self.grain_rate_constraints[sender_id]["constraint_sets"],
            ):
                return test.FAIL("Contraints are different")
            _, response = TestHelper.do_request(
                "DELETE",
                self.compat_url + "senders/" + sender_id + "constraints/active/",
            )
            if response.status_code != 200:
                return test.FAIL(
                    "The request has not succeeded: {}".format(response.json())
                )
            _, response = TestHelper.do_request(
                "GET", self.node_url + "senders/" + sender_id
            )
            if response.status_code != 200:
                return test.FAIL(
                    "The request has not succeeded: {}".format(response.json())
                )
            version = response.json()["version"]
            if version == self.version[sender_id]:
                return test.FAIL("Version are different")
            self.version[sender_id] = version
            _, response = TestHelper.do_request(
                "GET", self.compat_url + "senders/" + sender_id + "constraints/active/"
            )
            if response.status_code != 200:
                return test.FAIL(
                    "The request has not succeeded: {}".format(response.json())
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
            return test.UNCLEAR("There is no audio format.")
        for sender_id in self.flow_format_audio:
            _, response = TestHelper.do_request(
                "GET", self.node_url + "senders/" + sender_id
            )
            if response.status_code != 200:
                return test.FAIL(
                    "The request has not succeeded: {}".format(response.json())
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
            _, response = TestHelper.do_request(
                "PUT",
                self.compat_url + "senders/" + sender_id + "constraints/active/",
                json=self.sample_rate_constraints[sender_id],
            )
            if response.status_code != 200:
                return test.FAIL(
                    "The request has not succeeded: {}".format(response.json())
                )
            _, response = TestHelper.do_request(
                "GET", self.node_url + "senders/" + sender_id
            )
            if response.status_code != 200:
                return test.FAIL(
                    "The request has not succeeded: {}".format(response.json())
                )
            version = response.json()["version"]
            if version == self.version[sender_id]:
                return test.FAIL("Version are different")
            self.version[sender_id] = version

            _, response = TestHelper.do_request(
                "GET", self.compat_url + "senders/" + sender_id + "constraints/active/"
            )
            if response.status_code != 200:
                return test.FAIL(
                    "The request has not succeeded: {}".format(response.json())
                )
            constraints = response.json()

            if not IS04Utils.compare_constraint_sets(
                constraints["constraint_sets"],
                self.sample_rate_constraints[sender_id]["constraint_sets"],
            ):
                return test.FAIL(
                    "constraints and SampleRateConstraints["
                    + sender_id
                    + "] are different "
                )

            _, response = TestHelper.do_request(
                "DELETE",
                self.compat_url + "senders/" + sender_id + "constraints/active/",
            )
            if response.status_code != 200:
                return test.FAIL(
                    "The request has not succeeded: {}".format(response.json())
                )

            _, response = TestHelper.do_request(
                "GET", self.node_url + "senders/" + sender_id
            )
            if response.status_code != 200:
                return test.FAIL(
                    "The request has not succeeded: {}".format(response.json())
                )
            version = response.json()["version"]
            if version == self.version[sender_id]:
                return test.FAIL("Version are different")
            self.version[sender_id] = version

            _, response = TestHelper.do_request(
                "GET", self.compat_url + "senders/" + sender_id + "constraints/active/"
            )
            if response.status_code != 200:
                return test.FAIL(
                    "The request has not succeeded: {}".format(response.json())
                )
            constraints = response.json()
            if constraints != self.empty_constraints[sender_id]:
                return test.FAIL("Contraints are different")
        return test.PASS()

    def test_02_02_05_01(self, test):
        """
        Verify that setting NOP constraints for frame(width,height),
        grain_rate doesn't change the flow of a sender(video).
        """
        if len(self.flow_format_video) == 0:
            return test.UNCLEAR("There is no video format.")

        for sender_id in self.flow_format_video:
            _, response = TestHelper.do_request(
                "GET", self.compat_url + "senders/" + sender_id + "status/"
            )
            if response.status_code != 200:
                return test.FAIL(
                    "The request has not succeeded: {}".format(response.json())
                )
            state = response.json()["state"]
            if state in ["awating_essence", "no_essence"]:
                for i in range(0, 5):
                    _, response = TestHelper.do_request(
                        "GET", self.compat_url + "senders/" + sender_id + "status/"
                    )
                    if response.status_code != 200:
                        return test.FAIL(
                            "The request has not succeeded: {}".format(response.json())
                        )
                    state = response.json()["state"]
                    if state in ["awating_essence", "no_essence"]:
                        time.sleep(3)
                    else:
                        break
            if state != "unconstrained":
                return test.FAIL("inputs are unstable.")

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

            _, response = TestHelper.do_request(
                "PUT",
                self.compat_url + "senders/" + sender_id + "constraints/active/",
                json=self.constraints[sender_id],
            )
            if response.status_code != 200:
                return test.FAIL(
                    "The request has not succeeded: {}".format(response.json())
                )

            _, response = TestHelper.do_request(
                "GET", self.compat_url + "senders/" + sender_id + "status/"
            )
            if response.status_code != 200:
                return test.FAIL(
                    "The request has not succeeded: {}".format(response.json())
                )
            state = response.json()["state"]

            if state in ["awating_essence", "no_essence"]:
                for i in range(0, 5):
                    _, response = TestHelper.do_request(
                        "GET", self.compat_url + "senders/" + sender_id + "status/"
                    )
                    if response.status_code != 200:
                        return test.FAIL(
                            "The request has not succeeded: {}".format(response.json())
                        )
                    state = response.json()["state"]
                    if state in ["awating_essence", "no_essence"]:
                        time.sleep(3)
                    else:
                        break
            if state != "constrained":
                return test.FAIL("inputs are unstable.")

            _, response = TestHelper.do_request(
                "GET", self.node_url + "senders/" + sender_id
            )
            if response.status_code != 200:
                return test.FAIL(
                    "The request has not succeeded: {}".format(response.json())
                )
            sender_flow_id = response.json()["flow_id"]
            if sender_flow_id is None:
                return test.FAIL("the sender must have a flow")

            _, response = TestHelper.do_request(
                "GET", self.node_url + "flows/" + sender_flow_id
            )
            if response.status_code != 200:
                return test.FAIL(
                    "The request has not succeeded: {}".format(response.json())
                )

            if (
                self.flow_grain_rate[sender_id] != response.json()["grain_rate"]
                or self.flow_width[sender_id] != response.json()["frame_width"]
                or self.flow_height[sender_id] != response.json()["frame_height"]
            ):
                return test.FAIL("different argument")

            _, response = TestHelper.do_request(
                "DELETE",
                self.compat_url + "senders/" + sender_id + "constraints/active/",
            )
            if response.status_code != 200:
                return test.FAIL(
                    "The request has not succeeded: {}".format(response.json())
                )

        return test.PASS()

    def test_02_02_05_02(self, test):
        """
        Verify that setting NOP constraints for sample_rate doesn't change the flow of a sender(audio).
        """

        if len(self.flow_format_audio) == 0:
            return test.UNCLEAR("There is no audio format.")

        for sender_id in self.flow_format_audio:
            _, response = TestHelper.do_request(
                "GET", self.compat_url + "senders/" + sender_id + "status/"
            )
            if response.status_code != 200:
                return test.FAIL(
                    "The request has not succeeded: {}".format(response.json())
                )
            state = response.json()["state"]

            if state in ["awating_essence", "no_essence"]:
                for i in range(0, 5):
                    _, response = TestHelper.do_request(
                        "GET", self.compat_url + "senders/" + sender_id + "status/"
                    )
                    if response.status_code != 200:
                        return test.FAIL(
                            "The request has not succeeded: {}".format(response.json())
                        )
                    state = response.json()["state"]
                    if state in ["awating_essence", "no_essence"]:
                        time.sleep(3)
                    else:
                        break
            if state != "unconstrained":
                return test.FAIL("inputs are unstable.")

            self.constraints[sender_id] = {
                "constraint_sets": [
                    {
                        "urn:x-nmos:cap:format:sample_rate": {
                            "enum": [self.flow_sample_rate[sender_id]]
                        }
                    }
                ]
            }
            _, response = TestHelper.do_request(
                "PUT",
                self.compat_url + "senders/" + sender_id + "constraints/active/",
                json=self.constraints[sender_id],
            )
            if response.status_code != 200:
                return test.FAIL(
                    "The request has not succeeded: {}".format(response.json())
                )

            _, response = TestHelper.do_request(
                "GET", self.compat_url + "senders/" + sender_id + "status/"
            )
            if response.status_code != 200:
                return test.FAIL(
                    "The request has not succeeded: {}".format(response.json())
                )
            state = response.json()["state"]

            if state in ["awating_essence", "no_essence"]:
                for i in range(0, 5):
                    _, response = TestHelper.do_request(
                        "GET", self.compat_url + "senders/" + sender_id + "status/"
                    )
                    if response.status_code != 200:
                        return test.FAIL(
                            "The request has not succeeded: {}".format(response.json())
                        )
                    state = response.json()["state"]
                    if state in ["awating_essence", "no_essence"]:
                        time.sleep(3)
                    else:
                        break
            if state != "constrained":
                return test.FAIL("inputs are unstable.")

            _, response = TestHelper.do_request(
                "GET", self.node_url + "senders/" + sender_id
            )
            if response.status_code != 200:
                return test.FAIL(
                    "The request has not succeeded: {}".format(response.json())
                )
            sender_flow_id = response.json()["flow_id"]
            if sender_flow_id is None:
                return test.FAIL("the sender must have a flow")

            _, response = TestHelper.do_request(
                "GET", self.node_url + "flows/" + sender_flow_id
            )
            if response.status_code != 200:
                return test.FAIL(
                    "The request has not succeeded: {}".format(response.json())
                )
            flow_sample_rate = response.json()["sample_rate"]
            if self.flow_sample_rate[sender_id] != flow_sample_rate:
                return test.FAIL("Different sample rate")

            _, response = TestHelper.do_request(
                "DELETE",
                self.compat_url + "senders/" + sender_id + "constraints/active/",
            )
            if response.status_code != 200:
                return test.FAIL(
                    "The request has not succeeded: {}".format(response.json())
                )
        return test.PASS()

    def test_02_02_06_01(self, test):
        """
        Verify that setting NOP constraints for supported constraints
        doesn't change the flow of a sender(video).
        """
        if len(self.flow_format_video) == 0:
            return test.UNCLEAR("There is no video format.")

        for sender_id in self.flow_format_video:
            _, response = TestHelper.do_request(
                "GET", self.compat_url + "senders/" + sender_id + "status/"
            )
            if response.status_code != 200:
                return test.FAIL(
                    "The request has not succeeded: {}".format(response.json())
                )
            state = response.json()["state"]
            if state in ["awating_essence", "no_essence"]:
                for i in range(0, 5):
                    _, response = TestHelper.do_request(
                        "GET", self.compat_url + "senders/" + sender_id + "status/"
                    )
                    if response.status_code != 200:
                        return test.FAIL(
                            "The request has not succeeded: {}".format(response.json())
                        )
                    state = response.json()["state"]
                    if state in ["awating_essence", "no_essence"]:
                        time.sleep(3)
                    else:
                        break
            if state != "unconstrained":
                return test.FAIL("inputs are unstable.")

            _, response = TestHelper.do_request(
                "GET", self.node_url + "senders/" + sender_id
            )
            if response.status_code != 200:
                return test.FAIL(
                    "The request has not succeeded: {}".format(response.json())
                )
            sender = response.json()

            _, response = TestHelper.do_request(
                "GET", self.node_url + "flows/" + sender["flow_id"]
            )
            if response.status_code != 200:
                return test.FAIL(
                    "The request has not succeeded: {}".format(response.json())
                )
            flow = response.json()
            color_sampling = IS04Utils.make_sampling(flow["components"])
            if color_sampling is None:
                return test.FAIL("invalid array of video components")
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

            _, response = TestHelper.do_request(
                "PUT",
                self.compat_url + "senders/" + sender_id + "constraints/active/",
                json=self.constraints[sender_id],
            )
            if response.status_code != 200:
                return test.FAIL(
                    "The request has not succeeded: {}".format(response.json())
                )

            _, response = TestHelper.do_request(
                "GET", self.node_url + "flows/" + sender["flow_id"]
            )
            if response.status_code != 200:
                return test.FAIL(
                    "The request has not succeeded: {}".format(response.json())
                )
            new_flow = response.json()

            new_color_sampling = IS04Utils.make_sampling(new_flow["components"])
            if new_color_sampling is None:
                return test.FAIL("invalid array of video components")

            for item in REF_SUPPORTED_CONSTRAINTS_VIDEO:
                try:
                    if item == "urn:x-nmos:cap:format:media_type":
                        if flow["media_type"] != new_flow["media_type"]:
                            return test.FAIL("different media_type")
                    if item == "urn:x-nmos:cap:format:grain_rate":
                        if flow["grain_rate"] != new_flow["grain_rate"]:
                            return test.FAIL("different grain_rate")
                    if item == "urn:x-nmos:cap:format:frame_width":
                        if flow["frame_width"] != new_flow["frame_width"]:
                            return test.FAIL("different frame_width")
                    if item == "urn:x-nmos:cap:format:frame_height":
                        if flow["frame_height"] != new_flow["frame_height"]:
                            return test.FAIL("different frame_height")
                    if item == "urn:x-nmos:cap:format:interlace_mode":
                        if flow["interlace_mode"] != new_flow["interlace_mode"]:
                            return test.FAIL("different interlace_mode")
                    if item == "urn:x-nmos:cap:format:color_sampling":
                        if color_sampling != new_color_sampling:
                            return test.FAIL("different color_sampling")
                    if item == "urn:x-nmos:cap:format:component_depth":
                        if (
                            flow["components"][0]["bit_depth"]
                            != new_flow["components"][0]["bit_depth"]
                        ):
                            return test.FAIL("different component_depth")
                except Exception:
                    pass
            _, response = TestHelper.do_request(
                "DELETE",
                self.compat_url + "senders/" + sender_id + "constraints/active/",
            )
            if response.status_code != 200:
                return test.FAIL(
                    "The request has not succeeded: {}".format(response.json())
                )
        return test.PASS()

    def test_02_02_06_02(self, test):
        """
        Verify that setting NOP constraints for supported
        constraints doesn't change the flow of a sender(audio).
        """
        if len(self.flow_format_audio) == 0:
            return test.UNCLEAR("There is no audio format.")
        for sender_id in self.flow_format_audio:
            _, response = TestHelper.do_request(
                "GET", self.compat_url + "senders/" + sender_id + "status/"
            )
            if response.status_code != 200:
                test.FAIL("The request has not succeeded: {}".format(response.json()))
            state = response.json()["state"]
            if state in ["awating_essence", "no_essence"]:
                for i in range(0, 5):
                    _, response = TestHelper.do_request(
                        "GET", self.compat_url + "senders/" + sender_id + "status/"
                    )
                    if response.status_code != 200:
                        return test.FAIL(
                            "The request has not succeeded: {}".format(response.json())
                        )
                    state = response.json()["state"]
                    if state in ["awating_essence", "no_essence"]:
                        time.sleep(3)
                    else:
                        break
            if state != "unconstrained":
                return test.FAIL("inputs are unstable.")
            _, response = TestHelper.do_request(
                "GET", self.node_url + "senders/" + sender_id
            )
            if response.status_code != 200:
                return test.FAIL(
                    "The request has not succeeded: {}".format(response.json())
                )
            sender = response.json()

            _, response = TestHelper.do_request(
                "GET", self.node_url + "flows/" + sender["flow_id"]
            )
            if response.status_code != 200:
                return test.FAIL(
                    "The request has not succeeded: {}".format(response.json())
                )
            flow = response.json()
            constraint_set = {}

            _, response = TestHelper.do_request(
                "GET", self.node_url + "sources/" + flow["source_id"]
            )
            if response.status_code != 200:
                return test.FAIL(
                    "The request has not succeeded: {}".format(response.json())
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
            _, response = TestHelper.do_request(
                "PUT",
                self.compat_url + "senders/" + sender_id + "constraints/active/",
                json=self.constraints[sender_id],
            )
            if response.status_code != 200:
                return test.FAIL(
                    "The request has not succeeded: {}".format(response.json())
                )

            _, response = TestHelper.do_request(
                "GET", self.node_url + "flows/" + sender["flow_id"]
            )
            if response.status_code != 200:
                return test.FAIL(
                    "The request has not succeeded: {}".format(response.json())
                )
            new_flow = response.json()

            _, response = TestHelper.do_request(
                "GET", self.node_url + "sources/" + flow["source_id"]
            )
            if response.status_code != 200:
                return test.FAIL(
                    "The request has not succeeded: {}".format(response.json())
                )
            new_source = response.json()

            for item in REF_SUPPORTED_CONSTRAINTS_AUDIO:
                try:
                    if item == "urn:x-nmos:cap:format:media_type":
                        if flow["media_type"] != new_flow["media_type"]:
                            return test.FAIL("different media_type")
                    if item == "urn:x-nmos:cap:format:sample_rate":
                        if flow["sample_rate"] != new_flow["sample_rate"]:
                            return test.FAIL("different sample_rate")
                    if item == "urn:x-nmos:cap:format:channel_count":
                        if len(source["channels"]) != len(new_source["channels"]):
                            return test.FAIL("different channel_count")
                    if item == "urn:x-nmos:cap:format:sample_depth":
                        if flow["bit_depth"] != new_flow["bit_depth"]:
                            return test.FAIL("different sample_depth")
                except Exception:
                    pass
            _, response = TestHelper.do_request(
                "DELETE",
                self.compat_url + "senders/" + sender_id + "constraints/active/",
            )
            if response.status_code != 200:
                return test.FAIL(
                    "The request has not succeeded: {}".format(response.json())
                )
        return test.PASS()

    def test_02_02_07_01(self, test):
        "Verify that the device adhere to the preference of the constraint_set."
        if len(self.flow_format_video) == 0:
            return test.UNCLEAR("There is no video format.")

        for sender_id in self.flow_format_video:
            _, response = TestHelper.do_request(
                "GET", self.compat_url + "senders/" + sender_id + "status/"
            )
            if response.status_code != 200:
                return test.FAIL(
                    "The request has not succeeded: {}".format(response.json())
                )
            state = response.json()["state"]
            if state in ["awating_essence", "no_essence"]:
                for i in range(0, 5):
                    _, response = TestHelper.do_request(
                        "GET", self.compat_url + "senders/" + sender_id + "status/"
                    )
                    if response.status_code != 200:
                        return test.FAIL(
                            "The request has not succeeded: {}".format(response.json())
                        )
                    state = response.json()["state"]

                    if state in ["awating_essence", "no_essence"]:
                        time.sleep(3)
                    else:
                        break
            if state != "unconstrained":
                return test.FAIL("inputs are unstable.")

            _, response = TestHelper.do_request(
                "GET", self.node_url + "senders/" + sender_id
            )
            if response.status_code != 200:
                return test.FAIL(
                    "The request has not succeeded: {}".format(response.json())
                )
            sender = response.json()

            _, response = TestHelper.do_request(
                "GET", self.node_url + "flows/" + sender["flow_id"]
            )
            if response.status_code != 200:
                return test.FAIL(
                    "The request has not succeeded: {}".format(response.json())
                )
            flow = response.json()
            color_sampling = IS04Utils.make_sampling(flow["components"])
            if color_sampling is None:
                return test.FAIL("invalid array of video components")
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
            _, response = TestHelper.do_request(
                "PUT",
                self.compat_url + "senders/" + sender_id + "constraints/active/",
                json=self.constraints[sender_id],
            )
            if response.status_code != 200:
                return test.FAIL(
                    "The request has not succeeded: {}".format(response.json())
                )

            _, response = TestHelper.do_request(
                "GET", self.node_url + "flows/" + sender["flow_id"]
            )
            if response.status_code != 200:
                return test.FAIL(
                    "The request has not succeeded: {}".format(response.json())
                )
            new_flow = response.json()

            new_color_sampling = IS04Utils.make_sampling(new_flow["components"])
            if new_color_sampling is None:
                return test.FAIL("invalid array of video components")

            for item in REF_SUPPORTED_CONSTRAINTS_VIDEO:
                try:
                    if item == "urn:x-nmos:cap:format:media_type":
                        if flow["media_type"] != new_flow["media_type"]:
                            return test.FAIL("different media_type")
                    if item == "urn:x-nmos:cap:format:grain_rate":
                        if flow["grain_rate"] != new_flow["grain_rate"]:
                            return test.FAIL("different grain_rate")
                    if item == "urn:x-nmos:cap:format:frame_width":
                        if flow["frame_width"] != new_flow["frame_width"]:
                            return test.FAIL("different frame_width")
                    if item == "urn:x-nmos:cap:format:frame_height":
                        if flow["frame_height"] != new_flow["frame_height"]:
                            return test.FAIL("different frame_height")
                    if item == "urn:x-nmos:cap:format:interlace_mode":
                        if flow["interlace_mode"] != new_flow["interlace_mode"]:
                            return test.FAIL("different interlace_mode")
                    if item == "urn:x-nmos:cap:format:color_sampling":
                        if color_sampling != new_color_sampling:
                            return test.FAIL("different color_sampling")
                    if item == "urn:x-nmos:cap:format:component_depth":
                        if (
                            flow["components"][0]["bit_depth"]
                            != new_flow["components"][0]["bit_depth"]
                        ):
                            return test.FAIL("different component_depth")
                except Exception:
                    pass

            _, response = TestHelper.do_request(
                "DELETE",
                self.compat_url + "senders/" + sender_id + "constraints/active/",
            )
            if response.status_code != 200:
                return test.FAIL(
                    "The request has not succeeded: {}".format(response.json())
                )
        return test.PASS()

    def test_02_02_07_02(self, test):
        "Verify that the device adhere to the preference of the constraint_set."
        if len(self.flow_format_audio) == 0:
            return test.UNCLEAR("There is no audio format.")

        for sender_id in self.flow_format_audio:
            _, response = TestHelper.do_request(
                "GET", self.compat_url + "senders/" + sender_id + "status/"
            )
            if response.status_code != 200:
                test.FAIL("The request has not succeeded: {}".format(response.json()))
            state = response.json()["state"]
            if state in ["awating_essence", "no_essence"]:
                for i in range(0, 5):
                    _, response = TestHelper.do_request(
                        "GET", self.compat_url + "senders/" + sender_id + "status/"
                    )
                    if response.status_code != 200:
                        return test.FAIL(
                            "The request has not succeeded: {}".format(response.json())
                        )
                    state = response.json()["state"]
                    if state in ["awating_essence", "no_essence"]:
                        time.sleep(3)
                    else:
                        break
            if state != "unconstrained":
                return test.FAIL("inputs are unstable.")

            _, response = TestHelper.do_request(
                "GET", self.node_url + "senders/" + sender_id
            )
            if response.status_code != 200:
                return test.FAIL(
                    "The request has not succeeded: {}".format(response.json())
                )
            sender = response.json()

            _, response = TestHelper.do_request(
                "GET", self.node_url + "flows/" + sender["flow_id"]
            )
            if response.status_code != 200:
                return test.FAIL(
                    "The request has not succeeded: {}".format(response.json())
                )
            flow = response.json()
            _, response = TestHelper.do_request(
                "GET", self.node_url + "sources/" + flow["source_id"]
            )
            if response.status_code != 200:
                return test.FAIL(
                    "The request has not succeeded: {}".format(response.json())
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

            _, response = TestHelper.do_request(
                "PUT",
                self.compat_url + "senders/" + sender_id + "constraints/active/",
                json=self.constraints[sender_id],
            )
            if response.status_code != 200:
                return test.FAIL(
                    "The request has not succeeded: {}".format(response.json())
                )
            _, response = TestHelper.do_request(
                "GET", self.node_url + "flows/" + sender["flow_id"]
            )
            if response.status_code != 200:
                return test.FAIL(
                    "The request has not succeeded: {}".format(response.json())
                )
            new_flow = response.json()

            _, response = TestHelper.do_request(
                "GET", self.node_url + "sources/" + flow["source_id"]
            )
            if response.status_code != 200:
                return test.FAIL(
                    "The request has not succeeded: {}".format(response.json())
                )
            new_source = response.json()

            for item in REF_SUPPORTED_CONSTRAINTS_AUDIO:
                try:
                    if item == "urn:x-nmos:cap:format:media_type":
                        if flow["media_type"] != new_flow["media_type"]:
                            return test.FAIL("different media_type")
                    if item == "urn:x-nmos:cap:format:sample_rate":
                        if flow["sample_rate"] != new_flow["sample_rate"]:
                            return test.FAIL("different sample_rate")
                    if item == "urn:x-nmos:cap:format:channel_count":
                        if len(source["channels"]) != len(new_source["channels"]):
                            return test.FAIL("different channel_count")
                    if item == "urn:x-nmos:cap:format:sample_depth":
                        if flow["bit_depth"] != new_flow["bit_depth"]:
                            return test.FAIL("different sample_depth")
                except Exception:
                    pass
            _, response = TestHelper.do_request(
                "DELETE",
                self.compat_url + "senders/" + sender_id + "constraints/active/",
            )
            if response.status_code != 200:
                return test.FAIL(
                    "The request has not succeeded: {}".format(response.json())
                )
        return test.PASS()

    # OUTPUTS TESTS
    def test_03_01(self, test):
        """
        Verify that the device supports the concept of Output.
        """
        _, response = TestHelper.do_request("GET", self.compat_url + "outputs/")

        if response.status_code == 200:
            if len(response.json()) != 0:
                self.outputs.append(response.json()[0])
            if len(self.outputs) == 0:
                return test.UNCLEAR("No outputs")
            return test.PASS()
        return test.FAIL("The request has not succeeded: {}".format(response.json()))

    def test_03_02(self, test):
        """
        Verify that some of the outputs of the device are connected.
        """
        if len(self.outputs) == 0:
            return test.UNCLEAR("No IS-11 outputs")
        for output in self.outputs:
            _, response = TestHelper.do_request(
                "GET", self.compat_url + "outputs/" + output + "properties/"
            )
            if response.status_code == 200:
                outputs_properties_json = []
                outputs_properties_json.append(response.json())
                for output in outputs_properties_json:
                    if output["connected"]:
                        self.connected_outputs.append(output["id"])
            else:
                return test.FAIL("The request has not succeeded: {}".format(response.json()))
        if len(self.connected_outputs) == 0:
            return test.UNCLEAR("No connected outputs.")
        return test.PASS()

    def test_03_03(self, test):
        """
        Verify that all connected outputs do not have
        a signal as test 0 put all of the receivers inactive.
        """
        if len(self.connected_outputs) == 0:
            return test.UNCLEAR("No connected outputs.")
        for output_id in self.connected_outputs:
            _, response = TestHelper.do_request(
                "GET", self.compat_url + "outputs/" + output_id + "/properties/"
            )
            if response.status_code == 200:
                if response.json()["status"]["state"] == "signal_present":
                    self.active_connected_outputs.append(response.json())
            else:
                return test.FAIL("The request has not succeeded: {}".format(response.json()))
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
            return test.UNCLEAR("No connected outputs.")
        for output_id in self.connected_outputs:
            _, response = TestHelper.do_request(
                "GET", self.compat_url + "outputs/" + output_id + "/properties/"
            )
            if response.status_code == 200:
                if response.json()["edid_support"]:
                    self.edid_connected_outputs.append(response.json()["id"])
            else:
                return test.FAIL("The request has not succeeded: {}".format(response.json()))
        if self.edid_connected_outputs == 0:
            return test.UNCLEAR("Outputs not supporting edid.")
        return test.PASS()

    def test_03_04_01(self, test):
        """
        Verify that an output indicating EDID support behaves according to the RAML file.
        """
        if len(self.edid_connected_outputs) == 0:
            return test.UNCLEAR("No edid connected outputs.")
        for output_id in self.edid_connected_outputs:
            _, response = TestHelper.do_request(
                "GET", self.compat_url + "outputs/" + output_id
            )
            if response.status_code != 200:
                return test.FAIL("The request has not succeeded: {}".format(response.json()))
        return test.PASS()

    def test_03_04_02(self, test):
        """
        Verify that a valid EDID can be retrieved from the device;
        this EDID represents the default EDID of the device.
        """
        is_valid_response = True
        if len(self.edid_connected_outputs) == 0:
            return test.UNCLEAR("No edid connected outputs.")
        for output_id in self.edid_connected_outputs:
            _, response = TestHelper.do_request(
                "GET", self.compat_url + "outputs/" + output_id + "/edid/"
            )
            if (
                response.status_code != 200
                or response.headers["Content-Type"] != "application/octet-stream"
            ):
                is_valid_response = False
            break
        if is_valid_response:
            return test.PASS()
        return test.FAIL("The request has not succeeded: {}".format(response.json()))

    def test_03_05(self, test):
        """
        Verify that connected outputs not supporting EDID behave according to the RAML file.
        """
        if len(self.connected_outputs) == 0:
            return test.UNCLEAR("No connected outputs.")
        for output_id in self.connected_outputs:
            _, response = TestHelper.do_request(
                "GET", self.compat_url + "outputs/" + output_id + "/properties/"
            )
            if response.status_code == 200:
                if not response.json()["edid_support"]:
                    self.not_edid_connected_outputs.append(response.json()["id"])
            else:
                return test.FAIL("The request has not succeeded: {}".format(response.json()))
        if len(self.not_edid_connected_outputs) == 0:
            return test.UNCLEAR("Outputs supporting edid.")
        return test.PASS()

    def test_03_05_01(self, test):
        """
        Verify that there is no EDID support.
        """
        if len(self.not_edid_connected_outputs) == 0:
            return test.UNCLEAR("None of not edid connected outputs.")
        for output_id in self.not_edid_connected_outputs:
            _, response = TestHelper.do_request(
                "GET", self.compat_url + "outputs/" + output_id + "/edid/"
            )
            if response.status_code != 204:
                return test.FAIL("Status code should be 204.")
        return test.PASS()

    # RECEIVERS TESTS
    def test_04_01(self, test):
        """
        Verify that the device supports the concept of IS-11 Receiver.
        """
        _, response = TestHelper.do_request("GET", self.compat_url + "receivers/")

        if response.status_code != 200:
            return test.FAIL("The request has not succeeded: {}".format(response.json()))
        self.receivers = response.json()
        if len(self.receivers) == 0:
            return test.UNCLEAR("No IS-11 receivers.")
        return test.PASS()

    def test_04_01_01(self, test):
        """
        Verify that IS-11 Receivers exist on the Node API as Receivers.
        """
        if len(self.receivers) == 0:
            return test.UNCLEAR("No IS-11 receivers.")
        for receiver_id in self.receivers:
            _, response = TestHelper.do_request(
                "GET", self.node_url + "receivers/" + receiver_id
            )
            if response.status_code != 200:
                return test.FAIL("The request has not succeeded: {}".format(response.json()))
            if response.json()["id"] != receiver_id[:-1]:
                return test.UNCLEAR(
                    "The IS-11 Receiver doesn't exist on the Node API as receiver."
                )
        return test.PASS()

    def test_04_02(self, test):
        """
        Verify receivers (generic with/without outputs)
        """
        _, response = TestHelper.do_request("GET", self.compat_url + "receivers/")
        if response.status_code != 200:
            return test.FAIL("The request has not succeeded: {}".format(response.json()))
        self.receivers = response.json()
        if len(self.receivers) == 0:
            return test.UNCLEAR("No IS-11 receivers.")
        return test.PASS()

    def test_04_02_01(self, test):
        """
        Verify that the status is "unknown" or "non_compliant_stream"
        as per our pre-conditions of not being master_enabled.
        """
        if len(self.receivers) == 0:
            return test.UNCLEAR("No IS-11 receivers.")
        for receiver_id in self.receivers:
            _, response = TestHelper.do_request(
                "GET", self.compat_url + "receivers/" + receiver_id + "status/"
            )
            if response.status_code != 200:
                return test.FAIL("The request has not succeeded: {}".format(response.json()))
            if response.json()["state"] not in ["unknown", "non_compliant_stream"]:
                return test.FAIL("The state is not unknown or non_compliant_stream.")
        return test.PASS()

    def test_04_02_02(self, test):
        """
        Verify that the Receiver supports Receiver Capabilities.
        """
        if len(self.receivers) == 0:
            return test.UNCLEAR("No IS-11 receivers.")
        for receiver_id in self.receivers:
            _, response = TestHelper.do_request(
                "GET", self.node_url + "receivers/" + receiver_id
            )
            if response.status_code != 200:
                return test.FAIL("The request has not succeeded: {}".format(response.json()))
            self.caps = response.json()["caps"]
            if "constraint_sets" not in self.caps:
                return test.UNCLEAR("The receiver does not have constraint_sets in caps.")
            if len(self.caps["constraint_sets"]) == 0:
                return test.WARNING("The receiver does not support BCP-004-01.")
        return test.PASS()
