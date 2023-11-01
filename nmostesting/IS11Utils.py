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
from . import Config as CONFIG
from .IS04Utils import IS04Utils
from .IS05Utils import IS05Utils
from .NMOSUtils import NMOSUtils
from .GenericTest import GenericTest
NODE_API_KEY = "node"
CONN_API_KEY = "connection"
SND_RCV_SUBSET = Enum('SndRcvSubset', ['ALL', 'WITH_I_O', 'WITHOUT_I_O'])


class IS11Utils(NMOSUtils, GenericTest):
    def __init__(self, url, apis):
        NMOSUtils.__init__(self, url=url)

        GenericTest.__init__(self, apis)
        self.node_url = self.apis[NODE_API_KEY]["url"]
        self.conn_url = self.apis[CONN_API_KEY]["url"]
        self.is04_utils = IS04Utils(self.node_url)
        self.is05_utils = IS05Utils(self.conn_url)
        if CONFIG.IS11_REFERENCE_SENDER_NODE_API_URL:
            self.reference_is04_utils = IS04Utils(CONFIG.IS11_REFERENCE_SENDER_NODE_API_URL)

        if CONFIG.IS11_REFERENCE_SENDER_CONNECTION_API_URL:
            self.reference_is05_utils = IS05Utils(CONFIG.IS11_REFERENCE_SENDER_CONNECTION_API_URL)

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

    def get_receivers_with_or_without_outputs_id(self, receivers, format):
        self.receivers_with_or_without_outputs = []
        for receiver_id in receivers:
            valid, response = self.is04_utils.checkCleanRequestJSON("GET", "receivers/" + receiver_id)
            if not valid:
                return valid, response

            if response["format"] == format:
                self.receivers_with_or_without_outputs.append(receiver_id)
        return valid, self.receivers_with_or_without_outputs

    def stable_state_request(self, receiver_id, activated_receivers):

        for i in range(0, CONFIG.STABLE_STATE_ATTEMPTS):
            valid, response = self.is05_utils.checkCleanRequestJSON(
                        "GET",
                        "single/receivers/" + receiver_id + "/active"
                    )
            if not valid:
                return "FAIL", response

            master_enable = response["master_enable"]

            valid, response = self.checkCleanRequestJSON(
                        "GET",
                        "receivers/" + receiver_id + "/status"
                    )
            if not valid:
                return "FAIL", response

            state = response["state"]

            if master_enable and state == "compliant_stream":
                break
            elif i == CONFIG.STABLE_STATE_ATTEMPTS - 1:
                return "FAIL", ("Expected positive \"master_enable\" and "
                                "\"compliant_stream\" state of receiver {}, got {} and {}"
                                .format(receiver_id, master_enable, state))
        activated_receivers += 1
        return valid, activated_receivers

    def activate_reference_sender_and_receiver(self, reference_senders, format, receiver, receiver_id):
        for sender_id in reference_senders[format]:
            valid, response = self.reference_is04_utils.checkCleanRequestJSON("GET", "senders/" + sender_id)
            if not valid:
                return "FAIL", response

            sender = response

            if sender["transport"] != receiver["transport"]:
                continue

            if response["flow_id"] is None:
                return "UNCLEAR", ("\"flow_id\" of sender {} is null".format(sender_id))

            valid, response = self.reference_is04_utils.checkCleanRequestJSON("GET", "flows/" + sender["flow_id"])
            if not valid:
                return "FAIL", response

            if response["media_type"] not in receiver["caps"]["media_types"]:
                continue

            valid, response = self.reference_is05_utils.checkCleanRequestJSON(
                "GET",
                "single/senders/" + sender_id + "/active"
                )
            if not valid:
                return "FAIL", response

            json_data = {
                    "master_enable": True,
                    "activation": {"mode": "activate_immediate"}
                }
            valid, response = self.reference_is05_utils.checkCleanRequestJSON(
                "PATCH",
                "single/senders/" + sender_id + "/staged",
                json_data
            )
            if not valid:
                return "FAIL", response
            sdp_transport_file = self.get_transportfile(
                CONFIG.IS11_REFERENCE_SENDER_CONNECTION_API_URL,
                sender_id
            )

            if len(sdp_transport_file.strip()) == 0:
                continue

            json_data = {
                "sender_id": sender_id,
                "master_enable": True,
                "activation": {"mode": "activate_immediate"},
                "transport_file": {"type": "application/sdp",
                                   "data": "{}".format(sdp_transport_file)}
            }
            valid, response = self.is05_utils.checkCleanRequestJSON(
                "PATCH",
                "single/receivers/" + receiver_id + "/staged",
                json_data)
            if not valid:
                return "FAIL", response
        return valid, ""
