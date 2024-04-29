# Copyright (C) 2023 Advanced Media Workflow Association
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
from ..IS12Utils import IS12Utils, NcDatatypeType, \
    NcObjectProperties, NcBlock

NODE_API_KEY = "node"
CONTROL_API_KEY = "ncp"
MS05_API_KEY = "controlframework"
FEATURE_SETS_KEY = "featuresets"


class IS1202Test(ControllerTest):

    def __init__(self, apis, **kwargs):
        ControllerTest.__init__(self, apis, **kwargs)
        self.node_url = self.apis[NODE_API_KEY]["url"]
        self.ncp_url = self.apis[CONTROL_API_KEY]["url"]
        self.is12_utils = IS12Utils(apis)
        self.is12_utils.load_reference_resources(CONTROL_API_KEY)
        self.device_model = None
        self.constraint_error = False
        self.constraint_error_msg = ""
        self.device_model_metadata = {"checked": False, "error": False, "error_msg": ""}
        self.sequences_validated = False
        self.get_sequence_item_metadata = {"checked": False, "error": False, "error_msg": ""}
        self.set_sequence_item_metadata = {"checked": False, "error": False, "error_msg": ""}
        self.add_sequence_item_metadata = {"checked": False, "error": False, "error_msg": ""}
        self.sequence_test_unclear = False
        self.remove_sequence_item_metadata = {"checked": False, "error": False, "error_msg": "", "unclear": False}
        self.invoke_methods_metadata = {"checked": False, "error": False, "error_msg": ""}

    def set_up_tests(self):
        # Don't set up mock resources as not needed
        pass

    def tear_down_tests(self):
        # Clean up Websocket resources
        self.is12_utils.close_ncp_websocket()

    def pre_tests_message(self):
        """
        Introduction to IS-12 Invasive Tests
        """
        if not IS12_INTERACTIVE_TESTING:
            return

        # In order to give the tests some context, a pre tests message is displayed
        # on the Testing Facade prior to the tests starting. This communicates any
        # pre-requisites or setup required by the Test User.
        question = """\
                   These tests validate a Node under test's MS-05 Device Model using IS-12.

                   These tests are invasive and could cause harm to the Node under test.

                   !!!Care should therefore be taken when running these tests!!!

                   Each test will allow parts of the Device Model to be excluded from the testing.

                   Start the tests by clicking the 'Next' button.
                   """

        try:
            self._invoke_testing_facade(question, [], test_type="action")

        except TestingFacadeException:
            # pre_test_introducton timed out
            pass

    def post_tests_message(self):
        """
        IS-12 Test Suite complete!
        """
        if not IS12_INTERACTIVE_TESTING:
            return
        # Once the tests are complete this post tests message is displayed.

        question = """\
                   IS-12 tests complete!

                   Please press the 'Next' button to exit the tests.
                   """

        try:
            self._invoke_testing_facade(question, [], test_type="action")

        except TestingFacadeException:
            # post_test_introducton timed out
            pass

    def create_ncp_socket(self, test):
        """Create a WebSocket client connection to Node under test. Raises NMOSTestException on error"""
        self.is12_utils.open_ncp_websocket(test)

    def get_property_value(self, test, oid, property_id, context):
        try:
            return self.is12_utils.get_property_value(test, oid, property_id)
        except NMOSTestException as e:
            self.device_model_metadata["error"] = True
            self.device_model_metadata["error_msg"] += context \
                + "Error getting property: " \
                + str(property_id) + ": " \
                + str(e.args[0].detail) \
                + "; "
        return None

    def _get_constraints(self, test, class_property, datatype_descriptors, object_runtime_constraints):
        datatype_constraints = None
        runtime_constraints = None
        # Level 0: Datatype constraints
        if class_property.get('typeName'):
            datatype_constraints = datatype_descriptors.get(class_property['typeName']).get('constraints')
        # Level 1: Property constraints
        property_constraints = class_property.get('constraints')
        # Level 3: Runtime constraints
        if object_runtime_constraints:
            for object_runtime_constraint in object_runtime_constraints:
                if object_runtime_constraint['propertyId']['level'] == class_property['id']['level'] and \
                        object_runtime_constraint['propertyId']['index'] == class_property['id']['index']:
                    runtime_constraints = object_runtime_constraint
        constraint_type = 'runtime' if runtime_constraints else 'property' if property_constraints else 'datatype'

        return runtime_constraints or property_constraints or datatype_constraints, constraint_type

    def _get_properties(self, test, block, get_constraints=True, get_sequences=False, get_readonly=False, context=""):
        results = []
        context += block.role

        class_manager = self.is12_utils.get_class_manager(test)

        block_member_descriptors = self.is12_utils.get_member_descriptors(test, block.oid, recurse=False)

        # Note that the userLabel of the block may also be changed, and therefore might be
        # subject to runtime constraints constraints

        for descriptor in block_member_descriptors:
            class_descriptor = self.is12_utils.get_control_class(test,
                                                                 class_manager.oid,
                                                                 descriptor['classId'],
                                                                 include_inherited=True)

            # Get runtime property constraints
            object_runtime_constraints = \
                self.is12_utils.get_property_value(test,
                                                   descriptor['oid'],
                                                   NcObjectProperties.RUNTIME_PROPERTY_CONSTRAINTS.value)

            for class_property in class_descriptor.get('properties'):
                if get_readonly != class_property['isReadOnly']:
                    continue
                if get_readonly and class_property.get('isSequence') == get_sequences:
                    results.append({'oid': descriptor['oid'],
                                    'name': context + ": " + class_descriptor['name'] + ": " + class_property['name'],
                                    'property_id': class_property['id'],
                                    'constraints': None,
                                    'constraints_type': None,
                                    'is_sequence': class_property.get('isSequence')})
                    continue

                constraints, constraints_type = self._get_constraints(test,
                                                                      class_property,
                                                                      class_manager.datatype_descriptors,
                                                                      object_runtime_constraints)
                if class_property.get('isSequence') == get_sequences and bool(constraints) == get_constraints:
                    results.append({'oid': descriptor['oid'],
                                    'name': context + ": " + class_descriptor['name'] + ": " + class_property['name'],
                                    'property_id': class_property['id'],
                                    'constraints': constraints,
                                    'constraints_type': constraints_type,
                                    'is_sequence': class_property.get('isSequence')})
        # Recurse through the child blocks
        for child_object in block.child_objects:
            if type(child_object) is NcBlock:
                results += (self._get_properties(test, child_object, get_constraints, get_sequences, get_readonly,
                                                 context + ": "))

        return results

    def _get_methods(self, test, block, context=""):
        results = []
        context += block.role

        class_manager = self.is12_utils.get_class_manager(test)

        block_member_descriptors = self.is12_utils.get_member_descriptors(test, block.oid, recurse=False)

        # We're only testing the methods from non-standard classes, as the standard methods are already tested elsewhere
        non_standard_member_descriptors = [d for d in block_member_descriptors
                                           if self.is12_utils.is_non_standard_class(d['classId'])]

        for descriptor in non_standard_member_descriptors:
            class_descriptor = self.is12_utils.get_control_class(test,
                                                                 class_manager.oid,
                                                                 descriptor['classId'],
                                                                 include_inherited=False)

            for method_descriptor in class_descriptor.get('methods'):
                results.append({'oid': descriptor['oid'],
                                'name': context + ": " + class_descriptor['name'] + ": " + method_descriptor['name'],
                                'method_id': method_descriptor['id'],
                                'result_datatype': method_descriptor['resultDatatype'],
                                'parameters': method_descriptor['parameters'],
                                'is_deprecated': method_descriptor['isDeprecated']})

        # Recurse through the child blocks
        for child_object in block.child_objects:
            if type(child_object) is NcBlock:
                results += (self._get_methods(test, child_object, context + ": "))

        return results

    def _check_constrained_parameter(self, test, constraint_type, constraint, constrained_property, value):
        def _do_check(check_function):
            try:
                check_function()
                self.constraint_error = True
                self.constraint_error_msg += \
                    constraint + " " + constraint_type + \
                    " constraint not enforced for " + constrained_property['name'] + "; "
            except NMOSTestException:
                # Expecting a parameter constraint violation
                pass

        def _do_set_sequence():
            index = self.is12_utils.get_sequence_length(test,
                                                        constrained_property['oid'],
                                                        constrained_property['property_id'])
            self.is12_utils.set_sequence_item(test,
                                              constrained_property['oid'],
                                              constrained_property['property_id'],
                                              index - 1,
                                              value)

        if constrained_property.get("is_sequence"):
            _do_check(lambda: self.is12_utils.add_sequence_item(test,
                                                                constrained_property['oid'],
                                                                constrained_property['property_id'],
                                                                value))
            _do_check(_do_set_sequence)
        else:
            _do_check(lambda: self.is12_utils.set_property(test,
                                                           constrained_property['oid'],
                                                           constrained_property['property_id'],
                                                           value))

    def _check_parameter_constraints_number(self, test, constrained_property):
        constraints = constrained_property.get('constraints')
        constraint_types = constrained_property.get('constraints_type')

        # Attempt to set to a "legal" value
        minimum = constraints.get("minimum", 0)
        maximum = constraints.get("maximum", sys.maxsize)
        step = constraints.get("step", 1)

        new_value = floor((((maximum - minimum) / 2) + minimum) / step) * step + minimum

        # Expect this to work OK
        if constrained_property.get("is_sequence"):
            index = self.is12_utils.get_sequence_length(test,
                                                        constrained_property['oid'],
                                                        constrained_property['property_id'])
            self.is12_utils.add_sequence_item(test,
                                              constrained_property['oid'],
                                              constrained_property['property_id'],
                                              new_value)
            self.is12_utils.set_sequence_item(test, constrained_property['oid'],
                                              constrained_property['property_id'],
                                              index, new_value)
        else:
            self.is12_utils.set_property(test,
                                         constrained_property['oid'],
                                         constrained_property['property_id'],
                                         new_value)

        # Attempt to set to an "illegal" value
        if constraints.get("minimum") is not None:
            self._check_constrained_parameter(test, constraint_types, "Minimum", constrained_property, minimum - step)

        if constraints.get("maximum") is not None:
            self._check_constrained_parameter(test, constraint_types, "Maximum", constrained_property, maximum + step)

        if constraints.get("step") is not None:
            self._check_constrained_parameter(test,
                                              constraint_types,
                                              "Step",
                                              constrained_property,
                                              new_value + step / 2)

        if constrained_property.get("is_sequence"):
            self.is12_utils.remove_sequence_item(test,
                                                 constrained_property['oid'],
                                                 constrained_property['property_id'],
                                                 index)

    def _check_parameter_constraints_string(self, test, constrained_property):
        constraints = constrained_property["constraints"]
        constraints_type = constrained_property["constraints_type"]
        new_value = "test"

        if constraints.get("pattern"):
            # Check legal case
            x = Xeger(limit=constraints.get("max_characters", 0) - len(constraints.get("pattern"))
                      if constraints.get("max_characters", 0) > len(constraints.get("pattern")) else 1)
            new_value = x.xeger(constraints.get("pattern"))

        # Expect this to work OK
        if constrained_property.get("is_sequence"):
            index = self.is12_utils.get_sequence_length(test,
                                                        constrained_property['oid'],
                                                        constrained_property['property_id'])
            self.is12_utils.add_sequence_item(test,
                                              constrained_property['oid'],
                                              constrained_property['property_id'],
                                              new_value)
            self.is12_utils.set_sequence_item(test,
                                              constrained_property['oid'],
                                              constrained_property['property_id'],
                                              index,
                                              new_value)
        else:
            self.is12_utils.set_property(test,
                                         constrained_property['oid'],
                                         constrained_property['property_id'],
                                         new_value)

        if constraints.get("pattern"):
            # Possible negative example strings
            # Ideally we would compute a negative string based on the regex.
            # In the meantime, some strings that might possibly violate the regex
            negative_examples = ['!$%^&*()+_:;/', '*********', '000000000', 'AAAAAAAA']

            for negative_example in negative_examples:
                # Verify this string violates constraint
                if not re.search(constraints.get("pattern"), negative_example):
                    self._check_constrained_parameter(test,
                                                      constraints_type,
                                                      "Pattern",
                                                      constrained_property,
                                                      negative_example)

        # Exceed max character limit
        if constraints.get("max_characters"):
            if constraints.get("pattern"):
                x = Xeger(limit=constraints.get("max_characters") * 2)
                new_value = x.xeger(constraints.get("pattern"))
            else:
                new_value = '*' * constraints.get("max_characters") * 2

            # Verfiy this string violates constraint
            if len(new_value) > constraints.get("max_characters"):
                self._check_constrained_parameter(test,
                                                  constraints_type,
                                                  "Max characters",
                                                  constrained_property,
                                                  new_value)

        # Remove added sequence item
        if constrained_property.get("is_sequence"):
            self.is12_utils.remove_sequence_item(test,
                                                 constrained_property['oid'],
                                                 constrained_property['property_id'],
                                                 index)

    def _do_check_property_test(self, test, question, get_constraints=False, get_sequences=False):
        """Test properties within the Device Model"""
        device_model = self.is12_utils.query_device_model(test)

        constrained_properties = self._get_properties(test, device_model, get_constraints, get_sequences)

        possible_properties = [{'answer_id': 'answer_'+str(i),
                                'display_answer': p['name'],
                                'resource': p} for i, p in enumerate(constrained_properties)]

        if len(possible_properties) == 0:
            return test.UNCLEAR("No testable properties in Device Model.")

        if IS12_INTERACTIVE_TESTING:
            selected_ids = \
                self._invoke_testing_facade(question, possible_properties, test_type="multi_choice")['answer_response']

            selected_properties = [p["resource"] for p in possible_properties if p['answer_id'] in selected_ids]

            if len(selected_properties) == 0:
                return test.UNCLEAR("No properties selected for testing.")
        else:
            # If non-interactive then test all methods
            selected_properties = [p["resource"] for p in possible_properties]

        self.constraint_error = False
        self.constraint_error_msg = ""

        for constrained_property in selected_properties:

            # Cache original property value
            try:
                constraint = constrained_property.get('constraints')

                original_value = self.is12_utils.get_property_value(test,
                                                                    constrained_property['oid'],
                                                                    constrained_property['property_id'])

            except NMOSTestException as e:
                return test.FAIL(constrained_property.get("name")
                                 + ": error getting property: "
                                 + str(e.args[0].detail)
                                 + ": constraint " + str(constraint))

            try:
                if constraint.get('minimum') or constraint.get('maximum') or constraint.get('step'):
                    self._check_parameter_constraints_number(test, constrained_property)

                if constraint.get('maxCharacters') or constraint.get('pattern'):
                    self._check_parameter_constraints_string(test, constrained_property)

            except NMOSTestException as e:
                return test.FAIL(constrained_property.get("name")
                                 + ": error setting property: "
                                 + str(e.args[0].detail),
                                 + ": constraint " + str(constraint))

            try:
                # Reset to original value
                self.is12_utils.set_property(test,
                                             constrained_property['oid'],
                                             constrained_property['property_id'],
                                             original_value)
            except NMOSTestException as e:
                return test.FAIL(constrained_property.get("name")
                                 + ": error restoring original value of property: "
                                 + str(e.args[0].detail)
                                 + " original value: " + str(original_value)
                                 + ": constraint " + str(constraint))

        if self.constraint_error:
            return test.FAIL(self.constraint_error_msg)

        return test.PASS()

    def _resolve_is_sequence(self, test, datatype):
        if datatype is None:
            return False

        class_manager = self.is12_utils.get_class_manager(test)

        parentType = class_manager.datatype_descriptors[datatype].get("parentType")

        if parentType and class_manager.datatype_descriptors[parentType].get('type') == NcDatatypeType.Primitive:
            return class_manager.datatype_descriptors[datatype]['isSequence']

        return self._resolve_is_sequence(test, parentType)

    def _generate_number_parameter(self, constraints):
        if [constraints[key] for key in constraints if key in ['minimum', 'maximum', 'step']]:
            minimum = constraints.get("minimum", 0)
            maximum = constraints.get("maximum", sys.maxsize)
            step = constraints.get("step", 1)

            return floor((((maximum - minimum) / 2) + minimum) / step) * step + minimum
        return None

    def _generate_string_parameter(self, constraints):
        if constraints.get("pattern"):
            # Check legal case
            x = Xeger(limit=constraints.get("max_characters", 0) - len(constraints.get("pattern"))
                      if constraints.get("max_characters", 0) > len(constraints.get("pattern")) else 1)
            return x.xeger(constraints.get("pattern"))
        return ""

    def _generate_primitive_parameter(self, datatype):
        type_mapping = {
            "NcBoolean": False,
            "NcInt16": 0,
            "NcInt32": 0,
            "NcInt64": 0,
            "NcUint16": 0,
            "NcUint32": 0,
            "NcUint64": 0,
            "NcFloat32": 0.0,
            "NcFloat64":  0.0,
            "NcString": ""
        }

        return type_mapping.get(datatype)

    def _create_compatible_parameter(self, test, parameter_descriptor):
        parameter = None

        # if there are constraints use them
        if parameter_descriptor.get('constraints'):
            constraints = parameter_descriptor['constraints']
            # either there is a default value, or this is a number constraint, or this is a string
            if constraints.get('defaultValue') is not None:
                return constraints.get('defaultValue')
            elif self._generate_number_parameter(constraints) is not None:
                return self._generate_number_parameter(constraints)
            else:
                return self._generate_string_parameter(constraints)
        else:
            # resolve the datatype to either a struct, enum or primative
            datatype = self.is12_utils.resolve_datatype(test, parameter_descriptor['typeName'])

            class_manager = self.is12_utils.get_class_manager(test)

            datatype_descriptor = class_manager.datatype_descriptors[datatype]

            if datatype_descriptor['type'] == NcDatatypeType.Enum:
                parameter = datatype_descriptor['items'][0]['value']
            elif datatype_descriptor['type'] == NcDatatypeType.Primitive:
                parameter = self._generate_primitive_parameter(datatype)
            elif datatype_descriptor['type'] == NcDatatypeType.Struct:
                parameter = self._create_compatible_parameters(test, datatype_descriptor['fields'])

        return [parameter] if self._resolve_is_sequence(test, parameter_descriptor['typeName']) else parameter

    def _create_compatible_parameters(self, test, parameters):
        result = {}

        for parameter in parameters:
            result[parameter['name']] = self._create_compatible_parameter(test, parameter)

        return result

    def test_01(self, test):
        """Constraints on writable properties are enforced"""

        question = """\
                    From this list of properties with parameter constraints\
                    carefully select those that can be safely altered by this test.

                    Note that this test will attempt to restore the original state of the Device Model.

                    Once you have made you selection please press the 'Submit' button.
                    """
        return self._do_check_property_test(test, question, get_constraints=True, get_sequences=False)

    def test_02(self, test):
        """Constraints on writable sequences are enforced"""
        question = """\
                   From this list of sequences with parameter constraints\
                   carefully select those that can be safely altered by this test.

                   Note that this test will attempt to restore the original state of the Device Model.

                   Once you have made you selection please press the 'Submit' button.
                   """

        return self._do_check_property_test(test, question, get_constraints=True, get_sequences=True)

    def _do_check_readonly_properties(self, test, question, get_sequences=False):
        device_model = self.is12_utils.query_device_model(test)

        readonly_properties = self._get_properties(test, device_model, get_constraints=False,
                                                   get_sequences=get_sequences, get_readonly=True)

        possible_properties = [{'answer_id': 'answer_'+str(i),
                                'display_answer': p['name'],
                                'resource': p} for i, p in enumerate(readonly_properties)]

        if len(possible_properties) == 0:
            return test.UNCLEAR("No testable properties in Device Model.")

        if IS12_INTERACTIVE_TESTING:
            selected_ids = \
                self._invoke_testing_facade(question, possible_properties, test_type="multi_choice")['answer_response']

            selected_properties = [p["resource"] for p in possible_properties if p['answer_id'] in selected_ids]

            if len(selected_properties) == 0:
                return test.UNCLEAR("No properties selected for testing.")
        else:
            # If non-interactive then test all methods
            selected_properties = [p["resource"] for p in possible_properties]

        readonly_checked = False

        for readonly_property in selected_properties:

            # Cache original property value
            try:
                original_value = self.is12_utils.get_property_value(test,
                                                                    readonly_property['oid'],
                                                                    readonly_property['property_id'])

            except NMOSTestException as e:
                return test.FAIL(readonly_property.get("name")
                                 + ": error getting property: "
                                 + str(e.args[0].detail))

            try:
                # Try setting this value
                self.is12_utils.set_property(test,
                                             readonly_property['oid'],
                                             readonly_property['property_id'],
                                             original_value)
                # if it gets this far it's failed
                return test.FAIL(readonly_property.get("name")
                                 + ": read only property is writable")
            except NMOSTestException:
                # expect an exception to be thrown
                readonly_checked = True

        if not readonly_checked:
            return test.UNCLEAR("No read only properties found")

        return test.PASS()

    def test_03(self, test):
        """Check read only properties are not writable"""

        question = """\
                   From this list of read only properties\
                   carefully select those that can be safely altered by this test.

                   Note that this test will attempt to restore the original state of the Device Model.

                   Once you have made you selection please press the 'Submit' button.
                   """

        return self._do_check_readonly_properties(test, question, get_sequences=False)

    def test_04(self, test):
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
        device_model = self.is12_utils.query_device_model(test)

        methods = self._get_methods(test, device_model)

        possible_methods = [{'answer_id': 'answer_'+str(i),
                             'display_answer': p['name'],
                             'resource': p} for i, p in enumerate(methods)]

        if len(possible_methods) == 0:
            return test.UNCLEAR("No non standard methods in Device Model.")

        if IS12_INTERACTIVE_TESTING:
            selected_ids = \
                self._invoke_testing_facade(question, possible_methods, test_type="multi_choice")['answer_response']

            selected_methods = [p["resource"] for p in possible_methods if p['answer_id'] in selected_ids]

            if len(selected_methods) == 0:
                return test.UNCLEAR("No methods selected for testing.")
        else:
            # If non-interactive then test all methods
            selected_methods = [p["resource"] for p in possible_methods]

        self.invoke_methods_metadata['error'] = False
        self.invoke_methods_metadata['error_msg'] = ""

        for method in selected_methods:
            try:
                parameters = self._create_compatible_parameters(test, method['parameters'])

                result = self.is12_utils.execute_command(test, method['oid'], method['method_id'], parameters)

                # check for deprecated status codes for deprecated methods
                if method['is_deprecated'] and result['status'] != 299:
                    self.invoke_methods_metadata['error'] = True
                    self.invoke_methods_metadata['error_msg'] += """
                        Deprecated method returned incorrect status code {} : {};
                        """.format(method.get("name"), result.status)
            except NMOSTestException as e:
                # ignore 4xx errors
                if e.args[0].detail['status'] >= 500:
                    self.invoke_methods_metadata['error'] = True
                    self.invoke_methods_metadata['error_msg'] += """
                        Error invoking method {} : {};
                        """.format(method.get("name"), e.args[0].detail)

        if self.invoke_methods_metadata['error']:
            return test.FAIL(self.invoke_methods_metadata['error_msg'])

        return test.PASS()

    def test_05(self, test):
        """Check discovered methods"""
        question = """\
                   From this list of methods\
                   carefully select those that can be safely invoked by this test.

                   Note that this test will NOT attempt to restore the original state of the Device Model.

                   Once you have made you selection please press the 'Submit' button.
                   """

        return self._do_check_methods_test(test, question)

    def check_add_sequence_item(self, test, oid, property_id, property_name, sequence_length, context=""):
        try:
            self.add_sequence_item_metadata["checked"] = True
            # Add a value to the end of the sequence
            new_item = self.is12_utils.get_sequence_item(test, oid, property_id, index=0)

            self.is12_utils.add_sequence_item(test, oid, property_id, new_item)

            # check the value
            value = self.is12_utils.get_sequence_item(test, oid, property_id, index=sequence_length)
            if value != new_item:
                self.add_sequence_item_metadata["error"] = True
                self.add_sequence_item_metadata["error_msg"] += \
                    context + property_name \
                    + ": Expected: " + str(new_item) + ", Actual: " + str(value) + ", "
            return True
        except NMOSTestException as e:
            self.add_sequence_item_metadata["error"] = True
            self.add_sequence_item_metadata["error_msg"] += \
                context + property_name + ": " + str(e.args[0].detail) + ", "
        return False

    def check_set_sequence_item(self, test, oid, property_id, property_name, sequence_length, context=""):
        try:
            self.set_sequence_item_metadata["checked"] = True
            new_value = self.is12_utils.get_sequence_item(test, oid, property_id, index=sequence_length - 1)

            # set to another value
            self.is12_utils.set_sequence_item(test, oid, property_id, index=sequence_length, value=new_value)

            # check the value
            value = self.is12_utils.get_sequence_item(test, oid, property_id, index=sequence_length)
            if value != new_value:
                self.set_sequence_item_metadata["error"] = True
                self.set_sequence_item_metadata["error_msg"] += \
                    context + property_name \
                    + ": Expected: " + str(new_value) + ", Actual: " + str(value) + ", "
            return True
        except NMOSTestException as e:
            self.set_sequence_item_metadata["error"] = True
            self.set_sequence_item_metadata["error_msg"] += \
                context + property_name + ": " + str(e.args[0].detail) + ", "
        return False

    def check_remove_sequence_item(self, test, oid, property_id, property_name, sequence_length, context=""):
        try:
            # remove item
            self.remove_sequence_item_metadata["checked"] = True
            self.is12_utils.remove_sequence_item(test, oid, property_id, index=sequence_length)
            return True
        except NMOSTestException as e:
            self.remove_sequence_item_metadata["error"] = True
            self.remove_sequence_item_metadata["error_msg"] += \
                context + property_name + ": " + str(e.args[0].detail) + ", "
        return False

    def check_sequence_methods(self, test, oid, property_id, property_name, context=""):
        """Check that sequence manipulation methods work correctly"""
        response = self.is12_utils.get_property_value(test, oid, property_id)

        if response is None or not isinstance(response, list) or len(response) == 0:
            # Hmmm, these tests depend on sequences already having some data in them.
            # This is so it can copy sequence items for add and set operations
            # without having to generate any new data. It would be better to synthesise
            # valid data to use in these tests
            return

        sequence_length = len(response)

        if not self.check_add_sequence_item(test, oid, property_id, property_name, sequence_length, context=context):
            return
        if sequence_length + 1 != self.is12_utils.get_sequence_length(test, oid, property_id):
            self.add_sequence_item_metadata["error"] = True
            self.add_sequence_item_metadata["error_msg"] = property_name + \
                ": add_sequence_item resulted in unexpected sequence length."
        self.check_set_sequence_item(test, oid, property_id, property_name, sequence_length, context=context)
        if sequence_length + 1 != self.is12_utils.get_sequence_length(test, oid, property_id):
            self.set_sequence_item_metadata["error"] = True
            self.set_sequence_item_metadata["error_msg"] = property_name + \
                ": set_sequence_item resulted in unexpected sequence length."
        self.check_remove_sequence_item(test, oid, property_id, property_name, sequence_length, context)
        if sequence_length != self.is12_utils.get_sequence_length(test, oid, property_id):
            self.remove_sequence_item_metadata["error"] = True
            self.remove_sequence_item_metadata["error_msg"] = property_name + \
                ": remove_sequence_item resulted in unexpected sequence length."

    def validate_sequences(self, test):
        """Test all writable sequences"""
        device_model = self.is12_utils.query_device_model(test)

        constrained_properties = self._get_properties(test, device_model, get_constraints=False, get_sequences=True)

        possible_properties = [{'answer_id': 'answer_'+str(i),
                                'display_answer': p['name'],
                                'resource': p} for i, p in enumerate(constrained_properties)]

        if len(possible_properties) == 0:
            return test.UNCLEAR("No properties with ParameterConstraints in Device Model.")

        if IS12_INTERACTIVE_TESTING:
            question = """\
                        From this list of sequences\
                        carefully select those that can be safely altered by this test.

                        Once you have made you selection please press the 'Submit' button.
                        """

            selected_ids = \
                self._invoke_testing_facade(question, possible_properties, test_type="multi_choice")['answer_response']

            selected_properties = [p["resource"] for p in possible_properties if p['answer_id'] in selected_ids]

            if len(selected_properties) == 0:
                # No properties selected so can't do the test
                self.sequence_test_unclear = True
        else:
            # If non interactive test all properties
            selected_properties = [p["resource"] for p in possible_properties]

        for constrained_property in selected_properties:
            self.check_sequence_methods(test,
                                        constrained_property['oid'],
                                        constrained_property['property_id'],
                                        constrained_property['name'])

        self.sequences_validated = True

    def test_06(self, test):
        """NcObject method: SetSequenceItem"""
        try:
            if not self.sequences_validated:
                self.validate_sequences(test)
        except NMOSTestException as e:
            # Couldn't validate model so can't perform test
            return test.UNCLEAR(e.args[0].detail, e.args[0].link)

        if self.sequence_test_unclear:
            return test.UNCLEAR("No sequences selected for testing.")

        if self.set_sequence_item_metadata["error"]:
            return test.FAIL(self.set_sequence_item_metadata["error_msg"])

        if not self.set_sequence_item_metadata["checked"]:
            return test.UNCLEAR("SetSequenceItem not tested.")

        return test.PASS()

    def test_07(self, test):
        """NcObject method: AddSequenceItem"""
        try:
            if not self.sequences_validated:
                self.validate_sequences(test)
        except NMOSTestException as e:
            # Couldn't validate model so can't perform test
            return test.UNCLEAR(e.args[0].detail, e.args[0].link)

        if self.sequence_test_unclear:
            return test.UNCLEAR("No sequences selected for testing.")

        if self.add_sequence_item_metadata["error"]:
            return test.FAIL(self.add_sequence_item_metadata["error_msg"])

        if not self.add_sequence_item_metadata["checked"]:
            return test.UNCLEAR("AddSequenceItem not tested.")

        return test.PASS()

    def test_08(self, test):
        """NcObject method: RemoveSequenceItem"""
        try:
            if not self.sequences_validated:
                self.validate_sequences(test)
        except NMOSTestException as e:
            # Couldn't validate model so can't perform test
            return test.UNCLEAR(e.args[0].detail, e.args[0].link)

        if self.sequence_test_unclear:
            return test.UNCLEAR("No sequences selected for testing.")

        if self.remove_sequence_item_metadata["error"]:
            return test.FAIL(self.remove_sequence_item_metadata["error_msg"])

        if not self.remove_sequence_item_metadata["checked"]:
            return test.UNCLEAR("RemoveSequenceItem not tested.")

        return test.PASS()
