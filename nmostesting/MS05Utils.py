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

from enum import IntEnum, Enum

NODE_API_KEY = "node"

class MS05Utils(NMOSUtils):
    def __init__(self, apis):
        NMOSUtils.__init__(self, apis[NODE_API_KEY]["url"])
 

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
    def __init__(self, class_id, oid, role, runtime_constraints):
        self.class_id = class_id
        self.oid = oid
        self.role = role
        self.runtime_constraints = runtime_constraints


class NcBlock(NcObject):
    def __init__(self, class_id, oid, role, descriptors, runtime_constraints):
        NcObject.__init__(self, class_id, oid, role, runtime_constraints)
        self.child_objects = []
        self.member_descriptors = descriptors

    # Utility Methods
    def add_child_object(self, nc_object):
        self.child_objects.append(nc_object)

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
    def __init__(self, class_id, oid, role, runtime_constraints):
        NcObject.__init__(self, class_id, oid, role, runtime_constraints)


class NcClassManager(NcManager):
    def __init__(self, class_id, oid, role, class_descriptors, datatype_descriptors, runtime_constraints):
        NcObject.__init__(self, class_id, oid, role, runtime_constraints)
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
