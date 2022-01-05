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

# The IS-04 Controller (IS-04-04) test suites map the tests described in Sections 7 of
# the JT-NM Tested March 2020 AMWA NMOS / JT-NM TR-1001-1 Media Nodes, Registries, Controllers Results Catalog
# https://static.jt-nm.org/documents/JT-NM_Tested_Catalog_NMOS-TR-1001_Full-Online-2020-05-12.pdf.

import time
import inspect
import random
import textwrap

from .. import Config as CONFIG
from ..ControllerTest import ControllerTest, TestingFacadeException, exitTestEvent


class IS0404Test(ControllerTest):
    """
    Testing initial set up of new test suite for controller testing
    """
    def __init__(self, apis, registries, node, dns_server):
        ControllerTest.__init__(self, apis, registries, node, dns_server)

    def set_up_tests(self):
        # Sender initial details
        self.senders = [{'label': 's1/gilmour', 'description': 'Mock sender 1', 'registered': False},
                        {'label': 's2/waters', 'description': 'Mock sender 2', 'registered': False},
                        {'label': 's3/wright', 'description': 'Mock sender 3', 'registered': False},
                        {'label': 's4/mason', 'description': 'Mock sender 4', 'registered': False},
                        {'label': 's5/barrett', 'description': 'Mock sender 5', 'registered': False}]

        # Randomly select some senders to register
        # minumum 3 to force pagination when paging_limit is set to 2
        register_senders = self._generate_random_indices(len(self.senders), min_index_count=3)

        for i in register_senders:
            self.senders[i]['registered'] = True

        # Receiver initial details
        self.receivers = [{'label': 'r1/palin', 'description': 'Mock receiver 1',
                           'connectable': True, 'registered': False},
                          {'label': 'r2/cleese', 'description': 'Mock receiver 2',
                           'connectable': True, 'registered': False},
                          {'label': 'r3/jones', 'description': 'Mock receiver 3',
                           'connectable': True, 'registered': False},
                          {'label': 'r4/chapman', 'description': 'Mock receiver 4',
                           'connectable': True, 'registered': False},
                          {'label': 'r5/idle', 'description': 'Mock receiver 5',
                           'connectable': True, 'registered': False},
                          {'label': 'r6/gilliam', 'description': 'Mock receiver 6',
                           'connectable': True, 'registered': False}]

        # Randomly select some receivers to register
        # minumum 3 to force pagination when paging_limit is set to 2
        register_receivers = self._generate_random_indices(len(self.receivers), min_index_count=3)

        for i in register_receivers:
            self.receivers[i]['registered'] = True

        ControllerTest.set_up_tests(self)

    def test_01(self, test):
        """
        Ensure NCuT uses unicast DNS-SD to find registry
        """
        # The NCuT shall use unicast DNS Service Discovery (DNS-SD) to locate the mock Registry.
        # A DHCP server will provide all the connection details to discover the mock Registry.

        if not CONFIG.ENABLE_DNS_SD or CONFIG.DNS_SD_MODE != "unicast":
            return test.DISABLED("This test cannot be performed when ENABLE_DNS_SD is False or DNS_SD_MODE is not "
                                 "'unicast'")

        # The DNS server will log queries that have been specified in set_up_tests()
        if self.dns_server.is_query_received():
            return test.PASS('DNS successfully queried by NCuT')

        return test.FAIL('DNS was not queried by the NCuT')

    def test_02(self, test):
        """
        Ensure NCuT can access the IS-04 Query API
        """
        # The NCuT shall use the mock Registry's IS-04 Query API either via the REST API or by
        # requesting websocket subscriptions.

        try:
            # Question 1 connection
            question = """\
                       Use the NCuT to browse the Senders and Receivers \
                       on the discovered Registry via the selected IS-04 Query API.

                       Once you have finished browsing click the 'Next' button.

                       Successful browsing of the Registry will be automatically logged by the test framework.
                       """
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
        # The NCuT shall use the mock Registry's IS-04 Query API to discover all the Senders that are
        # registered in the mock Registry. If using the RESTful API rather than WebSockets, Pagination must
        # be implemented.

        try:
            # reduce paging limit to force pagination on REST API
            self.primary_registry.paging_limit = 2
            # Check senders
            question = """\
                       The NCuT should be able to discover all the Senders \
                       that are registered in the Registry.

                       Refresh the NCuT's view of the Registry and carefully select the Senders \
                       that are available from the following list.

                       For this test the registry paging limit has been set to 2. \
                       If your NCuT implements pagination, you must ensure you view \
                       every available page to complete this test.
                       """
            possible_answers = [{'answer_id': 'answer_'+str(i), 'label': s['label'],
                                 'description': s['description'], 'id': s['id'], 'answer_str': s['answer_str']}
                                for i, s in enumerate(self.senders)]
            expected_answers = ['answer_'+str(i) for i, s in enumerate(self.senders) if s['registered']]

            actual_answers = self._invoke_testing_facade(
                question, possible_answers, test_type="multi_choice")['answer_response']

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
        # The NCuT shall use the mock Registry's IS-04 Query API to discover all the Receivers that
        # are registered in the mock Registry. If using the RESTful API rather than WebSockets,
        # Pagination must be implemented.

        try:
            # reduce paging limit to force pagination on REST API
            self.primary_registry.paging_limit = 2

            # Check receivers
            question = """\
                       The NCuT should be able to discover all the Receivers \
                       that are registered in the Registry.

                       Refresh the NCuT's view of the Registry and carefully select the Receivers \
                       that are available from the following list.

                       For this test the registry paging limit has been set to 2. \
                       If your NCuT implements pagination, you must ensure you view \
                       every available page to complete this test.
                       """
            possible_answers = [{'answer_id': 'answer_'+str(i), 'label': r['label'],
                                 'description': r['description'], 'id': r['id'], 'answer_str': r['answer_str']}
                                for i, r in enumerate(self.receivers)]
            expected_answers = ['answer_'+str(i) for i, r in enumerate(self.receivers) if r['registered']]

            actual_answers = self._invoke_testing_facade(
                question, possible_answers, test_type="multi_choice")['answer_response']

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
        # The NCuT shall discover and dynamically update all the Senders that are registered
        # in the Registry.
        # * Use the NCuT to browse and take note of the Senders that are available.
        # * After the 'Next' button has been clicked one of those Senders will be put 'offline'.
        # * The Sender which was put 'offline' will then come back online at a random moment within
        #   the following 60 seconds.
        # * As soon as the NCuT detects the Sender has come back online the user must press the
        #   'Next' button on the Testing Façade.
        # * The button must be pressed within 30 seconds of the Sender being put back 'online'.
        #   This includes any latency between the Sender being put 'online' and the NCuT updating.

        try:
            # Check senders

            question = """\
                       The NCuT should be able to discover and dynamically update all the Senders \
                       that are registered in the Registry.

                       Use the NCuT to browse and take note of the Senders that are available.

                       After the 'Next' button has been clicked one of those senders will be put 'offline'.
                       """
            possible_answers = []

            self._invoke_testing_facade(question, possible_answers, test_type="action")

            # Take one of the senders offline
            possible_answers = [{'answer_id': 'answer_'+str(i), 'label': s['label'],
                                 'description': s['description'], 'id': s['id'], 'answer_str': s['answer_str']}
                                for i, s in enumerate(self.senders) if s['registered']]
            answer_indices = [index for index, s in enumerate(self.senders) if s['registered']]
            offline_sender_index = random.choice(answer_indices)
            expected_answer = 'answer_' + str(offline_sender_index)

            self._delete_sender(test, self.senders[offline_sender_index])

            # Set the offline sender to registered false for future tests
            self.senders[offline_sender_index]['registered'] = False

            # Recheck senders
            question = 'Please refresh your NCuT and select the sender which has been put \'offline\'.'

            actual_answer = self._invoke_testing_facade(
                question, possible_answers, test_type="single_choice", multipart_test=1)['answer_response']

            if actual_answer != expected_answer:
                return test.FAIL('Offline/online sender not handled: Incorrect sender identified')

            max_time_until_online = 60
            max_time_to_answer = 30

            question = textwrap.dedent(f"""\
                       The sender which was put 'offline' will come back online at a random moment \
                       within the next {max_time_until_online} seconds. \
                       As soon as the NCuT detects the sender has come back online please press the 'Next' button.

                       The button must be pressed within {max_time_to_answer} seconds of the \
                       Sender being put back 'online'.

                       This includes any latency between the Sender being put 'online' and the NCuT updating.
                       """)
            possible_answers = []

            # Get the name of the calling test method to use as an identifier
            test_method_name = inspect.currentframe().f_code.co_name

            # Send the question to the Testing Façade
            # and then put sender online before waiting for the Testing Façade response
            sent_json = self._send_testing_facade_questions(
                test_method_name, question, possible_answers, test_type="action", multipart_test=2)

            # Wait a random amount of time before bringing sender back online
            exitTestEvent.clear()
            time_delay = random.randint(10, max_time_until_online)
            expected_time_online = time.time() + time_delay
            exitTestEvent.wait(time_delay)

            # Re-register sender
            self._register_sender(self.senders[offline_sender_index], codes=[200, 201])
            self.senders[offline_sender_index]['registered'] = True

            # Await/get testing façade response
            response = self._wait_for_testing_facade(sent_json['question_id'])

            if response['time_answered'] < expected_time_online:  # Answered before sender put online
                return test.FAIL('Offline/online sender not handled: Sender not yet online')
            elif response['time_answered'] > expected_time_online + max_time_to_answer:
                return test.FAIL('Offline/online sender not handled: Sender online ' +
                                 str(int(response['time_answered'] - expected_time_online)) + ' seconds ago')
            else:
                return test.PASS('Offline/online sender handled correctly')
        except TestingFacadeException as e:
            return test.UNCLEAR(e.args[0])
