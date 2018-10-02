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

import os
import json
import time
import requests
import git
import ramlfications
import jsonschema

from jsonschema import ValidationError, RefResolver, Draft4Validator

# TODO: Consider whether to set Accept headers? If we don't set them we expect APIs to default to application/json
# unless told otherwise. Is this part of the spec?

# The UTC leap seconds table below was extracted from the information provided at
# http://www.ietf.org/timezones/data/leap-seconds.list
#
# The order has been reversed.
# The NTP epoch seconds have been converted to Unix epoch seconds. The difference between
# the NTP epoch at 1 Jan 1900 and the Unix epoch at 1 Jan 1970 is 2208988800 seconds

UTC_LEAP = [
    # || UTC SEC  |  TAI SEC - 1 ||
    (1483228800, 1483228836),  # 1 Jan 2017, 37 leap seconds
    (1435708800, 1435708835),  # 1 Jul 2015, 36 leap seconds
    (1341100800, 1341100834),  # 1 Jul 2012, 35 leap seconds
    (1230768000, 1230768033),  # 1 Jan 2009, 34 leap seconds
    (1136073600, 1136073632),  # 1 Jan 2006, 33 leap seconds
    (915148800, 915148831),  # 1 Jan 1999, 32 leap seconds
    (867715200, 867715230),  # 1 Jul 1997, 31 leap seconds
    (820454400, 820454429),  # 1 Jan 1996, 30 leap seconds
    (773020800, 773020828),  # 1 Jul 1994, 29 leap seconds
    (741484800, 741484827),  # 1 Jul 1993, 28 leap seconds
    (709948800, 709948826),  # 1 Jul 1992, 27 leap seconds
    (662688000, 662688025),  # 1 Jan 1991, 26 leap seconds
    (631152000, 631152024),  # 1 Jan 1990, 25 leap seconds
    (567993600, 567993623),  # 1 Jan 1988, 24 leap seconds
    (489024000, 489024022),  # 1 Jul 1985, 23 leap seconds
    (425865600, 425865621),  # 1 Jul 1983, 22 leap seconds
    (394329600, 394329620),  # 1 Jul 1982, 21 leap seconds
    (362793600, 362793619),  # 1 Jul 1981, 20 leap seconds
    (315532800, 315532818),  # 1 Jan 1980, 19 leap seconds
    (283996800, 283996817),  # 1 Jan 1979, 18 leap seconds
    (252460800, 252460816),  # 1 Jan 1978, 17 leap seconds
    (220924800, 220924815),  # 1 Jan 1977, 16 leap seconds
    (189302400, 189302414),  # 1 Jan 1976, 15 leap seconds
    (157766400, 157766413),  # 1 Jan 1975, 14 leap seconds
    (126230400, 126230412),  # 1 Jan 1974, 13 leap seconds
    (94694400, 94694411),  # 1 Jan 1973, 12 leap seconds
    (78796800, 78796810),  # 1 Jul 1972, 11 leap seconds
    (63072000, 63072009),  # 1 Jan 1972, 10 leap seconds
]

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
        self.file_prefix = "file:///" if os.name == "nt" else "file:"

        self.major_version, self.minor_version = self._parse_version(self.test_version)

        repo = git.Repo(self.spec_path)
        self.result = list()

        spec_branch = self.test_version + ".x"
        repo.git.reset('--hard')
        repo.git.checkout(spec_branch)
        self.parse_RAML()

    def _parse_version(self, version):
        version_parts = version.strip("v").split(".")
        return int(version_parts[0]), int(version_parts[1])

    def execute_tests(self):
        print(" * Running basic API tests")
        self.result += self.basics()
        for method_name in dir(self):
            if method_name.startswith("test_"):
                method = getattr(self, method_name)
                if callable(method):
                    print(" * Running " + method_name)
                    self.result.append(method())

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

    def check_response(self, test, api_name, method, path, response):
        if not self.validate_CORS(method, response):
            return test.FAIL("Incorrect CORS headers: {}".format(response.headers))

        schema = self.apis[api_name]["spec"].get_schema(method, path, response.status_code)

        if schema:
            try:
                resolver = jsonschema.RefResolver(self.file_prefix + os.path.join(self.spec_path + '/APIs/schemas/'),
                                                  schema)
                jsonschema.validate(response.json(), schema, resolver=resolver)
            except jsonschema.ValidationError:
                return test.FAIL("Response schema validation error")
            except json.decoder.JSONDecodeError:
                return test.FAIL("Invalid JSON received")
        else:
            return test.MANUAL("Test suite unable to locate schema")

        return test.PASS()

    def do_request(self, method, url, data=None):
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
        except requests.exceptions.RequestException as e:
            return False, str(e)

    def basics(self):
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

                        status, response = self.do_request(resource[1]['method'], url)
                        if not status:
                            results.append(test.FAIL(response))
                            continue

                        if response.status_code != response_code:
                            results.append(test.FAIL("Incorrect response code: {}".format(response.status_code)))
                            continue

                        # Gather IDs of sub-resources for testing of parameterised URLs...
                        try:
                            if isinstance(response.json(), list):
                                for entry in response.json():
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

                        results.append(self.check_response(test, api, resource[1]["method"], resource[0], response))

        return results
        # TODO: For any method we can't test, flag it as a manual test
        # TODO: Write a harness for each write method with one or more things to send it. Test them using this as part
        #       of this loop
        # TODO: Equally test for each of these if the trailing slash version also works and if redirects are used on
        #       either.

    def getTAITime(self, offset=0.0):
        """Get the current TAI time as a colon seperated string"""
        myTime = time.time() + offset
        secs = int(myTime)
        nanos = int((myTime - secs) * 1e9)
        ippTime = self.from_UTC(secs, nanos)
        return str(ippTime[0]) + ":" + str(ippTime[1])

    def from_UTC(self, secs, nanos, is_leap=False):
        leap_sec = 0
        for tbl_sec, tbl_tai_sec_minus_1 in UTC_LEAP:
            if secs >= tbl_sec:
                leap_sec = (tbl_tai_sec_minus_1 + 1) - tbl_sec
                break
        return secs + leap_sec + is_leap, nanos

    def load_schema(self, path):
        """Used to load in schemas"""
        real_path = os.path.join(self.spec_path + '/APIs/schemas/', path)
        f = open(real_path, "r")
        return json.loads(f.read())

    def get_num_paths(self, port, portType):
        """Returns the number or redundant paths on a port"""
        url = self.url + "single/" + portType + "s/" + port + "/constraints/"
        try:
            r = requests.get(url)
            try:
                rjson = r.json()
                return len(rjson)
            except ValueError:
                return 0
        except requests.exceptions.RequestException:
            return 0

    def compare_to_schema(self, schema, endpoint, status_code=200):
        """Compares the response form an endpoint to a schema"""
        resolver = RefResolver(self.file_prefix + os.path.join(self.spec_path + '/APIs/schemas/'), schema)
        valid, response = self.checkCleanRequest("GET", endpoint, code=status_code)
        if valid:
            try:
                Draft4Validator(schema).validate(response)
                return True, ""
            except ValidationError as e:
                return False, "Response from {} did not meet schema: {}".format(endpoint, str(e))
        else:
            return False, "Invalid response while getting data: " + response

    def checkCleanRequest(self, method, dest, data=None, code=200):
        """Checks a request can be made and the resulting json can be parsed"""
        status, response = self.do_request(method, self.url + dest, data)
        if not status:
            return status, response

        message = "Expected status code {} from {}, got {}.".format(code, dest, response.status_code)
        if response.status_code == code:
            try:
                return True, response.json()
            except:
                # Failed parsing JSON
                msg = "Failed decoding JSON from {}, got {}. Please check JSON syntax".format(
                    dest,
                    response.text
                )
                return False, msg
        else:
            return False, message


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
        self._fix_schemas(file_path)
        api_raml = ramlfications.parse(file_path, "config.ini")
        self.global_schemas = {}
        if api_raml.schemas:
            for schema in api_raml.schemas:
                keys = list(schema.keys())
                self.global_schemas[keys[0]] = schema[keys[0]]
        elif "types" in api_raml.raw:
            # Handle parsing errors in ramlfications manually, notably for schemas in RAML 1.0
            for schema in api_raml.raw["types"]:
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
                        resource_data['body'] = self._deref_schema(os.path.dirname(file_path), schema=attr.raw)
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
                            if "type" in entry.raw:
                                schema_loc = entry.raw["type"]

                if isinstance(schema_loc, dict):
                    resource_data["responses"][response.code] = self._deref_schema(
                                                                     os.path.dirname(file_path),
                                                                     schema=schema_loc)
                elif schema_loc in self.global_schemas:
                    resource_data["responses"][response.code] = self._deref_schema(
                                                                     os.path.dirname(file_path),
                                                                     schema=self.global_schemas[schema_loc])

            if resource.path not in self.data:
                self.data[resource.path] = [resource_data]
            else:
                self.data[resource.path].append(resource_data)

    def _fix_schemas(self, file_path):
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
                if line.startswith("schemas:") or line.startswith("types:"):
                    in_schemas = True
                lines.append(line)
                line = raml.readline()
        with open(file_path, "w") as raml:
            raml.writelines("".join(lines))

    def _deref_schema(self, dir, name=None, schema=None):
        def process(obj):
            if isinstance(obj, dict):
                if len(obj) == 1 and "$ref" in obj:
                    return self._deref_schema(dir, name=obj['$ref'])
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

    def get_schema(self, method, path, response_code):
        if path in self.data:
            for response in self.data[path]:
                if response["method"].upper() == method.upper():
                    if response["responses"][response_code]:
                        return response["responses"][response_code]
        return None

    def get_reads(self):
        resources = []
        for resource in self.data:
            for method_def in self.data[resource]:
                if method_def['method'] in ['get', 'head', 'options']:
                    resources.append((resource, method_def))
        resources = sorted(resources, key=lambda x: x[0])
        return resources

    def get_writes(self):
        resources = []
        for resource in self.data:
            for method_def in self.data[resource]:
                if method_def['method'] in ['post', 'put', 'patch', 'delete']:
                    resources.append((resource, method_def))
        resources = sorted(resources, key=lambda x: x[0])
        return resources
