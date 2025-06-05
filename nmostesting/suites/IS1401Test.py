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
import random
import string
from ..Config import MS05_INVASIVE_TESTING
from ..GenericTest import GenericTest, NMOSTestException
from ..MS05Utils import NcBlock, NcBlockMemberDescriptor, NcBlockProperties, NcClassDescriptor, NcClassManager, NcDatatypeDescriptor, \
    NcDatatypeType, NcMethodResult, NcMethodResultError, NcObject, NcObjectProperties, NcPropertyDescriptor, \
    NcPropertyId, StandardClassIds
from ..IS14Utils import IS14Utils
from .MS0501Test import MS0501Test

NODE_API_KEY = "node"
CONFIGURATION_API_KEY = "configuration"


class NcRestoreMode(IntEnum):
    Modify = 0
    Rebuild = 1


class NcPropertyValueHolder():
    def __init__(self, property_value_holder_json):
        self.id = NcPropertyId(property_value_holder_json["id"])
        self.name = property_value_holder_json["name"]
        self.typeName = property_value_holder_json["typeName"]
        self.isReadOnly = property_value_holder_json["isReadOnly"]
        self.value = property_value_holder_json["value"]

    def __str__(self):
        return f"[id={self.id}, name={self.name}, typeName={self.typeName}, " \
            f"isReadOnly={self.isReadOnly}, value={self.value}"


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
            f"notices=[{', '.join(self.notices)}]]"


