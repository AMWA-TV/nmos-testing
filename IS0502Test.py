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

from requests.compat import json
import time
import uuid

from GenericTest import GenericTest
from IS05Utils import IS05Utils
from Config import API_PROCESSING_TIMEOUT

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
        self.is05_resources = {"senders": [], "receivers": [], "_requested": [], "transport_types": {}}
        self.is04_resources = {"senders": [], "receivers": [], "_requested": []}
        self.is05_utils = IS05Utils(self.connection_url)

    def get_is04_resources(self, resource_type):
        """Retrieve all Senders or Receivers from a Node API, keeping hold of the returned objects"""
        assert(resource_type in ["senders", "receivers"])

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

    def refresh_is04_resources(self, resource_type):
        """Force a re-retrieval of the IS-04 Senders or Receivers, bypassing the cache"""
        if resource_type in self.is04_resources["_requested"]:
            self.is04_resources["_requested"].remove(resource_type)
            self.is04_resources[resource_type] = []

        return self.get_is04_resources(resource_type)

    def get_is05_resources(self, resource_type):
        """Retrieve all Senders or Receivers from a Connection API, keeping hold of the returned IDs"""
        assert(resource_type in ["senders", "receivers"])

        # Prevent this being executed twice in one test run
        if resource_type in self.is05_resources["_requested"]:
            return True, ""

        valid, resources = self.do_request("GET", self.connection_url + "single/" + resource_type)
        if not valid:
            return False, "Connection API did not respond as expected: {}".format(resources)

        try:
            for resource in resources.json():
                resource_id = resource.rstrip("/")
                self.is05_resources[resource_type].append(resource_id)
                if self.is05_utils.compare_api_version(self.apis[CONN_API_KEY]["version"], "v1.1") >= 0:
                    transport_type = self.is05_utils.get_transporttype(resource_id, resource_type.rstrip("s"))
                    self.is05_resources["transport_types"][resource_id] = transport_type
                else:
                    self.is05_resources["transport_types"][resource_id] = "urn:x-nmos:transport:rtp"
            self.is05_resources["_requested"].append(resource_type)
        except json.JSONDecodeError:
            return False, "Non-JSON response returned from Node API"

        return True, ""

    def check_is04_in_is05(self, resource_type):
        """Check that each Sender or Receiver found via IS-04 has a matching entry in IS-05"""
        assert(resource_type in ["senders", "receivers"])

        result = True
        for is04_resource in self.is04_resources[resource_type]:
            valid_transports = self.is05_utils.get_valid_transports(self.apis[CONN_API_KEY]["version"])
            if is04_resource["transport"] in valid_transports:
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

    def activate_check_version(self, resource_type, resource_list):
        try:
            for is05_resource in resource_list:
                if self.is05_resources["transport_types"][is05_resource] == "urn:x-nmos:transport:websocket":
                    continue
                found_04_resource = False
                for is04_resource in self.is04_resources[resource_type]:
                    if is04_resource["id"] == is05_resource:
                        found_04_resource = True
                        current_ver = is04_resource["version"]

                        method = self.is05_utils.check_perform_immediate_activation
                        valid, response = self.is05_utils.check_activation(resource_type.rstrip("s"), is05_resource,
                                                                           method)
                        if not valid:
                            return False, response

                        time.sleep(API_PROCESSING_TIMEOUT)

                        valid, response = self.do_request("GET", self.node_url + resource_type + "/" + is05_resource)
                        if not valid:
                            return False, "Node API did not respond as expected: {}".format(response)

                        new_ver = response.json()["version"]

                        if self.is05_utils.compare_resource_version(new_ver, current_ver) != 1:
                            return False, "IS-04 resource version did not change when {} {} was activated" \
                                          .format(resource_type.rstrip("s").capitalize(), is05_resource)

                if not found_04_resource:
                    return False, "Unable to find an IS-04 resource with ID {}".format(is05_resource)

        except json.JSONDecodeError:
            return False, "Non-JSON response returned from Node API"
        except KeyError:
            return False, "Version attribute was not found in IS-04 resource"

        return True, ""

    def activate_check_parked(self, resource_type, resource_list):
        for is05_resource in resource_list:
            valid, response = self.is05_utils.park_resource(resource_type, is05_resource)
            if not valid:
                return False, response

        time.sleep(API_PROCESSING_TIMEOUT)

        valid, result = self.refresh_is04_resources(resource_type)
        if not valid:
            return False, result

        try:
            api = self.apis[NODE_API_KEY]
            for is05_resource in self.is05_resources[resource_type]:
                found_04_resource = False
                for is04_resource in self.is04_resources[resource_type]:
                    if is04_resource["id"] == is05_resource:
                        found_04_resource = True
                        subscription = is04_resource["subscription"]

                        # Only IS-04 v1.2+ has an 'active' subscription key
                        if self.is05_utils.compare_api_version(api["version"], "v1.2") >= 0:
                            if subscription["active"] is not False:
                                return False, "IS-04 {} {} was not marked as inactive when IS-05 master_enable set to" \
                                              " false".format(resource_type.rstrip("s").capitalize(), is05_resource)

                        id_key = "sender_id"
                        if resource_type == "senders":
                            id_key = "receiver_id"
                        if subscription[id_key] is not None:
                            return False, "IS-04 {} {} still indicates a subscribed '{}' when parked".format(
                                          resource_type.rstrip("s").capitalize(), is05_resource, id_key)

                if not found_04_resource:
                    return False, "Unable to find an IS-04 resource with ID {}".format(is05_resource)

        except KeyError:
            return False, "Subscription attribute was not found in IS-04 resource"

        return True, ""

    def activate_check_subscribed(self, resource_type, resource_list, nmos=True, multicast=True):
        sub_ids = {}
        for is05_resource in resource_list:
            if self.is05_resources["transport_types"][is05_resource] != "urn:x-nmos:transport:rtp":
                continue

            if (resource_type == "receivers" and nmos) or \
               (resource_type == "senders" and nmos and not multicast):
                sub_id = str(uuid.uuid4())
            else:
                sub_id = None
            sub_ids[is05_resource] = sub_id
            valid, response = self.is05_utils.subscribe_resource(resource_type, is05_resource, sub_id, multicast)
            if not valid:
                return False, response

        time.sleep(API_PROCESSING_TIMEOUT)

        valid, result = self.refresh_is04_resources(resource_type)
        if not valid:
            return False, result

        try:
            api = self.apis[NODE_API_KEY]
            for is05_resource in self.is05_resources[resource_type]:
                if self.is05_resources["transport_types"][is05_resource] != "urn:x-nmos:transport:rtp":
                    continue

                found_04_resource = False
                for is04_resource in self.is04_resources[resource_type]:
                    if is04_resource["id"] == is05_resource:
                        found_04_resource = True
                        subscription = is04_resource["subscription"]

                        # Only IS-04 v1.2+ has an 'active' subscription key
                        if self.is05_utils.compare_api_version(api["version"], "v1.2") >= 0:
                            if subscription["active"] is not True:
                                return False, "IS-04 {} {} was not marked as active when IS-05 master_enable set to" \
                                              " true".format(resource_type.rstrip("s").capitalize(), is05_resource)

                        id_key = "sender_id"
                        if resource_type == "senders":
                            id_key = "receiver_id"
                        if subscription[id_key] != sub_ids[is05_resource]:
                            return False, "IS-04 {} {} indicates subscription to '{}' rather than '{}'".format(
                                          resource_type.rstrip("s").capitalize(), is05_resource, subscription[id_key],
                                          sub_ids[is05_resource])

                if not found_04_resource:
                    return False, "Unable to find an IS-04 resource with ID {}".format(is05_resource)

        except KeyError:
            return False, "Subscription attribute was not found in IS-04 resource"

        return True, ""

    def test_01_node_api_1_2_or_greater(self, test):
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

    def test_02_device_control_present(self, test):
        """At least one Device is showing an IS-05 control advertisement matching the API under test"""

        valid, devices = self.do_request("GET", self.node_url + "devices")
        if not valid:
            return test.FAIL("Node API did not respond as expected: {}".format(devices))

        is05_devices = []
        found_api_match = False
        try:
            device_type = "urn:x-nmos:control:sr-ctrl/" + self.apis[CONN_API_KEY]["version"]
            for device in devices.json():
                controls = device["controls"]
                for control in controls:
                    if control["type"] == device_type:
                        is05_devices.append(control["href"])
                        if self.is05_utils.compare_urls(self.connection_url, control["href"]):
                            found_api_match = True
        except json.JSONDecodeError:
            return test.FAIL("Non-JSON response returned from Node API")
        except KeyError:
            return test.FAIL("One or more Devices were missing the 'controls' attribute")

        if len(is05_devices) > 0 and found_api_match:
            return test.PASS()
        elif len(is05_devices) > 0:
            return test.FAIL("Found one or more Device controls, but no href matched the Connection API under test")
        else:
            return test.FAIL("Unable to find any Devices which expose the control type '{}'".format(device_type))

    def test_03_is04_is05_rx_match(self, test):
        """Receivers shown in Connection API matches those shown in Node API"""

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

    def test_04_is04_is05_tx_match(self, test):
        """Senders shown in Connection API matches those shown in Node API"""

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

    def test_05_rx_activate_updates_ver(self, test):
        """Activation of a receiver increments the version timestamp"""

        resource_type = "receivers"

        valid, result = self.refresh_is04_resources(resource_type)
        if not valid:
            return test.FAIL(result)
        valid, result = self.get_is05_resources(resource_type)
        if not valid:
            return test.FAIL(result)

        if len(self.is05_resources[resource_type]) == 0:
            return test.UNCLEAR("Could not find any IS-05 Receivers to test")

        resource_subset = self.is05_utils.sampled_list(self.is05_resources[resource_type])
        valid, response = self.activate_check_version(resource_type, resource_subset)
        if not valid:
            return test.FAIL(response)
        else:
            return test.PASS()

    def test_06_tx_activate_updates_ver(self, test):
        """Activation of a sender increments the version timestamp"""

        resource_type = "senders"

        valid, result = self.refresh_is04_resources(resource_type)
        if not valid:
            return test.FAIL(result)
        valid, result = self.get_is05_resources(resource_type)
        if not valid:
            return test.FAIL(result)

        if len(self.is05_resources[resource_type]) == 0:
            return test.UNCLEAR("Could not find any IS-05 Senders to test")

        resource_subset = self.is05_utils.sampled_list(self.is05_resources[resource_type])
        valid, response = self.activate_check_version(resource_type, resource_subset)
        if not valid:
            return test.FAIL(response)
        else:
            return test.PASS()

    def test_07_rx_nmos_updates_sub(self, test):
        """Activation of a receiver from an NMOS sender updates the IS-04 subscription"""

        resource_type = "receivers"

        valid, result = self.get_is04_resources(resource_type)
        if not valid:
            return test.FAIL(result)
        valid, result = self.get_is05_resources(resource_type)
        if not valid:
            return test.FAIL(result)

        if len(self.is05_resources[resource_type]) == 0:
            return test.UNCLEAR("Could not find any IS-05 Receivers to test")

        resource_subset = self.is05_utils.sampled_list(self.is05_resources[resource_type])
        valid, response = self.activate_check_parked(resource_type, resource_subset)
        if not valid:
            return test.FAIL(response)

        valid, response = self.activate_check_subscribed(resource_type, resource_subset, nmos=True)
        if not valid:
            return test.FAIL(response)
        else:
            return test.PASS()

    def test_08_rx_ext_updates_sub(self, test):
        """Activation of a receiver from a non-NMOS sender updates the IS-04 subscription"""

        resource_type = "receivers"

        valid, result = self.get_is04_resources(resource_type)
        if not valid:
            return test.FAIL(result)
        valid, result = self.get_is05_resources(resource_type)
        if not valid:
            return test.FAIL(result)

        if len(self.is05_resources[resource_type]) == 0:
            return test.UNCLEAR("Could not find any IS-05 Receivers to test")

        resource_subset = self.is05_utils.sampled_list(self.is05_resources[resource_type])
        valid, response = self.activate_check_parked(resource_type, resource_subset)
        if not valid:
            return test.FAIL(response)

        valid, response = self.activate_check_subscribed(resource_type, resource_subset, nmos=False)
        if not valid:
            return test.FAIL(response)
        else:
            return test.PASS()

    def test_09_tx_mcast_updates_sub(self, test):
        """Activation of a sender to a multicast address updates the IS-04 subscription"""

        api = self.apis[NODE_API_KEY]
        if self.is05_utils.compare_api_version(api["version"], "v1.2") < 0:
            return test.NA("IS-04 v1.1 and earlier Senders do not have a subscription object")

        resource_type = "senders"

        valid, result = self.get_is04_resources(resource_type)
        if not valid:
            return test.FAIL(result)
        valid, result = self.get_is05_resources(resource_type)
        if not valid:
            return test.FAIL(result)

        if len(self.is05_resources[resource_type]) == 0:
            return test.UNCLEAR("Could not find any IS-05 Senders to test")

        resource_subset = self.is05_utils.sampled_list(self.is05_resources[resource_type])
        valid, response = self.activate_check_parked(resource_type, resource_subset)
        if not valid:
            return test.FAIL(response)

        valid, response = self.activate_check_subscribed(resource_type, resource_subset, nmos=True)
        if not valid:
            return test.FAIL(response)
        else:
            return test.PASS()

    def test_10_tx_ucast_nmos_updates_sub(self, test):
        """Activation of a sender to a unicast NMOS receiver updates the IS-04 subscription"""

        api = self.apis[NODE_API_KEY]
        if self.is05_utils.compare_api_version(api["version"], "v1.2") < 0:
            return test.NA("IS-04 v1.1 and earlier Senders do not have a subscription object")

        resource_type = "senders"

        valid, result = self.get_is04_resources(resource_type)
        if not valid:
            return test.FAIL(result)
        valid, result = self.get_is05_resources(resource_type)
        if not valid:
            return test.FAIL(result)

        if len(self.is05_resources[resource_type]) == 0:
            return test.UNCLEAR("Could not find any IS-05 Senders to test")

        resource_subset = self.is05_utils.sampled_list(self.is05_resources[resource_type])
        valid, response = self.activate_check_parked(resource_type, resource_subset)
        if not valid:
            return test.FAIL(response)

        valid, response = self.activate_check_subscribed(resource_type, resource_subset, nmos=True)
        if not valid:
            return test.FAIL(response)
        else:
            return test.PASS()

    def test_11_tx_ucast_ext_updates_sub(self, test):
        """Activation of a sender to a unicast non-NMOS receiver updates the IS-04 subscription"""

        api = self.apis[NODE_API_KEY]
        if self.is05_utils.compare_api_version(api["version"], "v1.2") < 0:
            return test.NA("IS-04 v1.1 and earlier Senders do not have a subscription object")

        resource_type = "senders"

        valid, result = self.get_is04_resources(resource_type)
        if not valid:
            return test.FAIL(result)
        valid, result = self.get_is05_resources(resource_type)
        if not valid:
            return test.FAIL(result)

        if len(self.is05_resources[resource_type]) == 0:
            return test.UNCLEAR("Could not find any IS-05 Senders to test")

        resource_subset = self.is05_utils.sampled_list(self.is05_resources[resource_type])
        valid, response = self.activate_check_parked(resource_type, resource_subset)
        if not valid:
            return test.FAIL(response)

        valid, response = self.activate_check_subscribed(resource_type, resource_subset, nmos=False)
        if not valid:
            return test.FAIL(response)
        else:
            return test.PASS()

    def test_12_interface_bindings_length(self, test):
        """IS-04 interface bindings array matches length of IS-05 transport_params array"""

        for resource_type in ["senders", "receivers"]:
            valid, result = self.get_is04_resources(resource_type)
            if not valid:
                return test.FAIL(result)

        try:
            for resource_type in ["senders", "receivers"]:
                for resource in self.is04_resources[resource_type]:
                    valid_transports = self.is05_utils.get_valid_transports(self.apis[CONN_API_KEY]["version"])
                    if resource["transport"] not in valid_transports:
                        continue

                    bindings_length = len(resource["interface_bindings"])
                    valid, result = self.do_request("GET", self.connection_url + "single/" + resource_type + "/" +
                                                    resource["id"] + "/active")
                    if not valid:
                        return test.FAIL("Connection API returned unexpected result \
                                          for {} '{}'".format(resource_type.capitalize(), resource["id"]))

                    trans_params_length = len(result.json()["transport_params"])
                    if trans_params_length != bindings_length:
                        return test.FAIL("Array length mismatch for Sender/Receiver ID '{}'".format(resource["id"]))

        except json.JSONDecodeError:
            return test.FAIL("Non-JSON response returned from Connection API")
        except KeyError as ex:
            return test.FAIL("Expected attribute not found in IS-04 Sender/Receiver \
                              or IS-05 active resource: {}".format(ex))

        return test.PASS()

    def test_13_transport_files_match(self, test):
        """IS-04 manifest_href matches IS-05 transportfile"""

        valid, result = self.get_is04_resources("senders")
        if not valid:
            return test.FAIL(result)

        try:
            for resource in self.is04_resources["senders"]:
                valid_transports = self.is05_utils.get_valid_transports(self.apis[CONN_API_KEY]["version"])
                if resource["transport"] not in valid_transports:
                    continue

                is04_transport_file = None
                is05_transport_file = None
                if resource["manifest_href"] is not None and resource["manifest_href"] != "":
                    valid, result = self.do_request("GET", resource["manifest_href"])
                    if valid and result.status_code != 404:
                        is04_transport_file = result.text

                valid, result = self.do_request("GET", self.connection_url + "single/senders/" +
                                                resource["id"] + "/transportfile")
                if valid and result.status_code != 404:
                    is05_transport_file = result.text

                if is04_transport_file != is05_transport_file:
                    return test.FAIL("Transport file contents for Sender '{}' do not match \
                                     between IS-04 and IS-05".format(resource["id"]))

        except KeyError as ex:
            return test.FAIL("Expected attribute not found in IS-04 Sender: {}".format(ex))

        return test.PASS()
