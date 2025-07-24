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
from typing import Optional, Union

from .GenericTest import NMOSTestException, GenericTest
from .TestResult import Test
from .TestHelper import load_resolved_schema

MS05_API_KEY = "controlframework"
FEATURE_SETS_KEY = "featuresets"
NODE_API_KEY = "node"


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

    def __hash__(self):
        return hash(str(self))


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
        self.constraints = NcParameterConstraints.factory(descriptor_json["constraints"], "property")  # Optional

    def __str__(self):
        return f"[id={self.id}, name={self.name}, typeName={self.typeName}, " \
            f"isReadOnly={self.isReadOnly}, owner={self.isNullable}, " \
            f"isSequence={self.isSequence}, isDeprecated={self.isDeprecated}, " \
            f"constraints={self.constraints}]"

    def __eq__(self, other):
        if not isinstance(other, NcPropertyDescriptor):
            return NotImplemented
        return self.id == other.id and self.name == other.name and self.typeName == other.typeName \
            and self.isReadOnly == other.isReadOnly and self.isNullable == other.isNullable \
            and self.isSequence == other.isSequence and self.isDeprecated == other.isDeprecated \
            and self.constraints == other.constraints


class NcBlockMemberDescriptor(NcDescriptor):
    def __init__(self, descriptor_json):
        NcDescriptor.__init__(self, descriptor_json)
        self.role = descriptor_json["role"]  # Role of member in its containing block
        self.oid = descriptor_json["oid"]  # OID of member
        self.constantOid = descriptor_json["constantOid"]  # TRUE iff member's OID is hardwired into device
        self.classId = descriptor_json["classId"]  # Class ID
        self.userLabel = descriptor_json["userLabel"]  # User label
        self.owner = descriptor_json["owner"]  # Containing block's OID

    def __eq__(self, other):
        if not isinstance(other, NcBlockMemberDescriptor):
            return NotImplemented
        # Don't compare description or user label
        return self.role == other.role and self.oid == other.oid and self.constantOid == other.constantOid \
            and self.classId == other.classId and self.owner == other.owner

    def __str__(self):
        return f"[role={self.role}, oid={self.oid}, constantOID={self.constantOid}, " \
            f"classId={self.classId}, owner={self.owner}]"


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
        self.constraints = NcParameterConstraints.factory(descriptor_json["constraints"], "datatype")  # Optional

    @staticmethod
    def get_descriptor_type(descriptor_json):
        if "fields" in descriptor_json and "parentType" in descriptor_json:
            return "NcDatatypeDescriptorStruct"

        if "parentType" in descriptor_json and "isSequence" in descriptor_json:
            return "NcDatatypeDescriptorTypeDef"

        if "items" in descriptor_json:
            return "NcDatatypeDescriptorEnum"

        return "NcDatatypeDescriptorPrimitive"

    @staticmethod
    def factory(descriptor_json):
        """Instantiate concrete NcDatatypeDescriptor object"""
        descriptor_type = NcDatatypeDescriptor.get_descriptor_type(descriptor_json)

        if descriptor_type == "NcDatatypeDescriptorStruct":
            return NcDatatypeDescriptorStruct(descriptor_json)

        if descriptor_type == "NcDatatypeDescriptorTypeDef":
            return NcDatatypeDescriptorTypeDef(descriptor_json)

        if descriptor_type == "NcDatatypeDescriptorEnum":
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


class NcEventDescriptor(NcDescriptor):
    def __init__(self, event_json):
        NcDescriptor.__init__(self, event_json)
        self.id = event_json["id"]  # Event id with level and index
        self.name = event_json["name"]  # Name of event
        self.eventDatatype = event_json["eventDatatype"]  # Name of event data's datatype
        self.isDeprecated = event_json["isDeprecated"]  # TRUE iff property is marked as deprecated


class NcFieldDescriptor(NcDescriptor):
    def __init__(self, descriptor_json):
        NcDescriptor.__init__(self, descriptor_json)
        self.name = descriptor_json["name"]  # Name of field
        self.typeName = descriptor_json["typeName"]  # Name of field's datatype.
        self.isNullable = descriptor_json["isNullable"]  # TRUE iff field is nullable
        self.isSequence = descriptor_json["isSequence"]  # TRUE iff field is a sequence
        self.constraints = NcParameterConstraints.factory(descriptor_json["constraints"], "field")  # Optional


