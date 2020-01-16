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
from requests.compat import json
import git
import jsonschema
import traceback
import inspect
import uuid

from . import TestHelper
from .Specification import Specification
from .TestResult import Test
from . import Config as CONFIG


NMOS_WIKI_URL = "https://github.com/AMWA-TV/nmos/wiki"


def test_depends(func):
    """Decorator to prevent a test being executed in individual mode"""
    def invalid(self, test):
        if self.test_individual:
            test.description = "Invalid"
            return test.DISABLED("This test cannot be performed individually")
        else:
            return func(self, test)
    invalid.__name__ = func.__name__
    invalid.__doc__ = func.__doc__
    return invalid


class NMOSTestException(Exception):
    """Provides a way to exit a single test, by providing the TestResult return statement as the first exception
       parameter"""
    pass


class NMOSInitException(Exception):
    """The test set was run in an invalid mode. Causes all tests to abort"""
    pass


class GenericTest(object):
    """
    Generic testing class.
    Can be inherited from in order to perform detailed testing.
    """
    def __init__(self, apis, omit_paths=None, disable_auto=False):
        self.apis = apis
        self.saved_entities = {}
        self.auto_test_count = 0
        self.test_individual = False
        self.result = list()
        self.protocol = "http"
        self.ws_protocol = "ws"
        if CONFIG.ENABLE_HTTPS:
            self.protocol = "https"
            self.ws_protocol = "wss"

        self.omit_paths = []
        if isinstance(omit_paths, list):
            self.omit_paths = omit_paths
        self.disable_auto = disable_auto

        test = Test("Test initialisation")

        for api_name, api_data in self.apis.items():
            if "spec_path" not in api_data or api_data["version"] is None:
                continue

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

            api_data["spec_branch"] = spec_branch

            repo.git.reset('--hard')
            repo.git.checkout(spec_branch)
            repo.git.rebase("origin/" + spec_branch)

        self.parse_RAML()

        self.result.append(test.NA(""))

    def parse_RAML(self):
        """Create a Specification object for each API defined in this object"""
        for api in self.apis:
            if "spec_path" not in self.apis[api]:
                continue
            raml_path = os.path.join(self.apis[api]["spec_path"] + '/APIs/' + self.apis[api]["raml"])
            self.apis[api]["spec"] = Specification(raml_path)

    def execute_tests(self, test_names):
        """Perform tests defined within this class"""

        for test_name in test_names:
            self.execute_test(test_name)

    def execute_test(self, test_name):
        """Perform a test defined within this class"""
        self.test_individual = (test_name != "all")

        # Run automatically defined tests
        if test_name in ["auto", "all"] and not self.disable_auto:
            print(" * Running basic API tests")
            self.result += self.basics()

        # Run manually defined tests
        if test_name == "all":
            for method_name in dir(self):
                if method_name.startswith("test_"):
                    method = getattr(self, method_name)
                    if callable(method):
                        print(" * Running " + method_name)
                        test = Test(inspect.getdoc(method), method_name)
                        try:
                            self.result.append(method(test))
                        except NMOSTestException as e:
                            self.result.append(e.args[0])
                        except Exception as e:
                            self.result.append(self.uncaught_exception(method_name, e))

        # Run a single test
        if test_name != "auto" and test_name != "all":
            method = getattr(self, test_name)
            if callable(method):
                print(" * Running " + test_name)
                test = Test(inspect.getdoc(method), test_name)
                try:
                    self.result.append(method(test))
                except NMOSTestException as e:
                    self.result.append(e.args[0])
                except Exception as e:
                    self.result.append(self.uncaught_exception(test_name, e))

    def uncaught_exception(self, test_name, exception):
        """Print a traceback and provide a test FAIL result for uncaught exceptions"""
        traceback.print_exc()
        test = Test("Error executing {}".format(test_name), test_name)
        return test.FAIL("Uncaught exception. Please report the traceback from the terminal to "
                         "https://github.com/amwa-tv/nmos-testing/issues. {}".format(exception))

    def set_up_tests(self):
        """Called before a set of tests is run. Override this method with setup code."""
        pass

    def tear_down_tests(self):
        """Called after a set of tests is run. Override this method with teardown code."""
        pass

    def run_tests(self, test_name=["all"]):
        """Perform tests and return the results as a list"""

        # Set up
        test = Test("Test setup", "set_up_tests")
        for api in self.apis:
            if "spec_path" not in self.apis[api] or self.apis[api]["url"] is None:
                continue
            valid, response = self.do_request("GET", self.apis[api]["url"])
            if not valid or response.status_code != 200:
                raise NMOSInitException("No API found at {}".format(self.apis[api]["url"]))
        self.set_up_tests()
        self.result.append(test.NA(""))

        # Run tests
        self.execute_tests(test_name)

        # Tear down
        test = Test("Test teardown", "tear_down_tests")
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

    # 'check' functions return a Boolean pass/fail indicator and a message
    def check_CORS(self, method, headers, expect_methods=None, expect_headers=None):
        """Check the CORS headers returned by an API call"""
        if 'Access-Control-Allow-Origin' not in headers:
            return False, "'Access-Control-Allow-Origin' not in CORS headers: {}".format(headers)
        if method.upper() == "OPTIONS":
            if 'Access-Control-Allow-Headers' not in headers:
                return False, "'Access-Control-Allow-Headers' not in CORS headers: {}".format(headers)
            if expect_headers is None:
                expect_headers = []
            for cors_header in expect_headers:
                current_headers = [x.strip().upper() for x in headers['Access-Control-Allow-Headers'].split(",")]
                if cors_header.upper() not in current_headers:
                    return False, "'{}' not in 'Access-Control-Allow-Headers' CORS header: {}" \
                                  .format(cors_header, headers)
            if 'Access-Control-Allow-Methods' not in headers:
                return False, "'Access-Control-Allow-Methods' not in CORS headers: {}".format(headers)
            if expect_methods is None:
                expect_methods = []
            for cors_method in expect_methods:
                current_methods = [x.strip().upper() for x in headers['Access-Control-Allow-Methods'].split(",")]
                if cors_method.upper() not in current_methods:
                    return False, "'{}' not in 'Access-Control-Allow-Methods' CORS header: {}" \
                                  .format(cors_method, headers)
        return True, ""

    def check_content_type(self, headers, expected_type="application/json"):
        """Check the Content-Type header of an API request or response"""
        if "Content-Type" not in headers:
            return False, "API failed to signal a Content-Type."
        else:
            ctype = headers["Content-Type"]
            ctype_params = ctype.split(";")
            if ctype_params[0] != expected_type:
                return False, "API signalled a Content-Type of {} rather than {}." \
                              .format(ctype, expected_type)
            elif len(ctype_params) == 2 and ctype_params[1].strip().lower() == "charset=utf-8":
                return True, "API signalled an unnecessary 'charset' in its Content-Type: {}" \
                             .format(ctype)
            elif len(ctype_params) >= 2:
                return False, "API signalled unexpected additional parameters in its Content-Type: {}" \
                              .format(ctype)
        return True, ""

    def check_accept(self, headers):
        """Check the Accept header of an API request"""
        if "Accept" in headers:
            accept_params = headers["Accept"].split(",")
            max_weight = 0
            max_weight_types = []
            for param in accept_params:
                param_parts = param.split(";")
                media_type = param_parts[0].strip()
                weight = 1
                for ext_param in param_parts[1:]:
                    if ext_param.strip().startswith("q="):
                        try:
                            weight = float(ext_param.split("=")[1].strip())
                            break
                        except Exception:
                            pass
                if weight > max_weight:
                    max_weight = weight
                    max_weight_types.clear()
                if weight == max_weight:
                    max_weight_types.append(media_type)
            if "application/json" not in max_weight_types and "*/*" not in max_weight_types:
                return False, "API did not signal a preference for application/json via its Accept header."
            try:
                max_weight_types.remove("application/json")
            except ValueError:
                pass
            try:
                max_weight_types.remove("*/*")
            except ValueError:
                pass
            if len(max_weight_types) > 0:
                return False, "API signalled multiple media types with the same preference as application/json in " \
                              "its Accept header: {}".format(max_weight_types)
        return True, ""

    def auto_test_name(self, api_name):
        """Get the name which should be used for an automatically defined test"""
        self.auto_test_count += 1
        return "auto_{}_{}".format(api_name, self.auto_test_count)

    # 'do_test' functions either return a TestResult, or raise an NMOSTestException when there's an error
    def do_test_base_path(self, api_name, base_url, path, expectation):
        """Check that a GET to a path returns a JSON array containing a defined string"""
        test = Test("GET {}".format(path), self.auto_test_name(api_name))
        valid, response = self.do_request("GET", base_url + path)
        if not valid:
            return test.FAIL("Unable to connect to API: {}".format(response))

        if response.status_code != 200:
            return test.FAIL("Incorrect response code: {}".format(response.status_code))
        else:
            cors_valid, cors_message = self.check_CORS('GET', response.headers)
            if not cors_valid:
                return test.FAIL(cors_message)
            try:
                if not isinstance(response.json(), list) or expectation not in response.json():
                    return test.FAIL("Response is not an array containing '{}'".format(expectation))
                else:
                    return test.PASS()
            except json.JSONDecodeError:
                return test.FAIL("Non-JSON response returned")

    def check_response(self, schema, method, response):
        """Confirm that a given Requests response conforms to the expected schema and has any expected headers"""
        ctype_valid, ctype_message = self.check_content_type(response.headers)
        if not ctype_valid:
            return False, ctype_message

        cors_valid, cors_message = self.check_CORS(method, response.headers)
        if not cors_valid:
            return False, cors_message

        try:
            self.validate_schema(response.json(), schema)
        except jsonschema.ValidationError:
            return False, "Response schema validation error"
        except json.JSONDecodeError:
            return False, "Invalid JSON received"

        return True, ctype_message

    def check_error_response(self, method, response, code):
        """Confirm that a given Requests response conforms to the 4xx/5xx error schema and has any expected headers"""
        schema = TestHelper.load_resolved_schema("test_data/core", "error.json", path_prefix=False)
        valid, message = self.check_response(schema, method, response)
        if valid:
            if response.json()["code"] != code:
                return False, "Error JSON 'code' was not set to {}".format(code)
            return True, ""
        else:
            return False, message

    def validate_schema(self, payload, schema):
        """
        Validate the payload under the given schema.
        Raises an exception if the payload (or schema itself) is invalid
        """
        checker = jsonschema.FormatChecker(["ipv4", "ipv6", "uri"])
        jsonschema.validate(payload, schema, format_checker=checker)

    def do_request(self, method, url, **kwargs):
        return TestHelper.do_request(method=method, url=url, **kwargs)

    def basics(self):
        """Perform basic API read requests (GET etc.) relevant to all API definitions"""
        results = []

        for api in sorted(self.apis.keys()):
            if "spec_path" not in self.apis[api]:
                continue

            if self.apis[api]["url"] is None:
                continue

            # Set the auto test count to zero as each test name includes the API type
            self.auto_test_count = 0

            # We don't check the very base of the URL (before x-nmos) as it may be used for other things
            results.append(self.do_test_base_path(api, self.apis[api]["base_url"], "/x-nmos", api + "/"))
            results.append(self.do_test_base_path(api, self.apis[api]["base_url"], "/x-nmos/{}".format(api),
                                                  self.apis[api]["version"] + "/"))

            for resource in self.apis[api]["spec"].get_reads():
                for response_code in resource[1]['responses']:
                    if response_code == 200 and resource[0] not in self.omit_paths:
                        # TODO: Test for each of these if the trailing slash version also works and if redirects are
                        # used on either.
                        result = self.do_test_api_resource(resource, response_code, api)
                        if result is not None:
                            results.append(result)

            # Perform an automatic check for an error condition
            results.append(self.do_test_404_path(api))

        return results

    def do_test_404_path(self, api_name):
        api = self.apis[api_name]
        error_code = 404
        invalid_path = str(uuid.uuid4())
        url = "{}/{}".format(api["url"].rstrip("/"), invalid_path)
        test = Test("GET /x-nmos/{}/{}/{} ({})".format(api_name, api["version"], invalid_path, error_code),
                    self.auto_test_name(api_name))

        valid, response = self.do_request("GET", url)
        if not valid:
            return test.FAIL(response)

        if response.status_code != error_code:
            return test.FAIL("Incorrect response code, expected {}: {}".format(error_code, response.status_code))

        valid, message = self.check_error_response("GET", response, error_code)
        if valid:
            return test.PASS()
        else:
            return test.FAIL(message)

    def do_test_api_resource(self, resource, response_code, api):
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
                                                        url_param), self.auto_test_name(api))
            else:
                # There were no saved entities found, so we can't test this parameterised URL
                test = Test("{} /x-nmos/{}/{}{}".format(resource[1]['method'].upper(),
                                                        api,
                                                        self.apis[api]["version"],
                                                        resource[0].rstrip("/")), self.auto_test_name(api))
                return test.UNCLEAR("No resources found to perform this test")

        # Test general URLs with no parameters
        elif not resource[1]['params']:
            url = "{}{}".format(self.apis[api]["url"].rstrip("/"), resource[0].rstrip("/"))
            test = Test("{} /x-nmos/{}/{}{}".format(resource[1]['method'].upper(),
                                                    api,
                                                    self.apis[api]["version"],
                                                    resource[0].rstrip("/")), self.auto_test_name(api))
        else:
            return None

        valid, response = self.do_request(resource[1]['method'], url)
        if not valid:
            return test.FAIL(response)

        if response.status_code != response_code:
            return test.FAIL("Incorrect response code: {}".format(response.status_code))

        # Gather IDs of sub-resources for testing of parameterised URLs...
        self.save_subresources(resource[0], response)

        # For methods which don't return a payload, just check the CORS headers
        if resource[1]['method'].upper() in ["HEAD", "OPTIONS"]:
            cors_methods = self.apis[api]["spec"].get_methods(resource[0])
            cors_valid, cors_message = self.check_CORS(resource[1]['method'], response.headers, cors_methods)
            if cors_valid:
                # Pass for a plain CORS check
                return test.PASS()
            else:
                # Fail for a plain CORS check
                return test.FAIL(cors_message)

        # For all other methods proceed to check the response against the schema
        schema = self.get_schema(api, resource[1]["method"], resource[0], response.status_code)

        if not schema:
            return test.MANUAL("Test suite unable to locate schema")

        valid, message = self.check_response(schema, resource[1]["method"], response)

        if valid:
            if message:
                return test.WARNING(message)
            else:
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
            elif isinstance(response.json(), dict):
                for key, value in response.json().items():
                    # Cover the audio channel mapping spec case with dictionary keys
                    if isinstance(key, str) and isinstance(value, dict):
                        subresources.append(key)
        except json.JSONDecodeError:
            pass

        if len(subresources) > 0:
            if path not in self.saved_entities:
                self.saved_entities[path] = subresources
            else:
                self.saved_entities[path] += subresources

    def get_schema(self, api_name, method, path, status_code):
        return self.apis[api_name]["spec"].get_schema(method, path, status_code)
