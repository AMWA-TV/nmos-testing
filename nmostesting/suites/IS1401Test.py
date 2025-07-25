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
from copy import copy, deepcopy
from enum import IntEnum
from functools import cmp_to_key
from typing import Dict, List, Union
import random
import string
from ..Config import MS05_INVASIVE_TESTING
from ..GenericTest import GenericTest, NMOSTestException
from ..MS05Utils import NcBlock, NcBlockMemberDescriptor, NcBlockProperties, NcClassDescriptor, \
    NcDatatypeDescriptor, NcDatatypeType, NcMethodResult, NcMethodResultError, NcObject, NcObjectProperties, \
    NcPropertyDescriptor, NcPropertyId, StandardClassIds
from ..IS14Utils import IS14Utils
from .MS0501Test import MS0501Test

NODE_API_KEY = "node"
CONFIGURATION_API_KEY = "configuration"


class NcRestoreMode(IntEnum):
    Modify = 0
    Rebuild = 1


class NcPropertyHolder():
    def __init__(self, property_holder_json):
        self.id = NcPropertyId(property_holder_json["id"])
        self.descriptor = NcPropertyDescriptor(property_holder_json["descriptor"]) \
            if property_holder_json["descriptor"] else None
        self.value = property_holder_json["value"]

    def __str__(self):
        return f"[id={self.id}, descriptor={str(self.descriptor)}, value={self.value}"


class NcObjectPropertiesHolder():
    def __init__(self, object_properties_holder_json):
        self.path = object_properties_holder_json["path"]
        self.dependencyPaths = object_properties_holder_json["dependencyPaths"]
        self.allowedMembersClasses = object_properties_holder_json["allowedMembersClasses"]
        self.values = [NcPropertyHolder(v) for v in object_properties_holder_json["values"]]
        self.isRebuildable = object_properties_holder_json["isRebuildable"]


class NcBulkPropertiesHolder():
    def __init__(self, bulk_properties_holder_json):
        self.validationFingerprint = bulk_properties_holder_json["validationFingerprint"]
        self.values = [NcObjectPropertiesHolder(v) for v in bulk_properties_holder_json["values"]]


class NcRestoreValidationStatus(IntEnum):
    Ok = 200  # Restore successful
    Failed = 400  # Restore failed
    NotFound = 404  # Role path not found
    DeviceError = 500  # Internal device error


class NcPropertyRestoreNoticeType(IntEnum):
    Warning = 300
    Error = 400


class NcPropertyRestoreNotice():
    def __init__(self, property_restore_notice_json):
        self.id = NcPropertyId(property_restore_notice_json["id"])
        self.name = property_restore_notice_json["name"]
        self.noticeType = NcPropertyRestoreNoticeType(property_restore_notice_json["noticeType"])
        self.noticeMessage = property_restore_notice_json["noticeMessage"]

    def __str__(self):
        return f"[id={self.id}, name={self.name}, statusMessage={self.noticeType}, " \
            f"noticeMessage={self.noticeMessage}]"


class NcObjectPropertiesSetValidation():
    def __init__(self, object_properties_set_validation_json):
        self.path = object_properties_set_validation_json["path"]
        self.status = NcRestoreValidationStatus(object_properties_set_validation_json["status"])
        self.notices = [NcPropertyRestoreNotice(n) for n in object_properties_set_validation_json["notices"]]
        self.statusMessage = object_properties_set_validation_json["statusMessage"] \
            if object_properties_set_validation_json["statusMessage"] else None

    def __str__(self):
        return f"[path={self.path}, status={self.status}, statusMessage={self.statusMessage}, " \
            f"notices=[{', '.join([str(n) for n in self.notices])}]]"