class NcParameterDescriptor(NcDescriptor):
    def __init__(self, descriptor_json):
        NcDescriptor.__init__(self, descriptor_json)
        self.name = descriptor_json["name"]  # Name of parameter
        self.typeName = descriptor_json["typeName"]  # Name of parameter's datatype.
        self.isNullable = descriptor_json["isNullable"]  # TRUE iff parameter is nullable
        self.isSequence = descriptor_json["isSequence"]  # TRUE iff parameter is a sequence
        self.constraints = NcParameterConstraints.factory(descriptor_json["constraints"], "parameter")  # Optional


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
    def __init__(self, constraints_json, level):
        self.defaultValue = constraints_json["defaultValue"]  # Default value
        self.level = level

    def __str__(self):
        return f"level={self.level}, defaultValue={self.defaultValue}"

    @staticmethod
    def factory(constraints_json, level=""):
        if constraints_json is None:
            return None
        if "minimum" in constraints_json and "maximum" in constraints_json and "step" in constraints_json:
            return NcParameterConstraintsNumber(constraints_json, level)
        if "maxCharacters" in constraints_json and "pattern" in constraints_json:
            return NcParameterConstraintsString(constraints_json, level)
        return NcParameterConstraints(constraints_json, level)


class NcParameterConstraintsNumber(NcParameterConstraints):
    def __init__(self, constraints_json, level):
        NcParameterConstraints.__init__(self, constraints_json, level)
        self.maximum = constraints_json["maximum"]  # Optional maximum
        self.minimum = constraints_json["minimum"]  # Optional minimum
        self.step = constraints_json["step"]  # Optional step

    def __str__(self):
        return f"[{super(NcParameterConstraintsNumber, self).__str__()}, " \
            f"maximum={self.maximum}, minimum={self.minimum}, step={self.step}]"

    def __eq__(self, other):
        if not isinstance(other, NcParameterConstraintsNumber):
            return NotImplemented
        return self.maximum == other.maximum and self.minimum == other.minimum \
            and self.step == other.step


class NcParameterConstraintsString(NcParameterConstraints):
    def __init__(self, constraints_json, level):
        NcParameterConstraints.__init__(self, constraints_json, level)
        self.maxCharacters = constraints_json["maxCharacters"]  # Maximum characters allowed
        self.pattern = constraints_json["pattern"]  # Regex pattern

    def __str__(self):
        return f"[{super(NcParameterConstraintsString, self).__str__()}, " \
            f"maxCharacters={self.maxCharacters}, pattern={self.pattern}]"

    def __eq__(self, other):
        if not isinstance(other, NcParameterConstraintsString):
            return NotImplemented
        return self.maxCharacters == other.maxCharacters and self.pattern == other.pattern


class NcPropertyConstraints:
    def __init__(self, constraints_json, level):
        self.propertyId = NcPropertyId(constraints_json["propertyId"])  # Property being constrained
        self.defaultValue = constraints_json["defaultValue"]  # Default value
        self.level = "runtime"

    def __str__(self):
        return f"propertyId={self.propertyId}, level={self.level}, defaultValue={self.defaultValue}"

    @staticmethod
    def factory(constraints_json, level=""):
        if "minimum" in constraints_json and "maximum" in constraints_json and "step" in constraints_json:
            return NcPropertyConstraintsNumber(constraints_json, level)
        if "maxCharacters" in constraints_json and "pattern" in constraints_json:
            return NcPropertyConstraintsString(constraints_json, level)
        return NcPropertyConstraints(constraints_json, level)


class NcPropertyConstraintsNumber(NcPropertyConstraints):
    def __init__(self, constraints_json, level):
        NcPropertyConstraints.__init__(self, constraints_json, level)
        self.maximum = constraints_json["maximum"]  # Optional maximum
        self.minimum = constraints_json["minimum"]  # Optional minimum
        self.step = constraints_json["step"]  # Optional step

    def __str__(self):
        return f"[{super(NcPropertyConstraintsNumber, self).__str__()}, " \
            f"maximum={self.maximum}, minimum={self.minimum}, step={self.step}]"


class NcPropertyConstraintsString(NcPropertyConstraints):
    def __init__(self, constraints_json, level):
        NcPropertyConstraints.__init__(self, constraints_json, level)
        self.maxCharacters = constraints_json["maxCharacters"]  # Maximum characters allowed
        self.pattern = constraints_json["pattern"]  # Regex pattern

    def __str__(self):
        return f"[{super(NcPropertyConstraintsString, self).__str__()}, " \
            f"maxCharacters={self.maxCharacters}, pattern={self.pattern}]"


class NcPropertyChangeType(IntEnum):
    ValueChanged = 0  # Current value changed
    SequenceItemAdded = 1  # Sequence item added
    SequenceItemChanged = 2  # Sequence item changed
    SequenceItemRemoved = 3  # Sequence item removed
    UNKNOWN = 9999

    @classmethod
    def _missing_(cls, _):
        return cls.UNKNOWN


