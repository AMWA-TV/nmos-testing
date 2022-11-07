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

from .. import Config as CONFIG
from ..ControllerTest import ControllerTest, TestingFacadeException
from ..NMOSUtils import NMOSUtils


class BCP0060102Test(ControllerTest):
    """
    Runs Controller Tests covering BCP-006-01
    """
    def __init__(self, apis, registries, node, dns_server):
        ControllerTest.__init__(self, apis, registries, node, dns_server)

    def _generate_caps(self, media_types):
        split_exactframerate = CONFIG.SDP_PREFERENCES["video_exactframerate"].split()
        caps = {
            "media_types": media_types,
            "constraint_sets": [
                {
                    "urn:x-nmos:cap:format:color_sampling": {
                        "enum": [CONFIG.SDP_PREFERENCES["video_sampling"]]
                    },
                    "urn:x-nmos:cap:format:frame_height": {
                        "enum": [CONFIG.SDP_PREFERENCES["video_height"]]
                    },
                    "urn:x-nmos:cap:format:frame_width": {
                        "enum": [CONFIG.SDP_PREFERENCES["video_width"]]
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
                        ] if CONFIG.SDP_PREFERENCES["video_interlace"] else [
                            "progressive"
                        ]
                    }
                }
            ],
            "version": NMOSUtils.get_TAI_time()
        }

        return caps

    def set_up_tests(self):
        self.senders = [{'label': 's1/plant', 'description': 'Mock sender 1', 'registered': True,
                         'sdp_params': {'media_type': 'jxsv', 'profile': 'High444.12', 'level': '2k-1',
                                        'sublevel': 'Sublev3bpp', 'sampling': 'YCbCr-4:2:2', 'depth': '10',
                                        'colorimetry': 'BT709', 'bit_rate': 109000, 'st2110_21_sender_type': '2110TPN',
                                        'transmode': 1, 'packetmode': 0}},
                        {'label': 's2/page', 'description': 'Mock sender 2', 'registered': True,
                         'sdp_params': {'media_type': 'raw'}},
                        {'label': 's3/bonham', 'description': 'Mock sender 3', 'registered': True,
                         'sdp_params': {'media_type': 'raw'}},
                        {'label': 's4/jones', 'description': 'Mock sender 4', 'registered': True,
                         'sdp_params': {'media_type': 'jxsv', 'profile': 'High444.12', 'level': '2k-1',
                                        'sublevel': 'Sublev3bpp', 'sampling': 'YCbCr-4:2:2', 'depth': '10',
                                        'colorimetry': 'BT709', 'bit_rate': 109000, 'st2110_21_sender_type': '2110TPN',
                                        'transmode': 1, 'packetmode': 1}}]

        self.receivers = [{'label': 'r1/john', 'description': 'Mock receiver 1',
                           'connectable': True, 'registered': True},
                          {'label': 'r2/paul', 'description': 'Mock receiver 2',
                           'connectable': True, 'registered': True},
                          {'label': 'r3/george', 'description': 'Mock receiver 3',
                           'connectable': True, 'registered': True},
                          {'label': 'r4/ringo', 'description': 'Mock receiver 4',
                           'connectable': True, 'registered': True}]

        # Randomly select some Receivers to be JPEG XS capable
        jxsv_receivers = self._generate_random_indices(len(self.receivers), min_index_count=1)

        for i in range(0, len(self.receivers)):
            if i in jxsv_receivers:
                self.receivers[i]['caps'] = self._generate_caps(["video/jxsv"])
            else:
                self.receivers[i]['caps'] = self._generate_caps(["video/raw"])

        ControllerTest.set_up_tests(self)

    def test_01(self, test):
        """
        Ensure NCuT can identify JPEG XS Receivers
        """

        try:
            # Question 1 connection
            question = """\
                       The NCuT should be able to discover all JPEG XS capable Receivers \
                       that are registered in the Registry.

                       Refresh the NCuT's view of the Registry and carefully select the Receivers \
                       that are JPEG XS capable from the following list.
                       """
            possible_answers = [{'answer_id': 'answer_'+str(i), 'display_answer': r['display_answer'],
                                'resource': {'id': r['id'], 'label': r['label'], 'description': r['description']}}
                                for i, r in enumerate(self.receivers)]
            expected_answers = ['answer_'+str(i) for i, r in enumerate(self.receivers)
                                if 'video/jxsv' in r['caps']['media_types']]

            actual_answers = self._invoke_testing_facade(
                question, possible_answers, test_type="multi_choice")['answer_response']

            if len(actual_answers) != len(expected_answers):
                return test.FAIL('Incorrect receiver identified')
            else:
                for answer in actual_answers:
                    if answer not in expected_answers:
                        return test.FAIL('Incorrect receiver identified')

            return test.PASS('All devices correctly identified')

        except TestingFacadeException as e:
            return test.UNCLEAR(e.args[0])
