# Copyright 2017 British Broadcasting Corporation
#
# Modifications Copyright 2018 Riedel Communications GmbH & Co. KG
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

import json
from .NMOSUtils import NMOSUtils
from . import TestHelper


class IS11Utils(NMOSUtils):
    def __init__(self, url):
        NMOSUtils.__init__(self, url)

    # TODO(prince-chrism): Move to NMOSUtils since I copied the implementation from IS-05
    def _get_resource(self, list_endpoint):
        """Gets a list of the available resource at the list endpoint"""

        toReturn = []
        valid, r = TestHelper.do_request("GET", self.url + list_endpoint)
        if valid and r.status_code == 200:
            try:
                for value in r.json():
                    toReturn.append(value[:-1])
            except ValueError:
                pass
        return toReturn

    # TODO(prince-chrism): Move to NMOSUtils since I copied the implementation from IS-05
    def check_for_api_control(self, node_url, current_api_url, expected_control_type):
        valid, devices = TestHelper.do_request("GET", node_url + "devices")
        if not valid:
            return False, "Node API did not respond as expected: {}".format(devices)

        devices_with_api = []
        found_api_match = False
        try:
            for device in devices.json():
                for control in device["controls"]:
                    if control["type"] == expected_control_type:
                        devices_with_api.append(control["href"])
                        if NMOSUtils.compare_urls(current_api_url, control["href"]) and \
                                self.authorization is control.get("authorization", False):
                            found_api_match = True
        except json.JSONDecodeError:
            return False, "Non-JSON response returned from Node API"
        except KeyError:
            return False, "One or more Devices were missing the 'controls' attribute"

        if len(devices_with_api) > 0 and found_api_match:
            return True, ""
        elif len(devices_with_api) > 0:
            return False, "Found one or more Device controls, but no href and/or authorization mode" \
                          " matched the API under test"
        else:
            return False, "Unable to find any Devices which expose the control type '{}'".format(expected_control_type)

    def get_senders(self):
        """Gets a list of the available senders from the API"""
        return self._get_resource("senders/")

    def get_receivers(self):
        """Gets a list of the available receivers from the API"""
        return self._get_resource("receivers/")

    def get_sinks(self):
        """Gets a list of the available sink from the API"""
        return self._get_resource("sinks/")
