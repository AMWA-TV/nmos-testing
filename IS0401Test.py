
# Copyright (C) 2018 Riedel Communications GmbH & Co. KG
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

from zeroconf import ServiceBrowser, ServiceInfo, Zeroconf
from TestHelper import MdnsListener, Test
from Generic import GenericTest


class IS0401Test(GenericTest):
    """
    Runs IS-04-01-Test
    """
    def __init__(self, base_url, apis, spec_versions, test_version, spec_path, registry):
        GenericTest.__init__(self, base_url, apis, spec_versions, test_version, spec_path)
        self.registry = registry
        self.node_url = self.apis["node"]["url"]
        self.query_api_url = None

    def execute_tests(self):
        super(IS0401Test, self).execute_tests()
        test_number = len(self.result) + 1
        self.result.append([test_number] + self.test_01())
        test_number += 1
        self.result.append([test_number] + self.test_new_02())
        test_number += 1
        self.result.append([test_number] + self.test_02())
        test_number += 1
        self.result.append([test_number] + self.test_03())
        # self.result.append(self.test_04())
        # self.result.append(self.test_05())
        # self.result.append(self.test_06())
        # self.result.append(self.test_07())
        # self.result.append(self.test_08())
        # self.result.append(self.test_09())
        # self.result.append(self.test_10())
        # self.result.append(self.test_11())
        # self.result.append(self.test_12())
        # self.result.append(self.test_13())
        # self.result.append(self.test_14())
        return self.result

    def test_01(self):
        """Node can discover network registration service via mDNS"""

        test = Test("Node can discover network registration service via mDNS")

        self.registry.reset()

        # TODO: Set api_ver to just the version under test. Later test support for parsing CSV string
        txt = {'api_ver': 'v1.0,v1.1,v1.2', 'api_proto': 'http', 'pri': '0'}
        info = ServiceInfo("_nmos-registration._tcp.local.",
                           "NMOS Test Suite._nmos-registration._tcp.local.",
                           socket.inet_aton("127.0.0.1"), 5000, 0, 0,
                           txt, "nmos-test.local.")  # TODO: Advertise on the local IP only. May allow config via args

        zeroconf = Zeroconf()
        zeroconf.register_service(info)

        while (time.time() - self.registry.last_time) < 5:  # Ensure we allow 5 seconds to get at least one heartbeat
            time.sleep(1)

        zeroconf.unregister_service(info)
        zeroconf.close()

        # TODO Schema check them all registrations etc
        if len(self.registry.get_data()) > 0:
            return test.PASS()

        return test.FAIL("Node did not attempt to register with the advertised registry.")

    def test_new_02(self):
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

    def test_mdns_pri(self):
        # Set priority to 100
        # Ensure nothing registers
        pass

    def test_mdns_proto(self):
        # Set proto to https
        # Ensure https used, otherwise fail
        pass

    def test_mdns_ver(self):
        # Set ver to something else comma separated?
        pass

    def test_02(self):
        """Node can register a valid Node resource with the network registration service,
        matching its Node API self resource"""

        test = Test("Node can register a valid Node resource with the network registration service, "
                    "matching its Node API self resource")

        url = "{}self".format(self.node_url)
        try:
            # Get node data from node itself
            r = requests.get(url)
            if r.status_code == 200:
                try:
                    # Compare to registered resource
                    last_node = None
                    for resource in self.registry.get_data():
                        if resource[1]["payload"]["type"] == "node":
                            last_node = resource[1]["payload"]["data"]

                    if last_node is not None:
                        if last_node == r.json():
                            return test.PASS()
                        else:
                            return test.FAIL("Node API JSON does not match data in registry.")
                    else:
                        return test.FAIL("No Node registration found in registry.")
                except ValueError:
                    return test.FAIL("Invalid JSON received!")
            else:
                return test.FAIL("Could not reach Node!")
        except requests.ConnectionError:
            return test.FAIL("Connection error for {}".format(url))

    def test_03(self):
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
                if heartbeat[1]["node_id"] != initial_node["id"]:
                    return test.FAIL("Heartbeats matched a different Node ID to the initial registration.")

            # Ensure the heartbeat request body is empty
            if heartbeat[1]["payload"] is not None:
                return test.FAIL("Heartbeat POST contained a payload body.")

            last_hb = heartbeat

        return test.PASS()

    def test_04(self):
        """Node correctly handles HTTP 4XX and 5XX codes from the registry,
        re-registering or trying alternative Registration APIs as required"""
        test_number = "04"
        test_description = "Node correctly handles HTTP 4XX and 5XX codes from the registry, " \
                           "re-registering or trying alternative Registration APIs as required"
        return test_number, test_description, "Manual", "This test has to be done manually."

    def test_05(self):
        """Node can register a valid Device resource with the network registration service, matching its
        Node API Device resource"""
        test_number = "05"
        test_description = "Node can register a valid Device resource with the network registration service, " \
                           "matching its Node API Device resource"
        url = "{}devices/".format(self.node_url)
        try:
            r = requests.get(url)
            try:
                returned_devices = r.json()
                if r.status_code == 200 and len(returned_devices) > 0:
                    for curr_device in returned_devices:
                        if "id" in curr_device:
                            url2 = "{}devices/{}".format(self.query_api_url, curr_device["id"])
                            try:
                                k = requests.get(url2)
                                if k.status_code == 200:
                                    pass
                                else:
                                    return test_number, test_description, "Fail", "Device not found on registry: {}"\
                                        .format(curr_device["id"])
                            except requests.ConnectionError:
                                return test_number, test_description, "Fail", "Connection error for {}".format(url2)
                    return test_number, test_description, "Pass", ""
                else:
                    return test_number, test_description, "N/A", "Not tested. No resources found."
            except ValueError:
                return test_number, test_description, "Fail", "Invalid JSON received!"
        except requests.ConnectionError:
            return test_number, test_description, "Fail", "Connection error for {}".format(url)

    def test_06(self):
        """Node can register a valid Source resource with the network
        registration service, matching its Node API Source resource"""
        test_number = "06"
        test_description = "Node can register a valid Source resource with the network " \
                           "registration service, matching its Node API Source resource"
        url = "{}sources/".format(self.node_url)
        try:
            r = requests.get(url)
            try:
                returned_sources = r.json()
                if r.status_code == 200 and len(returned_sources) > 0:
                    for curr_source in returned_sources:
                        if "id" in curr_source:
                            url2 = "{}sources/{}".format(self.query_api_url, curr_source["id"])
                            try:
                                k = requests.get(url2)
                                if k.status_code == 200:
                                    pass
                                else:
                                    return test_number, test_description, "Fail", "Source not found on registry: {}"\
                                        .format(curr_source["id"])
                            except requests.ConnectionError:
                                return test_number, test_description, "Fail", "Connection error for {}".format(url2)
                    return test_number, test_description, "Pass", ""
                else:
                    return test_number, test_description, "N/A", "Not tested. No resources found."
            except ValueError:
                return test_number, test_description, "Fail", "Invalid JSON received!"
        except requests.ConnectionError:
            return test_number, test_description, "Fail", "Connection error for {}".format(url)

    def test_07(self):
        """Node can register a valid Flow resource with the network
        registration service, matching its Node API Flow resource"""
        test_number = "07"
        test_description = "Node can register a valid Flow resource with the network " \
                           "registration service, matching its Node API Flow resource"
        url = "{}flows/".format(self.node_url)
        try:
            r = requests.get(url)
            try:
                returned_flows = r.json()
                if r.status_code == 200 and len(returned_flows) > 0:
                    for curr_flow in returned_flows:
                        if "id" in curr_flow:
                            url2 = "{}flows/{}".format(self.query_api_url, curr_flow["id"])
                            try:
                                k = requests.get("{}flows/{}".format(self.query_api_url, curr_flow["id"]))
                                if k.status_code == 200:
                                    pass
                                else:
                                    return test_number, test_description, "Fail", "Flow not found on registry: {}"\
                                        .format(curr_flow["id"])
                            except requests.ConnectionError:
                                return test_number, test_description, "Fail", "Connection error for {}".format(url2)
                    return test_number, test_description, "Pass", ""
                else:
                    return test_number, test_description, "N/A", "Not tested. No resources found."
            except ValueError:
                return test_number, test_description, "Fail", "Invalid JSON received!"
        except requests.ConnectionError:
            return test_number, test_description, "Fail", "Connection error for {}".format(url)

    def test_08(self):
        """Node can register a valid Sender resource with the network
        registration service, matching its Node API Sender resource"""
        test_number = "08"
        test_description = "Node can register a valid Sender resource with the network " \
                           "registration service, matching its Node API Sender resource"
        url = "{}senders/".format(self.node_url)
        try:
            r = requests.get(url)
            try:
                returned_senders = r.json()
                if r.status_code == 200 and len(returned_senders) > 0:
                    for curr_sender in returned_senders:
                        if "id" in curr_sender:
                            url2 = "{}senders/{}".format(self.query_api_url, curr_sender["id"])
                            try:
                                k = requests.get(url2)
                                if k.status_code == 200:
                                    pass
                                else:
                                    return test_number, test_description, "Fail", "Sender not found on registry: {}" \
                                        .format(curr_sender["id"])
                            except requests.ConnectionError:
                                return test_number, test_description, "Fail", "Connection error for {}".format(url2)
                    return test_number, test_description, "Pass", ""
                else:
                    return test_number, test_description, "N/A", "Not tested. No resources found."
            except ValueError:
                return test_number, test_description, "Fail", "Invalid JSON received!"
        except requests.ConnectionError:
            return test_number, test_description, "Fail", "Connection error for {}".format(url)

    def test_09(self):
        """Node can register a valid Receiver resource with the network
        registration service, matching its Node API Receiver resource"""
        test_number = "09"
        test_description = "Node can register a valid Receiver resource with the network " \
                           "registration service, matching its Node API Receiver resource"
        url = "{}receivers/".format(self.node_url)
        try:
            r = requests.get(url)
            try:
                returned_receivers = r.json()
                if r.status_code == 200 and len(returned_receivers) > 0:
                    for curr_receiver in returned_receivers:
                        if "id" in curr_receiver:
                            url2 = "{}receivers/{}".format(self.query_api_url, curr_receiver["id"])
                            try:
                                k = requests.get(url2)
                                if k.status_code == 200:
                                    pass
                                else:
                                    return test_number, test_description, "Fail", "Receiver not found on registry: {}" \
                                        .format(curr_receiver["id"])
                            except requests.ConnectionError:
                                return test_number, test_description, "Fail", "Connection error for {}".format(url2)
                    return test_number, test_description, "Pass", ""
                else:
                    return test_number, test_description, "N/A", "Not tested. No resources found."
            except ValueError:
                return test_number, test_description, "Fail", "Invalid JSON received!"
        except requests.ConnectionError:
            return test_number, test_description, "Fail", "Connection error for {}".format(url)

    def test_10(self):
        """Node advertises a Node type mDNS announcement with no ver_* TXT records
        in the presence of a Registration API"""
        test_number = "10"
        test_description = "Node advertises a Node type mDNS announcement with no ver_* TXT records in the presence " \
                           "of a Registration API"
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
                        return test_number, test_description, "Fail", "Found 'ver_'-txt record while node " \
                                                                      "is registered."
                return test_number, test_description, "Pass", ""
        return test_number, test_description, "Fail", "No matching mdns announcement found for node."

    def test_11(self):
        """PUTing to a Receiver target resource with a Sender resource payload is accepted
        and connects the Receiver to a stream"""
        test_number = "11"
        test_description = "PUTing to a Receiver target resource with a Sender resource payload " \
                           "is accepted and connects the Receiver to a stream"
        return test_number, test_description, "Manual", "This test has to be done manually."

    def test_12(self):
        """Receiver resource (in Node API and registry) is correctly updated to match the subscribed
        Sender ID upon subscription"""
        test_number = "12"
        test_description = "Receiver resource (in Node API and registry) is correctly updated to match " \
                           "the subscribed Sender ID upon subscription"
        return test_number, test_description, "Manual", "This test has to be done manually."

    def test_13(self):
        """PUTing to a Receiver target resource with an empty JSON object payload is accepted and
        disconnects the Receiver from a stream"""
        test_number = "13"
        test_description = "PUTing to a Receiver target resource with an empty JSON object payload " \
                           "is accepted and disconnects the Receiver from a stream"
        return test_number, test_description, "Manual", "This test has to be done manually."

    def test_14(self):
        """Node correctly selects a Registration API based on advertised priorities"""
        test_number = "14"
        test_description = "Node correctly selects a Registration API based on advertised priorities"
        return test_number, test_description, "Manual", "This test has to be done manually."
