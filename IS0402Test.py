
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


class IS0402Test:
    """
    Runs IS-04-02-Test
    Result-format:

    #TestNumber#    #TestDescription#   #Succeeded?#    #Reason#
    """
    def __init__(self, reg_url, query_url):
        repo = git.Repo(SPEC_PATH)
        self.reg_url = reg_url
        self.query_url = query_url
        self.result = list()
        if "/v1.0/" in self.reg_url:
            repo.git.checkout('v1.0.x')
            self.major_version = 1
            self.minor_version = 0
        elif "/v1.1/" in self.reg_url:
            repo.git.checkout('v1.1.x')
            self.major_version = 1
            self.minor_version = 1
        elif "/v1.2/" in self.reg_url:
            repo.git.checkout('v1.2.x')
            self.major_version = 1
            self.minor_version = 2
        self.parse_RAML()

    def run_tests(self):
        self.result.append(self.test_01())
        self.result.append(self.test_02())
        return self.result

# Tests: Schema checks for all resources
# CORS checks for all resources
# Trailing slashes

    def parse_RAML(self):
        self.registration_api = Specification(os.path.join(SPEC_PATH + '/APIs/RegistrationAPI.raml'))
        self.query_api = Specification(os.path.join(SPEC_PATH + '/APIs/QueryAPI.raml'))

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
        """Registration API advertises correctly via mDNS"""
        test_number = "01"
        test_description = "Registration API advertises correctly via mDNS"

        zeroconf = Zeroconf()
        listener = MdnsListener()
        browser = ServiceBrowser(zeroconf, "_nmos-registration._tcp.local.", listener)
        sleep(5)
        zeroconf.close()
        serv_list = listener.get_service_list()
        for api in serv_list:
            address = socket.inet_ntoa(api.address)
            port = api.port
            if address in self.reg_url and ":{}".format(port) in self.reg_url:
                properties_raw = api.properties
                if "pri" not in properties_raw:
                    return test_number, test_description, "Fail", "No 'pri' TXT record found in Registration API advertisement."
                if self.major_version > 1 or (self.major_version == 1 and self.minor_version > 0):
                    if "api_ver" not in properties_raw:
                        return test_number, test_description, "Fail", "No 'api_ver' TXT record found in Registration API advertisement."
                    if "api_proto" not in properties_raw:
                        return test_number, test_description, "Fail", "No 'api_proto' TXT record found in Registration API advertisement."
                return test_number, test_description, "Pass", ""
        return test_number, test_description, "Fail", "No matching mDNS announcement found for Registration API."

    def test_02(self):
        """Query API advertises correctly via mDNS"""
        test_number = "02"
        test_description = "Query API advertises correctly via mDNS"

        zeroconf = Zeroconf()
        listener = MdnsListener()
        browser = ServiceBrowser(zeroconf, "_nmos-query._tcp.local.", listener)
        sleep(5)
        zeroconf.close()
        serv_list = listener.get_service_list()
        for api in serv_list:
            address = socket.inet_ntoa(api.address)
            port = api.port
            if address in self.query_url and ":{}".format(port) in self.query_url:
                properties_raw = api.properties
                if "pri" not in properties_raw:
                    return test_number, test_description, "Fail", "No 'pri' TXT record found in Query API advertisement."
                if self.major_version > 1 or (self.major_version == 1 and self.minor_version > 0):
                    if "api_ver" not in properties_raw:
                        return test_number, test_description, "Fail", "No 'api_ver' TXT record found in Query API advertisement."
                    if "api_proto" not in properties_raw:
                        return test_number, test_description, "Fail", "No 'api_proto' TXT record found in Query API advertisement."
                return test_number, test_description, "Pass", ""
        return test_number, test_description, "Fail", "No matching mDNS announcement found for Query API."
