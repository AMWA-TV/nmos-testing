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

from functools import partial
import time
import re

from requests.compat import json
from ..NMOSUtils import NMOSUtils
from ..GenericTest import GenericTest, NMOSInitException, NMOSTestException
from .. import Config as CONFIG
from ..IS04Utils import IS04Utils
from ..IS05Utils import IS05Utils
import datetime
from ..IS11Utils import IS11Utils

COMPAT_API_KEY = "streamcompatibility"
CONTROLS = "controls"
NODE_API_KEY = "node"
CONN_API_KEY = "connection"
VALID_EDID_PATH = "test_data/IS1101/valid_edid.bin"
INVALID_EDID_PATH = "test_data/IS1101/invalid_edid.bin"

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
        self.not_active_connected_inputs = []
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
        with open(INVALID_EDID_PATH, "rb") as f:
            self.invalid_edid = f.read()

        with open(VALID_EDID_PATH, "rb") as f:
            self.valid_edid = f.read()

        self.senders = self.is11_utils.get_senders()
        self.receivers = self.is11_utils.get_receivers()

        self.receivers_with_outputs = list(filter(self.receiver_has_i_o, self.receivers))
        self.receivers_without_outputs = list(set(self.receivers) - set(self.receivers_with_outputs))

        self.inputs = self.is11_utils.get_inputs()
        self.outputs = self.is11_utils.get_outputs()

        self.connected_inputs = list(filter(self.is_input_connected, self.inputs))
        self.disconnected_inputs = list(set(self.inputs) - set(self.connected_inputs))

        self.edid_connected_inputs = list(filter(self.has_input_edid_support, self.connected_inputs))
        self.not_edid_connected_inputs = list(set(self.connected_inputs) - set(self.edid_connected_inputs))

        self.edid_inputs = list(filter(self.has_input_edid_support, self.inputs))
        self.non_edid_inputs = list(set(self.inputs) - set(self.edid_inputs))

        self.base_edid_inputs = list(filter(self.has_input_base_edid_support, self.edid_inputs))
        self.adjust_to_caps_inputs = list(filter(self.is_input_adjust_to_caps, self.base_edid_inputs))

        self.connected_outputs = list(filter(self.is_output_connected, self.outputs))
        self.disconnected_outputs = list(set(self.outputs) - set(self.connected_outputs))

        self.edid_outputs = list(filter(self.has_output_edid_support, self.outputs))
        self.non_edid_outputs = list(set(self.outputs) - set(self.edid_outputs))

        self.edid_connected_outputs = list(filter(self.has_output_edid_support, self.connected_outputs))
        self.edid_disconnected_outputs = list(filter(self.has_output_edid_support, self.disconnected_outputs))

        self.state_no_essence = "no_essence"
        self.state_awaiting_essence = "awaiting_essence"

        self.deactivate_connection_resources("sender")
        self.deactivate_connection_resources("receiver")

        self.delete_active_constraints()
        self.delete_base_edid()

    def tear_down_tests(self):
        for inputId in self.is11_utils.sampled_list(self.base_edid_inputs):
            # DELETE the Base EDID of the Input
            self.do_request("DELETE", self.compat_url + "inputs/" + inputId + "/edid/base")

    # GENERAL TESTS
    def test_00_00(self, test):
        """At least one Device is showing an IS-11 control advertisement matching the API under test"""

        control_type = "urn:x-nmos:control:stream-compat/" + self.apis[COMPAT_API_KEY]["version"]
        return NMOSUtils.do_test_device_control(
            test,
            self.node_url,
            control_type,
            self.compat_url,
            self.authorization
        )

    # INPUTS TESTS
    def test_01_00(self, test):
        """
        Verify that all connected inputs have a signal
        """
        if len(self.connected_inputs) != 0:
            for connectedInput in self.connected_inputs:
                input = self.get_json(test, self.compat_url + "inputs/" + connectedInput + "/properties/")
                state = input["status"]["state"]
                id = input["id"]
                if state == "no_signal" or state == "awaiting_signal":
                    if state == "awaiting_signal":
                        for i in range(0, CONFIG.STABLE_STATE_ATTEMPTS):
                            valid, response = self.do_request(
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
                        self.not_active_connected_inputs.append(input)
            if len(self.not_active_connected_inputs) != 0:
                for input in self.not_active_connected_inputs:
                    self.connected_inputs.remove(input)
            if len(self.connected_inputs) != 0:
                return test.PASS()
            return test.UNCLEAR("No connected input have a signal")
        return test.UNCLEAR("No resources found to perform this test")

    def test_01_01(self, test):
        """Inputs with EDID support return the Effective EDID"""
        if len(self.edid_inputs) == 0:
            return test.UNCLEAR("Not tested. No inputs with EDID support found.")

        for inputId in self.is11_utils.sampled_list(self.edid_inputs):
            self.get_effective_edid(test, inputId)

        return test.PASS()

    def test_01_02(self, test):
        """Inputs with Base EDID support handle PUTting and DELETing the Base EDID"""
        def is_edid_equal_to_effective_edid(self, test, inputId, edid):
            return self.get_effective_edid(test, inputId) == edid

        if len(self.base_edid_inputs) == 0:
            return test.UNCLEAR("Not tested. No inputs with Base EDID support found.")

        for inputId in self.is11_utils.sampled_list(self.base_edid_inputs):
            # Save the default value of the Effective EDID
            default_edid = self.get_effective_edid(test, inputId)

            # PUT the Base EDID to the Input
            valid, response = self.do_request("PUT",
                                              self.compat_url + "inputs/" + inputId + "/edid/base",
                                              headers={"Content-Type": "application/octet-stream"},
                                              data=self.valid_edid)
            if not valid or response.status_code != 204:
                return test.FAIL("Unexpected response from "
                                 "the Stream Compatibility Management API: {}".format(response))

            # Verify that /edid/base returns the last Base EDID put
            valid, response = self.do_request("GET", self.compat_url + "inputs/" + inputId + "/edid/base")
            if (
                not valid
                or response.status_code != 200
                or response.headers["Content-Type"] != "application/octet-stream"
            ):
                return test.FAIL("Unexpected response from "
                                 "the Stream Compatibility Management API: {}".format(response))
            if response.content != self.valid_edid:
                return test.FAIL("The Base EDID of Input {} "
                                 "doesn't match the Base EDID that has been put".format(inputId))

            # Verify that /edid/effective returns the last Base EDID put
            result = self.wait_until_true(
                partial(is_edid_equal_to_effective_edid, self, test, inputId, self.valid_edid)
            )
            if not result:
                return test.FAIL("The Effective EDID of Input {} "
                                 "doesn't match the Base EDID that has been put".format(inputId))

            # Delete the Base EDID
            valid, response = self.do_request("DELETE", self.compat_url + "inputs/" + inputId + "/edid/base")
            if not valid or response.status_code != 204:
                return test.FAIL("Unexpected response from "
                                 "the Stream Compatibility Management API: {}".format(response))

            # Verify that the Base EDID is properly deleted
            valid, response = self.do_request("GET", self.compat_url + "inputs/" + inputId + "/edid/base")
            if not valid or response.status_code != 204:
                return test.FAIL("Unexpected response from "
                                 "the Stream Compatibility Management API: {}".format(response))

            # Verify that /edid/effective returned to its defaults
            result = self.wait_until_true(partial(is_edid_equal_to_effective_edid, self, test, inputId, default_edid))
            if not result:
                return test.FAIL("The Effective EDID of Input {} "
                                 "doesn't match its initial value".format(inputId))

        return test.PASS()

    def test_01_03(self, test):
        """Inputs with Base EDID support reject an invalid EDID"""
        if len(self.base_edid_inputs) == 0:
            return test.UNCLEAR("Not tested. No inputs with Base EDID support found.")

        for inputId in self.is11_utils.sampled_list(self.base_edid_inputs):
            valid, response = self.do_request("PUT",
                                              self.compat_url + "inputs/" + inputId + "/edid/base",
                                              headers={"Content-Type": "application/octet-stream"},
                                              data=self.invalid_edid)
            if not valid or response.status_code != 400:
                return test.FAIL("Unexpected response from "
                                 "the Stream Compatibility Management API: {}".format(response))
        return test.PASS()

    def test_01_04(self, test):
        """Inputs without EDID support reject requests to /edid/*"""
        if len(self.non_edid_inputs) == 0:
            return test.UNCLEAR("Not tested. No inputs without EDID support found.")

        for inputId in self.is11_utils.sampled_list(self.non_edid_inputs):
            valid, response = self.do_request("GET", self.compat_url + "inputs/" + inputId + "/edid/effective")
            if not valid or response.status_code != 204:
                return test.FAIL("Unexpected response "
                                 "for GET /edid/effective: {}".format(response))

            valid, response = self.do_request("GET", self.compat_url + "inputs/" + inputId + "/edid/base")
            if not valid or response.status_code != 204:
                return test.FAIL("Unexpected response "
                                 "for GET /edid/base: {}".format(response))

            valid, response = self.do_request("DELETE", self.compat_url + "inputs/" + inputId + "/edid/base")
            if not valid or response.status_code != 405:
                return test.FAIL("Unexpected response "
                                 "for DELETE /edid/base: {}".format(response))

            valid, response = self.do_request("PUT",
                                              self.compat_url + "inputs/" + inputId + "/edid/base",
                                              headers={"Content-Type": "application/octet-stream"},
                                              data=self.valid_edid)
            if not valid or response.status_code != 405:
                return test.FAIL("Unexpected response "
                                 "for PUT /edid/base: {}".format(response))
        return test.PASS()

    def test_01_05(self, test):
        """
        Inputs with Base EDID increment their version and versions of associated Senders
        after the Base EDID gets modified
        """
        if len(self.base_edid_inputs) == 0:
            return test.UNCLEAR("Not tested. No inputs with Base EDID support found.")

        for inputId in self.is11_utils.sampled_list(self.base_edid_inputs):
            sender_ids = self.get_inputs_senders(test, inputId)

            in_version_1 = ""
            in_version_2 = ""
            in_version_3 = ""

            snd_versions_1 = {}
            snd_versions_2 = {}
            snd_versions_3 = {}

            for sender_id in sender_ids:
                snd_versions_1[sender_id] = ""
                snd_versions_2[sender_id] = ""
                snd_versions_3[sender_id] = ""

            valid, response = self.do_request("GET", self.compat_url + "inputs/" + inputId + "/properties")
            if not valid or response.status_code != 200:
                return test.FAIL("Unexpected response from "
                                 "the Stream Compatibility Management API: {}".format(response))
            try:
                in_version_1 = response.json()["version"]
            except json.JSONDecodeError:
                return test.FAIL("Non-JSON response returned from the Stream Compatibility Management API")
            except KeyError as e:
                return test.FAIL("Unable to find expected key: {}".format(e))

            for sender_id in sender_ids:
                valid, response = self.do_request("GET", self.node_url + "senders/" + sender_id)
                if not valid or response.status_code != 200:
                    return test.FAIL("Unexpected response from the Node API: {}".format(response))
                try:
                    snd_versions_1[sender_id] = response.json()["version"]
                except json.JSONDecodeError:
                    return test.FAIL("Non-JSON response returned from the Node API")
                except KeyError as e:
                    return test.FAIL("Unable to find expected key: {}".format(e))

            # PUT the Base EDID to the Input
            valid, response = self.do_request("PUT",
                                              self.compat_url + "inputs/" + inputId + "/edid/base",
                                              headers={"Content-Type": "application/octet-stream"},
                                              data=self.valid_edid)
            if not valid or response.status_code != 204:
                return test.FAIL("Unexpected response from "
                                 "the Stream Compatibility Management API: {}".format(response))

            valid, response = self.do_request("GET", self.compat_url + "inputs/" + inputId + "/properties")
            if not valid or response.status_code != 200:
                return test.FAIL("Unexpected response from "
                                 "the Stream Compatibility Management API: {}".format(response))
            try:
                in_version_2 = response.json()["version"]
            except json.JSONDecodeError:
                return test.FAIL("Non-JSON response returned from the Stream Compatibility Management API")
            except KeyError as e:
                return test.FAIL("Unable to find expected key: {}".format(e))

            for sender_id in sender_ids:
                valid, response = self.do_request("GET", self.node_url + "senders/" + sender_id)
                if not valid or response.status_code != 200:
                    return test.FAIL("Unexpected response from the Node API: {}".format(response))
                try:
                    snd_versions_2[sender_id] = response.json()["version"]
                except json.JSONDecodeError:
                    return test.FAIL("Non-JSON response returned from the Node API")
                except KeyError as e:
                    return test.FAIL("Unable to find expected key: {}".format(e))

            if in_version_2 == in_version_1:
                return test.FAIL("Input {} didn't increment its version after PUTting the Base EDID".format(inputId))
            for sender_id in sender_ids:
                if snd_versions_2[sender_id] == snd_versions_1[sender_id]:
                    return test.FAIL("Sender {} didn't increment its version "
                                     "after PUTting the Base EDID to Input {}".format(sender_id, inputId))

            # DELETE the Base EDID of the Input
            valid, response = self.do_request("DELETE", self.compat_url + "inputs/" + inputId + "/edid/base")
            if not valid or response.status_code != 204:
                return test.FAIL("Unexpected response from "
                                 "the Stream Compatibility Management API: {}".format(response))

            valid, response = self.do_request("GET", self.compat_url + "inputs/" + inputId + "/properties")
            if not valid or response.status_code != 200:
                return test.FAIL("Unexpected response from "
                                 "the Stream Compatibility Management API: {}".format(response))
            try:
                in_version_3 = response.json()["version"]
            except json.JSONDecodeError:
                return test.FAIL("Non-JSON response returned from the Stream Compatibility Management API")
            except KeyError as e:
                return test.FAIL("Unable to find expected key: {}".format(e))

            for sender_id in sender_ids:
                valid, response = self.do_request("GET", self.node_url + "senders/" + sender_id)
                if not valid or response.status_code != 200:
                    return test.FAIL("Unexpected response from the Node API: {}".format(response))
                try:
                    snd_versions_3[sender_id] = response.json()["version"]
                except json.JSONDecodeError:
                    return test.FAIL("Non-JSON response returned from the Node API")
                except KeyError as e:
                    return test.FAIL("Unable to find expected key: {}".format(e))

            if in_version_3 == in_version_2:
                return test.FAIL("Input {} didn't increment its version after DELETing the Base EDID".format(inputId))
            for sender_id in sender_ids:
                if snd_versions_3[sender_id] == snd_versions_2[sender_id]:
                    return test.FAIL("Sender {} didn't increment its version "
                                     "after PUTting the Base EDID to Input {}".format(sender_id, inputId))

        return test.PASS()

    def test_01_06(self, test):
        """Effective EDID updates if Base EDID changes with 'adjust_to_caps'"""

        def is_edid_equal_to_effective_edid(self, test, inputId, edid):
            return self.get_effective_edid(test, inputId) == edid

        def is_edid_inequal_to_effective_edid(self, test, inputId, edid):
            return self.get_effective_edid(test, inputId) != edid

        if len(self.adjust_to_caps_inputs) == 0:
            return test.UNCLEAR("Not tested. No inputs with 'adjust_to_caps' support found.")

        for inputId in self.is11_utils.sampled_list(self.adjust_to_caps_inputs):
            try:
                effective_edid_before = self.get_effective_edid(test, inputId)

                valid, response = self.do_request("PUT",
                                                  self.compat_url + "inputs/" + inputId + "/edid/base",
                                                  headers={"Content-Type": "application/octet-stream"},
                                                  data=self.valid_edid,
                                                  params={"adjust_to_caps": "true"})
                if not valid or response.status_code != 204:
                    return test.FAIL("Unexpected response from "
                                     "the Stream Compatibility Management API: {}".format(response))

                result = self.wait_until_true(
                    partial(is_edid_inequal_to_effective_edid, self, test, inputId, effective_edid_before)
                )
                if not result:
                    return test.FAIL("Effective EDID doesn't change when Base EDID changes")

                valid, response = self.do_request("DELETE", self.compat_url + "inputs/" + inputId + "/edid/base")
                if not valid or response.status_code != 204:
                    return test.FAIL("Unexpected response from "
                                     "the Stream Compatibility Management API: {}".format(response))

                result = self.wait_until_true(
                    partial(is_edid_equal_to_effective_edid, self, test, inputId, effective_edid_before)
                )
                if not result:
                    return test.FAIL("Effective EDID doesn't restore after Base EDID DELETion")

            except json.JSONDecodeError:
                return test.FAIL("Non-JSON response returned from Node API")
            except KeyError as e:
                return test.FAIL("Unable to find expected key: {}".format(e))
        return test.PASS()

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
                valid, response = self.do_request(
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
                valid, response = self.do_request("GET", self.node_url + "senders/" + sender_id)
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
                valid, response = self.do_request(
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
                        valid, response = self.do_request(
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
                valid, response = self.do_request(
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
            valid, response = self.do_request(
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
        "Verify that the video sender supports the minimum set of video constraints"

        sample = "^urn:x-nmos:cap:"

        if len(self.flow_format_audio) == 0:
            return test.UNCLEAR("There is no audio format")

        for sender_id in self.flow_format_audio:
            valid, response = self.do_request(
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
            valid, response = self.do_request(
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
            valid, response = self.do_request(
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
            valid, response = self.do_request(
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
            valid, response = self.do_request(
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
            valid, response = self.do_request(
                "DELETE",
                self.build_constraints_active_url(sender_id),
            )
            if not valid:
                return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
            if response.status_code != 200:
                return test.FAIL(
                   "The sender {} constraints cannot be deleted".format(sender_id)
                )
            valid, response = self.do_request(
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
            valid, response = self.do_request(
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
            valid, response = self.do_request(
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
            valid, response = self.do_request(
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
            valid, response = self.do_request(
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

            valid, response = self.do_request(
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

            valid, response = self.do_request(
                "DELETE",
                self.build_constraints_active_url(sender_id),
            )
            if not valid:
                return test.FAIL("Unexpected response from the streamcompatibility API: {}".format(response))
            if response.status_code != 200:
                return test.FAIL(
                    "The sender {} constraints cannot be deleted".format(sender_id)
                )

            valid, response = self.do_request(
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

            valid, response = self.do_request(
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
            valid, response = self.do_request(
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
                    valid, response = self.do_request(
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

            valid, response = self.do_request(
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

            valid, response = self.do_request(
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
                    valid, response = self.do_request(
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

            valid, response = self.do_request(
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

            valid, response = self.do_request(
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
            valid, response = self.do_request(
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
                    valid, response = self.do_request(
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
            valid, response = self.do_request(
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

            valid, response = self.do_request(
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
                    valid, response = self.do_request(
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

            valid, response = self.do_request(
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

            valid, response = self.do_request(
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
            valid, response = self.do_request(
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
                    valid, response = self.do_request(
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

            valid, response = self.do_request(
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

            valid, response = self.do_request(
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
            valid, response = self.do_request(
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
            valid, response = self.do_request(
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
                    valid, response = self.do_request(
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
            valid, response = self.do_request(
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

            valid, response = self.do_request(
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
            valid, response = self.do_request(
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

            valid, response = self.do_request(
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
            valid, response = self.do_request(
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
            valid, response = self.do_request(
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
                    valid, response = self.do_request(
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

            valid, response = self.do_request(
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
            valid, response = self.do_request(
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

            valid, response = self.do_request(
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
            valid, response = self.do_request(
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
                    valid, response = self.do_request(
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

            valid, response = self.do_request(
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
            valid, response = self.do_request(
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

            valid, response = self.do_request(
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

            valid, response = self.do_request(
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
            valid, response = self.do_request(
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
            valid, response = self.do_request(
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
                valid, response = self.do_request(
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

    def _test_02_03_02(self, test):
        """
        Verify that the input passed its test suite
        """
        if len(self.input_senders) != 0:
            for sender_id in self.input_senders:
                valid, response = self.do_request(
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
                valid, response = self.do_request(
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
                        valid, response = self.do_request(
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
                valid, response = self.do_request(
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
                            and input_id in self.base_edid_inputs
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
                    valid, response = self.do_request(
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

                    valid, response = self.do_request(
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

                    valid, response = self.do_request("PUT",
                                                      self.compat_url + "inputs/" + input_id + "/edid/base",
                                                      headers={"Content-Type": "application/octet-stream"},
                                                      data=self.valid_edid)
                    if not valid or response.status_code != 204:
                        return test.FAIL("Unexpected response from the Stream Compatibility Management API: {}"
                                         .format(response))
                    time.sleep(CONFIG.STABLE_STATE_DELAY)

                    valid, response = self.do_request(
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

                    valid, response = self.do_request(
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

                    valid, response = self.do_request(
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
        Verify for inputs supporting EDID that the version and the effective EDID change when applying constraints (video)
        """
        if len(self.flow_format_video) == 0:
            return test.UNCLEAR("There is no video format")

        for sender_id in self.flow_format_video:
            valid, response = self.do_request(
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
                        and input_id in self.base_edid_inputs
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
                valid, response = self.do_request(
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

                valid, response = self.do_request(
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

                default_edid = self.get_effective_edid(test, input_id)

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
                valid, response = self.do_request(
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

                valid, response = self.do_request(
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
                if response.content == default_edid:
                    print("Grain rate constraint are not changing effective EDID")

                valid, response = self.do_request(
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
                valid, response = self.do_request(
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
                    valid, response = self.do_request(
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

                valid, response = self.do_request(
                    "GET",
                    self.compat_url + "senders/" + sender_id + "/status/"
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
                        valid, response = self.do_request(
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

                valid, response = self.do_request(
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
                valid, response = self.do_request(
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
                valid, response = self.do_request(
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
        Verify for inputs supporting EDID that the version and the effective EDID change when applying constraints (audio)
        """
        if len(self.flow_format_audio) == 0:
            return test.UNCLEAR("There is no audio format")

        for sender_id in self.flow_format_audio:
            valid, response = self.do_request(
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
                        and input_id in self.base_edid_inputs
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
                valid, response = self.do_request(
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

                valid, response = self.do_request(
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

                default_edid = self.get_effective_edid(test, input_id)

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
                valid, response = self.do_request(
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

                valid, response = self.do_request(
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
                if response.content == default_edid:
                    print("Grain rate constraint are not changing effective EDID")

                valid, response = self.do_request(
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
                valid, response = self.do_request(
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
                    valid, response = self.do_request(
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

                valid, response = self.do_request(
                    "GET",
                    self.compat_url + "senders/" + sender_id + "/status/"
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
                    return test.UNCLEAR("This device can not constraint sample_rate")

                if state in ["awaiting_essence", "no_essence"]:
                    for i in range(0, CONFIG.STABLE_STATE_ATTEMPTS):
                        valid, response = self.do_request(
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

                valid, response = self.do_request(
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
                valid, response = self.do_request(
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
                valid, response = self.do_request(
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
            valid, response = self.do_request(
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
            valid, response = self.do_request(
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
                    valid, response = self.do_request(
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
    def test_03_00(self, test):
        """Connected Outputs with EDID support return the EDID"""
        if len(self.edid_connected_outputs) == 0:
            return test.UNCLEAR("Not tested. No connected Outputs with EDID support found.")

        for id in self.is11_utils.sampled_list(self.edid_connected_outputs):
            self.get_outputs_edid(test, id)

        return test.PASS()

    def test_03_01(self, test):
        """
        Disconnected Outputs with EDID support and Outputs without EDID support return the EDID
        """
        target_outputs = self.non_edid_outputs + self.edid_disconnected_outputs

        if len(target_outputs) == 0:
            return test.UNCLEAR("Not tested. No disconnected Outputs with EDID support "
                                "and Outputs without EDID support found.")

        for id in self.is11_utils.sampled_list(target_outputs):
            valid, response = self.do_request("GET", self.compat_url + "outputs/" + id + "/edid")
            if not valid or response.status_code != 204:
                return test.FAIL("Unexpected response "
                                 "for GET /edid: {}".format(response))

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
            valid, response = self.do_request(
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
            valid, response = self.do_request(
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
            valid, response = self.do_request(
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
            if (activated_receivers < len(self.receivers_with_outputs)):
                return test.WARNING("There are no compatible senders for {} receivers"
                                    .format(len(self.receivers_with_outputs) - activated_receivers))
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
            valid, response = self.do_request('GET', self.compat_url + "outputs/" + output_id + "/properties/")
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
                    valid, response = self.do_request('GET', self.build_output_properties_url(output_id))
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
            if (activated_receivers < len(self.receivers_with_outputs)):
                return test.WARNING("There are no compatible senders for {} receivers"
                                    .format(len(self.receivers_with_outputs) - activated_receivers))
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
            valid, response = self.do_request('GET', self.compat_url + "outputs/" + output_id + "/properties/")
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
                    valid, response = self.do_request('GET', self.build_output_properties_url(output_id))
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
            if (activated_receivers < len(self.receivers_without_outputs)):
                return test.WARNING("There are no compatible senders for {} receivers"
                                    .format(len(self.receivers_without_outputs) - activated_receivers))
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
            if (activated_receivers < len(self.receivers_without_outputs)):
                return test.WARNING("There are no compatible senders for {} receivers"
                                    .format(len(self.receivers_without_outputs) - activated_receivers))
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

    def deactivate_connection_resources(self, port):
        url = self.conn_url + "single/" + port + "s/"
        valid, response = self.do_request("GET", url)
        if not valid:
            raise NMOSInitException("Unexpected response from the Connection API: {}".format(response))
        if response.status_code != 200:
            raise NMOSInitException("The request {} has failed: {}".format(url, response))

        try:
            for myPort in response.json():
                staged_url = url + myPort + "staged/"
                deactivate_json = {
                    "master_enable": False,
                    "activation": {"mode": "activate_immediate"},
                }

                valid_patch, patch_response = self.do_request("PATCH", staged_url, json=deactivate_json)
                if not valid_patch:
                    raise NMOSInitException("Unexpected response from the Connection API: {}".format(patch_response))
                if (
                    patch_response.status_code != 200
                    or patch_response.json()["master_enable"]
                    or patch_response.json()["activation"]["mode"] != "activate_immediate"
                ):
                    raise NMOSInitException("The patch request to {} has failed: {}"
                                            .format(staged_url, patch_response))
        except json.JSONDecodeError:
            raise NMOSInitException("Non-JSON response returned from the Connection API")

    def has_i_o(self, id, type):
        connector = "senders/" if type == "sender" else "receivers/"
        i_o = "/inputs/" if type == "sender" else "/outputs/"
        url = self.compat_url + connector + id + i_o

        valid, r = self.do_request("GET", url)
        if valid and r.status_code == 200:
            return len(r.json()) > 0
        else:
            raise NMOSInitException("The request {} has failed: {}".format(url, r))

    def receiver_has_i_o(self, id):
        return self.has_i_o(id, "receiver")

    def is_input_adjust_to_caps(self, id):
        return self.has_property(id, "input", "adjust_to_caps")

    def has_property(self, id, type, property):
        i_o = "inputs/" if type == "input" else "outputs/"
        url = self.compat_url + i_o + id + "/properties/"

        valid, r = self.do_request("GET", url)
        if valid and r.status_code == 200:
            if property in r.json():
                return True
            else:
                return False
        else:
            raise NMOSInitException("The request {} has failed: {}".format(url, r))

    def has_boolean_property_true(self, id, type, property):
        i_o = "inputs/" if type == "input" else "outputs/"
        url = self.compat_url + i_o + id + "/properties/"

        valid, r = self.do_request("GET", url)
        if valid and r.status_code == 200:
            if r.json()[property]:
                return True
            else:
                return False
        else:
            raise NMOSInitException("The request {} has failed: {}".format(url, r))

    def is_input_connected(self, id):
        return self.has_boolean_property_true(id, "input", "connected")

    def has_input_edid_support(self, id):
        return self.has_boolean_property_true(id, "input", "edid_support")

    def has_input_base_edid_support(self, id):
        return self.has_boolean_property_true(id, "input", "base_edid_support")

    def is_output_connected(self, id):
        return self.has_boolean_property_true(id, "output", "connected")

    def has_output_edid_support(self, id):
        return self.has_boolean_property_true(id, "output", "edid_support")

    def delete_active_constraints(self):
        """
        Reset the active constraints of all the senders such that the base EDID is the effective EDID
        """

        for sender_id in self.senders:
            url = self.compat_url + "senders/" + sender_id + "/constraints/active/"
            valid, response = self.do_request("DELETE", url)

            if not valid:
                raise NMOSInitException("Unexpected response from the Stream Compatibility API: {}".format(response))
            if response.status_code != 200:
                raise NMOSInitException("The request {} has failed: {}".format(url, response))

    def delete_base_edid(self):
        for id in self.base_edid_inputs:
            url = self.compat_url + "inputs/" + id + "/edid/base/"
            valid, response = self.do_request("DELETE", url)

            if not valid:
                raise NMOSInitException("Unexpected response from the Stream Compatibility API: {}".format(response))
            if response.status_code != 204:
                raise NMOSInitException("The request {} has failed: {}".format(url, response))

    def get_inputs_senders(self, test, input_id):
        sender_ids = []

        for sender_id in self.senders:
            url = self.compat_url + "senders/" + sender_id + "/inputs"
            valid, response = self.do_request("GET", url)

            if not valid:
                raise NMOSTestException(
                    test.FAIL("Unexpected response from the Stream Compatibility API: {}".format(response))
                )
            if response.status_code != 200:
                raise NMOSTestException(test.FAIL("The request {} has failed: {}".format(url, response)))
            try:
                response_json = response.json()
                if input_id in response_json:
                    sender_ids.append(sender_id)
            except json.JSONDecodeError:
                raise NMOSTestException(
                    test.FAIL("Non-JSON response returned from the Stream Compatibility Management API")
                )

        return sender_ids

    def get_json(self, test, url):
        valid, response = self.do_request("GET", url)
        if not valid or response.status_code != 200:
            raise NMOSTestException(
                test.FAIL("Unexpected response from {}: {}".format(url, response))
            )
        try:
            return response.json()
        except json.JSONDecodeError:
            raise NMOSTestException(
                test.FAIL("Non-JSON response returned from Node API")
            )

    def get_effective_edid(self, test, input_id):
        valid, response = self.do_request("GET", self.compat_url + "inputs/" + input_id + "/edid/effective")
        if (
            not valid
            or response.status_code != 200
            or response.headers["Content-Type"] != "application/octet-stream"
        ):
            raise NMOSTestException(
                test.FAIL("Unexpected response from "
                          "the Stream Compatibility Management API: {}".format(response))
            )
        return response.content

    def get_outputs_edid(self, test, output_id):
        valid, response = self.do_request("GET", self.compat_url + "outputs/" + output_id + "/edid")
        if (
            not valid
            or response.status_code != 200
            or response.headers["Content-Type"] != "application/octet-stream"
        ):
            raise NMOSTestException(
                test.FAIL("Unexpected response from "
                          "the Stream Compatibility Management API: {}".format(response))
            )
        return response.content

    def wait_until_true(self, predicate):
        for i in range(0, CONFIG.STABLE_STATE_ATTEMPTS):
            if predicate():
                return True
            time.sleep(CONFIG.STABLE_STATE_DELAY)
        return False
