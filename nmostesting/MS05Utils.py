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
        self.load_reference_resources()

    def reset(self):
        self.device_model = None
        self.class_manager = None

    # Overridden functions specialized for IS-12 and IS-14
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
            self.device_model = self._nc_object_factory(
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
        spec_paths.append('test_data/IS1201')  # JRT this test_data should really be MS0501 test data

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
        self.reference_class_descriptors = self._load_model_descriptors(classes_paths)

        # Load MS-05 datatype descriptors
        self.reference_datatype_descriptors = self._load_model_descriptors(datatype_paths)

        # Generate MS-05 datatype schemas from MS-05 datatype descriptors
        self.reference_datatype_schemas = self.generate_json_schemas(
            datatype_descriptors=self.reference_datatype_descriptors,
            schema_path=os.path.join(self.apis[self.protocol_api_key]["spec_path"], 'APIs/schemas/'))

    def _load_model_descriptors(self, descriptor_paths):
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
            json_schema = self.descriptor_to_schema(descriptor)
            with open(os.path.join(base_schema_path, name + '.json'), 'w') as output_file:
                json.dump(json_schema, output_file, indent=4)
                datatype_schema_names.append(name)

        # Load resolved MS-05 datatype schemas
        datatype_schemas = {}
        for name in datatype_schema_names:
            datatype_schemas[name] = load_resolved_schema(schema_path, name + '.json', path_prefix=False)

        return datatype_schemas

    def descriptor_to_schema(self, descriptor):
        variant_type = ['number', 'string', 'boolean', 'object', 'array', 'null']

        json_schema = {}
        json_schema['$schema'] = 'http://json-schema.org/draft-07/schema#'

        json_schema['title'] = descriptor['name']
        json_schema['description'] = descriptor['description'] if descriptor['description'] else ""

        # Inheritance of datatype
        if descriptor.get('parentType'):
            if descriptor.get('isSequence'):
                json_schema['type'] = 'array'
                json_schema['items'] = {'$ref': descriptor['parentType'] + '.json'}
            else:
                json_schema['allOf'] = []
                json_schema['allOf'].append({'$ref': descriptor['parentType'] + '.json'})
        # Primitive datatype
        elif descriptor['type'] == NcDatatypeType.Primitive:
            json_schema['type'] = self._primitive_to_JSON(descriptor['name'])

        # Struct datatype
        if descriptor['type'] == NcDatatypeType.Struct and descriptor.get('fields'):
            json_schema['type'] = 'object'

            required = []
            properties = {}
            for field in descriptor['fields']:
                required.append(field['name'])

                property_type = {}
                if self._primitive_to_JSON(field['typeName']):
                    if field['isNullable']:
                        property_type = {'type': [self._primitive_to_JSON(field['typeName']), 'null']}
                    else:
                        property_type = {'type': self._primitive_to_JSON(field['typeName'])}
                else:
                    if field.get('typeName'):
                        if field['isNullable']:
                            property_type['anyOf'] = []
                            property_type['anyOf'].append({'$ref': field['typeName'] + '.json'})
                            property_type['anyOf'].append({'type': 'null'})
                        else:
                            property_type = {'$ref': field['typeName'] + '.json'}
                    else:
                        # variant
                        property_type = {'type': variant_type}

                if field.get('isSequence'):
                    property_type = {'type': 'array', 'items': property_type}

                property_type['description'] = field['description'] if descriptor['description'] else ""
                properties[field['name']] = property_type

            json_schema['required'] = required
            json_schema['properties'] = properties

        # Enum datatype
        if descriptor['type'] == NcDatatypeType.Enum and descriptor.get('items'):
            json_schema['enum'] = []
            for item in descriptor['items']:
                json_schema['enum'].append(int(item['value']))
            json_schema['type'] = 'integer'

        return json_schema

    def generate_device_model_datatype_schemas(self, test):
        # Generate datatype schemas based on the datatype decriptors
        # queried from the Node under test's Device Model.
        # This will include any Non-standard data types
        class_manager = self.get_class_manager(test)

        # Create JSON schemas for the queried datatypes
        return self.generate_json_schemas(
            datatype_descriptors=class_manager.datatype_descriptors,
            schema_path=os.path.join(self.apis[self.protocol_api_key]["spec_path"], 'APIs/tmp_schemas/'))

    def validate_reference_datatype_schema(self, test, payload, datatype_name, context=""):
        """Validate payload against reference datatype schema"""
        context += f"{datatype_name}: "
        self.validate_schema(test, payload, self.reference_datatype_schemas[datatype_name], context)

    def validate_schema(self, test, payload, schema, context=""):
        """Delegates to validate_schema. Raises NMOSTestExceptions on error"""
        if not schema:
            raise NMOSTestException(test.FAIL(context + "Missing schema. "))
        try:
            # Validate the JSON schema is correct
            checker = FormatChecker(["ipv4", "ipv6", "uri"])
            validate(payload, schema, format_checker=checker)
        except ValidationError as e:
            raise NMOSTestException(test.FAIL(context + "Schema validation error: " + e.message))
        except SchemaError as e:
            raise NMOSTestException(test.FAIL(context + "Schema error: " + e.message))

        return

    def validate_descriptor(self, test, reference, descriptor, context=""):
        """Validate descriptor against reference descriptor. Raises NMOSTestException on error"""
        non_normative_keys = ['description']

        if isinstance(reference, dict):
            if descriptor is None:
                raise NMOSTestException(test.FAIL(f"{context}: descriptor is None"))
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
            if len(reference) > 0 and isinstance(reference[0], dict):
                # Convert to dict and validate
                references = {item['name']: item for item in reference}
                descriptors = {item['name']: item for item in descriptor}

                self.validate_descriptor(test, references, descriptors, context)
            elif reference != descriptor:
                raise NMOSTestException(test.FAIL(context + "Unexpected sequence. Expected: "
                                                  + str(reference)
                                                  + " actual: " + str(descriptor)))
        else:
            if reference != descriptor:
                raise NMOSTestException(test.FAIL(context + 'Expected value: '
                                                  + str(reference)
                                                  + ', actual value: '
                                                  + str(descriptor)))
        return

    def _get_class_manager_descriptors(self, test, property_id, class_manager_oid, role_path):
        response = self.get_property_value(test, property_id, oid=class_manager_oid, role_path=role_path)

        if not response:
            return None

        # Create descriptor dictionary from response array
        # Use classId as key if present, otherwise use name
        def key_lambda(classId, name): return ".".join(map(str, classId)) if classId else name
        descriptors = {key_lambda(r.get('classId'), r['name']): r for r in response}

        return descriptors

    def _nc_object_factory(self, test, class_id, oid, role, _role_path=None):
        """Create NcObject or NcBlock based on class_id"""
        # will set self.device_model_error to True if problems encountered
        if _role_path is None:
            role_path = []
        else:
            role_path = _role_path.copy()

        role_path.append(role)
        try:
            runtime_constraints = self.get_property_value(
                    test,
                    NcObjectProperties.RUNTIME_PROPERTY_CONSTRAINTS.value,
                    oid=oid,
                    role_path=role_path)

            # Check class id to determine if this is a block
            if len(class_id) > 1 and class_id[0] == 1 and class_id[1] == 1:
                member_descriptors = self.get_property_value(
                    test,
                    NcBlockProperties.MEMBERS.value,
                    oid=oid,
                    role_path=role_path)

                if member_descriptors is None:
                    raise NMOSTestException(test.FAIL('Unable to get members for object: oid={}, role Path={}'
                                                      .format(str(oid), str(role_path))))

                nc_block = NcBlock(class_id, oid, role, role_path, member_descriptors, runtime_constraints)

                for m in member_descriptors:
                    child_object = self._nc_object_factory(test, m["classId"], m["oid"], m["role"], role_path)
                    if child_object:
                        nc_block.add_child_object(child_object)

                return nc_block
            else:
                # Check to determine if this is a Class Manager
                if len(class_id) > 2 and class_id[0] == 1 and class_id[1] == 3 and class_id[2] == 2:
                    class_descriptors = self._get_class_manager_descriptors(
                        test,
                        NcClassManagerProperties.CONTROL_CLASSES.value,
                        class_manager_oid=oid,
                        role_path=role_path)

                    datatype_descriptors = self._get_class_manager_descriptors(
                        test,
                        NcClassManagerProperties.DATATYPES.value,
                        class_manager_oid=oid,
                        role_path=role_path)

                    if not class_descriptors or not datatype_descriptors:
                        raise NMOSTestException(test.FAIL('No class descriptors or datatype descriptors'
                                                          + 'found in ClassManager'))

                    return NcClassManager(class_id,
                                          oid,
                                          role,
                                          role_path,
                                          class_descriptors,
                                          datatype_descriptors,
                                          runtime_constraints)

                return NcObject(class_id, oid, role, role_path, runtime_constraints)

        except NMOSTestException as e:
            raise NMOSTestException(test.FAIL("Error in Device Model " + role + ": " + str(e.args[0].detail)))

    def get_class_manager(self, test):
        """Get the Class Manager queried from the Node under test's Device Model"""
        if not self.class_manager:
            self.class_manager = self._get_manager(test, StandardClassIds.NCCLASSMANAGER.value)

        return self.class_manager

    def get_device_manager(self, test):
        """Get the Device Manager queried from the Node under test's Device Model"""
        return self._get_manager(test, StandardClassIds.NCDEVICEMANAGER.value)

    def _get_manager(self, test, class_id):
        device_model = self.query_device_model(test)
        members = device_model.find_members_by_class_id(class_id, include_derived=True)

        spec_link = f"https://specs.amwa.tv/ms-05-02/branches/{self.apis[MS05_API_KEY]['spec_branch']}" \
            + "/docs/Managers.html"

        if len(members) == 0:
            raise NMOSTestException(test.FAIL("Manager not found in Root Block.", spec_link))

        if len(members) > 1:
            raise NMOSTestException(test.FAIL("Manager MUST be a singleton.", spec_link))

        return members[0]

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
        return '.'.join([str(v) for v in takewhile(lambda x: x > 0, class_id)])

    def is_non_standard_class(self, class_id):
        """ Check class_id to determine if it is for a non-standard class """
        # Assumes at least one value follows the authority key
        return len([v for v in dropwhile(lambda x: x > 0, class_id)]) > 1

    def is_manager(self, class_id):
        """ Check class id to determine if this is a manager """
        return len(class_id) > 1 and class_id[0] == 1 and class_id[1] == 3

    def resolve_datatype(self, test, datatype):
        """Resolve datatype to its base type"""
        class_manager = self.get_class_manager(test)
        if class_manager.datatype_descriptors[datatype].get("parentType"):
            return self.resolve_datatype(test, class_manager.datatype_descriptors[datatype].get("parentType"))
        return datatype

    def create_role_path(self, base_role_path, role):
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
    CLASS_ID = {'level': 1, 'index': 1}
    OID = {'level': 1, 'index': 2}
    CONSTANT_OID = {'level': 1, 'index': 3}
    OWNER = {'level': 1, 'index': 4}
    ROLE = {'level': 1, 'index': 5}
    USER_LABEL = {'level': 1, 'index': 6}
    TOUCHPOINTS = {'level': 1, 'index': 7}
    RUNTIME_PROPERTY_CONSTRAINTS = {'level': 1, 'index': 8}
    UNKNOWN = {'level': 9999, 'index': 9999}

    @classmethod
    def _missing_(cls, _):
        return cls.UNKNOWN


class NcObjectMethods(Enum):
    GENERIC_GET = {'level': 1, 'index': 1}
    GENERIC_SET = {'level': 1, 'index': 2}
    GET_SEQUENCE_ITEM = {'level': 1, 'index': 3}
    SET_SEQUENCE_ITEM = {'level': 1, 'index': 4}
    ADD_SEQUENCE_ITEM = {'level': 1, 'index': 5}
    REMOVE_SEQUENCE_ITEM = {'level': 1, 'index': 6}
    GET_SEQUENCE_LENGTH = {'level': 1, 'index': 7}


class NcObjectEvents(Enum):
    PROPERTY_CHANGED = {'level': 1, 'index': 1}


class NcBlockProperties(Enum):
    ENABLED = {'level': 2, 'index': 1}
    MEMBERS = {'level': 2, 'index': 2}


class NcBlockMethods(Enum):
    GET_MEMBERS_DESCRIPTOR = {'level': 2, 'index': 1}
    FIND_MEMBERS_BY_PATH = {'level': 2, 'index': 2}
    FIND_MEMBERS_BY_ROLE = {'level': 2, 'index': 3}
    FIND_MEMBERS_BY_CLASS_ID = {'level': 2, 'index': 4}


class NcClassManagerProperties(Enum):
    CONTROL_CLASSES = {'level': 3, 'index': 1}
    DATATYPES = {'level': 3, 'index': 2}


class NcClassManagerMethods(Enum):
    GET_CONTROL_CLASS = {'level': 3, 'index': 1}
    GET_DATATYPE = {'level': 3, 'index': 2}


class NcDeviceManagerProperties(Enum):
    NCVERSION = {'level': 3, 'index': 1}


class StandardClassIds(Enum):
    NCOBJECT = [1]
    NCBLOCK = [1, 1]
    NCWORKER = [1, 2]
    NCMANAGER = [1, 3]
    NCDEVICEMANAGER = [1, 3, 1]
    NCCLASSMANAGER = [1, 3, 2]


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
                inherited_descriptor["properties"] += parent_descriptor["properties"]
                inherited_descriptor["methods"] += parent_descriptor["methods"]
                inherited_descriptor["events"] += parent_descriptor["events"]
            parent_class.pop()

        return inherited_descriptor

    def get_datatype(self, name, include_inherited):
        descriptor = self.datatype_descriptors[name]

        if not include_inherited or descriptor["type"] != NcDatatypeType.Struct:
            return descriptor

        inherited_descriptor = deepcopy(descriptor)

        while descriptor.get("parentType"):
            parent_type = descriptor.get("parentType")
            descriptor = self.datatype_descriptors[parent_type]
            inherited_descriptor["fields"] += descriptor["fields"]

        return inherited_descriptor
