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

from enum import Enum

from . import TestHelper
from .NMOSUtils import NMOSUtils

SND_RCV_SUBSET = Enum('SndRcvSubset', ['ALL', 'WITH_I_O', 'WITHOUT_I_O'])


class IS11Utils(NMOSUtils):
    def __init__(self, url):
        NMOSUtils.__init__(self, url)

    # TODO: Remove the duplication (IS05Utils)
    def get_senders(self, filter=SND_RCV_SUBSET.ALL):
        """Gets a list of the available senders on the API"""
        toReturn = []
        valid, r = TestHelper.do_request("GET", self.url + "senders/")
        if valid and r.status_code == 200:
            try:
                for value in r.json():
                    if filter == SND_RCV_SUBSET.ALL:
                        toReturn.append(value[:-1])
                    else:
                        valid_io, r_io = TestHelper.do_request("GET", self.url + "senders/" + value + "inputs/")
                        if valid_io and r_io.status_code == 200:
                            try:
                                if len(r_io.json()) > 0 and filter == SND_RCV_SUBSET.WITH_I_O or \
                                   len(r_io.json()) == 0 and filter == SND_RCV_SUBSET.WITHOUT_I_O:
                                    toReturn.append(value[:-1])
                            except ValueError:
                                pass
            except ValueError:
                pass
        return toReturn

    # TODO: Remove the duplication (IS05Utils)
    def get_receivers(self, filter=SND_RCV_SUBSET.ALL):
        """Gets a list of the available receivers on the API"""
        toReturn = []
        valid, r = TestHelper.do_request("GET", self.url + "receivers/")
        if valid and r.status_code == 200:
            try:
                for value in r.json():
                    if filter == SND_RCV_SUBSET.ALL:
                        toReturn.append(value[:-1])
                    else:
                        valid_io, r_io = TestHelper.do_request("GET", self.url + "receivers/" + value + "outputs/")
                        if valid_io and r_io.status_code == 200:
                            try:
                                if len(r_io.json()) > 0 and filter == SND_RCV_SUBSET.WITH_I_O or \
                                   len(r_io.json()) == 0 and filter == SND_RCV_SUBSET.WITHOUT_I_O:
                                    toReturn.append(value[:-1])
                            except ValueError:
                                pass
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

    def get_transportfile(self, url, sender_id):
        """Get the transport file for a given Sender"""
        toReturn = None
        valid, r = TestHelper.do_request("GET", url + "single/senders/" + sender_id + "/transportfile/")
        if valid and r.status_code == 200:
            toReturn = r.text
        return toReturn

    def get_flows(self, url, sender_id):
        """Get the flow for a given Sender"""
        toReturn = None
        valid, r = TestHelper.do_request("GET", url + "flows/" + sender_id)
        if valid and r.status_code == 200:
            toReturn = r.json()
        return toReturn
