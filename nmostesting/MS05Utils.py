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

from .NMOSUtils import NMOSUtils

import json
import os

from copy import deepcopy
from enum import IntEnum, Enum
from itertools import takewhile, dropwhile
from jsonschema import FormatChecker, SchemaError, validate, ValidationError

from .GenericTest import NMOSTestException
from .TestHelper import load_resolved_schema

MS05_API_KEY = "controlframework"
FEATURE_SETS_KEY = "featuresets"
NODE_API_KEY = "node"


class MS05Utils(NMOSUtils):
    def __init__(self, apis, protocol_api_key):
        NMOSUtils.__init__(self, apis[NODE_API_KEY]["url"])
        self.apis = apis
        self.ROOT_BLOCK_OID = 1
        self.protocol_api_key = protocol_api_key

    def reset(self):
        self.device_model = None
        self.class_manager = None
        self.datatype_schemas = None
        self.load_reference_resources()

    # Overridden functions specialized in derived classes
    def get_property_override(self, test, property_id, **kwargs):
        pass

    def set_property_override(self, test, property_id, argument, **kwargs):
        pass

    def invoke_method_override(self, test, method_id, argument, **kwargs):
        pass

    def get_sequence_item_override(self, test, property_id, index, **kwargs):
        pass

    def get_sequence_length_override(self, test, property_id, **kwargs):
        """Get sequence length. Raises NMOSTestException on error"""
        pass

    def set_sequence_item_override(self, test, property_id, index, value, **kwargs):
        """Add value to a sequence property. Raises NMOSTestException on error"""
        pass

    def add_sequence_item_override(self, test, property_id, value, **kwargs):
        """Add value to a sequence property. Raises NMOSTestException on error"""
        pass

    def remove_sequence_item_override(self, test, property_id, index, **kwargs):
        """Get value from sequence property. Raises NMOSTestException on error"""
        pass

    def get_member_descriptors_override(self, test, recurse, **kwargs):
        pass

    def find_members_by_path_override(self, test, path, **kwargs):
        """Query members based on role path. Raises NMOSTestException on error"""
        pass

    def find_members_by_role_override(self, test, role, case_sensitive, match_whole_string, recurse, **kwargs):
        """Query members based on role. Raises NMOSTestException on error"""
        pass

    def find_members_by_class_id_override(self, test, class_id, include_derived, recurse, **kwargs):
        """Query members based on class id. Raises NMOSTestException on error"""
        pass

    def get_control_class_override(self, test, class_id, include_inherited, **kwargs):
        """Query Class Manager for control class. Raises NMOSTestException on error"""
        pass

    def get_datatype_override(self, test, name, include_inherited, **kwargs):
        """Query Class Manager for datatype. Raises NMOSTestException on error"""
        pass

    # End of overridden functions

    def get_property(self, test, property_id, **kwargs):
        """Get property from object. Returns NcMethodResult. Raises NMOSTestException on error"""
        result = self.get_property_override(test, property_id, **kwargs)
        self.reference_datatype_schema_validate(test, result, NcMethodResult.__name__,
                                                role_path=kwargs.get("role_path"))
        return NcMethodResult.factory(result)

    def set_property(self, test, property_id, argument, **kwargs):
        """Set property from object. Returns NcMethodResult. Raises NMOSTestException on error"""
        result = self.set_property_override(test, property_id, argument, **kwargs)
        self.reference_datatype_schema_validate(test, result, NcMethodResult.__name__,
                                                role_path=kwargs.get("role_path"))
        return NcMethodResult.factory(result)

    def invoke_method(self, test, method_id, argument, **kwargs):
        """Invoke method on Node. Returns NcMethodResult. Raises NMOSTestException on error"""
        result = self.invoke_method_override(test, method_id, argument, **kwargs)
        self.reference_datatype_schema_validate(test, result, NcMethodResult.__name__,
                                                role_path=kwargs.get("role_path"))
        return NcMethodResult.factory(result)

    def get_sequence_item(self, test, property_id, index, **kwargs):
        result = self.get_sequence_item_override(test, property_id, index, **kwargs)
        self.reference_datatype_schema_validate(test, result, NcMethodResult.__name__,
                                                role_path=kwargs.get("role_path"))
        return NcMethodResult.factory(result)

    def get_sequence_length(self, test, property_id, **kwargs):
        """Get sequence length. Returns NcMethodResult. Raises NMOSTestException on error"""
        result = self.get_sequence_length_override(test, property_id, **kwargs)
        self.reference_datatype_schema_validate(test, result, NcMethodResult.__name__,
                                                role_path=kwargs.get("role_path"))
        return NcMethodResult.factory(result)

    def set_sequence_item(self, test, property_id, index, value, **kwargs):
        """Add value to a sequence property. Raises NMOSTestException on error"""
        result = self.set_sequence_item_override(test, property_id, index, value, **kwargs)
        self.reference_datatype_schema_validate(test, result, NcMethodResult.__name__,
                                                role_path=kwargs.get("role_path"))
        return NcMethodResult.factory(result)

    def add_sequence_item(self, test, property_id, value, **kwargs):
        """Add value to a sequence property. Raises NMOSTestException on error"""
        result = self.add_sequence_item_override(test, property_id, value, **kwargs)
        self.reference_datatype_schema_validate(test, result, NcMethodResult.__name__,
                                                role_path=kwargs.get("role_path"))
        return NcMethodResult.factory(result)

    def remove_sequence_item(self, test, property_id, index, **kwargs):
        """Get value from sequence property. Raises NMOSTestException on error"""
        result = self.remove_sequence_item_override(test, property_id, index, **kwargs)
        self.reference_datatype_schema_validate(test, result, NcMethodResult.__name__,
                                                role_path=kwargs.get("role_path"))
        return NcMethodResult.factory(result)

    def create_NcMethodResultBlockMemberDescriptors(self, test, result, role_path):
        self.reference_datatype_schema_validate(test, result, NcMethodResult.__name__, role_path=role_path)
        method_result = NcMethodResult.factory(result)

        if not isinstance(method_result, NcMethodResultError) and isinstance(method_result.value, list):
            # Validate block members and create NcBlockMemberDescriptor objects
            block_member_descriptors = []
            for member in method_result.value:
                self.reference_datatype_schema_validate(
                    test,
                    member,
                    NcBlockMemberDescriptor.__name__,
                    self.create_role_path(role_path, member.get("role")))
                block_member_descriptors.append(NcBlockMemberDescriptor(member))
            method_result.value = block_member_descriptors
        return method_result

    def get_member_descriptors(self, test, recurse, **kwargs):
        result = self.get_member_descriptors_override(test, recurse, **kwargs)
        return self.create_NcMethodResultBlockMemberDescriptors(test, result, kwargs.get("role_path"))

    def find_members_by_path(self, test, path, **kwargs):
        """Query members based on role path. Raises NMOSTestException on error"""
        result = self.find_members_by_path_override(test, path, **kwargs)
        return self.create_NcMethodResultBlockMemberDescriptors(test, result, kwargs.get("role_path"))

    def find_members_by_role(self, test, role, case_sensitive, match_whole_string, recurse, **kwargs):
        """Query members based on role. Raises NMOSTestException on error"""
        result = self.find_members_by_role_override(test, role, case_sensitive, match_whole_string, recurse, **kwargs)
        return self.create_NcMethodResultBlockMemberDescriptors(test, result, kwargs.get("role_path"))

    def find_members_by_class_id(self, test, class_id, include_derived, recurse, **kwargs):
        """Query members based on class id. Raises NMOSTestException on error"""
        result = self.find_members_by_class_id_override(test, class_id, include_derived, recurse, **kwargs)
        return self.create_NcMethodResultBlockMemberDescriptors(test, result, kwargs.get("role_path"))

    def get_control_class(self, test, class_id, include_inherited, **kwargs):
        """Query Class Manager for control class. Raises NMOSTestException on error"""
        result = self.get_control_class_override(test, class_id, include_inherited, **kwargs)
        self.reference_datatype_schema_validate(test, result, NcMethodResult.__name__,
                                                role_path=kwargs.get("role_path"))
        method_result = NcMethodResult.factory(result)

        if not isinstance(method_result, NcMethodResultError):
            self.reference_datatype_schema_validate(test, method_result.value, NcClassDescriptor.__name__,
                                                    role_path=kwargs.get("role_path"))
            method_result.value = NcClassDescriptor(method_result.value)

        return method_result

    def get_datatype(self, test, name, include_inherited, **kwargs):
        """Query Class Manager for datatype. Raises NMOSTestException on error"""
        result = self.get_datatype_override(test, name, include_inherited, **kwargs)
        self.reference_datatype_schema_validate(test, result, NcMethodResult.__name__,
                                                role_path=kwargs.get("role_path"))
        method_result = NcMethodResult.factory(result)

        if not isinstance(method_result, NcMethodResultError):
            self.reference_datatype_schema_validate(test, method_result.value, NcDatatypeDescriptor.__name__,
                                                    role_path=kwargs.get("role_path"))
            method_result.value = NcDatatypeDescriptor.factory(method_result.value)

        return method_result

    def query_device_model(self, test):
        """ Query Device Model from the Node under test.
            self.device_model_metadata set on Device Model validation error.
            NMOSTestException raised if unable to query Device Model """
        if not self.device_model:
            self.device_model = self.create_block(
                test,
                StandardClassIds.NCBLOCK.value,
                self.ROOT_BLOCK_OID,
                "root")

            if not self.device_model:
                raise NMOSTestException(test.FAIL("Unable to query Device Model"))
        return self.device_model

    def _primitive_to_JSON(self, type):
        """Convert MS-05 primitive type to corresponding JSON type"""

        types = {
            "NcBoolean": "boolean",
            "NcInt16": "number",
            "NcInt32": "number",
            "NcInt64": "number",
            "NcUint16": "number",
            "NcUint32": "number",
            "NcUint64": "number",
            "NcFloat32": "number",
            "NcFloat64":  "number",
            "NcString": "string"
        }

        return types.get(type, False)

    def load_reference_resources(self):
        """Load datatype and control class decriptors and create datatype JSON schemas"""
        # Calculate paths to MS-05 descriptors
        # including Feature Sets specified as additional_paths in test definition
        spec_paths = [os.path.join(self.apis[FEATURE_SETS_KEY]["spec_path"], path)
                      for path in self.apis[FEATURE_SETS_KEY]["repo_paths"]]
        spec_paths.append(self.apis[MS05_API_KEY]["spec_path"])
        # Root path for primitive datatypes
        spec_paths.append("test_data/MS05")

        datatype_paths = []
        classes_paths = []
        for spec_path in spec_paths:
            datatype_path = os.path.abspath(os.path.join(spec_path, "models/datatypes/"))
            if os.path.exists(datatype_path):
                datatype_paths.append(datatype_path)
            classes_path = os.path.abspath(os.path.join(spec_path, "models/classes/"))
            if os.path.exists(classes_path):
                classes_paths.append(classes_path)

        # Load class and datatype descriptors
        self.reference_class_descriptors = self._load_model_descriptors(classes_paths)

        # Load MS-05 datatype descriptors
        self.reference_datatype_descriptors = self._load_model_descriptors(datatype_paths)

        # Generate reference MS-05 datatype schemas from MS-05 datatype descriptors
        self.reference_datatype_schemas = self.generate_json_schemas(
            datatype_descriptors=self.reference_datatype_descriptors,
            schema_path=os.path.join(self.apis[self.protocol_api_key]["spec_path"], "APIs/schemas/"))

    def _load_model_descriptors(self, descriptor_paths):
        descriptors = {}
        for descriptor_path in descriptor_paths:
            for filename in os.listdir(descriptor_path):
                name, extension = os.path.splitext(filename)
                if extension == ".json":
                    with open(os.path.join(descriptor_path, filename), "r") as json_file:
                        descriptor = json.load(json_file)
                        if descriptor.get("classId"):
                            descriptors[name] = NcClassDescriptor(descriptor)
                        else:
                            descriptors[name] = NcDatatypeDescriptor.factory(descriptor)

        return descriptors

    def generate_json_schemas(self, datatype_descriptors, schema_path):
        """Generate datatype schemas from datatype descriptors"""
        datatype_schema_names = []
        base_schema_path = os.path.abspath(schema_path)
        if not os.path.exists(base_schema_path):
            os.makedirs(base_schema_path)

        for name, descriptor in datatype_descriptors.items():
            json_schema = self._datatype_descriptor_to_schema(descriptor)
            with open(os.path.join(base_schema_path, name + ".json"), "w") as output_file:
                json.dump(json_schema, output_file, indent=4)
                datatype_schema_names.append(name)

        # Load resolved MS-05 datatype schemas
        datatype_schemas = {}
        for name in datatype_schema_names:
            datatype_schemas[name] = load_resolved_schema(schema_path, name + ".json", path_prefix=False)

        return datatype_schemas

    def _datatype_descriptor_to_schema(self, descriptor):
        """Convert NcDatatypeDescriptor to json schema"""
        variant_type = ["number", "string", "boolean", "object", "array", "null"]

        json_schema = {}
        json_schema["$schema"] = "http://json-schema.org/draft-07/schema#"

        json_schema["title"] = descriptor.name
        json_schema["description"] = descriptor.description if descriptor.description else ""

        # Inheritance of datatype
        if isinstance(descriptor, (NcDatatypeDescriptorStruct, NcDatatypeDescriptorTypeDef)) and descriptor.parentType:
            if isinstance(descriptor, NcDatatypeDescriptorTypeDef) and descriptor.isSequence:
                json_schema["type"] = "array"
                json_schema["items"] = {"$ref": descriptor.parentType + ".json"}
            else:
                json_schema["allOf"] = []
                json_schema["allOf"].append({"$ref": descriptor.parentType + ".json"})
        # Primitive datatype
        elif isinstance(descriptor, NcDatatypeDescriptorPrimitive):
            json_schema["type"] = self._primitive_to_JSON(descriptor.name)

        # Struct datatype
        elif isinstance(descriptor, NcDatatypeDescriptorStruct):
            json_schema["type"] = "object"

            required = []
            properties = {}
            for field in descriptor.fields:
                required.append(field.name)

                property_type = {}
                if self._primitive_to_JSON(field.typeName):
                    if field.isNullable:
                        property_type = {"type": [self._primitive_to_JSON(field.typeName), "null"]}
                    else:
                        property_type = {"type": self._primitive_to_JSON(field.typeName)}
                else:
                    if field.typeName:
                        if field.isNullable:
                            property_type["anyOf"] = []
                            property_type["anyOf"].append({"$ref": field.typeName + ".json"})
                            property_type["anyOf"].append({"type": "null"})
                        else:
                            property_type = {"$ref": field.typeName + ".json"}
                    else:
                        # variant
                        property_type = {"type": variant_type}

                if field.isSequence:
                    property_type = {"type": "array", "items": property_type}

                property_type["description"] = field.description if field.description else ""
                properties[field.name] = property_type

            json_schema["required"] = required
            json_schema["properties"] = properties

        # Enum datatype
        elif isinstance(descriptor, NcDatatypeDescriptorEnum):
            json_schema["enum"] = []
            for item in descriptor.items:
                json_schema["enum"].append(int(item.value))
            json_schema["type"] = "integer"

        return json_schema

    def _generate_device_model_datatype_schemas(self, test):
        # Generate datatype schemas based on the datatype decriptors
        # queried from the Node under test's Device Model.
        # This will include any Non-standard data types
        class_manager = self.get_class_manager(test)

        try:
            # Create JSON schemas for the queried datatypes
            return self.generate_json_schemas(
                datatype_descriptors=class_manager.datatype_descriptors,
                schema_path=os.path.join(self.apis[self.protocol_api_key]["spec_path"], "APIs/tmp_schemas/"))
        except Exception as e:
            raise NMOSTestException(test.FAIL(f"Unable to create Device Model schemas: {e.message}"))

    def queried_datatype_schema_validate(self, test, payload, datatype_name, context=""):
        """Validate payload against datatype schema queried from Node under Test's Class Manager"""
        if not self.datatype_schemas:
            # Generate datatype schemas based on the datatype decriptors
            # queried from the Node under test's Device Model.
            # This will include any Non-standard data types
            class_manager = self.get_class_manager(test)

            try:
                # Create JSON schemas for the queried datatypes
                self.datatype_schemas = self.generate_json_schemas(
                    datatype_descriptors=class_manager.datatype_descriptors,
                    schema_path=os.path.join(self.apis[self.protocol_api_key]["spec_path"], "APIs/tmp_schemas/"))
            except Exception as e:
                raise NMOSTestException(test.FAIL(f"Unable to create Device Model schemas: {e.message}"))

        self._validate_schema(test, payload, self.datatype_schemas.get(datatype_name), f"{context}{datatype_name}: ")

    def reference_datatype_schema_validate(self, test, payload, datatype_name, role_path=None):
        """Validate payload against specification reference datatype schema"""
        self._validate_schema(test, payload, self.reference_datatype_schemas.get(datatype_name),
                              f"{self.create_role_path_string(role_path)}: {datatype_name}: ")

    def _validate_schema(self, test, payload, schema, context=""):
        """Delegates to jsonschema validate. Raises NMOSTestExceptions on error"""
        if not schema:
            raise NMOSTestException(test.FAIL(f"{context}Missing schema. Possible unknown type"))
        try:
            # Validate the JSON schema is correct
            checker = FormatChecker(["ipv4", "ipv6", "uri"])
            validate(payload, schema, format_checker=checker)
        except ValidationError as e:
            raise NMOSTestException(test.FAIL(f"{context}Schema validation error: {e.message}"))
        except SchemaError as e:
            raise NMOSTestException(test.FAIL(f"{context}Schema error: {e.message}"))

        return

    def validate_descriptor(self, test, reference, descriptor, context=""):
        """Validate descriptor against reference NcDescriptor. Raises NMOSTestException on error"""
        def sort_key(e):
            if isinstance(e, NcDescriptor):
                return e.name
            else:
                return e["name"]

        non_normative_keys = ["description"]

        # If the reference is an object then convert to a dict before comparison
        if isinstance(reference, (NcDescriptor, NcElementId, NcPropertyConstraints, NcParameterConstraints)):
            self.validate_descriptor(test, reference.__dict__, descriptor, context)
        # If the descriptor being checked is an object then convert to a dict before comparison
        elif isinstance(descriptor, (NcDescriptor, NcElementId, NcPropertyConstraints, NcParameterConstraints)):
            self.validate_descriptor(test, reference, descriptor.__dict__, context)
        # Compare dictionaries
        elif isinstance(reference, dict):
            # NcDescriptor objects have a json field that caches the json used to construct it
            reference.pop("json", None)
            descriptor.pop("json", None)

            reference_keys = set(reference.keys())
            descriptor_keys = set(descriptor.keys())

            # compare the keys to see if any extra/missing
            key_diff = (set(reference_keys) | set(descriptor_keys)) - (set(reference_keys) & set(descriptor_keys))
            if len(key_diff) > 0:
                raise NMOSTestException(test.FAIL(f"{context}Missing/additional keys: {str(key_diff)}"))
            for key in reference_keys:
                # Ignore keys that contain non-normative information
                if key in non_normative_keys:
                    continue
                self.validate_descriptor(test, reference[key], descriptor[key], context=f"{context}{key}->")
        # Compare lists
        elif isinstance(reference, list):
            if len(reference) != len(descriptor):
                raise NMOSTestException(test.FAIL(f"{context}List unexpected length. Expected: "
                                        f"{str(len(reference))}, actual: {str(len(descriptor))}"))
            if len(reference) > 0:
                # If comparing lists of objects or dicts then sort by name first.
                # Primitive arrays are unsorted as position is assumed to be important e.g. classId
                if isinstance(reference[0], (dict, NcDescriptor)):
                    reference.sort(key=sort_key)
                    descriptor.sort(key=sort_key)
                for refvalue, value in zip(reference, descriptor):
                    self.validate_descriptor(test, refvalue, value, context)
        # Compare primitives and primitive arrays directly
        elif reference != descriptor:
            raise NMOSTestException(test.FAIL(f"{context}Expected value: "
                                    f"{str(reference)}, actual value: {str(descriptor)}"))
        return

    def _get_class_manager_datatype_descriptors(self, test, class_manager_oid, role_path):
        method_result = self.get_property(test, NcClassManagerProperties.DATATYPES.value,
                                          oid=class_manager_oid, role_path=role_path)

        if isinstance(method_result, NcMethodResultError):
            raise NMOSTestException(test.FAIL(f"{self.create_role_path_string(role_path)}: "
                                              "Error getting Class Manager Datatype property: "
                                              f"{str(method_result.errorMessage)}"))
        response = method_result.value

        # Validate descriptors against schema
        for r in response:
            self.reference_datatype_schema_validate(test, r, NcDatatypeDescriptor.__name__, role_path)

        # Create NcDescriptor dictionary from response array
        descriptors = {r["name"]: NcDatatypeDescriptor.factory(r) for r in response}

        return descriptors

    def _get_class_manager_class_descriptors(self, test, class_manager_oid, role_path):
        method_result = self.get_property(test, NcClassManagerProperties.CONTROL_CLASSES.value,
                                          oid=class_manager_oid, role_path=role_path)

        if isinstance(method_result, NcMethodResultError):
            raise NMOSTestException(test.FAIL(f"{self.create_role_path_string(role_path)}: "
                                              "Error getting Class Manager Control Classes property: "
                                              f"{str(method_result.errorMessage)}"))

        response = method_result.value
        # Validate descriptors
        for r in response:
            self.reference_datatype_schema_validate(test, r, NcClassDescriptor.__name__, role_path)

        # Create NcClassDescriptor dictionary from response array
        descriptors = {self.create_class_id_string(r.get("classId")): NcClassDescriptor(r) for r in response}
        return descriptors

    def create_block(self, test, class_id, oid, role, base_role_path=None):
        """Recursively create Device Model hierarchy"""
        # will set self.device_model_error to True if problems encountered
        role_path = self.create_role_path(base_role_path, role)

        method_result = self.get_property(test, NcObjectProperties.RUNTIME_PROPERTY_CONSTRAINTS.value,
                                          oid=oid, role_path=role_path)

        if isinstance(method_result, NcMethodResultError):
            raise NMOSTestException(test.FAIL(f"{self.create_role_path_string(role_path)}: "
                                              "Unable to get runtime property constraints: "
                                              f"{str(method_result.errorMessage)}"))

        runtime_constraints = method_result.value
        if runtime_constraints:
            for constraint in runtime_constraints:
                self.reference_datatype_schema_validate(test, constraint, NcPropertyConstraints.__name__,
                                                        role_path)

            runtime_constraints = [NcPropertyConstraints.factory(c) for c in runtime_constraints]

        if self.is_block(class_id):
            method_result = self.get_property(test, NcBlockProperties.MEMBERS.value,
                                              oid=oid, role_path=role_path)

            if isinstance(method_result, NcMethodResultError):
                raise NMOSTestException(test.FAIL(f"{self.create_role_path_string(role_path)}: "
                                                  "Unable to get members property: "
                                                  f"{str(method_result.errorMessage)}"))

            member_descriptors = method_result.value
            block_member_descriptors = []
            for m in member_descriptors:
                self.reference_datatype_schema_validate(test, m, NcBlockMemberDescriptor.__name__, role_path)
            block_member_descriptors = [NcBlockMemberDescriptor(m) for m in member_descriptors]

            nc_block = NcBlock(class_id, oid, role, role_path, block_member_descriptors, runtime_constraints)

            for m in member_descriptors:
                child_object = self.create_block(test, m["classId"], m["oid"], m["role"], role_path)
                if child_object:
                    nc_block.add_child_object(child_object)

            return nc_block
        else:
            if self._is_class_manager(class_id):
                class_descriptors = self._get_class_manager_class_descriptors(
                    test, class_manager_oid=oid, role_path=role_path)

                datatype_descriptors = self._get_class_manager_datatype_descriptors(
                    test, class_manager_oid=oid, role_path=role_path)

                if not class_descriptors or not datatype_descriptors:
                    raise NMOSTestException(test.FAIL("No class descriptors or datatype descriptors "
                                                      "found in ClassManager"))

                return NcClassManager(class_id, oid, role, role_path,
                                      class_descriptors, datatype_descriptors,
                                      runtime_constraints)

            return NcObject(class_id, oid, role, role_path, runtime_constraints)

    def _get_singleton_object_by_class_id(self, test, class_id):
        device_model = self.query_device_model(test)
        members = device_model.find_members_by_class_id(class_id, include_derived=True)

        spec_link = f"https://specs.amwa.tv/ms-05-02/branches/{self.apis[MS05_API_KEY]["spec_branch"]}" \
            + "/docs/Managers.html"

        if len(members) == 0:
            raise NMOSTestException(test.FAIL(f"Class: {class_id} not found in Root Block.", spec_link))

        if len(members) > 1:
            raise NMOSTestException(test.FAIL(f"Class: {class_id} expected to be a singleton.", spec_link))

        return members[0]

    def get_class_manager(self, test):
        """Get the Class Manager queried from the Node under test's Device Model"""
        if not self.class_manager:
            self.class_manager = self._get_singleton_object_by_class_id(test, StandardClassIds.NCCLASSMANAGER.value)
        return self.class_manager

    def get_device_manager(self, test):
        """Get the Device Manager queried from the Node under test's Device Model"""
        return self._get_singleton_object_by_class_id(test, StandardClassIds.NCDEVICEMANAGER.value)

    def primitive_to_python_type(self, type):
        """Convert MS-05 primitive type to corresponding Python type"""

        types = {
            "NcBoolean": bool,
            "NcInt16": int,
            "NcInt32": int,
            "NcInt64": int,
            "NcUint16": int,
            "NcUint32": int,
            "NcUint64": int,
            "NcFloat32": float,
            "NcFloat64":  float,
            "NcString": str
        }

        return types.get(type, False)

    def get_base_class_id(self, class_id):
        """ Given a class_id returns the standard base class id as a string"""
        return ".".join([str(v) for v in takewhile(lambda x: x > 0, class_id)])

    def is_non_standard_class(self, class_id):
        """ Check class_id to determine if it is for a non-standard class """
        # Assumes at least one value follows the authority key
        return len([v for v in dropwhile(lambda x: x > 0, class_id)]) > 1

    def is_manager(self, class_id):
        """ Check class id to determine if this is a manager class_id"""
        return len(class_id) > 1 and class_id[0] == 1 and class_id[1] == 3

    def _is_class_manager(self, class_id):
        """ Check class id to determine is this is a class manager class_id """
        return len(class_id) > 2 and class_id[0] == 1 and class_id[1] == 3 and class_id[2] == 2

    def is_block(self, class_id):
        """ Check class id to determine if this is a block class_id"""
        return len(class_id) > 1 and class_id[0] == 1 and class_id[1] == 1

    def resolve_datatype(self, test, datatype):
        """Resolve datatype to its base type"""
        # Datatype of None denotes 'any' in MS-05-02 framework
        if datatype is None:
            return None
        class_manager = self.get_class_manager(test)
        if datatype not in class_manager.datatype_descriptors:
            raise NMOSTestException(test.FAIL(f"Unknown datatype: {datatype}"))

        datatype_descriptor = class_manager.datatype_descriptors[datatype]
        if isinstance(datatype_descriptor, (NcDatatypeDescriptorStruct, NcDatatypeDescriptorTypeDef)) and \
                class_manager.datatype_descriptors[datatype].parentType:
            return self.resolve_datatype(test, class_manager.datatype_descriptors[datatype].parentType)
        return datatype

    def create_role_path(self, base_role_path, role):
        """Appends role to base_role_path"""
        if base_role_path is None:
            role_path = []
        else:
            role_path = base_role_path.copy()
        role_path.append(role)
        return role_path

    def create_role_path_string(self, role_path):
        if role_path is None or not isinstance(role_path, list):
            return ""
        return "/".join([str(r) for r in role_path])

    def create_class_id_string(self, class_id):
        if class_id is None or not isinstance(class_id, list):
            return ""
        return ".".join(map(str, class_id))


