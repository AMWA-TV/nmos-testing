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

from ..GenericTest import GenericTest, NMOSTestException
from .. import Config as CONFIG
from ..MdnsListener import MdnsListener
from ..TestHelper import get_default_ip
from ..TestResult import Test
from ..NMOSUtils import NMOSUtils
from ..ControllerTest import ControllerTest, TestingFacadeException, exitTestEvent

#from flask import Flask, Blueprint, request

#TF_API_KEY = "controller"
#REG_API_KEY = "registration"
#CALLBACK_ENDPOINT = "/testingfacade_response"
#CACHEBUSTER = random.randint(1, 10000)

## asyncio queue for passing Testing Façade answer responses back to tests
#_event_loop = asyncio.new_event_loop()
#asyncio.set_event_loop(_event_loop)
#_answer_response_queue = asyncio.Queue()

## use exit Event to quit tests early that involve waiting for senders/connections 
#exit = Event()

#app = Flask(__name__)
#TEST_API = Blueprint('test_api', __name__)

#class TestingFacadeException(Exception):
#    """Exception thrown due to comms or data errors between NMOS Testing and Testing Façade"""
#    pass

#@TEST_API.route(CALLBACK_ENDPOINT, methods=['POST'])
#def retrieve_answer():

#    if request.method == 'POST':
#        if 'name' not in request.json:
#            return 'Invalid JSON received'

#        _event_loop.call_soon_threadsafe(_answer_response_queue.put_nowait, request.json)

#        # Interupt any 'sleeps' that are still active 
#        exit.set()

#    return 'OK'

