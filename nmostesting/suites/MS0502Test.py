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

    def _get_methods(self, test, block):
        results = []

        class_manager = self.ms05_utils.get_class_manager(test)

        for child in block.child_objects:
            class_descriptor = class_manager.get_control_class(child.class_id, include_inherited=True)

            # Only test methods on non-standard classes, as the standard classes are already tested elsewhere
            if not self.ms05_utils.is_non_standard_class(class_descriptor.classId):
                continue

            role_path = self.ms05_utils.create_role_path(block.role_path, child.role)

            for method_descriptor in class_descriptor.methods:
                results.append(MS0502Test.MethodMetadata(
                    child.oid, role_path,
                    f"{self.ms05_utils.create_role_path_string(role_path)}: {class_descriptor.name}: "
                    f"{method_descriptor.name}", method_descriptor))

            if type(child) is NcBlock:
                results += (self._get_methods(test, child))

        return results

    def _check_constrained_parameter(self, test, constrained_property, value, expect_error=True):
        def _do_check(check_function):
            method_result = check_function()
            # Expecting a parameter constraint violation
            if not (expect_error ^ isinstance(method_result, NcMethodResultError)):
                if expect_error:  # only set checked if constraints have been violated/tested
                    self.check_property_metadata.checked = True
            else:
                self.check_property_metadata.error = True
                if expect_error:
                    self.check_property_metadata.error_msg += \
                        f"Constraints not enforced for {constrained_property.name}. " \
                        f"Value: {value}, " \
                        f"Constraints: {constrained_property.constraints}; "
                else:
                    self.check_property_metadata.error_msg += \
                        f"Constraints incorrectly applied for {constrained_property.name}; "

        def _do_set_sequence():
            method_result = self.ms05_utils.get_sequence_length(test,
                                                                constrained_property.descriptor.id,
                                                                oid=constrained_property.oid,
                                                                role_path=constrained_property.role_path)

            if isinstance(method_result, NcMethodResultError):
                # We don't want this error to be confused with a constraints violation error
                raise NMOSTestException(test.FAIL(f"Error getting sequence length {str(method_result.errorMessage)}"))

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

    def _check_parameter_constraints_number(self, test, constrained_property):
        constraints = constrained_property.constraints

        # Attempt to set to a "legal" value
        minimum = (constraints.minimum or 0)
        maximum = (constraints.maximum or sys.maxsize)
        step = (constraints.step or 1)

        new_value = floor((((maximum - minimum) / 2) + minimum) / step) * step + minimum

        # Expect this to work OK
        self._check_constrained_parameter(test, constrained_property, new_value, expect_error=False)

        # Attempt to set to an "illegal" value
        if constraints.minimum is not None:
            self._check_constrained_parameter(test, constrained_property, minimum - step)

        if constraints.maximum is not None:
            self._check_constrained_parameter(test, constrained_property, maximum + step)

        if constraints.step is not None and step > 1:
            self._check_constrained_parameter(test, constrained_property, new_value + step / 2)

    def _check_parameter_constraints_string(self, test, constrained_property):
        constraints = constrained_property.constraints
        new_value = "test"

        if constraints.pattern:
            # Check legal case
            x = Xeger(limit=(constraints.maxCharacters or 0) - len(constraints.pattern)
                      if (constraints.maxCharacters or 0) > len(constraints.pattern) else 1)
            new_value = x.xeger(constraints.pattern)

        # Expect this to work OK
        self._check_constrained_parameter(test, constrained_property, new_value, expect_error=False)

        if constraints.pattern:
            # Possible negative example strings
            # Ideally we would compute a negative string based on the regex.
            # In the meantime, some strings that might possibly violate the regex
            negative_examples = ["!$%^&*()+_:;/", "*********", "000000000", "AAAAAAAA"]

            for negative_example in negative_examples:
                # Verify this string violates constraint
                if not re.search(constraints.pattern, negative_example):
                    self._check_constrained_parameter(test, constrained_property, negative_example)

        # Exceed max character limit
        if constraints.maxCharacters:
            if constraints.pattern:
                x = Xeger(limit=constraints.maxCharacters * 2)
                new_value = x.xeger(constraints.pattern)
            else:
                new_value = "*" * constraints.maxCharacters * 2

            # Verfiy this string violates constraint
            if len(new_value) > constraints.maxCharacters:
                self._check_constrained_parameter(test, constrained_property, new_value)

    def _check_sequence_datatype_type(self, test, property_under_test, original_value):
        self.check_property_metadata.checked = True

        modified_value = list(reversed(original_value))

        # Reset to original value
        method_result = self.ms05_utils.set_property(test,
                                                     property_under_test.descriptor.id,
                                                     modified_value,
                                                     oid=property_under_test.oid,
                                                     role_path=property_under_test.role_path)

        if isinstance(method_result, NcMethodResultError):
            self.check_property_metadata.error = True
            self.check_property_metadata.error_msg += \
                f"{self.ms05_utils.create_role_path_string(property_under_test.role_path)}. " \
                f"Unable to set property {str(property_under_test.descriptor.id)}: " \
                f"{str(method_result.errorMessage)} "

    def _do_check_property_test(self, test, question, get_constraints=False, get_sequences=False, datatype_type=None):
        """Test properties within the Device Model"""
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
            if isinstance(method_result, NcMethodResultError):
                return test.FAIL(f"{constrained_property.name}: Error getting value of property. "
                                 f"{str(constrained_property.descriptor.id)}: {str(method_result.errorMessage)}. "
                                 f"Constraints: {str(constraints)}")

            original_value = method_result.value
            try:
                if get_constraints:
                    if isinstance(constraints, (NcParameterConstraintsNumber, NcPropertyConstraintsNumber)):
                        self._check_parameter_constraints_number(test, constrained_property)
                    if isinstance(constraints, (NcParameterConstraintsString, NcPropertyConstraintsString)):
                        self._check_parameter_constraints_string(test, constrained_property)
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
                return test.FAIL(f"{constrained_property.name}: Error setting value of property: "
                                 f"{str(constrained_property.descriptor.id)}: {str(method_result.errorMessage)}. "
                                 f"Original value: {str(original_value)}, "
                                 f"Constraints {str(constraints)}")

        if self.check_property_metadata.error:
            # JRT add link to constraints spec
            return test.FAIL(self.check_property_metadata.error_msg)

        if get_constraints and self.check_property_metadata.checked:
            return test.PASS()

        return test.UNCLEAR("No properties of this type checked")

    def _resolve_is_sequence(self, test, datatype):
        if datatype is None:
            return False

        class_manager = self.ms05_utils.get_class_manager(test)

        datatype_descriptor = class_manager.datatype_descriptors[datatype]

        if isinstance(datatype_descriptor, NcDatatypeDescriptorTypeDef):
            return datatype_descriptor.isSequence

        if isinstance(datatype_descriptor, NcDatatypeDescriptorStruct) and datatype_descriptor.parentType:
            return self._resolve_is_sequence(test, datatype_descriptor.parentType)

        return False

    def _generate_number_parameter(self, constraints):
        if isinstance(constraints, (NcParameterConstraintsNumber, NcPropertyConstraintsNumber)):
            minimum = (constraints.minimum or 0)
            maximum = (constraints.maximum or sys.maxsize)
            step = (constraints.step or 1)

            return floor((((maximum - minimum) / 2) + minimum) / step) * step + minimum
        return None

    def _generate_string_parameter(self, constraints):
        if constraints.pattern and isinstance(constraints, (NcParameterConstraintsString,
                                                            NcPropertyConstraintsString)):
            # Check legal case
            x = Xeger(limit=(constraints.maxCharacters or 0) - len(constraints.pattern)
                      if (constraints.maxCharacters or 0) > len(constraints.pattern) else 1)
            return x.xeger(constraints.pattern)
        return ""

    def _generate_primitive_parameter(self, datatype):
        type_mapping = {
            "NcBoolean": False,
            "NcInt16": 1,
            "NcInt32": 1,
            "NcInt64": 1,
            "NcUint16": 1,
            "NcUint32": 1,
            "NcUint64": 1,
            "NcFloat32": 1.0,
            "NcFloat64":  1.0,
            "NcString": ""
        }

        return type_mapping.get(datatype)

    def _create_compatible_parameters(self, test, parameters):
        result = {}

        for parameter_descriptor in parameters:
            parameter = None

            # if there are constraints use them
            if parameter_descriptor.constraints:
                constraints = parameter_descriptor.constraints
                # either there is a default value, or this is a number constraint, or this is a string
                if constraints.defaultValue is not None:
                    parameter = constraints.defaultValue
                elif isinstance(constraints, (NcParameterConstraintsNumber, NcPropertyConstraintsNumber)):
                    parameter = self._generate_number_parameter(constraints)
                elif isinstance(constraints, (NcParameterConstraintsString, NcPropertyConstraintsString)):
                    parameter = self._generate_string_parameter(constraints)
            else:
                # resolve the datatype to either a struct, enum, primative or None
                datatype = self.ms05_utils.resolve_datatype(test, parameter_descriptor.typeName)

                if datatype is None:
                    parameter = 42  # None denotes an 'any' type so set to an arbitrary type/value
                else:
                    class_manager = self.ms05_utils.get_class_manager(test)

                    datatype_descriptor = class_manager.datatype_descriptors[datatype]

                    if isinstance(datatype_descriptor, NcDatatypeDescriptorEnum):
                        parameter = datatype_descriptor.items[0].value
                    elif isinstance(datatype_descriptor, NcDatatypeDescriptorPrimitive):
                        parameter = self._generate_primitive_parameter(datatype)
                    elif isinstance(datatype_descriptor, NcDatatypeDescriptorStruct):
                        parameter = self._create_compatible_parameters(test, datatype_descriptor.fields)

            if parameter_descriptor.isSequence:
                parameter = [parameter]

            # Note that only NcDatatypeDescriptorTypeDef has an isSequence property
            result[parameter_descriptor.name] = [parameter] \
                if self._resolve_is_sequence(test, parameter_descriptor.typeName) else parameter

        return result

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

            if isinstance(method_result, NcMethodResultError):
                return test.FAIL(f"{readonly_property.name}: Error getting property: "
                                 f"{str(method_result.errorMessage)} ")

            original_value = method_result.value
            # Try setting this value
            method_result = self.ms05_utils.set_property(test,
                                                         readonly_property.descriptor.id,
                                                         original_value,
                                                         oid=readonly_property.oid,
                                                         role_path=readonly_property.role_path)

            if not isinstance(method_result, NcMethodResultError):
                # if it gets this far it's failed
                return test.FAIL(f"{readonly_property.name}: Read only property is writable")
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

    def _do_check_methods_test(self, test, question):
        """Test methods of non-standard objects within the Device Model"""
        device_model = self.ms05_utils.query_device_model(test)

        methods = self._get_methods(test, device_model)

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

            parameters = self._create_compatible_parameters(test, method.descriptor.parameters)

            try:
                method_result = self.ms05_utils.invoke_method(test, method.descriptor.id, parameters,
                                                              oid=method.oid, role_path=method.role_path)

                # JRT TODO: check that the returning method result is an error if it has an error status
                # check for deprecated status codes for deprecated methods
                if method.descriptor.isDeprecated and method_result.status != 299:
                    self.invoke_methods_metadata.error = True
                    self.invoke_methods_metadata.error_msg += \
                        f"Deprecated method returned incorrect status code {method.name} : {method_result.status}"
            except NMOSTestException as e:
                self.invoke_methods_metadata.error = True
                self.invoke_methods_metadata.error_msg += \
                    f"Error invoking method {method.name} : {e.args[0].detail}"
        if self.invoke_methods_metadata.error:
            return test.FAIL(self.invoke_methods_metadata.error_msg)

        if self.invoke_methods_metadata.checked:
            return test.PASS()

        return test.UNCLEAR("No methods checked.")

    def test_ms05_07(self, test):
        """Check discovered methods"""
        question = """\
                   From this list of methods\
                   carefully select those that can be safely invoked by this test.

                   Note that this test will NOT attempt to restore the original state of the Device Model.

                   Once you have made you selection please press the 'Submit' button.
                   """

        return self._do_check_methods_test(test, question)

    def check_add_sequence_item(self, test, property_id, property_name, sequence_length, oid, role_path):
        context = self.ms05_utils.create_role_path_string(role_path)
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
        # Check return type of addSequenceItem - should be NcMethodResultId
        if not isinstance(method_result, NcMethodResultError):
            if not isinstance(method_result, NcMethodResultXXX):
                self.add_sequence_item_metadata.error = True
                self.add_sequence_item_metadata.error_msg += \
                    f"{context}{property_name}: Unexpected return type from addSequenceItem. "
                return False
            # add_sequence_item should return index of added item
            if method_result.value != new_item_index:
                self.add_sequence_item_metadata.error = True
                self.add_sequence_item_metadata.error_msg += \
                    f"{context}{property_name}: Unexpected index of added item. " \
                    f"Expected: {str(new_item_index)}, Actual: {str(method_result.value)}"
                return False
            # check the added item value
            method_result = self.ms05_utils.get_sequence_item(test, property_id, index=sequence_length,
                                                              oid=oid, role_path=role_path)
        if isinstance(method_result, NcMethodResultError):
            self.add_sequence_item_metadata.error = True
            self.add_sequence_item_metadata.error_msg += \
                f"{context}{property_name}: Sequence method error: {str(method_result.errorMessage)} "
            return False

        if method_result.value != new_item_value:
            self.add_sequence_item_metadata.error = True
            self.add_sequence_item_metadata.error_msg += \
                f"{context}{property_name}: Error adding sequence item. " \
                f"Expected: {str(new_item_value)}, Actual: {str(method_result.value)}, "
        self.add_sequence_item_metadata.checked = True

        return True

    def check_set_sequence_item(self, test, property_id, property_name, sequence_length, oid, role_path):
        context = self.ms05_utils.create_role_path_string(role_path)
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
                    f"{context}{property_name}: Error setting sequence value. " \
                    f"Expected: {str(new_value)}, Actual: {str(method_result.value)}, "
        else:
            self.add_sequence_item_metadata.error = True
            self.add_sequence_item_metadata.error_msg += \
                f"{context}{property_name}: Sequence method error: {str(method_result.errorMessage)} "
            return False

        self.set_sequence_item_metadata.checked = True

        return True

    def check_remove_sequence_item(self, test, property_id, property_name, sequence_length, oid, role_path):
        # remove item
        self.remove_sequence_item_metadata.checked = True
        method_result = self.ms05_utils.remove_sequence_item(test, property_id, index=sequence_length,
                                                             oid=oid, role_path=role_path)
        if isinstance(method_result, NcMethodResultError):
            self.remove_sequence_item_metadata.error = True
            self.remove_sequence_item_metadata.error_msg += \
                f"{self.ms05_utils.create_role_path_string(role_path)}{property_name}: " \
                f"Error removing sequence item: {str(method_result.errorMessage)}, "
        return False

    def check_sequence_methods(self, test, property_id, property_name, oid, role_path):
        """Check that sequence manipulation methods work correctly"""

        method_result = self.ms05_utils.get_property(test, property_id, oid=oid, role_path=role_path)

        if isinstance(method_result, NcMethodResultError):
            self.add_sequence_item_metadata.error = True
            self.add_sequence_item_metadata.error_msg += \
                f"error getting property: {str(property_id)}, {str(method_result.errorMessage)} "
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
                    f"{property_name}: add_sequence_item resulted in unexpected sequence length. " \
                    f"Expected: {str(sequence_length + 1)}, Actual: {str(method_result.value)}. "

            self.check_set_sequence_item(test, property_id, property_name, sequence_length, oid, role_path)

            method_result = self.ms05_utils.get_sequence_length(test, property_id, oid=oid, role_path=role_path)

        if not isinstance(method_result, NcMethodResultError):
            if sequence_length + 1 != method_result.value:
                self.set_sequence_item_metadata.error = True
                self.set_sequence_item_metadata.error_msg += \
                    f"{property_name}: set_sequence_item resulted in unexpected sequence length." \
                    f"Expected: {str(sequence_length + 1)}, Actual: {str(method_result.value)}. "
            self.check_remove_sequence_item(test, property_id, property_name, sequence_length, oid, role_path)

            method_result = self.ms05_utils.get_sequence_length(test, property_id, oid=oid, role_path=role_path)

        if not isinstance(method_result, NcMethodResultError):
            if sequence_length != method_result.value:
                self.remove_sequence_item_metadata.error = True
                self.remove_sequence_item_metadata.error_msg += \
                    f"{property_name}: remove_sequence_item resulted in unexpected sequence length." \
                    f"Expected: {str(sequence_length)}, Actual: {str(method_result.value)}. "
        else:
            self.remove_sequence_item_metadata.error = True
            self.remove_sequence_item_metadata.error_msg += \
                f"{property_name}: Error getting sequence length. {str(method_result.errorMessage)}"

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

    def test_ms05_08(self, test):
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

    def test_ms05_09(self, test):
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

    def test_ms05_10(self, test):
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