class NcMethodStatus(IntEnum):
    OK = 200
    PropertyDeprecated = 298
    MethodDeprecated = 299
    BadCommandFormat = 400
    Unauthorized = 401
    BadOid = 404
    Readonly = 405
    InvalidRequest = 406
    Conflict = 409
    BufferOverflow = 413
    IndexOutOfBounds = 414
    ParameterError = 417
    Locked = 423
    DeviceError = 500
    MethodNotImplemented = 501
    PropertyNotImplemented = 502
    NotReady = 503
    Timeout = 504
    UNKNOWN = 9999

    @classmethod
    def _missing_(cls, _):
        return cls.UNKNOWN


class NcDatatypeType(IntEnum):
    Primitive = 0  # Primitive datatype
    Typedef = 1  # Simple alias of another datatype
    Struct = 2  # Data structure
    Enum = 3  # Enum datatype


class NcPropertyChangeType(IntEnum):
    ValueChanged = 0  # Current value changed
    SequenceItemAdded = 1  # Sequence item added
    SequenceItemChanged = 2  # Sequence item changed
    SequenceItemRemoved = 3  # Sequence item removed
    UNKNOWN = 9999

    @classmethod
    def _missing_(cls, _):
        return cls.UNKNOWN


class StandardClassIds(Enum):
    NCOBJECT = [1]
    NCBLOCK = [1, 1]
    NCWORKER = [1, 2]
    NCMANAGER = [1, 3]
    NCDEVICEMANAGER = [1, 3, 1]
    NCCLASSMANAGER = [1, 3, 2]


