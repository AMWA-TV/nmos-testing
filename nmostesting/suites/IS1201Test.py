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

import json
import os
import time

from itertools import product
from jsonschema import ValidationError, SchemaError

from ..Config import WS_MESSAGE_TIMEOUT
from ..GenericTest import GenericTest, NMOSTestException
from ..IS12Utils import IS12Utils, NcObject, NcMethodStatus, NcBlockProperties,  NcPropertyChangeType,\
    NcObjectMethods, NcObjectProperties, NcObjectEvents, NcClassManagerProperties, NcDeviceManagerProperties,\
    StandardClassIds, NcClassManager, NcBlock
from ..TestHelper import load_resolved_schema
from ..TestResult import Test

NODE_API_KEY = "node"
CONTROL_API_KEY = "ncp"
MS05_API_KEY = "controlframework"
FEATURE_SETS_KEY = "featuresets"


class IS1201Test(GenericTest):

    def __init__(self, apis, **kwargs):
        # Remove the RAML key to prevent this test suite from auto-testing IS-04 API
        apis[NODE_API_KEY].pop("raml", None)
        GenericTest.__init__(self, apis, **kwargs)
        self.node_url = self.apis[NODE_API_KEY]["url"]
        self.ncp_url = self.apis[CONTROL_API_KEY]["url"]
        self.is12_utils = IS12Utils(self.node_url,
                                    self.apis[CONTROL_API_KEY]["spec_path"],
                                    self.apis[CONTROL_API_KEY]["spec_branch"])
        self.load_reference_resources()
        self.device_model = None

    def set_up_tests(self):
        self.unique_roles_error = False
        self.unique_oids_error = False
        self.managers_are_singletons_error = False
        self.managers_members_root_block_error = False
        self.device_model_checked = False
        self.organization_metadata = {"checked": False, "error": False, "error_msg": ""}
        self.touchpoints_metadata = {"checked": False, "error": False, "error_msg": ""}
        self.get_sequence_item_metadata = {"checked": False, "error": False, "error_msg": ""}
        self.get_sequence_length_metadata = {"checked": False, "error": False, "error_msg": ""}

        self.oid_cache = []

    def tear_down_tests(self):
        # Clean up Websocket resources
        self.is12_utils.close_ncp_websocket()

    def execute_tests(self, test_names):
        """Perform tests defined within this class"""
        # Override to allow 'auto' testing of MS-05 types and classes

        for test_name in test_names:
            if test_name in ["auto", "all"] and not self.disable_auto:
                # Validate all standard datatypes and classes advertised by the Class Manager
                try:
                    self.result += self.auto_tests()
                except NMOSTestException as e:
                    self.result.append(e.args[0])
            self.execute_test(test_name)

    def load_model_descriptors(self, descriptor_paths):
        descriptors = {}
        for descriptor_path in descriptor_paths:
            for filename in os.listdir(descriptor_path):
                name, extension = os.path.splitext(filename)
                if extension == ".json":
                    with open(os.path.join(descriptor_path, filename), 'r') as json_file:
                        descriptors[name] = json.load(json_file)

        return descriptors

    def generate_json_schemas(self, datatype_descriptors, schema_path):
        """Generate datatype schemas from datatype descriptors"""
        datatype_schema_names = []
        base_schema_path = os.path.abspath(schema_path)
        if not os.path.exists(base_schema_path):
            os.makedirs(base_schema_path)

        for name, descriptor in datatype_descriptors.items():
            json_schema = self.is12_utils.descriptor_to_schema(descriptor)
            with open(os.path.join(base_schema_path, name + '.json'), 'w') as output_file:
                json.dump(json_schema, output_file, indent=4)
                datatype_schema_names.append(name)

        # Load resolved MS-05 datatype schemas
        datatype_schemas = {}
        for name in datatype_schema_names:
            datatype_schemas[name] = load_resolved_schema(schema_path, name + '.json', path_prefix=False)

        return datatype_schemas

    def load_reference_resources(self):
        """Load datatype and control class decriptors and create datatype JSON schemas"""
        # Calculate paths to MS-05 descriptors
        # including Feature Sets specified as additional_paths in test definition
        spec_paths = [os.path.join(self.apis[FEATURE_SETS_KEY]["spec_path"], path)
                      for path in self.apis[FEATURE_SETS_KEY]["repo_paths"]]
        spec_paths.append(self.apis[MS05_API_KEY]["spec_path"])

        datatype_paths = []
        classes_paths = []
        for spec_path in spec_paths:
            datatype_path = os.path.abspath(os.path.join(spec_path, 'models/datatypes/'))
            if os.path.exists(datatype_path):
                datatype_paths.append(datatype_path)
            classes_path = os.path.abspath(os.path.join(spec_path, 'models/classes/'))
            if os.path.exists(classes_path):
                classes_paths.append(classes_path)

        # Load class and datatype descriptors
        self.reference_class_descriptors = self.load_model_descriptors(classes_paths)

        # Load MS-05 datatype descriptors
        self.reference_datatype_descriptors = self.load_model_descriptors(datatype_paths)

        # Generate MS-05 datatype schemas from MS-05 datatype descriptors
        self.datatype_schemas = self.generate_json_schemas(
            datatype_descriptors=self.reference_datatype_descriptors,
            schema_path=os.path.join(self.apis[CONTROL_API_KEY]["spec_path"], 'APIs/schemas/'))

    def create_ncp_socket(self, test):
        """Create a WebSocket client connection to Node under test. Raises NMOSTestException on error"""
        self.is12_utils.open_ncp_websocket(test, self.apis[CONTROL_API_KEY]["url"])

    def validate_descriptor(self, test, reference, descriptor, context=""):
        """Validate descriptor against reference descriptor. Raises NMOSTestException on error"""
        non_normative_keys = ['description']

        if isinstance(reference, dict):
            reference_keys = set(reference.keys())
            descriptor_keys = set(descriptor.keys())

            # compare the keys to see if any extra/missing
            key_diff = (set(reference_keys) | set(descriptor_keys)) - (set(reference_keys) & set(descriptor_keys))
            if len(key_diff) > 0:
                error_description = "Missing keys " if set(key_diff) <= set(reference_keys) else "Additional keys "
                raise NMOSTestException(test.FAIL(context + error_description + str(key_diff)))
            for key in reference_keys:
                if key in non_normative_keys and not isinstance(reference[key], dict):
                    continue
                # Check for class ID
                if key == 'classId' and isinstance(reference[key], list):
                    if reference[key] != descriptor[key]:
                        raise NMOSTestException(test.FAIL(context + "Unexpected ClassId. Expected: "
                                                          + str(reference[key])
                                                          + " actual: " + str(descriptor[key])))
                else:
                    self.validate_descriptor(test, reference[key], descriptor[key], context=context + key + "->")
        elif isinstance(reference, list):
            # Convert to dict and validate
            references = {item['name']: item for item in reference}
            descriptors = {item['name']: item for item in descriptor}

            return self.validate_descriptor(test, references, descriptors, context)
        else:
            if reference != descriptor:
                raise NMOSTestException(test.FAIL(context + 'Expected value: '
                                                  + str(reference)
                                                  + ', actual value: '
                                                  + str(descriptor)))
        return

    def _validate_schema(self, test, payload, schema, context=""):
        """Delegates to validate_schema. Raises NMOSTestExceptions on error"""
        try:
            # Validate the JSON schema is correct
            self.validate_schema(payload, schema)
        except ValidationError as e:
            raise NMOSTestException(test.FAIL(context + "Schema validation error: " + e.message))
        except SchemaError as e:
            raise NMOSTestException(test.FAIL(context + "Schema error: " + e.message))

        return

    def get_class_manager_descriptors(self, test, class_manager_oid, property_id):
        response = self.is12_utils.get_property(test, class_manager_oid, property_id)

        # Create descriptor dictionary from response array
        # Use classId as key if present, otherwise use name
        def key_lambda(classId, name): return ".".join(map(str, classId)) if classId else name
        descriptors = {key_lambda(r.get('classId'), r['name']): r for r in response}

        return descriptors

    def validate_model_definitions(self, descriptors, schema_name, reference_descriptors):
        """Validate class manager model definitions against reference model descriptors. Returns [test result array]"""
        results = list()

        reference_descriptor_keys = sorted(reference_descriptors.keys())

        for key in reference_descriptor_keys:
            test = Test("Validate " + str(key) + " definition", "auto_" + str(key))
            try:
                if descriptors.get(key):
                    descriptor = descriptors[key]

                    # Validate the JSON schema is correct
                    self._validate_schema(test, descriptor, self.datatype_schemas[schema_name])

                    # Validate the descriptor is correct
                    self.validate_descriptor(test, reference_descriptors[key], descriptor)

                    results.append(test.PASS())
                else:
                    results.append(test.UNCLEAR("Not Implemented"))
            except NMOSTestException as e:
                results.append(e.args[0])

        return results

    def query_device_model(self, test):
        self.create_ncp_socket(test)
        if not self.device_model:
            self.device_model = self.nc_object_factory(test,
                                                       StandardClassIds.NCBLOCK.value,
                                                       self.is12_utils.ROOT_BLOCK_OID,
                                                       "root")
        return self.device_model

    def query_class_manager(self, test):
        """Query class manager to use as source of ground truths"""

        self.create_ncp_socket(test)
        device_model = self.query_device_model(test)

        return device_model.get_manager(test,
                                        self.apis[CONTROL_API_KEY]["spec_branch"],
                                        StandardClassIds.NCCLASSMANAGER.value)

    def query_device_manager(self, test):
        """Query class manager to use as source of ground truths"""

        self.create_ncp_socket(test)
        device_model = self.query_device_model(test)

        return device_model.get_manager(test,
                                        self.apis[CONTROL_API_KEY]["spec_branch"],
                                        StandardClassIds.NCDEVICEMANAGER.value)

    def auto_tests(self):
        """Automatically validate all standard datatypes and control classes. Returns [test result array]"""
        # Referencing the Google sheet
        # MS-05-02 (75)  Model definitions
        results = list()
        test = Test("Initialize auto tests", "auto_init")

        self.create_ncp_socket(test)

        class_manager = self.query_class_manager(test)

        results += self.validate_model_definitions(class_manager.class_descriptors,
                                                   'NcClassDescriptor',
                                                   self.reference_class_descriptors)

        results += self.validate_model_definitions(class_manager.datatype_descriptors,
                                                   'NcDatatypeDescriptor',
                                                   self.reference_datatype_descriptors)
        return results

    def test_01(self, test):
        """Control Endpoint: Node under test advertises IS-12 control endpoint matching API under test"""
        # Referencing the Google sheet
        # IS-12 (1) Control endpoint advertised in Node endpoint's Device controls array

        control_type = "urn:x-nmos:control:ncp/" + self.apis[CONTROL_API_KEY]["version"]
        return self.is12_utils.do_test_device_control(
            test,
            self.node_url,
            control_type,
            self.ncp_url,
            self.authorization
        )

    def test_02(self, test):
        """WebSocket: endpoint successfully opened"""
        # Referencing the Google sheet
        # IS-12 (2) WebSocket successfully opened on advertised urn:x-nmos:control:ncp endpoint

        self.create_ncp_socket(test)

        return test.PASS()

    def test_03(self, test):
        """WebSocket: socket is kept open until client closes"""
        # Referencing the Google sheet
        # IS-12 (3) Socket is kept open until client closes

        self.create_ncp_socket(test)

        # Ensure WebSocket remains open
        start_time = time.time()
        while time.time() < start_time + WS_MESSAGE_TIMEOUT:
            if not self.is12_utils.ncp_websocket.is_open():
                return test.FAIL("Node failed to keep WebSocket open")
            time.sleep(0.2)

        return test.PASS()

    def test_04(self, test):
        """Device Model: Root Block exists with correct oid and role"""
        # Referencing the Google sheet
        # MS-05-02 (44)	Root Block must exist
        # MS-05-02 (45) Verify oID and role of Root Block
        # https://specs.amwa.tv/ms-05-02/branches/v1.0-dev/docs/Blocks.html

        self.create_ncp_socket(test)

        role = self.is12_utils.get_property(test,
                                            self.is12_utils.ROOT_BLOCK_OID,
                                            NcObjectProperties.ROLE.value)

        if role != "root":
            return test.FAIL("Unexpected role in Root Block: " + str(role),
                             "https://specs.amwa.tv/ms-05-02/branches/{}"
                             "/docs/Blocks.html"
                             .format(self.apis[CONTROL_API_KEY]["spec_branch"]))

        return test.PASS()

    def validate_property_type(self, test, value, type, is_nullable, datatype_schemas, context=""):
        if value is None:
            if is_nullable:
                return
            else:
                raise NMOSTestException(test.FAIL(context + "Non-nullable property set to null."))

        if self.is12_utils.primitive_to_python_type(type):
            # Special case: if this is a floating point value it
            # can be intepreted as an int in the case of whole numbers
            # e.g. 0.0 -> 0, 1.0 -> 1
            if self.is12_utils.primitive_to_python_type(type) == float and isinstance(value, int):
                return

            if not isinstance(value, self.is12_utils.primitive_to_python_type(type)):
                raise NMOSTestException(test.FAIL(context + str(value) + " is not of type " + str(type)))
        else:
            self._validate_schema(test, value, datatype_schemas[type], context)

        return

    def check_get_sequence_item(self, test, oid, sequence_values, property_metadata, context=""):
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
                value = self.is12_utils.get_sequence_item(test, oid, property_metadata['id'], sequence_index)
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

    def check_get_sequence_length(self, test, oid, sequence_values, property_metadata, context=""):
        if sequence_values is None and not property_metadata["isNullable"]:
            self.get_sequence_length_metadata["error"] = True
            self.get_sequence_length_metadata["error_msg"] += \
                context + property_metadata["name"] + ": Non-nullable property set to null, "
            return

        try:
            self.get_sequence_length_metadata["checked"] = True
            length = self.is12_utils.get_sequence_length(test, oid, property_metadata['id'])

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

    def check_sequence_methods(self, test, oid, sequence_values, property_metadata, context=""):
        """Check that sequence manipulation methods work correctly"""
        self.check_get_sequence_item(test, oid, sequence_values, property_metadata, context)
        self.check_get_sequence_length(test, oid, sequence_values, property_metadata, context)

    def validate_object_properties(self, test, reference_class_descriptor, oid, datatype_schemas, context):
        for class_property in reference_class_descriptor['properties']:
            response = self.is12_utils.get_property(test, oid, class_property['id'])

            # validate property type
            if class_property['isSequence']:
                for property_value in response:
                    self.validate_property_type(test,
                                                property_value,
                                                class_property['typeName'],
                                                class_property['isNullable'],
                                                datatype_schemas,
                                                context=context + class_property["typeName"]
                                                + ": " + class_property["name"] + ": ")
                self.check_sequence_methods(test,
                                            oid,
                                            response,
                                            class_property,
                                            context=context)
            else:
                self.validate_property_type(test,
                                            response,
                                            class_property['typeName'],
                                            class_property['isNullable'],
                                            datatype_schemas,
                                            context=context + class_property["typeName"]
                                            + class_property["name"] + ": ")
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
        base_id = self.is12_utils.get_base_class_id(class_id)
        base_class_name = class_descriptors[base_id]["name"]

        # manager checks
        if self.is12_utils.is_manager(class_id):
            if owner != self.is12_utils.ROOT_BLOCK_OID:
                self.managers_members_root_block_error = True
            if base_class_name in manager_cache:
                self.managers_are_singletons_error = True
            else:
                manager_cache.append(base_class_name)

    def check_touchpoints(self, test, oid, datatype_schemas, context):
        """Touchpoint checks"""
        touchpoints = self.is12_utils.get_property(test,
                                                   oid,
                                                   NcObjectProperties.TOUCHPOINTS.value)
        if touchpoints is not None:
            self.touchpoints_metadata["checked"] = True
            try:
                for touchpoint in touchpoints:
                    schema = datatype_schemas["NcTouchpointNmos"] \
                        if touchpoint["contextNamespace"] == "x-nmos" \
                        else datatype_schemas["NcTouchpointNmosChannelMapping"]
                    self._validate_schema(test,
                                          touchpoint,
                                          schema,
                                          context=context + schema["title"] + ": ")
            except NMOSTestException as e:
                self.touchpoints_metadata["error"] = True
                self.touchpoints_metadata["error_msg"] = context + str(e.args[0].detail)

    def check_block(self, test, block, class_descriptors, datatype_schemas, context=""):
        for child_object in block.child_objects:
            # If this child object is a Block, recurse
            if type(child_object) is NcBlock:
                self.check_block(test,
                                 child_object,
                                 class_descriptors,
                                 datatype_schemas,
                                 context=context + str(child_object.role) + ': ')
        role_cache = []
        manager_cache = []
        for descriptor in block.member_descriptors:
            self._validate_schema(test,
                                  descriptor,
                                  datatype_schemas["NcBlockMemberDescriptor"],
                                  context="NcBlockMemberDescriptor: ")

            self.check_unique_roles(descriptor['role'], role_cache)
            self.check_unique_oid(descriptor['oid'])
            # check for non-standard classes
            if self.is12_utils.is_non_standard_class(descriptor['classId']):
                self.organization_metadata["checked"] = True
            self.check_manager(descriptor['classId'], descriptor["owner"], class_descriptors, manager_cache)
            self.check_touchpoints(test, descriptor['oid'], datatype_schemas,
                                   context=context + str(descriptor['role']) + ': ')

            class_identifier = ".".join(map(str, descriptor['classId']))
            if class_identifier:
                self.validate_object_properties(test,
                                                class_descriptors[class_identifier],
                                                descriptor['oid'],
                                                datatype_schemas,
                                                context=context + str(descriptor['role']) + ': ')
            else:
                # Not a standard or non-standard class
                self.organization_metadata["error"] = True
                self.organization_metadata["error_msg"] = str(descriptor['role']) + ': ' \
                    + "Non-standard class id does not contain authority key: " \
                    + str(descriptor['classId']) + ". "

    def check_device_model(self, test):
        if not self.device_model_checked:
            self.create_ncp_socket(test)
            class_manager = self.query_class_manager(test)
            device_model = self.query_device_model(test)

            # Create JSON schemas for the queried datatypes
            datatype_schemas = self.generate_json_schemas(
                datatype_descriptors=class_manager.datatype_descriptors,
                schema_path=os.path.join(self.apis[CONTROL_API_KEY]["spec_path"], 'APIs/tmp_schemas/'))

            self.check_block(test,
                             device_model,
                             class_manager.class_descriptors,
                             datatype_schemas)

            self.device_model_checked = True
        return

    def nc_object_factory(self, test, class_id, oid, role):
        """Create NcObject or NcBlock based on class_id"""
        # Check class id to determine if this is a block
        if len(class_id) > 1 and class_id[0] == 1 and class_id[1] == 1:
            member_descriptors = self.is12_utils.get_property(test, oid, NcBlockProperties.MEMBERS.value)
            nc_block = NcBlock(class_id, oid, role, member_descriptors)

            for m in member_descriptors:
                nc_block.add_child_object(self.nc_object_factory(test, m["classId"], m["oid"], m["role"]))
            return nc_block
        else:
            # Check to determine if this is a Class Manager
            if len(class_id) > 2 and class_id[0] == 1 and class_id[1] == 3 and class_id[2] == 2:
                class_descriptors = self.get_class_manager_descriptors(test,
                                                                       oid,
                                                                       NcClassManagerProperties.CONTROL_CLASSES.value)
                datatype_descriptors = self.get_class_manager_descriptors(test,
                                                                          oid,
                                                                          NcClassManagerProperties.DATATYPES.value)
                return NcClassManager(class_id, oid, role, class_descriptors, datatype_descriptors)
            return NcObject(class_id, oid, role)

    def test_05(self, test):
        """Device Model: Device Model is correct according to classes and datatypes advertised by Class Manager"""
        # Referencing the Google sheet
        # MS-05-02 (34) All workers MUST inherit from NcWorker
        # MS-05-02 (35) All managers MUST inherit from NcManager

        self.check_device_model(test)

        return test.PASS()

    def test_06(self, test):
        """Device Model: roles are unique within a containing Block"""
        # Referencing the Google sheet
        # MS-05-02 (59) The role of an object MUST be unique within its containing Block.
        # https://specs.amwa.tv/ms-05-02/branches/v1.0-dev/docs/NcObject.html

        try:
            self.check_device_model(test)
        except NMOSTestException as e:
            # Couldn't validate model so can't perform test
            return test.UNCLEAR(e.args[0].detail, e.args[0].link)

        if self.unique_roles_error:
            return test.FAIL("Roles must be unique. ",
                             "https://specs.amwa.tv/ms-05-02/branches/{}"
                             "/docs/NcObject.html"
                             .format(self.apis[MS05_API_KEY]["spec_branch"]))

        return test.PASS()

    def test_07(self, test):
        """Device Model: oids are globally unique"""
        # Referencing the Google sheet
        # MS-05-02 (60) Object ids (oid property) MUST uniquely identity objects in the device model.
        # https://specs.amwa.tv/ms-05-02/branches/v1.0-dev/docs/NcObject.html

        try:
            self.check_device_model(test)
        except NMOSTestException as e:
            # Couldn't validate model so can't perform test
            return test.UNCLEAR(e.args[0].detail, e.args[0].link)

        if self.unique_oids_error:
            return test.FAIL("Oids must be unique. ",
                             "https://specs.amwa.tv/ms-05-02/branches/{}"
                             "/docs/NcObject.html"
                             .format(self.apis[MS05_API_KEY]["spec_branch"]))

        return test.PASS()

    def test_08(self, test):
        """Device Model: non-standard classes contain an authority key"""
        # Referencing the Google sheet
        # MS-05-02 (72) Non-standard Classes NcClassId
        # MS-05-02 (73) Organization Identifier
        # For organizations which own a unique CID or OUI the authority key MUST be the organization
        # identifier as an integer which MUST be negated.
        # For organizations which do not own a unique CID or OUI the authority key MUST be 0
        # https://specs.amwa.tv/ms-05-02/branches/v1.0-dev/docs/Managers.html

        try:
            self.check_device_model(test)
        except NMOSTestException as e:
            # Couldn't validate model so can't perform test
            return test.UNCLEAR(e.args[0].detail, e.args[0].link)

        if self.organization_metadata["error"]:
            return test.FAIL(self.organization_metadata["error_msg"],
                             "https://specs.amwa.tv/ms-05-02/branches/{}"
                             "/docs/Framework.html#ncclassid"
                             .format(self.apis[MS05_API_KEY]["spec_branch"]))

        if not self.organization_metadata["checked"]:
            return test.UNCLEAR("No non-standard classes found.")

        return test.PASS()

    def test_09(self, test):
        """Device Model: touchpoint datatypes are correct"""
        # Referencing the Google sheet
        # MS-05-02 (56) For general NMOS contexts (IS-04, IS-05 and IS-07) the NcTouchpointNmos datatype MUST be used
        # which has a resource of type NcTouchpointResourceNmos.
        # For IS-08 Audio Channel Mapping the NcTouchpointResourceNmosChannelMapping datatype MUST be used
        # https://specs.amwa.tv/ms-05-02/branches/v1.0-dev/docs/NcObject.html#touchpoints

        try:
            self.check_device_model(test)
        except NMOSTestException as e:
            # Couldn't validate model so can't perform test
            return test.UNCLEAR(e.args[0].detail, e.args[0].link)

        if self.touchpoints_metadata["error"]:
            return test.FAIL(self.touchpoints_metadata["error_msg"],
                             "https://specs.amwa.tv/ms-05-02/branches/{}"
                             "/docs/NcObject.html#touchpoints"
                             .format(self.apis[MS05_API_KEY]["spec_branch"]))

        if not self.touchpoints_metadata["checked"]:
            return test.UNCLEAR("No Touchpoints found.")
        return test.PASS()

    def test_10(self, test):
        """Managers: managers are members of the Root Block"""
        # Referencing the Google sheet
        # MS-05-02 (36) All managers MUST always exist as members in the Root Block and have a fixed role.
        # https://specs.amwa.tv/ms-05-02/branches/v1.0-dev/docs/Managers.html

        try:
            self.check_device_model(test)
        except NMOSTestException as e:
            # Couldn't validate model so can't perform test
            return test.UNCLEAR(e.args[0].detail, e.args[0].link)

        if self.managers_members_root_block_error:
            return test.FAIL("Managers must be members of Root Block. ",
                             "https://specs.amwa.tv/ms-05-02/branches/{}"
                             "/docs/Managers.html"
                             .format(self.apis[MS05_API_KEY]["spec_branch"]))

        return test.PASS()

    def test_11(self, test):
        """Managers: managers are singletons"""
        # Referencing the Google sheet
        # MS-05-02 (63) Managers are singleton (MUST only be instantiated once) classes.
        # https://specs.amwa.tv/ms-05-02/branches/v1.0-dev/docs/Managers.html

        try:
            self.check_device_model(test)
        except NMOSTestException as e:
            # Couldn't validate model so can't perform test
            return test.UNCLEAR(e.args[0].detail, e.args[0].link)

        if self.managers_are_singletons_error:
            return test.FAIL("Managers must be singleton classes. ",
                             "https://specs.amwa.tv/ms-05-02/branches/{}"
                             "/docs/Managers.html"
                             .format(self.apis[MS05_API_KEY]["spec_branch"]))

        return test.PASS()

    def test_12(self, test):
        """Managers: Class Manager exists with correct role"""
        # Referencing the Google sheet
        # MS-05-02 (40) Class manager exists in root

        spec_link = "https://specs.amwa.tv/ms-05-02/branches/{}/docs/Managers.html"\
            .format(self.apis[CONTROL_API_KEY]["spec_branch"])

        class_manager = self.query_class_manager(test)

        class_id_str = ".".join(map(str, StandardClassIds.NCCLASSMANAGER.value))
        class_descriptor = self.reference_class_descriptors[class_id_str]

        if class_manager.role != class_descriptor["fixedRole"]:
            return test.FAIL("Class Manager MUST have a role of ClassManager.", spec_link)

        return test.PASS()

    def test_13(self, test):
        """Managers: Device Manager exists with correct Role"""
        # Referencing the Google sheet
        # MS-05-02 (37) A minimal device implementation MUST have a device manager in the Root Block.

        spec_link = "https://specs.amwa.tv/ms-05-02/branches/{}/docs/Managers.html"\
            .format(self.apis[CONTROL_API_KEY]["spec_branch"])

        device_manager = self.query_device_manager(test)

        class_id_str = ".".join(map(str, StandardClassIds.NCDEVICEMANAGER.value))
        class_descriptor = self.reference_class_descriptors[class_id_str]

        if device_manager.role != class_descriptor["fixedRole"]:
            return test.FAIL("Device Manager MUST have a role of DeviceManager.", spec_link)

        # Check MS-05-02 Version
        property_id = NcDeviceManagerProperties.NCVERSION.value

        version = self.is12_utils.get_property(test, device_manager.oid, property_id)

        if self.is12_utils.compare_api_version(version, self.apis[MS05_API_KEY]["version"]):
            return test.FAIL("Unexpected version. Expected: "
                             + self.apis[MS05_API_KEY]["version"]
                             + ". Actual: " + str(version))
        return test.PASS()

    def test_14(self, test):
        """Class Manager: GetControlClass method is correct"""
        # Referencing the Google sheet
        # MS-05-02 (93)  Where the functionality of a device uses control classes and datatypes listed in this
        # specification it MUST comply with the model definitions published

        class_manager = self.query_class_manager(test)

        for _, class_descriptor in class_manager.class_descriptors.items():
            for include_inherited in [False, True]:
                actual_descriptor = self.is12_utils.get_control_class(test,
                                                                      class_manager.oid,
                                                                      class_descriptor["classId"],
                                                                      include_inherited)
                expected_descriptor = class_manager.get_control_class(class_descriptor["classId"],
                                                                      include_inherited)
                self.validate_descriptor(test,
                                         expected_descriptor,
                                         actual_descriptor,
                                         context=str(class_descriptor["classId"]) + ": ")

        return test.PASS()

    def test_15(self, test):
        """Class Manager: GetDatatype method is correct"""
        # Referencing the Google sheet
        # MS-05-02 (94)  Where the functionality of a device uses control classes and datatypes listed in this
        # specification it MUST comply with the model definitions published

        class_manager = self.query_class_manager(test)

        for _, datatype_descriptor in class_manager.datatype_descriptors.items():
            for include_inherited in [False, True]:
                actual_descriptor = self.is12_utils.get_datatype(test,
                                                                 class_manager.oid,
                                                                 datatype_descriptor["name"],
                                                                 include_inherited)
                expected_descriptor = class_manager.get_datatype(datatype_descriptor["name"],
                                                                 include_inherited)
                self.validate_descriptor(test,
                                         expected_descriptor,
                                         actual_descriptor,
                                         context=datatype_descriptor["name"] + ": ")

        return test.PASS()

    def test_16(self, test):
        """NcObject: Get and Set methods are correct"""
        # Referencing the Google sheet
        # MS-05-02 (39) Generic getter and setter. The value of any property of a control class MUST be retrievable
        # using the Get method.
        # https://specs.amwa.tv/ms-05-02/branches/v1.0-dev/docs/NcObject.html#generic-getter-and-setter

        link = "https://specs.amwa.tv/ms-05-02/branches/{}" \
               "/docs/NcObject.html#generic-getter-and-setter" \
               .format(self.apis[MS05_API_KEY]["spec_branch"])

        # Attempt to set labels
        self.create_ncp_socket(test)

        property_id = NcObjectProperties.USER_LABEL.value

        old_user_label = self.is12_utils.get_property(test, self.is12_utils.ROOT_BLOCK_OID, property_id)

        # Set user label
        new_user_label = "NMOS Testing Tool"

        self.is12_utils.set_property(test, self.is12_utils.ROOT_BLOCK_OID, property_id, new_user_label)

        # Check user label
        label = self.is12_utils.get_property(test, self.is12_utils.ROOT_BLOCK_OID, property_id)
        if label != new_user_label:
            if label == old_user_label:
                return test.FAIL("Unable to set user label", link)
            else:
                return test.FAIL("Unexpected user label: " + str(label), link)

        # Reset user label
        self.is12_utils.set_property(test, self.is12_utils.ROOT_BLOCK_OID, property_id, old_user_label)

        # Check user label
        label = self.is12_utils.get_property(test, self.is12_utils.ROOT_BLOCK_OID, property_id)
        if label != old_user_label:
            if label == new_user_label:
                return test.FAIL("Unable to set user label", link)
            else:
                return test.FAIL("Unexpected user label: " + str(label), link)

        return test.PASS()

    def test_17(self, test):
        """NcObject: GetSequenceItem method is correct"""
        # Referencing the Google sheet
        # MS-05-02 (76)  Where the functionality of a device uses control classes and datatypes listed in this
        # specification it MUST comply with the model definitions published

        try:
            self.check_device_model(test)
        except NMOSTestException as e:
            # Couldn't validate model so can't perform test
            return test.UNCLEAR(e.args[0].detail, e.args[0].link)

        if self.get_sequence_item_metadata["error"]:
            return test.FAIL(self.get_sequence_item_metadata["error_msg"])

        if not self.get_sequence_item_metadata["checked"]:
            return test.UNCLEAR("GetSequenceItem not tested.")

        return test.PASS()

    def test_18(self, test):
        """NcObject: SetSequenceItem method is correct"""
        # Referencing the Google sheet
        # MS-05-02 (77)  Where the functionality of a device uses control classes and datatypes listed in this
        # specification it MUST comply with the model definitions published

        return test.DISABLED()

    def test_19(self, test):
        """NcObject: AddSequenceItem method is correct"""
        # Referencing the Google sheet
        # MS-05-02 (78)  Where the functionality of a device uses control classes and datatypes listed in this
        # specification it MUST comply with the model definitions published

        return test.DISABLED()

    def test_20(self, test):
        """NcObject: RemoveSequenceItem method is correct"""
        # Referencing the Google sheet
        # MS-05-02 (79)  Where the functionality of a device uses control classes and datatypes listed in this
        # specification it MUST comply with the model definitions published

        return test.DISABLED()

    def test_21(self, test):
        """NcObject: GetSequenceLength method is correct"""
        # Referencing the Google sheet
        # MS-05-02 (80)  Where the functionality of a device uses control classes and datatypes listed in this
        # specification it MUST comply with the model definitions published

        try:
            self.check_device_model(test)
        except NMOSTestException as e:
            # Couldn't validate model so can't perform test
            return test.UNCLEAR(e.args[0].detail, e.args[0].link)

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

            queried_members = self.is12_utils.get_member_descriptors(test, block.oid, search_condition["recurse"])

            if len(queried_members) != len(expected_members):
                raise NMOSTestException(test.FAIL(context
                                                  + block.role
                                                  + ": Unexpected number of block members found. Expected: "
                                                  + str(len(expected_members)) + ", Actual: "
                                                  + str(len(queried_members))))

            expected_members_oids = [m["oid"] for m in expected_members]

            for queried_member in queried_members:
                self._validate_schema(test,
                                      queried_member,
                                      self.datatype_schemas["NcBlockMemberDescriptor"],
                                      context=context
                                      + block.role
                                      + ": NcBlockMemberDescriptor: ")

                if queried_member["oid"] not in expected_members_oids:
                    raise NMOSTestException(test.FAIL(context
                                                      + block.role
                                                      + ": Unsuccessful attempt to get member descriptors."))

    def test_22(self, test):
        """NcBlock: GetMemberDescriptors method is correct"""
        # Referencing the Google sheet
        # MS-05-02 (91)  Where the functionality of a device uses control classes and datatypes listed in this
        # specification it MUST comply with the model definitions published

        device_model = self.query_device_model(test)

        self.do_get_member_descriptors_test(test, device_model)

        return test.PASS()

    def do_find_member_by_path_test(self, test, block, context=""):
        # Recurse through the child blocks
        for child_object in block.child_objects:
            if type(child_object) is NcBlock:
                self.do_find_member_by_path_test(test, child_object, context + block.role + ": ")

        # Get ground truth role paths
        role_paths = block.get_role_paths()

        for role_path in role_paths:
            # Get ground truth data from local device model object tree
            expected_member = block.find_members_by_path(role_path)

            queried_members = self.is12_utils.find_members_by_path(test, block.oid, role_path)

            for queried_member in queried_members:
                self._validate_schema(test,
                                      queried_member,
                                      self.datatype_schemas["NcBlockMemberDescriptor"],
                                      context=context
                                      + block.role
                                      + ": NcBlockMemberDescriptor: ")

            if len(queried_members) != 1:
                raise NMOSTestException(test.FAIL(context
                                                  + block.role
                                                  + ": Incorrect member found by role path: " + str(role_path)))

            queried_member_oids = [m['oid'] for m in queried_members]

            if expected_member.oid not in queried_member_oids:
                raise NMOSTestException(test.FAIL(context
                                                  + block.role
                                                  + ": Unsuccessful attempt to find member by role path: "
                                                  + str(role_path)))

    def test_23(self, test):
        """NcBlock: FindMemberByPath method is correct"""
        # Referencing the Google sheet
        # MS-05-02 (52)  Where the functionality of a device uses control classes and datatypes listed in this
        # specification it MUST comply with the model definitions published

        device_model = self.query_device_model(test)

        # Recursively check each block in Device Model
        self.do_find_member_by_path_test(test, device_model)

        return test.PASS()

    def do_find_member_by_role_test(self, test, block, context=""):
        # Recurse through the child blocks
        for child_object in block.child_objects:
            if type(child_object) is NcBlock:
                self.do_find_member_by_role_test(test, child_object, context + block.role + ": ")

        role_paths = IS12Utils.sampled_list(block.get_role_paths())
        # Generate every combination of case_sensitive, match_whole_string and recurse
        truth_table = IS12Utils.sampled_list(list(product([False, True], repeat=3)))
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
                        self.is12_utils.find_members_by_role(test,
                                                             block.oid,
                                                             query_string,
                                                             case_sensitive=condition["case_sensitive"],
                                                             match_whole_string=condition["match_whole_string"],
                                                             recurse=condition["recurse"])

                    expected_results_oids = [m.oid for m in expected_results]

                    if len(actual_results) != len(expected_results):
                        raise NMOSTestException(test.FAIL(context
                                                          + block.role
                                                          + ": Expected "
                                                          + str(len(expected_results))
                                                          + ", but got "
                                                          + str(len(actual_results))))

                    for actual_result in actual_results:
                        if actual_result["oid"] not in expected_results_oids:
                            raise NMOSTestException(test.FAIL(context
                                                              + block.role
                                                              + ": Unexpected search result. "
                                                              + str(actual_result)))

    def test_24(self, test):
        """NcBlock: FindMembersByRole method is correct"""
        # Referencing the Google sheet
        # MS-05-02 (52)  Where the functionality of a device uses control classes and datatypes listed in this
        # specification it MUST comply with the model definitions published

        device_model = self.query_device_model(test)

        # Recursively check each block in Device Model
        self.do_find_member_by_role_test(test, device_model)

        return test.PASS()

    def do_find_members_by_class_id_test(self, test, block, context=""):
        # Recurse through the child blocks
        for child_object in block.child_objects:
            if type(child_object) is NcBlock:
                self.do_find_members_by_class_id_test(test, child_object, context + block.role + ": ")

        class_ids = [e.value for e in StandardClassIds]

        truth_table = IS12Utils.sampled_list(list(product([False, True], repeat=2)))
        search_conditions = []
        for state in truth_table:
            search_conditions += [{"include_derived": state[0], "recurse": state[1]}]

        for class_id in class_ids:
            for condition in search_conditions:
                # Recursively check each block in Device Model
                expected_results = block.find_members_by_class_id(class_id,
                                                                  condition["include_derived"],
                                                                  condition["recurse"])

                actual_results = self.is12_utils.find_members_by_class_id(test,
                                                                          block.oid,
                                                                          class_id,
                                                                          condition["include_derived"],
                                                                          condition["recurse"])

                expected_results_oids = [m.oid for m in expected_results]

                if len(actual_results) != len(expected_results):
                    raise NMOSTestException(test.FAIL(context
                                                      + block.role
                                                      + ": Expected "
                                                      + str(len(expected_results))
                                                      + ", but got "
                                                      + str(len(actual_results))))

                for actual_result in actual_results:
                    if actual_result["oid"] not in expected_results_oids:
                        raise NMOSTestException(test.FAIL(context
                                                          + block.role
                                                          + ": Unexpected search result. " + str(actual_result)))

    def test_25(self, test):
        """NcBlock: FindMembersByClassId method is correct"""
        # Referencing the Google sheet
        # MS-05-02 (52)  Where the functionality of a device uses control classes and datatypes listed in this
        # specification it MUST comply with the model definitions published

        device_model = self.query_device_model(test)

        self.do_find_members_by_class_id_test(test, device_model)

        return test.PASS()

    def do_error_test(self, test, command_json, expected_status=None):
        """Execute command with expected error status."""
        # when expected_status = None checking of the status code is skipped
        # check the syntax of the error message according to is12_error

        try:
            self.create_ncp_socket(test)

            self.is12_utils.send_command(test, command_json)

            return test.FAIL("Error expected")

        except NMOSTestException as e:
            error_msg = e.args[0].detail

            # Expecting an error status dictionary
            if not isinstance(error_msg, dict):
                # It must be some other type of error so re-throw
                raise e

            if not error_msg.get('status'):
                return test.FAIL("Command error: " + str(error_msg))

            if error_msg['status'] == NcMethodStatus.OK:
                return test.FAIL("Error not handled. Expected: " + expected_status.name
                                 + " (" + str(expected_status) + ")"
                                 + ", actual: " + NcMethodStatus(error_msg['status']).name
                                 + " (" + str(error_msg['status']) + ")")

            if expected_status and error_msg['status'] != expected_status:
                return test.WARNING("Unexpected status. Expected: " + expected_status.name
                                    + " (" + str(expected_status) + ")"
                                    + ", actual: " + NcMethodStatus(error_msg['status']).name
                                    + " (" + str(error_msg['status']) + ")")

            return test.PASS()

    def test_26(self, test):
        """IS-12 Protocol Error: Node handles command handle that is not in range 1 to 65535"""
        # Referencing the Google sheet
        # IS-12 (5) Error messages MUST be used by devices to return general error messages when more specific
        # responses cannot be returned

        command_json = self.is12_utils.create_command_JSON(self.is12_utils.ROOT_BLOCK_OID,
                                                           NcObjectMethods.GENERIC_GET.value,
                                                           {'id': NcObjectProperties.OID.value})

        # Handle should be between 1 and 65535
        illegal_command_handle = 999999999
        command_json['commands'][0]['handle'] = illegal_command_handle

        return self.do_error_test(test, command_json)

    def test_27(self, test):
        """IS-12 Protocol Error: Node handles command handle that is not a number"""
        # Referencing the Google sheet
        # IS-12 (5) Error messages MUST be used by devices to return general error messages when more specific
        # responses cannot be returned

        command_json = self.is12_utils.create_command_JSON(self.is12_utils.ROOT_BLOCK_OID,
                                                           NcObjectMethods.GENERIC_GET.value,
                                                           {'id': NcObjectProperties.OID.value})

        # Use invalid handle
        invalid_command_handle = "NOT A HANDLE"
        command_json['commands'][0]['handle'] = invalid_command_handle

        return self.do_error_test(test, command_json)

    def test_28(self, test):
        """IS-12 Protocol Error: Node handles invalid command type"""
        # Referencing the Google sheet
        # IS-12 (5) Error messages MUST be used by devices to return general error messages when more specific
        # responses cannot be returned

        command_json = \
            self.is12_utils.create_command_JSON(self.is12_utils.ROOT_BLOCK_OID,
                                                NcObjectMethods.GENERIC_GET.value,
                                                {'id': NcObjectProperties.OID.value})
        # Use invalid message type
        command_json['messageType'] = 7

        return self.do_error_test(test, command_json)

    def test_29(self, test):
        """IS-12 Protocol Error: Node handles invalid JSON"""
        # Referencing the Google sheet
        # IS-12 (5) Error messages MUST be used by devices to return general error messages when more specific
        # responses cannot be returned

        # Use invalid JSON
        command_json = {'not_a': 'valid_command'}

        return self.do_error_test(test, command_json)

    def test_30(self, test):
        """IS-12 Protocol Error: Node handles oid not in range 1 to 65535"""
        # Referencing the Google sheet
        # IS-12 (5) Error messages MUST be used by devices to return general error messages when more specific
        # responses cannot be returned

        # Oid should be between 1 and 65535
        invalid_oid = 999999999
        command_json = \
            self.is12_utils.create_command_JSON(invalid_oid,
                                                NcObjectMethods.GENERIC_GET.value,
                                                {'id': NcObjectProperties.OID.value})

        return self.do_error_test(test, command_json)

    def test_31(self, test):
        """MS-05-02 Error: Node handles oid of object not found in Device Model"""
        # Referencing the Google sheet
        # MS-05-02 (15) Devices MUST use the exact status code from NcMethodStatus when errors are encountered
        # for the following scenarios...

        device_model = self.query_device_model(test)
        # Calculate invalid oid from the max oid value in device model
        oids = device_model.get_oids()
        invalid_oid = max(oids) + 1

        command_json = \
            self.is12_utils.create_command_JSON(invalid_oid,
                                                NcObjectMethods.GENERIC_GET.value,
                                                {'id': NcObjectProperties.OID.value})

        return self.do_error_test(test,
                                  command_json,
                                  expected_status=NcMethodStatus.BadOid)

    def test_32(self, test):
        """MS-05-02 Error: Node handles invalid property identifier"""
        # Referencing the Google sheet
        # MS-05-02 (15) Devices MUST use the exact status code from NcMethodStatus when errors are encountered
        # for the following scenarios...

        # Use invalid property id
        invalid_property_identifier = {'level': 1, 'index': 999}
        command_json = \
            self.is12_utils.create_command_JSON(self.is12_utils.ROOT_BLOCK_OID,
                                                NcObjectMethods.GENERIC_GET.value,
                                                {'id': invalid_property_identifier})
        return self.do_error_test(test,
                                  command_json,
                                  expected_status=NcMethodStatus.PropertyNotImplemented)

    def test_33(self, test):
        """MS-05-02 Error: Node handles invalid method identifier"""
        # Referencing the Google sheet
        # MS-05-02 (15) Devices MUST use the exact status code from NcMethodStatus when errors are encountered
        # for the following scenarios...

        command_json = \
            self.is12_utils.create_command_JSON(self.is12_utils.ROOT_BLOCK_OID,
                                                NcObjectMethods.GENERIC_GET.value,
                                                {'id': NcObjectProperties.OID.value})

        # Use invalid method id
        invalid_method_id = {'level': 1, 'index': 999}
        command_json['commands'][0]['methodId'] = invalid_method_id

        return self.do_error_test(test,
                                  command_json,
                                  expected_status=NcMethodStatus.MethodNotImplemented)

    def test_34(self, test):
        """MS-05-02 Error: Node handles read only error"""
        # Try to set a read only property
        # Referencing the Google sheet
        # MS-05-02 (15) Devices MUST use the exact status code from NcMethodStatus when errors are encountered
        # for the following scenarios...

        command_json = \
            self.is12_utils.create_command_JSON(self.is12_utils.ROOT_BLOCK_OID,
                                                NcObjectMethods.GENERIC_SET.value,
                                                {'id': NcObjectProperties.ROLE.value,
                                                 'value': "ROLE IS READ ONLY"})

        return self.do_error_test(test,
                                  command_json,
                                  expected_status=NcMethodStatus.Readonly)

    def test_35(self, test):
        """MS-05-02 Error: Node handles GetSequence index out of bounds error"""
        # Referencing the Google sheet
        # MS-05-02 (15) Devices MUST use the exact status code from NcMethodStatus when errors are encountered
        # for the following scenarios...

        self.create_ncp_socket(test)

        length = self.is12_utils.get_sequence_length(test,
                                                     self.is12_utils.ROOT_BLOCK_OID,
                                                     NcBlockProperties.MEMBERS.value)
        out_of_bounds_index = length + 10

        command_json = \
            self.is12_utils.create_command_JSON(self.is12_utils.ROOT_BLOCK_OID,
                                                NcObjectMethods.GET_SEQUENCE_ITEM.value,
                                                {'id': NcBlockProperties.MEMBERS.value,
                                                 'index': out_of_bounds_index})
        return self.do_error_test(test,
                                  command_json,
                                  expected_status=NcMethodStatus.IndexOutOfBounds)

    def test_36(self, test):
        """Node implements subscription and notification mechanism"""
        # Referencing the Google sheet
        # MS-05-02 (12) Notification message type
        # MS-05-02 (13) Subscription message type
        # MS-05-02 (14) Subscription response message type
        # MS-05-02 (17) Property Changed events
        # MS-05-02 (21) Check notification is received

        device_model = self.query_device_model(test)

        # Get all oids for objects in this Device Model
        device_model_objects = device_model.find_members_by_class_id(class_id=StandardClassIds.NCOBJECT.value,
                                                                     include_derived=True,
                                                                     recurse=True)

        oids = [self.is12_utils.ROOT_BLOCK_OID] + [o.oid for o in device_model_objects]

        self.is12_utils.update_subscritions(test, oids)

        error = False
        error_message = ""

        for oid in oids:
            new_user_label = "NMOS Testing Tool " + str(oid)
            old_user_label = self.is12_utils.get_property(test, oid, NcObjectProperties.USER_LABEL.value)

            context = "oid: " + str(oid) + ", "

            for label in [new_user_label, old_user_label]:
                self.is12_utils.reset_notifications()
                self.is12_utils.set_property(test, oid, NcObjectProperties.USER_LABEL.value, label)

                if len(self.is12_utils.get_notifications()) == 0:
                    error = True
                    error_message = context + "No notification recieved"

                for notification in self.is12_utils.get_notifications():
                    if notification['oid'] != oid:
                        error = True
                        error_message += context + "Unexpected Oid " + str(notification['oid']) + ", "

                    if notification['eventId'] != NcObjectEvents.PROPERTY_CHANGED.value:
                        error = True
                        error_message += context + "Unexpected event type: " + str(notification['eventId']) + ", "

                    if notification["eventData"]["propertyId"] != NcObjectProperties.USER_LABEL.value:
                        error = True
                        error_message += context + "Unexpected property id: " \
                            + str(NcObjectProperties(notification["eventData"]["propertyId"]).name) + ", "

                    if notification["eventData"]["changeType"] != NcPropertyChangeType.ValueChanged.value:
                        error = True
                        error_message += context + "Unexpected change type: " \
                            + str(NcPropertyChangeType(notification["eventData"]["changeType"]).name) + ", "

                    if notification["eventData"]["value"] != label:
                        error = True
                        error_message += context + "Unexpected value: " + str(notification["eventData"]["value"]) + ", "

                    if notification["eventData"]["sequenceItemIndex"] is not None:
                        error = True
                        error_message += context + "Unexpected sequence item index: " \
                            + str(notification["eventData"]["sequenceItemIndex"]) + ", "

        if error:
            return test.FAIL(error_message)
        return test.PASS()
