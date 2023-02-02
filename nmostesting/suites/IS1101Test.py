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

from ..GenericTest import GenericTest
from ..IS11Utils import IS11Utils

COMPAT_API_KEY = "streamcompatibility"


class IS1101Test(GenericTest):
    """
    Runs Node Tests covering IS-11
    """
    def __init__(self, apis, **kwargs):
        # Don't auto-test paths responding with an EDID binary as they don't have a JSON Schema
        omit_paths = [
            "/inputs/{inputId}/edid/base",
            "/inputs/{inputId}/edid/effective",
            "/outputs/{outputId}/edid"
        ]
        GenericTest.__init__(self, apis, omit_paths)
        self.compat_url = self.apis[COMPAT_API_KEY]["url"]
        self.is11_utils = IS11Utils(self.compat_url)

    def set_up_tests(self):
        self.senders = self.is11_utils.get_senders()
        self.receivers = self.is11_utils.get_receivers()
        self.inputs = self.is11_utils.get_inputs()
        self.outputs = self.is11_utils.get_outputs()

        self.state_no_essence = "no_essence"
        self.state_awaiting_essence = "awaiting_essence"

    def test_01(self, test):
        """A sender rejects Active Constraints with unsupported Parameter Constraint URN(s)"""

        if len(self.senders) == 0:
            return test.UNCLEAR("Not tested. No senders found.")

        senderId = self.senders[0]

        try:
            url = "senders/{}/constraints/active".format(senderId)
            data = {"constraint_sets": [{"urn:x-nmos:cap:not:existing": {"enum": [""]}}]}
            valid, response = self.is11_utils.checkCleanRequestJSON("PUT", url, data, 400)
            if valid:
                return test.PASS()
            else:
                return test.FAIL(response)

        except json.JSONDecodeError:
            return test.FAIL("Non-JSON response returned from Node API")
        except KeyError as e:
            return test.FAIL("Unable to find expected key: {}".format(e))

    def test_02(self, test):
        """
        PUTting an empty 'constraint_sets' array to Active Constraints of a sender switches its state to 'unconstrained'
        """

        if len(self.senders) == 0:
            return test.UNCLEAR("Not tested. No senders found.")

        senderId = self.senders[0]

        try:
            url = "senders/{}/constraints/active".format(senderId)
            data = {"constraint_sets": []}
            valid, response = self.is11_utils.checkCleanRequestJSON("PUT", url, data)
            if not valid:
                return test.FAIL(response)

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
            else:
                return test.PASS()

        except json.JSONDecodeError:
            return test.FAIL("Non-JSON response returned from Node API")
        except KeyError as e:
            return test.FAIL("Unable to find expected key: {}".format(e))

    def test_03(self, test):
        """DELETing Active Constrains of a sender switches its state to 'unconstrained'"""

        if len(self.senders) == 0:
            return test.UNCLEAR("Not tested. No senders found.")

        senderId = self.senders[0]

        try:
            url = "senders/{}/constraints/active".format(senderId)
            valid, response = self.is11_utils.checkCleanRequestJSON("DELETE", url)
            if not valid:
                return test.FAIL(response)

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
            else:
                return test.PASS()

        except json.JSONDecodeError:
            return test.FAIL("Non-JSON response returned from Node API")
        except KeyError as e:
            return test.FAIL("Unable to find expected key: {}".format(e))

    def test_04(self, test):
        """State of a sender complies with its Active Constraints when they are empty"""

        if len(self.senders) == 0:
            return test.UNCLEAR("Not tested. No senders found.")

        senderId = self.senders[0]

        try:
            url = "senders/{}/status".format(senderId)
            valid, response = self.is11_utils.checkCleanRequestJSON("GET", url)
            if not valid:
                return test.FAIL(response)

            state = response["state"]
            state_expected = "unconstrained"
            if state != state_expected:
                return test.UNCLEAR("Sender {} has state: {}. Expected state: "
                                    "{}".format(senderId, state, state_expected))

            url = "senders/{}/constraints/active".format(senderId)
            valid, response = self.is11_utils.checkCleanRequestJSON("GET", url)
            if not valid:
                return test.FAIL(response)

            active_constraints_empty = {"constraint_sets": []}
            if response != active_constraints_empty:
                return test.FAIL("Active Constraints are: {}. Expected empty Active Constraints".format(response))
            else:
                return test.PASS()

        except json.JSONDecodeError:
            return test.FAIL("Non-JSON response returned from Node API")
        except KeyError as e:
            return test.FAIL("Unable to find expected key: {}".format(e))

    def test_05(self, test):
        """
        PUTting a non-empty 'constraint_sets' array to Active Constraints of a sender appropriately switches its state
        """

        if len(self.senders) == 0:
            return test.UNCLEAR("Not tested. No senders found.")

        senderId = self.senders[0]

        try:
            url = "senders/{}/constraints/active".format(senderId)
            data = {"constraint_sets": [{"urn:x-nmos:cap:format:frame_width": {"minimum": 0, "maximum": 65535}}]}
            valid, response = self.is11_utils.checkCleanRequestJSON("PUT", url, data)
            if not valid:
                return test.FAIL(response)

            url = "senders/{}/status".format(senderId)
            valid, response = self.is11_utils.checkCleanRequestJSON("GET", url)
            if not valid:
                return test.FAIL(response)

            state = response["state"]
            if state != "constrained" and state != "active_constraints_violation":
                if state == self.state_awaiting_essence or state == self.state_no_essence:
                    return test.UNCLEAR("Sender {} has state: {}".format(senderId, state))
                else:
                    return test.FAIL("Sender {} has state: {}. Expected state is "
                                     "'active_constraints_violation' or 'constrained'".format(senderId, state))
            else:
                return test.PASS()

        except json.JSONDecodeError:
            return test.FAIL("Non-JSON response returned from Node API")
        except KeyError as e:
            return test.FAIL("Unable to find expected key: {}".format(e))

    def test_06(self, test):
        """State of a sender complies with its Active Constraints when they are non-empty"""

        if len(self.senders) == 0:
            return test.UNCLEAR("Not tested. No senders found.")

        senderId = self.senders[0]

        try:
            url = "senders/{}/status".format(senderId)
            valid, response = self.is11_utils.checkCleanRequestJSON("GET", url)
            if not valid:
                return test.FAIL(response)

            state = response["state"]
            if state != "constrained" and state != "active_constraints_violation":
                return test.UNCLEAR("Sender {} has state: {}. Expected state is "
                                    "'active_constraints_violation' or 'constrained'".format(senderId, state))

            url = "senders/{}/constraints/active".format(senderId)
            valid, response = self.is11_utils.checkCleanRequestJSON("GET", url)
            if not valid:
                return test.FAIL(response)

            active_constraints_empty = {"constraint_sets": []}
            if response == active_constraints_empty:
                return test.FAIL("Active Constraints are empty")
            else:
                return test.PASS()

        except json.JSONDecodeError:
            return test.FAIL("Non-JSON response returned from Node API")
        except KeyError as e:
            return test.FAIL("Unable to find expected key: {}".format(e))

    def test_07(self, test):
        """An input with no EDID support doesn't let to GET its Effective EDID"""

        if len(self.inputs) > 0:
            inputs_tested = []

            for inputId in self.is11_utils.sampled_list(self.inputs):
                valid, response = self.do_request("GET", self.compat_url + "inputs/" + inputId + "/properties")
                if not valid or response.status_code != 200:
                    return test.FAIL("Unexpected response from "
                                     "the Stream Compatibility Management API: {}".format(response))

                try:
                    input = response.json()
                    if input["edid_support"]:
                        continue

                    url = "inputs/{}/edid/effective".format(inputId)
                    valid, response = self.is11_utils.checkCleanRequest("GET", url, code=204)
                    if not valid:
                        return test.FAIL(response)

                    inputs_tested.append(inputId)

                except json.JSONDecodeError:
                    return test.FAIL("Non-JSON response returned from Node API")
                except KeyError as e:
                    return test.FAIL("Unable to find expected key: {}".format(e))

            if len(inputs_tested) > 0:
                return test.PASS()
            else:
                return test.UNCLEAR("Not tested. No inputs with no EDID support found.")
        else:
            return test.UNCLEAR("Not tested. No inputs found.")

    def test_08(self, test):
        """An input with no EDID support doesn't let to modify its Base EDID"""

        if len(self.inputs) > 0:
            inputs_tested = []

            for inputId in self.is11_utils.sampled_list(self.inputs):
                valid, response = self.do_request("GET", self.compat_url + "inputs/" + inputId + "/properties")
                if not valid or response.status_code != 200:
                    return test.FAIL("Unexpected response from "
                                     "the Stream Compatibility Management API: {}".format(response))

                try:
                    input = response.json()
                    if input["edid_support"]:
                        continue

                    url = "inputs/{}/edid/effective".format(inputId)
                    valid, response = self.is11_utils.checkCleanRequestJSON("PUT", url, {}, 405)
                    if not valid:
                        return test.FAIL(response)

                    valid, response = self.is11_utils.checkCleanRequest("DELETE", url, code=405)
                    if not valid:
                        return test.FAIL(response)

                    inputs_tested.append(inputId)

                except json.JSONDecodeError:
                    return test.FAIL("Non-JSON response returned from Node API")
                except KeyError as e:
                    return test.FAIL("Unable to find expected key: {}".format(e))

            if len(inputs_tested) > 0:
                return test.PASS()
            else:
                return test.UNCLEAR("Not tested. No inputs with no EDID support found.")
        else:
            return test.UNCLEAR("Not tested. No inputs found.")

    def test_09(self, test):
        """An output with no EDID support doesn't let to GET its EDID"""

        if len(self.outputs) > 0:
            outputs_tested = []

            for outputId in self.is11_utils.sampled_list(self.outputs):
                valid, response = self.do_request("GET", self.compat_url + "outputs/" + outputId + "/properties")
                if not valid or response.status_code != 200:
                    return test.FAIL("Unexpected response from "
                                     "the Stream Compatibility Management API: {}".format(response))

                try:
                    input = response.json()
                    if input["edid_support"]:
                        continue

                    url = "outputs/{}/edid".format(outputId)
                    valid, response = self.is11_utils.checkCleanRequest("GET", url, code=204)
                    if not valid:
                        return test.FAIL(response)

                    outputs_tested.append(outputId)

                except json.JSONDecodeError:
                    return test.FAIL("Non-JSON response returned from Node API")
                except KeyError as e:
                    return test.FAIL("Unable to find expected key: {}".format(e))

            if len(outputs_tested) > 0:
                return test.PASS()
            else:
                return test.UNCLEAR("Not tested. No outputs with no EDID support found.")
        else:
            return test.UNCLEAR("Not tested. No outputs found.")