class NcPropertyChangedEventData():
    def __init__(self, event_data_json):
        self.propertyId = NcPropertyId(event_data_json["propertyId"])  # The id of the property that changed
        self.changeType = NcPropertyChangeType(event_data_json["changeType"])
        self.value = event_data_json["value"]  # Property-type specific value
        self.sequenceItemIndex = event_data_json["sequenceItemIndex"]  # Index of item if property is sequence


class NcObject():
    def __init__(self, class_id: list, oid: int, owner: Optional[int], role: str, role_path: list,
                 runtime_constraints: Optional[NcPropertyConstraints],
                 member_descriptor: NcBlockMemberDescriptor):
        self.class_id = class_id
        self.oid = oid
        self.owner = owner
        self.role = role
        self.role_path = role_path
        self.runtime_constraints = runtime_constraints
        self.member_descriptor = member_descriptor


class NcBlock(NcObject):
    def __init__(self, class_id: list, oid: int, owner: Optional[int], role: str, role_path: list,
                 runtime_constraints: Optional[NcPropertyConstraints],
                 member_descriptor: NcBlockMemberDescriptor):
        NcObject.__init__(self, class_id, oid, owner, role, role_path, runtime_constraints, member_descriptor)
        self.child_objects = []

    # Utility Methods
    def add_child_object(self, nc_object):
        self.child_objects.append(nc_object)

    def get_role_paths(self) -> list[list[str]]:
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

    def get_oids(self, root=True) -> list[int]:
        oids = [self.oid] if root else []
        for child_object in self.child_objects:
            oids.append(child_object.oid)
            if type(child_object) is NcBlock:
                oids += child_object.get_oids(False)
        return oids

    def find_object_by_path(self, role_path) -> NcObject:
        """Helper function to locate an NcObject by role path"""
        # Returns None if role path can't be found
        if role_path == self.role_path:
            return self

        ret_val = None
        for child_object in self.child_objects:
            if isinstance(child_object, NcBlock):
                ret_val = child_object.find_object_by_path(role_path)
                if ret_val:
                    break
        return ret_val

    # NcBlock Methods
    def get_member_descriptors(self, recurse=False) -> list[NcBlockMemberDescriptor]:
        query_results = []
        for child_object in self.child_objects:
            query_results.append(child_object.member_descriptor)
            if recurse and type(child_object) is NcBlock:
                query_results += child_object.get_member_descriptors(recurse)
        return query_results

    def find_members_by_path(self, role_path) -> list[NcBlockMemberDescriptor]:
        query_results = []
        query_role = role_path[0]
        for child_object in self.child_objects:
            if child_object.role == query_role:
                if len(role_path[1:]) and type(child_object) is NcBlock:
                    query_results += child_object.find_members_by_path(role_path[1:])
                else:
                    query_results.append(child_object.member_descriptor)
        return query_results

    def find_members_by_role(self,
                             role,
                             case_sensitive=False,
                             match_whole_string=False,
                             recurse=False) -> list[NcBlockMemberDescriptor]:
        def match(query_role, role, case_sensitive, match_whole_string):
            if case_sensitive:
                return query_role == role if match_whole_string else query_role in role
            return query_role.lower() == role.lower() if match_whole_string else query_role.lower() in role.lower()

        query_results = []
        for child_object in self.child_objects:
            if match(role, child_object.role, case_sensitive, match_whole_string):
                query_results.append(child_object.member_descriptor)
            if recurse and type(child_object) is NcBlock:
                query_results += child_object.find_members_by_role(role,
                                                                   case_sensitive,
                                                                   match_whole_string,
                                                                   recurse)
        return query_results

    def find_members_by_class_id(self,
                                 class_id,
                                 include_derived=False,
                                 recurse=False,
                                 get_objects=False) -> Union[list[NcBlockMemberDescriptor], list[NcObject]]:
        def match(query_class_id, class_id, include_derived):
            if query_class_id == (class_id[:len(query_class_id)] if include_derived else class_id):
                return True
            return False

        query_results = []
        for child_object in self.child_objects:
            if match(class_id, child_object.class_id, include_derived):
                # if get_objects is set returns NcObject rather than NcBlockMemberDescriptor
                query_results.append(child_object if get_objects else child_object.member_descriptor)
            if recurse and type(child_object) is NcBlock:
                query_results += child_object.find_members_by_class_id(class_id,
                                                                       include_derived,
                                                                       recurse,
                                                                       get_objects)
        return query_results


