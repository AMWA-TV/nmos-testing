# Copyright 2017 British Broadcasting Corporation
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

from . import TestHelper

from .NMOSUtils import NMOSUtils
from copy import deepcopy


class IS04Utils(NMOSUtils):
    def __init__(self, url):
        NMOSUtils.__init__(self, url)

    def get_self(self):
        """Get node self resource from the Node API"""

        valid_resource, resource = TestHelper.do_request("GET", self.url + "self")
        if valid_resource and resource.status_code == 200:
            return resource.json()
        else:
            return None

    def get_devices(self, url=None):
        """Get node devices from the Node API"""

        return self.get_resources("devices", url)

    def get_sources(self, url=None):
        """Get node sources from the Node API"""

        return self.get_resources("sources", url)

    def get_flows(self, url=None):
        """Get node flows from the Node API"""

        return self.get_resources("flows", url)

    def get_senders(self, url=None):
        """Get node senders from the Node API"""

        return self.get_resources("senders", url)

    def get_receivers(self, url=None):
        """Get node receivers from the Node API"""

        return self.get_resources("receivers", url)

    def get_resources(self, resource, url=None):
        """Get node resources from the Node API"""

        if not url:
            url = self.url

        toReturn = {}
        valid_resources, resources = TestHelper.do_request("GET", url + resource)
        if valid_resources and resources.status_code == 200:
            for res in resources.json():
                toReturn[res["id"]] = res

        return toReturn

    @staticmethod
    def downgrade_resource(resource_type, resource_data, requested_version):
        """Downgrades given resource data to requested version"""
        version_major, version_minor = [int(x) for x in requested_version[1:].split(".")]

        data = deepcopy(resource_data)

        if version_major == 1:
            if resource_type == "node":
                if version_minor <= 2:
                    if "interfaces" in data:
                        key = "attached_network_device"
                        for interface in data["interfaces"]:
                            if key in interface:
                                del interface[key]
                    key = "authorization"
                    for service in data["services"]:
                        if key in service:
                            del service[key]
                    if "api" in data and "endpoints" in data["api"]:
                        for endpoint in data["api"]["endpoints"]:
                            if key in endpoint:
                                del endpoint[key]
                if version_minor <= 1:
                    keys_to_remove = [
                        "interfaces"
                    ]
                    for key in keys_to_remove:
                        if key in data:
                            del data[key]
                if version_minor == 0:
                    keys_to_remove = [
                        "api",
                        "clocks",
                        "description",
                        "tags"
                    ]
                    for key in keys_to_remove:
                        if key in data:
                            del data[key]
                return data

            elif resource_type == "device":
                if version_minor <= 2:
                    key = "authorization"
                    if "controls" in data:
                        for control in data["controls"]:
                            if key in control:
                                del control[key]
                if version_minor <= 1:
                    pass
                if version_minor == 0:
                    keys_to_remove = [
                        "controls",
                        "description",
                        "tags"
                    ]
                    for key in keys_to_remove:
                        if key in data:
                            del data[key]
                return data

            elif resource_type == "sender":
                if version_minor <= 2:
                    pass
                if version_minor <= 1:
                    keys_to_remove = [
                        "caps",
                        "interface_bindings",
                        "subscription"
                    ]
                    for key in keys_to_remove:
                        if key in data:
                            del data[key]
                if version_minor == 0:
                    pass
                return data

            elif resource_type == "receiver":
                if version_minor <= 2:
                    pass
                if version_minor <= 1:
                    keys_to_remove = [
                        "interface_bindings"
                    ]
                    for key in keys_to_remove:
                        if key in data:
                            del data[key]
                    if "subscription" in data and "active" in data["subscription"]:
                        del data["subscription"]["active"]
                if version_minor == 0:
                    pass
                return data

            elif resource_type == "source":
                if version_minor <= 2:
                    keys_to_remove = [
                        "event_type"
                    ]
                    for key in keys_to_remove:
                        if key in data:
                            del data[key]
                if version_minor <= 1:
                    pass
                if version_minor == 0:
                    keys_to_remove = [
                        "channels",
                        "clock_name",
                        "grain_rate"
                    ]
                    for key in keys_to_remove:
                        if key in data:
                            del data[key]
                return data

            elif resource_type == "flow":
                if version_minor <= 2:
                    keys_to_remove = [
                        "event_type"
                    ]
                    for key in keys_to_remove:
                        if key in data:
                            del data[key]
                if version_minor <= 1:
                    pass
                if version_minor == 0:
                    keys_to_remove = [
                        "bit_depth",
                        "colorspace",
                        "components",
                        "device_id",
                        "DID_SDID",
                        "frame_height",
                        "frame_width",
                        "grain_rate",
                        "interlace_mode",
                        "media_type",
                        "sample_rate",
                        "transfer_characteristic"
                    ]
                    for key in keys_to_remove:
                        if key in data:
                            del data[key]
                return data

            elif resource_type == "subscription":
                if version_minor <= 2:
                    keys_to_remove = [
                        "authorization"
                    ]
                    for key in keys_to_remove:
                        if key in data:
                            del data[key]
                if version_minor <= 1:
                    pass
                if version_minor == 0:
                    keys_to_remove = [
                        "secure"
                    ]
                    for key in keys_to_remove:
                        if key in data:
                            del data[key]
                return data

        # Invalid request
        return None
