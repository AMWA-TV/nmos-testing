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
import textwrap
from copy import deepcopy
from urllib.parse import urlparse
from dnslib import QTYPE
from threading import Event

from .GenericTest import GenericTest, NMOSTestException
from . import Config as CONFIG
from .TestHelper import get_default_ip
from .TestResult import Test
from .NMOSUtils import NMOSUtils

from flask import Flask, Blueprint, request

CONTROLLER_TEST_API_KEY = "testquestion"
QUERY_API_KEY = "query"
CONN_API_KEY = "connection"

CALLBACK_ENDPOINT = "/x-nmos/testanswer/"

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
def receive_answer():

    if request.method == 'POST':
        if 'question_id' not in request.json:
            return 'Invalid JSON received', 400

        answer_json = request.json
        answer_json['time_received'] = time.time()
        _event_loop.call_soon_threadsafe(_answer_response_queue.put_nowait, answer_json)

        # Interrupt any 'sleeps' that are still active
        exitTestEvent.set()

    return '', 202


class ControllerTest(GenericTest):
    """
    Testing initial set up of new test suite for controller testing
    """
    def __init__(self, apis, registries, node, dns_server, disable_auto=True):
        # Remove the spec_path as there are no corresponding GitHib repos for Controller Tests
        apis[CONTROLLER_TEST_API_KEY].pop("spec_path", None)
        GenericTest.__init__(self, apis, disable_auto=disable_auto)
        self.authorization = False
        self.primary_registry = registries[1]
        self.node = node
        self.dns_server = dns_server
        self.mock_registry_base_url = ''
        self.mock_node_base_url = ''
        self.question_timeout = 600  # default timeout in seconds
        self.extra_time = 2 * CONFIG.API_PROCESSING_TIMEOUT  # API processing time to add to test timeout
        self.test_data = self.load_resource_data()
        self.senders = []
        self.receivers = []
        # receiver list containing: {'label': '', 'description': '', 'id': '',
        #   'registered': True/False, 'connectable': True/False, 'display_answer': ''}
        self.senders_ip_base = '239.3.14.'  # Random multicast IP to assign to senders
        self.query_api_version = self.apis[QUERY_API_KEY]["version"] \
            if QUERY_API_KEY in apis and "version" in self.apis[QUERY_API_KEY] else "v1.3"
        self.connection_api_version = self.apis[CONN_API_KEY]["version"] \
            if CONN_API_KEY in apis and "version" in self.apis[CONN_API_KEY] else "v1.1"

    def set_up_tests(self):
        if self.dns_server:
            self.dns_server.load_zone(self.apis[CONTROLLER_TEST_API_KEY]["version"], self.protocol, self.authorization,
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
        self.mock_registry_base_url = 'http://' + get_default_ip() + ':' + \
            str(self.primary_registry.get_data().port) + '/'
        self.mock_node_base_url = 'http://' + get_default_ip() + ':' + str(self.node.port) + '/'

        # Populate mock registry with senders and receivers and store the results
        self._populate_registry()

        # Set up mock node
        self.node.registry_url = self.mock_registry_base_url

    def tear_down_tests(self):
        self.primary_registry.disable()

        # Reset the state of the Testing Façade
        self.do_request("POST", self.apis[CONTROLLER_TEST_API_KEY]["url"], json={"clear": "True"})

        if self.dns_server:
            self.dns_server.reset()

        self.mock_registry_base_url = ''

    def execute_tests(self, test_names):
        """Perform tests defined within this class"""

        # If auto tests the only test and auto tests disabled then return immediately
        if len(test_names) == 1 and test_names[0] == "auto" and self.disable_auto:
            return

        self.pre_tests_message()

        for test_name in test_names:
            self.primary_registry.query_api_called = False
            self.execute_test(test_name)

        self.post_tests_message()

    async def get_answer_response(self, timeout):
        return await asyncio.wait_for(_answer_response_queue.get(), timeout=timeout)

    def _send_testing_facade_questions(
            self,
            test_method_name,
            question,
            answers,
            test_type,
            timeout=None,
            multipart_test=None,
            metadata=None):
        """
        Send question and answers to Testing Façade
        question:   text to be presented to Test User
        answers:    list of all possible answers
        test_type:  "single_choice" - one and only one answer
                    "multi_choice" - multiple answers
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
            "timeout": question_timeout,
            "answer_uri": "http://" + get_default_ip() + ":5000" + CALLBACK_ENDPOINT,
            "metadata": metadata
        }
        # Send questions to Testing Façade API endpoint then wait
        valid, response = self.do_request("POST", self.apis[CONTROLLER_TEST_API_KEY]["url"], json=json_out)

        if not valid or response.status_code != 202:
            raise TestingFacadeException("Problem contacting Testing Façade: " + response.text if valid else response)

        return json_out

    def _wait_for_testing_facade(self, question_id, test_type, timeout=None):

        question_timeout = (timeout or self.question_timeout) + self.extra_time

        # Wait for answer response or question timeout in seconds
        try:
            answer_response = _event_loop.run_until_complete(self.get_answer_response(timeout=question_timeout))
        except asyncio.TimeoutError:
            raise TestingFacadeException("Test timed out")

        # Basic integrity check for response json
        if answer_response['question_id'] is None:
            raise TestingFacadeException("Integrity check failed: result format error: "
                                         + json.dump(answer_response))

        if answer_response['question_id'] != question_id:
            raise TestingFacadeException(
                "Integrity check failed: cannot compare result of " + question_id +
                " with expected result for " + answer_response['question_id'])

        # Multi_choice question submitted without any answers should be an empty list
        if test_type == 'multi_choice' and answer_response['answer_response'] is None:
            answer_response['answer_response'] = []

        return answer_response

    def _invoke_testing_facade(self, question, answers, test_type, timeout=None, multipart_test=None, metadata=None):
        # Get the name of the calling test method to use as an identifier
        test_method_name = inspect.currentframe().f_back.f_code.co_name

        json_out = self._send_testing_facade_questions(
            test_method_name, question, answers, test_type, timeout, multipart_test, metadata)

        return self._wait_for_testing_facade(json_out['question_id'], test_type, timeout)

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
        """Populate registry and mock node with mock senders and receivers"""
        self.node.reset()  # Ensure previouly added senders and receivers are removed
        self.primary_registry.common.reset()  # Ensure any previouly registered senders and receivers are removed
        sender_ip = 159

        # Register node
        self._register_node(self.node.id, "AMWA Test Suite Node", "AMWA Test Suite Node")

        # self.senders should be initialized in the set_up_tests() override of derived test
        # each mock sender defined as: {'label': <unique label>, 'description': '',
        #   'registered': <is registered with mock Registry>}
        for sender in self.senders:
            sender["id"] = str(uuid.uuid4())
            sender["device_id"] = str(uuid.uuid4())
            sender["flow_id"] = str(uuid.uuid4())
            sender["source_id"] = str(uuid.uuid4())
            sender["manifest_href"] = self.mock_node_base_url + "x-nmos/connection/" + self.connection_api_version \
                + "/single/senders/" + sender["id"] + "/transportfile"
            sender["version"] = NMOSUtils.get_TAI_time()
            sender["display_answer"] = self._format_device_metadata(sender['label'], sender['description'], sender['id'])
            # Introduce a short delay to ensure unique version numbers.
            # Version number is used by pagination in lieu of creation or update time
            time.sleep(0.1)
            if sender["registered"]:
                self._register_sender(sender)
                # Add sender to mock node
                sender_json = self._create_sender_json(sender)
                self.node.add_sender(sender_json, self.senders_ip_base + str(sender_ip))
                sender_ip += 1

        # self.receivers should be initialized in the set_up_tests() override of derived test
        # each mock receiver defined as: {'label': <unique label>, 'description': '',
        #   'connectable': <has IS-05 connection API>, 'registered': <is registered with mock Registry>}
        for receiver in self.receivers:
            receiver["id"] = str(uuid.uuid4())
            receiver["device_id"] = str(uuid.uuid4())
            receiver["controls_href"] = self.mock_node_base_url + "x-nmos/connection/" \
                + self.connection_api_version + "/"
            receiver["controls_type"] = "urn:x-nmos:control:sr-ctrl/" + self.connection_api_version
            receiver["version"] = NMOSUtils.get_TAI_time()
            receiver["display_answer"] = self._format_device_metadata(
                    receiver['label'], receiver['description'], receiver['id'])
            # Introduce a short delay to ensure unique version numbers.
            # Version number is used by pagination in lieu of creation or update time
            time.sleep(0.1)
            if receiver["registered"]:
                self._register_receiver(receiver)
                # Add receiver to mock node
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
        device_data["controls"][0]["href"] = self.mock_node_base_url + "x-nmos/connection/" \
            + self.connection_api_version + "/"
        device_data["controls"][0]["type"] = "urn:x-nmos:control:sr-ctrl/" + self.connection_api_version
        device_data["senders"] = [sender["id"]]
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
            device_data["controls"][0]["type"] = receiver['controls_type']
        else:
            # Remove controls data
            device_data["controls"] = []
        device_data["version"] = receiver["version"]
        device_data["senders"] = []
        device_data["receivers"] = [receiver["id"]]
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
        Introduction to Controller Test Suite
        """
        # In order to give the tests some context, a pre tests message is displayed
        # on the Testing Façade prior to the tests starting. This communicates any
        # pre-requisites or setup required by the Test User. The pre tests message
        # will vary depending on whether or not unicast DNS-SD is being used to discover the mock Registry.

        if CONFIG.ENABLE_DNS_SD and CONFIG.DNS_SD_MODE == "unicast":
            registry_text = "A Test AMWA IS-04 reference Registry is available on the network"\
                            "and is being advertised via unicast DNS-SD."

            config_text = textwrap.dedent(f"""\
                          Please ensure that the following configuration has been set on the NCuT machine.

                          * Ensure that the primary DNS of the NCuT machine has been set to \"{get_default_ip()}\".
                          * Ensure that the NCuT unicast search domain is set to \"{CONFIG.DNS_DOMAIN}\".

                          Alternatively it\
                          """)
        else:
            registry_text = "A Test AMWA IS-04 reference Registry is available on the network."\

            config_text = "It"

        question = textwrap.dedent(f"""\
                   These tests validate an NMOS Controller under Test (NCuT).

                   {registry_text}

                   {config_text} is possible to reach the Registry via the following URL:

                   {self.mock_registry_base_url}x-nmos/query/{self.query_api_version}

                   Please ensure the NCuT has located the test AMWA IS-04 Registry before clicking the 'Next' button.
                   """)

        try:
            self._invoke_testing_facade(question, [], test_type="action")

        except TestingFacadeException:
            # pre_test_introducton timed out
            pass

    def post_tests_message(self):
        """
        Controller Test Suite complete!
        """
        # Once the tests are complete this post tests message is displayed.

        question = """\
                   NMOS Controller Test Suite complete!

                   Please press the 'Next' button to exit the tests.
                   """

        try:
            self._invoke_testing_facade(question, [], test_type="action", timeout=10)

        except TestingFacadeException:
            # post_test_introducton timed out
            pass
