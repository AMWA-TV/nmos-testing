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

import os
from .GenericTest import NMOSTestException
from .MS05Utils import MS05Utils, NcBlockMethods, NcClassManagerMethods, NcObjectMethods
from .TestResult import Test

from . import TestHelper

CONFIGURATION_API_KEY = "configuration"
FEATURE_SETS_KEY = "featuresets"
MS05_API_KEY = "controlframework"


class IS14Utils(MS05Utils):
    def __init__(self, apis):
        MS05Utils.__init__(self, apis, CONFIGURATION_API_KEY)
        self.configuration_url = apis[CONFIGURATION_API_KEY]["url"]

    def reset(self):
        super().reset()

    def load_reference_resources(self):
        """Override to load specification specific feature sets"""
        super().load_reference_resources()

        self.apis['featuresets']['repo_paths'] = ['device-configuration']
        # Calculate paths to MS-05 descriptors
        # including Feature Sets specified as additional_paths in test definition
        spec_paths = [os.path.join(self.apis[FEATURE_SETS_KEY]["spec_path"], "device-configuration")]
        spec_paths.append(self.apis[MS05_API_KEY]["spec_path"])
        # Root path for primitive datatypes
        spec_paths.append("test_data/MS05")

        datatype_paths = []
        classes_paths = []
        for spec_path in spec_paths:
            datatype_path = os.path.abspath(os.path.join(spec_path, "models/datatypes/"))
            if os.path.exists(datatype_path):
                datatype_paths.append(datatype_path)
            classes_path = os.path.abspath(os.path.join(spec_path, "models/classes/"))
            if os.path.exists(classes_path):
                classes_paths.append(classes_path)

        # Load class and datatype descriptors
        self.is14_reference_class_descriptors = self._load_model_descriptors(classes_paths)

        # Load MS-05 datatype descriptors
        self.is14_reference_datatype_descriptors = self._load_model_descriptors(datatype_paths)

    def auto_tests(self):
        """Overide to only test sepecification specific feature sets"""

        results = list()
        test = Test("Initialize auto tests", "auto_init")

        class_manager = self.get_class_manager(test)

        results += self._validate_model_definitions(class_manager.class_descriptors,
                                                    self.is14_reference_class_descriptors)

        results += self._validate_model_definitions(class_manager.datatype_descriptors,
                                                    self.is14_reference_datatype_descriptors)
        return results

    def _format_property_id(self, property_id):
        return f"{str(property_id.level)}p{str(property_id.index)}"

    def _format_method_id(self, method_id):
        return f"{str(method_id.level)}m{str(method_id.index)}"

    def _format_role_path(self, role_path):
        return ".".join(r for r in role_path)

    def _create_role_path_base(self, role_path):
        formatted_role_path = self._format_role_path(role_path)
        return f"{self.configuration_url}rolePaths/{formatted_role_path}"

    def _create_property_value_endpoint(self, role_path, property_id):
        formatted_property_id = self._format_property_id(property_id)
        return f"{self._create_role_path_base(role_path)}/properties/{formatted_property_id}/value"

    def _create_methods_endpoint(self, role_path, method_id):
        formatted_method_id = self._format_method_id(method_id)
        return f"{self._create_role_path_base(role_path)}/methods/{formatted_method_id}"

    def _do_request(self, test, method, url, **kwargs):
        valid, r = TestHelper.do_request(method, url, **kwargs)

        if not valid:
            raise NMOSTestException(test.FAIL(f"{r} for {method}: {url}, json={kwargs}"))
        try:
            self.reference_datatype_schema_validate(test, r.json(), "NcMethodResult")
        except ValueError as e:
            raise NMOSTestException(test.FAIL(f"Error: {e.args[0]} for {method}: {url}. "
                                              f"http/s response={r.text} "
                                              f"json={kwargs}"))
        except NMOSTestException as e:
            # NcMethodResult not returned
            raise NMOSTestException(test.FAIL(f"Error{e.args[0].detail} for {method}: {url}. "
                                              f"http/s response={r.text} "
                                              f"json={kwargs}"))

        return r.json()

    # Overridden functions
    def get_property_override(self, test, property_id, role_path, **kwargs):
        """Get value of property from object. Raises NMOSTestException on error"""
        property_value_endpoint = self._create_property_value_endpoint(role_path, property_id)
        return self._do_request(test, "GET", property_value_endpoint)

    def set_property_override(self, test, property_id, argument, role_path, **kwargs):
        """Get value of property from object. Raises NMOSTestException on error"""
        property_value_endpoint = self._create_property_value_endpoint(role_path, property_id)
        return self._do_request(test, "PUT", property_value_endpoint, json={"value": argument})

    def invoke_method_override(self, test, method_id, argument, role_path, **kwargs):
        """Invoke method on Node. Raises NMOSTestException on error"""
        methods_endpoint = self._create_methods_endpoint(role_path, method_id)
        return self._do_request(test, "PATCH", methods_endpoint, json={"arguments": argument})

    def get_sequence_item_override(self, test, property_id, index, role_path, **kwargs):
        """Get value from sequence property. Raises NMOSTestException on error"""
        methods_endpoint = self._create_methods_endpoint(role_path, NcObjectMethods.GET_SEQUENCE_ITEM.value)
        return self._do_request(test, "PATCH", methods_endpoint,
                                json={"arguments": {"id": property_id.__dict__, "index": index}})

    def get_sequence_length_override(self, test, property_id, role_path, **kwargs):
        """Get sequence length. Raises NMOSTestException on error"""
        methods_endpoint = self._create_methods_endpoint(role_path, NcObjectMethods.GET_SEQUENCE_LENGTH.value)
        return self._do_request(test, "PATCH", methods_endpoint, json={"arguments": {"id": property_id.__dict__}})

    def set_sequence_item_override(self, test, property_id, index, value, role_path, **kwargs):
        """Add value to a sequence property. Raises NMOSTestException on error"""
        methods_endpoint = self._create_methods_endpoint(role_path, NcObjectMethods.SET_SEQUENCE_ITEM.value)
        return self._do_request(test, "PATCH", methods_endpoint,
                                json={"arguments": {"id": property_id.__dict__,  "index": index, "value": value}})

    def add_sequence_item_override(self, test, property_id, value, role_path, **kwargs):
        """Add value to a sequence property. Raises NMOSTestException on error"""
        methods_endpoint = self._create_methods_endpoint(role_path, NcObjectMethods.ADD_SEQUENCE_ITEM.value)
        return self._do_request(test, "PATCH", methods_endpoint,
                                json={"arguments": {"id": property_id.__dict__, "value": value}})

    def remove_sequence_item_override(self, test, property_id, index, role_path, **kwargs):
        """Get value from sequence property. Raises NMOSTestException on error"""
        methods_endpoint = self._create_methods_endpoint(role_path, NcObjectMethods.REMOVE_SEQUENCE_ITEM.value)
        return self._do_request(test, "PATCH", methods_endpoint,
                                json={"arguments": {"id": property_id.__dict__,  "index": index}})

    def get_member_descriptors_override(self, test, recurse, role_path, **kwargs):
        """Get BlockMemberDescritors for this block. Raises NMOSTestException on error"""
        methods_endpoint = self._create_methods_endpoint(role_path, NcBlockMethods.GET_MEMBERS_DESCRIPTOR.value)
        return self._do_request(test, "PATCH", methods_endpoint, json={"arguments": {"recurse": recurse}})

    def find_members_by_path_override(self, test, path, role_path, **kwargs):
        """Query members based on role path. Raises NMOSTestException on error"""
        methods_endpoint = self._create_methods_endpoint(role_path, NcBlockMethods.FIND_MEMBERS_BY_PATH.value)
        return self._do_request(test, "PATCH", methods_endpoint, json={"arguments": {"path": path}})

    def find_members_by_role_override(self, test, role, case_sensitive, match_whole_string, recurse, role_path,
                                      **kwargs):
        """Query members based on role. Raises NMOSTestException on error"""
        methods_endpoint = self._create_methods_endpoint(role_path, NcBlockMethods.FIND_MEMBERS_BY_ROLE.value)
        return self._do_request(test, "PATCH", methods_endpoint,
                                json={"arguments": {"role": role,
                                                    "caseSensitive": case_sensitive,
                                                    "matchWholeString": match_whole_string,
                                                    "recurse": recurse}})

    def find_members_by_class_id_override(self, test, class_id, include_derived, recurse, role_path, **kwargs):
        """Query members based on class id. Raises NMOSTestException on error"""
        methods_endpoint = self._create_methods_endpoint(role_path, NcBlockMethods.FIND_MEMBERS_BY_CLASS_ID.value)
        return self._do_request(test, "PATCH", methods_endpoint,
                                json={"arguments": {"classId": class_id,
                                                    "includeDerived": include_derived,
                                                    "recurse": recurse}})

    def get_control_class_override(self, test, class_id, include_inherited, role_path, **kwargs):
        """Query Class Manager for control class. Raises NMOSTestException on error"""
        methods_endpoint = self._create_methods_endpoint(role_path, NcClassManagerMethods.GET_CONTROL_CLASS.value)
        return self._do_request(test, "PATCH", methods_endpoint,
                                json={"arguments": {"classId": class_id,
                                                    "includeInherited": include_inherited}})

    def get_datatype_override(self, test, name, include_inherited, role_path, **kwargs):
        """Query Class Manager for datatype. Raises NMOSTestException on error"""
        methods_endpoint = self._create_methods_endpoint(role_path, NcClassManagerMethods.GET_DATATYPE.value)
        return self._do_request(test, "PATCH", methods_endpoint,
                                json={"arguments": {"name": name,
                                                    "includeInherited": include_inherited}})

    # end of overridden functions
