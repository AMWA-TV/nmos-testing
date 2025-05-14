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

# The IS-05 Controller (IS-05-03) test suites map the tests described in Sections 8 of
# the JT-NM Tested March 2020 AMWA NMOS / JT-NM TR-1001-1 Media Nodes, Registries, Controllers Results Catalog
# https://static.jt-nm.org/documents/JT-NM_Tested_Catalog_NMOS-TR-1001_Full-Online-2020-05-12.pdf.

import time
import inspect
import random
import textwrap

from ..ControllerTest import ControllerTest, TestingFacadeException
from ..TestingFacadeUtils import exitTestEvent


class IS0503Test(ControllerTest):
    """
    Testing initial set up of new test suite for controller testing
    """
    def __init__(self, apis, **kwargs):
        ControllerTest.__init__(self, apis, **kwargs)

    def set_up_tests(self):
        # Sender initial details
        self.senders = [{'label': 's1/partridge', 'description': 'Mock sender 1', 'registered': False},
                        {'label': 's2/moulding', 'description': 'Mock sender 2', 'registered': False},
                        {'label': 's3/gregory', 'description': 'Mock sender 3', 'registered': False},
                        {'label': 's4/chambers', 'description': 'Mock sender 4', 'registered': False},
                        {'label': 's5/andrews', 'description': 'Mock sender 5', 'registered': False}]

        # Randomly select some senders to register
        register_senders = self.generate_random_indices(len(self.senders))

        for i in register_senders:
            self.senders[i]['registered'] = True

        # Receiver initial details
        self.receivers = [{'label': 'r1/byrne', 'description': 'Mock receiver 1',
                           'connectable': False, 'registered': True},
                          {'label': 'r2/frantz', 'description': 'Mock receiver 2',
                           'connectable': False, 'registered': True},
                          {'label': 'r3/weymouth', 'description': 'Mock receiver 3',
                           'connectable': False, 'registered': True},
                          {'label': 'r4/harrison', 'description': 'Mock receiver 4',
                           'connectable': False, 'registered': True},
                          {'label': 'r5/belew', 'description': 'Mock receiver 5',
                           'connectable': False, 'registered': True}]

        # Randomly select some receivers to be connectable
        connectable_receivers = self.generate_random_indices(len(self.receivers), min_index_count=2, max_index_count=4)

        for i in connectable_receivers:
            self.receivers[i]['connectable'] = True

        ControllerTest.set_up_tests(self)

    def _reset_receivers(self):
        """
        Send deactivate requests to all receivers
        """
        connectable_receivers = [receiver for receiver in self.receivers if receiver["connectable"]]

        for receiver in connectable_receivers:
            deactivate_json = {"master_enable": False, 'sender_id': None,
                               "activation": {"mode": "activate_immediate"}}
            self.node.patch_staged('receivers', receiver['id'], deactivate_json)

    def test_01(self, test):
        """
        Identify which Receiver devices are controllable via IS-05
        """
        # The NCuT shall identify which of the discovered Receivers are controllable via IS-05, for instance,
        # allowing Senders to be connected.
        # * The Testing Tool registers additional Receivers with the mock Registry,
        #   a subset of which have a connection API.
        # * The Test User refreshes the NCuT and selects the Receivers that have a
        #   connection API from the provided list.
        # * Some NCuTs only display those Receivers which have a connection API,
        #   therefore some of the Receivers in the provided list may not be visible.

        try:
            # Check receivers
            question = """\
                       A subset of the Receivers registered with the Registry are controllable via IS-05, \
                       for instance, allowing Senders to be connected. \

                       Please refresh your NCuT and select the Receivers \
                       that have a Connection API from the list below.

                       Be aware that if your NCuT only displays Receivers which have a Connection API, \
                       some of the Receivers in the following list may not be visible.
                       """
            possible_answers = [{'answer_id': 'answer_'+str(i), 'display_answer': r['display_answer'],
                                'resource': {'id': r['id'], 'label': r['label'], 'description': r['description']}}
                                for i, r in enumerate(self.receivers)]
            expected_answers = ['answer_'+str(i) for i, r in enumerate(self.receivers)
                                if r['registered'] and r['connectable']]

            actual_answers = self.testing_facade_utils.invoke_testing_facade(
                question, possible_answers, test_type="multi_choice")['answer_response']

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
            self._reset_receivers()

    def test_02(self, test):
        """
        Instruct Receiver to subscribe to a Sender's Flow via IS-05
        """
        # The NCuT shall allow all flows that are available in a Sender to be connected to a Receiver.
        # * The Test User is prompted to perform an immediate activation between a specified Sender and Receiver.

        try:
            self.node.clear_staged_requests()
            # Choose random sender and receiver to be connected
            registered_senders = [s for s in self.senders if s['registered']]
            sender = random.choice(registered_senders)
            registered_receivers = [r for r in self.receivers if r['registered'] and r['connectable']]
            receiver = random.choice(registered_receivers)

            question = textwrap.dedent(f"""\
                       All flows that are available in a Sender should be able to be connected to a Receiver.

                       Use the NCuT to perform an 'immediate' activation between sender:

                       {sender['display_answer']}

                       and receiver:

                       {receiver['display_answer']}

                       Click the 'Next' button once the connection is active.
                       """)

            possible_answers = []

            metadata = {'sender':
                        {'id': sender['id'],
                         'label': sender['label'],
                         'description': sender['description']},
                        'receiver':
                        {'id': receiver['id'],
                         'label': receiver['label'],
                         'description': receiver['description']}}

            self.testing_facade_utils.invoke_testing_facade(question, possible_answers,
                                                            test_type="action", metadata=metadata)

            # Check the staged API endpoint received the correct PATCH request
            patch_requests = [r for r in self.node.staged_requests
                              if r['method'] == 'PATCH' and r['resource'] == 'receivers']
            if len(patch_requests) < 1:
                return test.FAIL('No PATCH request was received by the node')
            elif len(patch_requests) == 1:
                if patch_requests[0]['resource_id'] != receiver['id']:
                    return test.FAIL('Connection request sent to incorrect receiver')

                if 'master_enable' not in patch_requests[0]['data']:
                    return test.FAIL('Master enable not found in PATCH request')
                else:
                    if not patch_requests[0]['data']['master_enable']:
                        return test.FAIL('Master_enable not set to True in PATCH request')

                if 'sender_id' in patch_requests[0]['data'] and patch_requests[0]['data']['sender_id']\
                        and patch_requests[0]['data']['sender_id'] != sender['id']:
                    return test.FAIL('Incorrect sender found in PATCH request')

                if 'activation' not in patch_requests[0]['data']:
                    return test.FAIL('No activation details in PATCH request')

                if patch_requests[0]['data']['activation'].get('mode') != 'activate_immediate':
                    return test.FAIL('Immediate activation not requested in PATCH request')
            else:
                return test.FAIL('Multiple PATCH requests were found')

            # Check the receiver now has subscription details
            if receiver['id'] in self.primary_registry.get_resources()["receiver"]:
                receiver_details = self.primary_registry.get_resources()["receiver"][receiver['id']]

                if not receiver_details['subscription']['active']:
                    return test.FAIL('Receiver does not have active subscription')

                if 'sender_id' in receiver_details['subscription'] and receiver_details['subscription']['sender_id']\
                        and receiver_details['subscription']['sender_id'] != sender['id']:
                    return test.FAIL('Receiver did not connect to correct sender')

            if 'sender_id' not in patch_requests[0]['data'] or not patch_requests[0]['data']['sender_id']:
                return test.WARNING('Sender id SHOULD be set in patch request')

            return test.PASS("Connection successfully established")
        except TestingFacadeException as e:
            return test.UNCLEAR(e.args[0])
        finally:
            self._reset_receivers()

    def test_03(self, test):
        """
        Disconnecting a Receiver from a connected Flow via IS-05
        """
        # The NCuT shall allow removal of active connections via the IS-05 API.
        # * The Testing Tool activates a connection between a Sender and a Receiver.
        # * The Test User is asked to perform an immediate deactivation on this connection.

        try:
            # Choose random sender and receiver to be connected
            registered_senders = [s for s in self.senders if s['registered']]
            sender = random.choice(registered_senders)
            registered_receivers = [r for r in self.receivers if r['registered'] and r['connectable']]
            receiver = random.choice(registered_receivers)

            # Set up connection on the mock node
            valid, response = self.do_request('GET', self.mock_node_base_url
                                              + 'x-nmos/connection/' + self.connection_api_version + '/single/senders/'
                                              + sender['id'] + '/transportfile')
            transport_file = response.content.decode()
            activate_json = {"activation": {"mode": "activate_immediate"},
                             "master_enable": True,
                             "sender_id": sender['id'],
                             "transport_file": {"data": transport_file, "type": "application/sdp"}}
            self.node.patch_staged('receivers', receiver['id'], activate_json)

            # Clear staged requests once connection has been set up
            self.node.clear_staged_requests()

            question = textwrap.dedent(f"""\
                       IS-05 provides a mechanism for removing an active connection through its API.

                       Use the NCuT to remove the connection between sender:

                       {sender['display_answer']}

                       and receiver:

                       {receiver['display_answer']}

                       Click the 'Next' button once the connection has been removed.
                       """)

            possible_answers = []

            metadata = {'sender':
                        {'id': sender['id'],
                         'label': sender['label'],
                         'description': sender['description']},
                        'receiver':
                        {'id': receiver['id'],
                         'label': receiver['label'],
                         'description': receiver['description']}}

            self.testing_facade_utils.invoke_testing_facade(question, possible_answers,
                                                            test_type="action", metadata=metadata)

            # Check the staged API endpoint received a PATCH request
            patch_requests = [r for r in self.node.staged_requests
                              if r['method'] == 'PATCH' and r['resource'] == 'receivers']
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

                    if receiver_details['subscription']['active'] \
                            or receiver_details['subscription']['sender_id'] == sender['id']:
                        return test.FAIL('Receiver still has subscription')

            return test.PASS('Receiver successfully disconnected from sender')
        except TestingFacadeException as e:
            return test.UNCLEAR(e.args[0])
        finally:
            self._reset_receivers()

    def test_04(self, test):
        """
        Indicating the state of connections via updates received from the IS-04 Query API
        """
        # The NCuT shall monitor and update the connection status of all registered Devices.
        # This test seeks to validate the NCuT's ability to monitor connections that are made between
        # Senders and Receivers outside of the NCuT's control.
        # * A connection to a Receiver is activated.
        # * The Test User is asked to identify this Receiver.
        # * The Test User is asked to identify the Sender connected to the Receiver.
        # * The Receiver connection is deactivated in the background by the Testing Tool
        #   within the following 60 seconds.
        # * As soon as the NCuT detects the Receiver has been deactivated the Test User must press the 'Next' button.
        # * The button must be pressed within 30 seconds of the Receiver connection being deactivated.
        #   This includes any latency between the Receiver connection being deactivated and the NCuT updating.

        try:
            # Choose random sender and receiver to be connected
            registered_senders = [s for s in self.senders if s['registered']]
            sender = random.choice(registered_senders)
            registered_receivers = [r for r in self.receivers if r['registered'] and r['connectable']]
            receiver = random.choice(registered_receivers)

            # Set up connection on the mock node
            valid, response = self.do_request('GET', self.mock_node_base_url
                                              + 'x-nmos/connection/' + self.connection_api_version + '/single/senders/'
                                              + sender['id'] + '/transportfile')
            transport_file = response.content.decode()
            activate_json = {"activation": {"mode": "activate_immediate"},
                             "master_enable": True,
                             "sender_id": sender['id'],
                             "transport_file": {"data": transport_file, "type": "application/sdp"}}
            self.node.patch_staged('receivers', receiver['id'], activate_json)

            # Identify which Receiver has been activated
            question = """\
                       The NCuT should be able to monitor \
                       and update the connection status of all registered Devices.

                       Use the NCuT to identify the receiver that has just been connected.
                       """

            possible_answers = [{'answer_id': 'answer_'+str(i), 'display_answer': r['display_answer'],
                                'resource': {'id': r['id'], 'label': r['label'], 'description': r['description']}}
                                for i, r in enumerate(registered_receivers) if r['registered']]
            expected_answer = ['answer_' + str(i) for i, r in enumerate(registered_receivers)
                               if r['display_answer'] == receiver['display_answer']][0]

            actual_answer = self.testing_facade_utils.invoke_testing_facade(
                question, possible_answers, test_type="single_choice")['answer_response']

            if actual_answer != expected_answer:
                return test.FAIL('Incorrect receiver identified')

            # Identify a connection
            question = textwrap.dedent(f"""\
                       Use the NCuT to identify the sender currently connected to receiver:

                       {receiver['display_answer']}
                       """)

            possible_answers = [{'answer_id': 'answer_'+str(i), 'display_answer': s['display_answer'],
                                'resource': {'id': s['id'], 'label': s['label'], 'description': s['description']}}
                                for i, s in enumerate(registered_senders) if s['registered']]
            expected_answer = ['answer_'+str(i) for i, s in enumerate(registered_senders)
                               if s['display_answer'] == sender['display_answer']][0]

            metadata = {'receiver':
                        {'id': receiver['id'],
                         'label': receiver['label'],
                         'description': receiver['description']}}

            actual_answer = self.testing_facade_utils.invoke_testing_facade(
                question, possible_answers, test_type="single_choice", multipart_test=1,
                metadata=metadata)['answer_response']

            if actual_answer != expected_answer:
                return test.FAIL('Incorrect sender identified')

            max_time_until_online = 60
            max_time_to_answer = 30

            # Indicate when connection has gone offline
            question = textwrap.dedent(f"""\
                       The connection on the following receiver will be disconnected \
                       at a random moment within the next {max_time_until_online} seconds.

                       {receiver['display_answer']}

                       As soon as the NCuT detects the connection is inactive please press the 'Next' button.\
                       The button must be pressed within {max_time_to_answer} seconds \
                       of the connection being removed.

                       This includes any latency between the connection being removed and the NCuT updating.
                       """)
            possible_answers = []

            # Get the name and the description of this test method to use as an identifier
            test_method_name = inspect.currentframe().f_code.co_name
            method = getattr(self, test_method_name)
            test_method_description = inspect.getdoc(method)

            # Send the question to the Testing Façade
            sent_json = self.testing_facade_utils.send_testing_facade_questions(
                test_method_name, test_method_description, question, possible_answers,
                test_type="action", multipart_test=2, metadata=metadata)

            # Wait a random amount of time before disconnecting
            exitTestEvent.clear()
            time_delay = random.randint(10, max_time_until_online)
            expected_time_online = time.time() + time_delay
            exitTestEvent.wait(time_delay)

            # Remove connection
            deactivate_json = {"master_enable": False, 'sender_id': None,
                               "activation": {"mode": "activate_immediate"}}
            self.node.patch_staged('receivers', receiver['id'], deactivate_json)

            response = self.testing_facade_utils.wait_for_testing_facade(sent_json['question_id'], 'action')

            if response['time_received'] < expected_time_online:  # Answered before connection was removed
                return test.FAIL('Connection not handled: Connection still active')
            elif response['time_received'] > expected_time_online + max_time_to_answer:
                return test.FAIL('Connection not handled: Connection removed ' +
                                 str(int(response['time_received'] - expected_time_online)) + ' seconds ago')
            else:
                return test.PASS('Connection handled correctly')
        except TestingFacadeException as e:
            return test.UNCLEAR(e.args[0])
        finally:
            self._reset_receivers()
