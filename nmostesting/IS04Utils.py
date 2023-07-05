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

import re
from copy import deepcopy
from fractions import Fraction
from . import TestHelper
from .NMOSUtils import NMOSUtils


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
    def comparable_parameter_constraint_value(value):
        if isinstance(value, dict):
            return Fraction(value["numerator"], value.get("denominator", 1))
        return value

    @staticmethod
    def comparable_parameter_constraint(param_constraint):
        result = deepcopy(param_constraint)
        if "minimum" in result:
            result["minimum"] = IS04Utils.comparable_parameter_constraint_value(
                result["minimum"]
            )
        if "maximum" in result:
            result["maximum"] = IS04Utils.comparable_parameter_constraint_value(
                result["maximum"]
            )
        if "enum" in result:
            for i, value in enumerate(result["enum"]):
                result["enum"][i] = IS04Utils.comparable_parameter_constraint_value(
                    value
                )
        return result

    @staticmethod
    def comparable_constraint_set(constraint_set):
        result = {
            k: IS04Utils.comparable_parameter_constraint(v)
            if re.match("^urn:x-nmos:cap:(?!meta:)", k)
            else v
            for k, v in constraint_set.items()
        }
        # could also remove urn:x-nmos:cap:meta:label?
        if "urn:x-nmos:cap:meta:preference" not in result:
            result["urn:x-nmos:cap:meta:preference"] = 0
        if "urn:x-nmos:cap:meta:enabled" not in result:
            result["urn:x-nmos:cap:meta:enabled"] = True
        return result

    @staticmethod
    def comparable_constraint_sets(constraint_sets):
        return [IS04Utils.comparable_constraint_set(_) for _ in constraint_sets]

    @staticmethod
    def compare_constraint_sets(lhs, rhs):
        """Check that two Constraint Sets arrays are closely equivalent"""
        return TestHelper.compare_json(
            IS04Utils.comparable_constraint_sets(lhs),
            IS04Utils.comparable_constraint_sets(rhs),
        )

    @staticmethod
    def make_sampling(flow_components):
        samplers = {
            # Red-Green-Blue-Alpha
            "RGBA": {"R": (1, 1), "G": (1, 1), "B": (1, 1), "A": (1, 1)},
            # Red-Green-Blue
            "RGB": {"R": (1, 1), "G": (1, 1), "B": (1, 1)},
            # Non-constant luminance YCbCr
            "YCbCr-4:4:4": {"Y": (1, 1), "Cb": (1, 1), "Cr": (1, 1)},
            "YCbCr-4:2:2": {"Y": (1, 1), "Cb": (2, 1), "Cr": (2, 1)},
            "YCbCr-4:2:0": {"Y": (1, 1), "Cb": (2, 2), "Cr": (2, 2)},
            "YCbCr-4:1:1": {"Y": (1, 1), "Cb": (4, 1), "Cr": (4, 1)},
            # Constant luminance YCbCr
            "CLYCbCr-4:4:4": {"Yc": (1, 1), "Cbc": (1, 1), "Crc": (1, 1)},
            "CLYCbCr-4:2:2": {"Yc": (1, 1), "Cbc": (2, 1), "Crc": (2, 1)},
            "CLYCbCr-4:2:0": {"Yc": (1, 1), "Cbc": (2, 2), "Crc": (2, 2)},
            # Constant intensity ICtCp
            "ICtCp-4:4:4": {"I": (1, 1), "Ct": (1, 1), "Cp": (1, 1)},
            "ICtCp-4:2:2": {"I": (1, 1), "Ct": (2, 1), "Cp": (2, 1)},
            "ICtCp-4:2:0": {"I": (1, 1), "Ct": (2, 2), "Cp": (2, 2)},
            # XYZ
            "XYZ": {"X": (1, 1), "Y": (1, 1), "Z": (1, 1)},
            # Key signal represented as a single component
            "KEY": {"Key": (1, 1)},
            # Sampling signaled by the payload
            "UNSPECIFIED": {},
        }

        max_w, max_h = 0, 0
        for component in flow_components:
            w, h = component["width"], component["height"]
            if w > max_w:
                max_w = w
            if h > max_h:
                max_h = h

        components_sampler = {}
        for component in flow_components:
            w, h = component["width"], component["height"]
            components_sampler[component["name"]] = (max_w / w, max_h / h)

        for sampling, sampler in samplers.items():
            if sampler == components_sampler:
                return sampling

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
