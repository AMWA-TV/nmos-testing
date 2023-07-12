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

from .NMOSUtils import NMOSUtils

from enum import IntEnum
from itertools import takewhile


class MessageTypes(IntEnum):
    Command = 0
    CommandResponse = 1
    Notification = 2
    Subscription = 3
    SubscriptionResponse = 4
    Error = 5


class NcMethodStatus(IntEnum):
    OK = 200
    BadCommandFormat = 400
    Unauthorized = 401
    BadOid = 404
    Readonly = 405
    InvalidRequest = 406
    Conflict = 409
    BufferOverflow = 413
    ParameterError = 417
    Locked = 423
    DeviceError = 500
    MethodNotImplemented = 501
    PropertyNotImplemented = 502
    NotReady = 503
    Timeout = 504
    ProtocolVersionError = 505


class NcDatatypeType(IntEnum):
    Primitive = 0  # Primitive datatype
    Typedef = 1  # Simple alias of another datatype
    Struct = 2  # Data structure
    Enum = 3  # Enum datatype


class IS12Utils(NMOSUtils):
    def __init__(self, url):
        NMOSUtils.__init__(self, url)
        self.protocol_definitions()

    def protocol_definitions(self):
        self.ROOT_BLOCK_OID = 1

        self.METHOD_IDS = {
            'NCOBJECT': {
                'GENERIC_GET': {'level': 1, 'index': 1},
                'GENERIC_SET': {'level': 1, 'index': 2}
            },
            'NCBLOCK': {
                'GET_MEMBERS_DESCRIPTOR': {'level': 2, 'index': 1}
            },
            'NCCLASSMANAGER': {
                'GET_CONTROL_CLASS': {'level': 3, 'index': 1}
            },
        }

        self.PROPERTY_IDS = {
            'NCOBJECT': {
                'CLASS_ID': {'level': 1, 'index': 1},
                'OID': {'level': 1, 'index': 2},
                'CONSTANT_OID': {'level': 1, 'index': 3},
                'OWNER': {'level': 1, 'index': 4},
                'ROLE': {'level': 1, 'index': 5},
                'USER_LABEL': {'level': 1, 'index': 6},
                'TOUCHPOINTS': {'level': 1, 'index': 7},
                'RUNTIME_PROPERTY_CONSTRAINTS': {'level': 1, 'index': 8}
            },
            'NCCLASSMANAGER': {
                'CONTROL_CLASSES': {'level': 3, 'index': 1},
                'DATATYPES': {'level': 3, 'index': 2}
            }
        }

    def create_command_JSON(self, version, handle, oid, method_id, arguments):
        """Create command JSON for generic get of a property"""
        return {
            'protocolVersion': version,
            'messageType': MessageTypes.Command,
            'commands': [
                {
                    'handle': handle,
                    'oid': oid,
                    'methodId': method_id,
                    'arguments': arguments
                }
            ],
        }

    def create_generic_get_command_JSON(self, version, handle, oid, property_id):
        """Create command JSON for generic get of a property"""

        return self.create_command_JSON(version,
                                        handle,
                                        oid,
                                        self.METHOD_IDS["NCOBJECT"]["GENERIC_GET"],
                                        {'id': property_id})

    def create_generic_set_command_JSON(self, version, handle, oid, property_id, value):
        """Create command JSON for generic get of a property"""

        return self.create_command_JSON(version,
                                        handle,
                                        oid,
                                        self.METHOD_IDS["NCOBJECT"]["GENERIC_SET"],
                                        {'id': property_id, 'value': value})

    def create_get_member_descriptors_JSON(self, version, handle, oid):
        """Create message that will request the member descriptors of the object with the given oid"""

        return self.create_command_JSON(version,
                                        handle,
                                        oid,
                                        self.METHOD_IDS["NCBLOCK"]["GET_MEMBERS_DESCRIPTOR"],
                                        {'recurse': False})

    def model_primitive_to_JSON(self, type):
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

    def descriptor_to_schema(self, descriptor):
        variant_type = ['number', 'string', 'boolean', 'object', 'array', 'null']

        json_schema = {}
        json_schema['$schema'] = 'http://json-schema.org/draft-07/schema#'

        json_schema['title'] = descriptor['name']
        json_schema['description'] = descriptor['description']

        # Inheritance of datatype
        if descriptor.get('parentType'):
            json_primitive_type = self.model_primitive_to_JSON(descriptor['parentType'])
            if json_primitive_type:
                if descriptor['isSequence']:
                    json_schema['type'] = 'array'
                    json_schema['items'] = {'type': json_primitive_type}
                else:
                    json_schema['type'] = json_primitive_type
            else:
                json_schema['allOf'] = []
                json_schema['allOf'].append({'$ref': descriptor['parentType'] + '.json'})

        # Struct datatype
        if descriptor['type'] == NcDatatypeType.Struct and descriptor.get('fields'):
            json_schema['type'] = 'object'

            required = []
            properties = {}
            for field in descriptor['fields']:
                required.append(field['name'])

                property_type = {}
                if self.model_primitive_to_JSON(field['typeName']):
                    if field['isNullable']:
                        property_type = {'type': [self.model_primitive_to_JSON(field['typeName']), 'null']}
                    else:
                        property_type = {'type': self.model_primitive_to_JSON(field['typeName'])}
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

                property_type['description'] = field['description']
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

    def format_version(self, version):
        """ Formats the spec version to create IS-12 protocol version"""
        # Currently IS-12 version format is inconsistant with other IS specs
        # this helper converts from spec version to protocol version
        # e.g. v1.0 ==> 1.0.0
        return version.strip('v') + ".0"

    def get_base_class_id(self, class_id):
        """ Given a class_id returns the standard base class id as a string"""
        return '.'.join([str(v) for v in takewhile(lambda x: x > 0, class_id)])

    def is_block(self, class_id):
        """ Check class id to determine if this is a block """
        return len(class_id) > 1 and class_id[0] == 1 and class_id[1] == 1
