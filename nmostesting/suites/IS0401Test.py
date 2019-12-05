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

import time
import socket
from requests.compat import json
from urllib.parse import urlparse
from dnslib import QTYPE
from copy import deepcopy
from zeroconf_monkey import ServiceBrowser, ServiceInfo, Zeroconf

from .. import Config as CONFIG
from ..MdnsListener import MdnsListener
from ..GenericTest import GenericTest, NMOSTestException, NMOS_WIKI_URL
from ..IS04Utils import IS04Utils
from ..TestHelper import get_default_ip

NODE_API_KEY = "node"


class IS0401Test(GenericTest):
    """
    Runs IS-04-01-Test
    """
    def __init__(self, apis, registries, node, dns_server):
        GenericTest.__init__(self, apis)
        self.invalid_registry = registries[0]
        self.primary_registry = registries[1]
        self.registries = registries[1:]
        self.node = node
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
        self.is04_utils = IS04Utils(self.node_url)
        self.zc = None
        self.zc_listener = None

    def set_up_tests(self):
        self.zc = Zeroconf()
        self.zc_listener = MdnsListener(self.zc)
        if self.dns_server:
            self.dns_server.load_zone(self.apis[NODE_API_KEY]["version"], self.protocol)
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

    def tear_down_tests(self):
        if self.zc:
            self.zc.close()
            self.zc = None
        if self.dns_server:
            self.dns_server.reset()

    def _registry_mdns_info(self, port, priority=0, api_ver=None, api_proto=None, ip=None):
        """Get an mDNS ServiceInfo object in order to create an advertisement"""
        if api_ver is None:
            api_ver = self.apis[NODE_API_KEY]["version"]
        if api_proto is None:
            api_proto = self.protocol

        if ip is None:
            ip = get_default_ip()
            hostname = "nmos-mocks.local."
        else:
            hostname = ip.replace(".", "-") + ".local."

        # TODO: Add another test which checks support for parsing CSV string in api_ver
        txt = {'api_ver': api_ver, 'api_proto': api_proto, 'pri': str(priority), 'api_auth': 'false'}

        service_type = "_nmos-registration._tcp.local."
        if self.is04_utils.compare_api_version(self.apis[NODE_API_KEY]["version"], "v1.3") >= 0:
            service_type = "_nmos-register._tcp.local."

        info = ServiceInfo(service_type,
                           "NMOSTestSuite{}{}.{}".format(port, api_proto, service_type),
                           socket.inet_aton(ip), port, 0, 0,
                           txt, hostname)
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

        if not CONFIG.ENABLE_DNS_SD:
            self.do_node_basics_prereqs()
            return

        if CONFIG.DNS_SD_MODE == "multicast":
            registry_mdns = []
            priority = 0

            # Add advertisement with invalid version
            info = self._registry_mdns_info(self.invalid_registry.get_data().port, priority, "v9.0")
            registry_mdns.append(info)
            # Add advertisement with invalid protocol
            info = self._registry_mdns_info(self.invalid_registry.get_data().port, priority, None, "invalid")
            registry_mdns.append(info)

            # Add advertisement for primary and failover registries
            for registry in self.registries[0:-1]:
                info = self._registry_mdns_info(registry.get_data().port, priority)
                registry_mdns.append(info)
                priority += 10

            # Add a fake advertisement for a timeout simulating registry
            info = self._registry_mdns_info(444, priority, ip="192.0.2.1")
            registry_mdns.append(info)
            priority += 10

            # Add the final real registry advertisement
            info = self._registry_mdns_info(self.registries[-1].get_data().port, priority)
            registry_mdns.append(info)

        # Reset all registries to clear previous heartbeats, etc.
        self.invalid_registry.reset()
        for registry in self.registries:
            registry.reset()

        self.invalid_registry.enable()
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
            if self.invalid_registry.has_registrations():
                break
            time.sleep(0.2)

        # Wait until we're sure the Node has registered everything it intends to, and we've had at least one heartbeat
        while (time.time() - self.primary_registry.last_time) < CONFIG.HEARTBEAT_INTERVAL + 1 or \
              (time.time() - self.invalid_registry.last_time) < CONFIG.HEARTBEAT_INTERVAL + 1:
            time.sleep(0.2)

        # Collect matching resources from the Node
        self.do_node_basics_prereqs()

        # Ensure we have two heartbeats from the Node, assuming any are arriving (for test_05)
        if len(self.primary_registry.get_data().heartbeats) > 0 or len(self.invalid_registry.get_data().heartbeats) > 0:
            # It is heartbeating, but we don't have enough of them yet
            while len(self.primary_registry.get_data().heartbeats) < 2 and \
                    len(self.invalid_registry.get_data().heartbeats) < 2:
                time.sleep(0.2)

            # Once registered, advertise all other registries at different (ascending) priorities
            for index, registry in enumerate(self.registries[1:]):
                registry.enable()

            if CONFIG.DNS_SD_MODE == "multicast":
                for info in registry_mdns[3:]:
                    self.zc.register_service(info)

            # Kill registries one by one to collect data around failover
            self.invalid_registry.disable()
            for index, registry in enumerate(self.registries):
                registry.disable()

                # Prevent access to an out of bounds index below
                if (index + 1) >= len(self.registries):
                    break

                # in event of testing HTTPS support, the TLS handshake seems to take nearly 2 seconds, so
                # when the first registry is disabled, an additional few seconds is needed to ensure the node
                # has a chance to make a connection to it, receive the 5xx error, and make a connection to
                # the next one
                if CONFIG.ENABLE_HTTPS:
                    heartbeat_countdown = CONFIG.HEARTBEAT_INTERVAL + 1 + 5
                else:
                    heartbeat_countdown = CONFIG.HEARTBEAT_INTERVAL + 1

                # Wait an extra heartbeat interval when dealing with the timout test
                # This allows a Node's connection to time out and then register with the next mock registry
                if (index + 2) == len(self.registries):
                    heartbeat_countdown += CONFIG.HEARTBEAT_INTERVAL

                while len(self.registries[index + 1].get_data().heartbeats) < 1 and heartbeat_countdown > 0:
                    # Wait until the heartbeat interval has elapsed or a heartbeat has been received
                    time.sleep(0.2)
                    heartbeat_countdown -= 0.2

                if len(self.registries[index + 1].get_data().heartbeats) < 1:
                    # Testing has failed at this point, so we might as well abort
                    break

        # Clean up mDNS advertisements and disable registries
        if CONFIG.DNS_SD_MODE == "multicast":
            for info in registry_mdns:
                self.zc.unregister_service(info)
        self.invalid_registry.disable()
        for index, registry in enumerate(self.registries):
            registry.disable()

        self.registry_basics_done = True
        for registry in self.registries:
            self.registry_basics_data.append(registry.get_data())
        self.registry_invalid_data = self.invalid_registry.get_data()

        # If the Node preferred the invalid registry, don't penalise it for other tests which check the general
        # interactions are correct
        if len(self.registry_invalid_data.posts) > 0:
            self.registry_primary_data = self.registry_invalid_data
        else:
            self.registry_primary_data = self.registry_basics_data[0]

    def test_01(self, test):
        """Node can discover network registration service via multicast DNS"""

        if not CONFIG.ENABLE_DNS_SD or CONFIG.DNS_SD_MODE != "multicast":
            return test.DISABLED("This test cannot be performed when ENABLE_DNS_SD is False or DNS_SD_MODE is not "
                                 "'multicast'")

        self.do_registry_basics_prereqs()

        registry_data = self.registry_primary_data
        if len(registry_data.posts) > 0:
            return test.PASS()

        return test.FAIL("Node did not attempt to register with the advertised registry.")

    def test_01_01(self, test):
        """Node does not attempt to register with an unsuitable registry"""

        if self.is04_utils.compare_api_version(self.apis[NODE_API_KEY]["version"], "v1.0") == 0:
            return test.NA("Nodes running v1.0 do not check DNS-SD api_ver and api_proto TXT records")

        if not CONFIG.ENABLE_DNS_SD or CONFIG.DNS_SD_MODE != "multicast":
            return test.DISABLED("This test cannot be performed when ENABLE_DNS_SD is False or DNS_SD_MODE is not "
                                 "'multicast'")

        self.do_registry_basics_prereqs()

        if len(self.registry_invalid_data.posts) > 0:
            return test.FAIL("Node incorrectly registered with a registry advertising an invalid 'api_ver' or "
                             "'api_proto'")

        return test.PASS()

    def test_02(self, test):
        """Node can discover network registration service via unicast DNS"""

        if not CONFIG.ENABLE_DNS_SD or CONFIG.DNS_SD_MODE != "unicast":
            return test.DISABLED("This test cannot be performed when ENABLE_DNS_SD is False or DNS_SD_MODE is not "
                                 "'unicast'")

        self.do_registry_basics_prereqs()

        registry_data = self.registry_primary_data
        if len(registry_data.posts) > 0:
            return test.PASS()

        return test.FAIL("Node did not attempt to register with the advertised registry.")

    def test_02_01(self, test):
        """Node does not attempt to register with an unsuitable registry"""

        if self.is04_utils.compare_api_version(self.apis[NODE_API_KEY]["version"], "v1.0") == 0:
            return test.NA("Nodes running v1.0 do not check DNS-SD api_ver and api_proto TXT records")

        if not CONFIG.ENABLE_DNS_SD or CONFIG.DNS_SD_MODE != "unicast":
            return test.DISABLED("This test cannot be performed when ENABLE_DNS_SD is False or DNS_SD_MODE is not "
                                 "'unicast'")

        self.do_registry_basics_prereqs()

        if len(self.registry_invalid_data.posts) > 0:
            return test.FAIL("Node incorrectly registered with a registry advertising an invalid 'api_ver' or "
                             "'api_proto'")

        return test.PASS()

    def test_03(self, test):
        """Registration API interactions use the correct headers"""

        if not CONFIG.ENABLE_DNS_SD:
            return test.DISABLED("This test cannot be performed when ENABLE_DNS_SD is False")

        self.do_registry_basics_prereqs()

        registry_data = self.registry_primary_data
        if len(registry_data.posts) == 0:
            return test.UNCLEAR("No registrations found")

        ctype_warn = ""
        for resource in registry_data.posts:
            ctype_valid, ctype_message = self.check_content_type(resource[1]["headers"])
            if not ctype_valid:
                return test.FAIL(ctype_message)
            elif ctype_message and not ctype_warn:
                ctype_warn = ctype_message

            accept_valid, accept_message = self.check_accept(resource[1]["headers"])
            if not accept_valid:
                return test.FAIL(accept_message)

            if "Transfer-Encoding" not in resource[1]["headers"]:
                if "Content-Length" not in resource[1]["headers"]:
                    return test.FAIL("One or more Node POSTs did not include Content-Length")
            else:
                if "Content-Length" in resource[1]["headers"]:
                    return test.FAIL("API signalled both Transfer-Encoding and Content-Length")

        if ctype_warn:
            return test.WARNING(ctype_warn)
        else:
            return test.PASS()

    def test_03_01(self, test):
        """Registration API interactions use the correct versioned path"""

        if not CONFIG.ENABLE_DNS_SD:
            return test.DISABLED("This test cannot be performed when ENABLE_DNS_SD is False")

        api = self.apis[NODE_API_KEY]

        self.do_registry_basics_prereqs()

        registry_data = self.registry_primary_data
        if len(registry_data.posts) == 0:
            return test.UNCLEAR("No registrations found")

        for resource in registry_data.posts:
            if resource[1]["version"] != api["version"]:
                return test.FAIL("One or more Node POSTs used version '{}' instead of '{}'"
                                 .format(resource[1]["version"], api["version"]))

        for resource in registry_data.deletes:
            if resource[1]["version"] != api["version"]:
                return test.FAIL("One or more Node DELETEs used version '{}' instead of '{}'"
                                 .format(resource[1]["version"], api["version"]))

        for resource in registry_data.heartbeats:
            if resource[1]["version"] != api["version"]:
                return test.FAIL("One or more Node heartbeats used version '{}' instead of '{}'"
                                 .format(resource[1]["version"], api["version"]))

        return test.PASS()

    def get_registry_resource(self, res_type, res_id):
        """Get a specific resource ID from the mock registry, or a real registry if DNS-SD is disabled"""
        found_resource = None
        if CONFIG.ENABLE_DNS_SD:
            # Look up data in local mock registry
            registry_data = self.registry_primary_data
            for resource in registry_data.posts:
                if resource[1]["payload"]["type"] == res_type and resource[1]["payload"]["data"]["id"] == res_id:
                    found_resource = resource[1]["payload"]["data"]
        else:
            # Look up data from a configured Query API
            url = "{}://{}:{}/x-nmos/query/{}/{}s/{}".format(
                self.protocol,
                CONFIG.QUERY_API_HOST,
                str(CONFIG.QUERY_API_PORT),
                self.apis[NODE_API_KEY]["version"],
                res_type,
                res_id
            )

            try:
                valid, r = self.do_request("GET", url)
                if valid and r.status_code == 200:
                    found_resource = r.json()
                else:
                    raise Exception
            except Exception:
                print(" * ERROR: Unable to load resource from the configured Query API ({}:{})".format(
                    CONFIG.QUERY_API_HOST,
                    CONFIG.QUERY_API_PORT
                ))
        return found_resource

    def get_node_resources(self, res_type):
        """Get resources matching a specific type from the Node API"""
        if res_type == "node":
            res_type = "self"
        else:
            res_type = res_type + "s"
        resp_json = self.node_basics_data[res_type]
        resources = {}
        if resp_json is None:
            raise ValueError
        elif isinstance(resp_json, dict):
            resources[resp_json["id"]] = resp_json
        else:
            for resource in resp_json:
                resources[resource["id"]] = resource
        return resources

    def do_test_matching_resource(self, test, res_type):
        """Check that a resource held in the registry matches the resource held by the Node API"""
        try:
            node_resources = self.get_node_resources(res_type)

            if len(node_resources) == 0:
                return test.UNCLEAR("No {} resources were found on the Node.".format(res_type.title()))

            for res_id in node_resources:
                reg_resource = self.get_registry_resource(res_type, res_id)
                if not reg_resource:
                    return test.FAIL("{} {} was not found in the registry.".format(res_type.title(), res_id))
                elif reg_resource != node_resources[res_id]:
                    return test.FAIL("Node API JSON does not match data in registry for "
                                     "{} {}.".format(res_type.title(), res_id))

            return test.PASS()
        except ValueError:
            return test.FAIL("Failed to reach Node API or invalid JSON received!")

    def parent_resource_type(self, res_type):
        """Find the parent resource type required for a given resource type"""
        if res_type == "device":
            return "node"
        elif res_type == "flow" and \
                self.is04_utils.compare_api_version(self.apis[NODE_API_KEY]["version"], "v1.0") <= 0:
            return "source"
        elif res_type in ["sender", "receiver", "source", "flow"]:
            return "device"
        else:
            return None

    def preceding_resource_type(self, res_type):
        """Find the preceding resource type recommended for a given resource type,
        if different than the parent resource type"""
        # The recommendation ensures e.g. that a Query API client would find the Source and Flow
        # associated with a particular Sender
        if res_type == "flow" and \
                self.is04_utils.compare_api_version(self.apis[NODE_API_KEY]["version"], "v1.0") > 0:
            return "source"
        elif res_type == "sender":
            return "flow"
        else:
            return None

    def do_test_referential_integrity(self, test, res_type):
        """Check that the parents for a specific resource type are held in the mock registry,
        and the recommended order for referential integrity has been adhered to"""

        api = self.apis[NODE_API_KEY]

        # Look up data in local mock registry
        registry_data = self.registry_primary_data
        parent_type = self.parent_resource_type(res_type)
        registered_parents = []
        preceding_type = self.preceding_resource_type(res_type)
        registered_preceding = []

        preceding_warn = ""
        found_resource = False
        try:
            # Cycle over registrations in order
            for resource in registry_data.posts:
                rtype = resource[1]["payload"]["type"]
                rdata = resource[1]["payload"]["data"]
                if rtype == parent_type:
                    registered_parents.append(rdata["id"])
                elif preceding_type and rtype == preceding_type:
                    registered_preceding.append(rdata["id"])
                elif rtype == res_type:
                    found_resource = True
                    if rdata[parent_type + "_id"] not in registered_parents:
                        return test.FAIL("{} '{}' was registered before its referenced '{}' '{}'"
                                         .format(res_type.title(), rdata["id"],
                                                 parent_type + "_id", rdata[parent_type + "_id"]))
                    if preceding_type and rdata[preceding_type + "_id"] not in registered_preceding \
                            and not preceding_warn:
                        preceding_warn = "{} '{}' was registered before its referenced '{}' '{}'" \
                                         .format(res_type.title(), rdata["id"],
                                                 preceding_type + "_id", rdata[preceding_type + "_id"])
            if preceding_warn:
                return test.WARNING(preceding_warn,
                                    "https://amwa-tv.github.io/nmos-discovery-registration/branches/{}"
                                    "/docs/4.1._Behaviour_-_Registration.html#referential-integrity"
                                    .format(api["spec_branch"]))
            elif found_resource:
                return test.PASS()
            else:
                return test.UNCLEAR("No {} resources were registered with the mock registry.".format(res_type.title()))
        except KeyError as e:
            return test.FAIL("Unable to find expected key in the registered {}: {}".format(res_type.title(), e))

    def test_04(self, test):
        """Node can register a valid Node resource with the network registration service,
        matching its Node API self resource"""

        self.do_registry_basics_prereqs()

        return self.do_test_matching_resource(test, "node")

    def test_05(self, test):
        """Node maintains itself in the registry via periodic calls to the health resource"""

        if not CONFIG.ENABLE_DNS_SD:
            return test.DISABLED("This test cannot be performed when ENABLE_DNS_SD is False")

        api = self.apis[NODE_API_KEY]

        self.do_registry_basics_prereqs()

        registry_data = self.registry_primary_data
        if len(registry_data.heartbeats) < 2:
            return test.FAIL("Not enough heartbeats were made in the time period.")

        initial_node = registry_data.posts[0]

        last_hb = None
        for heartbeat in registry_data.heartbeats:
            # Ensure the Node ID for heartbeats matches the registrations
            if heartbeat[1]["node_id"] != initial_node[1]["payload"]["data"]["id"]:
                return test.FAIL("Heartbeats matched a different Node ID to the initial registration.")

            if last_hb:
                # Check frequency of heartbeats matches the defaults
                time_diff = heartbeat[0] - last_hb[0]
                if time_diff > CONFIG.HEARTBEAT_INTERVAL + 0.5:
                    return test.FAIL("Heartbeats are not frequent enough.")
                elif time_diff < CONFIG.HEARTBEAT_INTERVAL - 0.5:
                    return test.FAIL("Heartbeats are too frequent.")
            else:
                # For first heartbeat, check against Node registration
                if (heartbeat[0] - initial_node[0]) > CONFIG.HEARTBEAT_INTERVAL + 0.5:
                    return test.FAIL("First heartbeat occurred too long after initial Node registration.")

            # Ensure the heartbeat request body is empty
            if heartbeat[1]["payload"] is not bytes():
                return test.WARNING("Heartbeat POST contained a payload body.",
                                    "https://amwa-tv.github.io/nmos-discovery-registration/branches/{}"
                                    "/docs/2.2._APIs_-_Client_Side_Implementation_Notes.html#empty-request-bodies"
                                    .format(api["spec_branch"]))

            if "Content-Type" in heartbeat[1]["headers"]:
                return test.WARNING("Heartbeat POST contained a Content-Type header.",
                                    "https://amwa-tv.github.io/nmos-discovery-registration/branches/{}"
                                    "/docs/2.2._APIs_-_Client_Side_Implementation_Notes.html#empty-request-bodies"
                                    .format(api["spec_branch"]))

            if "Transfer-Encoding" not in heartbeat[1]["headers"]:
                if "Content-Length" not in heartbeat[1]["headers"] or \
                        int(heartbeat[1]["headers"]["Content-Length"]) != 0:
                    # The NMOS spec currently says Content-Length: 0 is OPTIONAL, but it is RECOMMENDED in RFC 7230
                    # and omitting it causes problems for commonly deployed HTTP servers
                    return test.WARNING("Heartbeat POST did not contain a valid Content-Length header.",
                                        "https://amwa-tv.github.io/nmos-discovery-registration/branches/{}"
                                        "/docs/2.2._APIs_-_Client_Side_Implementation_Notes.html#empty-request-bodies"
                                        .format(api["spec_branch"]))
            else:
                if "Content-Length" in heartbeat[1]["headers"]:
                    return test.FAIL("API signalled both Transfer-Encoding and Content-Length")

            accept_valid, accept_message = self.check_accept(heartbeat[1]["headers"])
            if not accept_valid:
                return test.FAIL(accept_message)

            last_hb = heartbeat

        return test.PASS()

    def test_07(self, test):
        """Node can register a valid Device resource with the network registration service, matching its
        Node API Device resource"""

        self.do_registry_basics_prereqs()

        return self.do_test_matching_resource(test, "device")

    def test_07_01(self, test):
        """Registered Device was POSTed after a matching referenced Node"""

        if not CONFIG.ENABLE_DNS_SD:
            return test.DISABLED("This test cannot be performed when ENABLE_DNS_SD is False")

        self.do_registry_basics_prereqs()

        return self.do_test_referential_integrity(test, "device")

    def test_08(self, test):
        """Node can register a valid Source resource with the network
        registration service, matching its Node API Source resource"""

        self.do_registry_basics_prereqs()

        return self.do_test_matching_resource(test, "source")

    def test_08_01(self, test):
        """Registered Source was POSTed after a matching referenced Device"""

        if not CONFIG.ENABLE_DNS_SD:
            return test.DISABLED("This test cannot be performed when ENABLE_DNS_SD is False")

        self.do_registry_basics_prereqs()

        return self.do_test_referential_integrity(test, "source")

    def test_09(self, test):
        """Node can register a valid Flow resource with the network
        registration service, matching its Node API Flow resource"""

        self.do_registry_basics_prereqs()

        return self.do_test_matching_resource(test, "flow")

    def test_09_01(self, test):
        """Registered Flow was POSTed after a matching referenced Device or Source"""

        if not CONFIG.ENABLE_DNS_SD:
            return test.DISABLED("This test cannot be performed when ENABLE_DNS_SD is False")

        self.do_registry_basics_prereqs()

        return self.do_test_referential_integrity(test, "flow")

    def test_10(self, test):
        """Node can register a valid Sender resource with the network
        registration service, matching its Node API Sender resource"""

        self.do_registry_basics_prereqs()

        return self.do_test_matching_resource(test, "sender")

    def test_10_01(self, test):
        """Registered Sender was POSTed after a matching referenced Device"""

        if not CONFIG.ENABLE_DNS_SD:
            return test.DISABLED("This test cannot be performed when ENABLE_DNS_SD is False")

        self.do_registry_basics_prereqs()

        return self.do_test_referential_integrity(test, "sender")

    def test_11(self, test):
        """Node can register a valid Receiver resource with the network
        registration service, matching its Node API Receiver resource"""

        self.do_registry_basics_prereqs()

        return self.do_test_matching_resource(test, "receiver")

    def test_11_01(self, test):
        """Registered Receiver was POSTed after a matching referenced Device"""

        if not CONFIG.ENABLE_DNS_SD:
            return test.DISABLED("This test cannot be performed when ENABLE_DNS_SD is False")

        self.do_registry_basics_prereqs()

        return self.do_test_referential_integrity(test, "receiver")

    def test_12(self, test):
        """Node advertises a Node type mDNS announcement with no ver_* TXT records
        in the presence of a Registration API (v1.0, v1.1 and v1.2)"""

        if not CONFIG.ENABLE_DNS_SD:
            return test.DISABLED("This test cannot be performed when ENABLE_DNS_SD is False")

        api = self.apis[NODE_API_KEY]

        if self.is04_utils.compare_api_version(api["version"], "v1.3") >= 0:
            return test.DISABLED("This test is disabled for Nodes >= v1.3")

        node_list = self.collect_mdns_announcements()

        for node in node_list:
            address = socket.inet_ntoa(node.address)
            port = node.port
            if address == api["ip"] and port == api["port"]:
                properties = self.convert_bytes(node.properties)
                for prop in properties:
                    if "ver_" in prop:
                        return test.FAIL("Found 'ver_' TXT record while Node is registered.")

                if self.is04_utils.compare_api_version(api["version"], "v1.1") >= 0:
                    if "api_ver" not in properties:
                        return test.FAIL("No 'api_ver' TXT record found in Node API advertisement.")
                    elif api["version"] not in properties["api_ver"].split(","):
                        return test.FAIL("Node does not claim to support version under test.")

                    if "api_proto" not in properties:
                        return test.FAIL("No 'api_proto' TXT record found in Node API advertisement.")
                    elif properties["api_proto"] != self.protocol:
                        return test.FAIL("API protocol ('api_proto') TXT record is not '{}'.".format(self.protocol))

                if self.is04_utils.compare_api_version(api["version"], "v1.3") >= 0:
                    if "api_auth" not in properties:
                        return test.FAIL("No 'api_auth' TXT record found in Node API advertisement.")
                    elif not isinstance(properties["api_auth"], bool):
                        # zeroconf translates 'true' to True and 'false' to False automatically
                        return test.FAIL("API authorization ('api_auth') TXT record is not one of 'true' or 'false'.")

                return test.PASS()

        return test.WARNING("No matching mDNS announcement found for Node with IP/Port {}:{}. This will not affect "
                            "operation in registered mode but may indicate a lack of support for peer to peer "
                            "operation.".format(api["ip"], api["port"]),
                            NMOS_WIKI_URL + "/IS-04#nodes-peer-to-peer-mode")

    def test_12_01(self, test):
        """Node does not advertise a Node type mDNS announcement in the presence of a Registration API (v1.3+)"""

        if not CONFIG.ENABLE_DNS_SD:
            return test.DISABLED("This test cannot be performed when ENABLE_DNS_SD is False")

        api = self.apis[NODE_API_KEY]

        if self.is04_utils.compare_api_version(api["version"], "v1.3") < 0:
            return test.DISABLED("This test is disabled for Nodes < v1.3")

        node_list = self.collect_mdns_announcements()

        for node in node_list:
            address = socket.inet_ntoa(node.address)
            port = node.port
            if address == api["ip"] and port == api["port"]:
                properties = self.convert_bytes(node.properties)
                if "api_ver" not in properties:
                    return test.FAIL("No 'api_ver' TXT record found in Node API advertisement.")

                min_version_lt_v1_3 = False
                for api_version in properties["api_ver"].split(","):
                    if self.is04_utils.compare_api_version(api_version, "v1.3") < 0:
                        min_version_lt_v1_3 = True

                if not min_version_lt_v1_3:
                    return test.WARNING("Nodes which support v1.3+ only should not advertise via mDNS when in "
                                        "registered mode.")

        return test.PASS()

    def test_13(self, test):
        """PUTing to a Receiver target resource with a Sender resource payload is accepted
        and connects the Receiver to a stream"""

        valid, receivers = self.do_request("GET", self.node_url + "receivers")
        if not valid or receivers.status_code != 200:
            return test.FAIL("Unexpected response from the Node API: {}".format(receivers))

        try:
            formats_tested = []
            for receiver in receivers.json():
                if not receiver["transport"].startswith("urn:x-nmos:transport:rtp"):
                    continue

                try:
                    stream_type = receiver["format"].split(":")[-1]
                except TypeError:
                    return test.FAIL("Unexpected Receiver format: {}".format(receiver))

                # Test each available receiver format once
                if stream_type in formats_tested:
                    continue

                if stream_type not in ["video", "audio", "data", "mux"]:
                    return test.FAIL("Unexpected Receiver format: {}".format(receiver["format"]))

                request_data = self.node.get_sender(stream_type)
                self.do_receiver_put(test, receiver["id"], request_data)

                time.sleep(CONFIG.API_PROCESSING_TIMEOUT)

                valid, response = self.do_request("GET", self.node_url + "receivers/" + receiver["id"])
                if not valid or response.status_code != 200:
                    return test.FAIL("Unexpected response from the Node API: {}".format(receiver))

                receiver = response.json()
                if receiver["subscription"]["sender_id"] != request_data["id"]:
                    return test.FAIL("Node API Receiver {} subscription does not reflect the subscribed "
                                     "Sender ID".format(receiver["id"]))

                api = self.apis[NODE_API_KEY]
                if self.is04_utils.compare_api_version(api["version"], "v1.2") >= 0:
                    if not receiver["subscription"]["active"]:
                        return test.FAIL("Node API Receiver {} subscription does not indicate an active "
                                         "subscription".format(receiver["id"]))

                formats_tested.append(stream_type)

            if len(formats_tested) > 0:
                return test.PASS()
        except json.JSONDecodeError:
            return test.FAIL("Non-JSON response returned from Node API")

        return test.UNCLEAR("Node API does not expose any RTP Receivers")

    def test_14(self, test):
        """PUTing to a Receiver target resource with an empty JSON object payload is accepted and
        disconnects the Receiver from a stream"""

        valid, receivers = self.do_request("GET", self.node_url + "receivers")
        if not valid or receivers.status_code != 200:
            return test.FAIL("Unexpected response from the Node API: {}".format(receivers))

        try:
            test_receiver = None
            for receiver in receivers.json():
                if not receiver["transport"].startswith("urn:x-nmos:transport:rtp"):
                    continue
                test_receiver = receiver
                break

            if test_receiver is not None:
                self.do_receiver_put(test, test_receiver["id"], {})

                time.sleep(CONFIG.API_PROCESSING_TIMEOUT)

                valid, response = self.do_request("GET", self.node_url + "receivers/" + test_receiver["id"])
                if not valid or response.status_code != 200:
                    return test.FAIL("Unexpected response from the Node API: {}".format(test_receiver))

                receiver = response.json()
                if receiver["subscription"]["sender_id"] is not None:
                    return test.FAIL("Node API Receiver {} subscription does not reflect the subscribed "
                                     "Sender ID".format(receiver["id"]))

                api = self.apis[NODE_API_KEY]
                if self.is04_utils.compare_api_version(api["version"], "v1.2") >= 0:
                    if receiver["subscription"]["active"]:
                        return test.FAIL("Node API Receiver {} subscription does not indicate an inactive "
                                         "subscription".format(receiver["id"]))

                return test.PASS()
        except json.JSONDecodeError:
            return test.FAIL("Non-JSON response returned from Node API")

        return test.UNCLEAR("Node API does not expose any RTP Receivers")

    def test_15(self, test):
        """Node correctly selects a Registration API based on advertised priorities"""

        if not CONFIG.ENABLE_DNS_SD:
            return test.DISABLED("This test cannot be performed when ENABLE_DNS_SD is False")

        self.do_registry_basics_prereqs()

        last_hb = None
        last_registry = None
        # All but the first and last registry can be used for priority tests. The last one is reserved for timeout tests
        for index, registry_data in enumerate(self.registry_basics_data[1:-1]):
            if len(registry_data.heartbeats) < 1:
                return test.FAIL("Node never made contact with registry {} advertised on port {}"
                                 .format(index + 1, registry_data.port))

            first_hb_to_registry = registry_data.heartbeats[0]
            if last_hb:
                if first_hb_to_registry < last_hb:
                    return test.FAIL("Node sent a heartbeat to the registry on port {} before the registry on port {}, "
                                     "despite their priorities requiring the opposite behaviour"
                                     .format(registry_data.port, last_registry.port))

            last_hb = first_hb_to_registry
            last_registry = registry_data

        return test.PASS()

    def test_16(self, test):
        """Node correctly fails over between advertised Registration APIs when one fails"""

        if not CONFIG.ENABLE_DNS_SD:
            return test.DISABLED("This test cannot be performed when ENABLE_DNS_SD is False")

        self.do_registry_basics_prereqs()

        # All but the first and last registry can be used for failover tests. The last one is reserved for timeout tests
        for index, registry_data in enumerate(self.registry_basics_data[1:-1]):
            if len(registry_data.heartbeats) < 1:
                return test.FAIL("Node never made contact with registry {} advertised on port {}"
                                 .format(index + 1, registry_data.port))

            if index > 0:
                for resource in registry_data.posts:
                    if resource[1]["payload"]["type"] == "node":
                        return test.FAIL("Node re-registered its resources when it failed over to a new registry, when "
                                         "it should only have issued a heartbeat")

        return test.PASS()

    def test_16_01(self, test):
        """Node correctly handles Registration APIs whose connections time out"""

        if not CONFIG.ENABLE_DNS_SD:
            return test.DISABLED("This test cannot be performed when ENABLE_DNS_SD is False")

        self.do_registry_basics_prereqs()

        # The second to last registry will intentionally cause a timeout. Check here that the Node successfully times
        # out its attempted connection within a heartbeat period and then registers with the next available one.
        registry_data = self.registry_basics_data[-1]
        if len(registry_data.heartbeats) < 1:
            return test.WARNING("Node never made contact with registry {} advertised on port {}"
                                .format(len(self.registry_basics_data), registry_data.port))

        for resource in registry_data.posts:
            if resource[1]["payload"]["type"] == "node":
                return test.WARNING("Node re-registered its resources when it failed over to a new registry, when it "
                                    "should only have issued a heartbeat")

        return test.PASS()

    def test_17(self, test):
        """All Node resources use different UUIDs"""

        uuids = set()
        valid, response = self.do_request("GET", self.node_url + "self")
        if not valid or response.status_code != 200:
            return test.FAIL("Unexpected response from the Node API: {}".format(response))
        try:
            uuids.add(response.json()["id"])
        except json.JSONDecodeError:
            return test.FAIL("Non-JSON response returned from Node API")

        for resource_type in ["devices", "sources", "flows", "senders", "receivers"]:
            valid, response = self.do_request("GET", self.node_url + resource_type)
            if not valid or response.status_code != 200:
                return test.FAIL("Unexpected response from the Node API: {}".format(response))
            try:
                for resource in response.json():
                    if resource["id"] in uuids:
                        return test.FAIL("Duplicate ID '{}' found in Node API '{}' resource".format(resource["id"],
                                                                                                    resource_type))
                    uuids.add(resource["id"])
            except json.JSONDecodeError:
                return test.FAIL("Non-JSON response returned from Node API")

        return test.PASS()

    def test_17_01(self, test):
        """All Devices refer to their attached Senders and Receivers"""

        # store references from Devices to Senders and Receivers
        from_devices = {}
        # store references to Devices from Senders and Receivers
        to_devices = {}

        # get all the Node's Devices
        valid, response = self.do_request("GET", self.node_url + "devices")
        if not valid or response.status_code != 200:
            return test.FAIL("Unexpected response from the Node API: {}".format(response))
        try:
            for resource in response.json():
                from_devices[resource["id"]] = {
                    "senders": set(resource["senders"]),
                    "receivers": set(resource["receivers"])
                }
        except json.JSONDecodeError:
            return test.FAIL("Non-JSON response returned from Node API")

        if len(from_devices) == 0:
            return test.UNCLEAR("Node API does not expose any Devices")

        # get all the Node's Senders and Receivers
        empty_refs = {"senders": set(), "receivers": set()}
        for resource_type in ["senders", "receivers"]:
            valid, response = self.do_request("GET", self.node_url + resource_type)
            if not valid or response.status_code != 200:
                return test.FAIL("Unexpected response from the Node API: {}".format(response))
            try:
                for resource in response.json():
                    id = resource["device_id"]
                    if id not in to_devices:
                        to_devices[id] = deepcopy(empty_refs)
                    to_devices[id][resource_type].add(resource["id"])
            except json.JSONDecodeError:
                return test.FAIL("Non-JSON response returned from Node API")

        found_empty_refs = False

        for id, from_device in from_devices.items():
            if id not in to_devices:
                if from_device == empty_refs:
                    # no Senders or Receivers are attached to this Device
                    continue
                else:
                    return test.FAIL("Device '{}' references one or more unknown Senders or Receivers."
                                     .format(id))
            to_device = to_devices[id]
            if from_device == empty_refs:
                # Device appears not to be populating the deprecated attributes
                found_empty_refs = True
            else:
                for refs in ["senders", "receivers"]:
                    if len(from_device[refs] - to_device[refs]) > 0:
                        return test.FAIL("Device '{}' references one or more unknown {}."
                                         .format(id, refs.title()))
                    elif len(to_device[refs] - from_device[refs]) > 0:
                        return test.FAIL("Device '{}' does not have a reference to one or more of its {}."
                                         .format(id, refs.title()))
                    # else: references from Device to its Senders and Receivers
                    # match references from Senders and Receivers to that Device

        if found_empty_refs:
            return test.WARNING("One or more Devices do not have references to any of their Senders or Receivers. "
                                "(The 'senders' and 'receivers' attributes are deprecated since IS-04 v1.2.)")

        return test.PASS()

    def test_18(self, test):
        """All Node clocks are unique, and relate to any visible Sources' clocks"""

        api = self.apis[NODE_API_KEY]
        if self.is04_utils.compare_api_version(api["version"], "v1.1") < 0:
            return test.NA("Clocks are not available until IS-04 v1.1")

        clocks = set()
        valid, response = self.do_request("GET", self.node_url + "self")
        if not valid or response.status_code != 200:
            return test.FAIL("Unexpected response from the Node API: {}".format(response))
        try:
            for clock in response.json()["clocks"]:
                clock_name = clock["name"]
                if clock_name in clocks:
                    return test.FAIL("Duplicate clock name '{}' found in Node API self resource".format(clock_name))
                clocks.add(clock_name)
        except json.JSONDecodeError:
            return test.FAIL("Non-JSON response returned from Node API")

        valid, response = self.do_request("GET", self.node_url + "sources")
        if not valid or response.status_code != 200:
            return test.FAIL("Unexpected response from the Node API: {}".format(response))
        try:
            for source in response.json():
                clock_name = source["clock_name"]
                if clock_name not in clocks and clock_name is not None:
                    return test.FAIL("Source '{}' uses a non-existent clock name '{}'".format(source["id"], clock_name))
        except json.JSONDecodeError:
            return test.FAIL("Non-JSON response returned from Node API")

        return test.PASS()

    def test_19(self, test):
        """All Node interfaces are unique, and relate to any visible Senders and Receivers' interface_bindings"""

        api = self.apis[NODE_API_KEY]
        if self.is04_utils.compare_api_version(api["version"], "v1.2") < 0:
            return test.NA("Interfaces are not available until IS-04 v1.2")

        interfaces = set()
        valid, response = self.do_request("GET", self.node_url + "self")
        if not valid or response.status_code != 200:
            return test.FAIL("Unexpected response from the Node API: {}".format(response))
        try:
            for interface in response.json()["interfaces"]:
                interface_name = interface["name"]
                if interface_name in interfaces:
                    return test.FAIL("Duplicate interface name '{}' found in Node API self resource"
                                     .format(interface_name))
                interfaces.add(interface_name)
        except json.JSONDecodeError:
            return test.FAIL("Non-JSON response returned from Node API")

        valid, response = self.do_request("GET", self.node_url + "senders")
        if not valid or response.status_code != 200:
            return test.FAIL("Unexpected response from the Node API: {}".format(response))
        try:
            for sender in response.json():
                interface_bindings = sender["interface_bindings"]
                for interface_name in interface_bindings:
                    if interface_name not in interfaces:
                        return test.FAIL("Sender '{}' uses a non-existent interface name '{}'"
                                         .format(sender["id"], interface_name))
        except json.JSONDecodeError:
            return test.FAIL("Non-JSON response returned from Node API")

        valid, response = self.do_request("GET", self.node_url + "receivers")
        if not valid or response.status_code != 200:
            return test.FAIL("Unexpected response from the Node API: {}".format(response))
        try:
            for receiver in response.json():
                interface_bindings = receiver["interface_bindings"]
                for interface_name in interface_bindings:
                    if interface_name not in interfaces:
                        return test.FAIL("Receiver '{}' uses a non-existent interface name '{}'"
                                         .format(receiver["id"], interface_name))
        except json.JSONDecodeError:
            return test.FAIL("Non-JSON response returned from Node API")

        return test.PASS()

    def test_20(self, test):
        """Node's resources correctly signal the current protocol and IP/hostname"""

        found_api_endpoint = False
        found_href = False

        href_hostname_warn = False
        api_endpoint_host_warn = False
        service_href_scheme_warn = False
        service_href_hostname_warn = False
        control_href_scheme_warn = False
        control_href_hostname_warn = False
        manifest_href_scheme_warn = False
        manifest_href_hostname_warn = False

        api = self.apis[NODE_API_KEY]
        valid, response = self.do_request("GET", self.node_url + "self")
        if not valid or response.status_code != 200:
            return test.FAIL("Unexpected response from the Node API: {}".format(response))
        try:
            node_self = response.json()
            if not node_self["href"].startswith(self.protocol + "://"):
                return test.FAIL("Node 'href' does not match the current protocol")
            if node_self["href"].startswith("https://") and urlparse(node_self["href"]).hostname[-1].isdigit():
                href_hostname_warn = True
            if self.is04_utils.compare_api_version(api["version"], "v1.1") >= 0:
                for endpoint in node_self["api"]["endpoints"]:
                    if endpoint["protocol"] != self.protocol:
                        return test.FAIL("One or more Node 'api.endpoints' do not match the current protocol")
                    if endpoint["host"] == api["hostname"] and endpoint["port"] == api["port"]:
                        found_api_endpoint = True
                    if self.is04_utils.compare_urls(node_self["href"], "{}://{}:{}"
                                                    .format(endpoint["protocol"], endpoint["host"], endpoint["port"])):
                        found_href = True
                    if endpoint["protocol"] == "https" and endpoint["host"][-1].isdigit():
                        api_endpoint_host_warn = True
            for service in node_self["services"]:
                href = service["href"]
                if href.startswith("http") and not href.startswith(self.protocol + "://"):
                    # Only warn about these at the end so that more major failures are flagged first
                    # Protocols other than HTTP may be used, so don't incorrectly flag those too
                    service_href_scheme_warn = True
                if href.startswith("https://") and urlparse(href).hostname[-1].isdigit():
                    service_href_hostname_warn = True
        except json.JSONDecodeError:
            return test.FAIL("Non-JSON response returned from Node API")

        if self.is04_utils.compare_api_version(api["version"], "v1.1") >= 0:
            if not found_api_endpoint:
                return test.FAIL("None of the Node 'api.endpoints' match the current protocol, IP/hostname and port")

            if not found_href:
                return test.FAIL("None of the Node 'api.endpoints' match the Node 'href'")

            valid, response = self.do_request("GET", self.node_url + "devices")
            if not valid or response.status_code != 200:
                return test.FAIL("Unexpected response from the Node API: {}".format(response))
            try:
                node_devices = response.json()
                for device in node_devices:
                    for control in device["controls"]:
                        href = control["href"]
                        if href.startswith("http") and not href.startswith(self.protocol + "://"):
                            # Only warn about these at the end so that more major failures are flagged first
                            # Protocols other than HTTP may be used, so don't incorrectly flag those too
                            control_href_scheme_warn = True
                        if href.startswith("https://") and urlparse(href).hostname[-1].isdigit():
                            control_href_hostname_warn = True
            except json.JSONDecodeError:
                return test.FAIL("Non-JSON response returned from Node API")

        valid, response = self.do_request("GET", self.node_url + "senders")
        if not valid or response.status_code != 200:
            return test.FAIL("Unexpected response from the Node API: {}".format(response))
        try:
            node_senders = response.json()
            for sender in node_senders:
                href = sender["manifest_href"]
                if href is not None and href.startswith("http") and not href.startswith(self.protocol + "://"):
                    manifest_href_scheme_warn = True
                if href is not None and href.startswith("https://") and urlparse(href).hostname[-1].isdigit():
                    manifest_href_hostname_warn = True
        except json.JSONDecodeError:
            return test.FAIL("Non-JSON response returned from Node API")

        if href_hostname_warn:
            return test.WARNING("Node 'href' value has an IP address not a hostname")
        elif api_endpoint_host_warn:
            return test.WARNING("One or more Node 'api.endpoints.host' values are an IP address not a hostname")
        elif service_href_hostname_warn:
            return test.WARNING("One or more Node service 'href' values have an IP address not a hostname")
        elif control_href_hostname_warn:
            return test.WARNING("One or more Device control 'href' values have an IP address not a hostname")
        elif manifest_href_hostname_warn:
            return test.WARNING("One or more Sender 'manifest_href' values have an IP address not a hostname")
        elif service_href_scheme_warn:
            return test.WARNING("One or more Node service 'href' values do not match the current protocol")
        elif control_href_scheme_warn:
            return test.WARNING("One or more Device control 'href' values do not match the current protocol")
        elif manifest_href_scheme_warn:
            return test.WARNING("One or more Sender 'manifest_href' values do not match the current protocol")

        return test.PASS()

    def test_21(self, test):
        """Node correctly interprets a 200 code from a registry upon initial registration"""

        if not CONFIG.ENABLE_DNS_SD:
            return test.DISABLED("This test cannot be performed when ENABLE_DNS_SD is False")

        registry_info = self._registry_mdns_info(self.primary_registry.get_data().port, 0)

        # Reset the registry to clear previous heartbeats, and enable in 200 test mode
        self.primary_registry.reset()
        self.primary_registry.enable(first_reg=True)

        if CONFIG.DNS_SD_MODE == "multicast":
            # Advertise a registry at pri 0 and allow the Node to do a basic registration
            self.zc.register_service(registry_info)

        # Wait for n seconds after advertising the service for the first POST and then DELETE from a Node
        self.primary_registry.wait_for_registration(CONFIG.DNS_SD_ADVERT_TIMEOUT)
        self.primary_registry.wait_for_delete(CONFIG.HEARTBEAT_INTERVAL + 1)

        # Wait for the Node to finish its interactions
        while (time.time() - self.primary_registry.last_time) < CONFIG.HEARTBEAT_INTERVAL + 1:
            time.sleep(0.2)

        # By this point we should have had at least one Node POST and a corresponding DELETE
        if CONFIG.DNS_SD_MODE == "multicast":
            self.zc.unregister_service(registry_info)
        self.primary_registry.disable()

        # Get the relevant Node ID
        url = "{}self".format(self.node_url)
        valid, r = self.do_request("GET", url)
        if valid and r.status_code == 200:
            try:
                # Check that a POST and DELETE match the Node's ID
                node_id = r.json()["id"]
                found_post = False
                for resource in self.primary_registry.get_data().posts:
                    if resource[1]["payload"]["type"] == "node" and resource[1]["payload"]["data"]["id"] == node_id:
                        found_post = True
                if not found_post:
                    return test.FAIL("Node did not attempt to make contact with the registry")
                found_delete = False
                found_extra_deletes = False
                for resource in self.primary_registry.get_data().deletes:
                    if resource[1]["type"] == "node" and resource[1]["id"] == node_id:
                        found_delete = True
                    elif resource[1]["type"] != "node":
                        found_extra_deletes = True
                if not found_delete:
                    return test.FAIL("Node did not attempt to DELETE itself having encountered a 200 code on initial "
                                     "registration")
                elif found_extra_deletes:
                    return test.WARNING("Node DELETEd more than just its 'node' resource. This is unnecessary when "
                                        "encountering a 200 code on initial registration")
            except json.JSONDecodeError:
                return test.FAIL("Non-JSON response returned from Node API")
        else:
            return test.FAIL("Unexpected responses from Node API self resource")

        return test.PASS()

    def test_22(self, test):
        """Node resource IDs persist over a reboot"""

        return test.MANUAL("This check must be performed manually, or via use of the following tool",
                           "https://github.com/AMWA-TV/nmos-testing/blob/master/utilities/uuid-checker/README.md")

    def test_23(self, test):
        """Senders and Receivers correctly use BCP-002-01 grouping syntax"""

        found_groups = False
        found_senders_receivers = False
        groups = {"node": {}, "device": {}}
        for resource_name in ["senders", "receivers"]:
            valid, response = self.do_request("GET", self.node_url + resource_name)
            if valid and response.status_code == 200:
                try:
                    for resource in response.json():
                        found_senders_receivers = True
                        if resource["device_id"] not in groups["device"]:
                            groups["device"][resource["device_id"]] = {}
                        for tag_name, tag_value in resource["tags"].items():
                            if tag_name != "urn:x-nmos:tag:grouphint/v1.0":
                                continue
                            if not isinstance(tag_value, list) or len(tag_value) == 0:
                                return test.FAIL("Group tag for {} {} is not an array or has too few items"
                                                 .format(resource_name.capitalize().rstrip("s"), resource["id"]))
                            found_groups = True
                            for group_def in tag_value:
                                group_params = group_def.split(":")
                                group_scope = "device"

                                # Perform basic validation on the group syntax
                                if len(group_params) < 2:
                                    return test.FAIL("Group syntax for {} {} has too few parameters"
                                                     .format(resource_name.capitalize().rstrip("s"), resource["id"]))
                                elif len(group_params) > 3:
                                    return test.FAIL("Group syntax for {} {} has too many parameters"
                                                     .format(resource_name.capitalize().rstrip("s"), resource["id"]))
                                elif len(group_params) == 3:
                                    if group_params[2] not in ["device", "node"]:
                                        return test.FAIL("Group syntax for {} {} uses an invalid group scope: {}"
                                                         .format(resource_name.capitalize().rstrip("s"), resource["id"],
                                                                 group_params[2]))
                                    group_scope = group_params[2]

                                # Ensure we have a reference to the group name stored
                                if group_scope == "node":
                                    if group_params[0] not in groups["node"]:
                                        groups["node"][group_params[0]] = {}
                                    group_ref = groups["node"][group_params[0]]
                                elif group_scope == "device":
                                    if group_params[0] not in groups["device"][resource["device_id"]]:
                                        groups["device"][resource["device_id"]][group_params[0]] = {}
                                    group_ref = groups["device"][resource["device_id"]][group_params[0]]

                                # Check for duplicate roles within groups
                                if group_params[1] in group_ref:
                                    return test.FAIL("Duplicate role found in group {} for resources {} and {}"
                                                     .format(group_params[0], resource["id"],
                                                             group_ref[group_params[1]]))
                                else:
                                    group_ref[group_params[1]] = resource["id"]

                except json.JSONDecodeError:
                    return test.FAIL("Non-JSON response returned from Node API")

        if not found_senders_receivers:
            return test.UNCLEAR("No Sender or Receiver resources were found on the Node")
        elif found_groups:
            return test.PASS()
        else:
            return test.OPTIONAL("No BCP-002-01 groups were identified in Sender or Receiver tags",
                                 "https://amwa-tv.github.io/nmos-grouping/best-practice-natural-grouping.html")

    def test_24(self, test):
        """Periodic Sources specify a 'grain_rate'"""

        valid, response = self.do_request("GET", self.node_url + "sources")
        if valid and response.status_code == 200:
            try:
                for resource in response.json():
                    # Currently testing where it would be particularly unusual to find a non-periodic Source
                    if resource["format"] in ["urn:x-nmos:format:video",
                                              "urn:x-nmos:format:audio",
                                              "urn:x-nmos:format:mux"]:
                        if "grain_rate" not in resource:
                            return test.WARNING("Sources MUST specify a 'grain_rate' if they are periodic")
                if len(response.json()) > 0:
                    return test.PASS()
            except json.JSONDecodeError:
                return test.FAIL("Non-JSON response returned from Node API")

        return test.UNCLEAR("No Source resources were found on the Node")

    def test_24_01(self, test):
        """Periodic Flows' 'grain_rate' is divisible by their parent Source 'grain_rate'"""

        source_valid, source_response = self.do_request("GET", self.node_url + "sources")
        flow_valid, flow_response = self.do_request("GET", self.node_url + "flows")

        if source_valid and flow_valid and source_response.status_code == 200 and flow_response.status_code == 200:
            try:
                sources = {source["id"]: source for source in source_response.json()}
                flows = flow_response.json()
                for flow in flows:
                    if "grain_rate" in flow:
                        source = sources[flow["source_id"]]
                        if "grain_rate" not in source:
                            return test.FAIL("Sources MUST specify a 'grain_rate' when their child Flows specify a "
                                             "'grain_rate'")
                        flow_rate = flow["grain_rate"]
                        if "denominator" not in flow_rate:
                            flow_rate["denominator"] = 1
                        source_rate = source["grain_rate"]
                        if "denominator" not in source_rate:
                            source_rate["denominator"] = 1
                        if ((source_rate["numerator"] * flow_rate["denominator"]) %
                           (flow_rate["numerator"] * source_rate["denominator"])):
                            return test.FAIL("Flow 'grain_rate' MUST be integer divisible by the Source 'grain_rate'")
                if len(flow_response.json()) > 0:
                    return test.PASS()
            except json.JSONDecodeError:
                return test.FAIL("Non-JSON response returned from Node API")
            except KeyError:
                return test.FAIL("No Source found for one or more advertised Flows")

        return test.UNCLEAR("No Source or Flow resources were found on the Node")

    def test_25(self, test):
        """Receivers expose expected 'caps' for their API version"""

        api = self.apis[NODE_API_KEY]
        receivers_valid, receivers_response = self.do_request("GET", self.node_url + "receivers")

        no_receivers = True
        if receivers_valid and receivers_response.status_code == 200:
            try:
                for receiver in receivers_response.json():
                    no_receivers = False
                    if self.is04_utils.compare_api_version(api["version"], "v1.1") >= 0:
                        if "media_types" not in receiver["caps"]:
                            return test.WARNING("Receiver 'caps' should include a list of accepted 'media_types'")
                    if self.is04_utils.compare_api_version(api["version"], "v1.3") >= 0:
                        if receiver["format"] == "urn:x-nmos:format:data" and \
                               receiver["transport"] in ["urn:x-nmos:transport:websocket", "urn:x-nmos:transport:mqtt"]:
                            # Technically this is a bit IS-07 specific, but it may still be best placed here for now
                            if "event_types" not in receiver["caps"]:
                                return test.WARNING("Receiver 'caps' should include a list of accepted 'event_types' "
                                                    "if the Receiver accepts IS-07 events")
            except json.JSONDecodeError:
                return test.FAIL("Non-JSON response returned from Node API")

        if no_receivers:
            return test.UNCLEAR("No Receivers were found on the Node")
        else:
            return test.PASS()

    def do_receiver_put(self, test, receiver_id, data):
        """Perform a PUT to the Receiver 'target' resource with the specified data"""

        valid, put_response = self.do_request("PUT", self.node_url + "receivers/" + receiver_id + "/target", json=data)
        if not valid:
            raise NMOSTestException(test.FAIL("Unexpected response from the Node API: {}".format(put_response)))

        if put_response.status_code == 501:
            api = self.apis[NODE_API_KEY]
            if self.is04_utils.compare_api_version(api["version"], "v1.3") >= 0:
                raise NMOSTestException(test.OPTIONAL("Node indicated that basic connection management is not "
                                                      "supported",
                                                      NMOS_WIKI_URL + "/IS-04#nodes-basic-connection-management"))
            else:
                raise NMOSTestException(test.WARNING("501 'Not Implemented' status code is not supported below API "
                                                     "version v1.3",
                                                     NMOS_WIKI_URL + "/IS-04#nodes-basic-connection-management"))
        elif put_response.status_code != 202:
            raise NMOSTestException(test.FAIL("Receiver target PUT did not produce a 202 response code: "
                                              "{}".format(put_response.status_code)))

        schema = self.get_schema(NODE_API_KEY, "PUT", "/receivers/{receiverId}/target", put_response.status_code)
        valid, message = self.check_response(schema, "PUT", put_response)
        if valid:
            # if message:
            #     return WARNING somehow...
            pass
        else:
            raise NMOSTestException(test.FAIL(message))

    def collect_mdns_announcements(self):
        """Helper function to collect Node mDNS announcements in the presence of a Registration API"""

        registry_info = self._registry_mdns_info(self.primary_registry.get_data().port, 0)

        # Reset the registry to clear previous data, although we won't be checking it
        self.primary_registry.reset()
        self.primary_registry.enable()

        if CONFIG.DNS_SD_MODE == "multicast":
            # Advertise a registry at pri 0 and allow the Node to do a basic registration
            self.zc.register_service(registry_info)

        # Wait for n seconds after advertising the service for the first POST from a Node
        self.primary_registry.wait_for_registration(CONFIG.DNS_SD_ADVERT_TIMEOUT)

        ServiceBrowser(self.zc, "_nmos-node._tcp.local.", self.zc_listener)
        time.sleep(CONFIG.DNS_SD_BROWSE_TIMEOUT)
        node_list = self.zc_listener.get_service_list()

        # Withdraw the registry advertisement now we've performed a browse for Node advertisements
        if CONFIG.DNS_SD_MODE == "multicast":
            self.zc.unregister_service(registry_info)
        self.primary_registry.disable()

        return node_list
