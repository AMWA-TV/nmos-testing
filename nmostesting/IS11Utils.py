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
    @staticmethod
    def check_for_api_control(node_url, current_api_url, expected_control_type, authorization):
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
                                authorization is control.get("authorization", False):
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

    def get_media_profiles(self, sender_id):
        """Get the Media Profiles for a given Sender"""
        valid, r = TestHelper.do_request("GET", f"{self.url}senders/{sender_id}/media-profiles")
        if valid and r.status_code == 200:
            try:
                return True, r.json()
            except Exception:
                # Failed parsing JSON
                return False, "Invalid JSON received"
        return False, "Sink-MP API did not respond as expected: {}".format(r)

    def put_media_profiles(self, sender_id, data):
        """Put some Media Profiles on a given Sender"""
        valid, r = TestHelper.do_request("GET", f"{self.url}senders/{sender_id}/media-profiles", json=data)
        if valid and r.status_code == 200:
            try:
                return True, r.json()
            except Exception:
                # Failed parsing JSON
                return False, "Invalid JSON received"
        return False, "Sink-MP API did not respond as expected: {}".format(r)

    def delete_media_profiles(self, sender_id):
        """Delete the Media Profiles of a given Sender"""
        valid, r = TestHelper.do_request("DELETE", f"{self.url}senders/{sender_id}/media-profiles")
        if valid and r.status_code == 204:
            try:
                return True, r.content
            except Exception:
                # Failed parsing JSON
                return False, "Invalid JSON received"
        return False, "Sink-MP API did not respond as expected: {}".format(r)

    def get_receivers(self):
        """Gets a list of the available receivers from the API"""
        return self._get_resource("receivers/")

    def get_associated_sinks(self, receiver_id):
        """Get the accosicated Sinks for a given receiver"""
        valid, r = TestHelper.do_request("GET", self.url + "receivers/" + receiver_id + "/sinks")
        if valid and r.status_code == 200:
            try:
                return True, r.json()
            except Exception:
                # Failed parsing JSON
                return False, "Invalid JSON received"
        return False, "Sink-MP API did not respond as expected: {}".format(r)

    def get_sinks(self):
        """Gets a list of the available sink from the API"""
        return self._get_resource("sinks/")