class IS1401Test(MS0501Test):
    """
    Runs Tests covering MS-05 and IS-14
    """
    class TestMetadata():
        def __init__(self, checked=False, error=False, error_msg="", warning=False):
            self.checked = checked
            self.error = error
            self.error_msg = error_msg
            self.warning = warning

    def __init__(self, apis, **kwargs):
        self.is14_utils = IS14Utils(apis)
        MS0501Test.__init__(self, apis, self.is14_utils, **kwargs)
        self.node_url = apis[NODE_API_KEY]["url"]
        self.configuration_url = apis[CONFIGURATION_API_KEY]["url"]

    def set_up_tests(self):
        self.bulk_properties_checked = False
        self.check_validate_return_type_metadata = IS1401Test.TestMetadata()
        self.check_restore_return_type_metadata = IS1401Test.TestMetadata()
        self.check_validate_return_objects_metadata = IS1401Test.TestMetadata()
        self.check_restore_return_objects_metadata = IS1401Test.TestMetadata()
        self.check_validate_does_not_modify_metadata = IS1401Test.TestMetadata()
        self.check_restore_does_modify_metadata = IS1401Test.TestMetadata()
        super().set_up_tests()

    def tear_down_tests(self):
        super().tear_down_tests()

    def reset_device_model(self):
        self.is14_utils.device_model = None
        self.oid_cache = []

    def _do_request_json(self, test: GenericTest, method: str, url: str, **kwargs) -> any:
        """Perform an HTTP request and return JSON response"""
        valid, response = self.do_request(method, url, **kwargs)

        if not valid:
            raise NMOSTestException(test.FAIL(f"Invalid response from endpoint {method} {url}: "
                                              f"response: {str(response)}"))

        if response.status_code != 200:
            raise NMOSTestException(test.FAIL(f"Unexpected status code from endpoint {method} {url}: "
                                              f"status code={response.status_code}, "
                                              f"response: {response.text}"))

        if "application/json" not in response.headers["Content-Type"]:
            raise NMOSTestException(test.FAIL(f"JSON response expected from endpoint {url}"))

        return response.json()

    def _compare_property_ids(self, a: NcPropertyId, b: NcPropertyId) -> int:
        """Compare level and index of an NcPropertyId"""
        if a.level > b.level:
            return 1
        elif a.level < b.level:
            return -1
        elif a.index > b.index:
            return 1
        elif a.index < b.index:
            return -1
        else:
            return 0

    def _compare_property_objects(self,
                                  a: Union[NcPropertyDescriptor, NcPropertyHolder],
                                  b: Union[NcPropertyDescriptor, NcPropertyHolder]) -> int:
        """Compare NcPropertyIds of NcPropertyDescriptors or NcPropertyHolders"""
        return self._compare_property_ids(a.id, b.id)

    def _to_dict(self, obj):
        """Convert object to a dictionary"""
        if isinstance(obj, dict):
            data = {}
            for (k, v) in obj.items():
                data[k] = self._to_dict(v)
            return data
        elif isinstance(obj, list):
            return [self._to_dict(e) for e in obj]
        elif hasattr(obj, "__dict__"):
            data = {}
            for (k, v) in obj.__dict__.items():
                data[k] = self._to_dict(v)
            return data
        else:
            return obj

    def _get_bulk_properties_holder(self, test: GenericTest, endpoint: str) -> NcBulkPropertiesHolder:
        """Get backup dataset from endpoint"""
        method_result_json = self._do_request_json(test, "GET", endpoint)

        # Check this is of type NcMethodResult
        self.is14_utils.reference_datatype_schema_validate(test,
                                                           method_result_json,
                                                           NcMethodResult.__name__,
                                                           role_path=f"{endpoint}")
        method_result = NcMethodResult.factory(method_result_json)

        # Check the result value is of type NcBulkPropertiesHolder
        self.is14_utils.reference_datatype_schema_validate(test,
                                                           method_result.value,
                                                           NcBulkPropertiesHolder.__name__,
                                                           role_path=f"{endpoint}")

        return NcBulkPropertiesHolder(method_result.value)

    def _apply_bulk_properties_holder(self,
                                      test: GenericTest,
                                      test_metadata: TestMetadata,
                                      method: str,
                                      endpoint: str,
                                      bulk_properties_holder: NcBulkPropertiesHolder,
                                      restoreMode: NcRestoreMode,
                                      recurse: bool) -> List[NcObjectPropertiesSetValidation]:
        """Apply a backup dataset to the endpoint"""
        backup_dataset = {
            "arguments": {
                "dataSet": self._to_dict(bulk_properties_holder),
                "recurse": recurse,
                "restoreMode": restoreMode.value
                }
            }

        # Attempt to set on Device
        method_result_json = self._do_request_json(test, method, endpoint, json=backup_dataset)

        # Check this is of type NcMethodResult
        self.is14_utils.reference_datatype_schema_validate(test,
                                                           method_result_json,
                                                           NcMethodResult.__name__,
                                                           role_path=f"{endpoint}")
        method_result = NcMethodResult.factory(method_result_json)

        # Devices MUST return a response of type NcMethodResultObjectPropertiesSetValidation.
        if not isinstance(method_result.value, list):
            raise NMOSTestException(test.FAIL("Sequence of NcObjectPropertiesSetValidation expected"))

        for value in method_result.value:
            # Check this is an array of NcObjectPropertiesSetValidation
            self.is14_utils.reference_datatype_schema_validate(test,
                                                               value,
                                                               NcObjectPropertiesSetValidation.__name__,
                                                               role_path=f"{endpoint}")
        test_metadata.checked = True

        return [NcObjectPropertiesSetValidation(v) for v in method_result.value]

    def _restore_bulk_properties_holder(self,
                                        test: GenericTest,
                                        test_metadata: TestMetadata,
                                        endpoint: str,
                                        bulk_properties_holder: NcBulkPropertiesHolder,
                                        restoreMode=NcRestoreMode.Modify,
                                        recurse=True) -> List[NcObjectPropertiesSetValidation]:
        """Perform an HTTP PUT of the backup dataset to the endpoint"""
        return self._apply_bulk_properties_holder(test,
                                                  test_metadata,
                                                  "PUT", endpoint, bulk_properties_holder, restoreMode, recurse)

    def _validate_bulk_properties_holder(self,
                                         test: GenericTest,
                                         test_metadata: TestMetadata,
                                         endpoint: str,
                                         bulk_properties_holder: NcBulkPropertiesHolder,
                                         restoreMode=NcRestoreMode.Modify,
                                         recurse=True) -> List[NcObjectPropertiesSetValidation]:
        """Perform an HTTP PATCH of the backup dataset to the endpoint"""
        return self._apply_bulk_properties_holder(test,
                                                  test_metadata,
                                                  "PATCH", endpoint, bulk_properties_holder, restoreMode, recurse)

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

    def _check_block_member_role_syntax(self, test: GenericTest, role_path: List[str]):
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
                self._check_block_member_role_syntax(test, child_role_path)

    def test_03(self, test):
        """Role Syntax: Check the `.` character is not be used in roles"""
        # https://specs.amwa.tv/is-14/branches/v1.0-dev/docs/API_requests.html#url-and-usage

        self._check_block_member_role_syntax(test, ["root"])

        return test.PASS()

    def test_04(self, test):
        """RolePaths endpoint returns all the device model's role paths"""
        # Get expected role paths from device model
        device_model = self.is14_utils.query_device_model(test)

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
        role_paths_endpoint = f"{self.configuration_url}rolePaths/root.this.path.does.not.exist"

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
                    role_path=f"{role_path}properties/{property_id}/descriptor/")

                method_result = NcMethodResult.factory(method_result_json)

                # Check the result value is of type NcClassDescriptor
                self.is14_utils.reference_datatype_schema_validate(
                    test,
                    method_result.value,
                    NcDatatypeDescriptor.__name__,
                    role_path=f"{role_path}properties/{property_id}/descriptor/")

                actual_descriptor = NcDatatypeDescriptor.factory(method_result.value)

                # Yes, we already have the descriptor, but we might want its inherited attributes

                expected_descriptor = class_manager.get_datatype(actual_descriptor.name, True)

                self.is14_utils.validate_descriptor(
                    test,
                    expected_descriptor,
                    actual_descriptor,
                    f"role path={role_path}properties/{property_id}/descriptor/, "
                    f"datatype={str(actual_descriptor.name)}: ")

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

    def _check_bulk_properties_recurse_param(self, test: GenericTest, nc_block: NcBlock):
        """Check the recurse parameter is working as expected"""
        role_paths = nc_block.get_role_paths()
        root_role_path = '.'.join(nc_block.role_path)
        formatted_role_paths = ([f"{root_role_path}.{'.'.join(p)}/" for p in role_paths])
        formatted_role_paths.append(f"{root_role_path}/")

        conditions = [{"query_string": "", "expected_object_count": len(formatted_role_paths)},
                      {"query_string": "?recurse=true", "expected_object_count": len(formatted_role_paths)},
                      {"query_string": "?recurse=false", "expected_object_count": 1}]

        for condition in conditions:

            bulk_properties_endpoint = f"{self.configuration_url}rolePaths/{root_role_path}/" \
                f"bulkProperties{condition['query_string']}"

            bulk_properties_holder = self._get_bulk_properties_holder(test, bulk_properties_endpoint)

            if len(bulk_properties_holder.values) != condition["expected_object_count"]:
                raise NMOSTestException(test.FAIL("Unexpected NcBulkValueHolders returned. "
                                                  f"Expected {condition['expected_object_count']}, "
                                                  f"actual {len(bulk_properties_holder.values)} "
                                                  f"for endpoint {bulk_properties_endpoint}"))

    def test_09(self, test):
        """Recurse query parameter defaults to true on bulkProperties endpoint"""
        device_model = self.is14_utils.query_device_model(test)

        # Check root block
        self._check_bulk_properties_recurse_param(test, device_model)

        blocks = device_model.find_members_by_class_id(class_id=StandardClassIds.NCBLOCK.value,
                                                       include_derived=False,
                                                       recurse=True,
                                                       get_objects=True)
        # Check other blocks in Device Model
        for block in blocks:
            self._check_bulk_properties_recurse_param(test, block)

        return test.PASS()

    def _check_bulk_properties(self, test: GenericTest, nc_object: NcObject, include_descriptors=True):
        """Check that all expected properties are returned by the HTTP GET of the backup dataset"""
        if isinstance(nc_object, NcBlock):
            for child in nc_object.child_objects:
                self._check_bulk_properties(test, child)

        role_path = ".".join(nc_object.role_path)

        bulk_properties_endpoint = f"{self.configuration_url}rolePaths/{role_path}/bulkProperties" \
                                   f"?recurse=false&includeDescriptors={'true' if include_descriptors else 'false'}"

        bulk_properties_holder = self._get_bulk_properties_holder(test, bulk_properties_endpoint)

        if len(bulk_properties_holder.values) != 1:
            raise NMOSTestException(test.FAIL("Expected number of NcObjectPropertiesHolder "
                                              f"in NcBulkPropertiesHolder for endpoint {bulk_properties_endpoint}"))

        class_manager = self.is14_utils.get_class_manager(test)

        class_descriptor = class_manager.get_control_class(nc_object.class_id,
                                                           include_inherited=True)

        # Check all NcPropertyIds have been returned
        expected_property_ids = [p.id for p in class_descriptor.properties]
        actual_property_ids = [p.id for p in bulk_properties_holder.values[0].values]

        difference = list(set(expected_property_ids) - set(actual_property_ids))

        if len(difference) > 0:
            raise NMOSTestException(test.FAIL("Expected properties not returned from bulkProperties endpoint. "
                                              f"Missing properties={str(difference)}, "
                                              f"endpoint={bulk_properties_endpoint}"))

        # Compare NcPropertyDescriptors from class descriptor to the NcPropertyHolders from bulk properties holder
        property_descriptors = sorted(class_descriptor.properties,
                                      key=cmp_to_key(self._compare_property_objects))
        property_holders = sorted(bulk_properties_holder.values[0].values,
                                  key=cmp_to_key(self._compare_property_objects))

        for property_descriptor, property_holder in zip(property_descriptors, property_holders):
            if (property_holder.descriptor is not None) and not include_descriptors:
                raise NMOSTestException(
                    test.FAIL("NcPropertyHolder expected to have a null descriptor property "
                              "when includeDescriptors=false; "
                              f"Backup dataset NcPropertyHolder={property_holder} "
                              f"for role path={role_path}"))
            if (property_holder.descriptor is None) and include_descriptors:
                raise NMOSTestException(
                    test.FAIL("NcPropertyHolder expected to have a valid descriptor property "
                              "when includeDescriptors=true; "
                              f"Backup dataset NcPropertyHolder={property_holder} "
                              f"for role path={role_path}"))
            if property_holder.descriptor and property_holder.descriptor != property_descriptor:
                raise NMOSTestException(
                    test.FAIL("Definition of property in NcPropertyHolder inconsistant with class descriptor's "
                              f"NcPropertyDescriptor. Class descriptor NcPropertyDescriptor={property_descriptor}; "
                              f"Backup dataset NcPropertyHolder={property_holder} "
                              f"for role path={role_path}"))
            # Validate that the property holders are of the correct type
            if property_holder.value is None:
                if not property_descriptor.isNullable:
                    raise NMOSTestException(test.FAIL(f"Value can not be null for {property_descriptor.name}"
                                            f"at role path={role_path}"))
            elif property_descriptor.typeName not in self.is14_utils.reference_datatype_descriptors:
                # If we don't recognise the data type let's just move on
                continue
            elif property_descriptor.isSequence:
                if not isinstance(property_holder.value, list):
                    raise NMOSTestException(test.FAIL("Sequence of values expected for "
                                                      f"{property_descriptor.name} "
                                                      f"at role path={role_path}"))
                for v in property_holder.value:
                    self.is14_utils.reference_datatype_schema_validate(test, v,
                                                                       property_descriptor.typeName,
                                                                       role_path=role_path)
            else:
                self.is14_utils.reference_datatype_schema_validate(test, property_holder.value,
                                                                   property_descriptor.typeName,
                                                                   role_path=role_path)

    def test_10(self, test):
        """All properties of the target role path are returned from bulkProperties endpoint"""

        device_model = self.is14_utils.query_device_model(test)

        self._check_bulk_properties(test, device_model)

        return test.PASS()

    def test_11(self, test):
        """Property descriptors are excluded from backup dataset when includeDescriptors=false"""

        device_model = self.is14_utils.query_device_model(test)

        self._check_bulk_properties(test, device_model, include_descriptors=False)

        return test.PASS()

    def _check_for_class_manager(self, test: GenericTest, include_descriptors: bool):
        """Check that whether the class manager is part of the backup dataset"""
        bulk_properties_endpoint = f"{self.configuration_url}rolePaths/root/bulkProperties" \
                                   f"?recurse=true&includeDescriptors={'true' if include_descriptors else 'false'}"

        bulk_properties_holder = self._get_bulk_properties_holder(test, bulk_properties_endpoint)

        class_manager_values = [v for v in bulk_properties_holder.values if v.path == ["root", "ClassManager"]]

        # Only expect a class manager in the backup dataset if include_descriptors = true
        if len(class_manager_values) != include_descriptors:
            error_message = f"Class Manager {'expected' if include_descriptors else 'unexpected'} " \
                            f"when includeDescriptors={include_descriptors}"
            raise NMOSTestException(
                test.FAIL(f"{error_message} "
                          f"for endpoint={bulk_properties_endpoint} "))

    def test_12(self, test):
        """Class Manager is included/excluded when includeDescriptors=true/false"""
        self._check_for_class_manager(test, include_descriptors=True)
        self._check_for_class_manager(test, include_descriptors=False)

        return test.PASS()

    def test_13(self, test):
        """BulkProperties endpoint returns NcMethodResultError or a derived datatype on PATCH error."""
        bulk_properties_endpoint = f"{self.configuration_url}rolePaths/root/bulkProperties/"

        bogus_backup_dataset = {"this": "is", "not": "a", "backup": "dataset"}

        valid, response = self.do_request("PATCH", bulk_properties_endpoint, json=bogus_backup_dataset)

        if not valid:
            raise NMOSTestException(test.FAIL(f"Failed to access endpoint {bulk_properties_endpoint}"))

        if response.status_code < 300:
            raise NMOSTestException(test.FAIL(f"Expected error status code for {bulk_properties_endpoint}"))

        if "application/json" not in response.headers["Content-Type"]:
            raise NMOSTestException(test.FAIL(f"JSON response expected from endpoint {bulk_properties_endpoint}"))

        method_result_json = response.json()

        # Check this is of type NcMethodResult
        self.is14_utils.reference_datatype_schema_validate(test,
                                                           method_result_json,
                                                           NcMethodResult.__name__,
                                                           role_path=bulk_properties_endpoint)
        method_result = NcMethodResult.factory(method_result_json)

        if not isinstance(method_result, NcMethodResultError):
            return test.FAIL("Expected a response of type NcMethodResultError")

        return test.PASS()

    def test_14(self, test):
        """BulkProperties endpoint returns NcMethodResultError or a derived datatype on PUT error."""
        bulk_properties_endpoint = f"{self.configuration_url}rolePaths/root/bulkProperties/"

        bogus_backup_dataset = {"this": "is", "not": "a", "backup": "dataset"}

        valid, response = self.do_request("PUT", bulk_properties_endpoint, json=bogus_backup_dataset)

        if not valid:
            raise NMOSTestException(test.FAIL(f"Failed to access endpoint {bulk_properties_endpoint}"))

        if response.status_code < 300:
            raise NMOSTestException(test.FAIL(f"Expected error status code for {bulk_properties_endpoint}"))

        if "application/json" not in response.headers["Content-Type"]:
            raise NMOSTestException(test.FAIL(f"JSON response expected from endpoint {bulk_properties_endpoint}"))

        method_result_json = response.json()

        # Check this is of type NcMethodResult
        self.is14_utils.reference_datatype_schema_validate(test,
                                                           method_result_json,
                                                           NcMethodResult.__name__,
                                                           role_path=bulk_properties_endpoint)
        method_result = NcMethodResult.factory(method_result_json)

        if not isinstance(method_result, NcMethodResultError):
            return test.FAIL("Expected a response of type NcMethodResultError")

        return test.PASS()

    def _create_notices_list(self, set_validations: List[NcObjectPropertiesSetValidation]) -> List[str]:
        """Create list of validation notices"""
        return [".".join(v.path) + str(n.id) for v in set_validations for n in v.notices]

    def _create_object_properties_dict(self, bulk_properties_holder: NcBulkPropertiesHolder) \
            -> Dict[str, NcObjectPropertiesHolder]:
        """Creates a dict keyed on formatted role path and property id"""
        return {".".join(o.path) + str(v.id): v for o in bulk_properties_holder.values for v in o.values}

    def _compare_backup_datasets(self,
                                 test_metadata: TestMetadata,
                                 original_bulk_properties_holder: NcBulkPropertiesHolder,
                                 applied_bulk_properties_holder: NcBulkPropertiesHolder,
                                 updated_bulk_properties_holder: NcBulkPropertiesHolder,
                                 target_role_path: List[str],
                                 set_validations: List[NcObjectPropertiesSetValidation],
                                 recurse: bool, validate=False):
        """Compare the original backup dataset to the updated, given the applied dataset"""
        # original_bulk_properties_holder is the state before dataset applied
        # applied_bulk_properties_holder is the dataset applied to the Node under test
        # updated_bulk_properties_holder is the state after dataset applied
        def _compare_values(expected, actual):
            if isinstance(expected, list):
                if not isinstance(actual, list):
                    return False
                return len(expected) == len(actual)
            return expected == actual

        # Create dict from validation notices
        property_notices = self._create_notices_list(set_validations)

        # Create dict from original bulk properties holder
        original_properties = self._create_object_properties_dict(original_bulk_properties_holder)

        # Create dict from applied bulk properties holder
        applied_properties = self._create_object_properties_dict(applied_bulk_properties_holder)

        # Check updated bulk properties holder against restored and original bulk value holders
        for object_property_holder in updated_bulk_properties_holder.values:
            for property_holder in object_property_holder.values:
                key = ".".join(object_property_holder.path) + str(property_holder.id)
                if key in property_notices:
                    # This value may not have been updated, so ignore
                    continue
                if (object_property_holder.path == target_role_path or recurse) \
                        and not validate \
                        and key in applied_properties \
                        and not _compare_values(applied_properties[key].value, property_holder.value):
                    test_metadata.error = True
                    test_metadata.error_msg += "Property not updated by restore " \
                        f"for role path {object_property_holder.path} " \
                        f"and property {str(property_holder.id)} " \
                        f"when restoring to {target_role_path} " \
                        f"with recurse={recurse}, " \
                        f"expected={applied_properties[key].value}, actual={property_holder.value}; "
                # Has something been added to the device model unexpectedly
                if validate and key in applied_properties and key not in original_properties:
                    test_metadata.error = True
                    test_metadata.error_msg += "Validate operation: Device model unexpectedly changed " \
                        f"for role path {object_property_holder.path} " \
                        f"and property {str(property_holder.id)} " \
                        f"when restoring to {target_role_path} " \
                        f"with recurse={recurse}, " \
                        "validate=true; "
                    continue
                if (validate or (not recurse and object_property_holder.path != target_role_path and not validate)) \
                        and key in applied_properties \
                        and not _compare_values(original_properties[key].value, property_holder.value):
                    test_metadata.error = True
                    test_metadata.error_msg += "Validate operation: " if validate else "Restore operation: "
                    test_metadata.error_msg += "Property unexpectedly updated " \
                        f"for role path {object_property_holder.path} " \
                        f"and property {str(property_holder.id)} " \
                        f"when restoring to {target_role_path} " \
                        f"with recurse={recurse}, " \
                        f"expected={original_properties[key].value}, actual={property_holder.value}; "
        test_metadata.checked = True

    def _check_object_properties_set_validations(self,
                                                 test_metadata: TestMetadata,
                                                 bulk_properties_holder: NcBulkPropertiesHolder,
                                                 validations: List[NcObjectPropertiesSetValidation],
                                                 target_role_path: List[str],
                                                 recurse: bool):
        """Check that the NcObjectPropertiesSetValidations have no errors"""
        # Check there is one validation per object changed
        expected_role_paths = [o.path for o in bulk_properties_holder.values if recurse or o.path == target_role_path]
        actual_role_paths = [v.path for v in validations]

        if len(expected_role_paths) != len(actual_role_paths):
            test_metadata.error = True
            test_metadata.error_msg += f"Unexpected number of NcObjectPropertiesSetValidation objects " \
                f"expected {len(expected_role_paths)} role paths={str(expected_role_paths)}, " \
                f"actual {len(actual_role_paths)} role paths = {str(actual_role_paths)} for " \
                f"target role path={target_role_path}; "

        # Check the role paths are correct
        bulk_value_holders_dict = {".".join(o.path): o for o in bulk_properties_holder.values}

        for validation in validations:
            key = ".".join(validation.path)
            if key not in bulk_value_holders_dict.keys():
                test_metadata.error = True
                test_metadata.error_msg += "Unexpected NcObjectPropertiesSetValidation object " \
                    "returned from bulkProperties endpoint. " \
                    f"{str(validation)}; "

        # Check status is OK
        for validation in validations:
            if validation.status == NcRestoreValidationStatus.DeviceError.value:
                test_metadata.error = True
                test_metadata.error_msg += f"Unexpected NcRestoreValidationStatus. " \
                    f"Expected OK but got {validation.status} " \
                    f"for role path {validation.path}, " \
                    f"target role path={target_role_path} " \
                    f"{str(validation)}; "
            elif validation.status != NcRestoreValidationStatus.Ok.value:
                test_metadata.warning = True
                test_metadata.error_msg += f"Unexpected NcRestoreValidationStatus. " \
                    f"Expected OK but got {validation.status} " \
                    f"for role path {validation.path}, " \
                    f"target role path={target_role_path} " \
                    f"{str(validation)}; "
        test_metadata.checked = True

    def _check_validate_restore_properties(self,
                                           test: GenericTest,
                                           target_role_path: List[str],
                                           restoreMode: NcRestoreMode,
                                           recurse: bool):
        """Perform a validate and restore on the target role path"""
        target_role_path_formatted = ".".join(target_role_path)
        bulk_properties_endpoint = f"{self.configuration_url}rolePaths/{target_role_path_formatted}/bulkProperties"

        bulk_properties_holder = self._get_bulk_properties_holder(test, bulk_properties_endpoint)

        # Cache bulk_properties_holder
        original_bulk_properties_holder = deepcopy(bulk_properties_holder)

        # Remove all property_holders apart from user label properties
        for object_property_holder in bulk_properties_holder.values:
            object_property_holder.values = [v for v in object_property_holder.values
                                             if v.id == NcObjectProperties.USER_LABEL.value]

            # Change the user labels to random ten character strings
            for property_holder in object_property_holder.values:
                property_holder.value = "".join(random.choices(string.ascii_uppercase + string.digits, k=10))

        # Validate Bulk Values returns an array of NcObjectPropertiesSetValidation objects
        validations = self._validate_bulk_properties_holder(test,
                                                            self.check_validate_return_type_metadata,
                                                            bulk_properties_endpoint,
                                                            bulk_properties_holder,
                                                            restoreMode,
                                                            recurse)

        self._check_object_properties_set_validations(self.check_validate_return_objects_metadata,
                                                      bulk_properties_holder,
                                                      validations,
                                                      target_role_path,
                                                      recurse)

        # Verify the labels have NOT changed
        updated_bulk_properties_holder = self._get_bulk_properties_holder(test, bulk_properties_endpoint)

        self._compare_backup_datasets(self.check_validate_does_not_modify_metadata,
                                      original_bulk_properties_holder,
                                      bulk_properties_holder,
                                      updated_bulk_properties_holder,
                                      target_role_path, validations,
                                      recurse, validate=True)

        if self.check_validate_does_not_modify_metadata.error:
            return

        # Restore Bulk Values returns an array of NcObjectPropertiesSetValidation objects
        validations = self._restore_bulk_properties_holder(test,
                                                           self.check_restore_return_type_metadata,
                                                           bulk_properties_endpoint,
                                                           bulk_properties_holder,
                                                           restoreMode,
                                                           recurse)

        self._check_object_properties_set_validations(self.check_restore_return_objects_metadata,
                                                      bulk_properties_holder,
                                                      validations,
                                                      target_role_path,
                                                      recurse)

        # Verify the labels have changed
        updated_bulk_properties_holder = self._get_bulk_properties_holder(test, bulk_properties_endpoint)

        # Compare original, applied and updated bulk value holders
        self._compare_backup_datasets(self.check_restore_does_modify_metadata,
                                      original_bulk_properties_holder,
                                      bulk_properties_holder,
                                      updated_bulk_properties_holder, target_role_path,
                                      validations, recurse)

    def _do_bulk_properties_checks(self, test: GenericTest):
        """Check backup and restore for all role paths in Device Model"""
        if self.bulk_properties_checked is True:
            return

        # In their attempt to use the provided dataSet, devices MUST target the properties
        # of the target role path and all nested role paths when the body of the request contains
        # the recurse value set to true.
        # Devices MUST return a response of type NcMethodResultObjectPropertiesSetValidation.
        # Devices MUST NOT make any changes to the device model when validating bulk properties.

        device_model = self.is14_utils.query_device_model(test)

        bulk_properties_endpoint = f"{self.configuration_url}rolePaths/root/bulkProperties"
        bulk_properties_holder = self._get_bulk_properties_holder(test, bulk_properties_endpoint)
        # Cache bulk_properties_holder
        original_bulk_properties_holder = deepcopy(bulk_properties_holder)

        partial_role_paths = device_model.get_role_paths()

        role_paths = [["root"] + partial_role_path for partial_role_path in partial_role_paths]
        role_paths.append(["root"])

        # Check backup and restore to each role path
        for role_path in role_paths:
            self._check_validate_restore_properties(test, role_path, restoreMode=NcRestoreMode.Modify, recurse=True)
            self._check_validate_restore_properties(test, role_path, restoreMode=NcRestoreMode.Modify, recurse=False)

        # Reset to original backup dataset
        self._restore_bulk_properties_holder(test,
                                             self.check_restore_return_type_metadata,
                                             bulk_properties_endpoint,
                                             original_bulk_properties_holder)

        self.bulk_properties_checked = True

    def test_15(self, test):
        """Validating backup dataset devices returns NcMethodResultObjectPropertiesSetValidation array."""
        self._do_bulk_properties_checks(test)

        if self.check_validate_return_type_metadata.error:
            return test.FAIL(self.check_validate_return_objects_metadata.error_msg)

        if not self.check_validate_return_objects_metadata.checked:
            return test.UNCLEAR()

        return test.PASS()

    def test_16(self, test):
        """Restoring backup dataset devices returns NcMethodResultObjectPropertiesSetValidation array."""
        self._do_bulk_properties_checks(test)

        if self.check_restore_return_type_metadata.error:
            return test.FAIL(self.check_restore_return_type_metadata.error_msg)

        if not self.check_restore_return_type_metadata.checked:
            return test.UNCLEAR()

        return test.PASS()

    def test_17(self, test):
        """Validating returns one NcObjectPropertiesSetValidation for each object in the restore scope."""
        # A restore operation or validating a restore operation MUST always generate
        # ObjectPropertiesSetValidation entries for each object which is part of the restore scope.
        self._do_bulk_properties_checks(test)

        if self.check_validate_return_objects_metadata.error:
            return test.FAIL(self.check_validate_return_objects_metadata.error_msg)

        if not self.check_validate_return_objects_metadata.checked:
            return test.UNCLEAR()

        return test.PASS()

    def test_18(self, test):
        """Restoring returns one NcObjectPropertiesSetValidation for each object in the restore scope."""
        # A restore operation or validating a restore operation MUST always generate
        # ObjectPropertiesSetValidation entries for each object which is part of the restore scope.
        self._do_bulk_properties_checks(test)

        if self.check_restore_return_objects_metadata.error:
            return test.FAIL(self.check_restore_return_objects_metadata.error_msg)

        if not self.check_restore_return_objects_metadata.checked:
            return test.UNCLEAR()

        return test.PASS()

    def test_19(self, test):
        """Validating results in no changes to the device model."""
        # Devices MUST NOT make any changes to the device model when validating bulk properties.
        self._do_bulk_properties_checks(test)

        if self.check_validate_does_not_modify_metadata.error:
            return test.FAIL(self.check_validate_does_not_modify_metadata.error_msg)

        if not self.check_validate_does_not_modify_metadata.checked:
            return test.UNCLEAR()

        return test.PASS()

    def test_20(self, test):
        """Devices restores properties of target role path and all nested role paths when recurse is true"""
        # In their attempt to use the provided dataSet, devices MUST target the properties
        # of the target role path and all nested role paths when the body of the request
        # contains the recurse value set to true.
        self._do_bulk_properties_checks(test)

        if self.check_restore_does_modify_metadata.error:
            return test.FAIL(self.check_restore_does_modify_metadata.error_msg)

        if not self.check_restore_does_modify_metadata.checked:
            return test.UNCLEAR()

        return test.PASS()

    # Invasive testing

    def _generate_property_value(self, test: GenericTest, type_name: str, value: any) -> any:
        """Generate a new value based on the existing value"""

        # If this is a null property then not sure how to manipulate it
        if value is None:
            return value

        # If this is a sequence then process each element
        if isinstance(value, list):
            new_val = []
            for e in value:
                new_val.append(self._generate_property_value(test, type_name, e))
            return new_val

        class_manager = self.is14_utils.get_class_manager(test)
        datatype_descriptor = class_manager.get_datatype(type_name)

        if datatype_descriptor.type == NcDatatypeType.Primitive:
            resolved_type = self.is14_utils.resolve_datatype(test, type_name)

            if resolved_type in ["NcInt16", "NcInt32", "NcInt64", "NcUint16", "NcUint32", "NcUint64"]:
                return value + 1
            elif resolved_type in ["NcFloat32", "NcFloat64"]:
                return value + 0.5
            elif resolved_type == "NcBoolean":
                return not value
            else:
                return "".join(random.choices(string.ascii_uppercase + string.digits, k=10))

        if datatype_descriptor.type == NcDatatypeType.Enum:
            for item in datatype_descriptor.items:
                if item.value == value + 1:
                    return value + 1
                if item.value == value - 1:
                    return value - 1
            return value

        if datatype_descriptor.type == NcDatatypeType.Struct:
            ret_value = {}
            for field in datatype_descriptor.fields:
                ret_value[field.name] = self._generate_property_value(test, field.typeName, value[field.name])
            return ret_value

        if datatype_descriptor.type == NcDatatypeType.Typedef:
            return self._generate_property_value(test, datatype_descriptor.parentType, value)

        # If it got this far something has gone badly wrong
        raise NMOSTestException(test.FAIL(f"Unknown MS-05 datatype type: {datatype_descriptor.type}"))

    def _check_device_model_structure(self,
                                      test: GenericTest,
                                      bulk_properties_holder: NcBulkPropertiesHolder,
                                      reference_device_model: NcBlock):
        """Check that the Device Model has same structure as reference Device Model block"""
        for object_properties_holder in bulk_properties_holder.values:
            role_path = object_properties_holder.path
            reference_object = reference_device_model.find_object_by_path(role_path)
            if not isinstance(reference_object, NcBlock):
                continue

            expected_member_descriptors = reference_object.get_member_descriptors()
            method_result = self.is14_utils.get_member_descriptors(test, recurse=False, role_path=role_path)
            if isinstance(method_result, NcMethodResultError):
                raise NMOSTestException(test.FAIL(f"Error getting member descriptors: {method_result.errorMessage} "
                                                  f"for role path={role_path}"))
            actual_member_descriptors = method_result.value

            expected_roles = [m.role for m in expected_member_descriptors]
            actual_roles = [m.role for m in actual_member_descriptors]

            difference = list(set(expected_roles) - set(actual_roles))

            if len(difference) > 0:
                raise NMOSTestException(test.FAIL(f"Expected roles not returned role={str(difference)} "
                                                  f"for role path={role_path}"))

            difference = list(set(actual_roles) - set(expected_roles))

            if len(difference) > 0:
                raise NMOSTestException(test.FAIL(f"Unexpected roles returned role={str(difference)} "
                                                  f"for role path={role_path}"))

    def _filter_property_holders(self,
                                 bulk_properties_holder: NcBulkPropertiesHolder,
                                 filter_list: List[str],
                                 include=False) -> NcBulkPropertiesHolder:
        """Either include or exclude the filter_list property keys from the bulk properties holder"""
        # if include = True then properties with keys found in filter_list are kept (all others removed)
        # if include = False then properties with keys found in filter_list are removed
        filtered_object_property_holders = []
        for object_property_holder in bulk_properties_holder.values:
            filtered_property_holders = []
            for property_holder in object_property_holder.values:
                key = ".".join(object_property_holder.path) + str(property_holder.id)
                if (key in filter_list) == include:
                    filtered_property_holders.append(property_holder)
            if len(filtered_property_holders):
                object_property_holder.values = filtered_property_holders
                filtered_object_property_holders.append(object_property_holder)
        bulk_properties_holder.values = filtered_object_property_holders

        return bulk_properties_holder

    def _perform_restore(self,
                         test: GenericTest,
                         test_metadata: TestMetadata,
                         target_role_path: List[str],
                         bulk_properties_holder: NcBulkPropertiesHolder,
                         original_bulk_properties_holder: NcBulkPropertiesHolder,
                         restoreMode: NcRestoreMode,
                         recurse: bool,
                         readonly=False):
        """Check invasive backup and restore of backup dataset"""
        # Find the properties to test in bulk properties holder
        device_model = self.is14_utils.query_device_model(test)
        properties_under_test = self.is14_utils.get_properties(test, device_model, get_readonly=readonly)

        # Create a dict of properties to remove from bulk properties holder
        properties_under_test_list = [".".join(p.role_path) + str(p.descriptor.id) for p in properties_under_test]

        bulk_properties_endpoint = f"{self.configuration_url}rolePaths/{'.'.join(target_role_path)}/bulkProperties"

        # Keep these properties in the bulk_properties_holder (exclude everthing else)
        bulk_properties_holder = self._filter_property_holders(bulk_properties_holder,
                                                               properties_under_test_list,
                                                               include=True)
        if len(bulk_properties_holder.values) > 0:
            # Modify the values
            for object_property_holder in bulk_properties_holder.values:
                for property_holder in object_property_holder.values:
                    property_holder.value = self._generate_property_value(test,
                                                                          property_holder.descriptor.typeName,
                                                                          property_holder.value)

            # Validate the modified bulk properties holder
            validations = self._validate_bulk_properties_holder(test,
                                                                test_metadata,
                                                                bulk_properties_endpoint,
                                                                bulk_properties_holder,
                                                                restoreMode,
                                                                recurse)

            # Create a dict from validation warnings and errors
            problem_properties = self._create_notices_list(validations)

            # Remove any problem properties from the dataset
            bulk_properties_holder = self._filter_property_holders(bulk_properties_holder, problem_properties)

        if len(bulk_properties_holder.values) > 0:
            # Apply bulk properties holder to Node
            validations = self._restore_bulk_properties_holder(test,
                                                               test_metadata,
                                                               bulk_properties_endpoint,
                                                               bulk_properties_holder,
                                                               restoreMode,
                                                               recurse)

            # Check there were no errors
            self._check_object_properties_set_validations(test_metadata,
                                                          bulk_properties_holder,
                                                          validations,
                                                          target_role_path,
                                                          recurse)

            # Check the properties were changed
            updated_bulk_properties_holder = self._get_bulk_properties_holder(test, bulk_properties_endpoint)
            self._compare_backup_datasets(test_metadata,
                                          original_bulk_properties_holder,
                                          bulk_properties_holder,
                                          updated_bulk_properties_holder,
                                          target_role_path,
                                          validations,
                                          recurse)

            # If this is a modify then check the structure hasn't changed
            if restoreMode == NcRestoreMode.Modify:
                self._check_device_model_structure(test, bulk_properties_holder, device_model)

            # Attempt to return to initial device state
            self._restore_bulk_properties_holder(test,
                                                 test_metadata,
                                                 bulk_properties_endpoint,
                                                 original_bulk_properties_holder,
                                                 restoreMode,
                                                 recurse)
        else:
            test_metadata.checked = False

        if restoreMode == NcRestoreMode.Rebuild:
            # Invalidate cached device model as it might have been structurally changed by the restore
            self.reset_device_model()

            # Do check on device model to make sure it hasn't broken
            self.device_model_metadata = MS0501Test.TestMetadata()

            self._check_device_model(test)

            if self.device_model_metadata.error:
                raise NMOSTestException(test.FAIL(self.device_model_metadata.error_msg))

    def test_21(self, test):
        """Perform invasive 'Modify' validation and restore"""
        if not MS05_INVASIVE_TESTING:
            return test.DISABLED("This test cannot be performed when MS05_INVASIVE_TESTING is False ")

        target_role_path = ["root"]
        recurse = True
        # Get the backup dataset
        bulk_properties_endpoint = f"{self.configuration_url}rolePaths/{'.'.join(target_role_path)}/bulkProperties"
        bulk_properties_holder = self._get_bulk_properties_holder(test, bulk_properties_endpoint)

        # Cache original bulk properties holder
        original_bulk_properties_holder = deepcopy(bulk_properties_holder)

        check_invasive_modify_metadata = IS1401Test.TestMetadata()

        self._perform_restore(test,
                              check_invasive_modify_metadata,
                              target_role_path,
                              bulk_properties_holder,
                              original_bulk_properties_holder,
                              NcRestoreMode.Modify,
                              recurse)

        if check_invasive_modify_metadata.error:
            return test.FAIL(check_invasive_modify_metadata.error_msg)

        if check_invasive_modify_metadata.warning:
            return test.WARNING(check_invasive_modify_metadata.error_msg)

        if not check_invasive_modify_metadata.checked:
            return test.UNCLEAR()

        return test.PASS()

    def test_22(self, test):
        """Non-rebuildable Device Models accept Rebuild restores but only perform changes to writeable properties"""
        # In the interest of interoperability even devices with no rebuildable device model objects
        # MUST accept Rebuild restores but only perform changes to writeable properties of device model
        # objects whilst including notices for any other changes not supported by the device.
        if not MS05_INVASIVE_TESTING:
            return test.DISABLED("This test cannot be performed when MS05_INVASIVE_TESTING is False ")

        target_role_path = ["root"]
        recurse = True
        # Get the backup dataset
        bulk_properties_endpoint = f"{self.configuration_url}rolePaths/{'.'.join(target_role_path)}/bulkProperties"
        bulk_properties_holder = self._get_bulk_properties_holder(test, bulk_properties_endpoint)

        # Cache original bulk properties holder
        original_bulk_properties_holder = deepcopy(bulk_properties_holder)

        # Filter out rebuildable objects in the dataset
        non_rebuildable_object_holders = [o for o in bulk_properties_holder.values if o.isRebuildable is False]

        bulk_properties_holder.values = non_rebuildable_object_holders

        check_rebuild_modify_metadata = IS1401Test.TestMetadata()

        self._perform_restore(test,
                              check_rebuild_modify_metadata,
                              target_role_path,
                              bulk_properties_holder,
                              original_bulk_properties_holder,
                              NcRestoreMode.Rebuild,
                              recurse)

        if check_rebuild_modify_metadata.error:
            return test.FAIL(check_rebuild_modify_metadata.error_msg)

        if check_rebuild_modify_metadata.warning:
            return test.WARNING(check_rebuild_modify_metadata.error_msg)

        if not check_rebuild_modify_metadata.checked:
            return test.UNCLEAR()

        return test.PASS()

    def test_23(self, test):
        """Rebuild restore modifies read only properties in rebuildable objects"""
        if not MS05_INVASIVE_TESTING:
            return test.DISABLED("This test cannot be performed when MS05_INVASIVE_TESTING is False ")

        device_model = self.is14_utils.query_device_model(test)

        target_role_path = ["root"]
        recurse = True
        # Get the backup dataset
        bulk_properties_endpoint = f"{self.configuration_url}rolePaths/{'.'.join(target_role_path)}/bulkProperties"
        bulk_properties_holder = self._get_bulk_properties_holder(test, bulk_properties_endpoint)

        # Cache original bulk properties holder
        original_bulk_properties_holder = deepcopy(bulk_properties_holder)

        # Remove all objects from bulk properties holder apart from rebuildable objects, excluding rebuildable blocks
        block_paths = [o.role_path for o in
                       device_model.find_members_by_class_id(StandardClassIds.NCBLOCK.value, get_objects=True)]
        block_paths.append(["root"])  # root block is excluded from search results
        bulk_properties_holder.values = [o for o in bulk_properties_holder.values
                                         if o.isRebuildable and o.path not in block_paths]

        check_rebuild_objects_metadata = IS1401Test.TestMetadata()

        # Attempt to change the read only properties of rebuildable objects
        self._perform_restore(test,
                              check_rebuild_objects_metadata,
                              target_role_path,
                              bulk_properties_holder,
                              original_bulk_properties_holder,
                              NcRestoreMode.Rebuild,
                              recurse,
                              readonly=True)

        if check_rebuild_objects_metadata.error:
            return test.FAIL(check_rebuild_objects_metadata.error_msg)

        if check_rebuild_objects_metadata.warning:
            return test.WARNING(check_rebuild_objects_metadata.error_msg)

        if not check_rebuild_objects_metadata.checked:
            return test.UNCLEAR("Unable to modify any read only properties in rebuildable objects")

        return test.PASS()

    def _modify_rebuildable_block(self, test: GenericTest, test_metadata: TestMetadata, remove_member=False):
        """Perform a Rebuild restore which modifies the structure of the Device Model"""
        def _is_sub_array(sub_arr, arr):
            if len(sub_arr) >= len(arr):
                return False
            for s, a in zip(sub_arr, arr):
                if s != a:
                    return False
            return True
        device_model = self.is14_utils.query_device_model(test)

        target_role_path = ["root"]
        recurse = True
        # Get the backup dataset
        bulk_properties_endpoint = f"{self.configuration_url}rolePaths/{'.'.join(target_role_path)}/bulkProperties"
        bulk_properties_holder = self._get_bulk_properties_holder(test, bulk_properties_endpoint)

        # Cache original bulk properties holder
        original_bulk_properties_holder = deepcopy(bulk_properties_holder)

        # Find rebuildable blocks
        rebuildable_blocks = [device_model.find_object_by_path(o.path)
                              for o in bulk_properties_holder.values if o.isRebuildable
                              and isinstance(device_model.find_object_by_path(o.path), NcBlock)]

        for block in rebuildable_blocks:
            # Find block and child objects in bulk properties holder
            block_object_property_holders = [o for o in bulk_properties_holder.values
                                             if block.role_path == o.path]
            child_object_property_holders = [o for o in bulk_properties_holder.values
                                             if _is_sub_array(block.role_path, o.path)]
            # Expecting one block and more than one child
            if not len(child_object_property_holders) or len(block_object_property_holders) != 1:
                continue

            target_role_path = block.role_path
            # Identify the first child of the members array
            role_to_remove = child_object_property_holders[0].path

            # Find the block member's property holder
            property_holders = [p for p in block_object_property_holders[0].values
                                if p.id == NcBlockProperties.MEMBERS.value]
            if len(property_holders) != 1:
                continue

            # Validate that the value of this property holder is an NcBlockMemberDescriptor list
            if not isinstance(property_holders[0].value, list):
                return test.FAIL(f"Unexpected value for NcBlock members property {NcBlockProperties.MEMBERS.value}: "
                                 f"{property_holders[0].value} for role path={block.role_path}")
            for m in property_holders[0].value:
                self.is14_utils.reference_datatype_schema_validate(test, m,
                                                                   NcBlockMemberDescriptor.__name__,
                                                                   role_path=block.role_path)

            if remove_member:
                # Remove the "role_to_remove"'s member from the block
                for property_holder in block_object_property_holders[0].values:
                    if property_holder.id == NcBlockProperties.MEMBERS.value:
                        property_holder.value = [m for m in property_holder.value
                                                 if NcBlockMemberDescriptor(m).role != role_to_remove[-1]]

                # Only include the block and remaining children in bulk properties holder
                block_object_property_holders.extend([c for c in child_object_property_holders
                                                      if c.path != role_to_remove])
                bulk_properties_holder.values = block_object_property_holders
            else:
                # Duplicate an object
                role = "".join(random.choices(string.ascii_uppercase + string.digits, k=10))
                oid = 99999  # arbitrarily high to avoid clash of OIDs - although the device should take care of this
                for property_holder in block_object_property_holders[0].values:
                    if property_holder.id == NcBlockProperties.MEMBERS.value:
                        new_block_member = deepcopy(property_holder.value[0])
                        new_block_member["oid"] = oid
                        new_block_member["role"] = role
                        property_holder.value.append(new_block_member)

                new_object_property_holder = deepcopy(child_object_property_holders[0])
                new_object_property_holder.path = new_object_property_holder.path[:-1] + [role]

                for v in new_object_property_holder.values:
                    if v.id == NcObjectProperties.OID.value:
                        v.value = oid
                    if v.id == NcObjectProperties.ROLE.value:
                        v.value = role
                    if v.id == NcObjectProperties.CONSTANT_OID.value:
                        v.value = False  # ensure the device can create a new OID if there is a clash
                block_object_property_holders.extend(child_object_property_holders)
                block_object_property_holders.append(new_object_property_holder)
                bulk_properties_holder.values = block_object_property_holders

            # Validate the modified bulk properties holder
            bulk_properties_endpoint = f"{self.configuration_url}rolePaths/{'.'.join(target_role_path)}/bulkProperties"
            validations = self._validate_bulk_properties_holder(test,
                                                                test_metadata,
                                                                bulk_properties_endpoint,
                                                                bulk_properties_holder,
                                                                NcRestoreMode.Rebuild,
                                                                recurse)

            # Check the properties have not changed after validation
            validated_bulk_properties_holder = self._get_bulk_properties_holder(test, bulk_properties_endpoint)
            self._compare_backup_datasets(test_metadata,
                                          original_bulk_properties_holder,
                                          bulk_properties_holder,
                                          validated_bulk_properties_holder,
                                          target_role_path,
                                          validations,
                                          recurse,
                                          validate=True)
            if test_metadata.error:
                break
            for v in validations:
                member_notices = [n for n in v.notices if v.path == block.role_path and
                                  n.id == NcBlockProperties.MEMBERS.value]
                # Any problem with the members property means we can't test
                if len(member_notices):
                    test_metadata.checked = False
                    break
                if v.status != NcRestoreValidationStatus.Ok:
                    test_metadata.error = True
                    test_metadata.error_msg += ", ".join([n.noticeMessage for n in v.notices])
                    break

            validations = self._restore_bulk_properties_holder(test,
                                                               test_metadata,
                                                               bulk_properties_endpoint,
                                                               bulk_properties_holder,
                                                               NcRestoreMode.Rebuild,
                                                               recurse)

            self._check_object_properties_set_validations(test_metadata,
                                                          bulk_properties_holder,
                                                          validations,
                                                          target_role_path,
                                                          recurse)

            # Check the properties were changed
            updated_bulk_properties_holder = self._get_bulk_properties_holder(test, bulk_properties_endpoint)
            self._compare_backup_datasets(test_metadata,
                                          original_bulk_properties_holder,
                                          bulk_properties_holder,
                                          updated_bulk_properties_holder,
                                          target_role_path,
                                          validations,
                                          recurse)
            if test_metadata.error:
                break

        # Restore the original bulk properties holder
        self._restore_bulk_properties_holder(test,
                                             test_metadata,
                                             bulk_properties_endpoint,
                                             original_bulk_properties_holder,
                                             NcRestoreMode.Rebuild,
                                             recurse)

        # Invalidate cached device model as it might have been structurally changed by the restore
        self.reset_device_model()

    def test_24(self, test):
        """Rebuild restore removes member from rebuildable blocks"""
        if not MS05_INVASIVE_TESTING:
            return test.DISABLED("This test cannot be performed when MS05_INVASIVE_TESTING is False ")

        test_metadata = IS1401Test.TestMetadata()
        self._modify_rebuildable_block(test, test_metadata, remove_member=True)

        if test_metadata.error:
            return test.FAIL(test_metadata.error_msg)

        if test_metadata.warning:
            return test.WARNING(test_metadata.error_msg)

        if not test_metadata.checked:
            return test.UNCLEAR()

        return test.PASS()

    def test_25(self, test):
        """Rebuild restore adds member to rebuildable blocks"""
        if not MS05_INVASIVE_TESTING:
            return test.DISABLED("This test cannot be performed when MS05_INVASIVE_TESTING is False ")

        test_metadata = IS1401Test.TestMetadata()
        self._modify_rebuildable_block(test, test_metadata, remove_member=False)

        if test_metadata.error:
            return test.FAIL(test_metadata.error_msg)

        if test_metadata.warning:
            return test.WARNING(test_metadata.error_msg)

        if not test_metadata.checked:
            return test.UNCLEAR()

        return test.PASS()
