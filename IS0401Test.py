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
import json
from time import sleep
import socket

from zeroconf import ServiceBrowser, Zeroconf


class MdnsListener(object):
    def __init__(self):
        self.services = list()

    def add_service(self, zeroconf, type, name):
        info = zeroconf.get_service_info(type, name)
		if info is not None:
			self.services.append(info)

    def get_service_list(self):
        return self.services


class IS0401Test:
    """
    Runs IS-04-01-Test
    Result-format:

    #TestNumber#    #TestDescription#   #Succeeded?#    #Reason#
    """
    def __init__(self, url, query_url):
        self.url = url
        self.result = list()
        self.query_api_url_base = query_url
        if "/v1.0/" in self.url:
            self.query_api_url = self.query_api_url_base + "/v1.0/"
        elif "/v1.1/" in self.url:
            self.query_api_url = self.query_api_url_base + "/v1.1/"
        elif "/v1.2/" in self.url:
            self.query_api_url = self.query_api_url_base + "/v1.2/"

    def run_tests(self):
        self.result.append(self.test_01())
        self.result.append(self.test_02())
        self.result.append(self.test_03())
        self.result.append(self.test_04())
        self.result.append(self.test_05())
        self.result.append(self.test_06())
        self.result.append(self.test_07())
        self.result.append(self.test_08())
        self.result.append(self.test_09())
        self.result.append(self.test_10())
        self.result.append(self.test_11())
        self.result.append(self.test_12())
        self.result.append(self.test_13())
        self.result.append(self.test_14())
        return self.result

    def test_01(self):
        """Node can discover network registration service via mDNS"""
        test_number = "01"
        test_description = "Node can discover network registration service via mDNS"
        return test_number, test_description, "Manual", "This test has to be done manually."

    def test_02(self):
        """Node can register a valid Node resource with the network registration service,
        matching its Node API self resource"""
        test_number = "02"
        test_description = "Node can register a valid Node resource with the network registration service, " \
                           "matching its Node API self resource"
        try:
            # Get node data from node itself
            r = requests.get("{}self".format(self.url))

            if r.status_code == 200:
                # Get data from queryserver
                if "id" in r.json():
                    query_data = requests.get("{}nodes/".format(self.query_api_url, r.json()["id"]))
                    if query_data.status_code == 200:
                        return test_number, test_description, "Pass", ""
                    else:
                        return test_number, test_description, "Fail", json.dumps(query_data.json())

                return test_number, test_description, "Fail", "No id in json data found!"
            else:
                return test_number, test_description, "Fail", "Could not reach Node!"
        except requests.ConnectionError:
            return test_number, test_description, "Fail", "Connection error."

    def test_03(self):
        """Node maintains itself in the registry via periodic calls to the health resource"""
        test_number = "03"
        test_description = "Node maintains itself in the registry via periodic calls to the health resource"
        return test_number, test_description, "Manual", "This test has to be done manually."

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
        try:
            r = requests.get("{}devices/".format(self.url))
            returned_devices = r.json()
            if r.status_code == 200 and len(returned_devices) > 0:
                for curr_device in returned_devices:
                    if "id" in curr_device:
                        k = requests.get("{}devices/{}".format(self.query_api_url, curr_device["id"]))
                        if k.status_code == 200:
                            pass
                        else:
                            return test_number, test_description, "Fail", "Device not found on registry: {}"\
                                .format(curr_device["id"])
                return test_number, test_description, "Pass", ""
            else:
                return test_number, test_description, "N/A", "Not tested. No resources found."
        except requests.ConnectionError:
            return test_number, test_description, "Fail", "Connection error."

    def test_06(self):
        """Node can register a valid Source resource with the network
        registration service, matching its Node API Source resource"""
        test_number = "06"
        test_description = "Node can register a valid Source resource with the network " \
                           "registration service, matching its Node API Source resource"
        try:
            r = requests.get("{}sources/".format(self.url))
            returned_sources = r.json()
            if r.status_code == 200 and len(returned_sources) > 0:
                for curr_source in returned_sources:
                    if "id" in curr_source:
                        url = "{}sources/{}".format(self.query_api_url, curr_source["id"])
                        k = requests.get("{}sources/{}".format(self.query_api_url, curr_source["id"]))
                        if k.status_code == 200:
                            pass
                        else:
                            return test_number, test_description, "Fail", "Source not found on registry: {}"\
                                .format(curr_source["id"])
                return test_number, test_description, "Pass", ""
            else:
                return test_number, test_description, "N/A", "Not tested. No resources found."
        except requests.ConnectionError:
            return test_number, test_description, "Fail", "Connection error."

    def test_07(self):
        """Node can register a valid Flow resource with the network
        registration service, matching its Node API Flow resource"""
        test_number = "07"
        test_description = "Node can register a valid Flow resource with the network " \
                           "registration service, matching its Node API Flow resource"
        try:
            r = requests.get("{}flows/".format(self.url))
            returned_flows = r.json()
            if r.status_code == 200 and len(returned_flows) > 0:
                for curr_flow in returned_flows:
                    if "id" in curr_flow:
                        url = "{}flows/{}".format(self.query_api_url, curr_flow["id"])
                        k = requests.get("{}flows/{}".format(self.query_api_url, curr_flow["id"]))
                        if k.status_code == 200:
                            pass
                        else:
                            return test_number, test_description, "Fail", "Flow not found on registry: {}"\
                                .format(curr_flow["id"])
                return test_number, test_description, "Pass", ""
            else:
                return test_number, test_description, "N/A", "Not tested. No resources found."
        except requests.ConnectionError:
            return test_number, test_description, "Fail", "Connection error."

    def test_08(self):
        """Node can register a valid Sender resource with the network
        registration service, matching its Node API Sender resource"""
        test_number = "08"
        test_description = "Node can register a valid Sender resource with the network " \
                           "registration service, matching its Node API Sender resource"
        try:
            r = requests.get("{}senders/".format(self.url))
            returned_senders = r.json()
            if r.status_code == 200 and len(returned_senders) > 0:
                for curr_sender in returned_senders:
                    if "id" in curr_sender:
                        url = "{}senders/{}".format(self.query_api_url, curr_sender["id"])
                        k = requests.get("{}senders/{}".format(self.query_api_url, curr_sender["id"]))
                        if k.status_code == 200:
                            pass
                        else:
                            return test_number, test_description, "Fail", "Sender not found on registry: {}" \
                                .format(curr_sender["id"])
                return test_number, test_description, "Pass", ""
            else:
                return test_number, test_description, "N/A", "Not tested. No resources found."
        except requests.ConnectionError:
            return test_number, test_description, "Fail", "Connection error."

    def test_09(self):
        """Node can register a valid Receiver resource with the network
        registration service, matching its Node API Receiver resource"""
        test_number = "09"
        test_description = "Node can register a valid Receiver resource with the network " \
                           "registration service, matching its Node API Receiver resource"
        try:
            r = requests.get("{}receivers/".format(self.url))
            returned_receivers = r.json()
            if r.status_code == 200 and len(returned_receivers) > 0:
                for curr_receiver in returned_receivers:
                    if "id" in curr_receiver:
                        url = "{}receivers/{}".format(self.query_api_url, curr_receiver["id"])
                        k = requests.get("{}receivers/{}".format(self.query_api_url, curr_receiver["id"]))
                        if k.status_code == 200:
                            pass
                        else:
                            return test_number, test_description, "Fail", "Receiver not found on registry: {}" \
                                .format(curr_receiver["id"])
                return test_number, test_description, "Pass", ""
            else:
                return test_number, test_description, "N/A", "Not tested. No resources found."
        except requests.ConnectionError:
            return test_number, test_description, "Fail", "Connection error."

    def test_10(self):
        """Node advertises a Node type mDNS announcement with no ver_* TXT records
        in the presence of a Registration API"""
        test_number = "10"
        test_description = "Node advertises a Node type mDNS announcement with no ver_* TXT records in the presence " \
                           "of a Registration API"
        zeroconf = Zeroconf()
        listener = MdnsListener()
        browser = ServiceBrowser(zeroconf, "_nmos-node._tcp.local.", listener)
        sleep(1)
        zeroconf.close()
        node_list = listener.get_service_list()
        for node in node_list:
            address = socket.inet_ntoa(node.address)
            port = node.port
            if address in self.url and ":{}".format(port) in self.url:
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


