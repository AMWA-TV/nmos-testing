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

import os
import json
import requests
import git
import ramlfications
import jsonschema

# TODO: Consider whether to set Accept headers? If we don't set them we expect APIs to default to application/json
# unless told otherwise. Is this part of the spec?


class GenericTest(object):
    """
    Generic testing class.
    Can be used independently or inhereted from in order to perform more detailed testing.
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
        self.result += self.test_basics()

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
        headers['Access-Control-Request-Method'] = method  # Match to request type
        headers['Access-Control-Request-Headers'] = "Content-Type"  # Needed for POST/PATCH etc
        return headers

    def validate_CORS(self, method, response):
        if 'Access-Control-Allow-Origin' not in response.headers:
            return False
        if method in ['OPTIONS', 'POST', 'PUT', 'PATCH', 'DELETE']:
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
# TODO: Worth checking PTP etc too, and reachability of Node API on all endpoints, plus endpoint matching the one under
#       test
# TODO: Test the Node API first and in isolation to check it all looks generally OK before proceeding with Reg API
#       interactions

    def check_base_path(self, path, expectation):
        test = Test("GET {}".format(path))
        req = requests.get(self.base_url + path)
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

    def test_basics(self):
        results = []

        # When a 'list' is encountered, the results are stored here for subsequent parameterised GETs
        saved_entities = {}

        for api in self.apis:
            results.append(self.check_base_path("/", "x-nmos/"))
            results.append(self.check_base_path("/x-nmos", api + "/"))
            results.append(self.check_base_path("/x-nmos/{}".format(api), self.test_version + "/"))

            for resource in self.apis[api]["spec"].get_reads():
                for response_code in resource[1]['responses']:
                    if response_code == 200:
                        # Test URLs which include a {resourceId} or similar parameter
                        if resource[1]['params'] and len(resource[1]['params']) == 1:
                            path_parts = resource[0].split("/")
                            path = ""
                            for part in path_parts:
                                if part.startswith("{"):
                                    break
                                if part != "":
                                    path += "/" + part
                            if path in saved_entities:
                                # Pick the first relevant saved entity and construct a test
                                entity = saved_entities[path][0]
                                url_param = resource[0].replace("{" + resource[1]['params'][0].name + "}", entity)
                                url = "{}{}".format(self.apis[api]["url"].rstrip("/"), url_param)
                                test = Test("{} /x-nmos/{}/{}{}".format(resource[1]['method'].upper(),
                                                                        api,
                                                                        self.test_version,
                                                                        url_param))
                            else:
                                # There were no saved entities found, so we can't test this parameterised URL
                                test = Test("{} /x-nmos/{}/{}{}".format(resource[1]['method'].upper(),
                                                                        api,
                                                                        self.test_version,
                                                                        resource[0]))
                                results.append(test.NA("No resources found to perform this test"))
                                continue

                        # Test general URLs with no parameters
                        elif not resource[1]['params']:
                            url = "{}{}".format(self.apis[api]["url"].rstrip("/"), resource[0])
                            test = Test("{} /x-nmos/{}/{}{}".format(resource[1]['method'].upper(),
                                                                    api,
                                                                    self.test_version,
                                                                    resource[0]))
                        else:
                            continue

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

                        # Gather IDs of sub-resources for testing of parameterised URLs...
                        try:
                            if isinstance(r.json(), list):
                                for entry in r.json():
                                    # In general, lists return fully fledged objects which each have an ID
                                    if isinstance(entry, dict) and "id" in entry:
                                        if resource[0] not in saved_entities:
                                            saved_entities[resource[0]] = [entry["id"]]
                                        else:
                                            saved_entities[resource[0]].append(entry["id"])
                                    # In some cases lists contain strings which indicate the path to each resource
                                    elif isinstance(entry, str) and entry.endswith("/"):
                                        res_id = entry.rstrip("/")
                                        if resource[0] not in saved_entities:
                                            saved_entities[resource[0]] = [res_id]
                                        else:
                                            saved_entities[resource[0]].append(res_id)
                        except json.decoder.JSONDecodeError:
                            pass

                        if resource[1]['responses'][response_code]:
                            try:
                                jsonschema.validate(r.json(), resource[1]['responses'][response_code])
                            except jsonschema.ValidationError:
                                results.append(test.FAIL("Response schema validation error"))
                                continue
                            except json.decoder.JSONDecodeError:
                                results.append(test.FAIL("Invalid JSON received"))
                                continue
                        else:
                            results.append(test.MANUAL("Test suite unable to locate schema"))
                            continue

                        results.append(test.PASS())
        return results
        # TODO: For any method we can't test, flag it as a manual test
        # TODO: Write a harness for each write method with one or more things to send it. Test them using this as part
        #       of this loop
        # TODO: Equally test for each of these if the trailing slash version also works and if redirects are used on
        #       either.


def ordered(obj):
    if isinstance(obj, dict):
        return sorted((k, ordered(v)) for k, v in obj.items())
    if isinstance(obj, list):
        return sorted(ordered(x) for x in obj)
    else:
        return obj


def compare_json(json1, json2):
    """Compares two json objects for equality"""
    return ordered(json1) == ordered(json2)


class Test(object):
    def __init__(self, description):
        self.description = description

    def PASS(self, detail=""):
        return [self.description, "Pass", detail]

    def MANUAL(self, detail=""):
        return [self.description, "Manual", detail]

    def NA(self, detail):
        return [self.description, "N/A", detail]

    def FAIL(self, detail):
        return [self.description, "Fail", detail]


class MdnsListener(object):
    def __init__(self):
        self.services = list()

    def add_service(self, zeroconf, type, name):
        info = zeroconf.get_service_info(type, name)
        if info is not None:
            self.services.append(info)

    def get_service_list(self):
        return self.services


class Specification(object):
    def __init__(self, file_path):
        self.data = {}
        self.fix_schemas(file_path)
        api_raml = ramlfications.parse(file_path, "config.ini")
        self.global_schemas = {}
        if api_raml.schemas:
            for schema in api_raml.schemas:
                keys = list(schema.keys())
                self.global_schemas[keys[0]] = schema[keys[0]]
        for resource in api_raml.resources:
            resource_data = {'method': resource.method,
                             'params': resource.uri_params,
                             'body': None,
                             'responses': {}}
            if resource.body is not None:
                for attr in resource.body:
                    if attr.mime_type == "schema":
                        resource_data['body'] = self.deref_schema(os.path.dirname(file_path), schema=attr.raw)
                        break
            for response in resource.responses:
                if response.code not in resource_data["responses"]:
                    resource_data["responses"][response.code] = None
                schema_loc = None
                if not response.body:
                    # Handle parsing errors in ramlfications manually, notably for schemas in RAML 1.0
                    if response.code in response.raw and response.raw[response.code] is not None:
                        if "body" in response.raw[response.code]:
                            if "type" in response.raw[response.code]["body"]:
                                schema_loc = response.raw[response.code]["body"]["type"]
                else:
                    for entry in response.body:
                        schema_loc = entry.schema
                        if not schema_loc:
                            schema_loc = entry.raw

                if isinstance(schema_loc, dict):
                    resource_data["responses"][response.code] = self.deref_schema(
                                                                     os.path.dirname(file_path),
                                                                     schema=schema_loc)
                elif schema_loc in self.global_schemas:
                    resource_data["responses"][response.code] = self.deref_schema(
                                                                     os.path.dirname(file_path),
                                                                     schema=self.global_schemas[schema_loc])

            if resource.path not in self.data:
                self.data[resource.path] = [resource_data]
            else:
                self.data[resource.path].append(resource_data)

    def fix_schemas(self, file_path):
        # Fixes RAML to match ramlfications expectations (bugs)
        lines = []
        in_schemas = False
        with open(file_path) as raml:
            line = raml.readline()
            while line:
                if in_schemas and not line.startswith(" "):
                    in_schemas = False
                if in_schemas and "- " not in line:
                    line = "  - " + line.lstrip()
                if line.startswith("schemas:"):
                    in_schemas = True
                lines.append(line)
                line = raml.readline()
        with open(file_path, "w") as raml:
            raml.writelines("".join(lines))

    def deref_schema(self, dir, name=None, schema=None):
        def process(obj):
            if isinstance(obj, dict):
                if len(obj) == 1 and "$ref" in obj:
                    return self.deref_schema(dir, name=obj['$ref'])
                return {k: process(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [process(x) for x in obj]
            else:
                return obj

        local = {}
        if name:
            filename = "{}/{}".format(dir, name)
            with open(filename, 'r') as fh:
                local = process(json.load(fh))
            return local
        else:
            return process(schema)

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
            for method_def in self.data[resource]:
                if method_def['method'] in ['get', 'head', 'options']:
                    resources.append((resource, method_def))
        resources.sort()
        return resources

    def get_writes(self):
        resources = []
        for resource in self.data:
            for method_def in self.data[resource]:
                if method_def['method'] in ['post', 'put', 'patch', 'delete']:
                    resources.append((resource, method_def))
        resources.sort()
        return resources
