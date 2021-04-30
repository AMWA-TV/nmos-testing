import time
import json
import socket
import requests
from time import sleep
from urllib.parse import parse_qs
from OpenSSL import crypto
from zeroconf_monkey import ServiceBrowser, ServiceInfo, Zeroconf

from ..GenericTest import GenericTest, NMOSTestException, NMOSInitException
from ..IS04Utils import IS04Utils
from .. import Config as CONFIG
from zeroconf_monkey import ServiceBrowser, Zeroconf
from ..MdnsListener import MdnsListener
from ..TestHelper import get_default_ip, load_resolved_schema

NODE_API_KEY = "node"


class HeatherTest(GenericTest):
    """
    Testing initial set up of new test suite for controller testing
    """
    def __init__(self, apis, registries, dns_server):
        print('init-ing')
        GenericTest.__init__(self, apis)
        self.primary_registry = registries[1]
        self.registries = registries[1:]
        self.dns_server = dns_server
        self.node_url = self.apis[NODE_API_KEY]["url"]
        self.registry_basics_done = False
        self.registry_basics_data = []
        self.registry_primary_data = None
        self.registry_invalid_data = None
        self.node_basics_data = {
            "self": None, "devices": None, "sources": None,
            "flows": None, "senders": None, "receivers": None
        }
        self.zc = None
        self.zc_listener = None
        self.is04_utils = IS04Utils(self.node_url)

    def set_up_tests(self):
        print('Setting up tests')
        self.zc = Zeroconf()
        self.zc_listener = MdnsListener(self.zc)
        if self.dns_server:
            self.dns_server.load_zone(self.apis[NODE_API_KEY]["version"], self.protocol, self.authorization,
                                      "test_data/IS0401/dns_records.zone", CONFIG.PORT_BASE+100)
            print(" * Waiting for up to {} seconds for a DNS query before executing tests"
                  .format(CONFIG.DNS_SD_ADVERT_TIMEOUT))
            self.dns_server.wait_for_query(
                QTYPE.PTR,
                [
                    "_nmos-register._tcp.{}.".format(CONFIG.DNS_DOMAIN),
                    "_nmos-registration._tcp.{}.".format(CONFIG.DNS_DOMAIN)
                ],
                CONFIG.DNS_SD_ADVERT_TIMEOUT
            )
            # Wait for a short time to allow the device to react after performing the query
            time.sleep(CONFIG.API_PROCESSING_TIMEOUT)

        if self.registry_basics_done:
            return

        if CONFIG.DNS_SD_MODE == "multicast":
            registry_mdns = []
            priority = 100

            # Add advertisement for primary and failover registries
            for registry in self.registries[0:-1]:
                info = self._registry_mdns_info(registry.get_data().port, priority)
                registry_mdns.append(info)
                priority += 10

            # Add the final real registry advertisement
            info = self._registry_mdns_info(self.registries[-1].get_data().port, priority)
            registry_mdns.append(info)

        # Reset all registries to clear previous heartbeats, etc.
        for registry in self.registries:
            registry.reset()

        self.primary_registry.enable()

        if CONFIG.DNS_SD_MODE == "multicast":
            # Advertise the primary registry and invalid ones at pri 0, and allow the Node to do a basic registration
            if self.is04_utils.compare_api_version(self.apis[NODE_API_KEY]["version"], "v1.0") != 0:
                self.zc.register_service(registry_mdns[0])
                self.zc.register_service(registry_mdns[1])
            self.zc.register_service(registry_mdns[2])

        # Wait for n seconds after advertising the service for the first POST from a Node
        start_time = time.time()
        while time.time() < start_time + CONFIG.DNS_SD_ADVERT_TIMEOUT:
            if self.primary_registry.has_registrations():
                break
            time.sleep(0.2)

        # Wait until we're sure the Node has registered everything it intends to, and we've had at least one heartbeat
        while (time.time() - self.primary_registry.last_time) < CONFIG.HEARTBEAT_INTERVAL + 1:
            time.sleep(0.2)

        # Collect matching resources from the Node
        self.do_node_basics_prereqs()

        # Ensure we have two heartbeats from the Node, assuming any are arriving (for test_05)
        if len(self.primary_registry.get_data().heartbeats) > 0:
            # It is heartbeating, but we don't have enough of them yet
            while len(self.primary_registry.get_data().heartbeats) < 2:
                time.sleep(0.2)

            # Once registered, advertise all other registries at different (ascending) priorities
            for index, registry in enumerate(self.registries[1:]):
                registry.enable()

            if CONFIG.DNS_SD_MODE == "multicast":
                for info in registry_mdns[3:]:
                    self.zc.register_service(info)

    def tear_down_tests(self):
        print('Tearing down tests')
        # Clean up mDNS advertisements and disable registries
        # if CONFIG.DNS_SD_MODE == "multicast":
        #     for info in registry_mdns:
        #         self.zc.unregister_service(info)

        for index, registry in enumerate(self.registries):
            registry.disable()

        self.registry_basics_done = True
        for registry in self.registries:
            self.registry_basics_data.append(registry.get_data())

        self.registry_primary_data = self.registry_basics_data[0]

        if self.zc:
            self.zc.close()
            self.zc = None
        if self.dns_server:
            self.dns_server.reset()

    def _registry_mdns_info(self, port, priority=0, api_ver=None, api_proto=None, api_auth=None, ip=None):
        """Get an mDNS ServiceInfo object in order to create an advertisement"""
        if api_ver is None:
            api_ver = self.apis[NODE_API_KEY]["version"]
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

        service_type = "_nmos-registration._tcp.local."
        if self.is04_utils.compare_api_version(self.apis[NODE_API_KEY]["version"], "v1.3") >= 0:
            service_type = "_nmos-register._tcp.local."

        info = ServiceInfo(service_type,
                           "NMOSTestSuite{}{}.{}".format(port, api_proto, service_type),
                           addresses=[socket.inet_aton(ip)], port=port,
                           properties=txt, server=hostname)
        return info

    def do_node_basics_prereqs(self):
        """Collect a copy of each of the Node's resources"""
        for resource in self.node_basics_data:
            url = "{}{}".format(self.node_url, resource)
            valid, r = self.do_request("GET", url)
            if valid and r.status_code == 200:
                try:
                    self.node_basics_data[resource] = r.json()
                except Exception:
                    pass
    
    def do_registry_basics_prereqs(self):
        """Advertise a registry and collect data from any Nodes which discover it"""

        if self.registry_basics_done:
            return

        if CONFIG.DNS_SD_MODE == "multicast":
            registry_mdns = []
            priority = 100

            # Add advertisement for primary and failover registries
            for registry in self.registries[0:-1]:
                info = self._registry_mdns_info(registry.get_data().port, priority)
                registry_mdns.append(info)
                priority += 10

            # Add the final real registry advertisement
            info = self._registry_mdns_info(self.registries[-1].get_data().port, priority)
            registry_mdns.append(info)

        # Reset all registries to clear previous heartbeats, etc.
        for registry in self.registries:
            registry.reset()

        self.primary_registry.enable()

        if CONFIG.DNS_SD_MODE == "multicast":
            # Advertise the primary registry and invalid ones at pri 0, and allow the Node to do a basic registration
            if self.is04_utils.compare_api_version(self.apis[NODE_API_KEY]["version"], "v1.0") != 0:
                self.zc.register_service(registry_mdns[0])
                self.zc.register_service(registry_mdns[1])
            self.zc.register_service(registry_mdns[2])

        # Wait for n seconds after advertising the service for the first POST from a Node
        start_time = time.time()
        while time.time() < start_time + CONFIG.DNS_SD_ADVERT_TIMEOUT:
            if self.primary_registry.has_registrations():
                break
            time.sleep(0.2)

        # Wait until we're sure the Node has registered everything it intends to, and we've had at least one heartbeat
        while (time.time() - self.primary_registry.last_time) < CONFIG.HEARTBEAT_INTERVAL + 1:
            time.sleep(0.2)

        # Collect matching resources from the Node
        self.do_node_basics_prereqs()

        # Ensure we have two heartbeats from the Node, assuming any are arriving (for test_05)
        if len(self.primary_registry.get_data().heartbeats) > 0:
            # It is heartbeating, but we don't have enough of them yet
            while len(self.primary_registry.get_data().heartbeats) < 2:
                time.sleep(0.2)

            # Once registered, advertise all other registries at different (ascending) priorities
            for index, registry in enumerate(self.registries[1:]):
                registry.enable()

            if CONFIG.DNS_SD_MODE == "multicast":
                for info in registry_mdns[3:]:
                    self.zc.register_service(info)

    def test_01(self, test):
        """
        Test setting up registry for testing and leaving test active for a bit to see if registry can be accessed
        """
        print('Registry will be available for 5 minutes at http://' + get_default_ip() + ':' + str(self.primary_registry.get_data().port))
        time.sleep(300)
        print('5 minutes up')
        return test.PASS()

    def test_02(self, test):
        """
        Set up registry, add node and leave test active for 5 minutes to see if node can be found
        """
        print('Registry will be available for 5 minutes at http://' + get_default_ip() + ':' + str(self.primary_registry.get_data().port))
        time.sleep(300)
        print('5 minutes up')
        return test.PASS(len(self.primary_registry.get_data().heartbeats))
