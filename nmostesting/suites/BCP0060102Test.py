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

    def _initialize_capability_set_AB_level_FHD(self):

        interoperability_points = []  # 10 interoperability point defined here

        # Interoperability Points Capability Set A & Set B, Conformance Level FHD with reference to VSF TR-08:2022
        # NOTE: Set A & Set B  have the same metadata as currently
        # IS-04 doesn't distinguish between ST 2110-21 Type A and Type W Receivers
        ip1_6c_base = {'media_type': 'jxsv', 'video_width': 1920, 'video_height': 1080, 'video_interlace': False,
                       'video_exactframerate': '60000/1001', 'bit_rate': 109000, 'video_depth': '10',
                       'video_sampling': 'YCbCr-4:2:2', 'video_colorimetry': 'BT709', 'profile': 'High444.12',
                       'level': '2k-1', 'sublevel': 'Sublev3bpp', 'video_transfer_characteristic': 'SDR',
                       'min_bit_rate': 186000, 'max_bit_rate': 497000,
                       'st2110_21_sender_type': '2110TPW', 'packet_transmission_mode': 'codestream',
                       'capability_set': 'AB', 'conformance_level': 'FHD'}

        interop_point_1 = self._create_interop_point(ip1_6c_base, [('video_width', 1280), ('video_height', 720),
                                                                   ('min_bit_rate', 83000), ('max_bit_rate', 221000),
                                                                   ('interop_point', 'AB_1')])
        interoperability_points.append(interop_point_1)

        interop_point_2 = self._create_interop_point(ip1_6c_base, [('video_width', 1280), ('video_height', 720),
                                                                   ('video_exactframerate', '50'),
                                                                   ('min_bit_rate', 69000), ('max_bit_rate', 184000),
                                                                   ('interop_point', 'AB_2')])
        interoperability_points.append(interop_point_2)

        interop_point_3 = self._create_interop_point(ip1_6c_base, [('video_exactframerate', '30000/1001'),
                                                                   ('video_interlace', True),
                                                                   ('min_bit_rate', 93000), ('max_bit_rate', 249000),
                                                                   ('interop_point', 'AB_3')])
        interoperability_points.append(interop_point_3)

        interop_point_4 = self._create_interop_point(ip1_6c_base, [('video_exactframerate', '25'),
                                                                   ('video_interlace', True),
                                                                   ('min_bit_rate', 78000), ('max_bit_rate', 207000),
                                                                   ('interop_point', 'AB_4')])
        interoperability_points.append(interop_point_4)

        interop_point_5a = self._create_interop_point(ip1_6c_base, [('bit_rate', 250000),
                                                                    ('interop_point', 'AB_5a')])
        interoperability_points.append(interop_point_5a)

        interop_point_5b = self._create_interop_point(ip1_6c_base, [('bit_rate', 250000),
                                                                    ('video_colorimetry', 'BT2100'),
                                                                    ('video_transfer_characteristic', 'PQ'),
                                                                    ('interop_point', 'AB_5b')])
        interoperability_points.append(interop_point_5b)

        interop_point_5c = self._create_interop_point(ip1_6c_base, [('bit_rate', 250000),
                                                                    ('video_colorimetry', 'BT2100'),
                                                                    ('video_transfer_characteristic', 'HLG'),
                                                                    ('interop_point', 'AB_5c')])
        interoperability_points.append(interop_point_5c)

        interop_point_6a = self._create_interop_point(ip1_6c_base, [('video_exactframerate', '50'),
                                                                    ('bit_rate', 250000),
                                                                    ('video_exactframerate', '50'),
                                                                    ('min_bit_rate', 156000), ('max_bit_rate', 415000),
                                                                    ('interop_point', 'AB_6a')])
        interoperability_points.append(interop_point_6a)

        interop_point_6b = self._create_interop_point(ip1_6c_base, [('bit_rate', 250000),
                                                                    ('min_bit_rate', 156000), ('max_bit_rate', 415000),
                                                                    ('video_exactframerate', '50'),
                                                                    ('video_colorimetry', 'BT2100'),
                                                                    ('video_transfer_characteristic', 'PQ'),
                                                                    ('interop_point', 'AB_6b')])
        interoperability_points.append(interop_point_6b)

        interop_point_6c = self._create_interop_point(ip1_6c_base, [('bit_rate', 250000), ('min_bit_rate', 156000),
                                                                    ('max_bit_rate', 415000),
                                                                    ('video_exactframerate', '50'),
                                                                    ('video_colorimetry', 'BT2100'),
                                                                    ('video_transfer_characteristic', 'HLG'),
                                                                    ('interop_point', 'AB_6c')])
        interoperability_points.append(interop_point_6c)

        return interoperability_points

    def _initialize_capability_set_AB_level_UHD1(self):

        interoperability_points = []  # 6 interoperability point defined here

        # Interoperability Points Capability Set A & Set B, Conformance Level UHD1 with reference to VSF TR-08:2022
        # NOTE: Set A & Set B  have the same metadata as currently
        # IS-04 doesn't distinguish between ST 2110-21 Type A and Type W Receivers
        ip7a_8c_base = {'media_type': 'jxsv', 'video_width': 3840, 'video_height': 2160, 'video_interlace': False,
                        'video_exactframerate': '60000/1001', 'bit_rate': 100000, 'video_depth': '10',
                        'video_sampling': 'YCbCr-4:2:2', 'video_colorimetry': 'BT2100', 'profile': 'High444.12',
                        'level': '4k-2', 'sublevel': 'Sublev3bpp', 'video_transfer_characteristic': 'SDR',
                        'min_bit_rate': 746000, 'max_bit_rate': 1989000,
                        'st2110_21_sender_type': '2110TPW', 'packet_transmission_mode': 'codestream',
                        'capability_set': 'AB', 'conformance_level': 'UHD1'}

        interop_point_7a = self._create_interop_point(ip7a_8c_base, [('video_colorimetry', 'BT2020'),
                                                                     ('interop_point', 'AB_7a')])
        interoperability_points.append(interop_point_7a)

        interop_point_7b = self._create_interop_point(ip7a_8c_base, [('video_transfer_characteristic', 'PQ'),
                                                                     ('interop_point', 'AB_7b')])
        interoperability_points.append(interop_point_7b)

        interop_point_7c = self._create_interop_point(ip7a_8c_base, [('video_transfer_characteristic', 'HLG'),
                                                                     ('interop_point', 'AB_7c')])
        interoperability_points.append(interop_point_7c)

        interop_point_8a = self._create_interop_point(ip7a_8c_base, [('min_bit_rate', 622000),
                                                                     ('max_bit_rate', 1659000),
                                                                     ('video_exactframerate', '50'),
                                                                     ('video_colorimetry', 'BT2020'),
                                                                     ('interop_point', 'AB_8a')])
        interoperability_points.append(interop_point_8a)

        interop_point_8b = self._create_interop_point(ip7a_8c_base, [('min_bit_rate', 622000),
                                                                     ('max_bit_rate', 1659000),
                                                                     ('video_exactframerate', '50'),
                                                                     ('video_transfer_characteristic', 'PQ'),
                                                                     ('interop_point', 'AB_8b')])
        interoperability_points.append(interop_point_8b)

        interop_point_8c = self._create_interop_point(ip7a_8c_base, [('min_bit_rate', 622000),
                                                                     ('max_bit_rate', 1659000),
                                                                     ('video_exactframerate', '50'),
                                                                     ('video_transfer_characteristic', 'HLG'),
                                                                     ('interop_point', 'AB_8c')])
        interoperability_points.append(interop_point_8c)

        return interoperability_points

    def _initialize_capability_set_AB_level_UHD2(self):

        interoperability_points = []  # 6 interoperability point defined here

        # Interoperability Points Capability Set A & Set B, Conformance Level UHD2 with reference to VSF TR-08:2022
        # NOTE: Set A & Set B have the same metadata as currently
        # IS-04 doesn't distinguish between ST 2110-21 Type A and Type W Receivers
        ip9a_10c_base = {'media_type': 'jxsv', 'video_width': 7680, 'video_height': 4320, 'video_interlace': False,
                         'video_exactframerate': '60000/1001', 'bit_rate': 4000000, 'video_depth': '10',
                         'video_sampling': 'YCbCr-4:2:2', 'video_colorimetry': 'BT2100', 'profile': 'High444.12',
                         'level': '8k-2', 'sublevel': 'Sublev3bpp', 'video_transfer_characteristic': 'SDR',
                         'min_bit_rate': 2983000, 'max_bit_rate': 7955000,
                         'st2110_21_sender_type': '2110TPW', 'packet_transmission_mode': 'codestream',
                         'capability_set': 'AB', 'conformance_level': 'UHD2'}

        interop_point_9a = self._create_interop_point(ip9a_10c_base, [('video_colorimetry', 'BT2020'),
                                                                      ('interop_point', 'AB_9a')])
        interoperability_points.append(interop_point_9a)

        interop_point_9b = self._create_interop_point(ip9a_10c_base, [('video_transfer_characteristic', 'PQ'),
                                                                      ('interop_point', 'AB_9b')])
        interoperability_points.append(interop_point_9b)

        interop_point_9c = self._create_interop_point(ip9a_10c_base, [('video_transfer_characteristic', 'HLG'),
                                                                      ('interop_point', 'AB_9c')])
        interoperability_points.append(interop_point_9c)

        interop_point_10a = self._create_interop_point(ip9a_10c_base, [('min_bit_rate', 2488000),
                                                                       ('max_bit_rate', 6636000),
                                                                       ('video_exactframerate', '50'),
                                                                       ('video_colorimetry', 'BT2020'),
                                                                       ('interop_point', 'AB_10a')])
        interoperability_points.append(interop_point_10a)

        interop_point_10b = self._create_interop_point(ip9a_10c_base, [('min_bit_rate', 2488000),
                                                                       ('max_bit_rate', 6636000),
                                                                       ('video_exactframerate', '50'),
                                                                       ('video_transfer_characteristic', 'PQ'),
                                                                       ('interop_point', 'AB_10b')])
        interoperability_points.append(interop_point_10b)

        interop_point_10c = self._create_interop_point(ip9a_10c_base, [('min_bit_rate', 2488000),
                                                                       ('max_bit_rate', 6636000),
                                                                       ('video_exactframerate', '50'),
                                                                       ('video_transfer_characteristic', 'HLG'),
                                                                       ('interop_point', 'AB_10c')])
        interoperability_points.append(interop_point_10c)

        return interoperability_points

    def _initialize_capability_set_C_level_FHD(self):

        interoperability_points = []  # 6 interoperability point defined here

        # Interoperability Points Capability Set C, Conformance Level FHD with reference to VSF TR-08:2022
        ip1a_2b_base = {'media_type': 'jxsv', 'video_width': 1920, 'video_height': 1080, 'video_interlace': False,
                        'video_exactframerate': '60000/1001', 'bit_rate': 250000, 'video_depth': '8',
                        'video_sampling': 'RGB', 'video_colorimetry': 'BT709', 'profile': 'High444.12',
                        'level': '2k-1', 'sublevel': 'Sublev3bpp', 'video_transfer_characteristic': 'SDR',
                        'min_bit_rate': 186000, 'max_bit_rate': 497000,
                        'st2110_21_sender_type': '2110TPW', 'packet_transmission_mode': 'codestream',
                        'capability_set': 'C', 'conformance_level': 'FHD'}

        interop_point_1a = self._create_interop_point(ip1a_2b_base, [('interop_point', 'C_1a')])
        interoperability_points.append(interop_point_1a)

        interop_point_1b = self._create_interop_point(ip1a_2b_base, [('video_exactframerate', '50'),
                                                                     ('min_bit_rate', 156000),
                                                                     ('max_bit_rate', 415000),
                                                                     ('interop_point', 'C_1b')])
        interoperability_points.append(interop_point_1b)

        interop_point_1c = self._create_interop_point(ip1a_2b_base, [('video_exactframerate', '60'),
                                                                     ('min_bit_rate', 187000),
                                                                     ('max_bit_rate', 498000),
                                                                     ('video_depth', '10'),
                                                                     ('interop_point', 'C_1c')])
        interoperability_points.append(interop_point_1c)

        interop_point_1d = self._create_interop_point(ip1a_2b_base, [('video_sampling', 'YCbCr-4:4:4'),
                                                                     ('interop_point', 'C_1d')])
        interoperability_points.append(interop_point_1d)

        interop_point_2a = self._create_interop_point(ip1a_2b_base, [('video_height', 1200),
                                                                     ('video_exactframerate', '60'),
                                                                     ('level', '4k-1'),
                                                                     ('min_bit_rate', 207000),
                                                                     ('max_bit_rate', 552000),
                                                                     ('fullrange', True),
                                                                     ('interop_point', 'C_2a')])
        interoperability_points.append(interop_point_2a)

        interop_point_2b = self._create_interop_point(ip1a_2b_base, [('video_height', 1200),
                                                                     ('video_exactframerate', '50'),
                                                                     ('level', '4k-1'),
                                                                     ('min_bit_rate', 173000),
                                                                     ('max_bit_rate', 461000),
                                                                     ('fullrange', True),
                                                                     ('interop_point', 'C_2b')])
        interoperability_points.append(interop_point_2b)

        return interoperability_points

    def _initialize_capability_set_C_level_UHD1_UHD2(self):

        interoperability_points = []  # 8 interoperability point defined here

        # Interoperability Points Capability Set C, Conformance Level UHD1 & UHD2 with reference to VSF TR-08:2022
        ip3a_4c_base = {'media_type': 'jxsv', 'video_width': 3840, 'video_height': 2160, 'video_interlace': False,
                        'video_exactframerate': '60000/1001', 'bit_rate': 200000, 'video_depth': '10',
                        'video_sampling': 'YCbCr-4:4:4', 'video_colorimetry': 'BT2100', 'profile': 'High444.12',
                        'level': '4k-2', 'sublevel': 'Sublev3bpp', 'video_transfer_characteristic': 'SDR',
                        'min_bit_rate': 746000, 'max_bit_rate': 1991000,
                        'st2110_21_sender_type': '2110TPW', 'packet_transmission_mode': 'codestream',
                        'capability_set': 'C', 'conformance_level': 'UHD1'}

        interop_point_3a = self._create_interop_point(ip3a_4c_base, [('video_depth', '8'),
                                                                     ('video_sampling', 'RGB'),
                                                                     ('video_colorimetry', 'BT709'),
                                                                     ('interop_point', 'C_3a')])
        interoperability_points.append(interop_point_3a)

        interop_point_3b = self._create_interop_point(ip3a_4c_base, [('interop_point', 'C_3b')])
        interoperability_points.append(interop_point_3b)

        interop_point_3c = self._create_interop_point(ip3a_4c_base, [('video_transfer_characteristic', 'PQ'),
                                                                     ('interop_point', 'C_3c')])
        interoperability_points.append(interop_point_3c)

        interop_point_3d = self._create_interop_point(ip3a_4c_base, [('video_transfer_characteristic', 'HLG'),
                                                                     ('interop_point', 'C_3d')])
        interoperability_points.append(interop_point_3d)

        interop_point_3e = self._create_interop_point(ip3a_4c_base, [('video_sampling', 'RGB'),
                                                                     ('video_colorimetry', 'BT2020'),
                                                                     ('interop_point', 'C_3e')])
        interoperability_points.append(interop_point_3e)

        interop_point_4a = self._create_interop_point(ip3a_4c_base, [('min_bit_rate', 2986000),
                                                                     ('max_bit_rate', 7963000),
                                                                     ('level', '8k-2'),
                                                                     ('conformance_level', 'UHD2'),
                                                                     ('interop_point', 'C_4a')])
        interoperability_points.append(interop_point_4a)

        interop_point_4b = self._create_interop_point(ip3a_4c_base, [('min_bit_rate', 2986000),
                                                                     ('max_bit_rate', 7963000),
                                                                     ('level', '8k-2'),
                                                                     ('video_transfer_characteristic', 'PQ'),
                                                                     ('conformance_level', 'UHD2'),
                                                                     ('interop_point', 'C_4b')])
        interoperability_points.append(interop_point_4b)

        interop_point_4c = self._create_interop_point(ip3a_4c_base, [('min_bit_rate', 2986000),
                                                                     ('max_bit_rate', 7963000),
                                                                     ('level', '8k-2'),
                                                                     ('video_transfer_characteristic', 'HLG'),
                                                                     ('conformance_level', 'UHD2'),
                                                                     ('interop_point', 'C_4c')])
        interoperability_points.append(interop_point_4c)

        return interoperability_points

    def _initialize_capability_set_D_level_UHD1_UHD2(self):

        interoperability_points = []  # 7 interoperability point defined here

        # Interoperability Points Capability Set D, Conformance Level UHD1 & UHD2 with reference to VSF TR-08:2022
        ip1a_2c_base = {'media_type': 'jxsv', 'video_width': 3840, 'video_height': 2160, 'video_interlace': False,
                        'video_exactframerate': '60000/1001', 'bit_rate': 200000, 'video_depth': '10',
                        'video_sampling': 'YCbCr-4:2:0', 'video_colorimetry': 'BT2020', 'profile': 'High444.12',
                        'level': '4k-2', 'sublevel': 'Sublev3bpp', 'video_transfer_characteristic': 'SDR',
                        'min_bit_rate': 746000, 'max_bit_rate': 1989000,
                        'st2110_21_sender_type': '2110TPW', 'packet_transmission_mode': 'codestream',
                        'capability_set': 'D', 'conformance_level': 'UHD1'}

        interop_point_1a = self._create_interop_point(ip1a_2c_base, [('video_depth', '8'),
                                                                     ('interop_point', 'D_1a')])
        interoperability_points.append(interop_point_1a)

        interop_point_1b = self._create_interop_point(ip1a_2c_base, [('video_depth', '8'),
                                                                     ('video_exactframerate', '50'),
                                                                     ('min_bit_rate', 622000),
                                                                     ('max_bit_rate', 1659000),
                                                                     ('interop_point', 'D_1b')])
        interoperability_points.append(interop_point_1b)

        interop_point_1c = self._create_interop_point(ip1a_2c_base, [('interop_point', 'D_1c')])
        interoperability_points.append(interop_point_1c)

        interop_point_1d = self._create_interop_point(ip1a_2c_base, [('video_depth', '12'),
                                                                     ('interop_point', 'D_1d')])
        interoperability_points.append(interop_point_1d)

        interop_point_2a = self._create_interop_point(ip1a_2c_base, [('video_width', 7680), ('video_height', 4320),
                                                                     ('min_bit_rate', 2983000),
                                                                     ('max_bit_rate', 7955000),
                                                                     ('level', '8k-2'),
                                                                     ('conformance_level', 'UHD2'),
                                                                     ('interop_point', 'D_2a')])
        interoperability_points.append(interop_point_2a)

        interop_point_2b = self._create_interop_point(ip1a_2c_base, [('video_width', 7680), ('video_height', 4320),
                                                                     ('min_bit_rate', 2983000),
                                                                     ('max_bit_rate', 7955000),
                                                                     ('video_transfer_characteristic', 'PQ'),
                                                                     ('level', '8k-2'),
                                                                     ('conformance_level', 'UHD2'),
                                                                     ('interop_point', 'D_2b')])
        interoperability_points.append(interop_point_2b)

        interop_point_2c = self._create_interop_point(ip1a_2c_base, [('video_width', 7680), ('video_height', 4320),
                                                                     ('min_bit_rate', 2983000),
                                                                     ('max_bit_rate', 7955000),
                                                                     ('video_transfer_characteristic', 'HLG'),
                                                                     ('level', '8k-2'),
                                                                     ('conformance_level', 'UHD2'),
                                                                     ('interop_point', 'D_2c')])
        interoperability_points.append(interop_point_2c)

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
            },
            "capability_set": sdp_params.get('capability_set'),
            "conformance_level": sdp_params.get('conformance_level')
        }

        # JPEG XS specific caps
        if "profile" in sdp_params and "level" in sdp_params:
            constraint_set.update({"urn:x-nmos:cap:format:profile": {"enum": [sdp_params.get("profile")]},
                                   "urn:x-nmos:cap:format:level": {"enum": [sdp_params.get("level")]},
                                   "urn:x-nmos:cap:format:sublevel": {"enum": ["Sublev3bpp", "Sublev4bpp"]},
                                   "urn:x-nmos:cap:transport:packet_transmission_mode": {"enum": ["codestream"]},
                                   "urn:x-nmos:cap:format:bit_rate": {"minimum": sdp_params.get("min_bit_rate"),
                                                                      "maximum": sdp_params.get("max_bit_rate")},
                                   "urn:x-nmos:cap:transport:st2110_21_sender_type": {
                                       "enum": ['2110TN', '2110TNL', '2110TPW']}})
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
        param_mapping = [('video_width', 'frame_width'), ('video_height', 'frame_height'),
                         ('profile', 'profile'), ('level', 'level'), ('sublevel', 'sublevel'),
                         ('video_colorimetry', 'colorspace'), ('bit_rate', 'bit_rate'),
                         ('video_transfer_characteristic', 'transfer_characteristic')]

        flow_params["media_type"] = "video/" + sdp_params.get("media_type", "raw")

        for sdp_param, flow_param in param_mapping:
            if sdp_param in sdp_params:
                flow_params[flow_param] = sdp_params[sdp_param]

        flow_params["interlace_mode"] = "interlaced_tff" \
            if sdp_params.get("video_interlace") else "progressive"

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

    def _is_compatible(self, sender, receiver):
        if sender.get('conformance_level') == receiver.get('conformance_level'):

            if sender.get('capability_set') in receiver['capability_set']:
                return True

        return False

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

        interoperability_points = self._initialize_capability_set_AB_level_FHD()
        interoperability_points.extend(self._initialize_capability_set_AB_level_UHD1())
        interoperability_points.extend(self._initialize_capability_set_AB_level_UHD2())
        interoperability_points.extend(self._initialize_capability_set_C_level_FHD())
        interoperability_points.extend(self._initialize_capability_set_C_level_UHD1_UHD2())
        interoperability_points.extend(self._initialize_capability_set_D_level_UHD1_UHD2())

        # create a map of the interop points so they can be assigned to Senders
        capability_set_map = {interop_point['interop_point']: interop_point
                              for interop_point in interoperability_points}

        # create sub list of representative interoperability points, key is TR-08 Interoperability Point
        sender_interop_points = [capability_set_map['AB_1'],  # FHD
                                 capability_set_map['AB_7a'],  # UHD1
                                 capability_set_map['AB_9a'],  # UHD2
                                 capability_set_map['C_1a'],  # FHD
                                 capability_set_map['C_3a'],  # UHD1
                                 capability_set_map['C_4a'],  # UHD2
                                 capability_set_map['D_1a'],  # UHD1
                                 capability_set_map['D_2a']]  # UHD2

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
                'conformance_level': interop_point.get('conformance_level'),
                'interop_point': interop_point.get('interop_point')
            }
            self.senders.append(sender)

        # Notes on TR-08 Compatibility of Senders and Receivers
        # Set A and Set B are not distinguished here and are denoted as Set AB
        # For a particular conformance level (FHD, UHD1, UHD2):
        # * AB Senders are compatible with: [AB, C, D] Receivers
        # * C  Senders are compatible with: [C, D] Receivers
        # * D  Senders are compatible with: [D Receivers

        # pad configurations with some video/raw (None, None) configurations
        capability_configurations = [(['AB', 'C', 'D'], 'FHD'), (['AB', 'C', 'D'], 'UHD1'), (['AB', 'C', 'D'], 'UHD2'),
                                     (['C', 'D'], 'FHD'), (['C', 'D'], 'UHD1'), (['C', 'D'], 'UHD2'),
                                     (['D'], 'UHD1'), (['D'], 'UHD2'),
                                     ([], None), ([], None), ([], None)]

        self.receivers.clear()

        random.shuffle(receiver_names)
        random.shuffle(capability_configurations)
        for idx, (receiver_name, (capability_set, conformance_level)) in \
                enumerate(zip(receiver_names, capability_configurations)):
            # choose a random interop point
            caps = [i for i in interoperability_points
                    if i["capability_set"] in capability_set and i["conformance_level"] == conformance_level]

            receiver = {
                'label': 'r' + str(idx) + '/' + receiver_name,
                'description': 'Mock Receiver ' + str(idx),
                'connectable': True,
                'registered': True,
                'caps': self._generate_caps(caps) if caps else {"media_types": ['video/raw']},
                'capability_set': capability_set,
                'conformance_level': conformance_level,
                'interop_point': interop_point.get('interop_point')
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
        Ensure NCuT can identify JPEG XS Receiver compatibility according to TR-08 Capability Set and Conformance Level
        """

        MAX_COMPATIBLE_RECEIVER_COUNT = 4
        CANDIDATE_RECEIVER_COUNT = 6

        try:
            jxsv_senders = [s for s in self.senders
                            if s['capability_set'] is not None and s['conformance_level'] is not None]

            for i, sender in enumerate(jxsv_senders):

                question = textwrap.dedent(f"""\
                           The NCuT should be able to discover JPEG XS capable Receivers \
                           that are compatible with JPEG XS Senders according to \
                           TR-08 Capability Set and Conformance Level.

                           Refresh the NCuT's view of the Registry and carefully select the Receivers \
                           that are compatible with the following Sender:

                           {sender['display_answer']}
                           """)

                compatible_receviers = [r for r in self.receivers if self._is_compatible(sender, r)]
                other_receivers = [r for r in self.receivers if not self._is_compatible(sender, r)]

                candidate_receivers = random.sample(compatible_receviers,
                                                    random.randint(1, min(MAX_COMPATIBLE_RECEIVER_COUNT,
                                                                          len(compatible_receviers))))
                if len(candidate_receivers) < CANDIDATE_RECEIVER_COUNT:
                    candidate_receivers.extend(random.sample(other_receivers,
                                                             min(CANDIDATE_RECEIVER_COUNT - len(candidate_receivers),
                                                                 len(other_receivers))))

                candidate_receivers.sort(key=itemgetter("label"))

                possible_answers = [{'answer_id': 'answer_'+str(i), 'display_answer': r['display_answer'],
                                    'resource': {'id': r['id'], 'label': r['label'], 'description': r['description']}}
                                    for i, r in enumerate(candidate_receivers)]
                expected_answers = ['answer_'+str(i) for i, r in enumerate(candidate_receivers)
                                    if self._is_compatible(sender, r)]

                actual_answers = self._invoke_testing_facade(
                    question, possible_answers, test_type="multi_choice", multipart_test=i)['answer_response']

                if len(actual_answers) != len(expected_answers):
                    return test.FAIL('Incorrect Receiver identified for Compatability Set ' + sender['capability_set']
                                     + ', Conformance Level ' + sender['conformance_level']
                                     + ' and Interoperability Point ' + sender['interop_point'])
                else:
                    for answer in actual_answers:
                        if answer not in expected_answers:
                            return test.FAIL('Incorrect Receiver identified for Compatability Set '
                                             + sender['capability_set']
                                             + ', Conformance Level ' + sender['conformance_level']
                                             + ' and Interoperability Point ' + sender['interop_point'])

            return test.PASS('All Receivers correctly identified')

        except TestingFacadeException as e:
            return test.UNCLEAR(e.args[0])

    def test_06(self, test):
        """
        Ensure NCuT can identify JPEG XS Sender compatibility according to TR-08 Capability Set and Conformance Level
        """

        MAX_COMPATIBLE_SENDER_COUNT = 3
        CANDIDATE_SENDER_COUNT = 6

        try:
            jxsv_receivers = [r for r in self.receivers
                              if len(r['capability_set']) != 0 and r['conformance_level'] is not None]

            for i, receiver in enumerate(jxsv_receivers):

                question = textwrap.dedent(f"""\
                           The NCuT should be able to discover JPEG XS capable Senders \
                           that are compatible with JPEG XS Receivers according to \
                           TR-08 Capability Set and Conformance Level.

                           Refresh the NCuT's view of the Registry and carefully select the Senders \
                           that are compatible with the following Receiver:

                           {receiver['display_answer']}
                           """)

                compatible_senders = [s for s in self.senders if self._is_compatible(s, receiver)]
                other_senders = [s for s in self.senders if not self._is_compatible(s, receiver)]

                candidate_senders = random.sample(compatible_senders,
                                                  random.randint(1, min(MAX_COMPATIBLE_SENDER_COUNT,
                                                                        len(compatible_senders))))
                if len(candidate_senders) < CANDIDATE_SENDER_COUNT:
                    candidate_senders.extend(random.sample(other_senders,
                                                           min(CANDIDATE_SENDER_COUNT - len(candidate_senders),
                                                               len(other_senders))))

                candidate_senders.sort(key=itemgetter("label"))

                possible_answers = [{'answer_id': 'answer_'+str(i), 'display_answer': r['display_answer'],
                                    'resource': {'id': r['id'], 'label': r['label'], 'description': r['description']}}
                                    for i, r in enumerate(candidate_senders)]
                expected_answers = ['answer_'+str(i) for i, s in enumerate(candidate_senders)
                                    if self._is_compatible(s, receiver)]

                actual_answers = self._invoke_testing_facade(
                    question, possible_answers, test_type="multi_choice", multipart_test=i)['answer_response']

                if len(actual_answers) != len(expected_answers):
                    return test.FAIL('Incorrect Sender identified for Compatability Set ('
                                     + str(receiver['capability_set'])
                                     + '), Conformance Level ' + receiver['conformance_level']
                                     + ' and Interoperability Point ' + receiver['interop_point'])
                else:
                    for answer in actual_answers:
                        if answer not in expected_answers:
                            return test.FAIL('Incorrect Sender identified for Compatability Set ('
                                             + str(receiver['capability_set'])
                                             + '), Conformance Level ' + receiver['conformance_level']
                                             + ' and Interoperability Point ' + receiver['interop_point'])

            return test.PASS('All Senders correctly identified')

        except TestingFacadeException as e:
            return test.UNCLEAR(e.args[0])
