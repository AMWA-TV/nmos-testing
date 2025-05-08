# Copyright (C) 2025 Advanced Media Workflow Association
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

from enum import Enum, IntEnum

from .IS12Utils import IS12Utils
from .MS05Utils import NcMethodId, NcPropertyId


class NcStatusMonitorProperties(Enum):
    OVERALL_STATUS = NcPropertyId({"level": 3, "index": 1})
    OVERALL_STATUS_MESSAGE = NcPropertyId({"level": 3, "index": 2})
    STATUS_REPORTING_DELAY = NcPropertyId({"level": 3, "index": 3})


class NcReceiverMonitorProperties(Enum):
    LINK_STATUS = NcPropertyId({"level": 4, "index": 1})
    LINK_STATUS_MESSAGE = NcPropertyId({"level": 4, "index": 2})
    LINK_STATUS_TRANSITION_COUNTER = NcPropertyId({"level": 4, "index": 3})
    CONNECTION_STATUS = NcPropertyId({"level": 4, "index": 4})
    CONNECTION_STATUS_MESSAGE = NcPropertyId({"level": 4, "index": 5})
    CONNECTION_STATUS_TRANSITION_COUNTER = NcPropertyId({"level": 4, "index": 6})
    EXTERNAL_SYNCHRONIZATION_STATUS = NcPropertyId({"level": 4, "index": 7})
    EXTERNAL_SYNCHRONIZATION_STATUS_MESSAGE = NcPropertyId({"level": 4, "index": 8})
    EXTERNAL_SYNCHRONIZATION_STATUS_TRANSITION_COUNTER = NcPropertyId({"level": 4, "index": 9})
    SYNCHRONIZATION_SOURCE_ID = NcPropertyId({"level": 4, "index": 10})
    STREAM_STATUS = NcPropertyId({"level": 4, "index": 11})
    STREAM_STATUS_MESSAGE = NcPropertyId({"level": 4, "index": 12})
    STREAM_STATUS_TRANSITION_COUNTER = NcPropertyId({"level": 4, "index": 13})
    AUTO_RESET_COUNTERS = NcPropertyId({"level": 4, "index": 14})


class NcReceiverMonitorMethods(Enum):
    GET_LOST_PACKET_COUNTERS = NcMethodId({"level": 4, "index": 1})
    GET_LATE_PACKET_COUNTERS = NcMethodId({"level": 4, "index": 2})
    RESET_COUNTERS = NcMethodId({"level": 4, "index": 3})


class NcSenderMonitorProperties(Enum):
    LINK_STATUS = NcPropertyId({"level": 4, "index": 1})
    LINK_STATUS_MESSAGE = NcPropertyId({"level": 4, "index": 2})
    LINK_STATUS_TRANSITION_COUNTER = NcPropertyId({"level": 4, "index": 3})
    TRANSMISSION_STATUS = NcPropertyId({"level": 4, "index": 4})
    TRANSMISSION_STATUS_MESSAGE = NcPropertyId({"level": 4, "index": 5})
    TRANSMISSION_STATUS_TRANSITION_COUNTER = NcPropertyId({"level": 4, "index": 6})
    EXTERNAL_SYNCHRONIZATION_STATUS = NcPropertyId({"level": 4, "index": 7})
    EXTERNAL_SYNCHRONIZATION_STATUS_MESSAGE = NcPropertyId({"level": 4, "index": 8})
    EXTERNAL_SYNCHRONIZATION_STATUS_TRANSITION_COUNTER = NcPropertyId({"level": 4, "index": 9})
    SYNCHRONIZATION_SOURCE_ID = NcPropertyId({"level": 4, "index": 10})
    ESSENCE_STATUS = NcPropertyId({"level": 4, "index": 11})
    ESSENCE_STATUS_MESSAGE = NcPropertyId({"level": 4, "index": 12})
    ESSENCE_STATUS_TRANSITION_COUNTER = NcPropertyId({"level": 4, "index": 13})
    AUTO_RESET_COUNTERS = NcPropertyId({"level": 4, "index": 14})


class NcSenderMonitorMethods(Enum):
    GET_TRANSMISSION_ERROR_COUNTERS = NcMethodId({"level": 4, "index": 1})
    RESET_COUNTERS = NcMethodId({"level": 4, "index": 2})


class NcOverallStatus(IntEnum):
    Inactive = 0
    Healthy = 1
    PartiallyHealthy = 2
    Unhealthy = 3
    UNKNOWN = 9999

    @classmethod
    def _missing_(cls, _):
        return cls.UNKNOWN


class NcLinkStatus(IntEnum):
    AllUp = 1
    SomeDown = 2
    AllDown = 3
    UNKNOWN = 9999

    @classmethod
    def _missing_(cls, _):
        return cls.UNKNOWN


class NcConnectionStatus(IntEnum):
    Inactive = 0
    Healthy = 1
    PartiallyHealthy = 2
    Unhealthy = 3
    UNKNOWN = 9999

    @classmethod
    def _missing_(cls, _):
        return cls.UNKNOWN


class NcSynchronizationStatus(IntEnum):
    NotUsed = 0
    Healthy = 1
    PartiallyHealthy = 2
    Unhealthy = 3
    UNKNOWN = 9999

    @classmethod
    def _missing_(cls, _):
        return cls.UNKNOWN


class NcStreamStatus(IntEnum):
    Inactive = 0
    Healthy = 1
    PartiallyHealthy = 2
    Unhealthy = 3
    UNKNOWN = 9999

    @classmethod
    def _missing_(cls, _):
        return cls.UNKNOWN


class BCP008Utils(IS12Utils):
    def __init__(self, apis):
        IS12Utils.__init__(self, apis)
