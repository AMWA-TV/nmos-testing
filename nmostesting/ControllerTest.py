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
import uuid
import inspect
import random
from copy import deepcopy
from urllib.parse import urlparse
from dnslib import QTYPE
from threading import Event
from zeroconf_monkey import Zeroconf

from .GenericTest import GenericTest, NMOSTestException
from . import Config as CONFIG
from .MdnsListener import MdnsListener
from .TestHelper import get_default_ip
from .TestResult import Test
from .NMOSUtils import NMOSUtils

from flask import Flask, Blueprint, request

NC_API_KEY = "testing-facade"
REG_API_KEY = "registration"
CALLBACK_ENDPOINT = "/testingfacade_response"
CACHEBUSTER = random.randint(1, 10000)

# asyncio queue for passing Testing Façade answer responses back to tests
_event_loop = asyncio.new_event_loop()
asyncio.set_event_loop(_event_loop)
_answer_response_queue = asyncio.Queue()

# use exit Event to quit tests early that involve waiting for senders/connections 
exitTestEvent = Event()

app = Flask(__name__)
TEST_API = Blueprint('test_api', __name__)

class TestingFacadeException(Exception):
    """Exception thrown due to comms or data errors between NMOS Testing and Testing Façade"""
    pass

@TEST_API.route(CALLBACK_ENDPOINT, methods=['POST'])
def retrieve_answer():

    if request.method == 'POST':
        if 'name' not in request.json:
            return 'Invalid JSON received'

        _event_loop.call_soon_threadsafe(_answer_response_queue.put_nowait, request.json)

        # Interupt any 'sleeps' that are still active 
        exitTestEvent.set()

    return 'OK'

