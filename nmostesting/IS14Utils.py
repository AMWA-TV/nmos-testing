# Copyright (C) 2024 Advanced Media Workflow Association
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

from nmostesting.GenericTest import NMOSTestException
from .MS05Utils import MS05Utils, NcBlockMethods

from . import TestHelper

CONFIGURATION_API_KEY = 'configuration'


class IS14Utils(MS05Utils):
    def __init__(self, apis):
        MS05Utils.__init__(self, apis, CONFIGURATION_API_KEY)
        self.configuration_url = apis[CONFIGURATION_API_KEY]['url']

    def _format_property_id(self, property_id):
        return str(property_id['level']) + 'p' + str(property_id['index'])

    def _format_method_id(self, method_id):
        return str(method_id['level']) + 'm' + str(method_id['index'])

    def _format_role_path(self, role_path):
        return '.'.join(r for r in role_path)

    def _create_role_path_base(self, role_path):
        formatted_role_path = self._format_role_path(role_path)
        return '{}rolePaths/{}'.format(self.configuration_url,
                                       formatted_role_path)

    def _create_property_value_endpoint(self, role_path, property_id):
        formatted_property_id = self._format_property_id(property_id)
        return self._create_role_path_base(role_path) + '/properties/{}/value'.format(formatted_property_id)

    def _create_methods_endpoint(self, role_path, method_id):
        formatted_method_id = self._format_method_id(method_id)
        return self._create_role_path_base(role_path) + '/methods/{}'.format(formatted_method_id)

    def _do_request(self, test, method, url, **kwargs):
        valid, r = TestHelper.do_request(method, url, **kwargs)

        if not valid:
            raise NMOSTestException(test.FAIL("{} for {}:{}".format(r, method, url)))
        if r.status_code < 200 or r.status_code > 299:
            raise NMOSTestException(test.FAIL("Unexpected status code: {} for {}:{}".format(r.status_code,
                                                                                            method,
                                                                                            url))) 
        try:
            return r.json()
        except ValueError as e:
            raise NMOSTestException(test.FAIL("Error: {} for {}:{}".format(e.args[0], method, url)))
    
    # Overridden functions
    def get_property(self, test, property_id, role_path, **kwargs):
        """Get value of property from object. Raises NMOSTestException on error"""
        property_value_endpoint = self._create_property_value_endpoint(role_path, property_id)

        return self._do_request(test, 'GET', property_value_endpoint)

    def get_property_value(self, test, property_id, role_path, **kwargs):
        """Get value of property from object. Raises NMOSTestException on error"""
        return self.get_property(test, property_id, role_path=role_path)['value']

    def set_property(self, test, property_id, argument, role_path, **kwargs):
        """Get value of property from object. Raises NMOSTestException on error"""
        property_value_endpoint = self._create_property_value_endpoint(role_path, property_id)

        return self._do_request(test, 'SET', property_value_endpoint, data={'value': argument})

    def get_sequence_item_value(self, test, property_id, index, role_path, **kwargs):
        # Hmmm should we reply on get or should we assume that get_sequence_item has been
        # implemented?
        raise NMOSTestException(test.FAIL("get_sequence_item_value not implemented"))
        # value = self.get_property_value(test, property_id, role_path=role_path)

        # return value[index]

    def get_sequence_item(self, test, property_id, index, role_path, **kwargs):
        """Get value from sequence property. Raises NMOSTestException on error"""
        raise NMOSTestException(test.FAIL("get_sequence_item not implemented"))
        #pass

    def get_sequence_length(self, test, property_id, role_path, **kwargs):
        """Get sequence length. Raises NMOSTestException on error"""
        # Hmmm should we reply on get or should we assume that get_sequence_item has been
        # implemented?
        raise NMOSTestException(test.FAIL("get_sequence_length not implemented"))
        # value = self.get_property_value(test, property_id, role_path=role_path)

        # return len(value)

    def get_member_descriptors(self, test, recurse, role_path, **kwargs):
        """Get BlockMemberDescritors for this block. Raises NMOSTestException on error"""
        methods_endpoint = self._create_methods_endpoint(role_path, NcBlockMethods.GET_MEMBERS_DESCRIPTOR.value)

        return self._do_request(test, 'PATCH', methods_endpoint, data={'argument': {'recurse': recurse}})

    def find_members_by_path(self, test, path, role_path, **kwargs):
        """Query members based on role path. Raises NMOSTestException on error"""
        raise NMOSTestException(test.FAIL("find_members_by_path not implemented"))

    def find_members_by_role(self, test, role, case_sensitive, match_whole_string, recurse, role_path, **kwargs):
        """Query members based on role. Raises NMOSTestException on error"""
        raise NMOSTestException(test.FAIL("find_members_by_role not implemented"))

    def find_members_by_class_id(self, test, class_id, include_derived, recurse, role_path, **kwargs):
        """Query members based on class id. Raises NMOSTestException on error"""
        raise NMOSTestException(test.FAIL("find_members_by_class_id not implemented"))

    # end of overridden functions
