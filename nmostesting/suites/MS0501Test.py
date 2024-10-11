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
from ..MS05Utils import MS05Utils, NcBlock, NcBlockProperties, NcDatatypeType, NcDeviceManagerProperties, \
    NcMethodStatus, NcObjectProperties, StandardClassIds
from ..TestResult import Test

# Note: this test suite is a base class for the IS1201Test and IS1401Test test suites
# where there are common MS-05 tests.  The test suite is not configured and
# instantiated in the same way as the other test suites.  This is
# explicitly instantiated by the IS-12 and IS-14 test suites

NODE_API_KEY = "node"
MS05_API_KEY = "controlframework"


class MS0501Test(GenericTest):
    """
    Runs Tests covering MS-05
    """
    def __init__(self, apis, utils, **kwargs):
        # Remove the RAML key to prevent this test suite from auto-testing IS-04 API
        apis[NODE_API_KEY].pop("raml", None)
        GenericTest.__init__(self, apis, **kwargs)
        self.ms05_utils = utils

    def set_up_tests(self):
        super().set_up_tests()
        self.ms05_utils.reset()
        self.datatype_schemas = None
        self.unique_roles_error = False
        self.unique_oids_error = False
        self.managers_are_singletons_error = False
        self.managers_members_root_block_error = False
        self.device_model_metadata = {"checked": False, "error": False, "error_msg": ""}
        self.organization_metadata = {"checked": False, "error": False, "error_msg": ""}
        self.touchpoints_metadata = {"checked": False, "error": False, "error_msg": ""}
        self.deprecated_property_metadata = {"checked": False, "error": False, "error_msg": ""}
        self.get_sequence_item_metadata = {"checked": False, "error": False, "error_msg": ""}
        self.get_sequence_length_metadata = {"checked": False, "error": False, "error_msg": ""}
        self.validate_runtime_constraints_metadata = {"checked": False, "error": False, "error_msg": ""}
        self.validate_property_constraints_metadata = {"checked": False, "error": False, "error_msg": ""}
        self.validate_datatype_constraints_metadata = {"checked": False, "error": False, "error_msg": ""}
        self.check_constraints_hierarchy = {"checked": False, "error": False, "error_msg": ""}

        self.oid_cache = []

    # Used to inject specialized utils after construction
    def set_utils(self, ms05_utils):
        self.ms05_utils = ms05_utils

    # Override basics to include the MS-05 auto tests
    def basics(self):
        results = super().basics()
        try:
            results += self.auto_tests()
        except NMOSTestException as e:
            results.append(e.args[0])
        except Exception as e:
            results.append(self.uncaught_exception("auto_tests", e))
        return results

    def validate_model_definitions(self, descriptors, schema_name, reference_descriptors):
        """ Validate Class Manager model definitions against reference model descriptors.
            Returns [test result array] """
        results = list()

        reference_descriptor_keys = sorted(reference_descriptors.keys())

        for key in reference_descriptor_keys:
            test = Test("Validate " + str(key) + " definition", "auto_ms05_" + str(key))
            try:
                if descriptors.get(key):
                    descriptor = descriptors[key]

                    # Validate descriptor obeys the JSON schema
                    self.ms05_utils.validate_reference_datatype_schema(test, descriptor, schema_name)

                    # Validate the descriptor is correct
                    self.ms05_utils.validate_descriptor(test, reference_descriptors[key], descriptor)

                    results.append(test.PASS())
                else:
                    results.append(test.UNCLEAR("Not Implemented"))
            except NMOSTestException as e:
                results.append(e.args[0])

        return results

    def auto_tests(self):
        """Automatically validate all standard datatypes and control classes. Returns [test result array]"""
        # https://specs.amwa.tv/ms-05-02/releases/v1.0.0/docs/Framework.html

        results = list()
        test = Test("Initialize auto tests", "auto_init")

        class_manager = self.ms05_utils.get_class_manager(test)

        results += self.validate_model_definitions(class_manager.class_descriptors,
                                                   'NcClassDescriptor',
                                                   self.ms05_utils.reference_class_descriptors)

        results += self.validate_model_definitions(class_manager.datatype_descriptors,
                                                   'NcDatatypeDescriptor',
                                                   self.ms05_utils.reference_datatype_descriptors)
        return results

    def test_ms05_01(self, test):
        """Device Model: Root Block exists with correct oid and role"""
        # https://specs.amwa.tv/ms-05-02/releases/v1.0.0/docs/Blocks.html

        # Check role is correct
        role = self.ms05_utils.get_property_value(
            test,
            NcObjectProperties.ROLE.value,
            oid=self.ms05_utils.ROOT_BLOCK_OID,
            role_path=['root'])

        if role != "root":
            return test.FAIL("Unexpected role in Root Block: " + str(role),
                             "https://specs.amwa.tv/ms-05-02/branches/{}"
                             "/docs/Blocks.html"
                             .format(self.apis[MS05_API_KEY]["spec_branch"]))

        # Check OID is correct
        oid = self.ms05_utils.get_property_value(
            test,
            NcObjectProperties.OID.value,
            oid=self.ms05_utils.ROOT_BLOCK_OID,
            role_path=['root'])

        if oid != self.ms05_utils.ROOT_BLOCK_OID:
            return test.FAIL("Unexpected role in Root Block: " + str(role),
                             "https://specs.amwa.tv/ms-05-02/branches/{}"
                             "/docs/Blocks.html"
                             .format(self.apis[MS05_API_KEY]["spec_branch"]))

        return test.PASS()

    def get_datatype_schema(self, test, type_name):
        """Get generated JSON schema for datatype specified"""
        if not self.datatype_schemas:
            self.datatype_schemas = self.ms05_utils.generate_device_model_datatype_schemas(test)

        return self.datatype_schemas.get(type_name)

    def get_property(self, test, oid, property_id, role_path, context):
        """Get property from object. Sets self.device_model_metadata on error"""
        try:
            return self.ms05_utils.get_property(test, property_id, oid=oid, role_path=role_path)
        except NMOSTestException as e:
            self.device_model_metadata["error"] = True
            self.device_model_metadata["error_msg"] += context \
                + "Error getting property: " \
                + str(property_id) + ": " \
                + str(e.args[0].detail) \
                + "; "
        return None

    def get_property_value(self, test, property_id, context, oid, role_path):
        """Get value of property from object. Sets self.device_model_metadata on error"""
        try:
            return self.ms05_utils.get_property_value(test, property_id, oid=oid, role_path=role_path)
        except NMOSTestException as e:
            self.device_model_metadata["error"] = True
            self.device_model_metadata["error_msg"] += context \
                + "Error getting property: " \
                + str(property_id) + ": " \
                + str(e.args[0].detail) \
                + "; "
            return None

    def _validate_property_type(self, test, value, data_type, is_nullable, context=""):
        """Validate the the property value is correct according to the type. Raises NMOSTestException on error"""
        if value is None:
            if is_nullable:
                return
            else:
                raise NMOSTestException(test.FAIL(context + "Non-nullable property set to null."))

        if self.ms05_utils.primitive_to_python_type(data_type):
            # Special case: if this is a floating point value it
            # can be intepreted as an int in the case of whole numbers
            # e.g. 0.0 -> 0, 1.0 -> 1
            if self.ms05_utils.primitive_to_python_type(data_type) == float and isinstance(value, int):
                return

            if not isinstance(value, self.ms05_utils.primitive_to_python_type(data_type)):
                raise NMOSTestException(test.FAIL(context + str(value) + " is not of type " + str(data_type)))
        else:
            self.ms05_utils.validate_schema(test, value, self.get_datatype_schema(test, data_type), context + data_type)

        return

    def check_get_sequence_item(self, test, oid, role_path, sequence_values, property_metadata, context=""):
        if sequence_values is None and not property_metadata["isNullable"]:
            self.get_sequence_item_metadata["error"] = True
            self.get_sequence_item_metadata["error_msg"] += \
                context + property_metadata["name"] + ": Non-nullable property set to null, "
            return
        try:
            # GetSequenceItem
            self.get_sequence_item_metadata["checked"] = True
            sequence_index = 0
            for property_value in sequence_values:
                value = self.ms05_utils.get_sequence_item_value(test, property_metadata['id'], sequence_index,
                                                                oid=oid, role_path=role_path)
                if property_value != value:
                    self.get_sequence_item_metadata["error"] = True
                    self.get_sequence_item_metadata["error_msg"] += \
                        context + property_metadata["name"] \
                        + ": Expected: " + str(property_value) + ", Actual: " + str(value) \
                        + " at index " + sequence_index + ", "
                sequence_index += 1
            return True
        except NMOSTestException as e:
            self.get_sequence_item_metadata["error"] = True
            self.get_sequence_item_metadata["error_msg"] += \
                context + property_metadata["name"] + ": " + str(e.args[0].detail) + ", "
        return False

    def check_get_sequence_length(self, test, oid, role_path, sequence_values, property_metadata, context=""):
        if sequence_values is None and not property_metadata["isNullable"]:
            self.get_sequence_length_metadata["error"] = True
            self.get_sequence_length_metadata["error_msg"] += \
                context + property_metadata["name"] + ": Non-nullable property set to null, "
            return

        try:
            self.get_sequence_length_metadata["checked"] = True
            length = self.ms05_utils.get_sequence_length(test, property_metadata['id'],
                                                         oid=oid, role_path=role_path)

            if length == len(sequence_values):
                return True
            self.get_sequence_length_metadata["error_msg"] += \
                context + property_metadata["name"] \
                + ": GetSequenceLength error. Expected: " \
                + str(len(sequence_values)) + ", Actual: " + str(length) + ", "
        except NMOSTestException as e:
            self.get_sequence_length_metadata["error_msg"] += \
                context + property_metadata["name"] + ": " + str(e.args[0].detail) + ", "
        self.get_sequence_length_metadata["error"] = True
        return False

    def check_sequence_methods(self, test, oid, role_path, sequence_values, property_metadata, context=""):
        """Check that sequence manipulation methods work correctly"""
        self.check_get_sequence_item(test, oid, role_path, sequence_values, property_metadata, context)
        self.check_get_sequence_length(test, oid, role_path, sequence_values, property_metadata, context)

    def check_object_properties(self, test, reference_class_descriptor, oid, role_path, context):
        for class_property in reference_class_descriptor['properties']:
            response = self.get_property(test, oid, class_property.get('id'), role_path, context)

            if response is None:
                # Can't find this property - do we have an ID clash
                self.device_model_metadata["error"] = True
                self.device_model_metadata["error_msg"] += \
                    "Property does not exist - it is possible that the class id for this class is NOT unique? " \
                    + "classId: " + ".".join(map(str, reference_class_descriptor['classId']))
                continue

            object_property = response["value"]

            if class_property["isDeprecated"]:
                self.deprecated_property_metadata["checked"] = True
                if response["status"] != NcMethodStatus.PropertyDeprecated.value:
                    self.deprecated_property_metadata["error"] = True
                    self.deprecated_property_metadata["error_msg"] = context + \
                        " PropertyDeprecated status code expected when getting " + class_property["name"]

            if not object_property:
                continue

            # validate property type
            if class_property['isSequence']:
                for property_value in object_property:
                    self._validate_property_type(
                        test,
                        property_value,
                        class_property['typeName'],
                        class_property['isNullable'],
                        context=context + class_property["typeName"]
                        + ": " + class_property["name"] + ": ")
                self.check_sequence_methods(test,
                                            oid,
                                            role_path,
                                            object_property,
                                            class_property,
                                            context=context)
            else:
                self._validate_property_type(
                    test,
                    object_property,
                    class_property['typeName'],
                    class_property['isNullable'],
                    context=context + class_property["name"] + ": ")
        return

    def check_unique_roles(self, role, role_cache):
        """Check role is unique within containing Block"""
        if role in role_cache:
            self.unique_roles_error = True
        else:
            role_cache.append(role)

    def check_unique_oid(self, oid):
        """Check oid is globally unique"""
        if oid in self.oid_cache:
            self.unique_oids_error = True
        else:
            self.oid_cache.append(oid)

    def check_manager(self, class_id, owner, class_descriptors, manager_cache):
        """Check manager is singleton and that it inherits from NcManager"""
        # detemine the standard base class name
        base_id = self.ms05_utils.get_base_class_id(class_id)
        base_class_name = class_descriptors[base_id]["name"]

        # manager checks
        if self.ms05_utils.is_manager(class_id):
            if owner != self.ms05_utils.ROOT_BLOCK_OID:
                self.managers_members_root_block_error = True
            if base_class_name in manager_cache:
                self.managers_are_singletons_error = True
            else:
                manager_cache.append(base_class_name)

    def check_touchpoints(self, test, oid, role_path, context):
        """Touchpoint checks"""
        touchpoints = self.get_property_value(
            test,
            NcObjectProperties.TOUCHPOINTS.value,
            context,
            oid,
            role_path)

        if touchpoints is not None:
            self.touchpoints_metadata["checked"] = True
            try:
                for touchpoint in touchpoints:
                    schema = self.get_datatype_schema(test, "NcTouchpointNmos") \
                        if touchpoint["contextNamespace"] == "x-nmos" \
                        else self.get_datatype_schema(test, "NcTouchpointNmosChannelMapping")
                    self.ms05_utils.validate_schema(
                        test,
                        touchpoint,
                        schema,
                        context=context + schema["title"])

            except NMOSTestException as e:
                self.touchpoints_metadata["error"] = True
                self.touchpoints_metadata["error_msg"] = context + str(e.args[0].detail)

    def check_block(self, test, block, class_descriptors, context=""):
        for child_object in block.child_objects:
            # If this child object is a Block, recurse
            if type(child_object) is NcBlock:
                self.check_block(test,
                                 child_object,
                                 class_descriptors,
                                 context=context + str(child_object.role) + ': ')
        role_cache = []
        manager_cache = []
        for descriptor in block.member_descriptors:
            role_path = self.ms05_utils.create_role_path(block.role_path, descriptor['role'])
            self.ms05_utils.validate_schema(
                test,
                descriptor,
                self.get_datatype_schema(test, "NcBlockMemberDescriptor"),
                context=context + "NcBlockMemberDescriptor: " + str(descriptor['role']))

            self.check_unique_roles(descriptor['role'], role_cache)
            self.check_unique_oid(descriptor['oid'])
            # check for non-standard classes
            if self.ms05_utils.is_non_standard_class(descriptor['classId']):
                self.organization_metadata["checked"] = True
            self.check_manager(descriptor['classId'], descriptor["owner"], class_descriptors, manager_cache)
            self.check_touchpoints(test, descriptor['oid'], role_path,
                                   context=context + str(descriptor['role']) + ': ')

            class_identifier = ".".join(map(str, descriptor['classId']))
            if class_identifier and class_identifier in class_descriptors:
                self.ms05_utils.validate_schema(
                    test,
                    class_descriptors[class_identifier],
                    self.get_datatype_schema(test, "NcClassDescriptor"),
                    context=context + "NcClassDescriptor for class " + str(descriptor['classId']))
                self.check_object_properties(test,
                                             class_descriptors[class_identifier],
                                             descriptor['oid'],
                                             role_path,
                                             context=context + str(descriptor['role']) + ': ')
            else:
                self.device_model_metadata["error"] = True
                self.device_model_metadata["error_msg"] += str(descriptor['role']) + ': ' \
                    + "Class not advertised by Class Manager: " \
                    + str(descriptor['classId']) + ". "

            if class_identifier not in self.ms05_utils.reference_class_descriptors and \
                    not self.ms05_utils.is_non_standard_class(descriptor['classId']):
                # Not a standard or non-standard class
                self.organization_metadata["error"] = True
                self.organization_metadata["error_msg"] = str(descriptor['role']) + ': ' \
                    + "Non-standard class id does not contain authority key: " \
                    + str(descriptor['classId']) + ". "

    def check_device_model(self, test):
        if not self.device_model_metadata["checked"]:
            class_manager = self.ms05_utils.get_class_manager(test)
            device_model = self.ms05_utils.query_device_model(test)

            self.check_block(test,
                             device_model,
                             class_manager.class_descriptors)

            self.device_model_metadata["checked"] = True
        return

    def test_ms05_02(self, test):
        """Device Model: Device Model is correct according to classes and datatypes advertised by Class Manager"""
        # https://specs.amwa.tv/ms-05-02/releases/v1.0.0/docs/Managers.html
        # https://specs.amwa.tv/ms-05-02/releases/v1.0.0/docs/Workers.html

        self.check_device_model(test)

        if self.device_model_metadata["error"]:
            return test.FAIL(self.device_model_metadata["error_msg"])

        if not self.device_model_metadata["checked"]:
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

        if self.unique_roles_error:
            return test.FAIL("Roles must be unique. ",
                             "https://specs.amwa.tv/ms-05-02/branches/{}"
                             "/docs/NcObject.html"
                             .format(self.apis[MS05_API_KEY]["spec_branch"]))

        if not self.device_model_metadata["checked"]:
            return test.UNCLEAR("Unable to check Device Model.")

        return test.PASS()

    def test_ms05_04(self, test):
        """Device Model: oids are globally unique"""
        # https://specs.amwa.tv/ms-05-02/releases/v1.0.0/docs/NcObject.html

        try:
            self.check_device_model(test)
        except NMOSTestException as e:
            # Couldn't validate model so can't perform test
            return test.FAIL(e.args[0].detail, e.args[0].link)

        if self.unique_oids_error:
            return test.FAIL("Oids must be unique. ",
                             "https://specs.amwa.tv/ms-05-02/branches/{}"
                             "/docs/NcObject.html"
                             .format(self.apis[MS05_API_KEY]["spec_branch"]))

        if not self.device_model_metadata["checked"]:
            return test.UNCLEAR("Unable to check Device Model.")

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

        if self.organization_metadata["error"]:
            return test.FAIL(self.organization_metadata["error_msg"],
                             "https://specs.amwa.tv/ms-05-02/branches/{}"
                             "/docs/Framework.html#ncclassid"
                             .format(self.apis[MS05_API_KEY]["spec_branch"]))

        if not self.device_model_metadata["checked"]:
            return test.UNCLEAR("Unable to check Device Model.")

        if not self.organization_metadata["checked"]:
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

        if self.touchpoints_metadata["error"]:
            return test.FAIL(self.touchpoints_metadata["error_msg"],
                             "https://specs.amwa.tv/ms-05-02/branches/{}"
                             "/docs/NcObject.html#touchpoints"
                             .format(self.apis[MS05_API_KEY]["spec_branch"]))

        if not self.device_model_metadata["checked"]:
            return test.UNCLEAR("Unable to check Device Model.")

        if not self.touchpoints_metadata["checked"]:
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

        if self.deprecated_property_metadata["error"]:
            return test.FAIL(self.deprecated_property_metadata["error_msg"],
                             "https://specs.amwa.tv/ms-05-02/branches/{}"
                             "/docs/Framework.html#ncmethodstatus"
                             .format(self.apis[MS05_API_KEY]["spec_branch"]))

        if not self.device_model_metadata["checked"]:
            return test.UNCLEAR("Unable to check Device Model.")

        if not self.deprecated_property_metadata["checked"]:
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

        if self.managers_members_root_block_error:
            return test.FAIL("Managers must be members of Root Block. ",
                             "https://specs.amwa.tv/ms-05-02/branches/{}"
                             "/docs/Managers.html"
                             .format(self.apis[MS05_API_KEY]["spec_branch"]))

        if not self.device_model_metadata["checked"]:
            return test.UNCLEAR("Unable to check Device Model.")

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

        if self.managers_are_singletons_error:
            return test.FAIL("Managers must be singleton classes. ",
                             "https://specs.amwa.tv/ms-05-02/branches/{}"
                             "/docs/Managers.html"
                             .format(self.apis[MS05_API_KEY]["spec_branch"]))

        if not self.device_model_metadata["checked"]:
            return test.UNCLEAR("Unable to check Device Model.")

        return test.PASS()

    def test_ms05_10(self, test):
        """Managers: Class Manager exists with correct role"""
        # Class manager exists in root
        # https://specs.amwa.tv/ms-05-02/releases/v1.0.0/docs/Managers.html

        spec_link = "https://specs.amwa.tv/ms-05-02/branches/{}/docs/Managers.html"\
            .format(self.apis[MS05_API_KEY]["spec_branch"])

        class_manager = self.ms05_utils.get_class_manager(test)

        class_id_str = ".".join(map(str, StandardClassIds.NCCLASSMANAGER.value))
        class_descriptor = self.ms05_utils.reference_class_descriptors[class_id_str]

        if class_manager.role != class_descriptor["fixedRole"]:
            return test.FAIL("Class Manager MUST have a role of ClassManager.", spec_link)

        return test.PASS()

    def test_ms05_11(self, test):
        """Managers: Device Manager exists with correct Role"""
        # A minimal device implementation MUST have a device manager in the Root Block.
        # https://specs.amwa.tv/ms-05-02/releases/v1.0.0/docs/Managers.html

        spec_link = "https://specs.amwa.tv/ms-05-02/branches/{}/docs/Managers.html"\
            .format(self.apis[MS05_API_KEY]["spec_branch"])

        device_manager = self.ms05_utils.get_device_manager(test)

        class_id_str = ".".join(map(str, StandardClassIds.NCDEVICEMANAGER.value))
        class_descriptor = self.ms05_utils.reference_class_descriptors[class_id_str]

        if device_manager.role != class_descriptor["fixedRole"]:
            return test.FAIL("Device Manager MUST have a role of DeviceManager.", spec_link)

        # Check MS-05-02 Version
        property_id = NcDeviceManagerProperties.NCVERSION.value

        version = self.ms05_utils.get_property_value(test, property_id,
                                                     oid=device_manager.oid,
                                                     role_path=device_manager.role_path)

        if self.ms05_utils.compare_api_version(version, self.apis[MS05_API_KEY]["version"]):
            return test.FAIL("Unexpected version. Expected: "
                             + self.apis[MS05_API_KEY]["version"]
                             + ". Actual: " + str(version))
        return test.PASS()

    def test_ms05_12(self, test):
        """Class Manager: GetControlClass method is correct"""
        # Where the functionality of a device uses control classes and datatypes listed in this
        # specification it MUST comply with the model definitions published
        # https://specs.amwa.tv/ms-05-02/releases/v1.0.0/docs/Framework.html#ncclassmanager

        class_manager = self.ms05_utils.get_class_manager(test)

        for _, class_descriptor in class_manager.class_descriptors.items():
            for include_inherited in [False, True]:
                actual_descriptor = self.ms05_utils.get_control_class(test,
                                                                      class_descriptor["classId"],
                                                                      include_inherited,
                                                                      oid=class_manager.oid,
                                                                      role_path=class_manager.role_path)
                expected_descriptor = class_manager.get_control_class(class_descriptor["classId"],
                                                                      include_inherited)
                self.ms05_utils.validate_descriptor(
                    test,
                    expected_descriptor,
                    actual_descriptor,
                    context=f"Class: {str(class_descriptor['classId'])}: ")

        return test.PASS()

    def test_ms05_13(self, test):
        """Class Manager: GetDatatype method is correct"""
        # Where the functionality of a device uses control classes and datatypes listed in this
        # specification it MUST comply with the model definitions published
        # https://specs.amwa.tv/ms-05-02/releases/v1.0.0/docs/Framework.html#ncclassmanager

        class_manager = self.ms05_utils.get_class_manager(test)

        for _, datatype_descriptor in class_manager.datatype_descriptors.items():
            for include_inherited in [False, True]:
                actual_descriptor = self.ms05_utils.get_datatype(test,
                                                                 datatype_descriptor["name"],
                                                                 include_inherited,
                                                                 oid=class_manager.oid,
                                                                 role_path=class_manager.role_path)
                expected_descriptor = class_manager.get_datatype(datatype_descriptor["name"],
                                                                 include_inherited)
                self.ms05_utils.validate_descriptor(
                    test,
                    expected_descriptor,
                    actual_descriptor,
                    context=f"Datatype: {datatype_descriptor['name']}: ")

        return test.PASS()

    def test_ms05_14(self, test):
        """NcObject: Get and Set methods are correct"""
        # Generic getter and setter. The value of any property of a control class MUST be retrievable
        # using the Get method.
        # https://specs.amwa.tv/ms-05-02/releases/v1.0.0/docs/NcObject.html#generic-getter-and-setter

        link = "https://specs.amwa.tv/ms-05-02/branches/{}" \
               "/docs/NcObject.html#generic-getter-and-setter" \
               .format(self.apis[MS05_API_KEY]["spec_branch"])

        # Attempt to set labels
        property_id = NcObjectProperties.USER_LABEL.value

        old_user_label = self.ms05_utils.get_property_value(test, property_id,
                                                            oid=self.ms05_utils.ROOT_BLOCK_OID,
                                                            role_path=['root'])

        # Set user label
        new_user_label = "NMOS Testing Tool"

        self.ms05_utils.set_property(test, property_id, new_user_label,
                                     oid=self.ms05_utils.ROOT_BLOCK_OID,
                                     role_path=['root'])

        # Check user label
        label = self.ms05_utils.get_property_value(test, property_id,
                                                   oid=self.ms05_utils.ROOT_BLOCK_OID,
                                                   role_path=['root'])
        if label != new_user_label:
            if label == old_user_label:
                return test.FAIL("Unable to set user label", link)
            else:
                return test.FAIL("Unexpected user label: " + str(label), link)

        # Reset user label
        self.ms05_utils.set_property(test, property_id, old_user_label,
                                     oid=self.ms05_utils.ROOT_BLOCK_OID,
                                     role_path=['root'])

        # Check user label
        label = self.ms05_utils.get_property_value(test, property_id,
                                                   oid=self.ms05_utils.ROOT_BLOCK_OID,
                                                   role_path=['root'])
        if label != old_user_label:
            if label == new_user_label:
                return test.FAIL("Unable to set user label", link)
            else:
                return test.FAIL("Unexpected user label: " + str(label), link)

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

        if self.get_sequence_item_metadata["error"]:
            return test.FAIL(self.get_sequence_item_metadata["error_msg"])

        if not self.get_sequence_item_metadata["checked"]:
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

        if self.get_sequence_length_metadata["error"]:
            return test.FAIL(self.get_sequence_length_metadata["error_msg"])

        if not self.get_sequence_length_metadata["checked"]:
            return test.UNCLEAR("GetSequenceItem not tested.")

        return test.PASS()

    def do_get_member_descriptors_test(self, test, block, context=""):
        # Recurse through the child blocks
        for child_object in block.child_objects:
            if type(child_object) is NcBlock:
                self.do_get_member_descriptors_test(test, child_object, context + block.role + ": ")

        search_conditions = [{"recurse": True}, {"recurse": False}]

        for search_condition in search_conditions:
            expected_members = block.get_member_descriptors(search_condition["recurse"])

            queried_members = self.ms05_utils.get_member_descriptors(test, search_condition["recurse"],
                                                                     oid=block.oid, role_path=block.role_path)

            if not isinstance(queried_members, list):
                raise NMOSTestException(test.FAIL(context
                                                  + block.role
                                                  + ": Did not return an array of results."))

            if len(queried_members) != len(expected_members):
                raise NMOSTestException(test.FAIL(context
                                                  + block.role
                                                  + ": Unexpected number of block members found. Expected: "
                                                  + str(len(expected_members)) + ", Actual: "
                                                  + str(len(queried_members))))

            expected_members_oids = [m["oid"] for m in expected_members]

            for queried_member in queried_members:
                self.ms05_utils.validate_reference_datatype_schema(
                    test,
                    queried_member,
                    "NcBlockMemberDescriptor",
                    context=context
                    + block.role
                    + ": NcBlockMemberDescriptor: ")

                if queried_member["oid"] not in expected_members_oids:
                    raise NMOSTestException(test.FAIL(context
                                                      + block.role
                                                      + ": Unsuccessful attempt to get member descriptors."))

    def test_ms05_17(self, test):
        """NcBlock: GetMemberDescriptors method is correct"""
        # Where the functionality of a device uses control classes and datatypes listed in this
        # specification it MUST comply with the model definitions published
        # https://specs.amwa.tv/ms-05-02/releases/v1.0.0/docs/Framework.html#ncblock

        device_model = self.ms05_utils.query_device_model(test)

        self.do_get_member_descriptors_test(test, device_model)

        return test.PASS()

    def do_find_member_by_path_test(self, test, block, context=""):
        # Recurse through the child blocks
        for child_object in block.child_objects:
            if type(child_object) is NcBlock:
                self.do_find_member_by_path_test(test, child_object, context + block.role + ": ")

        # Get ground truth role paths
        role_paths = block.get_role_paths()

        for path in role_paths:
            # Get ground truth data from local device model object tree
            expected_member = block.find_members_by_path(path)

            queried_members = self.ms05_utils.find_members_by_path(test, path,
                                                                   oid=block.oid,
                                                                   role_path=block.role_path)

            if not isinstance(queried_members, list):
                raise NMOSTestException(test.FAIL(context
                                                  + block.role
                                                  + ": Did not return an array of results for query: "
                                                  + str(path)))

            for queried_member in queried_members:
                self.ms05_utils.validate_reference_datatype_schema(
                    test,
                    queried_member,
                    "NcBlockMemberDescriptor",
                    context=context
                    + block.role
                    + ": NcBlockMemberDescriptor: ")

            if len(queried_members) != 1:
                raise NMOSTestException(test.FAIL(context
                                                  + block.role
                                                  + ": Incorrect member found by role path: " + str(path)))

            queried_member_oids = [m['oid'] for m in queried_members]

            if expected_member.oid not in queried_member_oids:
                raise NMOSTestException(test.FAIL(context
                                                  + block.role
                                                  + ": Unsuccessful attempt to find member by role path: "
                                                  + str(path)))

    def test_ms05_18(self, test):
        """NcBlock: FindMemberByPath method is correct"""
        # Where the functionality of a device uses control classes and datatypes listed in this
        # specification it MUST comply with the model definitions published
        # https://specs.amwa.tv/ms-05-02/releases/v1.0.0/docs/Framework.html#ncblock

        device_model = self.ms05_utils.query_device_model(test)

        # Recursively check each block in Device Model
        self.do_find_member_by_path_test(test, device_model)

        return test.PASS()

    def do_find_member_by_role_test(self, test, block, context=""):
        # Recurse through the child blocks
        for child_object in block.child_objects:
            if type(child_object) is NcBlock:
                self.do_find_member_by_role_test(test, child_object, context + block.role + ": ")

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
                    expected_results = \
                        block.find_members_by_role(query_string,
                                                   case_sensitive=condition["case_sensitive"],
                                                   match_whole_string=condition["match_whole_string"],
                                                   recurse=condition["recurse"])
                    actual_results = \
                        self.ms05_utils.find_members_by_role(test,
                                                             query_string,
                                                             case_sensitive=condition["case_sensitive"],
                                                             match_whole_string=condition["match_whole_string"],
                                                             recurse=condition["recurse"],
                                                             oid=block.oid,
                                                             role_path=block.role_path)

                    expected_results_oids = [m.oid for m in expected_results]

                    if actual_results is None or len(actual_results) != len(expected_results):
                        raise NMOSTestException(test.FAIL(context
                                                          + block.role
                                                          + ": Expected "
                                                          + str(len(expected_results))
                                                          + ", but got "
                                                          + str(len(actual_results) if actual_results else 0)
                                                          + " when searching with query=" + str(query_string)
                                                          + ", case sensitive=" + str(condition["case_sensitive"])
                                                          + ", match whole string="
                                                          + str(condition["match_whole_string"])
                                                          + ", recurse=" + str(condition["recurse"])))

                    for actual_result in actual_results:
                        if actual_result["oid"] not in expected_results_oids:
                            raise NMOSTestException(test.FAIL(context
                                                              + block.role
                                                              + ": Unexpected search result. "
                                                              + str(actual_result)
                                                              + " when searching with query=" + str(query_string)
                                                              + ", case sensitive=" + str(condition["case_sensitive"])
                                                              + ", match whole string="
                                                              + str(condition["match_whole_string"])
                                                              + ", recurse=" + str(condition["recurse"])))

    def check_constraint(self, test, constraint, type_name, is_sequence, test_metadata, context):
        if constraint.get("defaultValue"):
            datatype_schema = self.get_datatype_schema(test, type_name)
            if isinstance(constraint.get("defaultValue"), list) is not is_sequence:
                test_metadata["error"] = True
                test_metadata["error_msg"] = context + (" a default value sequence was expected"
                                                        if is_sequence else " unexpected default value sequence.")
                return
            if is_sequence:
                for value in constraint.get("defaultValue"):
                    self.ms05_utils.validate_schema(test, value, datatype_schema, context + ": defaultValue ")
            else:
                self.ms05_utils.validate_schema(
                    test,
                    constraint.get("defaultValue"),
                    datatype_schema,
                    context + ": defaultValue ")

        datatype = self.ms05_utils.resolve_datatype(test, type_name)
        # check NcXXXConstraintsNumber
        if constraint.get("minimum") or constraint.get("maximum") or constraint.get("step"):
            constraint_type = "NcPropertyConstraintsNumber" \
                if constraint.get("propertyId") else "NcParameterConstraintsNumber"
            if datatype not in ["NcInt16", "NcInt32", "NcInt64", "NcUint16", "NcUint32",
                                "NcUint64", "NcFloat32", "NcFloat64"]:
                test_metadata["error"] = True
                test_metadata["error_msg"] = context + ". " + datatype + \
                    " can not be constrainted by " + constraint_type + "."
        # check NcXXXConstraintsString
        if constraint.get("maxCharacters") or constraint.get("pattern"):
            constraint_type = "NcPropertyConstraintsString" \
                if constraint.get("propertyId") else "NcParameterConstraintsString"
            if datatype not in ["NcString"]:
                test_metadata["error"] = True
                test_metadata["error_msg"] = context + ". " + datatype + \
                    " can not be constrainted by " + constraint_type + "."

    def do_validate_runtime_constraints_test(self, test, nc_object, class_manager, context=""):
        if nc_object.runtime_constraints:
            self.validate_runtime_constraints_metadata["checked"] = True
            for constraint in nc_object.runtime_constraints:
                class_descriptor = class_manager.class_descriptors[".".join(map(str, nc_object.class_id))]
                for class_property in class_descriptor["properties"]:
                    if class_property["id"] == constraint["propertyId"]:
                        message_root = context + nc_object.role + ": " + class_property["name"] + \
                            ": " + class_property.get("typeName")
                        self.check_constraint(test,
                                              constraint,
                                              class_property.get("typeName"),
                                              class_property["isSequence"],
                                              self.validate_runtime_constraints_metadata,
                                              message_root)

        # Recurse through the child blocks
        if type(nc_object) is NcBlock:
            for child_object in nc_object.child_objects:
                self.do_validate_runtime_constraints_test(test,
                                                          child_object,
                                                          class_manager,
                                                          context + nc_object.role + ": ")

    def test_ms05_19(self, test):
        """NcBlock: FindMembersByRole method is correct"""
        # Where the functionality of a device uses control classes and datatypes listed in this
        # specification it MUST comply with the model definitions published
        # https://specs.amwa.tv/ms-05-02/releases/v1.0.0/docs/Framework.html#ncblock

        device_model = self.ms05_utils.query_device_model(test)

        # Recursively check each block in Device Model
        self.do_find_member_by_role_test(test, device_model)

        return test.PASS()

    def do_find_members_by_class_id_test(self, test, block, context=""):
        # Recurse through the child blocks
        for child_object in block.child_objects:
            if type(child_object) is NcBlock:
                self.do_find_members_by_class_id_test(test, child_object, context + block.role + ": ")

        class_ids = [e.value for e in StandardClassIds]

        truth_table = MS05Utils.sampled_list(list(product([False, True], repeat=2)))
        search_conditions = []
        for state in truth_table:
            search_conditions += [{"include_derived": state[0], "recurse": state[1]}]

        for class_id in class_ids:
            for condition in search_conditions:
                # Recursively check each block in Device Model
                expected_results = block.find_members_by_class_id(class_id,
                                                                  condition["include_derived"],
                                                                  condition["recurse"])

                actual_results = self.ms05_utils.find_members_by_class_id(test,
                                                                          class_id,
                                                                          condition["include_derived"],
                                                                          condition["recurse"],
                                                                          oid=block.oid,
                                                                          role_path=block.role_path)

                expected_results_oids = [m.oid for m in expected_results]

                if actual_results is None or len(actual_results) != len(expected_results):
                    raise NMOSTestException(test.FAIL(context
                                                      + block.role
                                                      + ": Expected "
                                                      + str(len(expected_results))
                                                      + ", but got "
                                                      + str(len(actual_results) if actual_results else 0)
                                                      + " when searching with class id=" + str(class_id)
                                                      + ", include derived=" + str(condition["include_derived"])
                                                      + ", recurse=" + str(condition["recurse"])))

                for actual_result in actual_results:
                    if actual_result["oid"] not in expected_results_oids:
                        raise NMOSTestException(test.FAIL(context
                                                          + block.role
                                                          + ": Unexpected search result. " + str(actual_result)
                                                          + " when searching with class id=" + str(class_id)
                                                          + ", include derived=" + str(condition["include_derived"])
                                                          + ", recurse=" + str(condition["recurse"])))

    def test_ms05_20(self, test):
        """NcBlock: FindMembersByClassId method is correct"""
        # Where the functionality of a device uses control classes and datatypes listed in this
        # specification it MUST comply with the model definitions published
        # https://specs.amwa.tv/ms-05-02/releases/v1.0.0/docs/Framework.html#ncblock

        device_model = self.ms05_utils.query_device_model(test)

        self.do_find_members_by_class_id_test(test, device_model)

        return test.PASS()

    def test_ms05_21(self, test):
        """Constraints: validate runtime constraints"""

        device_model = self.ms05_utils.query_device_model(test)
        class_manager = self.ms05_utils.get_class_manager(test)

        self.do_validate_runtime_constraints_test(test, device_model, class_manager)

        if self.validate_runtime_constraints_metadata["error"]:
            return test.FAIL(self.validate_runtime_constraints_metadata["error_msg"])

        if not self.validate_runtime_constraints_metadata["checked"]:
            return test.UNCLEAR("No runtime constraints found.")

        return test.PASS()

    def do_validate_property_constraints_test(self, test, nc_object, class_manager, context=""):
        class_descriptor = class_manager.class_descriptors[".".join(map(str, nc_object.class_id))]

        for class_property in class_descriptor["properties"]:
            if class_property["constraints"]:
                self.validate_property_constraints_metadata["checked"] = True
                message_root = context + nc_object.role + ": " + class_property["name"] + \
                    ": " + class_property.get("typeName")
                self.check_constraint(test,
                                      class_property["constraints"],
                                      class_property.get("typeName"),
                                      class_property["isSequence"],
                                      self.validate_property_constraints_metadata,
                                      message_root)
        # Recurse through the child blocks
        if type(nc_object) is NcBlock:
            for child_object in nc_object.child_objects:
                self.do_validate_property_constraints_test(test,
                                                           child_object,
                                                           class_manager,
                                                           context + nc_object.role + ": ")

    def test_ms05_22(self, test):
        """Constraints: validate property constraints"""

        device_model = self.ms05_utils.query_device_model(test)
        class_manager = self.ms05_utils.get_class_manager(test)

        self.do_validate_property_constraints_test(test, device_model, class_manager)

        if self.validate_property_constraints_metadata["error"]:
            return test.FAIL(self.validate_property_constraints_metadata["error_msg"])

        if not self.validate_property_constraints_metadata["checked"]:
            return test.UNCLEAR("No property constraints found.")

        return test.PASS()

    def do_validate_datatype_constraints_test(self, test, datatype, type_name, context=""):
        if datatype.get("constraints"):
            self.validate_datatype_constraints_metadata["checked"] = True
            self.check_constraint(test,
                                  datatype.get("constraints"),
                                  type_name,
                                  datatype.get("isSequence", False),
                                  self.validate_datatype_constraints_metadata,
                                  context + ": " + type_name)
        if datatype.get("type") == NcDatatypeType.Struct.value:
            for field in datatype.get("fields"):
                self.do_validate_datatype_constraints_test(test,
                                                           field,
                                                           field["typeName"],
                                                           context + ": " + type_name + ": " + field["name"])

    def test_ms05_23(self, test):
        """Constraints: validate datatype constraints"""

        class_manager = self.ms05_utils.get_class_manager(test)

        for _, datatype in class_manager.datatype_descriptors.items():
            self.do_validate_datatype_constraints_test(test, datatype, datatype["name"])

        if self.validate_datatype_constraints_metadata["error"]:
            return test.FAIL(self.validate_datatype_constraints_metadata["error_msg"])

        if not self.validate_datatype_constraints_metadata["checked"]:
            return test.UNCLEAR("No datatype constraints found.")

        return test.PASS()

    def _xor_constraint(self, left, right):
        return bool(left is not None) ^ bool(right is not None)

    def _check_constraint_override(self, test, constraint, override_constraint, context):
        # Is this a number constraint
        if 'minimum' in constraint or 'maximum' in constraint or 'step' in constraint:
            self.check_constraints_hierarchy["checked"] = True

            if self._xor_constraint(constraint.get('minimum'), override_constraint.get('minimum')) \
                    or self._xor_constraint(constraint.get('maximum'), override_constraint.get('maximum')) \
                    or self._xor_constraint(constraint.get('step'), override_constraint.get('step')):
                raise NMOSTestException(
                    test.FAIL(context + "Constraints implementations MUST fully override the previous level: "
                              + "constraint: " + str(constraint) + ", override_constraint: "
                              + str(override_constraint)))
            if constraint.get('minimum') and override_constraint.get('minimum') < constraint.get('minimum'):
                raise NMOSTestException(
                    test.FAIL(context + "Constraints implementations MUST not result in widening "
                              + "the constraints defined in previous levels: "
                              + "minimum constraint: " + str(constraint.get('minimum'))
                              + ", override minimum constraint: " + str(override_constraint.get('minimum'))))
            if constraint.get('maximum') and override_constraint.get('maximum') > constraint.get('maximum'):
                raise NMOSTestException(
                    test.FAIL(context + "Constraints implementations MUST not result in widening "
                              + "the constraints defined in previous levels: "
                              + "maximum constraint: " + str(constraint.get('maximum'))
                              + ", override maximum constraint: " + str(override_constraint.get('maximum'))))
            if constraint.get('step') and override_constraint.get('step') < constraint.get('step'):
                raise NMOSTestException(
                    test.FAIL(context + "Constraints implementations MUST not result in widening "
                              + "the constraints defined in previous levels: "
                              + "step constraint: " + str(constraint.get('step'))
                              + ", override step constraint: " + str(override_constraint.get('step'))))

        # is this a string constraint
        if 'maxCharacters' in constraint or 'pattern' in constraint:
            self.check_constraints_hierarchy["checked"] = True

            if self._xor_constraint(constraint.get('maxCharacters'), override_constraint.get('maxCharacters')) \
                    or self._xor_constraint(constraint.get('pattern'), override_constraint.get('pattern')):
                raise NMOSTestException(
                    test.FAIL(context + "Constraints implementations MUST fully override the previous level: "
                              + "constraint: " + str(constraint) + ", override_constraint: "
                              + str(override_constraint)))
            if constraint.get('maxCharacters') \
                    and override_constraint.get('maxCharacters') > constraint.get('maxCharacters'):
                raise NMOSTestException(
                    test.FAIL(context + "Constraints implementations MUST not result in widening "
                              + "the constraints defined in previous levels: "
                              + "maxCharacters constraint: " + str(constraint.get('maxCharacters'))
                              + ", override maxCharacters constraint: "
                              + str(override_constraint.get('maxCharacters'))))
            # Hmm, difficult to determine whether an overridden regex pattern is widening the constraint
            # so rule of thumb here is that a shorter pattern is less constraining that a longer pattern
            if constraint.get('pattern') and len(override_constraint.get('pattern')) < len(constraint.get('pattern')):
                raise NMOSTestException(
                    test.FAIL(context + "Constraints implementations MUST not result in widening "
                              + "the constraints defined in previous levels: "
                              + "pattern constraint: " + str(constraint.get('pattern'))
                              + ", override pattern constraint: " + str(override_constraint.get('pattern'))))

    def _check_constraints_hierarchy(self, test, class_property, datatype_descriptors, object_runtime_constraints,
                                     context):
        datatype_constraints = None
        runtime_constraints = None
        # Level 0: Datatype constraints
        if class_property.get('typeName'):
            if datatype_descriptors.get(class_property['typeName']):
                datatype_constraints = datatype_descriptors.get(class_property['typeName']).get('constraints')
            else:
                raise NMOSTestException(test.FAIL(context + "Unknown data type: " + class_property['typeName']))
        else:
            raise NMOSTestException(test.FAIL(context + "Missing data type from class descriptor"))

        # Level 1: Property constraints
        property_constraints = class_property.get('constraints')
        # Level 3: Runtime constraints
        if object_runtime_constraints:
            for object_runtime_constraint in object_runtime_constraints:
                if object_runtime_constraint['propertyId']['level'] == class_property['id']['level'] and \
                        object_runtime_constraint['propertyId']['index'] == class_property['id']['index']:
                    runtime_constraints = object_runtime_constraint

        if datatype_constraints and property_constraints:
            self._check_constraint_override(test, datatype_constraints, property_constraints,
                                            context + "datatype constraints overridden by property constraints: ")

        if datatype_constraints and runtime_constraints:
            self._check_constraint_override(test, datatype_constraints, runtime_constraints,
                                            context + "datatype constraints overridden by runtime constraints: ")

        if property_constraints and runtime_constraints:
            self._check_constraint_override(test, property_constraints, runtime_constraints,
                                            context + "property constraints overridden by runtime constraints: ")

    def _check_constraints(self, test, block, context=""):
        context += block.role

        class_manager = self.ms05_utils.get_class_manager(test)

        block_member_descriptors = self.ms05_utils.get_member_descriptors(test, recurse=False,
                                                                          oid=block.oid, role_path=block.role_path)

        for descriptor in block_member_descriptors:
            class_descriptor = self.ms05_utils.get_control_class(test,
                                                                 descriptor['classId'],
                                                                 include_inherited=True,
                                                                 oid=class_manager.oid,
                                                                 role_path=class_manager.role_path)

            # Get runtime property constraints
            # will set error on device_model_metadata on failure
            role_path = self.ms05_utils.create_role_path(block.role_path, descriptor['role'])
            object_runtime_constraints = \
                self.get_property_value(test,
                                        NcObjectProperties.RUNTIME_PROPERTY_CONSTRAINTS.value,
                                        context,
                                        oid=descriptor['oid'],
                                        role_path=role_path)

            for class_property in class_descriptor.get('properties'):
                if class_property['isReadOnly']:
                    continue
                try:
                    self._check_constraints_hierarchy(test, class_property, class_manager.datatype_descriptors,
                                                      object_runtime_constraints,
                                                      context + ": " + class_descriptor['name'] + ": "
                                                      + class_property['name'] + ": ")
                except NMOSTestException as e:
                    self.check_constraints_hierarchy["error"] = True
                    self.check_constraints_hierarchy["error_msg"] += str(e.args[0].detail) + "; "

        # Recurse through the child blocks
        for child_object in block.child_objects:
            if type(child_object) is NcBlock:
                self._check_constraints(test, child_object, context + ": ")

    def test_ms05_24(self, test):
        """Constraints: check constraints hierarchy"""

        # When using multiple levels of constraints implementations MUST fully override the previous level
        # and this MUST not result in widening the constraints defined in previous levels
        # https://specs.amwa.tv/ms-05-02/branches/v1.0.x/docs/Constraints.html

        device_model = self.ms05_utils.query_device_model(test)

        self._check_constraints(test, device_model)

        if self.device_model_metadata["error"]:
            return test.FAIL(self.device_model_metadata["error_msg"])

        if self.check_constraints_hierarchy["error"]:
            return test.FAIL(self.check_constraints_hierarchy["error_msg"],
                             "https://specs.amwa.tv/ms-05-02/branches/v1.0.x/docs/Constraints.html")

        if not self.check_constraints_hierarchy["checked"]:
            return test.UNCLEAR("No constraints hierarchy found.")

        return test.PASS()

    def test_ms05_25(self, test):
        """MS-05-02 Error: Node handles read only error"""
        # Devices MUST use the exact status code from NcMethodStatus when errors are encountered
        # for the following scenarios...
        # https://specs.amwa.tv/ms-05-02/releases/v1.0.0/docs/Framework.html#ncmethodresult

        try:
            self.ms05_utils.set_property(test, NcObjectProperties.ROLE.value, "ROLE IS READ ONLY",
                                         oid=self.ms05_utils.ROOT_BLOCK_OID, role_path=["root"])

            return test.FAIL("Read only properties error expected.",
                             f"https://specs.amwa.tv/ms-05-02/branches/{self.apis[MS05_API_KEY]['spec_branch']}"
                             + "/docs/Framework.html#ncmethodresult")

        except NMOSTestException as e:
            error_msg = e.args[0].detail

            # Expecting an error status dictionary
            if not isinstance(error_msg, dict):
                # It must be some other type of error so re-throw
                raise e

            if not error_msg.get('status'):
                return test.FAIL("No status returned: " + str(error_msg))

            if error_msg['status'] != NcMethodStatus.Readonly.value:
                return test.WARNING(f"Unexpected status. Expected: {NcMethodStatus.Readonly.name}"
                                    + f" ({str(NcMethodStatus.Readonly)})"
                                    + f", actual: {NcMethodStatus(error_msg['status']).name}"
                                    + f" ({str(error_msg['status'])})",
                                    + "https://specs.amwa.tv/ms-05-02/branches/"
                                    + f"{self.apis[MS05_API_KEY]['spec_branch']}"
                                    + "/docs/Framework.html#ncmethodresult")

            return test.PASS()

    def test_ms05_26(self, test):
        """MS-05-02 Error: Node handles GetSequence index out of bounds error"""
        # Devices MUST use the exact status code from NcMethodStatus when errors are encountered
        # for the following scenarios...
        # https://specs.amwa.tv/ms-05-02/releases/v1.0.0/docs/Framework.html#ncmethodresult

        try:
            length = self.ms05_utils.get_sequence_length(test,
                                                         NcBlockProperties.MEMBERS.value,
                                                         oid=self.ms05_utils.ROOT_BLOCK_OID,
                                                         role_path=["root"])
            out_of_bounds_index = length + 10

            self.ms05_utils.get_sequence_item(test,
                                              NcBlockProperties.MEMBERS.value,
                                              out_of_bounds_index,
                                              oid=self.ms05_utils.ROOT_BLOCK_OID,
                                              role_path=["root"])

            return test.FAIL("Sequence out of bounds error expected.",
                             f"https://specs.amwa.tv/ms-05-02/branches/{self.apis[MS05_API_KEY]['spec_branch']}"
                             + "/docs/Framework.html#ncmethodresult")

        except NMOSTestException as e:
            error_msg = e.args[0].detail

            # Expecting an error status dictionary
            if not isinstance(error_msg, dict):
                # It must be some other type of error so re-throw
                raise e

            if not error_msg.get('status'):
                return test.FAIL("No status returned: " + str(error_msg))

            if error_msg['status'] != NcMethodStatus.IndexOutOfBounds.value:
                return test.WARNING(f"Unexpected status. Expected: {NcMethodStatus.IndexOutOfBounds.name}"
                                    + f" ({str(NcMethodStatus.IndexOutOfBounds)})"
                                    + f", actual: {NcMethodStatus(error_msg['status']).name}"
                                    + f" ({str(error_msg['status'])})",
                                    + "https://specs.amwa.tv/ms-05-02/branches/"
                                    + f"{self.apis[MS05_API_KEY]['spec_branch']}"
                                    + "/docs/Framework.html#ncmethodresult")

            return test.PASS()