# MS-05-02 All methods MUST return a datatype which inherits from NcMethodResult.
# When a method call encounters an error the return MUST be NcMethodResultError
# or a derived datatype.
# https://specs.amwa.tv/ms-05-02/branches/v1.0/docs/Framework.html#ncmethodresult
class NcMethodResult():
    def __init__(self, result_json):
        self.status = NcMethodStatus(result_json["status"])  # Status for the invoked method

    @staticmethod
    def factory(result_json):
        """Instantiate concrete NcMethodResult object"""
        if "errorMessage" in result_json:
            return NcMethodResultError(result_json)

        if "value" in result_json:
            return NcMethodResultXXX(result_json)

        return NcMethodResult(result_json)


# Concrete class for all non-error result types
# e.g. NcMethodResultBlockMemberDescriptors, NcMethodResultClassDescriptor etc.
class NcMethodResultXXX(NcMethodResult):
    def __init__(self, result_json):
        NcMethodResult.__init__(self, result_json)
        self.value = result_json["value"]  # Value can be any type


class NcMethodResultError(NcMethodResult):
    def __init__(self, result_json):
        NcMethodResult.__init__(self, result_json)
        self.errorMessage = result_json["errorMessage"]  # Error message


class NcElementId():
    def __init__(self, id_json):
        self.level = id_json["level"]  # Level of the element
        self.index = id_json["index"]  # Index of the element

    def __eq__(self, other):
        if not isinstance(other, NcElementId):
            return NotImplemented

        return self.level == other.level and self.index == other.index

    def __str__(self):
        return f"[level={self.level}, index={self.index}]"


