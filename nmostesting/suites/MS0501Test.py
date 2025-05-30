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


import inspect
import re
import sys

from copy import copy, deepcopy
from itertools import product
from math import floor
from xeger import Xeger

from ..Config import MS05_INVASIVE_TESTING, MS05_INTERACTIVE_TESTING
from ..GenericTest import GenericTest, NMOSTestException
from ..TestingFacadeUtils import TestingFacadeUtils, TestingFacadeException
from ..MS05Utils import MS05Utils, NcBlock, NcBlockProperties, NcDatatypeDescriptor, \
    NcDatatypeDescriptorEnum, NcDatatypeDescriptorPrimitive, NcDatatypeType, NcDatatypeDescriptorStruct, \
    NcDatatypeDescriptorTypeDef, NcDeviceManagerProperties, NcMethodResultError, NcMethodResultXXX, \
    NcMethodStatus, NcObjectProperties, NcParameterConstraintsNumber, NcParameterConstraintsString, \
    NcParameterDescriptor, NcPropertyConstraintsNumber, NcPropertyConstraintsString, NcPropertyDescriptor, \
    NcTouchpoint, NcTouchpointNmos, NcTouchpointNmosChannelMapping, StandardClassIds

NODE_API_KEY = "node"
CONTROL_API_KEY = "ncp"
MS05_API_KEY = "controlframework"
FEATURE_SETS_KEY = "featuresets"
TESTING_FACADE_API_KEY = "testquestion"


# Note: this test suite is a base class for the IS1202Test and IS1402Test test suites
# where there are common MS-05 tests.  The test suite is not configured and
# instantiated in the same way as the other test suites.


