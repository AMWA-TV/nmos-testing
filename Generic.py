
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
import os
import git

from TestHelper import Specification

SPEC_PATH = 'cache/is-04'


class Generic:
    """
    Runs Generic
    Result-format:

    #TestNumber#    #TestDescription#   #Succeeded?#    #Reason#
    """
    def __init__(self, url):
        repo = git.Repo(SPEC_PATH)
        self.url = url
        self.result = list()
        if "/v1.0/" in self.url:
            repo.git.checkout('v1.0.x')
        elif "/v1.1/" in self.url:
            repo.git.checkout('v1.1.x')
        elif "/v1.2/" in self.url:
            repo.git.checkout('v1.2.x')
        self.parse_RAML()

    def run_tests(self):
        self.result.append(self.test_node_read())
        return self.result

# Tests: Schema checks for all resources
# CORS checks for all resources
# Trailing slashes

    def parse_RAML(self):
        self.node_api = Specification(os.path.join(SPEC_PATH + '/APIs/NodeAPI.raml'))

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
        for resource in self.node_api.get_reads():
            for response_code in resource[1]['responses']:
                if response_code == 200:
                    if resource[1]['responses'][response_code]:
                        print(resource[0])
                        print(response_code)
                        print(resource[1]['responses'][response_code])
                        print(resource[1]['params'])
        #TODO: For any method we can't test, flag it as a manual test
        # Write a harness for each write method with one or more things to send it. Test them using this as part of this loop
        #TODO: Some basic tests of the Node API itself? Such as presence of arrays at /, /x-nmos, /x-nmos/node etc.
        #TODO: Equally test for each of these if the trailing slash version also works and if redirects are used on either.