class NcManager(NcObject):
    def __init__(self, class_id: list, oid: int, owner: Optional[int], role: list, role_path: str,
                 runtime_constraints: Optional[NcPropertyConstraints],
                 member_descriptor: NcBlockMemberDescriptor):
        NcObject.__init__(self, class_id, oid, owner, role, role_path, runtime_constraints, member_descriptor)


class NcClassManager(NcManager):
    def __init__(self, class_id: list, oid: int, owner: Optional[int], role: list, role_path: str,
                 class_descriptors: list[NcClassDescriptor],
                 datatype_descriptors: list[NcDatatypeDescriptor],
                 runtime_constraints: Optional[NcPropertyConstraints],
                 member_descriptor: NcBlockMemberDescriptor):
        NcObject.__init__(self, class_id, oid, owner, role, role_path, runtime_constraints, member_descriptor)
        self.class_descriptors = class_descriptors
        self.datatype_descriptors = datatype_descriptors

    def get_control_class(self, class_id, include_inherited=True) -> NcClassDescriptor:
        class_id_str = ".".join(map(str, class_id))
        descriptor = self.class_descriptors.get(class_id_str)

        if not include_inherited or not descriptor:
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

    def get_datatype(self, name, include_inherited=True) -> NcDatatypeDescriptor:
        descriptor = self.datatype_descriptors.get(name)

        if not include_inherited or not descriptor or descriptor.type != NcDatatypeType.Struct:
            return descriptor

        inherited_descriptor = deepcopy(descriptor)

        while descriptor.parentType:
            parent_type = descriptor.parentType
            descriptor = self.datatype_descriptors[parent_type]
            inherited_descriptor.fields += descriptor.fields

        return inherited_descriptor


class MS05PropertyMetadata():
    def __init__(self, oid, role_path, name, constraints, datatype_type, descriptor):
        self.oid = oid
        self.role_path = role_path
        self.name = name
        self.constraints = constraints
        self.datatype_type = datatype_type
        self.descriptor = descriptor


