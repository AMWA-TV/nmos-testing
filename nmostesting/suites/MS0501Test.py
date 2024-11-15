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

from itertools import product

from ..GenericTest import GenericTest, NMOSTestException
from ..MS05Utils import MS05Utils, NcBlock, NcBlockProperties, NcDatatypeDescriptorStruct, \
    NcDeviceManagerProperties, NcMethodResultError, NcMethodStatus, NcObjectProperties, NcParameterConstraintsNumber, \
    NcParameterConstraintsString, NcPropertyConstraintsNumber, NcPropertyConstraintsString, NcTouchpoint, \
    NcTouchpointNmos, NcTouchpointNmosChannelMapping, StandardClassIds
from ..TestResult import Test

# Note: this test suite is a base class for the IS1201Test and IS1401Test test suites
# where there are common MS-05 tests.  Therefore this test suite is not configured and
# instantiated in the same way as the other test suites.

NODE_API_KEY = "node"
MS05_API_KEY = "controlframework"


class MS0501Test(GenericTest):
    """
    Runs Tests covering MS-05
    """
    class TestMetadata():
        def __init__(self, checked=False, error=False, error_msg="", unclear=False):
            self.checked = checked
            self.error = error
            self.error_msg = error_msg

    def __init__(self, apis, utils, **kwargs):
        # Remove the RAML key to prevent this test suite from auto-testing IS-04 API
        apis[NODE_API_KEY].pop("raml", None)
        GenericTest.__init__(self, apis, **kwargs)
        self.ms05_utils = utils

    def set_up_tests(self):
        super().set_up_tests()
        self.ms05_utils.reset()
        # check_device_model validates that device model is correct according to specification
        self.device_model_metadata = MS0501Test.TestMetadata()
        # checked in check_device_model, reported in test_ms05_03
        self.unique_roles_metadata = MS0501Test.TestMetadata()
        # checked in check_device_model, reported in test_ms05_04
        self.unique_oids_metadata = MS0501Test.TestMetadata()
        # checked in check_device_model, reported in test_ms05_05
        self.organization_metadata = MS0501Test.TestMetadata()
        # checked in check_device_model, reported in test_ms05_06
        self.touchpoints_metadata = MS0501Test.TestMetadata()
        # checked in check_device_model, reported in test_ms05_07
        self.deprecated_property_metadata = MS0501Test.TestMetadata()
        # checked in check_device_model, reported in test_ms05_08
        self.managers_members_root_block_metadata = MS0501Test.TestMetadata()
        # checked in check_device_model, reported in test_ms05_09
        self.managers_are_singletons_metadata = MS0501Test.TestMetadata()
        # checked in check_device_model, reported in test_ms05_15
        self.get_sequence_item_metadata = MS0501Test.TestMetadata()
        # checked in check_device_model, reported in test_ms05_16
        self.get_sequence_length_metadata = MS0501Test.TestMetadata()

        self.oid_cache = []

    # Override basics to include the MS-05 auto tests
    def basics(self):
        results = super().basics()
        try:
            results += self._auto_tests()
        except NMOSTestException as e:
            results.append(e.args[0])
        except Exception as e:
            results.append(self.uncaught_exception("auto_tests", e))
        return results

    def _validate_model_definitions(self, descriptors, reference_descriptors):
        # Validate Class Manager model definitions against reference model descriptors.
        # Returns [test result array]
        results = list()

        reference_descriptor_keys = sorted(reference_descriptors.keys())

        for key in reference_descriptor_keys:
            test = Test(f"Validate {str(key)} definition", f"auto_ms05_{str(key)}")
            try:
                if descriptors.get(key):
                    descriptor = descriptors[key]

                    # Validate descriptor obeys the JSON schema
                    self.ms05_utils.reference_datatype_schema_validate(test, descriptor.json,
                                                                       descriptor.__class__.__name__)

                    # Validate the content of descriptor is correct
                    self.ms05_utils.validate_descriptor(test, reference_descriptors[key], descriptor)

                    results.append(test.PASS())
                else:
                    results.append(test.UNCLEAR("Not Implemented"))
            except NMOSTestException as e:
                results.append(e.args[0])

        return results

    def _auto_tests(self):
        # Automatically validate all standard datatypes and control classes.
        # Returns [test result array]
        # https://specs.amwa.tv/ms-05-02/releases/v1.0.0/docs/Framework.html

        results = list()
        test = Test("Initialize auto tests", "auto_init")

        class_manager = self.ms05_utils.get_class_manager(test)

        results += self._validate_model_definitions(class_manager.class_descriptors,
                                                    self.ms05_utils.reference_class_descriptors)

        results += self._validate_model_definitions(class_manager.datatype_descriptors,
                                                    self.ms05_utils.reference_datatype_descriptors)
        return results

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

    def check_get_sequence_item(self, test, oid, role_path, sequence_values, property_descriptor):
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

    def check_get_sequence_length(self, test, oid, role_path, sequence_values, property_descriptor):
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

    def check_sequence_methods(self, test, oid, role_path, sequence_values, property_descriptor):
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
            self.check_get_sequence_item(test, oid, role_path, sequence_values, property_descriptor)
            self.check_get_sequence_length(test, oid, role_path, sequence_values, property_descriptor)

    def check_object_properties(self, test, reference_class_descriptor, oid, role_path):
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
                self.check_sequence_methods(test,
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

    def check_unique_roles(self, role, role_cache, role_path):
        """Check role is unique within containing Block"""
        if role in role_cache:
            error_msg_base = f"role path={self.ms05_utils.create_role_path_string(role_path)}: "
            self.unique_roles_metadata.error = True
            self.unique_roles_metadata.error_msg += f"{error_msg_base}Multiple objects use role={role}; "
        else:
            self.unique_roles_metadata.checked = True
            role_cache.append(role)

    def check_unique_oid(self, oid, role_path):
        """Check oid is globally unique"""
        if oid in self.oid_cache:
            error_msg_base = f"role path={self.ms05_utils.create_role_path_string(role_path)}: "
            self.unique_oids_metadata.error = True
            self.unique_oids_metadata.error_msg = f"{error_msg_base}Multiple objects use OID={oid}; "
        else:
            self.unique_oids_metadata.checked = True
            self.oid_cache.append(oid)

    def check_manager(self, class_id, owner, class_descriptors, manager_cache, role_path):
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

    def check_touchpoints(self, test, oid, role_path):
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

    def check_block(self, test, block, class_descriptors):
        for child_object in block.child_objects:
            # If this child object is a Block, recurse
            if type(child_object) is NcBlock:
                self.check_block(test,
                                 child_object,
                                 class_descriptors)
        role_cache = []
        manager_cache = []
        for child_object in block.child_objects:
            descriptor = child_object.member_descriptor
            role_path = self.ms05_utils.create_role_path(block.role_path, descriptor.role)

            self.check_unique_roles(descriptor.role, role_cache, block.role_path)
            self.check_unique_oid(descriptor.oid, block.role_path)
            # check for non-standard classes
            if self.ms05_utils.is_non_standard_class(descriptor.classId):
                self.organization_metadata.checked = True
            self.check_manager(descriptor.classId, descriptor.owner, class_descriptors, manager_cache, role_path)
            self.check_touchpoints(test, descriptor.oid, role_path)

            class_identifier = self.ms05_utils.create_class_id_string(descriptor.classId)
            if class_identifier and class_identifier in class_descriptors:
                self.check_object_properties(test,
                                             class_descriptors[class_identifier],
                                             descriptor.oid,
                                             role_path)
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
                    f"class id={class_identifier}" \
                    f"Non-standard class id does not contain authority key: {class_identifier}; "

    def check_device_model(self, test):
        if not self.device_model_metadata.checked:
            class_manager = self.ms05_utils.get_class_manager(test)
            device_model = self.ms05_utils.query_device_model(test)

            self.check_block(test,
                             device_model,
                             class_manager.class_descriptors)

            self.device_model_metadata.checked = True
        return

    def test_ms05_02(self, test):
        """Device Model: Device Model is correct according to classes and datatypes advertised by Class Manager"""
        # https://specs.amwa.tv/ms-05-02/releases/v1.0.0/docs/Managers.html
        # https://specs.amwa.tv/ms-05-02/releases/v1.0.0/docs/Workers.html

        self.check_device_model(test)

        if self.device_model_metadata.error:
            return test.FAIL(self.device_model_metadata.error_msg)

        if not self.device_model_metadata.checked:
            return test.UNCLEAR("Unable to check Device Model.")

        return test.PASS()

    def test_ms05_03(self, test):
        """Device Model: roles are unique within a containing Block"""
        # https://specs.amwa.tv/ms-05-02/releases/v1.0.0/docs/NcObject.html

        try:
            self.check_device_model(test)
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
            self.check_device_model(test)
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
            self.check_device_model(test)
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
            self.check_device_model(test)
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
            self.check_device_model(test)
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
        """Managers: managers are members of the Root Block"""
        # All managers MUST always exist as members in the Root Block and have a fixed role.
        # https://specs.amwa.tv/ms-05-02/releases/v1.0.0/docs/Managers.html

        try:
            self.check_device_model(test)
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

    def test_ms05_09(self, test):
        """Managers: managers are singletons"""
        # Managers are singleton (MUST only be instantiated once) classes.
        # https://specs.amwa.tv/ms-05-02/releases/v1.0.0/docs/Managers.html

        try:
            self.check_device_model(test)
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

    def test_ms05_10(self, test):
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

    def test_ms05_11(self, test):
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

    def test_ms05_12(self, test):
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

    def test_ms05_13(self, test):
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

    def test_ms05_14(self, test):
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

    def test_ms05_15(self, test):
        """NcObject: GetSequenceItem method is correct"""
        # Where the functionality of a device uses control classes and datatypes listed in this
        # specification it MUST comply with the model definitions published
        # https://specs.amwa.tv/ms-05-02/releases/v1.0.0/docs/Framework.html#ncobject

        try:
            self.check_device_model(test)
        except NMOSTestException as e:
            # Couldn't validate model so can't perform test
            return test.FAIL(e.args[0].detail, e.args[0].link)

        if self.get_sequence_item_metadata.error:
            return test.FAIL(self.get_sequence_item_metadata.error_msg)

        if not self.get_sequence_item_metadata.checked:
            return test.UNCLEAR("GetSequenceItem not tested.")

        return test.PASS()

    def test_ms05_16(self, test):
        """NcObject: GetSequenceLength method is correct"""
        # Where the functionality of a device uses control classes and datatypes listed in this
        # specification it MUST comply with the model definitions published
        # https://specs.amwa.tv/ms-05-02/releases/v1.0.0/docs/Framework.html#ncobject

        try:
            self.check_device_model(test)
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

    def do_get_member_descriptors_test(self, test, block):
        # Recurse through the child blocks
        for child_object in block.child_objects:
            if type(child_object) is NcBlock:
                self.do_get_member_descriptors_test(test, child_object)

        search_conditions = [{"recurse": True}, {"recurse": False}]

        for search_condition in search_conditions:
            expected_members = block.get_member_descriptors(search_condition["recurse"])

            method_result = self.ms05_utils.get_member_descriptors(test, search_condition["recurse"],
                                                                   oid=block.oid, role_path=block.role_path)
            self._check_member_descriptors(test, expected_members, method_result, block.role_path,
                                           search_condition=search_condition)

    def test_ms05_17(self, test):
        """NcBlock: GetMemberDescriptors method is correct"""
        # Where the functionality of a device uses control classes and datatypes listed in this
        # specification it MUST comply with the model definitions published
        # https://specs.amwa.tv/ms-05-02/releases/v1.0.0/docs/Framework.html#ncblock

        device_model = self.ms05_utils.query_device_model(test)

        self.do_get_member_descriptors_test(test, device_model)

        return test.PASS()

    def do_find_member_by_path_test(self, test, block):
        # Recurse through the child blocks
        for child_object in block.child_objects:
            if type(child_object) is NcBlock:
                self.do_find_member_by_path_test(test, child_object)

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

    def test_ms05_18(self, test):
        """NcBlock: FindMemberByPath method is correct"""
        # Where the functionality of a device uses control classes and datatypes listed in this
        # specification it MUST comply with the model definitions published
        # https://specs.amwa.tv/ms-05-02/releases/v1.0.0/docs/Framework.html#ncblock

        device_model = self.ms05_utils.query_device_model(test)

        # Recursively check each block in Device Model
        self.do_find_member_by_path_test(test, device_model)

        return test.PASS()

    def do_find_member_by_role_test(self, test, block):
        # Recurse through the child blocks
        for child_object in block.child_objects:
            if type(child_object) is NcBlock:
                self.do_find_member_by_role_test(test, child_object)

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

    def test_ms05_19(self, test):
        """NcBlock: FindMembersByRole method is correct"""
        # Where the functionality of a device uses control classes and datatypes listed in this
        # specification it MUST comply with the model definitions published
        # https://specs.amwa.tv/ms-05-02/releases/v1.0.0/docs/Framework.html#ncblock

        device_model = self.ms05_utils.query_device_model(test)

        # Recursively check each block in Device Model
        self.do_find_member_by_role_test(test, device_model)

        return test.PASS()

    def do_find_members_by_class_id_test(self, test, block):
        # Recurse through the child blocks
        for child_object in block.child_objects:
            if type(child_object) is NcBlock:
                self.do_find_members_by_class_id_test(test, child_object)

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

    def test_ms05_20(self, test):
        """NcBlock: FindMembersByClassId method is correct"""
        # Where the functionality of a device uses control classes and datatypes listed in this
        # specification it MUST comply with the model definitions published
        # https://specs.amwa.tv/ms-05-02/releases/v1.0.0/docs/Framework.html#ncblock

        device_model = self.ms05_utils.query_device_model(test)

        self.do_find_members_by_class_id_test(test, device_model)

        return test.PASS()

    def check_constraint(self, test, constraint, descriptor, test_metadata, role_path):
        error_msg_base = f"role path={self.ms05_utils.create_role_path_string(role_path)}: " \
            f"name={descriptor.name}: datatype={descriptor.typeName}: "
        if constraint.defaultValue:
            if isinstance(constraint.defaultValue, list) is not descriptor.isSequence:
                self.test_metadata.error = True
                message = "Default value sequence was expected " \
                    if descriptor.isSequence else "Unexpected default value sequence. "
                self.test_metadata.error_msg = f"{error_msg_base}{message}; "
                return
            if descriptor.isSequence:
                for value in constraint.defaultValue:
                    self.ms05_utils.queried_datatype_schema_validate(test, value, descriptor.typeName,
                                                                     role_path=role_path)
            else:
                self.ms05_utils.queried_datatype_schema_validate(test, constraint.defaultValue, descriptor.typeName,
                                                                 role_path=role_path)

        datatype = self.ms05_utils.resolve_datatype(test, descriptor.typeName)
        if isinstance(constraint, (NcParameterConstraintsNumber, NcPropertyConstraintsNumber)):
            if datatype not in ["NcInt16", "NcInt32", "NcInt64", "NcUint16", "NcUint32",
                                "NcUint64", "NcFloat32", "NcFloat64"]:
                test_metadata.error = True
                test_metadata.error_msg = f"{error_msg_base}{datatype} " \
                    f"can not be constrainted by {constraint.__class__.__name__}; "
        if isinstance(constraint, (NcParameterConstraintsString, NcPropertyConstraintsString)):
            if datatype not in ["NcString"]:
                test_metadata.error = True
                test_metadata.error_msg = f"{error_msg_base}{datatype} " \
                    f"can not be constrainted by {constraint.__class__.__name__}; "

    def do_validate_runtime_constraints_test(self, test, nc_object, class_manager, test_metadata, context=""):
        if nc_object.runtime_constraints:
            for constraint in nc_object.runtime_constraints:
                class_descriptor = class_manager.get_control_class(nc_object.class_id)
                if class_descriptor:
                    for property_descriptor in class_descriptor.properties:
                        if property_descriptor.id == constraint.propertyId:
                            test_metadata.checked = True
                            self.check_constraint(test,
                                                  constraint,
                                                  property_descriptor,
                                                  test_metadata,
                                                  nc_object.role_path)

        # Recurse through the child blocks
        if type(nc_object) is NcBlock:
            for child_object in nc_object.child_objects:
                self.do_validate_runtime_constraints_test(test,
                                                          child_object,
                                                          class_manager,
                                                          test_metadata,
                                                          f"{context}{nc_object.role}: ")

    def test_ms05_21(self, test):
        """Constraints: validate runtime constraints"""

        device_model = self.ms05_utils.query_device_model(test)
        class_manager = self.ms05_utils.get_class_manager(test)

        test_metadata = MS0501Test.TestMetadata()

        self.do_validate_runtime_constraints_test(test, device_model, class_manager, test_metadata)

        if test_metadata.error:
            return test.FAIL(test_metadata.error_msg,
                             "https://specs.amwa.tv/ms-05-02/branches/"
                             f"{self.apis[MS05_API_KEY]['spec_branch']}"
                             "/docs/Constraints.html")

        if not test_metadata.checked:
            return test.UNCLEAR("No runtime constraints found.")

        return test.PASS()

    def do_validate_property_constraints_test(self, test, nc_object, class_manager, test_metadata):
        class_descriptor = class_manager.get_control_class(nc_object.class_id)

        if class_descriptor:
            for property_descriptor in class_descriptor.properties:
                if property_descriptor.constraints:
                    test_metadata.checked = True
                    self.check_constraint(test,
                                          property_descriptor.constraints,
                                          property_descriptor,
                                          test_metadata,
                                          nc_object.role_path)
        # Recurse through the child blocks
        if type(nc_object) is NcBlock:
            for child_object in nc_object.child_objects:
                self.do_validate_property_constraints_test(test,
                                                           child_object,
                                                           class_manager,
                                                           test_metadata)

    def test_ms05_22(self, test):
        """Constraints: validate property constraints"""

        device_model = self.ms05_utils.query_device_model(test)
        class_manager = self.ms05_utils.get_class_manager(test)

        test_metadata = MS0501Test.TestMetadata()
        self.do_validate_property_constraints_test(test, device_model, class_manager, test_metadata)

        if test_metadata.error:
            return test.FAIL(test_metadata.error_msg,
                             "https://specs.amwa.tv/ms-05-02/branches/"
                             f"{self.apis[MS05_API_KEY]['spec_branch']}"
                             "/docs/Constraints.html")

        if not test_metadata.checked:
            return test.UNCLEAR("No property constraints found.")

        return test.PASS()

    def do_validate_datatype_constraints_test(self, test, datatype, test_metadata, context=[]):
        if datatype.constraints:
            test_metadata.checked = True
            self.check_constraint(test,
                                  datatype.constraints,
                                  datatype,
                                  test_metadata,
                                  context)
        if isinstance(datatype, NcDatatypeDescriptorStruct):
            for field in datatype.fields:
                self.do_validate_datatype_constraints_test(test,
                                                           field,
                                                           test_metadata,
                                                           [datatype.name])

    def test_ms05_23(self, test):
        """Constraints: validate datatype constraints"""

        class_manager = self.ms05_utils.get_class_manager(test)

        test_metadata = MS0501Test.TestMetadata()

        for _, datatype in class_manager.datatype_descriptors.items():
            self.do_validate_datatype_constraints_test(test, datatype, test_metadata)

        if test_metadata.error:
            return test.FAIL(test_metadata.error_msg,
                             "https://specs.amwa.tv/ms-05-02/branches/"
                             f"{self.apis[MS05_API_KEY]['spec_branch']}"
                             "/docs/Constraints.html")

        if not test_metadata.checked:
            return test.UNCLEAR("No datatype constraints found.")

        return test.PASS()

    def _check_constraint_override(self, test, constraint, override_constraint, error_msg_base):
        def _xor_constraint(left, right):
            return bool(left is not None) ^ bool(right is not None)

        checked = False
        # Is this a number constraint
        if isinstance(constraint, (NcParameterConstraintsNumber, NcPropertyConstraintsNumber)):
            checked = True

            if _xor_constraint(constraint.minimum, override_constraint.minimum) \
                    or _xor_constraint(constraint.maximum, override_constraint.maximum) \
                    or _xor_constraint(constraint.step, override_constraint.step):
                raise NMOSTestException(
                    test.FAIL(f"{error_msg_base}Constraints implementations MUST fully override the previous level. "
                              f"Constraint: {str(constraint)}, Override_constraint: {str(override_constraint)}"))
            if constraint.minimum and override_constraint.minimum < constraint.minimum:
                raise NMOSTestException(
                    test.FAIL(f"{error_msg_base}Constraints implementations MUST not result in widening "
                              "the minimum constraint defined in previous levels. "
                              f"Constraint: {str(constraint)}, Override_constraint: {str(override_constraint)}"))
            if constraint.maximum and override_constraint.maximum > constraint.maximum:
                raise NMOSTestException(
                    test.FAIL(f"{error_msg_base}Constraints implementations MUST not result in widening "
                              "the maximum constraint defined in previous levels. "
                              f"Constraint: {str(constraint)}, Override_constraint: {str(override_constraint)}"))
            if constraint.step and override_constraint.step < constraint.step:
                raise NMOSTestException(
                    test.FAIL(f"{error_msg_base}Constraints implementations MUST not result in widening "
                              "the step constraint defined in previous levels. "
                              f"Constraint: {str(constraint)}, Override_constraint: {str(override_constraint)}"))

        # is this a string constraint
        if isinstance(constraint, (NcParameterConstraintsString, NcPropertyConstraintsString)):
            checked = True

            if _xor_constraint(constraint.maxCharacters, override_constraint.maxCharacters) \
                    or _xor_constraint(constraint.pattern, override_constraint.pattern):
                raise NMOSTestException(
                    test.FAIL(f"{error_msg_base}Constraints implementations MUST fully override the previous level. "
                              f"Constraint: {str(constraint)}, Override_constraint: "
                              f"{str(override_constraint)}"))
            if constraint.maxCharacters \
                    and override_constraint.maxCharacters > constraint.maxCharacters:
                raise NMOSTestException(
                    test.FAIL(f"{error_msg_base}Constraints implementations MUST not result in widening "
                              "the maxCharacters constraint defined in previous levels. "
                              f"Constraint: {str(constraint)}, Override_constraint: {str(override_constraint)}"))
            # Hmm, difficult to meaningfully determine whether an overridden regex pattern is widening the constraint
            # so rule of thumb here is that a shorter pattern is less constraining that a longer pattern
            if constraint.pattern and len(override_constraint.pattern) < len(constraint.pattern):
                raise NMOSTestException(
                    test.FAIL(f"{error_msg_base}Constraints implementations MUST not result in widening "
                              "the pattern constraint defined in previous levels. "
                              f"Constraint: {str(constraint)}, Override_constraint: {str(override_constraint)}"))
        return checked

    def _check_constraints_hierarchy(self, test, property_descriptor, datatype_descriptors, object_runtime_constraints,
                                     role_path):
        error_msg_base = f"role path={self.ms05_utils.create_role_path_string(role_path)}: " \
            f"property name={property_descriptor.name}: " \
            f"property id={property_descriptor.id}: "
        datatype_constraints = None
        runtime_constraints = None
        checked = False
        # Level 0: Datatype constraints
        if property_descriptor.typeName:
            if datatype_descriptors.get(property_descriptor.typeName):
                datatype_constraints = datatype_descriptors.get(property_descriptor.typeName).constraints
            else:
                raise NMOSTestException(test.FAIL(f"{error_msg_base}Unknown data type: {property_descriptor.typeName}"))
        else:
            raise NMOSTestException(test.FAIL(f"{error_msg_base}Missing data type from class descriptor"))

        # Level 1: Property constraints
        property_constraints = property_descriptor.constraints
        # Level 3: Runtime constraints
        if object_runtime_constraints:
            for object_runtime_constraint in object_runtime_constraints:
                if object_runtime_constraint.propertyId == property_descriptor.id:
                    runtime_constraints = object_runtime_constraint

        if datatype_constraints and property_constraints:
            checked = checked or \
                self._check_constraint_override(test, datatype_constraints, property_constraints,
                                                f"{error_msg_base}Datatype constraints overridden "
                                                "by property constraints: ")

        if datatype_constraints and runtime_constraints:
            checked = checked or \
                self._check_constraint_override(test, datatype_constraints, runtime_constraints,
                                                f"{error_msg_base}Datatype constraints overridden "
                                                "by runtime constraints: ")

        if property_constraints and runtime_constraints:
            checked = checked or \
                self._check_constraint_override(test, property_constraints, runtime_constraints,
                                                f"{error_msg_base}Droperty constraints overridden "
                                                "by runtime constraints: ")

        return checked

    def _check_constraints(self, test, block, test_metadata):
        class_manager = self.ms05_utils.get_class_manager(test)

        for child in block.child_objects:
            class_descriptor = class_manager.get_control_class(child.class_id, include_inherited=True)

            if not class_descriptor:
                continue
            for property_descriptor in class_descriptor.properties:
                if property_descriptor.isReadOnly:
                    continue
                try:
                    test_metadata.checked = test_metadata.checked or \
                        self._check_constraints_hierarchy(test, property_descriptor,
                                                          class_manager.datatype_descriptors,
                                                          child.runtime_constraints,
                                                          child.role_path)
                except NMOSTestException as e:
                    test_metadata.error = True
                    test_metadata.error_msg += f"{str(e.args[0].detail)}; "

            if type(child) is NcBlock:
                self._check_constraints(test, child, test_metadata)

        return test_metadata

    def test_ms05_24(self, test):
        """Constraints: check constraints hierarchy"""

        # When using multiple levels of constraints implementations MUST fully override the previous level
        # and this MUST not result in widening the constraints defined in previous levels
        # https://specs.amwa.tv/ms-05-02/branches/v1.0.x/docs/Constraints.html

        device_model = self.ms05_utils.query_device_model(test)

        if self.device_model_metadata.error:
            return test.FAIL(self.device_model_metadata.error_msg)

        test_metadata = MS0501Test.TestMetadata()

        self._check_constraints(test, device_model, test_metadata)

        if test_metadata.error:
            return test.FAIL(test_metadata.error_msg,
                             "https://specs.amwa.tv/ms-05-02/branches/"
                             f"{self.apis[MS05_API_KEY]['spec_branch']}"
                             "/docs/Constraints.html")

        if not test_metadata.checked:
            return test.UNCLEAR("No constraints hierarchy found.")

        return test.PASS()

    def test_ms05_25(self, test):
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

    def test_ms05_26(self, test):
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
