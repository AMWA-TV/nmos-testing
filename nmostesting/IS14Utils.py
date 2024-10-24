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
from .MS05Utils import MS05Utils, NcBlockMethods, NcClassManagerMethods, NcObjectMethods

from . import TestHelper

CONFIGURATION_API_KEY = "configuration"


class IS14Utils(MS05Utils):
    def __init__(self, apis):
        MS05Utils.__init__(self, apis, CONFIGURATION_API_KEY)
        self.configuration_url = apis[CONFIGURATION_API_KEY]["url"]

    def reset(self):
        super().reset()

    def _format_property_id(self, property_id):
        return f"{str(property_id['level'])}p{str(property_id['index'])}"

    def _format_method_id(self, method_id):
        return f"{str(method_id['level'])}m{str(method_id['index'])}"

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
            raise NMOSTestException(test.FAIL(f"{r} for {method}: {url}"))
        try:
            self.reference_datatype_schema_validate(test, r.json(), "NcMethodResult")
        except ValueError as e:
            raise NMOSTestException(test.FAIL(f"Error: {e.args[0]} for {method}: {url}"))
        except NMOSTestException as e:
            if r.status_code < 200 or r.status_code > 299:
                raise NMOSTestException(test.FAIL(f"Unexpected status code: {r.status_code} for {method}: {url}"))
            raise NMOSTestException(test.FAIL(f"Error: {e.args[0]} for {method}: {url}"))

        if r.status_code < 200 or r.status_code > 299:
            raise NMOSTestException(test.FAIL(r.json()))

        return r.json()

    # Overridden functions
    def get_property(self, test, property_id, role_path, **kwargs):
        """Get value of property from object. Raises NMOSTestException on error"""
        property_value_endpoint = self._create_property_value_endpoint(role_path, property_id)
        return self._do_request(test, "GET", property_value_endpoint)

    def get_property_value(self, test, property_id, role_path, **kwargs):
        """Get value of property from object. Raises NMOSTestException on error"""
        return self.get_property(test, property_id, role_path=role_path)["value"]

    def set_property(self, test, property_id, argument, role_path, **kwargs):
        """Get value of property from object. Raises NMOSTestException on error"""
        property_value_endpoint = self._create_property_value_endpoint(role_path, property_id)
        return self._do_request(test, "PUT", property_value_endpoint, json={"value": argument})

    def invoke_method(self, test, method_id, argument, role_path, **kwargs):
        """Invoke method on Node. Raises NMOSTestException on error"""
        methods_endpoint = self._create_methods_endpoint(role_path, method_id)
        return self._do_request(test, "PATCH", methods_endpoint, json={"arguments": argument})

    def get_sequence_item(self, test, property_id, index, role_path, **kwargs):
        """Get value from sequence property. Raises NMOSTestException on error"""
        methods_endpoint = self._create_methods_endpoint(role_path, NcObjectMethods.GET_SEQUENCE_ITEM.value)
        return self._do_request(test, "PATCH", methods_endpoint,
                                json={"arguments": {"id": property_id, "index": index}})

    def get_sequence_item_value(self, test, property_id, index, role_path, **kwargs):
        return self.get_sequence_item(test, property_id, index, role_path, **kwargs)["value"]

    def get_sequence_length(self, test, property_id, role_path, **kwargs):
        """Get sequence length. Raises NMOSTestException on error"""
        methods_endpoint = self._create_methods_endpoint(role_path, NcObjectMethods.GET_SEQUENCE_LENGTH.value)
        return self._do_request(test, "PATCH", methods_endpoint, json={"arguments": {"id": property_id}})['value']

    def set_sequence_item(self, test, property_id, index, value, role_path, **kwargs):
        """Add value to a sequence property. Raises NMOSTestException on error"""
        methods_endpoint = self._create_methods_endpoint(role_path, NcObjectMethods.SET_SEQUENCE_ITEM.value)
        return self._do_request(test, "PATCH", methods_endpoint,
                                json={"arguments": {"id": property_id,  "index": index, "value": value}})

    def add_sequence_item(self, test, property_id, value, role_path, **kwargs):
        """Add value to a sequence property. Raises NMOSTestException on error"""
        methods_endpoint = self._create_methods_endpoint(role_path, NcObjectMethods.ADD_SEQUENCE_ITEM.value)
        return self._do_request(test, "PATCH", methods_endpoint,
                                json={"arguments": {"id": property_id, "value": value}})

    def remove_sequence_item(self, test, property_id, index, role_path, **kwargs):
        """Get value from sequence property. Raises NMOSTestException on error"""
        methods_endpoint = self._create_methods_endpoint(role_path, NcObjectMethods.REMOVE_SEQUENCE_ITEM.value)
        return self._do_request(test, "PATCH", methods_endpoint,
                                json={"arguments": {"id": property_id,  "index": index}})

    def get_member_descriptors(self, test, recurse, role_path, **kwargs):
        """Get BlockMemberDescritors for this block. Raises NMOSTestException on error"""
        methods_endpoint = self._create_methods_endpoint(role_path, NcBlockMethods.GET_MEMBERS_DESCRIPTOR.value)
        return self._do_request(test, "PATCH", methods_endpoint, json={"arguments": {"recurse": recurse}})['value']

    def find_members_by_path(self, test, path, role_path, **kwargs):
        """Query members based on role path. Raises NMOSTestException on error"""
        methods_endpoint = self._create_methods_endpoint(role_path, NcBlockMethods.FIND_MEMBERS_BY_PATH.value)
        return self._do_request(test, "PATCH", methods_endpoint, json={"arguments": {"path": path}})['value']

    def find_members_by_role(self, test, role, case_sensitive, match_whole_string, recurse, role_path, **kwargs):
        """Query members based on role. Raises NMOSTestException on error"""
        methods_endpoint = self._create_methods_endpoint(role_path, NcBlockMethods.FIND_MEMBERS_BY_ROLE.value)
        return self._do_request(test, "PATCH", methods_endpoint,
                                json={"arguments": {"role": role,
                                                    "caseSensitive": case_sensitive,
                                                    "matchWholeString": match_whole_string,
                                                    "recurse": recurse}})['value']

    def find_members_by_class_id(self, test, class_id, include_derived, recurse, role_path, **kwargs):
        """Query members based on class id. Raises NMOSTestException on error"""
        methods_endpoint = self._create_methods_endpoint(role_path, NcBlockMethods.FIND_MEMBERS_BY_CLASS_ID.value)
        return self._do_request(test, "PATCH", methods_endpoint,
                                json={"arguments": {"classId": class_id,
                                                    "includeDerived": include_derived,
                                                    "recurse": recurse}})['value']

    def get_control_class(self, test, class_id, include_inherited, role_path, **kwargs):
        """Query Class Manager for control class. Raises NMOSTestException on error"""
        methods_endpoint = self._create_methods_endpoint(role_path, NcClassManagerMethods.GET_CONTROL_CLASS.value)
        return self._do_request(test, "PATCH", methods_endpoint,
                                json={"arguments": {"classId": class_id,
                                                    "includeInherited": include_inherited}})['value']

    def get_datatype(self, test, name, include_inherited, role_path, **kwargs):
        """Query Class Manager for datatype. Raises NMOSTestException on error"""
        methods_endpoint = self._create_methods_endpoint(role_path, NcClassManagerMethods.GET_DATATYPE.value)
        return self._do_request(test, "PATCH", methods_endpoint,
                                json={"arguments": {"name": name,
                                                    "includeInherited": include_inherited}})['value']

    # end of overridden functions