class MS0501Test(GenericTest):
    """
    Runs Tests covering MS-05
    """
    class TestMetadata():
        def __init__(self, checked=False, error=False, error_msg="", unclear=False):
            self.checked = checked
            self.error = error
            self.error_msg = error_msg
            self.unclear = unclear

    class PropertyMetadata():
        def __init__(self, oid, role_path, name, constraints, datatype_type, descriptor):
            self.oid = oid
            self.role_path = role_path
            self.name = name
            self.constraints = constraints
            self.datatype_type = datatype_type
            self.descriptor = descriptor

    class MethodMetadata():
        def __init__(self, oid, role_path, name, descriptor):
            self.oid = oid
            self.role_path = role_path
            self.name = name
            self.descriptor = descriptor

    def __init__(self, apis, utils, **kwargs):
        # Remove the Node API RAML key to prevent this test suite from auto-testing IS-04 API
        apis[NODE_API_KEY].pop("raml", None)
        # Remove the Testing Facade spec_path as there are no corresponding GitHub repos for the Testing Facade API
        apis[TESTING_FACADE_API_KEY].pop("spec_path", None)

        GenericTest.__init__(self, apis, disable_auto=False, **kwargs)
        self.ms05_utils = utils
        self.testing_facade_utils = TestingFacadeUtils(apis)

    def set_up_tests(self):
        super().set_up_tests()
        self.ms05_utils.reset()
        # _check_device_model validates that device model is correct according to specification
        self.device_model_metadata = MS0501Test.TestMetadata()
        # checked in _check_device_model(), reported in test_ms05_03
        self.unique_roles_metadata = MS0501Test.TestMetadata()
        # checked in _check_device_model(), reported in test_ms05_04
        self.unique_oids_metadata = MS0501Test.TestMetadata()
        # checked in _check_device_model(), reported in test_ms05_05
        self.organization_metadata = MS0501Test.TestMetadata()
        # checked in _check_device_model(), reported in test_ms05_06
        self.touchpoints_metadata = MS0501Test.TestMetadata()
        # checked in _check_device_model(), reported in test_ms05_07
        self.deprecated_property_metadata = MS0501Test.TestMetadata()
        # checked in _check_device_model(), reported in test_ms05_09
        self.managers_members_root_block_metadata = MS0501Test.TestMetadata()
        # checked in _check_device_model(), reported in test_ms05_10
        self.managers_are_singletons_metadata = MS0501Test.TestMetadata()
        # checked in _check_device_model(), reported in test_ms05_16
        self.get_sequence_item_metadata = MS0501Test.TestMetadata()
        # checked in _check_device_model(), reported in test_ms05_17
        self.get_sequence_length_metadata = MS0501Test.TestMetadata()
        # checked in _check_device_model(), reported in test_ms05_22
        self.runtime_constraints_metadata = MS0501Test.TestMetadata()
        # checked in _check_device_model(), reported in test_ms05_23
        self.property_constraints_metadata = MS0501Test.TestMetadata()
        # checked in _check_device_model(), reported in test_ms05_25
        self.parameter_constraints_metadata = MS0501Test.TestMetadata()
        # checked in _check_device_model(), reported in test_ms05_26
        self.constraint_hierarchy_metadata = MS0501Test.TestMetadata()

        self.check_property_metadata = MS0501Test.TestMetadata()
        self.set_sequence_item_metadata = MS0501Test.TestMetadata()
        self.add_sequence_item_metadata = MS0501Test.TestMetadata()
        self.remove_sequence_item_metadata = MS0501Test.TestMetadata()
        self.invoke_methods_metadata = MS0501Test.TestMetadata()
        self.sequences_validated = False
        self.sequence_test_unclear = False

        self.oid_cache = []

    # Override basics to include the MS-05 auto tests
    def basics(self):
        results = super().basics()
        try:
            results += self.ms05_utils.auto_tests()
        except NMOSTestException as e:
            results.append(e.args[0])
        except Exception as e:
            results.append(self.uncaught_exception("auto_tests", e))
        return results

    def pre_tests_message(self):
        """
        Introduction to MS-05 Invasive Tests
        """
        if not MS05_INVASIVE_TESTING or not MS05_INTERACTIVE_TESTING:
            return

        # In order to give the tests some context, a pre tests message is displayed
        # on the Testing Facade prior to the tests starting. This communicates any
        # pre-requisites or setup required by the Test User.
        question = """\
                   These tests validate a Node under test's MS-05 Device Model.

                   These tests are invasive and could cause harm to the Node under test.

                   !!!Care should therefore be taken when running these tests!!!

                   Each test will allow Device Model object properties/methods to be excluded from the testing.

                   Start the tests by clicking the 'Next' button.
                   """

        try:
            self.testing_facade_utils.invoke_testing_facade(question, [], test_type="action")

        except TestingFacadeException:
            # pre_test_introducton timed out
            pass

    def post_tests_message(self):
        """
        MS-05 Test Suite complete!
        """
        if not MS05_INVASIVE_TESTING or not MS05_INTERACTIVE_TESTING:
            return
        # Once the tests are complete this post tests message is displayed.

        question = """\
                   MS-05 tests complete!

                   Please press the 'Next' button to exit the tests.
                   """

        try:
            self.testing_facade_utils.invoke_testing_facade(question, [], test_type="action")

        except TestingFacadeException:
            # post_test_introducton timed out
            pass

    def execute_tests(self, test_names):
        """Perform tests defined within this class"""

        self.pre_tests_message()

        super().execute_tests(test_names)

        self.post_tests_message()

    def test_ms05_01(self, test):
        """Device Model: Root Block exists with correct oid and role"""
        # https://specs.amwa.tv/ms-05-02/releases/v1.0.0/docs/Blocks.html

        error_msg_base = "role path=/root: " \
                         f"property name={NcObjectProperties.ROLE.name}: " \
                         f"property id={NcObjectProperties.ROLE.value}: "
        # Check role is correct
        method_result = self.ms05_utils.get_property(
            test,
            NcObjectProperties.ROLE.value,
            oid=self.ms05_utils.ROOT_BLOCK_OID,
            role_path=['root'])

        if isinstance(method_result, NcMethodResultError):
            return test.FAIL(f"{error_msg_base}"
                             "GetProperty error: Error getting role property of the Root Block: "
                             f"{str(method_result.errorMessage)}")

        if self.ms05_utils.is_error_status(method_result.status):
            return test.FAIL(f"{error_msg_base}"
                             "GetProperty error: NcMethodResultError MUST be returned on an error",
                             "https://specs.amwa.tv/ms-05-02/branches/"
                             f"{self.apis[MS05_API_KEY]['spec_branch']}"
                             "/docs/Framework.html#ncmethodresulterror")

        role = method_result.value

        if role != "root":
            return test.FAIL(f"{error_msg_base}"
                             f"Unexpected role in Root Block: {str(role)}",
                             "https://specs.amwa.tv/ms-05-02/branches/"
                             f"{self.apis[MS05_API_KEY]['spec_branch']}"
                             "/docs/Blocks.html")

        # Check OID is correct
        method_result = self.ms05_utils.get_property(
            test,
            NcObjectProperties.OID.value,
            oid=self.ms05_utils.ROOT_BLOCK_OID,
            role_path=['root'])

        if isinstance(method_result, NcMethodResultError):
            return test.FAIL(f"{error_msg_base}"
                             "GetProperty error: Error getting OID property of the Root Block: "
                             f"{str(method_result.errorMessage)}")

        if self.ms05_utils.is_error_status(method_result.status):
            return test.FAIL(f"{error_msg_base}"
                             "GetProperty error: NcMethodResultError MUST be returned on an error",
                             "https://specs.amwa.tv/ms-05-02/branches/"
                             f"{self.apis[MS05_API_KEY]['spec_branch']}"
                             "/docs/Framework.html#ncmethodresulterror")

        oid = method_result.value

        if oid != self.ms05_utils.ROOT_BLOCK_OID:
            return test.FAIL("role path=/root: Unexpected OID for Root Block: "
                             f"Expected {self.ms05_utils.ROOT_BLOCK_OID}, Actual {str(oid)}",
                             "https://specs.amwa.tv/ms-05-02/branches/"
                             f"{self.apis[MS05_API_KEY]['spec_branch']}"
                             "/docs/Blocks.html")

        return test.PASS()

    def _check_property_type(self, test, value, property_descriptor, role_path):
        """Check property type. Raises NMOSTestException on error"""
        error_msg_base = f"role path={self.ms05_utils.create_role_path_string(role_path)}: " \
            f"property name={property_descriptor.name}: property id={property_descriptor.id}: "

        if value is None:
            if property_descriptor.isNullable:
                return
            else:
                raise NMOSTestException(test.FAIL(f"{error_msg_base}Non-nullable property set to null."))

        if self.ms05_utils.primitive_to_python_type(property_descriptor.typeName):
            # Special case: if this is a floating point value it
            # can be intepreted as an int in the case of whole numbers
            # e.g. 0.0 -> 0, 1.0 -> 1
            if self.ms05_utils.primitive_to_python_type(property_descriptor.typeName) \
                    == float and isinstance(value, int):
                return

            if not isinstance(value, self.ms05_utils.primitive_to_python_type(property_descriptor.typeName)):
                raise NMOSTestException(test.FAIL(f"{error_msg_base} value={str(value)} is not of type "
                                                  f"{str(property_descriptor.typeName)}"))
        else:
            self.ms05_utils.queried_datatype_schema_validate(test, value, property_descriptor.typeName, role_path)

        return

    def _check_get_sequence_item(self, test, oid, role_path, sequence_values, property_descriptor):
        error_msg_base = f"role path={self.ms05_utils.create_role_path_string(role_path)}: "
        self.get_sequence_item_metadata.checked = True
        sequence_index = 0
        for property_value in sequence_values:
            method_result = self.ms05_utils.get_sequence_item(test, property_descriptor.id,
                                                              sequence_index, oid=oid, role_path=role_path)
            if isinstance(method_result, NcMethodResultError):
                self.get_sequence_item_metadata.error = True
                self.get_sequence_item_metadata.error_msg += f"{error_msg_base}" \
                    f"property name={property_descriptor.name}: " \
                    f"property id={str(property_descriptor.id)}: " \
                    f"GetSequenceItem error: {method_result.error}; "
                continue
            if self.ms05_utils.is_error_status(method_result.status):
                self.get_sequence_item_metadata.error = True
                self.get_sequence_item_metadata.error_msg += f"{error_msg_base}" \
                    f"property name={property_descriptor.name}: " \
                    f"property id={str(property_descriptor.id)}: " \
                    "GetSequenceItem error: " \
                    "NcMethodResultError MUST be returned on an error; "
                continue
            if property_value != method_result.value:
                self.get_sequence_item_metadata.error = True
                self.get_sequence_item_metadata.error_msg += f"{error_msg_base}" \
                    f"property name={property_descriptor.name}: " \
                    f"property id={str(property_descriptor.id)}: " \
                    f"Expected value: {str(property_value)}, " \
                    f"Actual value: {str(method_result.value)} " \
                    f"at index {sequence_index}; "
            sequence_index += 1

    def _check_get_sequence_length(self, test, oid, role_path, sequence_values, property_descriptor):
        error_msg_base = f"role path={self.ms05_utils.create_role_path_string(role_path)}: "

        self.get_sequence_length_metadata.checked = True
        method_result = self.ms05_utils.get_sequence_length(test, property_descriptor.id,
                                                            oid=oid, role_path=role_path)

        if isinstance(method_result, NcMethodResultError):
            self.get_sequence_length_metadata.error_msg += f"{error_msg_base}" \
                f"property name={property_descriptor.name}: " \
                f"property id={str(property_descriptor.id)}: " \
                f"GetSequenceLength error: {str(method_result.errorMessage)}; "
            self.get_sequence_length_metadata.error = True
            return False
        if self.ms05_utils.is_error_status(method_result.status):
            self.get_sequence_length_metadata.error = True
            self.get_sequence_length_metadata.error_msg += f"{error_msg_base}" \
                f"property name={property_descriptor.name}: " \
                f"property id={str(property_descriptor.id)}: " \
                "GetSequenceLength error: " \
                "NcMethodResultError MUST be returned on an error; "
            return False
        length = method_result.value
        if length != len(sequence_values):
            self.get_sequence_length_metadata.error_msg += f"{error_msg_base}" \
                f"property name={property_descriptor.name}: " \
                f"property id={str(property_descriptor.id)}: " \
                "GetSequenceLength error. Expected length: " \
                f"{str(len(sequence_values))}, Actual length: {str(length)}; "
            self.get_sequence_length_metadata.error = True
            return False
        return True

    def _check_sequence_methods(self, test, oid, role_path, sequence_values, property_descriptor):
        """Check that sequence manipulation methods work correctly. Raises NMOSTestException on error"""
        if sequence_values is None:
            if not property_descriptor.isNullable:
                self.get_sequence_length_metadata.error = True
                self.get_sequence_length_metadata.error_msg += \
                    f"role path={self.ms05_utils.create_role_path_string(role_path)}: " \
                    f"property name={property_descriptor.name}: " \
                    f"property id={str(property_descriptor.id)}: " \
                    "Non-nullable property set to null; "
        else:
            self._check_get_sequence_item(test, oid, role_path, sequence_values, property_descriptor)
            self._check_get_sequence_length(test, oid, role_path, sequence_values, property_descriptor)

    def _check_object_properties(self, test, reference_class_descriptor, oid, role_path):
        error_msg_base = f"role path={self.ms05_utils.create_role_path_string(role_path)}: "
        """Check properties of an object against reference NcClassDescriptor"""
        for property_descriptor in reference_class_descriptor.properties:
            method_result = self.ms05_utils.get_property(test, property_descriptor.id,
                                                         oid=oid, role_path=role_path)
            if isinstance(method_result, NcMethodResultError):
                self.device_model_metadata.error = True
                self.device_model_metadata.error_msg += f"{error_msg_base}" \
                    f"property name={property_descriptor.name}: " \
                    f"property id={str(property_descriptor.id)}: " \
                    f"GetProperty error: {str(method_result.errorMessage)}; "
                continue
            if self.ms05_utils.is_error_status(method_result.status):
                self.device_model_metadata.error = True
                self.device_model_metadata.error_msg += f"{error_msg_base}" \
                    f"property name={property_descriptor.name}: " \
                    f"property id={str(property_descriptor.id)}: " \
                    "GetProperty error: NcMethodResultError MUST be returned on an error; "
                continue
            property_value = method_result.value

            if property_descriptor.isDeprecated:
                self.deprecated_property_metadata.checked = True
                if method_result.status != NcMethodStatus.PropertyDeprecated:
                    self.deprecated_property_metadata.error = True
                    self.deprecated_property_metadata.error_msg += f"{error_msg_base}" \
                        f"property name={property_descriptor.name}: " \
                        f"property id={str(property_descriptor.id)}: " \
                        f"Expected GetProperty to return {NcMethodStatus.PropertyDeprecated.name} " \
                        f"({NcMethodStatus.PropertyDeprecated.value}) status; "

            if not property_value:
                continue

            # validate property type
            if property_descriptor.isSequence:
                for sequence_value in property_value:
                    self._check_property_type(
                        test,
                        sequence_value,
                        property_descriptor,
                        role_path)
                self._check_sequence_methods(test,
                                             oid,
                                             role_path,
                                             property_value,
                                             property_descriptor)
            else:
                self._check_property_type(
                    test,
                    property_value,
                    property_descriptor,
                    role_path)
        return

    def _check_unique_roles(self, role, role_cache, role_path):
        """Check role is unique within containing Block"""
        if role in role_cache:
            error_msg_base = f"role path={self.ms05_utils.create_role_path_string(role_path)}: "
            self.unique_roles_metadata.error = True
            self.unique_roles_metadata.error_msg += f"{error_msg_base}Multiple objects use role={role}; "
        else:
            self.unique_roles_metadata.checked = True
            role_cache.append(role)

    def _check_unique_oid(self, oid, role_path):
        """Check oid is globally unique"""
        if oid in self.oid_cache:
            error_msg_base = f"role path={self.ms05_utils.create_role_path_string(role_path)}: "
            self.unique_oids_metadata.error = True
            self.unique_oids_metadata.error_msg = f"{error_msg_base}Multiple objects use OID={oid}; "
        else:
            self.unique_oids_metadata.checked = True
            self.oid_cache.append(oid)

    def _check_owner(self, test, block_oid, member_desc_owner, oid, role_path):
        """Check owner is correct"""
        # Check the oid of the containing NcBlock (block_oid) is consistant with both the
        # NcBlockMemberDescriptor owner (member_desc_owner) and the owner property queried from the
        # NcObject (method_result.value)

        method_result = self.ms05_utils.get_property(test, NcObjectProperties.OWNER.value, oid=oid, role_path=role_path)

        if isinstance(method_result, NcMethodResultError):
            error_msg_base = f"role path={self.ms05_utils.create_role_path_string(role_path)}: "
            self.device_model_metadata.error = True
            self.device_model_metadata.error_msg = f"{error_msg_base}Unable to get owner property; " \
                f"{method_result.errorMessage}; "
            return

        if block_oid != method_result.value:
            error_msg_base = f"role path={self.ms05_utils.create_role_path_string(role_path)}: "
            self.device_model_metadata.error = True
            self.device_model_metadata.error_msg = f"{error_msg_base} inconsistent owner property; " \
                f"containing NcBlock oid: {block_oid}, NcObject owner property: {method_result.value}; "

        if block_oid != member_desc_owner:
            error_msg_base = f"role path={self.ms05_utils.create_role_path_string(role_path)}: "
            self.device_model_metadata.error = True
            self.device_model_metadata.error_msg = f"{error_msg_base} inconsistent owner property; " \
                f"containing NcBlock oid: {block_oid}, NcBlockMemberDescriptor owner property: {member_desc_owner}; "

    def _check_manager(self, class_id, owner, class_descriptors, manager_cache, role_path):
        """Check manager is singleton and that it inherits from NcManager"""
        # detemine the standard base class name
        base_id = self.ms05_utils.get_base_class_id(class_id)
        if base_id not in class_descriptors:
            self.device_model_metadata.error = True
            self.device_model_metadata.error_msg += f"Cant find base class for class id: {str(class_id)}; "
            return
        base_class_name = class_descriptors[base_id].name

        # manager checks
        if self.ms05_utils.is_manager(class_id):
            if owner != self.ms05_utils.ROOT_BLOCK_OID:
                self.managers_members_root_block_metadata.error = True
                self.managers_members_root_block_metadata.error_msg += \
                    f"role path={self.ms05_utils.create_role_path_string(role_path)}: "
            if base_class_name in manager_cache:
                self.managers_are_singletons_metadata.error = True
                self.managers_are_singletons_metadata.error_msg += \
                    f"role path={self.ms05_utils.create_role_path_string(role_path)}: " \
                    "More than one instance found in Device Model: "
            else:
                self.managers_members_root_block_metadata.checked = True
                self.managers_are_singletons_metadata.checked = True
                manager_cache.append(base_class_name)

    def _check_touchpoints(self, test, oid, role_path):
        """Touchpoint checks"""
        error_msg_base = f"role path={self.ms05_utils.create_role_path_string(role_path)}: "
        method_result = self.ms05_utils.get_property(
            test,
            NcObjectProperties.TOUCHPOINTS.value,
            oid=oid,
            role_path=role_path)

        if isinstance(method_result, NcMethodResultError):
            self.device_model_metadata.error = True
            self.device_model_metadata.error_msg += f"{error_msg_base}" \
                f"property name={NcObjectProperties.TOUCHPOINTS.name}: " \
                f"property id={NcObjectProperties.TOUCHPOINTS.value}: " \
                f"Error getting touchpoints for object: {str(method_result.errorMessage)}; "
            return
        if self.ms05_utils.is_error_status(method_result.status):
            self.device_model_metadata.error = True
            self.device_model_metadata.error_msg += f"{error_msg_base}" \
                f"property name={NcObjectProperties.TOUCHPOINTS.name}: " \
                f"property id={NcObjectProperties.TOUCHPOINTS.value}: " \
                "GetProperty error: NcMethodResultError MUST be returned on an error; "
            return

        # touchpoints can be null
        if method_result.value is None:
            return

        if not isinstance(method_result.value, list):
            self.device_model_metadata.error = True
            self.device_model_metadata.error_msg += f"{error_msg_base}Expected touchpoint sequence for object: "
            return

        try:
            for touchpoint_json in method_result.value:
                # Check base type
                self.ms05_utils.queried_datatype_schema_validate(test, touchpoint_json, NcTouchpoint.__name__,
                                                                 role_path=role_path)
                datatype_name = NcTouchpointNmos.__name__ \
                    if touchpoint_json["contextNamespace"] == "x-nmos" else NcTouchpointNmosChannelMapping.__name__
                # Check concrete types
                self.ms05_utils.queried_datatype_schema_validate(test, touchpoint_json, datatype_name,
                                                                 role_path=role_path)
                self.touchpoints_metadata.checked = True
        except NMOSTestException as e:
            self.touchpoints_metadata.error = True
            self.touchpoints_metadata.error_msg = f"{error_msg_base}{str(e.args[0].detail)}"

    def _check_constraint_override(self, test, constraint, override_constraint, context):
        error_msg_base = f"{context}{constraint.level} constraints overridden by " \
            f"{override_constraint.level} constraints: "

        # Is this a number constraint
        if isinstance(constraint, (NcParameterConstraintsNumber, NcPropertyConstraintsNumber)):
            self.constraint_hierarchy_metadata.checked = True

            # Are these the same type of constraints
            if not isinstance(override_constraint, (NcParameterConstraintsNumber, NcPropertyConstraintsNumber)):
                self.constraint_hierarchy_metadata.error = True
                self.constraint_hierarchy_metadata.error_msg += \
                    f"{error_msg_base}cannot override {constraint.__class__.__name__} constraint type " \
                    f"with {override_constraint.__class__.__name__} constraint type. " \
                    f"constraint={str(constraint)}, override constraint={str(override_constraint)}; "
                return
            if (constraint.minimum is not None and override_constraint.minimum is None) \
                    or (constraint.maximum is not None and override_constraint.maximum is None) \
                    or (constraint.step is not None and override_constraint.step is None):
                self.constraint_hierarchy_metadata.error = True
                self.constraint_hierarchy_metadata.error_msg += \
                    f"{error_msg_base}Constraints implementations MUST fully override the previous level. " \
                    f"constraint={str(constraint)}, override constraint={str(override_constraint)}; "
                return
            if (constraint.minimum and override_constraint.minimum < constraint.minimum) or \
                    (constraint.maximum and override_constraint.maximum > constraint.maximum) or \
                    (constraint.step and override_constraint.step < constraint.step):
                self.constraint_hierarchy_metadata.error = True
                self.constraint_hierarchy_metadata.error_msg += \
                    f"{error_msg_base}Constraints implementations MUST not result in widening " \
                    "the minimum, maximum or step constraint defined in previous levels. " \
                    f"constraint={str(constraint)}, override constraint={str(override_constraint)}; "
                return
        # is this a string constraint
        if isinstance(constraint, (NcParameterConstraintsString, NcPropertyConstraintsString)):
            self.constraint_hierarchy_metadata.checked = True

            # Are these the same type of constraints
            if not isinstance(override_constraint, (NcParameterConstraintsString, NcPropertyConstraintsString)):
                self.constraint_hierarchy_metadata.error = True
                self.constraint_hierarchy_metadata.error_msg += \
                    f"{error_msg_base}cannot override {constraint.__class__.__name__} constraint type " \
                    f"with {override_constraint.__class__.__name__} constraint type. " \
                    f"constraint={str(constraint)}, override constraint={str(override_constraint)}; "
                return
            if (constraint.maxCharacters is not None and override_constraint.maxCharacters is None) \
                    or (constraint.pattern is not None and override_constraint.pattern is None):
                self.constraint_hierarchy_metadata.error = True
                self.constraint_hierarchy_metadata.error_msg += \
                    f"{error_msg_base}Constraints implementations MUST fully override the previous level. " \
                    f"constraint={str(constraint)}, override constraint=" \
                    f"{str(override_constraint)}; "
                return
            if constraint.maxCharacters \
                    and override_constraint.maxCharacters > constraint.maxCharacters:
                self.constraint_hierarchy_metadata.error = True
                self.constraint_hierarchy_metadata.error_msg += \
                    f"{error_msg_base}Constraints implementations MUST not result in widening " \
                    "the maxCharacters constraint defined in previous levels. " \
                    f"constraint={str(constraint)}, override constraint={str(override_constraint)}; "
                return
            # Hmm, difficult to meaningfully determine whether an overridden regex pattern is widening the constraint
            # so rule of thumb here is that a shorter pattern is less constraining that a longer pattern
            if constraint.pattern and len(override_constraint.pattern) < len(constraint.pattern):
                self.constraint_hierarchy_metadata.error = True
                self.constraint_hierarchy_metadata.error_msg += \
                    f"{error_msg_base}Constraints implementations MUST not result in widening " \
                    "the pattern constraint defined in previous levels. " \
                    f"constraint={str(constraint)}, override constraint={str(override_constraint)}; "

    def _check_constraints_hierarchy(self, test, attribute_descriptor, datatype_descriptor, object_runtime_constraints,
                                     role_path, context=""):
        error_msg_base = f"role path={self.ms05_utils.create_role_path_string(role_path)}, {context}"
        if isinstance(attribute_descriptor, NcPropertyDescriptor):
            error_msg_base += f"property name={attribute_descriptor.name}: " \
                              f"property id={attribute_descriptor.id}: "
        if isinstance(attribute_descriptor, NcParameterDescriptor):
            error_msg_base += f"parameter name={attribute_descriptor.name}: "

        datatype_constraints = None
        runtime_constraints = None
        # Level 0: Datatype constraints
        if attribute_descriptor.typeName:
            if datatype_descriptor:
                datatype_constraints = datatype_descriptor.constraints
            else:
                self.constraint_hierarchy_metadata.error = True
                self.constraint_hierarchy_metadata.error_msg += \
                    f"{error_msg_base}Unknown data type: {attribute_descriptor.typeName}; "
                return

        # Level 1: Property constraints
        property_constraints = attribute_descriptor.constraints
        # Level 3: Runtime constraints
        if object_runtime_constraints:
            for object_runtime_constraint in object_runtime_constraints:
                if isinstance(attribute_descriptor, NcPropertyDescriptor) and \
                        object_runtime_constraint.propertyId == attribute_descriptor.id:
                    runtime_constraints = object_runtime_constraint

        if datatype_constraints and property_constraints:
            self._check_constraint_override(test, datatype_constraints, property_constraints, error_msg_base)

        if datatype_constraints and runtime_constraints:
            self._check_constraint_override(test, datatype_constraints, runtime_constraints, error_msg_base)

        if property_constraints and runtime_constraints:
            self._check_constraint_override(test, property_constraints, runtime_constraints, error_msg_base)

    def _check_constraint(self, test, constraint, attribute_descriptor, test_metadata, role_path=None, context=""):
        # checks that constraints are for the correct type of property/parameter
        # checks that default values are of the correct type
        datatype_name = attribute_descriptor.name if isinstance(attribute_descriptor, NcDatatypeDescriptor) \
            else attribute_descriptor.typeName
        role_path_string = f"role path={self.ms05_utils.create_role_path_string(role_path)}: " if role_path else ""
        # runtime constraints apply to properties
        error_msg_base = f"{role_path_string}{context}: "
        if constraint.defaultValue:
            if isinstance(constraint.defaultValue, list) is not attribute_descriptor.isSequence:
                test_metadata.error = True
                message = "Default value sequence was expected " \
                    if attribute_descriptor.isSequence else "Unexpected default value sequence. "
                test_metadata.error_msg = f"{error_msg_base}{message}; "
                return
            if attribute_descriptor.isSequence:
                for value in constraint.defaultValue:
                    self.ms05_utils.queried_datatype_schema_validate(test, value, datatype_name,
                                                                     role_path=role_path)
            else:
                self.ms05_utils.queried_datatype_schema_validate(test, constraint.defaultValue, datatype_name,
                                                                 role_path=role_path)
        datatype = self.ms05_utils.resolve_datatype(test, datatype_name)
        if isinstance(constraint, (NcParameterConstraintsNumber, NcPropertyConstraintsNumber)):
            if datatype not in ["NcInt16", "NcInt32", "NcInt64", "NcUint16", "NcUint32",
                                "NcUint64", "NcFloat32", "NcFloat64"]:
                test_metadata.error = True
                test_metadata.error_msg = f"{error_msg_base}{datatype} " \
                    f"cannot be constrainted by {constraint.__class__.__name__}; "
        if isinstance(constraint, (NcParameterConstraintsString, NcPropertyConstraintsString)):
            if datatype not in ["NcString"]:
                test_metadata.error = True
                test_metadata.error_msg = f"{error_msg_base}{datatype} " \
                    f"cannot be constrainted by {constraint.__class__.__name__}; "

    def _check_runtime_constraints(self, test, child_object, property_descriptor):
        if child_object.runtime_constraints:
            constraints = [c for c in child_object.runtime_constraints if property_descriptor.id == c.propertyId]
            if len(constraints) > 1:
                self.runtime_constraints_metadata.error = True
                constraints_str = ", ".join([f"constraints={str(c)}" for c in constraints])
                self.runtime_constraints_metadata.error_msg += \
                    f"role path={self.ms05_utils.create_role_path_string(child_object.role_path)}, " \
                    f"property name={property_descriptor.name}, property id={property_descriptor.id}. " \
                    f"More than one runtime constraint found for property: {constraints_str}"
            if len(constraints) == 1:
                self.runtime_constraints_metadata.checked = True
                self._check_constraint(test,
                                       constraints[0],
                                       property_descriptor,
                                       self.runtime_constraints_metadata,
                                       child_object.role_path,
                                       context=f"property id={property_descriptor.id}, "
                                       f"property name={property_descriptor.name}: ")

    def _check_property_constraints(self, test, property_descriptor, role_path):
        if property_descriptor.constraints:
            self.property_constraints_metadata.checked = True
            self._check_constraint(test,
                                   property_descriptor.constraints,
                                   property_descriptor,
                                   self.property_constraints_metadata,
                                   role_path,
                                   f"property id={property_descriptor.id}, "
                                   f"property name={property_descriptor.name}: ")

    def _check_parameter_constraints(self, test, parameter_descriptor, method_descriptor, datatype_descriptor,
                                     role_path):
        error_msg_base = f"method name={method_descriptor.name}, " \
            f"method id={method_descriptor.id}, " \
            f"parameter name={parameter_descriptor.name}, " \
            f"parameter datatype={parameter_descriptor.typeName}: "
        if parameter_descriptor.constraints:
            self.parameter_constraints_metadata.checked = True
            self._check_constraint(test,
                                   parameter_descriptor.constraints,
                                   parameter_descriptor,
                                   self.parameter_constraints_metadata,
                                   role_path,
                                   context=error_msg_base)
        # Check field constraints if this parameter is a struct
        if isinstance(datatype_descriptor, NcDatatypeDescriptorStruct):
            constrained_field_descriptors = [f for f in datatype_descriptor.fields if f.constraints]
            for field_descriptor in constrained_field_descriptors:
                self._check_constraint(test,
                                       field_descriptor.constraints,
                                       field_descriptor,
                                       self.parameter_constraints_metadata,
                                       role_path,
                                       context=f"{error_msg_base}"
                                       f"field name={field_descriptor.name}, "
                                       f"field datatype={field_descriptor.typeName}: ")

    def _check_object_constraints(self, test, child_object, class_descriptor, datatype_descriptors):
        for property_descriptor in class_descriptor.properties:
            if property_descriptor.isReadOnly:
                continue
            datatype_descriptor = datatype_descriptors.get(property_descriptor.typeName)
            self._check_runtime_constraints(test, child_object, property_descriptor)
            self._check_property_constraints(test, property_descriptor, child_object.role_path)
            self._check_constraints_hierarchy(test, property_descriptor,
                                              datatype_descriptor,
                                              child_object.runtime_constraints,
                                              child_object.role_path)
        for method_descriptor in class_descriptor.methods:
            context = f"method name={method_descriptor.name}: method id={method_descriptor.id}: "
            for parameter_descriptor in method_descriptor.parameters:
                datatype_descriptor = datatype_descriptors.get(parameter_descriptor.typeName)
                self._check_parameter_constraints(test, parameter_descriptor,
                                                  method_descriptor,
                                                  datatype_descriptor,
                                                  child_object.role_path)
                self._check_constraints_hierarchy(test, parameter_descriptor,
                                                  datatype_descriptor,
                                                  None,  # methods don't have runtime constraints
                                                  child_object.role_path,
                                                  context)

    def _check_block(self, test, block, class_descriptors, datatype_descriptors):
        for child_object in block.child_objects:
            # If this child object is a Block, recurse
            if type(child_object) is NcBlock:
                self._check_block(test,
                                  child_object,
                                  class_descriptors,
                                  datatype_descriptors)
        role_cache = []
        manager_cache = []
        for child_object in block.child_objects:
            descriptor = child_object.member_descriptor
            role_path = self.ms05_utils.create_role_path(block.role_path, descriptor.role)

            self._check_unique_roles(descriptor.role, role_cache, block.role_path)
            self._check_unique_oid(descriptor.oid, block.role_path)
            self._check_owner(test, block.oid, child_object.owner, child_object.oid, child_object.role_path)

            # check for non-standard classes
            if self.ms05_utils.is_non_standard_class(descriptor.classId):
                self.organization_metadata.checked = True
            self._check_manager(descriptor.classId, descriptor.owner, class_descriptors, manager_cache, role_path)
            self._check_touchpoints(test, descriptor.oid, role_path)

            class_identifier = self.ms05_utils.create_class_id_string(descriptor.classId)
            if class_identifier and class_identifier in class_descriptors:
                class_descriptor = class_descriptors[class_identifier]
                self._check_object_properties(test,
                                              class_descriptor,
                                              descriptor.oid,
                                              role_path)
                self._check_object_constraints(test,
                                               child_object,
                                               class_descriptor,
                                               datatype_descriptors)
            else:
                self.device_model_metadata.error = True
                self.device_model_metadata.error_msg += \
                    f"role path={self.ms05_utils.create_role_path_string(role_path)}: "\
                    f"class id={class_identifier}" \
                    f"Class not advertised by Class Manager: {class_identifier}; "

            if class_identifier not in self.ms05_utils.reference_class_descriptors and \
                    not self.ms05_utils.is_non_standard_class(descriptor.classId):
                # Not a standard or non-standard class
                self.organization_metadata.error = True
                self.organization_metadata.error_msg = \
                    f"role path={str(self.ms05_utils.create_role_path_string(role_path))}: " \
                    f"class id={class_identifier}: " \
                    f"Non-standard class id does not contain authority key: {class_identifier}; "

    def _check_device_model(self, test):
        if not self.device_model_metadata.checked:
            class_manager = self.ms05_utils.get_class_manager(test)
            device_model = self.ms05_utils.query_device_model(test)

            self._check_block(test,
                              device_model,
                              class_manager.class_descriptors,
                              class_manager.datatype_descriptors)

            self.device_model_metadata.checked = True
        return

    def test_ms05_02(self, test):
        """Device Model: Device Model is correct according to classes and datatypes advertised by Class Manager"""
        # https://specs.amwa.tv/ms-05-02/releases/v1.0.0/docs/Managers.html
        # https://specs.amwa.tv/ms-05-02/releases/v1.0.0/docs/Workers.html

        self._check_device_model(test)

        if self.device_model_metadata.error:
            return test.FAIL(self.device_model_metadata.error_msg)

        if not self.device_model_metadata.checked:
            return test.UNCLEAR("Unable to check Device Model.")

        return test.PASS()

    def test_ms05_03(self, test):
        """Device Model: roles are unique within a containing Block"""
        # https://specs.amwa.tv/ms-05-02/releases/v1.0.0/docs/NcObject.html

        try:
            self._check_device_model(test)
        except NMOSTestException as e:
            # Couldn't validate model so can't perform test
            return test.FAIL(e.args[0].detail, e.args[0].link)

        if self.unique_roles_metadata.error:
            return test.FAIL(f"{self.unique_roles_metadata.error_msg} "
                             "The role of an object MUST be unique within its containing block.",
                             "https://specs.amwa.tv/ms-05-02/branches/"
                             f"{self.apis[MS05_API_KEY]['spec_branch']}"
                             "/docs/NcObject.html")

        if not self.unique_roles_metadata.checked:
            return test.UNCLEAR("No roles were checked.")

        return test.PASS()

    def test_ms05_04(self, test):
        """Device Model: oids are globally unique"""
        # https://specs.amwa.tv/ms-05-02/releases/v1.0.0/docs/NcObject.html

        try:
            self._check_device_model(test)
        except NMOSTestException as e:
            # Couldn't validate model so can't perform test
            return test.FAIL(e.args[0].detail, e.args[0].link)

        if self.unique_oids_metadata.error:
            return test.FAIL(f"{self.unique_oids_metadata.error_msg} "
                             "Object ids (oid property) MUST uniquely identity objects in the device model.",
                             "https://specs.amwa.tv/ms-05-02/branches/"
                             f"{self.apis[MS05_API_KEY]['spec_branch']}"
                             "/docs/NcObject.html")

        if not self.unique_oids_metadata.checked:
            return test.UNCLEAR("Unable to check for unique OIDs.")

        return test.PASS()

    def test_ms05_05(self, test):
        """Device Model: non-standard classes contain an authority key"""
        # For organizations which own a unique CID or OUI the authority key MUST be the organization
        # identifier as an integer which MUST be negated.
        # For organizations which do not own a unique CID or OUI the authority key MUST be 0
        # https://specs.amwa.tv/ms-05-02/releases/v1.0.0/docs/Framework.html#ncclassid

        try:
            self._check_device_model(test)
        except NMOSTestException as e:
            # Couldn't validate model so can't perform test
            return test.FAIL(e.args[0].detail, e.args[0].link)

        if self.organization_metadata.error:
            return test.FAIL(self.organization_metadata.error_msg,
                             "https://specs.amwa.tv/ms-05-02/branches/"
                             f"{self.apis[MS05_API_KEY]['spec_branch']}"
                             "/docs/Framework.html#ncclassid")

        if not self.device_model_metadata.checked:
            return test.UNCLEAR("Unable to check Device Model.")

        if not self.organization_metadata.checked:
            return test.UNCLEAR("No non-standard classes found.")

        return test.PASS()

    def test_ms05_06(self, test):
        """Device Model: touchpoint datatypes are correct"""
        # For general NMOS contexts (IS-04, IS-05 and IS-07) the NcTouchpointNmos datatype MUST be used
        # which has a resource of type NcTouchpointResourceNmos.
        # For IS-08 Audio Channel Mapping the NcTouchpointResourceNmosChannelMapping datatype MUST be used
        # https://specs.amwa.tv/ms-05-02/releases/v1.0.0/docs/NcObject.html#touchpoints

        try:
            self._check_device_model(test)
        except NMOSTestException as e:
            # Couldn't validate model so can't perform test
            return test.FAIL(e.args[0].detail, e.args[0].link)

        if self.touchpoints_metadata.error:
            return test.FAIL(self.touchpoints_metadata.error_msg,
                             "https://specs.amwa.tv/ms-05-02/branches/"
                             f"{self.apis[MS05_API_KEY]['spec_branch']}"
                             "/docs/NcObject.html#touchpoints")

        if not self.device_model_metadata.checked:
            return test.UNCLEAR("Unable to check Device Model.")

        if not self.touchpoints_metadata.checked:
            return test.UNCLEAR("No Touchpoints found.")
        return test.PASS()

    def test_ms05_07(self, test):
        """Device Model: deprecated properties are indicated"""
        # Getting deprecated properties MUST return a PropertyDeprecated status
        # https://specs.amwa.tv/ms-05-02/releases/v1.0.0/docs/Framework.html#ncmethodstatus

        try:
            self._check_device_model(test)
        except NMOSTestException as e:
            # Couldn't validate model so can't perform test
            return test.FAIL(e.args[0].detail, e.args[0].link)

        if self.deprecated_property_metadata.error:
            return test.FAIL(self.deprecated_property_metadata.error_msg,
                             "https://specs.amwa.tv/ms-05-02/branches/"
                             f"{self.apis[MS05_API_KEY]['spec_branch']}"
                             "/docs/Framework.html#ncmethodstatus")

        if not self.device_model_metadata.checked:
            return test.UNCLEAR("Unable to check Device Model.")

        if not self.deprecated_property_metadata.checked:
            return test.UNCLEAR("No deprecated properties found.")
        return test.PASS()

    def test_ms05_08(self, test):
        """Device Model: NcDescriptor, NcPropertyConstraint and NcParameterConstraint
           are not subtyped by non-standard datatypes"""
        try:
            class_manager = self.ms05_utils.get_class_manager(test)
            # Check for subtyping of NcDescriptor, NcParameterConstraint, NcPropertyConstraint
            if not class_manager.datatype_descriptors:
                return
            not_subtypable_datatypes = self.ms05_utils.get_not_subtypable_datatypes()

            illegal_subtypes = [n for n, d in class_manager.datatype_descriptors.items()
                                if (isinstance(d, NcDatatypeDescriptorStruct)
                                    and d.parentType in not_subtypable_datatypes  # shouldn't inherit
                                    and n not in not_subtypable_datatypes)]  # unless a standard datatype

            if bool(illegal_subtypes):
                return test.FAIL("NcDescriptor, NcPropertyConstraint and NcParameterConstraint SHOULD NOT "
                                 f"be subtyped: the following subtypes are illegal: {str(illegal_subtypes)}")
        except NMOSTestException as e:
            # Couldn't validate model so can't perform test
            return test.FAIL(e.args[0].detail, e.args[0].link)

        return test.PASS()

    def test_ms05_09(self, test):
        """Managers: managers are members of the Root Block"""
        # All managers MUST always exist as members in the Root Block and have a fixed role.
        # https://specs.amwa.tv/ms-05-02/releases/v1.0.0/docs/Managers.html

        try:
            self._check_device_model(test)
        except NMOSTestException as e:
            # Couldn't validate model so can't perform test
            return test.FAIL(e.args[0].detail, e.args[0].link)

        if self.managers_members_root_block_metadata.error:
            return test.FAIL(f"{self.managers_members_root_block_metadata.error_msg}"
                             "Managers MUST be members of the Root Block. ",
                             "https://specs.amwa.tv/ms-05-02/branches/"
                             f"{self.apis[MS05_API_KEY]['spec_branch']}"
                             "/docs/Managers.html")

        if not self.managers_members_root_block_metadata.checked:
            return test.UNCLEAR("No managers found in Device Model.")

        return test.PASS()

    def test_ms05_10(self, test):
        """Managers: managers are singletons"""
        # Managers are singleton (MUST only be instantiated once) classes.
        # https://specs.amwa.tv/ms-05-02/releases/v1.0.0/docs/Managers.html

        try:
            self._check_device_model(test)
        except NMOSTestException as e:
            # Couldn't validate model so can't perform test
            return test.FAIL(e.args[0].detail, e.args[0].link)

        if self.managers_are_singletons_metadata.error:
            return test.FAIL(f"{self.managers_are_singletons_metadata.error_msg}"
                             "Managers must be singleton classes. ",
                             "https://specs.amwa.tv/ms-05-02/branches/"
                             f"{self.apis[MS05_API_KEY]['spec_branch']}"
                             "/docs/Managers.html")

        if not self.managers_are_singletons_metadata.checked:
            return test.UNCLEAR("No managers found in Device Model.")

        return test.PASS()

    def test_ms05_11(self, test):
        """Managers: Class Manager exists with correct role"""
        # Class manager exists in root
        # https://specs.amwa.tv/ms-05-02/releases/v1.0.0/docs/Managers.html

        spec_link = "https://specs.amwa.tv/ms-05-02/branches/" \
            f"{self.apis[MS05_API_KEY]['spec_branch']}/docs/Managers.html"

        class_manager = self.ms05_utils.get_class_manager(test)

        class_id_str = self.ms05_utils.create_class_id_string(StandardClassIds.NCCLASSMANAGER.value)
        class_descriptor = self.ms05_utils.reference_class_descriptors[class_id_str]

        if class_manager.role != class_descriptor.fixedRole:
            return test.FAIL(f"Class Manager role={class_manager.role}. "
                             "Class Manager MUST have a role of ClassManager.", spec_link)

        return test.PASS()

    def test_ms05_12(self, test):
        """Managers: Device Manager exists with correct role"""
        # A minimal device implementation MUST have a device manager in the Root Block.
        # https://specs.amwa.tv/ms-05-02/releases/v1.0.0/docs/Managers.html

        spec_link = "https://specs.amwa.tv/ms-05-02/branches/" \
            f"{self.apis[MS05_API_KEY]['spec_branch']}/docs/Managers.html"

        device_manager = self.ms05_utils.get_device_manager(test)

        class_id_str = self.ms05_utils.create_class_id_string(StandardClassIds.NCDEVICEMANAGER.value)
        class_descriptor = self.ms05_utils.reference_class_descriptors[class_id_str]

        if device_manager.role != class_descriptor.fixedRole:
            return test.FAIL(f"Device Manager role={device_manager.role}. "
                             "Device Manager MUST have a role of DeviceManager.", spec_link)

        # Check MS-05-02 Version
        property_id = NcDeviceManagerProperties.NCVERSION.value

        method_result = self.ms05_utils.get_property(test, property_id,
                                                     oid=device_manager.oid,
                                                     role_path=device_manager.role_path)
        if isinstance(method_result, NcMethodResultError):
            return test.FAIL(f"Error getting version from Device Manager : {str(method_result.errorMessage)}")

        if self.ms05_utils.is_error_status(method_result.status):
            return test.FAIL("NcMethodResultError MUST be returned on an error",
                             "https://specs.amwa.tv/ms-05-02/branches/"
                             f"{self.apis[MS05_API_KEY]['spec_branch']}"
                             "/docs/Framework.html#ncmethodresulterror")

        version = method_result.value

        if self.ms05_utils.compare_api_version(version, self.apis[MS05_API_KEY]["version"]):
            return test.FAIL(f"Unexpected version. Expected: {self.apis[MS05_API_KEY]['version']}"
                             f". Actual: {str(version)}")
        return test.PASS()

    def test_ms05_13(self, test):
        """Class Manager: GetControlClass method is correct"""
        # Where the functionality of a device uses control classes and datatypes listed in this
        # specification it MUST comply with the model definitions published
        # https://specs.amwa.tv/ms-05-02/releases/v1.0.0/docs/Framework.html#ncclassmanager

        class_manager = self.ms05_utils.get_class_manager(test)

        for _, class_descriptor in class_manager.class_descriptors.items():
            for include_inherited in [False, True]:
                method_result = self.ms05_utils.get_control_class(test,
                                                                  class_descriptor.classId,
                                                                  include_inherited,
                                                                  oid=class_manager.oid,
                                                                  role_path=class_manager.role_path)
                if isinstance(method_result, NcMethodResultError):
                    return test.FAIL("Error calling getControlClass on ClassManager: "
                                     f"{str(method_result.errorMessage)}")

                if self.ms05_utils.is_error_status(method_result.status):
                    return test.FAIL("Error calling getControlClass on ClassManager: "
                                     "NcMethodResultError MUST be returned on an error",
                                     "https://specs.amwa.tv/ms-05-02/branches/"
                                     f"{self.apis[MS05_API_KEY]['spec_branch']}"
                                     "/docs/Framework.html#ncmethodresulterror")

                # Yes, we already have the class descriptor, but we might want its inherited attributes
                expected_descriptor = class_manager.get_control_class(class_descriptor.classId,
                                                                      include_inherited)
                self.ms05_utils.validate_descriptor(
                    test,
                    expected_descriptor,
                    method_result.value,
                    f"Class: {str(class_descriptor.name)}: ")

        return test.PASS()

    def test_ms05_14(self, test):
        """Class Manager: GetDatatype method is correct"""
        # Where the functionality of a device uses control classes and datatypes listed in this
        # specification it MUST comply with the model definitions published
        # https://specs.amwa.tv/ms-05-02/releases/v1.0.0/docs/Framework.html#ncclassmanager

        class_manager = self.ms05_utils.get_class_manager(test)

        for _, datatype_descriptor in class_manager.datatype_descriptors.items():
            for include_inherited in [False, True]:
                method_result = self.ms05_utils.get_datatype(test,
                                                             datatype_descriptor.name,
                                                             include_inherited,
                                                             oid=class_manager.oid,
                                                             role_path=class_manager.role_path)
                if isinstance(method_result, NcMethodResultError):
                    return test.FAIL(f"Error calling getDatatype: {str(method_result.errorMessage)}")

                if self.ms05_utils.is_error_status(method_result.status):
                    return test.FAIL("Error calling getDatatype: "
                                     "NcMethodResultError MUST be returned on an error",
                                     "https://specs.amwa.tv/ms-05-02/branches/"
                                     f"{self.apis[MS05_API_KEY]['spec_branch']}"
                                     "/docs/Framework.html#ncmethodresulterror")

                expected_descriptor = class_manager.get_datatype(datatype_descriptor.name,
                                                                 include_inherited)
                self.ms05_utils.validate_descriptor(
                    test,
                    expected_descriptor,
                    method_result.value,
                    f"Datatype: {datatype_descriptor.name}: ")

        return test.PASS()

    def test_ms05_15(self, test):
        """NcObject: Get and Set methods are correct"""
        # Generic getter and setter. The value of any property of a control class MUST be retrievable
        # using the Get method.
        # https://specs.amwa.tv/ms-05-02/releases/v1.0.0/docs/NcObject.html#generic-getter-and-setter

        link = "https://specs.amwa.tv/ms-05-02/branches/" \
               f"{self.apis[MS05_API_KEY]['spec_branch']}" \
               "/docs/NcObject.html#generic-getter-and-setter" \

        error_msg_base = "role path=/root: " \
                         f"property name={NcObjectProperties.OID.name}: " \
                         f"property id={NcObjectProperties.OID.value}: "
        # Attempt to set labels
        property_id = NcObjectProperties.USER_LABEL.value

        method_result = self.ms05_utils.get_property(test, property_id,
                                                     oid=self.ms05_utils.ROOT_BLOCK_OID,
                                                     role_path=['root'])

        if isinstance(method_result, NcMethodResultError):
            return test.FAIL(f"{error_msg_base}"
                             f"GetProperty error: {str(method_result.errorMessage)}")

        if self.ms05_utils.is_error_status(method_result.status):
            return test.FAIL(f"{error_msg_base}"
                             "GetProperty error: NcMethodResultError MUST be returned on an error",
                             "https://specs.amwa.tv/ms-05-02/branches/"
                             f"{self.apis[MS05_API_KEY]['spec_branch']}"
                             "/docs/Framework.html#ncmethodresulterror")

        old_user_label = method_result.value
        # Set user label
        new_user_label = "NMOS Testing Tool"

        method_result = self.ms05_utils.set_property(test, property_id, new_user_label,
                                                     oid=self.ms05_utils.ROOT_BLOCK_OID,
                                                     role_path=['root'])

        if isinstance(method_result, NcMethodResultError):
            return test.FAIL(f"{error_msg_base}"
                             f"SetProperty error: {str(method_result.errorMessage)}")

        if self.ms05_utils.is_error_status(method_result.status):
            return test.FAIL(f"{error_msg_base}"
                             "SetProperty error: NcMethodResultError MUST be returned on an error",
                             "https://specs.amwa.tv/ms-05-02/branches/"
                             f"{self.apis[MS05_API_KEY]['spec_branch']}"
                             "/docs/Framework.html#ncmethodresulterror")

        # Check user label
        method_result = self.ms05_utils.get_property(test, property_id,
                                                     oid=self.ms05_utils.ROOT_BLOCK_OID,
                                                     role_path=['root'])

        if isinstance(method_result, NcMethodResultError):
            return test.FAIL(f"{error_msg_base}"
                             f"GetProperty error: {str(method_result.errorMessage)}")

        if self.ms05_utils.is_error_status(method_result.status):
            return test.FAIL(f"{error_msg_base}"
                             "GetProperty error: NcMethodResultError MUST be returned on an error",
                             "https://specs.amwa.tv/ms-05-02/branches/"
                             f"{self.apis[MS05_API_KEY]['spec_branch']}"
                             "/docs/Framework.html#ncmethodresulterror")

        label = method_result.value
        if label != new_user_label:
            if label == old_user_label:
                return test.FAIL("Unable to set user label", link)
            else:
                return test.FAIL(f"Unexpected user label: {str(label)}", link)

        # Reset user label
        method_result = self.ms05_utils.set_property(test, property_id, old_user_label,
                                                     oid=self.ms05_utils.ROOT_BLOCK_OID,
                                                     role_path=['root'])

        if isinstance(method_result, NcMethodResultError):
            return test.FAIL(f"{error_msg_base}"
                             f"SetProperty error: {str(method_result.errorMessage)}")

        if self.ms05_utils.is_error_status(method_result.status):
            return test.FAIL(f"{error_msg_base}"
                             "SetProperty error: NcMethodResultError MUST be returned on an error",
                             "https://specs.amwa.tv/ms-05-02/branches/"
                             f"{self.apis[MS05_API_KEY]['spec_branch']}"
                             "/docs/Framework.html#ncmethodresulterror")

        # Check user label
        method_result = self.ms05_utils.get_property(test, property_id,
                                                     oid=self.ms05_utils.ROOT_BLOCK_OID,
                                                     role_path=['root'])
        if isinstance(method_result, NcMethodResultError):
            return test.FAIL(f"{error_msg_base}"
                             f"GetProperty error: {str(method_result.errorMessage)}")

        if self.ms05_utils.is_error_status(method_result.status):
            return test.FAIL(f"{error_msg_base}"
                             "GetProperty error: NcMethodResultError MUST be returned on an error",
                             "https://specs.amwa.tv/ms-05-02/branches/"
                             f"{self.apis[MS05_API_KEY]['spec_branch']}"
                             "/docs/Framework.html#ncmethodresulterror")

        label = method_result.value
        if label != old_user_label:
            if label == new_user_label:
                return test.FAIL("Unable to set user label", link)
            else:
                return test.FAIL(f"Unexpected user label: {str(label)}", link)

        return test.PASS()

    def test_ms05_16(self, test):
        """NcObject: GetSequenceItem method is correct"""
        # Where the functionality of a device uses control classes and datatypes listed in this
        # specification it MUST comply with the model definitions published
        # https://specs.amwa.tv/ms-05-02/releases/v1.0.0/docs/Framework.html#ncobject

        try:
            self._check_device_model(test)
        except NMOSTestException as e:
            # Couldn't validate model so can't perform test
            return test.FAIL(e.args[0].detail, e.args[0].link)

        if self.get_sequence_item_metadata.error:
            return test.FAIL(self.get_sequence_item_metadata.error_msg)

        if not self.get_sequence_item_metadata.checked:
            return test.UNCLEAR("GetSequenceItem not tested.")

        return test.PASS()

    def test_ms05_17(self, test):
        """NcObject: GetSequenceLength method is correct"""
        # Where the functionality of a device uses control classes and datatypes listed in this
        # specification it MUST comply with the model definitions published
        # https://specs.amwa.tv/ms-05-02/releases/v1.0.0/docs/Framework.html#ncobject

        try:
            self._check_device_model(test)
        except NMOSTestException as e:
            # Couldn't validate model so can't perform test
            return test.FAIL(e.args[0].detail, e.args[0].link)

        if self.get_sequence_length_metadata.error:
            return test.FAIL(self.get_sequence_length_metadata.error_msg)

        if not self.get_sequence_length_metadata.checked:
            return test.UNCLEAR("GetSequenceItem not tested.")

        return test.PASS()

    def _check_member_descriptors(self, test, expected_members, method_result, role_path,
                                  query_condition=None, search_condition=None):
        error_msg_base = f"role path={self.ms05_utils.create_role_path_string(role_path)}"

        query_string = f" for query={str(query_condition)}" if query_condition else ""
        search_condition_string = f", search parameters: {str(search_condition)}" if search_condition else ""

        if isinstance(method_result, NcMethodResultError):
            raise NMOSTestException(test.FAIL(f"{error_msg_base}: GetMemberDescriptors error: "
                                              f"{str(method_result.errorMessage)}"))
        if self.ms05_utils.is_error_status(method_result.status):
            raise NMOSTestException(test.FAIL(f"{error_msg_base}: GetMemberDescriptors error: "
                                              "NcMethodResultError MUST be returned on an error"))
        if method_result.value is None:
            raise NMOSTestException(test.FAIL(f"{error_msg_base}"
                                              f": Function returned None{str(query_string)}"))
        if not isinstance(method_result.value, list):
            raise NMOSTestException(test.FAIL(f"{error_msg_base}"
                                              f": Result sequence expected{str(query_string)}"))

        if len(method_result.value) != len(expected_members):
            raise NMOSTestException(
                test.FAIL(f"{error_msg_base}: Expected {str(len(expected_members))} members, "
                          f"but got {str(len(method_result.value))}"
                          f"{str(query_string)}"
                          f"{search_condition_string}"))

        actual_members = {member.oid: member for member in method_result.value}

        for expected_member in expected_members:
            if expected_member.oid not in actual_members.keys():
                raise NMOSTestException(
                    test.FAIL(f"{error_msg_base}: Unexpected search result. "
                              f"{str(expected_member)}"
                              f"{str(query_string)}"
                              f"{search_condition_string}"))

            actual_member = actual_members.get(expected_member.oid)
            if expected_member != actual_member:
                raise NMOSTestException(
                    test.FAIL(f"{error_msg_base}: Unexpected NcBlockMemberDescriptor value: "
                              f"Expected value: {str(expected_member)}, Actual value: {str(actual_member)}"
                              f"{str(query_string)}"
                              f"{search_condition_string}"))

    def _do_get_member_descriptors_test(self, test, block):
        # Recurse through the child blocks
        for child_object in block.child_objects:
            if type(child_object) is NcBlock:
                self._do_get_member_descriptors_test(test, child_object)

        search_conditions = [{"recurse": True}, {"recurse": False}]

        for search_condition in search_conditions:
            expected_members = block.get_member_descriptors(search_condition["recurse"])

            method_result = self.ms05_utils.get_member_descriptors(test, search_condition["recurse"],
                                                                   oid=block.oid, role_path=block.role_path)
            self._check_member_descriptors(test, expected_members, method_result, block.role_path,
                                           search_condition=search_condition)

    def test_ms05_18(self, test):
        """NcBlock: GetMemberDescriptors method is correct"""
        # Where the functionality of a device uses control classes and datatypes listed in this
        # specification it MUST comply with the model definitions published
        # https://specs.amwa.tv/ms-05-02/releases/v1.0.0/docs/Framework.html#ncblock

        device_model = self.ms05_utils.query_device_model(test)

        self._do_get_member_descriptors_test(test, device_model)

        return test.PASS()

    def _do_find_member_by_path_test(self, test, block):
        # Recurse through the child blocks
        for child_object in block.child_objects:
            if type(child_object) is NcBlock:
                self._do_find_member_by_path_test(test, child_object)

        # Get ground truth role paths
        role_paths = block.get_role_paths()

        for path in role_paths:
            # Get ground truth data from local device model object tree
            expected_members = block.find_members_by_path(path)

            method_result = self.ms05_utils.find_members_by_path(test, path,
                                                                 oid=block.oid,
                                                                 role_path=block.role_path)

            self._check_member_descriptors(test, expected_members, method_result, block.role_path,
                                           query_condition=self.ms05_utils.create_role_path_string(path))

    def test_ms05_19(self, test):
        """NcBlock: FindMemberByPath method is correct"""
        # Where the functionality of a device uses control classes and datatypes listed in this
        # specification it MUST comply with the model definitions published
        # https://specs.amwa.tv/ms-05-02/releases/v1.0.0/docs/Framework.html#ncblock

        device_model = self.ms05_utils.query_device_model(test)

        # Recursively check each block in Device Model
        self._do_find_member_by_path_test(test, device_model)

        return test.PASS()

    def _do_find_member_by_role_test(self, test, block):
        # Recurse through the child blocks
        for child_object in block.child_objects:
            if type(child_object) is NcBlock:
                self._do_find_member_by_role_test(test, child_object)

        role_paths = MS05Utils.sampled_list(block.get_role_paths())
        # Generate every combination of case_sensitive, match_whole_string and recurse
        truth_table = MS05Utils.sampled_list(list(product([False, True], repeat=3)))
        search_conditions = []
        for state in truth_table:
            search_conditions += [{"case_sensitive": state[0], "match_whole_string": state[1], "recurse": state[2]}]

        for role_path in role_paths:
            role = role_path[-1]
            # Case sensitive role, case insensitive role, CS role substring and CI role substring
            query_strings = [role, role.upper(), role[-4:], role[-4:].upper()]

            for condition in search_conditions:
                for query_string in query_strings:
                    # Get ground truth result
                    expected_members = \
                        block.find_members_by_role(query_string,
                                                   case_sensitive=condition["case_sensitive"],
                                                   match_whole_string=condition["match_whole_string"],
                                                   recurse=condition["recurse"])
                    method_result = \
                        self.ms05_utils.find_members_by_role(test,
                                                             query_string,
                                                             case_sensitive=condition["case_sensitive"],
                                                             match_whole_string=condition["match_whole_string"],
                                                             recurse=condition["recurse"],
                                                             oid=block.oid,
                                                             role_path=block.role_path)

                    self._check_member_descriptors(test, expected_members, method_result, block.role_path,
                                                   query_condition=query_string, search_condition=condition)

    def test_ms05_20(self, test):
        """NcBlock: FindMembersByRole method is correct"""
        # Where the functionality of a device uses control classes and datatypes listed in this
        # specification it MUST comply with the model definitions published
        # https://specs.amwa.tv/ms-05-02/releases/v1.0.0/docs/Framework.html#ncblock

        device_model = self.ms05_utils.query_device_model(test)

        # Recursively check each block in Device Model
        self._do_find_member_by_role_test(test, device_model)

        return test.PASS()

    def _do_find_members_by_class_id_test(self, test, block):
        # Recurse through the child blocks
        for child_object in block.child_objects:
            if type(child_object) is NcBlock:
                self._do_find_members_by_class_id_test(test, child_object)

        class_ids = [e.value for e in StandardClassIds]

        truth_table = MS05Utils.sampled_list(list(product([False, True], repeat=2)))
        search_conditions = []
        for state in truth_table:
            search_conditions += [{"include_derived": state[0], "recurse": state[1]}]

        for class_id in class_ids:
            for condition in search_conditions:
                # Recursively check each block in Device Model
                expected_members = block.find_members_by_class_id(class_id,
                                                                  condition["include_derived"],
                                                                  condition["recurse"])

                method_result = self.ms05_utils.find_members_by_class_id(test,
                                                                         class_id,
                                                                         condition["include_derived"],
                                                                         condition["recurse"],
                                                                         oid=block.oid,
                                                                         role_path=block.role_path)

                self._check_member_descriptors(test, expected_members, method_result, block.role_path,
                                               query_condition=f"class_id={str(class_id)}", search_condition=condition)

    def test_ms05_21(self, test):
        """NcBlock: FindMembersByClassId method is correct"""
        # Where the functionality of a device uses control classes and datatypes listed in this
        # specification it MUST comply with the model definitions published
        # https://specs.amwa.tv/ms-05-02/releases/v1.0.0/docs/Framework.html#ncblock

        device_model = self.ms05_utils.query_device_model(test)

        self._do_find_members_by_class_id_test(test, device_model)

        return test.PASS()

    def test_ms05_22(self, test):
        """Constraints: validate runtime constraints"""

        self._check_device_model(test)

        if self.runtime_constraints_metadata.error:
            return test.FAIL(self.runtime_constraints_metadata.error_msg,
                             "https://specs.amwa.tv/ms-05-02/branches/"
                             f"{self.apis[MS05_API_KEY]['spec_branch']}"
                             "/docs/Constraints.html")

        if not self.runtime_constraints_metadata.checked:
            return test.UNCLEAR("No runtime constraints found.")

        return test.PASS()

    def test_ms05_23(self, test):
        """Constraints: validate property constraints"""

        self._check_device_model(test)

        if self.property_constraints_metadata.error:
            return test.FAIL(self.property_constraints_metadata.error_msg,
                             "https://specs.amwa.tv/ms-05-02/branches/"
                             f"{self.apis[MS05_API_KEY]['spec_branch']}"
                             "/docs/Constraints.html")

        if not self.property_constraints_metadata.checked:
            return test.UNCLEAR("No property constraints found.")

        return test.PASS()

    def _do_validate_datatype_constraints_test(self, test, datatype_descriptor, test_metadata, context=""):
        if datatype_descriptor.constraints:
            test_metadata.checked = True
            type_str = ""
            if not isinstance(datatype_descriptor, NcDatatypeDescriptor):
                type_str = f", {datatype_descriptor.constraints.level} type={datatype_descriptor.typeName}"
            self._check_constraint(test,
                                   datatype_descriptor.constraints,
                                   datatype_descriptor,
                                   test_metadata,
                                   role_path=None,
                                   context=f"{context}"
                                   f"{datatype_descriptor.constraints.level} name={datatype_descriptor.name}"
                                   f"{type_str}")
        if isinstance(datatype_descriptor, NcDatatypeDescriptorStruct):
            constrained_field_descriptors = [f for f in datatype_descriptor.fields if f.constraints]
            if datatype_descriptor.constraints and bool(constrained_field_descriptors):
                # You can't specify constraints
                test_metadata.error = True
                test_metadata.error_msg += f"datatype name={datatype_descriptor.name}: " \
                    "struct datatypes cannot have constraints defined at both the struct and field level; "
                return
            for field_descriptor in constrained_field_descriptors:
                self._do_validate_datatype_constraints_test(test,
                                                            field_descriptor,
                                                            test_metadata,
                                                            f"struct datatype name={datatype_descriptor.name}, ")

    def test_ms05_24(self, test):
        """Constraints: validate datatype constraints"""

        class_manager = self.ms05_utils.get_class_manager(test)

        test_metadata = MS0501Test.TestMetadata()

        for _, datatype_descriptor in class_manager.datatype_descriptors.items():
            self._do_validate_datatype_constraints_test(test, datatype_descriptor, test_metadata)

        if test_metadata.error:
            return test.FAIL(test_metadata.error_msg,
                             "https://specs.amwa.tv/ms-05-02/branches/"
                             f"{self.apis[MS05_API_KEY]['spec_branch']}"
                             "/docs/Constraints.html")

        if not test_metadata.checked:
            return test.UNCLEAR("No datatype constraints found.")

        return test.PASS()

    def test_ms05_25(self, test):
        """Constraints: validate parameter constraints"""

        self._check_device_model(test)

        if self.parameter_constraints_metadata.error:
            return test.FAIL(self.parameter_constraints_metadata.error_msg,
                             "https://specs.amwa.tv/ms-05-02/branches/"
                             f"{self.apis[MS05_API_KEY]['spec_branch']}"
                             "/docs/Constraints.html")

        if not self.parameter_constraints_metadata.checked:
            return test.UNCLEAR("No property constraints found.")

        return test.PASS()

    def test_ms05_26(self, test):
        """Constraints: check constraints hierarchy"""

        # When using multiple levels of constraints implementations MUST fully override the previous level
        # and this MUST not result in widening the constraints defined in previous levels
        # https://specs.amwa.tv/ms-05-02/branches/v1.0.x/docs/Constraints.html

        self._check_device_model(test)

        if self.device_model_metadata.error:
            return test.FAIL(self.device_model_metadata.error_msg)

        if self.constraint_hierarchy_metadata.error:
            return test.FAIL(self.constraint_hierarchy_metadata.error_msg,
                             "https://specs.amwa.tv/ms-05-02/branches/"
                             f"{self.apis[MS05_API_KEY]['spec_branch']}"
                             "/docs/Constraints.html")

        if not self.constraint_hierarchy_metadata.checked:
            return test.UNCLEAR("No constraints hierarchy found.")

        return test.PASS()

    def test_ms05_27(self, test):
        """MS-05-02 Error: Node handles read only error"""
        # Devices MUST use the exact status code from NcMethodStatus when errors are encountered
        # for the following scenarios...
        # https://specs.amwa.tv/ms-05-02/releases/v1.0.0/docs/Framework.html#ncmethodresult

        error_msg_base = "role path=/root: " \
                         f"property name={NcObjectProperties.OID.name}: " \
                         f"property id={NcObjectProperties.OID.value}: "

        method_result = self.ms05_utils.set_property(test, NcObjectProperties.ROLE.value, "ROLE IS READ ONLY",
                                                     oid=self.ms05_utils.ROOT_BLOCK_OID, role_path=["root"])

        if not isinstance(method_result, NcMethodResultError):
            return test.FAIL(f"{error_msg_base}"
                             "Read only properties error expected.",
                             "https://specs.amwa.tv/ms-05-02/branches/"
                             f"{self.apis[MS05_API_KEY]['spec_branch']}"
                             "/docs/Framework.html#ncmethodresult")

        if method_result.status != NcMethodStatus.Readonly.value:
            return test.WARNING(f"{error_msg_base}"
                                f"Unexpected status. Expected: {NcMethodStatus.Readonly.name}"
                                f" ({str(NcMethodStatus.Readonly.value)})"
                                f", actual: {method_result.status.name}"
                                f" ({str(method_result.status.value)})",
                                "https://specs.amwa.tv/ms-05-02/branches/"
                                f"{self.apis[MS05_API_KEY]['spec_branch']}"
                                "/docs/Framework.html#ncmethodresult")

        return test.PASS()

    def test_ms05_28(self, test):
        """MS-05-02 Error: Node handles GetSequence index out of bounds error"""
        # Devices MUST use the exact status code from NcMethodStatus when errors are encountered
        # for the following scenarios...
        # https://specs.amwa.tv/ms-05-02/releases/v1.0.0/docs/Framework.html#ncmethodresult

        error_msg_base = "role path=/root: " \
                         f"property name={NcObjectProperties.OID.name}: " \
                         f"property id={NcObjectProperties.OID.value}: "

        method_result = self.ms05_utils.get_sequence_length(test,
                                                            NcBlockProperties.MEMBERS.value,
                                                            oid=self.ms05_utils.ROOT_BLOCK_OID,
                                                            role_path=["root"])
        if isinstance(method_result, NcMethodResultError):
            return test.FAIL(f"{error_msg_base}Error getting sequence length: {str(method_result.errorMessage)} ")
        if self.ms05_utils.is_error_status(method_result.status):
            return test.FAIL(f"{error_msg_base}GetSequenceLength error: "
                             "NcMethodResultError MUST be returned on an error")

        out_of_bounds_index = method_result.value + 10

        method_result = self.ms05_utils.get_sequence_item(test,
                                                          NcBlockProperties.MEMBERS.value,
                                                          out_of_bounds_index,
                                                          oid=self.ms05_utils.ROOT_BLOCK_OID,
                                                          role_path=["root"])

        if not isinstance(method_result, NcMethodResultError):
            return test.FAIL(f"{error_msg_base}"
                             "Sequence out of bounds error expected for GetSequenceItem: "
                             f"index={out_of_bounds_index}: ",
                             "https://specs.amwa.tv/ms-05-02/branches/"
                             f"{self.apis[MS05_API_KEY]['spec_branch']}"
                             "/docs/Framework.html#ncmethodresult")

        if method_result.status != NcMethodStatus.IndexOutOfBounds:
            return test.WARNING(f"{error_msg_base}"
                                "Unexpected status for GetSequenceItem "
                                f"(index={out_of_bounds_index}) out of bounds error: "
                                f"Expected: {NcMethodStatus.IndexOutOfBounds.name}"
                                f" ({str(NcMethodStatus.IndexOutOfBounds.value)})"
                                f", actual: {method_result.status.name}"
                                f" ({str(method_result.status.value)})",
                                "https://specs.amwa.tv/ms-05-02/branches/"
                                f"{self.apis[MS05_API_KEY]['spec_branch']}"
                                "/docs/Framework.html#ncmethodresult")

        return test.PASS()

    # Invasive tests - run when MS05_INVASIVE_TESTING is True.
    # When MS05_INTERACTIVE_TESTING is True the Testing Facade must be also run

    def _get_testing_facade_selection(self, question, possible_answers, test_type, test_method_name):
        """Get a list of selected answer IDs, given a question and list of possible answers"""
        # remove resources from the possible_answers before invoking the testing facade
        filtered = deepcopy(possible_answers)
        for p in filtered:
            p.pop("resource", None)
        return self.testing_facade_utils.invoke_testing_facade(question, filtered,
                                                               test_type="multi_choice",
                                                               test_method_name=test_method_name)["answer_response"]

    def _invasive_check_constrained_parameter(self, test, constrained_property, value, expect_error=True):
        error_msg_base = f"role path={self.ms05_utils.create_role_path_string(constrained_property.role_path)}, " \
                         f"property id={constrained_property.descriptor.id}, " \
                         f"property name={constrained_property.descriptor.name}: "

        def _do_check(check_function):
            method_result = check_function()
            # Expecting a parameter constraint violation
            if not (expect_error ^ isinstance(method_result, NcMethodResultError)):
                if expect_error:  # only set checked if constraints have been violated/tested
                    self.check_property_metadata.checked = True
                elif self.ms05_utils.is_error_status(method_result.status):
                    self.check_property_metadata.error = True
                    self.check_property_metadata.error_msg += \
                        f"{error_msg_base}Method error: NcMethodResultError MUST be returned on an error; "
            else:
                self.check_property_metadata.error = True
                if expect_error:
                    self.check_property_metadata.error_msg += \
                        f"{error_msg_base}Constraints not enforced error, " \
                        f"Value: {value}, " \
                        f"Constraints: {constrained_property.constraints}; "
                else:
                    self.check_property_metadata.error_msg += \
                        f"{error_msg_base}Constraints incorrectly applied, " \
                        f"Value: {value}, " \
                        f"Constraints: {constrained_property.constraints}; "

        def _do_set_sequence():
            method_result = self.ms05_utils.get_sequence_length(test,
                                                                constrained_property.descriptor.id,
                                                                oid=constrained_property.oid,
                                                                role_path=constrained_property.role_path)
            if isinstance(method_result, NcMethodResultError):
                # We don't want this error to be confused with a constraints violation error
                raise NMOSTestException(test.FAIL(f"{error_msg_base}GetSequenceLength error: "
                                                  f"{str(method_result.errorMessage)}"))
            if self.ms05_utils.is_error_status(method_result.status):
                # We don't want this error to be confused with a constraints violation error
                raise NMOSTestException(test.FAIL(f"{error_msg_base}GetSequenceLength error: "
                                                  "NcMethodResultError MUST be returned on an error."))
            return self.ms05_utils.set_sequence_item(test,
                                                     constrained_property.descriptor.id,
                                                     method_result.value - 1,
                                                     value,
                                                     oid=constrained_property.oid,
                                                     role_path=constrained_property.role_path)

        if constrained_property.descriptor.isSequence:
            _do_check(lambda: self.ms05_utils.add_sequence_item(test,
                                                                constrained_property.descriptor.id,
                                                                value,
                                                                oid=constrained_property.oid,
                                                                role_path=constrained_property.role_path))
            _do_check(_do_set_sequence)
        else:
            _do_check(lambda: self.ms05_utils.set_property(test,
                                                           constrained_property.descriptor.id,
                                                           value,
                                                           oid=constrained_property.oid,
                                                           role_path=constrained_property.role_path))

    def _generate_number_parameters(self, constraints_, violate_constraints=False):
        # Generate list of number value based on constraints if present.
        # violate_constraints=True will generate an "invalid" value based on constraints
        parameters = []
        constraints = deepcopy(constraints_)
        # If constraints incorrect type fail gracefully
        if not isinstance(constraints, (NcParameterConstraintsNumber, NcPropertyConstraintsNumber)):
            constraints = None

        minimum = (constraints.minimum or 0 if constraints else 0)
        maximum = (constraints.maximum or sys.maxsize if constraints else sys.maxsize)
        step = (constraints.step or 1 if constraints else 1)

        valid_value = floor((((maximum - minimum) / 2) + minimum) / step) * step + minimum

        # Valid value
        if not violate_constraints:
            parameters.append(valid_value)

        # Invalid values
        if violate_constraints and constraints and constraints.minimum is not None:
            parameters.append(minimum - step)

        if violate_constraints and constraints and constraints.maximum is not None:
            parameters.append(maximum + step)

        if violate_constraints and constraints and constraints.step is not None and step > 1:
            parameters.append(valid_value + step / 2)

        return parameters

    def _generate_string_parameters(self, constraints_, violate_constraints):
        # Generate list of string value based on constraints if present.
        # violate_constraints=True will generate an "invalid" string based on constraints
        parameters = []
        constraints = deepcopy(constraints_)
        # If constraints incorrect type fail gracefully
        if not isinstance(constraints, (NcParameterConstraintsString, NcPropertyConstraintsString)):
            constraints = None

        # Valid value
        if not violate_constraints and constraints and constraints.pattern:
            # Check legal case
            x = Xeger(limit=(constraints.maxCharacters or 0) - len(constraints.pattern)
                      if (constraints.maxCharacters or 0) > len(constraints.pattern) else 1)
            parameters.append(x.xeger(constraints.pattern))
        elif not violate_constraints:
            parameters.append("new_value")

        # Invalid values
        if violate_constraints and constraints and constraints.pattern:
            # Possible negative example strings
            # Ideally we would compute a negative string based on the regex.
            # In the meantime, some strings that might possibly violate the regex
            negative_examples = ["!$%^&*()+_:;/", "*********", "000000000", "AAAAAAAA"]

            for negative_example in negative_examples:
                # Verify this string violates constraint
                if not re.search(constraints.pattern, negative_example):
                    parameters.append(negative_example)

        if violate_constraints and constraints and constraints.maxCharacters:
            if constraints.pattern:
                x = Xeger(limit=constraints.maxCharacters * 2)
                value = x.xeger(constraints.pattern)
            else:
                value = "*" * constraints.maxCharacters * 2

            # Verfiy this string violates constraint
            if len(value) > constraints.maxCharacters:
                parameters.append(value)

        return parameters

    def _invasive_check_parameter_constraints(self, test, constrained_property):
        # Check property constraints with parameters that both don't and do violate constraints
        for violate_constraints in [False, True]:
            parameters = []
            if isinstance(constrained_property.constraints,
                          (NcParameterConstraintsNumber, NcPropertyConstraintsNumber)):
                parameters = self._generate_number_parameters(constrained_property.constraints,
                                                              violate_constraints=violate_constraints)
            if isinstance(constrained_property.constraints,
                          (NcParameterConstraintsString, NcPropertyConstraintsString)):
                parameters = self._generate_string_parameters(constrained_property.constraints,
                                                              violate_constraints=violate_constraints)
            for parameter in parameters:
                self._invasive_check_constrained_parameter(test, constrained_property, parameter,
                                                           expect_error=violate_constraints)

    def _check_sequence_datatype_type(self, test, property_under_test, original_value):
        # Check that a sequence property can be set
        self.check_property_metadata.checked = True

        modified_value = list(reversed(original_value))

        method_result = self.ms05_utils.set_property(test,
                                                     property_under_test.descriptor.id,
                                                     modified_value,
                                                     oid=property_under_test.oid,
                                                     role_path=property_under_test.role_path)

        error_msg_base = f"role path={self.ms05_utils.create_role_path_string(property_under_test.role_path)}, " \
                         f"property id={property_under_test.descriptor.id}, " \
                         f"property name={property_under_test.descriptor.name}: "
        if isinstance(method_result, NcMethodResultError):
            self.check_property_metadata.error = True
            self.check_property_metadata.error_msg += \
                f"{error_msg_base}SetProperty error: {str(method_result.errorMessage)}; "
        else:
            self.check_property_metadata.checked = True
        if not isinstance(method_result, NcMethodResultError) and \
                self.ms05_utils.is_error_status(method_result.status):
            raise NMOSTestException(test.FAIL(f"{error_msg_base}SetProperty error: "
                                              "NcMethodResultError MUST be returned on an error."))

    def _do_check_property_test(self, test, question, get_constraints=False, get_sequences=False, datatype_type=None):
        # Test properties of the Device Model
        # get_constraints - select properties that have constraints
        # get_sequences - select properties that are sequences
        # datatype_type - only select properties that are this datatype type (None selects all)
        try:
            device_model = self.ms05_utils.query_device_model(test)

            constrained_properties = self.ms05_utils.get_properties(test, device_model, get_constraints, get_sequences)

            # Filter constrained properties according to datatype_type
            constrained_properties = [p for p in constrained_properties
                                      if datatype_type is None or p.datatype_type == datatype_type]

            possible_properties = [{"answer_id": f"answer_{str(i)}",
                                    "display_answer": p.name,
                                    "resource": p} for i, p in enumerate(constrained_properties)]

            if len(possible_properties) == 0:
                return test.UNCLEAR("No testable properties in Device Model.")

            if MS05_INTERACTIVE_TESTING:
                test_method_name = inspect.currentframe().f_back.f_code.co_name

                selected_ids = \
                    self._get_testing_facade_selection(question, possible_properties,
                                                       test_type="multi_choice", test_method_name=test_method_name)

                selected_properties = [p["resource"] for p in possible_properties if p["answer_id"] in selected_ids]

                if len(selected_properties) == 0:
                    return test.UNCLEAR("No properties selected for testing.")
            else:
                # If non-interactive then test all methods
                selected_properties = [p["resource"] for p in possible_properties]

            self.check_property_metadata = MS0501Test.TestMetadata()

            for constrained_property in selected_properties:
                error_msg_base = \
                    f"role path={self.ms05_utils.create_role_path_string(constrained_property.role_path)}, " \
                    f"property id={constrained_property.descriptor.id}, " \
                    f"property name={constrained_property.descriptor.name}: "

                # Cache original property value
                method_result = self.ms05_utils.get_property(test, constrained_property.descriptor.id,
                                                             oid=constrained_property.oid,
                                                             role_path=constrained_property.role_path)
                if isinstance(method_result, NcMethodResultError):
                    return test.FAIL(f"{error_msg_base}GetProperty error: {str(method_result.errorMessage)}: "
                                     f"constraints={str(constrained_property.constraints)}")
                if self.ms05_utils.is_error_status(method_result.status):
                    return test.FAIL(f"{error_msg_base}GetProperty error: "
                                     "NcMethodResultError MUST be returned on an error.")

                original_value = method_result.value
                if get_constraints:
                    self._invasive_check_parameter_constraints(test, constrained_property)
                elif datatype_type is not None and get_sequences:
                    # Enums and Struct are validated against their type definitions
                    self._check_sequence_datatype_type(test, constrained_property, original_value)

                # Reset to original value
                method_result = self.ms05_utils.set_property(test,
                                                             constrained_property.descriptor.id,
                                                             original_value,
                                                             oid=constrained_property.oid,
                                                             role_path=constrained_property.role_path)
                if isinstance(method_result, NcMethodResultError):
                    return test.FAIL(f"{error_msg_base}SetProperty error: {str(method_result.errorMessage)}: "
                                     f"value={str(original_value)}, "
                                     f"constraints={str(constrained_property.constraints)}")
                if self.ms05_utils.is_error_status(method_result.status):
                    return test.FAIL(f"{error_msg_base}SetProperty error: "
                                     "NcMethodResultError MUST be returned on an error.")

            if self.check_property_metadata.error:
                link = "https://specs.amwa.tv/ms-05-02/branches/" \
                    f"{self.apis[MS05_API_KEY]['spec_branch']}" \
                    "/docs/Constraints.html" if get_constraints else \
                    "https://specs.amwa.tv/ms-05-02/branches/" \
                    f"{self.apis[MS05_API_KEY]['spec_branch']}" \
                    "/docs/NcObject.html#generic-getter-and-setter"
                return test.FAIL(self.check_property_metadata.error_msg, link)

            if self.check_property_metadata.checked:
                return test.PASS()

            return test.UNCLEAR("No properties of this type checked")
        except TestingFacadeException as e:
            return test.UNCLEAR(f"Testing Facade error: {e.args[0]}")

    def test_ms05_29(self, test):
        """Constraints on writable properties are enforced"""
        if not MS05_INVASIVE_TESTING:
            return test.DISABLED("This test cannot be performed when MS05_INVASIVE_TESTING is False ")

        question = """\
                    From this list of properties with parameter constraints\
                    carefully select those that can be safely altered by this test.

                    Note that this test will attempt to restore the original state of the Device Model.

                    Once you have made you selection please press the 'Submit' button.
                    """
        return self._do_check_property_test(test, question, get_constraints=True, get_sequences=False)

    def test_ms05_30(self, test):
        """Constraints on writable sequences are enforced"""
        if not MS05_INVASIVE_TESTING:
            return test.DISABLED("This test cannot be performed when MS05_INVASIVE_TESTING is False ")

        question = """\
                   From this list of sequences with parameter constraints\
                   carefully select those that can be safely altered by this test.

                   Note that this test will attempt to restore the original state of the Device Model.

                   Once you have made you selection please press the 'Submit' button.
                   """

        return self._do_check_property_test(test, question, get_constraints=True, get_sequences=True)

    def test_ms05_31(self, test):
        """Check writable enumeration sequences"""
        if not MS05_INVASIVE_TESTING:
            return test.DISABLED("This test cannot be performed when MS05_INVASIVE_TESTING is False ")

        # This test will use Get and Set to test reading/writing entire sequences, rather than per item tests
        question = """\
                   From this list of enumeration sequences\
                   carefully select those that can be safely altered by this test.

                   Note that this test will attempt to restore the original state of the Device Model.

                   Once you have made you selection please press the 'Submit' button.
                   """

        return self._do_check_property_test(test, question, get_constraints=False, get_sequences=True,
                                            datatype_type=NcDatatypeType.Enum)

    def test_ms05_32(self, test):
        """Check writable struct sequences"""
        if not MS05_INVASIVE_TESTING:
            return test.DISABLED("This test cannot be performed when MS05_INVASIVE_TESTING is False ")

        # This test will use Get and Set to test reading/writing entire sequences, rather than per item tests
        question = """\
                   From this list of struct sequences\
                   carefully select those that can be safely altered by this test.

                   Note that this test will attempt to restore the original state of the Device Model.

                   Once you have made you selection please press the 'Submit' button.
                   """

        return self._do_check_property_test(test, question, get_constraints=False, get_sequences=True,
                                            datatype_type=NcDatatypeType.Struct)

    def _do_check_readonly_properties(self, test, question, get_sequences=False):
        # Check that properties that have a read only property set to True
        # cannot be written
        # https://specs.amwa.tv/ms-05-02/branches/v1.0.x/docs/NcObject.html#generic-getter-and-setter
        try:
            device_model = self.ms05_utils.query_device_model(test)

            readonly_properties = self.ms05_utils.get_properties(test, device_model, get_constraints=False,
                                                                 get_sequences=get_sequences, get_readonly=True)

            possible_properties = [{"answer_id": f"answer_{str(i)}",
                                    "display_answer": p.name,
                                    "resource": p} for i, p in enumerate(readonly_properties)]

            if len(possible_properties) == 0:
                return test.UNCLEAR("No testable properties in Device Model.")

            if MS05_INTERACTIVE_TESTING:
                test_method_name = inspect.currentframe().f_back.f_code.co_name

                selected_ids = \
                    self._get_testing_facade_selection(question, possible_properties,
                                                       test_type="multi_choice", test_method_name=test_method_name)

                selected_properties = [p["resource"] for p in possible_properties if p["answer_id"] in selected_ids]

                if len(selected_properties) == 0:
                    return test.UNCLEAR("No properties selected for testing.")
            else:
                # If non-interactive then test all methods
                selected_properties = [p["resource"] for p in possible_properties]

            readonly_checked = False

            for readonly_property in selected_properties:
                error_msg_base = f"role path={self.ms05_utils.create_role_path_string(readonly_property.role_path)}, " \
                                 f"property id={readonly_property.descriptor.id}, " \
                                 f"property name={readonly_property.descriptor.name}: "

                # Cache original property value
                method_result = self.ms05_utils.get_property(test,
                                                             readonly_property.descriptor.id,
                                                             oid=readonly_property.oid,
                                                             role_path=readonly_property.role_path)
                if isinstance(method_result, NcMethodResultError):
                    return test.FAIL(f"{error_msg_base}GetProperty error:{str(method_result.errorMessage)}")
                if self.ms05_utils.is_error_status(method_result.status):
                    return test.FAIL(f"{error_msg_base}GetProperty error: "
                                     "NcMethodResultError MUST be returned on an error.")
                original_value = method_result.value
                # Try setting this value
                method_result = self.ms05_utils.set_property(test,
                                                             readonly_property.descriptor.id,
                                                             original_value,
                                                             oid=readonly_property.oid,
                                                             role_path=readonly_property.role_path)
                if not isinstance(method_result, NcMethodResultError):
                    # if it gets this far it's failed
                    # https://specs.amwa.tv/ms-05-02/branches/v1.0.x/docs/NcObject.html#generic-getter-and-setter
                    return test.FAIL(f"{error_msg_base}SetProperty error: Read only property is writable.",
                                     "https://specs.amwa.tv/ms-05-02/branches/"
                                     f"{self.apis[MS05_API_KEY]['spec_branch']}"
                                     "/docs/NcObject.html#generic-getter-and-setter")
                else:
                    readonly_checked = True

            if not readonly_checked:
                return test.UNCLEAR("No read only properties found")
        except TestingFacadeException as e:
            return test.UNCLEAR(f"Testing Facade error: {e.args[0]}")

        return test.PASS()

    def test_ms05_33(self, test):
        """Check read only properties are not writable"""
        if not MS05_INVASIVE_TESTING:
            return test.DISABLED("This test cannot be performed when MS05_INVASIVE_TESTING is False ")

        question = """\
                   From this list of read only properties\
                   carefully select those that can be safely altered by this test.

                   Note that this test will attempt to restore the original state of the Device Model.

                   Once you have made you selection please press the 'Submit' button.
                   """

        return self._do_check_readonly_properties(test, question, get_sequences=False)

    def test_ms05_34(self, test):
        """Check read only sequences are not writable"""
        if not MS05_INVASIVE_TESTING:
            return test.DISABLED("This test cannot be performed when MS05_INVASIVE_TESTING is False ")

        question = """\
                   From this list of read only sequences\
                   carefully select those that can be safely altered by this test.

                   Note that this test will attempt to restore the original state of the Device Model.

                   Once you have made you selection please press the 'Submit' button.
                   """

        return self._do_check_readonly_properties(test, question, get_sequences=True)

    def _resolve_is_sequence(self, test, datatype):
        # Check datatype parents in case it's been typedef'd as a sequence
        if datatype is None:
            return False

        class_manager = self.ms05_utils.get_class_manager(test)

        datatype_descriptor = class_manager.datatype_descriptors[datatype]

        if isinstance(datatype_descriptor, NcDatatypeDescriptorTypeDef):
            return datatype_descriptor.isSequence

        if isinstance(datatype_descriptor, NcDatatypeDescriptorStruct) and datatype_descriptor.parentType:
            return self._resolve_is_sequence(test, datatype_descriptor.parentType)

        return False

    def _make_violate_constraints_mask(self, parameters, violate_constraints):
        # If we're violating constraints then we want to violate each constrained parameter individually
        # so we test every combination of violation in isolation - rather than violating all constraints all at once.
        # This returns a list of masks. Each mask is a boolean list that corresponds exactly to the parameters list
        # For each parameter, the mask indicates True (violate constraints) or False (don't violate constraints)
        # output constraints_masks list of the form e.g. [[False, True, False, False],[False, False, True, False]]
        has_constraints = [p.constraints is not None for p in parameters]

        constraints_masks = []
        if violate_constraints:
            for index, has_constraint in enumerate(has_constraints):
                if has_constraint:
                    constraint_mask = [False] * len(has_constraints)
                    constraint_mask[index] = True
                    constraints_masks.append(constraint_mask)

        if len(constraints_masks) == 0:  # no constraints
            # null, violate_constraints=False case
            constraint_mask = [False] * len(has_constraints)
            constraints_masks.append(constraint_mask)
        return constraints_masks

    def _values_dict_to_parameters_list(self, values_, input_params=[{}]):
        # Convert a values dict into list of method parameters
        # values dict of the form:
        # e.g. {foo: [1,2,3], bar: [A,B]}
        # output of the form:
        # e.g. [[{foo:1,bar:A}], [{foo:1,bar:B]}],
        #       [{foo:2,bar:A}], [{foo:2,bar:B]}],
        #       [{foo:3,bar:A}], [{foo:3,bar:B]}]]
        values = copy(values_)
        if not bool(values):  # all values have been popped
            return input_params

        item = values.popitem()
        output_params = []

        for value in item[1]:  # item[1] is values list e.g. [1,2,3]
            params = deepcopy(input_params)
            for param in params:
                param[item[0]] = value  # item[0] is value key e.g. 'foo'
            output_params += params

        return self._values_dict_to_parameters_list(values, output_params)

    def _create_parameters_list(self, test, parameters, violate_constraints=False):
        # Create a list of parameters dicts. If violate_constraints=True then in each parameters dict
        # can contain parameters that violate their constraints. In this case there will be only one violating
        # pararmeter in each parameters dict to exercise each constraints violation case individually
        constraints_masks = self._make_violate_constraints_mask(parameters, violate_constraints)
        parameters_list = []

        for constraints_mask in constraints_masks:
            values = {}

            for parameter_descriptor, violate_constraints in zip(parameters, constraints_mask):
                parameter = []

                # resolve the datatype to either a struct, enum, primative or None
                datatype = self.ms05_utils.resolve_datatype(test, parameter_descriptor.typeName)

                if datatype is None:
                    parameter = [42]  # None denotes an 'any' type so set to an arbitrary type/value
                else:
                    class_manager = self.ms05_utils.get_class_manager(test)

                    datatype_descriptor = class_manager.datatype_descriptors[datatype]

                    if isinstance(datatype_descriptor, NcDatatypeDescriptorEnum):
                        parameter.append(datatype_descriptor.items[0].value)
                    elif isinstance(datatype_descriptor, NcDatatypeDescriptorPrimitive):
                        if datatype == "NcString":
                            parameter += self._generate_string_parameters(parameter_descriptor.constraints,
                                                                          violate_constraints=violate_constraints)
                        elif datatype == "NcBoolean":
                            parameter.append(False)
                        else:
                            parameter += self._generate_number_parameters(parameter_descriptor.constraints,
                                                                          violate_constraints=violate_constraints)
                    elif isinstance(datatype_descriptor, NcDatatypeDescriptorStruct):
                        parameter += self._create_parameters_list(test, datatype_descriptor.fields,
                                                                  violate_constraints=violate_constraints)

                if parameter_descriptor.isSequence:
                    parameter = [parameter]

                # Note that only NcDatatypeDescriptorTypeDef has an isSequence property
                values[parameter_descriptor.name] = [parameter] \
                    if self._resolve_is_sequence(test, parameter_descriptor.typeName) else parameter
            parameters_list += self._values_dict_to_parameters_list(values)
        return parameters_list

    def _do_check_methods_test(self, test, question, get_constraints):
        """Test methods of non-standard objects within the Device Model"""
        device_model = self.ms05_utils.query_device_model(test)

        methods = self.ms05_utils.get_methods(test, device_model, get_constraints)

        possible_methods = [{"answer_id": f"answer_{str(i)}",
                             "display_answer": p.name,
                             "resource": p} for i, p in enumerate(methods)]

        if len(possible_methods) == 0:
            return test.UNCLEAR("No non standard methods in Device Model.")

        if MS05_INTERACTIVE_TESTING:
            try:
                test_method_name = inspect.currentframe().f_back.f_code.co_name

                selected_ids = \
                    self._get_testing_facade_selection(question, possible_methods,
                                                       test_type="multi_choice", test_method_name=test_method_name)

                selected_methods = [p["resource"] for p in possible_methods if p["answer_id"] in selected_ids]

                if len(selected_methods) == 0:
                    return test.UNCLEAR("No methods selected for testing.")
            except TestingFacadeException as e:
                return test.UNCLEAR(f"Testing Facade error: {e.args[0]}")
        else:
            # If non-interactive then test all methods
            selected_methods = [p["resource"] for p in possible_methods]

        self.invoke_methods_metadata.error = False
        self.invoke_methods_metadata.error_msg = ""

        for method in selected_methods:
            self.invoke_methods_metadata.checked = True

            parameters_list = self._create_parameters_list(test, method.descriptor.parameters)
            error_msg_base = f"role path={self.ms05_utils.create_role_path_string(method.role_path)}, " \
                             f"method id={method.descriptor.id}, method name={method.name}"
            method_error = False
            for parameters in parameters_list:
                try:
                    method_result = self.ms05_utils.invoke_method(test, method.descriptor.id, parameters,
                                                                  oid=method.oid, role_path=method.role_path)

                    if isinstance(method_result, NcMethodResultError):
                        method_error = True
                    # Check for deprecated status codes for deprecated methods
                    if method.descriptor.isDeprecated and method_result.status != 299:
                        self.invoke_methods_metadata.error = True
                        self.invoke_methods_metadata.error_msg += \
                            f"{error_msg_base}, arguments={parameters}: " \
                            f"Deprecated method returned incorrect status code: {method_result.status}; "
                        continue
                    if self.ms05_utils.is_error_status(method_result.status) and \
                            not isinstance(method_result, NcMethodResultError):
                        self.invoke_methods_metadata.error = True
                        self.invoke_methods_metadata.error_msg += \
                            f"{error_msg_base}, arguments={parameters}: " \
                            "NcMethodResultError MUST be returned on an error; "
                        continue
                except NMOSTestException as e:
                    self.invoke_methods_metadata.error = True
                    self.invoke_methods_metadata.error_msg += \
                        f"{error_msg_base}: Error invoking method: {e.args[0].detail}; "

            # Only do negative checking of constrained parameters if positive case was successful
            if get_constraints and not method_error:
                invalid_parameters_list = self._create_parameters_list(test, method.descriptor.parameters,
                                                                       violate_constraints=True)
                for invalid_parameters in invalid_parameters_list:
                    try:
                        method_result = self.ms05_utils.invoke_method(test, method.descriptor.id, invalid_parameters,
                                                                      oid=method.oid, role_path=method.role_path)
                        if not isinstance(method_result, NcMethodResultError):
                            self.invoke_methods_metadata.error = True
                            self.invoke_methods_metadata.error_msg += \
                                f"{error_msg_base}, arguments={invalid_parameters}: Constraints not enforced error; "
                    except NMOSTestException as e:
                        self.invoke_methods_metadata.error = True
                        self.invoke_methods_metadata.error_msg += \
                            f"{error_msg_base}: Error invoking method {method.name} : {e.args[0].detail}; "

        if self.invoke_methods_metadata.error:
            return test.FAIL(self.invoke_methods_metadata.error_msg)

        if self.invoke_methods_metadata.checked:
            return test.PASS()

        return test.UNCLEAR("No methods checked.")

    def test_ms05_35(self, test):
        """Check discovered methods with unconstrained parameters"""
        if not MS05_INVASIVE_TESTING:
            return test.DISABLED("This test cannot be performed when MS05_INVASIVE_TESTING is False ")

        question = """\
                   From this list of methods\
                   carefully select those that can be safely invoked by this test.

                   Note that this test will NOT attempt to restore the original state of the Device Model.

                   Once you have made you selection please press the 'Submit' button.
                   """

        return self._do_check_methods_test(test, question, get_constraints=False)

    def test_ms05_36(self, test):
        """Constraints on method parameters are enforced"""
        if not MS05_INVASIVE_TESTING:
            return test.DISABLED("This test cannot be performed when MS05_INVASIVE_TESTING is False ")

        question = """\
                   From this list of methods\
                   carefully select those that can be safely invoked by this test.

                   Note that this test will NOT attempt to restore the original state of the Device Model.

                   Once you have made you selection please press the 'Submit' button.
                   """

        return self._do_check_methods_test(test, question, get_constraints=True)

    def _check_add_sequence_item(self, test, property_id, property_name, sequence_length, oid, role_path):
        error_msg_base = f"role path={self.ms05_utils.create_role_path_string(role_path)}, " \
                         f"property id={property_id}, " \
                         f"property name={property_name}: "
        # Add a value to the end of the sequence
        # Get the first item from this sequence (then we know it is of the correct type)
        method_result = self.ms05_utils.get_sequence_item(test, property_id, index=0,
                                                          oid=oid, role_path=role_path)

        if not isinstance(method_result, NcMethodResultError):
            new_item_value = method_result.value
            # The new item will be added to end of the sequence
            method_result = self.ms05_utils.get_sequence_length(test, property_id,
                                                                oid=oid, role_path=role_path)
        if not isinstance(method_result, NcMethodResultError):
            new_item_index = method_result.value
            method_result = self.ms05_utils.add_sequence_item(test, property_id, new_item_value,
                                                              oid=oid, role_path=role_path)
        # Check return type of AddSequenceItem - should be NcMethodResultId
        if not isinstance(method_result, NcMethodResultError):
            if not isinstance(method_result, NcMethodResultXXX):
                self.add_sequence_item_metadata.error = True
                self.add_sequence_item_metadata.error_msg += \
                    f"{error_msg_base}AddSequenceItem error: Unexpected return type; "
                return False
            # add_sequence_item should return index of added item
            if method_result.value != new_item_index:
                self.add_sequence_item_metadata.error = True
                self.add_sequence_item_metadata.error_msg += \
                    f"{error_msg_base}AddSequenceItem error: Unexpected index returned: " \
                    f"Expected: {str(new_item_index)}, Actual: {str(method_result.value)}; "
                return False
            # check the added item value
            method_result = self.ms05_utils.get_sequence_item(test, property_id, index=sequence_length,
                                                              oid=oid, role_path=role_path)
        if isinstance(method_result, NcMethodResultError):
            self.add_sequence_item_metadata.error = True
            self.add_sequence_item_metadata.error_msg += \
                f"{error_msg_base}GetSequenceItem error: {str(method_result.errorMessage)}; "
            return False
        if self.ms05_utils.is_error_status(method_result.status):
            self.add_sequence_item_metadata.error = True
            self.add_sequence_item_metadata.error_msg += \
                f"{error_msg_base}GetSequenceItem error: NcMethodResultError MUST be returned on an error; "
            return False
        if method_result.value != new_item_value:
            self.add_sequence_item_metadata.error = True
            self.add_sequence_item_metadata.error_msg += \
                f"{error_msg_base}AddSequenceItem error. Value added does not match value retrieved: " \
                f"Expected: {str(new_item_value)}, Actual: {str(method_result.value)}; "
        self.add_sequence_item_metadata.checked = True

        return True

    def _check_set_sequence_item(self, test, property_id, property_name, sequence_length, oid, role_path):
        error_msg_base = f"role path={self.ms05_utils.create_role_path_string(role_path)}, " \
                         f"property id={property_id}, " \
                         f"property name={property_name}: "
        method_result = self.ms05_utils.get_sequence_item(test, property_id, index=sequence_length - 1,
                                                          oid=oid, role_path=role_path)
        if not isinstance(method_result, NcMethodResultError):
            new_value = method_result.value
            # set to another value
            method_result = self.ms05_utils.set_sequence_item(test, property_id, index=sequence_length,
                                                              value=new_value, oid=oid, role_path=role_path)
        if not isinstance(method_result, NcMethodResultError):
            # check the value
            method_result = self.ms05_utils.get_sequence_item(test, property_id, index=sequence_length,
                                                              oid=oid, role_path=role_path)
        if not isinstance(method_result, NcMethodResultError):
            if method_result.value != new_value:
                self.set_sequence_item_metadata.error = True
                self.set_sequence_item_metadata.error_msg += \
                    f"{error_msg_base}Sequence method error. " \
                    f"Expected: {str(new_value)}, Actual: {str(method_result.value)}; "
        else:
            self.add_sequence_item_metadata.error = True
            self.add_sequence_item_metadata.error_msg += \
                f"{error_msg_base}Sequence method error: {str(method_result.errorMessage)}; "
            return False

        self.set_sequence_item_metadata.checked = True

        return True

    def _check_remove_sequence_item(self, test, property_id, property_name, sequence_length, oid, role_path):
        error_msg_base = f"role path={self.ms05_utils.create_role_path_string(role_path)}, " \
                         f"property id={property_id}, " \
                         f"property name={property_name}: "
        self.remove_sequence_item_metadata.checked = True
        method_result = self.ms05_utils.remove_sequence_item(test, property_id, index=sequence_length,
                                                             oid=oid, role_path=role_path)
        if isinstance(method_result, NcMethodResultError):
            self.remove_sequence_item_metadata.error = True
            self.remove_sequence_item_metadata.error_msg += \
                f"{error_msg_base}RemoveSequenceItem error: {str(method_result.errorMessage)}; "
        if self.ms05_utils.is_error_status(method_result.status):
            self.remove_sequence_item_metadata.error = True
            self.remove_sequence_item_metadata.error_msg += \
                f"{error_msg_base}RemoveSequenceItem error: NcMethodResultError MUST be returned on an error; "

    def _invasive_check_sequence_methods(self, test, property_id, property_name, oid, role_path):
        """Check that sequence manipulation methods work correctly"""
        error_msg_base = f"role path={self.ms05_utils.create_role_path_string(role_path)}, " \
                         f"property id={property_id}, " \
                         f"property name={property_name}: "

        method_result = self.ms05_utils.get_property(test, property_id, oid=oid, role_path=role_path)

        if isinstance(method_result, NcMethodResultError):
            self.add_sequence_item_metadata.error = True
            self.add_sequence_item_metadata.error_msg += \
                f"{error_msg_base}GetProperty error: {str(method_result.errorMessage)}; "
            return

        response = method_result.value

        if response is None or not isinstance(response, list) or len(response) == 0:
            # Hmmm, these tests depend on sequences already having some data in them.
            # This is so it can copy sequence items for add and set operations
            # without having to generate any new data. It would be better to synthesise
            # valid data to use in these tests
            return

        sequence_length = len(response)

        if not self._check_add_sequence_item(test, property_id, property_name, sequence_length, oid, role_path):
            return

        method_result = self.ms05_utils.get_sequence_length(test, property_id,
                                                            oid=oid, role_path=role_path)
        if not isinstance(method_result, NcMethodResultError):
            if sequence_length + 1 != method_result.value:
                self.add_sequence_item_metadata.error = True
                self.add_sequence_item_metadata.error_msg += \
                    f"{error_msg_base}: AddSequenceItem error, call resulted in unexpected sequence length. " \
                    f"Expected: {str(sequence_length + 1)}, Actual: {str(method_result.value)}; "

            self._check_set_sequence_item(test, property_id, property_name, sequence_length, oid, role_path)

            method_result = self.ms05_utils.get_sequence_length(test, property_id, oid=oid, role_path=role_path)

        if not isinstance(method_result, NcMethodResultError):
            if sequence_length + 1 != method_result.value:
                self.set_sequence_item_metadata.error = True
                self.set_sequence_item_metadata.error_msg += \
                    f"{error_msg_base}: SetSequenceItem error, call resulted in unexpected sequence length." \
                    f"Expected: {str(sequence_length + 1)}, Actual: {str(method_result.value)}; "
            self._check_remove_sequence_item(test, property_id, property_name, sequence_length, oid, role_path)

            method_result = self.ms05_utils.get_sequence_length(test, property_id, oid=oid, role_path=role_path)

        if not isinstance(method_result, NcMethodResultError):
            if sequence_length != method_result.value:
                self.remove_sequence_item_metadata.error = True
                self.remove_sequence_item_metadata.error_msg += \
                    f"{error_msg_base}: RemoveSequenceItem error, call resulted in unexpected sequence length." \
                    f"Expected: {str(sequence_length)}, Actual: {str(method_result.value)}; "
        else:
            self.remove_sequence_item_metadata.error = True
            self.remove_sequence_item_metadata.error_msg += \
                f"{error_msg_base}: sequence method error: {str(method_result.errorMessage)}; "

    def _validate_sequences(self, test):
        """Test all writable sequences"""
        device_model = self.ms05_utils.query_device_model(test)

        constrained_properties = self.ms05_utils.get_properties(test, device_model,
                                                                get_constraints=False, get_sequences=True)

        possible_properties = [{"answer_id": f"answer_{str(i)}",
                                "display_answer": p.name,
                                "resource": p} for i, p in enumerate(constrained_properties)]

        if len(possible_properties) == 0:
            return

        if MS05_INTERACTIVE_TESTING:
            question = """\
                        From this list of sequences\
                        carefully select those that can be safely altered by this test.

                        It should be noted that this test may attempt to Get, Set, Add and Remove sequence items.

                        Also note that this test will attempt to restore the original state of the Device Model.

                        Once you have made you selection please press the 'Submit' button.
                        """
            test_method_name = inspect.currentframe().f_back.f_code.co_name
            selected_ids = \
                self._get_testing_facade_selection(question, possible_properties,
                                                   test_type="multi_choice", test_method_name=test_method_name)

            selected_properties = [p["resource"] for p in possible_properties if p["answer_id"] in selected_ids]

            if len(selected_properties) == 0:
                # No properties selected so can't do the test
                self.sequence_test_unclear = True
        else:
            # If non interactive test all properties
            selected_properties = [p["resource"] for p in possible_properties]

        for constrained_property in selected_properties:
            self._invasive_check_sequence_methods(test,
                                                  constrained_property.descriptor.id,
                                                  constrained_property.descriptor.name,
                                                  constrained_property.oid,
                                                  constrained_property.role_path)

        self.sequences_validated = True

    def test_ms05_37(self, test):
        """NcObject method: SetSequenceItem"""
        if not MS05_INVASIVE_TESTING:
            return test.DISABLED("This test cannot be performed when MS05_INVASIVE_TESTING is False ")

        try:
            if not self.sequences_validated:
                self._validate_sequences(test)
        except NMOSTestException as e:
            # Couldn't validate model so can't perform test
            return test.FAIL(e.args[0].detail, e.args[0].link)
        except TestingFacadeException as e:
            return test.UNCLEAR(f"Testing Facade error: {e.args[0]}")

        if self.sequence_test_unclear:
            return test.UNCLEAR("No sequences selected for testing.")

        if self.set_sequence_item_metadata.error:
            return test.FAIL(self.set_sequence_item_metadata.error_msg)

        if not self.set_sequence_item_metadata.checked:
            return test.UNCLEAR("SetSequenceItem not tested.")

        return test.PASS()

    def test_ms05_38(self, test):
        """NcObject method: AddSequenceItem"""
        if not MS05_INVASIVE_TESTING:
            return test.DISABLED("This test cannot be performed when MS05_INVASIVE_TESTING is False ")

        try:
            if not self.sequences_validated:
                self._validate_sequences(test)
        except NMOSTestException as e:
            # Couldn't validate model so can't perform test
            return test.FAIL(e.args[0].detail, e.args[0].link)
        except TestingFacadeException as e:
            return test.UNCLEAR(f"Testing Facade error: {e.args[0]}")

        if self.sequence_test_unclear:
            return test.UNCLEAR("No sequences selected for testing.")

        if self.add_sequence_item_metadata.error:
            return test.FAIL(self.add_sequence_item_metadata.error_msg)

        if not self.add_sequence_item_metadata.checked:
            return test.UNCLEAR("AddSequenceItem not tested.")

        return test.PASS()

    def test_ms05_39(self, test):
        """NcObject method: RemoveSequenceItem"""
        if not MS05_INVASIVE_TESTING:
            return test.DISABLED("This test cannot be performed when MS05_INVASIVE_TESTING is False ")

        try:
            if not self.sequences_validated:
                self._validate_sequences(test)
        except NMOSTestException as e:
            # Couldn't validate model so can't perform test
            return test.FAIL(e.args[0].detail, e.args[0].link)
        except TestingFacadeException as e:
            return test.UNCLEAR(f"Testing Facade error: {e.args[0]}")

        if self.sequence_test_unclear:
            return test.UNCLEAR("No sequences selected for testing.")

        if self.remove_sequence_item_metadata.error:
            return test.FAIL(self.remove_sequence_item_metadata.error_msg)

        if not self.remove_sequence_item_metadata.checked:
            return test.UNCLEAR("RemoveSequenceItem not tested.")

        return test.PASS()
