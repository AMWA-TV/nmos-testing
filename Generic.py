
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
import git
import os
import jsonschema

from TestHelper import Test, Specification


class GenericTest(object):
    """
    Generic testing class. Can be used independently or inhereted from in order to perform more detailed testing.
    """
    def __init__(self, base_url, apis, spec_versions, test_version, spec_path):
        self.base_url = base_url
        self.apis = apis
        self.spec_versions = spec_versions
        self.test_version = test_version
        self.spec_path = spec_path

        self.major_version, self.minor_version = self.parse_version(self.test_version)

        repo = git.Repo(self.spec_path)
        self.result = list()

        spec_branch = self.test_version + ".x"
        repo.git.reset('--hard')
        repo.git.checkout(spec_branch)
        self.parse_RAML()

    def parse_version(self, version):
        version_parts = version.strip("v").split(".")
        return int(version_parts[0]), int(version_parts[1])

    def execute_tests(self):
        test_number = len(self.result) + 1
        for result in self.test_basics():
            self.result.append([test_number] + result)
            test_number += 1

    def run_tests(self):
        self.execute_tests()
        return self.result

    def convert_bytes(self, data):
        if isinstance(data, bytes):
            return data.decode('ascii')
        if isinstance(data, dict):
            return dict(map(self.convert_bytes, data.items()))
        if isinstance(data, tuple):
            return map(self.convert_bytes, data)
        return data

# Tests: Schema checks for all resources
# CORS checks for all resources
# Trailing slashes

    def parse_RAML(self):
        for api in self.apis:
            self.apis[api]["spec"] = Specification(os.path.join(self.spec_path + '/APIs/' + self.apis[api]["raml"]))

    def prepare_CORS(self, method):
        headers = {}
        headers['Access-Control-Request-Method'] = method # Match to request type
        headers['Access-Control-Request-Headers'] = "Content-Type" # Needed for POST/PATCH etc
        return headers

    def validate_CORS(self, method, response):
        if 'Access-Control-Allow-Origin' not in response.headers:
            return False
        if method in ['POST', 'PUT', 'PATCH', 'DELETE']:
            if 'Access-Control-Allow-Headers' not in response.headers:
                return False
            if method not in response.headers['Access-Control-Allow-Headers']:
                return False
            if 'Access-Control-Allow-Method' not in response.headers:
                return False
            if method not in response.headers['Access-Control-Allow-Methods']:
                return False
        return True

# TODO: Scan the Node first for all our its resources. We'll match these to the registrations received.
# Worth checking PTP etc too, and reachability of Node API on all endpoints, plus endpoint matching the one under test
# TODO: Test the Node API first and in isolation to check it all looks generally OK before proceeding with Reg API interactions

    def test_basics(self):
        #TODO: Check the /, x-nmos/ and x-nmos/node/ locations too...
        results = []

        for api in self.apis:
            for resource in self.apis[api]["spec"].get_reads():
                for response_code in resource[1]['responses']:
                    #TODO: Handle cases where we have params by checking at least one active ID
                    if response_code == 200 and not resource[1]['params']:
                        url = "{}{}".format(self.apis[api]["url"].rstrip("/"), resource[0])
                        test = Test("{} {}".format(resource[1]['method'].upper(), resource[0]))
                        s = requests.Session()
                        req = requests.Request(resource[1]['method'], url)
                        prepped = s.prepare_request(req)
                        r = s.send(prepped)
                        if r.status_code != response_code:
                            results.append(test.FAIL("Incorrect response code: {}".format(r.status_code)))
                            continue
                        if not self.validate_CORS(resource[1]['method'], r):
                            results.append(test.FAIL("Incorrect CORS headers: {}".format(r.headers)))
                            continue
                        if resource[1]['responses'][response_code]:
                            try:
                                jsonschema.validate(r.json(), resource[1]['responses'][response_code])
                            except jsonschema.ValidationError:
                                results.append(test.FAIL("Response schema validation error"))
                                continue
                        else:
                            results.append(test.FAIL("Test suite unable to locate schema"))
                            continue
                        results.append(test.PASS())
        return results
        #TODO: For any method we can't test, flag it as a manual test
        # Write a harness for each write method with one or more things to send it. Test them using this as part of this loop
        #TODO: Some basic tests of the Node API itself? Such as presence of arrays at /, /x-nmos, /x-nmos/node etc.
        #TODO: Equally test for each of these if the trailing slash version also works and if redirects are used on either.
