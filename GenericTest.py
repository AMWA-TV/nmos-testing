# Copyright (C) 2018 British Broadcasting Corporation
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

import os
import json
import requests
import git
import jsonschema

from Specification import Specification
from TestResult import Test


def test_depends(func):
    """ Decorator to prevent a test being executed in individual mode"""
    def invalid(self):
        if self.test_individual:
            test = Test("Invalid")
            return test.FAIL("This test cannot be performed individually")
        else:
            return func(self)
    return invalid


class GenericTest(object):
    """
    Generic testing class.
    Can be inhereted from in order to perform detailed testing.
    """
    def __init__(self, apis, omit_paths=None):
        self.apis = apis
        self.file_prefix = "file:///" if os.name == "nt" else "file:"
        self.saved_entities = {}
        self.auto_test_count = 0
        self.test_individual = False
        self.result = list()

        self.omit_paths = []
        if isinstance(omit_paths, list):
            self.omit_paths = omit_paths

        test = Test("Test initialisation")

        for api_name, api_data in self.apis.items():
            self.apis[api_name]["major_version"], self.apis[api_name]["minor_version"] = self._parse_version(
                api_data["version"])

            repo = git.Repo(api_data["spec_path"])

            # List remote branches and check there is a v#.#.x or v#.#-dev
            branches = repo.git.branch('-a')
            spec_branch = None
            branch_names = [api_data["version"] + ".x", api_data["version"] + "-dev"]
            for branch in branch_names:
                if "remotes/origin/" + branch in branches:
                    spec_branch = branch
                    break

            if not spec_branch:
                raise Exception("No branch matching the expected patterns was found in the Git repository")

            repo.git.reset('--hard')
            repo.git.checkout(spec_branch)
            repo.git.rebase("origin/" + spec_branch)

        self.parse_RAML()

        self.result.append(test.NA(""))

    def _parse_version(self, version):
        """Parse a string based API version into its major and minor numbers"""
        version_parts = version.strip("v").split(".")
        return int(version_parts[0]), int(version_parts[1])

    def parse_RAML(self):
        """Create a Specification object for each API defined in this object"""
        for api in self.apis:
            self.apis[api]["spec"] = Specification(os.path.join(self.apis[api]["spec_path"] + '/APIs/' + self.apis[api]["raml"]))

    def execute_tests(self, test_name):
        """Perform all tests defined within this class"""

        # Run automatically defined tests
        if test_name in ["auto", "all"]:
            print(" * Running basic API tests")
            self.result += self.basics()

        # Run manually defined tests
        if test_name == "all":
            for method_name in dir(self):
                if method_name.startswith("test_"):
                    method = getattr(self, method_name)
                    if callable(method):
                        print(" * Running " + method_name)
                        self.result.append(method())

        # Run a single test
        if test_name != "auto" and test_name != "all":
            method = getattr(self, test_name)
            if callable(method):
                print(" * Running " + test_name)
                self.result.append(method())

    def set_up_tests(self):
        """Called before a set of tests is run. Override this method with setup code."""
        pass

    def tear_down_tests(self):
        """Called after a set of tests is run. Override this method with teardown code."""
        pass

    def run_tests(self, test_name="all"):
        """Perform tests and return the results as a list"""
        self.test_individual = (test_name != "all")

        # Set up
        test = Test("Test setup")
        self.set_up_tests()
        self.result.append(test.NA(""))

        # Run tests
        self.execute_tests(test_name)

        # Tear down
        test = Test("Test teardown")
        self.tear_down_tests()
        self.result.append(test.NA(""))

        return self.result

    def convert_bytes(self, data):
        """Convert bytes which may be contained within a dict or tuple into strings"""
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

    def prepare_CORS(self, method):
        """Prepare CORS headers to be used when making any API request"""
        headers = {}
        headers['Access-Control-Request-Method'] = method  # Match to request type
        headers['Access-Control-Request-Headers'] = "Content-Type"  # Needed for POST/PATCH etc only
        return headers

    def validate_CORS(self, method, response):
        """Check the CORS headers returned by an API call"""
        if 'Access-Control-Allow-Origin' not in response.headers:
            return False
        if method == "OPTIONS":
            if 'Access-Control-Allow-Headers' not in response.headers:
                return False
            if 'Access-Control-Allow-Methods' not in response.headers:
                return False
            if method not in response.headers['Access-Control-Allow-Methods']:
                return False
        return True

    def auto_test_name(self):
        """Get the name which should be used for an automatically defined test"""
        self.auto_test_count += 1
        return "auto_" + str(self.auto_test_count)

    def check_base_path(self, base_url, path, expectation):
        """Check that a GET to a path returns a JSON array containing a defined string"""
        test = Test("GET {}".format(path), self.auto_test_name())
        valid, req = self.do_request("GET", base_url + path)
        if not valid:
            return test.FAIL("Unable to connect to API: {}".format(req))

        if req.status_code != 200:
            return test.FAIL("Incorrect response code: {}".format(req.status_code))
        elif not self.validate_CORS('GET', req):
            return test.FAIL("Incorrect CORS headers: {}".format(req.headers))
        else:
            try:
                if not isinstance(req.json(), list) or expectation not in req.json():
                    return test.FAIL("Response is not an array containing '{}'".format(expectation))
                else:
                    return test.PASS()
            except json.decoder.JSONDecodeError:
                return test.FAIL("Non-JSON response returned")

    def check_response(self, api_name, schema, method, response):
        """Confirm that a given Requests response conforms to the expected schema and has any expected headers"""
        if not self.validate_CORS(method, response):
            return False, "Incorrect CORS headers: {}".format(response.headers)

        try:
            resolver = jsonschema.RefResolver(self.file_prefix + os.path.join(self.apis[api_name]["spec_path"] +
                                                                              '/APIs/schemas/'),
                                              schema)
            jsonschema.validate(response.json(), schema, resolver=resolver)
        except jsonschema.ValidationError:
            return False, "Response schema validation error"
        except json.decoder.JSONDecodeError:
            return False, "Invalid JSON received"

        return True, ""

    def do_request(self, method, url, data=None):
        """Perform a basic HTTP request with appropriate error handling"""
        try:
            s = requests.Session()
            req = None
            if data is not None:
                req = requests.Request(method, url, json=data)
            else:
                req = requests.Request(method, url)
            prepped = req.prepare()
            r = s.send(prepped)
            return True, r
        except requests.exceptions.Timeout:
            return False, "Connection timeout"
        except requests.exceptions.TooManyRedirects:
            return False, "Too many redirects"
        except requests.exceptions.ConnectionError as e:
            return False, str(e)
        except requests.exceptions.RequestException as e:
            return False, str(e)

    def basics(self):
        """Perform basic API read requests (GET etc.) relevant to all API definitions"""
        results = []

        for api in self.apis:
            # This test isn't mandatory... Many systems will use the base path for other things
            # results.append(self.check_base_path(self.apis[api]["base_url"], "/", "x-nmos/"))

            results.append(self.check_base_path(self.apis[api]["base_url"], "/x-nmos", api + "/"))
            results.append(self.check_base_path(self.apis[api]["base_url"], "/x-nmos/{}".format(api),
                                                self.apis[api]["version"] + "/"))

            for resource in self.apis[api]["spec"].get_reads():
                for response_code in resource[1]['responses']:
                    if response_code == 200 and resource[0] not in self.omit_paths:
                        # TODO: Test for each of these if the trailing slash version also works and if redirects are
                        # used on either.
                        result = self.check_api_resource(resource, response_code, api)
                        if result is not None:
                            results.append(result)

        return results

    def check_api_resource(self, resource, response_code, api):
        # Test URLs which include a {resourceId} or similar parameter
        if resource[1]['params'] and len(resource[1]['params']) == 1:
            path = resource[0].split("{")[0].rstrip("/")
            if path in self.saved_entities:
                # Pick the first relevant saved entity and construct a test
                entity = self.saved_entities[path][0]
                params = {resource[1]['params'][0].name: entity}
                url_param = resource[0].format(**params)
                url = "{}{}".format(self.apis[api]["url"].rstrip("/"), url_param)
                test = Test("{} /x-nmos/{}/{}{}".format(resource[1]['method'].upper(),
                                                        api,
                                                        self.apis[api]["version"],
                                                        url_param), self.auto_test_name())
            else:
                # There were no saved entities found, so we can't test this parameterised URL
                test = Test("{} /x-nmos/{}/{}{}".format(resource[1]['method'].upper(),
                                                        api,
                                                        self.apis[api]["version"],
                                                        resource[0].rstrip("/")), self.auto_test_name())
                return test.NA("No resources found to perform this test")

        # Test general URLs with no parameters
        elif not resource[1]['params']:
            url = "{}{}".format(self.apis[api]["url"].rstrip("/"), resource[0])
            test = Test("{} /x-nmos/{}/{}{}".format(resource[1]['method'].upper(),
                                                    api,
                                                    self.apis[api]["version"],
                                                    resource[0].rstrip("/")), self.auto_test_name())
        else:
            return None

        status, response = self.do_request(resource[1]['method'], url)
        if not status:
            return test.FAIL(response)

        if response.status_code != response_code:
            return test.FAIL("Incorrect response code: {}".format(response.status_code))

        # Gather IDs of sub-resources for testing of parameterised URLs...
        self.save_subresources(resource[0], response)

        # For methods which don't return a payload, just check the CORS headers
        if resource[1]['method'].upper() in ["HEAD", "OPTIONS"]:
            if self.validate_CORS(resource[1]['method'], response):
                # Pass for a plain CORS check
                return test.PASS()
            else:
                # Fail for a plain CORS check
                return test.FAIL("Incorrect CORS headers: {}".format(response.headers))

        # For all other methods proceed to check the response against the schema
        schema = self.get_schema(api, resource[1]["method"], resource[0], response.status_code)

        if not schema:
            return test.MANUAL("Test suite unable to locate schema")

        valid, message = self.check_response(api, schema, resource[1]["method"], response)

        if valid:
            return test.PASS()
        else:
            return test.FAIL(message)

    def save_subresources(self, path, response):
        """Get IDs contained within an array JSON response such that they can be interrogated individually"""
        subresources = list()
        try:
            if isinstance(response.json(), list):
                for entry in response.json():
                    # In general, lists return fully fledged objects which each have an ID
                    if isinstance(entry, dict) and "id" in entry:
                        subresources.append(entry["id"])
                    # In some cases lists contain strings which indicate the path to each resource
                    elif isinstance(entry, str) and entry.endswith("/"):
                        res_id = entry.rstrip("/")
                        subresources.append(res_id)
        except json.decoder.JSONDecodeError:
            pass

        if len(subresources) > 0:
            if path not in self.saved_entities:
                self.saved_entities[path] = subresources
            else:
                self.saved_entities[path] += subresources

    def load_schema(self, api_name, path):
        """Used to load in schemas"""
        real_path = os.path.join(self.apis[api_name]["spec_path"] + '/APIs/schemas/', path)
        f = open(real_path, "r")
        return json.loads(f.read())

    def get_schema(self, api_name, method, path, status_code):
        return self.apis[api_name]["spec"].get_schema(method, path, status_code)
