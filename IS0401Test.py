
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
import time
import socket
import ramlfications
import os
import git

from zeroconf import ServiceBrowser, ServiceInfo, Zeroconf

SPEC_PATH = 'cache/is-04'

class Specification(object):
    def __init__(self, file_path):
        self.data = {}
        api_raml = ramlfications.parse(file_path, "config.ini")
        for resource in api_raml.resources:
            resource_data = {'method': resource.method,
                             'params': resource.uri_params,
                             'responses': {}}
            for response in resource.responses:
                resource_data[response.code] = None
                if response.body:
                    for entry in response.body:
                        resource_data[response.code] = entry.schema
                        break
            self.data[resource.path] = resource_data

    def get_path(self, path):
        path_parts = path.split('/')
        for resource in self.data:
            resource_parts = resource.split('/')
            for part in path_parts:
                for rpart in resource_parts:
                    if part == rpart:
                        pass
                    elif rpart in resource.uri_params:
                        pass

            path_builder = '/'
            count = 0

            count += 1
            path_builder += part

            if len(path_parts) == count:
                pass

            if resource.startswith(path_builder):
                pass

        # TODO: Exchange {} cases for what's in the path

    def get_reads(self):
        resources = []
        for resource in self.data:
            if resource['method'] in ['get', 'head', 'options']:
                resources.append(resource)
        return resources

    def get_writes(self):
        resources = []
        for resource in self.data:
            if resource['method'] in ['post', 'put', 'patch', 'delete']:
                resources.append(resource)
        return resources


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
    def __init__(self, url, registry):
        repo = git.Repo(SPEC_PATH)
        self.registry = registry
        self.url = url
        self.query_api_url = None
        self.result = list()
        if "/v1.0/" in self.url:
            repo.git.checkout('v1.0.x')
        elif "/v1.1/" in self.url:
            repo.git.checkout('v1.1.x')
        elif "/v1.2/" in self.url:
            repo.git.checkout('v1.2.x')
        self.parse_RAML()

    def run_tests(self):
        self.result.append(self.test_01())
        self.result.append(self.test_new_02())
        self.result.append(self.test_02())
        self.result.append(self.test_03())
        #self.result.append(self.test_04())
        #self.result.append(self.test_05())
        #self.result.append(self.test_06())
        #self.result.append(self.test_07())
        #self.result.append(self.test_08())
        #self.result.append(self.test_09())
        #self.result.append(self.test_10())
        #self.result.append(self.test_11())
        #self.result.append(self.test_12())
        #self.result.append(self.test_13())
        #self.result.append(self.test_14())
        return self.result

# Tests: Schema checks for all resources
# CORS checks for all resources
# Trailing slashes

    def parse_RAML(self):
        self.node_api = Specification(os.path.join(SPEC_PATH + '/APIs/NodeAPI.raml'))
        self.registration_api = Specification(os.path.join(SPEC_PATH + '/APIs/RegistrationAPI.raml'))

        #print(self.node_api.get_path('/self'))

    def prepare_CORS(self, method):
        headers = {}
        headers['Access-Control-Request-Method'] = method # Match to request type
        headers['Access-Control-Request-Headers'] = "Content-Type" # Needed for POST/PATCH etc
        return headers

    def validate_CORS(self, method, response):
        if not 'Access-Control-Allow-Origin' in response.headers:
            return False
        if method in ['POST', 'PUT', 'PATCH', 'DELETE']:
            if not 'Access-Control-Allow-Headers' in response.headers:
                return False
            if not method in response.headers['Access-Control-Allow-Headers']:
                return False
            if not 'Access-Control-Allow-Method' in response.headers:
                return False
            if not method in response.headers['Access-Control-Allow-Methods']:
                return False

