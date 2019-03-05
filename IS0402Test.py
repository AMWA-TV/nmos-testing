# Copyright (C) 2018 British Broadcasting Corporation
#
# Modifications Copyright 2018 Riedel Communications GmbH & Co. KG
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

from time import sleep
import socket
import uuid
import json
from copy import deepcopy
from jsonschema import ValidationError
import re

from zeroconf_monkey import ServiceBrowser, Zeroconf
from MdnsListener import MdnsListener
from TestResult import Test
from GenericTest import GenericTest, NMOSTestException, NMOSInitException, test_depends
from IS04Utils import IS04Utils
from Config import GARBAGE_COLLECTION_TIMEOUT
from TestHelper import WebsocketWorker, load_resolved_schema

REG_API_KEY = "registration"
QUERY_API_KEY = "query"


class IS0402Test(GenericTest):
    """
    Runs IS-04-02-Test
    """
    def __init__(self, apis):
        # Don't auto-test /health/nodes/{nodeId} as it's impossible to automatically gather test data
        omit_paths = [
          "/health/nodes/{nodeId}"
        ]
        GenericTest.__init__(self, apis, omit_paths)
        self.reg_url = self.apis[REG_API_KEY]["url"]
        self.query_url = self.apis[QUERY_API_KEY]["url"]
        if self.apis[REG_API_KEY]["version"] != self.apis[QUERY_API_KEY]["version"]:
            raise NMOSInitException("The Registration and Query API versions under test must be identical")
        self.zc = None
        self.zc_listener = None
        self.is04_reg_utils = IS04Utils(self.reg_url)
        self.is04_query_utils = IS04Utils(self.query_url)
        self.test_data = self.load_resource_data()
        self.subscription_data = self.load_subscription_request_data()

    def set_up_tests(self):
        self.zc = Zeroconf()
        self.zc_listener = MdnsListener(self.zc)

    def tear_down_tests(self):
        if self.zc:
            self.zc.close()
            self.zc = None

    def test_01(self):
        """Registration API advertises correctly via mDNS"""

        test = Test("Registration API advertises correctly via mDNS")

        service_type = "_nmos-registration._tcp.local."
        if self.is04_reg_utils.compare_api_version(self.apis[REG_API_KEY]["version"], "v1.3") >= 0:
            service_type = "_nmos-register._tcp.local."

        browser = ServiceBrowser(self.zc, service_type, self.zc_listener)
        sleep(2)
        serv_list = self.zc_listener.get_service_list()
        for api in serv_list:
            address = socket.inet_ntoa(api.address)
            port = api.port
            if "/{}:{}/".format(address, port) in self.reg_url:
                properties = self.convert_bytes(api.properties)
                if "pri" not in properties:
                    return test.FAIL("No 'pri' TXT record found in Registration API advertisement.")
                try:
                    priority = int(properties["pri"])
                    if priority < 0:
                        return test.FAIL("Priority ('pri') TXT record must be greater than zero.")
                    elif priority >= 100:
                        return test.WARNING("Priority ('pri') TXT record must be less than 100 for a production instance.")
                except Exception:
                    return test.FAIL("Priority ('pri') TXT record is not an integer.")

                # Other TXT records only came in for IS-04 v1.1+
                api = self.apis[REG_API_KEY]
                if self.is04_reg_utils.compare_api_version(api["version"], "v1.1") >= 0:
                    if "api_ver" not in properties:
                        return test.FAIL("No 'api_ver' TXT record found in Registration API advertisement.")
                    elif api["version"] not in properties["api_ver"].split(","):
                        return test.FAIL("Registry does not claim to support version under test.")

                    if "api_proto" not in properties:
                        return test.FAIL("No 'api_proto' TXT record found in Registration API advertisement.")
                    elif properties["api_proto"] == "https":
                        return test.MANUAL("API protocol is not advertised as 'http'. "
                                           "This test suite does not currently support 'https'.")
                    elif properties["api_proto"] != "http":
                        return test.FAIL("API protocol ('api_proto') TXT record is not 'http' or 'https'.")

                return test.PASS()
        return test.FAIL("No matching mDNS announcement found for Registration API.")

    def test_02(self):
        """Query API advertises correctly via mDNS"""

        test = Test("Query API advertises correctly via mDNS")

        browser = ServiceBrowser(self.zc, "_nmos-query._tcp.local.", self.zc_listener)
        sleep(2)
        serv_list = self.zc_listener.get_service_list()
        for api in serv_list:
            address = socket.inet_ntoa(api.address)
            port = api.port
            if "/{}:{}/".format(address, port) in self.query_url:
                properties = self.convert_bytes(api.properties)
                if "pri" not in properties:
                    return test.FAIL("No 'pri' TXT record found in Query API advertisement.")
                try:
                    priority = int(properties["pri"])
                    if priority < 0:
                        return test.FAIL("Priority ('pri') TXT record must be greater than zero.")
                    elif priority >= 100:
                        return test.WARNING("Priority ('pri') TXT record must be less than 100 for a production instance.")
                except Exception:
                    return test.FAIL("Priority ('pri') TXT record is not an integer.")

                # Other TXT records only came in for IS-04 v1.1+
                api = self.apis[QUERY_API_KEY]
                if self.is04_query_utils.compare_api_version(api["version"], "v1.1") >= 0:
                    if "api_ver" not in properties:
                        return test.FAIL("No 'api_ver' TXT record found in Query API advertisement.")
                    elif api["version"] not in properties["api_ver"].split(","):
                        return test.FAIL("Registry does not claim to support version under test.")

                    if "api_proto" not in properties:
                        return test.FAIL("No 'api_proto' TXT record found in Query API advertisement.")
                    elif properties["api_proto"] == "https":
                        return test.MANUAL("API protocol is not advertised as 'http'. "
                                           "This test suite does not currently support 'https'.")
                    elif properties["api_proto"] != "http":
                        return test.FAIL("API protocol ('api_proto') TXT record is not 'http' or 'https'.")

                return test.PASS()
        return test.FAIL("No matching mDNS announcement found for Query API.")

    def test_03(self):
        """Registration API accepts and stores a valid Node resource"""

        test = Test("Registration API accepts and stores a valid Node resource")

        api = self.apis[REG_API_KEY]
        if self.is04_reg_utils.compare_api_version(api["version"], "v2.0") < 0:
            node_json = deepcopy(self.test_data["node"])
            if self.is04_reg_utils.compare_api_version(api["version"], "v1.2") < 0:
                node_json = self.downgrade_resource("node", node_json, self.apis[REG_API_KEY]["version"])

            self.post_resource(test, "node", node_json, 201)

            return test.PASS()
        else:
            return test.FAIL("Version > 1 not supported yet.")

    def test_04(self):
        """Registration API rejects an invalid Node resource with a 400 HTTP code"""

        test = Test("Registration API rejects an invalid Node resource with a 400 HTTP code")

        bad_json = {"notanode": True}
        return self.do_400_check(test, "node", bad_json)

    @test_depends
    def test_05(self):
        """Registration API accepts and stores a valid Device resource"""

        test = Test("Registration API accepts and stores a valid Device resource")

        api = self.apis[REG_API_KEY]
        if self.is04_reg_utils.compare_api_version(api["version"], "v2.0") < 0:
            device_json = deepcopy(self.test_data["device"])

            if self.is04_reg_utils.compare_api_version(api["version"], "v1.2") < 0:
                device_json = self.downgrade_resource("device", device_json, self.apis[REG_API_KEY]["version"])

            self.post_resource(test, "device", device_json, 201)

            return test.PASS()
        else:
            return test.FAIL("Version > 1 not supported yet.")

    @test_depends
    def test_06(self):
        """Registration API rejects an invalid Device resource with a 400 HTTP code"""

        test = Test("Registration API rejects an invalid Device resource with a 400 HTTP code")

        bad_json = {"notadevice": True}
        return self.do_400_check(test, "device", bad_json)

    @test_depends
    def test_07(self):
        """Registration API accepts and stores a valid Source resource"""

        test = Test("Registration API accepts and stores a valid Source resource")

        api = self.apis[REG_API_KEY]
        if self.is04_reg_utils.compare_api_version(api["version"], "v2.0") < 0:
            source_json = deepcopy(self.test_data["source"])
            if self.is04_reg_utils.compare_api_version(api["version"], "v1.2") < 0:
                source_json = self.downgrade_resource("source", source_json, self.apis[REG_API_KEY]["version"])

            self.post_resource(test, "source", source_json, 201)

            return test.PASS()
        else:
            return test.FAIL("Version > 1 not supported yet.")

    @test_depends
    def test_08(self):
        """Registration API rejects an invalid Source resource with a 400 HTTP code"""

        test = Test("Registration API rejects an invalid Source resource with a 400 HTTP code")

        bad_json = {"notasource": True}
        return self.do_400_check(test, "source", bad_json)

    @test_depends
    def test_09(self):
        """Registration API accepts and stores a valid Flow resource"""

        test = Test("Registration API accepts and stores a valid Flow resource")

        api = self.apis[REG_API_KEY]
        if self.is04_reg_utils.compare_api_version(api["version"], "v2.0") < 0:
            flow_json = deepcopy(self.test_data["flow"])

            if self.is04_reg_utils.compare_api_version(api["version"], "v1.2") < 0:
                flow_json = self.downgrade_resource("flow", flow_json, self.apis[REG_API_KEY]["version"])

            self.post_resource(test, "flow", flow_json, 201)

            return test.PASS()
        else:
            return test.FAIL("Version > 1 not supported yet.")

    @test_depends
    def test_10(self):
        """Registration API rejects an invalid Flow resource with a 400 HTTP code"""

        test = Test("Registration API rejects an invalid Flow resource with a 400 HTTP code")

        bad_json = {"notaflow": True}
        return self.do_400_check(test, "flow", bad_json)

    @test_depends
    def test_11(self):
        """Registration API accepts and stores a valid Sender resource"""

        test = Test("Registration API accepts and stores a valid Sender resource")

        api = self.apis[REG_API_KEY]
        if self.is04_reg_utils.compare_api_version(api["version"], "v2.0") < 0:
            sender_json = deepcopy(self.test_data["sender"])
            if self.is04_reg_utils.compare_api_version(api["version"], "v1.2") < 0:
                sender_json = self.downgrade_resource("sender", sender_json, self.apis[REG_API_KEY]["version"])

            self.post_resource(test, "sender", sender_json, 201)

            return test.PASS()
        else:
            return test.FAIL("Version > 1 not supported yet.")

    @test_depends
    def test_12(self):
        """Registration API rejects an invalid Sender resource with a 400 HTTP code"""

        test = Test("Registration API rejects an invalid Sender resource with a 400 HTTP code")

        bad_json = {"notasender": True}
        return self.do_400_check(test, "sender", bad_json)

    @test_depends
    def test_13(self):
        """Registration API accepts and stores a valid Receiver resource"""

        test = Test("Registration API accepts and stores a valid Receiver resource")

        api = self.apis[REG_API_KEY]
        if self.is04_reg_utils.compare_api_version(api["version"], "v2.0") < 0:
            receiver_json = deepcopy(self.test_data["receiver"])
            if self.is04_reg_utils.compare_api_version(api["version"], "v1.2") < 0:
                receiver_json = self.downgrade_resource("receiver", receiver_json, self.apis[REG_API_KEY]["version"])

            self.post_resource(test, "receiver", receiver_json, 201)

            return test.PASS()
        else:
            return test.FAIL("Version > 1 not supported yet.")

    @test_depends
    def test_14(self):
        """Registration API rejects an invalid Receiver resource with a 400 HTTP code"""

        test = Test("Registration API rejects an invalid Receiver resource with a 400 HTTP code")

        bad_json = {"notareceiver": True}
        return self.do_400_check(test, "receiver", bad_json)

    @test_depends
    def test_15(self):
        """Updating Node resource results in 200"""
        test = Test("Registration API responds with 200 HTTP code on updating a registered Node")

        api = self.apis[REG_API_KEY]
        if self.is04_reg_utils.compare_api_version(api["version"], "v2.0") < 0:
            node_json = deepcopy(self.test_data["node"])
            if self.is04_reg_utils.compare_api_version(api["version"], "v1.2") < 0:
                node_json = self.downgrade_resource("node", node_json, self.apis[REG_API_KEY]["version"])

            self.post_resource(test, "node", node_json, 200)

            return test.PASS()
        else:
            return test.FAIL("Version > 1 not supported yet.")

    @test_depends
    def test_16(self):
        """Updating Device resource results in 200"""
        test = Test("Registration API responds with 200 HTTP code on updating a registered Device")

        api = self.apis[REG_API_KEY]
        if self.is04_reg_utils.compare_api_version(api["version"], "v2.0") < 0:
            device_json = deepcopy(self.test_data["device"])

            if self.is04_reg_utils.compare_api_version(api["version"], "v1.2") < 0:
                device_json = self.downgrade_resource("device", device_json, self.apis[REG_API_KEY]["version"])

            self.post_resource(test, "device", device_json, 200)

            return test.PASS()
        else:
            return test.FAIL("Version > 1 not supported yet.")

    @test_depends
    def test_17(self):
        """Updating Source resource results in 200"""
        test = Test("Registration API responds with 200 HTTP code on updating a registered Source")

        api = self.apis[REG_API_KEY]
        if self.is04_reg_utils.compare_api_version(api["version"], "v2.0") < 0:
            source_json = deepcopy(self.test_data["source"])
            if self.is04_reg_utils.compare_api_version(api["version"], "v1.2") < 0:
                source_json = self.downgrade_resource("source", source_json, self.apis[REG_API_KEY]["version"])

            self.post_resource(test, "source", source_json, 200)

            return test.PASS()
        else:
            return test.FAIL("Version > 1 not supported yet.")

    @test_depends
    def test_18(self):
        """Updating Flow resource results in 200"""
        test = Test("Registration API responds with 200 HTTP code on updating a registered Flow")

        api = self.apis[REG_API_KEY]
        if self.is04_reg_utils.compare_api_version(api["version"], "v2.0") < 0:
            flow_json = deepcopy(self.test_data["flow"])

            if self.is04_reg_utils.compare_api_version(api["version"], "v1.2") < 0:
                flow_json = self.downgrade_resource("flow", flow_json, self.apis[REG_API_KEY]["version"])

            self.post_resource(test, "flow", flow_json, 200)

            return test.PASS()
        else:
            return test.FAIL("Version > 1 not supported yet.")

    @test_depends
    def test_19(self):
        """Updating Sender resource results in 200"""
        test = Test("Registration API responds with 200 HTTP code on updating a registered Sender")

        api = self.apis[REG_API_KEY]
        if self.is04_reg_utils.compare_api_version(api["version"], "v2.0") < 0:
            sender_json = deepcopy(self.test_data["sender"])
            if self.is04_reg_utils.compare_api_version(api["version"], "v1.2") < 0:
                sender_json = self.downgrade_resource("sender", sender_json, self.apis[REG_API_KEY]["version"])

            self.post_resource(test, "sender", sender_json, 200)

            return test.PASS()
        else:
            return test.FAIL("Version > 1 not supported yet.")

    @test_depends
    def test_20(self):
        """Updating Receiver resource results in 200"""
        test = Test("Registration API responds with 200 HTTP code on updating a registered Receiver")

        api = self.apis[REG_API_KEY]
        if self.is04_reg_utils.compare_api_version(api["version"], "v2.0") < 0:
            receiver_json = deepcopy(self.test_data["receiver"])
            if self.is04_reg_utils.compare_api_version(api["version"], "v1.2") < 0:
                receiver_json = self.downgrade_resource("receiver", receiver_json,
                                                        self.apis[REG_API_KEY]["version"])

            self.post_resource(test, "receiver", receiver_json, 200)

            return test.PASS()
        else:
            return test.FAIL("Version > 1 not supported yet.")

    def check_paged_trait(self, test):
        """Precondition check that the 'paged' trait applies to the API version under test"""

        api = self.apis[QUERY_API_KEY]
        if self.is04_query_utils.compare_api_version(api["version"], "v1.1") < 0:
            raise NMOSTestException(test.NA("This test does not apply to v1.0"))
        if self.is04_query_utils.compare_api_version(api["version"], "v2.0") >= 0:
            raise NMOSTestException(test.FAIL("Version > 1 not supported yet."))

    def post_sample_nodes(self, test, count, description, labeller = None):
        """Perform a POST request on the Registration API to register a number of sample nodes"""

        node_data = deepcopy(self.test_data["node"])
        node_data["description"] = description

        update_timestamps = []
        ids = []

        for _ in range(count):
            ids.append(str(uuid.uuid4()))

            node_data["id"] = ids[-1]
            self.bump_resource_version(node_data)

            if labeller != None:
                node_data["label"] = labeller(_)

            # For debugging
            node_data["tags"]["index"] = [str(_)]

            self.post_resource(test, "node", node_data, 201)

            # Perform a Query API request to get the update timestamp of the most recently POSTed node
            # Wish there was a better way, as this puts the cart before the horse!
            # Another alternative would be to use local timestamps, provided clocks were synchronised?

            response = self.do_paged_request(limit = 1)
            self.check_paged_response(test, response,
                                      expected_ids = [node_data["id"]],
                                      expected_since = None, expected_until = None)
            valid, r, query_parameters = response
            update_timestamps.append(r.headers["X-Paging-Until"])

        # Bear in mind that the returned arrays are in forward order
        # whereas Query API responses are required to be in reverse order
        return update_timestamps, ids

    def do_paged_request(self, resource_type = "nodes", limit = None, since = None, until = None,
                         description = None, label = None, id = None):
        """Perform a GET request on the Query API"""

        query_parameters = []

        if limit != None:
            query_parameters.append("paging.limit=" + str(limit))
        if since != None:
            query_parameters.append("paging.since=" + since)
        if until != None:
            query_parameters.append("paging.until=" + until)

        if description != None:
            query_parameters.append("description=" + description)
        if label != None:
            query_parameters.append("label=" + label)
        if id != None:
            query_parameters.append("id=" + id)

        query_string = "?" + "&".join(query_parameters) if len(query_parameters) !=0 else ""

        valid, response = self.do_request("GET", self.query_url + resource_type + query_string)

        return valid, response, query_parameters

    def check_paged_response(self, test, paged_response,
                             expected_ids,
                             expected_since, expected_until, expected_limit = None):
        """Check the result of a paged request, and when there's an error, raise an NMOSTestException"""

        valid, response, query_parameters = paged_response

        query_string = "?" + "&".join(query_parameters) if len(query_parameters) !=0 else ""

        if not valid:
            raise NMOSTestException(test.FAIL("Query API did not respond as expected, "
                                              "for query: {}".format(query_string)))
        elif response.status_code == 501:
            # Many of the paged queries also use basic query parameters, which means that
            # a 501 could indicate lack of support for either basic queries or pagination.
            # The initial "test_21_1" therefore does not use basic query parameters.
            raise NMOSTestException(test.OPTIONAL("Query API signalled that it does not support this query: {}. "
                                                  "Query APIs should support pagination for scalability."
                                                  .format(query_string),
                                                  "https://github.com/AMWA-TV/nmos/wiki/IS-04#registries-pagination"))
        elif response.status_code != 200:
            raise NMOSTestException(test.FAIL("Query API returned an unexpected response: "
                                              "{} {}".format(response.status_code, response.text)))

        # check *presence* of paging headers before checking response body

        PAGING_HEADERS = ["Link", "X-Paging-Limit", "X-Paging-Since", "X-Paging-Until"]

        absent_paging_headers = [_ for _ in PAGING_HEADERS if _ not in response.headers]
        if (len(absent_paging_headers) == len(PAGING_HEADERS)):
            raise NMOSTestException(test.OPTIONAL("Query API response did not include any pagination headers. "
                                                  "Query APIs should support pagination for scalability.",
                                                  "https://github.com/AMWA-TV/nmos/wiki/IS-04#registries-pagination"))
        elif (len(absent_paging_headers) != 0):
            raise NMOSTestException(test.FAIL("Query API response did not include all pagination headers, "
                                              "missing: {}".format(absent_paging_headers)))

        # check response body

        if expected_ids is not None:
            try:
                if len(response.json()) != len(expected_ids):
                    raise NMOSTestException(test.FAIL("Query API response did not include the correct number of resources, "
                                                      "for query: {}".format(query_string)))

                for i in range(len(response.json())):
                    if (response.json()[i]["id"]) != expected_ids[-(i + 1)]:
                        raise NMOSTestException(test.FAIL("Query API response did not include the correct resources, "
                                                          "for query: {}".format(query_string)))

            except json.decoder.JSONDecodeError:
                raise NMOSTestException(test.FAIL("Non-JSON response returned"))
            except KeyError:
                raise NMOSTestException(test.FAIL("Query API did not respond as expected, "
                                                  "for query: {}".format(query_string)))

        # check *values* of paging headers after body

        def check_timestamp(expected, actual):
            return expected is None or self.is04_query_utils.compare_resource_version(expected, actual) == 0

        try:
            since = response.headers["X-Paging-Since"]
            until = response.headers["X-Paging-Until"]
            limit = response.headers["X-Paging-Limit"]

            if not check_timestamp(expected_since, since):
                raise NMOSTestException(test.FAIL("Query API response did not include the correct X-Paging-Since header, "
                                                  "for query: {}".format(query_string)))

            if not check_timestamp(expected_until, until):
                raise NMOSTestException(test.FAIL("Query API response did not include the correct X-Paging-Until header, "
                                                  "for query: {}".format(query_string)))

            if not (expected_limit is None or str(expected_limit) == limit):
                raise NMOSTestException(test.FAIL("Query API response did not include the correct X-Paging-Limit header, "
                                                  "for query: {}".format(query_string)))

            LINK_PATTERN = re.compile('<(?P<url>.+)>; rel="(?P<rel>.+)"')

            link_header = {rel: url for (rel, url) in
                [(_.group("rel"), _.group("url")) for _ in
                    [LINK_PATTERN.search(_) for _ in
                        response.headers["Link"].split(",")]]}

            prev = link_header["prev"]
            next = link_header["next"]

            if "paging.until=" + since not in prev or "paging.since=" in prev:
                raise NMOSTestException(test.FAIL("Query API response did not include the correct 'prev' value "
                                                  "in the Link header, for query: {}".format(query_string)))

            if "paging.since=" + until not in next or "paging.until=" in next:
                raise NMOSTestException(test.FAIL("Query API response did not include the correct 'next' value "
                                                  "in the Link header, for query: {}".format(query_string)))

            # 'first' and 'last' are optional, though there's no obvious reason for them to be
            first = link_header["first"] if "first" in link_header else None
            last = link_header["last"] if "last" in link_header else None

            if first is not None:
                if "paging.since=0:0" not in first or "paging.until=" in first:
                    raise NMOSTestException(test.FAIL("Query API response did not include the correct 'first' value "
                                                      "in the Link header, for query: {}".format(query_string)))

            if last is not None:
                if "paging.until=" in last or "paging.since=" in last:
                    raise NMOSTestException(test.FAIL("Query API response did not include the correct 'last' value "
                                                      "in the Link header, for query: {}".format(query_string)))

            for rel in ["first", "prev", "next", "last"]:
                if rel not in link_header:
                    continue

                if "paging.limit=" + limit not in link_header[rel]:
                    raise NMOSTestException(test.FAIL("Query API response did not include the correct '{}' value "
                                                      "in the Link header, for query: {}".format(rel, query_string)))

                for param in query_parameters:
                    if "paging." in param:
                        continue
                    if param not in link_header[rel]:
                        raise NMOSTestException(test.FAIL("Query API response did not include the correct '{}' value "
                                                          "in the Link header, for query: {}".format(rel, query_string)))

        except KeyError as ex:
            raise NMOSTestException(test.FAIL("Query API response did not include the expected value "
                                              "in the Link header: {}".format(ex)))

    def test_21_1(self):
        """Query API implements pagination (no query or paging parameters)"""

        test = Test("Query API implements pagination (no query or paging parameters)")
        self.check_paged_trait(test)
        # description = inspect.currentframe().f_code.co_name
        description = "test_21_1"

        # Perform a query with no query or paging parameters (see note in check_paged_response regarding 501)
        response = self.do_paged_request()

        # Check whether the response contains the X-Paging- headers but don't check values
        self.check_paged_response(test, response,
                                  expected_ids = None,
                                  expected_since = None, expected_until = None, expected_limit = None)

        return test.PASS()

    def test_21_1_1(self):
        """Query API implements pagination (when explicitly requested)"""

        test = Test("Query API implements pagination (when explicitly requested)")
        self.check_paged_trait(test)
        description = "test_21_1_1"

        # Same as above, but query with paging.limit to clearly 'opt in'
        response = self.do_paged_request(limit = 10)

        # Check whether the response contains the X-Paging- headers but don't check values
        self.check_paged_response(test, response,
                                  expected_ids = None,
                                  expected_since = None, expected_until = None, expected_limit = None)

        return test.PASS()

    def test_21_2(self):
        """Query API implements pagination (documentation examples)"""

        test = Test("Query API implements pagination (documentation examples)")
        self.check_paged_trait(test)
        description = "test_21_2"

        # Initial test cases based on the examples in NMOS documentation
        # See https://github.com/AMWA-TV/nmos-discovery-registration/blob/v1.2.x/docs/2.5.%20APIs%20-%20Query%20Parameters.md#pagination

        ts, ids = self.post_sample_nodes(test, 20, description)

        # In order to make the array indices match up with the documentation more clearly
        # insert an extra element 0 in both arrays
        ts.insert(0, None)
        ids.insert(0, None)

        # "Implementations may specify their own default and maximum for the limit"
        # so theoretically, if a Query API had a very low maximum limit, that number could be returned
        # rather than the requested limit, for many of the following tests.
        # See https://github.com/AMWA-TV/nmos-discovery-registration/blob/v1.2.x/APIs/QueryAPI.raml#L37

        # Example 1: Initial /nodes Request

        # Ideally, we shouldn't specify the limit, and adapt the checks for whatever the default limit turns out to be
        response = self.do_paged_request(description = description, limit = 10)
        self.check_paged_response(test, response,
                                  expected_ids = ids[11:20 + 1],
                                  expected_since = ts[10], expected_until = ts[20], expected_limit = 10)

        # Example 2: Request With Custom Limit

        response = self.do_paged_request(description = description, limit = 5)
        self.check_paged_response(test, response,
                                  expected_ids = ids[16:20 + 1],
                                  expected_since = ts[15], expected_until = ts[20], expected_limit = 5)

        # Example 3: Request With Since Parameter

        response = self.do_paged_request(description = description, since = ts[4], limit = 10)
        self.check_paged_response(test, response,
                                  expected_ids = ids[5:14 + 1],
                                  expected_since = ts[4], expected_until = ts[14], expected_limit = 10)

        # Example 4: Request With Until Parameter

        response = self.do_paged_request(description = description, until = ts[16], limit = 10)
        self.check_paged_response(test, response,
                                  expected_ids = ids[7:16 + 1],
                                  expected_since = ts[6], expected_until = ts[16], expected_limit = 10)

        # Example 5: Request With Since & Until Parameters

        response = self.do_paged_request(description = description, since = ts[4], until = ts[16], limit = 10)
        self.check_paged_response(test, response,
                                  expected_ids = ids[5:14 + 1],
                                  expected_since = ts[4], expected_until = ts[14], expected_limit = 10)

        return test.PASS()

    def test_21_3(self):
        """Query API implements pagination (edge cases)"""

        test = Test("Query API implements pagination (edge cases)")
        self.check_paged_trait(test)
        description = "test_21_3"

        # Some additional test cases based on Basecamp discussion
        # See https://basecamp.com/1791706/projects/10192586/messages/70545892

        timestamps, ids = self.post_sample_nodes(test, 20, description)

        after = "{}:0".format(int (timestamps[-1].split(":")[0]) + 1)
        before = "{}:0".format(int (timestamps[0].split(":")[0]) - 1)

        # Check the header values when a client specifies a paging.since value after the newest resource's timestamp

        self.check_paged_response(test, self.do_paged_request(description = description, since = after),
                                  expected_ids = [],
                                  expected_since = after, expected_until = after)

        # Check the header values when a client specifies a paging.until value before the oldest resource's timestamp

        self.check_paged_response(test, self.do_paged_request(description = description, until = before),
                                  expected_ids = [],
                                  expected_since = "0:0", expected_until = before)

        # Check the header values for a query that results in only one resource, without any paging parameters

        # expected_until check could be more forgiving, i.e. >= timestamps[-1] and <= 'now'
        self.check_paged_response(test, self.do_paged_request(id = ids[12]),
                                  expected_ids = [ids[12]],
                                  expected_since = "0:0", expected_until = timestamps[-1])

        # Check the header values for a query that results in no resources, without any paging parameters

        # expected_until check could be more forgiving, i.e. >= timestamps[-1] and <= 'now'
        self.check_paged_response(test, self.do_paged_request(id = str(uuid.uuid4())),
                                  expected_ids = [],
                                  expected_since = "0:0", expected_until = timestamps[-1])

        return test.PASS()

    def test_21_4(self):
        """Query API implements pagination (requests that require empty responses)"""

        test = Test("Query API implements pagination (requests that require empty responses)")
        self.check_paged_trait(test)
        description = "test_21_4"

        timestamps, ids = self.post_sample_nodes(test, 20, description)

        ts = timestamps[12]

        # Check paging.since == paging.until

        response = self.do_paged_request(description = description, since = ts, until = ts, limit = 10)
        self.check_paged_response(test, response,
                                  expected_ids = [],
                                  expected_since = ts, expected_until = ts, expected_limit = 10)

        # Check paging.limit == 0, paging.since specified

        response = self.do_paged_request(description = description, since = ts, limit = 0)
        self.check_paged_response(test, response,
                                  expected_ids = [],
                                  expected_since = ts, expected_until = ts, expected_limit = 0)

        # Check paging.limit == 0, paging.since not specified

        response = self.do_paged_request(description = description, until = ts, limit = 0)
        self.check_paged_response(test, response,
                                  expected_ids = [],
                                  expected_since = ts, expected_until = ts, expected_limit = 0)

        return test.PASS()

    def test_21_5(self):
        """Query API implements pagination (filters that select discontiguous resources)"""

        test = Test("Query API implements pagination (filters that select discontiguous resources)")
        self.check_paged_trait(test)
        description = "test_21_5"

        foo = lambda index: 3 > (index + 1) % 5
        bar = lambda index: not foo(index)

        ts, ids = self.post_sample_nodes(test, 20, description, lambda index: "foo" if foo(index) else "bar")

        # Specify paging.limit in the requests with 'default paging parameters' in the following tests
        # because we can't rely on the implementation's default being 10

        # Query 1: "foo", default paging parameters
        #          filter         0, 1, -, -, 4, 5, 6, -, -, 9, 10, 11, --, --, 14, 15, 16, --, --, 19
        #          request      (                                                                      ]
        #          response           (       ^  ^  ^        ^   ^   ^           ^   ^   ^           ^ ]

        # expected_until check could be more forgiving, i.e. >= ts[19] and <= 'now'
        # expected_since check could be more forgiving, i.e. >= ts[1] and < ts[4]
        self.check_paged_response(test, self.do_paged_request(label = "foo", limit = 10),
                                  expected_ids = [ids[i] for i in range(len(ids)) if foo(i)][-10:],
                                  expected_since = ts[1], expected_until = ts[19], expected_limit = 10)

        # Query 2: 'prev' of Query 1
        #          filter         0, 1, -, -, 4, 5, 6, -, -, 9, 10, 11, --, --, 14, 15, 16, --, --, 19
        #          request      (      ]
        #          response     ( ^  ^ ]

        self.check_paged_response(test, self.do_paged_request(label = "foo", until = ts[1], limit = 10),
                                  expected_ids = [ids[i] for i in range(len(ids)) if foo(i)][0:-10],
                                  expected_since = "0:0", expected_until = ts[1], expected_limit = 10)

        # Query 3: 'next' of Query 1
        #          filter         0, 1, -, -, 4, 5, 6, -, -, 9, 10, 11, --, --, 14, 15, 16, --, --, 19
        #          request                                                                            (]
        #          response                                                                           (]

        self.check_paged_response(test, self.do_paged_request(label = "foo", since = ts[19], limit = 10),
                                  expected_ids = [],
                                  expected_since = ts[19], expected_until = ts[19], expected_limit = 10)

        # Query 4: "bar", default paging parameters
        #          filter         -, -, 2, 3, -, -, -, 7, 8, -, --, --, 12, 13, --, --, --, 17, 18, --
        #          request      (                                                                      ]
        #          response     (       ^  ^           ^  ^              ^   ^               ^   ^     ]

        # expected_until check could be more forgiving, i.e. >= ts[19] and <= 'now'
        self.check_paged_response(test, self.do_paged_request(label = "bar", limit = 10),
                                  expected_ids = [ids[i] for i in range(len(ids)) if bar(i)],
                                  expected_since = "0:0", expected_until = ts[19], expected_limit = 10)

        # Query 5: "bar", limited to 3
        #          filter         -, -, 2, 3, -, -, -, 7, 8, -, --, --, 12, 13, --, --, --, 17, 18, --
        #          request      (                                                                      ]
        #          response                                               (  ^               ^   ^     ]

        # expected_until check could be more forgiving, i.e. >= ts[18] and <= 'now'
        # expected_since check could be more forgiving, i.e. >= ts[12] and < ts[13]
        self.check_paged_response(test, self.do_paged_request(label = "bar", limit = 3),
                                  expected_ids = [ids[13], ids[17], ids[18]],
                                  expected_since = ts[12], expected_until = ts[19], expected_limit = 3)

        # Query 6: 'prev' of Query 5
        #          filter         -, -, 2, 3, -, -, -, 7, 8, -, --, --, 12, 13, --, --, --, 17, 18, --
        #          request      (                                          ]
        #          response                 (          ^  ^              ^ ]

        # expected_since check could be more forgiving, i.e. >= ts[3] and < ts[7]
        self.check_paged_response(test, self.do_paged_request(label = "bar", until = ts[12], limit = 3),
                                  expected_ids = [ids[7], ids[8], ids[12]],
                                  expected_since = ts[3], expected_until = ts[12], expected_limit = 3)

        # Query 7: like Query 5, with paging.since specified, but still enough matches
        #          filter         -, -, 2, 3, -, -, -, 7, 8, -, --, --, 12, 13, --, --, --, 17, 18, --
        #          request                     (                           ]
        #          response                    (       ^  ^              ^ ]

        self.check_paged_response(test, self.do_paged_request(label = "bar", since = ts[4], until = ts[12], limit = 3),
                                  expected_ids = [ids[7], ids[8], ids[12]],
                                  expected_since = ts[4], expected_until = ts[12], expected_limit = 3)

        # Query 8: like Query 5, with paging.since specified, and not enough matches
        #          filter         -, -, 2, 3, -, -, -, 7, 8, -, --, --, 12, 13, --, --, --, 17, 18, --
        #          request                                    (            ]
        #          response                                   (          ^ ]

        self.check_paged_response(test, self.do_paged_request(label = "bar", since = ts[9], until = ts[12], limit = 3),
                                  expected_ids = [ids[12]],
                                  expected_since = ts[9], expected_until = ts[12], expected_limit = 3)

        # Query 9: like Query 5, but no matches
        #          filter         -, -, 2, 3, -, -, -, 7, 8, -, --, --, 12, 13, --, --, --, 17, 18, --
        #          request                                    (        ]
        #          response                                   (        ]

        self.check_paged_response(test, self.do_paged_request(label = "bar", since = ts[9], until = ts[11], limit = 3),
                                  expected_ids = [],
                                  expected_since = ts[9], expected_until = ts[11], expected_limit = 3)

        return test.PASS()

    def test_21_6(self):
        """Query API implements pagination (bad requests)"""

        test = Test("Query API implements pagination (bad requests)")
        self.check_paged_trait(test)
        description = "test_21_6"

        before = self.is04_query_utils.get_TAI_time()
        after = self.is04_query_utils.get_TAI_time(1)

        # Specifying since after until is a bad request
        valid, response, query_parameters = self.do_paged_request(since = after, until = before)

        query_string = "?" + "&".join(query_parameters) if len(query_parameters) !=0 else ""

        if not valid:
            raise NMOSTestException(test.FAIL("Query API did not respond as expected, "
                                              "for query: {}".format(query_string)))

        if response.status_code == 501:
            raise NMOSTestException(test.OPTIONAL("Query API signalled that it does not support this query: {}. "
                                                  "Query APIs should support pagination for scalability."
                                                  .format(query_string),
                                                  "https://github.com/AMWA-TV/nmos/wiki/IS-04#registries-pagination"))

        # 200 OK *without* any paging headers also indicates not implemented (paging parameters ignored)
        PAGING_HEADERS = ["Link", "X-Paging-Limit", "X-Paging-Since", "X-Paging-Until"]

        absent_paging_headers = [_ for _ in PAGING_HEADERS if _ not in response.headers]
        if response.status_code == 200 and len(absent_paging_headers) == len(PAGING_HEADERS):
            raise NMOSTestException(test.OPTIONAL("Query API response did not include any pagination headers. "
                                                  "Query APIs should support pagination for scalability.",
                                                  "https://github.com/AMWA-TV/nmos/wiki/IS-04#registries-pagination"))

        # 200 OK *with* any paging headers indicates the Query API failed to identify the bad request
        # which is an error like any code other than the expected 400 Bad Request
        if response.status_code != 400:
            raise NMOSTestException(test.FAIL("Query API responded with wrong HTTP code, "
                                              "for query: {}".format(query_string)))

        return test.PASS()

    def test_21_7(self):
        """Query API implements pagination (updates between paged requests)"""

        test = Test("Query API implements pagination (updates between paged requests)")
        self.check_paged_trait(test)
        description = "test_21_7"

        count = 3
        ts, ids = self.post_sample_nodes(test, count, description)

        # initial paged request

        response = self.do_paged_request(description = description, limit = count)
        self.check_paged_response(test, response,
                                  expected_ids = ids,
                                  expected_since = "0:0", expected_until = ts[-1], expected_limit = count)

        resources = response[1].json()
        resources.reverse()

        # 'next' page should be empty

        response = self.do_paged_request(description = description, limit = count, since = ts[-1])
        self.check_paged_response(test, response,
                                  expected_ids = [],
                                  expected_since = ts[-1], expected_until = None, expected_limit = count)

        # 'current' page should be same as initial response

        response = self.do_paged_request(description = description, limit = count, until = ts[-1])
        self.check_paged_response(test, response,
                                  expected_ids = ids,
                                  expected_since = None, expected_until = ts[-1], expected_limit = count)

        # after an update, the 'next' page should now contain only the updated resource

        self.post_resource(test, "node", resources[1], 200)

        response = self.do_paged_request(description = description, limit = count, since = ts[-1])
        self.check_paged_response(test, response,
                                  expected_ids = [ids[1]],
                                  expected_since = ts[-1], expected_until = None, expected_limit = count)

        # and what was the 'current' page should now contain only the unchanged resources

        response = self.do_paged_request(description = description, limit = count, until = ts[-1])
        self.check_paged_response(test, response,
                                  expected_ids = [ids[0], ids[2]],
                                  expected_since = None, expected_until = ts[-1], expected_limit = count)

        # after the other resources are also updated, what was the 'current' page should now be empty

        self.post_resource(test, "node", resources[2], 200)
        self.post_resource(test, "node", resources[0], 200)

        response = self.do_paged_request(description = description, limit = count, until = ts[-1])
        self.check_paged_response(test, response,
                                  expected_ids = [],
                                  expected_since = None, expected_until = ts[-1], expected_limit = count)

        # and what was the 'next' page should now contain all the resources in the update order

        response = self.do_paged_request(description = description, limit = count, since = ts[-1])
        self.check_paged_response(test, response,
                                  expected_ids = [ids[1], ids[2], ids[0]],
                                  expected_since = ts[-1], expected_until = None, expected_limit = count)

        return test.PASS()

    def test_21_8(self):
        """Query API implements pagination (correct encoding of URLs in Link header)"""

        test = Test("Query API implements pagination (correct encoding of URLs in Link header)")
        self.check_paged_trait(test)
        description = "test_21_8"

        # check '&' is returned encoded
        response = self.do_paged_request(label = "foo%26bar")
        self.check_paged_response(test, response,
                                  expected_ids = None,
                                  expected_since = None, expected_until = None)

        return test.PASS()

    # TODO
    def _test_21_x(self):
        """Query API implements pagination (paging.order=create)"""

        test = Test("Query API implements pagination (paging.order=create)")
        self.check_paged_trait(test)
        description = "test_21_x"

        return test.MANUAL()

    def test_22(self):
        """Query API implements downgrade queries"""

        test = Test("Query API implements downgrade queries")

        if self.apis[QUERY_API_KEY]["version"] == "v1.0":
            return test.NA("This test does not apply to v1.0")

        # Find the API versions supported by the Reg API
        valid, r = self.do_request("GET", self.reg_url.rstrip(self.apis[REG_API_KEY]["version"] + "/"))
        if not valid:
            return test.FAIL("Registration API failed to respond to request")
        else:
            reg_versions = [version.rstrip("/") for version in r.json()]

        # Sort the list and remove API versions higher than the one under test
        reg_versions = self.is04_reg_utils.sort_versions(reg_versions)
        for api_version in list(reg_versions):
            if self.is04_reg_utils.compare_api_version(api_version, self.apis[REG_API_KEY]["version"]) > 0:
                reg_versions.remove(api_version)

        # Find the API versions supported by the Query API
        valid, r = self.do_request("GET", self.query_url.rstrip(self.apis[QUERY_API_KEY]["version"] + "/"))
        if not valid:
            return test.FAIL("Query API failed to respond to request")
        else:
            query_versions = [version.rstrip("/") for version in r.json()]

        # Sort the list and remove API versions higher than the one under test
        query_versions = self.is04_query_utils.sort_versions(query_versions)
        for api_version in list(query_versions):
            if self.is04_query_utils.compare_api_version(api_version, self.apis[QUERY_API_KEY]["version"]) > 0:
                query_versions.remove(api_version)

        # If we're testing the lowest API version, exit with an N/A or warning indicating we can't test at this level
        if query_versions[0] == self.apis[QUERY_API_KEY]["version"]:
            return test.NA("Downgrade queries are unnecessary when requesting from the lowest supported version of"
                           "a Query API")

        # Exit if the Registration API doesn't support the required versions
        for api_version in query_versions:
            if api_version not in reg_versions:
                return test.MANUAL("This test cannot run automatically as the Registration API does not support all"
                                   "of the API versions that the Query API does",
                                   "https://github.com/AMWA-TV/nmos/wiki/IS-04#registries-downgrade-queries")

        # Register a Node at each API version available (up to the version under test)
        node_ids = {}
        test_id = str(uuid.uuid4())
        for api_version in query_versions:
            # Note: We iterate over the Query API versions, not the Reg API as it's the Query API that's under test
            test_data = deepcopy(self.test_data["node"])
            test_data = self.downgrade_resource("node", test_data, api_version)
            test_data["id"] = str(uuid.uuid4())
            test_data["description"] = test_id
            node_ids[api_version] = test_data["id"]
            valid, r = self.do_request("POST", "{}/{}/resource"
                                               .format(self.reg_url.rstrip(self.apis[REG_API_KEY]["version"] + "/"),
                                                       api_version),
                                       data={"type": "node", "data": test_data})
            if not valid or r.status_code != 201:
                return test.FAIL("Bad status code: {}".format(r.status_code))

        # Make a request to the Query API for each Node POSTed to ensure it's visible (or not) at the version under test
        for api_version in query_versions:
            valid, r = self.do_request("GET", self.query_url + "nodes/{}".format(node_ids[api_version]))
            if not valid:
                return test.FAIL("Query API failed to respond to request")
            else:
                if r.status_code == 200 and api_version != self.apis[QUERY_API_KEY]["version"]:
                    return test.FAIL("Query API incorrectly exposed a {} resource at {}"
                                     .format(api_version, self.apis[QUERY_API_KEY]["version"]))
                elif r.status_code == 404 and api_version == self.apis[QUERY_API_KEY]["version"]:
                    return test.FAIL("Query API failed to expose a {} resource at {}"
                                     .format(api_version, self.apis[QUERY_API_KEY]["version"]))
                elif r.status_code not in [200, 404, 409]:
                    return test.FAIL("Query API returned an unexpected response code: {}".format(r.status_code))

        # Make a request with downgrades turned on for each API version down to the minimum
        # Raise an error if resources below the requested version are returned, or those for the relevant API versions
        # are not returned. Otherwise pass.
        for api_version in query_versions:
            valid, r = self.do_request("GET", self.query_url + "nodes/{}?query.downgrade={}".format(node_ids[api_version],
                                                                                                    api_version))
            if not valid:
                return test.FAIL("Query API failed to respond to request")
            elif self.is04_query_utils.compare_api_version(self.apis[QUERY_API_KEY]["version"], "v1.3") >= 0 and r.status_code == 501:
                return test.OPTIONAL("Query API signalled that it does not support downgrade queries. This may be "
                                     "important for multi-version support.",
                                     "https://github.com/AMWA-TV/nmos/wiki/IS-04#registries-downgrade-queries")
            elif r.status_code != 200:
                return test.FAIL("Query API failed to respond with a Node when asked to downgrade to {}"
                                 .format(api_version))

        # Make a request at each API version again, filtering with the test ID as the description
        for api_version in query_versions:
            # Find which Nodes should and shouldn't be visible
            expected_nodes = []
            for node_api_version, node_id in node_ids.items():
                if self.is04_query_utils.compare_api_version(node_api_version, api_version) >= 0:
                    expected_nodes.append(node_id)

            valid, r = self.do_request("GET", self.query_url + "nodes?query.downgrade={}&description={}"
                                                               .format(api_version, test_id))
            if not valid:
                return test.FAIL("Query API failed to respond to request")
            elif r.status_code != 200:
                return test.FAIL("Query API failed to respond with a Node when asked to downgrade to {}"
                                 .format(api_version))
            else:
                for node in r.json():
                    if node["id"] not in expected_nodes:
                        return test.FAIL("Query API exposed a Node from a lower version than expected when downgrading "
                                         "to {}".format(api_version))
                    expected_nodes.remove(node["id"])
                if len(expected_nodes) > 0:
                    return test.FAIL("Query API failed to expose an expected Node when downgrading to {}"
                                     .format(api_version))

        return test.PASS()

    def test_23(self):
        """Query API implements basic query parameters"""

        test = Test("Query API implements basic query parameters")

        try:
            valid, r = self.do_request("GET", self.query_url + "nodes")
            if not valid:
                return test.FAIL("Query API failed to respond to query")
            elif len(r.json()) == 0:
                return test.UNCLEAR("No Nodes found in registry. Test cannot proceed.")
        except json.decoder.JSONDecodeError:
            return test.FAIL("Non-JSON response returned")

        random_label = uuid.uuid4()
        query_string = "?label=" + str(random_label)
        valid, r = self.do_request("GET", self.query_url + "nodes" + query_string)
        api = self.apis[QUERY_API_KEY]
        if not valid:
            return test.FAIL("Query API failed to respond to query")
        elif self.is04_query_utils.compare_api_version(api["version"], "v1.3") >= 0 and r.status_code == 501:
            return test.OPTIONAL("Query API signalled that it does not support basic queries. This may be important for"
                                 " scalability.", "https://github.com/AMWA-TV/nmos/wiki/IS-04#registries-basic-queries")
        elif r.status_code != 200:
            raise NMOSTestException(test.FAIL("Query API returned an unexpected response: "
                                              "{} {}".format(r.status_code, r.text)))
        elif len(r.json()) > 0:
            return test.FAIL("Query API returned more records than expected for query: {}".format(query_string))

        return test.PASS()

    def test_24(self):
        """Query API implements RQL"""

        test = Test("Query API implements RQL")

        if self.apis[QUERY_API_KEY]["version"] == "v1.0":
            return test.NA("This test does not apply to v1.0")

        try:
            valid, r = self.do_request("GET", self.query_url + "nodes")
            if not valid:
                return test.FAIL("Query API failed to respond to query")
            elif len(r.json()) == 0:
                return test.UNCLEAR("No Nodes found in registry. Test cannot proceed.")
        except json.decoder.JSONDecodeError:
            return test.FAIL("Non-JSON response returned")

        random_label = uuid.uuid4()
        query_string = "?query.rql=eq(label," + str(random_label) + ")"
        valid, r = self.do_request("GET", self.query_url + "nodes" + query_string)
        if not valid:
            return test.FAIL("Query API failed to respond to query")
        elif r.status_code == 501:
            return test.OPTIONAL("Query API signalled that it does not support RQL queries. This may be important for "
                                 "scalability.",
                                 "https://github.com/AMWA-TV/nmos/wiki/IS-04#registries-resource-query-language-rql")
        elif r.status_code == 400:
            return test.OPTIONAL("Query API signalled that it refused to support this RQL query: "
                                 "{}".format(query_string),
                                 "https://github.com/AMWA-TV/nmos/wiki/IS-04#registries-resource-query-language-rql")
        elif r.status_code != 200:
            raise NMOSTestException(test.FAIL("Query API returned an unexpected response: "
                                              "{} {}".format(r.status_code, r.text)))
        elif len(r.json()) > 0:
            return test.FAIL("Query API returned more records than expected for query: {}".format(query_string))

        return test.PASS()

    def test_25(self):
        """Query API implements ancestry queries"""

        test = Test("Query API implements ancestry queries")

        if self.apis[QUERY_API_KEY]["version"] == "v1.0":
            return test.NA("This test does not apply to v1.0")

        try:
            valid, r = self.do_request("GET", self.query_url + "sources")
            if not valid:
                return test.FAIL("Query API failed to respond to query")
            elif len(r.json()) == 0:
                return test.UNCLEAR("No Sources found in registry. Test cannot proceed.")
        except json.decoder.JSONDecodeError:
            return test.FAIL("Non-JSON response returned")

        random_label = uuid.uuid4()
        query_string = "?query.ancestry_id=" + str(random_label) + "&query.ancestry_type=children"
        valid, r = self.do_request("GET", self.query_url + "sources" + query_string)
        if not valid:
            return test.FAIL("Query API failed to respond to query")
        elif r.status_code == 501:
            return test.OPTIONAL("Query API signalled that it does not support ancestry queries.",
                                 "https://github.com/AMWA-TV/nmos/wiki/IS-04#registries-ancestry-queries")
        elif r.status_code == 400:
            return test.OPTIONAL("Query API signalled that it refused to support this ancestry query: "
                                 "{}".format(query_string),
                                 "https://github.com/AMWA-TV/nmos/wiki/IS-04#registries-ancestry-queries")
        elif r.status_code != 200:
            raise NMOSTestException(test.FAIL("Query API returned an unexpected response: "
                                              "{} {}".format(r.status_code, r.text)))
        elif len(r.json()) > 0:
            return test.FAIL("Query API returned more records than expected for query: {}".format(query_string))

        return test.PASS()

    def test_26(self):
        """Posting resource without parent results in 400"""
        test = Test("Registration API responds with 400 HTTP code on posting a resource without parent")

        api = self.apis[REG_API_KEY]

        resources = ["device", "source", "flow", "sender", "receiver"]
        if self.is04_reg_utils.compare_api_version(api["version"], "v2.0") < 0:
            for curr_resource in resources:
                resource_json = deepcopy(self.test_data[curr_resource])
                if self.is04_reg_utils.compare_api_version(api["version"], "v1.2") < 0:
                    resource_json = self.downgrade_resource(curr_resource, resource_json,
                                                            self.apis[REG_API_KEY]["version"])

                resource_json["id"] = str(uuid.uuid4())

                # Set random uuid for parent (depending on resource type and version)
                if curr_resource == "device":
                    resource_json["node_id"] = str(uuid.uuid4())
                elif curr_resource == "flow":
                    if self.is04_reg_utils.compare_api_version(api["version"], "v1.0") > 0:
                        resource_json["device_id"] = str(uuid.uuid4())
                    resource_json["source_id"] = str(uuid.uuid4())
                else:
                    resource_json["device_id"] = str(uuid.uuid4())

                self.post_resource(test, curr_resource, resource_json, 400)

            return test.PASS()

        else:
            return test.FAIL("Version > 1 not supported yet.")

    @test_depends
    def test_27(self):
        """Node and sub-resources should be removed after a timeout because of missing heartbeats"""
        test = Test("Registration API cleans up Nodes and their sub-resources when a heartbeat doesn’t occur for "
                    "the duration of a fixed timeout period")

        api = self.apis[REG_API_KEY]

        if self.is04_reg_utils.compare_api_version(api["version"], "v2.0") < 0:
            resources = ["node", "device", "source", "flow", "sender", "receiver"]

            # Check if all resources are registered
            for resource in resources:
                resource_json = deepcopy(self.test_data[resource])
                curr_id = resource_json["id"]

                valid, r = self.do_request("GET", self.query_url + "{}s/{}".format(resource, curr_id))
                if not valid or r.status_code != 200:
                    return test.FAIL("Cannot execute test, as expected resources are not registered")

            # Wait for garbage collection
            sleep(GARBAGE_COLLECTION_TIMEOUT + 0.5)

            # Verify all resources are removed
            for resource in resources:
                resource_json = deepcopy(self.test_data[resource])
                curr_id = resource_json["id"]

                valid, r = self.do_request("GET", self.query_url + "{}s/{}".format(resource, curr_id))
                if valid:
                    if r.status_code != 404:
                        return test.FAIL("Query API returned not 404 on a resource which should have been "
                                         "removed due to missing heartbeats")
                else:
                    return test.FAIL("Query API returned an unexpected response: {} {}".format(r.status_code, r.text))
            return test.PASS()
        else:
            return test.FAIL("Version > 1 not supported yet.")

    def test_28(self):
        """Child-resources of a Node which unregistered it's resources in an incorrect order must be removed by
        the registry"""
        test = Test("Registry removes stale child-resources of an incorrectly unregistered Node")

        api = self.apis[REG_API_KEY]

        if self.is04_reg_utils.compare_api_version(api["version"], "v2.0") < 0:
            resources = ["node", "device", "source", "flow", "sender", "receiver"]

            # Post all resources
            for resource in resources:
                resource_json = deepcopy(self.test_data[resource])
                if self.is04_reg_utils.compare_api_version(api["version"], "v1.2") < 0:
                    resource_json = self.downgrade_resource(resource, resource_json,
                                                            self.apis[REG_API_KEY]["version"])

                self.post_resource(test, resource, resource_json)

            # Remove Node
            valid, r = self.do_request("DELETE", self.reg_url + "resource/nodes/{}"
                                       .format(self.test_data["node"]["id"]))
            if not valid:
                return test.FAIL("Registration API did not respond as expected: Cannot delete Node: {}"
                                 .format(r))
            elif r.status_code != 204:
                return test.FAIL("Registration API did not respond as expected: Cannot delete Node: {} {}"
                                 .format(r.status_code, r.text))

            # Check if node and all child_resources are removed
            for resource in resources:
                valid, r = self.do_request("GET", self.query_url + "{}s/{}".format(resource,
                                                                                   self.test_data[resource]["id"]))
                if valid:
                    if r.status_code != 404:
                        return test.FAIL("Query API returned not 404 on a resource which should have been "
                                         "removed because parent resource was deleted")
                else:
                    return test.FAIL("Query API did not respond as expected")
            return test.PASS()
        else:
            return test.FAIL("Version > 1 not supported yet.")

    def test_29(self):
        """Query API supports websocket subscription request"""
        test = Test("Query API supports request of a websocket subscription")

        api = self.apis[REG_API_KEY]

        if self.is04_reg_utils.compare_api_version(api["version"], "v2.0") < 0:
            sub_json = deepcopy(self.subscription_data)
            if self.is04_reg_utils.compare_api_version(api["version"], "v1.2") < 0:
                sub_json = self.downgrade_resource("subscription", sub_json, self.apis[REG_API_KEY]["version"])

            valid, r = self.do_request("POST", "{}subscriptions".format(self.query_url), data=sub_json)
            if not valid:
                return test.FAIL("Query API did not respond as expected")
            elif r.status_code == 200 or r.status_code == 201:
                # Test if subscription is available
                sub_id = r.json()["id"]
                valid, r = self.do_request("GET", "{}subscriptions/{}".format(self.query_url, sub_id))
                if not valid:
                    return test.FAIL("Query API did not respond as expected")
                elif r.status_code == 200:
                    return test.PASS()
                else:
                    return test.FAIL("Query API does not provide requested subscription: {} {}"
                                     .format(r.status_code, r.text))
            else:
                return test.FAIL("Query API returned an unexpected response: {} {}".format(r.status_code, r.text))
        else:
            return test.FAIL("Version > 1 not supported yet.")

    def test_30(self):
        """Registration API accepts heartbeat requests for a Node held in the registry"""
        test = Test("Registration API accepts heartbeat requests for a Node held in the registry")

        api = self.apis[REG_API_KEY]
        if self.is04_reg_utils.compare_api_version(api["version"], "v2.0") < 0:
            node_json = deepcopy(self.test_data["node"])
            if self.is04_reg_utils.compare_api_version(api["version"], "v1.2") < 0:
                node_json = self.downgrade_resource("node", node_json, self.apis[REG_API_KEY]["version"])

            # Post Node
            self.post_resource(test, "node", node_json)

            # Post heartbeat
            valid, r = self.do_request("POST", "{}health/nodes/{}".format(self.reg_url, node_json["id"]))
            if not valid:
                return test.FAIL("Registration API did not respond as expected")
            elif r.status_code == 200:
                return test.PASS()
            else:
                return test.FAIL("Registration API returned an unexpected response: {} {}"
                                 .format(r.status_code, r.text))
        else:
            return test.FAIL("Version > 1 not supported yet.")

    def test_31(self):
        """Query API sends correct websocket event messages for UNCHANGED (SYNC), ADDED, MODIFIED and REMOVED"""

        test = Test("Query API sends correct websocket event messages for UNCHANGED (SYNC), ADDED, MODIFIED "
                    "and REMOVED")
        api = self.apis[QUERY_API_KEY]
        if self.is04_reg_utils.compare_api_version(api["version"], "v2.0") < 0:

            # Check for clean state // delete resources if needed
            resource_types = ["node", "device", "source", "flow", "sender", "receiver"]
            for curr_resource in resource_types:
                valid, r = self.do_request("GET", "{}{}s/{}".format(self.query_url,
                                                                    curr_resource,
                                                                    self.test_data[curr_resource]["id"]))
                if not valid:
                    return test.FAIL("Query API returned an unexpected response: {}".format(r))
                elif r.status_code == 200:
                    valid_delete, r_delete = self.do_request("DELETE", "{}resource/{}s/{}"
                                                             .format(self.reg_url,
                                                                     curr_resource,
                                                                     self.test_data[curr_resource]["id"]))
                    if not valid_delete:
                        return test.FAIL("Registration API returned an unexpected response: {}".format(r_delete))
                    elif r_delete.status_code != 204:
                        return test.FAIL("Cannot delete resources. Cannot execute test: {} {}"
                                         .format(r_delete.status_code, r_delete.text))
                elif r.status_code == 404:
                    pass
                else:
                    return test.FAIL("Query API returned an unexpected response: {} {}. Cannot execute test."
                                     .format(r.status_code, r.text))

            # Request websocket subscription / ws_href on resource topic
            test_data = deepcopy(self.test_data)

            websockets = dict()
            resources_to_post = ["node", "device", "source", "flow", "sender", "receiver"]

            for resource in resources_to_post:
                sub_json = deepcopy(self.subscription_data)
                sub_json["resource_path"] = "/{}s".format(resource)
                valid, r = self.do_request("POST", "{}subscriptions".format(self.query_url), data=sub_json)

                if not valid:
                    return test.FAIL("Query API returned an unexpected response: {}".format(r))
                else:
                    if r.status_code == 200 or r.status_code == 201:
                        websockets[resource] = WebsocketWorker(r.json()["ws_href"])
                    else:
                        return test.FAIL("Cannot request websocket subscriptions. Cannot execute test: {} {}"
                                         .format(r.status_code, r.text))

            # Post sample data
            for resource in resources_to_post:
                self.post_resource(test, resource, test_data[resource], 201)

            # Verify if corresponding message received via websocket: UNCHANGED (SYNC)

            # Load schema
            if self.is04_reg_utils.compare_api_version(api["version"], "v1.0") == 0:
                schema = load_resolved_schema(self.apis[QUERY_API_KEY]["spec_path"],
                                              "queryapi-v1.0-subscriptions-websocket.json")
            else:
                schema = load_resolved_schema(self.apis[QUERY_API_KEY]["spec_path"],
                                              "queryapi-subscriptions-websocket.json")

            for resource, resource_data in test_data.items():
                websockets[resource].start()
                sleep(0.5)
                if websockets[resource].did_error_occur():
                    return test.FAIL("Error opening websocket: {}".format(websockets[resource].get_error_message()))

                received_messages = websockets[resource].get_messages()

                # Validate received data against schema
                for message in received_messages:
                    try:
                        self.validate_schema(json.loads(message), schema)
                    except ValidationError as e:
                        return test.FAIL("Received event message is invalid: {}".format(str(e)))

                # Verify data inside messages
                grain_data = list()

                for curr_msg in received_messages:
                    json_msg = json.loads(curr_msg)
                    grain_data.extend(json_msg["grain"]["data"])

                found_data_set = False
                for curr_data in grain_data:
                    pre_data = json.dumps(curr_data["pre"], sort_keys=True)
                    post_data = json.dumps(curr_data["post"], sort_keys=True)
                    sorted_resource_data = json.dumps(resource_data, sort_keys=True)

                    if pre_data == sorted_resource_data:
                        if post_data == sorted_resource_data:
                            found_data_set = True

                if not found_data_set:
                    return test.FAIL("Did not found expected data set in websocket UNCHANGED (SYNC) message for '{}'"
                                     .format(resource))

            # Verify if corresponding message received via websocket: MODIFIED
            old_resource_data = deepcopy(test_data)  # Backup old resource data for later comparison
            for resource, resource_data in test_data.items():
                # Update resource
                self.post_resource(test, resource, resource_data, 200)

            sleep(1)

            for resource, resource_data in test_data.items():
                received_messages = websockets[resource].get_messages()

                # Validate received data against schema
                for message in received_messages:
                    try:
                        self.validate_schema(json.loads(message), schema)
                    except ValidationError as e:
                        return test.FAIL("Received event message is invalid: {}".format(str(e)))

                # Verify data inside messages
                grain_data = list()

                for curr_msg in received_messages:
                    json_msg = json.loads(curr_msg)
                    grain_data.extend(json_msg["grain"]["data"])

                found_data_set = False
                for curr_data in grain_data:
                    pre_data = json.dumps(curr_data["pre"], sort_keys=True)
                    post_data = json.dumps(curr_data["post"], sort_keys=True)
                    sorted_resource_data = json.dumps(resource_data, sort_keys=True)
                    sorted_old_resource_data = json.dumps(old_resource_data[resource], sort_keys=True)

                    if pre_data == sorted_old_resource_data:
                        if post_data == sorted_resource_data:
                            found_data_set = True

                if not found_data_set:
                    return test.FAIL("Did not found expected data set in websocket MODIFIED message for '{}'"
                                     .format(resource))

            # Verify if corresponding message received via websocket: REMOVED
            reversed_resource_list = deepcopy(resources_to_post)
            reversed_resource_list.reverse()
            for resource in reversed_resource_list:
                valid, r = self.do_request("DELETE", self.reg_url + "resource/{}s/{}".format(resource,
                                                                                             test_data[resource]["id"]))
                if not valid:
                    return test.FAIL("Registration API did not respond as expected: Cannot delete {}: {}"
                                     .format(resource, r))
                elif r.status_code != 204:
                    return test.FAIL("Registration API did not respond as expected: Cannot delete {}: {} {}"
                                     .format(resource, r.status_code, r.text))

            sleep(1)
            for resource, resource_data in test_data.items():
                received_messages = websockets[resource].get_messages()

                # Validate received data against schema
                for message in received_messages:
                    try:
                        self.validate_schema(json.loads(message), schema)
                    except ValidationError as e:
                        return test.FAIL("Received event message is invalid: {}".format(str(e)))

                # Verify data inside messages
                grain_data = list()

                for curr_msg in received_messages:
                    json_msg = json.loads(curr_msg)
                    grain_data.extend(json_msg["grain"]["data"])

                found_data_set = False
                for curr_data in grain_data:
                    pre_data = json.dumps(curr_data["pre"], sort_keys=True)
                    sorted_resource_data = json.dumps(resource_data, sort_keys=True)

                    if pre_data == sorted_resource_data:
                        if "post" not in curr_data:
                            found_data_set = True

                if not found_data_set:
                    return test.FAIL("Did not found expected data set in websocket REMOVED message for '{}'"
                                     .format(resource))

            # Verify if corresponding message received via Websocket: ADDED
            # Post sample data again
            for resource in resources_to_post:
                # Recreate resource with updated version
                self.bump_resource_version(test_data[resource])
                self.post_resource(test, resource, test_data[resource], 201)

            sleep(1)
            for resource, resource_data in test_data.items():
                received_messages = websockets[resource].get_messages()

                # Validate received data against schema
                for message in received_messages:
                    try:
                        self.validate_schema(json.loads(message), schema)
                    except ValidationError as e:
                        return test.FAIL("Received event message is invalid: {}".format(str(e)))

                grain_data = list()
                # Verify data inside messages
                for curr_msg in received_messages:
                    json_msg = json.loads(curr_msg)
                    grain_data.extend(json_msg["grain"]["data"])

                found_data_set = False
                for curr_data in grain_data:
                    post_data = json.dumps(curr_data["post"], sort_keys=True)
                    sorted_resource_data = json.dumps(resource_data, sort_keys=True)

                    if post_data == sorted_resource_data:
                        if "pre" not in curr_data:
                            found_data_set = True

                if not found_data_set:
                    return test.FAIL("Did not found expected data set in websocket ADDED message for '{}'"
                                     .format(resource))

                    # Tear down
            for k, v in websockets.items():
                v.close()

            return test.PASS()
        else:
            return test.FAIL("Version > 1 not supported yet.")

    def load_resource_data(self):
        """Loads test data from files"""
        result_data = dict()
        resources = ["node", "device", "source", "flow", "sender", "receiver"]
        for resource in resources:
            with open("test_data/IS0402/v1.2_{}.json".format(resource)) as resource_data:
                resource_json = json.load(resource_data)
                if self.is04_reg_utils.compare_api_version(self.apis[REG_API_KEY]["version"], "v1.2") < 0:
                    resource_json = self.downgrade_resource(resource, resource_json,
                                                            self.apis[REG_API_KEY]["version"])

                result_data[resource] = resource_json
        return result_data

    def load_subscription_request_data(self):
        """Loads subscription request data"""
        with open("test_data/IS0402/subscriptions_request.json") as resource_data:
            resource_json = json.load(resource_data)
            if self.is04_reg_utils.compare_api_version(self.apis[QUERY_API_KEY]["version"], "v1.2") < 0:
                return self.downgrade_resource("subscription", resource_json, self.apis[QUERY_API_KEY]["version"])
            return resource_json

    def do_400_check(self, test, resource_type, data):
        valid, r = self.do_request("POST", self.reg_url + "resource", data={"type": resource_type, "data": data})

        if not valid:
            return test.FAIL(r)

        if r.status_code != 400:
            return test.FAIL("Registration API returned a {} code for an invalid registration".format(r.status_code))

        schema = self.get_schema(REG_API_KEY, "POST", "/resource", 400)
        valid, message = self.check_response(schema, "POST", r)

        if valid:
            return test.PASS()
        else:
            return test.FAIL(message)

    def downgrade_resource(self, resource_type, data, requested_version):
        """Downgrades given resource data to requested version"""
        version_major, version_minor = [int(x) for x in requested_version[1:].split(".")]

        if version_major == 1:
            if resource_type == "node":
                if version_minor <= 1:
                    keys_to_remove = [
                        "interfaces"
                    ]
                    for key in keys_to_remove:
                        if key in data:
                            del data[key]
                if version_minor == 0:
                    keys_to_remove = [
                        "api",
                        "clocks",
                        "description",
                        "tags"
                    ]
                    for key in keys_to_remove:
                        if key in data:
                            del data[key]
                return data

            elif resource_type == "device":
                if version_minor <= 1:
                    pass
                if version_minor == 0:
                    keys_to_remove = [
                        "controls",
                        "description",
                        "tags"
                    ]
                    for key in keys_to_remove:
                        if key in data:
                            del data[key]
                return data

            elif resource_type == "sender":
                if version_minor <= 1:
                    keys_to_remove = [
                        "caps",
                        "interface_bindings",
                        "subscription"
                    ]
                    for key in keys_to_remove:
                        if key in data:
                            del data[key]
                if version_minor == 0:
                    pass
                return data

            elif resource_type == "receiver":
                if version_minor <= 1:
                    keys_to_remove = [
                        "interface_bindings"
                    ]
                    for key in keys_to_remove:
                        if key in data:
                            del data[key]
                    if "subscription" in data and "active" in data["subscription"]:
                        del data["subscription"]["active"]
                if version_minor == 0:
                    pass
                return data

            elif resource_type == "source":
                if version_minor <= 1:
                    pass
                if version_minor == 0:
                    keys_to_remove = [
                        "channels",
                        "clock_name",
                        "grain_rate"
                    ]
                    for key in keys_to_remove:
                        if key in data:
                            del data[key]
                return data

            elif resource_type == "flow":
                if version_minor <= 1:
                    pass
                if version_minor == 0:
                    keys_to_remove = [
                        "bit_depth",
                        "colorspace",
                        "components",
                        "device_id",
                        "DID_SDID",
                        "frame_height",
                        "frame_width",
                        "grain_rate",
                        "interlace_mode",
                        "media_type",
                        "sample_rate",
                        "transfer_characteristic"
                    ]
                    for key in keys_to_remove:
                        if key in data:
                            del data[key]
                return data

            elif resource_type == "subscription":
                if version_minor <= 1:
                    pass
                if version_minor == 0:
                    keys_to_remove = [
                        "secure"
                    ]
                    for key in keys_to_remove:
                        if key in data:
                            del data[key]
                return data

        # Invalid request
        return None

    def bump_resource_version(self, resource):
        """Bump version timestamp of the given resource"""
        v = [int(i) for i in resource["version"].split(':')]
        v[1] += 1
        if v[1] == 1e9:
            v[0] += 1
            v[1] = 0
        resource["version"] = str(v[0]) + ':' + str(v[1])

    def post_resource(self, test, type, data, code = None):
        """Perform a POST request on the Registration API to create or update a resource registration"""

        # As a convenience, bump the version if this is expected to be an update
        if code == 200:
            self.bump_resource_version(data)

        valid, r = self.do_request("POST", self.reg_url + "resource",
                                   data = {"type": type, "data": data})
        if not valid:
            raise NMOSTestException(test.FAIL("Registration API did not respond as expected"))

        expected_codes = [200, 201] if code is None else [code]
        wrong_codes = [_ for _ in [200, 201] if _ not in expected_codes]

        if r.status_code in wrong_codes:
            raise NMOSTestException(test.FAIL("Registration API returned wrong HTTP code"))
        elif r.status_code not in expected_codes:
            raise NMOSTestException(test.FAIL("Registration API returned an unexpected response: "
                                              "{} {}".format(r.status_code, r.text)))
