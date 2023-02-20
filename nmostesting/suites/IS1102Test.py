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

from ..GenericTest import GenericTest
from .. import TestHelper
import time
import re

COMPAT_API_KEY = "streamcompatibility"
NODE_API_KEY = "node"
CONTROLS = "controls"

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


class IS1102Test(GenericTest):
    """
    Runs Node Tests covering IS-11
    """
    def __init__(self, apis):
        # Don't auto-test paths responding with an EDID binary as they don't have a JSON Schema
        omit_paths = [
            "/inputs/{inputId}/edid",
            "/inputs/{inputId}/edid/base",
            "/inputs/{inputId}/edid/effective",
            "/outputs/{outputId}/edid"
        ]
        GenericTest.__init__(self, apis, omit_paths)
        self.node_url = self.apis[NODE_API_KEY]["url"]
        self.compat_url = self.apis[COMPAT_API_KEY]["url"]
        self.base_url = self.apis[COMPAT_API_KEY]["base_url"]
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

    # SENDERS TESTS
    """
    Runs Node Tests covering IS-11 for Senders
    """

    def compare_complex(self, response_constraints, sample_rate_constraints):

        response_constraints_enum = response_constraints["constraint_sets"][0][
            "urn:x-nmos:cap:format:sample_rate"
        ]["enum"]
        sample_rate_constraints_enum = sample_rate_constraints["constraint_sets"][0][
            "urn:x-nmos:cap:format:sample_rate"
        ]["enum"]

        if len(response_constraints_enum) > 0 and len(sample_rate_constraints_enum) > 0:
            if (
                "numerator" in response_constraints_enum[0]
                and "numerator" in sample_rate_constraints_enum[0]
                and "denominator" in response_constraints_enum[0]
                and "denominator" in sample_rate_constraints_enum[0]
            ):
                return (
                    response_constraints_enum[0]["numerator"]
                    == sample_rate_constraints_enum[0]["numerator"]
                    and response_constraints_enum[0]["denominator"]
                    == sample_rate_constraints_enum[0]["denominator"]
                )

            if (
                "numerator" in response_constraints_enum[0]
                and "numerator" in sample_rate_constraints_enum[0]
                and "denominator" in response_constraints_enum[0]
                and "denominator" not in sample_rate_constraints_enum[0]
            ):
                return (
                    response_constraints_enum[0]["numerator"]
                    == sample_rate_constraints_enum[0]["numerator"]
                    and response_constraints_enum[0]["denominator"] == 1
                )

            if (
                "numerator" in response_constraints_enum[0]
                and "numerator" in sample_rate_constraints_enum[0]
                and "denominator" not in response_constraints_enum[0]
                and "denominator" in sample_rate_constraints_enum[0]
            ):
                return (
                    response_constraints_enum[0]["numerator"]
                    == sample_rate_constraints_enum[0]["numerator"]
                    and 1 == sample_rate_constraints_enum[0]["denominator"]
                )
        return False

    def getSdpColorSampling(self, flow_components):
        """
        getColorSamplingFromComponents supports RGB,
        YCbCr-4:4:4, YCbCr-4:2:2, YCbCr-4:2:0 and assumes
        that the bit-depth is compliant without verifying it.
        """
        names = []
        widths = []
        heights = []

        if len(flow_components) != 3:
            return "invalid array of video components"

        for i in range(0, 3):
            if "name" in flow_components[i]:
                names.append(
                    {"name" + str(i): flow_components[i]["name"], "err" + str(i): None}
                )
            else:
                names.append({"name" + str(i): None, "err" + str(i): "not defined"})

        if (
            names[0]["err0"] is None
            and names[0]["name0"] == "R"
            and names[1]["err1"] is None
            and names[1]["name1"] == "G"
            and names[2]["err2"] is None
            and names[2]["name2"] == "B"
        ):
            for i in range(0, 3):
                if "width" in flow_components[i]:
                    widths.append(
                        {
                            "width" + str(i): flow_components[i]["width"],
                            "err" + str(i): None,
                        }
                    )
                else:
                    widths.append(
                        {"width" + str(i): None, "err" + str(i): "not defined"}
                    )

            if (
                widths[0]["err0"] is not None
                or widths[1]["err1"] is not None
                or widths[2]["err2"] is not None
            ):
                return "invalid array of video components"

            for i in range(0, 3):
                if "height" in flow_components[i]:
                    heights.append(
                        {
                            "height" + str(i): flow_components[i]["height"],
                            "err" + str(i): None,
                        }
                    )
                else:
                    heights.append(
                        {"height" + str(i): None, "err" + str(i): "not defined"}
                    )

            if (
                heights[0]["err0"] is not None
                or heights[1]["err1"] is not None
                or heights[2]["err2"] is not None
            ):
                return "invalid array of video components"

            if (
                widths[0]["width0"] == widths[1]["width1"]
                and widths[0]["width0"] == widths[2]["width2"]
                and heights[0]["height0"] == heights[1]["height1"]
                and heights[0]["height0"] == heights[2]["height2"]
            ):
                return "RGB"

        if (
            names[0]["err0"] is None
            and names[0]["name0"] == "Y"
            and names[1]["err1"] is None
            and names[1]["name1"] == "Cb"
            and names[2]["err2"] is None
            and names[2]["name2"] == "Cr"
        ):

            for i in range(0, 3):
                if "width" in flow_components[i]:
                    widths.append(
                        {
                            "width" + str(i): flow_components[i]["width"],
                            "err" + str(i): None,
                        }
                    )
                else:
                    widths.append(
                        {"width" + str(i): None, "err" + str(i): "not defined"}
                    )

            if (
                widths[0]["err0"] is not None
                or widths[1]["err1"] is not None
                or widths[2]["err2"] is not None
            ):
                return "invalid array of video components"

            for i in range(0, 3):
                if "height" in flow_components[i]:
                    heights.append(
                        {
                            "height" + str(i): flow_components[i]["height"],
                            "err" + str(i): None,
                        }
                    )
                else:
                    heights.append(
                        {"height" + str(i): None, "err" + str(i): "not defined"}
                    )

            if (
                heights[0]["err0"] is not None
                or heights[1]["err1"] is not None
                or heights[2]["err2"] is not None
            ):
                return "invalid array of video components"

            if (
                widths[0]["width0"] == widths[1]["width1"]
                and widths[0]["width0"] == widths[2]["width2"]
                and heights[0]["height0"] == heights[1]["height1"]
                and heights[0]["height0"] == heights[2]["height2"]
            ):
                return "YCbCr-4:4:4"

            if (
                widths[0]["width0"] == 2 * widths[1]["width1"]
                and widths[0]["width0"] == 2 * widths[2]["width2"]
                and heights[0]["height0"] == heights[1]["height1"]
                and heights[0]["height0"] == heights[2]["height2"]
            ):
                return "YCbCr-4:2:2"

            if (
                widths[0]["width0"] == 2 * widths[1]["width1"]
                and widths[0]["width0"] == 2 * widths[2]["width2"]
                and heights[0]["height0"] == 2 * heights[1]["height1"]
                and heights[0]["height0"] == 2 * heights[2]["height2"]
            ):
                return "YCbCr-4:2:0"

        return "invalid array of video components"

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
        if numerator == 48000:
            return {"numerator": 44100}
        if numerator == 44100:
            return {"numerator": 48000}
        if numerator == 96000:
            return {"numerator": 4800}
        if numerator == 88200:
            return {"numerator": 44100}
        return "sample_rate not valid"

    def test_02_00(self, test):
        "Reset active constraints of all senders"
        _, response = TestHelper.do_request("GET", self.compat_url + "senders/")
        if response.status_code == 200:
            self.senders = response.json()
            for sender in self.senders:
                _, response = TestHelper.do_request(
                    "DELETE",
                    self.compat_url + "senders/" + sender + "constraints/active/",
                )
                if response.status_code != 200:
                    return test.FAIL("senders constraints cannot be deleted")
            return test.PASS()

        return test.FAIL(response.json())

    def test_02_01(self, test):
        "Verify that the device supports the concept of IS-11 Sender"
        _, response = TestHelper.do_request("GET", self.compat_url + "senders/")
        if response.status_code != 200:
            return test.FAIL(response.json)
        self.senders = response.json()
        if len(self.senders) == 0:
            return test.UNCLEAR("there is no IS-11 senders")
        return test.PASS()

    def test_02_01_01(self, test):
        "Verify that the device supports the concept of IS-11 Sender"
        if len(self.senders) != 0:
            for sender_id in self.senders:
                _, response = TestHelper.do_request(
                    "GET", self.node_url + "senders/" + sender_id
                )
                if response.status_code != 200:
                    return test.FAIL()
                sender_node = response.json()["id"]
                if sender_id[:-1] != sender_node:
                    return test.FAIL("")
            return test.PASS()
        return test.UNCLEAR("there is no IS-11 senders")

    def test_02_02(self, test):
        "Verify senders (generic with/without inputs)"
        _, response = TestHelper.do_request("GET", self.compat_url + "senders/")
        if response.status_code != 200:
            return test.FAIL(response.json())
        self.senders_2 = response.json()
        return test.PASS()

    def test_02_02_01(self, test):
        "Verify that the status is unconstrained as per our pre-conditions"
        if len(self.senders_2) != 0:
            for sender_id in self.senders_2:
                _, response = TestHelper.do_request(
                    "GET", self.compat_url + "senders/" + sender_id + "status/"
                )
                if response.status_code != 200:
                    return test.FAIL(response.json())
                state = response.json()["state"]
                if state in ["awating_essence", "no_essence"]:
                    for i in range(0, 5):
                        _, response = TestHelper.do_request(
                            "GET", self.compat_url + "senders/" + sender_id + "status/"
                        )
                        state = response.json()["status"]["state"]
                        if state in ["awating_essence", "no_essence"]:
                            time.sleep(3000)
                        else:
                            break
                if state != "unconstrained":
                    return test.FAIL("inputs are unstable.")
            return test.PASS()
        return test.UNCLEAR("there is no IS-11 senders")

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
                    return test.FAIL(response.json)
                sender_node = response.json()["id"]
                if sender_id[:-1] != sender_node:
                    return test.FAIL("")
                sender_flow_id = response.json()["flow_id"]
                if sender_flow_id is None:
                    return test.FAIL("the sender must have a flow")
                sender_subscription_active = response.json()["subscription"]["active"]
                if sender_subscription_active:
                    return test.FAIL("the sender must be inactive")
                _, response = TestHelper.do_request(
                    "GET", self.node_url + "flows/" + sender_flow_id
                )
                if response.status_code != 200:
                    return test.FAIL(response.json())
                flow_format = response.json()["format"]
                self.flow_format[sender_id] = flow_format
                if flow_format == "urn:x-nmos:format:video":
                    self.flow_format_video.append(sender_id)
                    flow_frame_width = response.json()["frame_width"]
                    self.flow_width[sender_id] = flow_frame_width
                    flow_frame_height = response.json()["frame_height"]
                    self.flow_height[sender_id] = flow_frame_height
                    flow_grain_rate = response.json()["grain_rate"]
                    self.flow_grain_rate[sender_id] = flow_grain_rate
                if flow_format == "urn:x-nmos:format:audio":
                    self.flow_format_audio.append(sender_id)
                    flow_sample_rate = response.json()["sample_rate"]
                    self.flow_sample_rate[sender_id] = flow_sample_rate
                if (
                    flow_format != "urn:x-nmos:format:video"
                    and flow_format != "urn:x-nmos:format:audio"
                ):
                    print("only audio and video senders are tested at this time.")
            return test.PASS()
        return test.UNCLEAR("there is no IS-11 senders")

    def test_02_02_03_01(self, test):
        "Verify that the video sender supports the minimum set of video constraints"

        pattern = "^urn:x-nmos:cap:"

        if len(self.flow_format_video) == 0:
            return test.UNCLEAR("There is no video format")

        for sender_id in self.flow_format_video:
            _, response = TestHelper.do_request(
                "GET",
                self.compat_url + "senders/" + sender_id + "constraints/supported/ ",
            )
            if response.status_code != 200:
                return test.FAIL(response.json())
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
            return test.UNCLEAR("There is no video format")

        for sender_id in self.flow_format_audio:
            _, response = TestHelper.do_request(
                "GET",
                self.compat_url + "senders/" + sender_id + "constraints/supported/ ",
            )
            if response.status_code != 200:
                return test.FAIL(response.json())
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
            return test.UNCLEAR("There is no video format")

        for sender_id in self.flow_format_video:
            _, response = TestHelper.do_request(
                "GET", self.node_url + "senders/" + sender_id
            )
            if response.status_code != 200:
                return test.FAIL(response.json())
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
                return test.FAIL(response.json())
            _, response = TestHelper.do_request(
                "GET", self.node_url + "senders/" + sender_id
            )
            if response.status_code != 200:
                return test.FAIL(response.json())
            version = response.json()["version"]
            if version == self.version[sender_id]:
                return test.FAIL()
            self.version[sender_id] = version
            _, response = TestHelper.do_request(
                "GET", self.compat_url + "senders/" + sender_id + "constraints/active/ "
            )
            if response.status_code != 200:
                return test.FAIL(response.json())
            constraints = response.json()
            if constraints != self.grain_rate_constraints[sender_id]:
                return test.FAIL()
            _, response = TestHelper.do_request(
                "DELETE",
                self.compat_url + "senders/" + sender_id + "constraints/active/",
            )
            if response.status_code != 200:
                return test.FAIL(response.json())
            _, response = TestHelper.do_request(
                "GET", self.node_url + "senders/" + sender_id
            )
            if response.status_code != 200:
                return test.FAIL(response.json())
            version = response.json()["version"]
            if version == self.version[sender_id]:
                return test.FAIL()
            self.version[sender_id] = version
            _, response = TestHelper.do_request(
                "GET", self.compat_url + "senders/" + sender_id + "constraints/active/"
            )
            if response.status_code != 200:
                return test.FAIL(response.json())
            constraints = response.json()
            if constraints != self.empty_constraints[sender_id]:
                return test.FAIL("Constraints doesn't match")
        return test.PASS()

    def test_02_02_04_02(self, test):
        """
        Verify that changing the constraints of an IS-11
        sender(audio) changes the version of the associated IS-04 sender.
        """
        if len(self.flow_format_audio) == 0:
            return test.UNCLEAR("There is no audio format")
        for sender_id in self.flow_format_audio:
            _, response = TestHelper.do_request(
                "GET", self.node_url + "senders/" + sender_id
            )
            if response.status_code != 200:
                return test.FAIL(response.json())
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
                return test.FAIL(response.json())
            _, response = TestHelper.do_request(
                "GET", self.node_url + "senders/" + sender_id
            )
            if response.status_code != 200:
                return test.FAIL(response.json())
            version = response.json()["version"]
            if version == self.version[sender_id]:
                return test.FAIL()
            self.version[sender_id] = version

            _, response = TestHelper.do_request(
                "GET", self.compat_url + "senders/" + sender_id + "constraints/active/"
            )
            if response.status_code != 200:
                return test.FAIL(response.json())
            constraints = response.json()

            if not self.compare_complex(
                constraints, self.sample_rate_constraints[sender_id]
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
                return test.FAIL(response.json())

            _, response = TestHelper.do_request(
                "GET", self.node_url + "senders/" + sender_id
            )
            if response.status_code != 200:
                return test.FAIL(response.json())
            version = response.json()["version"]
            if version == self.version[sender_id]:
                return test.FAIL()
            self.version[sender_id] = version

            _, response = TestHelper.do_request(
                "GET", self.compat_url + "senders/" + sender_id + "constraints/active/ "
            )
            if response.status_code != 200:
                return test.FAIL(response.json())
            constraints = response.json()
            if constraints != self.empty_constraints[sender_id]:
                return test.FAIL("Constraints doesn't match")
        return test.PASS()

    def test_02_02_05_01(self, test):
        """Verify that setting NOP constraints for frame_width,
        frame_height and grain_rate does not change the flow of
        a sender (video) and that the state goes from \"unconstrained\"
        to \"constrained\"
        """
        if len(self.flow_format_video) == 0:
            return test.UNCLEAR("There is no audio format ")

        for sender_id in self.flow_format_video:
            _, response = TestHelper.do_request(
                "GET", self.compat_url + "senders/" + sender_id + "status/"
            )
            if response.status_code != 200:
                return test.FAIL(response.json())
            state = response.json()["state"]
            if state in ["awating_essence", "no_essence"]:
                for i in range(0, 5):
                    _, response = TestHelper.do_request(
                        "GET", self.compat_url + "senders/" + sender_id + "status/"
                    )
                    state = response.json()["status"]["state"]
                    if state in ["awating_essence", "no_essence"]:
                        time.sleep(3000)
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
                return test.FAIL(response.json())

            _, response = TestHelper.do_request(
                "GET", self.compat_url + "senders/" + sender_id + "status/"
            )
            if response.status_code != 200:
                return test.FAIL(response.json())
            state = response.json()["state"]

            if state in ["awating_essence", "no_essence"]:
                for i in range(0, 5):
                    _, response = TestHelper.do_request(
                        "GET", self.compat_url + "senders/" + sender_id + "status/"
                    )
                    state = response.json()["status"]["state"]
                    if state in ["awating_essence", "no_essence"]:
                        time.sleep(3000)
                    else:
                        break
            if state != "constrained":
                return test.FAIL("inputs are unstable.")

            _, response = TestHelper.do_request(
                "GET", self.node_url + "senders/" + sender_id
            )
            if response.status_code != 200:
                return test.FAIL(response.json)
            sender_flow_id = response.json()["flow_id"]
            if sender_flow_id is None:
                return test.FAIL("the sender must have a flow")

            _, response = TestHelper.do_request(
                "GET", self.node_url + "flows/" + sender_flow_id
            )
            if response.status_code != 200:
                return test.FAIL(response.json())

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
                return test.FAIL(response.json())

        return test.PASS()

    def test_02_02_05_02(self, test):
        """Verify that setting NOP constraints for sample_rate does not change the flow of  a sender (audio) and \
            that the state goes from \"unconstrained\" to \"constrained\""""

        if len(self.flow_format_audio) == 0:
            return test.UNCLEAR("There is no audio format ")

        for sender_id in self.flow_format_audio:
            _, response = TestHelper.do_request(
                "GET", self.compat_url + "senders/" + sender_id + "status/"
            )
            if response.status_code != 200:
                return test.FAIL(response.json())
            state = response.json()["state"]

            if state in ["awating_essence", "no_essence"]:
                for i in range(0, 5):
                    _, response = TestHelper.do_request(
                        "GET", self.compat_url + "senders/" + sender_id + "status/"
                    )
                    state = response.json()["status"]["state"]
                    if state in ["awating_essence", "no_essence"]:
                        time.sleep(3000)
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
                return test.FAIL(response.json())

            _, response = TestHelper.do_request(
                "GET", self.compat_url + "senders/" + sender_id + "status/"
            )
            if response.status_code != 200:
                return test.FAIL(response.json())
            state = response.json()["state"]

            if state in ["awating_essence", "no_essence"]:
                for i in range(0, 5):
                    _, response = TestHelper.do_request(
                        "GET", self.compat_url + "senders/" + sender_id + "status/"
                    )
                    state = response.json()["status"]["state"]
                    if state in ["awating_essence", "no_essence"]:
                        time.sleep(3000)
                    else:
                        break
            if state != "constrained":
                return test.FAIL("inputs are unstable.")

            _, response = TestHelper.do_request(
                "GET", self.node_url + "senders/" + sender_id
            )
            if response.status_code != 200:
                return test.FAIL(response.json)
            sender_flow_id = response.json()["flow_id"]
            if sender_flow_id is None:
                return test.FAIL("the sender must have a flow")

            _, response = TestHelper.do_request(
                "GET", self.node_url + "flows/" + sender_flow_id
            )
            if response.status_code != 200:
                return test.FAIL(response.json())
            flow_sample_rate = response.json()["sample_rate"]
            if self.flow_sample_rate[sender_id] != flow_sample_rate:
                return test.FAIL("Different sample rate")

            _, response = TestHelper.do_request(
                "DELETE",
                self.compat_url + "senders/" + sender_id + "constraints/active/",
            )
            if response.status_code != 200:
                return test.FAIL(response.json())
        return test.PASS()

    def test_02_02_06_01(self, test):
        """Verify that setting NOP constraints for supported constraints does not change the flow of  a sender (video) \
            and that the state goes from \"unconstrained\" to \"constrained\""""
        if len(self.flow_format_video) == 0:
            return test.UNCLEAR("There is no audio format ")

        for sender_id in self.flow_format_video:
            _, response = TestHelper.do_request(
                "GET", self.compat_url + "senders/" + sender_id + "status/"
            )
            if response.status_code != 200:
                return test.FAIL(response.json())
            state = response.json()["state"]
            if state in ["awating_essence", "no_essence"]:
                for i in range(0, 5):
                    _, response = TestHelper.do_request(
                        "GET", self.compat_url + "senders/" + sender_id + "status/"
                    )
                    state = response.json()["status"]["state"]
                    if state in ["awating_essence", "no_essence"]:
                        time.sleep(3000)
                    else:
                        break
            if state != "unconstrained":
                return test.FAIL("inputs are unstable.")

            _, response = TestHelper.do_request(
                "GET", self.node_url + "senders/" + sender_id
            )
            if response.status_code != 200:
                return test.FAIL(response.json)
            sender = response.json()

            _, response = TestHelper.do_request(
                "GET", self.node_url + "flows/" + sender["flow_id"]
            )
            if response.status_code != 200:
                return test.FAIL(response.json())
            flow = response.json()
            color_sampling = self.getSdpColorSampling(flow["components"])
            if color_sampling == "invalid array of video components":
                return test.FAIL("invalid array of video components")
            constraint_set = {}

            for item in REF_SUPPORTED_CONSTRAINTS_VIDEO:

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
            self.constraints[sender_id] = {"constraint_sets": [constraint_set]}

            _, response = TestHelper.do_request(
                "PUT",
                self.compat_url + "senders/" + sender_id + "constraints/active/",
                json=self.constraints[sender_id],
            )
            if response.status_code != 200:
                return test.FAIL(response.json())

            _, response = TestHelper.do_request(
                "GET", self.node_url + "flows/" + sender["flow_id"]
            )
            if response.status_code != 200:
                return test.FAIL(response.json())
            new_flow = response.json()

            new_color_sampling = self.getSdpColorSampling(new_flow["components"])
            if new_color_sampling == "invalid array of video components":
                return test.FAIL("invalid array of video components")

            for item in REF_SUPPORTED_CONSTRAINTS_VIDEO:

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

            _, response = TestHelper.do_request(
                "DELETE",
                self.compat_url + "senders/" + sender_id + "constraints/active/",
            )
            if response.status_code != 200:
                return test.FAIL(response.json())
        return test.PASS()

    def test_02_02_06_02(self, test):
        """Verify that setting NOP constraints for supported
        constraints does not change the flow of  a sender (audio)
        and that the state goes from \"unconstrained\" to \"constrained\"
        """
        if len(self.flow_format_audio) == 0:
            return test.UNCLEAR("There is no audio format")
        for sender_id in self.flow_format_audio:
            _, response = TestHelper.do_request(
                "GET", self.compat_url + "senders/" + sender_id + "status/"
            )
            if response.status_code != 200:
                test.FAIL(response.json())
            state = response.json()["state"]
            if state in ["awating_essence", "no_essence"]:
                for i in range(0, 5):
                    _, response = TestHelper.do_request(
                        "GET", self.compat_url + "senders/" + sender_id + "status/"
                    )
                    state = response.json()["status"]["state"]
                    if state in ["awating_essence", "no_essence"]:
                        time.sleep(3000)
                    else:
                        break
            if state != "unconstrained":
                return test.FAIL("inputs are unstable.")
            _, response = TestHelper.do_request(
                "GET", self.node_url + "senders/" + sender_id
            )
            if response.status_code != 200:
                return test.FAIL(response.json)
            sender = response.json()

            _, response = TestHelper.do_request(
                "GET", self.node_url + "flows/" + sender["flow_id"]
            )
            if response.status_code != 200:
                return test.FAIL(response.json())
            flow = response.json()
            constraint_set = {}

            _, response = TestHelper.do_request(
                "GET", self.node_url + "sources/" + flow["source_id"]
            )
            if response.status_code != 200:
                return test.FAIL(response.json())
            source = response.json()

            for item in REF_SUPPORTED_CONSTRAINTS_AUDIO:

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

            self.constraints[sender_id] = {"constraint_sets": [constraint_set]}
            _, response = TestHelper.do_request(
                "PUT",
                self.compat_url + "senders/" + sender_id + "constraints/active/",
                json=self.constraints[sender_id],
            )
            if response.status_code != 200:
                return test.FAIL(response.json())

            _, response = TestHelper.do_request(
                "GET", self.node_url + "flows/" + sender["flow_id"]
            )
            if response.status_code != 200:
                return test.FAIL(response.json())
            new_flow = response.json()

            _, response = TestHelper.do_request(
                "GET", self.node_url + "sources/" + flow["source_id"]
            )
            if response.status_code != 200:
                return test.FAIL(response.json())
            new_source = response.json()

            for item in REF_SUPPORTED_CONSTRAINTS_AUDIO:

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

            _, response = TestHelper.do_request(
                "DELETE",
                self.compat_url + "senders/" + sender_id + "constraints/active/",
            )
            if response.status_code != 200:
                return test.FAIL(response.json())
        return test.PASS()

    def test_02_02_07_01(self, test):
        "Verify that the device adhere to the preference of the constraint_set."
        if len(self.flow_format_video) == 0:
            return test.UNCLEAR("There is no audio format ")

        for sender_id in self.flow_format_video:
            _, response = TestHelper.do_request(
                "GET", self.compat_url + "senders/" + sender_id + "status/"
            )
            if response.status_code != 200:
                return test.FAIL(response.json())
            state = response.json()["state"]
            if state in ["awating_essence", "no_essence"]:
                for i in range(0, 5):
                    _, response = TestHelper.do_request(
                        "GET", self.compat_url + "senders/" + sender_id + "status/"
                    )
                    state = response.json()["status"]["state"]
                    if state in ["awating_essence", "no_essence"]:
                        time.sleep(3000)
                    else:
                        break
            if state != "unconstrained":
                return test.FAIL("inputs are unstable.")

            _, response = TestHelper.do_request(
                "GET", self.node_url + "senders/" + sender_id
            )
            if response.status_code != 200:
                return test.FAIL(response.json)
            sender = response.json()

            _, response = TestHelper.do_request(
                "GET", self.node_url + "flows/" + sender["flow_id"]
            )
            if response.status_code != 200:
                return test.FAIL(response.json())
            flow = response.json()
            color_sampling = self.getSdpColorSampling(flow["components"])
            if color_sampling == "invalid array of video components":
                return test.FAIL("invalid array of video components")
            constraint_set0 = {}
            constraint_set1 = {}

            for item in REF_SUPPORTED_CONSTRAINTS_VIDEO:

                if item == "urn:x-nmos:cap:meta:label":
                    constraint_set0["urn:x-nmos:cap:meta:label"] = "video constraint"
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

            for item in REF_SUPPORTED_CONSTRAINTS_VIDEO:

                if item == "urn:x-nmos:cap:meta:label":
                    constraint_set1["urn:x-nmos:cap:meta:label"] = "video constraint"
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

            self.constraints[sender_id] = {
                "constraint_sets": [constraint_set0, constraint_set0]
            }
            _, response = TestHelper.do_request(
                "PUT",
                self.compat_url + "senders/" + sender_id + "constraints/active/",
                json=self.constraints[sender_id],
            )
            if response.status_code != 200:
                return test.FAIL(response.json())

            _, response = TestHelper.do_request(
                "GET", self.node_url + "flows/" + sender["flow_id"]
            )
            if response.status_code != 200:
                return test.FAIL(response.json())
            new_flow = response.json()

            new_color_sampling = self.getSdpColorSampling(new_flow["components"])
            if new_color_sampling == "invalid array of video components":
                return test.FAIL("invalid array of video components")

            for item in REF_SUPPORTED_CONSTRAINTS_VIDEO:

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

            _, response = TestHelper.do_request(
                "DELETE",
                self.compat_url + "senders/" + sender_id + "constraints/active/",
            )
            if response.status_code != 200:
                return test.FAIL(response.json())
        return test.PASS()

    def test_02_02_07_02(self, test):
        "Verify that the device adhere to the preference of the constraint_set."
        if len(self.flow_format_audio) == 0:
            return test.UNCLEAR("There is no audio format")

        for sender_id in self.flow_format_audio:
            _, response = TestHelper.do_request(
                "GET", self.compat_url + "senders/" + sender_id + "status/"
            )
            if response.status_code != 200:
                test.FAIL(response.json())
            state = response.json()["state"]
            if state in ["awating_essence", "no_essence"]:
                for i in range(0, 5):
                    _, response = TestHelper.do_request(
                        "GET", self.compat_url + "senders/" + sender_id + "status/"
                    )
                    state = response.json()["status"]["state"]
                    if state in ["awating_essence", "no_essence"]:
                        time.sleep(3000)
                    else:
                        break
            if state != "unconstrained":
                return test.FAIL("inputs are unstable.")

            _, response = TestHelper.do_request(
                "GET", self.node_url + "senders/" + sender_id
            )
            if response.status_code != 200:
                return test.FAIL(response.json)
            sender = response.json()

            _, response = TestHelper.do_request(
                "GET", self.node_url + "flows/" + sender["flow_id"]
            )
            if response.status_code != 200:
                return test.FAIL(response.json())
            flow = response.json()
            _, response = TestHelper.do_request(
                "GET", self.node_url + "sources/" + flow["source_id"]
            )
            if response.status_code != 200:
                return test.FAIL(response.json())
            source = response.json()

            constraint_set0 = {}
            constraint_set1 = {}

            for item in REF_SUPPORTED_CONSTRAINTS_AUDIO:

                if item == "urn:x-nmos:cap:meta:label":
                    constraint_set0["urn:x-nmos:cap:meta:label"] = "video constraint"
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

            for item in REF_SUPPORTED_CONSTRAINTS_AUDIO:

                if item == "urn:x-nmos:cap:meta:label":
                    constraint_set1["urn:x-nmos:cap:meta:label"] = "video constraint"
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

            self.constraints[sender_id] = {
                "constraint_sets": [constraint_set0, constraint_set1]
            }

            _, response = TestHelper.do_request(
                "PUT",
                self.compat_url + "senders/" + sender_id + "constraints/active/",
                json=self.constraints[sender_id],
            )
            if response.status_code != 200:
                return test.FAIL(response.json())
            _, response = TestHelper.do_request(
                "GET", self.node_url + "flows/" + sender["flow_id"]
            )
            if response.status_code != 200:
                return test.FAIL(response.json())
            new_flow = response.json()

            _, response = TestHelper.do_request(
                "GET", self.node_url + "sources/" + flow["source_id"]
            )
            if response.status_code != 200:
                return test.FAIL(response.json())
            new_source = response.json()

            for item in REF_SUPPORTED_CONSTRAINTS_AUDIO:

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

            _, response = TestHelper.do_request(
                "DELETE",
                self.compat_url + "senders/" + sender_id + "constraints/active/",
            )
            if response.status_code != 200:
                return test.FAIL(response.json())
        return test.PASS()
