# Copyright 2018 British Broadcasting Corporation
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

import json

from TestResult import Test
from GenericTest import GenericTest

NODE_API_KEY = "node"
CONN_API_KEY = "connection"


class IS0502Test(GenericTest):
    """
    Runs Tests covering both IS-04 and IS-05
    """
    def __init__(self, apis):
        # Don't auto-test /transportfile as it is permitted to generate a 404 when master_enable is false
        omit_paths = [
            "/single/senders/{senderId}/transportfile"
        ]
        GenericTest.__init__(self, apis, omit_paths)
        self.node_url = self.apis[NODE_API_KEY]["url"]
        self.connection_url = self.apis[CONN_API_KEY]["url"]
        self.is05_resources = {"senders": [], "receivers": []}
        self.is04_resources = {"senders": [], "receivers": []}

    def get_is04_resources(self, resource_type):
        """Retrieve all Senders or Receivers from a Node API, keeping hold of the returned objects"""
        assert(resource_type in ["senders", "receivers"])

        valid, resources = self.do_request("GET", self.node_url + resource_type)
        if not valid:
            return False, "Node API did not respond as expected: {}".format(resources)

        try:
            for resource in resources.json():
                self.is04_resources[resource_type].append(resource)
        except json.decoder.JSONDecodeError:
            return False, "Non-JSON response returned from Node API"

        return True, ""

    def get_is05_resources(self, resource_type):
        """Retrieve all Senders or Receivers from a Connection API, keeping hold of the returned IDs"""
        assert(resource_type in ["senders", "receivers"])

        valid, resources = self.do_request("GET", self.connection_url + "single/" + resource_type)
        if not valid:
            return False, "Connection API did not respond as expected: {}".format(resources)

        try:
            for resource in resources.json():
                self.is05_resources[resource_type].append(resource.rstrip("/"))
        except json.decoder.JSONDecodeError:
            return False, "Non-JSON response returned from Node API"

        return True, ""

    def get_valid_transports(self):
        """Identify the valid transport types for a given version of IS-05"""
        valid_transports = ["urn:x-nmos:transport:rtp"]
        api = self.apis[CONN_API_KEY]
        if api["major_version"] > 1 or (api["major_version"] == 1 and api["minor_version"] >= 1):
            valid_transports.append("urn:x-nmos:transport:websocket")
            valid_transports.append("urn:x-nmos:transport:mqtt")
        return valid_transports

    def check_is04_in_is05(self, resource_type):
        """Check that each Sender or Receiver found via IS-04 has a matching entry in IS-05"""
        assert(resource_type in ["senders", "receivers"])

        result = True
        for is04_resource in self.is04_resources[resource_type]:
            if is04_resource["transport"] in self.get_valid_transports():
                if is04_resource["id"] not in self.is05_resources[resource_type]:
                    result = False

        return result

    def check_is05_in_is04(self, resource_type):
        """Check that each Sender or Receiver found via IS-05 has a matching entry in IS-04"""
        assert(resource_type in ["senders", "receivers"])

        result = True
        for is05_resource in self.is05_resources[resource_type]:
            is05_res_ok = False
            for is04_resource in self.is04_resources[resource_type]:
                if is04_resource["id"] == is05_resource:
                    is05_res_ok = True
                    break
            result = is05_res_ok
            if not result:
                break

        return result

    def test_01_node_api_1_2_or_greater(self):
        """Check that version 1.2 or greater of the Node API is available"""

        test = Test("Check that version 1.2 or greater of the Node API is available")

        api = self.apis[NODE_API_KEY]
        if api["major_version"] > 1 or (api["major_version"] == 1 and api["minor_version"] >= 2):
            valid, result = self.do_request("GET", self.node_url)
            if valid:
                return test.PASS()
            else:
                return test.FAIL("Node API did not respond as expected: {}".format(result))
        else:
            return test.FAIL("Node API must be running v1.2 or greater")

    def test_02_device_control_present(self):
        """At least one Device is showing an IS-05 control advertisement matching the API under test"""

        test = Test("At least one Device is showing an IS-05 control advertisement matching the API under test")

        valid, devices = self.do_request("GET", self.node_url + "devices")
        if not valid:
            return test.FAIL("Node API did not respond as expected: {}".format(devices))

        is05_devices = []
        try:
            device_type = "urn:x-nmos:control:sr-ctrl/" + self.apis[CONN_API_KEY]["version"]
            for device in devices.json():
                controls = device["controls"]
                for control in controls:
                    if control["type"] == device_type:
                        is05_devices.append(control["href"].rstrip("/"))
        except json.decoder.JSONDecodeError:
            return test.FAIL("Non-JSON response returned from Node API")
        except KeyError:
            return test.FAIL("One or more Devices were missing the 'controls' attribute")

        if len(is05_devices) > 0:
            # TODO: Note that the connection_url includes the port, but the control href may or may not if it uses the
            # default HTTP/HTTPS port.
            return test.PASS()
        else:
            return test.FAIL("Unable to find any Devices which expose the control type '{}'".format(device_type))

    def test_03_is04_is05_rx_match(self):
        """Receivers shown in Connection API matches those shown in Node API"""

        test = Test("Receivers shown in Connection API matches those shown in Node API")

        valid, result = self.get_is04_resources("receivers")
        if not valid:
            return test.FAIL(result)
        valid, result = self.get_is05_resources("receivers")
        if not valid:
            return test.FAIL(result)

        if not self.check_is04_in_is05("receivers"):
            return test.FAIL("Unable to find all Receivers from IS-04 in IS-05")

        if not self.check_is05_in_is04("receivers"):
            return test.FAIL("Unable to find all Receivers from IS-05 in IS-04")

        return test.PASS()

    def test_04_is04_is05_tx_match(self):
        """Senders shown in Connection API matches those shown in Node API"""

        test = Test("Senders shown in Connection API matches those shown in Node API")

        valid, result = self.get_is04_resources("senders")
        if not valid:
            return test.FAIL(result)
        valid, result = self.get_is05_resources("senders")
        if not valid:
            return test.FAIL(result)

        if not self.check_is04_in_is05("senders"):
            return test.FAIL("Unable to find all Senders from IS-04 in IS-05")

        if not self.check_is05_in_is04("senders"):
            return test.FAIL("Unable to find all Senders from IS-05 in IS-04")

        return test.PASS()

    def test_05_rx_activate_updates_ver(self):
        """Activation of a receiver increments the version timestamp"""

        test = Test("Activation of a receiver increments the version timestamp")

        return test.MANUAL()

    def test_06_tx_activate_updates_ver(self):
        """Activation of a sender increments the version timestamp"""

        test = Test("Activation of a sender increments the version timestamp")

        return test.MANUAL()
