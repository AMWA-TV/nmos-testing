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

from .MS05Utils import MS05Utils

from .MS05Utils import NcMethodStatus, NcObjectMethods, NcBlockMethods, NcClassManagerMethods, NcClassManagerProperties, NcDatatypeType, StandardClassIds, NcObjectProperties, NcBlockProperties,  NcObject, NcBlock, NcClassManager
from . import TestHelper

CONFIGURATION_API_KEY = 'configuration'


class IS14Utils(MS05Utils):
    def __init__(self, apis):
        MS05Utils.__init__(self, apis)
        self.configuration_url = apis[CONFIGURATION_API_KEY]['url']
        
    def _format_property_id(self, property_id):
        return property_id['level'] + 'p' + property_id['index']

    def get_property_value(self, rolePath, property_id):
        """Get value of property from object. Raises NMOSTestException on error"""
        formatted_property_id = self._format_property_id(property_id)
        # delimit role path?
        # get the api base from the apis
        get_property_endpoint = '{}rolePaths/{}/properties/{}/value'.format( self.configuration_url, rolePath, formatted_property_id)
        
        valid, r = TestHelper.do_request('GET', get_property_endpoint)
        
        value = r.content['value']

        return value
    
    # def _nc_object_factory(self, test, class_id, oid, role):
    #     """Create NcObject or NcBlock based on class_id"""
    #     # will set self.device_model_error to True if problems encountered
    #     try:
    #         runtime_constraints = self.get_property_value(
    #                 test,
    #                 oid,
    #                 NcObjectProperties.RUNTIME_PROPERTY_CONSTRAINTS.value)

    #         # Check class id to determine if this is a block
    #         if len(class_id) > 1 and class_id[0] == 1 and class_id[1] == 1:
    #             member_descriptors = self.get_property_value(
    #                 test,
    #                 oid,
    #                 NcBlockProperties.MEMBERS.value)

    #             nc_block = NcBlock(class_id, oid, role, member_descriptors, runtime_constraints)

    #             for m in member_descriptors:
    #                 child_object = self._nc_object_factory(test, m["classId"], m["oid"], m["role"])
    #                 if child_object:
    #                     nc_block.add_child_object(child_object)

    #             return nc_block
    #         else:
    #             # Check to determine if this is a Class Manager
    #             if len(class_id) > 2 and class_id[0] == 1 and class_id[1] == 3 and class_id[2] == 2:
    #                 class_descriptors = self._get_class_manager_descriptors(
    #                     test,
    #                     oid,
    #                     NcClassManagerProperties.CONTROL_CLASSES.value)

    #                 datatype_descriptors = self._get_class_manager_descriptors(
    #                     test,
    #                     oid,
    #                     NcClassManagerProperties.DATATYPES.value)

    #                 if not class_descriptors or not datatype_descriptors:
    #                     # An error has likely occured
    #                     return None

    #                 return NcClassManager(class_id,
    #                                       oid,
    #                                       role,
    #                                       class_descriptors,
    #                                       datatype_descriptors,
    #                                       runtime_constraints)

    #             return NcObject(class_id, oid, role, runtime_constraints)

    #     except NMOSTestException as e:
    #         raise NMOSTestException(test.FAIL("Error in Device Model " + role + ": " + str(e.args[0].detail)))
