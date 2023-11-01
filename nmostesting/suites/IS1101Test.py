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

from requests.compat import json
from ..NMOSUtils import NMOSUtils
from ..GenericTest import GenericTest
from .. import TestHelper
from .. import Config as CONFIG
from ..IS04Utils import IS04Utils
from ..IS05Utils import IS05Utils
import requests
import datetime
from ..IS11Utils import IS11Utils, SND_RCV_SUBSET

COMPAT_API_KEY = "streamcompatibility"
CONTROLS = "controls"
NODE_API_KEY = "node"
CONN_API_KEY = "connection"
VALID_EDID = "test_data/IS1101/valid_edid.bin"
INVALID_EDID = "test_data/IS1101/invalid_edid.bin"

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
    "urn:x-nmos:cap:format:component_depth"
]
REF_SUPPORTED_CONSTRAINTS_AUDIO = [
    "urn:x-nmos:cap:meta:label",
    "urn:x-nmos:cap:meta:preference",
    "urn:x-nmos:cap:meta:enabled",
    "urn:x-nmos:cap:format:media_type",
    "urn:x-nmos:cap:format:channel_count",
    "urn:x-nmos:cap:format:sample_rate",
    "urn:x-nmos:cap:format:sample_depth"
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
        self.not_edid_connected_outputs = []
        self.edid_connected_outputs = []
        self.reference_senders = {}
        self.receivers_with_outputs = []
        self.receivers_without_outputs = []
        self.flow = ""
        self.caps = ""
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
        self.some_input = {}
        self.input_senders = []
        self.connected_inputs = []
        self.disconnected_input = []
        self.not_active_connected_inputs = []
        self.not_edid_connected_inputs = []
        self.edid_connected_inputs = []
        self.support_base_edid = {}
        self.default_edid = {}
        self.another_grain_rate_constraints = {}
        self.another_sample_rate_constraints = {}
        self.not_input_senders = []
        self.is04_utils = IS04Utils(self.node_url)
        self.is05_utils = IS05Utils(self.conn_url)
        self.is11_utils = IS11Utils(self.compat_url, self.apis)

        if CONFIG.IS11_REFERENCE_SENDER_NODE_API_URL:
            self.reference_is04_utils = IS04Utils(CONFIG.IS11_REFERENCE_SENDER_NODE_API_URL)

        if CONFIG.IS11_REFERENCE_SENDER_CONNECTION_API_URL:
            self.reference_is05_utils = IS05Utils(CONFIG.IS11_REFERENCE_SENDER_CONNECTION_API_URL)

    def build_constraints_active_url(self, sender_id):
        return self.compat_url + "senders/" + sender_id + "/constraints/active/"

    def build_sender_status_url(self, sender_id):
        return self.compat_url + "senders/" + sender_id + "/status/"

    def build_output_properties_url(self, id):
        return self.compat_url + "outputs/" + id + "/properties/"

    def set_up_tests(self):
        self.senders = self.is11_utils.get_senders()
        self.receivers = self.is11_utils.get_receivers()
        self.receivers_with_outputs = self.is11_utils.get_receivers(SND_RCV_SUBSET.WITH_I_O)
        self.receivers_without_outputs = self.is11_utils.get_receivers(SND_RCV_SUBSET.WITHOUT_I_O)
        self.inputs = self.is11_utils.get_inputs()
        self.outputs = self.is11_utils.get_outputs()

        self.state_no_essence = "no_essence"
        self.state_awaiting_essence = "awaiting_essence"

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

    # INPUTS TESTS
    def test_01_00(self, test):
        """
        Reset the active constraints of all the senders such that the base EDID is the effective EDID
        """

        if len(self.senders) > 0:
            for sender_id in self.senders:
                valid, response = TestHelper.do_request(
                    "DELETE",
                    self.build_constraints_active_url(sender_id),
                )
                if not valid:
                    return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
                if response.status_code != 200:
                    return test.FAIL("The sender {} constraints cannot be deleted".format(sender_id))
            return test.PASS()
        return test.UNCLEAR("There are no IS-11 senders")

    def test_01_01(self, test):
        """
        Verify that the device supports the concept of Input.
        """

        if len(self.inputs) == 0:
            return test.UNCLEAR("No inputs")
        return test.PASS()

    def test_01_02(self, test):
        """
        Verify that some of the inputs of the device are connected
        """
        if len(self.inputs) != 0:
            for input in self.inputs:
                valid, response = TestHelper.do_request(
                    "GET", self.compat_url + "inputs/" + input + "/properties/"
                )
                if not valid:
                    return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
                if response.status_code != 200:
                    return test.FAIL("The input {} properties streamcompatibility request has failed: {}"
                                     .format(input, response))
                try:
                    if response.json()["connected"]:
                        self.connected_inputs.append(response.json())
                except json.JSONDecodeError:
                    return test.FAIL("Non-JSON response returned from Node API")
                except KeyError as e:
                    return test.FAIL("Unable to find expected key: {}".format(e))
            if len(self.connected_inputs) == 0:
                return test.UNCLEAR("inputs are not connected")
            return test.PASS()
        return test.UNCLEAR("No resources found to perform this test")

    def test_01_03(self, test):
        """
        Verify that all connected inputs have a signal
        """
        if len(self.connected_inputs) != 0:
            for connectedInput in self.connected_inputs:
                state = connectedInput["status"]["state"]
                id = connectedInput["id"]
                if state == "no_signal" or state == "awaiting_signal":
                    if state == "awaiting_signal":
                        for i in range(0, CONFIG.STABLE_STATE_ATTEMPTS):
                            valid, response = TestHelper.do_request(
                                "GET", self.compat_url + "inputs/" + id + "/properties/"
                            )
                            if not valid:
                                return test.FAIL("Unexpected response from the streamcompatibility API: {}"
                                                 .format(response))
                            if response.status_code != 200:
                                return test.FAIL("The input {} properties streamcompatibility request has failed: {}"
                                                 .format(id, response))
                            try:
                                state = response.json()["status"]["state"]
                            except json.JSONDecodeError:
                                return test.FAIL("Non-JSON response returned from Node API")
                            except KeyError as e:
                                return test.FAIL("Unable to find expected key: {}".format(e))
                            if state == "awaiting_signal":
                                time.sleep(CONFIG.STABLE_STATE_DELAY)
                            else:
                                break
                        if state == "awaiting_signal":
                            return test.FAIL("Expected state of input {} is \"awaiting_signal\", got \"{}\""
                                             .format(id, state))
                        self.not_active_connected_inputs.append(connectedInput)
            if len(self.not_active_connected_inputs) != 0:
                for input in self.not_active_connected_inputs:
                    self.connected_inputs.remove(input)
            if len(self.connected_inputs) != 0:
                return test.PASS()
            return test.UNCLEAR("No connected input have a signal")
        return test.UNCLEAR("No resources found to perform this test")

    def test_01_04_00(self, test):
        """
        Verify that connected inputs supporting EDID behave according to the RAML file
        """
        if len(self.connected_inputs) != 0:
            for connectedInput in self.connected_inputs:
                id = connectedInput["id"]
                valid, response = TestHelper.do_request(
                    "GET", self.compat_url + "inputs/" + id + "/properties/"
                )
                if not valid:
                    return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
                if response.status_code != 200:
                    return test.FAIL("The input {} properties streamcompatibility request has failed: {}"
                                     .format(id, response))
                try:
                    if response.json()["edid_support"]:
                        self.edid_connected_inputs.append(response.json()["id"])
                except json.JSONDecodeError:
                    return test.FAIL("Non-JSON response returned from Node API")
                except KeyError as e:
                    return test.FAIL("Unable to find expected key: {}".format(e))
            if len(self.edid_connected_inputs) != 0:
                self.test_01_04_pass = True
                return test.PASS()
            return test.UNCLEAR("No resources found to perform this test")
        return test.UNCLEAR("No resources found to perform this test")

    def test_01_04_01(self, test):
        """
        Verify that an input indicating EDID support behaves according to the RAML file.
        """
        if len(self.connected_inputs) != 0 and len(self.edid_connected_inputs) != 0:
            for input_id in self.edid_connected_inputs:
                valid, response = TestHelper.do_request(
                    "GET", self.compat_url + "inputs/" + input_id + "/edid/"
                )
                if not valid:
                    return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
                if response.status_code != 200:
                    return test.FAIL("The input {} edid streamcompatibility request has failed: {}"
                                     .format(input_id, response))
            return test.PASS()
        return test.UNCLEAR("No resources found to perform this test")

    def test_01_04_02(self, test):
        """
        Verify that a valid EDID can be retrieved from the device;
        this EDID represents the default EDID of the device
        """

        if len(self.connected_inputs) != 0 and len(self.edid_connected_inputs) != 0:

            for input_id in self.edid_connected_inputs:
                valid, response = TestHelper.do_request(
                    "GET", self.compat_url + "inputs/" + input_id + "/edid/effective/"
                )
                if not valid:
                    return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
                if (
                    response.status_code != 200
                    and response.headers["Content-Type"] != "application/octet-stream"
                ):
                    return test.FAIL("The input {} edid effective streamcompatibility request has failed: {}"
                                     .format(input_id, response))
                self.default_edid[input_id] = response.content
            return test.PASS()

        return test.UNCLEAR("No resources found to perform this test")

    def test_01_04_03(self, test):
        """
        Verify if the device supports changing the base EDID
        """
        if len(self.connected_inputs) != 0 and len(self.edid_connected_inputs) != 0:
            for input_id in self.edid_connected_inputs:
                valid, response = TestHelper.do_request(
                    "DELETE", self.compat_url + "inputs/" + input_id + "/edid/base/"
                )
                if not valid:
                    return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
                if response.status_code == 405:
                    return test.UNCLEAR(
                        "device does not support changing the base EDID"
                    )
                if response.status_code == 204:
                    self.support_base_edid[input_id] = True
                else:
                    return test.FAIL("The input {} base edid cannot be deleted".format(input_id))

            return test.PASS()
        return test.UNCLEAR("No resources found to perform this test")

    def test_01_04_04(self, test):
        """
        Verify that there is no base EDID after a delete
        """
        if len(self.connected_inputs) != 0 and len(self.edid_connected_inputs) != 0:
            for input_id in self.edid_connected_inputs:
                valid, response = TestHelper.do_request(
                    "GET", self.compat_url + "inputs/" + input_id + "/edid/base/"
                )
                if not valid:
                    return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
                if response.status_code != 204:
                    return test.FAIL("The input {} edid base streamcompatibility request has failed: {}"
                                     .format(input_id, response))
            return test.PASS()
        return test.UNCLEAR("No resources found to perform this test")

    def test_01_04_05(self, test):
        """
        Verify that a valid base EDID can be put
        """
        if len(self.connected_inputs) != 0 and len(self.edid_connected_inputs) != 0:
            for input_id in self.edid_connected_inputs:
                file = open(VALID_EDID, "rb")
                response = requests.put(
                    self.compat_url + "inputs/" + input_id + "/edid/base/",
                    data=file,
                    headers={"Content-Type": "application/octet-stream"},
                )
                file.close()
                if response.status_code != 204:
                    return test.FAIL("The input {} edid base change has failed: {}".format(input_id, response))
            return test.PASS()
        return test.UNCLEAR("No resources found to perform this test")

    def test_01_04_06(self, test):
        """
        Verify that the last PUT base EDID can be retrieved
        """
        if len(self.connected_inputs) != 0 and len(self.edid_connected_inputs) != 0:
            for input_id in self.edid_connected_inputs:
                valid, response = TestHelper.do_request(
                    "GET", self.compat_url + "inputs/" + input_id + "/edid/base/"
                )
                if not valid:
                    return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
                if response.status_code != 200:
                    return test.FAIL("The input {} edid base streamcompatibility request has failed: {}"
                                     .format(input_id, response))
                if response.content != open(VALID_EDID, "rb").read():
                    return test.FAIL("Edid files does'nt match")
            return test.PASS()
        return test.UNCLEAR("No resources found to perform this test")

    def test_01_04_07(self, test):
        """
        Verify that the base EDID without constraints is visible as the effective EDID
        """
        if len(self.connected_inputs) != 0 and len(self.edid_connected_inputs) != 0:
            for input_id in self.edid_connected_inputs:
                time.sleep(CONFIG.STABLE_STATE_DELAY)
                valid, response = TestHelper.do_request(
                    "GET", self.compat_url + "inputs/" + input_id + "/edid/effective/"
                )
                if not valid:
                    return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
                if response.status_code != 200:
                    return test.FAIL("The input {} edid effective streamcompatibility request has failed: {}"
                                     .format(input_id, response))
                if response.content != open(VALID_EDID, "rb").read():
                    return test.FAIL("Edid files does'nt match")
            return test.PASS()
        return test.UNCLEAR("No resources found to perform this test")

    def test_01_04_08(self, test):
        """
        Verify that the base EDID can be deleted
        """
        if len(self.connected_inputs) != 0 and len(self.edid_connected_inputs) != 0:
            for input_id in self.edid_connected_inputs:
                valid, response = TestHelper.do_request(
                    "DELETE", self.compat_url + "inputs/" + input_id + "/edid/base/"
                )
                if not valid:
                    return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
                if response.status_code != 204:
                    return test.FAIL("The input {} base edid cannot be deleted".format(input_id))
            return test.PASS()
        return test.UNCLEAR("No resources found to perform this test")

    def test_01_04_09(self, test):
        """
        Verify that the base EDID is properly deleted
        """
        if len(self.connected_inputs) != 0 and len(self.edid_connected_inputs) != 0:
            for input_id in self.edid_connected_inputs:
                valid, response = TestHelper.do_request(
                    "GET", self.compat_url + "inputs/" + input_id + "/edid/base/"
                )
                if not valid:
                    return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
                if response.status_code != 204:
                    return test.FAIL("The input {} edid base streamcompatibility request has failed: {}"
                                     .format(input_id, response))
            return test.PASS()
        return test.UNCLEAR("No resources found to perform this test")

    def test_01_04_10(self, test):
        """
        Verify that the default EDID becomes visible again after deleting the base EDID
        """
        if len(self.connected_inputs) != 0 and len(self.edid_connected_inputs) != 0:
            for input_id in self.edid_connected_inputs:
                time.sleep(CONFIG.STABLE_STATE_DELAY)
                valid, response = TestHelper.do_request(
                    "GET", self.compat_url + "inputs/" + input_id + "/edid/effective/"
                )
                if not valid:
                    return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
                if response.status_code != 200:
                    return test.FAIL("The input {} edid effective streamcompatibility request has failed: {}"
                                     .format(input_id, response))
                if response.content != self.default_edid[input_id]:
                    return test.FAIL("Edid files does'nt match")
            return test.PASS()
        return test.UNCLEAR("No resources found to perform this test")

    def test_01_04_11(self, test):
        """
        Verify that a put of an invalid EDID fail
        """
        if len(self.connected_inputs) != 0 and len(self.edid_connected_inputs) != 0:
            for input_id in self.edid_connected_inputs:
                file = open(INVALID_EDID, "rb")
                response = requests.put(
                    self.compat_url + "inputs/" + input_id + "/edid/base/",
                    data=file,
                    headers={"Content-Type": "application/octet-stream"},
                )
                file.close()
                if response.status_code != 400:
                    return test.FAIL("The input {} edid base change has failed: {}".format(input_id, response))
            return test.PASS()
        return test.UNCLEAR("No resources found to perform this test")

    def test_01_05_00(self, test):
        """
        Verify that connected inputs not supporting EDID behave according to the RAML file
        """
        if len(self.connected_inputs) != 0:
            for connectedInput in self.connected_inputs:
                id = connectedInput["id"]
                valid, response = TestHelper.do_request(
                    "GET", self.compat_url + "inputs/" + id + "/properties/"
                )
                if not valid:
                    return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
                if response.status_code != 200:
                    return test.FAIL("The input {} properties streamcompatibility request has failed: {}"
                                     .format(id, response.json()))
                try:
                    if not response.json()["edid_support"]:
                        self.not_edid_connected_inputs.append(response.json()["id"])
                except json.JSONDecodeError:
                    return test.FAIL("Non-JSON response returned from Node API")
                except KeyError as e:
                    return test.FAIL("Unable to find expected key: {}".format(e))
            if len(self.not_edid_connected_inputs) != 0:
                return test.PASS()
            return test.UNCLEAR("No connected inputs not supporting EDID ")
        return test.UNCLEAR("No resources found to perform this test")

    def test_01_05_01(self, test):
        """
        Verify that there is no EDID support
        TODO: Remove, duplicates test_01_05_02
        """
        if len(self.connected_inputs) != 0 and len(self.not_edid_connected_inputs) != 0:

            for input_id in self.not_edid_connected_inputs:
                valid, response = TestHelper.do_request(
                    "GET", self.compat_url + "inputs/" + input_id + "/edid/effective/"
                )
                if not valid:
                    return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
                if response.status_code != 204:
                    return test.FAIL("The input {} edid effective streamcompatibility request has failed: {}"
                                     .format(input_id, response))
            return test.PASS()

        return test.UNCLEAR("No resources found to perform this test")

    def test_01_05_02(self, test):
        """
        Verify that there is no effective EDID
        """
        if len(self.connected_inputs) != 0 and len(self.not_edid_connected_inputs) != 0:

            for input_id in self.not_edid_connected_inputs:
                valid, response = TestHelper.do_request(
                    "GET", self.compat_url + "inputs/" + input_id + "/edid/effective/"
                )
                if not valid:
                    return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
                if response.status_code != 204:
                    return test.FAIL("The input {} edid effective streamcompatibility request has failed: {}"
                                     .format(input_id, response))
            return test.PASS()

        return test.UNCLEAR("No resources found to perform this test")

    def test_01_05_03(self, test):
        """
        Verify that there is no base EDID (DELETE failure)
        """
        if len(self.connected_inputs) != 0 and len(self.not_edid_connected_inputs) != 0:

            for input_id in self.not_edid_connected_inputs:
                valid, response = TestHelper.do_request(
                    "DELETE", self.compat_url + "inputs/" + input_id + "/edid/base/"
                )
                if not valid:
                    return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
                if response.status_code != 405:
                    return test.FAIL("The input {} edid base streamcompatibility request has failed: {}"
                                     .format(input_id, response))
            return test.PASS()

        return test.UNCLEAR("No resources found to perform this test")

    def test_01_05_04(self, test):
        """
        Verify that there is no base EDID (PUT failure)
        """
        if len(self.connected_inputs) != 0 and len(self.not_edid_connected_inputs) != 0:
            for input_id in self.not_edid_connected_inputs:
                file = open(VALID_EDID, "rb")
                response = requests.put(
                    self.compat_url + "inputs/" + input_id + "/edid/base/",
                    data=file,
                    headers={"Content-Type": "application/octet-stream"},
                )
                file.close()
                if response.status_code != 405:
                    return test.FAIL("The input {} edid base change has failed: {}".format(input_id, response))
            return test.PASS()
        return test.UNCLEAR("No resources found to perform this test")

    def test_01_05_05(self, test):
        """
        Verify that there is no base EDID (GET failure)
        """
        if len(self.connected_inputs) != 0 and len(self.not_edid_connected_inputs) != 0:

            for input_id in self.not_edid_connected_inputs:
                valid, response = TestHelper.do_request(
                    "GET", self.compat_url + "inputs/" + input_id + "/edid/base/"
                )
                if not valid:
                    return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
                if response.status_code != 204:
                    return test.FAIL("The input {} edid base streamcompatibility request has failed: {}"
                                     .format(input_id, response))
            return test.PASS()

        return test.UNCLEAR("No resources found to perform this test")

    def test_01_06_01(self, test):
        """
        Verify that the input supports changing the base EDID which is optional from the specification.
        """
        if len(self.connected_inputs) != 0 and len(self.edid_connected_inputs) != 0:
            for input_id in self.edid_connected_inputs:
                if (
                    input_id in self.support_base_edid
                    and not self.support_base_edid[input_id]
                ):
                    continue
            return test.PASS()
        return test.UNCLEAR("No resources found to perform this test")

    def test_01_06_02(self, test):
        """
        Verify that the Input resource version changes when putting/deleting base EDID
        """
        if len(self.connected_inputs) != 0 and len(self.edid_connected_inputs) != 0:
            for input_id in self.edid_connected_inputs:
                valid, response = TestHelper.do_request(
                    "GET", self.compat_url + "inputs/" + input_id + "/properties/"
                )
                if not valid:
                    return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
                if response.status_code != 200:
                    return test.FAIL("The input {} properties streamcompatibility request has failed: {}"
                                     .format(input_id, response))
                try:
                    version = response.json()["version"]
                except json.JSONDecodeError:
                    return test.FAIL("Non-JSON response returned from Node API")
                except KeyError as e:
                    return test.FAIL("Unable to find expected key: {}".format(e))
                self.version[input_id] = version

                file = open(VALID_EDID, "rb")
                response = requests.put(
                    self.compat_url + "inputs/" + input_id + "/edid/base/",
                    data=file,
                    headers={"Content-Type": "application/octet-stream"},
                )
                file.close()
                if response.status_code != 204:
                    return test.FAIL("The input {} edid base change has failed: {}".format(input_id, response.json()))
                time.sleep(CONFIG.STABLE_STATE_DELAY)
                valid, response = TestHelper.do_request(
                    "GET", self.compat_url + "inputs/" + input_id + "/properties/"
                )
                if not valid:
                    return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
                if response.status_code != 200:
                    return test.FAIL("The input {} properties streamcompatibility request has failed: {}"
                                     .format(input_id, response))
                try:
                    version = response.json()["version"]
                except json.JSONDecodeError:
                    return test.FAIL("Non-JSON response returned from Node API")
                except KeyError as e:
                    return test.FAIL("Unable to find expected key: {}".format(e))
                if version == self.version[input_id]:
                    return test.FAIL("Version doesn't change")
                self.version[input_id] = version

                valid, response = TestHelper.do_request(
                    "DELETE", self.compat_url + "inputs/" + input_id + "/edid/base/"
                )
                if not valid:
                    return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
                if response.status_code != 204:
                    return test.FAIL("The input {} base edid cannot be deleted".format(input_id))
                time.sleep(CONFIG.STABLE_STATE_DELAY)
                valid, response = TestHelper.do_request(
                    "GET", self.compat_url + "inputs/" + input_id + "/properties/"
                )
                if not valid:
                    return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
                if response.status_code != 200:
                    return test.FAIL("The input {} properties streamcompatibility request has failed: {}"
                                     .format(input_id, response.json()))
                try:
                    version = response.json()["version"]
                except json.JSONDecodeError:
                    return test.FAIL("Non-JSON response returned from Node API")
                except KeyError as e:
                    return test.FAIL("Unable to find expected key: {}".format(e))
                if version == self.version[input_id]:
                    return test.FAIL("Version does'nt change")
            return test.PASS()
        return test.UNCLEAR("No resources found to perform this test")

    def test_01_07_01(self, test):
        """
        Verify that the input supports changing the base EDID
        """
        if len(self.connected_inputs) != 0 and len(self.edid_connected_inputs) != 0:
            for input_id in self.edid_connected_inputs:
                if (
                    input_id in self.support_base_edid
                    and not self.support_base_edid[input_id]
                ):
                    continue
            return test.PASS()
        return test.UNCLEAR("No resources found to perform this test")

    def test_01_07_02(self, test):
        """
        Verify that the input is associated with a device
        """
        if len(self.connected_inputs) != 0 and len(self.edid_connected_inputs) != 0:
            for input_id in self.edid_connected_inputs:
                valid, response = TestHelper.do_request(
                    "GET", self.compat_url + "inputs/" + input_id + "/properties/"
                )
                if not valid:
                    return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
                if response.status_code != 200:
                    return test.FAIL("The input {} properties streamcompatibility request has failed: {}"
                                     .format(input_id, response.json()))
                try:
                    input = response.json()
                    if not input["device_id"]:
                        return test.FAIL("no device_id")
                except json.JSONDecodeError:
                    return test.FAIL("Non-JSON response returned from Node API")
                except KeyError as e:
                    return test.FAIL("Unable to find expected key: {}".format(e))
                self.version[input_id] = input["version"]

                valid, response = TestHelper.do_request(
                    "GET", self.node_url + "devices/" + input["device_id"]
                )
                if not valid:
                    return test.FAIL("Unexpected response from the Node API: {}".format(response))
                if response.status_code != 200:
                    return test.FAIL("The device {} Node API request has failed: {}"
                                     .format(input["device_id"], response.json()))
                try:
                    device = response.json()
                    if device["id"] != input["device_id"]:
                        return test.FAIL("device_id does'nt match.")
                except json.JSONDecodeError:
                    return test.FAIL("Non-JSON response returned from Node API")
                except KeyError as e:
                    return test.FAIL("Unable to find expected key: {}".format(e))

                self.version[device["id"]] = input["version"]

                file = open(VALID_EDID, "rb")
                response = requests.put(
                    self.compat_url + "inputs/" + input_id + "/edid/base/",
                    data=file,
                    headers={"Content-Type": "application/octet-stream"},
                )
                file.close()
                time.sleep(CONFIG.STABLE_STATE_DELAY)
                valid, response = TestHelper.do_request(
                    "GET", self.compat_url + "inputs/" + input_id + "/properties/"
                )
                if not valid:
                    return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
                if response.status_code != 200:
                    return test.FAIL("The input {} properties streamcompatibility request has failed: {}"
                                     .format(input_id, response.json()))
                try:
                    version = response.json()["version"]
                except json.JSONDecodeError:
                    return test.FAIL("Non-JSON response returned from Node API")
                except KeyError as e:
                    return test.FAIL("Unable to find expected key: {}".format(e))
                if version == self.version[input_id]:
                    return test.FAIL("Version should not match.")
                valid, response = TestHelper.do_request(
                    "GET", self.node_url + "devices/" + device["id"]
                )
                if not valid:
                    return test.FAIL("Unexpected response from the Node API: {}".format(response))
                if response.status_code != 200:
                    return test.FAIL("The device {} Node API request has failed: {}"
                                     .format(device["id"], response.json()))
                version = response.json()["version"]
                if version == self.version[device["id"]]:
                    return test.FAIL("Version should not match.")
                valid, response = TestHelper.do_request(
                    "DELETE", self.compat_url + "inputs/" + input_id + "/edid/base/"
                )
                if not valid:
                    return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
                if response.status_code != 204:
                    return test.FAIL("The input {} base edid cannot be deleted".format(input_id))

            return test.PASS()
        return test.UNCLEAR("No resources found to perform this test")

    def test_01_08(self, test):
        """
        Verify that disconnected inputs have a minimum of functionality
        """
        if len(self.edid_connected_inputs) != 0:
            for input_id in self.edid_connected_inputs:
                valid, response = TestHelper.do_request(
                    "GET", self.compat_url + "inputs/" + input_id + "/properties/"
                )
                if not valid:
                    return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
                if response.status_code != 200:
                    return test.FAIL("The input {} properties streamcompatibility request has failed: {}"
                                     .format(input_id, response.json()))
                try:
                    if not response.json()["connected"]:
                        self.disconnected_input.append(response.json())
                except json.JSONDecodeError:
                    return test.FAIL("Non-JSON response returned from Node API")
                except KeyError as e:
                    return test.FAIL("Unable to find expected key: {}".format(e))
            if len(self.disconnected_input) == 0:
                return test.UNCLEAR("All inputs are connected")
            return test.PASS()
        return test.UNCLEAR("No resources found to perform this test")

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

        if len(self.senders) > 0:
            for sender_id in self.senders:
                valid, response = TestHelper.do_request(
                    "DELETE",
                    self.build_constraints_active_url(sender_id),
                )
                if not valid:
                    return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
                if response.status_code != 200:
                    return test.FAIL("The sender {} constraints cannot be deleted".format(sender_id))
            return test.PASS()
        return test.UNCLEAR("There are no IS-11 senders")

    def test_02_01(self, test):
        "Verify that the device supports the concept of IS-11 Sender"
        if len(self.senders) == 0:
            return test.UNCLEAR("There are no IS-11 senders")
        return test.PASS()

    def test_02_01_01(self, test):
        "Verify that IS-11 Senders exist on the Node API as Senders"
        if len(self.senders) > 0:
            for sender_id in self.senders:
                valid, response = TestHelper.do_request("GET", self.node_url + "senders/" + sender_id)
                if not valid:
                    return test.FAIL("Unexpected response from the Node API: {}".format(response))
                if response.status_code != 200:
                    return test.FAIL(
                        "The sender {} is not available in the Node API response: {}".format(sender_id, response.json())
                    )
                sender_node_id = response.json()["id"]
                if sender_id != sender_node_id:
                    return test.FAIL("Senders {} and {} are different".format(sender_id, sender_node_id))
            return test.PASS()
        return test.UNCLEAR("There are no IS-11 senders")

    def test_02_02(self, test):
        "Verify senders (generic with/without inputs)"
        if len(self.senders) == 0:
            return test.UNCLEAR("There are no IS-11 senders")
        return test.PASS()

    def test_02_02_01(self, test):
        """
        Verify that the status is "unconstrained" as per our pre-conditions
        """
        if len(self.senders) > 0:
            for sender_id in self.senders:
                valid, response = TestHelper.do_request(
                    "GET", self.build_sender_status_url(sender_id)
                )
                if not valid:
                    return test.FAIL("Unexpected response from the Stream Compatibility Management API: {}"
                                     .format(response))
                if response.status_code != 200:
                    return test.FAIL(
                        "The streamcompatibility request for sender {} status has failed: {}"
                        .format(sender_id, response.json())
                    )
                try:
                    state = response.json()["state"]
                except json.JSONDecodeError:
                    return test.FAIL("Non-JSON response returned from the Stream Compatibility Management API")
                except KeyError as e:
                    return test.FAIL("Unable to find expected key: {}".format(e))

                if state in ["awaiting_essence", "no_essence"]:
                    for i in range(0, CONFIG.STABLE_STATE_ATTEMPTS):
                        valid, response = TestHelper.do_request(
                            "GET", self.build_sender_status_url(sender_id)
                        )
                        if not valid:
                            return test.FAIL("Unexpected response from the streamcompatibility API: {}"
                                             .format(response))
                        if response.status_code != 200:
                            return test.FAIL(
                                "The streamcompatibility request for sender {} status has failed: {}"
                                .format(sender_id, response.json())
                            )
                        try:
                            state = response.json()["state"]
                        except json.JSONDecodeError:
                            return test.FAIL("Non-JSON response returned from the Stream Compatibility Management API")
                        except KeyError as e:
                            return test.FAIL("Unable to find expected key: {}".format(e))

                        if state in ["awaiting_essence", "no_essence"]:
                            time.sleep(CONFIG.STABLE_STATE_DELAY)
                        else:
                            break
                if state != "unconstrained":
                    return test.FAIL("Expected state of sender {} is \"unconstrained\", got \"{}\""
                                     .format(sender_id, state))
            return test.PASS()
        return test.UNCLEAR("There are no IS-11 senders")

    def test_02_02_03(self, test):
        """
        Verify that the sender is available in the node API,
        has an associated flow and is inactive
        """
        if len(self.senders) > 0:
            for sender_id in self.senders:
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
                if sender_id != sender_node_id:
                    return test.FAIL("Senders {} and {} are different".format(sender_id, sender_node_id))
                sender_flow_id = response.json()["flow_id"]
                if sender_flow_id is None:
                    return test.FAIL("The sender {} must have a flow".format(sender_id))
                sender_subscription_active = response.json()["subscription"]["active"]
                if sender_subscription_active:
                    return test.FAIL(
                        "The sender {} must be inactive ".format(sender_id)
                    )
                self.flow = self.is11_utils.get_flows(self.node_url, sender_flow_id)
                flow_format = self.flow["format"]
                self.flow_format[sender_id] = flow_format
                if flow_format == "urn:x-nmos:format:video":
                    self.flow_format_video.append(sender_id)
                    self.flow_width[sender_id] = self.flow["frame_width"]
                    self.flow_height[sender_id] = self.flow["frame_height"]
                    self.flow_grain_rate[sender_id] = self.flow["grain_rate"]
                if flow_format == "urn:x-nmos:format:audio":
                    self.flow_format_audio.append(sender_id)
                    self.flow_sample_rate[sender_id] = self.flow["sample_rate"]
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
                self.compat_url + "senders/" + sender_id + "/constraints/supported/",
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
        "Verify that the audio sender supports the minimum set of audio constraints"

        sample = "^urn:x-nmos:cap:"

        if len(self.flow_format_audio) == 0:
            return test.UNCLEAR("There is no audio format")

        for sender_id in self.flow_format_audio:
            valid, response = TestHelper.do_request(
                "GET",
                self.compat_url + "senders/" + sender_id + "/constraints/supported/",
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
                self.build_constraints_active_url(sender_id),
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
                "GET", self.build_constraints_active_url(sender_id)
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
                self.build_constraints_active_url(sender_id),
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
                "GET", self.build_constraints_active_url(sender_id)
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
                self.build_constraints_active_url(sender_id),
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
                "GET", self.build_constraints_active_url(sender_id)
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
                self.build_constraints_active_url(sender_id),
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
                "GET", self.build_constraints_active_url(sender_id)
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
                "GET", self.build_sender_status_url(sender_id)
            )
            if not valid:
                return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
            if response.status_code != 200:
                return test.FAIL(
                    "The streamcompatibility request for sender {} status has failed: {}"
                    .format(sender_id, response.json())
                )
            state = response.json()["state"]
            if state in ["awaiting_essence", "no_essence"]:
                for i in range(0, CONFIG.STABLE_STATE_ATTEMPTS):
                    valid, response = TestHelper.do_request(
                        "GET", self.build_sender_status_url(sender_id)
                    )
                    if not valid:
                        return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
                    if response.status_code != 200:
                        return test.FAIL(
                            "The streamcompatibility request for sender {} status has failed: {}"
                            .format(sender_id, response.json())
                        )
                    state = response.json()["state"]
                    if state in ["awaiting_essence", "no_essence"]:
                        time.sleep(CONFIG.STABLE_STATE_DELAY)
                    else:
                        break
            if state != "unconstrained":
                return test.FAIL("Expected state of sender {} is \"unconstrained\", got \"{}\""
                                 .format(sender_id, state))

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
                self.build_constraints_active_url(sender_id),
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
                "GET", self.build_sender_status_url(sender_id)
            )
            if not valid:
                return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
            if response.status_code != 200:
                return test.FAIL(
                    "The streamcompatibility request for sender {} status has failed: {}"
                    .format(sender_id, response.json())
                )
            state = response.json()["state"]

            if state in ["awaiting_essence", "no_essence"]:
                for i in range(0, CONFIG.STABLE_STATE_ATTEMPTS):
                    valid, response = TestHelper.do_request(
                        "GET", self.build_sender_status_url(sender_id)
                    )
                    if not valid:
                        return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
                    if response.status_code != 200:
                        return test.FAIL(
                            "The streamcompatibility request for sender {} status has failed: {}"
                            .format(sender_id, response.json())
                        )
                    state = response.json()["state"]
                    if state in ["awaiting_essence", "no_essence"]:
                        time.sleep(CONFIG.STABLE_STATE_DELAY)
                    else:
                        break
            if state != "constrained":
                return test.FAIL("Expected state of sender {} is \"constrained\", got \"{}\"".format(sender_id, state))

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
            self.flow = self.is11_utils.get_flows(self.node_url, sender_flow_id)

            if (
                self.flow_grain_rate[sender_id] != self.flow["grain_rate"]
                or self.flow_width[sender_id] != self.flow["frame_width"]
                or self.flow_height[sender_id] != self.flow["frame_height"]
            ):
                return test.FAIL(
                    "The constraints on frame_width, frame_height\
                    and grain_rate were not expected to change the flow of sender(video) {}"
                    .format(sender_id)
                )

            valid, response = TestHelper.do_request(
                "DELETE",
                self.build_constraints_active_url(sender_id),
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
                "GET", self.build_sender_status_url(sender_id)
            )
            if not valid:
                return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
            if response.status_code != 200:
                return test.FAIL(
                    "The streamcompatibility request for sender {} status has failed: {}"
                    .format(sender_id, response.json())
                )
            state = response.json()["state"]

            if state in ["awaiting_essence", "no_essence"]:
                for i in range(0, CONFIG.STABLE_STATE_ATTEMPTS):
                    valid, response = TestHelper.do_request(
                        "GET", self.build_sender_status_url(sender_id)
                    )
                    if not valid:
                        return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
                    if response.status_code != 200:
                        return test.FAIL(
                            "The streamcompatibility request for sender {} status has failed: {}"
                            .format(sender_id, response.json())
                        )
                    state = response.json()["state"]
                    if state in ["awaiting_essence", "no_essence"]:
                        time.sleep(CONFIG.STABLE_STATE_DELAY)
                    else:
                        break
            if state != "unconstrained":
                return test.FAIL("Expected state of sender {} is \"unconstrained\", got \"{}\""
                                 .format(sender_id, state))

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
                self.build_constraints_active_url(sender_id),
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
                "GET", self.build_sender_status_url(sender_id)
            )
            if not valid:
                return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
            if response.status_code != 200:
                return test.FAIL(
                    "The streamcompatibility request for sender {} status has failed: {}"
                    .format(sender_id, response.json())
                )
            state = response.json()["state"]

            if state in ["awaiting_essence", "no_essence"]:
                for i in range(0, CONFIG.STABLE_STATE_ATTEMPTS):
                    valid, response = TestHelper.do_request(
                        "GET", self.build_sender_status_url(sender_id)
                    )
                    if not valid:
                        return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
                    if response.status_code != 200:
                        return test.FAIL(
                            "The streamcompatibility request for sender {} status has failed: {}"
                            .format(sender_id, response.json())
                        )
                    state = response.json()["state"]
                    if state in ["awaiting_essence", "no_essence"]:
                        time.sleep(CONFIG.STABLE_STATE_DELAY)
                    else:
                        break
            if state != "constrained":
                return test.FAIL("Expected state of sender {} is \"constrained\", got \"{}\"".format(sender_id, state))

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
            self.flow = self.is11_utils.get_flows(self.node_url, sender_flow_id)
            flow_sample_rate = self.flow["sample_rate"]
            if self.flow_sample_rate[sender_id] != flow_sample_rate:
                return test.FAIL("Different sample rate")

            valid, response = TestHelper.do_request(
                "DELETE",
                self.build_constraints_active_url(sender_id),
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
                "GET", self.build_sender_status_url(sender_id)
            )
            if not valid:
                return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
            if response.status_code != 200:
                return test.FAIL(
                    "The streamcompatibility request for sender {} status has failed: {}"
                    .format(sender_id, response.json())
                )
            state = response.json()["state"]
            if state in ["awaiting_essence", "no_essence"]:
                for i in range(0, CONFIG.STABLE_STATE_ATTEMPTS):
                    valid, response = TestHelper.do_request(
                        "GET", self.build_sender_status_url(sender_id)
                    )
                    if not valid:
                        return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
                    if response.status_code != 200:
                        return test.FAIL(
                            "The streamcompatibility request for sender {} status has failed: {}"
                            .format(sender_id, response.json())
                        )
                    state = response.json()["state"]
                    if state in ["awaiting_essence", "no_essence"]:
                        time.sleep(CONFIG.STABLE_STATE_DELAY)
                    else:
                        break
            if state != "unconstrained":
                return test.FAIL("Expected state of sender {} is \"unconstrained\", got \"{}\""
                                 .format(sender_id, state))

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
            self.flow = self.is11_utils.get_flows(self.node_url, sender["flow_id"])
            color_sampling = IS04Utils.make_sampling(self.flow["components"])
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
                            "enum": [self.flow["media_type"]]
                        }
                    if item == "urn:x-nmos:cap:format:grain_rate":
                        constraint_set["urn:x-nmos:cap:format:grain_rate"] = {
                            "enum": [self.flow["grain_rate"]]
                        }
                    if item == "urn:x-nmos:cap:format:frame_width":
                        constraint_set["urn:x-nmos:cap:format:frame_width"] = {
                            "enum": [self.flow["frame_width"]]
                        }
                    if item == "urn:x-nmos:cap:format:frame_height":
                        constraint_set["urn:x-nmos:cap:format:frame_height"] = {
                            "enum": [self.flow["frame_height"]]
                        }
                    if item == "urn:x-nmos:cap:format:interlace_mode":
                        constraint_set["urn:x-nmos:cap:format:interlace_mode"] = {
                            "enum": [self.flow["interlace_mode"]]
                        }
                    if item == "urn:x-nmos:cap:format:color_sampling":
                        constraint_set["urn:x-nmos:cap:format:color_sampling"] = {
                            "enum": [color_sampling]
                        }
                    if item == "urn:x-nmos:cap:format:component_depth":
                        constraint_set["urn:x-nmos:cap:format:component_depth"] = {
                            "enum": [self.flow["components"][0]["bit_depth"]]
                        }
                except Exception:
                    pass

            self.constraints[sender_id] = {"constraint_sets": [constraint_set]}

            valid, response = TestHelper.do_request(
                "PUT",
                self.build_constraints_active_url(sender_id),
                json=self.constraints[sender_id],
            )
            if not valid:
                return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
            if response.status_code != 200:
                return test.FAIL(
                    "The sender {} constraints change has failed: {}"
                    .format(sender_id, response.json())
                )
            new_flow = self.is11_utils.get_flows(self.node_url, sender["flow_id"])
            new_color_sampling = IS04Utils.make_sampling(new_flow["components"])
            if new_color_sampling is None:
                return test.FAIL("Invalid array of video components")

            for item in REF_SUPPORTED_CONSTRAINTS_VIDEO:
                try:
                    if item == "urn:x-nmos:cap:format:media_type":
                        if self.flow["media_type"] != new_flow["media_type"]:
                            return test.FAIL("Different media_type")
                    if item == "urn:x-nmos:cap:format:grain_rate":
                        if self.flow["grain_rate"] != new_flow["grain_rate"]:
                            return test.FAIL("Different grain_rate")
                    if item == "urn:x-nmos:cap:format:frame_width":
                        if self.flow["frame_width"] != new_flow["frame_width"]:
                            return test.FAIL("Different frame_width")
                    if item == "urn:x-nmos:cap:format:frame_height":
                        if self.flow["frame_height"] != new_flow["frame_height"]:
                            return test.FAIL("Different frame_height")
                    if item == "urn:x-nmos:cap:format:interlace_mode":
                        if self.flow["interlace_mode"] != new_flow["interlace_mode"]:
                            return test.FAIL("Different interlace_mode")
                    if item == "urn:x-nmos:cap:format:color_sampling":
                        if color_sampling != new_color_sampling:
                            return test.FAIL("Different color_sampling")
                    if item == "urn:x-nmos:cap:format:component_depth":
                        if (
                            self.flow["components"][0]["bit_depth"]
                            != new_flow["components"][0]["bit_depth"]
                        ):
                            return test.FAIL("Different component_depth")
                except Exception:
                    pass
            valid, response = TestHelper.do_request(
                "DELETE",
                self.build_constraints_active_url(sender_id),
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
                "GET", self.build_sender_status_url(sender_id)
            )
            if not valid:
                return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
            if response.status_code != 200:
                test.FAIL("The streamcompatibility request for sender {} status has failed: {}"
                          .format(sender_id, response.json()))
            state = response.json()["state"]
            if state in ["awaiting_essence", "no_essence"]:
                for i in range(0, CONFIG.STABLE_STATE_ATTEMPTS):
                    valid, response = TestHelper.do_request(
                        "GET", self.build_sender_status_url(sender_id)
                    )
                    if not valid:
                        return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
                    if response.status_code != 200:
                        return test.FAIL(
                            "The streamcompatibility request for sender {} status has failed: {}"
                            .format(sender_id, response.json())
                        )
                    state = response.json()["state"]
                    if state in ["awaiting_essence", "no_essence"]:
                        time.sleep(CONFIG.STABLE_STATE_DELAY)
                    else:
                        break
            if state != "unconstrained":
                return test.FAIL("Expected state of sender {} is \"unconstrained\", got \"{}\""
                                 .format(sender_id, state))
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
            self.flow = self.is11_utils.get_flows(self.node_url, sender["flow_id"])
            constraint_set = {}

            valid, response = TestHelper.do_request(
                "GET", self.node_url + "sources/" + self.flow["source_id"]
            )
            if not valid:
                return test.FAIL("Unexpected response from the Node API: {}".format(response))
            if response.status_code != 200:
                return test.FAIL(
                    "The source {} is not available in the Node API: {}"
                    .format(self.flow["source_id"], response.json())
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
                            "enum": [self.flow["media_type"]]
                        }
                    if item == "urn:x-nmos:cap:format:sample_rate":
                        constraint_set["urn:x-nmos:cap:format:sample_rate"] = {
                            "enum": [self.flow["sample_rate"]]
                        }
                    if item == "urn:x-nmos:cap:format:channel_count":
                        constraint_set["urn:x-nmos:cap:format:channel_count"] = {
                            "enum": [len(source["channels"])]
                        }
                    if item == "urn:x-nmos:cap:format:sample_depth":
                        constraint_set["urn:x-nmos:cap:format:sample_depth"] = {
                            "enum": [self.flow["bit_depth"]]
                        }
                except Exception:
                    pass
            self.constraints[sender_id] = {"constraint_sets": [constraint_set]}
            valid, response = TestHelper.do_request(
                "PUT",
                self.build_constraints_active_url(sender_id),
                json=self.constraints[sender_id],
            )
            if not valid:
                return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
            if response.status_code != 200:
                return test.FAIL(
                    "The sender {} constraints change has failed: {}"
                    .format(sender_id, response.json())
                )
            new_flow = self.is11_utils.get_flows(self.node_url, sender["flow_id"])

            valid, response = TestHelper.do_request(
                "GET", self.node_url + "sources/" + self.flow["source_id"]
            )
            if not valid:
                return test.FAIL("Unexpected response from the Node API: {}".format(response))
            if response.status_code != 200:
                return test.FAIL(
                    "The source {} is not available in the Node API: {}"
                    .format(self.flow["source_id"], response.json())
                )
            new_source = response.json()

            for item in REF_SUPPORTED_CONSTRAINTS_AUDIO:
                try:
                    if item == "urn:x-nmos:cap:format:media_type":
                        if self.flow["media_type"] != new_flow["media_type"]:
                            return test.FAIL("Different media_type")
                    if item == "urn:x-nmos:cap:format:sample_rate":
                        if self.flow["sample_rate"] != new_flow["sample_rate"]:
                            return test.FAIL("Different sample_rate")
                    if item == "urn:x-nmos:cap:format:channel_count":
                        if len(source["channels"]) != len(new_source["channels"]):
                            return test.FAIL("Different channel_count")
                    if item == "urn:x-nmos:cap:format:sample_depth":
                        if self.flow["bit_depth"] != new_flow["bit_depth"]:
                            return test.FAIL("Different sample_depth")
                except Exception:
                    pass
            valid, response = TestHelper.do_request(
                "DELETE",
                self.build_constraints_active_url(sender_id),
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
                "GET", self.build_sender_status_url(sender_id)
            )
            if not valid:
                return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
            if response.status_code != 200:
                return test.FAIL(
                    "The streamcompatibility request for sender {} status has failed: {}"
                    .format(sender_id, response.json())
                )
            state = response.json()["state"]
            if state in ["awaiting_essence", "no_essence"]:
                for i in range(0, CONFIG.STABLE_STATE_ATTEMPTS):
                    valid, response = TestHelper.do_request(
                        "GET", self.build_sender_status_url(sender_id)
                    )
                    if not valid:
                        return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
                    if response.status_code != 200:
                        return test.FAIL(
                            "The streamcompatibility request for sender {} status has failed: {}"
                            .format(sender_id, response.json())
                        )
                    state = response.json()["state"]

                    if state in ["awaiting_essence", "no_essence"]:
                        time.sleep(CONFIG.STABLE_STATE_DELAY)
                    else:
                        break
            if state != "unconstrained":
                return test.FAIL("Expected state of sender {} is \"unconstrained\", got \"{}\""
                                 .format(sender_id, state))

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
            self.flow = self.is11_utils.get_flows(self.node_url, sender["flow_id"])
            color_sampling = IS04Utils.make_sampling(self.flow["components"])
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
                            "enum": [self.flow["media_type"]]
                        }
                    if item == "urn:x-nmos:cap:format:grain_rate":
                        constraint_set0["urn:x-nmos:cap:format:grain_rate"] = {
                            "enum": [self.flow["grain_rate"]]
                        }
                    if item == "urn:x-nmos:cap:format:frame_width":
                        constraint_set0["urn:x-nmos:cap:format:frame_width"] = {
                            "enum": [self.flow["frame_width"]]
                        }
                    if item == "urn:x-nmos:cap:format:frame_height":
                        constraint_set0["urn:x-nmos:cap:format:frame_height"] = {
                            "enum": [self.flow["frame_height"]]
                        }
                    if item == "urn:x-nmos:cap:format:interlace_mode":
                        constraint_set0["urn:x-nmos:cap:format:interlace_mode"] = {
                            "enum": [self.flow["interlace_mode"]]
                        }
                    if item == "urn:x-nmos:cap:format:color_sampling":
                        constraint_set0["urn:x-nmos:cap:format:color_sampling"] = {
                            "enum": [color_sampling]
                        }
                    if item == "urn:x-nmos:cap:format:component_depth":
                        constraint_set0["urn:x-nmos:cap:format:component_depth"] = {
                            "enum": [self.flow["components"][0]["bit_depth"]]
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
                            "enum": [self.flow["media_type"]]
                        }
                    if item == "urn:x-nmos:cap:format:grain_rate":
                        constraint_set1["urn:x-nmos:cap:format:grain_rate"] = {
                            "enum": [self.get_another_grain_rate(self.flow["grain_rate"])]
                        }
                    if item == "urn:x-nmos:cap:format:frame_width":
                        constraint_set1["urn:x-nmos:cap:format:frame_width"] = {
                            "enum": [self.flow["frame_width"]]
                        }
                    if item == "urn:x-nmos:cap:format:frame_height":
                        constraint_set1["urn:x-nmos:cap:format:frame_height"] = {
                            "enum": [self.flow["frame_height"]]
                        }
                    if item == "urn:x-nmos:cap:format:interlace_mode":
                        constraint_set1["urn:x-nmos:cap:format:interlace_mode"] = {
                            "enum": [self.flow["interlace_mode"]]
                        }
                    if item == "urn:x-nmos:cap:format:color_sampling":
                        constraint_set1["urn:x-nmos:cap:format:color_sampling"] = {
                            "enum": [color_sampling]
                        }
                    if item == "urn:x-nmos:cap:format:component_depth":
                        constraint_set1["urn:x-nmos:cap:format:component_depth"] = {
                            "enum": [self.flow["components"][0]["bit_depth"]]
                        }
                except Exception:
                    pass

            self.constraints[sender_id] = {
                "constraint_sets": [constraint_set0, constraint_set0]
            }
            valid, response = TestHelper.do_request(
                "PUT",
                self.build_constraints_active_url(sender_id),
                json=self.constraints[sender_id],
            )
            if not valid:
                return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
            if response.status_code != 200:
                return test.FAIL(
                    "The sender {} constraints change has failed: {}"
                    .format(sender_id, response.json())
                )

            new_flow = self.is11_utils.get_flows(self.node_url, sender["flow_id"])

            new_color_sampling = IS04Utils.make_sampling(new_flow["components"])
            if new_color_sampling is None:
                return test.FAIL("invalid array of video components")

            for item in REF_SUPPORTED_CONSTRAINTS_VIDEO:
                try:
                    if item == "urn:x-nmos:cap:format:media_type":
                        if self.flow["media_type"] != new_flow["media_type"]:
                            return test.FAIL("Different media_type")
                    if item == "urn:x-nmos:cap:format:grain_rate":
                        if self.flow["grain_rate"] != new_flow["grain_rate"]:
                            return test.FAIL("Different grain_rate")
                    if item == "urn:x-nmos:cap:format:frame_width":
                        if self.flow["frame_width"] != new_flow["frame_width"]:
                            return test.FAIL("Different frame_width")
                    if item == "urn:x-nmos:cap:format:frame_height":
                        if self.flow["frame_height"] != new_flow["frame_height"]:
                            return test.FAIL("Different frame_height")
                    if item == "urn:x-nmos:cap:format:interlace_mode":
                        if self.flow["interlace_mode"] != new_flow["interlace_mode"]:
                            return test.FAIL("Different interlace_mode")
                    if item == "urn:x-nmos:cap:format:color_sampling":
                        if color_sampling != new_color_sampling:
                            return test.FAIL("Different color_sampling")
                    if item == "urn:x-nmos:cap:format:component_depth":
                        if (
                            self.flow["components"][0]["bit_depth"]
                            != new_flow["components"][0]["bit_depth"]
                        ):
                            return test.FAIL("Different component_depth")
                except Exception:
                    pass

            valid, response = TestHelper.do_request(
                "DELETE",
                self.build_constraints_active_url(sender_id),
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
                "GET", self.build_sender_status_url(sender_id)
            )
            if not valid:
                return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
            if response.status_code != 200:
                return test.FAIL("The streamcompatibility request for sender {} status has failed: {}"
                                 .format(sender_id, response.json()))
            state = response.json()["state"]
            if state in ["awaiting_essence", "no_essence"]:
                for i in range(0, CONFIG.STABLE_STATE_ATTEMPTS):
                    valid, response = TestHelper.do_request(
                        "GET", self.build_sender_status_url(sender_id)
                    )
                    if not valid:
                        return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
                    if response.status_code != 200:
                        return test.FAIL(
                            "The streamcompatibility request for sender {} status has failed: {}"
                            .format(sender_id, response.json())
                        )
                    state = response.json()["state"]
                    if state in ["awaiting_essence", "no_essence"]:
                        time.sleep(CONFIG.STABLE_STATE_DELAY)
                    else:
                        break
            if state != "unconstrained":
                return test.FAIL("Expected state of sender {} is \"unconstrained\", got \"{}\""
                                 .format(sender_id, state))

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
            self.flow = self.is11_utils.get_flows(self.node_url, sender["flow_id"])
            valid, response = TestHelper.do_request(
                "GET", self.node_url + "sources/" + self.flow["source_id"]
            )
            if not valid:
                return test.FAIL("Unexpected response from the Node API: {}".format(response))
            if response.status_code != 200:
                return test.FAIL(
                    "The source {} is not available in the Node API: {}"
                    .format(self.flow["source_id"], response.json())
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
                            "enum": [self.flow["media_type"]]
                        }
                    if item == "urn:x-nmos:cap:format:sample_rate":
                        constraint_set0["urn:x-nmos:cap:format:sample_rate"] = {
                            "enum": [self.flow["sample_rate"]]
                        }
                    if item == "urn:x-nmos:cap:format:channel_count":
                        constraint_set0["urn:x-nmos:cap:format:channel_count"] = {
                            "enum": [len(source["channels"])]
                        }
                    if item == "urn:x-nmos:cap:format:sample_depth":
                        constraint_set0["urn:x-nmos:cap:format:sample_depth"] = {
                            "enum": [self.flow["bit_depth"]]
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
                            "enum": [self.flow["media_type"]]
                        }
                    if item == "urn:x-nmos:cap:format:sample_rate":
                        constraint_set1["urn:x-nmos:cap:format:sample_rate"] = {
                            "enum": [self.get_another_sample_rate(self.flow["sample_rate"])]
                        }
                    if item == "urn:x-nmos:cap:format:channel_count":
                        constraint_set1["urn:x-nmos:cap:format:channel_count"] = {
                            "enum": [len(source["channels"])]
                        }
                    if item == "urn:x-nmos:cap:format:sample_depth":
                        constraint_set1["urn:x-nmos:cap:format:sample_depth"] = {
                            "enum": [self.flow["bit_depth"]]
                        }
                except Exception:
                    pass

            self.constraints[sender_id] = {
                "constraint_sets": [constraint_set0, constraint_set1]
            }

            valid, response = TestHelper.do_request(
                "PUT",
                self.build_constraints_active_url(sender_id),
                json=self.constraints[sender_id],
            )
            if not valid:
                return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
            if response.status_code != 200:
                return test.FAIL(
                    "The sender {} constraints change has failed: {}"
                    .format(sender_id, response.json())
                )
            new_flow = self.is11_utils.get_flows(self.node_url, sender["flow_id"])

            valid, response = TestHelper.do_request(
                "GET", self.node_url + "sources/" + self.flow["source_id"]
            )
            if not valid:
                return test.FAIL("Unexpected response from the Node API: {}".format(response))
            if response.status_code != 200:
                return test.FAIL(
                    "The source {} is not available in the Node API: {}"
                    .format(self.flow["source_id"], response.json())
                )
            new_source = response.json()

            for item in REF_SUPPORTED_CONSTRAINTS_AUDIO:
                try:
                    if item == "urn:x-nmos:cap:format:media_type":
                        if self.flow["media_type"] != new_flow["media_type"]:
                            return test.FAIL("Different media_type")
                    if item == "urn:x-nmos:cap:format:sample_rate":
                        if self.flow["sample_rate"] != new_flow["sample_rate"]:
                            return test.FAIL("Different sample_rate")
                    if item == "urn:x-nmos:cap:format:channel_count":
                        if len(source["channels"]) != len(new_source["channels"]):
                            return test.FAIL("Different channel_count")
                    if item == "urn:x-nmos:cap:format:sample_depth":
                        if self.flow["bit_depth"] != new_flow["bit_depth"]:
                            return test.FAIL("Different sample_depth")
                except Exception:
                    pass
            valid, response = TestHelper.do_request(
                "DELETE",
                self.build_constraints_active_url(sender_id),
            )
            if not valid:
                return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
            if response.status_code != 200:
                return test.FAIL(
                    "The sender {} constraints cannot be deleted".format(sender_id)
                )
        return test.PASS()

    def test_02_03_00(self, test):
        """
        Verify senders supporting inputs
        """
        for input in self.senders:
            valid, response = TestHelper.do_request(
                        "GET", self.compat_url + "senders/" + input + "/inputs/"
                    )
            if not valid:
                return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
            if response.status_code != 200:
                return test.FAIL("The sender's inputs {} streamcompatibility request has failed: {}"
                                 .format(input, response))
            try:
                if len(response.json()) != 0:
                    self.input_senders.append(input)
            except json.JSONDecodeError:
                return test.FAIL("Non-JSON response returned from Node API")
            except KeyError as e:
                return test.FAIL("Unable to find expected key: {}".format(e))
        if len(self.input_senders) == 0:
            return test.UNCLEAR("No senders supporting inputs")
        return test.PASS()

    def test_02_03_01(self, test):
        """
        Verify that the input is valid
        """
        if len(self.input_senders) != 0:
            for sender_id in self.input_senders:
                valid, response = TestHelper.do_request(
                    "GET", self.compat_url + "senders/" + sender_id + "/inputs/"
                )
                if not valid:
                    return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
                if response.status_code != 200:
                    return test.FAIL("The sender {} inputs streamcompatibility request has failed: {}"
                                     .format(sender_id, response))
                try:
                    inputs = response.json()
                except json.JSONDecodeError:
                    return test.FAIL("Non-JSON response returned from Node API")
                except KeyError as e:
                    return test.FAIL("Unable to find expected key: {}".format(e))
                if len(inputs) == 0:
                    return test.UNCLEAR("No inputs")
                for input_id in inputs:
                    if input_id not in self.inputs:
                        return test.FAIL("The input does not exist")
                self.some_input[sender_id] = input_id
            return test.PASS()
        return test.UNCLEAR("No resources found to perform this test")

    def test_02_03_02(self, test):
        """
        Verify that the input passed its test suite
        """
        if len(self.input_senders) != 0:
            for sender_id in self.input_senders:
                valid, response = TestHelper.do_request(
                    "GET", self.compat_url + "senders/" + sender_id + "/inputs/"
                )
                if not valid:
                    return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
                if response.status_code != 200:
                    return test.FAIL("The sender {} inputs streamcompatibility request has failed: {}"
                                     .format(sender_id, response))
                try:
                    inputs = response.json()
                except json.JSONDecodeError:
                    return test.FAIL("Non-JSON response returned from Node API")
                except KeyError as e:
                    return test.FAIL("Unable to find expected key: {}".format(e))
                if len(inputs) == 0:
                    return test.UNCLEAR("No inputs")
                for input_id in inputs:
                    if (
                        input_id not in self.edid_connected_inputs
                        and input_id not in self.not_edid_connected_inputs
                    ):
                        print("Input does not exist.")
                        break
                    if input_id in self.edid_connected_inputs and not self.test_01_04_00(
                        test
                    ):
                        return test.FAIL("Input supporting EDID failed test suite")
                    if (
                        input_id in self.not_edid_connected_inputs
                        and not self.test_01_05_00(test)
                    ):
                        return test.FAIL("Input not supporting EDID failed test suite")
            return test.PASS()
        return test.UNCLEAR("No resources found to perform this test")

    def test_02_03_03(self, test):
        """
        Verify that the status is "unconstrained" as per our pre-conditions
        """

        if len(self.input_senders) > 0:
            for sender_id in self.input_senders:
                valid, response = TestHelper.do_request(
                    "GET", self.build_sender_status_url(sender_id)
                )
                if not valid:
                    return test.FAIL("Unexpected response from the Stream Compatibility Management API: {}"
                                     .format(response))
                if response.status_code != 200:
                    return test.FAIL(
                        "The streamcompatibility request for sender {} status has failed: {}"
                        .format(sender_id, response.json())
                    )
                try:
                    state = response.json()["state"]
                except json.JSONDecodeError:
                    return test.FAIL("Non-JSON response returned from the Stream Compatibility Management API")
                except KeyError as e:
                    return test.FAIL("Unable to find expected key: {}".format(e))

                if state in ["awaiting_essence", "no_essence"]:
                    for i in range(0, CONFIG.STABLE_STATE_ATTEMPTS):
                        valid, response = TestHelper.do_request(
                            "GET", self.build_sender_status_url(sender_id)
                        )
                        if not valid:
                            return test.FAIL("Unexpected response from the streamcompatibility API: {}"
                                             .format(response))
                        if response.status_code != 200:
                            return test.FAIL(
                                "The streamcompatibility request for sender {} status has failed: {}"
                                .format(sender_id, response.json())
                            )
                        try:
                            state = response.json()["state"]
                        except json.JSONDecodeError:
                            return test.FAIL("Non-JSON response returned from the Stream Compatibility Management API")
                        except KeyError as e:
                            return test.FAIL("Unable to find expected key: {}".format(e))

                        if state in ["awaiting_essence", "no_essence"]:
                            time.sleep(CONFIG.STABLE_STATE_DELAY)
                        else:
                            break
                if state != "unconstrained":
                    return test.FAIL("Expected state of sender {} is \"unconstrained\", got \"{}\""
                                     .format(sender_id, state))
            return test.PASS()
        return test.UNCLEAR("There are no IS-11 senders with associated Inputs")

    def test_02_03_04(self, test):
        """
        Verify for inputs supporting EDID and supporting changing the base EDID
        """
        if len(self.input_senders) != 0:
            for sender_id in self.input_senders:
                valid, response = TestHelper.do_request(
                    "GET", self.compat_url + "senders/" + sender_id + "/inputs/"
                )
                if not valid:
                    return test.FAIL("Unexpected response from the streamcompatibility API: {}"
                                     .format(response))
                if response.status_code != 200:
                    return test.FAIL("The sender {} inputs streamcompatibility request has failed: {}"
                                     .format(sender_id, response))
                inputs = []
                try:
                    for input_id in response.json():
                        if (
                            input_id in self.edid_connected_inputs
                            and input_id in self.support_base_edid
                        ):
                            inputs.append(input_id)
                        else:
                            print(
                                "Inputs {} are not connected or does'nt support base Edid".format(
                                    input_id
                                )
                            )
                            break
                except json.JSONDecodeError:
                    return test.FAIL("Non-JSON response returned from Node API")
                except KeyError as e:
                    return test.FAIL("Unable to find expected key: {}".format(e))
                if len(inputs) == 0:
                    return test.UNCLEAR("No input supports changing the base EDID")
                for input_id in inputs:
                    valid, response = TestHelper.do_request(
                        "GET", self.compat_url + "inputs/" + input_id + "/properties/"
                    )
                    if not valid:
                        return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
                    if response.status_code != 200:
                        return test.FAIL("The input {} properties streamcompatibility request has failed: {}"
                                         .format(input_id, response))
                    try:
                        version = response.json()["version"]
                    except json.JSONDecodeError:
                        return test.FAIL("Non-JSON response returned from Node API")
                    except KeyError as e:
                        return test.FAIL("Unable to find expected key: {}".format(e))
                    self.version[input_id] = version

                    valid, response = TestHelper.do_request(
                        "GET", self.node_url + "senders/" + sender_id
                    )
                    if not valid:
                        return test.FAIL("Unexpected response from the Node API: {}".format(response))
                    if response.status_code != 200:
                        return test.FAIL("The sender {} is not available in the Node API request: {}"
                                         .format(sender_id, response))
                    try:
                        version = response.json()["version"]
                    except json.JSONDecodeError:
                        return test.FAIL("Non-JSON response returned from Node API")
                    except KeyError as e:
                        return test.FAIL("Unable to find expected key: {}".format(e))
                    self.version[sender_id] = version

                    file = open(VALID_EDID, "rb")
                    response = requests.put(
                        self.compat_url + "inputs/" + input_id + "/edid/base/",
                        data=file,
                        headers={"Content-Type": "application/octet-stream"},
                    )
                    file.close()
                    time.sleep(CONFIG.STABLE_STATE_DELAY)

                    valid, response = TestHelper.do_request(
                        "GET", self.compat_url + "inputs/" + input_id + "/properties/"
                    )
                    if not valid:
                        return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
                    if response.status_code != 200:
                        return test.FAIL("The input {} properties streamcompatibility request has failed: {}"
                                         .format(input_id, response))
                    try:
                        version = response.json()["version"]
                    except json.JSONDecodeError:
                        return test.FAIL("Non-JSON response returned from Node API")
                    except KeyError as e:
                        return test.FAIL("Unable to find expected key: {}".format(e))
                    if version == self.version[input_id]:
                        return test.FAIL("Version should change")

                    valid, response = TestHelper.do_request(
                        "GET", self.node_url + "senders/" + sender_id
                    )
                    if not valid:
                        return test.FAIL("Unexpected response from the Node API: {}".format(response))
                    if response.status_code != 200:
                        return test.FAIL("The sender {} is not available in the Node API request: {}"
                                         .format(sender_id, response))
                    try:
                        version = response.json()["version"]
                    except json.JSONDecodeError:
                        return test.FAIL("Non-JSON response returned from Node API")
                    except KeyError as e:
                        return test.FAIL("Unable to find expected key: {}".format(e))
                    if version == self.version[input_id]:
                        return test.FAIL("Version should change")

                    valid, response = TestHelper.do_request(
                        "DELETE", self.compat_url + "inputs/" + input_id + "/edid/base/"
                    )
                    if not valid:
                        return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
                    if response.status_code != 204:
                        return test.FAIL("The input {} base edid cannot be deleted".format(input_id))
            return test.PASS()
        return test.UNCLEAR("No resources found to perform this test.")

    def test_02_03_05_01(self, test):
        """
        Verify for inputs supporting EDID that the version and the effective EDID change when applying constraints
        """
        if len(self.flow_format_video) == 0:
            return test.UNCLEAR("There is no video format")

        for sender_id in self.flow_format_video:
            valid, response = TestHelper.do_request(
                "GET", self.compat_url + "senders/" + sender_id + "/inputs/"
            )
            if not valid:
                return test.FAIL(
                    "Unexpected response from the streamcompatibility API: {}".format(
                        response
                    )
                )
            if response.status_code != 200:
                return test.FAIL(
                    "The sender {} inputs streamcompatibility request has failed: {}".format(
                        sender_id, response
                    )
                )
            inputs = []
            try:
                for input_id in response.json():
                    if (
                        input_id in self.edid_connected_inputs
                        and input_id in self.support_base_edid
                    ):
                        inputs.append(input_id)
                    else:
                        print(
                            "Inputs {} are not connected or does'nt support base Edid".format(
                                input_id
                            )
                        )
                        break
            except json.JSONDecodeError:
                return test.FAIL("Non-JSON response returned from Node API")
            except KeyError as e:
                return test.FAIL("Unable to find expected key: {}".format(e))

            if len(inputs) == 0:
                return test.UNCLEAR("No input supports changing the base EDID")
            for input_id in inputs:
                valid, response = TestHelper.do_request(
                    "GET", self.compat_url + "inputs/" + input_id + "/properties/"
                )
                if not valid:
                    return test.FAIL(
                        "Unexpected response from the streamcompatibility API: {}".format(
                            response
                        )
                    )
                if response.status_code != 200:
                    return test.FAIL(
                        "The input {} properties streamcompatibility request has failed: {}".format(
                            input_id, response
                        )
                    )
                try:
                    version = response.json()["version"]
                except json.JSONDecodeError:
                    return test.FAIL("Non-JSON response returned from Node API")
                except KeyError as e:
                    return test.FAIL("Unable to find expected key: {}".format(e))

                self.version[input_id] = version

                valid, response = TestHelper.do_request(
                    "GET", self.node_url + "senders/" + sender_id
                )
                if not valid:
                    return test.FAIL(
                        "Unexpected response from the Node API: {}".format(response)
                    )
                if response.status_code != 200:
                    return test.FAIL(
                        "The sender {} is not available in the Node API request: {}".format(
                            sender_id, response.json()
                        )
                    )
                try:
                    version = response.json()["version"]
                except json.JSONDecodeError:
                    return test.FAIL("Non-JSON response returned from Node API")
                except KeyError as e:
                    return test.FAIL("Unable to find expected key: {}".format(e))

                self.version[sender_id] = version

                self.another_grain_rate_constraints[sender_id] = {
                    "constraint_sets": [
                        {
                            "urn:x-nmos:cap:format:grain_rate": {
                                "enum": [
                                    self.get_another_grain_rate(
                                        self.flow_grain_rate[sender_id]
                                    )
                                ]
                            }
                        }
                    ]
                }
                valid, response = TestHelper.do_request(
                    "PUT",
                    self.compat_url + "senders/" + sender_id + "/constraints/active/",
                    json=self.another_grain_rate_constraints[sender_id],
                )
                time.sleep(CONFIG.STABLE_STATE_DELAY)
                if not valid:
                    return test.FAIL(
                        "Unexpected response from the Node API: {}".format(response)
                    )
                if response.status_code != 200:
                    return test.FAIL(
                        "The sender {} is not available in the Node API request: {}".format(
                            sender_id, response
                        )
                    )
                if response.status_code == 422:
                    print("Device does not accept grain_rate constraint")

                valid, response = TestHelper.do_request(
                    "GET",
                    self.compat_url + "inputs/" + input_id + "/edid/effective/",
                )
                if not valid:
                    return test.FAIL(
                        "Unexpected response from the streamcompatibility API: {}".format(
                            response
                        )
                    )
                if response.status_code != 200:
                    return test.FAIL(
                        "The input {} properties streamcompatibility request has failed: {}".format(
                            input_id, response
                        )
                    )
                if response.content == self.default_edid[input_id]:
                    print("Grain rate constraint are not changing effective EDID")

                valid, response = TestHelper.do_request(
                    "GET", self.compat_url + "inputs/" + input_id + "/properties/"
                )
                if not valid:
                    return test.FAIL(
                        "Unexpected response from the streamcompatibility API: {}".format(
                            response
                        )
                    )
                if response.status_code != 200:
                    return test.FAIL(
                        "The input {} properties streamcompatibility request has failed: {}".format(
                            input_id, response
                        )
                    )
                try:
                    version = response.json()["version"]
                except json.JSONDecodeError:
                    return test.FAIL("Non-JSON response returned from Node API")
                except KeyError as e:
                    return test.FAIL("Unable to find expected key: {}".format(e))

                if version == self.version[input_id]:
                    return test.FAIL("Version should change")
                valid, response = TestHelper.do_request(
                    "GET", self.node_url + "senders/" + sender_id
                )
                if not valid:
                    return test.FAIL(
                        "Unexpected response from the Node API: {}".format(response)
                    )
                if response.status_code != 200:
                    return test.FAIL(
                        "The sender {} is not available in the Node API request: {}".format(
                            sender_id, response.json()
                        )
                    )
                try:
                    version = response.json()["version"]
                except json.JSONDecodeError:
                    return test.FAIL("Non-JSON response returned from Node API")
                except KeyError as e:
                    return test.FAIL("Unable to find expected key: {}".format(e))

                if version == self.version[input_id]:
                    return test.FAIL("Version should change")

                stable_count = 0
                time_start = datetime.datetime.now()
                while stable_count < 5:
                    if datetime.datetime.now() > time_start + datetime.timedelta(
                        seconds=15
                    ):
                        time.sleep(CONFIG.HTTP_TIMEOUT)
                    valid, response = TestHelper.do_request(
                        "GET", self.node_url + "senders/" + sender_id
                    )
                    if not valid:
                        return test.FAIL(
                            "Unexpected response from the Node API: {}".format(response)
                        )
                    if response.status_code != 200:
                        return test.FAIL(
                            "The sender {} is not available in the Node API request: {}".format(
                                sender_id, response.json()
                            )
                        )
                    try:
                        version = response.json()["version"]
                    except json.JSONDecodeError:
                        return test.FAIL("Non-JSON response returned from Node API")
                    except KeyError as e:
                        return test.FAIL("Unable to find expected key: {}".format(e))
                    if version != self.version[sender_id]:
                        stable_count = 0
                        self.version[sender_id] = version
                    else:
                        stable_count += 1

                valid, response = TestHelper.do_request(
                    "GET",
                    self.compat_url + "senders/" + sender_id + "/status/",
                    time.sleep(20),
                )

                if not valid:
                    return test.FAIL(
                        "Unexpected response from the Node API: {}".format(response)
                    )
                if response.status_code != 200:
                    return test.FAIL(
                        "The sender {} is not available in the Node API request: {}".format(
                            sender_id, response
                        )
                    )

                try:
                    state = response.json()["state"]
                except json.JSONDecodeError:
                    return test.FAIL("Non-JSON response returned from Node API")
                except KeyError as e:
                    return test.FAIL("Unable to find expected key: {}".format(e))

                if state == "active_constraints_violation":
                    return test.UNCLEAR("This device can not constraint grain_rate")

                if state in ["awaiting_essence", "no_essence"]:
                    for i in range(0, CONFIG.STABLE_STATE_ATTEMPTS):
                        valid, response = TestHelper.do_request(
                            "GET", self.build_sender_status_url(sender_id)
                        )
                        if not valid:
                            return test.FAIL("Unexpected response from the streamcompatibility API: {}"
                                             .format(response))
                        if response.status_code != 200:
                            return test.FAIL(
                                "The streamcompatibility request for sender {} status has failed: {}"
                                .format(sender_id, response.json())
                            )
                        try:
                            state = response.json()["state"]
                        except json.JSONDecodeError:
                            return test.FAIL("Non-JSON response returned from the Stream Compatibility Management API")
                        except KeyError as e:
                            return test.FAIL("Unable to find expected key: {}".format(e))

                        if state in ["awaiting_essence", "no_essence"]:
                            time.sleep(CONFIG.STABLE_STATE_DELAY)
                        else:
                            break
                if state != "constrained":
                    return test.FAIL("Expected state of sender {} is \"constrained\", got \"{}\""
                                     .format(sender_id, state))

                valid, response = TestHelper.do_request(
                    "GET", self.node_url + "senders/" + sender_id
                )
                if not valid:
                    return test.FAIL(
                        "Unexpected response from the streamcompatibility API: {}".format(
                            response
                        )
                    )
                if response.status_code != 200:
                    return test.FAIL(
                        "The streamcompatibility request for sender {} status has failed: {}".format(
                            sender_id, response
                        )
                    )

                try:
                    flow_id = response.json()["flow_id"]
                except json.JSONDecodeError:
                    return test.FAIL("Non-JSON response returned from Node API")
                except KeyError as e:
                    return test.FAIL("Unable to find expected key: {}".format(e))

                if flow_id is None:
                    return test.FAIL("flow_id is null")
                valid, response = TestHelper.do_request(
                    "GET", self.node_url + "flows/" + flow_id
                )
                if not valid:
                    return test.FAIL(
                        "Unexpected response from the streamcompatibility API: {}".format(
                            response
                        )
                    )
                if response.status_code != 200:
                    return test.FAIL(
                        "The streamcompatibility request for sender {} status has failed: {}".format(
                            sender_id, response
                        )
                    )
                try:
                    grain_rate = response.json()["grain_rate"]
                except json.JSONDecodeError:
                    return test.FAIL("Non-JSON response returned from Node API")
                except KeyError as e:
                    return test.FAIL("Unable to find expected key: {}".format(e))

                if grain_rate != self.get_another_grain_rate(
                    self.flow_grain_rate[sender_id]
                ):
                    return test.FAIL(
                        "The flow_grain_rate does not match the constraint"
                    )
                valid, response = TestHelper.do_request(
                    "DELETE",
                    self.compat_url + "senders/" + sender_id + "/constraints/active/",
                )
                if not valid:
                    return test.FAIL(
                        "Unexpected response from the streamcompatibility API: {}".format(
                            response
                        )
                    )
                if response.status_code != 200:
                    return test.FAIL(
                        "The streamcompatibility request for sender {} status has failed: {}".format(
                            sender_id, response
                        )
                    )
            return test.PASS()
        return test.UNCLEAR("No resources found to perform this test.")

    def test_02_03_05_02(self, test):
        """
        Verify for inputs supporting EDID that the version and the effective EDID change when applying constraints
        """
        if len(self.flow_format_audio) == 0:
            return test.UNCLEAR("There is no audio format")

        for sender_id in self.flow_format_audio:
            valid, response = TestHelper.do_request(
                "GET", self.compat_url + "senders/" + sender_id + "/inputs/"
            )
            if not valid:
                return test.FAIL(
                    "Unexpected response from the streamcompatibility API: {}".format(
                        response
                    )
                )
            if response.status_code != 200:
                return test.FAIL(
                    "The sender {} inputs streamcompatibility request has failed: {}".format(
                        sender_id, response
                    )
                )
            inputs = []
            try:
                for input_id in response.json():
                    if (
                        input_id in self.edid_connected_inputs
                        and input_id in self.support_base_edid
                    ):
                        inputs.append(input_id)
                    else:
                        print(
                            "Inputs {} are not connected or does'nt support base Edid".format(
                                input_id
                            )
                        )
                        break
            except json.JSONDecodeError:
                return test.FAIL("Non-JSON response returned from Node API")
            except KeyError as e:
                return test.FAIL("Unable to find expected key: {}".format(e))

            if len(inputs) == 0:
                return test.UNCLEAR("No input supports changing the base EDID")
            for input_id in inputs:
                valid, response = TestHelper.do_request(
                    "GET", self.compat_url + "inputs/" + input_id + "/properties/"
                )
                if not valid:
                    return test.FAIL(
                        "Unexpected response from the streamcompatibility API: {}".format(
                            response
                        )
                    )
                if response.status_code != 200:
                    return test.FAIL(
                        "The input {} properties streamcompatibility request has failed: {}".format(
                            input_id, response
                        )
                    )
                try:
                    version = response.json()["version"]
                except json.JSONDecodeError:
                    return test.FAIL("Non-JSON response returned from Node API")
                except KeyError as e:
                    return test.FAIL("Unable to find expected key: {}".format(e))
                self.version[input_id] = version

                valid, response = TestHelper.do_request(
                    "GET", self.node_url + "senders/" + sender_id
                )
                if not valid:
                    return test.FAIL(
                        "Unexpected response from the Node API: {}".format(response)
                    )
                if response.status_code != 200:
                    return test.FAIL(
                        "The sender {} is not available in the Node API request: {}".format(
                            sender_id, response
                        )
                    )
                try:
                    version = response.json()["version"]
                except json.JSONDecodeError:
                    return test.FAIL("Non-JSON response returned from Node API")
                except KeyError as e:
                    return test.FAIL("Unable to find expected key: {}".format(e))
                self.version[sender_id] = version

                self.another_sample_rate_constraints[sender_id] = {
                    "constraint_sets": [
                        {
                            "urn:x-nmos:cap:format:sample_rate": {
                                "enum": [
                                    self.get_another_sample_rate(
                                        self.flow_sample_rate[sender_id]
                                    )
                                ]
                            }
                        }
                    ]
                }
                valid, response = TestHelper.do_request(
                    "PUT",
                    self.compat_url + "senders/" + sender_id + "/constraints/active/",
                    json=self.another_sample_rate_constraints[sender_id],
                )
                time.sleep(CONFIG.STABLE_STATE_DELAY)
                if not valid:
                    return test.FAIL(
                        "Unexpected response from the Node API: {}".format(response)
                    )
                if response.status_code != 200:
                    return test.FAIL(
                        "The sender {} is not available in the Node API request: {}".format(
                            sender_id, response
                        )
                    )
                if response.status_code == 422:
                    print("Device does not accept grain_rate constraint")

                valid, response = TestHelper.do_request(
                    "GET",
                    self.compat_url + "inputs/" + input_id + "/edid/effective/",
                )
                if not valid:
                    return test.FAIL(
                        "Unexpected response from the streamcompatibility API: {}".format(
                            response
                        )
                    )
                if response.status_code != 200:
                    return test.FAIL(
                        "The input {} properties streamcompatibility request has failed: {}".format(
                            input_id, response
                        )
                    )
                if response.content == self.default_edid[input_id]:
                    print("Grain rate constraint are not changing effective EDID")

                valid, response = TestHelper.do_request(
                    "GET", self.compat_url + "inputs/" + input_id + "/properties/"
                )
                if not valid:
                    return test.FAIL(
                        "Unexpected response from the streamcompatibility API: {}".format(
                            response
                        )
                    )
                if response.status_code != 200:
                    return test.FAIL(
                        "The input {} properties streamcompatibility request has failed: {}".format(
                            input_id, response
                        )
                    )
                try:
                    version = response.json()["version"]
                except json.JSONDecodeError:
                    return test.FAIL("Non-JSON response returned from Node API")
                except KeyError as e:
                    return test.FAIL("Unable to find expected key: {}".format(e))

                if version == self.version[input_id]:
                    return test.FAIL("Version should change")
                valid, response = TestHelper.do_request(
                    "GET", self.node_url + "senders/" + sender_id
                )
                if not valid:
                    return test.FAIL(
                        "Unexpected response from the Node API: {}".format(response)
                    )
                if response.status_code != 200:
                    return test.FAIL(
                        "The sender {} is not available in the Node API request: {}".format(
                            sender_id, response
                        )
                    )
                try:
                    version = response.json()["version"]
                except json.JSONDecodeError:
                    return test.FAIL("Non-JSON response returned from Node API")
                except KeyError as e:
                    return test.FAIL("Unable to find expected key: {}".format(e))
                if version == self.version[input_id]:
                    return test.FAIL("Version should change")

                stable_count = 0
                time_start = datetime.datetime.now()
                while stable_count < 5:
                    if datetime.datetime.now() > time_start + datetime.timedelta(
                        seconds=15
                    ):
                        time.sleep(CONFIG.HTTP_TIMEOUT)
                    valid, response = TestHelper.do_request(
                        "GET", self.node_url + "senders/" + sender_id
                    )
                    if not valid:
                        return test.FAIL(
                            "Unexpected response from the Node API: {}".format(response)
                        )
                    if response.status_code != 200:
                        return test.FAIL(
                            "The sender {} is not available in the Node API request: {}".format(
                                sender_id, response.json()
                            )
                        )
                    try:
                        version = response.json()["version"]
                    except json.JSONDecodeError:
                        return test.FAIL("Non-JSON response returned from Node API")
                    except KeyError as e:
                        return test.FAIL("Unable to find expected key: {}".format(e))
                    if version != self.version[sender_id]:
                        stable_count = 0
                        self.version[sender_id] = version
                    else:
                        stable_count += 1

                valid, response = TestHelper.do_request(
                    "GET",
                    self.compat_url + "senders/" + sender_id + "/status/", time.sleep(20)
                )
                if not valid:
                    return test.FAIL(
                        "Unexpected response from the Node API: {}".format(response)
                    )
                if response.status_code != 200:
                    return test.FAIL(
                        "The sender {} is not available in the Node API request: {}".format(
                            sender_id, response
                        )
                    )

                time.sleep(CONFIG.STABLE_STATE_DELAY)
                try:
                    state = response.json()["state"]
                except json.JSONDecodeError:
                    return test.FAIL("Non-JSON response returned from Node API")
                except KeyError as e:
                    return test.FAIL("Unable to find expected key: {}".format(e))

                if state == "active_constraints_violation":
                    return test.UNCLEAR("This device can not constraint grain_rate")

                if state in ["awaiting_essence", "no_essence"]:
                    for i in range(0, CONFIG.STABLE_STATE_ATTEMPTS):
                        valid, response = TestHelper.do_request(
                            "GET", self.build_sender_status_url(sender_id)
                        )
                        if not valid:
                            return test.FAIL("Unexpected response from the streamcompatibility API: {}"
                                             .format(response))
                        if response.status_code != 200:
                            return test.FAIL(
                                "The streamcompatibility request for sender {} status has failed: {}"
                                .format(sender_id, response.json())
                            )
                        try:
                            state = response.json()["state"]
                        except json.JSONDecodeError:
                            return test.FAIL("Non-JSON response returned from the Stream Compatibility Management API")
                        except KeyError as e:
                            return test.FAIL("Unable to find expected key: {}".format(e))

                        if state in ["awaiting_essence", "no_essence"]:
                            time.sleep(CONFIG.STABLE_STATE_DELAY)
                        else:
                            break
                if state != "constrained":
                    return test.FAIL("Expected state of sender {} is \"constrained\", got \"{}\""
                                     .format(sender_id, state))

                valid, response = TestHelper.do_request(
                    "GET", self.node_url + "senders/" + sender_id
                )
                if not valid:
                    return test.FAIL(
                        "Unexpected response from the streamcompatibility API: {}".format(
                            response
                        )
                    )
                if response.status_code != 200:
                    return test.FAIL(
                        "The streamcompatibility request for sender {} status has failed: {}".format(
                            sender_id, response.json()
                        )
                    )
                try:
                    flow_id = response.json()["flow_id"]
                except json.JSONDecodeError:
                    return test.FAIL("Non-JSON response returned from Node API")
                except KeyError as e:
                    return test.FAIL("Unable to find expected key: {}".format(e))
                if flow_id is None:
                    return test.FAIL("flow_id is null")
                valid, response = TestHelper.do_request(
                    "GET", self.node_url + "flows/" + flow_id
                )
                if not valid:
                    return test.FAIL(
                        "Unexpected response from the streamcompatibility API: {}".format(
                            response
                        )
                    )
                if response.status_code != 200:
                    return test.FAIL(
                        "The streamcompatibility request for sender {} status has failed: {}".format(
                            sender_id, response
                        )
                    )
                try:
                    sample_rate = response.json()["sample_rate"]
                except json.JSONDecodeError:
                    return test.FAIL("Non-JSON response returned from Node API")
                except KeyError as e:
                    return test.FAIL("Unable to find expected key: {}".format(e))
                if sample_rate != self.get_another_sample_rate(
                    self.flow_sample_rate[sender_id]
                ):
                    return test.FAIL(
                        "The flow_grain_rate does not match the constraint"
                    )
                valid, response = TestHelper.do_request(
                    "DELETE",
                    self.compat_url + "senders/" + sender_id + "/constraints/active/",
                )
                if not valid:
                    return test.FAIL(
                        "Unexpected response from the streamcompatibility API: {}".format(
                            response
                        )
                    )
                if response.status_code != 200:
                    return test.FAIL(
                        "The streamcompatibility request for sender {} status has failed: {}".format(
                            sender_id, response
                        )
                    )
            return test.PASS()
        return test.UNCLEAR("No resources found to perform this test.")

    def test_02_04(self, test):
        """
        Verify senders not supporting inputs
        """
        for input in self.senders:
            valid, response = TestHelper.do_request(
                "GET", self.compat_url + "senders/" + input + "/inputs/"
                )
            if not valid:
                return test.FAIL(
                     "Unexpected response from the streamcompatibility API: {}".format(
                         response
                        )
                    )
            if response.status_code != 200:
                return test.FAIL(
                    "The sender's inputs {} streamcompatibility request has failed: {}".format(
                         input, response
                        )
                    )
            try:
                if len(response.json()) == 0:
                    self.not_input_senders.append(input)
            except json.JSONDecodeError:
                return test.FAIL("Non-JSON response returned from Node API")
            except KeyError as e:
                return test.FAIL("Unable to find expected key: {}".format(e))

        if len(self.not_input_senders) == 0:
            return test.UNCLEAR("All senders support inputs")
        return test.PASS()

    def test_02_04_01(self, test):
        """
        Verify that the status is "unconstrained" as per our pre-conditions
        """
        if len(self.not_input_senders) == 0:
            return test.UNCLEAR("All senders support inputs")
        for sender_id in self.not_input_senders:
            valid, response = TestHelper.do_request(
                "GET",
                self.compat_url + "senders/" + sender_id + "/status/",
            )
            if not valid:
                return test.FAIL(
                    "Unexpected response from the Node API: {}".format(response)
                )
            if response.status_code != 200:
                return test.FAIL(
                    "The sender {} is not available in the Node API request: {}".format(
                        sender_id, response
                    )
                )

            time.sleep(CONFIG.STABLE_STATE_DELAY)
            try:
                state = response.json()["state"]
            except json.JSONDecodeError:
                return test.FAIL("Non-JSON response returned from Node API")
            except KeyError as e:
                return test.FAIL("Unable to find expected key: {}".format(e))
            if state != "OK":
                return test.FAIL("The status is incorrect")

            if state in ["awaiting_essence", "no_essence"]:
                for i in range(0, CONFIG.STABLE_STATE_ATTEMPTS):
                    valid, response = TestHelper.do_request(
                        "GET", self.build_sender_status_url(sender_id)
                        )
                    if not valid:
                        return test.FAIL("Unexpected response from the streamcompatibility API: {}"
                                         .format(response))
                    if response.status_code != 200:
                        return test.FAIL(
                                "The streamcompatibility request for sender {} status has failed: {}"
                                .format(sender_id, response.json())
                            )
                    try:
                        state = response.json()["state"]
                    except json.JSONDecodeError:
                        return test.FAIL("Non-JSON response returned from the Stream Compatibility Management API")
                    except KeyError as e:
                        return test.FAIL("Unable to find expected key: {}".format(e))

                    if state in ["awaiting_essence", "no_essence"]:
                        time.sleep(CONFIG.STABLE_STATE_DELAY)
                    else:
                        break
            if state != "unconstrained":
                return test.FAIL("Expected state of sender {} is \"unconstrained\", got \"{}\""
                                 .format(sender_id, state))
        return test.PASS()

    # OUTPUTS TESTS
    def test_03_01(self, test):
        """
        Verify that the device supports the concept of Output.
        """
        if len(self.outputs) == 0:
            return test.UNCLEAR("No outputs")
        return test.PASS()

    def test_03_02(self, test):
        """
        Verify that some of the outputs of the device are connected.
        """
        if len(self.outputs) == 0:
            return test.UNCLEAR("No IS-11 outputs")
        for output in self.outputs:
            valid, response = TestHelper.do_request(
                "GET", self.compat_url + "outputs/" + output + "/properties/"
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

        active_connected_outputs = []

        for output_id in self.connected_outputs:
            valid, response = TestHelper.do_request(
                "GET", self.compat_url + "outputs/" + output_id + "/properties/"
            )
            if not valid:
                return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
            if response.status_code == 200:
                if response.json()["status"]["state"] == "signal_present":
                    active_connected_outputs.append(response.json())
            else:
                return test.FAIL("The output {} properties streamcompatibility request has failed: {}"
                                 .format(output_id, response.json()))
        if len(active_connected_outputs) != 0:
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
            if response.json()["id"] != receiver_id:
                return test.UNCLEAR(
                    "The IS-11 Receiver doesn't exist on the Node API as receiver."
                )
        return test.PASS()

    def test_04_02(self, test):
        """
        Verify receivers (generic with/without outputs)
        """
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
                "GET",  self.compat_url + "receivers/" + receiver_id + "/status/"
            )
            if not valid:
                return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
            if response.status_code != 200:
                return test.FAIL("The streamcompatibility request for receiver {} has failed: {}"
                                 .format(receiver_id, response.json()))
            if response.json()["state"] not in ["unknown", "non_compliant_stream"]:
                return test.FAIL("Receiver {}: expected states: \"unknown\" and \"non_compliant_stream\", got \"{}\""
                                 .format(receiver_id, response.json()["state"]))
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
                return test.WARNING("The receiver does not support BCP-004-01")
        return test.PASS()

    def test_04_03(self, test):
        """
        Verify receivers supporting outputs
        """
        if len(self.receivers_with_outputs) == 0:
            return test.UNCLEAR("No IS-11 receivers supporting outputs")
        """
        This test requires streaming from a Sender in order to
        verify the state of the Receiver and the associated outputs.
        If IS11_REFERENCE_SENDER_NODE_API_URL and IS11_REFERENCE_SENDER_CONNECTION_API_URL are not configured,
        this test fails.
        """
        if not (CONFIG.IS11_REFERENCE_SENDER_CONNECTION_API_URL and CONFIG.IS11_REFERENCE_SENDER_NODE_API_URL):
            return test.DISABLED("Please configure IS11_REFERENCE_SENDER_NODE_API_URL"
                                 " and IS11_REFERENCE_SENDER_CONNECTION_API_URL in Config.py")

        connection_api_senders = IS05Utils(CONFIG.IS11_REFERENCE_SENDER_CONNECTION_API_URL).get_senders()

        for format in ["urn:x-nmos:format:video", "urn:x-nmos:format:audio"]:
            self.reference_senders[format] = []
            for sender_id in connection_api_senders:
                valid, response = self.reference_is04_utils.checkCleanRequestJSON("GET", "senders/" + sender_id)
                if not valid:
                    return test.FAIL(response)

                if response["flow_id"] is None:
                    return test.UNCLEAR("\"flow_id\" of sender {} is null".format(sender_id))

                valid, response = self.reference_is04_utils.checkCleanRequestJSON("GET", "flows/" + response["flow_id"])
                if not valid:
                    return test.FAIL(response)

                if response["format"] == format:
                    if format in self.reference_senders:
                        self.reference_senders[format].append(sender_id)
                    else:
                        self.reference_senders[format] = [sender_id]
        if (len(self.reference_senders["urn:x-nmos:format:video"]) > 0 or
           len(self.reference_senders["urn:x-nmos:format:audio"]) > 0):
            return test.PASS()

        return test.UNCLEAR("Video and audio reference senders weren't found")

    def test_04_03_01(self, test):
        """
        Verify the status of the Receiver and the associated outputs using
        the reference Sender to produce the video stream consumed by the Receiver
        """
        if len(self.receivers_with_outputs) == 0:
            return test.UNCLEAR("No IS-11 receivers supporting outputs")
        """
        This test requires streaming from a Sender in order to
        verify the state of the Receiver and the associated outputs.
        If IS11_REFERENCE_SENDER_NODE_API_URL and IS11_REFERENCE_SENDER_CONNECTION_API_URL are not configured,
        this test fails.
        """
        if not (CONFIG.IS11_REFERENCE_SENDER_CONNECTION_API_URL and CONFIG.IS11_REFERENCE_SENDER_NODE_API_URL):
            return test.DISABLED("Please configure IS11_REFERENCE_SENDER_NODE_API_URL"
                                 " and IS11_REFERENCE_SENDER_CONNECTION_API_URL in Config.py")
        format = "urn:x-nmos:format:video"
        activated_receivers = 0
        valid, response = self.is11_utils.get_receivers_with_or_without_outputs_id(self.receivers, format)
        if not valid:
            return test.FAIL(response)
        for receiver_id in self.is11_utils.receivers_with_or_without_outputs:
            valid, response = self.is04_utils.checkCleanRequestJSON("GET", "receivers/" + receiver_id)
            if not valid:
                return test.FAIL(response)

            receiver = response

            if format not in self.reference_senders:
                return test.UNCLEAR("No reference video senders found")

            valid, response = self.is11_utils.activate_reference_sender_and_receiver(self.reference_senders, format,
                                                                                     receiver, receiver_id)
            if not valid:
                return test.FAIL(response)
            valid, response = self.is11_utils.stable_state_request(receiver_id, activated_receivers)
            if not valid:
                return test.FAIL(response)
            activated_receivers = response
            break
        try:
            if (activated_receivers < len(self.is11_utils.receivers_with_or_without_outputs)):
                return test.WARNING("There are no compatible senders for {} receivers"
                                    .format(len(self.is11_utils.receivers_with_or_without_outputs)
                                            - activated_receivers))
        except Exception:
            return test.UNCLEAR("No activated receivers")

        return test.PASS()

    def test_04_03_01_01(self, test):
        """
        Verify that the status of Outputs associated with video Receivers indicates that there is a signal.
        """
        if len(self.receivers_with_outputs) == 0:
            return test.UNCLEAR("No IS-11 receivers")
        if len(self.outputs) == 0:
            return test.UNCLEAR("No IS-11 receiver outputs")
        """
        This test requires streaming from a Sender in order to
        verify the state of the Receiver and the associated outputs.
        If IS11_REFERENCE_SENDER_NODE_API_URL and IS11_REFERENCE_SENDER_CONNECTION_API_URL are not configured,
        this test fails.
        """
        if not (CONFIG.IS11_REFERENCE_SENDER_CONNECTION_API_URL and CONFIG.IS11_REFERENCE_SENDER_NODE_API_URL):
            return test.DISABLED("Please configure IS11_REFERENCE_SENDER_NODE_API_URL"
                                 " and IS11_REFERENCE_SENDER_CONNECTION_API_URL in Config.py")

        for output_id in self.outputs:
            valid, response = TestHelper.do_request('GET', self.compat_url + "outputs/" + output_id + "/properties/")
            if not valid:
                return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
            if response.status_code != 200:
                return test.FAIL("The streamcompatibility request for output {} properties has failed: {}"
                                 .format(output_id, response.json()))
            try:
                state = response.json()["status"]["state"]
                print(state)
            except json.JSONDecodeError:
                return test.FAIL("Non-JSON response returned from the Stream Compatibility Management API")
            except KeyError as e:
                return test.FAIL("Unable to find expected key: {}".format(e))

            if state != "signal_present":
                for i in range(0, CONFIG.STABLE_STATE_ATTEMPTS):
                    valid, response = TestHelper.do_request('GET', self.build_output_properties_url(output_id))
                    if not valid:
                        return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
                    if response.status_code != 200:
                        return test.FAIL("The streamcompatibility request for output {} properties has failed: {}"
                                         .format(output_id, response.json()))

                    try:
                        state = response.json()["status"]["state"]
                        print(state)
                    except json.JSONDecodeError:
                        return test.FAIL("Non-JSON response returned from the Stream Compatibility Management API")
                    except KeyError as e:
                        return test.FAIL("Unable to find expected key: {}".format(e))

                    if state != "signal_present":
                        time.sleep(CONFIG.STABLE_STATE_DELAY)
                    else:
                        break
            if state != "signal_present":
                return test.FAIL("Expected state of output {} is \"signal_present\", got \"{}\""
                                 .format(output_id, state))

        if len(self.reference_senders["urn:x-nmos:format:video"]) == 0:
            return test.DISABLED("No IS-11 video reference senders")

        for sender_id in self.reference_senders["urn:x-nmos:format:video"]:
            valid, response = self.reference_is05_utils.checkCleanRequestJSON(
                "GET",
                "single/senders/" + sender_id + "/active"
            )
            if not valid:
                return test.FAIL(response)

            master_enable = response["master_enable"]

            if master_enable:
                json_data = {
                    "master_enable": False,
                    "activation": {"mode": "activate_immediate"}
                }

                valid, response = self.reference_is05_utils.checkCleanRequestJSON(
                    "PATCH",
                    "single/senders/" + sender_id + "/staged",
                    json_data
                )
                if not valid:
                    return test.FAIL(response)
        return test.PASS()

    def test_04_03_02(self, test):
        """
        Verify the status of the Receiver and the associated outputs using
        the reference Sender to produce an audio stream consumed by the Receiver
        """
        if len(self.receivers_with_outputs) == 0:
            return test.UNCLEAR("No IS-11 receivers supporting outputs")
        """
        This test requires streaming from a Sender in order to
        verify the state of the Receiver and the associated outputs.
        If IS11_REFERENCE_SENDER_NODE_API_URL and IS11_REFERENCE_SENDER_CONNECTION_API_URL are not configured,
        this test fails.
        """
        if not (CONFIG.IS11_REFERENCE_SENDER_CONNECTION_API_URL and CONFIG.IS11_REFERENCE_SENDER_NODE_API_URL):
            return test.DISABLED("Please configure IS11_REFERENCE_SENDER_NODE_API_URL"
                                 " and IS11_REFERENCE_SENDER_CONNECTION_API_URL in Config.py")
        format = "urn:x-nmos:format:audio"
        activated_receivers = 0
        valid, response = self.is11_utils.get_receivers_with_or_without_outputs_id(self.receivers, format)
        if not valid:
            return test.FAIL(response)
        for receiver_id in self.is11_utils.receivers_with_or_without_outputs:
            valid, response = self.is04_utils.checkCleanRequestJSON("GET", "receivers/" + receiver_id)
            if not valid:
                return test.FAIL(response)

            receiver = response

            if format not in self.reference_senders:
                return test.UNCLEAR("No reference audio senders found")

            valid, response = self.is11_utils.activate_reference_sender_and_receiver(self.reference_senders, format,
                                                                                     receiver, receiver_id)
            if not valid:
                return test.FAIL(response)
            valid, response = self.is11_utils.stable_state_request(receiver_id, activated_receivers)
            if not valid:
                return test.FAIL(response)
            activated_receivers = response
            break
        try:
            if (activated_receivers < len(self.is11_utils.receivers_with_or_without_outputs)):
                return test.WARNING("There are no compatible senders for {} receivers"
                                    .format(len(self.is11_utils.receivers_with_or_without_outputs)
                                            - activated_receivers))
        except Exception:
            return test.UNCLEAR("No activated receivers")

        return test.PASS()

    def test_04_03_02_01(self, test):
        """
        Verify that the status of Outputs associated with audio Receivers indicates that there is a signal.
        """
        if len(self.receivers_with_outputs) == 0:
            return test.UNCLEAR("No IS-11 receivers")
        if len(self.outputs) == 0:
            return test.UNCLEAR("No IS-11 receiver outputs")
        """
        This test requires streaming from a Sender in order to
        verify the state of the Receiver and the associated outputs.
        If IS11_REFERENCE_SENDER_NODE_API_URL and IS11_REFERENCE_SENDER_CONNECTION_API_URL are not configured,
        this test fails.
        """
        if not (CONFIG.IS11_REFERENCE_SENDER_CONNECTION_API_URL and CONFIG.IS11_REFERENCE_SENDER_NODE_API_URL):
            return test.DISABLED("Please configure IS11_REFERENCE_SENDER_NODE_API_URL"
                                 " and IS11_REFERENCE_SENDER_CONNECTION_API_URL in Config.py")

        for output_id in self.outputs:
            valid, response = TestHelper.do_request('GET', self.compat_url + "outputs/" + output_id + "/properties/")
            if not valid:
                return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
            if response.status_code != 200:
                return test.FAIL("The streamcompatibility request for output {} properties has failed: {}"
                                 .format(output_id, response.json()))
            try:
                state = response.json()["status"]["state"]
            except json.JSONDecodeError:
                return test.FAIL("Non-JSON response returned from the Stream Compatibility Management API")
            except KeyError as e:
                return test.FAIL("Unable to find expected key: {}".format(e))

            if state != "signal_present":
                for i in range(0, CONFIG.STABLE_STATE_ATTEMPTS):
                    valid, response = TestHelper.do_request('GET', self.build_output_properties_url(output_id))
                    if not valid:
                        return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
                    if response.status_code != 200:
                        return test.FAIL("The streamcompatibility request for output {} properties has failed: {}"
                                         .format(output_id, response.json()))

                    try:
                        state = response.json()["status"]["state"]
                    except json.JSONDecodeError:
                        return test.FAIL("Non-JSON response returned from the Stream Compatibility Management API")
                    except KeyError as e:
                        return test.FAIL("Unable to find expected key: {}".format(e))

                    if state != "signal_present":
                        time.sleep(CONFIG.STABLE_STATE_DELAY)
                    else:
                        break
            if state != "signal_present":
                return test.FAIL("Expected state of output {} is \"signal_present\", got \"{}\""
                                 .format(output_id, state))
        if len(self.reference_senders["urn:x-nmos:format:audio"]) == 0:
            return test.DISABLED("No IS-11 audio reference senders")

        for sender_id in self.reference_senders["urn:x-nmos:format:audio"]:
            valid, response = self.reference_is05_utils.checkCleanRequestJSON(
                "GET",
                "single/senders/" + sender_id + "/active"
            )
            if not valid:
                return test.FAIL(response)

            master_enable = response["master_enable"]

            if master_enable:
                json_data = {
                    "master_enable": False,
                    "activation": {"mode": "activate_immediate"}
                }

                valid, response = self.reference_is05_utils.checkCleanRequestJSON(
                    "PATCH",
                    "single/senders/" + sender_id + "/staged",
                    json_data
                )
                if not valid:
                    return test.FAIL(response)
        return test.PASS()

    def test_04_04(self, test):
        """
        Verify receivers not supporting outputs
        """
        if len(self.receivers) == 0:
            return test.UNCLEAR("No IS-11 receivers")
        if len(self.receivers_without_outputs) == 0:
            return test.UNCLEAR("All IS-11 receivers support outputs")
        """
        The test requires streaming from a Sender in
        order to verify the state of the Receiver.
        """
        if not (CONFIG.IS11_REFERENCE_SENDER_CONNECTION_API_URL and CONFIG.IS11_REFERENCE_SENDER_NODE_API_URL):
            return test.DISABLED("Please configure IS11_REFERENCE_SENDER_NODE_API_URL"
                                 " and IS11_REFERENCE_SENDER_CONNECTION_API_URL in Config.py")
        connection_api_senders = IS05Utils(CONFIG.IS11_REFERENCE_SENDER_CONNECTION_API_URL).get_senders()
        for format in ["urn:x-nmos:format:video", "urn:x-nmos:format:audio"]:
            for sender_id in connection_api_senders:
                valid, response = self.reference_is04_utils.checkCleanRequestJSON("GET", "senders/" + sender_id)
                if not valid:
                    return test.FAIL(response)

                if response["flow_id"] is None:
                    return test.UNCLEAR("\"flow_id\" of sender {} is null".format(sender_id))

                valid, response = self.reference_is04_utils.checkCleanRequestJSON("GET", "flows/" + response["flow_id"])
                if not valid:
                    return test.FAIL(response)

                if response["format"] == format:
                    if format in self.reference_senders:
                        self.reference_senders[format].append(sender_id)
                    else:
                        self.reference_senders[format] = [sender_id]
        if (len(self.reference_senders["urn:x-nmos:format:video"]) > 0 or
           len(self.reference_senders["urn:x-nmos:format:audio"]) > 0):
            return test.PASS()

        return test.UNCLEAR("Video and audio reference senders weren't found")

    def test_04_04_01(self, test):
        """
        Verify the status of the Receiver.
        The test requires video  streaming from a Sender
        in order to verify the state of the Receiver.
        """
        if len(self.receivers_without_outputs) == 0:
            return test.UNCLEAR("All IS-11 receivers support outputs")
        if not (CONFIG.IS11_REFERENCE_SENDER_CONNECTION_API_URL and CONFIG.IS11_REFERENCE_SENDER_NODE_API_URL):
            return test.DISABLED("Please configure IS11_REFERENCE_SENDER_NODE_API_URL"
                                 " and IS11_REFERENCE_SENDER_CONNECTION_API_URL in Config.py")
        format = "urn:x-nmos:format:video"
        activated_receivers = 0
        valid, response = self.is11_utils.get_receivers_with_or_without_outputs_id(self.receivers, format)
        if not valid:
            return test.FAIL(response)
        for receiver_id in self.is11_utils.receivers_with_or_without_outputs:
            valid, response = self.is04_utils.checkCleanRequestJSON("GET", "receivers/" + receiver_id)
            if not valid:
                return test.FAIL(response)

            receiver = response

            if format not in self.reference_senders:
                return test.UNCLEAR("No reference video senders found")

            valid, response = self.is11_utils.activate_reference_sender_and_receiver(self.reference_senders, format,
                                                                                     receiver, receiver_id)
            if not valid:
                return test.FAIL(response)
            valid, response = self.is11_utils.stable_state_request(receiver_id, activated_receivers)
            if not valid:
                return test.FAIL(response)
            activated_receivers = response
            break
        try:
            if (activated_receivers < len(self.is11_utils.receivers_with_or_without_outputs)):
                return test.WARNING("There are no compatible senders for {} receivers"
                                    .format(len(self.is11_utils.receivers_with_or_without_outputs)
                                            - activated_receivers))
        except Exception:
            return test.UNCLEAR("No activated receivers")
        return test.PASS()

    def test_04_04_02(self, test):
        """
        Verify the status of the Receiver.
        The test requires audio  streaming from a Sender
        in order to verify the state of the Receiver.
        """
        if len(self.receivers_without_outputs) == 0:
            return test.UNCLEAR("All IS-11 receivers support outputs")

        if not (CONFIG.IS11_REFERENCE_SENDER_CONNECTION_API_URL and CONFIG.IS11_REFERENCE_SENDER_NODE_API_URL):
            return test.DISABLED("Please configure IS11_REFERENCE_SENDER_NODE_API_URL"
                                 " and IS11_REFERENCE_SENDER_CONNECTION_API_URL in Config.py")
        format = "urn:x-nmos:format:audio"
        activated_receivers = 0
        valid, response = self.is11_utils.get_receivers_with_or_without_outputs_id(self.receivers, format)
        if not valid:
            return test.FAIL(response)
        for receiver_id in self.is11_utils.receivers_with_or_without_outputs:
            valid, response = self.is04_utils.checkCleanRequestJSON("GET", "receivers/" + receiver_id)
            if not valid:
                return test.FAIL(response)

            receiver = response

            if format not in self.reference_senders:
                return test.UNCLEAR("No reference video senders found")

            valid, response = self.is11_utils.activate_reference_sender_and_receiver(self.reference_senders, format,
                                                                                     receiver, receiver_id)
            if not valid:
                return test.FAIL(response)
            valid, response = self.is11_utils.stable_state_request(receiver_id, activated_receivers)
            if not valid:
                return test.FAIL(response)
            activated_receivers = response
            break
        try:
            if (activated_receivers < len(self.is11_utils.receivers_with_or_without_outputs)):
                return test.WARNING("There are no compatible senders for {} receivers"
                                    .format(len(self.is11_utils.receivers_with_or_without_outputs)
                                            - activated_receivers))
        except Exception:
            return test.UNCLEAR("No activated receivers")
        return test.PASS()

    def test_06_01(self, test):
        """A sender rejects Active Constraints with unsupported Parameter Constraint URN(s)"""

        if len(self.senders) == 0:
            return test.UNCLEAR("Not tested. No senders found.")

        for senderId in self.is11_utils.sampled_list(self.senders):
            try:
                url = "senders/{}/constraints/active".format(senderId)
                data = {"constraint_sets": [{"urn:x-nmos:cap:not:existing": {"enum": [""]}}]}
                valid, response = self.is11_utils.checkCleanRequestJSON("PUT", url, data, 400)
                if not valid:
                    return test.FAIL(response)
            except json.JSONDecodeError:
                return test.FAIL("Non-JSON response returned from Node API")
            except KeyError as e:
                return test.FAIL("Unable to find expected key: {}".format(e))

        return test.PASS()

    def test_06_02(self, test):
        """
        PUTting an empty 'constraint_sets' array to Active Constraints of a sender switches its state to 'unconstrained'
        """

        if len(self.senders) == 0:
            return test.UNCLEAR("Not tested. No senders found.")

        for senderId in self.is11_utils.sampled_list(self.senders):
            try:
                url = "senders/{}/constraints/active".format(senderId)
                data = {"constraint_sets": []}
                valid, response = self.is11_utils.checkCleanRequestJSON("PUT", url, data)
                if not valid:
                    return test.FAIL(response)

                valid, response = self.is11_utils.checkCleanRequestJSON("GET", url)
                if not valid:
                    return test.FAIL(response)

                if response != data:
                    return test.FAIL("Sender {} has Active Constraints {} when {} is expected"
                                     .format(senderId, response, data))

                url = "senders/{}/status".format(senderId)
                valid, response = self.is11_utils.checkCleanRequestJSON("GET", url)
                if not valid:
                    return test.FAIL(response)

                state = response["state"]
                state_expected = "unconstrained"
                if state != state_expected:
                    if state == self.state_awaiting_essence or state == self.state_no_essence:
                        return test.UNCLEAR("Sender {} has state: {}".format(senderId, state))
                    else:
                        return test.FAIL("Sender {} has state: {}. Expected state: "
                                         "{}".format(senderId, state, state_expected))

            except json.JSONDecodeError:
                return test.FAIL("Non-JSON response returned from Node API")
            except KeyError as e:
                return test.FAIL("Unable to find expected key: {}".format(e))

        return test.PASS()

    def test_06_03(self, test):
        """
        DELETing Active Constrains of a sender switches its state to 'unconstrained'
        """

        if len(self.senders) == 0:
            return test.UNCLEAR("Not tested. No senders found.")

        for senderId in self.is11_utils.sampled_list(self.senders):
            try:
                url = "senders/{}/constraints/active".format(senderId)
                data = {"constraint_sets": []}
                valid, response = self.is11_utils.checkCleanRequestJSON("DELETE", url)
                if not valid:
                    return test.FAIL(response)

                valid, response = self.is11_utils.checkCleanRequestJSON("GET", url)
                if not valid:
                    return test.FAIL(response)

                if response != data:
                    return test.FAIL("Sender {} has Active Constraints {} when {} is expected"
                                     .format(senderId, response, data))

                url = "senders/{}/status".format(senderId)
                valid, response = self.is11_utils.checkCleanRequestJSON("GET", url)
                if not valid:
                    return test.FAIL(response)

                state = response["state"]
                state_expected = "unconstrained"
                if state != state_expected:
                    if state == self.state_awaiting_essence or state == self.state_no_essence:
                        return test.UNCLEAR("Sender {} has state: {}".format(senderId, state))
                    else:
                        return test.FAIL("Sender {} has state: {}. Expected state: "
                                         "{}".format(senderId, state, state_expected))

            except json.JSONDecodeError:
                return test.FAIL("Non-JSON response returned from Stream Compatibility Management API")
            except KeyError as e:
                return test.FAIL("Unable to find expected key: {}".format(e))

        return test.PASS()

    def test_06_04(self, test):
        """Effective EDID updates if Base EDID changes"""

        if len(self.inputs) == 0:
            return test.UNCLEAR("Not tested. No inputs found.")

        inputs_tested = []

        for inputId in self.is11_utils.sampled_list(self.inputs):
            valid, response = self.do_request("GET", self.compat_url + "inputs/" + inputId + "/properties")
            if not valid or response.status_code != 200:
                return test.FAIL("Unexpected response from "
                                 "the Stream Compatibility Management API: {}".format(response))

            try:
                input = response.json()
                if not input["edid_support"]:
                    continue

                valid, response = self.do_request("GET", self.compat_url + "inputs/" + inputId + "/edid/effective")
                if not valid or response.status_code != 200:
                    return test.FAIL("Unexpected response from "
                                     "the Stream Compatibility Management API: {}".format(response))

                effective_edid_before = response.content

                base_edid = bytearray([
                    0x00, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0x00,
                    0x04, 0x43, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
                    0x00, 0x0a, 0x01, 0x04, 0x80, 0x00, 0x00, 0x00,
                    0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
                    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x01, 0x01,
                    0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01,
                    0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x00, 0x00,
                    0x00, 0x10, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
                    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
                    0x00, 0x00, 0x00, 0x10, 0x00, 0x00, 0x00, 0x00,
                    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
                    0x00, 0x00, 0x00, 0x00, 0x00, 0x10, 0x00, 0x00,
                    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
                    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x10,
                    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
                    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xde
                ])

                valid, response = self.do_request("PUT",
                                                  self.compat_url + "inputs/" + inputId + "/edid/base",
                                                  headers={"Content-Type": "application/octet-stream"},
                                                  data=base_edid)
                if not valid or response.status_code != 204:
                    return test.FAIL("Unexpected response from "
                                     "the Stream Compatibility Management API: {}".format(response))

                time.sleep(CONFIG.STABLE_STATE_DELAY)

                valid, response = self.do_request("GET", self.compat_url + "inputs/" + inputId + "/edid/effective")
                if not valid or response.status_code != 200:
                    return test.FAIL("Unexpected response from "
                                     "the Stream Compatibility Management API: {}".format(response))

                if response.content == effective_edid_before:
                    return test.FAIL("Effective EDID doesn't change when Base EDID changes")

                inputs_tested.append(inputId)

            except json.JSONDecodeError:
                return test.FAIL("Non-JSON response returned from Node API")
            except KeyError as e:
                return test.FAIL("Unable to find expected key: {}".format(e))

        if len(inputs_tested) > 0:
            return test.PASS()
        else:
            return test.UNCLEAR("Not tested. No inputs with EDID support found.")

    def test_06_05(self, test):
        """Effective EDID updates if Base EDID removed"""

        if len(self.inputs) == 0:
            return test.UNCLEAR("Not tested. No inputs found.")

        inputs_tested = []

        for inputId in self.is11_utils.sampled_list(self.inputs):
            valid, response = self.do_request("GET", self.compat_url + "inputs/" + inputId + "/properties")
            if not valid or response.status_code != 200:
                return test.FAIL("Unexpected response from "
                                 "the Stream Compatibility Management API: {}".format(response))

            try:
                input = response.json()
                if not input["edid_support"]:
                    continue

                valid, response = self.do_request("GET", self.compat_url + "inputs/" + inputId + "/edid/effective")
                if not valid or response.status_code != 200:
                    return test.FAIL("Unexpected response from "
                                     "the Stream Compatibility Management API: {}".format(response))

                effective_edid_before = response.content

                valid, response = self.do_request("DELETE", self.compat_url + "inputs/" + inputId + "/edid/base")
                if not valid or response.status_code != 204:
                    return test.FAIL("Unexpected response from "
                                     "the Stream Compatibility Management API: {}".format(response))

                time.sleep(CONFIG.STABLE_STATE_DELAY)

                valid, response = self.do_request("GET", self.compat_url + "inputs/" + inputId + "/edid/effective")
                if not valid or response.status_code != 200:
                    return test.FAIL("Unexpected response from "
                                     "the Stream Compatibility Management API: {}".format(response))

                if response.content == effective_edid_before:
                    return test.FAIL("Effective EDID doesn't change when Base EDID changes")

                inputs_tested.append(inputId)

            except json.JSONDecodeError:
                return test.FAIL("Non-JSON response returned from Node API")
            except KeyError as e:
                return test.FAIL("Unable to find expected key: {}".format(e))

        if len(inputs_tested) > 0:
            return test.PASS()
        else:
            return test.UNCLEAR("Not tested. No inputs with EDID support found.")
