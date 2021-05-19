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
import json
import socket
import requests
import inspect
from time import sleep
from urllib.parse import parse_qs
from dnslib import QTYPE
from OpenSSL import crypto
from zeroconf_monkey import ServiceBrowser, ServiceInfo, Zeroconf

from ..GenericTest import GenericTest, NMOSTestException, NMOSInitException
from ..IS04Utils import IS04Utils
from .. import Config as CONFIG
from zeroconf_monkey import ServiceBrowser, Zeroconf
from ..MdnsListener import MdnsListener
from ..TestHelper import get_default_ip, load_resolved_schema
from ..TestResult import Test

from flask import Flask, render_template, make_response, abort, Blueprint, flash, request, Response
import random

JTNM_API_KEY = "client-testing"

CACHEBUSTER = random.randint(1, 10000)
app = Flask(__name__)
TEST_API = Blueprint('test_api', __name__)
TESTS_COMPLETE = False
TESTS_CANCELLED = False

@TEST_API.route('/testing', methods=['POST'])
def index():
    """
    Testing cancel/complete buttons to end test suite execution
    """
    global TESTS_COMPLETE, TESTS_CANCELLED

    form = request.form.to_dict()
    if 'button_type' in form:
        if form['button_type'] == 'Cancel':
            TESTS_CANCELLED = True
            print('Tests cancelled')
            return 'Tests cancelled'
        elif form['button_type'] == 'Finish':
            TESTS_COMPLETE = True
            print("Tests completed")
            return 'Tests completed'