class NcPropertyId(NcElementId):
    def __init__(self, id_json):
        NcElementId.__init__(self, id_json)


class NcMethodId(NcElementId):
    def __init__(self, id_json):
        NcElementId.__init__(self, id_json)


class NcEventId(NcElementId):
    def __init__(self, id_json):
        NcElementId.__init__(self, id_json)


class NcObjectProperties(Enum):
    CLASS_ID = NcPropertyId({"level": 1, "index": 1})
    OID = NcPropertyId({"level": 1, "index": 2})
    CONSTANT_OID = NcPropertyId({"level": 1, "index": 3})
    OWNER = NcPropertyId({"level": 1, "index": 4})
    ROLE = NcPropertyId({"level": 1, "index": 5})
    USER_LABEL = NcPropertyId({"level": 1, "index": 6})
    TOUCHPOINTS = NcPropertyId({"level": 1, "index": 7})
    RUNTIME_PROPERTY_CONSTRAINTS = NcPropertyId({"level": 1, "index": 8})
    UNKNOWN = NcPropertyId({"level": 9999, "index": 9999})

    @classmethod
    def _missing_(cls, _):
        return cls.UNKNOWN


class NcBlockProperties(Enum):
    ENABLED = NcPropertyId({"level": 2, "index": 1})
    MEMBERS = NcPropertyId({"level": 2, "index": 2})


