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

import textwrap
from operator import itemgetter
from itertools import cycle, islice
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
        interop_point = {**sdp_base, **override_params}
        # Set bit rate and sublevel based on 2 bpp relying on VSF TR-08:2022 Appendix B min bit rate for 1.5 bpp
        interop_point['bit_rate'] = int(round(interop_point['min_bit_rate'] * 2/1.5, -3))
        interop_point['sublevel'] = 'Sublev3bpp'
        return interop_point

    def _initialize_capability_set_AB_level_FHD(self):

        interoperability_points = []  # 10 interoperability points defined here

        # Interoperability Points Capability Set A & Set B, Conformance Level FHD with reference to VSF TR-08:2022
        # NOTE: Set A & Set B have the same metadata as currently IS-04 doesn't distinguish between
        # ST 2110-21 Type A and Type W Receivers
        ip1_6c_base = {'media_type': 'jxsv', 'video_width': 1920, 'video_height': 1080, 'video_interlace': False,
                       'video_exactframerate': '60000/1001', 'min_bit_rate': 186000, 'max_bit_rate': 497000,
                       'video_depth': 10, 'video_sampling': 'YCbCr-4:2:2', 'video_colorimetry': 'BT709',
                       'profile': 'High444.12', 'level': '2k-1', 'video_transfer_characteristic': 'SDR',
                       'st2110_21_sender_type': '2110TPW', 'packet_transmission_mode': 'codestream',
                       'capability_set': 'AB', 'conformance_level': 'FHD'}

        interop_point_1 = self._create_interop_point(ip1_6c_base, {'interop_point': '1',
                                                                   'video_width': 1280,
                                                                   'video_height': 720,
                                                                   'min_bit_rate': 83000,
                                                                   'max_bit_rate': 221000,
                                                                   'level': '1k-1'})
        interoperability_points.append(interop_point_1)

        interop_point_2 = self._create_interop_point(ip1_6c_base, {'interop_point': '2',
                                                                   'video_width': 1280,
                                                                   'video_height': 720,
                                                                   'video_exactframerate': '50',
                                                                   'min_bit_rate': 69000,
                                                                   'max_bit_rate': 184000,
                                                                   'level': '1k-1'})
        interoperability_points.append(interop_point_2)

        interop_point_3 = self._create_interop_point(ip1_6c_base, {'interop_point': '3',
                                                                   'video_exactframerate': '30000/1001',
                                                                   'video_interlace': True,
                                                                   'min_bit_rate': 93000,
                                                                   'max_bit_rate': 249000})
        interoperability_points.append(interop_point_3)

        interop_point_4 = self._create_interop_point(ip1_6c_base, {'interop_point': '4',
                                                                   'video_exactframerate': '25',
                                                                   'video_interlace': True,
                                                                   'min_bit_rate': 78000,
                                                                   'max_bit_rate': 207000})
        interoperability_points.append(interop_point_4)

        interop_point_5a = self._create_interop_point(ip1_6c_base, {'interop_point': '5a'})
        interoperability_points.append(interop_point_5a)

        interop_point_5b = self._create_interop_point(ip1_6c_base, {'interop_point': '5b',
                                                                    'video_colorimetry': 'BT2100',
                                                                    'video_transfer_characteristic': 'PQ'})
        interoperability_points.append(interop_point_5b)

        interop_point_5c = self._create_interop_point(ip1_6c_base, {'interop_point': '5c',
                                                                    'video_colorimetry': 'BT2100',
                                                                    'video_transfer_characteristic': 'HLG'})
        interoperability_points.append(interop_point_5c)

        interop_point_6a = self._create_interop_point(ip1_6c_base, {'interop_point': '6a',
                                                                    'video_exactframerate': '50',
                                                                    'min_bit_rate': 156000,
                                                                    'max_bit_rate': 415000})
        interoperability_points.append(interop_point_6a)

        interop_point_6b = self._create_interop_point(ip1_6c_base, {'interop_point': '6b',
                                                                    'video_exactframerate': '50',
                                                                    'min_bit_rate': 156000,
                                                                    'max_bit_rate': 415000,
                                                                    'video_colorimetry': 'BT2100',
                                                                    'video_transfer_characteristic': 'PQ'})
        interoperability_points.append(interop_point_6b)

        interop_point_6c = self._create_interop_point(ip1_6c_base, {'interop_point': '6c',
                                                                    'video_exactframerate': '50',
                                                                    'min_bit_rate': 156000,
                                                                    'max_bit_rate': 415000,
                                                                    'video_colorimetry': 'BT2100',
                                                                    'video_transfer_characteristic': 'HLG'})
        interoperability_points.append(interop_point_6c)

        return interoperability_points

    def _initialize_capability_set_AB_level_UHD1(self):

        interoperability_points = []  # 6 interoperability points defined here

        # Interoperability Points Capability Set A & Set B, Conformance Level UHD1 with reference to VSF TR-08:2022
        # NOTE: Set A & Set B have the same metadata as currently IS-04 doesn't distinguish between
        # ST 2110-21 Type A and Type W Receivers
        ip7a_8c_base = {'media_type': 'jxsv', 'video_width': 3840, 'video_height': 2160, 'video_interlace': False,
                        'video_exactframerate': '60000/1001', 'min_bit_rate': 746000, 'max_bit_rate': 1989000,
                        'video_depth': 10, 'video_sampling': 'YCbCr-4:2:2', 'video_colorimetry': 'BT2100',
                        'profile': 'High444.12', 'level': '4k-2', 'video_transfer_characteristic': 'SDR',
                        'st2110_21_sender_type': '2110TPW', 'packet_transmission_mode': 'codestream',
                        'capability_set': 'AB', 'conformance_level': 'UHD1'}

        interop_point_7a = self._create_interop_point(ip7a_8c_base, {'interop_point': '7a',
                                                                     'video_colorimetry': 'BT2020'})
        interoperability_points.append(interop_point_7a)

        interop_point_7b = self._create_interop_point(ip7a_8c_base, {'interop_point': '7b',
                                                                     'video_transfer_characteristic': 'PQ'})
        interoperability_points.append(interop_point_7b)

        interop_point_7c = self._create_interop_point(ip7a_8c_base, {'interop_point': '7c',
                                                                     'video_transfer_characteristic': 'HLG'})
        interoperability_points.append(interop_point_7c)

        interop_point_8a = self._create_interop_point(ip7a_8c_base, {'interop_point': '8a',
                                                                     'video_exactframerate': '50',
                                                                     'min_bit_rate': 622000,
                                                                     'max_bit_rate': 1659000,
                                                                     'video_colorimetry': 'BT2020'})
        interoperability_points.append(interop_point_8a)

        interop_point_8b = self._create_interop_point(ip7a_8c_base, {'interop_point': '8b',
                                                                     'video_exactframerate': '50',
                                                                     'min_bit_rate': 622000,
                                                                     'max_bit_rate': 1659000,
                                                                     'video_transfer_characteristic': 'PQ'})
        interoperability_points.append(interop_point_8b)

        interop_point_8c = self._create_interop_point(ip7a_8c_base, {'interop_point': '8c',
                                                                     'video_exactframerate': '50',
                                                                     'min_bit_rate': 622000,
                                                                     'max_bit_rate': 1659000,
                                                                     'video_transfer_characteristic': 'HLG'})
        interoperability_points.append(interop_point_8c)

        return interoperability_points

    def _initialize_capability_set_AB_level_UHD2(self):

        interoperability_points = []  # 6 interoperability points defined here

        # Interoperability Points Capability Set A & Set B, Conformance Level UHD2 with reference to VSF TR-08:2022
        # NOTE: Set A & Set B have the same metadata as currently IS-04 doesn't distinguish between
        # ST 2110-21 Type A and Type W Receivers
        ip9a_10c_base = {'media_type': 'jxsv', 'video_width': 7680, 'video_height': 4320, 'video_interlace': False,
                         'video_exactframerate': '60000/1001', 'min_bit_rate': 2983000, 'max_bit_rate': 7955000,
                         'video_depth': 10, 'video_sampling': 'YCbCr-4:2:2', 'video_colorimetry': 'BT2100',
                         'profile': 'High444.12', 'level': '8k-2', 'video_transfer_characteristic': 'SDR',
                         'st2110_21_sender_type': '2110TPW', 'packet_transmission_mode': 'codestream',
                         'capability_set': 'AB', 'conformance_level': 'UHD2'}

        interop_point_9a = self._create_interop_point(ip9a_10c_base, {'interop_point': '9a',
                                                                      'video_colorimetry': 'BT2020'})
        interoperability_points.append(interop_point_9a)

        interop_point_9b = self._create_interop_point(ip9a_10c_base, {'interop_point': '9b',
                                                                      'video_transfer_characteristic': 'PQ'})
        interoperability_points.append(interop_point_9b)

        interop_point_9c = self._create_interop_point(ip9a_10c_base, {'interop_point': '9c',
                                                                      'video_transfer_characteristic': 'HLG'})
        interoperability_points.append(interop_point_9c)

        interop_point_10a = self._create_interop_point(ip9a_10c_base, {'interop_point': '10a',
                                                                       'video_exactframerate': '50',
                                                                       'min_bit_rate': 2488000,
                                                                       'max_bit_rate': 6636000,
                                                                       'video_colorimetry': 'BT2020'})
        interoperability_points.append(interop_point_10a)

        interop_point_10b = self._create_interop_point(ip9a_10c_base, {'interop_point': '10b',
                                                                       'video_exactframerate': '50',
                                                                       'min_bit_rate': 2488000,
                                                                       'max_bit_rate': 6636000,
                                                                       'video_transfer_characteristic': 'PQ'})
        interoperability_points.append(interop_point_10b)

        interop_point_10c = self._create_interop_point(ip9a_10c_base, {'interop_point': '10c',
                                                                       'video_exactframerate': '50',
                                                                       'min_bit_rate': 2488000,
                                                                       'max_bit_rate': 6636000,
                                                                       'video_transfer_characteristic': 'HLG'})
        interoperability_points.append(interop_point_10c)

        return interoperability_points

    def _initialize_capability_set_C_level_FHD(self):

        interoperability_points = []  # 6 interoperability points defined here

        # Interoperability Points Capability Set C, Conformance Level FHD with reference to VSF TR-08:2022
        ip1a_2b_base = {'media_type': 'jxsv', 'video_width': 1920, 'video_height': 1080, 'video_interlace': False,
                        'video_exactframerate': '60000/1001', 'min_bit_rate': 186000, 'max_bit_rate': 497000,
                        'video_depth': 8, 'video_sampling': 'RGB', 'video_colorimetry': 'BT709',
                        'profile': 'High444.12', 'level': '2k-1', 'video_transfer_characteristic': 'SDR',
                        'st2110_21_sender_type': '2110TPW', 'packet_transmission_mode': 'codestream',
                        'capability_set': 'C', 'conformance_level': 'FHD'}

        interop_point_1a = self._create_interop_point(ip1a_2b_base, {'interop_point': '1a'})
        interoperability_points.append(interop_point_1a)

        interop_point_1b = self._create_interop_point(ip1a_2b_base, {'interop_point': '1b',
                                                                     'video_exactframerate': '50',
                                                                     'min_bit_rate': 156000,
                                                                     'max_bit_rate': 415000})
        interoperability_points.append(interop_point_1b)

        interop_point_1c = self._create_interop_point(ip1a_2b_base, {'interop_point': '1c',
                                                                     'video_exactframerate': '60',
                                                                     'min_bit_rate': 187000,
                                                                     'max_bit_rate': 498000,
                                                                     'video_depth': 10})
        interoperability_points.append(interop_point_1c)

        interop_point_1d = self._create_interop_point(ip1a_2b_base, {'interop_point': '1d',
                                                                     'video_sampling': 'YCbCr-4:4:4'})
        interoperability_points.append(interop_point_1d)

        interop_point_2a = self._create_interop_point(ip1a_2b_base, {'interop_point': '2a',
                                                                     'video_height': 1200,
                                                                     'video_exactframerate': '60',
                                                                     'min_bit_rate': 207000,
                                                                     'max_bit_rate': 552000,
                                                                     'fullrange': True,
                                                                     'level': '4k-1'})
        interoperability_points.append(interop_point_2a)

        interop_point_2b = self._create_interop_point(ip1a_2b_base, {'interop_point': '2b',
                                                                     'video_height': 1200,
                                                                     'video_exactframerate': '50',
                                                                     'min_bit_rate': 173000,
                                                                     'max_bit_rate': 461000,
                                                                     'fullrange': True,
                                                                     'level': '4k-1'})
        interoperability_points.append(interop_point_2b)

        return interoperability_points

    def _initialize_capability_set_C_level_UHD1(self):

        interoperability_points = []  # 5 interoperability points defined here

        # Interoperability Points Capability Set C, Conformance Level UHD1 with reference to VSF TR-08:2022
        ip3a_3e_base = {'media_type': 'jxsv', 'video_width': 3840, 'video_height': 2160, 'video_interlace': False,
                        'video_exactframerate': '60000/1001', 'min_bit_rate': 746000, 'max_bit_rate': 1991000,
                        'video_depth': 10, 'video_sampling': 'YCbCr-4:4:4', 'video_colorimetry': 'BT2100',
                        'profile': 'High444.12', 'level': '4k-2', 'video_transfer_characteristic': 'SDR',
                        'st2110_21_sender_type': '2110TPW', 'packet_transmission_mode': 'codestream',
                        'capability_set': 'C', 'conformance_level': 'UHD1'}

        interop_point_3a = self._create_interop_point(ip3a_3e_base, {'interop_point': '3a',
                                                                     'video_depth': 8,
                                                                     'video_sampling': 'RGB',
                                                                     'video_colorimetry': 'BT709'})
        interoperability_points.append(interop_point_3a)

        interop_point_3b = self._create_interop_point(ip3a_3e_base, {'interop_point': '3b'})
        interoperability_points.append(interop_point_3b)

        interop_point_3c = self._create_interop_point(ip3a_3e_base, {'interop_point': '3c',
                                                                     'video_transfer_characteristic': 'PQ'})
        interoperability_points.append(interop_point_3c)

        interop_point_3d = self._create_interop_point(ip3a_3e_base, {'interop_point': '3d',
                                                                     'video_transfer_characteristic': 'HLG'})
        interoperability_points.append(interop_point_3d)

        interop_point_3e = self._create_interop_point(ip3a_3e_base, {'interop_point': '3e',
                                                                     'video_sampling': 'RGB',
                                                                     'video_colorimetry': 'BT2020'})
        interoperability_points.append(interop_point_3e)

        return interoperability_points

    def _initialize_capability_set_C_level_UHD2(self):

        interoperability_points = []  # 3 interoperability points defined here

        # Interoperability Points Capability Set C, Conformance Level UHD2 with reference to VSF TR-08:2022
        ip4a_4c_base = {'media_type': 'jxsv', 'video_width': 7680, 'video_height': 4320, 'video_interlace': False,
                        'video_exactframerate': '60000/1001', 'min_bit_rate': 2986000, 'max_bit_rate': 7963000,
                        'video_depth': 10, 'video_sampling': 'YCbCr-4:4:4', 'video_colorimetry': 'BT2100',
                        'profile': 'High444.12', 'level': '8k-2', 'video_transfer_characteristic': 'SDR',
                        'st2110_21_sender_type': '2110TPW', 'packet_transmission_mode': 'codestream',
                        'capability_set': 'C', 'conformance_level': 'UHD2'}

        interop_point_4a = self._create_interop_point(ip4a_4c_base, {'interop_point': '4a'})
        interoperability_points.append(interop_point_4a)

        interop_point_4b = self._create_interop_point(ip4a_4c_base, {'interop_point': '4b',
                                                                     'video_transfer_characteristic': 'PQ'})
        interoperability_points.append(interop_point_4b)

        interop_point_4c = self._create_interop_point(ip4a_4c_base, {'interop_point': '4c',
                                                                     'video_transfer_characteristic': 'HLG'})
        interoperability_points.append(interop_point_4c)

        return interoperability_points

    def _initialize_capability_set_D_level_UHD1(self):

        interoperability_points = []  # 4 interoperability points defined here

        # Interoperability Points Capability Set D, Conformance Level UHD1 with reference to VSF TR-08:2022
        ip1a_1d_base = {'media_type': 'jxsv', 'video_width': 3840, 'video_height': 2160, 'video_interlace': False,
                        'video_exactframerate': '60000/1001', 'min_bit_rate': 746000, 'max_bit_rate': 1989000,
                        'video_depth': 10, 'video_sampling': 'YCbCr-4:2:0', 'video_colorimetry': 'BT2020',
                        'profile': 'High444.12', 'level': '4k-2', 'video_transfer_characteristic': 'SDR',
                        'st2110_21_sender_type': '2110TPW', 'packet_transmission_mode': 'codestream',
                        'capability_set': 'D', 'conformance_level': 'UHD1'}

        interop_point_1a = self._create_interop_point(ip1a_1d_base, {'interop_point': '1a',
                                                                     'video_depth': 8})
        interoperability_points.append(interop_point_1a)

        interop_point_1b = self._create_interop_point(ip1a_1d_base, {'interop_point': '1b',
                                                                     'video_exactframerate': '50',
                                                                     'min_bit_rate': 622000,
                                                                     'max_bit_rate': 1659000,
                                                                     'video_depth': 8})
        interoperability_points.append(interop_point_1b)

        interop_point_1c = self._create_interop_point(ip1a_1d_base, {'interop_point': '1c'})
        interoperability_points.append(interop_point_1c)

        interop_point_1d = self._create_interop_point(ip1a_1d_base, {'interop_point': '1d',
                                                                     'video_depth': 12})
        interoperability_points.append(interop_point_1d)

        return interoperability_points

    def _initialize_capability_set_D_level_UHD2(self):

        interoperability_points = []  # 3 interoperability points defined here

        # Interoperability Points Capability Set D, Conformance Level UHD2 with reference to VSF TR-08:2022
        ip2a_2c_base = {'media_type': 'jxsv', 'video_width': 7680, 'video_height': 4320, 'video_interlace': False,
                        'video_exactframerate': '60000/1001', 'min_bit_rate': 2983000, 'max_bit_rate': 7955000,
                        'video_depth': 10, 'video_sampling': 'YCbCr-4:2:0', 'video_colorimetry': 'BT2100',
                        'profile': 'High444.12', 'level': '8k-2', 'video_transfer_characteristic': 'SDR',
                        'st2110_21_sender_type': '2110TPW', 'packet_transmission_mode': 'codestream',
                        'capability_set': 'D', 'conformance_level': 'UHD2'}

        interop_point_2a = self._create_interop_point(ip2a_2c_base, {'interop_point': '2a'})
        interoperability_points.append(interop_point_2a)

        interop_point_2b = self._create_interop_point(ip2a_2c_base, {'interop_point': '2b',
                                                                     'video_transfer_characteristic': 'PQ'})
        interoperability_points.append(interop_point_2b)

        interop_point_2c = self._create_interop_point(ip2a_2c_base, {'interop_point': '2c',
                                                                     'video_transfer_characteristic': 'HLG'})
        interoperability_points.append(interop_point_2c)

        return interoperability_points

    def _generate_non_JXSV_interop_points(self, size):
        # Non JPEG XS Interoperability Points
        non_jxsv_base = {'media_type': 'raw', 'capability_set': None, 'conformance_level': None}

        interoperability_points = []

        for i in range(0, size):
            interop_point = {**non_jxsv_base, 'interop_point': 'NonJXSV' + str(i)}
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
        param_mapping = {'video_width': 'frame_width', 'video_height': 'frame_height',
                         'profile': 'profile', 'level': 'level', 'sublevel': 'sublevel',
                         'video_colorimetry': 'colorspace', 'bit_rate': 'bit_rate',
                         'video_transfer_characteristic': 'transfer_characteristic'}

        flow_params["media_type"] = "video/" + sdp_params.get("media_type", "raw")

        for sdp_param, flow_param in param_mapping.items():
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

    # Adapted from itertools recipes
    # https://docs.python.org/3/library/itertools.html#itertools-recipes
    def _roundrobin(self, *iterables):
        "roundrobin('ABC', 'D', 'EF') --> A D E B F C"
        # Recipe credited to George Sakkis
        num_active = len(iterables)
        nexts = cycle(iter(it).__next__ for it in iterables)
        while num_active:
            try:
                for next in nexts:
                    yield next()
            except StopIteration:
                # Remove the iterator we just exhausted from the cycle.
                num_active -= 1
                nexts = cycle(islice(nexts, num_active))

    def set_up_tests(self):
        NMOSUtils.RANDOM.seed(a=CONFIG.RANDOM_SEED)

        sender_names = ['rush', 'fly_by_night', 'caress_of_steel', '_2112_', 'all_the_worlds_a_stage',
                        'farewell_to_kings', 'hemispheres', 'permanent_waves', 'moving_pictures', 'exit_stage_left',
                        'signals', 'grace_under_pressure', 'power_windows', 'hold_your_fire', 'show_of_hands',
                        'presto', 'roll_the_bones', 'counterparts', 'test_for_echo', 'different_stages',
                        'vapor_trails', 'feedback', 'snakes_and_ladders', 'clockwork_angels', 'in_rio',
                        'to_revelation', 'trespass', 'nursery_cryme', 'foxtrot', 'by_the_pound',
                        'lamb_lies', 'trick_of_the_tail', 'wind_wuthering', 'were_three', 'duke',
                        'abacab', 'genesis', 'invisible_touch', 'cant_dance', 'all_stations',
                        'murmur', 'reckoning', 'fables', 'rich_pageant', 'document'
                        'green', 'out_of_time', 'automatic', 'monster', 'new_adventures',
                        'up', 'reveal', 'around_the_sun', 'accelerate', 'collapse']

        receiver_names = ['tubular_bells', 'hergest_ridge', 'ommadawn', 'incantations', 'platinum',
                          'qe2', 'five_miles_out', 'crises', 'discovery', 'islands',
                          'earth_moving', 'amarok', 'heavens_open', 'tb2', 'songs_of_distant_earth',
                          'yoyager', 'tb3', 'guitars', 'millenium_bell', 'tres_luna',
                          'tb2003', 'light_shade', 'music_of_the_spheres', 'man_on_the_rocks',
                          'return_to_ommadawn',
                          'piper_at_the_gates', 'saucerful_of_secrets', 'more', 'ummagumma', 'atom_heart_mother',
                          'meddle', 'obscured_by_clouds', 'dark_side', 'wish_you_were_here', 'animals',
                          'the_wall', 'final_cut', 'momentary_lapse', 'division_bell', 'endless_river']

        capability_set_AB_level_FHD = self._initialize_capability_set_AB_level_FHD()
        capability_set_AB_level_UHD1 = self._initialize_capability_set_AB_level_UHD1()
        capability_set_AB_level_UHD2 = self._initialize_capability_set_AB_level_UHD2()
        capability_set_C_level_FHD = self._initialize_capability_set_C_level_FHD()
        capability_set_C_level_UHD1 = self._initialize_capability_set_C_level_UHD1()
        capability_set_C_level_UHD2 = self._initialize_capability_set_C_level_UHD2()
        capability_set_D_level_UHD1 = self._initialize_capability_set_D_level_UHD1()
        capability_set_D_level_UHD2 = self._initialize_capability_set_D_level_UHD2()

        NMOSUtils.RANDOM.shuffle(capability_set_AB_level_FHD)
        NMOSUtils.RANDOM.shuffle(capability_set_AB_level_UHD1)
        NMOSUtils.RANDOM.shuffle(capability_set_AB_level_UHD2)
        NMOSUtils.RANDOM.shuffle(capability_set_C_level_FHD)
        NMOSUtils.RANDOM.shuffle(capability_set_C_level_UHD1)
        NMOSUtils.RANDOM.shuffle(capability_set_C_level_UHD2)
        NMOSUtils.RANDOM.shuffle(capability_set_D_level_UHD1)
        NMOSUtils.RANDOM.shuffle(capability_set_D_level_UHD2)

        interleaved_interop_points = self._roundrobin(capability_set_AB_level_FHD,
                                                      capability_set_AB_level_UHD1,
                                                      capability_set_AB_level_UHD2,
                                                      capability_set_C_level_FHD,
                                                      capability_set_C_level_UHD1,
                                                      capability_set_C_level_UHD2,
                                                      capability_set_D_level_UHD1,
                                                      capability_set_D_level_UHD2)

        interoperability_points = [i for i in interleaved_interop_points]

        sender_configurations = [('AB', 'FHD'), ('AB', 'UHD1'), ('AB', 'UHD2'),
                                 ('C', 'FHD'), ('C', 'UHD1'), ('C', 'UHD2'),
                                 ('D', 'UHD1'), ('D', 'UHD2')]

        sender_count = len(interoperability_points) if not CONFIG.MAX_TEST_ITERATIONS \
            else max(CONFIG.MAX_TEST_ITERATIONS, len(sender_configurations))

        sender_interop_points = interoperability_points[:sender_count].copy()

        # pad with video raw Senders
        VIDEO_RAW_SENDER_COUNT = 3
        sender_interop_points.extend(self._generate_non_JXSV_interop_points(VIDEO_RAW_SENDER_COUNT))

        self.senders.clear()

        NMOSUtils.RANDOM.shuffle(sender_names)
        NMOSUtils.RANDOM.shuffle(sender_interop_points)
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

        NMOSUtils.RANDOM.shuffle(receiver_names)
        NMOSUtils.RANDOM.shuffle(capability_configurations)
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
        # Controllers MUST support IS-04 to discover JPEG XS Senders

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

            candidate_senders = NMOSUtils.RANDOM.sample(jpeg_xs_senders,
                                                        NMOSUtils.RANDOM.randint(1,
                                                                                 min(CANDIDATE_SENDER_COUNT,
                                                                                     len(jpeg_xs_senders))))
            if len(candidate_senders) < CANDIDATE_SENDER_COUNT:
                candidate_senders.extend(NMOSUtils.RANDOM.sample(video_raw_senders,
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
        # Controllers MUST support IS-04 to discover JPEG XS Receivers

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

            candidate_receivers = NMOSUtils.RANDOM.sample(jpeg_xs_receivers,
                                                          NMOSUtils.RANDOM.randint(1, min(CANDIDATE_RECEIVER_COUNT,
                                                                                   len(jpeg_xs_receivers))))
            if len(candidate_receivers) < CANDIDATE_RECEIVER_COUNT:
                candidate_receivers.extend(NMOSUtils.RANDOM.sample(video_raw_receivers,
                                                                   min(CANDIDATE_RECEIVER_COUNT
                                                                       - len(candidate_receivers),
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

    def test_03(self, test):
        """
        Ensure NCuT can identify JPEG XS Receiver compatibility according to TR-08 Capability Set and Conformance Level
        """
        # Indentify compatible Receivers given a random Sender.
        # Sender and Recievers have SDP/caps as specifiied in TR-08.

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

                candidate_receivers = NMOSUtils.RANDOM.sample(compatible_receviers,
                                                              NMOSUtils.RANDOM.randint(
                                                                  1,
                                                                  min(MAX_COMPATIBLE_RECEIVER_COUNT,
                                                                      len(compatible_receviers))))
                if len(candidate_receivers) < CANDIDATE_RECEIVER_COUNT:
                    candidate_receivers.extend(NMOSUtils.RANDOM.sample(other_receivers,
                                                                       min(CANDIDATE_RECEIVER_COUNT
                                                                           - len(candidate_receivers),
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
                    return test.FAIL('Incorrect Receiver identified for Compatibility Set ' + sender['capability_set']
                                     + ', Conformance Level ' + sender['conformance_level']
                                     + ' and Interoperability Point ' + sender['interop_point'])
                else:
                    for answer in actual_answers:
                        if answer not in expected_answers:
                            return test.FAIL('Incorrect Receiver identified for Compatibility Set '
                                             + sender['capability_set']
                                             + ', Conformance Level ' + sender['conformance_level']
                                             + ' and Interoperability Point ' + sender['interop_point'])

            return test.PASS('All Receivers correctly identified')

        except TestingFacadeException as e:
            return test.UNCLEAR(e.args[0])

    def test_04(self, test):
        """
        Ensure NCuT can identify JPEG XS Sender compatibility according to TR-08 Capability Set and Conformance Level
        """
        # Indentify compatible Receivers given a random Sender.
        # Sender and Recievers have SDP/caps as specifiied in TR-08

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

                candidate_senders = NMOSUtils.RANDOM.sample(compatible_senders,
                                                            NMOSUtils.RANDOM.randint(
                                                                1, min(MAX_COMPATIBLE_SENDER_COUNT,
                                                                       len(compatible_senders))))
                if len(candidate_senders) < CANDIDATE_SENDER_COUNT:
                    candidate_senders.extend(NMOSUtils.RANDOM.sample(other_senders,
                                                                     min(CANDIDATE_SENDER_COUNT
                                                                         - len(candidate_senders),
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
                    return test.FAIL('Incorrect Sender identified for Compatibility Set(s) '
                                     + str(receiver['capability_set'])
                                     + ', Conformance Level ' + receiver['conformance_level'])
                else:
                    for answer in actual_answers:
                        if answer not in expected_answers:
                            return test.FAIL('Incorrect Sender identified for Compatibility Set(s) '
                                             + str(receiver['capability_set'])
                                             + ', Conformance Level ' + receiver['conformance_level'])

            return test.PASS('All Senders correctly identified')

        except TestingFacadeException as e:
            return test.UNCLEAR(e.args[0])
