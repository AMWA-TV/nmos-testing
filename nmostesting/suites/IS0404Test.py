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

class IS0404Test(ControllerTest):
    """
    Testing initial set up of new test suite for controller testing
    """
    def __init__(self, apis, registries, node, dns_server):
        ControllerTest.__init__(self, apis, registries, node, dns_server)
    
    def test_01(self, test):
        """
        Ensure NCuT uses DNS-SD to find registry
        """
        if not CONFIG.ENABLE_DNS_SD or CONFIG.DNS_SD_MODE != "unicast":
            return test.DISABLED("This test cannot be performed when ENABLE_DNS_SD is False or DNS_SD_MODE is not "
                                 "'unicast'")

        # The DNS server will log queries that have been specified in set_up_tests()
        if not self.dns_server.is_query_received():
            return test.FAIL('DNS was not queried by the NCuT')
            
        return test.PASS('DNS successfully queried by NCuT')

    def test_02(self, test):
        """
        Ensure NCuT can access the IS-04 Query API
        """
        try:
            # Question 1 connection
            question = 'Use the NCuT to browse the Senders and Receivers on the discovered Registry via the selected IS-04 Query API.\n\n' \
            'Once you have finished browsing click the \'Next\' button. \n\n' \
            'Successful browsing of the Registry will be automatically logged by the test framework.\n'

            self._invoke_testing_facade(question, [], test_type="action")

            # Fail if the REST Query API was not called, and no query subscriptions were made
            # The registry will log calls to the Query API endpoints
            if not self.primary_registry.query_api_called and len(self.primary_registry.subscriptions) == 0:
                return test.FAIL('IS-04 Query API not reached')
            
            return test.PASS('IS-04 Query API reached successfully')

        except TestingFacadeException as e:
            return test.UNCLEAR(e.args[0])

    def test_03(self, test):
        """
        Query API should be able to discover all the senders that are registered in the Registry
        """
        try:
            # reduce paging limit to force pagination on REST API
            self.primary_registry.paging_limit = 2
            # Check senders 
            question = 'The NCuT should be able to discover all the Senders that are registered in the Registry.\n\n' \
            'Refresh the NCuT\'s view of the Registry and carefully select the Senders that are available from the following list.\n\n' \
            'For this test the registry paging limit has been set to 2. If your NCuT implements pagination, you must ensure you view ' \
            'every available page to complete this test.' 
            possible_answers = [{'answer_id': 'answer_'+str(i), 'label': s['label'], 'description': s['description'], 'id': s['id'], 'answer_str': s['answer_str']} for i, s in enumerate(self.senders)]
            expected_answers = ['answer_'+str(i) for i, s in enumerate(self.senders) if s['registered'] == True]

            actual_answers = self._invoke_testing_facade(question, possible_answers, test_type="checkbox")['answer_response']

            if len(actual_answers) != len(expected_answers):
                return test.FAIL('Incorrect sender identified')
            else:
                for answer in actual_answers:
                    if answer not in expected_answers:
                        return test.FAIL('Incorrect sender identified')

            if not self.primary_registry.pagination_used and len(self.primary_registry.subscriptions) == 0:
                return test.FAIL('Pagination not exercised')
            return test.PASS('All devices correctly identified')
        except TestingFacadeException as e:
            return test.UNCLEAR(e.args[0])
        finally:
            self.primary_registry.paging_limit = 100

    def test_04(self, test):
        """
        Query API should be able to discover all the receivers that are registered in the Registry
        """
        try:
            # reduce paging limit to force pagination on REST API
            self.primary_registry.paging_limit = 2

            # Check receivers 
            question = 'The NCuT should be able to discover all the Receivers that are registered in the Registry.\n\n' \
            'Refresh the NCuT\'s view of the Registry and carefully select the Receivers that are available from the following list.\n\n' \
            'For this test the registry paging limit has been set to 2. If your NCuT implements pagination, you must ensure you view ' \
            'every available page to complete this test.' 
            possible_answers = [{'answer_id': 'answer_'+str(i), 'label': r['label'], 'description': r['description'], 'id': r['id'], 'answer_str': r['answer_str']} for i, r in enumerate(self.receivers)]
            expected_answers = ['answer_'+str(i) for i, r in enumerate(self.receivers) if r['registered'] == True]

            actual_answers = self._invoke_testing_facade(question, possible_answers, test_type="checkbox")['answer_response']

            if len(actual_answers) != len(expected_answers):
                return test.FAIL('Incorrect receiver identified')
            else:
                for answer in actual_answers:
                    if answer not in expected_answers:
                        return test.FAIL('Incorrect receiver identified')
            if not self.primary_registry.pagination_used and len(self.primary_registry.subscriptions) == 0:
                return test.FAIL('Pagination not exercised')

            return test.PASS('All devices correctly identified')
        except TestingFacadeException as e:
            return test.UNCLEAR(e.args[0])
        finally:
            self.primary_registry.paging_limit = 100

    def test_05(self, test):
        """
        Reference Sender is put offline and then back online
        """
        try:
            # Check senders 

            question = 'The NCuT should be able to discover and dynamically update all the Senders that are registered in the Registry.\n\n' \
                'Use the NCuT to browse and take note of the Senders that are available.\n\n' \
                'After the \'Next\' button has been clicked one of those senders will be put \'offline\'.'
            possible_answers = []

            self._invoke_testing_facade(question, possible_answers, test_type="action")

            # Take one of the senders offline
            possible_answers = [{'answer_id': 'answer_'+str(i), 'label': s['label'], 'description': s['description'], 'id': s['id'], 'answer_str': s['answer_str']} for i, s in enumerate(self.senders) if s['registered'] == True]
            answer_indices = [index for index, s in enumerate(self.senders) if s['registered'] == True]
            offline_sender_index = random.choice(answer_indices)
            expected_answer = 'answer_' + str(offline_sender_index)

            self._delete_sender(test, self.senders[offline_sender_index])

            # Set the offline sender to registered false for future tests
            self.senders[offline_sender_index]['registered'] = False

            # Recheck senders
            question = 'Please refresh your NCuT and select the sender which has been put \'offline\''

            actual_answer = self._invoke_testing_facade(question, possible_answers, test_type="radio", multipart_test=1)['answer_response']

            if actual_answer != expected_answer:
                return test.FAIL('Offline/online sender not handled: Incorrect sender identified')

            max_time_until_online = 60
            max_time_to_answer = 30

            question = 'The sender which was put \'offline\' will come back online at a random moment within the next ' + str(max_time_until_online) + ' seconds. ' \
                'As soon as the NCuT detects the sender has come back online please press the \'Next\' button.\n\n' \
                'The button must be pressed within ' + str(max_time_to_answer) + ' seconds of the Sender being put back \'online\'. \n\n' \
                'This includes any latency between the Sender being put \'online\' and the NCuT updating.'
            possible_answers = []

            # Get the name of the calling test method to use as an identifier
            test_method_name = inspect.currentframe().f_code.co_name

            # Send the question to the Testing Façade and then put sender online before waiting for the Testing Façade response
            sent_json = self._send_testing_facade_questions(test_method_name, question, possible_answers, test_type="action", multipart_test=2)
            
            # Wait a random amount of time before bringing sender back online
            exitTestEvent.clear()
            time_delay = random.randint(10, max_time_until_online)
            expected_time_online = time.time() + time_delay
            exitTestEvent.wait(time_delay)

            # Re-register sender
            self._register_sender(self.senders[offline_sender_index], codes=[200, 201])
            self.senders[offline_sender_index]['registered'] = True

            # Await/get testing façade response
            response = self._wait_for_testing_facade(sent_json['name'])    

            if response['time_answered'] < expected_time_online: # Answered before sender put online
                return test.FAIL('Offline/online sender not handled: Sender not yet online')
            elif response['time_answered'] > expected_time_online + max_time_to_answer:
                return test.FAIL('Offline/online sender not handled: Sender online '  + str(int(response['time_answered'] - expected_time_online)) + ' seconds ago')
            else:
                return test.PASS('Offline/online sender handled correctly')                
        except TestingFacadeException as e:
            return test.UNCLEAR(e.args[0])
         