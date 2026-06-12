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

import textwrap
from operator import itemgetter

from .. import Config as CONFIG
from ..ControllerTest import ControllerTest, MXL_TRANSPORT, TestingFacadeException
from ..GenericTest import NMOSInitException
from ..NMOSUtils import NMOSUtils

MINIMUM_MXL_ENDPOINTS = 3
TEST_EXAMPLE_COUNT = 3


def _mxl_components(frame_width, frame_height, bit_depth=10):
    return [
        {'name': 'Y', 'width': frame_width, 'height': frame_height, 'bit_depth': bit_depth},
        {'name': 'Cb', 'width': frame_width // 2, 'height': frame_height, 'bit_depth': bit_depth},
        {'name': 'Cr', 'width': frame_width // 2, 'height': frame_height, 'bit_depth': bit_depth},
    ]


MXL_FLOW_PROFILE_1080P25 = {
    'profile_id': '1080p25',
    'media_type': 'video/v210',
    'frame_width': 1920,
    'frame_height': 1080,
    'grain_rate': {'numerator': 25, 'denominator': 1},
    'interlace_mode': 'progressive',
    'colorspace': 'BT709',
    'transfer_characteristic': 'SDR',
    'components': _mxl_components(1920, 1080),
}

MXL_FLOW_PROFILE_720P50 = {
    'profile_id': '720p50',
    'media_type': 'video/v210',
    'frame_width': 1280,
    'frame_height': 720,
    'grain_rate': {'numerator': 50, 'denominator': 1},
    'interlace_mode': 'progressive',
    'colorspace': 'BT709',
    'transfer_characteristic': 'SDR',
    'components': _mxl_components(1280, 720),
}

MXL_FLOW_PROFILES = [MXL_FLOW_PROFILE_1080P25, MXL_FLOW_PROFILE_720P50]

CAP_URI_TO_FLOW_FIELD = {
    'urn:x-nmos:cap:format:media_type': 'media_type',
    'urn:x-nmos:cap:format:frame_width': 'frame_width',
    'urn:x-nmos:cap:format:frame_height': 'frame_height',
    'urn:x-nmos:cap:format:grain_rate': 'grain_rate',
    'urn:x-nmos:cap:format:interlace_mode': 'interlace_mode',
    'urn:x-nmos:cap:format:colorspace': 'colorspace',
    'urn:x-nmos:cap:format:transfer_characteristic': 'transfer_characteristic',
}


class BCP0070302Test(ControllerTest):
    """
    Controller tests for AMWA BCP-007-03 MXL.
    """

    def __init__(self, apis, registries, node, dns_server, **kwargs):
        ControllerTest.__init__(self, apis, registries, node, dns_server, **kwargs)

    def _profile_to_flow_params(self, profile):
        return {key: value for key, value in profile.items() if key != 'profile_id'}

    def _apply_flow_profile_to_sender(self, sender, profile):
        sender['profile_id'] = profile['profile_id']
        sender['flow_params'] = self._profile_to_flow_params(profile)

    def _generate_constraint_set(self, profile):
        return {
            'urn:x-nmos:cap:format:media_type': {
                'enum': [profile['media_type']]
            },
            'urn:x-nmos:cap:format:frame_width': {
                'enum': [profile['frame_width']]
            },
            'urn:x-nmos:cap:format:frame_height': {
                'enum': [profile['frame_height']]
            },
            'urn:x-nmos:cap:format:grain_rate': {
                'enum': [profile['grain_rate']]
            },
            'urn:x-nmos:cap:format:interlace_mode': {
                'enum': [profile['interlace_mode']]
            },
            'urn:x-nmos:cap:format:colorspace': {
                'enum': [profile['colorspace']]
            },
            'urn:x-nmos:cap:format:transfer_characteristic': {
                'enum': [profile['transfer_characteristic']]
            },
            'urn:x-nmos:cap:format:component_depth': {
                'enum': [max(component['bit_depth'] for component in profile['components'])]
            },
        }

    def _generate_caps(self, accepted_profiles):
        caps = {
            'media_types': [],
            'constraint_sets': [],
        }

        for profile in accepted_profiles:
            media_type = profile['media_type']
            if media_type not in caps['media_types']:
                caps['media_types'].append(media_type)
            caps['constraint_sets'].append(self._generate_constraint_set(profile))

        return caps

    def _flow_value_for_cap(self, flow_params, cap_uri):
        if cap_uri == 'urn:x-nmos:cap:format:component_depth':
            return max(component['bit_depth'] for component in flow_params['components'])

        flow_field = CAP_URI_TO_FLOW_FIELD[cap_uri]
        return flow_params[flow_field]

    def _constraint_satisfied(self, flow_value, constraint):
        for constraint_key, constraint_value in constraint.items():
            if constraint_key == 'enum' and flow_value not in constraint_value:
                return False
            if constraint_key == 'minimum' and flow_value < constraint_value:
                return False
            if constraint_key == 'maximum' and flow_value > constraint_value:
                return False
        return True

    def _flow_matches_constraint_set(self, flow_params, constraint_set):
        for cap_uri, constraint in constraint_set.items():
            if cap_uri not in CAP_URI_TO_FLOW_FIELD and cap_uri != 'urn:x-nmos:cap:format:component_depth':
                continue
            flow_value = self._flow_value_for_cap(flow_params, cap_uri)
            if not self._constraint_satisfied(flow_value, constraint):
                return False
        return True

    def _is_compatible(self, sender, receiver):
        if not self._sender_uses_mxl_transport(sender) or not self._receiver_uses_mxl_transport(receiver):
            return False

        flow_params = sender.get('flow_params', {})
        receiver_caps = receiver.get('caps', {})
        media_type = flow_params.get('media_type')

        if media_type not in receiver_caps.get('media_types', []):
            return False

        constraint_sets = receiver_caps.get('constraint_sets', [])
        if not constraint_sets:
            return False

        return any(self._flow_matches_constraint_set(flow_params, constraint_set)
                   for constraint_set in constraint_sets)

    def _select_mxl_indices(self, endpoint_count):
        # Need at least MINIMUM_MXL_ENDPOINTS MXL and one RTP transport
        if endpoint_count < MINIMUM_MXL_ENDPOINTS + 1:
            raise NMOSInitException(
                "Fixture setup: need at least {} endpoints to support both MXL and RTP transports".format(
                    MINIMUM_MXL_ENDPOINTS + 1))

        mxl_count = NMOSUtils.RANDOM.randint(MINIMUM_MXL_ENDPOINTS, endpoint_count - 1)
        return NMOSUtils.RANDOM.sample(range(endpoint_count), mxl_count)

    def _assign_mxl_sender_profiles(self, mxl_sender_indices):
        for position, sender_index in enumerate(mxl_sender_indices):
            profile = MXL_FLOW_PROFILES[position % len(MXL_FLOW_PROFILES)]
            self._apply_flow_profile_to_sender(self.senders[sender_index], profile)

    def _assign_mxl_receiver_caps(self, mxl_receiver_indices):
        for position, receiver_index in enumerate(mxl_receiver_indices):
            profile = MXL_FLOW_PROFILES[position % len(MXL_FLOW_PROFILES)]
            self.receivers[receiver_index]['caps'] = self._generate_caps([profile])

    def _select_test_mxl_senders(self):
        connectable_mxl_receivers = self._registered_connectable_mxl_receivers()
        testable_senders = [
            sender for sender in self._registered_mxl_senders()
            if any(self._is_compatible(sender, receiver) for receiver in connectable_mxl_receivers)
        ]

        if CONFIG.MAX_TEST_ITERATIONS:
            example_count = min(CONFIG.MAX_TEST_ITERATIONS, len(testable_senders))
        else:
            example_count = min(TEST_EXAMPLE_COUNT, len(testable_senders))

        if example_count == 0:
            return []

        return NMOSUtils.RANDOM.sample(testable_senders, example_count)

    def set_up_tests(self):
        NMOSUtils.RANDOM.seed(a=CONFIG.RANDOM_SEED)

        self.senders = [
            {'label': 's1/connery', 'description': 'Mock sender 1', 'registered': False},
            {'label': 's2/niven', 'description': 'Mock sender 2', 'registered': False},
            {'label': 's3/lazenby', 'description': 'Mock sender 3', 'registered': False},
            {'label': 's4/moore', 'description': 'Mock sender 4', 'registered': False},
            {'label': 's5/dalton', 'description': 'Mock sender 5', 'registered': False},
            {'label': 's6/brosnan', 'description': 'Mock sender 6', 'registered': False},
            {'label': 's7/craig', 'description': 'Mock sender 7', 'registered': False},
        ]

        mxl_sender_indices = self._select_mxl_indices(len(self.senders))
        for index, sender in enumerate(self.senders):
            if index in mxl_sender_indices:
                sender['transport'] = MXL_TRANSPORT
            sender['registered'] = True

        self._assign_mxl_sender_profiles(mxl_sender_indices)

        self.receivers = [
            {'label': 'r1/dr_no', 'description': 'Mock receiver 1',
             'connectable': True, 'registered': False},
            {'label': 'r2/blofeld', 'description': 'Mock receiver 2',
             'connectable': True, 'registered': False},
            {'label': 'r3/goldfinger', 'description': 'Mock receiver 3',
             'connectable': True, 'registered': False},
            {'label': 'r4/scaramanga', 'description': 'Mock receiver 4',
             'connectable': True, 'registered': False},
            {'label': 'r5/le_chiffre', 'description': 'Mock receiver 5',
             'connectable': True, 'registered': False},
            {'label': 'r6/silva', 'description': 'Mock receiver 6',
             'connectable': True, 'registered': False},
            {'label': 'r7/oberhauser', 'description': 'Mock receiver 7',
             'connectable': True, 'registered': False},
        ]

        mxl_receiver_indices = self._select_mxl_indices(len(self.receivers))
        for index, receiver in enumerate(self.receivers):
            if index in mxl_receiver_indices:
                receiver['transport'] = MXL_TRANSPORT
            receiver['registered'] = True

        self._assign_mxl_receiver_caps(mxl_receiver_indices)

        ControllerTest.set_up_tests(self)

    def _reset_mxl_receivers(self):
        for receiver in self._registered_connectable_mxl_receivers():
            deactivate_json = {
                'master_enable': False,
                'sender_id': None,
                'activation': {'mode': 'activate_immediate'},
            }
            self.node.patch_staged('receivers', receiver['id'], deactivate_json)

    def _registered_mxl_senders(self):
        return [
            sender for sender in self.senders
            if sender['registered'] and self._sender_uses_mxl_transport(sender)
        ]

    def _registered_connectable_mxl_receivers(self):
        return [
            receiver for receiver in self.receivers
            if receiver['registered'] and receiver['connectable']
            and self._receiver_uses_mxl_transport(receiver)
        ]

    def _transport_file_acceptable(self, patch_data):
        if 'transport_file' not in patch_data:
            return True

        transport_file = patch_data['transport_file']
        if transport_file is None:
            return True

        return transport_file.get('data') is None and transport_file.get('type') is None

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

    def test_03(self, test):
        """
        Connect an MXL Receiver to an MXL Sender via the IS-05 Connection API
        """
        try:
            mxl_senders = self._select_test_mxl_senders()

            if not mxl_senders:
                return test.FAIL('No registered MXL Senders available for connection test')

            tested_connection = False

            for sender in mxl_senders:
                self.node.clear_staged_requests()
                self._reset_mxl_receivers()

                compatible_receivers = [
                    receiver for receiver in self._registered_connectable_mxl_receivers()
                    if self._is_compatible(sender, receiver)
                ]
                if not compatible_receivers:
                    continue

                receiver = NMOSUtils.RANDOM.choice(compatible_receivers)
                tested_connection = True

                question = textwrap.dedent(f"""\
                           It should be possible to connect available MXL Senders to compatible MXL Receivers \
                           using the IS-05 Connection API.

                           Use the NCuT to perform an 'immediate' activation between sender:

                           {sender['display_answer']}

                           and receiver:

                           {receiver['display_answer']}

                           Click the 'Next' button once the connection is active.
                           """)

                metadata = {
                    'sender': {
                        'id': sender['id'],
                        'label': sender['label'],
                        'description': sender['description'],
                    },
                    'receiver': {
                        'id': receiver['id'],
                        'label': receiver['label'],
                        'description': receiver['description'],
                    },
                }

                self.testing_facade_utils.invoke_testing_facade(
                    question, [], test_type='action', metadata=metadata)

                patch_requests = [
                    request for request in self.node.staged_requests
                    if request['method'] == 'PATCH' and request['resource'] == 'receivers'
                ]
                if len(patch_requests) < 1:
                    return test.FAIL('No PATCH request was received by the node')
                if len(patch_requests) > 1:
                    return test.FAIL('Multiple PATCH requests were found')

                patch_request = patch_requests[0]
                patch_data = patch_request['data']

                if patch_request['resource_id'] != receiver['id']:
                    return test.FAIL('Connection request sent to incorrect receiver')

                if 'master_enable' not in patch_data:
                    return test.FAIL('Master enable not found in PATCH request')
                if not patch_data['master_enable']:
                    return test.FAIL('Master_enable not set to True in PATCH request')

                if patch_data.get('sender_id') and patch_data['sender_id'] != sender['id']:
                    return test.FAIL('Incorrect sender found in PATCH request')

                if 'activation' not in patch_data:
                    return test.FAIL('No activation details in PATCH request')
                if patch_data['activation'].get('mode') != 'activate_immediate':
                    return test.FAIL('Immediate activation not requested in PATCH request')

                if receiver['id'] in self.primary_registry.get_resources()['receiver']:
                    receiver_details = self.primary_registry.get_resources()['receiver'][receiver['id']]

                    if not receiver_details['subscription']['active']:
                        return test.FAIL('Receiver does not have active subscription')

                    subscription_sender_id = receiver_details['subscription'].get('sender_id')
                    if subscription_sender_id and subscription_sender_id != sender['id']:
                        return test.FAIL('Receiver did not connect to correct sender')

                if 'sender_id' not in patch_data or not patch_data['sender_id']:
                    return test.WARNING('Sender id SHOULD be set in patch request')

                if 'transport_params' in patch_data:
                    transport_params = patch_data['transport_params'][0]
                    mxl_flow_id = transport_params.get('mxl_flow_id')
                    if mxl_flow_id and mxl_flow_id not in (None, 'auto') and mxl_flow_id != sender['flow_id']:
                        return test.FAIL('Incorrect mxl_flow_id found in PATCH request')

                deactivate_json = {
                    'master_enable': False,
                    'sender_id': None,
                    'activation': {'mode': 'activate_immediate'},
                }
                self.node.patch_staged('receivers', receiver['id'], deactivate_json)

            if not tested_connection:
                return test.FAIL('No compatible MXL Sender and Receiver pairs available for connection test')

            return test.PASS('Connections successfully established')

        except TestingFacadeException as exception:
            return test.UNCLEAR(exception.args[0])
        finally:
            self._reset_mxl_receivers()

    def test_04(self, test):
        """
        Ensure NCuT does not provide a transport_file when staging an MXL Receiver connection
        """
        try:
            mxl_senders = self._select_test_mxl_senders()

            if not mxl_senders:
                return test.FAIL('No registered MXL Senders available for connection test')

            tested_connection = False

            for sender in mxl_senders:
                self.node.clear_staged_requests()
                self._reset_mxl_receivers()

                compatible_receivers = [
                    receiver for receiver in self._registered_connectable_mxl_receivers()
                    if self._is_compatible(sender, receiver)
                ]
                if not compatible_receivers:
                    continue

                receiver = NMOSUtils.RANDOM.choice(compatible_receivers)
                tested_connection = True

                question = textwrap.dedent(f"""\
                           When connecting an MXL Receiver using the IS-05 Connection API, the NCuT MUST NOT \
                           provide a transport file in the PATCH request to the Receiver /staged endpoint.

                           Use the NCuT to perform an 'immediate' activation between sender:

                           {sender['display_answer']}

                           and receiver:

                           {receiver['display_answer']}

                           Click the 'Next' button once the connection is active.
                           """)

                metadata = {
                    'sender': {
                        'id': sender['id'],
                        'label': sender['label'],
                        'description': sender['description'],
                    },
                    'receiver': {
                        'id': receiver['id'],
                        'label': receiver['label'],
                        'description': receiver['description'],
                    },
                }

                self.testing_facade_utils.invoke_testing_facade(
                    question, [], test_type='action', metadata=metadata)

                patch_requests = [
                    request for request in self.node.staged_requests
                    if request['method'] == 'PATCH' and request['resource'] == 'receivers'
                ]
                if len(patch_requests) < 1:
                    return test.FAIL('No PATCH request was received by the node')

                for patch_request in patch_requests:
                    if not self._transport_file_acceptable(patch_request['data']):
                        return test.FAIL(
                            'transport_file attribute was provided with non-null data or type in PATCH request')

                deactivate_json = {
                    'master_enable': False,
                    'sender_id': None,
                    'activation': {'mode': 'activate_immediate'},
                }
                self.node.patch_staged('receivers', receiver['id'], deactivate_json)

            if not tested_connection:
                return test.FAIL('No compatible MXL Sender and Receiver pairs available for connection test')

            return test.PASS('transport_file attribute not provided in PATCH requests')

        except TestingFacadeException as exception:
            return test.UNCLEAR(exception.args[0])
        finally:
            self._reset_mxl_receivers()

    def test_05(self, test):
        """
        Ensure NCuT can evaluate MXL Flow compatibility using BCP-004-01 Receiver Capabilities
        """
        MAX_COMPATIBLE_RECEIVER_COUNT = 4
        CANDIDATE_RECEIVER_COUNT = 6

        try:
            mxl_senders = self._select_test_mxl_senders()

            if not mxl_senders:
                return test.FAIL('No registered MXL Senders available for compatibility test')

            tested_compatibility = False

            for iteration, sender in enumerate(mxl_senders):
                compatible_receivers = [
                    receiver for receiver in self._registered_connectable_mxl_receivers()
                    if self._is_compatible(sender, receiver)
                ]
                if not compatible_receivers:
                    continue

                tested_compatibility = True

                question = textwrap.dedent(f"""\
                           The NCuT should be able to evaluate MXL Flow compatibility between MXL Senders and \
                           MXL Receivers using the BCP-004-01 Receiver Capabilities mechanism.

                           Refresh the NCuT's view of the Registry and carefully select the Receivers \
                           that are compatible with the following MXL Sender:

                           {sender['display_answer']}

                           Once compatible Receivers have been identified press 'Submit'. If unable \
                           to identify compatible Receivers, press 'Submit' without making a selection.
                           """)

                other_receivers = [
                    receiver for receiver in self._registered_connectable_mxl_receivers()
                    if not self._is_compatible(sender, receiver)
                ]

                compatible_receiver_count = NMOSUtils.RANDOM.randint(
                    1, min(MAX_COMPATIBLE_RECEIVER_COUNT, len(compatible_receivers)))
                candidate_receivers = NMOSUtils.RANDOM.sample(compatible_receivers, compatible_receiver_count)

                if len(candidate_receivers) < CANDIDATE_RECEIVER_COUNT:
                    incompatible_receiver_count = min(
                        CANDIDATE_RECEIVER_COUNT - len(candidate_receivers), len(other_receivers))
                    candidate_receivers.extend(
                        NMOSUtils.RANDOM.sample(other_receivers, incompatible_receiver_count))

                candidate_receivers.sort(key=itemgetter('label'))

                possible_answers = [
                    {
                        'answer_id': 'answer_' + str(index),
                        'display_answer': receiver['display_answer'],
                        'resource': {
                            'id': receiver['id'],
                            'label': receiver['label'],
                            'description': receiver['description'],
                        },
                    }
                    for index, receiver in enumerate(candidate_receivers)
                ]
                expected_answers = [
                    'answer_' + str(index) for index, receiver in enumerate(candidate_receivers)
                    if self._is_compatible(sender, receiver)
                ]

                actual_answers = self.testing_facade_utils.invoke_testing_facade(
                    question, possible_answers, test_type='multi_choice',
                    multipart_test=iteration)['answer_response']

                actual = set(actual_answers)
                expected = set(expected_answers)

                if expected - actual:
                    return test.FAIL(
                        'Not all compatible Receivers identified for Sender {}'.format(sender['display_answer']))
                if actual - expected:
                    return test.FAIL(
                        'Receivers incorrectly identified as compatible for Sender {}'
                        .format(sender['display_answer']))

            if not tested_compatibility:
                return test.FAIL('No compatible MXL Sender and Receiver pairs available for compatibility test')

            return test.PASS('All compatible Receivers correctly identified')

        except TestingFacadeException as exception:
            return test.UNCLEAR(exception.args[0])
