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

from time import sleep
import socket

from zeroconf import ServiceBrowser, Zeroconf
from MdnsListener import MdnsListener
from TestResult import Test
from GenericTest import GenericTest


class IS0402Test(GenericTest):
    """
    Runs IS-04-02-Test
    """
    def __init__(self, base_url, apis, spec_versions, test_version, spec_path):
        GenericTest.__init__(self, base_url, apis, spec_versions, test_version, spec_path)
        self.reg_url = self.apis["registration"]["url"]
        self.query_url = self.apis["query"]["url"]

    def execute_tests(self):
        self.init_zeroconf()
        super(IS0402Test, self).execute_tests()
        self.close_zeroconf()

    def init_zeroconf(self):
        self.zc = Zeroconf()
        self.zc_listener = MdnsListener()

    def close_zeroconf(self):
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
                        return test.FAIL("Priority ('pri') TXT record must be less than 100 for a production instance.")
                except Exception as e:
                    return test.FAIL("Priority ('pri') TXT record is not an integer.")

                # Other TXT records only came in for IS-04 v1.1+
                if self.major_version > 1 or (self.major_version == 1 and self.minor_version > 0):
                    if "api_ver" not in properties:
                        return test.FAIL("No 'api_ver' TXT record found in Registration API advertisement.")
                    elif "v{}.{}".format(self.major_version,
                                         self.minor_version) not in properties["api_ver"].split(","):
                        return test.FAIL("Registry does not claim to support version under test.")

                    if "api_proto" not in properties:
                        return test.FAIL("No 'api_proto' TXT record found in Registration API advertisement.")
                    elif properties["api_proto"] != "http":
                        return test.FAIL("API protocol is not advertised as 'http'. "
                                         "This test suite does not currently support 'https'.")

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
                        return test.FAIL("Priority ('pri') TXT record must be less than 100 for a production instance.")
                except Exception as e:
                    return test.FAIL("Priority ('pri') TXT record is not an integer.")

                # Other TXT records only came in for IS-04 v1.1+
                if self.major_version > 1 or (self.major_version == 1 and self.minor_version > 0):
                    if "api_ver" not in properties:
                        return test.FAIL("No 'api_ver' TXT record found in Query API advertisement.")
                    elif "v{}.{}".format(self.major_version,
                                         self.minor_version) not in properties["api_ver"].split(","):
                        return test.FAIL("Registry does not claim to support version under test.")

                    if "api_proto" not in properties:
                        return test.FAIL("No 'api_proto' TXT record found in Query API advertisement.")
                    elif properties["api_proto"] != "http":
                        return test.FAIL("API protocol is not advertised as 'http'. "
                                         "This test suite does not currently support 'https'.")

                return test.PASS()
        return test.FAIL("No matching mDNS announcement found for Query API.")

    def test_03(self):
        """Registration API accepts and stores a valid Node resource"""

        test = Test("Registration API accepts and stores a valid Node resource")

        # TODO: Need a mechanism to do this correctly for each API version. Might require a resource stripping method
        # from nmos-common

        return test.MANUAL()

    def test_04(self):
        """Registration API rejects an invalid Node resource with a 400 HTTP code"""

        test = Test("Registration API rejects an invalid Node resource with a 400 HTTP code")

        bad_json = {"notanode": True}
        return self.do_400_check(test, "node", bad_json)

    def test_05(self):
        """Registration API accepts and stores a valid Device resource"""

        test = Test("Registration API accepts and stores a valid Device resource")

        return test.MANUAL()

    def test_06(self):
        """Registration API rejects an invalid Device resource with a 400 HTTP code"""

        test = Test("Registration API rejects an invalid Device resource with a 400 HTTP code")

        bad_json = {"notadevice": True}
        return self.do_400_check(test, "device", bad_json)

    def test_07(self):
        """Registration API accepts and stores a valid Source resource"""

        test = Test("Registration API accepts and stores a valid Source resource")

        return test.MANUAL()

    def test_08(self):
        """Registration API rejects an invalid Source resource with a 400 HTTP code"""

        test = Test("Registration API rejects an invalid Source resource with a 400 HTTP code")

        bad_json = {"notasource": True}
        return self.do_400_check(test, "source", bad_json)

    def test_09(self):
        """Registration API accepts and stores a valid Flow resource"""

        test = Test("Registration API accepts and stores a valid Flow resource")

        return test.MANUAL()

    def test_10(self):
        """Registration API rejects an invalid Flow resource with a 400 HTTP code"""

        test = Test("Registration API rejects an invalid Flow resource with a 400 HTTP code")

        bad_json = {"notaflow": True}
        return self.do_400_check(test, "flow", bad_json)

    def test_11(self):
        """Registration API accepts and stores a valid Sender resource"""

        test = Test("Registration API accepts and stores a valid Sender resource")

        return test.MANUAL()

    def test_12(self):
        """Registration API rejects an invalid Sender resource with a 400 HTTP code"""

        test = Test("Registration API rejects an invalid Sender resource with a 400 HTTP code")

        bad_json = {"notasender": True}
        return self.do_400_check(test, "sender", bad_json)

    def test_13(self):
        """Registration API accepts and stores a valid Receiver resource"""

        test = Test("Registration API accepts and stores a valid Receiver resource")

        return test.MANUAL()

    def test_14(self):
        """Registration API rejects an invalid Receiver resource with a 400 HTTP code"""

        test = Test("Registration API rejects an invalid Receiver resource with a 400 HTTP code")

        bad_json = {"notareceiver": True}
        return self.do_400_check(test, "receiver", bad_json)

    def do_400_check(self, test, resource_type, data):
        valid, r = self.do_request("POST", self.reg_url + "resource", data={"type": resource_type, "data": data})

        if not valid:
            return test.FAIL(r)

        if r.status_code != 400:
            return test.FAIL("Registration API returned a {} code for an invalid registration".format(r.status_code))

        schema = self.apis["registration"]["spec"].get_schema("POST", "/resource", 400)
        valid, message = self.check_response(schema, "POST", r)

        if valid:
            return test.PASS()
        else:
            return test.FAIL(message)