class NcClassManagerProperties(Enum):
    CONTROL_CLASSES = NcPropertyId({"level": 3, "index": 1})
    DATATYPES = NcPropertyId({"level": 3, "index": 2})


class NcDeviceManagerProperties(Enum):
    NCVERSION = NcPropertyId({"level": 3, "index": 1})


class NcObjectMethods(Enum):
    GENERIC_GET = NcMethodId({"level": 1, "index": 1})
    GENERIC_SET = NcMethodId({"level": 1, "index": 2})
    GET_SEQUENCE_ITEM = NcMethodId({"level": 1, "index": 3})
    SET_SEQUENCE_ITEM = NcMethodId({"level": 1, "index": 4})
    ADD_SEQUENCE_ITEM = NcMethodId({"level": 1, "index": 5})
    REMOVE_SEQUENCE_ITEM = NcMethodId({"level": 1, "index": 6})
    GET_SEQUENCE_LENGTH = NcMethodId({"level": 1, "index": 7})


class NcBlockMethods(Enum):
    GET_MEMBERS_DESCRIPTOR = NcMethodId({"level": 2, "index": 1})
    FIND_MEMBERS_BY_PATH = NcMethodId({"level": 2, "index": 2})
    FIND_MEMBERS_BY_ROLE = NcMethodId({"level": 2, "index": 3})
    FIND_MEMBERS_BY_CLASS_ID = NcMethodId({"level": 2, "index": 4})