class IS0503Test(ControllerTest):
    """
    Testing initial set up of new test suite for controller testing
    """
    def __init__(self, apis, registries, node, dns_server):
        ControllerTest.__init__(self, apis, registries, node, dns_server)

    def test_01(self, test):
        """
        Identify which Receiver devices are controllable via IS-05
        """
        try:
            # Receiver initial details
            test_06_receivers = [{'label': 'r6/byrne', 'description': 'Mock receiver 6', 'connectable': False},
                              {'label': 'r7/frantz', 'description': 'Mock receiver 7', 'connectable': False},
                              {'label': 'r8/weymouth', 'description': 'Mock receiver 8', 'connectable': False},
                              {'label': 'r9/harrison', 'description': 'Mock receiver 9', 'connectable': False}]

            # Make at least one receiver connectable
            connectable_receiver_indices = self._generate_random_indices(len(test_06_receivers), 1, len(test_06_receivers) - 1)
            for i in connectable_receiver_indices:
                test_06_receivers[i]['connectable'] = True

            # Register receivers (some of which are non connectable)
            for receiver in test_06_receivers:
                receiver["id"] = str(uuid.uuid4())
                receiver["device_id"] = str(uuid.uuid4())
                receiver["controls_href"] = self.mock_node_base_url + "x-nmos/connection/v1.0/"
                receiver["registered"] = True
                receiver["answer_str"] = self._format_device_metadata(receiver['label'], receiver['description'], receiver['id'])
                receiver["version"] = NMOSUtils.get_TAI_time()
                self._register_receiver(receiver)
                self.node.add_receiver(receiver)

            # Check receivers 
            question = 'Some of the discovered Receivers are controllable via IS-05, for instance, allowing Senders to be connected. ' \
                'Additional Receivers have just been registered with the Registry, a subset of which have a connection API.\n\n' \
                'Please refresh your NCuT and select the Receivers that have a connection API from the list below.\n\n' \
                'Be aware that if your NCuT only displays Receivers which have a connection API, some of the Receivers in the following list may not be visible.'
            possible_answers = [{'answer_id': 'answer_'+str(i), 'label': r['label'], 'description': r['description'], 'id': r['id'], 'answer_str': r['answer_str']} for i, r in enumerate(test_06_receivers)]
            expected_answers = ['answer_'+str(i) for i, r in enumerate(test_06_receivers) if r['connectable'] == True]

            actual_answers = self._invoke_testing_facade(question, possible_answers, test_type="checkbox")['answer_response']

            if len(actual_answers) != len(expected_answers):
                return test.FAIL('Incorrect Receiver identified')
            else:
                for answer in actual_answers:
                    if answer not in expected_answers:
                        return test.FAIL('Incorrect Receiver identified')

            return test.PASS('All Receivers correctly identified')
        except TestingFacadeException as e:
            return test.UNCLEAR(e.args[0])
        finally:
            #Delete receivers
            for receiver in test_06_receivers:
                self._delete_receiver(test, receiver)
                self.node.remove_receiver(receiver['id'])

    def test_02(self, test):
        """
        Instruct Receiver to subscribe to a Sender’s Flow via IS-05
        """
        try:
            self.node.clear_staged_requests()
            # Choose random sender and receiver to be connected
            registered_senders = [s for s in self.senders if s['registered'] == True]
            sender = random.choice(registered_senders)
            registered_receivers = [r for r in self.receivers if r['registered'] == True]
            receiver = random.choice(registered_receivers)

            question = 'All flows that are available in a Sender should be able to be connected to a Receiver. \n\n' \
                'Use the NCuT to perform an \'immediate\' activation between sender: \n\n' \
                 + sender['answer_str'] + ' \n\n' \
                'and receiver: \n\n' \
                 + receiver['answer_str'] + ' \n\n' \
                'Click the \'Next\' button once the connection is active.'
            possible_answers = []

            metadata = {'sender': {'id': sender['id'], 'label': sender['label'], 'description': sender['description']},
                'receiver': {'id': receiver['id'], 'label': receiver['label'], 'description': receiver['description']}}

            self._invoke_testing_facade(question, possible_answers, test_type="action", metadata=metadata)

            # Check the staged API endpoint received a PATCH request
            patch_requests = [r for r in self.node.staged_requests if r['method'] == 'PATCH']
            if len(patch_requests) < 1:
                return test.FAIL('No PATCH request was received by the node')
            elif len(patch_requests) == 1:
                # One request should be direct activation, two if staged first
                # First request should contain sender id and master enable
                if patch_requests[0]['resource_id'] != receiver['id']:
                    return test.FAIL('Connection request sent to incorrect receiver')

                if 'master_enable' not in patch_requests[0]['data'] or 'sender_id' not in patch_requests[0]['data']:
                    return test.FAIL('Sender id or master enable not found in PATCH request')
                else:
                    if patch_requests[0]['data']['master_enable'] != True:
                        return test.FAIL('Master_enable not set to True in PATCH request')

                    if patch_requests[0]['data']['sender_id'] != sender['id']:
                        return test.FAIL('Incorrect sender found in PATCH request')

                # Activation details may be in either request. If not in first must have staged first so should be in second to activate
                if 'activation' not in patch_requests[0]['data']:
                    return test.FAIL('No activation details in PATCH request')

                if patch_requests[0]['data']['activation'].get('mode') != 'activate_immediate':
                    return test.FAIL('Immediate activation not requested in PATCH request')
            else:
                return test.FAIL('Multiple PATCH requests were found')

            # Check the receiver now has subscription details
            if receiver['id'] in self.primary_registry.get_resources()["receiver"]:
                receiver_details = self.primary_registry.get_resources()["receiver"][receiver['id']]

                if receiver_details['subscription']['active'] != True:
                    return test.FAIL('Receiver does not have active subscription')

                if receiver_details['subscription']['sender_id'] != sender['id']:
                    return test.FAIL('Receiver did not connect to correct sender')

            return test.PASS("Connection successfully established")
        except TestingFacadeException as e:
            return test.UNCLEAR(e.args[0])
        finally:
            #Remove subscription
            deactivate_json = {"transport_params":[{}],"activation":{"mode":"activate_immediate"}}
            deactivate_url = self.mock_node_base_url + 'x-nmos/connection/v1.0/single/receivers/' + receiver['id'] + '/staged'
            self.do_request('PATCH', deactivate_url, json=deactivate_json)

    def test_03(self, test):
        """
        Disconnecting a Receiver from a connected Flow via IS-05
        """
        try:
            # Choose random sender and receiver to be connected
            registered_senders = [s for s in self.senders if s['registered'] == True]
            sender = random.choice(registered_senders)
            registered_receivers = [r for r in self.receivers if r['registered'] == True]
            receiver = random.choice(registered_receivers)

            # Send PATCH request to node to set up connection
            valid, response = self.do_request('GET', self.mock_node_base_url + 'x-nmos/connection/v1.0/single/senders/' + sender['id'] + '/transportfile')
            transport_file = response.content.decode()
            transport_params = self.node.receivers[receiver['id']]['activations']['active']['transport_params']
            activate_json = {"transport_params": transport_params,"activation":{"mode":"activate_immediate"},"master_enable":True,"sender_id":sender['id'],"transport_file":{"data": transport_file,"type":"application/sdp"}}
            activate_url = self.mock_node_base_url + 'x-nmos/connection/v1.0/single/receivers/' + receiver['id'] + '/staged'
            self.do_request('PATCH', activate_url, json=activate_json)

            # Clear staged requests once connection has been set up
            self.node.clear_staged_requests()

            question =  'IS-05 provides a mechanism for removing an active connection through its API. \n\n' \
                'Use the NCuT to remove the connection between sender: \n\n'\
                + sender['answer_str'] + ' \n\n'\
                'and receiver: \n\n' + \
                receiver['answer_str'] + ' \n\n'\
                'Click the \'Next\' button once the connection has been removed.'
            possible_answers = []

            metadata = {'sender': {'id': sender['id'], 'label': sender['label'], 'description': sender['description']},
                'receiver': {'id': receiver['id'], 'label': receiver['label'], 'description': receiver['description']}}

            self._invoke_testing_facade(question, possible_answers, test_type="action", metadata=metadata)

            # Check the staged API endpoint received a PATCH request
            patch_requests = [r for r in self.node.staged_requests if r['method'] == 'PATCH']
            if len(patch_requests) < 1:
                return test.FAIL('No PATCH request was received by the node')
            elif len(patch_requests) > 1:
                return test.FAIL('Multiple PATCH requests were received by the node')
            else:
                # Should be one PATCH request for disconnection
                if patch_requests[0]['resource_id'] != receiver['id']:
                    return test.FAIL('Disconnection request sent to incorrect receiver')

                if 'activation' not in patch_requests[0]['data']:
                    return test.FAIL('No activation details in PATCH request')
                elif 'mode' not in patch_requests[0]['data']['activation']:
                    return test.FAIL('No activation mode found in PATCH request')
                elif patch_requests[0]['data']['activation']['mode'] != 'activate_immediate':
                    return test.FAIL('Activation mode in PATCH request was not activate_immediate')

                # Check the receiver has empty subscription details
                if receiver['id'] in self.primary_registry.get_resources()["receiver"]:
                    receiver_details = self.primary_registry.get_resources()["receiver"][receiver['id']]

                    if receiver_details['subscription']['active'] == True or receiver_details['subscription']['sender_id'] == sender['id']:
                        return test.FAIL('Receiver still has subscription')
            
            return test.PASS('Receiver successfully disconnected from sender')
        except TestingFacadeException as e:
            return test.UNCLEAR(e.args[0])
        finally:
            #Remove subscription
            deactivate_json = {"transport_params":[{}],"activation":{"mode":"activate_immediate"}}
            deactivate_url = self.mock_node_base_url + 'x-nmos/connection/v1.0/single/receivers/' + receiver['id'] + '/staged'
            self.do_request('PATCH', deactivate_url, json=deactivate_json)

    def test_04(self, test):
        """
        Indicating the state of connections via updates received from the IS-04 Query API
        """
        try:
            # Choose random sender and receiver to be connected
            registered_senders = [s for s in self.senders if s['registered'] == True]
            sender = random.choice(registered_senders)
            registered_receivers = [r for r in self.receivers if r['registered'] == True]
            receiver = random.choice(registered_receivers)

            # Send PATCH request to node to set up connection
            valid, response = self.do_request('GET', self.mock_node_base_url + 'x-nmos/connection/v1.0/single/senders/' + sender['id'] + '/transportfile')
            transport_file = response.content.decode()
            transport_params = self.node.receivers[receiver['id']]['activations']['active']['transport_params']
            activate_json = {"transport_params": transport_params,"activation":{"mode":"activate_immediate"},"master_enable":True,"sender_id":sender['id'],"transport_file":{"data": transport_file,"type":"application/sdp"}}
            activate_url = self.mock_node_base_url + 'x-nmos/connection/v1.0/single/receivers/' + receiver['id'] + '/staged'
            self.do_request('PATCH', activate_url, json=activate_json)

            # Identify which Receiver has been activated
            question = 'The NCuT should be able to monitor and update the connection status of all registered Devices. \n\n' \
                'Use the NCuT to identify the receiver that has just been connected.'
            possible_answers = [{'answer_id': 'answer_'+str(i), 'label': r['label'], 'description': r['description'], 'id': r['id'], 'answer_str': r['answer_str']} for i, r in enumerate(registered_receivers) if r['registered'] == True]
            expected_answer = ['answer_'+str(i) for i, r in enumerate(registered_receivers) if r['answer_str'] == receiver['answer_str']][0]

            actual_answer = self._invoke_testing_facade(question, possible_answers, test_type="radio")['answer_response']

            if actual_answer != expected_answer:
                return test.FAIL('Incorrect receiver identified')

            # Identify a connection
            question = 'Use the NCuT to identify the sender currently connected to receiver: \n\n' \
                + receiver['answer_str']
            possible_answers = [{'answer_id': 'answer_'+str(i), 'label': s['label'], 'description': s['description'], 'id': s['id'], 'answer_str': s['answer_str']} for i, s in enumerate(registered_senders) if s['registered'] == True]
            expected_answer = ['answer_'+str(i) for i, s in enumerate(registered_senders) if s['answer_str'] == sender['answer_str']][0]

            metadata = {'receiver': {'id': receiver['id'], 'label': receiver['label'], 'description': receiver['description']}}

            actual_answer = self._invoke_testing_facade(question, possible_answers, test_type="radio", multipart_test=1, metadata=metadata)['answer_response']

            if actual_answer != expected_answer:
                return test.FAIL('Incorrect sender identified')

            max_time_until_online = 60
            max_time_to_answer = 30

            # Indicate when connection has gone offline
            question = 'The connection on the following receiver will be disconnected at a random moment within the next ' + str(max_time_until_online) + ' seconds.\n\n' \
                + receiver['answer_str'] + ' \n\n' \
                'As soon as the NCuT detects the connection is inactive please press the \'Next\' button. \n\n' \
                'The button must be pressed within ' + str(max_time_to_answer)  + ' seconds of the connection being removed. \n\n' \
                'This includes any latency between the connection being removed and the NCuT updating.'
            possible_answers = []

            # Get the name of the calling test method to use as an identifier
            test_method_name = inspect.currentframe().f_code.co_name

            # Send the question to the Testing Façade 
            sent_json = self._send_testing_facade_questions(test_method_name, question, possible_answers, test_type="action", multipart_test=2, metadata=metadata)

            # Wait a random amount of time before disconnecting
            exitTestEvent.clear()
            time_delay = random.randint(10, max_time_until_online)
            expected_time_online = time.time() + time_delay
            exitTestEvent.wait(time_delay)

            # Remove connection
            deactivate_json = {"transport_params":[{}],"activation":{"mode":"activate_immediate"}}
            deactivate_url = self.mock_node_base_url + 'x-nmos/connection/v1.0/single/receivers/' + receiver['id'] + '/staged'
            self.do_request('PATCH', deactivate_url, json=deactivate_json)

            response = self._wait_for_testing_facade(sent_json['name'])

            if response['time_answered'] < expected_time_online: # Answered before connection was removed
                return test.FAIL('Connection not handled: Connection still active')
            elif response['time_answered'] > expected_time_online + max_time_to_answer:
                return test.FAIL('Connection not handled: Connection removed '  + str(int(response['time_answered'] - expected_time_online)) + ' seconds ago')
            else:
                return test.PASS('Connection handled correctly')
        except TestingFacadeException as e:
            return test.UNCLEAR(e.args[0])
