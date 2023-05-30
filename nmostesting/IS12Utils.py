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


class IS12Utils(NMOSUtils):
    def __init__(self, url):
        NMOSUtils.__init__(self, url)
        self.protocol_definitions()

    def protocol_definitions(self):
        self.DEFAULT_PROTOCOL_VERSION = '1.0.0'

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
            }
        }

    def create_command_JSON(self, handle, oid, method_id, arguments):
        """Create command JSON for generic get of a property"""
        return {
            'protocolVersion': self.DEFAULT_PROTOCOL_VERSION,
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

    def create_generic_get_command_JSON(self, handle, oid, property_id):
        """Create command JSON for generic get of a property"""

        return self.create_command_JSON(handle,
                                        oid,
                                        self.METHOD_IDS["NCOBJECT"]["GENERIC_GET"],
                                        {'id': property_id})

    def create_get_member_descriptors_JSON(self, handle, oid):
        """Create message that will request the member descriptors of the object with the given oid"""

        return self.create_command_JSON(handle,
                                        oid,
                                        self.METHOD_IDS["NCBLOCK"]["GET_MEMBERS_DESCRIPTOR"],
                                        {'recurse': False})