class NcClassManagerMethods(Enum):
    GET_CONTROL_CLASS = NcMethodId({"level": 3, "index": 1})
    GET_DATATYPE = NcMethodId({"level": 3, "index": 2})


class NcObjectEvents(Enum):
    PROPERTY_CHANGED = NcEventId({"level": 1, "index": 1})


# Base descriptor
class NcDescriptor():
    def __init__(self, descriptor_json):
        self.json = descriptor_json  # Store original JSON to use for schema validation
        self.description = descriptor_json["description"]  # Optional user facing description


class NcPropertyDescriptor(NcDescriptor):
    def __init__(self, descriptor_json):
        NcDescriptor.__init__(self, descriptor_json)
        self.id = NcPropertyId(descriptor_json["id"])  # Property id with level and index
        self.name = descriptor_json["name"]  # Name of property
        self.typeName = descriptor_json["typeName"]  # Name of property's datatype.
        self.isReadOnly = descriptor_json["isReadOnly"]  # TRUE iff property is read-only
        self.isNullable = descriptor_json["isNullable"]  # TRUE iff property is nullable
        self.isSequence = descriptor_json["isSequence"]  # TRUE iff property is a sequence
        self.isDeprecated = descriptor_json["isDeprecated"]  # TRUE iff property is marked as deprecated
        self.constraints = NcParameterConstraints.factory(descriptor_json["constraints"])  # Optional constraints


class NcBlockMemberDescriptor(NcDescriptor):
    def __init__(self, descriptor_json):
        NcDescriptor.__init__(self, descriptor_json)
        self.role = descriptor_json["role"]  # Role of member in its containing block
        self.oid = descriptor_json["oid"]  # OID of member
        self.constantOid = descriptor_json["constantOid"]  # TRUE iff member's OID is hardwired into device
        self.classId = descriptor_json["classId"]  # Class ID
        self.userLabel = descriptor_json["userLabel"]  # User label
        self.owner = descriptor_json["owner"]  # Containing block's OID


class NcClassDescriptor(NcDescriptor):
    def __init__(self, descriptor_json):
        NcDescriptor.__init__(self, descriptor_json)
        self.classId = descriptor_json["classId"]  # Identity of the class
        self.name = descriptor_json["name"]  # Name of the class
        self.fixedRole = descriptor_json["fixedRole"]  # Role if the class has fixed role (manager classes)
        self.properties = [NcPropertyDescriptor(p) for p in descriptor_json["properties"]]
        self.methods = [NcMethodDescriptor(p) for p in descriptor_json["methods"]]
        self.events = descriptor_json["events"]  # Event descriptors