class MS05MethodMetadata():
    def __init__(self, oid, role_path, name, descriptor):
        self.oid = oid
        self.role_path = role_path
        self.name = name
        self.descriptor = descriptor


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
        """Get property vlaue from object. Raises NMOSTestException on error"""
        pass

    def set_property_override(self, test, property_id, argument, **kwargs):
        """Set property value on object. Raises NMOSTestException on error"""
        pass

    def invoke_method_override(self, test, method_id, argument, **kwargs):
        """Invoke method on Node. Raises NMOSTestException on error"""
        pass

    def get_sequence_item_override(self, test, property_id, index, **kwargs):
        """Get sequence value. Raises NMOSTestException on error"""
        pass

    def set_sequence_item_override(self, test, property_id, index, value, **kwargs):
        """Add value to a sequence property. Raises NMOSTestException on error"""
        pass

    def add_sequence_item_override(self, test, property_id, value, **kwargs):
        """Add value to a sequence. Raises NMOSTestException on error"""
        pass

    def remove_sequence_item_override(self, test, property_id, index, **kwargs):
        """Remove a sequence value. Raises NMOSTestException on error"""
        pass

    def get_sequence_length_override(self, test, property_id, **kwargs):
        """Get sequence length. Raises NMOSTestException on error"""
        pass

    def get_member_descriptors_override(self, test, recurse, **kwargs):
        """Get NcBlockMemberDescriptors for this block. Raises NMOSTestException on error"""
        pass

    def find_members_by_path_override(self, test, path, **kwargs):
        """Query for NcBlockMemberDescriptors based on role path. Raises NMOSTestException on error"""
        pass

    def find_members_by_role_override(self, test, role, case_sensitive, match_whole_string, recurse, **kwargs):
        """Query for NcBlockMemberDescriptors based on role. Raises NMOSTestException on error"""
        pass

    def find_members_by_class_id_override(self, test, class_id, include_derived, recurse, **kwargs):
        """Query for NcBlockMemberDescriptors based on class id. Raises NMOSTestException on error"""
        pass

    def get_control_class_override(self, test, class_id, include_inherited, **kwargs):
        """Query Class Manager for NcClassDescriptor. Raises NMOSTestException on error"""
        pass

    def get_datatype_override(self, test, name, include_inherited, **kwargs):
        """Query Class Manager for NcDatatypeDescriptor. Raises NMOSTestException on error"""
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
        """Get item from a sequence property. Returns NcMethodResult. Raises NMOSTestException on error"""
        result = self.get_sequence_item_override(test, property_id, index, **kwargs)
        self.reference_datatype_schema_validate(test, result, NcMethodResult.__name__,
                                                role_path=kwargs.get("role_path"))
        return NcMethodResult.factory(result)

    def get_sequence_length(self, test, property_id, **kwargs):
        """Get length of a sequence property. Returns NcMethodResult. Raises NMOSTestException on error"""
        result = self.get_sequence_length_override(test, property_id, **kwargs)
        self.reference_datatype_schema_validate(test, result, NcMethodResult.__name__,
                                                role_path=kwargs.get("role_path"))
        return NcMethodResult.factory(result)

    def set_sequence_item(self, test, property_id, index, value, **kwargs):
        """Set item in a sequence property. Raises NMOSTestException on error"""
        result = self.set_sequence_item_override(test, property_id, index, value, **kwargs)
        self.reference_datatype_schema_validate(test, result, NcMethodResult.__name__,
                                                role_path=kwargs.get("role_path"))
        return NcMethodResult.factory(result)

    def add_sequence_item(self, test, property_id, value, **kwargs):
        """Add item to a sequence property. Raises NMOSTestException on error"""
        result = self.add_sequence_item_override(test, property_id, value, **kwargs)
        self.reference_datatype_schema_validate(test, result, NcMethodResult.__name__,
                                                role_path=kwargs.get("role_path"))
        return NcMethodResult.factory(result)

    def remove_sequence_item(self, test, property_id, index, **kwargs):
        """Remove item from a sequence property. Raises NMOSTestException on error"""
        result = self.remove_sequence_item_override(test, property_id, index, **kwargs)
        self.reference_datatype_schema_validate(test, result, NcMethodResult.__name__,
                                                role_path=kwargs.get("role_path"))
        return NcMethodResult.factory(result)

    def _create_NcMethodResultBlockMemberDescriptors(self, test, result, role_path):
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
        return self._create_NcMethodResultBlockMemberDescriptors(test, result, kwargs.get("role_path"))

    def find_members_by_path(self, test, path, **kwargs):
        """Query members based on role path. Raises NMOSTestException on error"""
        result = self.find_members_by_path_override(test, path, **kwargs)
        return self._create_NcMethodResultBlockMemberDescriptors(test, result, kwargs.get("role_path"))

    def find_members_by_role(self, test, role, case_sensitive, match_whole_string, recurse, **kwargs):
        """Query members based on role. Raises NMOSTestException on error"""
        result = self.find_members_by_role_override(test, role, case_sensitive, match_whole_string, recurse, **kwargs)
        return self._create_NcMethodResultBlockMemberDescriptors(test, result, kwargs.get("role_path"))

    def find_members_by_class_id(self, test, class_id, include_derived, recurse, **kwargs):
        """Query members based on class id. Raises NMOSTestException on error"""
        result = self.find_members_by_class_id_override(test, class_id, include_derived, recurse, **kwargs)
        return self._create_NcMethodResultBlockMemberDescriptors(test, result, kwargs.get("role_path"))

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
            self.reference_datatype_schema_validate(test,
                                                    method_result.value,
                                                    NcDatatypeDescriptor.get_descriptor_type(method_result.value),
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
            with open(os.path.join(base_schema_path, f"{name}.json"), "w") as output_file:
                json.dump(json_schema, output_file, indent=4)
                datatype_schema_names.append(name)

        # Load resolved MS-05 datatype schemas
        datatype_schemas = {}
        for name in datatype_schema_names:
            datatype_schemas[name] = load_resolved_schema(schema_path, f"{name}.json", path_prefix=False)

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
                json_schema["items"] = {"$ref": f"{descriptor.parentType}.json"}
            else:
                json_schema["allOf"] = []
                json_schema["allOf"].append({"$ref": f"{descriptor.parentType}.json"})

        # Primitive datatype
        if isinstance(descriptor, NcDatatypeDescriptorPrimitive):
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
                            property_type["anyOf"].append({"$ref": f"{field.typeName}.json"})
                            property_type["anyOf"].append({"type": "null"})
                        else:
                            property_type = {"$ref": f"{field.typeName}.json"}
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

    def queried_datatype_schema_validate(self, test, payload, datatype_name, role_path=None):
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

        self._validate_schema(test, payload, self.datatype_schemas.get(datatype_name),
                              f"role path={self.create_role_path_string(role_path)}: datatype={datatype_name}: ")

    def reference_datatype_schema_validate(self, test, payload, datatype_name, role_path=None):
        """Validate payload against specification reference datatype schema"""
        self._validate_schema(test, payload, self.reference_datatype_schemas.get(datatype_name),
                              f"role path={self.create_role_path_string(role_path)}: datatype={datatype_name}: ")

    def _validate_schema(self, test, payload, schema, context=""):
        """Delegates to jsonschema validate. Raises NMOSTestExceptions on error"""
        if not schema:
            raise NMOSTestException(test.FAIL(f"{context}Missing schema. Possible unknown type"))
        try:
            # Validate the JSON schema is correct
            checker = FormatChecker(["ipv4", "ipv6", "uri"])
            validate(payload, schema, format_checker=checker)
        except ValidationError as e:
            raise NMOSTestException(test.FAIL(f"{context}Schema validation error: {e.message}. "
                                              "Note that error may originate from a subschema of this schema."))
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
        if isinstance(reference, (NcDescriptor, NcElementId)):
            self.validate_descriptor(test, reference.__dict__, descriptor, context)
        elif isinstance(reference, (NcPropertyConstraints, NcParameterConstraints)):
            # level is a decoratation to improve reporting
            # and threrefore not needed for comparison
            reference_dict = deepcopy(reference.__dict__)
            reference_dict.pop("level", None)
            self.validate_descriptor(test, reference_dict, descriptor, context)
        # If the descriptor being checked is an object then convert to a dict before comparison
        elif isinstance(descriptor, (NcDescriptor, NcElementId)):
            self.validate_descriptor(test, reference, descriptor.__dict__, context)
        elif isinstance(descriptor, (NcPropertyConstraints, NcParameterConstraints)):
            # level is a decoratation to improve reporting
            # and threrefore not needed for comparison
            descriptor_dict = deepcopy(descriptor.__dict__)
            descriptor_dict.pop("level", None)
            self.validate_descriptor(test, reference, descriptor_dict, context)
        # Compare dictionaries
        elif isinstance(reference, dict):
            # NcDescriptor objects have a json field that caches the json used to construct it
            reference_copy = deepcopy(reference)
            descriptor_copy = deepcopy(descriptor)
            reference_copy.pop("json", None)
            descriptor_copy.pop("json", None)

            reference_keys = set(reference_copy.keys())
            descriptor_keys = set(descriptor_copy.keys())

            # compare the keys to see if any extra/missing
            key_diff = (set(reference_keys) | set(descriptor_keys)) - (set(reference_keys) & set(descriptor_keys))
            if len(key_diff) > 0:
                raise NMOSTestException(test.FAIL(f"{context}Missing/additional keys: {str(key_diff)}"))
            for key in reference_keys:
                # Ignore keys that contain non-normative information
                if key in non_normative_keys:
                    continue
                self.validate_descriptor(test, reference_copy[key], descriptor_copy[key], context=f"{context}{key}->")
        # Compare lists
        elif isinstance(reference, list):
            if len(reference) != len(descriptor):
                raise NMOSTestException(test.FAIL(f"{context}List unexpected length. Expected="
                                        f"{str(len(reference))}, actual={str(len(descriptor))}"))
            if len(reference) > 0:
                # If comparing lists of objects or dicts then sort by name first.
                # Primitive arrays are unsorted as position is assumed to be important e.g. classId
                if isinstance(reference[0], (dict, NcDescriptor)):
                    reference.sort(key=sort_key)
                    descriptor.sort(key=sort_key)
                for refvalue, value in zip(reference, descriptor):
                    name = refvalue.name if isinstance(refvalue, NcDescriptor) else \
                        refvalue["name"] if isinstance(dict, NcDescriptor) else ""
                    self.validate_descriptor(test, refvalue, value, context=f"{context}{name}: ")
        # Compare primitives and primitive arrays directly
        elif reference != descriptor:
            raise NMOSTestException(test.FAIL(f"{context}Expected value="
                                    f"{str(reference)}, actual value={str(descriptor)}"))
        return

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
                    self.reference_datatype_schema_validate(test, descriptor.json,
                                                            descriptor.__class__.__name__)

                    # Validate the content of descriptor is correct
                    self.validate_descriptor(test, reference_descriptors[key], descriptor)

                    results.append(test.PASS())
                else:
                    results.append(test.UNCLEAR("Not Implemented"))
            except NMOSTestException as e:
                results.append(e.args[0])

        return results

    def auto_tests(self):
        # Automatically validate all standard datatypes and control classes advertised by Class Manager.
        # Returns [test result array]
        # https://specs.amwa.tv/ms-05-02/releases/v1.0.0/docs/Framework.html

        results = list()
        test = Test("Initialize auto tests", "auto_init")

        class_manager = self.get_class_manager(test)

        results += self._validate_model_definitions(class_manager.class_descriptors,
                                                    self.reference_class_descriptors)

        results += self._validate_model_definitions(class_manager.datatype_descriptors,
                                                    self.reference_datatype_descriptors)
        return results

    def _get_class_manager_datatype_descriptors(self, test, class_manager_oid, role_path):
        method_result = self.get_property(test, NcClassManagerProperties.DATATYPES.value,
                                          oid=class_manager_oid, role_path=role_path)

        if isinstance(method_result, NcMethodResultError):
            raise NMOSTestException(test.FAIL(f"role path={self.create_role_path_string(role_path)}: "
                                              "Error getting Class Manager Datatype property: "
                                              f"{str(method_result.errorMessage)}"))

        if method_result.value is None or not isinstance(method_result.value, list):
            return None
        response = method_result.value

        # Validate descriptors against schema
        for r in response:
            self.reference_datatype_schema_validate(test, r, NcDatatypeDescriptor.get_descriptor_type(r), role_path)

        # Create NcDescriptor dictionary from response array
        descriptors = {r["name"]: NcDatatypeDescriptor.factory(r) for r in response}

        return descriptors

    def _get_class_manager_class_descriptors(self, test, class_manager_oid, role_path):
        method_result = self.get_property(test, NcClassManagerProperties.CONTROL_CLASSES.value,
                                          oid=class_manager_oid, role_path=role_path)

        if isinstance(method_result, NcMethodResultError):
            raise NMOSTestException(test.FAIL(f"role path={self.create_role_path_string(role_path)}: "
                                              "Error getting Class Manager Control Classes property: "
                                              f"{str(method_result.errorMessage)}"))

        if method_result.value is None or not isinstance(method_result.value, list):
            return None
        response = method_result.value
        # Validate descriptors
        for r in response:
            self.reference_datatype_schema_validate(test, r, NcClassDescriptor.__name__, role_path)

        # Create NcClassDescriptor dictionary from response array
        descriptors = {self.create_class_id_string(r.get("classId")): NcClassDescriptor(r) for r in response}
        return descriptors

    def create_block(self, test, class_id, oid, role, base_role_path=None, member_descriptor=None, owner=None):
        """Recursively create Device Model hierarchy"""
        # will set self.device_model_error to True if problems encountered
        role_path = self.create_role_path(base_role_path, role)

        method_result = self.get_property(test, NcObjectProperties.RUNTIME_PROPERTY_CONSTRAINTS.value,
                                          oid=oid, role_path=role_path)

        if isinstance(method_result, NcMethodResultError):
            raise NMOSTestException(test.FAIL(f"role path={self.create_role_path_string(role_path)}: "
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
                raise NMOSTestException(test.FAIL(f"role path={self.create_role_path_string(role_path)}: "
                                                  "Unable to get members property: "
                                                  f"{str(method_result.errorMessage)}"))

            if method_result.value is None or not isinstance(method_result.value, list):
                raise NMOSTestException(test.FAIL(f"role path={self.create_role_path_string(role_path)}: "
                                                  "Block members not a list: "
                                                  f"{str(method_result.value)}"))

            nc_block = NcBlock(class_id, oid, owner, role, role_path, runtime_constraints, member_descriptor)

            for m in method_result.value:
                self.reference_datatype_schema_validate(test, m, NcBlockMemberDescriptor.__name__, role_path)
                child_object = self.create_block(test, m["classId"], m["oid"], m["role"], role_path,
                                                 NcBlockMemberDescriptor(m), m["owner"])
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

                return NcClassManager(class_id, oid, owner, role, role_path,
                                      class_descriptors, datatype_descriptors,
                                      runtime_constraints, member_descriptor)

            return NcObject(class_id, oid, owner, role, role_path, runtime_constraints, member_descriptor)

    def _get_singleton_object_by_class_id(self, test, class_id):
        device_model = self.query_device_model(test)
        members = device_model.find_members_by_class_id(class_id, include_derived=True, get_objects=True)

        spec_link = f"https://specs.amwa.tv/ms-05-02/branches/{self.apis[MS05_API_KEY]['spec_branch']}" \
            "/docs/Managers.html"

        if len(members) == 0:
            raise NMOSTestException(test.FAIL(f"Class: {class_id} not found in Root Block.", spec_link))

        return members[0]

    def get_class_manager(self, test):
        """Get the Class Manager queried from the Node under test's Device Model"""
        if not self.class_manager:
            self.class_manager = self._get_singleton_object_by_class_id(test, StandardClassIds.NCCLASSMANAGER.value)

        if not self.class_manager:
            return test.FAIL("Unable to query Class Manager")
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

    def is_error_status(self, status):
        return status != NcMethodStatus.OK and status != NcMethodStatus.PropertyDeprecated \
            and status != NcMethodStatus.MethodDeprecated

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
        if role_path is None:
            return ""
        if not isinstance(role_path, list):
            return role_path
        return f"/{'/'.join([str(r) for r in role_path])}"

    def create_class_id_string(self, class_id):
        if class_id is None or not isinstance(class_id, list):
            return ""
        return ".".join(map(str, class_id))

    def get_not_subtypable_datatypes(self):
        """These datatypes should not allow non-standard/vendor specific subtypes"""
        return [NcDescriptor.__name__, NcBlockMemberDescriptor.__name__, NcClassDescriptor.__name__,
                NcDatatypeDescriptor.__name__, NcDatatypeDescriptorEnum.__name__,
                NcDatatypeDescriptorPrimitive.__name__, NcDatatypeDescriptorStruct.__name__,
                NcDatatypeDescriptorTypeDef.__name__, NcEnumItemDescriptor.__name__, NcEventDescriptor.__name__,
                NcFieldDescriptor.__name__, NcMethodDescriptor.__name__, NcParameterDescriptor.__name__,
                NcPropertyDescriptor.__name__, NcPropertyConstraints.__name__, NcPropertyConstraintsNumber.__name__,
                NcPropertyConstraintsString.__name__, NcParameterConstraints.__name__,
                NcParameterConstraintsNumber.__name__, NcParameterConstraintsString.__name__]

    def _get_constraints(self,
                         class_property: NcPropertyDescriptor,
                         datatype_descriptors: NcDatatypeDescriptor,
                         object_runtime_constraints: NcPropertyConstraints) -> NcPropertyConstraints:
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
                    runtime_constraints = object_runtime_constraint

        return runtime_constraints or property_constraints or datatype_constraints

    def get_properties(self,
                       test: GenericTest,
                       block: NcBlock,
                       get_constraints=False,
                       get_sequences=False,
                       get_readonly=False) -> list[MS05PropertyMetadata]:

        def is_read_only(class_id, property_descriptor):
            """Account for Worker enabled property cludge in the BCP-008 specs"""
            # If the class id starts with [1,2,2] it's a NcStatusMonitor
            # And its "writable" enabled flag is not, in fact, writable
            # if class_id[0] == 1 and class_id[1] == 2 and class_id[2] == 2 and \
            #         property_descriptor.id == NcPropertyId({"level": 2, "index": 1}):
            #     return True
            return property_descriptor.isReadOnly

        results = []

        class_manager = self.get_class_manager(test)

        # Note that the userLabel of the block may also be changed, and therefore might be
        # subject to runtime constraints constraints
        for child in block.child_objects:
            class_descriptor = class_manager.get_control_class(child.class_id, include_inherited=True)

            if not class_descriptor:
                continue
            role_path = self.create_role_path(block.role_path, child.role)

            for property_descriptor in class_descriptor.properties:
                constraints = self._get_constraints(property_descriptor,
                                                    class_manager.datatype_descriptors,
                                                    child.runtime_constraints)
                if get_readonly == is_read_only(class_descriptor.classId, property_descriptor) \
                        and property_descriptor.isSequence == get_sequences \
                        and bool(constraints) == get_constraints:
                    datatype = class_manager.get_datatype(property_descriptor.typeName, include_inherited=False)

                    results.append(MS05PropertyMetadata(
                        child.oid, role_path,
                        f"role path={self.create_role_path_string(role_path)}: "
                        f"class name={class_descriptor.name}: "
                        f"property name={property_descriptor.name}",
                        constraints,
                        datatype.type,
                        property_descriptor))
            if type(child) is NcBlock:
                results += (self.get_properties(test, child, get_constraints, get_sequences, get_readonly))

        return results

    def get_methods(self, test: GenericTest, block: NcBlock, get_constraints=False) -> MS05MethodMetadata:
        results = []

        class_manager = self.get_class_manager(test)

        for child in block.child_objects:
            class_descriptor = class_manager.get_control_class(child.class_id, include_inherited=True)

            if not class_descriptor:
                continue

            if type(child) is NcBlock:
                results += (self.get_methods(test, child, get_constraints))

            # Only test methods on non-standard classes, as the standard classes are already tested elsewhere
            if not self.is_non_standard_class(class_descriptor.classId):
                continue

            role_path = self.create_role_path(block.role_path, child.role)

            for method_descriptor in class_descriptor.methods:
                # Check for parameter constraints
                parameter_constraints = False
                for parameter in method_descriptor.parameters:
                    if parameter.constraints:
                        parameter_constraints = True

                if parameter_constraints == get_constraints:
                    results.append(MS05MethodMetadata(
                        child.oid, role_path,
                        f"role path={self.create_role_path_string(role_path)}: "
                        f"class name={class_descriptor.name}: "
                        f"method name={method_descriptor.name}",
                        method_descriptor))

        return results
