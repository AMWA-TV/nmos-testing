# Copyright (C) 2019 Advanced Media Workflow Association
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

import time
import socket
from zeroconf_monkey import ServiceInfo, Zeroconf

from .. import Config as CONFIG
from ..MdnsListener import MdnsListener
from ..GenericTest import GenericTest
from ..TestHelper import get_default_ip

NODE_API_KEY = "node"
SYSTEM_API_KEY = "system"


class IS0902Test(GenericTest):
    """
    Runs IS-09-02-Test
    """
    def __init__(self, apis, systems, dns_server, **kwargs):
        GenericTest.__init__(self, apis, **kwargs)
        self.authorization = False  # System API doesn't use auth, so don't send tokens in every request
        self.invalid_system = systems[0]
        self.primary_system = systems[1]
        self.systems = systems[1:]
        self.dns_server = dns_server
        self.system_basics_done = False
        self.system_basics_data = []
        self.system_primary_data = None
        self.system_invalid_data = None
        self.zc = None
        self.zc_listener = None

    def set_up_tests(self):
        self.zc = Zeroconf()
        self.zc_listener = MdnsListener(self.zc)
        if self.dns_server:
            self.dns_server.load_zone(self.apis[SYSTEM_API_KEY]["version"], self.protocol, self.authorization,
                                      "test_data/IS0902/dns_records.zone", CONFIG.PORT_BASE+300)

    def tear_down_tests(self):
        if self.zc:
            self.zc.close()
            self.zc = None
        if self.dns_server:
            self.dns_server.reset()

    def _system_mdns_info(self, port, priority=0, api_ver=None, api_proto=None, api_auth=None, ip=None):
        """Get an mDNS ServiceInfo object in order to create an advertisement"""
        if api_ver is None:
            api_ver = self.apis[SYSTEM_API_KEY]["version"]
        if api_proto is None:
            api_proto = self.protocol
        if api_auth is None:
            api_auth = self.authorization

        if ip is None:
            ip = get_default_ip()
            hostname = "nmos-mocks.local."
        else:
            hostname = ip.replace(".", "-") + ".local."

        # TODO: Add another test which checks support for parsing CSV string in api_ver
        txt = {'api_ver': api_ver, 'api_proto': api_proto, 'pri': str(priority), 'api_auth': str(api_auth).lower()}

        service_type = "_nmos-system._tcp.local."
        info = ServiceInfo(service_type,
                           "NMOSTestSuite{}{}.{}".format(port, api_proto, service_type),
                           addresses=[socket.inet_aton(ip)], port=port,
                           properties=txt, server=hostname)
        return info

    def do_system_basics_prereqs(self):
        """Advertise a System API and collect data from any Nodes which discover it"""

        if self.system_basics_done:
            return

        if CONFIG.DNS_SD_MODE == "multicast":
            system_mdns = []
            priority = 0

            # Add advertisement with invalid version
            info = self._system_mdns_info(self.invalid_system.port, priority, "v9.0")
            system_mdns.append(info)
            # Add advertisement with invalid protocol
            info = self._system_mdns_info(self.invalid_system.port, priority, None, "invalid")
            system_mdns.append(info)

            # Add advertisement for primary and failover System APIs
            for system in self.systems[0:-1]:
                info = self._system_mdns_info(system.port, priority)
                system_mdns.append(info)
                priority += 10

            # Add a fake advertisement for a timeout simulating System API
            info = self._system_mdns_info(444, priority, ip="192.0.2.1")
            system_mdns.append(info)
            priority += 10

            # Add the final real System API advertisement
            info = self._system_mdns_info(self.systems[-1].port, priority)
            system_mdns.append(info)

        # Reset all System APIs
        self.invalid_system.reset()
        for system in self.systems:
            system.reset()

        self.invalid_system.enable()
        self.primary_system.enable()

        if CONFIG.DNS_SD_MODE == "multicast":
            # Advertise the primary System API and invalid ones at pri 0, and allow the Node to do a basic registration
            self.zc.register_service(system_mdns[0])
            self.zc.register_service(system_mdns[1])
            self.zc.register_service(system_mdns[2])

        # Wait for n seconds after advertising the service for the first interaction
        start_time = time.time()
        while time.time() < start_time + CONFIG.DNS_SD_ADVERT_TIMEOUT:
            if len(self.primary_system.requests) > 0:
                break
            if len(self.invalid_system.requests) > 0:
                break
            time.sleep(0.2)

        # Clean up mDNS advertisements and disable System APIs
        if CONFIG.DNS_SD_MODE == "multicast":
            for info in system_mdns:
                self.zc.unregister_service(info)
        self.invalid_system.disable()
        for index, system in enumerate(self.systems):
            system.disable()

        self.system_basics_done = True
        for system in self.systems:
            self.system_basics_data.append(system)
        self.system_invalid_data = self.invalid_system

        # If the Node preferred the invalid System API, don't penalise it for other tests which check the general
        # interactions are correct
        self.system_primary_data = self.system_basics_data[0]
        if len(self.system_invalid_data.requests) > 0:
            self.system_primary_data.requests.update(self.system_invalid_data.requests)

    def test_01(self, test):
        """Node can discover System API via multicast DNS"""

        if not CONFIG.ENABLE_DNS_SD or CONFIG.DNS_SD_MODE != "multicast":
            return test.DISABLED("This test cannot be performed when ENABLE_DNS_SD is False or DNS_SD_MODE is not "
                                 "'multicast'")

        self.do_system_basics_prereqs()

        if self.apis[NODE_API_KEY]["ip"] in self.system_primary_data.requests:
            return test.PASS()

        return test.FAIL("Node did not attempt to contact the advertised System API.")

    def test_01_01(self, test):
        """Node does not attempt to contact an unsuitable System API"""

        if not CONFIG.ENABLE_DNS_SD or CONFIG.DNS_SD_MODE != "multicast":
            return test.DISABLED("This test cannot be performed when ENABLE_DNS_SD is False or DNS_SD_MODE is not "
                                 "'multicast'")

        self.do_system_basics_prereqs()

        if self.apis[NODE_API_KEY]["ip"] in self.system_invalid_data.requests:
            return test.FAIL("Node incorrectly contacted a System API advertising an invalid 'api_ver' or 'api_proto'")

        return test.PASS()

    def test_02(self, test):
        """Node can discover System API via unicast DNS"""

        if not CONFIG.ENABLE_DNS_SD or CONFIG.DNS_SD_MODE != "unicast":
            return test.DISABLED("This test cannot be performed when ENABLE_DNS_SD is False or DNS_SD_MODE is not "
                                 "'unicast'")

        self.do_system_basics_prereqs()

        if self.apis[NODE_API_KEY]["ip"] in self.system_primary_data.requests:
            return test.PASS()

        return test.FAIL("Node did not attempt to contact the advertised System API.")

    def test_02_01(self, test):
        """Node does not attempt to contact an unsuitable System API"""

        if not CONFIG.ENABLE_DNS_SD or CONFIG.DNS_SD_MODE != "unicast":
            return test.DISABLED("This test cannot be performed when ENABLE_DNS_SD is False or DNS_SD_MODE is not "
                                 "'unicast'")

        self.do_system_basics_prereqs()

        if self.apis[NODE_API_KEY]["ip"] in self.system_invalid_data.requests:
            return test.FAIL("Node incorrectly contacted a System API advertising an invalid 'api_ver' or 'api_proto'")

        return test.PASS()

    def test_03(self, test):
        """System API interactions use the correct versioned path"""

        if not CONFIG.ENABLE_DNS_SD:
            return test.DISABLED("This test cannot be performed when ENABLE_DNS_SD is False")

        self.do_system_basics_prereqs()

        api = self.apis[SYSTEM_API_KEY]

        if not self.apis[NODE_API_KEY]["ip"] in self.system_primary_data.requests:
            return test.FAIL("Node did not attempt to contact the advertised System API.")

        if not self.system_primary_data.requests[self.apis[NODE_API_KEY]["ip"]] == api["version"]:
            return test.FAIL("System API interaction used version '{}' instead of '{}'"
                             .format(self.system_primary_data.version, api["version"]))

        return test.PASS()

    def test_04(self, test):
        """Node correctly selects a System API based on advertised priorities"""

        if not CONFIG.ENABLE_DNS_SD:
            return test.DISABLED("This test cannot be performed when ENABLE_DNS_SD is False")

        self.do_system_basics_prereqs()

        if not self.apis[NODE_API_KEY]["ip"] in self.system_primary_data.requests:
            return test.FAIL("Node did not attempt to contact the advertised System API.")

        # All but the first and last System API can be used for priority tests.
        for index, system_data in enumerate(self.system_basics_data[1:-1]):
            if self.apis[NODE_API_KEY]["ip"] in system_data.requests:
                return test.FAIL("Node incorrectly contacted System API {} advertised on port {}"
                                 .format(index + 1, system_data.port))

        return test.PASS()

    def test_05(self, test):
        """System API configuration takes effect in the Node"""

        return test.MANUAL()