class NcDatatypeDescriptor(NcDescriptor):
    def __init__(self, descriptor_json):
        NcDescriptor.__init__(self, descriptor_json)
        self.name = descriptor_json["name"]  # Datatype name
        self.type = descriptor_json["type"]  # Type: Primitive, Typedef, Struct, Enum
        self.constraints = NcParameterConstraints.factory(descriptor_json["constraints"])  # Optional constraints

    @staticmethod
    def factory(descriptor_json):
        """Instantiate concrete NcDatatypeDescriptor object"""
        if "fields" in descriptor_json and "parentType" in descriptor_json:
            return NcDatatypeDescriptorStruct(descriptor_json)

        if "parentType" in descriptor_json and "isSequence" in descriptor_json:
            return NcDatatypeDescriptorTypeDef(descriptor_json)

        if "items" in descriptor_json:
            return NcDatatypeDescriptorEnum(descriptor_json)

        return NcDatatypeDescriptorPrimitive(descriptor_json)


class NcDatatypeDescriptorEnum(NcDatatypeDescriptor):
    def __init__(self, descriptor_json):
        NcDatatypeDescriptor.__init__(self, descriptor_json)
        self.items = [NcEnumItemDescriptor(i) for i in descriptor_json["items"]]


class NcDatatypeDescriptorPrimitive(NcDatatypeDescriptor):
    def __init__(self, descriptor_json):
        NcDatatypeDescriptor.__init__(self, descriptor_json)


class NcDatatypeDescriptorStruct(NcDatatypeDescriptor):
    def __init__(self, descriptor_json):
        NcDatatypeDescriptor.__init__(self, descriptor_json)
        self.fields = [NcFieldDescriptor(p) for p in descriptor_json["fields"]]
        self.parentType = descriptor_json["parentType"]


class NcDatatypeDescriptorTypeDef(NcDatatypeDescriptor):
    def __init__(self, descriptor_json):
        NcDatatypeDescriptor.__init__(self, descriptor_json)
        self.parentType = descriptor_json["parentType"]  # Original typedef datatype name
        self.isSequence = descriptor_json["isSequence"]  # TRUE iff type is a typedef sequence of another type


class NcEnumItemDescriptor(NcDescriptor):
    def __init__(self, descriptor_json):
        NcDescriptor.__init__(self, descriptor_json)
        self.name = descriptor_json["name"]  # Name of option
        self.value = descriptor_json["value"]  # Enum item numerical value


class NcFieldDescriptor(NcDescriptor):
    def __init__(self, descriptor_json):
        NcDescriptor.__init__(self, descriptor_json)
        self.name = descriptor_json["name"]  # Name of field
        self.typeName = descriptor_json["typeName"]  # Name of field's datatype.
        self.isNullable = descriptor_json["isNullable"]  # TRUE iff field is nullable
        self.isSequence = descriptor_json["isSequence"]  # TRUE iff field is a sequence
        self.constraints = NcParameterConstraints.factory(descriptor_json["constraints"])  # Optional constraints


class NcParameterDescriptor(NcDescriptor):
    def __init__(self, descriptor_json):
        NcDescriptor.__init__(self, descriptor_json)
        self.name = descriptor_json["name"]  # Name of parameter
        self.typeName = descriptor_json["typeName"]  # Name of parameter's datatype.
        self.isNullable = descriptor_json["isNullable"]  # TRUE iff parameter is nullable
        self.isSequence = descriptor_json["isSequence"]  # TRUE iff parameter is a sequence
        self.constraints = NcParameterConstraints.factory(descriptor_json["constraints"])  # Optional constraints


class NcMethodDescriptor(NcDescriptor):
    def __init__(self, descriptor_json):
        NcDescriptor.__init__(self, descriptor_json)
        self.id = NcMethodId(descriptor_json["id"])  # Method id with level and index
        self.name = descriptor_json["name"]  # Name of method
        self.resultDatatype = descriptor_json["resultDatatype"]  # Name of method result's datatype
        self.parameters = [NcParameterDescriptor(p) for p in descriptor_json["parameters"]]  # Parameter descriptors
        self.isDeprecated = descriptor_json["isDeprecated"]  # TRUE iff property is marked as deprecated


class NcTouchpoint():
    def __init__(self, touchpoint_json):
        self.context_namespace = touchpoint_json["contextNamespace"]  # Context namespace


class NcTouchpointNmos(NcTouchpoint):
    def __init__(self, touchpoint_json):
        NcTouchpoint.__init__(self, touchpoint_json)
        self.resource = touchpoint_json["resource"]  # Context NMOS resource


class NcTouchpointNmosChannelMapping(NcTouchpoint):
    def __init__(self, touchpoint_json):
        NcTouchpoint.__init__(self, touchpoint_json)
        self.resource = touchpoint_json["resource"]  # Context Channel Mapping resource


class NcParameterConstraints:
    def __init__(self, constraints_json):
        self.defaultValue = constraints_json["defaultValue"]  # Default value

    @staticmethod
    def factory(constraints_json):
        if constraints_json is None:
            return None
        if "minimum" in constraints_json and "maximum" in constraints_json and "step" in constraints_json:
            return NcParameterConstraintsNumber(constraints_json)
        if "maxCharacters" in constraints_json and "pattern" in constraints_json:
            return NcParameterConstraintsString(constraints_json)
        return NcParameterConstraints(constraints_json)


class NcParameterConstraintsNumber(NcParameterConstraints):
    def __init__(self, constraints_json):
        NcParameterConstraints.__init__(self, constraints_json)
        self.maximum = constraints_json["maximum"]  # Optional maximum
        self.minimum = constraints_json["minimum"]  # Optional minimum
        self.step = constraints_json["step"]  # Optional step


class NcParameterConstraintsString(NcParameterConstraints):
    def __init__(self, constraints_json):
        NcParameterConstraints.__init__(self, constraints_json)
        self.maxCharacters = constraints_json["maxCharacters"]  # Maximum characters allowed
        self.pattern = constraints_json["pattern"]  # Regex pattern