class IS1401Test(MS0501Test):
    """
    Runs Tests covering MS-05 and IS-14
    """
    class TestMetadata():
        def __init__(self, checked=False, error=False, error_msg="", unclear=False):
            self.checked = checked
            self.error = error
            self.error_msg = error_msg
            self.unclear = unclear

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

    def _do_request_json(self, test, method, url, **kwargs):
        valid, response = self.do_request(method, url, **kwargs)

        if not valid or response.status_code != 200:
            raise NMOSTestException(test.FAIL(f"Error from endpoint {url}: "
                                              f"response: {response}"))

        if "application/json" not in response.headers["Content-Type"]:
            raise NMOSTestException(test.FAIL(f"JSON response expected from endpoint {url}"))

        return response.json()

    def _compare_property_ids(self, a: NcPropertyId, b: NcPropertyId):
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

    def _compare_property_descriptors(self, a: NcPropertyDescriptor, b: NcPropertyDescriptor):
        return self._compare_property_ids(a.id, b.id)

    def _compare_property_value_holders(self, a: NcPropertyValueHolder, b: NcPropertyValueHolder):
        return self._compare_property_ids(a.id, b.id)

    def _to_dict(self, obj):
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

    def _get_bulk_values_holder(self, test, endpoint):
        method_result_json = self._do_request_json(test, "GET", endpoint)

        # Check this is of type NcMethodResult
        self.is14_utils.reference_datatype_schema_validate(test,
                                                           method_result_json,
                                                           NcMethodResult.__name__,
                                                           role_path=f"{endpoint}")
        method_result = NcMethodResult.factory(method_result_json)

        # Check the result value is of type NcBulkValuesHolder
        self.is14_utils.reference_datatype_schema_validate(test,
                                                           method_result.value,
                                                           NcBulkValuesHolder.__name__,
                                                           role_path=f"{endpoint}")

        return NcBulkValuesHolder(method_result.value)

    def _apply_bulk_values_holder(self,
                                  test: GenericTest,
                                  test_metadata: TestMetadata,
                                  method: str,
                                  endpoint: str,
                                  bulk_values_holder: NcBulkValuesHolder,
                                  restoreMode: NcRestoreMode,
                                  recurse: bool):
        backup_dataset = {
            "arguments": {
                "dataSet": self._to_dict(bulk_values_holder),
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

    def _restore_bulk_values_holder(self,
                                    test: GenericTest,
                                    test_metadata: TestMetadata,
                                    endpoint: string,
                                    bulk_values_holder: NcBulkValuesHolder,
                                    restoreMode=NcRestoreMode.Modify,
                                    recurse=True):
        return self._apply_bulk_values_holder(test,
                                              test_metadata,
                                              "PUT", endpoint, bulk_values_holder, restoreMode, recurse)

    def _validate_bulk_values_holder(self,
                                     test: GenericTest,
                                     test_metadata: TestMetadata,
                                     endpoint: string,
                                     bulk_values_holder: NcBulkValuesHolder,
                                     restoreMode=NcRestoreMode.Modify,
                                     recurse=True):
        return self._apply_bulk_values_holder(test,
                                              test_metadata,
                                              "PATCH", endpoint, bulk_values_holder, restoreMode, recurse)

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
                    role_path=f"{role_path}properties/{property_id}descriptor/")

                method_result = NcMethodResult.factory(method_result_json)

                # Check the result value is of type NcClassDescriptor
                self.is14_utils.reference_datatype_schema_validate(
                    test,
                    method_result.value,
                    NcDatatypeDescriptor.__name__,
                    role_path=f"{role_path}properties/{property_id}descriptor/")

                actual_descriptor = NcDatatypeDescriptor.factory(method_result.value)

                # Yes, we already have the descriptor, but we might want its inherited attributes

                expected_descriptor = class_manager.get_datatype(actual_descriptor.name, True)

                self.is14_utils.validate_descriptor(
                    test,
                    expected_descriptor,
                    actual_descriptor,
                    f"role path={role_path}properties/{property_id}descriptor/, "
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

    def _check_bulk_properties_recurse_param(self, test, nc_block):

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

            bulk_values_holder = self._get_bulk_values_holder(test, bulk_properties_endpoint)

            if len(bulk_values_holder.values) != condition["expected_object_count"]:
                raise NMOSTestException(test.FAIL("Unexpected NcBulkValueHolders returned. "
                                                  f"Expected {condition['expected_object_count']}, "
                                                  f"actual {len(bulk_values_holder.values)} "
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

    def _check_bulk_properties(self, test: GenericTest, nc_object: NcObject):
        if isinstance(nc_object, NcBlock):
            for child in nc_object.child_objects:
                self._check_bulk_properties(test, child)

        role_path = ".".join(nc_object.role_path)

        bulk_properties_endpoint = f"{self.configuration_url}rolePaths/{role_path}/bulkProperties?recurse=false"

        bulk_values_holder = self._get_bulk_values_holder(test, bulk_properties_endpoint)

        if len(bulk_values_holder.values) != 1:
            raise NMOSTestException(test.FAIL("Expected number of NcObjectPropertiesHolder "
                                              f"in NcBulkValuesHolder for endpoint {bulk_properties_endpoint}"))

        class_manager = self.is14_utils.get_class_manager(test)

        class_descriptor = class_manager.get_control_class(nc_object.class_id,
                                                           include_inherited=True)

        # Check all NcPropertyIds have been returned
        expected_property_ids = [p.id for p in class_descriptor.properties]
        actual_property_ids = [p.id for p in bulk_values_holder.values[0].values]

        difference = list(set(expected_property_ids) - set(actual_property_ids))

        if len(difference) > 0:
            raise NMOSTestException(test.FAIL("Expected properties not returned from bulkProperties endpoint. "
                                              f"Missing properties={str(difference)}, "
                                              f"endpoint={bulk_properties_endpoint}"))

        # Compare NcPropertyDescriptors from class descriptor to the NcPropertyValueHolders from bulk values holder
        property_descriptors = sorted(class_descriptor.properties,
                                      key=cmp_to_key(self._compare_property_descriptors))
        property_value_holders = sorted(bulk_values_holder.values[0].values,
                                        key=cmp_to_key(self._compare_property_value_holders))

        for property_descriptor, property_value_holder in zip(property_descriptors, property_value_holders):
            if property_descriptor.name != property_value_holder.name or \
                    property_descriptor.typeName != property_value_holder.typeName or \
                    property_descriptor.isReadOnly != property_value_holder.isReadOnly:
                raise NMOSTestException(
                    test.FAIL("Definition of property in NcPropertyValueHolder inconsistant with class descriptor's "
                              f"NcPropertyDescriptor. Class descriptor NcPropertyDescriptor={property_descriptor}; "
                              f"Backup dataset NcPropertyValueHolder={property_value_holder} "
                              f"for endpoint {bulk_properties_endpoint}"))

    def test_10(self, test):
        """All properties of the target role path are returned from bulkProperties endpoint"""

        device_model = self.is14_utils.query_device_model(test)

        self._check_bulk_properties(test, device_model)

        return test.PASS()

    def test_11(self, test):
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

    def test_12(self, test):
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

    def _create_object_properties_dict(self, bulk_values_holder: NcBulkValuesHolder):
        """Creates a dict keyed on formatted role path and property id"""
        bulk_values_holder_properties = {}
        for object_property_holder in bulk_values_holder.values:
            for property_value_holder in object_property_holder.values:
                key = ".".join(object_property_holder.path) + str(property_value_holder.id)
                bulk_values_holder_properties[key] = property_value_holder
        return bulk_values_holder_properties

    def _compare_backup_datasets(self,
                                 test: GenericTest,
                                 test_metadata: TestMetadata,
                                 original_bulk_values_holder: NcBulkValuesHolder,
                                 applied_bulk_values_holder: NcBulkValuesHolder,
                                 updated_bulk_values_holder: NcBulkValuesHolder,
                                 target_role_path: list[str], recurse: bool, validate=False):
        # original_bulk_values_holder is the state before dataset applied
        # applied_bulk_values_holder is the dataset applied to the Node under test
        # updated_bulk_values_holder is the state after dataset applied

        # Compare backup datasets
        # Create dict from original bulk values holder
        original_properties = self._create_object_properties_dict(original_bulk_values_holder)

        # Create dict from applied bulk values holder
        applied_properties = self._create_object_properties_dict(applied_bulk_values_holder)

        # Check updated bulk values holder against restored and original bulk value holders
        for object_property_holder in updated_bulk_values_holder.values:
            for property_value_holder in object_property_holder.values:
                key = ".".join(object_property_holder.path) + str(property_value_holder.id)
                if (object_property_holder.path == target_role_path or recurse) \
                        and not validate \
                        and key in applied_properties \
                        and property_value_holder.value != applied_properties[key].value:
                    test_metadata.error = True
                    test_metadata.error_msg += "Property not updated by restore " \
                        f"for role path {object_property_holder.path} " \
                        f"and property {str(property_value_holder.id)} " \
                        f"when restoring to {target_role_path} " \
                        f"with recurse={recurse}; "
                if not recurse and object_property_holder.path != target_role_path \
                        and not validate \
                        and key in applied_properties \
                        and property_value_holder.value != original_properties[key].value:
                    test_metadata.error = True
                    test_metadata.error_msg += "Property unexpectedly updated by restore " \
                        f"for role path {object_property_holder.path} " \
                        f"and property {str(property_value_holder.id)} " \
                        f"when restoring to {target_role_path} " \
                        f"with recurse={recurse}; "
                if validate and key in applied_properties \
                        and property_value_holder.value == applied_properties[key].value:
                    test_metadata.error = True
                    test_metadata.error_msg += "Property unexpectedly updated by validate " \
                        f"for role path {object_property_holder.path} " \
                        f"and property {str(property_value_holder.id)} " \
                        f"when restoring to {target_role_path} " \
                        f"with recurse={recurse}; "
        test_metadata.checked = True

    def _check_object_properties_set_validations(self, test: GenericTest,
                                                 test_metadata: TestMetadata,
                                                 bulk_values_holder: NcBulkValuesHolder,
                                                 validations: list[NcObjectPropertiesSetValidation],
                                                 target_role_path: list[str],
                                                 recurse: bool):
        # Check there is one validation per object changed
        expected_role_paths = [o.path for o in bulk_values_holder.values if recurse or o.path == target_role_path]
        actual_role_paths = [v.path for v in validations]

        if len(expected_role_paths) != len(actual_role_paths):
            test_metadata.error = True
            test_metadata.error_msg += f"Unexpected number of NcObjectPropertiesSetValidation objects " \
                f"expected {len(expected_role_paths)} role paths={str(expected_role_paths)}, " \
                f"actual {len(actual_role_paths)} role paths = {str(actual_role_paths)} for " \
                f"target role path={target_role_path}; "

        # Check the role paths are correct
        bulk_value_holders_dict = self._create_object_properties_dict(bulk_values_holder)
        bulk_value_holders_dict = {}
        for object_property_holder in bulk_values_holder.values:
            key = ".".join(object_property_holder.path)
            bulk_value_holders_dict[key] = object_property_holder

        for validation in validations:
            key = ".".join(validation.path)
            if key not in bulk_value_holders_dict.keys():
                test_metadata.error = True
                test_metadata.error_msg += "Unexpected NcObjectPropertiesSetValidation object " \
                    "returned from bulkProperties endpoint. " \
                    f"{str(validation)}; "

        # Check status is OK
        for validation in validations:
            if validation.status != NcRestoreValidationStatus.Ok.value:
                test_metadata.error = True
                test_metadata.error_msg += f"Unexpected NcRestoreValidationStatus. " \
                    f"Expected OK but got {validation.status} " \
                    f"for role path {validation.path}, " \
                    f"target role path={target_role_path} " \
                    f"{str(validation)}; "
        test_metadata.checked = True

    def _check_validate_restore_properties(self,
                                           test: GenericTest,
                                           target_role_path: list[str],
                                           restoreMode: NcRestoreMode,
                                           recurse: bool):
        target_role_path_formatted = ".".join(target_role_path)
        bulk_properties_endpoint = f"{self.configuration_url}rolePaths/{target_role_path_formatted}/bulkProperties"

        bulk_values_holder = self._get_bulk_values_holder(test, bulk_properties_endpoint)

        # Cache bulk_values_holder
        original_bulk_values_holder = deepcopy(bulk_values_holder)

        # Remove all property_value_holders apart from user label properties
        for object_property_holder in bulk_values_holder.values:
            object_property_holder.values = [v for v in object_property_holder.values
                                             if v.id == NcObjectProperties.USER_LABEL.value]

            # Change the user labels to random ten character strings
            for property_value_holder in object_property_holder.values:
                property_value_holder.value = "".join(random.choices(string.ascii_uppercase + string.digits, k=10))

        # Validate Bulk Values returns an array of NcObjectPropertiesSetValidation objects
        validations = self._validate_bulk_values_holder(test,
                                                        self.check_validate_return_type_metadata,
                                                        bulk_properties_endpoint,
                                                        bulk_values_holder,
                                                        restoreMode,
                                                        recurse)

        self._check_object_properties_set_validations(test,
                                                      self.check_validate_return_objects_metadata,
                                                      bulk_values_holder,
                                                      validations,
                                                      target_role_path,
                                                      recurse)

        # Verify the labels have NOT changed
        updated_bulk_values_holder = self._get_bulk_values_holder(test, bulk_properties_endpoint)

        self._compare_backup_datasets(test,
                                      self.check_validate_does_not_modify_metadata,
                                      original_bulk_values_holder,
                                      bulk_values_holder,
                                      updated_bulk_values_holder,
                                      target_role_path, recurse, validate=True)

        # Restore Bulk Values returns an array of NcObjectPropertiesSetValidation objects
        validations = self._restore_bulk_values_holder(test,
                                                       self.check_restore_return_type_metadata,
                                                       bulk_properties_endpoint,
                                                       bulk_values_holder,
                                                       restoreMode,
                                                       recurse)

        self._check_object_properties_set_validations(test,
                                                      self.check_restore_return_objects_metadata,
                                                      bulk_values_holder,
                                                      validations,
                                                      target_role_path,
                                                      recurse)

        # Verify the labels have changed
        updated_bulk_values_holder = self._get_bulk_values_holder(test, bulk_properties_endpoint)

        # Compare original, applied and updated bulk value holders
        self._compare_backup_datasets(test,
                                      self.check_restore_does_modify_metadata,
                                      original_bulk_values_holder,
                                      bulk_values_holder,
                                      updated_bulk_values_holder, target_role_path, recurse)

    def _do_bulk_properties_checks(self, test):
        if self.bulk_properties_checked is True:
            return

        # In their attempt to use the provided dataSet, devices MUST target the properties
        # of the target role path and all nested role paths when the body of the request contains
        # the recurse value set to true.
        # Devices MUST return a response of type NcMethodResultObjectPropertiesSetValidation.
        # Devices MUST NOT make any changes to the device model when validating bulk properties.

        device_model = self.is14_utils.query_device_model(test)

        bulk_properties_endpoint = f"{self.configuration_url}rolePaths/root/bulkProperties"
        bulk_values_holder = self._get_bulk_values_holder(test, bulk_properties_endpoint)
        # Cache bulk_values_holder
        original_bulk_values_holder = deepcopy(bulk_values_holder)

        partial_role_paths = device_model.get_role_paths()

        role_paths = [["root"] + partial_role_path for partial_role_path in partial_role_paths]
        role_paths.append(["root"])

        # Check backup and restore to each role path
        for role_path in role_paths:
            self._check_validate_restore_properties(test, role_path, restoreMode=NcRestoreMode.Modify, recurse=True)
            self._check_validate_restore_properties(test, role_path, restoreMode=NcRestoreMode.Modify, recurse=False)

        # Reset to original backup dataset
        self._restore_bulk_values_holder(test,
                                         self.check_restore_return_type_metadata,
                                         bulk_properties_endpoint,
                                         original_bulk_values_holder)

        self.bulk_properties_checked = True

    def test_13(self, test):
        """Validating backup dataset devices returns NcMethodResultObjectPropertiesSetValidation array."""
        self._do_bulk_properties_checks(test)

        if self.check_validate_return_type_metadata.error:
            return test.FAIL(self.check_validate_return_objects_metadata.error_msg)

        if not self.check_validate_return_objects_metadata.checked:
            return test.UNCLEAR()

        return test.PASS()

    def test_14(self, test):
        """Restoring backup dataset devices returns NcMethodResultObjectPropertiesSetValidation array."""
        self._do_bulk_properties_checks(test)

        if self.check_restore_return_type_metadata.error:
            return test.FAIL(self.check_restore_return_type_metadata.error_msg)

        if not self.check_restore_return_type_metadata.checked:
            return test.UNCLEAR()

        return test.PASS()

    def test_15(self, test):
        """Validating returns one NcObjectPropertiesSetValidation for each object in the restore scope."""
        # A restore operation or validating a restore operation MUST always generate
        # ObjectPropertiesSetValidation entries for each object which is part of the restore scope.
        self._do_bulk_properties_checks(test)

        if self.check_validate_return_objects_metadata.error:
            return test.FAIL(self.check_validate_return_objects_metadata.error_msg)

        if not self.check_validate_return_objects_metadata.checked:
            return test.UNCLEAR()

        return test.PASS()

    def test_16(self, test):
        """Restoring returns one NcObjectPropertiesSetValidation for each object in the restore scope."""
        # A restore operation or validating a restore operation MUST always generate
        # ObjectPropertiesSetValidation entries for each object which is part of the restore scope.
        self._do_bulk_properties_checks(test)

        if self.check_restore_return_objects_metadata.error:
            return test.FAIL(self.check_restore_return_objects_metadata.error_msg)

        if not self.check_restore_return_objects_metadata.checked:
            return test.UNCLEAR()

        return test.PASS()

    def test_17(self, test):
        """Validating results in no changes to the device model."""
        # Devices MUST NOT make any changes to the device model when validating bulk properties.
        self._do_bulk_properties_checks(test)

        if self.check_validate_does_not_modify_metadata.error:
            return test.FAIL(self.check_validate_does_not_modify_metadata.error_msg)

        if not self.check_validate_does_not_modify_metadata.checked:
            return test.UNCLEAR()

        return test.PASS()

    def test_18(self, test):
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

    def _generate_property_value(self, test: GenericTest, class_manager: NcClassManager, type_name: str, value: any):
        """Generate a new value based on the existing value"""
        datatype_descriptor = class_manager.get_datatype(type_name)

        # If this is a null property then not sure how to manipulate it
        if value == None:
            return value

        # If this is a sequence then process each element
        if isinstance(value, list):
            new_val = []
            for e in value:
                new_val.append(self._generate_property_value(test, class_manager, type_name, e))
            return new_val

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
                ret_value[field.name] = self._generate_property_value(test,
                                                                      class_manager,
                                                                      field.typeName,
                                                                      value[field.name])
            return ret_value

        if datatype_descriptor.type == NcDatatypeType.Typedef:
            return self._generate_property_value(test, class_manager, datatype_descriptor.parentType, value)

        # If it got this far something has gone badly wrong
        raise NMOSTestException(test.FAIL(f"Unknown MS-05 datatype type: {datatype_descriptor.type}"))

    def _check_device_model_structure(self,
                                      test: GenericTest,
                                      bulk_values_holder: NcBulkValuesHolder,
                                      device_model: NcBlock):
        """Check that the Device Model has same structure as reference block"""
        for object_properties_holder in bulk_values_holder.values:
            role_path = object_properties_holder.path
            device_model_object = device_model.find_object_by_path(role_path)
            if not isinstance(device_model_object, NcBlock):
                continue

            expected_member_descriptors = device_model_object.get_member_descriptors()
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

    def _filter_property_value_holders(self, bulk_values_holder: NcBulkValuesHolder, filter_dict: dict, include=False):
        """ filter_dict is a dict of prorerty keys in the form {role_path}{property_id}"""
        filtered_object_property_holders = []
        for object_property_holder in bulk_values_holder.values:
            filtered_property_value_holders = []
            for property_value_holder in object_property_holder.values:
                key = ".".join(object_property_holder.path) + str(property_value_holder.id)
                if (key in filter_dict) == include:
                    filtered_property_value_holders.append(property_value_holder)
            if len(filtered_property_value_holders):
                object_property_holder.values = filtered_property_value_holders
                filtered_object_property_holders.append(object_property_holder)
        bulk_values_holder.values = filtered_object_property_holders

        return bulk_values_holder

    def _perform_restore(self,
                         test: GenericTest,
                         test_metadata: TestMetadata,
                         target_role_path: list[str],
                         bulk_values_holder: NcBulkValuesHolder,
                         original_bulk_values_holder: NcBulkValuesHolder,
                         restoreMode: NcRestoreMode,
                         recurse: bool,
                         readonly = False):
        # Find the properties to keep in bulk values holder
        device_model = self.is14_utils.query_device_model(test)
        keep_properties = self.is14_utils.get_properties(test, device_model, get_readonly=readonly)

        # Create a dict of properties to remove from bulk values holder
        keep_properties_dict = {}
        for ms05_property in keep_properties:
            key = ".".join(ms05_property.role_path) + str(ms05_property.descriptor.id)
            keep_properties_dict[key] = ms05_property

        bulk_properties_endpoint = f"{self.configuration_url}rolePaths/{'.'.join(target_role_path)}/bulkProperties"

        # Keep these properties in the bulk_values_holder (exlude everthing else)
        bulk_values_holder = self._filter_property_value_holders(bulk_values_holder, keep_properties_dict, include=True)
        if len(bulk_values_holder.values) > 0:
            # Modify the values
            class_manager = self.is14_utils.get_class_manager(test)
            for object_property_holder in bulk_values_holder.values:
                for property_value_holder in object_property_holder.values:
                        property_value_holder.value = self._generate_property_value(test,
                                                                                    class_manager,
                                                                                    property_value_holder.typeName,
                                                                                    property_value_holder.value)

            # Validate the modified bulk values holder
            validations = self._validate_bulk_values_holder(test,
                                                            test_metadata,
                                                            bulk_properties_endpoint,
                                                            bulk_values_holder,
                                                            restoreMode,
                                                            recurse)

            # Create a dict from validation warnings and errors
            problem_properties = {}
            for validation in validations:
                for notice in validation.notices:
                    key = ".".join(validation.path) + str(notice.id)
                    problem_properties[key] = notice

            # Remove any problem properties from the dataset
            bulk_values_holder = self._filter_property_value_holders(bulk_values_holder, problem_properties)

        if len(bulk_values_holder.values) > 0:
            # Apply bulk values holder to Node
            validations = self._restore_bulk_values_holder(test,
                                                            test_metadata,
                                                            bulk_properties_endpoint,
                                                            bulk_values_holder,
                                                            restoreMode,
                                                            recurse)

            # Check there were no errors
            self._check_object_properties_set_validations(test,
                                                            test_metadata,
                                                            bulk_values_holder,
                                                            validations,
                                                            target_role_path,
                                                            recurse)

            # Check the properties were changed
            updated_bulk_values_holder = self._get_bulk_values_holder(test, bulk_properties_endpoint)
            self._compare_backup_datasets(test,
                                            test_metadata,
                                            original_bulk_values_holder,
                                            bulk_values_holder,
                                            updated_bulk_values_holder,
                                            target_role_path,
                                            recurse)

            # If this is a modify then check the structure hasn't changed
            if restoreMode == NcRestoreMode.Modify:
                self._check_device_model_structure(test, bulk_values_holder, device_model)
        else:
            test_metadata.checked = False

        # Restore the original bulk values holder
        self._restore_bulk_values_holder(test,
                                         test_metadata,
                                         bulk_properties_endpoint,
                                         original_bulk_values_holder,
                                         restoreMode,
                                         recurse)

        if restoreMode == NcRestoreMode.Rebuild:
            # Invalidate cached device model as it might have been structurally changed by the restore
            self.is14_utils.device_model = None

    def test_19(self, test):
        """Perform invasive 'Modify' validation and restore"""
        if not MS05_INVASIVE_TESTING:
            return test.DISABLED("This test cannot be performed when MS05_INVASIVE_TESTING is False ")

        target_role_path = ["root"]
        recurse = True
        # Get the backup dataset
        bulk_properties_endpoint = f"{self.configuration_url}rolePaths/{'.'.join(target_role_path)}/bulkProperties"
        bulk_values_holder = self._get_bulk_values_holder(test, bulk_properties_endpoint)

        # Cache original bulk values holder
        original_bulk_values_holder = deepcopy(bulk_values_holder)

        check_invasive_modify_metadata = IS1401Test.TestMetadata()

        self._perform_restore(test,
                              check_invasive_modify_metadata,
                              target_role_path,
                              bulk_values_holder,
                              original_bulk_values_holder,
                              NcRestoreMode.Modify,
                              recurse)

        if check_invasive_modify_metadata.error:
            return test.FAIL(check_invasive_modify_metadata.error_msg)

        if not check_invasive_modify_metadata.checked:
            return test.UNCLEAR()

        return test.PASS()

    def test_20(self, test):
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
        bulk_values_holder = self._get_bulk_values_holder(test, bulk_properties_endpoint)

        # Cache original bulk values holder
        original_bulk_values_holder = deepcopy(bulk_values_holder)

        # Filter out rebuildable objects in the dataset
        non_rebuildable_object_holders = [o for o in bulk_values_holder.values if o.isRebuildable is False]

        bulk_values_holder.values = non_rebuildable_object_holders

        check_rebuild_modify_metadata = IS1401Test.TestMetadata()

        self._perform_restore(test,
                              check_rebuild_modify_metadata,
                              target_role_path,
                              bulk_values_holder,
                              original_bulk_values_holder,
                              NcRestoreMode.Rebuild,
                              recurse)

        if check_rebuild_modify_metadata .error:
            return test.FAIL(check_rebuild_modify_metadata .error_msg)

        if not check_rebuild_modify_metadata .checked:
            return test.UNCLEAR()

        return test.PASS()

    def test_21(self, test):
        """Rebuild restore modifies read only properties in rebuildable objects"""

        device_model = self.is14_utils.query_device_model(test)

        target_role_path = ["root"]
        recurse = True
        # Get the backup dataset
        bulk_properties_endpoint = f"{self.configuration_url}rolePaths/{'.'.join(target_role_path)}/bulkProperties"
        bulk_values_holder = self._get_bulk_values_holder(test, bulk_properties_endpoint)

        # Cache original bulk values holder
        original_bulk_values_holder = deepcopy(bulk_values_holder)

        # Find a rebuildable objects
        filtered_object_property_holders = []
        for object_property_holder in bulk_values_holder.values:
            if object_property_holder.isRebuildable:
                # Get corresponding NcObject from device model
                device_model_object = device_model.find_object_by_path(object_property_holder.path)

                # Is object an NcObject
                if not isinstance(device_model_object, NcBlock):
                    filtered_object_property_holders.append(object_property_holder)
        bulk_values_holder.values = filtered_object_property_holders

        check_rebuild_objects_metadata = IS1401Test.TestMetadata()

        # Attempt to change the read only properties of rebuildable objects
        self._perform_restore(test,
                              check_rebuild_objects_metadata,
                              target_role_path,
                              bulk_values_holder,
                              original_bulk_values_holder,
                              NcRestoreMode.Rebuild,
                              recurse,
                              readonly=True)

        if check_rebuild_objects_metadata.error:
            return test.FAIL(check_rebuild_objects_metadata.error_msg)

        if not check_rebuild_objects_metadata.checked:
            return test.UNCLEAR("Unable to modify any read only properties in rebuildable objects")

        return test.PASS()

    def test_22(self, test):
        """Rebuild restore modifies rebuildable block members"""
        def _is_sub_array(sub_arr, arr):
            if len(sub_arr) > len(arr):
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
        bulk_values_holder = self._get_bulk_values_holder(test, bulk_properties_endpoint)

        # Cache original bulk values holder
        original_bulk_values_holder = deepcopy(bulk_values_holder)

        # Find a rebuildable block
        rebuildable_blocks = []
        for object_property_holder in bulk_values_holder.values:
            if object_property_holder.isRebuildable:
                # Get corresponding NcObject from device model
                device_model_object = device_model.find_object_by_path(object_property_holder.path)
                # Is object an NcObject
                if isinstance(device_model_object, NcBlock):
                    rebuildable_blocks.append(device_model_object)

        check_rebuild_blocks_metadata = IS1401Test.TestMetadata()

        for block in rebuildable_blocks:
            # Find block and containing objects in bulk values holder
            child_object_property_holders = []
            block_object_property_holder = None
            for object_property_holder in bulk_values_holder.values:
                if object_property_holder.path == block.role_path:  # This is the block
                    block_object_property_holder = object_property_holder
                elif _is_sub_array(block.role_path, object_property_holder.path):  # This is a child of the block
                    child_object_property_holders.append(object_property_holder)

            if not len(child_object_property_holders):
                continue

            role_to_remove = child_object_property_holders[0].path

            new_children = []
            for c in child_object_property_holders:
                if c.path != role_to_remove:
                    new_children.append(c)

            # Remove a member from the block
            for property_value_holder in block_object_property_holder.values:
                if property_value_holder.id == NcBlockProperties.MEMBERS.value:
                    members = property_value_holder.value  # a list of NcBlockMemberDescriptors
                    new_members = []
                    for m in members:
                        if NcBlockMemberDescriptor(m).role != role_to_remove[-1]:
                            new_members.append(m)
                    property_value_holder.value = new_members

            new_object_property_holders = [block_object_property_holder]
            new_object_property_holders.extend(new_children)

            bulk_values_holder.values = new_object_property_holders

            # Attempt to change the read only properties of rebuildable objects
            # Validate the modified bulk values holder
            bulk_properties_endpoint = f"{self.configuration_url}rolePaths/{'.'.join(target_role_path)}/bulkProperties"
            validations = self._validate_bulk_values_holder(test,
                                                            check_rebuild_blocks_metadata,
                                                            bulk_properties_endpoint,
                                                            bulk_values_holder,
                                                            NcRestoreMode.Rebuild,
                                                            recurse)
            for validation in validations:
                for notice in validation.notices:
                    if validation.path == block.role_path and notice.id == NcBlockProperties.MEMBERS.value:
                        # Any problem with the members property means we can't test
                        continue

            validations = self._restore_bulk_values_holder(test,
                                                           check_rebuild_blocks_metadata,
                                                           bulk_properties_endpoint,
                                                           bulk_values_holder,
                                                           NcRestoreMode.Rebuild,
                                                           recurse)

            self._check_object_properties_set_validations(test,
                                                          check_rebuild_blocks_metadata,
                                                          bulk_values_holder,
                                                          validations,
                                                          target_role_path,
                                                          recurse)

            # Check the properties were changed
            updated_bulk_values_holder = self._get_bulk_values_holder(test, bulk_properties_endpoint)
            self._compare_backup_datasets(test,
                                          check_rebuild_blocks_metadata,
                                          original_bulk_values_holder,
                                          bulk_values_holder,
                                          updated_bulk_values_holder,
                                          target_role_path,
                                          recurse)

        # Restore the original bulk values holder
        self._restore_bulk_values_holder(test,
                                         check_rebuild_blocks_metadata,
                                         bulk_properties_endpoint,
                                         original_bulk_values_holder,
                                         NcRestoreMode.Rebuild,
                                         recurse)

        # Invalidate cached device model as it might have been structurally changed by the restore
        self.is14_utils.device_model = None

        if check_rebuild_blocks_metadata.error:
            return test.FAIL(check_rebuild_blocks_metadata.error_msg)

        if not check_rebuild_blocks_metadata.checked:
            return test.UNCLEAR()

        return test.PASS()
