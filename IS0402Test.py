
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

from time import sleep
import socket

from zeroconf import ServiceBrowser, Zeroconf
from TestHelper import MdnsListener, Test, GenericTest


class IS0402Test(GenericTest):
    """
    Runs IS-04-02-Test
    """
    def __init__(self, base_url, apis, spec_versions, test_version, spec_path):
        GenericTest.__init__(self, base_url, apis, spec_versions, test_version, spec_path)
        self.reg_url = self.apis["registration"]["url"]
        self.query_url = self.apis["query"]["url"]

    def execute_tests(self):
        super(IS0402Test, self).execute_tests()
        self.result.append(self.test_01())
        self.result.append(self.test_02())

    def test_01(self):
        """Registration API advertises correctly via mDNS"""

        test = Test("Registration API advertises correctly via mDNS")

        zeroconf = Zeroconf()
        listener = MdnsListener()
        browser = ServiceBrowser(zeroconf, "_nmos-registration._tcp.local.", listener)
        sleep(5)
        zeroconf.close()
        serv_list = listener.get_service_list()
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

        zeroconf = Zeroconf()
        listener = MdnsListener()
        browser = ServiceBrowser(zeroconf, "_nmos-query._tcp.local.", listener)
        sleep(5)
        zeroconf.close()
        serv_list = listener.get_service_list()
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