class NcPropertyConstraints:
    def __init__(self, constraints_json):
        self.propertyId = NcPropertyId(constraints_json["propertyId"])  # Property being constrained
        self.defaultValue = constraints_json["defaultValue"]  # Default value

    @staticmethod
    def factory(constraints_json):
        if "minimum" in constraints_json and "maximum" in constraints_json and "step" in constraints_json:
            return NcPropertyConstraintsNumber(constraints_json)
        if "maxCharacters" in constraints_json and "pattern" in constraints_json:
            return NcPropertyConstraintsString(constraints_json)
        return NcPropertyConstraints(constraints_json)


class NcPropertyConstraintsNumber(NcPropertyConstraints):
    def __init__(self, constraints_json):
        NcPropertyConstraints.__init__(self, constraints_json)
        self.maximum = constraints_json["maximum"]  # Optional maximum
        self.minimum = constraints_json["minimum"]  # Optional minimum
        self.step = constraints_json["step"]  # Optional step


class NcPropertyConstraintsString(NcPropertyConstraints):
    def __init__(self, constraints_json):
        NcPropertyConstraints.__init__(self, constraints_json)
        self.maxCharacters = constraints_json["maxCharacters"]  # Maximum characters allowed
        self.pattern = constraints_json["pattern"]  # Regex pattern


class NcObject():
    def __init__(self, class_id, oid, role, role_path, runtime_constraints):
        self.class_id = class_id
        self.oid = oid
        self.role = role
        self.role_path = role_path
        self.runtime_constraints = runtime_constraints


class NcBlock(NcObject):
    def __init__(self, class_id, oid, role, role_path, descriptors, runtime_constraints):
        NcObject.__init__(self, class_id, oid, role, role_path, runtime_constraints)
        self.child_objects = []
        self.member_descriptors = descriptors

    # Utility Methods
    def add_child_object(self, nc_object):
        self.child_objects.append(nc_object)

    # JRT this could be simplified now that we have the role_path as a member
    def get_role_paths(self):
        role_paths = []
        for child_object in self.child_objects:
            role_paths.append([child_object.role])
            if type(child_object) is NcBlock:
                child_paths = child_object.get_role_paths()
                for child_path in child_paths:
                    role_path = [child_object.role]
                    role_path += child_path
                    role_paths.append(role_path)
        return role_paths

    def get_oids(self, root=True):
        oids = [self.oid] if root else []
        for child_object in self.child_objects:
            oids.append(child_object.oid)
            if type(child_object) is NcBlock:
                oids += child_object.get_oids(False)
        return oids

    # NcBlock Methods
    def get_member_descriptors(self, recurse=False):
        query_results = []
        query_results += self.member_descriptors
        if recurse:
            for child_object in self.child_objects:
                if type(child_object) is NcBlock:
                    query_results += child_object.get_member_descriptors(recurse)
        return query_results

    def find_members_by_path(self, role_path):
        query_role = role_path[0]
        for child_object in self.child_objects:
            if child_object.role == query_role:
                if len(role_path[1:]) and type(child_object) is NcBlock:
                    return child_object.find_members_by_path(role_path[1:])
                else:
                    return child_object
        return None

    def find_members_by_role(self, role, case_sensitive=False, match_whole_string=False, recurse=False):
        def match(query_role, role, case_sensitive, match_whole_string):
            if case_sensitive:
                return query_role == role if match_whole_string else query_role in role
            return query_role.lower() == role.lower() if match_whole_string else query_role.lower() in role.lower()

        query_results = []
        for child_object in self.child_objects:
            if match(role, child_object.role, case_sensitive, match_whole_string):
                query_results.append(child_object)
            if recurse and type(child_object) is NcBlock:
                query_results += child_object.find_members_by_role(role,
                                                                   case_sensitive,
                                                                   match_whole_string,
                                                                   recurse)
        return query_results

    def find_members_by_class_id(self, class_id, include_derived=False, recurse=False):
        def match(query_class_id, class_id, include_derived):
            if query_class_id == (class_id[:len(query_class_id)] if include_derived else class_id):
                return True
            return False

        query_results = []
        for child_object in self.child_objects:
            if match(class_id, child_object.class_id, include_derived):
                query_results.append(child_object)
            if recurse and type(child_object) is NcBlock:
                query_results += child_object.find_members_by_class_id(class_id,
                                                                       include_derived,
                                                                       recurse)
        return query_results


class NcManager(NcObject):
    def __init__(self, class_id, oid, role, role_path, runtime_constraints):
        NcObject.__init__(self, class_id, oid, role, role_path, runtime_constraints)


class NcClassManager(NcManager):
    def __init__(self, class_id, oid, role, role_path, class_descriptors, datatype_descriptors, runtime_constraints):
        NcObject.__init__(self, class_id, oid, role, role_path, runtime_constraints)
        self.class_descriptors = class_descriptors
        self.datatype_descriptors = datatype_descriptors

    def get_control_class(self, class_id, include_inherited):
        class_id_str = ".".join(map(str, class_id))
        descriptor = self.class_descriptors[class_id_str]

        if not include_inherited:
            return descriptor

        parent_class = class_id[:-1]
        inherited_descriptor = deepcopy(descriptor)

        # add inherited classes
        while len(parent_class) > 0:
            if parent_class[-1] > 0:  # Ignore Authority Keys
                class_id_str = ".".join(map(str, parent_class))
                parent_descriptor = self.class_descriptors[class_id_str]
                inherited_descriptor.properties += parent_descriptor.properties
                inherited_descriptor.methods += parent_descriptor.methods
                inherited_descriptor.events += parent_descriptor.events
            parent_class.pop()

        return inherited_descriptor

    def get_datatype(self, name, include_inherited):
        descriptor = self.datatype_descriptors[name]

        if not include_inherited or descriptor.type != NcDatatypeType.Struct:
            return descriptor

        inherited_descriptor = deepcopy(descriptor)

        while descriptor.parentType:
            parent_type = descriptor.parentType
            descriptor = self.datatype_descriptors[parent_type]
            inherited_descriptor.fields += descriptor.fields

        return inherited_descriptor