class JTNMTest(GenericTest):
    """
    Testing initial set up of new test suite for controller testing
    """
    test_list = {}
    
    def __init__(self, apis, registries, dns_server):
        # JRT: overwrite the spec_path parameter to prevent GenericTest from attempting to download RAML from repo
        apis["client-testing"]["spec_path"] = None
        GenericTest.__init__(self, apis)
        self.authorization = False  # System API doesn't use auth, so don't send tokens in every request
        self.primary_registry = registries[1]
        self.registries = registries[1:]
        self.dns_server = dns_server
        self.jtnm_url = self.apis[JTNM_API_KEY]["url"]
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
        self.is04_utils = IS04Utils(self.jtnm_url)
        self.registry_location = ''

    def set_up_tests(self):
        print('Setting up tests')
        self.zc = Zeroconf()
        self.zc_listener = MdnsListener(self.zc)
        if self.dns_server:
            self.dns_server.load_zone(self.apis[JTNM_API_KEY]["version"], self.protocol, self.authorization,
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
        self.registry_location = get_default_ip() + ':' + str(self.primary_registry.get_data().port)

        if CONFIG.DNS_SD_MODE == "multicast":
            self.zc.register_service(registry_mdns[0])
            self.zc.register_service(registry_mdns[1])
            self.zc.register_service(registry_mdns[2])

        # Once registered, advertise all other registries at different (ascending) priorities
        for index, registry in enumerate(self.registries[1:]):
            registry.enable()

        if CONFIG.DNS_SD_MODE == "multicast":
            for info in registry_mdns[3:]:
                self.zc.register_service(info)

        print('Registry should be available at http://' + get_default_ip() + ':' + str(self.primary_registry.get_data().port))

    def tear_down_tests(self):
        print('Tearing down tests')
        # Clean up mDNS advertisements and disable registries
        # if CONFIG.DNS_SD_MODE == "multicast":
        #     for info in registry_mdns:
        #         self.zc.unregister_service(info)
        global TESTS_COMPLETE, TESTS_CANCELLED
        TESTS_CANCELLED = False
        TESTS_COMPLETE = False

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

        self.registry_location = ''
        JTNMTest.test_list = {}
    
    def run_tests(self, test_name=["all"]):
        """
        Perform tests and return the results as a list
        Overriding GenericTest run_tests to stop after set up since this test suite is user-driven
        """
        # Set up
        global TESTS_COMPLETE, TESTS_CANCELLED
        print('Running')
        test = Test("Test setup", "set_up_tests")
        CONFIG.AUTH_TOKEN = None
        if self.authorization:
            # We write to config here as this needs to be available outside this class
            scopes = []
            for api in self.apis:
                scopes.append(api)
            # Add 'query' permission when mock registry is disabled and existing network registry is used
            if not CONFIG.ENABLE_DNS_SD and "query" not in scopes:
                scopes.append("query")
            CONFIG.AUTH_TOKEN = self.generate_token(scopes, True)
        if CONFIG.PREVALIDATE_API:
            for api in self.apis:
                if "raml" not in self.apis[api] or self.apis[api]["url"] is None:
                    continue
                valid, response = self.do_request("GET", self.apis[api]["url"])
                if not valid:
                    raise NMOSInitException("No API found at {}".format(self.apis[api]["url"]))
                elif response.status_code != 200:
                    raise NMOSInitException("No API found or unexpected error at {} ({})".format(self.apis[api]["url"],
                                                                                                 response.status_code))

        self.set_up_tests()
        self.result.append(test.NA(""))

        # Run tests
        self.execute_tests(test_name)

        while not TESTS_CANCELLED and not TESTS_COMPLETE:
            print('waiting')
            time.sleep(20)

        # TODO move return_results to somewhere else, triggered by user completing tests
        self.return_results()
        return self.result

    def return_results(self):
        """
        Tear down section from GenericTest run_tests to be called once the user has completed the tests
        """
        # Tear down
        test = Test("Test teardown", "tear_down_tests")
        self.tear_down_tests()
        self.result.append(test.NA(""))

        return self.result

    def execute_tests(self, test_names):
        """
        Overriding GenericTest execute tests to not auto run all of the tests.
        Produces dict of test names and descriptions
        """
        for test in test_names:
            method = getattr(self, test)
            if callable(method):
                t = Test(inspect.getdoc(method), test)
                question, answers = method()
                json_out = {
                    'name': test,
                    'description': inspect.getdoc(method),
                    'question': question,
                    'answers': answers,
                    'time_sent': time.time(),
                    'url_for_response': request.headers.get('Host'),
                    'answer_response': '',
                    'time_answered': ''
                }
                # Send questions to jtnm testing API endpoint then wait
                valid, response = self.do_request("POST", self.apis[JTNM_API_KEY]["url"], json=json_out)
                time.sleep(20)
                # Do something to retrieve user response
                # Validate response and add to results
                # self.result.append(method(False, t, response.json['answer_response']))

    def _registry_mdns_info(self, port, priority=0, api_ver=None, api_proto=None, api_auth=None, ip=None):
        """Get an mDNS ServiceInfo object in order to create an advertisement"""
        if api_ver is None:
            api_ver = self.apis[JTNM_API_KEY]["version"]
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

        service_type = "_nmos-register._tcp.local."

        info = ServiceInfo(service_type,
                           "NMOSTestSuite{}{}.{}".format(port, api_proto, service_type),
                           addresses=[socket.inet_aton(ip)], port=port,
                           properties=txt, server=hostname)
        return info
    
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
            self.zc.register_service(registry_mdns[0])
            self.zc.register_service(registry_mdns[1])
            self.zc.register_service(registry_mdns[2])

        # Once registered, advertise all other registries at different (ascending) priorities
        for index, registry in enumerate(self.registries[1:]):
            registry.enable()

        if CONFIG.DNS_SD_MODE == "multicast":
            for info in registry_mdns[3:]:
                self.zc.register_service(info)

    def test_01(self, setup=True, test=None, answer=None):
        """
        Example test 1
        """
        test_question = 'What is your name?'
        test_answers = ['Sir Robin of Camelot', 'Sir Galahad of Camelot', 'Arthur, King of the Britons']
        if setup:
            return test_question, test_answers
        else:
            if answer == 'Arthur, King of the Britons':
                return test.PASS('I didn\'t vote for him')
            else:
                return test.FAIL('Knight of the round table')

    def test_02(self, setup=True, test=None, answer=None):
        """
        Example test 2
        """
        test_question = 'What is your Quest?'
        test_answers = ['To find a shrubbery', 'To seek the Holy Grail']
        if setup:
            return test_question, test_answers
        else:
            if answer == 'To seek the Holy Grail':
                return test.PASS('The Grail awaits')
            else:
                return test.FAIL('Ni')

    def test_03(self, setup=True, test=None, answer=None):
        """
        Example test 3
        """
        test_question = 'What is your favourite colour?'
        test_answers = ['Blue', 'Yellow']
        if setup:
            return test_question, test_answers
        else:
            if answer == 'Yellow':
                return test.PASS('Off you go then')
            else:
                return test.FAIL('Ahhhhhhhhh')