class ControllerTest(GenericTest):
    """
    Testing initial set up of new test suite for controller testing
    """
    def __init__(self, apis, registries, node, dns_server):
        # Remove the spec_path parameter to prevent attempt to download RAML from repo
        apis[NC_API_KEY].pop("spec_path", None)
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
        self.senders_ip_base = '239.3.14.' # Random multicast IP to assign to senders

    def set_up_tests(self):
        self.zc = Zeroconf()
        self.zc_listener = MdnsListener(self.zc)
        if self.dns_server:
            self.dns_server.load_zone(self.apis[NC_API_KEY]["version"], self.protocol, self.authorization,
                                      "test_data/controller/dns_records.zone", CONFIG.PORT_BASE+100)
            self.dns_server.set_expected_query(
                QTYPE.PTR,
                [
                    "_nmos-query._tcp.{}.".format(CONFIG.DNS_DOMAIN)
                ]
            )
        # Reset registry to clear previous heartbeats, etc.
        self.primary_registry.reset()
        self.primary_registry.enable()
        self.mock_registry_base_url = 'http://' + get_default_ip() + ':' + str(self.primary_registry.get_data().port) + '/'
        self.mock_node_base_url = 'http://' + get_default_ip() + ':' + str(self.node.port) + '/'

        # Populate mock registry with senders and receivers and store the results
        self._populate_registry()

        # Set up mock node
        self.node.registry_url = self.mock_registry_base_url

        print('Registry should be available at ' + self.mock_registry_base_url)


    def tear_down_tests(self):

        self.primary_registry.disable()
        
        # Reset the state of the Testing Façade
        self.do_request("POST", self.apis[NC_API_KEY]["url"], json={"clear": "True"})

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

    def _send_testing_facade_questions(self, test_method_name, question, answers, test_type, timeout=None, multipart_test=None, metadata=None):
        """ 
        Send question and answers to Testing Façade
        question:   text to be presented to Test User
        answers:    list of all possible answers
        test_type:  "radio" - one and only one answer
                    "checkbox" - multiple answers
                    "action" - Test User asked to click button, defaults to self.question_timeout
        timeout:    number of seconds before Testing Façade times out test
        multipart_test: indicates test uses multiple questions. Default None, should be increasing
                    integers with each subsequent call within the same test
        metadata: Test details to assist fully automated testing
        """

        method = getattr(self, test_method_name)

        question_timeout = timeout if timeout else self.question_timeout
        question_id = test_method_name if not multipart_test else test_method_name + '_' + str(multipart_test)

        json_out = {
            "test_type": test_type,
            "question_id": question_id,
            "name": test_method_name,
            "description": inspect.getdoc(method),
            "question": question,
            "answers": answers,
            "time_sent": time.time(),
            "timeout": question_timeout,
            "url_for_response": "http://" + get_default_ip() + ":5000" + CALLBACK_ENDPOINT,
            "answer_response": "",
            "time_answered": "",
            "metadata": metadata
        }
        # Send questions to Testing Façade API endpoint then wait
        valid, response = self.do_request("POST", self.apis[NC_API_KEY]["url"], json=json_out)

        if not valid:
            raise TestingFacadeException("Problem contacting Testing Façade: " + response)

        return json_out

    def _wait_for_testing_facade(self, test_name, timeout=None):

        question_timeout = timeout if timeout else self.question_timeout

        # Wait for answer response or question timeout in seconds
        try:
            answer_response = _event_loop.run_until_complete(self.getAnswerResponse(timeout=question_timeout))
        except asyncio.TimeoutError:
            raise TestingFacadeException("Test timed out")

        # Basic integrity check for response json
        if answer_response['name'] is None:
            raise TestingFacadeException("Integrity check failed: result format error: " +json.dump(answer_response))

        if answer_response['name'] != test_name:
            raise TestingFacadeException("Integrity check failed: cannot compare result of " + test_name + " with expected result for " + answer_response['name'])
            
        return answer_response

    def _invoke_testing_facade(self, question, answers, test_type, timeout=None, multipart_test=None, metadata=None):
        
        # Get the name of the calling test method to use as an identifier
        test_method_name = inspect.currentframe().f_back.f_code.co_name

        json_out = self._send_testing_facade_questions(test_method_name, question, answers, test_type, timeout, multipart_test, metadata)

        return self._wait_for_testing_facade(json_out['name'], timeout)    

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
        self.senders = [{'label': 's1/gilmour', 'description': 'Mock sender 1'},
                        {'label': 's2/waters', 'description': 'Mock sender 2'},
                        {'label': 's3/wright', 'description': 'Mock sender 3'},
                        {'label': 's4/mason', 'description': 'Mock sender 4'},
                        {'label': 's5/barrett', 'description': 'Mock sender 5'}]
        for sender in self.senders:
            sender["id"] = str(uuid.uuid4())
            sender["device_id"] = str(uuid.uuid4())
            sender["flow_id"] = str(uuid.uuid4())
            sender["source_id"] = str(uuid.uuid4())
            sender["manifest_href"] = self.mock_node_base_url + "x-nmos/connection/v1.0/single/senders/" + sender["id"] + "/transportfile"
            sender["registered"] = False
            sender["version"] = NMOSUtils.get_TAI_time()
            sender["answer_str"] = self._format_device_metadata(sender['label'], sender['description'], sender['id'])
            # Introduce a short delay to ensure unique version numbers. Version number is used by pagination in lieu of creation or update time
            time.sleep(0.1) 

        sender_indices = self._generate_random_indices(len(self.senders), min_index_count=3) # minumum 3 to force pagination when paging_limit is set to 2

        # Register randomly chosen senders and generate answer strings
        for i, sender in enumerate(self.senders):
            if i in sender_indices:
                self._register_sender(sender)
                sender['registered'] = True

        # Receiver initial details
        self.receivers = [{'label': 'r1/palin', 'description': 'Mock receiver 1'},
                          {'label': 'r2/cleese', 'description': 'Mock receiver 2'},
                          {'label': 'r3/jones', 'description': 'Mock receiver 3'},
                          {'label': 'r4/chapman', 'description': 'Mock receiver 4'},
                          {'label': 'r5/idle', 'description': 'Mock receiver 5'},
                          {'label': 'r6/gilliam', 'description': 'Mock receiver 6'}]

        for receiver in self.receivers:
            receiver["id"] = str(uuid.uuid4())
            receiver["device_id"] = str(uuid.uuid4())
            receiver["controls_href"] = self.mock_node_base_url + "x-nmos/connection/v1.0/"
            receiver["registered"] = False
            receiver["connectable"] = True
            receiver["version"] = NMOSUtils.get_TAI_time()
            receiver["answer_str"] = self._format_device_metadata(receiver['label'], receiver['description'], receiver['id'])
            # Introduce a short delay to ensure unique version numbers. Version number is used by pagination in lieu of creation or update time
            time.sleep(0.1) 

        # Generate indices of self.receivers to be registered and some of those to be non connectable
        receiver_indices = self._generate_random_indices(len(self.receivers), min_index_count=3) # minumum 3 to force pagination when paging_limit is set to 2

        # Register randomly chosen resources, with some excluding connection api and generate answer strings
        for i in receiver_indices:
            self._register_receiver(self.receivers[i])
            self.receivers[i]['registered'] = True

        # Add registered senders and receivers to mock node
        registered_senders = [s for s in self.senders if s['registered'] == True]
        registered_receivers = [r for r in self.receivers if r['registered'] == True]

        self.node.remove_senders() # Remove previouly added senders
        sender_ip = 159
        for sender in registered_senders:
            sender_json = self._create_sender_json(sender)
            self.node.add_sender(sender_json, self.senders_ip_base + str(sender_ip))
            sender_ip += 1

        self.node.remove_receivers() # Remove previouly added receivers
        for receiver in registered_receivers:
            receiver_json = self._create_receiver_json(receiver)
            self.node.add_receiver(receiver_json)

    def load_resource_data(self):
        """Loads test data from files"""
        result_data = dict()
        resources = ["node", "device", "source", "flow", "sender", "receiver"]
        for resource in resources:
            with open("test_data/controller/v1.3_{}.json".format(resource)) as resource_data:
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
        node_data["label"] = label
        node_data["description"] = description
        node_data["version"] = NMOSUtils.get_TAI_time()
        self.post_resource(self, "node", node_data, codes=[201])

    def _create_sender_json(self, sender):
        sender_data = deepcopy(self.test_data["sender"])
        sender_data["id"] = sender["id"]
        sender_data["label"] = sender["label"]
        sender_data["description"] = sender["description"]
        sender_data["device_id"] = sender["device_id"]
        sender_data["flow_id"] = sender["flow_id"]  
        sender_data["manifest_href"] = sender["manifest_href"]
        sender_data["version"] = sender["version"]

        return sender_data

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
        device_data["version"] = sender["version"]
        self.post_resource(self, "device", device_data, codes=codes, fail=fail)

        # Register source
        source_data = deepcopy(self.test_data["source"])
        source_data["id"] = sender["source_id"]
        source_data["label"] = "AMWA Test Source"
        source_data["description"] = "AMWA Test Source"
        source_data["device_id"] = sender["device_id"]
        source_data["version"] = sender["version"]
        self.post_resource(self, "source", source_data, codes=codes, fail=fail)

        # Register flow
        flow_data = deepcopy(self.test_data["flow"])
        flow_data["id"] = sender["flow_id"]
        flow_data["label"] = "AMWA Test Flow"
        flow_data["description"] = "AMWA Test Flow"
        flow_data["device_id"] = sender["device_id"]
        flow_data["source_id"] = sender["source_id"]
        flow_data["version"] = sender["version"]
        self.post_resource(self, "flow", flow_data, codes=codes, fail=fail)

        # Register sender
        sender_data = self._create_sender_json(sender)
        self.post_resource(self, "sender", sender_data, codes=codes, fail=fail)

    def _delete_sender(self, test, sender):
        
        del_url = self.mock_registry_base_url + 'x-nmos/registration/v1.3/resource/senders/' + sender['id']
        
        valid, r = self.do_request("DELETE", del_url)
        if not valid:
            # Hmm - do we need these exceptions as the registry is our own mock registry?
            raise NMOSTestException(test.FAIL(test, "Registration API returned an unexpected response: {}".format(r)))

    def _create_receiver_json(self, receiver):
        # Register receiver
        receiver_data = deepcopy(self.test_data["receiver"])
        receiver_data["id"] = receiver["id"]
        receiver_data["label"] = receiver["label"]
        receiver_data["description"] = receiver["description"]
        receiver_data["device_id"] = receiver["device_id"]
        receiver_data["version"] = receiver["version"]

        return receiver_data

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
        device_data["version"] = receiver["version"] 
        device_data["senders"] = [] 
        device_data["receivers"] = [ receiver["id"] ] 
        self.post_resource(self, "device", device_data, codes=codes, fail=fail)

        # Register receiver
        receiver_data = self._create_receiver_json(receiver)

        self.post_resource(self, "receiver", receiver_data, codes=codes, fail=fail)

    def _delete_receiver(self, test, receiver):
        
        del_url = self.mock_registry_base_url + 'x-nmos/registration/v1.3/resource/receivers/' + receiver['id']
        
        valid, r = self.do_request("DELETE", del_url)
        if not valid:
            # Hmm - do we need these exceptions as the registry is our own mock registry?
            raise NMOSTestException(test.FAIL(test, "Registration API returned an unexpected response: {}".format(r)))

        del_url = self.mock_registry_base_url + 'x-nmos/registration/v1.3/resource/devices/' + receiver['device_id']
        
        valid, r = self.do_request("DELETE", del_url)
        if not valid:
            # Hmm - do we need these exceptions as the registry is our own mock registry?
            raise NMOSTestException(test.FAIL(test, "Registration API returned an unexpected response: {}".format(r)))

    def pre_tests_message(self):
        """
        Introduction to NMOS Controller Test Suite
        """
        dns_sd_enabled = CONFIG.ENABLE_DNS_SD and CONFIG.DNS_SD_MODE == "unicast"

        paragraphs = []
        paragraphs.append('These tests validate a NMOS Controller under Test’s (NCuT) ability to query an IS-04 ' \
            'Registry with the IS-04 Query API and to control a Media Node using the IS-05 Connection ' \
            'Management API.\n\n')

        paragraphs.append('A Test AMWA IS-04 reference Registry is available on the network')

        paragraphs.append(' and is being advertised via unicast DNS-SD.\n\n' if dns_sd_enabled else '.\n\n')

        paragraphs.append('Please ensure that the following configuration has been set on the NCuT machine.\n\n ' \
            '* Ensure that the primary DNS of the NCuT machine has been set to \"' + get_default_ip() + '\". \n' \
            '* Ensure that the NCuT unicast search domain is set to \"' + CONFIG.DNS_DOMAIN + '\". \n\n' \
            'Alternatively it '  if dns_sd_enabled else 'It ')
        
        paragraphs.append('is possible to reach the Registry via the following URL:\n\n' + self.mock_registry_base_url + 'x-nmos/query/v1.3\n\n'\
            'Please ensure the NCuT has located the test AMWA IS-04 Registry before clicking the \'Next\' button.')

        question = ''.join(paragraphs)
                
        try:
            self._invoke_testing_facade(question, [], test_type="action", timeout=600)

        except TestingFacadeException as e:
            # pre_test_introducton timed out
            pass

    def post_tests_message(self):
        """
        NMOS Controller Test Suite complete!
        """
        question =  'NMOS Controller Test Suite complete!\r\n\r\nPlease press the \'Next\' button to exit the tests'

        try:
            self._invoke_testing_facade(question, [], test_type="action", timeout=10)

        except TestingFacadeException as e:
            # post_test_introducton timed out
            pass
    
    #def test_01(self, test):
    #    """
    #    Ensure NCuT uses DNS-SD to find registry
    #    """
    #    if not CONFIG.ENABLE_DNS_SD or CONFIG.DNS_SD_MODE != "unicast":
    #        return test.DISABLED("This test cannot be performed when ENABLE_DNS_SD is False or DNS_SD_MODE is not "
    #                             "'unicast'")

    #    # The DNS server will log queries that have been specified in set_up_tests()
    #    if not self.dns_server.is_query_received():
    #        return test.FAIL('DNS was not queried by the NCuT')
            
    #    return test.PASS('DNS successfully queried by NCuT')

    #def test_02(self, test):
    #    """
    #    Ensure NCuT can access the IS-04 Query API
    #    """
    #    try:
    #        # Question 1 connection
    #        question = 'Use the NCuT to browse the Senders and Receivers on the discovered Registry via the selected IS-04 Query API.\n\n' \
    #        'Once you have finished browsing click the \'Next\' button. \n\n' \
    #        'Successful browsing of the Registry will be automatically logged by the test framework.\n'

    #        self._invoke_testing_facade(question, [], test_type="action")

    #        # Fail if the REST Query API was not called, and no query subscriptions were made
    #        # The registry will log calls to the Query API endpoints
    #        if not self.primary_registry.query_api_called and len(self.primary_registry.subscriptions) == 0:
    #            return test.FAIL('IS-04 Query API not reached')
            
    #        return test.PASS('IS-04 Query API reached successfully')

    #    except TestingFacadeException as e:
    #        return test.UNCLEAR(e.args[0])

    #def test_03(self, test):
    #    """
    #    Query API should be able to discover all the senders that are registered in the Registry
    #    """
    #    try:
    #        # reduce paging limit to force pagination on REST API
    #        self.primary_registry.paging_limit = 2
    #        # Check senders 
    #        question = 'The NCuT should be able to discover all the Senders that are registered in the Registry.\n\n' \
    #        'Refresh the NCuT\'s view of the Registry and carefully select the Senders that are available from the following list.\n\n' \
    #        'For this test the registry paging limit has been set to 2. If your NCuT implements pagination, you must ensure you view ' \
    #        'every available page to complete this test.' 
    #        possible_answers = [{'answer_id': 'answer_'+str(i), 'label': s['label'], 'description': s['description'], 'id': s['id'], 'answer_str': s['answer_str']} for i, s in enumerate(self.senders)]
    #        expected_answers = ['answer_'+str(i) for i, s in enumerate(self.senders) if s['registered'] == True]

    #        actual_answers = self._invoke_testing_facade(question, possible_answers, test_type="checkbox")['answer_response']

    #        if len(actual_answers) != len(expected_answers):
    #            return test.FAIL('Incorrect sender identified')
    #        else:
    #            for answer in actual_answers:
    #                if answer not in expected_answers:
    #                    return test.FAIL('Incorrect sender identified')

    #        if not self.primary_registry.pagination_used and len(self.primary_registry.subscriptions) == 0:
    #            return test.FAIL('Pagination not exercised')
    #        return test.PASS('All devices correctly identified')
    #    except TestingFacadeException as e:
    #        return test.UNCLEAR(e.args[0])
    #    finally:
    #        self.primary_registry.paging_limit = 100

    #def test_04(self, test):
    #    """
    #    Query API should be able to discover all the receivers that are registered in the Registry
    #    """
    #    try:
    #        # reduce paging limit to force pagination on REST API
    #        self.primary_registry.paging_limit = 2

    #        # Check receivers 
    #        question = 'The NCuT should be able to discover all the Receivers that are registered in the Registry.\n\n' \
    #        'Refresh the NCuT\'s view of the Registry and carefully select the Receivers that are available from the following list.\n\n' \
    #        'For this test the registry paging limit has been set to 2. If your NCuT implements pagination, you must ensure you view ' \
    #        'every available page to complete this test.' 
    #        possible_answers = [{'answer_id': 'answer_'+str(i), 'label': r['label'], 'description': r['description'], 'id': r['id'], 'answer_str': r['answer_str']} for i, r in enumerate(self.receivers)]
    #        expected_answers = ['answer_'+str(i) for i, r in enumerate(self.receivers) if r['registered'] == True]

    #        actual_answers = self._invoke_testing_facade(question, possible_answers, test_type="checkbox")['answer_response']

    #        if len(actual_answers) != len(expected_answers):
    #            return test.FAIL('Incorrect receiver identified')
    #        else:
    #            for answer in actual_answers:
    #                if answer not in expected_answers:
    #                    return test.FAIL('Incorrect receiver identified')
    #        if not self.primary_registry.pagination_used and len(self.primary_registry.subscriptions) == 0:
    #            return test.FAIL('Pagination not exercised')

    #        return test.PASS('All devices correctly identified')
    #    except TestingFacadeException as e:
    #        return test.UNCLEAR(e.args[0])
    #    finally:
    #        self.primary_registry.paging_limit = 100

    #def test_05(self, test):
    #    """
    #    Reference Sender is put offline and then back online
    #    """
    #    try:
    #        # Check senders 

    #        question = 'The NCuT should be able to discover and dynamically update all the Senders that are registered in the Registry.\n\n' \
    #            'Use the NCuT to browse and take note of the Senders that are available.\n\n' \
    #            'After the \'Next\' button has been clicked one of those senders will be put \'offline\'.'
    #        possible_answers = []

    #        self._invoke_testing_facade(question, possible_answers, test_type="action")

    #        # Take one of the senders offline
    #        possible_answers = [{'answer_id': 'answer_'+str(i), 'label': s['label'], 'description': s['description'], 'id': s['id'], 'answer_str': s['answer_str']} for i, s in enumerate(self.senders) if s['registered'] == True]
    #        answer_indices = [index for index, s in enumerate(self.senders) if s['registered'] == True]
    #        offline_sender_index = random.choice(answer_indices)
    #        expected_answer = 'answer_' + str(offline_sender_index)

    #        self._delete_sender(test, self.senders[offline_sender_index])

    #        # Set the offline sender to registered false for future tests
    #        self.senders[offline_sender_index]['registered'] = False

    #        # Recheck senders
    #        question = 'Please refresh your NCuT and select the sender which has been put \'offline\''

    #        actual_answer = self._invoke_testing_facade(question, possible_answers, test_type="radio", multipart_test=1)['answer_response']

    #        if actual_answer != expected_answer:
    #            return test.FAIL('Offline/online sender not handled: Incorrect sender identified')

    #        max_time_until_online = 60
    #        max_time_to_answer = 30

    #        question = 'The sender which was put \'offline\' will come back online at a random moment within the next ' + str(max_time_until_online) + ' seconds. ' \
    #            'As soon as the NCuT detects the sender has come back online please press the \'Next\' button.\n\n' \
    #            'The button must be pressed within ' + str(max_time_to_answer) + ' seconds of the Sender being put back \'online\'. \n\n' \
    #            'This includes any latency between the Sender being put \'online\' and the NCuT updating.'
    #        possible_answers = []

    #        # Get the name of the calling test method to use as an identifier
    #        test_method_name = inspect.currentframe().f_code.co_name

    #        # Send the question to the Testing Façade and then put sender online before waiting for the Testing Façade response
    #        sent_json = self._send_testing_facade_questions(test_method_name, question, possible_answers, test_type="action", multipart_test=2)
            
    #        # Wait a random amount of time before bringing sender back online
    #        exit.clear()
    #        time_delay = random.randint(10, max_time_until_online)
    #        expected_time_online = time.time() + time_delay
    #        exit.wait(time_delay)

    #        # Re-register sender
    #        self._register_sender(self.senders[offline_sender_index], codes=[200, 201])
    #        self.senders[offline_sender_index]['registered'] = True

    #        # Await/get testing façade response
    #        response = self._wait_for_testing_facade(sent_json['name'])    

    #        if response['time_answered'] < expected_time_online: # Answered before sender put online
    #            return test.FAIL('Offline/online sender not handled: Sender not yet online')
    #        elif response['time_answered'] > expected_time_online + max_time_to_answer:
    #            return test.FAIL('Offline/online sender not handled: Sender online '  + str(int(response['time_answered'] - expected_time_online)) + ' seconds ago')
    #        else:
    #            return test.PASS('Offline/online sender handled correctly')                
    #    except TestingFacadeException as e:
    #        return test.UNCLEAR(e.args[0])

    #def test_06(self, test):
    #    """
    #    Identify which Receiver devices are controllable via IS-05
    #    """
    #    try:
    #        # Receiver initial details
    #        test_06_receivers = [{'label': 'r6/byrne', 'description': 'Mock receiver 6', 'connectable': False},
    #                          {'label': 'r7/frantz', 'description': 'Mock receiver 7', 'connectable': False},
    #                          {'label': 'r8/weymouth', 'description': 'Mock receiver 8', 'connectable': False},
    #                          {'label': 'r9/harrison', 'description': 'Mock receiver 9', 'connectable': False}]

    #        # Make at least one receiver connectable
    #        connectable_receiver_indices = self._generate_random_indices(len(test_06_receivers), 1, len(test_06_receivers) - 1)
    #        for i in connectable_receiver_indices:
    #            test_06_receivers[i]['connectable'] = True

    #        # Register receivers (some of which are non connectable)
    #        for receiver in test_06_receivers:
    #            receiver["id"] = str(uuid.uuid4())
    #            receiver["device_id"] = str(uuid.uuid4())
    #            receiver["controls_href"] = self.mock_node_base_url + "x-nmos/connection/v1.0/"
    #            receiver["registered"] = True
    #            receiver["answer_str"] = self._format_device_metadata(receiver['label'], receiver['description'], receiver['id'])
    #            receiver["version"] = NMOSUtils.get_TAI_time()
    #            self._register_receiver(receiver)
    #            self.node.add_receiver(receiver)

    #        # Check receivers 
    #        question = 'Some of the discovered Receivers are controllable via IS-05, for instance, allowing Senders to be connected. ' \
    #            'Additional Receivers have just been registered with the Registry, a subset of which have a connection API.\n\n' \
    #            'Please refresh your NCuT and select the Receivers that have a connection API from the list below.\n\n' \
    #            'Be aware that if your NCuT only displays Receivers which have a connection API, some of the Receivers in the following list may not be visible.'
    #        possible_answers = [{'answer_id': 'answer_'+str(i), 'label': r['label'], 'description': r['description'], 'id': r['id'], 'answer_str': r['answer_str']} for i, r in enumerate(test_06_receivers)]
    #        expected_answers = ['answer_'+str(i) for i, r in enumerate(test_06_receivers) if r['connectable'] == True]

    #        actual_answers = self._invoke_testing_facade(question, possible_answers, test_type="checkbox")['answer_response']

    #        if len(actual_answers) != len(expected_answers):
    #            return test.FAIL('Incorrect Receiver identified')
    #        else:
    #            for answer in actual_answers:
    #                if answer not in expected_answers:
    #                    return test.FAIL('Incorrect Receiver identified')

    #        return test.PASS('All Receivers correctly identified')
    #    except TestingFacadeException as e:
    #        return test.UNCLEAR(e.args[0])
    #    finally:
    #        #Delete receivers
    #        for receiver in test_06_receivers:
    #            self._delete_receiver(test, receiver)
    #            self.node.remove_receiver(receiver['id'])

    #def test_07(self, test):
    #    """
    #    Instruct Receiver to subscribe to a Sender’s Flow via IS-05
    #    """
    #    try:
    #        self.node.clear_staged_requests()
    #        # Choose random sender and receiver to be connected
    #        registered_senders = [s for s in self.senders if s['registered'] == True]
    #        sender = random.choice(registered_senders)
    #        registered_receivers = [r for r in self.receivers if r['registered'] == True]
    #        receiver = random.choice(registered_receivers)

    #        question = 'All flows that are available in a Sender should be able to be connected to a Receiver. \n\n' \
    #            'Use the NCuT to perform an \'immediate\' activation between sender: \n\n' \
    #             + sender['answer_str'] + ' \n\n' \
    #            'and receiver: \n\n' \
    #             + receiver['answer_str'] + ' \n\n' \
    #            'Click the \'Next\' button once the connection is active.'
    #        possible_answers = []

    #        metadata = {'sender': {'id': sender['id'], 'label': sender['label'], 'description': sender['description']},
    #            'receiver': {'id': receiver['id'], 'label': receiver['label'], 'description': receiver['description']}}

    #        self._invoke_testing_facade(question, possible_answers, test_type="action", metadata=metadata)

    #        # Check the staged API endpoint received a PATCH request
    #        patch_requests = [r for r in self.node.staged_requests if r['method'] == 'PATCH']
    #        if len(patch_requests) < 1:
    #            return test.FAIL('No PATCH request was received by the node')
    #        elif len(patch_requests) == 1:
    #            # One request should be direct activation, two if staged first
    #            # First request should contain sender id and master enable
    #            if patch_requests[0]['resource_id'] != receiver['id']:
    #                return test.FAIL('Connection request sent to incorrect receiver')

    #            if 'master_enable' not in patch_requests[0]['data'] or 'sender_id' not in patch_requests[0]['data']:
    #                return test.FAIL('Sender id or master enable not found in PATCH request')
    #            else:
    #                if patch_requests[0]['data']['master_enable'] != True:
    #                    return test.FAIL('Master_enable not set to True in PATCH request')

    #                if patch_requests[0]['data']['sender_id'] != sender['id']:
    #                    return test.FAIL('Incorrect sender found in PATCH request')

    #            # Activation details may be in either request. If not in first must have staged first so should be in second to activate
    #            if 'activation' not in patch_requests[0]['data']:
    #                return test.FAIL('No activation details in PATCH request')

    #            if patch_requests[0]['data']['activation'].get('mode') != 'activate_immediate':
    #                return test.FAIL('Immediate activation not requested in PATCH request')
    #        else:
    #            return test.FAIL('Multiple PATCH requests were found')

    #        # Check the receiver now has subscription details
    #        if receiver['id'] in self.primary_registry.get_resources()["receiver"]:
    #            receiver_details = self.primary_registry.get_resources()["receiver"][receiver['id']]

    #            if receiver_details['subscription']['active'] != True:
    #                return test.FAIL('Receiver does not have active subscription')

    #            if receiver_details['subscription']['sender_id'] != sender['id']:
    #                return test.FAIL('Receiver did not connect to correct sender')

    #        return test.PASS("Connection successfully established")
    #    except TestingFacadeException as e:
    #        return test.UNCLEAR(e.args[0])
    #    finally:
    #        #Remove subscription
    #        deactivate_json = {"transport_params":[{}],"activation":{"mode":"activate_immediate"}}
    #        deactivate_url = self.mock_node_base_url + 'x-nmos/connection/v1.0/single/receivers/' + receiver['id'] + '/staged'
    #        self.do_request('PATCH', deactivate_url, json=deactivate_json)

    #def test_08(self, test):
    #    """
    #    Disconnecting a Receiver from a connected Flow via IS-05
    #    """
    #    try:
    #        # Choose random sender and receiver to be connected
    #        registered_senders = [s for s in self.senders if s['registered'] == True]
    #        sender = random.choice(registered_senders)
    #        registered_receivers = [r for r in self.receivers if r['registered'] == True]
    #        receiver = random.choice(registered_receivers)

    #        # Send PATCH request to node to set up connection
    #        valid, response = self.do_request('GET', self.mock_node_base_url + 'x-nmos/connection/v1.0/single/senders/' + sender['id'] + '/transportfile')
    #        transport_file = response.content.decode()
    #        transport_params = self.node.receivers[receiver['id']]['activations']['active']['transport_params']
    #        activate_json = {"transport_params": transport_params,"activation":{"mode":"activate_immediate"},"master_enable":True,"sender_id":sender['id'],"transport_file":{"data": transport_file,"type":"application/sdp"}}
    #        activate_url = self.mock_node_base_url + 'x-nmos/connection/v1.0/single/receivers/' + receiver['id'] + '/staged'
    #        self.do_request('PATCH', activate_url, json=activate_json)

    #        # Clear staged requests once connection has been set up
    #        self.node.clear_staged_requests()

    #        question =  'IS-05 provides a mechanism for removing an active connection through its API. \n\n' \
    #            'Use the NCuT to remove the connection between sender: \n\n'\
    #            + sender['answer_str'] + ' \n\n'\
    #            'and receiver: \n\n' + \
    #            receiver['answer_str'] + ' \n\n'\
    #            'Click the \'Next\' button once the connection has been removed.'
    #        possible_answers = []

    #        metadata = {'sender': {'id': sender['id'], 'label': sender['label'], 'description': sender['description']},
    #            'receiver': {'id': receiver['id'], 'label': receiver['label'], 'description': receiver['description']}}

    #        self._invoke_testing_facade(question, possible_answers, test_type="action", metadata=metadata)

    #        # Check the staged API endpoint received a PATCH request
    #        patch_requests = [r for r in self.node.staged_requests if r['method'] == 'PATCH']
    #        if len(patch_requests) < 1:
    #            return test.FAIL('No PATCH request was received by the node')
    #        elif len(patch_requests) > 1:
    #            return test.FAIL('Multiple PATCH requests were received by the node')
    #        else:
    #            # Should be one PATCH request for disconnection
    #            if patch_requests[0]['resource_id'] != receiver['id']:
    #                return test.FAIL('Disconnection request sent to incorrect receiver')

    #            if 'activation' not in patch_requests[0]['data']:
    #                return test.FAIL('No activation details in PATCH request')
    #            elif 'mode' not in patch_requests[0]['data']['activation']:
    #                return test.FAIL('No activation mode found in PATCH request')
    #            elif patch_requests[0]['data']['activation']['mode'] != 'activate_immediate':
    #                return test.FAIL('Activation mode in PATCH request was not activate_immediate')

    #            # Check the receiver has empty subscription details
    #            if receiver['id'] in self.primary_registry.get_resources()["receiver"]:
    #                receiver_details = self.primary_registry.get_resources()["receiver"][receiver['id']]

    #                if receiver_details['subscription']['active'] == True or receiver_details['subscription']['sender_id'] == sender['id']:
    #                    return test.FAIL('Receiver still has subscription')
            
    #        return test.PASS('Receiver successfully disconnected from sender')
    #    except TestingFacadeException as e:
    #        return test.UNCLEAR(e.args[0])
    #    finally:
    #        #Remove subscription
    #        deactivate_json = {"transport_params":[{}],"activation":{"mode":"activate_immediate"}}
    #        deactivate_url = self.mock_node_base_url + 'x-nmos/connection/v1.0/single/receivers/' + receiver['id'] + '/staged'
    #        self.do_request('PATCH', deactivate_url, json=deactivate_json)

    #def test_09(self, test):
    #    """
    #    Indicating the state of connections via updates received from the IS-04 Query API
    #    """
    #    try:
    #        # Choose random sender and receiver to be connected
    #        registered_senders = [s for s in self.senders if s['registered'] == True]
    #        sender = random.choice(registered_senders)
    #        registered_receivers = [r for r in self.receivers if r['registered'] == True]
    #        receiver = random.choice(registered_receivers)

    #        # Send PATCH request to node to set up connection
    #        valid, response = self.do_request('GET', self.mock_node_base_url + 'x-nmos/connection/v1.0/single/senders/' + sender['id'] + '/transportfile')
    #        transport_file = response.content.decode()
    #        transport_params = self.node.receivers[receiver['id']]['activations']['active']['transport_params']
    #        activate_json = {"transport_params": transport_params,"activation":{"mode":"activate_immediate"},"master_enable":True,"sender_id":sender['id'],"transport_file":{"data": transport_file,"type":"application/sdp"}}
    #        activate_url = self.mock_node_base_url + 'x-nmos/connection/v1.0/single/receivers/' + receiver['id'] + '/staged'
    #        self.do_request('PATCH', activate_url, json=activate_json)

    #        # Identify which Receiver has been activated
    #        question = 'The NCuT should be able to monitor and update the connection status of all registered Devices. \n\n' \
    #            'Use the NCuT to identify the receiver that has just been connected.'
    #        possible_answers = [{'answer_id': 'answer_'+str(i), 'label': r['label'], 'description': r['description'], 'id': r['id'], 'answer_str': r['answer_str']} for i, r in enumerate(registered_receivers) if r['registered'] == True]
    #        expected_answer = ['answer_'+str(i) for i, r in enumerate(registered_receivers) if r['answer_str'] == receiver['answer_str']][0]

    #        actual_answer = self._invoke_testing_facade(question, possible_answers, test_type="radio")['answer_response']

    #        if actual_answer != expected_answer:
    #            return test.FAIL('Incorrect receiver identified')

    #        # Identify a connection
    #        question = 'Use the NCuT to identify the sender currently connected to receiver: \n\n' \
    #            + receiver['answer_str']
    #        possible_answers = [{'answer_id': 'answer_'+str(i), 'label': s['label'], 'description': s['description'], 'id': s['id'], 'answer_str': s['answer_str']} for i, s in enumerate(registered_senders) if s['registered'] == True]
    #        expected_answer = ['answer_'+str(i) for i, s in enumerate(registered_senders) if s['answer_str'] == sender['answer_str']][0]

    #        metadata = {'receiver': {'id': receiver['id'], 'label': receiver['label'], 'description': receiver['description']}}

    #        actual_answer = self._invoke_testing_facade(question, possible_answers, test_type="radio", multipart_test=1, metadata=metadata)['answer_response']

    #        if actual_answer != expected_answer:
    #            return test.FAIL('Incorrect sender identified')

    #        max_time_until_online = 60
    #        max_time_to_answer = 30

    #        # Indicate when connection has gone offline
    #        question = 'The connection on the following receiver will be disconnected at a random moment within the next ' + str(max_time_until_online) + ' seconds.\n\n' \
    #            + receiver['answer_str'] + ' \n\n' \
    #            'As soon as the NCuT detects the connection is inactive please press the \'Next\' button. \n\n' \
    #            'The button must be pressed within ' + str(max_time_to_answer)  + ' seconds of the connection being removed. \n\n' \
    #            'This includes any latency between the connection being removed and the NCuT updating.'
    #        possible_answers = []

    #        # Get the name of the calling test method to use as an identifier
    #        test_method_name = inspect.currentframe().f_code.co_name

    #        # Send the question to the Testing Façade 
    #        sent_json = self._send_testing_facade_questions(test_method_name, question, possible_answers, test_type="action", multipart_test=2, metadata=metadata)

    #        # Wait a random amount of time before disconnecting
    #        exit.clear()
    #        time_delay = random.randint(10, max_time_until_online)
    #        expected_time_online = time.time() + time_delay
    #        exit.wait(time_delay)

    #        # Remove connection
    #        deactivate_json = {"transport_params":[{}],"activation":{"mode":"activate_immediate"}}
    #        deactivate_url = self.mock_node_base_url + 'x-nmos/connection/v1.0/single/receivers/' + receiver['id'] + '/staged'
    #        self.do_request('PATCH', deactivate_url, json=deactivate_json)

    #        response = self._wait_for_testing_facade(sent_json['name'])

    #        if response['time_answered'] < expected_time_online: # Answered before connection was removed
    #            return test.FAIL('Connection not handled: Connection still active')
    #        elif response['time_answered'] > expected_time_online + max_time_to_answer:
    #            return test.FAIL('Connection not handled: Connection removed '  + str(int(response['time_answered'] - expected_time_online)) + ' seconds ago')
    #        else:
    #            return test.PASS('Connection handled correctly')
    #    except TestingFacadeException as e:
    #        return test.UNCLEAR(e.args[0])
