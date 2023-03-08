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

COMPAT_API_KEY = "streamcompatibility"
CONTROLS = "controls"
NODE_API_KEY = "node"
CONN_API_KEY = "connection"


class IS1101Test(GenericTest):
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

    # GENERAL TESTS
    def test_01(self, test):
        """Verify that IS-11 is exposed in the Node API as \
        urn:x-nmos:control:stream-compat/v1.0 at url /x-nmos/streamcompatibility/v1.0/
        """
        _, response = TestHelper.do_request(
            "GET", self.node_url + "devices/"
        )
        if response.status_code != 200:
            return test.FAIL("The request has not succeeded.", response)
        controls = response.json()[0][CONTROLS]
        control_href = ""
        if len(controls) > 0:
            for control in controls:
                if control["type"] == "urn:x-nmos:control:stream-compat/" + self.apis[COMPAT_API_KEY]["version"]:
                    control_href = control["href"]
                    break
            if not control_href.endswith(self.compat_url):
                return test.FAIL("IS-11 URL is invalid")
            return test.PASS()
        return test.FAIL("IS-11 API is not available")

    def test_02(self, test):
        "Put all senders into inactive state"
        senders_url = self.conn_url + "single/senders/"
        _, response = TestHelper.do_request("GET", senders_url)
        if response.status_code != 200:
            return test.FAIL("The request has not succeeded.", response.json())
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
                    return test.FAIL("The request has not succeeded.", response.json())
            return test.PASS()
        return test.UNCLEAR("Could not find any senders to test")

    def test_03(self, test):
        "Put all the receivers into inactive state"
        receivers_url = self.conn_url + "single/receivers/"
        _, response = TestHelper.do_request("GET", receivers_url)
        if response.status_code != 200:
            return test.FAIL("The request has not succeeded.", response.json())
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
                    return test.FAIL("The request has not succeeded.", response.json())

            return test.PASS()

        return test.UNCLEAR("Could not find any receivers to test")

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
        return test.FAIL("The request has not succeeded.", response.json())

    def test_03_02(self, test):
        """
        Verify that some of the outputs of the device are connected.
        """
        if len(self.outputs) == 0:
            return test.UNCLEAR("No IS11 outputs")
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
                return test.FAIL("The request has not succeeded.", response.json())
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
                return test.FAIL("The request has not succeeded.", response.json())
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
                return test.FAIL("The request has not succeeded.", response.json())
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
                return test.FAIL("The request has not succeeded.", response.json())
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
        return test.FAIL("The request has not succeeded.", response.json())

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
                return test.FAIL("The request has not succeeded.", response.json())
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
                return test.UNCLEAR("Status code should be 204.")
        return test.PASS()

    # RECEIVERS TESTS
    def test_04_01(self, test):
        """
        Verify that the device supports the concept of IS-11 Receiver.
        """
        _, response = TestHelper.do_request("GET", self.compat_url + "receivers/")

        if response.status_code != 200:
            return test.FAIL("The request has not succeeded.", response.json())
        self.receivers = response.json()
        if len(self.receivers) == 0:
            return test.UNCLEAR("No IS_11 receivers.")
        return test.PASS()

    def test_04_01_01(self, test):
        """
        Verify that IS-11 Receivers exist on the Node API as Receivers.
        """
        if len(self.receivers) == 0:
            return test.UNCLEAR("No IS_11 receivers.")
        for receiver_id in self.receivers:
            _, response = TestHelper.do_request(
                "GET", self.node_url + "receivers/" + receiver_id
            )
            if response.status_code != 200:
                return test.FAIL("The request has not succeeded.", response.json())
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
            return test.FAIL("The request has not succeeded.", response.json())
        self.receivers = response.json()
        if len(self.receivers) == 0:
            return test.UNCLEAR("No IS_11 receivers.")
        return test.PASS()

    def test_04_02_01(self, test):
        """
        Verify that the status is "unknown" or "non_compliant_stream"
        as per our pre-conditions of not being master_enabled.
        """
        if len(self.receivers) == 0:
            return test.UNCLEAR("No IS_11 receivers.")
        for receiver_id in self.receivers:
            _, response = TestHelper.do_request(
                "GET", self.compat_url + "receivers/" + receiver_id + "status/"
            )
            if response.status_code != 200:
                return test.FAIL("The request has not succeeded.", response.json())
            if response.json()["state"] not in ["unknown", "non compliant stream"]:
                return test.FAIL("The state is not unknown or non compliant stream.")
        return test.PASS()

    def test_04_02_02(self, test):
        """
        Verify that the Receiver supports Receiver Capabilities.
        """
        if len(self.receivers) == 0:
            return test.UNCLEAR("No IS_11 receivers.")
        for receiver_id in self.receivers:
            _, response = TestHelper.do_request(
                "GET", self.node_url + "receivers/" + receiver_id
            )
            if response.status_code != 200:
                return test.FAIL("The request has not succeeded.", response.json())
            self.caps = response.json()["caps"]
            if "constraint_sets" not in self.caps:
                return test.UNCLEAR("The receiver does not have constraint_sets in caps.")
            if len(self.caps["constraint_sets"]) == 0:
                return test.UNCLEAR("The receiver does not support BCP-004-01.")
        return test.PASS()
