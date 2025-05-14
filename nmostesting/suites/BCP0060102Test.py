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

QUERY_API_KEY = "query"


class BCP0060102Test(ControllerTest):
    """
    Runs Controller Tests covering BCP-006-01
    """
    def __init__(self, apis, registries, node, dns_server, **kwargs):
        ControllerTest.__init__(self, apis, registries, node, dns_server, **kwargs)

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
        ip1_6c_base = {'media_type': 'video/jxsv',
                       'width': 1920, 'height': 1080, 'interlace': False,
                       'exactframerate': '60000/1001', 'min_bit_rate': 186000, 'max_bit_rate': 497000,
                       'depth': 10, 'sampling': 'YCbCr-4:2:2', 'colorimetry': 'BT709',
                       'profile': 'High444.12', 'level': '2k-1', 'TCS': 'SDR',
                       'TP': '2110TPW',
                       'capability_set': 'A/B', 'conformance_level': 'FHD'}

        interop_point_1 = self._create_interop_point(ip1_6c_base, {'interop_point': '1',
                                                                   'width': 1280,
                                                                   'height': 720,
                                                                   'min_bit_rate': 83000,
                                                                   'max_bit_rate': 221000,
                                                                   'level': '1k-1'})
        interoperability_points.append(interop_point_1)

        interop_point_2 = self._create_interop_point(ip1_6c_base, {'interop_point': '2',
                                                                   'width': 1280,
                                                                   'height': 720,
                                                                   'exactframerate': '50',
                                                                   'min_bit_rate': 69000,
                                                                   'max_bit_rate': 184000,
                                                                   'level': '1k-1'})
        interoperability_points.append(interop_point_2)

        interop_point_3 = self._create_interop_point(ip1_6c_base, {'interop_point': '3',
                                                                   'exactframerate': '30000/1001',
                                                                   'interlace': True,
                                                                   'min_bit_rate': 93000,
                                                                   'max_bit_rate': 249000})
        interoperability_points.append(interop_point_3)

        interop_point_4 = self._create_interop_point(ip1_6c_base, {'interop_point': '4',
                                                                   'exactframerate': '25',
                                                                   'interlace': True,
                                                                   'min_bit_rate': 78000,
                                                                   'max_bit_rate': 207000})
        interoperability_points.append(interop_point_4)

        interop_point_5a = self._create_interop_point(ip1_6c_base, {'interop_point': '5a'})
        interoperability_points.append(interop_point_5a)

        interop_point_5b = self._create_interop_point(ip1_6c_base, {'interop_point': '5b',
                                                                    'colorimetry': 'BT2100',
                                                                    'TCS': 'PQ'})
        interoperability_points.append(interop_point_5b)

        interop_point_5c = self._create_interop_point(ip1_6c_base, {'interop_point': '5c',
                                                                    'colorimetry': 'BT2100',
                                                                    'TCS': 'HLG'})
        interoperability_points.append(interop_point_5c)

        interop_point_6a = self._create_interop_point(ip1_6c_base, {'interop_point': '6a',
                                                                    'exactframerate': '50',
                                                                    'min_bit_rate': 156000,
                                                                    'max_bit_rate': 415000})
        interoperability_points.append(interop_point_6a)

        interop_point_6b = self._create_interop_point(ip1_6c_base, {'interop_point': '6b',
                                                                    'exactframerate': '50',
                                                                    'min_bit_rate': 156000,
                                                                    'max_bit_rate': 415000,
                                                                    'colorimetry': 'BT2100',
                                                                    'TCS': 'PQ'})
        interoperability_points.append(interop_point_6b)

        interop_point_6c = self._create_interop_point(ip1_6c_base, {'interop_point': '6c',
                                                                    'exactframerate': '50',
                                                                    'min_bit_rate': 156000,
                                                                    'max_bit_rate': 415000,
                                                                    'colorimetry': 'BT2100',
                                                                    'TCS': 'HLG'})
        interoperability_points.append(interop_point_6c)

        return interoperability_points

    def _initialize_capability_set_AB_level_UHD1(self):

        interoperability_points = []  # 6 interoperability points defined here

        # Interoperability Points Capability Set A & Set B, Conformance Level UHD1 with reference to VSF TR-08:2022
        # NOTE: Set A & Set B have the same metadata as currently IS-04 doesn't distinguish between
        # ST 2110-21 Type A and Type W Receivers
        ip7a_8c_base = {'media_type': 'video/jxsv',
                        'width': 3840, 'height': 2160, 'interlace': False,
                        'exactframerate': '60000/1001', 'min_bit_rate': 746000, 'max_bit_rate': 1989000,
                        'depth': 10, 'sampling': 'YCbCr-4:2:2', 'colorimetry': 'BT2100',
                        'profile': 'High444.12', 'level': '4k-2', 'TCS': 'SDR',
                        'TP': '2110TPW',
                        'capability_set': 'A/B', 'conformance_level': 'UHD1'}

        interop_point_7a = self._create_interop_point(ip7a_8c_base, {'interop_point': '7a',
                                                                     'colorimetry': 'BT2020'})
        interoperability_points.append(interop_point_7a)

        interop_point_7b = self._create_interop_point(ip7a_8c_base, {'interop_point': '7b',
                                                                     'TCS': 'PQ'})
        interoperability_points.append(interop_point_7b)

        interop_point_7c = self._create_interop_point(ip7a_8c_base, {'interop_point': '7c',
                                                                     'TCS': 'HLG'})
        interoperability_points.append(interop_point_7c)

        interop_point_8a = self._create_interop_point(ip7a_8c_base, {'interop_point': '8a',
                                                                     'exactframerate': '50',
                                                                     'min_bit_rate': 622000,
                                                                     'max_bit_rate': 1659000,
                                                                     'colorimetry': 'BT2020'})
        interoperability_points.append(interop_point_8a)

        interop_point_8b = self._create_interop_point(ip7a_8c_base, {'interop_point': '8b',
                                                                     'exactframerate': '50',
                                                                     'min_bit_rate': 622000,
                                                                     'max_bit_rate': 1659000,
                                                                     'TCS': 'PQ'})
        interoperability_points.append(interop_point_8b)

        interop_point_8c = self._create_interop_point(ip7a_8c_base, {'interop_point': '8c',
                                                                     'exactframerate': '50',
                                                                     'min_bit_rate': 622000,
                                                                     'max_bit_rate': 1659000,
                                                                     'TCS': 'HLG'})
        interoperability_points.append(interop_point_8c)

        return interoperability_points

    def _initialize_capability_set_AB_level_UHD2(self):

        interoperability_points = []  # 6 interoperability points defined here

        # Interoperability Points Capability Set A & Set B, Conformance Level UHD2 with reference to VSF TR-08:2022
        # NOTE: Set A & Set B have the same metadata as currently IS-04 doesn't distinguish between
        # ST 2110-21 Type A and Type W Receivers
        ip9a_10c_base = {'media_type': 'video/jxsv',
                         'width': 7680, 'height': 4320, 'interlace': False,
                         'exactframerate': '60000/1001', 'min_bit_rate': 2983000, 'max_bit_rate': 7955000,
                         'depth': 10, 'sampling': 'YCbCr-4:2:2', 'colorimetry': 'BT2100',
                         'profile': 'High444.12', 'level': '8k-2', 'TCS': 'SDR',
                         'TP': '2110TPW',
                         'capability_set': 'A/B', 'conformance_level': 'UHD2'}

        interop_point_9a = self._create_interop_point(ip9a_10c_base, {'interop_point': '9a',
                                                                      'colorimetry': 'BT2020'})
        interoperability_points.append(interop_point_9a)

        interop_point_9b = self._create_interop_point(ip9a_10c_base, {'interop_point': '9b',
                                                                      'TCS': 'PQ'})
        interoperability_points.append(interop_point_9b)

        interop_point_9c = self._create_interop_point(ip9a_10c_base, {'interop_point': '9c',
                                                                      'TCS': 'HLG'})
        interoperability_points.append(interop_point_9c)

        interop_point_10a = self._create_interop_point(ip9a_10c_base, {'interop_point': '10a',
                                                                       'exactframerate': '50',
                                                                       'min_bit_rate': 2488000,
                                                                       'max_bit_rate': 6636000,
                                                                       'colorimetry': 'BT2020'})
        interoperability_points.append(interop_point_10a)

        interop_point_10b = self._create_interop_point(ip9a_10c_base, {'interop_point': '10b',
                                                                       'exactframerate': '50',
                                                                       'min_bit_rate': 2488000,
                                                                       'max_bit_rate': 6636000,
                                                                       'TCS': 'PQ'})
        interoperability_points.append(interop_point_10b)

        interop_point_10c = self._create_interop_point(ip9a_10c_base, {'interop_point': '10c',
                                                                       'exactframerate': '50',
                                                                       'min_bit_rate': 2488000,
                                                                       'max_bit_rate': 6636000,
                                                                       'TCS': 'HLG'})
        interoperability_points.append(interop_point_10c)

        return interoperability_points

    def _initialize_capability_set_C_level_FHD(self):

        interoperability_points = []  # 6 interoperability points defined here

        # Interoperability Points Capability Set C, Conformance Level FHD with reference to VSF TR-08:2022
        ip1a_2b_base = {'media_type': 'video/jxsv',
                        'width': 1920, 'height': 1080, 'interlace': False,
                        'exactframerate': '60000/1001', 'min_bit_rate': 186000, 'max_bit_rate': 497000,
                        'depth': 8, 'sampling': 'RGB', 'colorimetry': 'BT709',
                        'profile': 'High444.12', 'level': '2k-1', 'TCS': 'SDR',
                        'TP': '2110TPW',
                        'capability_set': 'C', 'conformance_level': 'FHD'}

        interop_point_1a = self._create_interop_point(ip1a_2b_base, {'interop_point': '1a'})
        interoperability_points.append(interop_point_1a)

        interop_point_1b = self._create_interop_point(ip1a_2b_base, {'interop_point': '1b',
                                                                     'exactframerate': '50',
                                                                     'min_bit_rate': 156000,
                                                                     'max_bit_rate': 415000})
        interoperability_points.append(interop_point_1b)

        interop_point_1c = self._create_interop_point(ip1a_2b_base, {'interop_point': '1c',
                                                                     'exactframerate': '60',
                                                                     'min_bit_rate': 187000,
                                                                     'max_bit_rate': 498000,
                                                                     'depth': 10})
        interoperability_points.append(interop_point_1c)

        interop_point_1d = self._create_interop_point(ip1a_2b_base, {'interop_point': '1d',
                                                                     'sampling': 'YCbCr-4:4:4'})
        interoperability_points.append(interop_point_1d)

        interop_point_2a = self._create_interop_point(ip1a_2b_base, {'interop_point': '2a',
                                                                     'height': 1200,
                                                                     'exactframerate': '60',
                                                                     'min_bit_rate': 207000,
                                                                     'max_bit_rate': 552000,
                                                                     'RANGE': 'FULL',
                                                                     'level': '4k-1'})
        interoperability_points.append(interop_point_2a)

        interop_point_2b = self._create_interop_point(ip1a_2b_base, {'interop_point': '2b',
                                                                     'height': 1200,
                                                                     'exactframerate': '50',
                                                                     'min_bit_rate': 173000,
                                                                     'max_bit_rate': 461000,
                                                                     'RANGE': 'FULL',
                                                                     'level': '4k-1'})
        interoperability_points.append(interop_point_2b)

        return interoperability_points

    def _initialize_capability_set_C_level_UHD1(self):

        interoperability_points = []  # 5 interoperability points defined here

        # Interoperability Points Capability Set C, Conformance Level UHD1 with reference to VSF TR-08:2022
        ip3a_3e_base = {'media_type': 'video/jxsv',
                        'width': 3840, 'height': 2160, 'interlace': False,
                        'exactframerate': '60000/1001', 'min_bit_rate': 746000, 'max_bit_rate': 1991000,
                        'depth': 10, 'sampling': 'YCbCr-4:4:4', 'colorimetry': 'BT2100',
                        'profile': 'High444.12', 'level': '4k-2', 'TCS': 'SDR',
                        'TP': '2110TPW',
                        'capability_set': 'C', 'conformance_level': 'UHD1'}

        interop_point_3a = self._create_interop_point(ip3a_3e_base, {'interop_point': '3a',
                                                                     'depth': 8,
                                                                     'sampling': 'RGB',
                                                                     'colorimetry': 'BT709'})
        interoperability_points.append(interop_point_3a)

        interop_point_3b = self._create_interop_point(ip3a_3e_base, {'interop_point': '3b'})
        interoperability_points.append(interop_point_3b)

        interop_point_3c = self._create_interop_point(ip3a_3e_base, {'interop_point': '3c',
                                                                     'TCS': 'PQ'})
        interoperability_points.append(interop_point_3c)

        interop_point_3d = self._create_interop_point(ip3a_3e_base, {'interop_point': '3d',
                                                                     'TCS': 'HLG'})
        interoperability_points.append(interop_point_3d)

        interop_point_3e = self._create_interop_point(ip3a_3e_base, {'interop_point': '3e',
                                                                     'sampling': 'RGB',
                                                                     'colorimetry': 'BT2020'})
        interoperability_points.append(interop_point_3e)

        return interoperability_points

    def _initialize_capability_set_C_level_UHD2(self):

        interoperability_points = []  # 3 interoperability points defined here

        # Interoperability Points Capability Set C, Conformance Level UHD2 with reference to VSF TR-08:2022
        ip4a_4c_base = {'media_type': 'video/jxsv',
                        'width': 7680, 'height': 4320, 'interlace': False,
                        'exactframerate': '60000/1001', 'min_bit_rate': 2986000, 'max_bit_rate': 7963000,
                        'depth': 10, 'sampling': 'YCbCr-4:4:4', 'colorimetry': 'BT2100',
                        'profile': 'High444.12', 'level': '8k-2', 'TCS': 'SDR',
                        'TP': '2110TPW',
                        'capability_set': 'C', 'conformance_level': 'UHD2'}

        interop_point_4a = self._create_interop_point(ip4a_4c_base, {'interop_point': '4a'})
        interoperability_points.append(interop_point_4a)

        interop_point_4b = self._create_interop_point(ip4a_4c_base, {'interop_point': '4b',
                                                                     'TCS': 'PQ'})
        interoperability_points.append(interop_point_4b)

        interop_point_4c = self._create_interop_point(ip4a_4c_base, {'interop_point': '4c',
                                                                     'TCS': 'HLG'})
        interoperability_points.append(interop_point_4c)

        return interoperability_points

    def _initialize_capability_set_D_level_UHD1(self):

        interoperability_points = []  # 4 interoperability points defined here

        # Interoperability Points Capability Set D, Conformance Level UHD1 with reference to VSF TR-08:2022
        ip1a_1d_base = {'media_type': 'video/jxsv',
                        'width': 3840, 'height': 2160, 'interlace': False,
                        'exactframerate': '60000/1001', 'min_bit_rate': 746000, 'max_bit_rate': 1989000,
                        'depth': 10, 'sampling': 'YCbCr-4:2:0', 'colorimetry': 'BT2020',
                        'profile': 'High444.12', 'level': '4k-2', 'TCS': 'SDR',
                        'TP': '2110TPW',
                        'capability_set': 'D', 'conformance_level': 'UHD1'}

        interop_point_1a = self._create_interop_point(ip1a_1d_base, {'interop_point': '1a',
                                                                     'depth': 8})
        interoperability_points.append(interop_point_1a)

        interop_point_1b = self._create_interop_point(ip1a_1d_base, {'interop_point': '1b',
                                                                     'exactframerate': '50',
                                                                     'min_bit_rate': 622000,
                                                                     'max_bit_rate': 1659000,
                                                                     'depth': 8})
        interoperability_points.append(interop_point_1b)

        interop_point_1c = self._create_interop_point(ip1a_1d_base, {'interop_point': '1c'})
        interoperability_points.append(interop_point_1c)

        interop_point_1d = self._create_interop_point(ip1a_1d_base, {'interop_point': '1d',
                                                                     'depth': 12})
        interoperability_points.append(interop_point_1d)

        return interoperability_points

    def _initialize_capability_set_D_level_UHD2(self):

        interoperability_points = []  # 3 interoperability points defined here

        # Interoperability Points Capability Set D, Conformance Level UHD2 with reference to VSF TR-08:2022
        ip2a_2c_base = {'media_type': 'video/jxsv',
                        'width': 7680, 'height': 4320, 'interlace': False,
                        'exactframerate': '60000/1001', 'min_bit_rate': 2983000, 'max_bit_rate': 7955000,
                        'depth': 10, 'sampling': 'YCbCr-4:2:0', 'colorimetry': 'BT2100',
                        'profile': 'High444.12', 'level': '8k-2', 'TCS': 'SDR',
                        'TP': '2110TPW',
                        'capability_set': 'D', 'conformance_level': 'UHD2'}

        interop_point_2a = self._create_interop_point(ip2a_2c_base, {'interop_point': '2a'})
        interoperability_points.append(interop_point_2a)

        interop_point_2b = self._create_interop_point(ip2a_2c_base, {'interop_point': '2b',
                                                                     'TCS': 'PQ'})
        interoperability_points.append(interop_point_2b)

        interop_point_2c = self._create_interop_point(ip2a_2c_base, {'interop_point': '2c',
                                                                     'TCS': 'HLG'})
        interoperability_points.append(interop_point_2c)

        return interoperability_points

    def _generate_non_JXSV_interop_points(self, size):
        # Non JPEG XS Interoperability Points
        non_jxsv_base = {'media_type': 'video/raw', 'capability_set': None, 'conformance_level': None}

        interoperability_points = []

        for i in range(0, size):
            interop_point = {**non_jxsv_base, 'interop_point': 'NonJXSV' + str(i)}
            interoperability_points.append(interop_point)

        return interoperability_points

    def _generate_constraint_set(self, sdp_params):

        sdp_params = {**CONFIG.SDP_PREFERENCES, **sdp_params}

        split_exactframerate = sdp_params.get('exactframerate').split('/')

        constraint_set = {
            'urn:x-nmos:cap:format:color_sampling': {
                'enum': [sdp_params.get('sampling')]
            },
            'urn:x-nmos:cap:format:frame_height': {
                'enum': [sdp_params.get('height')]
            },
            'urn:x-nmos:cap:format:frame_width': {
                'enum': [sdp_params.get('width')]
            },
            'urn:x-nmos:cap:format:grain_rate': {
                'enum': [{
                            'denominator': int(split_exactframerate[1]) if 1 < len(split_exactframerate) else 1,
                            'numerator': int(split_exactframerate[0])
                        }]
            },
            'urn:x-nmos:cap:format:interlace_mode': {
                'enum': [
                    'interlaced_bff',
                    'interlaced_tff',
                    'interlaced_psf'
                ] if sdp_params.get('interlace') else [
                    'progressive'
                ]
            },
            'urn:x-nmos:cap:format:component_depth': {
                'enum': [sdp_params.get('depth')]
            },
            'urn:x-nmos:cap:format:colorspace': {
                'enum': [sdp_params.get('colorimetry')]
            },
            'urn:x-nmos:cap:format:transfer_characteristic': {
                'enum': [sdp_params.get('TCS')]
            }
        }

        # JPEG XS specific caps
        if 'profile' in sdp_params and 'level' in sdp_params:
            constraint_set.update({'urn:x-nmos:cap:format:profile': {'enum': [sdp_params.get('profile')]},
                                   'urn:x-nmos:cap:format:level': {'enum': [sdp_params.get('level')]},
                                   'urn:x-nmos:cap:format:sublevel': {'enum': ['Sublev3bpp', 'Sublev4bpp']},
                                   'urn:x-nmos:cap:transport:packet_transmission_mode': {'enum': ['codestream']},
                                   'urn:x-nmos:cap:format:bit_rate': {'minimum': sdp_params.get('min_bit_rate'),
                                                                      'maximum': sdp_params.get('max_bit_rate')},
                                   'urn:x-nmos:cap:transport:st2110_21_sender_type': {
                                       'enum': ['2110TN', '2110TNL', '2110TPW']}})
        return constraint_set

    # convert sdp_params into Receiver caps
    def _generate_caps(self, sdp_params_set):

        caps = {
            'media_types': [],
            'constraint_sets': [],
            'version': NMOSUtils.get_TAI_time()
        }

        for sdp_params in sdp_params_set:
            media_type = sdp_params.get('media_type', 'video/raw')
            if media_type not in caps['media_types']:
                caps['media_types'].append(media_type)

            caps['constraint_sets'].append(self._generate_constraint_set(sdp_params))

        return caps

    # convert sdp_params into Flow parameters
    def _generate_flow_params(self, sdp_params):
        flow_params = {}

        # Mapping sdp_params names to flow_params names
        param_mapping = {'width': 'frame_width', 'height': 'frame_height',
                         'profile': 'profile', 'level': 'level', 'sublevel': 'sublevel',
                         'colorimetry': 'colorspace', 'bit_rate': 'bit_rate',
                         'TCS': 'transfer_characteristic'}

        flow_params['media_type'] = sdp_params.get('media_type', 'video/raw')

        for sdp_param, flow_param in param_mapping.items():
            if sdp_param in sdp_params:
                flow_params[flow_param] = sdp_params[sdp_param]

        flow_params['interlace_mode'] = 'interlaced_tff' \
            if sdp_params.get('interlace') else 'progressive'

        if 'exactframerate' in sdp_params:
            split_exactframerate = sdp_params['exactframerate'].split('/')
            flow_params['grain_rate'] = {
                'denominator': int(split_exactframerate[1]) if 1 < len(split_exactframerate) else 1,
                'numerator': int(split_exactframerate[0])
            }
        if 'sampling' in sdp_params:
            frame_width = sdp_params['width']
            frame_height = sdp_params['height']
            component_depth = sdp_params['depth']
            if sdp_params['sampling'] == 'YCbCr-4:2:2':
                flow_params['components'] = [
                    {'name': 'Y',  'width': frame_width, 'height': frame_height, 'bit_depth': component_depth},
                    {'name': 'Cb', 'width': frame_width//2, 'height': frame_height, 'bit_depth': component_depth},
                    {'name': 'Cr', 'width': frame_width//2, 'height': frame_height, 'bit_depth': component_depth},
                ]
            elif sdp_params['sampling'] == 'YCbCr-4:2:0':
                flow_params['components'] = [
                    {'name': 'Y',  'width': frame_width, 'height': frame_height, 'bit_depth': component_depth},
                    {'name': 'Cb', 'width': frame_width//2, 'height': frame_height//2, 'bit_depth': component_depth},
                    {'name': 'Cr', 'width': frame_width//2, 'height': frame_height//2, 'bit_depth': component_depth},
                ]
            elif sdp_params['sampling'] == 'RGB':
                flow_params['components'] = [
                    {'name': 'R',  'width': frame_width, 'height': frame_height, 'bit_depth': component_depth},
                    {'name': 'G', 'width': frame_width, 'height': frame_height, 'bit_depth': component_depth},
                    {'name': 'B', 'width': frame_width, 'height': frame_height, 'bit_depth': component_depth},
                ]
            elif sdp_params['sampling'] == 'YCbCr-4:4:4':
                flow_params['components'] = [
                    {'name': 'Y',  'width': frame_width, 'height': frame_height, 'bit_depth': component_depth},
                    {'name': 'Cb', 'width': frame_width, 'height': frame_height, 'bit_depth': component_depth},
                    {'name': 'Cr', 'width': frame_width, 'height': frame_height, 'bit_depth': component_depth},
                ]

        return flow_params

    def _is_compatible(self, sender, receiver):
        # Notes on TR-08 Compatibility of Senders and Receivers
        # Set A and Set B are not distinguished here and are denoted as Set A/B
        # For a particular conformance level (FHD, UHD1, UHD2):
        # * A/B Senders are compatible with: [A/B, C, D] Receivers
        # * C   Senders are compatible with: [C, D] Receivers
        # * D   Senders are compatible with: [D] Receivers
        receiver_capability_sets = {
            'A/B': ['A/B'],
            'C':   ['A/B', 'C'],
            'D':   ['A/B', 'C', 'D'],
            None:  [None]
        }
        if sender.get('conformance_level') == receiver.get('conformance_level'):

            if sender.get('capability_set') in receiver_capability_sets[receiver['capability_set']]:
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
                        'abacab', 'genesis', 'invisible_touch', 'cant_dance',
                        'murmur', 'reckoning', 'fables', 'rich_pageant', 'document',
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

        capability_sets = [capability_set_AB_level_FHD,
                           capability_set_AB_level_UHD1,
                           capability_set_AB_level_UHD2,
                           capability_set_C_level_FHD,
                           capability_set_C_level_UHD1,
                           capability_set_C_level_UHD2,
                           capability_set_D_level_UHD1,
                           capability_set_D_level_UHD2]
        interleaved_interop_points = self._roundrobin(*capability_sets)

        interoperability_points = [i for i in interleaved_interop_points]

        sender_interop_points = interoperability_points.copy()

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

        # pad configurations with some video/raw (None, None) configurations
        capability_configurations = [('A/B', 'FHD'), ('A/B', 'UHD1'), ('A/B', 'UHD2'),
                                     ('C', 'FHD'), ('C', 'UHD1'), ('C', 'UHD2'),
                                     ('D', 'UHD1'), ('D', 'UHD2'),
                                     (None, None), (None, None), (None, None)]

        self.receivers.clear()

        NMOSUtils.RANDOM.shuffle(receiver_names)
        NMOSUtils.RANDOM.shuffle(capability_configurations)
        for idx, (receiver_name, (capability_set, conformance_level)) in \
                enumerate(zip(receiver_names, capability_configurations)):
            receiver = {
                'label': 'r' + str(idx) + '/' + receiver_name,
                'description': 'Mock Receiver ' + str(idx),
                'connectable': True,
                'registered': True,
                'capability_set': capability_set,
                'conformance_level': conformance_level
            }
            caps = [i for i in interoperability_points if self._is_compatible(i, receiver)]
            receiver['caps'] = self._generate_caps(caps) if caps else {'media_types': ['video/raw']}
            self.receivers.append(receiver)

        ControllerTest.set_up_tests(self)

    def test_01(self, test):
        """
        Ensure NCuT can identify JPEG XS Senders
        """
        # Controllers MUST support IS-04 to discover JPEG XS Senders

        MAX_COMPATIBLE_SENDER_COUNT = 3
        CANDIDATE_SENDER_COUNT = 4

        try:
            # Identify capable Senders
            question = """\
                       The NCuT should be able to discover JPEG XS capable Senders \
                       that are registered in the Registry.

                       Refresh the NCuT's view of the Registry and carefully select the Senders \
                       that are JPEG XS capable from the following list.

                       Once capable Senders have been identified press 'Submit'. If unable \
                       to identify capable Senders, press 'Submit' without making a selection.
                       """

            jpeg_xs_senders = [s for s in self.senders if 'video/jxsv' == s['sdp_params']['media_type']]
            video_raw_senders = [s for s in self.senders if 'video/raw' == s['sdp_params']['media_type']]

            jpeg_xs_sender_count = NMOSUtils.RANDOM.randint(1, min(MAX_COMPATIBLE_SENDER_COUNT, len(jpeg_xs_senders)))
            candidate_senders = NMOSUtils.RANDOM.sample(jpeg_xs_senders, jpeg_xs_sender_count)

            if len(candidate_senders) < CANDIDATE_SENDER_COUNT:
                other_sender_count = min(CANDIDATE_SENDER_COUNT - len(candidate_senders), len(video_raw_senders))
                candidate_senders.extend(NMOSUtils.RANDOM.sample(video_raw_senders, other_sender_count))

            candidate_senders.sort(key=itemgetter('label'))

            possible_answers = [{'answer_id': 'answer_'+str(i), 'display_answer': r['display_answer'],
                                'resource': {'id': r['id'], 'label': r['label'], 'description': r['description']}}
                                for i, r in enumerate(candidate_senders)]
            expected_answers = ['answer_'+str(i) for i, r in enumerate(candidate_senders)
                                if 'video/jxsv' == r['sdp_params']['media_type']]

            actual_answers = self.testing_facade_utils.invoke_testing_facade(
                question, possible_answers, test_type='multi_choice')['answer_response']

            actual = set(actual_answers)
            expected = set(expected_answers)

            if expected - actual:
                return test.FAIL('Not all capable Senders identified')
            elif actual - expected:
                return test.FAIL('Senders incorrectly identified as capable')

            return test.PASS('All capable Senders correctly identified')

        except TestingFacadeException as e:
            return test.UNCLEAR(e.args[0])

    def test_02(self, test):
        """
        Ensure NCuT can identify JPEG XS Receivers
        """
        # Controllers MUST support IS-04 to discover JPEG XS Receivers

        MAX_COMPATIBLE_RECEIVER_COUNT = 3
        CANDIDATE_RECEIVER_COUNT = 4

        try:
            # Identify capable Receivers
            question = """\
                       The NCuT should be able to discover JPEG XS capable Receivers \
                       that are registered in the Registry.

                       Refresh the NCuT's view of the Registry and carefully select the Receivers \
                       that are JPEG XS capable from the following list.

                       Once capable Receivers have been identified press 'Submit'. If unable \
                       to identify capable Receivers, press 'Submit' without making a selection.
                       """

            jpeg_xs_receivers = [r for r in self.receivers if 'video/jxsv' in r['caps']['media_types']]
            video_raw_receivers = [r for r in self.receivers if 'video/raw' in r['caps']['media_types']]

            jpeg_xs_receiver_count = NMOSUtils.RANDOM.randint(1, min(MAX_COMPATIBLE_RECEIVER_COUNT,
                                                                     len(jpeg_xs_receivers)))
            candidate_receivers = NMOSUtils.RANDOM.sample(jpeg_xs_receivers, jpeg_xs_receiver_count)

            if len(candidate_receivers) < CANDIDATE_RECEIVER_COUNT:
                other_receiver_count = min(CANDIDATE_RECEIVER_COUNT - len(candidate_receivers),
                                           len(video_raw_receivers))
                candidate_receivers.extend(NMOSUtils.RANDOM.sample(video_raw_receivers, other_receiver_count))

            candidate_receivers.sort(key=itemgetter('label'))

            possible_answers = [{'answer_id': 'answer_'+str(i), 'display_answer': r['display_answer'],
                                'resource': {'id': r['id'], 'label': r['label'], 'description': r['description']}}
                                for i, r in enumerate(candidate_receivers)]
            expected_answers = ['answer_'+str(i) for i, r in enumerate(candidate_receivers)
                                if 'video/jxsv' in r['caps']['media_types']]

            actual_answers = self.testing_facade_utils.invoke_testing_facade(
                question, possible_answers, test_type='multi_choice')['answer_response']

            actual = set(actual_answers)
            expected = set(expected_answers)

            if expected - actual:
                return test.FAIL('Not all capable Receivers identified')
            elif actual - expected:
                return test.FAIL('Receivers incorrectly identified as capable')

            return test.PASS('All capable Receivers correctly identified')

        except TestingFacadeException as e:
            return test.UNCLEAR(e.args[0])

    def test_03(self, test):
        """
        Ensure NCuT can identify JPEG XS Receiver compatibility according to TR-08 Capability Set and Conformance Level
        """
        # Identify compatible Receivers given a random Sender.
        # Sender and Receivers have SDP/caps as specified in TR-08.

        MAX_COMPATIBLE_RECEIVER_COUNT = 4
        CANDIDATE_RECEIVER_COUNT = 6

        try:
            sender_iterations = CONFIG.MAX_TEST_ITERATIONS if CONFIG.MAX_TEST_ITERATIONS else len(self.senders)

            jxsv_senders = [s for s in self.senders
                            if s['capability_set'] is not None
                            and s['conformance_level'] is not None][:sender_iterations]

            NMOSUtils.RANDOM.shuffle(jxsv_senders)

            for i, sender in enumerate(jxsv_senders):

                # Identify compatible Receivers
                question = textwrap.dedent(f"""\
                           The NCuT should be able to discover JPEG XS capable Receivers \
                           that are compatible with JPEG XS Senders according to \
                           TR-08 Capability Set and Conformance Level.

                           Refresh the NCuT's view of the Registry and carefully select the Receivers \
                           that are compatible with the following Sender:

                           {sender['display_answer']}

                           Once compatible Receivers have been identified press 'Submit'. If unable \
                           to identify compatible Receivers, press 'Submit' without making a selection.
                           """)

                compatible_receivers = [r for r in self.receivers if self._is_compatible(sender, r)]
                other_receivers = [r for r in self.receivers if not self._is_compatible(sender, r)]

                compatible_receiver_count = NMOSUtils.RANDOM.randint(1, min(MAX_COMPATIBLE_RECEIVER_COUNT,
                                                                            len(compatible_receivers)))
                candidate_receivers = NMOSUtils.RANDOM.sample(compatible_receivers, compatible_receiver_count)

                if len(candidate_receivers) < CANDIDATE_RECEIVER_COUNT:
                    incompatible_receiver_count = min(CANDIDATE_RECEIVER_COUNT - len(candidate_receivers),
                                                      len(other_receivers))
                    candidate_receivers.extend(NMOSUtils.RANDOM.sample(other_receivers, incompatible_receiver_count))

                candidate_receivers.sort(key=itemgetter('label'))

                possible_answers = [{'answer_id': 'answer_'+str(i), 'display_answer': r['display_answer'],
                                    'resource': {'id': r['id'], 'label': r['label'], 'description': r['description']}}
                                    for i, r in enumerate(candidate_receivers)]
                expected_answers = ['answer_'+str(i) for i, r in enumerate(candidate_receivers)
                                    if self._is_compatible(sender, r)]

                actual_answers = self.testing_facade_utils.invoke_testing_facade(
                    question, possible_answers, test_type='multi_choice', multipart_test=i)['answer_response']

                actual = set(actual_answers)
                expected = set(expected_answers)

                if expected - actual:
                    return test.FAIL('Not all compatible Receivers identified for Sender {}: '
                                     'Capability Set {}, Conformance Level {}, Interoperability Point {}'
                                     .format(sender['display_answer'], sender['capability_set'],
                                             sender['conformance_level'], sender['interop_point']))
                elif actual - expected:
                    return test.FAIL('Receivers incorrectly identified as compatible for Sender {}: '
                                     'Capability Set {}, Conformance Level {}, Interoperability Point {}'
                                     .format(sender['display_answer'], sender['capability_set'],
                                             sender['conformance_level'], sender['interop_point']))

            return test.PASS('All compatible Receivers correctly identified')

        except TestingFacadeException as e:
            return test.UNCLEAR(e.args[0])

    def test_04(self, test):
        """
        Ensure NCuT can identify JPEG XS Sender compatibility according to TR-08 Capability Set and Conformance Level
        """
        # Identify compatible Receivers given a random Sender.
        # Sender and Receivers have SDP/caps as specified in TR-08

        MAX_COMPATIBLE_SENDER_COUNT = 3
        CANDIDATE_SENDER_COUNT = 6

        try:
            receiver_iterations = CONFIG.MAX_TEST_ITERATIONS if CONFIG.MAX_TEST_ITERATIONS else len(self.receivers)

            jxsv_receivers = [r for r in self.receivers
                              if r['capability_set'] is not None
                              and r['conformance_level'] is not None][:receiver_iterations]

            for i, receiver in enumerate(jxsv_receivers):

                # Identify compatible Senders
                question = textwrap.dedent(f"""\
                           The NCuT should be able to discover JPEG XS capable Senders \
                           that are compatible with JPEG XS Receivers according to \
                           TR-08 Capability Set and Conformance Level.

                           Refresh the NCuT's view of the Registry and carefully select the Senders \
                           that are compatible with the following Receiver:

                           {receiver['display_answer']}

                           Once compatible Senders have been identified press 'Submit'. If unable \
                           to identify compatible Senders, press 'Submit' without making a selection.
                           """)

                compatible_senders = [s for s in self.senders if self._is_compatible(s, receiver)]
                other_senders = [s for s in self.senders if not self._is_compatible(s, receiver)]

                compatible_sender_count = NMOSUtils.RANDOM.randint(1, min(MAX_COMPATIBLE_SENDER_COUNT,
                                                                          len(compatible_senders)))
                candidate_senders = NMOSUtils.RANDOM.sample(compatible_senders, compatible_sender_count)

                if len(candidate_senders) < CANDIDATE_SENDER_COUNT:
                    incompatible_sender_count = min(CANDIDATE_SENDER_COUNT - len(candidate_senders),
                                                    len(other_senders))
                    candidate_senders.extend(NMOSUtils.RANDOM.sample(other_senders, incompatible_sender_count))

                candidate_senders.sort(key=itemgetter('label'))

                possible_answers = [{'answer_id': 'answer_'+str(i), 'display_answer': r['display_answer'],
                                    'resource': {'id': r['id'], 'label': r['label'], 'description': r['description']}}
                                    for i, r in enumerate(candidate_senders)]
                expected_answers = ['answer_'+str(i) for i, s in enumerate(candidate_senders)
                                    if self._is_compatible(s, receiver)]

                actual_answers = self.testing_facade_utils.invoke_testing_facade(
                    question, possible_answers, test_type='multi_choice', multipart_test=i)['answer_response']

                actual = set(actual_answers)
                expected = set(expected_answers)

                if expected - actual:
                    return test.FAIL('Not all compatible Senders identified for Receiver {}: '
                                     'Capability Set {}, Conformance Level {}'
                                     .format(receiver['display_answer'],
                                             receiver['capability_set'], receiver['conformance_level']))
                elif actual - expected:
                    return test.FAIL('Senders incorrectly identified as compatible for Receiver {}: '
                                     'Capability Set {}, Conformance Level {}'
                                     .format(receiver['display_answer'],
                                             receiver['capability_set'], receiver['conformance_level']))

            return test.PASS('All compatible Senders correctly identified')

        except TestingFacadeException as e:
            return test.UNCLEAR(e.args[0])

    def test_05(self, test):
        """
        Instruct Receiver to subscribe to a Sender's JPEG XS Flow via IS-05
        """
        # Perform an immediate activation between a Receiver and a Sender.
        # Sender and Receivers have SDP/caps as specified in TR-08.

        try:
            # A representative cross section of interoperability points
            jxsv_interops = [{'capability_set': 'A/B', 'conformance_level': 'FHD', 'interop_point': '1'},  # 720p/59
                             {'capability_set': 'A/B', 'conformance_level': 'FHD', 'interop_point': '4'},  # 1080i/25
                             {'capability_set': 'A/B', 'conformance_level': 'FHD', 'interop_point': '6a'},  # 1080p/50
                             {'capability_set': 'C', 'conformance_level': 'FHD', 'interop_point': '2b'},  # FULL RGB
                             {'capability_set': 'C', 'conformance_level': 'UHD1', 'interop_point': '3a'},  # 2160p/59
                             {'capability_set': 'D', 'conformance_level': 'UHD2', 'interop_point': '2a'}]  # 4320p/59

            jxsv_senders = []

            for interop in jxsv_interops:
                jxsv_senders.extend([s for s in self.senders
                                     if s['capability_set'] == interop['capability_set']
                                     and s['conformance_level'] == interop['conformance_level']
                                     and s['interop_point'] == interop['interop_point']])

            for sender in jxsv_senders:
                self.node.clear_staged_requests()

                jxsv_receivers = [r for r in self.receivers if self._is_compatible(sender, r)]
                receiver = NMOSUtils.RANDOM.choice(jxsv_receivers)

                question = textwrap.dedent(f"""\
                           It should be possible to connect available Senders of JPEG XS flows to compatible Receivers.

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
                                                                test_type='action', metadata=metadata)

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
                if receiver['id'] in self.primary_registry.get_resources()['receiver']:
                    receiver_details = self.primary_registry.get_resources()['receiver'][receiver['id']]

                    if not receiver_details['subscription']['active']:
                        return test.FAIL('Receiver does not have active subscription')

                    if 'sender_id' in receiver_details['subscription'] \
                            and receiver_details['subscription']['sender_id'] \
                            and receiver_details['subscription']['sender_id'] != sender['id']:
                        return test.FAIL('Receiver did not connect to correct sender')

                if 'sender_id' not in patch_requests[0]['data'] or not patch_requests[0]['data']['sender_id']:
                    return test.WARNING('Sender id SHOULD be set in patch request')

                # Check patched SDP parameters are what were expected
                patched_sdp = self.node.patched_sdp[receiver['id']]

                if 'format' in patched_sdp[0]:
                    # Perhaps ought to loop over expected params and check in patched_sdp?
                    for param, value in patched_sdp[0]['format'].items():
                        if sender['sdp_params'].get(param) and sender['sdp_params'][param] != value:
                            return test.FAIL('Patched SDP does not match: ' + param)

                # Disconnect receiver
                deactivate_json = {'master_enable': False, 'sender_id': None,
                                   'activation': {'mode': 'activate_immediate'}}
                self.node.patch_staged('receivers', receiver['id'], deactivate_json)

            return test.PASS("Connections successfully established")
        except TestingFacadeException as e:
            return test.UNCLEAR(e.args[0])
        finally:
            # Disconnect all receivers
            for receiver in self.receivers:
                deactivate_json = {'master_enable': False, 'sender_id': None,
                                   'activation': {'mode': 'activate_immediate'}}
                self.node.patch_staged('receivers', receiver['id'], deactivate_json)
