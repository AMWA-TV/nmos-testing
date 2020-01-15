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

import re
import socket
import uuid
from requests.compat import json
from copy import deepcopy
from time import sleep
from jsonschema import ValidationError
from urllib.parse import urlparse
from zeroconf_monkey import ServiceBrowser, Zeroconf

from .. import Config as CONFIG
from ..MdnsListener import MdnsListener
from ..GenericTest import GenericTest, NMOSTestException, NMOSInitException, NMOS_WIKI_URL
from ..IS04Utils import IS04Utils
from ..TestHelper import WebsocketWorker, load_resolved_schema
from ..TestResult import Test

REG_API_KEY = "registration"
QUERY_API_KEY = "query"


class IS0402Test(GenericTest):
    """
    Runs IS-04-02-Test
    """
    def __init__(self, apis):
        # Don't auto-test /health/nodes/{nodeId} as it's impossible to automatically gather test data
        omit_paths = ["/health/nodes/{nodeId}"]
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

    def do_dns_sd_advertisement_check(self, test, api, service_type):
        """Registration API advertises correctly via mDNS"""

        if CONFIG.DNS_SD_MODE != "multicast":
            return test.DISABLED("This test cannot be performed when DNS_SD_MODE is not 'multicast'")

        ServiceBrowser(self.zc, service_type, self.zc_listener)
        sleep(CONFIG.DNS_SD_BROWSE_TIMEOUT)
        serv_list = self.zc_listener.get_service_list()
        for service in serv_list:
            address = socket.inet_ntoa(service.address)
            port = service.port
            if address == api["ip"] and port == api["port"]:
                properties = self.convert_bytes(service.properties)
                if "pri" not in properties:
                    return test.FAIL("No 'pri' TXT record found in {} advertisement.".format(api["name"]))
                try:
                    priority = int(properties["pri"])
                    if priority < 0:
                        return test.FAIL("Priority ('pri') TXT record must be greater than zero.")
                    elif priority >= 100:
                        return test.WARNING("Priority ('pri') TXT record must be less than 100 for a production "
                                            "instance.")
                except Exception:
                    return test.FAIL("Priority ('pri') TXT record is not an integer.")

                # Other TXT records only came in for IS-04 v1.1+
                if self.is04_reg_utils.compare_api_version(api["version"], "v1.1") >= 0:
                    if "api_ver" not in properties:
                        return test.FAIL("No 'api_ver' TXT record found in {} advertisement.".format(api["name"]))
                    elif api["version"] not in properties["api_ver"].split(","):
                        return test.FAIL("Registry does not claim to support version under test.")

                    if "api_proto" not in properties:
                        return test.FAIL("No 'api_proto' TXT record found in {} advertisement.".format(api["name"]))
                    elif properties["api_proto"] != self.protocol:
                        return test.FAIL("API protocol ('api_proto') TXT record is not '{}'.".format(self.protocol))

                if self.is04_reg_utils.compare_api_version(api["version"], "v1.3") >= 0:
                    if "api_auth" not in properties:
                        return test.FAIL("No 'api_auth' TXT record found in {} advertisement.".format(api["name"]))
                    elif not isinstance(properties["api_auth"], bool):
                        # zeroconf translates 'true' to True and 'false' to False automatically
                        return test.FAIL("API authorization ('api_auth') TXT record is not one of 'true' or 'false'.")

                return test.PASS()
        return test.FAIL("No matching mDNS announcement found for {} with IP/Port {}:{}."
                         .format(api["name"], api["ip"], api["port"]))

    def test_01(self, test):
        """Registration API advertises correctly via mDNS"""

        api = self.apis[REG_API_KEY]

        service_type = "_nmos-registration._tcp.local."
        if self.is04_reg_utils.compare_api_version(api["version"], "v1.3") >= 0:
            service_type = "_nmos-register._tcp.local."

        return self.do_dns_sd_advertisement_check(test, api, service_type)

    def test_02(self, test):
        """Query API advertises correctly via mDNS"""

        api = self.apis[QUERY_API_KEY]

        return self.do_dns_sd_advertisement_check(test, api, "_nmos-query._tcp.local.")

    def test_03(self, test):
        """Registration API accepts and stores a valid Node resource"""

        self.do_test_api_v1_x(test)
        self.post_super_resources_and_resource(test, "node", "test_03")
        return test.PASS()

    def test_03_1(self, test):
        """Registration API responds with correct Location header"""

        self.do_test_api_v1_x(test)

        data = self.copy_resource("node")
        data["id"] = str(uuid.uuid4())
        data["description"] = "test_03_1"

        # most tests on the Location header are actually done in every call to post_resource
        location = self.post_resource(test, "node", data, codes=[201])

        # also check an 'https' URL in the Location header has a hostname not an IP address
        if location is not None and location.startswith("https://") and urlparse(location).hostname[-1].isdigit():
            return test.WARNING("Registration API Location header has an IP address not a hostname")

        return test.PASS()

    def test_03_2(self, test):
        """Registration API accepts and stores a valid Node resource containing unicode characters"""

        self.do_test_api_v1_x(test)
        self.post_super_resources_and_resource(test, "node", "test_03_1 😁 😂 😃")
        return test.PASS()

    def test_04(self, test):
        """Registration API rejects an invalid Node resource with a 400 HTTP code"""

        return self.do_400_check(test, "node")

    def test_05(self, test):
        """Registration API accepts and stores a valid Device resource"""

        self.do_test_api_v1_x(test)
        self.post_super_resources_and_resource(test, "device", "test_05")
        return test.PASS()

    def test_06(self, test):
        """Registration API rejects an invalid Device resource with a 400 HTTP code"""

        return self.do_400_check(test, "device")

    def test_07(self, test):
        """Registration API accepts and stores a valid Source resource"""

        self.do_test_api_v1_x(test)
        self.post_super_resources_and_resource(test, "source", "test_07")
        return test.PASS()

    def test_08(self, test):
        """Registration API rejects an invalid Source resource with a 400 HTTP code"""

        return self.do_400_check(test, "source")

    def test_09(self, test):
        """Registration API accepts and stores a valid Flow resource"""

        self.do_test_api_v1_x(test)
        self.post_super_resources_and_resource(test, "flow", "test_09")
        return test.PASS()

    def test_10(self, test):
        """Registration API rejects an invalid Flow resource with a 400 HTTP code"""

        return self.do_400_check(test, "flow")

    def test_11(self, test):
        """Registration API accepts and stores a valid Sender resource"""

        self.do_test_api_v1_x(test)
        self.post_super_resources_and_resource(test, "sender", "test_11")
        return test.PASS()

    def test_11_1(self, test):
        """Registration API accepts and stores a valid Sender resource with null flow_id"""

        self.do_test_api_v1_x(test)
        api = self.apis[REG_API_KEY]

        # v1.1 introduced null for flow_id to "permit Senders without attached Flows
        # to model a Device before internal routing has been performed"

        if self.is04_reg_utils.compare_api_version(api["version"], "v1.1") < 0:
            return test.NA("This test does not apply to v1.0")

        device = self.post_super_resources_and_resource(test, "device", "test_11_1", fail=Test.UNCLEAR)

        data = self.copy_resource("sender")
        data["id"] = str(uuid.uuid4())
        data["description"] = "test_11_1"
        data["device_id"] = device["id"]

        data["flow_id"] = None

        self.post_resource(test, "sender", data, codes=[201])

        return test.PASS()

    def test_12(self, test):
        """Registration API rejects an invalid Sender resource with a 400 HTTP code"""

        return self.do_400_check(test, "sender")

    def test_13(self, test):
        """Registration API accepts and stores a valid Receiver resource"""

        self.do_test_api_v1_x(test)
        self.post_super_resources_and_resource(test, "receiver", "test_13")
        return test.PASS()

    def test_14(self, test):
        """Registration API rejects an invalid Receiver resource with a 400 HTTP code"""

        return self.do_400_check(test, "receiver")

    def test_15(self, test):
        """Registration API responds with 200 HTTP code on updating a registered Node"""

        self.do_test_api_v1_x(test)
        node_data = self.post_super_resources_and_resource(test, "node", "test_15")
        self.post_resource(test, "node", node_data, codes=[200])
        return test.PASS()

    def test_16(self, test):
        """Registration API responds with 200 HTTP code on updating a registered Device"""

        self.do_test_api_v1_x(test)
        device_data = self.post_super_resources_and_resource(test, "device", "test_16")
        self.post_resource(test, "device", device_data, codes=[200])
        return test.PASS()

    def test_17(self, test):
        """Registration API responds with 200 HTTP code on updating a registered Source"""

        self.do_test_api_v1_x(test)
        source_data = self.post_super_resources_and_resource(test, "source", "test_17")
        self.post_resource(test, "source", source_data, codes=[200])
        return test.PASS()

    def test_18(self, test):
        """Registration API responds with 200 HTTP code on updating a registered Flow"""

        self.do_test_api_v1_x(test)
        flow_data = self.post_super_resources_and_resource(test, "flow", "test_18")
        self.post_resource(test, "flow", flow_data, codes=[200])
        return test.PASS()

    def test_19(self, test):
        """Registration API responds with 200 HTTP code on updating a registered Sender"""

        self.do_test_api_v1_x(test)
        sender_data = self.post_super_resources_and_resource(test, "sender", "test_19")
        self.post_resource(test, "sender", sender_data, codes=[200])
        return test.PASS()

    def test_20(self, test):
        """Registration API responds with 200 HTTP code on updating a registered Receiver"""

        self.do_test_api_v1_x(test)
        receiver_data = self.post_super_resources_and_resource(test, "receiver", "test_20")
        self.post_resource(test, "receiver", receiver_data, codes=[200])
        return test.PASS()

    def do_test_paged_trait(self, test):
        """
        Precondition check that the 'paged' trait applies to the API version under test.
        Raises an NMOSTestException when there's an error
        """

        api = self.apis[QUERY_API_KEY]
        if self.is04_query_utils.compare_api_version(api["version"], "v1.1") < 0:
            raise NMOSTestException(test.NA("This test does not apply to v1.0"))
        if self.is04_query_utils.compare_api_version(api["version"], "v2.0") >= 0:
            raise NMOSTestException(test.FAIL("Version > 1 not supported yet."))

    def post_sample_nodes(self, test, count, description, labeller=None):
        """Perform a POST request on the Registration API to register a number of sample nodes"""

        node_data = self.copy_resource("node")
        node_data["description"] = description

        update_timestamps = []
        ids = []

        for _ in range(count):
            ids.append(str(uuid.uuid4()))

            node_data["id"] = ids[-1]
            self.bump_resource_version(node_data)

            if labeller is not None:
                node_data["label"] = labeller(_)

            # For debugging
            node_data["tags"]["index"] = [str(_)]

            self.post_resource(test, "node", node_data, codes=[201])

            # Perform a Query API request to get the update timestamp of the most recently POSTed node
            # Wish there was a better way, as this puts the cart before the horse!
            # Another alternative would be to use local timestamps, provided clocks were synchronised?

            response = self.do_paged_request(limit=1)
            self.do_test_paged_response(test, response,
                                        expected_ids=[node_data["id"]],
                                        expected_since=None, expected_until=None)
            valid, r, query_parameters = response
            update_timestamps.append(r.headers["X-Paging-Until"])

        # Bear in mind that the returned arrays are in forward order
        # whereas Query API responses are required to be in reverse order
        return update_timestamps, ids

    def do_paged_request(self, resource_type="nodes", limit=None, since=None, until=None,
                         description=None, label=None, id=None):
        """Perform a GET request on the Query API"""

        query_parameters = []

        if limit is not None:
            query_parameters.append("paging.limit=" + str(limit))
        if since is not None:
            query_parameters.append("paging.since=" + since)
        if until is not None:
            query_parameters.append("paging.until=" + until)

        if description is not None:
            query_parameters.append("description=" + description)
        if label is not None:
            query_parameters.append("label=" + label)
        if id is not None:
            query_parameters.append("id=" + id)

        query_string = "?" + "&".join(query_parameters) if len(query_parameters) != 0 else ""

        valid, response = self.do_request("GET", self.query_url + resource_type + query_string)

        return valid, response, query_parameters

    def parse_link_header(self, link_header):
        LINK_PATTERN = re.compile('<(?P<url>.+)>;[ \t]*rel="(?P<rel>.+)"')

        return {rel: url for (rel, url) in
                [(match.group("rel"), match.group("url")) for match in
                    [LINK_PATTERN.search(_) for _ in
                        link_header.split(",")] if match]}

    def do_test_paged_response(self, test, paged_response,
                               expected_ids,
                               expected_since, expected_until, expected_limit=None):
        """
        Check the result of a paged request.
        Raises an NMOSTestException when there's an error
        """

        valid, response, query_parameters = paged_response

        query_string = "?" + "&".join(query_parameters) if len(query_parameters) != 0 else ""

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
                                                  NMOS_WIKI_URL + "/IS-04#registries-pagination"))
        elif response.status_code != 200:
            raise NMOSTestException(test.FAIL("Query API returned an unexpected response: "
                                              "{} {}".format(response.status_code, response.text)))

        # check *presence* of paging headers before checking response body

        PAGING_HEADERS = ["Link", "X-Paging-Limit", "X-Paging-Since", "X-Paging-Until"]

        absent_paging_headers = [_ for _ in PAGING_HEADERS if _ not in response.headers]
        if (len(absent_paging_headers) == len(PAGING_HEADERS)):
            raise NMOSTestException(test.OPTIONAL("Query API response did not include any pagination headers. "
                                                  "Query APIs should support pagination for scalability.",
                                                  NMOS_WIKI_URL + "/IS-04#registries-pagination"))
        elif (len(absent_paging_headers) != 0):
            raise NMOSTestException(test.FAIL("Query API response did not include all pagination headers, "
                                              "missing: {}".format(absent_paging_headers)))

        # check response body

        if expected_ids is not None:
            try:
                if len(response.json()) != len(expected_ids):
                    raise NMOSTestException(test.FAIL("Query API response did not include the correct number of "
                                                      "resources, for query: {}".format(query_string)))

                for i in range(len(response.json())):
                    if (response.json()[i]["id"]) != expected_ids[-(i + 1)]:
                        raise NMOSTestException(test.FAIL("Query API response did not include the correct resources, "
                                                          "for query: {}".format(query_string)))

            except json.JSONDecodeError:
                raise NMOSTestException(test.FAIL("Non-JSON response returned"))
            except KeyError:
                raise NMOSTestException(test.FAIL("Query API did not respond as expected, "
                                                  "for query: {}".format(query_string)))

        # check *values* of paging headers after body

        def compare_timestamp(expected, actual):
            return expected is None or self.is04_query_utils.compare_resource_version(expected, actual) == 0

        try:
            since = response.headers["X-Paging-Since"]
            until = response.headers["X-Paging-Until"]
            limit = response.headers["X-Paging-Limit"]

            if not compare_timestamp(expected_since, since):
                raise NMOSTestException(test.FAIL("Query API response did not include the correct X-Paging-Since "
                                                  "header, for query: {}".format(query_string)))

            if not compare_timestamp(expected_until, until):
                raise NMOSTestException(test.FAIL("Query API response did not include the correct X-Paging-Until "
                                                  "header, for query: {}".format(query_string)))

            if not (expected_limit is None or str(expected_limit) == limit):
                raise NMOSTestException(test.FAIL("Query API response did not include the correct X-Paging-Limit "
                                                  "header, for query: {}".format(query_string)))

            link_header = self.parse_link_header(response.headers["Link"])

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

                if not link_header[rel].startswith(self.protocol + "://"):
                    raise NMOSTestException(test.FAIL("Query API Link header is invalid for the current protocol. "
                                                      "Expected '{}://'".format(self.protocol)))

                if "paging.limit=" + limit not in link_header[rel]:
                    raise NMOSTestException(test.FAIL("Query API response did not include the correct '{}' value "
                                                      "in the Link header, for query: {}".format(rel, query_string)))

                for param in query_parameters:
                    if "paging." in param:
                        continue
                    if param not in link_header[rel]:
                        raise NMOSTestException(test.FAIL("Query API response did not include the correct '{}' value "
                                                          "in the Link header, for query: {}"
                                                          .format(rel, query_string)))

        except KeyError as ex:
            raise NMOSTestException(test.FAIL("Query API response did not include the expected value "
                                              "in the Link header: {}".format(ex)))

    def test_21_1(self, test):
        """Query API implements pagination (no query or paging parameters)"""

        self.do_test_paged_trait(test)

        # Perform a query with no query or paging parameters (see note in do_test_paged_response regarding 501)
        response = self.do_paged_request()

        # Check whether the response contains the X-Paging- headers but don't check values
        self.do_test_paged_response(test, response,
                                    expected_ids=None,
                                    expected_since=None, expected_until=None, expected_limit=None)

        return test.PASS()

    def test_21_1_1(self, test):
        """Query API implements pagination (when explicitly requested)"""

        self.do_test_paged_trait(test)

        # Same as above, but query with paging.limit to clearly 'opt in'
        response = self.do_paged_request(limit=10)

        # Check whether the response contains the X-Paging- headers but don't check values
        self.do_test_paged_response(test, response,
                                    expected_ids=None,
                                    expected_since=None, expected_until=None, expected_limit=None)

        return test.PASS()

    def test_21_2(self, test):
        """Query API implements pagination (documentation examples)"""

        self.do_test_paged_trait(test)
        description = "test_21_2"

        # Initial test cases based on the examples in NMOS documentation
        # See https://github.com/AMWA-TV/nmos-discovery-registration/blob/v1.2.x/docs/2.5.%20APIs%20-%20Query%20Parameters.md#pagination # noqa: E501

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
        response = self.do_paged_request(description=description, limit=10)
        self.do_test_paged_response(test, response,
                                    expected_ids=ids[11:20 + 1],
                                    expected_since=ts[10], expected_until=ts[20], expected_limit=10)

        # Example 2: Request With Custom Limit

        response = self.do_paged_request(description=description, limit=5)
        self.do_test_paged_response(test, response,
                                    expected_ids=ids[16:20 + 1],
                                    expected_since=ts[15], expected_until=ts[20], expected_limit=5)

        # Example 3: Request With Since Parameter

        response = self.do_paged_request(description=description, since=ts[4], limit=10)
        self.do_test_paged_response(test, response,
                                    expected_ids=ids[5:14 + 1],
                                    expected_since=ts[4], expected_until=ts[14], expected_limit=10)

        # Example 4: Request With Until Parameter

        response = self.do_paged_request(description=description, until=ts[16], limit=10)
        self.do_test_paged_response(test, response,
                                    expected_ids=ids[7:16 + 1],
                                    expected_since=ts[6], expected_until=ts[16], expected_limit=10)

        # Example 5: Request With Since & Until Parameters

        response = self.do_paged_request(description=description, since=ts[4], until=ts[16], limit=10)
        self.do_test_paged_response(test, response,
                                    expected_ids=ids[5:14 + 1],
                                    expected_since=ts[4], expected_until=ts[14], expected_limit=10)

        return test.PASS()

    def test_21_3(self, test):
        """Query API implements pagination (edge cases)"""

        self.do_test_paged_trait(test)
        description = "test_21_3"

        # Some additional test cases based on Basecamp discussion
        # See https://basecamp.com/1791706/projects/10192586/messages/70545892

        timestamps, ids = self.post_sample_nodes(test, 20, description)

        after = "{}:0".format(int(timestamps[-1].split(":")[0]) + 1)
        before = "{}:0".format(int(timestamps[0].split(":")[0]) - 1)

        # Check the header values when a client specifies a paging.since value after the newest resource's timestamp

        self.do_test_paged_response(test, self.do_paged_request(description=description, since=after),
                                    expected_ids=[],
                                    expected_since=after, expected_until=after)

        # Check the header values when a client specifies a paging.until value before the oldest resource's timestamp

        self.do_test_paged_response(test, self.do_paged_request(description=description, until=before),
                                    expected_ids=[],
                                    expected_since="0:0", expected_until=before)

        # Check the header values for a query that results in only one resource, without any paging parameters

        # expected_until check could be more forgiving, i.e. >= timestamps[-1] and <= 'now'
        self.do_test_paged_response(test, self.do_paged_request(id=ids[12]),
                                    expected_ids=[ids[12]],
                                    expected_since="0:0", expected_until=timestamps[-1])

        # Check the header values for a query that results in no resources, without any paging parameters

        # expected_until check could be more forgiving, i.e. >= timestamps[-1] and <= 'now'
        self.do_test_paged_response(test, self.do_paged_request(id=str(uuid.uuid4())),
                                    expected_ids=[],
                                    expected_since="0:0", expected_until=timestamps[-1])

        return test.PASS()

    def test_21_4(self, test):
        """Query API implements pagination (requests that require empty responses)"""

        self.do_test_paged_trait(test)
        description = "test_21_4"

        timestamps, ids = self.post_sample_nodes(test, 20, description)

        ts = timestamps[12]

        # Check paging.since == paging.until

        response = self.do_paged_request(description=description, since=ts, until=ts, limit=10)
        self.do_test_paged_response(test, response,
                                    expected_ids=[],
                                    expected_since=ts, expected_until=ts, expected_limit=10)

        # Check paging.limit == 0, paging.since specified

        response = self.do_paged_request(description=description, since=ts, limit=0)
        self.do_test_paged_response(test, response,
                                    expected_ids=[],
                                    expected_since=ts, expected_until=ts, expected_limit=0)

        # Check paging.limit == 0, paging.since not specified

        response = self.do_paged_request(description=description, until=ts, limit=0)
        self.do_test_paged_response(test, response,
                                    expected_ids=[],
                                    expected_since=ts, expected_until=ts, expected_limit=0)

        return test.PASS()

    def test_21_5(self, test):
        """Query API implements pagination (filters that select discontiguous resources)"""

        self.do_test_paged_trait(test)
        description = "test_21_5"

        def foo(index):
            return 3 > (index + 1) % 5

        def bar(index):
            return not foo(index)

        ts, ids = self.post_sample_nodes(test, 20, description, lambda index: "foo" if foo(index) else "bar")

        # Specify paging.limit in the requests with 'default paging parameters' in the following tests
        # because we can't rely on the implementation's default being 10

        # Query 1: "foo", default paging parameters
        #          filter         0, 1, -, -, 4, 5, 6, -, -, 9, 10, 11, --, --, 14, 15, 16, --, --, 19
        #          request      (                                                                      ]
        #          response           (       ^  ^  ^        ^   ^   ^           ^   ^   ^           ^ ]

        # expected_until check could be more forgiving, i.e. >= ts[19] and <= 'now'
        # expected_since check could be more forgiving, i.e. >= ts[1] and < ts[4]
        self.do_test_paged_response(test, self.do_paged_request(label="foo", limit=10),
                                    expected_ids=[ids[i] for i in range(len(ids)) if foo(i)][-10:],
                                    expected_since=ts[1], expected_until=ts[19], expected_limit=10)

        # Query 2: 'prev' of Query 1
        #          filter         0, 1, -, -, 4, 5, 6, -, -, 9, 10, 11, --, --, 14, 15, 16, --, --, 19
        #          request      (      ]
        #          response     ( ^  ^ ]

        self.do_test_paged_response(test, self.do_paged_request(label="foo", until=ts[1], limit=10),
                                    expected_ids=[ids[i] for i in range(len(ids)) if foo(i)][0:-10],
                                    expected_since="0:0", expected_until=ts[1], expected_limit=10)

        # Query 3: 'next' of Query 1
        #          filter         0, 1, -, -, 4, 5, 6, -, -, 9, 10, 11, --, --, 14, 15, 16, --, --, 19
        #          request                                                                            (]
        #          response                                                                           (]

        self.do_test_paged_response(test, self.do_paged_request(label="foo", since=ts[19], limit=10),
                                    expected_ids=[],
                                    expected_since=ts[19], expected_until=ts[19], expected_limit=10)

        # Query 4: "bar", default paging parameters
        #          filter         -, -, 2, 3, -, -, -, 7, 8, -, --, --, 12, 13, --, --, --, 17, 18, --
        #          request      (                                                                      ]
        #          response     (       ^  ^           ^  ^              ^   ^               ^   ^     ]

        # expected_until check could be more forgiving, i.e. >= ts[19] and <= 'now'
        self.do_test_paged_response(test, self.do_paged_request(label="bar", limit=10),
                                    expected_ids=[ids[i] for i in range(len(ids)) if bar(i)],
                                    expected_since="0:0", expected_until=ts[19], expected_limit=10)

        # Query 5: "bar", limited to 3
        #          filter         -, -, 2, 3, -, -, -, 7, 8, -, --, --, 12, 13, --, --, --, 17, 18, --
        #          request      (                                                                      ]
        #          response                                               (  ^               ^   ^     ]

        # expected_until check could be more forgiving, i.e. >= ts[18] and <= 'now'
        # expected_since check could be more forgiving, i.e. >= ts[12] and < ts[13]
        self.do_test_paged_response(test, self.do_paged_request(label="bar", limit=3),
                                    expected_ids=[ids[13], ids[17], ids[18]],
                                    expected_since=ts[12], expected_until=ts[19], expected_limit=3)

        # Query 6: 'prev' of Query 5
        #          filter         -, -, 2, 3, -, -, -, 7, 8, -, --, --, 12, 13, --, --, --, 17, 18, --
        #          request      (                                          ]
        #          response                 (          ^  ^              ^ ]

        # expected_since check could be more forgiving, i.e. >= ts[3] and < ts[7]
        self.do_test_paged_response(test, self.do_paged_request(label="bar", until=ts[12], limit=3),
                                    expected_ids=[ids[7], ids[8], ids[12]],
                                    expected_since=ts[3], expected_until=ts[12], expected_limit=3)

        # Query 7: like Query 5, with paging.since specified, but still enough matches
        #          filter         -, -, 2, 3, -, -, -, 7, 8, -, --, --, 12, 13, --, --, --, 17, 18, --
        #          request                     (                           ]
        #          response                    (       ^  ^              ^ ]

        self.do_test_paged_response(test, self.do_paged_request(label="bar", since=ts[4], until=ts[12], limit=3),
                                    expected_ids=[ids[7], ids[8], ids[12]],
                                    expected_since=ts[4], expected_until=ts[12], expected_limit=3)

        # Query 8: like Query 5, with paging.since specified, and not enough matches
        #          filter         -, -, 2, 3, -, -, -, 7, 8, -, --, --, 12, 13, --, --, --, 17, 18, --
        #          request                                    (            ]
        #          response                                   (          ^ ]

        self.do_test_paged_response(test, self.do_paged_request(label="bar", since=ts[9], until=ts[12], limit=3),
                                    expected_ids=[ids[12]],
                                    expected_since=ts[9], expected_until=ts[12], expected_limit=3)

        # Query 9: like Query 5, but no matches
        #          filter         -, -, 2, 3, -, -, -, 7, 8, -, --, --, 12, 13, --, --, --, 17, 18, --
        #          request                                    (        ]
        #          response                                   (        ]

        self.do_test_paged_response(test, self.do_paged_request(label="bar", since=ts[9], until=ts[11], limit=3),
                                    expected_ids=[],
                                    expected_since=ts[9], expected_until=ts[11], expected_limit=3)

        return test.PASS()

    def test_21_6(self, test):
        """Query API implements pagination (bad requests)"""

        self.do_test_paged_trait(test)

        before = self.is04_query_utils.get_TAI_time()
        after = self.is04_query_utils.get_TAI_time(1)

        # Specifying since after until is a bad request
        valid, response, query_parameters = self.do_paged_request(since=after, until=before)

        query_string = "?" + "&".join(query_parameters) if len(query_parameters) != 0 else ""

        if not valid:
            raise NMOSTestException(test.FAIL("Query API did not respond as expected, "
                                              "for query: {}".format(query_string)))

        if response.status_code == 501:
            raise NMOSTestException(test.OPTIONAL("Query API signalled that it does not support this query: {}. "
                                                  "Query APIs should support pagination for scalability."
                                                  .format(query_string),
                                                  NMOS_WIKI_URL + "/IS-04#registries-pagination"))

        # 200 OK *without* any paging headers also indicates not implemented (paging parameters ignored)
        PAGING_HEADERS = ["Link", "X-Paging-Limit", "X-Paging-Since", "X-Paging-Until"]

        absent_paging_headers = [_ for _ in PAGING_HEADERS if _ not in response.headers]
        if response.status_code == 200 and len(absent_paging_headers) == len(PAGING_HEADERS):
            raise NMOSTestException(test.OPTIONAL("Query API response did not include any pagination headers. "
                                                  "Query APIs should support pagination for scalability.",
                                                  NMOS_WIKI_URL + "/IS-04#registries-pagination"))

        # 200 OK *with* any paging headers indicates the Query API failed to identify the bad request
        # which is an error like any code other than the expected 400 Bad Request
        if response.status_code != 400:
            raise NMOSTestException(test.FAIL("Query API responded with wrong HTTP code, "
                                              "for query: {}".format(query_string)))

        return test.PASS()

    def test_21_7(self, test):
        """Query API implements pagination (updates between paged requests)"""

        self.do_test_paged_trait(test)
        description = "test_21_7"

        count = 3
        ts, ids = self.post_sample_nodes(test, count, description)

        # initial paged request

        response = self.do_paged_request(description=description, limit=count)
        self.do_test_paged_response(test, response,
                                    expected_ids=ids,
                                    expected_since="0:0", expected_until=ts[-1], expected_limit=count)

        resources = response[1].json()  # valid json guaranteed by do_test_paged_response
        resources.reverse()

        # 'next' page should be empty

        response = self.do_paged_request(description=description, limit=count, since=ts[-1])
        self.do_test_paged_response(test, response,
                                    expected_ids=[],
                                    expected_since=ts[-1], expected_until=None, expected_limit=count)

        # 'current' page should be same as initial response

        response = self.do_paged_request(description=description, limit=count, until=ts[-1])
        self.do_test_paged_response(test, response,
                                    expected_ids=ids,
                                    expected_since=None, expected_until=ts[-1], expected_limit=count)

        # after an update, the 'next' page should now contain only the updated resource

        self.post_resource(test, "node", resources[1], codes=[200])

        response = self.do_paged_request(description=description, limit=count, since=ts[-1])
        self.do_test_paged_response(test, response,
                                    expected_ids=[ids[1]],
                                    expected_since=ts[-1], expected_until=None, expected_limit=count)

        # and what was the 'current' page should now contain only the unchanged resources

        response = self.do_paged_request(description=description, limit=count, until=ts[-1])
        self.do_test_paged_response(test, response,
                                    expected_ids=[ids[0], ids[2]],
                                    expected_since=None, expected_until=ts[-1], expected_limit=count)

        # after the other resources are also updated, what was the 'current' page should now be empty

        self.post_resource(test, "node", resources[2], codes=[200])
        self.post_resource(test, "node", resources[0], codes=[200])

        response = self.do_paged_request(description=description, limit=count, until=ts[-1])
        self.do_test_paged_response(test, response,
                                    expected_ids=[],
                                    expected_since=None, expected_until=ts[-1], expected_limit=count)

        # and what was the 'next' page should now contain all the resources in the update order

        response = self.do_paged_request(description=description, limit=count, since=ts[-1])
        self.do_test_paged_response(test, response,
                                    expected_ids=[ids[1], ids[2], ids[0]],
                                    expected_since=ts[-1], expected_until=None, expected_limit=count)

        return test.PASS()

    def test_21_8(self, test):
        """Query API implements pagination (correct encoding of URLs in Link header)"""

        self.do_test_paged_trait(test)

        # check '&' is returned encoded
        response = self.do_paged_request(label="foo%26bar")
        self.do_test_paged_response(test, response,
                                    expected_ids=None,
                                    expected_since=None, expected_until=None)

        return test.PASS()

    def test_21_9(self, test):
        """Query API implements pagination (correct protocol and IP/hostname in Link header)"""

        self.do_test_paged_trait(test)

        response = self.do_paged_request()
        # most tests on the Link header are actually done in every call to do_test_paged_response
        self.do_test_paged_response(test, response,
                                    expected_ids=None,
                                    expected_since=None, expected_until=None)

        # also check 'https' URLs in the Link header have a hostname not an IP address
        link_header = self.parse_link_header(response[1].headers["Link"])

        for rel in ["first", "prev", "next", "last"]:
            if rel not in link_header:
                continue

            if link_header[rel].startswith("https://") and urlparse(link_header[rel]).hostname[-1].isdigit():
                return test.WARNING("Query API Link header has an IP address not a hostname")

        return test.PASS()

    def test_22(self, test):
        """Query API implements downgrade queries"""

        reg_api = self.apis[REG_API_KEY]
        query_api = self.apis[QUERY_API_KEY]

        if query_api["version"] == "v1.0":
            return test.NA("This test does not apply to v1.0")

        # Find the API versions supported by the Reg API
        try:
            valid, r = self.do_request("GET", self.reg_url.rstrip(reg_api["version"] + "/"))
            if not valid:
                return test.FAIL("Registration API failed to respond to request")
            else:
                reg_versions = [version.rstrip("/") for version in r.json()]
        except json.JSONDecodeError:
            return test.FAIL("Non-JSON response returned")

        # Sort the list and remove API versions higher than the one under test
        reg_versions = self.is04_reg_utils.sort_versions(reg_versions)
        for api_version in list(reg_versions):
            if self.is04_reg_utils.compare_api_version(api_version, reg_api["version"]) > 0:
                reg_versions.remove(api_version)

        # Find the API versions supported by the Query API
        try:
            valid, r = self.do_request("GET", self.query_url.rstrip(query_api["version"] + "/"))
            if not valid:
                return test.FAIL("Query API failed to respond to request")
            else:
                query_versions = [version.rstrip("/") for version in r.json()]
        except json.JSONDecodeError:
            return test.FAIL("Non-JSON response returned")

        # Sort the list and remove API versions higher than the one under test
        query_versions = self.is04_query_utils.sort_versions(query_versions)
        for api_version in list(query_versions):
            if self.is04_query_utils.compare_api_version(api_version, query_api["version"]) > 0:
                query_versions.remove(api_version)

        # If we're testing the lowest API version, exit with an N/A or warning indicating we can't test at this level
        if query_versions[0] == query_api["version"]:
            return test.NA("Downgrade queries are unnecessary when requesting from the lowest supported version of "
                           "a Query API")

        # Exit if the Registration API doesn't support the required versions
        for api_version in query_versions:
            if api_version not in reg_versions:
                return test.MANUAL("This test cannot run automatically as the Registration API does not support all "
                                   "of the API versions that the Query API does",
                                   NMOS_WIKI_URL + "/IS-04#registries-downgrade-queries")

        # Register a Node at each API version available (up to the version under test)
        node_ids = {}
        test_id = str(uuid.uuid4())
        for api_version in query_versions:
            # Note: We iterate over the Query API versions, not the Reg API as it's the Query API that's under test
            test_data = self.copy_resource("node", api_ver=api_version)
            test_data["id"] = str(uuid.uuid4())
            test_data["description"] = test_id
            node_ids[api_version] = test_data["id"]

            reg_url = "{}/{}/".format(self.reg_url.rstrip(reg_api["version"] + "/"), api_version)
            self.post_resource(test, "node", test_data, codes=[201], reg_url=reg_url)

        # Make a request to the Query API for each Node POSTed to ensure it's visible (or not) at the version under test
        for api_version in query_versions:
            valid, r = self.do_request("GET", self.query_url + "nodes/{}".format(node_ids[api_version]))
            if not valid:
                return test.FAIL("Query API failed to respond to request")
            else:
                if r.status_code == 200 and api_version != query_api["version"]:
                    return test.FAIL("Query API incorrectly exposed a {} resource at {}"
                                     .format(api_version, query_api["version"]))
                elif r.status_code == 404 and api_version == query_api["version"]:
                    return test.FAIL("Query API failed to expose a {} resource at {}"
                                     .format(api_version, query_api["version"]))
                elif r.status_code not in [200, 404, 409]:
                    return test.FAIL("Query API returned an unexpected response code: {}".format(r.status_code))

        # Make a request with downgrades turned on for each API version down to the minimum
        # Raise an error if resources below the requested version are returned, or those for the relevant API versions
        # are not returned. Otherwise pass.
        for api_version in query_versions:
            valid, r = self.do_request(
                "GET",
                self.query_url + "nodes/{}?query.downgrade={}".format(node_ids[api_version], api_version)
            )
            if not valid:
                return test.FAIL("Query API failed to respond to request")
            elif self.is04_query_utils.compare_api_version(query_api["version"], "v1.3") >= 0 and r.status_code == 501:
                return test.OPTIONAL("Query API signalled that it does not support downgrade queries. This may be "
                                     "important for multi-version support.",
                                     NMOS_WIKI_URL + "/IS-04#registries-downgrade-queries")
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

            try:
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
                            return test.FAIL("Query API exposed a Node from a lower version than expected when "
                                             "downgrading to {}".format(api_version))
                        expected_nodes.remove(node["id"])
                    if len(expected_nodes) > 0:
                        return test.FAIL("Query API failed to expose an expected Node when downgrading to {}"
                                         .format(api_version))
            except json.JSONDecodeError:
                return test.FAIL("Non-JSON response returned")

        return test.PASS()

    def test_22_1(self, test):
        """Query API subscriptions resource does not support downgrade queries"""

        api = self.apis[QUERY_API_KEY]
        if api["version"] == "v1.0":
            return test.NA("This test does not apply to v1.0")

        # Find the API versions supported by the Query API
        try:
            valid, r = self.do_request("GET", self.query_url.rstrip(api["version"] + "/"))
            if not valid:
                return test.FAIL("Query API failed to respond to request")
            else:
                query_versions = [version.rstrip("/") for version in r.json()]
        except json.JSONDecodeError:
            return test.FAIL("Non-JSON response returned")

        # Sort the list and remove API versions higher than the one under test
        query_versions = self.is04_query_utils.sort_versions(query_versions)
        for api_version in list(query_versions):
            if self.is04_query_utils.compare_api_version(api_version, api["version"]) > 0:
                query_versions.remove(api_version)

        # If we're testing the lowest API version, exit with an N/A or warning indicating we can't test at this level
        if query_versions[0] == api["version"]:
            return test.NA("Downgrade queries are unnecessary when requesting from the lowest supported version of "
                           "a Query API")

        # Generate a subscription at the API version under test and the version below that
        valid_sub_id = None
        invalid_sub_id = None
        sub_json = self.prepare_subscription("/nodes")
        resp_json = self.post_subscription(test, sub_json)
        valid_sub_id = resp_json["id"]

        previous_version = query_versions[-2]
        query_sub_url = self.query_url.replace(api["version"], previous_version)
        sub_json = self.prepare_subscription("/nodes", api_ver=previous_version)
        resp_json = self.post_subscription(test, sub_json, query_url=query_sub_url)
        invalid_sub_id = resp_json["id"]

        # Test a request to GET subscriptions
        subscription_ids = set()
        valid, r = self.do_request("GET", self.query_url + "subscriptions?query.downgrade={}".format(previous_version))
        if not valid:
            return test.FAIL("Query API failed to respond to request")
        else:
            if r.status_code != 200:
                return test.FAIL("Query API did not respond as expected for subscription GET request: {}"
                                 .format(r.status_code))
            else:
                try:
                    for subscription in r.json():
                        subscription_ids.add(subscription["id"])
                except json.JSONDecodeError:
                    return test.FAIL("Non-JSON response returned")

        if valid_sub_id not in subscription_ids:
            return test.FAIL("Unable to find {} subscription in request to GET /subscriptions?query.downgrade={}"
                             .format(api["version"], previous_version))
        elif invalid_sub_id in subscription_ids:
            return test.FAIL("Found {} subscription in request to GET /subscriptions?query.downgrade={}"
                             .format(previous_version, previous_version))

        return test.PASS()

    def test_22_2(self, test):
        """Query API WebSockets implement downgrade queries"""

        reg_api = self.apis[REG_API_KEY]
        query_api = self.apis[QUERY_API_KEY]

        if query_api["version"] == "v1.0":
            return test.NA("This test does not apply to v1.0")

        # Find the API versions supported by the Reg API
        try:
            valid, r = self.do_request("GET", self.reg_url.rstrip(reg_api["version"] + "/"))
            if not valid:
                return test.FAIL("Registration API failed to respond to request")
            else:
                reg_versions = [version.rstrip("/") for version in r.json()]
        except json.JSONDecodeError:
            return test.FAIL("Non-JSON response returned")

        # Sort the list and remove API versions higher than the one under test
        reg_versions = self.is04_reg_utils.sort_versions(reg_versions)
        for api_version in list(reg_versions):
            if self.is04_reg_utils.compare_api_version(api_version, reg_api["version"]) > 0:
                reg_versions.remove(api_version)

        # Find the API versions supported by the Query API
        try:
            valid, r = self.do_request("GET", self.query_url.rstrip(query_api["version"] + "/"))
            if not valid:
                return test.FAIL("Query API failed to respond to request")
            else:
                query_versions = [version.rstrip("/") for version in r.json()]
        except json.JSONDecodeError:
            return test.FAIL("Non-JSON response returned")

        # Sort the list and remove API versions higher than the one under test
        query_versions = self.is04_query_utils.sort_versions(query_versions)
        for api_version in list(query_versions):
            if self.is04_query_utils.compare_api_version(api_version, query_api["version"]) > 0:
                query_versions.remove(api_version)

        # If we're testing the lowest API version, exit with an N/A or warning indicating we can't test at this level
        if query_versions[0] == query_api["version"]:
            return test.NA("Downgrade queries are unnecessary when requesting from the lowest supported version of "
                           "a Query API")

        # Exit if the Registration API doesn't support the required versions
        for api_version in query_versions:
            if api_version not in reg_versions:
                return test.MANUAL("This test cannot run automatically as the Registration API does not support all "
                                   "of the API versions that the Query API does",
                                   NMOS_WIKI_URL + "/IS-04#registries-downgrade-queries")

        # Request & start websocket subscriptions for each version
        websockets = dict()
        for api_version in query_versions:
            if api_version != query_api["version"]:
                sub_json = self.prepare_subscription("/nodes", params={"query.downgrade": api_version})
            else:
                sub_json = self.prepare_subscription("/nodes")  # No downgrade for version under test
            resp_json = self.post_subscription(test, sub_json)
            websockets[api_version] = WebsocketWorker(resp_json["ws_href"])
            websockets[api_version].start()

        sleep(CONFIG.WS_MESSAGE_TIMEOUT)  # Wait for SYNC messages

        # Verify no error occurred on starting websocket subscription & clear SYNC messages
        for api_version in query_versions:
            if websockets[api_version].did_error_occur():
                return test.FAIL("Error opening websocket: {}".format(websockets[api_version].get_error_message()))
            websockets[api_version].clear_messages()

        # Register a Node at each API version available (up to the version under test)
        node_ids = {}
        test_id = str(uuid.uuid4())
        for api_version in query_versions:
            # Note: We iterate over the Query API versions, not the Reg API as it's the Query API that's under test
            test_data = self.copy_resource("node", api_ver=api_version)
            test_data["id"] = str(uuid.uuid4())
            test_data["description"] = test_id
            node_ids[api_version] = test_data["id"]

            reg_url = "{}/{}/".format(self.reg_url.rstrip(reg_api["version"] + "/"), api_version)
            self.post_resource(test, "node", test_data, codes=[201], reg_url=reg_url)

        sleep(CONFIG.WS_MESSAGE_TIMEOUT)

        # Read data & close websockets
        sub_data = dict()
        for api_version in query_versions:
            received_messages = websockets[api_version].get_messages()
            websockets[api_version].close()
            grain_data = list()

            for curr_msg in received_messages:
                json_msg = json.loads(curr_msg)
                grain_data.extend(json_msg["grain"]["data"])

            sub_data[api_version] = grain_data

        # Verify that all POSTed Nodes are announced via the corresponding websocket sub as expected (incl downgrade)
        for api_version in query_versions:
            expected_nodes = list()
            unexpected_nodes = list()
            for node_api_version, node_id in node_ids.items():
                if self.is04_query_utils.compare_api_version(node_api_version, api_version) >= 0:
                    expected_nodes.append(node_id)
                else:
                    unexpected_nodes.append(node_id)

            # Collect ids of added nodes
            posted_node_ids = list()
            for curr_data in sub_data[api_version]:
                if "pre" not in curr_data and "post" in curr_data:  # Only check the 'Added Event'
                    if "id" in curr_data["post"]:
                        posted_node_ids.append(curr_data["post"]["id"])

            # Check for expected nodes
            for expected_node_id in expected_nodes:
                if expected_node_id not in posted_node_ids:
                    return test.FAIL("Query API failed to announce POSTed Node via websocket subscription.")

            # Check for unexpected nodes
            for unexpected_node_id in unexpected_nodes:
                if unexpected_node_id in posted_node_ids:
                    return test.FAIL("Query API returned an unexpected Node via websocket subscription.")

        return test.PASS()

    def test_23(self, test):
        """Query API implements basic query parameters"""

        node_descriptions = [str(uuid.uuid4()), str(uuid.uuid4())]
        for node_desc in node_descriptions:
            test_data = self.copy_resource("node")
            test_data["id"] = str(uuid.uuid4())
            test_data["label"] = "test_23"
            test_data["description"] = node_desc
            self.post_resource(test, "node", test_data, codes=[201])

        try:
            valid, r = self.do_request("GET", self.query_url + "nodes")
            if not valid:
                return test.FAIL("Query API failed to respond to query")
            elif len(r.json()) < 2:
                return test.UNCLEAR("Fewer Nodes found in registry than expected. Test cannot proceed.")

            query_string = "?description=" + node_descriptions[0]
            valid, r = self.do_request("GET", self.query_url + "nodes" + query_string)
            api = self.apis[QUERY_API_KEY]
            if not valid:
                return test.FAIL("Query API failed to respond to query")
            elif self.is04_query_utils.compare_api_version(api["version"], "v1.3") >= 0 and r.status_code == 501:
                return test.OPTIONAL("Query API signalled that it does not support basic queries. This may be "
                                     "important for scalability.",
                                     NMOS_WIKI_URL + "/IS-04#registries-basic-queries")
            elif r.status_code != 200:
                raise NMOSTestException(test.FAIL("Query API returned an unexpected response: "
                                                  "{} {}".format(r.status_code, r.text)))
            elif len(r.json()) != 1:
                return test.FAIL("Query API returned {} records for query {} when 1 was expected"
                                 .format(len(r.json()), query_string))
        except json.JSONDecodeError:
            return test.FAIL("Non-JSON response returned")

        return test.PASS()

    def test_23_1(self, test):
        """Query API WebSockets implement basic query parameters"""

        api = self.apis[QUERY_API_KEY]

        # Perform a basic test for APIs <= v1.2 checking for support
        try:
            valid, r = self.do_request("GET", self.query_url + "nodes?description={}".format(str(uuid.uuid4())))
            if not valid:
                return test.FAIL("Query API failed to respond to query")
            elif r.status_code == 200 and len(r.json()) > 0 or r.status_code != 200:
                return test.OPTIONAL("Query API signalled that it does not support basic queries. This may be "
                                     "important for scalability.",
                                     NMOS_WIKI_URL + "/IS-04#registries-basic-queries")
        except json.JSONDecodeError:
            return test.FAIL("Non-JSON response returned")

        # Create subscription to a specific Node description
        node_ids = [str(uuid.uuid4()), str(uuid.uuid4())]
        sub_json = self.prepare_subscription("/nodes", params={"description": node_ids[0]})
        resp_json = self.post_subscription(test, sub_json)

        websocket = WebsocketWorker(resp_json["ws_href"])
        try:
            websocket.start()
            sleep(CONFIG.WS_MESSAGE_TIMEOUT)
            if websocket.did_error_occur():
                return test.FAIL("Error opening websocket: {}".format(websocket.get_error_message()))

            # Discard SYNC messages
            received_messages = websocket.get_messages()

            # Register a matching Node and one non-matching Node
            for node_id in node_ids:
                test_data = self.copy_resource("node")
                test_data["id"] = node_id
                test_data["label"] = "test_23_1"
                test_data["description"] = node_id
                self.post_resource(test, "node", test_data, codes=[201])

            # Load schema
            if self.is04_reg_utils.compare_api_version(api["version"], "v1.0") == 0:
                schema = load_resolved_schema(api["spec_path"],
                                              "queryapi-v1.0-subscriptions-websocket.json")
            else:
                schema = load_resolved_schema(api["spec_path"],
                                              "queryapi-subscriptions-websocket.json")

            # Check that the single Node is reflected in the subscription
            sleep(CONFIG.WS_MESSAGE_TIMEOUT)
            received_messages = websocket.get_messages()

            if len(received_messages) < 1:
                return test.FAIL("Expected at least one message via WebSocket subscription")

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

            for curr_data in grain_data:
                if "pre" in curr_data:
                    return test.FAIL("Unexpected 'pre' key encountered in WebSocket message")
                if "post" not in curr_data:
                    return test.FAIL("Expected 'post' key not found in WebSocket message")
                post_data = curr_data["post"]
                if post_data["description"] != node_ids[0]:
                    return test.FAIL("Node 'post' 'description' received via WebSocket did not match "
                                     "the basic query filter")

            # Update the Node to no longer have that description
            test_data = self.copy_resource("node")
            test_data["id"] = node_ids[0]
            test_data["label"] = "test_23_1"
            test_data["description"] = str(uuid.uuid4)
            self.post_resource(test, "node", test_data, codes=[200])

            # Ensure it disappears from the subscription
            sleep(CONFIG.WS_MESSAGE_TIMEOUT)
            received_messages = websocket.get_messages()

            if len(received_messages) < 1:
                return test.FAIL("Expected at least one message via WebSocket subscription")

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

            for curr_data in grain_data:
                if "pre" not in curr_data:
                    return test.FAIL("Expected 'pre' key not found in WebSocket message")
                if "post" in curr_data:
                    return test.FAIL("Unexpected 'post' key encountered in WebSocket message")
                pre_data = curr_data["pre"]
                if pre_data["description"] != node_ids[0]:
                    return test.FAIL("Node 'pre' 'description' received via WebSocket did not match "
                                     "the basic query filter")

        finally:
            if websocket:
                websocket.close()

        return test.PASS()

    def test_24(self, test):
        """Query API implements RQL"""

        if self.apis[QUERY_API_KEY]["version"] == "v1.0":
            return test.NA("This test does not apply to v1.0")

        node_descriptions = [str(uuid.uuid4()), str(uuid.uuid4())]
        for node_desc in node_descriptions:
            test_data = self.copy_resource("node")
            test_data["id"] = str(uuid.uuid4())
            test_data["label"] = "test_24"
            test_data["description"] = node_desc
            self.post_resource(test, "node", test_data, codes=[201])

        try:
            valid, r = self.do_request("GET", self.query_url + "nodes")
            if not valid:
                return test.FAIL("Query API failed to respond to query")
            elif len(r.json()) < 2:
                return test.UNCLEAR("Fewer Nodes found in registry than expected. Test cannot proceed.")

            query_string = "?query.rql=eq(description," + str(node_descriptions[0]) + ")"
            valid, r = self.do_request("GET", self.query_url + "nodes" + query_string)
            if not valid:
                return test.FAIL("Query API failed to respond to query")
            elif r.status_code == 501:
                return test.OPTIONAL("Query API signalled that it does not support RQL queries. This may be "
                                     "important for scalability.",
                                     NMOS_WIKI_URL + "/IS-04#registries-resource-query-language-rql")
            elif r.status_code == 400:
                return test.OPTIONAL("Query API signalled that it refused to support this RQL query: "
                                     "{}".format(query_string),
                                     NMOS_WIKI_URL + "/IS-04#registries-resource-query-language-rql")
            elif r.status_code != 200:
                raise NMOSTestException(test.FAIL("Query API returned an unexpected response: "
                                                  "{} {}".format(r.status_code, r.text)))
            elif len(r.json()) != 1:
                return test.FAIL("Query API returned {} records for query {} when 1 was expected"
                                 .format(len(r.json()), query_string))
        except json.JSONDecodeError:
            return test.FAIL("Non-JSON response returned")

        return test.PASS()

    def test_24_1(self, test):
        """Query API WebSockets implement RQL"""

        api = self.apis[QUERY_API_KEY]

        # Perform a basic test for APIs <= v1.2 checking for support
        try:
            valid, r = self.do_request("GET", self.query_url + "nodes?query.rql=eq(description,{})"
                                                               .format(str(uuid.uuid4())))
            if not valid:
                return test.FAIL("Query API failed to respond to query")
            elif r.status_code == 200 and len(r.json()) > 0 or r.status_code != 200:
                return test.OPTIONAL("Query API signalled that it does not support RQL queries. This may be "
                                     "important for scalability.",
                                     NMOS_WIKI_URL + "/IS-04#registries-resource-query-language-rql")
        except json.JSONDecodeError:
            return test.FAIL("Non-JSON response returned")

        # Create subscription to a specific Node description
        node_ids = [str(uuid.uuid4()), str(uuid.uuid4())]
        query_string = "eq(description," + str(node_ids[0]) + ")"
        sub_json = self.prepare_subscription("/nodes", params={"query.rql": query_string})
        resp_json = self.post_subscription(test, sub_json)

        websocket = WebsocketWorker(resp_json["ws_href"])
        try:
            websocket.start()
            sleep(CONFIG.WS_MESSAGE_TIMEOUT)
            if websocket.did_error_occur():
                return test.FAIL("Error opening websocket: {}".format(websocket.get_error_message()))

            # Discard SYNC messages
            received_messages = websocket.get_messages()

            # Register a matching Node and one non-matching Node
            for node_id in node_ids:
                test_data = self.copy_resource("node")
                test_data["id"] = node_id
                test_data["label"] = "test_24_1"
                test_data["description"] = node_id
                self.post_resource(test, "node", test_data, codes=[201])

            # Load schema
            if self.is04_reg_utils.compare_api_version(api["version"], "v1.0") == 0:
                schema = load_resolved_schema(api["spec_path"],
                                              "queryapi-v1.0-subscriptions-websocket.json")
            else:
                schema = load_resolved_schema(api["spec_path"],
                                              "queryapi-subscriptions-websocket.json")

            # Check that the single Node is reflected in the subscription
            sleep(CONFIG.WS_MESSAGE_TIMEOUT)
            received_messages = websocket.get_messages()

            if len(received_messages) < 1:
                return test.FAIL("Expected at least one message via WebSocket subscription")

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

            for curr_data in grain_data:
                if "pre" in curr_data:
                    return test.FAIL("Unexpected 'pre' key encountered in WebSocket message")
                if "post" not in curr_data:
                    return test.FAIL("Expected 'post' key not found in WebSocket message")
                post_data = curr_data["post"]
                if post_data["description"] != node_ids[0]:
                    return test.FAIL("Node 'post' 'description' received via WebSocket did not match the RQL filter")

            # Update the Node to no longer have that description
            test_data = self.copy_resource("node")
            test_data["id"] = node_ids[0]
            test_data["label"] = "test_24_1"
            test_data["description"] = str(uuid.uuid4)
            self.post_resource(test, "node", test_data, codes=[200])

            # Ensure it disappears from the subscription
            sleep(CONFIG.WS_MESSAGE_TIMEOUT)
            received_messages = websocket.get_messages()

            if len(received_messages) < 1:
                return test.FAIL("Expected at least one message via WebSocket subscription")

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

            for curr_data in grain_data:
                if "pre" not in curr_data:
                    return test.FAIL("Expected 'pre' key not found in WebSocket message")
                if "post" in curr_data:
                    return test.FAIL("Unexpected 'post' key encountered in WebSocket message")
                pre_data = curr_data["pre"]
                if pre_data["description"] != node_ids[0]:
                    return test.FAIL("Node 'pre' 'description' received via WebSocket did not match the RQL filter")
        finally:
            if websocket:
                websocket.close()

        return test.PASS()

    def test_25(self, test):
        """Query API implements ancestry queries"""

        if self.apis[QUERY_API_KEY]["version"] == "v1.0":
            return test.NA("This test does not apply to v1.0")

        try:
            valid, r = self.do_request("GET", self.query_url + "sources")
            if not valid:
                return test.FAIL("Query API failed to respond to query")
            elif len(r.json()) == 0:
                return test.UNCLEAR("No Sources found in registry. Test cannot proceed.")

            random_label = uuid.uuid4()
            query_string = "?query.ancestry_id=" + str(random_label) + "&query.ancestry_type=children"
            valid, r = self.do_request("GET", self.query_url + "sources" + query_string)
            if not valid:
                return test.FAIL("Query API failed to respond to query")
            elif r.status_code == 501:
                return test.OPTIONAL("Query API signalled that it does not support ancestry queries.",
                                     NMOS_WIKI_URL + "/IS-04#registries-ancestry-queries")
            elif r.status_code == 400:
                return test.OPTIONAL("Query API signalled that it refused to support this ancestry query: "
                                     "{}".format(query_string),
                                     NMOS_WIKI_URL + "/IS-04#registries-ancestry-queries")
            elif r.status_code != 200:
                raise NMOSTestException(test.FAIL("Query API returned an unexpected response: "
                                                  "{} {}".format(r.status_code, r.text)))
            elif len(r.json()) > 0:
                return test.FAIL("Query API returned more records than expected for query: {}".format(query_string))
        except json.JSONDecodeError:
            return test.FAIL("Non-JSON response returned")

        return test.PASS()

    def test_25_1(self, test):
        """Query API WebSockets implement ancestry queries"""

        return test.MANUAL()

    def test_26(self, test):
        """Registration API responds with 400 HTTP code on posting a resource without parent"""

        self.do_test_api_v1_x(test)
        api = self.apis[REG_API_KEY]

        resources = ["device", "source", "flow", "sender", "receiver"]

        for curr_resource in resources:
            resource_json = self.copy_resource(curr_resource)
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

            self.post_resource(test, curr_resource, resource_json, codes=[400])

        return test.PASS()

    def test_27(self, test):
        """Registration API cleans up Nodes and their sub-resources when a heartbeat doesn't occur for
        the duration of a fixed timeout period"""

        self.do_test_api_v1_x(test)

        resources = ["node", "device", "source", "flow", "sender", "receiver"]

        # (Re-)post all resources
        for resource in resources:
            self.post_resource(test, resource, codes=[200, 201])

        # Check if all resources are registered
        for resource in resources:
            curr_id = self.test_data[resource]["id"]

            valid, r = self.do_request("GET", self.query_url + "{}s/{}".format(resource, curr_id))
            if not valid or r.status_code != 200:
                return test.FAIL("Cannot execute test, as expected resources are not registered")

        # Wait for garbage collection (plus one whole second, since health is in whole seconds so
        # a registry may wait that much longer to guarantee a minimum garbage collection interval)
        sleep(CONFIG.GARBAGE_COLLECTION_TIMEOUT + 1)

        # Verify all resources are removed
        for resource in resources:
            curr_id = self.test_data[resource]["id"]

            valid, r = self.do_request("GET", self.query_url + "{}s/{}".format(resource, curr_id))
            if valid:
                if r.status_code != 404:
                    return test.FAIL("Query API did not return 404 on a resource which should have been "
                                     "removed due to missing heartbeats")
            else:
                return test.FAIL("Query API returned an unexpected response: {} {}".format(r.status_code, r.text))
        return test.PASS()

    def test_28(self, test):
        """Registry removes stale child-resources of an incorrectly unregistered Node"""

        self.do_test_api_v1_x(test)

        resources = ["node", "device", "source", "flow", "sender", "receiver"]

        # (Re-)post all resources
        for resource in resources:
            self.post_resource(test, resource, codes=[200, 201])

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
                    return test.FAIL("Query API did not return 404 on a resource which should have been "
                                     "removed because parent resource was deleted")
            else:
                return test.FAIL("Query API did not respond as expected")
        return test.PASS()

    def test_29(self, test):
        """Query API supports websocket subscription request"""

        self.do_test_api_v1_x(test)
        api = self.apis[QUERY_API_KEY]

        sub_json = self.prepare_subscription("/nodes")
        resp_json = self.post_subscription(test, sub_json)
        # Check protocol
        if self.is04_query_utils.compare_api_version(api["version"], "v1.1") >= 0:
            if resp_json["secure"] is not CONFIG.ENABLE_HTTPS:
                return test.FAIL("Subscription 'secure' value is incorrect for the current protocol")
        if not resp_json["ws_href"].startswith(self.ws_protocol + "://"):
            return test.FAIL("Subscription 'ws_href' value does not match the current WebSocket protocol")

        # Check IP/hostname
        ws_href_hostname_warn = False
        if resp_json["ws_href"].startswith("wss://") and urlparse(resp_json["ws_href"]).hostname[-1].isdigit():
            ws_href_hostname_warn = True

        # Test if subscription is available
        sub_id = resp_json["id"]
        valid, r = self.do_request("GET", "{}subscriptions/{}".format(self.query_url, sub_id))
        if not valid:
            return test.FAIL("Query API did not respond as expected")
        elif r.status_code == 200:
            if ws_href_hostname_warn:
                return test.WARNING("Subscription 'ws_href' value has an IP address not a hostname")
            return test.PASS()
        else:
            return test.FAIL("Query API did not provide the requested subscription: {}".format(r.status_code))

    def test_29_1(self, test):
        """Query API websocket subscription requests default to the current protocol"""

        self.do_test_api_v1_x(test)
        api = self.apis[QUERY_API_KEY]

        sub_json = self.prepare_subscription("/nodes")
        if "secure" in sub_json:
            del sub_json["secure"]  # This is the key element under test
        resp_json = self.post_subscription(test, sub_json)
        # Check protocol
        if self.is04_query_utils.compare_api_version(api["version"], "v1.1") >= 0:
            if resp_json["secure"] is not CONFIG.ENABLE_HTTPS:
                return test.FAIL("Subscription 'secure' value is incorrect for the current protocol")
        if not resp_json["ws_href"].startswith(self.ws_protocol + "://"):
            return test.FAIL("Subscription 'ws_href' value does not match the current WebSocket protocol")

        return test.PASS()

    def test_30(self, test):
        """Registration API accepts heartbeat requests for a Node held in the registry"""

        self.do_test_api_v1_x(test)

        # Post Node
        self.post_resource(test, "node")

        # Post heartbeat
        valid, r = self.do_request("POST", "{}health/nodes/{}".format(self.reg_url, self.test_data["node"]["id"]))
        if not valid:
            return test.FAIL("Registration API did not respond as expected")
        elif r.status_code == 200:
            schema = self.get_schema(REG_API_KEY, "POST", "/health/nodes/{nodeId}", r.status_code)
            valid, message = self.check_response(schema, "POST", r)
            if valid:
                if message:
                    return test.WARNING(message)
                else:
                    return test.PASS()
            else:
                return test.FAIL(message)
        else:
            return test.FAIL("Registration API returned an unexpected response: {} {}"
                             .format(r.status_code, r.text))

    def test_31(self, test):
        """Query API sends correct websocket event messages for UNCHANGED (SYNC), ADDED, MODIFIED and REMOVED"""

        self.do_test_api_v1_x(test)
        api = self.apis[QUERY_API_KEY]

        # Check for clean state // delete resources if needed
        resource_types = ["node", "device", "source", "flow", "sender", "receiver"]
        for curr_resource in resource_types:
            valid, r = self.do_request(
                "GET",
                "{}{}s/{}".format(
                    self.query_url,
                    curr_resource,
                    self.test_data[curr_resource]["id"]
                )
            )
            if not valid:
                return test.FAIL("Query API returned an unexpected response: {}".format(r))
            elif r.status_code == 200:
                valid_delete, r_delete = self.do_request(
                    "DELETE",
                    "{}resource/{}s/{}".format(
                        self.reg_url,
                        curr_resource,
                        self.test_data[curr_resource]["id"]
                    )
                )
                if not valid_delete:
                    return test.FAIL("Registration API returned an unexpected response: {}".format(r_delete))
                elif r_delete.status_code not in [204, 404]:
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
        try:
            resources_to_post = ["node", "device", "source", "flow", "sender", "receiver"]

            for resource in resources_to_post:
                sub_json = self.prepare_subscription("/{}s".format(resource))
                resp_json = self.post_subscription(test, sub_json)
                websockets[resource] = WebsocketWorker(resp_json["ws_href"])

            # Post sample data
            for resource in resources_to_post:
                self.post_resource(test, resource, test_data[resource], codes=[201])

            # Verify if corresponding message received via websocket: UNCHANGED (SYNC)

            # Load schema
            if self.is04_reg_utils.compare_api_version(api["version"], "v1.0") == 0:
                schema = load_resolved_schema(api["spec_path"],
                                              "queryapi-v1.0-subscriptions-websocket.json")
            else:
                schema = load_resolved_schema(api["spec_path"],
                                              "queryapi-subscriptions-websocket.json")

            for resource in resources_to_post:
                websockets[resource].start()
            sleep(CONFIG.WS_MESSAGE_TIMEOUT)

            for resource, resource_data in test_data.items():
                if websockets[resource].did_error_occur():
                    return test.FAIL("Error opening websocket: {}"
                                     .format(websockets[resource].get_error_message()))

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
                    if "pre" not in curr_data or "post" not in curr_data:
                        continue
                    pre_data = json.dumps(curr_data["pre"], sort_keys=True)
                    post_data = json.dumps(curr_data["post"], sort_keys=True)
                    sorted_resource_data = json.dumps(resource_data, sort_keys=True)

                    if pre_data == sorted_resource_data:
                        if post_data == sorted_resource_data:
                            found_data_set = True

                if not found_data_set:
                    return test.FAIL("Did not find expected data set in websocket UNCHANGED (SYNC) message "
                                     "for '{}'".format(resource))

            # Verify if corresponding message received via websocket: MODIFIED
            old_resource_data = deepcopy(test_data)  # Backup old resource data for later comparison
            for resource, resource_data in test_data.items():
                # Update resource
                self.post_resource(test, resource, resource_data, codes=[200])

            sleep(CONFIG.WS_MESSAGE_TIMEOUT)

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
                    if "pre" not in curr_data or "post" not in curr_data:
                        continue
                    pre_data = json.dumps(curr_data["pre"], sort_keys=True)
                    post_data = json.dumps(curr_data["post"], sort_keys=True)
                    sorted_resource_data = json.dumps(resource_data, sort_keys=True)
                    sorted_old_resource_data = json.dumps(old_resource_data[resource], sort_keys=True)

                    if pre_data == sorted_old_resource_data:
                        if post_data == sorted_resource_data:
                            found_data_set = True

                if not found_data_set:
                    return test.FAIL("Did not find expected data set in websocket MODIFIED message "
                                     "for '{}'".format(resource))

            # Verify if corresponding message received via websocket: REMOVED
            reversed_resource_list = deepcopy(resources_to_post)
            reversed_resource_list.reverse()
            for resource in reversed_resource_list:
                valid, r = self.do_request(
                    "DELETE",
                    self.reg_url + "resource/{}s/{}".format(resource, test_data[resource]["id"])
                )
                if not valid:
                    return test.FAIL("Registration API did not respond as expected: Cannot delete {}: {}"
                                     .format(resource, r))
                elif r.status_code != 204:
                    return test.FAIL("Registration API did not respond as expected: Cannot delete {}: {} {}"
                                     .format(resource, r.status_code, r.text))

            sleep(CONFIG.WS_MESSAGE_TIMEOUT)
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
                    if "pre" not in curr_data:
                        continue
                    pre_data = json.dumps(curr_data["pre"], sort_keys=True)
                    sorted_resource_data = json.dumps(resource_data, sort_keys=True)

                    if pre_data == sorted_resource_data:
                        if "post" not in curr_data:
                            found_data_set = True

                if not found_data_set:
                    return test.FAIL("Did not find expected data set in websocket REMOVED message "
                                     "for '{}'".format(resource))

            # Verify if corresponding message received via Websocket: ADDED
            # Post sample data again
            for resource in resources_to_post:
                # Recreate resource with updated version
                self.bump_resource_version(test_data[resource])
                self.post_resource(test, resource, test_data[resource], codes=[201])

            sleep(CONFIG.WS_MESSAGE_TIMEOUT)
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
                    if "post" not in curr_data:
                        continue
                    post_data = json.dumps(curr_data["post"], sort_keys=True)
                    sorted_resource_data = json.dumps(resource_data, sort_keys=True)

                    if post_data == sorted_resource_data:
                        if "pre" not in curr_data:
                            found_data_set = True

                if not found_data_set:
                    return test.FAIL("Did not find expected data set in websocket ADDED message "
                                     "for '{}'".format(resource))

        finally:
            # Tear down
            for k, v in websockets.items():
                v.close()  # hmm, can raise OSError

        return test.PASS()

    def test_32(self, test):
        """Registration API generates 409 code when a conflicting registration exists"""

        self.do_test_api_v1_x(test)
        api = self.apis[REG_API_KEY]

        if self.is04_reg_utils.compare_api_version(api["version"], "v1.3") < 0:
            return test.NA("This test only applies to API version v1.3+")

        # Find the API versions supported by the Reg API
        try:
            valid, r = self.do_request("GET", self.reg_url.rstrip(api["version"] + "/"))
            if not valid:
                return test.FAIL("Registration API failed to respond to request")
            else:
                reg_versions = [version.rstrip("/") for version in r.json()]
        except json.JSONDecodeError:
            return test.FAIL("Non-JSON response returned")

        # Sort the list and remove the current version under test
        reg_versions = self.is04_reg_utils.sort_versions(reg_versions)
        reg_versions.remove(api["version"])

        if len(reg_versions) == 0:
            return test.NA("This test is only relevant to registries which implement multiple API versions")

        node_id = str(uuid.uuid4())

        # Post Node at a version other than the one under test
        alt_reg_url = "{}/{}/".format(self.reg_url.rstrip(api["version"] + "/"), reg_versions[0])
        alt_node = self.copy_resource("node", reg_versions[0])
        alt_node["id"] = node_id
        self.post_resource(test, "node", alt_node, reg_url=alt_reg_url)

        # Post Node at this version
        test_node = self.copy_resource("node")
        test_node["id"] = node_id
        self.post_resource(test, "node", test_node, codes=[409])

        return test.PASS()

    def load_resource_data(self):
        """Loads test data from files"""
        api = self.apis[REG_API_KEY]
        result_data = dict()
        resources = ["node", "device", "source", "flow", "sender", "receiver"]
        for resource in resources:
            with open("test_data/IS0402/v1.3_{}.json".format(resource)) as resource_data:
                resource_json = json.load(resource_data)
                if self.is04_reg_utils.compare_api_version(api["version"], "v1.3") < 0:
                    resource_json = self.downgrade_resource(resource, resource_json,
                                                            api["version"])

                result_data[resource] = resource_json
        return result_data

    def load_subscription_request_data(self):
        """Loads subscription request data"""
        api = self.apis[QUERY_API_KEY]
        with open("test_data/IS0402/subscriptions_request.json") as resource_data:
            resource_json = json.load(resource_data)
            if self.is04_reg_utils.compare_api_version(api["version"], "v1.3") < 0:
                return self.downgrade_resource("subscription", resource_json, api["version"])
            return resource_json

    def do_400_check(self, test, resource_type):
        # this is a more thorough check that the Registration API implements schema validation than previously
        data = self.copy_resource(resource_type)
        data["id"] = str(uuid.uuid4())
        # to cause schema validation failure, remove the label property (required for all resources since v1.0)
        del data["label"]
        valid, r = self.do_request("POST", self.reg_url + "resource", json={"type": resource_type, "data": data})

        if not valid:
            return test.FAIL(r)

        if r.status_code != 400:
            return test.FAIL("Registration API returned a {} code for an invalid registration".format(r.status_code))

        schema = self.get_schema(REG_API_KEY, "POST", "/resource", r.status_code)
        valid, message = self.check_response(schema, "POST", r)
        if valid:
            if message:
                return test.WARNING(message)
            else:
                return test.PASS()
        else:
            return test.FAIL(message)

    def downgrade_resource(self, resource_type, data, requested_version):
        """Downgrades given resource data to requested version"""
        version_major, version_minor = [int(x) for x in requested_version[1:].split(".")]

        if version_major == 1:
            if resource_type == "node":
                if version_minor <= 2:
                    if "interfaces" in data:
                        key = "attached_network_device"
                        for interface in data["interfaces"]:
                            if key in interface:
                                del interface[key]
                    key = "authorization"
                    for service in data["services"]:
                        if key in service:
                            del service[key]
                    if "api" in data and "endpoints" in data["api"]:
                        for endpoint in data["api"]["endpoints"]:
                            if key in endpoint:
                                del endpoint[key]
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
                if version_minor <= 2:
                    key = "authorization"
                    if "controls" in data:
                        for control in data["controls"]:
                            if key in control:
                                del control[key]
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
                if version_minor <= 2:
                    pass
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
                if version_minor <= 2:
                    pass
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
                if version_minor <= 2:
                    keys_to_remove = [
                        "event_type"
                    ]
                    for key in keys_to_remove:
                        if key in data:
                            del data[key]
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
                if version_minor <= 2:
                    keys_to_remove = [
                        "event_type"
                    ]
                    for key in keys_to_remove:
                        if key in data:
                            del data[key]
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
                if version_minor <= 2:
                    keys_to_remove = [
                        "authorization"
                    ]
                    for key in keys_to_remove:
                        if key in data:
                            del data[key]
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

    def copy_resource(self, type, api_ver=None):
        """Make a clone of the test data for the requested type and API version"""
        if api_ver is None:
            api_ver = self.apis[REG_API_KEY]["version"]
        data = deepcopy(self.test_data[type])
        if self.is04_reg_utils.compare_api_version(api_ver, "v1.3") < 0:
            data = self.downgrade_resource(type, data, api_ver)
        return data

    def bump_resource_version(self, resource):
        """Bump version timestamp of the given resource"""
        resource["version"] = self.is04_reg_utils.get_TAI_time()

    def prepare_subscription(self, resource_path, params=None, api_ver=None):
        """Prepare an object ready to send as the request body for a Query API subscription"""
        if params is None:
            params = {}
        if api_ver is None:
            api_ver = self.apis[QUERY_API_KEY]["version"]
        sub_json = deepcopy(self.subscription_data)
        sub_json["resource_path"] = resource_path
        sub_json["params"] = params
        sub_json["secure"] = CONFIG.ENABLE_HTTPS
        if self.is04_query_utils.compare_api_version(api_ver, "v1.3") < 0:
            sub_json = self.downgrade_resource("subscription", sub_json, api_ver)
        return sub_json

    def post_subscription(self, test, sub_json, query_url=None):
        """Perform a POST request to a Query API to create a subscription"""
        if query_url is None:
            query_url = self.query_url

        api_ver = query_url.rstrip("/").rsplit("/", 1)[-1]

        valid, r = self.do_request("POST", "{}subscriptions".format(query_url), json=sub_json)

        if not valid:
            raise NMOSTestException(test.FAIL("Query API returned an unexpected response: {}".format(r)))

        if r.status_code in [200, 201]:
            if self.is04_query_utils.compare_api_version(api_ver, "v1.3") >= 0:
                if "Location" not in r.headers:
                    raise NMOSTestException(test.FAIL("Query API failed to return a 'Location' response header"))
                path = "{}subscriptions/".format(urlparse(query_url).path)
                location = r.headers["Location"]
                if path not in location:
                    raise NMOSTestException(test.FAIL("Query API 'Location' response header is incorrect: "
                                                      "Location: {}".format(location)))
                if not location.startswith("/") and not location.startswith(self.protocol + "://"):
                    raise NMOSTestException(test.FAIL("Query API 'Location' response header is invalid for the "
                                                      "current protocol: Location: {}".format(location)))
        elif r.status_code in [400, 501]:
            raise NMOSTestException(test.FAIL("Query API signalled that it does not support the requested "
                                              "subscription parameters: {} {}".format(r.status_code, sub_json)))
        else:
            raise NMOSTestException(test.FAIL("Query API returned an unexpected response: "
                                              "{} {}".format(r.status_code, r.text)))

        # Currently can only validate schema for the API version under test
        if query_url == self.query_url:
            schema = self.get_schema(QUERY_API_KEY, "POST", "/subscriptions", r.status_code)
            valid, message = self.check_response(schema, "POST", r)
            if valid:
                # if message:
                #     return WARNING somehow...
                pass
            else:
                raise NMOSTestException(test.FAIL(message))

        try:
            return r.json()
        except json.JSONDecodeError:
            raise NMOSTestException(test.FAIL("Non-JSON response returned for Query API subscription request"))

    def post_resource(self, test, type, data=None, reg_url=None, codes=None, fail=Test.FAIL):
        """
        Perform a POST request on the Registration API to create or update a resource registration.
        Raises an NMOSTestException when the response is not as expected.
        Otherwise, returns value of Location header for successful requests
        """

        if not data:
            data = self.copy_resource(type)

        if not reg_url:
            reg_url = self.reg_url

        if not codes:
            codes = [200, 201]

        # As a convenience, bump the version if this is allowed to be an update
        if 200 in codes:
            self.bump_resource_version(data)

        valid, r = self.do_request("POST", reg_url + "resource",
                                   json={"type": type, "data": data})
        if not valid:
            raise NMOSTestException(fail(test, "Registration API returned an unexpected response: {}".format(r)))

        location = None

        wrong_codes = [_ for _ in [200, 201] if _ not in codes]

        if r.status_code in wrong_codes:
            raise NMOSTestException(fail(test, "Registration API returned wrong HTTP code"))
        elif r.status_code not in codes:
            raise NMOSTestException(fail(test, "Registration API returned an unexpected response: "
                                               "{} {}".format(r.status_code, r.text)))
        elif r.status_code in [200, 201]:
            if "Location" not in r.headers:
                raise NMOSTestException(fail(test, "Registration API failed to return a 'Location' response header"))
            path = "{}resource/{}s/{}".format(urlparse(reg_url).path, type, data["id"])
            location = r.headers["Location"]
            if path not in location:
                raise NMOSTestException(fail(test, "Registration API 'Location' response header is incorrect: "
                                             "Location: {}".format(location)))
            if not location.startswith("/") and not location.startswith(self.protocol + "://"):
                raise NMOSTestException(fail(test, "Registration API 'Location' response header is invalid for the "
                                             "current protocol: Location: {}".format(location)))

        # Currently can only validate schema for the API version under test
        if reg_url == self.reg_url:
            schema = self.get_schema(REG_API_KEY, "POST", "/resource", r.status_code)
            valid, message = self.check_response(schema, "POST", r)
            if valid:
                # if message:
                #     return WARNING somehow...
                pass
            else:
                raise NMOSTestException(test.FAIL(message))

        return location

    def post_super_resources_and_resource(self, test, type, description, fail=Test.FAIL):
        """
        Perform POST requests on the Registration API to create the super-resource registrations
        for the requested type, before performing a POST request to create that resource registration
        """

        # use the test data as a template for creating new resources
        data = self.copy_resource(type)
        data["id"] = str(uuid.uuid4())
        data["description"] = description

        if type == "node":
            pass
        elif type == "device":
            node = self.post_super_resources_and_resource(test, "node", description, fail=Test.UNCLEAR)
            data["node_id"] = node["id"]
            data["senders"] = []  # or add an id here, and use it when posting the sender?
            data["receivers"] = []  # or add an id here, and use it when posting the receiver?
        elif type == "source":
            device = self.post_super_resources_and_resource(test, "device", description, fail=Test.UNCLEAR)
            data["device_id"] = device["id"]
        elif type == "flow":
            source = self.post_super_resources_and_resource(test, "source", description, fail=Test.UNCLEAR)
            data["device_id"] = source["device_id"]
            data["source_id"] = source["id"]
            # since device_id is v1.1, downgrade
            data = self.downgrade_resource(type, data, self.apis[REG_API_KEY]["version"])
        elif type == "sender":
            device = self.post_super_resources_and_resource(test, "device", description, fail=Test.UNCLEAR)
            data["device_id"] = device["id"]
            data["flow_id"] = str(uuid.uuid4())  # or post a flow first and use its id here?
        elif type == "receiver":
            device = self.post_super_resources_and_resource(test, "device", description, fail=Test.UNCLEAR)
            data["device_id"] = device["id"]

        self.post_resource(test, type, data, codes=[201], fail=fail)

        return data

    def do_test_api_v1_x(self, test):
        """
        Precondition check of the API version.
        Raises an NMOSTestException when there's an error
        """
        api = self.apis[REG_API_KEY]
        if not self.is04_reg_utils.compare_api_version(api["version"], "v2.0") < 0:
            raise NMOSTestException(test.FAIL("Version > 1 not supported yet."))
