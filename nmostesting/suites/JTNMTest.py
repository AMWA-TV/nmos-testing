# Copyright (C) 2021 Advanced Media Workflow Association
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

import asyncio
import time
import json
import socket
import uuid
import inspect
import random
from copy import deepcopy
from urllib.parse import urlparse
from dnslib import QTYPE
from git.objects.base import IndexObject
from zeroconf_monkey import ServiceBrowser, ServiceInfo, Zeroconf

from ..GenericTest import GenericTest, NMOSTestException, NMOSInitException
from .. import Config as CONFIG
from ..MdnsListener import MdnsListener
from ..TestHelper import get_default_ip
from ..TestResult import Test

from flask import Flask, render_template, make_response, abort, Blueprint, flash, request, Response, session

JTNM_API_KEY = "client-testing"
REG_API_KEY = "registration"
CALLBACK_ENDPOINT = "/clientfacade_response"
CACHEBUSTER = random.randint(1, 10000)

# asyncio queue for passing client façade answer responses back to tests
_event_loop = asyncio.new_event_loop()
asyncio.set_event_loop(_event_loop)
_answer_response_queue = asyncio.Queue()

app = Flask(__name__)
TEST_API = Blueprint('test_api', __name__)

class ClientFacadeException(Exception):
    """Provides a way to exit a single test, by providing the TestResult return statement as the first exception
       parameter"""
    pass

@TEST_API.route(CALLBACK_ENDPOINT, methods=['POST'])
def retrieve_answer():

    if request.method == 'POST':
        clientfacade_answer_json = request.json
        if 'name' not in request.json:
            return 'Invalid JSON received'

        _event_loop.call_soon_threadsafe(_answer_response_queue.put_nowait, request.json)

    return 'OK'

