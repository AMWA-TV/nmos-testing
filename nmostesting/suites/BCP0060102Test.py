# Copyright (C) 2022 Advanced Media Workflow Association
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

import random
import textwrap
from copy import deepcopy
from operator import itemgetter
from .. import Config as CONFIG
from ..ControllerTest import ControllerTest, TestingFacadeException
from ..NMOSUtils import NMOSUtils


class BCP0060102Test(ControllerTest):
    """
    Runs Controller Tests covering BCP-006-01
    """
    def __init__(self, apis, registries, node, dns_server):
        ControllerTest.__init__(self, apis, registries, node, dns_server)

    def _create_interop_point(self, sdp_base, override_params):
        interop_point = deepcopy(sdp_base)

        for param, value in override_params:
            interop_point[param] = value

        return interop_point

    def _initialize_capability_set_A_level_FHD(self):

        interoperability_points = []  # 10 interoperability point defined here

        # Interoperability Points Capability Set A, Conformance Level FHD with reference to VSF TR-08:2022
        ip1_6c_base = {'media_type': 'jxsv', 'video_width': 1920, 'video_height': 1080, 'video_interlace': False,
                       'video_exactframerate': '60000/1001', 'bit_rate': 109000, 'video_depth': '10',
                       'video_sampling': 'YCbCr-4:2:2', 'video_colorimetry': 'BT709', 'profile': 'High444.12',
                       'level': '2k-1', 'sublevel': 'Sublev3bpp', 'video_transfer_characteristic': 'SDR',
                       'st2110_21_sender_type': '2110TPN', 'packet_transmission_mode': 'codestream',
                       'capability_set': 'A', 'conformance_level': 'FHD'}

        interop_point_1 = self._create_interop_point(ip1_6c_base, [('video_width', 1280), ('video_height', 720),
                                                                   ('min_bit_rate', 83000), ('max_bit_rate', 221000),
                                                                   ('interop_point', '1')])

        interoperability_points.append(interop_point_1)

        interop_point_2 = self._create_interop_point(ip1_6c_base, [('video_width', 1280), ('video_height', 720),
                                                                   ('video_exactframerate', '50'),
                                                                   ('min_bit_rate', 69000), ('max_bit_rate', 184000),
                                                                   ('interop_point', '2')])
        interoperability_points.append(interop_point_2)

        interop_point_3 = self._create_interop_point(ip1_6c_base, [('video_exactframerate', '30000/1001'),
                                                                   ('video_interlace', True),
                                                                   ('min_bit_rate', 93000), ('max_bit_rate', 249000),
                                                                   ('interop_point', '3')])
        interoperability_points.append(interop_point_3)

        interop_point_4 = self._create_interop_point(ip1_6c_base, [('video_exactframerate', '25'),
                                                                   ('video_interlace', True),
                                                                   ('min_bit_rate', 78000), ('max_bit_rate', 207000),
                                                                   ('interop_point', '4')])
        interoperability_points.append(interop_point_4)

        interop_point_5a = self._create_interop_point(ip1_6c_base, [('bit_rate', 250000), ('min_bit_rate', 186000),
                                                                    ('max_bit_rate', 497000),
                                                                    ('interop_point', '5a')])
        interoperability_points.append(interop_point_5a)

        interop_point_5b = self._create_interop_point(ip1_6c_base, [('bit_rate', 250000), ('min_bit_rate', 186000),
                                                                    ('max_bit_rate', 497000),
                                                                    ('video_colorimetry', 'BT2100'),
                                                                    ('video_transfer_characteristic', 'PQ'),
                                                                    ('interop_point', '5b')])
        interoperability_points.append(interop_point_5b)

        interop_point_5c = self._create_interop_point(ip1_6c_base, [('bit_rate', 250000), ('min_bit_rate', 186000),
                                                                    ('max_bit_rate', 497000),
                                                                    ('video_colorimetry', 'BT2100'),
                                                                    ('video_transfer_characteristic', 'HLG'),
                                                                    ('interop_point', '5c')])
        interoperability_points.append(interop_point_5c)

        interop_point_6a = self._create_interop_point(ip1_6c_base, [('video_exactframerate', '50'),
                                                                    ('bit_rate', 250000),
                                                                    ('min_bit_rate', 156000), ('max_bit_rate', 415000),
                                                                    ('interop_point', '6a')])
        interoperability_points.append(interop_point_6a)

        interop_point_6b = self._create_interop_point(ip1_6c_base, [('bit_rate', 250000),
                                                                    ('min_bit_rate', 156000), ('max_bit_rate', 415000),
                                                                    ('video_exactframerate', '50'),
                                                                    ('video_colorimetry', 'BT2100'),
                                                                    ('video_transfer_characteristic', 'PQ'),
                                                                    ('interop_point', '6b')])
        interoperability_points.append(interop_point_6b)

        interop_point_6c = self._create_interop_point(ip1_6c_base, [('bit_rate', 250000), ('min_bit_rate', 156000),
                                                                    ('max_bit_rate', 415000),
                                                                    ('video_exactframerate', '50'),
                                                                    ('video_colorimetry', 'BT2100'),
                                                                    ('video_transfer_characteristic', 'HLG'),
                                                                    ('interop_point', '6c')])
        interoperability_points.append(interop_point_6c)

        return interoperability_points

    def _initialize_capability_set_A_level_UHD1(self):

        interoperability_points = []  # 16 interoperability point defined here

        # Interoperability Points Capability Set A, Conformance Level UHD1 with reference to VSF TR-08:2022
        ip7a_8c_base = {'media_type': 'jxsv', 'video_width': 3840, 'video_height': 2160, 'video_interlace': False,
                        'video_exactframerate': '60000/1001', 'bit_rate': 100000, 'video_depth': '10',
                        'video_sampling': 'YCbCr-4:2:2', 'video_colorimetry': 'BT2100', 'profile': 'High444.12',
                        'level': '4k-2', 'sublevel': 'Sublev3bpp', 'video_transfer_characteristic': 'SDR',
                        'min_bit_rate': 746000, 'max_bit_rate': 1989000,
                        'st2110_21_sender_type': '2110TPN', 'packet_transmission_mode': 'codestream',
                        'capability_set': 'A', 'conformance_level': 'UHD1'}

        interop_point_7a = self._create_interop_point(ip7a_8c_base, [('video_colorimetry', 'BT2020'),
                                                                     ('interop_point', '7a')])

        interoperability_points.append(interop_point_7a)

        interop_point_7b = self._create_interop_point(ip7a_8c_base, [('video_transfer_characteristic', 'PQ'),
                                                                     ('interop_point', '7b')])
        interoperability_points.append(interop_point_7b)

        interop_point_7c = self._create_interop_point(ip7a_8c_base, [('video_transfer_characteristic', 'HLG'),
                                                                     ('interop_point', '7c')])
        interoperability_points.append(interop_point_7c)

        interop_point_8a = self._create_interop_point(ip7a_8c_base, [('min_bit_rate', 622000),
                                                                     ('max_bit_rate', 1659000),
                                                                     ('video_exactframerate', '50'),
                                                                     ('video_colorimetry', 'BT2020'),
                                                                     ('interop_point', '8a')])

        interoperability_points.append(interop_point_8a)

        interop_point_8b = self._create_interop_point(ip7a_8c_base, [('min_bit_rate', 622000),
                                                                     ('max_bit_rate', 1659000),
                                                                     ('video_exactframerate', '50'),
                                                                     ('video_transfer_characteristic', 'PQ'),
                                                                     ('interop_point', '8b')])
        interoperability_points.append(interop_point_8b)

        interop_point_8c = self._create_interop_point(ip7a_8c_base, [('min_bit_rate', 622000),
                                                                     ('max_bit_rate', 1659000),
                                                                     ('video_exactframerate', '50'),
                                                                     ('video_transfer_characteristic', 'HLG'),
                                                                     ('interop_point', '8c')])
        interoperability_points.append(interop_point_8c)

        return interoperability_points

    def _generate_non_JXSV_interop_points(self, size):
        # Non JPEG XS Interoperability Points
        non_jxsv_base = {'media_type': 'raw', 'capability_set': None, 'conformance_level': None}

        interoperability_points = []

        for i in range(0, size):
            interop_point = deepcopy(non_jxsv_base)
            interop_point['interop_point'] = 'NonJXSV' + str(i)
            interoperability_points.append(interop_point)

        return interoperability_points

    def _generate_constraint_set(self, sdp_params):
        split_exactframerate = sdp_params.get("video_exactframerate",
                                              CONFIG.SDP_PREFERENCES["video_exactframerate"]).split('/')

        constraint_set = {
            "urn:x-nmos:cap:format:color_sampling": {
                "enum": [sdp_params.get("video_sampling", CONFIG.SDP_PREFERENCES["video_sampling"])]
            },
            "urn:x-nmos:cap:format:frame_height": {
                "enum": [sdp_params.get("video_height", CONFIG.SDP_PREFERENCES["video_height"])]
            },
            "urn:x-nmos:cap:format:frame_width": {
                "enum": [sdp_params.get("video_width", CONFIG.SDP_PREFERENCES["video_width"])]
            },
            "urn:x-nmos:cap:format:grain_rate": {
                "enum": [{
                            "denominator": int(split_exactframerate[1]) if 1 < len(split_exactframerate) else 1,
                            "numerator": int(split_exactframerate[0])
                        }]
            },
            "urn:x-nmos:cap:format:interlace_mode": {
                "enum": [
                    "interlaced_bff",
                    "interlaced_tff",
                    "interlaced_psf"
                ] if sdp_params.get("video_interlace", CONFIG.SDP_PREFERENCES["video_interlace"]) else [
                    "progressive"
                ]
            },
            "urn:x-nmos:cap:format:component_depth": {
                "enum": [sdp_params.get("video_depth", CONFIG.SDP_PREFERENCES["video_depth"])]
            },
            "urn:x-nmos:cap:format:colorspace": {
                "enum": [sdp_params.get("video_colorimetry", CONFIG.SDP_PREFERENCES["video_colorimetry"])]
            },
            "urn:x-nmos:cap:format:transfer_characteristic": {
                "enum": [sdp_params.get("video_transfer_characteristic",
                                        CONFIG.SDP_PREFERENCES["video_transfer_characteristic"])]
            }
        }

        # JPEG XS specific caps
        if "profile" in sdp_params and "level" in sdp_params:
            constraint_set.update({"urn:x-nmos:cap:format:profile": {"enum": [sdp_params.get("profile")]},
                                   "urn:x-nmos:cap:format:level": {"enum": [sdp_params.get("level")]},
                                   "urn:x-nmos:cap:format:sublevel": {"enum": ["Sublev3bpp", "Sublev4bpp"]},
                                   "urn:x-nmos:cap:transport:packet_transmission_mode": {"enum": ["codestream"]},
                                   "urn:x-nmos:cap:format:bit_rate": {"minimum": sdp_params.get("min_bit_rate"),
                                                                      "maximum": sdp_params.get("max_bit_rate")}})
        return constraint_set

    # convert sdp_params into Receiver caps
    def _generate_caps(self, sdp_params_set):

        caps = {
            "media_types": [],
            "constraint_sets": [],
            "version": NMOSUtils.get_TAI_time()
        }

        for sdp_params in sdp_params_set:
            media_type = 'video/' + sdp_params.get("media_type", "raw")
            if media_type not in caps["media_types"]:
                caps["media_types"].append(media_type)

            caps["constraint_sets"].append(self._generate_constraint_set(sdp_params))

        return caps

    # convert sdp_params into Flow parameters
    def _generate_flow_params(self, sdp_params):
        flow_params = {}

        # Mapping sdp_param names to flow_param names
        param_mapping = [('media_type', 'media_type'), ('video_width', 'frame_width'), ('video_height', 'frame_height'),
                         ('profile', 'profile'), ('level', 'level'), ('sublevel', 'sublevel'),
                         ('video_colorimetry', 'colorspace'), ('bitrate', 'bitrate'),
                         ('video_transfer_characteristic', 'transfer_characteristic')]

        for sdp_param, flow_param in param_mapping:
            if sdp_param in sdp_params:
                flow_params[flow_param] = sdp_params[sdp_param]

        flow_params["interlace_mode"] = "progressive" \
            if sdp_params.get("video_interlace") else "interlaced_tff"

        if "video_exactframerate" in sdp_params:
            split_exactframerate = sdp_params["video_exactframerate"].split('/')
            flow_params["grain_rate"] = {
                "denominator": int(split_exactframerate[1]) if 1 < len(split_exactframerate) else 1,
                "numerator": int(split_exactframerate[0])
            }
        if "video_sampling" in sdp_params:
            if sdp_params["video_sampling"] == "YCbCr-4:2:2":
                flow_params["components"] = [
                    {"name": "Y",  "width": sdp_params["video_width"], "height": sdp_params["video_height"],
                        "bit_depth": sdp_params.get("video_depth")},
                    {"name": "Cb", "width": int(sdp_params["video_width"])//2, "height": sdp_params["video_height"],
                        "bit_depth": sdp_params.get("video_depth")},
                    {"name": "Cr", "width": int(sdp_params["video_width"])//2, "height": sdp_params["video_height"],
                        "bit_depth": sdp_params.get("video_depth")}
                ]

        return flow_params

    def set_up_tests(self):

        sender_names = ['rush', 'fly_by_night', 'caress_of_steel', '_2112_',
                        'farewell_to_kings', 'hemispheres', 'permanent_waves', 'moving_pictures',
                        'signals', 'grace_under_pressure', 'power_windows', 'hold_your_fire',
                        'presto', 'roll_the_bones', 'counterparts', 'test_for_echo',
                        'vapor_trails', 'feedback', 'snakes_and_ladders', 'clockwork_angels']

        receiver_names = ['tubular_bells', 'hergest_ridge', 'ommadawn', 'incantations', 'platinum',
                          'qe2', 'five_miles_out', 'crises', 'discovery', 'islands',
                          'earth_moving', 'amarok', 'heavens_open', 'tb2', 'songs_of_distant_earth',
                          'yoyager', 'tb3', 'guitars', 'millenium_bell', 'tres_luna',
                          'tb2003', 'light_shade', 'music_of_the_spheres', 'man_on_the_rocks',
                          'return_to_ommadawn',
                          'piper_at_the_gates', 'saucerful_of_secrets', 'more', 'ummagumma', 'atom_heart_mother',
                          'meddle', 'obscured_by_clouds', 'dark_side', 'wish_you_were_here', 'animals',
                          'the_wall', 'final_cut', 'momentary_lapse', 'division_bell', 'endless_river']

        interoperability_points = self._initialize_capability_set_A_level_FHD()
        interoperability_points.extend(self._initialize_capability_set_A_level_UHD1())

        # create a map of the interop points so they can be assigned to Senders
        capability_set_map = {interop_point['interop_point']: interop_point
                              for interop_point in interoperability_points}

        # create sub list of representative interoperability points, key is TR-08 Interoperability Point
        sender_interop_points = [capability_set_map['1'],
                                 capability_set_map['5b'],
                                 capability_set_map['6c'],
                                 capability_set_map['7a'],
                                 capability_set_map['8b']]

        # pad with video raw Senders
        VIDEO_RAW_SENDER_COUNT = 3
        sender_interop_points.extend(self._generate_non_JXSV_interop_points(VIDEO_RAW_SENDER_COUNT))

        self.senders.clear()

        random.shuffle(sender_names)
        random.shuffle(sender_interop_points)
        for idx, (sender_name, interop_point) in enumerate(zip(sender_names, sender_interop_points)):

            sender = {
                'label': 's' + str(idx) + '/' + sender_name,
                'description': 'Mock Sender ' + str(idx),
                'registered': True,
                'sdp_params': interop_point if interop_point else {},
                'flow_params': self._generate_flow_params(interop_point) if interop_point else {},
                'capability_set': interop_point.get('capability_set'),
                'conformance_level': interop_point.get('conformance_level')
            }
            self.senders.append(sender)

        # pad configurations with some video/raw (None, None) configurations
        capability_configurations = [('A', 'FHD'), ('A', 'UHD1'), (None, None), (None, None), (None, None)]

        self.receivers.clear()

        random.shuffle(receiver_names)
        random.shuffle(capability_configurations)
        for idx, (receiver_name, (capability_set, conformance_level)) in \
                enumerate(zip(receiver_names, capability_configurations)):
            # choose a random interop point
            caps = [i for i in interoperability_points
                    if i["capability_set"] == capability_set and i["conformance_level"] == conformance_level]

            receiver = {
                'label': 'r' + str(idx) + '/' + receiver_name,
                'description': 'Mock Receiver ' + str(idx),
                'connectable': True,
                'registered': True,
                'caps': self._generate_caps(caps) if caps else {"media_types": ['video/raw']},
                'capability_set': capability_set,
                'conformance_level': conformance_level
            }
            self.receivers.append(receiver)

        ControllerTest.set_up_tests(self)

    def test_01(self, test):
        """
        Ensure NCuT can identify JPEG XS Senders
        """

        CANDIDATE_SENDER_COUNT = 4

        try:
            # Question 1 connection
            question = """\
                       The NCuT should be able to discover JPEG XS capable Senders \
                       that are registered in the Registry.

                       Refresh the NCuT's view of the Registry and carefully select the Senders \
                       that are JPEG XS capable from the following list.
                       """

            jpeg_xs_senders = [r for r in self.senders if 'jxsv' == r['sdp_params']['media_type']]
            video_raw_senders = [r for r in self.senders if 'raw' == r['sdp_params']['media_type']]

            candidate_senders = random.sample(jpeg_xs_senders,
                                              random.randint(1, min(CANDIDATE_SENDER_COUNT, len(jpeg_xs_senders))))
            if len(candidate_senders) < CANDIDATE_SENDER_COUNT:
                candidate_senders.extend(random.sample(video_raw_senders,
                                                       min(CANDIDATE_SENDER_COUNT - len(candidate_senders),
                                                           len(video_raw_senders))))

            candidate_senders.sort(key=itemgetter("label"))

            possible_answers = [{'answer_id': 'answer_'+str(i), 'display_answer': r['display_answer'],
                                'resource': {'id': r['id'], 'label': r['label'], 'description': r['description']}}
                                for i, r in enumerate(candidate_senders)]
            expected_answers = ['answer_'+str(i) for i, r in enumerate(candidate_senders)
                                if 'jxsv' == r['sdp_params']['media_type']]

            actual_answers = self._invoke_testing_facade(
                question, possible_answers, test_type="multi_choice")['answer_response']

            if len(actual_answers) != len(expected_answers):
                return test.FAIL('Incorrect Sender identified')
            else:
                for answer in actual_answers:
                    if answer not in expected_answers:
                        return test.FAIL('Incorrect Sender identified')

            return test.PASS('All Senders correctly identified')

        except TestingFacadeException as e:
            return test.UNCLEAR(e.args[0])

    def test_02(self, test):
        """
        Ensure NCuT can identify JPEG XS Receivers
        """

        CANDIDATE_RECEIVER_COUNT = 4

        try:
            # Question 1 connection
            question = """\
                       The NCuT should be able to discover JPEG XS capable Receivers \
                       that are registered in the Registry.

                       Refresh the NCuT's view of the Registry and carefully select the Receivers \
                       that are JPEG XS capable from the following list.
                       """

            jpeg_xs_receivers = [r for r in self.receivers if 'video/jxsv' in r['caps']['media_types']]
            video_raw_receivers = [r for r in self.receivers if 'video/raw' in r['caps']['media_types']]

            candidate_receivers = random.sample(jpeg_xs_receivers,
                                                random.randint(1, min(CANDIDATE_RECEIVER_COUNT,
                                                                      len(jpeg_xs_receivers))))
            if len(candidate_receivers) < CANDIDATE_RECEIVER_COUNT:
                candidate_receivers.extend(random.sample(video_raw_receivers,
                                                         min(CANDIDATE_RECEIVER_COUNT - len(candidate_receivers),
                                                             len(video_raw_receivers))))

            candidate_receivers.sort(key=itemgetter("label"))

            possible_answers = [{'answer_id': 'answer_'+str(i), 'display_answer': r['display_answer'],
                                'resource': {'id': r['id'], 'label': r['label'], 'description': r['description']}}
                                for i, r in enumerate(candidate_receivers)]
            expected_answers = ['answer_'+str(i) for i, r in enumerate(candidate_receivers)
                                if 'video/jxsv' in r['caps']['media_types']]

            actual_answers = self._invoke_testing_facade(
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

    def test_05(self, test):
        """
        Ensure NCuT can identify JPEG XS Receivers compatible with Capability Set A, Conformance Level FHD Sender
        """

        MAX_COMPATIBLE_RECEIVER_COUNT = 4
        CANDIDATE_RECEIVER_COUNT = 8

        try:
            # Select Capability Set A, Conformance Level FHD Sender
            set_A_level_FHD_senders = [s for s in self.senders
                                       if s['capability_set'] == 'A' and s['conformance_level'] == 'FHD']

            sender = random.choice(set_A_level_FHD_senders)

            # Question 1 connection
            question = textwrap.dedent(f"""\
                       The NCuT should be able to discover JPEG XS capable Receivers \
                       that are compatible with Capability Set A, Conformance Level FHD Senders.

                       Refresh the NCuT's view of the Registry and carefully select the Receivers \
                       that are compatible with the following Sender:

                       {sender['display_answer']}
                       """)

            set_A_level_FHD_receivers = [r for r in self.receivers
                                         if r['capability_set'] == 'A' and r['conformance_level'] == 'FHD']
            other_receivers = [r for r in self.receivers
                               if r['capability_set'] != 'A' or r['conformance_level'] != 'FHD']

            candidate_receivers = random.sample(set_A_level_FHD_receivers,
                                                random.randint(1, min(MAX_COMPATIBLE_RECEIVER_COUNT,
                                                                      len(set_A_level_FHD_receivers))))
            if len(candidate_receivers) < CANDIDATE_RECEIVER_COUNT:
                candidate_receivers.extend(random.sample(other_receivers,
                                                         min(CANDIDATE_RECEIVER_COUNT - len(candidate_receivers),
                                                             len(other_receivers))))

            candidate_receivers.sort(key=itemgetter("label"))

            possible_answers = [{'answer_id': 'answer_'+str(i), 'display_answer': r['display_answer'],
                                'resource': {'id': r['id'], 'label': r['label'], 'description': r['description']}}
                                for i, r in enumerate(candidate_receivers)]
            expected_answers = ['answer_'+str(i) for i, r in enumerate(candidate_receivers)
                                if r['capability_set'] == 'A' or r['conformance_level'] == 'FHD']

            actual_answers = self._invoke_testing_facade(
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

    def test_06(self, test):
        """
        Ensure NCuT can identify JPEG XS Senders compatible with Capability Set A, Conformance Level FHD receiver
        """

        MAX_COMPATIBLE_SENDER_COUNT = 3
        CANDIDATE_SENDER_COUNT = 6

        try:
            # Select Capability Set A, Conformance Level FHD Sender
            set_A_level_FHD_receivers = [r for r in self.receivers
                                         if r['capability_set'] == 'A' and r['conformance_level'] == 'FHD']

            receiver = random.choice(set_A_level_FHD_receivers)

            # Question 1 connection
            question = textwrap.dedent(f"""\
                       The NCuT should be able to discover JPEG XS capable Senders \
                       that are compatible with Capability Set A, Conformance Level FHD Receivers.

                       Refresh the NCuT's view of the Registry and carefully select the Senders \
                       that are compatible with the following Receiver:

                       {receiver['display_answer']}
                       """)

            set_A_level_FHD_senders = [s for s in self.senders
                                       if s['capability_set'] == 'A' and s['conformance_level'] == 'FHD']
            other_senders = [s for s in self.senders
                             if s['capability_set'] != 'A' or s['conformance_level'] != 'FHD']

            candidate_senders = random.sample(set_A_level_FHD_senders,
                                              random.randint(1, min(MAX_COMPATIBLE_SENDER_COUNT,
                                                                    len(set_A_level_FHD_senders))))
            if len(candidate_senders) < CANDIDATE_SENDER_COUNT:
                candidate_senders.extend(random.sample(other_senders,
                                                       min(CANDIDATE_SENDER_COUNT - len(candidate_senders),
                                                           len(other_senders))))

            candidate_senders.sort(key=itemgetter("label"))

            possible_answers = [{'answer_id': 'answer_'+str(i), 'display_answer': r['display_answer'],
                                'resource': {'id': r['id'], 'label': r['label'], 'description': r['description']}}
                                for i, r in enumerate(candidate_senders)]
            expected_answers = ['answer_'+str(i) for i, s in enumerate(candidate_senders)
                                if s['capability_set'] == 'A' or s['conformance_level'] == 'FHD']

            actual_answers = self._invoke_testing_facade(
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
