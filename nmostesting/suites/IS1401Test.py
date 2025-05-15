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

# from ..GenericTest import NMOSTestException
from copy import copy
from nmostesting.GenericTest import NMOSTestException
from nmostesting.MS05Utils import NcBlockProperties, NcClassDescriptor, NcDatatypeDescriptor, \
    NcMethodResult, NcMethodResultError, NcPropertyId
from ..IS14Utils import IS14Utils
from .MS0501Test import MS0501Test

NODE_API_KEY = "node"
CONFIGURATION_API_KEY = "configuration"


class NcPropertyValueHolder():
    def __init__(self, property_value_holder_json):
        self.id = NcPropertyId(property_value_holder_json["id"])
        self.name = property_value_holder_json["name"]
        self.typeName = property_value_holder_json["typeName"]
        self.isReadOnly = property_value_holder_json["isReadOnly"]
        self.value = property_value_holder_json["value"]


class NcObjectPropertiesHolder():
    def __init__(self, object_properties_holder_json):
        self.path = object_properties_holder_json["path"]
        self.dependencyPaths = object_properties_holder_json["dependencyPaths"]
        self.allowedMembersClasses = object_properties_holder_json["allowedMembersClasses"]
        self.values = [NcPropertyValueHolder(v) for v in object_properties_holder_json["values"]]
        self.isRebuildable = object_properties_holder_json["isRebuildable"]


class NcBulkValuesHolder():
    def __init__(self, bulk_values_holder_json):
        self.validationFingerprint = bulk_values_holder_json["validationFingerprint"]
        self.values = [NcObjectPropertiesHolder(v) for v in bulk_values_holder_json["values"]]