class JTNMTest(GenericTest):
    """
    Testing initial set up of new test suite for controller testing
    """
    def __init__(self, apis, registries, node, dns_server):
        # JRT: remove the spec_path parameter to prevent GenericTest from attempting to download RAML from repo
        apis[JTNM_API_KEY].pop("spec_path", None)
        GenericTest.__init__(self, apis)
        self.authorization = False  # System API doesn't use auth, so don't send tokens in every request
        self.primary_registry = registries[1]
        self.node = node
        self.dns_server = dns_server
        self.registry_mdns = []
        self.zc = None
        self.zc_listener = None
        self.mock_registry_base_url = ''
        self.mock_node_base_url = ''
        self.question_timeout = 600 # default timeout in seconds
        self.test_data = self.load_resource_data()
        self.senders = [] # sender list containing: {'label': '', 'description': '', 'id': '', 'registered': True/False, 'answer_str': ''}
        self.receivers = [] # receiver list containing: {'label': '', 'description': '', 'id': '', 'registered': True/False, 'connectable': True/False, 'answer_str': ''}

    def set_up_tests(self):
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

        if CONFIG.DNS_SD_MODE == "multicast":
            priority = 0

            # Add advertisement for primary registry
            info = self._registry_mdns_info(self.primary_registry.get_data().port, priority)
            self.registry_mdns.append(info)

        # Reset registry to clear previous heartbeats, etc.
        self.primary_registry.reset()
        self.primary_registry.enable()
        self.mock_registry_base_url = 'http://' + get_default_ip() + ':' + str(self.primary_registry.get_data().port) + '/'
        self.mock_node_base_url = 'http://' + get_default_ip() + ':' + str(self.node.port) + '/'

        if CONFIG.DNS_SD_MODE == "multicast":
            self.zc.register_service(self.registry_mdns[0])

        # Populate mock registry with senders and receivers and store the results
        self._populate_registry()

        print('Registry should be available at ' + self.mock_registry_base_url)


    def tear_down_tests(self):
        # Clean up mDNS advertisements and disable registries
        if CONFIG.DNS_SD_MODE == "multicast":
            for info in self.registry_mdns:
                self.zc.unregister_service(info)
        self.primary_registry.disable()
        
        # Reset the state of the client testing façade
        self.do_request("POST", self.apis[JTNM_API_KEY]["url"], json={"clear": "True"})

        if self.zc:
            self.zc.close()
            self.zc = None
        if self.dns_server:
            self.dns_server.reset()

        self.mock_registry_base_url = ''
        self.registry_mdns = []
    
    def set_up_test(self):
        """Setup performed before EACH test"""
        self.primary_registry.query_api_called = False

    def execute_tests(self, test_names):
        """Perform tests defined within this class"""
        self.pre_tests_message()

        for test_name in test_names:
            self.execute_test(test_name)

        self.post_tests_message()

    def execute_test(self, test_name):
        """Perform a test defined within this class"""
        self.test_individual = (test_name != "all")

        # Run manually defined tests
        if test_name == "all":
            for method_name in dir(self):
                if method_name.startswith("test_"):
                    method = getattr(self, method_name)
                    if callable(method):
                        print(" * Running " + method_name)
                        test = Test(inspect.getdoc(method), method_name)
                        try:
                            self.set_up_test()
                            self.result.append(method(test))
                        except NMOSTestException as e:
                            self.result.append(e.args[0])
                        except Exception as e:
                            self.result.append(self.uncaught_exception(method_name, e))

        # Run a single test
        if test_name != "auto" and test_name != "all":
            method = getattr(self, test_name)
            if callable(method):
                print(" * Running " + test_name)
                test = Test(inspect.getdoc(method), test_name)
                try:
                    self.set_up_test()
                    self.result.append(method(test))
                except NMOSTestException as e:
                    self.result.append(e.args[0])
                except Exception as e:
                    self.result.append(self.uncaught_exception(test_name, e))

    async def getAnswerResponse(self, timeout):
        return await asyncio.wait_for(_answer_response_queue.get(), timeout=timeout)

    def _send_client_facade_questions(self, test_method_name, question, answers, test_type, timeout=None, multipart_test=None):
        """ 
        Send question and answers to Client Façade
        question:   text to be presented to Test User
        answers:    list of all possible answers
        test_type:  "radio" - one and only one answer
                    "checkbox" - multiple answers
                    "action" - Test User asked to click button, defaults to self.question_timeout
        timeout:    number of seconds before Client Façade times out test
        multipart_test: indicates test uses multiple questions. Default None, should be increasing
                    integers with each subsequent call within the same test
        """

        method = getattr(self, test_method_name)

        question_timeout = timeout if timeout else self.question_timeout
        test_name = test_method_name if not multipart_test else test_method_name + '_' + str(multipart_test)

        json_out = {
            "test_type": test_type,
            "name": test_name,
            "description": inspect.getdoc(method),
            "question": question,
            "answers": answers,
            "time_sent": time.time(),
            "timeout": question_timeout,
            "url_for_response": "http://" + request.headers.get("Host") + CALLBACK_ENDPOINT,
            "answer_response": "",
            "time_answered": ""
        }
        # Send questions to Client Façade API endpoint then wait
        valid, response = self.do_request("POST", self.apis[JTNM_API_KEY]["url"], json=json_out)

        if not valid:
            raise ClientFacadeException("Problem contacting Client Façade: " + response)

        return json_out

    def _wait_for_client_facade(self, test_name, timeout=None):

        question_timeout = timeout if timeout else self.question_timeout

        # Wait for answer response or question timeout in seconds
        try:
            answer_response = _event_loop.run_until_complete(self.getAnswerResponse(timeout=question_timeout))
        except asyncio.TimeoutError:
            raise ClientFacadeException("Test timed out")

        # Basic integrity check for response json
        if answer_response['name'] is None:
            raise ClientFacadeException("Integrity check failed: result format error: " +json.dump(answer_response))

        if answer_response['name'] != test_name:
            raise ClientFacadeException("Integrity check failed: cannot compare result of " + test_name + " with expected result for " + answer_response['name'])
            
        return answer_response

    def _invoke_client_facade(self, question, answers, test_type, timeout=None, multipart_test=None):
        
        # Get the name of the calling test method to use as an identifier
        test_method_name = inspect.currentframe().f_back.f_code.co_name

        json_out = self._send_client_facade_questions(test_method_name, question, answers, test_type, timeout, multipart_test)

        return self._wait_for_client_facade(json_out['name'], timeout)    

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

        txt = {'api_ver': api_ver, 'api_proto': api_proto, 'pri': str(priority), 'api_auth': str(api_auth).lower()}

        service_type = "_nmos-register._tcp.local."

        info = ServiceInfo(service_type,
                           "NMOSTestSuite{}{}.{}".format(port, api_proto, service_type),
                           addresses=[socket.inet_aton(ip)], port=port,
                           properties=txt, server=hostname)
        return info

    def _generate_random_indices(self, index_range, min_index_count=2, max_index_count=4):
        """
        index_range: number of possible indices
        min_index_count, max_index_count: Minimum, maximum number of indices to be returned. 
        """
        indices = list(range(index_range))
        index_count = random.randint(min_index_count, max_index_count)

        return random.sample(indices, index_count)

    def _format_device_metadata(self, label, description, id):
        """ Used to format answers based on device metadata """
        return label + ' (' + description + ', ' + id + ')'

    def _populate_registry(self):
        """This data is baseline data for all tests in the test suite"""
        # Register node
        self._register_node(self.node.id, "AMWA Test Suite Node", "AMWA Test Suite Node")

        # Sender initial details
        self.senders = [{'label': 'Test-node-1/sender/gilmour', 'description': 'Mock sender 1'},
                        {'label': 'Test-node-1/sender/waters', 'description': 'Mock sender 2'},
                        {'label': 'Test-node-1/sender/wright', 'description': 'Mock sender 3'},
                        {'label': 'Test-node-1/sender/mason', 'description': 'Mock sender 4'},
                        {'label': 'Test-node-1/sender/barrett', 'description': 'Mock sender 5'}]

        for sender in self.senders:
            sender["id"] = str(uuid.uuid4())
            sender["device_id"] = str(uuid.uuid4())
            sender["flow_id"] = str(uuid.uuid4())
            sender["source_id"] = str(uuid.uuid4())
            sender["manifest_href"] = self.mock_node_base_url + "video.sdp"
            sender["registered"] = False
            sender["answer_str"] = self._format_device_metadata(sender['label'], sender['description'], sender['id'])

        sender_indices = self._generate_random_indices(len(self.senders))

        # Register randomly chosen senders and generate answer strings
        for i, sender in enumerate(self.senders):
            if i in sender_indices:
                self._register_sender(sender)
                sender['registered'] = True

        # Receiver initial details
        self.receivers = [{'label': 'Test-node-2/receiver/palin', 'description': 'Mock receiver 1'},
                          {'label': 'Test-node-2/receiver/cleese', 'description': 'Mock receiver 2'},
                          {'label': 'Test-node-2/receiver/jones', 'description': 'Mock receiver 3'},
                          {'label': 'Test-node-2/receiver/chapman', 'description': 'Mock receiver 4'},
                          {'label': 'Test-node-2/receiver/idle', 'description': 'Mock receiver 5'},
                          {'label': 'Test-node-2/receiver/gilliam', 'description': 'Mock receiver 6'}]

        for receiver in self.receivers:
            receiver["id"] = str(uuid.uuid4())
            receiver["device_id"] = str(uuid.uuid4())
            receiver["controls_href"] = self.mock_node_base_url + "x-nmos/connection/v1.0/"
            receiver["registered"] = False
            receiver["connectable"] = True
            receiver["answer_str"] = self._format_device_metadata(receiver['label'], receiver['description'], receiver['id'])

        # Generate indices of self.receivers to be registered and some of those to be non connectable
        receiver_indices = self._generate_random_indices(len(self.receivers))

        # Register randomly chosen resources, with some excluding connection api and generate answer strings
        for i in receiver_indices:
            self._register_receiver(self.receivers[i])
            self.receivers[i]['registered'] = True

        # Send registered sender and receiver details over to mock node
        self.node.add_senders(self.senders, self.test_data['sender'])
        self.node.add_receivers(self.receivers, self.test_data['receiver'])

    def load_resource_data(self):
        """Loads test data from files"""
        result_data = dict()
        resources = ["node", "device", "source", "flow", "sender", "receiver"]
        for resource in resources:
            with open("test_data/JTNM/v1.3_{}.json".format(resource)) as resource_data:
                resource_json = json.load(resource_data)
                result_data[resource] = resource_json
        result_data['node']['id'] = self.node.id
        return result_data

    def post_resource(self, test, type, data=None, reg_url=None, codes=None, fail=Test.FAIL, headers=None):
        """
        Perform a POST request on the Registration API to create or update a resource registration.
        Raises an NMOSTestException when the response is not as expected.
        Otherwise, on success, returns values of the Location header and X-Paging-Timestamp debugging header.
        """
        if not data:
            data = self.test_data[type]

        if not reg_url:
            reg_url = self.mock_registry_base_url + 'x-nmos/registration/v1.3/'

        if not codes:
            codes = [200, 201]

        valid, r = self.do_request("POST", reg_url + "resource", json={"type": type, "data": data}, headers=headers)
        if not valid:
            # Hmm - do we need these exceptions as the registry is our own mock registry?
            raise NMOSTestException(fail(test, "Registration API returned an unexpected response: {}".format(r)))

        location = None
        timestamp = None

        wrong_codes = [_ for _ in [200, 201] if _ not in codes]

        if r.status_code in wrong_codes:
            raise NMOSTestException(fail(test, "Registration API returned wrong HTTP code: {}".format(r.status_code)))
        elif r.status_code not in codes:
            raise NMOSTestException(fail(test, "Registration API returned an unexpected response: "
                                               "{} {}".format(r.status_code, r.text)))
        elif r.status_code in [200, 201]:
            # X-Paging-Timestamp is a response header that implementations may include to aid debugging
            if "X-Paging-Timestamp" in r.headers:
                timestamp = r.headers["X-Paging-Timestamp"]
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

        return location, timestamp

    def _register_node(self, node_id, label, description):
        """
        Perform POST requests on the Registration API to create node registration
        Assume that Node has already been registered        
        """
        node_data = deepcopy(self.test_data["node"])
        node_data["id"] = node_id
        node_data['label'] = label
        node_data["description"] = description
        self.post_resource(self, "node", node_data, codes=[201])
        self.node.registry_url = self.mock_registry_base_url

    def _register_sender(self, sender, codes=[201], fail=Test.FAIL):
        """
        Perform POST requests on the Registration API to create sender registration
        Assume that Node has already been registered
        Use to create sender [code=201] or to update existing sender [code=200]
        """
        # use the test data as a template for creating new resources

        # Register device
        device_data = deepcopy(self.test_data["device"])
        device_data["id"] = sender["device_id"]
        device_data["label"] = "AMWA Test Device"
        device_data["description"] = "AMWA Test Device"
        device_data["node_id"] = self.node.id
        device_data["controls"][0]["href"] = self.mock_node_base_url + "x-nmos/connection/v1.0/"
        device_data["senders"] = [ sender["id"] ] 
        device_data["receivers"] = [] 
        self.post_resource(self, "device", device_data, codes=codes, fail=fail)

        # Register source
        source_data = deepcopy(self.test_data["source"])
        source_data["id"] = sender["source_id"]
        source_data["label"] = "AMWA Test Source"
        source_data["description"] = "AMWA Test Source"
        source_data["device_id"] = sender["device_id"]
        self.post_resource(self, "source", source_data, codes=codes, fail=fail)

        # Register flow
        flow_data = deepcopy(self.test_data["flow"])
        flow_data["id"] = sender["flow_id"]
        flow_data["label"] = "AMWA Test Flow"
        flow_data["description"] = "AMWA Test Flow"
        flow_data["device_id"] = sender["device_id"]
        flow_data["source_id"] = sender["source_id"]
        self.post_resource(self, "flow", flow_data, codes=codes, fail=fail)

        # Register sender
        sender_data = deepcopy(self.test_data["sender"])
        sender_data["id"] = sender["id"]
        sender_data["label"] = sender["label"]
        sender_data["description"] = sender["description"]
        sender_data["device_id"] = sender["device_id"]
        sender_data["flow_id"] = sender["flow_id"]  
        sender_data["manifest_href"] = sender["manifest_href"]
        self.post_resource(self, "sender", sender_data, codes=codes, fail=fail)

    def _delete_sender(self, sender):
        
        del_url = self.mock_registry_base_url + 'x-nmos/registration/v1.3/resource/senders/' + sender['id']
        
        valid, r = self.do_request("DELETE", del_url)
        if not valid:
            # Hmm - do we need these exceptions as the registry is our own mock registry?
            raise NMOSTestException(fail(test, "Registration API returned an unexpected response: {}".format(r)))

    def _register_receiver(self, receiver, codes=[201], fail=Test.FAIL):
        """
        Perform POST requests on the Registration API to create receiver registration
        Assume that Node has already been registered
        Use to create receiver [code=201] or to update existing receiver [code=200]
        """
        # use the test data as a template for creating new resources

        # Register device
        device_data = deepcopy(self.test_data["device"])
        device_data["id"] = receiver["device_id"]
        device_data["label"] = "AMWA Test Device"
        device_data["description"] = "AMWA Test Device"
        device_data["node_id"] = self.node.id
        if receiver["connectable"]:
            # Update the controls data with the URL of the mock node
            device_data["controls"][0]["href"] = receiver['controls_href']
        else:
            device_data["controls"] = [] # Remove controls data
        device_data["senders"] = [] 
        device_data["receivers"] = [ receiver["id"] ] 
        self.post_resource(self, "device", device_data, codes=codes, fail=fail)

        # Register receiver
        receiver_data = deepcopy(self.test_data["receiver"])
        receiver_data["id"] = receiver["id"]
        receiver_data["label"] = receiver["label"]
        receiver_data["description"] = receiver["description"]
        receiver_data["device_id"] = receiver["device_id"]
        self.post_resource(self, "receiver", receiver_data, codes=codes, fail=fail)

    def _delete_receiver(self, receiver):
        
        del_url = self.mock_registry_base_url + 'x-nmos/registration/v1.3/resource/receivers/' + receiver['id']
        
        valid, r = self.do_request("DELETE", del_url)
        if not valid:
            # Hmm - do we need these exceptions as the registry is our own mock registry?
            raise NMOSTestException(fail(test, "Registration API returned an unexpected response: {}".format(r)))

        del_url = self.mock_registry_base_url + 'x-nmos/registration/v1.3/resource/devices/' + receiver['device_id']
        
        valid, r = self.do_request("DELETE", del_url)
        if not valid:
            # Hmm - do we need these exceptions as the registry is our own mock registry?
            raise NMOSTestException(fail(test, "Registration API returned an unexpected response: {}".format(r)))

    def pre_tests_message(self):
        """
        Introduction to JT-NM Tested Test Suite
        """
        question =  'These tests validate a Broadcast Controller under Test’s (BCuT) ability to query an IS-04 ' \
        'Registry with the IS-04 Query API and to control a Media Node using the IS-05 Connection ' \
        'Management API.\n\nA Test AMWA IS-04 v1.2/1.3 reference Registry is available on the network, ' \
        'and advertised in the DNS server via unicast DNS-SD\n\n' \
        'Although the test AMWA IS-04 Registry should be discoverable via DNS-SD, for the purposes of developing this testing framework ' \
        'it is also possible to reach the Registry via the following URL:\n\n' + self.mock_registry_base_url + 'x-nmos/query/v1.3\n\n' \
        'Once the BCuT has located the test AMWA IS-04 Registry, please click \'Next\''

        try:
            self._invoke_client_facade(question, [], test_type="action", timeout=600)

        except ClientFacadeException as e:
            # pre_test_introducton timed out
            pass

    def post_tests_message(self):
        """
        JT-NM Tested Test Suite testing complete!
        """
        question =  'JT-NM Tested Test Suite testing complete!\r\n\r\nPlease press \'Next\' to exit the tests'

        try:
            self._invoke_client_facade(question, [], test_type="action", timeout=10)

        except ClientFacadeException as e:
            # post_test_introducton timed out
            pass
    
    def test_01(self, test):
        """
        Ensure BCuT uses DNS-SD to find registry
        """
        if not CONFIG.ENABLE_DNS_SD or CONFIG.DNS_SD_MODE != "multicast":
            return test.DISABLED("This test cannot be performed when ENABLE_DNS_SD is False or DNS_SD_MODE is not "
                                 "'multicast'")

        return test.DISABLED("Test not yet implemented")


    def test_02(self, test):
        """
        Ensure BCuT can access the IS-04 Query API
        """
        try:
            # Question 1 connection
            question = 'Use the BCuT to browse the Senders and Receivers on the discovered Registry via the selected IS-04 Query API.\n\n' \
            'Once you have finished browsing click the \'Next\' button. Successful browsing of the Registry will be automatically logged by the test framework.\n'

            self._invoke_client_facade(question, [], test_type="action")

            # Fail if the REST Query API was not called, and no query subscriptions were made
            # The registry will log calls to the Query API endpoints
            if not self.primary_registry.query_api_called and len(self.primary_registry.subscriptions) == 0:
                return test.FAIL('IS-04 Query API not reached')
            
            return test.PASS('IS-04 Query API reached successfully')

        except ClientFacadeException as e:
            return test.UNCLEAR(e.args[0])

    def test_03(self, test):
        """
        Query API should be able to discover all the senders that are registered in the Registry
        """
        try:
            # Check senders 
            question = 'The BCuT should be able to discover all the Senders that are registered in the Registry.\n\n' \
            'Refresh the BCuT\'s view of the Registry and carefully select the Senders that are available from the following list.' 
            possible_answers = [s['answer_str'] for s in self.senders]
            expected_answers = [s['answer_str'] for s in self.senders if s['registered'] == True]

            actual_answers = self._invoke_client_facade(question, possible_answers, test_type="checkbox")['answer_response']

            if len(actual_answers) != len(expected_answers):
                return test.FAIL('Incorrect sender identified')
            else:
                for answer in actual_answers:
                    if answer not in expected_answers:
                        return test.FAIL('Incorrect sender identified')

            return test.PASS('All devices correctly identified')
        except ClientFacadeException as e:
            return test.UNCLEAR(e.args[0])


    def test_04(self, test):
        """
        Query API should be able to discover all the receivers that are registered in the Registry
        """
        try:
            # Check receivers 
            question = 'The BCuT should be able to discover all the Receivers that are registered in the Registry.\n\n' \
            'Refresh the BCuT\'s view of the Registry and carefully select the Receivers that are available from the following list.'
            possible_answers = [r['answer_str'] for r in self.receivers]
            expected_answers = [r['answer_str'] for r in self.receivers if r['registered'] == True]

            actual_answers = self._invoke_client_facade(question, possible_answers, test_type="checkbox")['answer_response']

            if len(actual_answers) != len(expected_answers):
                return test.FAIL('Incorrect receiver identified')
            else:
                for answer in actual_answers:
                    if answer not in expected_answers:
                        return test.FAIL('Incorrect receiver identified')

            return test.PASS('All devices correctly identified')
        except ClientFacadeException as e:
            return test.UNCLEAR(e.args[0])

    def test_05(self, test):
        """
        Reference Sender is put offline and then back online
        """
        try:
            # Check senders 

            question = 'The BCuT should be able to discover and dynamically update all the Senders that are registered in the Registry.\n\n' \
                'Use the BCuT to browse and take note of the Senders that are available.\n\n' \
                'After the \'Next\' button has been clicked one of those senders will be put \'offline\'.'
            possible_answers = []

            self._invoke_client_facade(question, possible_answers, test_type="action")

            # Take one of the senders offline
            possible_answers = [s['answer_str'] for s in self.senders if s['registered'] == True]
            answer_indices = [index for index, s in enumerate(self.senders) if s['registered'] == True]
            offline_sender_index = random.choice(answer_indices)
            expected_answer = self.senders[offline_sender_index]['answer_str']

            self._delete_sender(self.senders[offline_sender_index])

            # Set the offline sender to registered false for future tests
            self.senders[offline_sender_index]['registered'] = False

            # Recheck senders
            question = 'Please refresh your BCuT and select the sender which has been put \'offline\''

            actual_answer = self._invoke_client_facade(question, possible_answers, test_type="radio")['answer_response']

            if actual_answer != expected_answer:
                return test.FAIL('Offline/online sender not handled: Incorrect sender identified')

            max_time_until_online = 60
            max_time_to_answer = 30

            question = 'The sender which was put \'offline\' will come back online at a random moment within the next ' + str(max_time_until_online) + ' seconds. ' \
                'As soon as the BCuT detects the sender has come back online please press the \'Next\' button.\n\n' \
                'The button must be pressed within ' + str(max_time_to_answer) + ' seconds of the Sender being put back \'online\'. ' \
                'This includes any latency between the Sender being put \'online\' and the BCuT updating.'
            possible_answers = []

            # Get the name of the calling test method to use as an identifier
            test_method_name = inspect.currentframe().f_code.co_name

            # Send the question to the Client Façade and then put sender online before waiting for the Client Facade response
            sent_json = self._send_client_facade_questions(test_method_name, question, possible_answers, test_type="action")

            # Wait a random amount of time before bringing sender back online
            time.sleep(random.randint(10, max_time_until_online))

            time_online = time.time()

            # Re-register sender
            self._register_sender(self.senders[offline_sender_index], codes=[200, 201])

            response = self._wait_for_client_facade(sent_json['name'])    

            if response['time_answered'] < time_online: # Answered before sender put online
                return test.FAIL('Offline/online sender not handled: Sender not yet online')
            elif response['time_answered'] > time_online + max_time_to_answer:
                return test.FAIL('Offline/online sender not handled: Sender online '  + str(int(response['time_answered'] - time_online)) + ' seconds ago')
            else:
                return test.PASS('Offline/online sender handled correctly')                
        except ClientFacadeException as e:
            return test.UNCLEAR(e.args[0])

    def test_06(self, test):
        """
        Identify which Receiver devices are controllable via IS-05
        """
        try:
            # Register receivers, some of which are non connectable
                    # Receiver initial details
            test_06_receivers = [{'label': 'Test-node-2/receiver/byrne', 'description': 'Mock receiver 7'},
                              {'label': 'Test-node-2/receiver/frantz', 'description': 'Mock receiver 8'},
                              {'label': 'Test-node-2/receiver/weymouth', 'description': 'Mock receiver 9'},
                              {'label': 'Test-node-2/receiver/harrison', 'description': 'Mock receiver 10'}]

            for receiver in test_06_receivers:
                receiver["id"] = str(uuid.uuid4())
                receiver["device_id"] = str(uuid.uuid4())
                receiver["controls_href"] = self.mock_node_base_url + "x-nmos/connection/v1.0/"
                receiver["registered"] = True
                receiver["connectable"] = random.choice([True, False])
                receiver["answer_str"] = self._format_device_metadata(receiver['label'], receiver['description'], receiver['id'])
                self._register_receiver(receiver)

            # Check receivers 
            question = 'Some of the discovered Receivers are controllable via IS-05, for instance, allowing Senders to be connected. ' \
                'Additional Receivers have just been registered with the Registry, a subset of which have a connection API.\n\n' \
                'Please refresh your BCuT and select the Receivers that have a connection API from the list below.\n\n' \
                'Be aware that if your BCuT only displays Receivers which have a connection API, some of the Receivers in the following list may not be visible.'
            possible_answers = [r['answer_str'] for r in test_06_receivers]
            expected_answers = [r['answer_str'] for r in test_06_receivers if r['connectable'] == True]

            actual_answers = self._invoke_client_facade(question, possible_answers, test_type="checkbox")['answer_response']

            if len(actual_answers) != len(expected_answers):
                return test.FAIL('Incorrect Receiver identified')
            else:
                for answer in actual_answers:
                    if answer not in expected_answers:
                        return test.FAIL('Incorrect Receiver identified')

            return test.PASS('All Receivers correctly identified')
        except ClientFacadeException as e:
            return test.UNCLEAR(e.args[0])
        finally:
            #Delete receivers
            for receiver in test_06_receivers:
                self._delete_receiver(receiver)

    def test_07(self, test):
        """
        Instruct Receiver to subscribe to a Sender’s Flow via IS-05
        """

        return test.DISABLED("Test not yet implemented")

    def test_08(self, test):
        """
        Disconnecting a Receiver from a connected Flow via IS-05
        """

        return test.DISABLED("Test not yet implemented")

    def test_09(self, test):
        """
        Indicating the state of connections via updates received from the IS-04 Query API
        """

        return test.DISABLED("Test not yet implemented")

