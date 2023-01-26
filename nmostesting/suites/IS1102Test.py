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
from ..IS05Utils import IS05Utils
from ..IS11Utils import IS11Utils

NODE_API_KEY = "node"
COMPAT_API_KEY = "streamcompatibility"
CONN_API_KEY = "connection"


class IS1102Test(GenericTest):
    """
    Runs Node Tests covering both IS-04 and IS-11
    """
    def __init__(self, apis, **kwargs):
        # Don't auto-test paths responding with an EDID binary as they don't have a JSON Schema
        omit_paths = [
            "/inputs/{inputId}/edid/base",
            "/inputs/{inputId}/edid/effective",
            "/outputs/{outputId}/edid"
        ]
        # Don't auto-test /transportfile as it is permitted to generate a 404 when master_enable is false
        omit_paths += [
            "/single/senders/{senderId}/transportfile"
        ]
        GenericTest.__init__(self, apis, omit_paths)
        self.node_url = self.apis[NODE_API_KEY]["url"]
        self.compat_url = self.apis[COMPAT_API_KEY]["url"]
        self.connection_url = self.apis[CONN_API_KEY]["url"]
        self.is05_utils = IS05Utils(self.connection_url)
        self.is11_utils = IS11Utils(self.compat_url)
        self.is04_resources = {"senders": [], "receivers": [], "_requested": [], "sources": [], "flows": []}
        self.is11_resources = {"senders": [], "receivers": [], "_requested": []}

    # TODO: Remove the duplication (IS0502Test)
    def get_is04_resources(self, resource_type):
        """Retrieve all Senders or Receivers from a Node API, keeping hold of the returned objects"""
        assert resource_type in ["senders", "receivers", "sources", "flows"]

        # Prevent this being executed twice in one test run
        if resource_type in self.is04_resources["_requested"]:
            return True, ""

        valid, resources = self.do_request("GET", self.node_url + resource_type)
        if not valid:
            return False, "Node API did not respond as expected: {}".format(resources)

        try:
            for resource in resources.json():
                self.is04_resources[resource_type].append(resource)
            self.is04_resources["_requested"].append(resource_type)
        except json.JSONDecodeError:
            return False, "Non-JSON response returned from Node API"

        return True, ""

    # TODO: Consider making it more generic (IS0502Test)
    def get_is11_resources(self, resource_type):
        """Retrieve all Senders or Receivers from a Stream Compatibility Management API,
        keeping hold of the returned objects"""

        assert resource_type in ["senders", "receivers"]

        # Prevent this being executed twice in one test run
        if resource_type in self.is11_resources["_requested"]:
            return True, ""

        valid, resources = self.do_request("GET", self.compat_url + resource_type)
        if not valid:
            return False, "Stream Compatibility Management API did not respond as expected: {}".format(resources)

        try:
            for resource in resources.json():
                self.is11_resources[resource_type].append(resource.rstrip('/'))
            self.is11_resources["_requested"].append(resource_type)
        except json.JSONDecodeError:
            return False, "Non-JSON response returned from Stream Compatibility Management API"

        return True, ""

    # TODO: Consider making it more generic (IS0502Test)
    def check_is11_in_is04(self, resource_type):
        """Check that each Sender or Receiver found via IS-11 has a matching entry in IS-04"""
        assert resource_type in ["senders", "receivers"]

        result = True
        for is11_resource in self.is11_resources[resource_type]:
            is11_res_ok = False
            for is04_resource in self.is04_resources[resource_type]:
                if is04_resource["id"] == is11_resource:
                    is11_res_ok = True
                    break
            result = is11_res_ok
            if not result:
                break

        return result

    # TODO: Remove the duplication (IS0502Test)
    def test_01(self, test):
        """Check that version 1.2 or greater of the Node API is available"""

        api = self.apis[NODE_API_KEY]
        if self.is05_utils.compare_api_version(api["version"], "v1.2") >= 0:
            valid, result = self.do_request("GET", self.node_url)
            if valid:
                return test.PASS()
            else:
                return test.FAIL("Node API did not respond as expected: {}".format(result))
        else:
            return test.FAIL("Node API must be running v1.2 or greater")

    # TODO: Remove the duplication (IS0502Test)
    def test_02(self, test):
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
                        if self.is05_utils.compare_urls(self.compat_url, control["href"]) and \
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

    # TODO: Consider making it more generic (IS0502Test)
    def test_03(self, test):
        """Receivers shown in Stream Compatibility Management API matches those shown in Node API"""

        valid, result = self.get_is04_resources("receivers")
        if not valid:
            return test.FAIL(result)
        valid, result = self.get_is11_resources("receivers")
        if not valid:
            return test.FAIL(result)

        if not self.check_is11_in_is04("receivers"):
            return test.FAIL("Unable to find all Receivers from IS-11 in IS-04")

        return test.PASS()

    # TODO: Consider making it more generic (IS0502Test)
    def test_04(self, test):
        """Senders shown in Stream Compatibility Management API matches those shown in Node API"""

        valid, result = self.get_is04_resources("senders")
        if not valid:
            return test.FAIL(result)
        valid, result = self.get_is11_resources("senders")
        if not valid:
            return test.FAIL(result)

        if not self.check_is11_in_is04("senders"):
            return test.FAIL("Unable to find all Senders from IS-11 in IS-04")

        return test.PASS()

    def test_05(self, test):
        """
        Immediate activation of a receiver without a transport file switches the state of the receiver to 'unknown'
        """

        valid, result = self.get_is11_resources("receivers")
        if not valid:
            return test.FAIL(result)

        if len(self.is11_resources["receivers"]) > 0:
            receivers_tested = []
            warn = ""
            for receiverId in self.is05_utils.sampled_list(self.is11_resources["receivers"]):
                valid, response = self.do_request("GET", self.node_url + "receivers/" + receiverId)
                if not valid or response.status_code != 200:
                    return test.FAIL("Unexpected response from the Node API: {}".format(response))

                try:
                    receiver = response.json()
                    if not receiver["transport"].startswith("urn:x-nmos:transport:rtp"):
                        continue

                    url = "single/receivers/{}/staged".format(receiverId)
                    data = {"sender_id": None, "transport_file": {"data": None, "type": None}}
                    valid, response = self.is05_utils.checkCleanRequestJSON("PATCH", url, data)
                    if not valid:
                        return test.FAIL("Receiver {} rejected staging of absent SDP file: "
                                         "{}".format(receiverId, response))

                    valid, response = self.is05_utils.check_activation(
                        "receiver", receiverId,
                        self.is05_utils.check_perform_immediate_activation,
                        receiver["transport"], True
                    )
                    if not valid:
                        return test.FAIL(response)

                    receivers_tested.append(receiverId)
                    if response and not warn:
                        warn = response

                    url = "receivers/{}/status".format(receiverId)
                    valid, response = self.is11_utils.checkCleanRequestJSON("GET", url)
                    if not valid:
                        return test.FAIL(response)

                    state = response["state"]
                    if state != "unknown":
                        return test.FAIL("Receiver {} has state: {}. Expected state: "
                                         "{}".format(receiverId, state, "unknown"))

                except json.JSONDecodeError:
                    return test.FAIL("Non-JSON response returned from Node API")
                except KeyError as e:
                    return test.FAIL("Unable to find expected key: {}".format(e))

            if warn:
                return test.WARNING(warn)
            elif len(receivers_tested) > 0:
                return test.PASS()
            else:
                return test.UNCLEAR("Not tested. No RTP receivers found.")
        else:
            return test.UNCLEAR("Not tested. No receivers found.")
