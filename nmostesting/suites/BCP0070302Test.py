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
from ..NMOSUtils import NMOSUtils

MXL_ENDPOINT_COUNT = 4
MXL_PROFILE_COUNT_PER_TYPE = 2
TEST_EXAMPLE_COUNT = 3

MXL_RECEIVER_DEACTIVATE_JSON = {
    'master_enable': False,
    'sender_id': None,
    'activation': {'mode': 'activate_immediate'},
}


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

    def _apply_flow_profile_to_sender(self, sender, profile):
        sender['profile_id'] = profile['profile_id']
        sender['flow_params'] = {key: value for key, value in profile.items() if key != 'profile_id'}

    def _apply_caps_profile_to_receiver(self, receiver, profile):
        receiver['caps'] = self._generate_caps([profile])

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

    def _assign_mxl_transport_and_profiles(self, endpoints, apply_profile):
        mxl_indices = NMOSUtils.RANDOM.sample(range(len(endpoints)), MXL_ENDPOINT_COUNT)
        profiles = (
            [MXL_FLOW_PROFILE_1080P25] * MXL_PROFILE_COUNT_PER_TYPE +
            [MXL_FLOW_PROFILE_720P50] * MXL_PROFILE_COUNT_PER_TYPE
        )
        NMOSUtils.RANDOM.shuffle(profiles)

        for endpoint_index, profile in zip(mxl_indices, profiles):
            endpoints[endpoint_index]['transport'] = MXL_TRANSPORT
            apply_profile(endpoints[endpoint_index], profile)

    def _select_test_mxl_senders(self):
        connectable_mxl_receivers = self._registered_connectable_mxl_receivers()
        testable_senders = [
            sender for sender in self.senders
            if sender['registered'] and self._sender_uses_mxl_transport(sender)
            and any(self._is_compatible(sender, receiver) for receiver in connectable_mxl_receivers)
        ]

        example_count = min(CONFIG.MAX_TEST_ITERATIONS or TEST_EXAMPLE_COUNT, len(testable_senders))
        if example_count == 0:
            return []

        return NMOSUtils.RANDOM.sample(testable_senders, example_count)

    def _resource_facade_metadata(self, resource):
        return {
            'id': resource['id'],
            'label': resource['label'],
            'description': resource['description'],
        }

    def _build_possible_answers(self, candidates):
        return [
            {
                'answer_id': 'answer_' + str(index),
                'display_answer': candidate['display_answer'],
                'resource': self._resource_facade_metadata(candidate),
            }
            for index, candidate in enumerate(candidates)
        ]

    def _multi_choice_mismatch(self, test, actual_answers, expected_answers,
                               missing_fail_message, extra_fail_message):
        actual = set(actual_answers)
        expected = set(expected_answers)
        if expected - actual:
            return test.FAIL(missing_fail_message)
        if actual - expected:
            return test.FAIL(extra_fail_message)

    def _select_candidate_resources(self, primary_resources, other_resources,
                                    max_primary_count, candidate_count):
        primary_sample_count = NMOSUtils.RANDOM.randint(1, min(max_primary_count, len(primary_resources)))
        candidates = NMOSUtils.RANDOM.sample(primary_resources, primary_sample_count)

        if len(candidates) < candidate_count:
            other_sample_count = min(candidate_count - len(candidates), len(other_resources))
            candidates.extend(NMOSUtils.RANDOM.sample(other_resources, other_sample_count))

        candidates.sort(key=itemgetter('label'))
        return candidates

    def _run_mxl_discovery_test(self, test, question, resources, is_mxl, is_non_mxl,
                                max_mxl_count, candidate_count,
                                missing_fail_message, extra_fail_message, pass_message):
        mxl_resources = [resource for resource in resources if is_mxl(resource)]
        non_mxl_resources = [resource for resource in resources if is_non_mxl(resource)]
        candidates = self._select_candidate_resources(
            mxl_resources, non_mxl_resources, max_mxl_count, candidate_count)

        possible_answers = self._build_possible_answers(candidates)
        expected_answers = [
            'answer_' + str(index) for index, resource in enumerate(candidates) if is_mxl(resource)
        ]

        actual_answers = self.testing_facade_utils.invoke_testing_facade(
            question, possible_answers, test_type='multi_choice',
            test_method_name=test.name)['answer_response']

        mismatch = self._multi_choice_mismatch(
            test, actual_answers, expected_answers, missing_fail_message, extra_fail_message)
        if mismatch:
            return mismatch

        return test.PASS(pass_message)

    def _compatible_receivers_for_sender(self, sender):
        return [
            receiver for receiver in self._registered_connectable_mxl_receivers()
            if self._is_compatible(sender, receiver)
        ]

    def _deactivate_mxl_receiver(self, receiver):
        self.node.patch_staged('receivers', receiver['id'], MXL_RECEIVER_DEACTIVATE_JSON)

    def set_up_tests(self):
        NMOSUtils.RANDOM.seed(a=CONFIG.RANDOM_SEED)

        self.senders = [
            {'label': 's1/connery', 'description': 'Mock sender 1', 'registered': True},
            {'label': 's2/niven', 'description': 'Mock sender 2', 'registered': True},
            {'label': 's3/lazenby', 'description': 'Mock sender 3', 'registered': True},
            {'label': 's4/moore', 'description': 'Mock sender 4', 'registered': True},
            {'label': 's5/dalton', 'description': 'Mock sender 5', 'registered': True},
            {'label': 's6/brosnan', 'description': 'Mock sender 6', 'registered': True},
            {'label': 's7/craig', 'description': 'Mock sender 7', 'registered': True},
        ]
        self._assign_mxl_transport_and_profiles(self.senders, self._apply_flow_profile_to_sender)

        self.receivers = [
            {'label': 'r1/dr_no', 'description': 'Mock receiver 1',
             'connectable': True, 'registered': True},
            {'label': 'r2/blofeld', 'description': 'Mock receiver 2',
             'connectable': True, 'registered': True},
            {'label': 'r3/goldfinger', 'description': 'Mock receiver 3',
             'connectable': True, 'registered': True},
            {'label': 'r4/scaramanga', 'description': 'Mock receiver 4',
             'connectable': True, 'registered': True},
            {'label': 'r5/le_chiffre', 'description': 'Mock receiver 5',
             'connectable': True, 'registered': True},
            {'label': 'r6/silva', 'description': 'Mock receiver 6',
             'connectable': True, 'registered': True},
            {'label': 'r7/oberhauser', 'description': 'Mock receiver 7',
             'connectable': True, 'registered': True},
        ]
        self._assign_mxl_transport_and_profiles(self.receivers, self._apply_caps_profile_to_receiver)

        ControllerTest.set_up_tests(self)

    def _reset_mxl_receivers(self):
        for receiver in self._registered_connectable_mxl_receivers():
            self._deactivate_mxl_receiver(receiver)

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

            return self._run_mxl_discovery_test(
                test, question, self.senders,
                self._sender_uses_mxl_transport, self._sender_uses_rtp_transport,
                MAX_COMPATIBLE_SENDER_COUNT, CANDIDATE_SENDER_COUNT,
                'Not all MXL Senders identified',
                'Senders incorrectly identified as MXL',
                'All MXL Senders correctly identified')

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

            return self._run_mxl_discovery_test(
                test, question, self.receivers,
                self._receiver_uses_mxl_transport, self._receiver_uses_rtp_transport,
                MAX_COMPATIBLE_RECEIVER_COUNT, CANDIDATE_RECEIVER_COUNT,
                'Not all MXL Receivers identified',
                'Receivers incorrectly identified as MXL',
                'All MXL Receivers correctly identified')

        except TestingFacadeException as exception:
            return test.UNCLEAR(exception.args[0])

    def test_03(self, test):
        """
        Connect an MXL Receiver to an MXL Sender via the IS-05 Connection API and ensure
        the NCuT does not provide a transport_file when staging the connection
        """
        try:
            mxl_senders = self._select_test_mxl_senders()

            if not mxl_senders:
                return test.FAIL('No registered MXL Senders available for connection test')

            tested_connection = False

            for sender in mxl_senders:
                self.node.clear_staged_requests()
                self._reset_mxl_receivers()

                compatible_receivers = self._compatible_receivers_for_sender(sender)
                if not compatible_receivers:
                    continue

                receiver = NMOSUtils.RANDOM.choice(compatible_receivers)
                tested_connection = True

                question = textwrap.dedent(f"""\
                           It should be possible to connect available MXL Senders to compatible MXL Receivers \
                           using the IS-05 Connection API. When staging the connection, the NCuT MUST NOT \
                           provide a transport file in the PATCH request to the Receiver /staged endpoint.

                           Use the NCuT to perform an 'immediate' activation between sender:

                           {sender['display_answer']}

                           and receiver:

                           {receiver['display_answer']}

                           Click the 'Next' button once the connection is active.
                           """)

                metadata = {
                    'sender': self._resource_facade_metadata(sender),
                    'receiver': self._resource_facade_metadata(receiver),
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

                if not self._transport_file_acceptable(patch_data):
                    return test.FAIL(
                        'transport_file attribute was provided with non-null data or type in PATCH request')

                self._deactivate_mxl_receiver(receiver)

            if not tested_connection:
                return test.FAIL('No compatible MXL Sender and Receiver pairs available for connection test')

            return test.PASS('Connections successfully established without transport_file in PATCH requests')

        except TestingFacadeException as exception:
            return test.UNCLEAR(exception.args[0])
        finally:
            self._reset_mxl_receivers()

    def test_04(self, test):
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
                compatible_receivers = self._compatible_receivers_for_sender(sender)
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

                connectable_mxl_receivers = self._registered_connectable_mxl_receivers()
                other_receivers = [
                    receiver for receiver in connectable_mxl_receivers
                    if receiver not in compatible_receivers
                ]
                candidate_receivers = self._select_candidate_resources(
                    compatible_receivers, other_receivers,
                    MAX_COMPATIBLE_RECEIVER_COUNT, CANDIDATE_RECEIVER_COUNT)

                possible_answers = self._build_possible_answers(candidate_receivers)
                expected_answers = [
                    'answer_' + str(index) for index, receiver in enumerate(candidate_receivers)
                    if self._is_compatible(sender, receiver)
                ]

                metadata = {
                    'sender': self._resource_facade_metadata(sender),
                }

                actual_answers = self.testing_facade_utils.invoke_testing_facade(
                    question, possible_answers, test_type='multi_choice',
                    multipart_test=iteration, metadata=metadata)['answer_response']

                mismatch = self._multi_choice_mismatch(
                    test, actual_answers, expected_answers,
                    'Not all compatible Receivers identified for Sender {}'.format(sender['display_answer']),
                    'Receivers incorrectly identified as compatible for Sender {}'
                    .format(sender['display_answer']))
                if mismatch:
                    return mismatch

            if not tested_compatibility:
                return test.FAIL('No compatible MXL Sender and Receiver pairs available for compatibility test')

            return test.PASS('All compatible Receivers correctly identified')

        except TestingFacadeException as exception:
            return test.UNCLEAR(exception.args[0])
