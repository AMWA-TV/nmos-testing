# Copyright (C) 2022 Advanced Media Workflow Association
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


class IS11Utils(NMOSUtils):
    def __init__(self, url):
        NMOSUtils.__init__(self, url)

    # TODO: Remove the duplication (IS05Utils)
    def get_senders(self):
        """Gets a list of the available senders on the API"""
        toReturn = []
        valid, r = TestHelper.do_request("GET", self.url + "senders/")
        if valid and r.status_code == 200:
            try:
                for value in r.json():
                    toReturn.append(value[:-1])
            except ValueError:
                pass
        return toReturn

    # TODO: Remove the duplication (IS05Utils)
    def get_receivers(self):
        """Gets a list of the available receivers on the API"""
        toReturn = []
        valid, r = TestHelper.do_request("GET", self.url + "receivers/")
        if valid and r.status_code == 200:
            try:
                for value in r.json():
                    toReturn.append(value[:-1])
            except ValueError:
                pass
        return toReturn

    # TODO: Remove the duplication (IS05Utils)
    def get_inputs(self):
        """Gets a list of the available inputs on the API"""
        toReturn = []
        valid, r = TestHelper.do_request("GET", self.url + "inputs/")
        if valid and r.status_code == 200:
            try:
                for value in r.json():
                    toReturn.append(value[:-1])
            except ValueError:
                pass
        return toReturn

    # TODO: Remove the duplication (IS05Utils)
    def get_outputs(self):
        """Gets a list of the available outputs on the API"""
        toReturn = []
        valid, r = TestHelper.do_request("GET", self.url + "outputs/")
        if valid and r.status_code == 200:
            try:
                for value in r.json():
                    toReturn.append(value[:-1])
            except ValueError:
                pass
        return toReturn

    # TODO: Remove the duplication (IS05Utils)
    def checkCleanRequest(self, method, dest, data=None, code=200):
        """Checks a request can be made and the resulting json can be parsed"""
        status, response = TestHelper.do_request(method, self.url + dest, json=data)
        if not status:
            return status, response

        message = "Expected status code {} from {}, got {}.".format(code, dest, response.status_code)
        if response.status_code == code:
            return True, response
        else:
            return False, message

    # TODO: Remove the duplication (IS05Utils)
    def checkCleanRequestJSON(self, method, dest, data=None, code=200):
        valid, response = self.checkCleanRequest(method, dest, data, code)
        if valid:
            try:
                return True, response.json()
            except Exception:
                # Failed parsing JSON
                return False, "Invalid JSON received"
        else:
            return valid, response