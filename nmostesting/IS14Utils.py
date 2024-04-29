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

from .MS05Utils import MS05Utils, StandardClassIds

from . import TestHelper
from .GenericTest import NMOSTestException

CONFIGURATION_API_KEY = 'configuration'


class IS14Utils(MS05Utils):
    def __init__(self, apis):
        MS05Utils.__init__(self, apis)
        self.configuration_url = apis[CONFIGURATION_API_KEY]['url']

    # Overridden functions
    def query_device_model(self, test):
        """ Query Device Model from the Node under test.
            self.device_model_metadata set on Device Model validation error.
            NMOSTestException raised if unable to query Device Model """
        if not self.device_model:
            self.device_model = self._nc_object_factory(
                test,
                StandardClassIds.NCBLOCK.value,
                self.ROOT_BLOCK_OID,
                "root")

            if not self.device_model:
                raise NMOSTestException(test.FAIL("Unable to query Device Model"))
        return self.device_model

    def _format_property_id(self, property_id):
        return str(property_id['level']) + 'p' + str(property_id['index'])

    def _format_role_path(self, role_path):
        return '.'.join(r for r in role_path)

    def get_property_value_polymorphic(self, test, property_id, role_path, **kwargs):
        """Get value of property from object. Raises NMOSTestException on error"""
        formatted_property_id = self._format_property_id(property_id)
        formatted_role_path = self._format_role_path(role_path)
        # delimit role path?
        # get the api base from the apis
        get_property_endpoint = '{}rolePaths/{}/properties/{}/value'.format(self.configuration_url,
                                                                            formatted_role_path,
                                                                            formatted_property_id)

        valid, r = TestHelper.do_request('GET', get_property_endpoint)

        if valid and r.status_code == 200:
            try:
                return r.json()['value']
            except ValueError:
                pass

        return None

    # end of overridden functions
