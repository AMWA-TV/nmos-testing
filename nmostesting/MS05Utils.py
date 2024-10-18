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
    def get_property(test, property_id, **kwargs):
        pass

    def get_property_value(self, test, property_id, **kwargs):
        pass

    def set_property(self, test, property_id, argument, **kwargs):
        pass

    def invoke_method(self, test, method_id, argument, **kwargs):
        pass

    def get_sequence_item(self, test, property_id, index, **kwargs):
        pass

    def get_sequence_item_value(self, test, property_id, index, **kwargs):
        """Get value from sequence property. Raises NMOSTestException on error"""
        pass

    def get_sequence_length(self, test, property_id, **kwargs):
        """Get sequence length. Raises NMOSTestException on error"""
        pass

    def set_sequence_item(self, test, property_id, index, value, **kwargs):
        """Add value to a sequence property. Raises NMOSTestException on error"""
        pass

    def add_sequence_item(self, test, property_id, value, **kwargs):
        """Add value to a sequence property. Raises NMOSTestException on error"""
        pass

    def remove_sequence_item(self, test, property_id, index, **kwargs):
        """Get value from sequence property. Raises NMOSTestException on error"""
        pass

    def get_member_descriptors(self, test, recurse, **kwargs):
        pass

    def find_members_by_path(self, test, path, **kwargs):
        """Query members based on role path. Raises NMOSTestException on error"""
        pass

    def find_members_by_role(self, test, role, case_sensitive, match_whole_string, recurse, **kwargs):
        """Query members based on role. Raises NMOSTestException on error"""
        pass

    def find_members_by_class_id(self, test, class_id, include_derived, recurse, **kwargs):
        """Query members based on class id. Raises NMOSTestException on error"""
        pass

    def get_control_class(self, test, class_id, include_inherited, **kwargs):
        """Query Class Manager for control class. Raises NMOSTestException on error"""
        pass

    def get_datatype(self, test, name, include_inherited, **kwargs):
        """Query Class Manager for datatype. Raises NMOSTestException on error"""
        pass

    # End of overridden functions

    def query_device_model(self, test):
        """ Query Device Model from the Node under test.
            self.device_model_metadata set on Device Model validation error.
            NMOSTestException raised if unable to query Device Model """
        if not self.device_model:
            self.device_model = self.create_device_model(
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

    def datatype_descriptor_factory(self, descriptor_json):
        if "fields" in descriptor_json and "parentType" in descriptor_json:
            return NcDatatypeDescriptorStruct(descriptor_json)

        if "parentType" in descriptor_json and "isSequence" in descriptor_json:
            return NcDatatypeDescriptorTypeDef(descriptor_json)

        if "items" in descriptor_json:
            return NcDatatypeDescriptorEnum(descriptor_json)

        return NcDatatypeDescriptorPrimitive(descriptor_json)

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
                            descriptors[name] = self.datatype_descriptor_factory(descriptor)

        return descriptors

    def generate_json_schemas(self, datatype_descriptors, schema_path):
        """Generate datatype schemas from datatype descriptors"""
        datatype_schema_names = []
        base_schema_path = os.path.abspath(schema_path)
        if not os.path.exists(base_schema_path):
            os.makedirs(base_schema_path)

        for name, descriptor in datatype_descriptors.items():
            json_schema = self._descriptor_to_schema(descriptor.json)
            with open(os.path.join(base_schema_path, name + ".json"), "w") as output_file:
                json.dump(json_schema, output_file, indent=4)
                datatype_schema_names.append(name)

        # Load resolved MS-05 datatype schemas
        datatype_schemas = {}
        for name in datatype_schema_names:
            datatype_schemas[name] = load_resolved_schema(schema_path, name + ".json", path_prefix=False)

        return datatype_schemas

    def _descriptor_to_schema(self, descriptor):
        variant_type = ["number", "string", "boolean", "object", "array", "null"]

        json_schema = {}
        json_schema["$schema"] = "http://json-schema.org/draft-07/schema#"

        json_schema["title"] = descriptor["name"]
        json_schema["description"] = descriptor["description"] if descriptor["description"] else ""

        # Inheritance of datatype
        if descriptor.get("parentType"):
            if descriptor.get("isSequence"):
                json_schema["type"] = "array"
                json_schema["items"] = {"$ref": descriptor["parentType"] + ".json"}
            else:
                json_schema["allOf"] = []
                json_schema["allOf"].append({"$ref": descriptor["parentType"] + ".json"})
        # Primitive datatype
        elif descriptor["type"] == NcDatatypeType.Primitive:
            json_schema["type"] = self._primitive_to_JSON(descriptor["name"])

        # Struct datatype
        if descriptor["type"] == NcDatatypeType.Struct and descriptor.get("fields"):
            json_schema["type"] = "object"

            required = []
            properties = {}
            for field in descriptor["fields"]:
                required.append(field["name"])

                property_type = {}
                if self._primitive_to_JSON(field["typeName"]):
                    if field["isNullable"]:
                        property_type = {"type": [self._primitive_to_JSON(field["typeName"]), "null"]}
                    else:
                        property_type = {"type": self._primitive_to_JSON(field["typeName"])}
                else:
                    if field.get("typeName"):
                        if field["isNullable"]:
                            property_type["anyOf"] = []
                            property_type["anyOf"].append({"$ref": field["typeName"] + ".json"})
                            property_type["anyOf"].append({"type": "null"})
                        else:
                            property_type = {"$ref": field["typeName"] + ".json"}
                    else:
                        # variant
                        property_type = {"type": variant_type}

                if field.get("isSequence"):
                    property_type = {"type": "array", "items": property_type}

                property_type["description"] = field["description"] if descriptor["description"] else ""
                properties[field["name"]] = property_type

            json_schema["required"] = required
            json_schema["properties"] = properties

        # Enum datatype
        if descriptor["type"] == NcDatatypeType.Enum and descriptor.get("items"):
            json_schema["enum"] = []
            for item in descriptor["items"]:
                json_schema["enum"].append(int(item["value"]))
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

    def get_datatype_schema(self, test, type_name):
        """Get generated JSON schema for datatype specified, based on descriptor queried from the Node under Test"""
        if not self.datatype_schemas:
            self.datatype_schemas = self._generate_device_model_datatype_schemas(test)

        return self.datatype_schemas.get(type_name)

    def queried_datatype_schema_validate(self, test, payload, datatype_name, context=""):
        """Validate payload against datatype schema queried from Node under Test Class Manager"""
        datatype_schema = self.get_datatype_schema(test, datatype_name)
        self._validate_schema(test, payload, datatype_schema, f"{context}{datatype_name}")

    def reference_datatype_schema_validate(self, test, payload, datatype_name, context=""):
        """Validate payload against reference datatype schema"""
        context += f"{datatype_name}: "
        self._validate_schema(test, payload, self.reference_datatype_schemas[datatype_name],
                              f"{context}{datatype_name}")

    def _validate_schema(self, test, payload, schema, context=""):
        """Delegates to jsonschema validate. Raises NMOSTestExceptions on error"""
        if not schema:
            raise NMOSTestException(test.FAIL(f"Missing schema. Possible unknown type: {context}"))
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

        # Compare disctionaries
        if isinstance(reference, dict):
            # NcDescriptor objects have a json field that caches the json used to construct it
            reference.pop("json", None)

            reference_keys = set(reference.keys())
            descriptor_keys = set(descriptor.keys())

            # compare the keys to see if any extra/missing
            key_diff = (set(reference_keys) | set(descriptor_keys)) - (set(reference_keys) & set(descriptor_keys))
            if len(key_diff) > 0:
                error_description = "Missing keys " if set(key_diff) <= set(reference_keys) else "Additional keys "
                raise NMOSTestException(test.FAIL(f"{context}{error_description}{str(key_diff)}"))
            for key in reference_keys:
                # Ignore keys that contain non-normative information
                if key in non_normative_keys:
                    continue
                self.validate_descriptor(test, reference[key], descriptor[key], context=context + key + "->")
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
        # If the reference is an object then convert to a dict before comparison
        elif isinstance(reference, (NcDescriptor, NcElementId)):
            self.validate_descriptor(test, reference.__dict__, descriptor, context)
        # Compare primitives and primitive arrays directly
        elif reference != descriptor:
            raise NMOSTestException(test.FAIL(f"{context}Expected value: "
                                    f"{str(reference)}, actual value: {str(descriptor)}"))
        return

    def _get_class_manager_datatype_descriptors(self, test, class_manager_oid, role_path):
        response = self.get_property_value(test, NcClassManagerProperties.DATATYPES.value,
                                           oid=class_manager_oid, role_path=role_path)

        if not response:
            return None

        # Validate descriptors against schema
        for r in response:
            self.reference_datatype_schema_validate(test, r, NcDatatypeDescriptor.__name__,
                                                    "/".join([str(r) for r in role_path]))

        # Create NcDescriptor dictionary from response array
        descriptors = {r["name"]: self.datatype_descriptor_factory(r) for r in response}

        return descriptors

    def _get_class_manager_class_descriptors(self, test, class_manager_oid, role_path):
        response = self.get_property_value(test, NcClassManagerProperties.CONTROL_CLASSES.value,
                                           oid=class_manager_oid, role_path=role_path)

        if not response:
            return None

        # Validate descriptors
        for r in response:
            self.reference_datatype_schema_validate(test, r, NcClassDescriptor.__name__,
                                                    "/".join([str(r) for r in role_path]))

        # Create NcClassDescriptor dictionary from response array
        def key_lambda(classId): return ".".join(map(str, classId))
        descriptors = {key_lambda(r.get("classId")): NcClassDescriptor(r) for r in response}
        return descriptors

    def create_device_model(self, test, class_id, oid, role, _role_path=None):
        """Recursively create Device Model hierarchy"""
        # will set self.device_model_error to True if problems encountered
        if _role_path is None:
            role_path = []
        else:
            role_path = _role_path.copy()
        role_path.append(role)

        try:
            runtime_constraints = self.get_property_value(
                    test, NcObjectProperties.RUNTIME_PROPERTY_CONSTRAINTS.value,
                    oid=oid, role_path=role_path)

            if self.is_block(class_id):
                member_descriptors = self.get_property_value(
                    test, NcBlockProperties.MEMBERS.value,
                    oid=oid, role_path=role_path)

                if member_descriptors is None:
                    raise NMOSTestException(test.FAIL("Unable to get members for object: "
                                                      f"oid={str(oid)}, role Path={str(role_path)}"))

                block_member_descriptors = []
                for m in member_descriptors:
                    self.reference_datatype_schema_validate(test, m, NcBlockMemberDescriptor.__name__,
                                                            "/".join([str(r) for r in role_path]))
                    block_member_descriptors.append(NcBlockMemberDescriptor(m))

                nc_block = NcBlock(class_id, oid, role, role_path, block_member_descriptors, runtime_constraints)

                for m in member_descriptors:
                    child_object = self.create_device_model(test, m["classId"], m["oid"], m["role"], role_path)
                    if child_object:
                        nc_block.add_child_object(child_object)

                return nc_block
            else:
                if self.is_class_manager(class_id):
                    class_descriptors = self._get_class_manager_class_descriptors(
                        test, class_manager_oid=oid, role_path=role_path)

                    datatype_descriptors = self._get_class_manager_datatype_descriptors(
                        test, class_manager_oid=oid, role_path=role_path)

                    if not class_descriptors or not datatype_descriptors:
                        raise NMOSTestException(test.FAIL("No class descriptors or datatype descriptors"
                                                          + "found in ClassManager"))

                    return NcClassManager(class_id, oid, role, role_path,
                                          class_descriptors, datatype_descriptors,
                                          runtime_constraints)

                return NcObject(class_id, oid, role, role_path, runtime_constraints)

        except NMOSTestException as e:
            raise NMOSTestException(test.FAIL(f"Error in Device Model {role}: {str(e.args[0].detail)}"))

    def _get_object_by_class_id(self, test, class_id):
        device_model = self.query_device_model(test)
        members = device_model.find_members_by_class_id(class_id, include_derived=True)

        spec_link = f"https://specs.amwa.tv/ms-05-02/branches/{self.apis[MS05_API_KEY]["spec_branch"]}" \
            + "/docs/Managers.html"

        if len(members) == 0:
            raise NMOSTestException(test.FAIL("Manager not found in Root Block.", spec_link))

        if len(members) > 1:
            raise NMOSTestException(test.FAIL("Manager MUST be a singleton.", spec_link))

        return members[0]

    def get_class_manager(self, test):
        """Get the Class Manager queried from the Node under test's Device Model"""
        if not self.class_manager:
            self.class_manager = self._get_object_by_class_id(test, StandardClassIds.NCCLASSMANAGER.value)

        return self.class_manager

    def get_device_manager(self, test):
        """Get the Device Manager queried from the Node under test's Device Model"""
        return self._get_object_by_class_id(test, StandardClassIds.NCDEVICEMANAGER.value)

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

    def is_class_manager(self, class_id):
        """ Check class id to determine is this is a class manager class_id """
        return len(class_id) > 2 and class_id[0] == 1 and class_id[1] == 3 and class_id[2] == 2

    def is_block(self, class_id):
        """ Check class id to determine if this is a block class_id"""
        return len(class_id) > 1 and class_id[0] == 1 and class_id[1] == 1

    def resolve_datatype(self, test, datatype):
        """Resolve datatype to its base type"""
        class_manager = self.get_class_manager(test)
        datatype_descriptor = class_manager.datatype_descriptors[datatype]
        if isinstance(datatype_descriptor, (NcDatatypeDescriptorStruct, NcDatatypeDescriptorTypeDef)) and \
                class_manager.datatype_descriptors[datatype].parentType:
            return self.resolve_datatype(test, class_manager.datatype_descriptors[datatype].parentType)
        return datatype

    def create_role_path(self, base_role_path, role):
        """Appends role to base_role_path"""
        role_path = base_role_path.copy()
        role_path.append(role)
        return role_path


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


class NcObjectProperties(Enum):
    CLASS_ID = {"level": 1, "index": 1}
    OID = {"level": 1, "index": 2}
    CONSTANT_OID = {"level": 1, "index": 3}
    OWNER = {"level": 1, "index": 4}
    ROLE = {"level": 1, "index": 5}
    USER_LABEL = {"level": 1, "index": 6}
    TOUCHPOINTS = {"level": 1, "index": 7}
    RUNTIME_PROPERTY_CONSTRAINTS = {"level": 1, "index": 8}
    UNKNOWN = {"level": 9999, "index": 9999}

    @classmethod
    def _missing_(cls, _):
        return cls.UNKNOWN


class NcObjectMethods(Enum):
    GENERIC_GET = {"level": 1, "index": 1}
    GENERIC_SET = {"level": 1, "index": 2}
    GET_SEQUENCE_ITEM = {"level": 1, "index": 3}
    SET_SEQUENCE_ITEM = {"level": 1, "index": 4}
    ADD_SEQUENCE_ITEM = {"level": 1, "index": 5}
    REMOVE_SEQUENCE_ITEM = {"level": 1, "index": 6}
    GET_SEQUENCE_LENGTH = {"level": 1, "index": 7}


class NcObjectEvents(Enum):
    PROPERTY_CHANGED = {"level": 1, "index": 1}


class NcBlockProperties(Enum):
    ENABLED = {"level": 2, "index": 1}
    MEMBERS = {"level": 2, "index": 2}


class NcBlockMethods(Enum):
    GET_MEMBERS_DESCRIPTOR = {"level": 2, "index": 1}
    FIND_MEMBERS_BY_PATH = {"level": 2, "index": 2}
    FIND_MEMBERS_BY_ROLE = {"level": 2, "index": 3}
    FIND_MEMBERS_BY_CLASS_ID = {"level": 2, "index": 4}


class NcClassManagerProperties(Enum):
    CONTROL_CLASSES = {"level": 3, "index": 1}
    DATATYPES = {"level": 3, "index": 2}


class NcClassManagerMethods(Enum):
    GET_CONTROL_CLASS = {"level": 3, "index": 1}
    GET_DATATYPE = {"level": 3, "index": 2}


class NcDeviceManagerProperties(Enum):
    NCVERSION = {"level": 3, "index": 1}


class StandardClassIds(Enum):
    NCOBJECT = [1]
    NCBLOCK = [1, 1]
    NCWORKER = [1, 2]
    NCMANAGER = [1, 3]
    NCDEVICEMANAGER = [1, 3, 1]
    NCCLASSMANAGER = [1, 3, 2]


class NcElementId():
    def __init__(self, id_json):
        self.level = id_json["level"]  # Level of the element
        self.index = id_json["index"]  # Index of the element


class NcPropertyId(NcElementId):
    def __init__(self, id_json):
        NcElementId.__init__(self, id_json)


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
        self.constraints = descriptor_json["constraints"]  # Optional constraints on top of the underlying data type


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
        self.methods = descriptor_json["methods"]  # Method descriptors
        self.events = descriptor_json["events"]  # Event descriptors


class NcDatatypeDescriptor(NcDescriptor):
    def __init__(self, descriptor_json):
        NcDescriptor.__init__(self, descriptor_json)
        self.name = descriptor_json["name"]  # Datatype name
        self.type = descriptor_json["type"]  # Type: Primitive, Typedef, Struct, Enum
        self.constraints = descriptor_json["constraints"]  # Optional constraints on top of the underlying data type


class NcDatatypeDescriptorEnum(NcDatatypeDescriptor):
    def __init__(self, descriptor_json):
        NcDatatypeDescriptor.__init__(self, descriptor_json)
        self.items = descriptor_json["items"]


class NcDatatypeDescriptorPrimitive(NcDatatypeDescriptor):
    def __init__(self, descriptor_json):
        NcDatatypeDescriptor.__init__(self, descriptor_json)


class NcDatatypeDescriptorStruct(NcDatatypeDescriptor):
    def __init__(self, descriptor_json):
        NcDatatypeDescriptor.__init__(self, descriptor_json)
        self.fields = descriptor_json["fields"]
        self.parentType = descriptor_json["parentType"]


class NcDatatypeDescriptorTypeDef(NcDatatypeDescriptor):
    def __init__(self, descriptor_json):
        NcDatatypeDescriptor.__init__(self, descriptor_json)
        self.parentType = descriptor_json["parentType"]  # Original typedef datatype name
        self.isSequence = descriptor_json["isSequence"]  # TRUE iff type is a typedef sequence of another type


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
