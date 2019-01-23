# Copyright (C) 2018 Riedel Communications GmbH & Co. KG
#
# Modifications Copyright 2018 British Broadcasting Corporation
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

import requests
import time
import socket
import netifaces
import json

from zeroconf_monkey import ServiceBrowser, ServiceInfo, Zeroconf
from MdnsListener import MdnsListener
from TestResult import Test
from GenericTest import GenericTest
from IS04Utils import IS04Utils
from Config import ENABLE_MDNS, QUERY_API_HOST, QUERY_API_PORT, MDNS_ADVERT_TIMEOUT

NODE_API_KEY = "node"


class IS0401Test(GenericTest):
    """
    Runs IS-04-01-Test
    """
    def __init__(self, apis, registries, node):
        GenericTest.__init__(self, apis)
        self.registries = registries
        self.node = node
        self.node_url = self.apis[NODE_API_KEY]["url"]
        self.registry_basics_done = False
        self.is04_utils = IS04Utils(self.node_url)

    def set_up_tests(self):
        self.zc = Zeroconf()
        self.zc_listener = MdnsListener(self.zc)

    def tear_down_tests(self):
        if self.zc:
            self.zc.close()
            self.zc = None

    def _registry_mdns_info(self, port, priority=0):
        """Get an mDNS ServiceInfo object in order to create an advertisement"""
        default_gw_interface = netifaces.gateways()['default'][netifaces.AF_INET][1]
        default_ip = netifaces.ifaddresses(default_gw_interface)[netifaces.AF_INET][0]['addr']

        # TODO: Add another test which checks support for parsing CSV string in api_ver
        txt = {'api_ver': self.apis[NODE_API_KEY]["version"], 'api_proto': 'http', 'pri': priority}
        info = ServiceInfo("_nmos-registration._tcp.local.",
                           "NMOS Test Suite {}._nmos-registration._tcp.local.".format(port),
                           socket.inet_aton(default_ip), port, 0, 0,
                           txt, "nmos-test.local.")
        return info

    def do_registry_basics_prereqs(self):
        """Advertise a registry and collect data from any Nodes which discover it"""

        if self.registry_basics_done or not ENABLE_MDNS:
            return

        registry_mdns = []
        priority = 0
        for registry in self.registries:
            info = self._registry_mdns_info(registry.get_port(), priority)
            registry_mdns.append(info)
            priority += 10

        registry = self.registries[0]
        self.registries[0].reset()
        self.registries[0].enable()

        # Advertise a registry at pri 0 and allow the Node to do a basic registration
        self.zc.register_service(registry_mdns[0])

        # Wait for n seconds after advertising the service for the first POST from a Node
        time.sleep(MDNS_ADVERT_TIMEOUT)

        # Wait until we're sure the Node has registered everything it intends to, and we've had at least one heartbeat
        while (time.time() - self.registries[0].last_time) < 6:
            time.sleep(1)

        # Ensure we have two heartbeats from the Node, assuming any are arriving (for test_05)
        if len(self.registries[0].get_heartbeats()) > 0:
            # It is heartbeating, but we don't have enough of them yet
            while len(self.registries[0].get_heartbeats()) < 2:
                time.sleep(1)

            # Once registered, advertise all other registries at different (ascending) priorities
            for index, registry in enumerate(self.registries[1:]):
                registry.enable()
                self.zc.register_service(registry_mdns[index + 1])

            # Wait for n seconds after advertising the service for the mDNS advertisements to be noticed
            time.sleep(MDNS_ADVERT_TIMEOUT)

            # Kill registries one by one to collect data around failover
            for registry in self.registries:
                registry.disable()
                time.sleep(6)  # Heartbeat interval plus one

        # Clean up mDNS advertisements and disable registries
        for index, registry in enumerate(self.registries):
            self.zc.unregister_service(registry_mdns[index])
            registry.disable()

        self.registry_basics_done = True

    def test_01(self):
        """Node can discover network registration service via mDNS"""

        test = Test("Node can discover network registration service via mDNS")

        if not ENABLE_MDNS:
            return test.MANUAL("This test cannot be performed when ENABLE_MDNS is False")

        self.do_registry_basics_prereqs()

        registry = self.registries[0]
        if len(registry.get_data()) > 0:
            return test.PASS()

        return test.FAIL("Node did not attempt to register with the advertised registry.")

    def test_02(self):
        """Node can discover network registration service via unicast DNS"""

        # TODO: Provide an option for the user to set up their own unicast DNS server?
        test = Test("Node can discover network registration service via unicast DNS")
        return test.MANUAL()

    def test_03(self):
        """Registration API interactions use the correct Content-Type"""

        test = Test("Registration API interactions use the correct Content-Type")

        if not ENABLE_MDNS:
            return test.MANUAL("This test cannot be performed when ENABLE_MDNS is False")

        self.do_registry_basics_prereqs()

        registry = self.registries[0]
        if len(registry.get_data()) == 0:
            return test.FAIL("No registrations found")

        for resource in registry.get_data():
            if "Content-Type" not in resource[1]["headers"]:
                return test.FAIL("Node failed to signal its Content-Type correctly when registering.")
            elif resource[1]["headers"]["Content-Type"] != "application/json":
                return test.FAIL("Node signalled a Content-Type other than application/json.")

        return test.PASS()

    def check_mdns_pri(self):
        # Set priority to 100
        # Ensure nothing registers
        pass

    def check_mdns_proto(self):
        # Set proto to https
        # Ensure https used, otherwise fail
        pass

    def check_mdns_ver(self):
        # Set ver to something else comma separated?
        pass

    def get_registry_resource(self, res_type, res_id):
        found_resource = None
        if ENABLE_MDNS:
            # Look up data in local mock registry
            registry = self.registries[0]
            for resource in registry.get_data():
                if resource[1]["payload"]["type"] == res_type and resource[1]["payload"]["data"]["id"] == res_id:
                    found_resource = resource[1]["payload"]["data"]
        else:
            # Look up data from a configured Query API
            url = "http://" + QUERY_API_HOST + ":" + str(QUERY_API_PORT) + "/x-nmos/query/" + \
                  self.apis[NODE_API_KEY]["version"] + "/" + res_type + "s/" + res_id
            try:
                r = requests.get(url)
                if r.status_code == 200:
                    found_resource = r.json()
                else:
                    raise Exception
            except Exception:
                print(" * ERROR: Unable to load resource from the configured Query API ({}:{})".format(QUERY_API_HOST,
                                                                                                       QUERY_API_PORT))
        return found_resource

    def get_node_resources(self, resp_json):
        resources = {}
        if isinstance(resp_json, dict):
            resources[resp_json["id"]] = resp_json
        else:
            for resource in resp_json:
                resources[resource["id"]] = resource
        return resources

    def check_matching_resource(self, test, res_type):
        if res_type == "node":
            url = "{}self".format(self.node_url)
        else:
            url = "{}{}s".format(self.node_url, res_type)
        try:
            # Get data from node itself
            r = requests.get(url)
            if r.status_code == 200:
                try:
                    node_resources = self.get_node_resources(r.json())

                    if len(node_resources) == 0:
                        return test.NA("No {} resources were found on the Node.".format(res_type.title()))

                    for res_id in node_resources:
                        reg_resource = self.get_registry_resource(res_type, res_id)
                        if not reg_resource:
                            return test.FAIL("{} {} was not found in the registry.".format(res_type.title(), res_id))
                        elif reg_resource != node_resources[res_id]:
                            return test.FAIL("Node API JSON does not match data in registry for "
                                             "{} {}.".format(res_type.title(), res_id))

                    return test.PASS()
                except ValueError:
                    return test.FAIL("Invalid JSON received!")
            else:
                return test.FAIL("Could not reach Node!")
        except requests.ConnectionError:
            return test.FAIL("Connection error for {}".format(url))

    def test_04(self):
        """Node can register a valid Node resource with the network registration service,
        matching its Node API self resource"""

        test = Test("Node can register a valid Node resource with the network registration service, "
                    "matching its Node API self resource")

        self.do_registry_basics_prereqs()

        return self.check_matching_resource(test, "node")

    def test_05(self):
        """Node maintains itself in the registry via periodic calls to the health resource"""

        test = Test("Node maintains itself in the registry via periodic calls to the health resource")

        if not ENABLE_MDNS:
            return test.MANUAL("This test cannot be performed when ENABLE_MDNS is False")

        self.do_registry_basics_prereqs()

        registry = self.registries[0]
        if len(registry.get_heartbeats()) < 2:
            return test.FAIL("Not enough heartbeats were made in the time period.")

        last_hb = None
        for heartbeat in registry.get_heartbeats():
            if last_hb:
                # Check frequency of heartbeats matches the defaults
                time_diff = heartbeat[0] - last_hb[0]
                if time_diff > 5.5:
                    return test.FAIL("Heartbeats are not frequent enough.")
                elif time_diff < 4.5:
                    return test.FAIL("Heartbeats are too frequent.")
            else:
                # For first heartbeat, check against Node registration
                initial_node = registry.get_data()[0]
                if (heartbeat[0] - initial_node[0]) > 5.5:
                    return test.FAIL("First heartbeat occurred too long after initial Node registration.")

                # Ensure the Node ID for heartbeats matches the registrations
                if heartbeat[1]["node_id"] != initial_node[1]["payload"]["data"]["id"]:
                    return test.FAIL("Heartbeats matched a different Node ID to the initial registration.")

            # Ensure the heartbeat request body is empty
            if heartbeat[1]["payload"] is not None:
                return test.FAIL("Heartbeat POST contained a payload body.")

            last_hb = heartbeat

        return test.PASS()

    def test_06(self):
        """Node correctly handles HTTP 4XX and 5XX codes from the registry,
        re-registering or trying alternative Registration APIs as required"""

        test = Test("Node correctly handles HTTP 4XX and 5XX codes from the registry, "
                    "re-registering or trying alternative Registration APIs as required")
        return test.MANUAL()

    def test_07(self):
        """Node can register a valid Device resource with the network registration service, matching its
        Node API Device resource"""

        test = Test("Node can register a valid Device resource with the network registration service, "
                    "matching its Node API Device resource")

        self.do_registry_basics_prereqs()

        return self.check_matching_resource(test, "device")

    def test_08(self):
        """Node can register a valid Source resource with the network
        registration service, matching its Node API Source resource"""

        test = Test("Node can register a valid Source resource with the network registration service, "
                    "matching its Node API Source resource")

        self.do_registry_basics_prereqs()

        return self.check_matching_resource(test, "source")

    def test_09(self):
        """Node can register a valid Flow resource with the network
        registration service, matching its Node API Flow resource"""

        test = Test("Node can register a valid Flow resource with the network registration service, "
                    "matching its Node API Flow resource")

        self.do_registry_basics_prereqs()

        return self.check_matching_resource(test, "flow")

    def test_10(self):
        """Node can register a valid Sender resource with the network
        registration service, matching its Node API Sender resource"""

        test = Test("Node can register a valid Sender resource with the network registration service, "
                    "matching its Node API Sender resource")

        self.do_registry_basics_prereqs()

        return self.check_matching_resource(test, "sender")

    def test_11(self):
        """Node can register a valid Receiver resource with the network
        registration service, matching its Node API Receiver resource"""

        test = Test("Node can register a valid Receiver resource with the network registration service, "
                    "matching its Node API Receiver resource")

        self.do_registry_basics_prereqs()

        return self.check_matching_resource(test, "receiver")

    def test_12(self):
        """Node advertises a Node type mDNS announcement with no ver_* TXT records
        in the presence of a Registration API"""
        test = Test("Node advertises a Node type mDNS announcement with no ver_* TXT records in the presence "
                    "of a Registration API")
        browser = ServiceBrowser(self.zc, "_nmos-node._tcp.local.", self.zc_listener)
        time.sleep(1)
        node_list = self.zc_listener.get_service_list()
        for node in node_list:
            address = socket.inet_ntoa(node.address)
            port = node.port
            if address in self.node_url and ":{}".format(port) in self.node_url:
                properties = self.convert_bytes(node.properties)
                for prop in properties:
                    if "ver_" in prop:
                        return test.FAIL("Found 'ver_'-txt record while node is registered.")
                return test.PASS()
        return test.FAIL("No matching mdns announcement found for node.")

    def test_13(self):
        """PUTing to a Receiver target resource with a Sender resource payload is accepted
        and connects the Receiver to a stream"""

        test = Test("PUTing to a Receiver target resource with a Sender resource payload " \
                    "is accepted and connects the Receiver to a stream")

        valid, receivers = self.do_request("GET", self.node_url + "receivers")
        if not valid:
            return test.FAIL("Unexpected response from the Node API: {}".format(receivers))

        try:
            formats_tested = []
            for receiver in receivers.json():
                try:
                    stream_type = receiver["format"].split(":")[-1]
                except TypeError:
                    return test.FAIL("Unexpected Receiver format: {}".format(receiver))

                # Test each available receiver format once
                if stream_type in formats_tested:
                    continue

                if stream_type not in ["video", "audio", "data", "mux"]:
                    return test.FAIL("Unexpected Receiver format: {}".format(receiver["format"]))

                request_data = self.node.get_sender(stream_type)
                result, error = self.do_receiver_put(receiver["id"], request_data)
                if not result:
                    return test.FAIL(error)

                # TODO: Define the sleep time globally for all connection tests
                time.sleep(1)

                valid, response = self.do_request("GET", self.node_url + "receivers/" + receiver["id"])
                if not valid:
                    return test.FAIL("Unexpected response from the Node API: {}".format(receiver))

                receiver = response.json()
                if receiver["subscription"]["sender_id"] != request_data["id"]:
                    return test.FAIL("Node API Receiver {} subscription does not reflect the subscribed " \
                                     "Sender ID".format(receiver["id"]))

                api = self.apis[NODE_API_KEY]
                if self.is04_utils.compare_api_version(api["version"], "v1.2") >= 0:
                    if not receiver["subscription"]["active"]:
                        return test.FAIL("Node API Receiver {} subscription does not indicate an active " \
                                         "subscription".format(receiver["id"]))

                formats_tested.append(stream_type)

            if len(formats_tested) > 0:
                return test.PASS()
        except json.decoder.JSONDecodeError:
            return test.FAIL("Non-JSON response returned from Node API")

        return test.NA("Node API does not expose any Receivers")

    def test_14(self):
        """PUTing to a Receiver target resource with an empty JSON object payload is accepted and
        disconnects the Receiver from a stream"""

        test = Test("PUTing to a Receiver target resource with an empty JSON object payload "
                    "is accepted and disconnects the Receiver from a stream")

        valid, receivers = self.do_request("GET", self.node_url + "receivers")
        if not valid:
            return test.FAIL("Unexpected response from the Node API: {}".format(receivers))

        try:
            if len(receivers.json()) > 0:
                receiver = receivers.json()[0]
                result, error = self.do_receiver_put(receiver["id"], {})
                if not result:
                    return test.FAIL(error)

                # TODO: Define the sleep time globally for all connection tests
                time.sleep(1)

                valid, response = self.do_request("GET", self.node_url + "receivers/" + receiver["id"])
                if not valid:
                    return test.FAIL("Unexpected response from the Node API: {}".format(receiver))

                receiver = response.json()
                if receiver["subscription"]["sender_id"] is not None:
                    return test.FAIL("Node API Receiver {} subscription does not reflect the subscribed " \
                                     "Sender ID".format(receiver["id"]))

                api = self.apis[NODE_API_KEY]
                if self.is04_utils.compare_api_version(api["version"], "v1.2") >= 0:
                    if receiver["subscription"]["active"]:
                        return test.FAIL("Node API Receiver {} subscription does not indicate an inactive " \
                                         "subscription".format(receiver["id"]))

                return test.PASS()
        except json.decoder.JSONDecodeError:
            return test.FAIL("Non-JSON response returned from Node API")

        return test.NA("Node API does not expose any Receivers")

    def test_15(self):
        """Node correctly selects a Registration API based on advertised priorities"""

        test = Test("Node correctly selects a Registration API based on advertised priorities")

        if not ENABLE_MDNS:
            return test.MANUAL("This test cannot be performed when ENABLE_MDNS is False")

        self.do_registry_basics_prereqs()

        last_hb = None
        last_registry = None
        for registry in self.registries:
            if len(registry.get_heartbeats()) < 1:
                return test.FAIL("Node never made contact with registry advertised on port {}"
                                 .format(registry.get_port()))

            first_hb_to_registry = registry.get_heartbeats()[0]
            if last_hb:
                if first_hb_to_registry < last_hb:
                    return test.FAIL("Node sent a heartbeat to the registry on port {} before the registry on port {}, "
                                     "despite their priorities requiring the opposite behaviour"
                                     .format(registry.get_port(), last_registry.get_port()))

            last_hb = first_hb_to_registry
            last_registry = registry

        return test.PASS()

    def test_16(self):
        """Node correctly fails over between advertised Registration APIs when one fails"""

        test = Test("Node correctly fails over between advertised Registration APIs when one fails")

        if not ENABLE_MDNS:
            return test.MANUAL("This test cannot be performed when ENABLE_MDNS is False")

        self.do_registry_basics_prereqs()

        for index, registry in enumerate(self.registries):
            if len(registry.get_heartbeats()) < 1:
                return test.FAIL("Node never made contact with registry advertised on port {}"
                                 .format(registry.get_port()))

            if index > 0 and len(registry.get_data()) > 0:
                return test.FAIL("Node re-registered its resources when it failed over to a new registry, when it "
                                 "should only have issued a heartbeat")

        return test.PASS()

    def test_17(self):
        """All Node resources use different UUIDs"""

        test = Test("All Node resources use different UUIDs")

        uuids = set()
        valid, response = self.do_request("GET", self.node_url + "self")
        if not valid:
            return test.FAIL("Unexpected response from the Node API: {}".format(response))
        try:
            uuids.add(response.json()["id"])
        except json.decoder.JSONDecodeError:
            return test.FAIL("Non-JSON response returned from Node API")

        for resource_type in ["devices", "sources", "flows", "senders", "receivers"]:
            valid, response = self.do_request("GET", self.node_url + resource_type)
            if not valid:
                return test.FAIL("Unexpected response from the Node API: {}".format(response))
            try:
                for resource in response.json():
                    if resource["id"] in uuids:
                        return test.FAIL("Duplicate ID '{}' found in Node API '{}' resource".format(resource["id"],
                                                                                                    resource_type))
                    uuids.add(resource["id"])
            except json.decoder.JSONDecodeError:
                return test.FAIL("Non-JSON response returned from Node API")

        return test.PASS()

    def do_receiver_put(self, receiver_id, data):
        """Perform a PUT to the Receiver 'target' resource with the specified data"""

        valid, put_response = self.do_request("PUT", self.node_url + "receivers/" + receiver_id + "/target", data)
        if not valid:
            return False, "Unexpected response from the Node API: {}".format(put_response)

        if put_response.status_code != 202:
            return False, "Receiver target PATCH did not produce a 202 response code: \
                          {}".format(put_response.status_code)
        else:
            return True, ""
