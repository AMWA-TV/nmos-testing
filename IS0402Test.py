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
from jsonschema import ValidationError, Draft4Validator

from zeroconf_monkey import ServiceBrowser, Zeroconf
from MdnsListener import MdnsListener
from TestResult import Test
from GenericTest import GenericTest, test_depends
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
        self.zc = None
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

        browser = ServiceBrowser(self.zc, "_nmos-registration._tcp.local.", self.zc_listener)
        sleep(2)
        serv_list = self.zc_listener.get_service_list()
        for api in serv_list:
            address = socket.inet_ntoa(api.address)
            port = api.port
            if address in self.reg_url and ":{}".format(port) in self.reg_url:
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
            if address in self.query_url and ":{}".format(port) in self.query_url:
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

            valid, r = self.do_request("POST", self.reg_url + "resource", data={"type": "node", "data": node_json})

            if not valid:
                return test.FAIL("Registration API did not respond as expected")
            elif r.status_code == 201:
                return test.PASS()
            else:
                return test.FAIL("Registration API returned an unexpected response: {} {}"
                                 .format(r.status_code, r.text))
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

            valid, r = self.do_request("POST", self.reg_url + "resource", data={"type": "device",
                                                                                "data": device_json})

            if not valid:
                return test.FAIL("Registration API did not respond as expected")
            elif r.status_code == 201:
                return test.PASS()
            else:
                return test.FAIL("Registration API returned an unexpected response: {} {}".format(r.status_code,
                                                                                                  r.text))
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

            valid, r = self.do_request("POST", self.reg_url + "resource", data={"type": "source",
                                                                                "data": source_json})

            if not valid:
                return test.FAIL("Registration API did not respond as expected")
            elif r.status_code == 201:
                return test.PASS()
            else:
                return test.FAIL("Registration API returned an unexpected response: {} {}"
                                 .format(r.status_code, r.text))
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
            valid, r = self.do_request("POST", self.reg_url + "resource", data={"type": "flow",
                                                                                "data": flow_json})

            if not valid:
                return test.FAIL("Registration API did not respond as expected")
            elif r.status_code == 201:
                return test.PASS()
            else:
                return test.FAIL("Registration API returned an unexpected response: {} {}"
                                 .format(r.status_code, r.text))
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
            valid, r = self.do_request("POST", self.reg_url + "resource", data={"type": "sender",
                                                                                "data": sender_json})

            if not valid:
                return test.FAIL("Registration API did not respond as expected")
            elif r.status_code == 201:
                return test.PASS()
            else:
                return test.FAIL("Registration API returned an unexpected response: {} {}"
                                 .format(r.status_code, r.text))
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
            valid, r = self.do_request("POST", self.reg_url + "resource", data={"type": "receiver",
                                                                                "data": receiver_json})

            if not valid:
                return test.FAIL("Registration API did not respond as expected")
            elif r.status_code == 201:
                return test.PASS()
            else:
                return test.FAIL("Registration API returned an unexpected response: {} {}"
                                 .format(r.status_code, r.text))
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
        test = Test("Registration API responds with 200 HTTP code on updating an registered Node")

        api = self.apis[REG_API_KEY]
        if self.is04_reg_utils.compare_api_version(api["version"], "v2.0") < 0:
            node_json = deepcopy(self.test_data["node"])
            if self.is04_reg_utils.compare_api_version(api["version"], "v1.2") < 0:
                node_json = self.downgrade_resource("node", node_json, self.apis[REG_API_KEY]["version"])
            self.bump_resource_version(node_json)

            valid, r = self.do_request("POST", self.reg_url + "resource", data={"type": "node", "data": node_json})

            if not valid:
                return test.FAIL("Registration API did not respond as expected")
            elif r.status_code == 201:
                return test.FAIL("Registration API returned wrong HTTP code.")
            elif r.status_code == 200:
                return test.PASS()
            else:
                return test.FAIL("Registration API returned an unexpected response: {} {}"
                                 .format(r.status_code, r.text))

        else:
            return test.FAIL("Version > 1 not supported yet.")

    @test_depends
    def test_16(self):
        """Updating Device resource results in 200"""
        test = Test("Registration API responds with 200 HTTP code on updating an registered Device")

        api = self.apis[REG_API_KEY]
        if self.is04_reg_utils.compare_api_version(api["version"], "v2.0") < 0:
            device_json = deepcopy(self.test_data["device"])

            if self.is04_reg_utils.compare_api_version(api["version"], "v1.2") < 0:
                device_json = self.downgrade_resource("device", device_json, self.apis[REG_API_KEY]["version"])

            self.bump_resource_version(device_json)

            valid, r = self.do_request("POST", self.reg_url + "resource", data={"type": "device",
                                                                                "data": device_json})

            if not valid:
                return test.FAIL("Registration API did not respond as expected")
            elif r.status_code == 201:
                return test.FAIL("Registration API returned wrong HTTP code.")
            elif r.status_code == 200:
                return test.PASS()
            else:
                return test.FAIL("Registration API returned an unexpected response: {} {}".format(r.status_code,
                                                                                                  r.text))

        else:
            return test.FAIL("Version > 1 not supported yet.")

    @test_depends
    def test_17(self):
        """Updating Source resource results in 200"""
        test = Test("Registration API responds with 200 HTTP code on updating an registered Source")

        api = self.apis[REG_API_KEY]
        if self.is04_reg_utils.compare_api_version(api["version"], "v2.0") < 0:
            source_json = deepcopy(self.test_data["source"])
            if self.is04_reg_utils.compare_api_version(api["version"], "v1.2") < 0:
                source_json = self.downgrade_resource("source", source_json, self.apis[REG_API_KEY]["version"])

            self.bump_resource_version(source_json)

            valid, r = self.do_request("POST", self.reg_url + "resource", data={"type": "source",
                                                                                "data": source_json})

            if not valid:
                return test.FAIL("Registration API did not respond as expected")
            elif r.status_code == 201:
                return test.FAIL("Registration API returned wrong HTTP code.")
            elif r.status_code == 200:
                return test.PASS()
            else:
                return test.FAIL("Registration API returned an unexpected response: {} {}"
                                 .format(r.status_code, r.text))

        else:
            return test.FAIL("Version > 1 not supported yet.")

    @test_depends
    def test_18(self):
        """Updating Flow resource results in 200"""
        test = Test("Registration API responds with 200 HTTP code on updating an registered Flow")

        api = self.apis[REG_API_KEY]
        if self.is04_reg_utils.compare_api_version(api["version"], "v2.0") < 0:
            flow_json = deepcopy(self.test_data["flow"])

            if self.is04_reg_utils.compare_api_version(api["version"], "v1.2") < 0:
                flow_json = self.downgrade_resource("flow", flow_json, self.apis[REG_API_KEY]["version"])

            self.bump_resource_version(flow_json)

            valid, r = self.do_request("POST", self.reg_url + "resource", data={"type": "flow",
                                                                                "data": flow_json})

            if not valid:
                return test.FAIL("Registration API did not respond as expected")
            elif r.status_code == 201:
                return test.FAIL("Registration API returned wrong HTTP code.")
            elif r.status_code == 200:
                return test.PASS()
            else:
                return test.FAIL("Registration API returned an unexpected response: {} {}"
                                 .format(r.status_code, r.text))

        else:
            return test.FAIL("Version > 1 not supported yet.")

    @test_depends
    def test_19(self):
        """Updating Sender resource results in 200"""
        test = Test("Registration API responds with 200 HTTP code on updating an registered Sender")

        api = self.apis[REG_API_KEY]
        if self.is04_reg_utils.compare_api_version(api["version"], "v2.0") < 0:
            sender_json = deepcopy(self.test_data["sender"])
            if self.is04_reg_utils.compare_api_version(api["version"], "v1.2") < 0:
                sender_json = self.downgrade_resource("sender", sender_json, self.apis[REG_API_KEY]["version"])

            self.bump_resource_version(sender_json)

            valid, r = self.do_request("POST", self.reg_url + "resource", data={"type": "sender",
                                                                                "data": sender_json})

            if not valid:
                return test.FAIL("Registration API did not respond as expected")
            elif r.status_code == 201:
                return test.FAIL("Registration API returned wrong HTTP code.")
            elif r.status_code == 200:
                return test.PASS()
            else:
                return test.FAIL("Registration API returned an unexpected response: {} {}"
                                 .format(r.status_code, r.text))

        else:
            return test.FAIL("Version > 1 not supported yet.")

    @test_depends
    def test_20(self):
        """Updating Receiver resource results in 200"""
        test = Test("Registration API responds with 200 HTTP code on updating an registered Receiver")

        api = self.apis[REG_API_KEY]
        if self.is04_reg_utils.compare_api_version(api["version"], "v2.0") < 0:
            receiver_json = deepcopy(self.test_data["receiver"])
            if self.is04_reg_utils.compare_api_version(api["version"], "v1.2") < 0:
                receiver_json = self.downgrade_resource("receiver", receiver_json,
                                                        self.apis[REG_API_KEY]["version"])

            valid, r = self.do_request("POST", self.reg_url + "resource", data={"type": "receiver",
                                                                                "data": receiver_json})
            self.bump_resource_version(receiver_json)

            if not valid:
                return test.FAIL("Registration API did not respond as expected")
            elif r.status_code == 201:
                return test.FAIL("Registration API returned wrong HTTP code.")
            elif r.status_code == 200:
                return test.PASS()
            else:
                return test.FAIL("Registration API returned an unexpected response: {} {}"
                                 .format(r.status_code, r.text))
        else:
            return test.FAIL("Version > 1 not supported yet.")

    def test_21(self):
        """Query API implements pagination"""

        test = Test("Query API implements pagination")

        if self.apis[QUERY_API_KEY]["version"] == "v1.0":
            return test.NA("This test does not apply to v1.0")

        return test.MANUAL("", "https://github.com/AMWA-TV/nmos/wiki/IS-04#registries-pagination")

    def test_22(self):
        """Query API implements downgrade queries"""

        test = Test("Query API implements downgrade queries")

        if self.apis[QUERY_API_KEY]["version"] == "v1.0":
            return test.NA("This test does not apply to v1.0")

        return test.MANUAL("", "https://github.com/AMWA-TV/nmos/wiki/IS-04#registries-downgrade-queries")

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

                valid, r = self.do_request("POST", self.reg_url + "resource", data={"type": curr_resource,
                                                                                    "data": resource_json})

                if not valid:
                    return test.FAIL("Registration API did not respond as expected")
                elif r.status_code == 200 or r.status_code == 201:
                    return test.FAIL("Registration API returned wrong HTTP code.")
                elif r.status_code == 400:
                    pass
                else:
                    return test.FAIL(
                        "Registration API returned an unexpected response: {} {}".format(r.status_code, r.text))

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

                valid, r = self.do_request("POST", self.reg_url + "resource", data={"type": resource,
                                                                                    "data": resource_json})
                if not valid:
                    return test.FAIL("Registration API did not respond as expected")
                elif r.status_code == 200 or r.status_code == 201:
                    pass
                else:
                    return test.FAIL(
                        "Registration API returned an unexpected response: {} {}".format(r.status_code, r.text))

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
                    return test.FAIL("Query API returned an unexpected response: {} {}".format(r.status_code, r.text))
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
            valid, r = self.do_request("POST", self.reg_url + "resource", data={"type": "node", "data": node_json})

            if not valid:
                return test.FAIL("Registration API did not respond as expected")
            elif r.status_code == 200 or r.status_code == 201:
                pass
            else:
                return test.FAIL("Registration API returned an unexpected response: {} {}"
                                 .format(r.status_code, r.text))

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
            valid, r = self.do_request("GET", "{}nodes/{}".format(self.query_url, self.test_data["node"]["id"]))
            if not valid:
                return test.FAIL("Query API returned an unexpected response: {}".format(r))
            else:
                if r.status_code == 200:
                    # Delete resource
                    valid_delete, r_delete = self.do_request("DELETE", "{}resource/nodes/{}"
                                                             .format(self.reg_url,
                                                                     self.test_data["node"]["id"]))
                    if not valid_delete:
                        return test.FAIL("Registration API returned an unexpected response: {}".format(r_delete))
                    else:
                        if r_delete.status_code != 204:
                            return test.FAIL("Cannot delete resources. Cannot execute test: {} {}"
                                             .format(r_delete.status_code, r_delete.text))
                        else:
                            # Verify all other resources are not available
                            remaining_resources = ["device", "flow", "source", "sender", "receiver"]
                            for curr_resource in remaining_resources:
                                v, r_resource_deleted = self.do_request("GET", "{}{}s/{}"
                                                                        .format(self.query_url,
                                                                                curr_resource,
                                                                                self.test_data[curr_resource]["id"]))
                                if not v:
                                    return test.FAIL("Query API returned an unexpected response: {}. Cannot execute "
                                                     "test.".format(r_resource_deleted))
                                elif r_resource_deleted.status_code != 404:
                                    return test.FAIL("Query API returned an unexpected response: {} {}. Cannot execute "
                                                     "test.".format(r_resource_deleted.status_code,
                                                                    r_resource_deleted.text))
                elif r.status_code == 404:
                    pass
                else:
                    return test.FAIL(
                        "Query API returned an unexpected response: {} {}. Cannot execute test.".format(r.status_code,
                                                                                                        r.text))

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
                valid, r = self.do_request("POST", self.reg_url + "resource", data={"type": resource,
                                                                                    "data": test_data[resource]})
                if not valid:
                    return test.FAIL("Cannot POST sample data. Cannot execute test: {}".format(r))
                elif r.status_code != 201:
                    return test.FAIL("Cannot POST sample data. Cannot execute test: {} {}"
                                     .format(r.status_code, r.text))

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
                        Draft4Validator(schema).validate(json.loads(message))
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
                self.bump_resource_version(resource_data)
                valid, r = self.do_request("POST", self.reg_url + "resource", data={"type": resource,
                                                                                    "data": resource_data})
                if not valid:
                    return test.FAIL("Cannot update sample data. Cannot execute test: {}".format(r))
                elif r.status_code != 200:
                    return test.FAIL("Cannot update sample data. Cannot execute test: {} {}"
                                     .format(r.status_code, r.text))

            sleep(1)

            for resource, resource_data in test_data.items():
                received_messages = websockets[resource].get_messages()

                # Validate received data against schema
                for message in received_messages:
                    try:
                        Draft4Validator(schema).validate(json.loads(message))
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
                        Draft4Validator(schema).validate(json.loads(message))
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
                # Update resource
                self.bump_resource_version(test_data[resource])
                valid, r = self.do_request("POST", self.reg_url + "resource", data={"type": resource,
                                                                                    "data": test_data[resource]})
                if not valid:
                    return test.FAIL("Cannot POST sample data. Cannot execute test: {}".format(r))
                elif r.status_code != 201:
                    return test.FAIL("Cannot POST sample data. Cannot execute test: {} {}"
                                     .format(r.status_code, r.text))

            sleep(1)
            for resource, resource_data in test_data.items():
                received_messages = websockets[resource].get_messages()

                # Validate received data against schema
                for message in received_messages:
                    try:
                        Draft4Validator(schema).validate(json.loads(message))
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
        valid, message = self.check_response(REG_API_KEY, schema, "POST", r)

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