class IS1401Test(MS0501Test):
    """
    Runs Tests covering MS-05 and IS-14
    """
    def __init__(self, apis, **kwargs):
        self.is14_utils = IS14Utils(apis)
        MS0501Test.__init__(self, apis, self.is14_utils, **kwargs)
        self.node_url = apis[NODE_API_KEY]["url"]
        self.configuration_url = apis[CONFIGURATION_API_KEY]["url"]

    def set_up_tests(self):
        super().set_up_tests()

    def tear_down_tests(self):
        super().tear_down_tests()

    def _do_request_json(self, test, method, url):
        valid, response = self.do_request(method, url)

        if not valid or response.status_code != 200:
            raise NMOSTestException(test.FAIL(f"Failed to get role paths from endpoint {url}"))

        if "application/json" not in response.headers["Content-Type"]:
            raise NMOSTestException(test.FAIL(f"JSON response expected from endpoint {url}"))

        return response.json()

    def test_01(self, test):
        """Control Endpoint: Node under test advertises IS-14 control endpoint matching API under test"""
        # https://specs.amwa.tv/is-14/branches/v1.0-dev/docs/IS-04_interactions.html

        control_type = "urn:x-nmos:control:configuration/" + self.apis[CONFIGURATION_API_KEY]["version"]
        return self.is14_utils.do_test_device_control(
            test,
            self.node_url,
            control_type,
            self.configuration_url,
            self.authorization
        )

    def test_02(self, test):
        """Role Path Syntax: Use the '.' character to delimit roles in role paths"""

        role_paths_endpoint = f"{self.configuration_url}rolePaths/"

        response = self._do_request_json(test, "GET", role_paths_endpoint)

        for role_path in response:
            if role_path != "root" and not role_path.startswith("root."):
                test.FAIL("Unexpected role path syntax.", "https://specs.amwa.tv/is-14/branches/"
                          + f"{self.apis[CONFIGURATION_API_KEY]['spec_branch']}"
                          + "/docs/API_requests.html#url-and-usage")
        return test.PASS()

    def check_block_member_role_syntax(self, test, role_path):
        """Check syntax of roles in this block"""
        method_result = self.is14_utils.get_property(test, NcBlockProperties.MEMBERS.value, role_path=role_path)

        if isinstance(method_result, NcMethodResultError):
            raise NMOSTestException(test.FAIL(f"{self.is14_utils.create_role_path_string(role_path)}: "
                                              f"Error getting members property: {str(method_result.errorMessage)}. "))

        response = method_result.value
        for member in response:
            # check the class descriptor schema
            if "." in member["role"]:
                raise NMOSTestException(test.FAIL(f"Illegal role syntax: {member['role']}. "
                                                  + "Roles must not contain a '.' character",
                                                  "https://specs.amwa.tv/is-14/branches/"
                                                  + f"{self.apis[CONFIGURATION_API_KEY]['spec_branch']}"
                                                  + "/docs/API_requests.html#url-and-usage"))
            if self.is14_utils.is_block(member["classId"]):
                child_role_path = copy(role_path)
                child_role_path.append(member["role"])
                self.check_block_member_role_syntax(test, child_role_path)

    def test_03(self, test):
        """Role Syntax: Check the `.` character is not be used in roles"""
        # https://specs.amwa.tv/is-14/branches/v1.0-dev/docs/API_requests.html#url-and-usage

        self.check_block_member_role_syntax(test, ["root"])

        return test.PASS()

    def test_04(self, test):
        """RolePaths endpoint returns all the device model's role paths"""

        # Get expected role paths from device model
        device_model = self.is14_utils.query_device_model(test)

        if not device_model:
            return test.FAIL("Unable to query Device Model")

        device_model_role_paths = device_model.get_role_paths()

        expected_role_paths = ([f"root.{'.'.join(p)}/" for p in device_model_role_paths])
        expected_role_paths.append("root/")

        # Get actual role paths from IS-14 endpoint
        role_paths_endpoint = f"{self.configuration_url}rolePaths/"

        actual_role_paths = self._do_request_json(test, "GET", role_paths_endpoint)

        difference = list(set(expected_role_paths) - set(actual_role_paths))

        if len(difference) > 0:
            return test.FAIL(f"Expected role paths not returned from role paths endpoint: {str(difference)}")

        return test.PASS()

    def test_05(self, test):
        """Class descriptor endpoint returns NcMethodResultClassDescriptor including all inherited elements."""

        class_manager = self.is14_utils.get_class_manager(test)

        if not class_manager:
            return test.FAIL("Unable to query Class Manager")

        # Get role paths from IS-14 endpoint
        role_paths_endpoint = f"{self.configuration_url}rolePaths/"

        role_paths = self._do_request_json(test, "GET", role_paths_endpoint)

        for role_path in role_paths:
            class_descriptor_endpoint = f"{role_paths_endpoint}{role_path}descriptor"

            method_result_json = self._do_request_json(test, "GET", class_descriptor_endpoint)

            # Check this is of type NcMethodResult
            self.is14_utils.reference_datatype_schema_validate(test,
                                                               method_result_json,
                                                               NcMethodResult.__name__,
                                                               role_path=f"{role_path}descriptor")
            method_result = NcMethodResult.factory(method_result_json)

            # Check the result value is of type NcClassDescriptor
            self.is14_utils.reference_datatype_schema_validate(test,
                                                               method_result.value,
                                                               NcClassDescriptor.__name__,
                                                               role_path=f"{role_path}descriptor")

            actual_descriptor = NcClassDescriptor(method_result.value)

            # Yes, we already have the class descriptor, but we might want its inherited attributes

            expected_descriptor = class_manager.get_control_class(actual_descriptor.classId, True)

            self.is14_utils.validate_descriptor(
                test,
                expected_descriptor,
                actual_descriptor,
                f"role path={role_path}, class={str(actual_descriptor.name)}: ")

        return test.PASS()

    def test_06(self, test):
        """Role path endpoint returns a response of type NcMethodResultError or a derived datatype on error"""

        # Force an error with a bogus role path
        role_paths_endpoint = f"{self.configuration_url}rolePaths/this.url.does.not.exist"

        valid, response = self.do_request("GET", role_paths_endpoint)

        if not valid:
            raise NMOSTestException(test.FAIL(f"Failed to access endpoint {role_paths_endpoint}"))

        if response.status_code != 404:
            raise NMOSTestException(test.FAIL(f"Expected 404 status code for {role_paths_endpoint}"))

        if "application/json" not in response.headers["Content-Type"]:
            raise NMOSTestException(test.FAIL(f"JSON response expected from endpoint {role_paths_endpoint}"))

        method_result_json = response.json()

        # Check this is of type NcMethodResult
        self.is14_utils.reference_datatype_schema_validate(test,
                                                           method_result_json,
                                                           NcMethodResult.__name__,
                                                           role_path=role_paths_endpoint)
        method_result = NcMethodResult.factory(method_result_json)

        if not isinstance(method_result, NcMethodResultError):
            return test.FAIL("Expected a response of type NcMethodResultError")

        return test.PASS()

    def test_07(self, test):
        """Datatype descriptor endpoint returns NcMethodResultDatatypeDescriptor including all inherited elements."""

        class_manager = self.is14_utils.get_class_manager(test)

        if not class_manager:
            return test.FAIL("Unable to query Class Manager")

        # Get role paths from IS-14 endpoint
        role_paths_endpoint = f"{self.configuration_url}rolePaths/"

        role_paths = self._do_request_json(test, "GET", role_paths_endpoint)

        for role_path in role_paths:
            properties_endpoint = f"{role_paths_endpoint}{role_path}properties/"

            properties_json = self._do_request_json(test, "GET", properties_endpoint)

            for property_id in properties_json:
                descriptor_endpoint = f"{properties_endpoint}{property_id}descriptor/"

                method_result_json = self._do_request_json(test, "GET", descriptor_endpoint)

                # Check this is of type NcMethodResult
                self.is14_utils.reference_datatype_schema_validate(
                    test,
                    method_result_json,
                    NcMethodResult.__name__,
                    role_path=f"{role_path}properties/{property_id}descriptor/")

                method_result = NcMethodResult.factory(method_result_json)

                # Check the result value is of type NcClassDescriptor
                self.is14_utils.reference_datatype_schema_validate(
                    test,
                    method_result.value,
                    NcDatatypeDescriptor.__name__,
                    role_path=f"{role_path}properties/{property_id}descriptor/")

                actual_descriptor = NcDatatypeDescriptor(method_result.value)

                # Yes, we already have the class descriptor, but we might want its inherited attributes

                expected_descriptor = class_manager.get_datatype(actual_descriptor.name, True)

                self.is14_utils.validate_descriptor(
                    test,
                    expected_descriptor,
                    actual_descriptor,
                    f"role path={role_path}, datatype={str(actual_descriptor.name)}: ")

        return test.PASS()

    def test_08(self, test):
        """Properties endpoint returns a response of type NcMethodResultError or a derived datatype on error"""

        # Force an error with a bogus property endpoint
        property_endpoint = f"{self.configuration_url}rolePaths/root/properties/999p999/"

        valid, response = self.do_request("GET", property_endpoint)

        if not valid:
            raise NMOSTestException(test.FAIL(f"Failed to access endpoint {property_endpoint}"))

        if response.status_code != 404:
            raise NMOSTestException(test.FAIL(f"Expected 404 status code for {property_endpoint}"))

        if "application/json" not in response.headers["Content-Type"]:
            raise NMOSTestException(test.FAIL(f"JSON response expected from endpoint {property_endpoint}"))

        method_result_json = response.json()

        # Check this is of type NcMethodResult
        self.is14_utils.reference_datatype_schema_validate(test,
                                                           method_result_json,
                                                           NcMethodResult.__name__,
                                                           role_path=property_endpoint)
        method_result = NcMethodResult.factory(method_result_json)

        if not isinstance(method_result, NcMethodResultError):
            return test.FAIL("Expected a response of type NcMethodResultError")

        return test.PASS()
