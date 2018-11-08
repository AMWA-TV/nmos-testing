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
from time import sleep
import time
import socket
import netifaces

from zeroconf import ServiceBrowser, ServiceInfo, Zeroconf
from MdnsListener import MdnsListener
from TestResult import Test
from GenericTest import GenericTest

# TODO: Worth checking PTP etc too, and reachability of Node API on all endpoints, plus endpoint matching the one under
#       test


class IS0401Test(GenericTest):
    """
    Runs IS-04-01-Test
    """
    def __init__(self, apis, spec_versions, test_version, spec_path, registry):
        GenericTest.__init__(self, apis, spec_versions, test_version, spec_path)
        self.registry = registry
        self.node_url = self.apis["node"]["url"]
        self.query_api_url = None

    def execute_tests(self):
        self.registry.enable()
        super(IS0401Test, self).execute_tests()
        self.registry.disable()

    def test_01(self):
        """Node can discover network registration service via mDNS"""

        test = Test("Node can discover network registration service via mDNS")

        self.registry.reset()

        default_gw_interface = netifaces.gateways()['default'][netifaces.AF_INET][1]
        default_ip = netifaces.ifaddresses(default_gw_interface)[netifaces.AF_INET][0]['addr']

        # TODO: Set api_ver to just the version under test. Later test support for parsing CSV string
        txt = {'api_ver': self.test_version, 'api_proto': 'http', 'pri': '0'}
        info = ServiceInfo("_nmos-registration._tcp.local.",
                           "NMOS Test Suite._nmos-registration._tcp.local.",
                           socket.inet_aton(default_ip), 5000, 0, 0,
                           txt, "nmos-test.local.")

        zeroconf = Zeroconf()
        zeroconf.register_service(info)

        while (time.time() - self.registry.last_time) < 5:  # Ensure we allow 5 seconds to get at least one heartbeat
            time.sleep(1)

        zeroconf.unregister_service(info)
        zeroconf.close()

        if len(self.registry.get_data()) > 0:
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

        if len(self.registry.get_data()) == 0:
            return test.FAIL("No registrations found")

        for resource in self.registry.get_data():
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

    def get_registry_resources(self, res_type):
        resources = {}
        for resource in self.registry.get_data():
            if resource[1]["payload"]["type"] == res_type:
                resources[resource[1]["payload"]["data"]["id"]] = resource[1]["payload"]["data"]
        return resources

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
                    reg_resources = self.get_registry_resources(res_type)
                    node_resources = self.get_node_resources(r.json())

                    if len(reg_resources) != len(node_resources):
                        return test.FAIL("One or more {} registrations were not found in either "
                                         "the Node or the registry.".format(res_type.title()))

                    if len(node_resources) == 0:
                        return test.NA("No {} resources were found on the Node.".format(res_type.title()))

                    for resource in node_resources:
                        if resource not in reg_resources:
                            test.FAIL("{} {} was not found in the registry.".format(res_type.title(), resource))
                        elif reg_resources[resource] != node_resources[resource]:
                            return test.FAIL("Node API JSON does not match data in registry for "
                                             "{} {}.".format(res_type.title(), resource))

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
        return self.check_matching_resource(test, "node")

    def test_05(self):
        """Node maintains itself in the registry via periodic calls to the health resource"""

        test = Test("Node maintains itself in the registry via periodic calls to the health resource")

        if len(self.registry.get_heartbeats()) < 2:
            return test.FAIL("Not enough heartbeats were made in the time period.")

        last_hb = None
        for heartbeat in self.registry.get_heartbeats():
            if last_hb:
                # Check frequency of heartbeats matches the defaults
                time_diff = heartbeat[0] - last_hb[0]
                if time_diff > 5.5:
                    return test.FAIL("Heartbeats are not frequent enough.")
                elif time_diff < 4.5:
                    return test.FAIL("Heartbeats are too frequent.")
            else:
                # For first heartbeat, check against Node registration
                initial_node = self.registry.get_data()[0]
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
        return self.check_matching_resource(test, "device")

    def test_08(self):
        """Node can register a valid Source resource with the network
        registration service, matching its Node API Source resource"""

        test = Test("Node can register a valid Source resource with the network registration service, "
                    "matching its Node API Source resource")
        return self.check_matching_resource(test, "source")

    def test_09(self):
        """Node can register a valid Flow resource with the network
        registration service, matching its Node API Flow resource"""

        test = Test("Node can register a valid Flow resource with the network registration service, "
                    "matching its Node API Flow resource")
        return self.check_matching_resource(test, "flow")

    def test_10(self):
        """Node can register a valid Sender resource with the network
        registration service, matching its Node API Sender resource"""

        test = Test("Node can register a valid Sender resource with the network registration service, "
                    "matching its Node API Sender resource")
        return self.check_matching_resource(test, "sender")

    def test_11(self):
        """Node can register a valid Receiver resource with the network
        registration service, matching its Node API Receiver resource"""

        test = Test("Node can register a valid Receiver resource with the network registration service, "
                    "matching its Node API Receiver resource")
        return self.check_matching_resource(test, "receiver")

    def test_12(self):
        """Node advertises a Node type mDNS announcement with no ver_* TXT records
        in the presence of a Registration API"""
        test = Test("Node advertises a Node type mDNS announcement with no ver_* TXT records in the presence "
                    "of a Registration API")
        zeroconf = Zeroconf()
        listener = MdnsListener()
        browser = ServiceBrowser(zeroconf, "_nmos-node._tcp.local.", listener)
        sleep(5)
        zeroconf.close()
        node_list = listener.get_service_list()
        for node in node_list:
            address = socket.inet_ntoa(node.address)
            port = node.port
            if address in self.node_url and ":{}".format(port) in self.node_url:
                properties_raw = node.properties
                for prop in properties_raw:
                    if "ver_" in prop.decode('ascii'):
                        return test.FAIL("Found 'ver_'-txt record while node is registered.")
                return test.PASS()
        return test.FAIL("No matching mdns announcement found for node.")

    def test_13(self):
        """PUTing to a Receiver target resource with a Sender resource payload is accepted
        and connects the Receiver to a stream"""

        test = Test("PUTing to a Receiver target resource with a Sender resource payload " \
                    "is accepted and connects the Receiver to a stream")
        return test.MANUAL()

    def test_14(self):
        """Receiver resource (in Node API and registry) is correctly updated to match the subscribed
        Sender ID upon subscription"""

        test = Test("Receiver resource (in Node API and registry) is correctly updated to match "
                    "the subscribed Sender ID upon subscription")
        return test.MANUAL()

    def test_15(self):
        """PUTing to a Receiver target resource with an empty JSON object payload is accepted and
        disconnects the Receiver from a stream"""

        test = Test("PUTing to a Receiver target resource with an empty JSON object payload "
                    "is accepted and disconnects the Receiver from a stream")
        return test.MANUAL()

    def test_16(self):
        """Node correctly selects a Registration API based on advertised priorities"""

        test = Test("Node correctly selects a Registration API based on advertised priorities")
        return test.MANUAL()
