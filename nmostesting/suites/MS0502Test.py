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

import re
import sys

from copy import copy, deepcopy
from math import floor
from xeger import Xeger

from ..Config import IS12_INTERACTIVE_TESTING
from ..GenericTest import NMOSTestException
from ..ControllerTest import ControllerTest, TestingFacadeException
from ..MS05Utils import NcDatatypeDescriptorEnum, NcDatatypeDescriptorPrimitive, NcDatatypeType, NcBlock, \
    NcDatatypeDescriptorStruct, NcDatatypeDescriptorTypeDef, NcMethodResultError, NcMethodResultXXX, \
    NcParameterConstraintsNumber, NcParameterConstraintsString, NcPropertyConstraintsNumber, \
    NcPropertyConstraintsString

NODE_API_KEY = "node"
CONTROL_API_KEY = "ncp"
MS05_API_KEY = "controlframework"
FEATURE_SETS_KEY = "featuresets"

# Note: this test suite is a base class for the IS1202Test and IS1402Test test suites
# where there are common MS-05 tests.  The test suite is not configured and
# instantiated in the same way as the other test suites.  This is
# explicitly instantiated by the IS-12 and IS-14 test suites


class MS0502Test(ControllerTest):
    """
    Runs Invasive Tests covering MS-05
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
        ControllerTest.__init__(self, apis, **kwargs)
        self.ms05_utils = utils

    def set_up_tests(self):
        self.ms05_utils.reset()
        self.check_property_metadata = MS0502Test.TestMetadata()
        self.set_sequence_item_metadata = MS0502Test.TestMetadata()
        self.add_sequence_item_metadata = MS0502Test.TestMetadata()
        self.remove_sequence_item_metadata = MS0502Test.TestMetadata()
        self.invoke_methods_metadata = MS0502Test.TestMetadata()
        self.sequences_validated = False
        self.sequence_test_unclear = False

    def tear_down_tests(self):
        pass

    def pre_tests_message(self):
        """
        Introduction to MS-05 Invasive Tests
        """
        if not IS12_INTERACTIVE_TESTING:
            return

        # In order to give the tests some context, a pre tests message is displayed
        # on the Testing Facade prior to the tests starting. This communicates any
        # pre-requisites or setup required by the Test User.
        question = """\
                   These tests validate a Node under test's MS-05 Device Model.

                   These tests are invasive and could cause harm to the Node under test.

                   !!!Care should therefore be taken when running these tests!!!

                   Each test will allow Device Model object properties to be excluded from the testing.

                   Start the tests by clicking the 'Next' button.
                   """

        try:
            self._invoke_testing_facade(question, [], test_type="action")

        except TestingFacadeException:
            # pre_test_introducton timed out
            pass

    def post_tests_message(self):
        """
        MS-05 Test Suite complete!
        """
        if not IS12_INTERACTIVE_TESTING:
            return
        # Once the tests are complete this post tests message is displayed.

        question = """\
                   MS-05 tests complete!

                   Please press the 'Next' button to exit the tests.
                   """

        try:
            self._invoke_testing_facade(question, [], test_type="action")

        except TestingFacadeException:
            # post_test_introducton timed out
            pass

    def _get_constraints(self, test, class_property, datatype_descriptors, object_runtime_constraints):
        datatype_constraints = None
        runtime_constraints = None
        # Level 0: Datatype constraints
        if class_property.typeName:
            datatype_constraints = datatype_descriptors.get(class_property.typeName).constraints
        # Level 1: Property constraints
        property_constraints = class_property.constraints
        # Level 3: Runtime constraints
        if object_runtime_constraints:
            for object_runtime_constraint in object_runtime_constraints:
                if object_runtime_constraint.propertyId == class_property.id:
                    runtime_constraints = object_runtime_constraints

        return runtime_constraints or property_constraints or datatype_constraints

    def _get_properties(self, test, block, get_constraints=True, get_sequences=False, get_readonly=False):
        results = []

        class_manager = self.ms05_utils.get_class_manager(test)

        # Note that the userLabel of the block may also be changed, and therefore might be
        # subject to runtime constraints constraints
        for child in block.child_objects:
            class_descriptor = class_manager.get_control_class(child.class_id, include_inherited=True)

            if not class_descriptor:
                continue
            role_path = self.ms05_utils.create_role_path(block.role_path, child.role)

            for property_descriptor in class_descriptor.properties:
                constraints = self._get_constraints(test,
                                                    property_descriptor,
                                                    class_manager.datatype_descriptors,
                                                    child.runtime_constraints)
                if get_readonly == property_descriptor.isReadOnly \
                        and property_descriptor.isSequence == get_sequences \
                        and bool(constraints) == get_constraints:
                    datatype = class_manager.get_datatype(property_descriptor.typeName, include_inherited=False)

                    results.append(MS0502Test.PropertyMetadata(
                        child.oid, role_path,
                        f"{self.ms05_utils.create_role_path_string(role_path)}: {class_descriptor.name}: "
                        f"{property_descriptor.name}",
                        constraints,
                        datatype.type,
                        property_descriptor))
            if type(child) is NcBlock:
                results += (self._get_properties(test, child, get_constraints, get_sequences, get_readonly))

        return results

    def _get_methods(self, test, block, get_constraints=False):
        results = []

        class_manager = self.ms05_utils.get_class_manager(test)

        for child in block.child_objects:
            class_descriptor = class_manager.get_control_class(child.class_id, include_inherited=True)

            if not class_descriptor:
                continue
            # Only test methods on non-standard classes, as the standard classes are already tested elsewhere
            if not self.ms05_utils.is_non_standard_class(class_descriptor.classId):
                continue

            role_path = self.ms05_utils.create_role_path(block.role_path, child.role)

            for method_descriptor in class_descriptor.methods:
                # Check for parameter constraints
                parameter_constraints = False
                for parameter in method_descriptor.parameters:
                    if parameter.constraints:
                        parameter_constraints = True

                if parameter_constraints == get_constraints:
                    results.append(MS0502Test.MethodMetadata(
                        child.oid, role_path, method_descriptor.name, method_descriptor))

            if type(child) is NcBlock:
                results += (self._get_methods(test, child))

        return results

    def _check_constrained_parameter(self, test, constrained_property, value, expect_error=True):
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

    def _generate_number_parameters(self, constraints, violate_constraints=False):
        # Generate a number value based on constraints if present.
        # violate_constraints=True will generate an "invalid" value based on constraints
        parameters = []

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

    def _generate_string_parameters(self, constraints, violate_constraints):
        # Generate a string value based on constraints if present.
        # violate_constraints=True will generate an "invalid" string based on constraints
        parameters = []

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

    def _check_parameter_constraints(self, test, constrained_property):
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
                self._check_constrained_parameter(test, constrained_property, parameter,
                                                  expect_error=violate_constraints)

    def _check_sequence_datatype_type(self, test, property_under_test, original_value):
        # Check that a sequence property can be set
        self.check_property_metadata.checked = True

        modified_value = list(reversed(original_value))

        # Reset to original value
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
        if self.ms05_utils.is_error_status(method_result.status):
            raise NMOSTestException(test.FAIL(f"{error_msg_base}SetProperty error: "
                                              "NcMethodResultError MUST be returned on an error."))

    def _do_check_property_test(self, test, question, get_constraints=False, get_sequences=False, datatype_type=None):
        # Test properties of the Device Model
        # get_constraints - select properties that have constraints
        # get_sequences - select properties that are sequences
        # datatype_type - only select properties that are this datatype type (None selects all)
        device_model = self.ms05_utils.query_device_model(test)

        constrained_properties = self._get_properties(test, device_model, get_constraints, get_sequences)

        # Filter constrained properties according to datatype_type
        constrained_properties = [p for p in constrained_properties
                                  if datatype_type is None or p.datatype_type == datatype_type]

        possible_properties = [{"answer_id": f"answer_{str(i)}",
                                "display_answer": p.name,
                                "resource": p} for i, p in enumerate(constrained_properties)]

        if len(possible_properties) == 0:
            return test.UNCLEAR("No testable properties in Device Model.")

        if IS12_INTERACTIVE_TESTING:
            selected_ids = \
                self._invoke_testing_facade(question, possible_properties, test_type="multi_choice")["answer_response"]

            selected_properties = [p["resource"] for p in possible_properties if p["answer_id"] in selected_ids]

            if len(selected_properties) == 0:
                return test.UNCLEAR("No properties selected for testing.")
        else:
            # If non-interactive then test all methods
            selected_properties = [p["resource"] for p in possible_properties]

        self.check_property_metadata = MS0502Test.TestMetadata()

        for constrained_property in selected_properties:

            # Cache original property value
            constraints = constrained_property.constraints

            method_result = self.ms05_utils.get_property(test, constrained_property.descriptor.id,
                                                         oid=constrained_property.oid,
                                                         role_path=constrained_property.role_path)
            error_msg_base = f"role path={self.ms05_utils.create_role_path_string(constrained_property.role_path)}, " \
                             f"property id={constrained_property.descriptor.id}, " \
                             f"property name={constrained_property.descriptor.name}: "
            if isinstance(method_result, NcMethodResultError):
                return test.FAIL(f"{error_msg_base}GetProperty error: {str(method_result.errorMessage)}. "
                                 f"constraints: {str(constraints)}")
            if self.ms05_utils.is_error_status(method_result.status):
                return test.FAIL(f"{error_msg_base}GetProperty error: "
                                 "NcMethodResultError MUST be returned on an error.")

            original_value = method_result.value
            try:
                if get_constraints:
                    self._check_parameter_constraints(test, constrained_property)
                elif datatype_type is not None and get_sequences:
                    # Enums and Struct are validated against their type definitions
                    self._check_sequence_datatype_type(test, constrained_property, original_value)
            except NMOSTestException as e:
                return test.FAIL(f"{constrained_property.name}: Error setting property: {str(e.args[0].detail)}. ")

            # Reset to original value
            method_result = self.ms05_utils.set_property(test,
                                                         constrained_property.descriptor.id,
                                                         original_value,
                                                         oid=constrained_property.oid,
                                                         role_path=constrained_property.role_path)
            if isinstance(method_result, NcMethodResultError):
                return test.FAIL(f"{error_msg_base}SetProperty error: {str(method_result.errorMessage)}. "
                                 f"original value: {str(original_value)}, "
                                 f"constraints: {str(constraints)}")
            if self.ms05_utils.is_error_status(method_result.status):
                return test.FAIL(f"{error_msg_base}SetProperty error: "
                                 "NcMethodResultError MUST be returned on an error.")

        if self.check_property_metadata.error:
            # JRT add link to constraints spec
            return test.FAIL(self.check_property_metadata.error_msg)

        if self.check_property_metadata.checked:
            return test.PASS()

        return test.UNCLEAR("No properties of this type checked")

    def test_ms05_01(self, test):
        """Constraints on writable properties are enforced"""

        question = """\
                    From this list of properties with parameter constraints\
                    carefully select those that can be safely altered by this test.

                    Note that this test will attempt to restore the original state of the Device Model.

                    Once you have made you selection please press the 'Submit' button.
                    """
        return self._do_check_property_test(test, question, get_constraints=True, get_sequences=False)

    def test_ms05_02(self, test):
        """Constraints on writable sequences are enforced"""
        question = """\
                   From this list of sequences with parameter constraints\
                   carefully select those that can be safely altered by this test.

                   Note that this test will attempt to restore the original state of the Device Model.

                   Once you have made you selection please press the 'Submit' button.
                   """

        return self._do_check_property_test(test, question, get_constraints=True, get_sequences=True)

    def test_ms05_03(self, test):
        """Check writable enumeration sequences"""
        question = """\
                   From this list of enumeration sequences\
                   carefully select those that can be safely altered by this test.

                   Note that this test will attempt to restore the original state of the Device Model.

                   Once you have made you selection please press the 'Submit' button.
                   """

        return self._do_check_property_test(test, question, get_constraints=False, get_sequences=True,
                                            datatype_type=NcDatatypeType.Enum)

    def test_ms05_04(self, test):
        """Check writable struct sequences"""
        question = """\
                   From this list of struct sequences\
                   carefully select those that can be safely altered by this test.

                   Note that this test will attempt to restore the original state of the Device Model.

                   Once you have made you selection please press the 'Submit' button.
                   """

        return self._do_check_property_test(test, question, get_constraints=False, get_sequences=True,
                                            datatype_type=NcDatatypeType.Struct)

    def _do_check_readonly_properties(self, test, question, get_sequences=False):
        device_model = self.ms05_utils.query_device_model(test)

        readonly_properties = self._get_properties(test, device_model, get_constraints=False,
                                                   get_sequences=get_sequences, get_readonly=True)

        possible_properties = [{"answer_id": f"answer_{str(i)}",
                                "display_answer": p.name,
                                "resource": p} for i, p in enumerate(readonly_properties)]

        if len(possible_properties) == 0:
            return test.UNCLEAR("No testable properties in Device Model.")

        if IS12_INTERACTIVE_TESTING:
            selected_ids = \
                self._invoke_testing_facade(question, possible_properties, test_type="multi_choice")["answer_response"]

            selected_properties = [p["resource"] for p in possible_properties if p["answer_id"] in selected_ids]

            if len(selected_properties) == 0:
                return test.UNCLEAR("No properties selected for testing.")
        else:
            # If non-interactive then test all methods
            selected_properties = [p["resource"] for p in possible_properties]

        readonly_checked = False

        for readonly_property in selected_properties:

            # Cache original property value
            method_result = self.ms05_utils.get_property(test,
                                                         readonly_property.descriptor.id,
                                                         oid=readonly_property.oid,
                                                         role_path=readonly_property.role_path)

            error_msg_base = f"role path={self.ms05_utils.create_role_path_string(readonly_property.role_path)}, " \
                             f"property id={readonly_property.descriptor.id}, " \
                             f"property name={readonly_property.descriptor.name}: "
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
                return test.FAIL(f"{error_msg_base}SetProperty error: Read only property is writable.")
            else:
                readonly_checked = True

        if not readonly_checked:
            return test.UNCLEAR("No read only properties found")

        return test.PASS()

    def test_ms05_05(self, test):
        """Check read only properties are not writable"""

        question = """\
                   From this list of read only properties\
                   carefully select those that can be safely altered by this test.

                   Note that this test will attempt to restore the original state of the Device Model.

                   Once you have made you selection please press the 'Submit' button.
                   """

        return self._do_check_readonly_properties(test, question, get_sequences=False)

    def test_ms05_06(self, test):
        """Check read only sequences are not writable"""

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
        # so we every combination of violation in isolation - rather than violating all constraints all at once.
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

        methods = self._get_methods(test, device_model, get_constraints)

        possible_methods = [{"answer_id": f"answer_{str(i)}",
                             "display_answer": p.name,
                             "resource": p} for i, p in enumerate(methods)]

        if len(possible_methods) == 0:
            return test.UNCLEAR("No non standard methods in Device Model.")

        if IS12_INTERACTIVE_TESTING:
            selected_ids = \
                self._invoke_testing_facade(question, possible_methods, test_type="multi_choice")["answer_response"]

            selected_methods = [p["resource"] for p in possible_methods if p["answer_id"] in selected_ids]

            if len(selected_methods) == 0:
                return test.UNCLEAR("No methods selected for testing.")
        else:
            # If non-interactive then test all methods
            selected_methods = [p["resource"] for p in possible_methods]

        self.invoke_methods_metadata.error = False
        self.invoke_methods_metadata.error_msg = ""

        for method in selected_methods:
            self.invoke_methods_metadata.checked = True

            parameters_list = self._create_parameters_list(test, method.descriptor.parameters)

            success = True
            for parameters in parameters_list:
                try:
                    method_result = self.ms05_utils.invoke_method(test, method.descriptor.id, parameters,
                                                                  oid=method.oid, role_path=method.role_path)

                    error_msg_base = f"role path={self.ms05_utils.create_role_path_string(method.role_path)}, " \
                                     f"method id={method.descriptor.id}, method name={method.name}, "
                    if isinstance(method_result, NcMethodResultError):
                        success = False
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
                        f"Error invoking method {method.name}: {e.args[0].detail}; "

            # Only do negative checking of constrained parameters if positive case was successful
            if get_constraints and success:
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

    def test_ms05_07(self, test):
        """Check discovered methods with unconstrained parameters"""
        question = """\
                   From this list of methods\
                   carefully select those that can be safely invoked by this test.

                   Note that this test will NOT attempt to restore the original state of the Device Model.

                   Once you have made you selection please press the 'Submit' button.
                   """

        return self._do_check_methods_test(test, question, get_constraints=False)

    def test_ms05_08(self, test):
        """Constraints on method parameters are enforced"""
        question = """\
                   From this list of methods\
                   carefully select those that can be safely invoked by this test.

                   Note that this test will NOT attempt to restore the original state of the Device Model.

                   Once you have made you selection please press the 'Submit' button.
                   """

        return self._do_check_methods_test(test, question, get_constraints=True)

    def check_add_sequence_item(self, test, property_id, property_name, sequence_length, oid, role_path):
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

    def check_set_sequence_item(self, test, property_id, property_name, sequence_length, oid, role_path):
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

    def check_remove_sequence_item(self, test, property_id, property_name, sequence_length, oid, role_path):
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

    def check_sequence_methods(self, test, property_id, property_name, oid, role_path):
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

        if not self.check_add_sequence_item(test, property_id, property_name, sequence_length, oid, role_path):
            return

        method_result = self.ms05_utils.get_sequence_length(test, property_id,
                                                            oid=oid, role_path=role_path)
        if not isinstance(method_result, NcMethodResultError):
            if sequence_length + 1 != method_result.value:
                self.add_sequence_item_metadata.error = True
                self.add_sequence_item_metadata.error_msg += \
                    f"{error_msg_base}: AddSequenceItem error, call resulted in unexpected sequence length. " \
                    f"Expected: {str(sequence_length + 1)}, Actual: {str(method_result.value)}; "

            self.check_set_sequence_item(test, property_id, property_name, sequence_length, oid, role_path)

            method_result = self.ms05_utils.get_sequence_length(test, property_id, oid=oid, role_path=role_path)

        if not isinstance(method_result, NcMethodResultError):
            if sequence_length + 1 != method_result.value:
                self.set_sequence_item_metadata.error = True
                self.set_sequence_item_metadata.error_msg += \
                    f"{error_msg_base}: SetSequenceItem error, call resulted in unexpected sequence length." \
                    f"Expected: {str(sequence_length + 1)}, Actual: {str(method_result.value)}; "
            self.check_remove_sequence_item(test, property_id, property_name, sequence_length, oid, role_path)

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

    def validate_sequences(self, test):
        """Test all writable sequences"""
        device_model = self.ms05_utils.query_device_model(test)

        constrained_properties = self._get_properties(test, device_model, get_constraints=False, get_sequences=True)

        possible_properties = [{"answer_id": f"answer_{str(i)}",
                                "display_answer": p.descriptor.name,
                                "resource": p} for i, p in enumerate(constrained_properties)]

        if len(possible_properties) == 0:
            return test.UNCLEAR("No properties with ParameterConstraints in Device Model.")

        if IS12_INTERACTIVE_TESTING:
            question = """\
                        From this list of sequences\
                        carefully select those that can be safely altered by this test.

                        Once you have made you selection please press the 'Submit' button.
                        """

            selected_ids = \
                self._invoke_testing_facade(question, possible_properties, test_type="multi_choice")["answer_response"]

            selected_properties = [p["resource"] for p in possible_properties if p["answer_id"] in selected_ids]

            if len(selected_properties) == 0:
                # No properties selected so can't do the test
                self.sequence_test_unclear = True
        else:
            # If non interactive test all properties
            selected_properties = [p["resource"] for p in possible_properties]

        for constrained_property in selected_properties:
            self.check_sequence_methods(test,
                                        constrained_property.descriptor.id,
                                        constrained_property.descriptor.name,
                                        constrained_property.oid,
                                        constrained_property.role_path)

        self.sequences_validated = True

    def test_ms05_09(self, test):
        """NcObject method: SetSequenceItem"""
        try:
            if not self.sequences_validated:
                self.validate_sequences(test)
        except NMOSTestException as e:
            # Couldn't validate model so can't perform test
            return test.FAIL(e.args[0].detail, e.args[0].link)

        if self.sequence_test_unclear:
            return test.UNCLEAR("No sequences selected for testing.")

        if self.set_sequence_item_metadata.error:
            return test.FAIL(self.set_sequence_item_metadata.error_msg)

        if not self.set_sequence_item_metadata.checked:
            return test.UNCLEAR("SetSequenceItem not tested.")

        return test.PASS()

    def test_ms05_10(self, test):
        """NcObject method: AddSequenceItem"""
        try:
            if not self.sequences_validated:
                self.validate_sequences(test)
        except NMOSTestException as e:
            # Couldn't validate model so can't perform test
            return test.FAIL(e.args[0].detail, e.args[0].link)

        if self.sequence_test_unclear:
            return test.UNCLEAR("No sequences selected for testing.")

        if self.add_sequence_item_metadata.error:
            return test.FAIL(self.add_sequence_item_metadata.error_msg)

        if not self.add_sequence_item_metadata.checked:
            return test.UNCLEAR("AddSequenceItem not tested.")

        return test.PASS()

    def test_ms05_11(self, test):
        """NcObject method: RemoveSequenceItem"""
        try:
            if not self.sequences_validated:
                self.validate_sequences(test)
        except NMOSTestException as e:
            # Couldn't validate model so can't perform test
            return test.FAIL(e.args[0].detail, e.args[0].link)

        if self.sequence_test_unclear:
            return test.UNCLEAR("No sequences selected for testing.")

        if self.remove_sequence_item_metadata.error:
            return test.FAIL(self.remove_sequence_item_metadata.error_msg)

        if not self.remove_sequence_item_metadata.checked:
            return test.UNCLEAR("RemoveSequenceItem not tested.")

        return test.PASS()
