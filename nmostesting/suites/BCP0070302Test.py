# Copyright (C) 2026 Advanced Media Workflow Association
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

from operator import itemgetter

from ..ControllerTest import ControllerTest, MXL_TRANSPORT, TestingFacadeException
from ..NMOSUtils import NMOSUtils

MXL_RECEIVER_CAPS = {'media_types': ['video/v210'], 'constraint_sets': []}


class BCP0070302Test(ControllerTest):
    """
    Controller tests for AMWA BCP-007-03 MXL.
    """

    def __init__(self, apis, registries, node, dns_server, **kwargs):
        ControllerTest.__init__(self, apis, registries, node, dns_server, **kwargs)

    def set_up_tests(self):
        self.senders = [
            {'label': 's1/connery', 'description': 'Mock sender 1', 'registered': False},
            {'label': 's2/moore', 'description': 'Mock sender 2', 'registered': False},
            {'label': 's3/dalton', 'description': 'Mock sender 3', 'registered': False},
            {'label': 's4/brosnan', 'description': 'Mock sender 4', 'registered': False},
            {'label': 's5/craig', 'description': 'Mock sender 5', 'registered': False},
        ]

        sender_indices = list(range(len(self.senders)))
        mxl_sender_index = NMOSUtils.RANDOM.choice(sender_indices)
        rtp_sender_indices = [index for index in sender_indices if index != mxl_sender_index]
        rtp_sender_index = NMOSUtils.RANDOM.choice(rtp_sender_indices)

        for index, sender in enumerate(self.senders):
            use_mxl_transport = index == mxl_sender_index
            if not use_mxl_transport and index != rtp_sender_index:
                use_mxl_transport = NMOSUtils.RANDOM.choice([True, False])
            if use_mxl_transport:
                sender['transport'] = MXL_TRANSPORT

        register_senders = self.generate_random_indices(len(self.senders), min_index_count=3)
        mxl_sender_indices = [index for index, sender in enumerate(self.senders)
                              if self._sender_uses_mxl_transport(sender)]
        rtp_sender_indices = [index for index, sender in enumerate(self.senders)
                              if self._sender_uses_rtp_transport(sender)]

        for transport_indices in (mxl_sender_indices, rtp_sender_indices):
            if not any(index in register_senders for index in transport_indices):
                register_senders.append(NMOSUtils.RANDOM.choice(transport_indices))

        for index in register_senders:
            self.senders[index]['registered'] = True

        self.receivers = [
            {'label': 'r1/blofeld', 'description': 'Mock receiver 1',
             'connectable': True, 'registered': False},
            {'label': 'r2/goldfinger', 'description': 'Mock receiver 2',
             'connectable': True, 'registered': False},
            {'label': 'r3/le_chiffre', 'description': 'Mock receiver 3',
             'connectable': True, 'registered': False},
            {'label': 'r4/oberhauser', 'description': 'Mock receiver 4',
             'connectable': True, 'registered': False},
            {'label': 'r5/silva', 'description': 'Mock receiver 5',
             'connectable': True, 'registered': False},
        ]

        receiver_indices = list(range(len(self.receivers)))
        mxl_receiver_index = NMOSUtils.RANDOM.choice(receiver_indices)
        rtp_receiver_indices = [index for index in receiver_indices if index != mxl_receiver_index]
        rtp_receiver_index = NMOSUtils.RANDOM.choice(rtp_receiver_indices)

        for index, receiver in enumerate(self.receivers):
            use_mxl_transport = index == mxl_receiver_index
            if not use_mxl_transport and index != rtp_receiver_index:
                use_mxl_transport = NMOSUtils.RANDOM.choice([True, False])
            if use_mxl_transport:
                receiver['transport'] = MXL_TRANSPORT
                receiver['caps'] = MXL_RECEIVER_CAPS

        register_receivers = self.generate_random_indices(len(self.receivers), min_index_count=3)
        mxl_receiver_indices = [index for index, receiver in enumerate(self.receivers)
                                if self._receiver_uses_mxl_transport(receiver)]
        rtp_receiver_indices = [index for index, receiver in enumerate(self.receivers)
                                if self._receiver_uses_rtp_transport(receiver)]

        for transport_indices in (mxl_receiver_indices, rtp_receiver_indices):
            if not any(index in register_receivers for index in transport_indices):
                register_receivers.append(NMOSUtils.RANDOM.choice(transport_indices))

        for index in register_receivers:
            self.receivers[index]['registered'] = True

        ControllerTest.set_up_tests(self)

    def test_01(self, test):
        """
        Ensure NCuT can discover MXL Senders via the IS-04 Query API
        """
        MAX_COMPATIBLE_SENDER_COUNT = 3
        CANDIDATE_SENDER_COUNT = 4

        try:
            question = """\
                       The NCuT should be able to discover MXL Senders \
                       (transport urn:x-nmos:transport:mxl) registered in the Registry.

                       Refresh the NCuT's view of the Registry and select the MXL Senders \
                       from the following list.

                       Once MXL Senders have been identified press 'Submit'. If unable \
                       to identify MXL Senders, press 'Submit' without making a selection.
                       """

            registered_senders = [sender for sender in self.senders if sender["registered"]]
            mxl_senders = [sender for sender in registered_senders if self._sender_uses_mxl_transport(sender)]
            non_mxl_senders = [sender for sender in registered_senders if self._sender_uses_rtp_transport(sender)]

            mxl_sender_count = NMOSUtils.RANDOM.randint(1, min(MAX_COMPATIBLE_SENDER_COUNT, len(mxl_senders)))
            candidate_senders = NMOSUtils.RANDOM.sample(mxl_senders, mxl_sender_count)

            if len(candidate_senders) < CANDIDATE_SENDER_COUNT:
                other_sender_count = min(CANDIDATE_SENDER_COUNT - len(candidate_senders), len(non_mxl_senders))
                candidate_senders.extend(NMOSUtils.RANDOM.sample(non_mxl_senders, other_sender_count))

            candidate_senders.sort(key=itemgetter('label'))

            possible_answers = [{'answer_id': 'answer_' + str(index),
                                 'display_answer': sender['display_answer'],
                                 'resource': {'id': sender['id'], 'label': sender['label'],
                                              'description': sender['description']}}
                                for index, sender in enumerate(candidate_senders)]
            expected_answers = ['answer_' + str(index) for index, sender in enumerate(candidate_senders)
                                if self._sender_uses_mxl_transport(sender)]

            actual_answers = self.testing_facade_utils.invoke_testing_facade(
                question, possible_answers, test_type='multi_choice')['answer_response']

            actual = set(actual_answers)
            expected = set(expected_answers)

            if expected - actual:
                return test.FAIL('Not all MXL Senders identified')
            if actual - expected:
                return test.FAIL('Senders incorrectly identified as MXL')

            return test.PASS('All MXL Senders correctly identified')

        except TestingFacadeException as exception:
            return test.UNCLEAR(exception.args[0])

    def test_02(self, test):
        """
        Ensure NCuT can discover MXL Receivers via the IS-04 Query API
        """
        MAX_COMPATIBLE_RECEIVER_COUNT = 3
        CANDIDATE_RECEIVER_COUNT = 4

        try:
            question = """\
                       The NCuT should be able to discover MXL Receivers \
                       (transport urn:x-nmos:transport:mxl) registered in the Registry.

                       Refresh the NCuT's view of the Registry and select the MXL Receivers \
                       from the following list.

                       Once MXL Receivers have been identified press 'Submit'. If unable \
                       to identify MXL Receivers, press 'Submit' without making a selection.
                       """

            registered_receivers = [receiver for receiver in self.receivers if receiver["registered"]]
            mxl_receivers = [receiver for receiver in registered_receivers
                             if self._receiver_uses_mxl_transport(receiver)]
            non_mxl_receivers = [receiver for receiver in registered_receivers
                                 if self._receiver_uses_rtp_transport(receiver)]

            mxl_receiver_count = NMOSUtils.RANDOM.randint(1, min(MAX_COMPATIBLE_RECEIVER_COUNT, len(mxl_receivers)))
            candidate_receivers = NMOSUtils.RANDOM.sample(mxl_receivers, mxl_receiver_count)

            if len(candidate_receivers) < CANDIDATE_RECEIVER_COUNT:
                other_receiver_count = min(CANDIDATE_RECEIVER_COUNT - len(candidate_receivers), len(non_mxl_receivers))
                candidate_receivers.extend(NMOSUtils.RANDOM.sample(non_mxl_receivers, other_receiver_count))

            candidate_receivers.sort(key=itemgetter('label'))

            possible_answers = [{'answer_id': 'answer_' + str(index),
                                 'display_answer': receiver['display_answer'],
                                 'resource': {'id': receiver['id'], 'label': receiver['label'],
                                              'description': receiver['description']}}
                                for index, receiver in enumerate(candidate_receivers)]
            expected_answers = ['answer_' + str(index) for index, receiver in enumerate(candidate_receivers)
                                if self._receiver_uses_mxl_transport(receiver)]

            actual_answers = self.testing_facade_utils.invoke_testing_facade(
                question, possible_answers, test_type='multi_choice')['answer_response']

            actual = set(actual_answers)
            expected = set(expected_answers)

            if expected - actual:
                return test.FAIL('Not all MXL Receivers identified')
            if actual - expected:
                return test.FAIL('Receivers incorrectly identified as MXL')

            return test.PASS('All MXL Receivers correctly identified')

        except TestingFacadeException as exception:
            return test.UNCLEAR(exception.args[0])