# TODO: Scan the Node first for all our its resources. We'll match these to the registrations received.
# Worth checking PTP etc too, and reachability of Node API on all endpoints, plus endpoint matching the one under test
# TODO: Test the Node API first and in isolation to check it all looks generally OK before proceeding with Reg API interactions

    def test_node_read(self):
        for resource in self.node_api.resources:
            if resource.method in ['get', 'head', 'options']:
                for response in resource.responses:
                    if response.code == 200:
                        for entry in response.body:
                            print(entry.schema)
                            print(resource.path)
                            print(resource.uri_params)
        #TODO: For any method we can't test, flag it as a manual test
        # Write a harness for each write method with one or more things to send it. Test them using this as part of this loop
        #TODO: Some basic tests of the Node API itself? Such as presence of arrays at /, /x-nmos, /x-nmos/node etc.
        #TODO: Equally test for each of these if the trailing slash version also works and if redirects are used on either.


    def test_01(self):
        """Node can discover network registration service via mDNS"""
        test_number = "01"
        test_description = "Node can discover network registration service via mDNS"

        self.registry.reset()

        #TODO: Set api_ver to just the version under test. Later test support for parsing CSV string
        txt = {'api_ver': 'v1.0,v1.1,v1.2', 'api_proto': 'http', 'pri': '0'}
        info = ServiceInfo("_nmos-registration._tcp.local.",
                           "NMOS Test Suite._nmos-registration._tcp.local.",
                           socket.inet_aton("127.0.0.1"), 5000, 0, 0,
                           txt, "nmos-test.local.") #TODO: Advertise on the local IP only. May allow config via args

        zeroconf = Zeroconf()
        zeroconf.register_service(info)

        while (time.time() - self.registry.last_time) < 5: # Ensure we allow 5 seconds to get at least one heartbeat
            time.sleep(1)

        zeroconf.unregister_service(info)
        zeroconf.close()

        # TODO Schema check them all registrations etc
        if len(self.registry.get_data()) > 0:
            return test_number, test_description, "Pass", ""

        return test_number, test_description, "Fail", "Node did not attempt to register with the advertised registry."

    def test_new_02(self):
        """Registration API interactions use the correct Content-Type"""
        test_number = "02"
        test_description = "Registration API interactions use the correct Content-Type"

        if len(self.registry.get_data()) == 0:
            return test_number, test_description, "Fail", "No registrations found"

        for resource in self.registry.get_data():
            if "Content-Type" not in resource[1]["headers"]:
                return test_number, test_description, "Fail", "Node failed to signal its Content-Type correctly when registering."
            elif resource[1]["headers"]["Content-Type"] != "application/json":
                return test_number, test_description, "Fail", "Node signalled a Content-Type other than application/json."

        return test_number, test_description, "Pass", ""

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
        test_number = "02"
        test_description = "Node can register a valid Node resource with the network registration service, " \
                           "matching its Node API self resource"
        url = "{}self".format(self.url)
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
                            return test_number, test_description, "Pass", ""
                        else:
                            return test_number, test_description, "Fail", "Node API JSON does not match data in registry."
                    else:
                        return test_number, test_description, "Fail", "No Node registration found in registry."
                except ValueError:
                    return test_number, test_description, "Fail", "Invalid JSON received!"
            else:
                return test_number, test_description, "Fail", "Could not reach Node!"
        except requests.ConnectionError:
            return test_number, test_description, "Fail", "Connection error for {}".format(url)

    def test_03(self):
        """Node maintains itself in the registry via periodic calls to the health resource"""
        test_number = "03"
        test_description = "Node maintains itself in the registry via periodic calls to the health resource"

        if len(self.registry.get_heartbeats()) < 2:
            return test_number, test_description, "Fail", "Not enough heartbeats were made in the time period."

        last_hb = None
        for heartbeat in self.registry.get_heartbeats():
            if last_hb:
                # Check frequency of heartbeats matches the defaults
                time_diff = heartbeat[0] - last_hb[0]
                if time_diff > 5.5:
                    return test_number, test_description, "Fail", "Heartbeats are not frequent enough."
                elif time_diff < 4.5:
                    return test_number, test_description, "Fail", "Heartbeats are too frequent."
            else:
                # For first heartbeat, check against Node registration
                initial_node = self.registry.get_data()[0]
                if (heartbeat[0] - initial_node[0]) > 5.5:
                    return test_number, test_description, "Fail", "First heartbeat occurred too long after initial Node registration."

                # Ensure the Node ID for heartbeats matches the registrations
                if heartbeat[1]["node_id"] != initial_node["id"]:
                    return test_number, test_description, "Fail", "Heartbeats matched a different Node ID to the initial registration."

            # Ensure the heartbeat request body is empty
            if heartbeat[1]["payload"] != None:
                return test_number, test_description, "Fail", "Heartbeat POST contained a payload body."

            last_hb = heartbeat

        return test_number, test_description, "Pass", ""

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
        url = "{}devices/".format(self.url)
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
        url = "{}sources/".format(self.url)
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
        url = "{}flows/".format(self.url)
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
        url = "{}senders/".format(self.url)
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
        url = "{}receivers/".format(self.url)
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
