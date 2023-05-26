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


class IS12Utils(NMOSUtils):
    def __init__(self, url):
        NMOSUtils.__init__(self, url)
        self.protocol_definitions()

    def protocol_definitions(self):
        self.DEFAULT_PROTOCOL_VERSION = '1.0.0'

        self.ROOT_BLOCK_OID = 1

        self.METHOD_IDS = {
            'NCOBJECT': {
                'GENERIC_GET': {
                    'level': 1,
                    'index': 1,
                },
                'GENERIC_SET': {
                    'level': 1,
                    'index': 2,
                }
            },
            'NCBLOCK': {
                'GET_MEMBERS_DESCRIPTOR': {
                    'level': 2,
                    'index': 1,
                }
            },
            'NCCLASSMANAGER': {
                'GET_CONTROL_CLASS': {
                    'level': 3,
                    'index': 1,
                }
            },
        }

    def get_member_descriptors_message(self, oid, handle):
        """Create message that will request the member descriptors of the object with the given oid"""
        return {
            'protocolVersion': self.DEFAULT_PROTOCOL_VERSION,
            'messageType': MessageTypes.Command,
            'commands': [
                {
                    'handle': handle,
                    'oid': oid,
                    'methodId': self.METHOD_IDS["NCBLOCK"]["GET_MEMBERS_DESCRIPTOR"],
                    'arguments': {
                        'recurse': False
                    },
                },
            ],
        }


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
