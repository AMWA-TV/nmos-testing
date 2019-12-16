# Copyright (C) 2019 Advanced Media Workflow Association
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

from ..GenericTest import GenericTest
from ..IS05Utils import IS05Utils
from ..IS07Utils import IS07Utils

EVENTS_API_KEY = "events"
CONN_API_KEY = "connection"


class IS0703Test(GenericTest):
    """
    Runs IS-07-03-Test
    """
    def __init__(self, apis):
        GenericTest.__init__(self, apis)
        self.events_url = self.apis[EVENTS_API_KEY]["url"]
        self.connection_url = self.apis[CONN_API_KEY]["url"]
        self.is05_utils = IS05Utils(self.connection_url)
        self.is07_utils = IS07Utils(self.events_url)

    def set_up_tests(self):
        self.senders = self.is05_utils.get_senders()
        self.sources = self.is07_utils.get_sources_states_and_types()
        self.transport_types = {}
        self.sender_active_params = {}

        for sender in self.senders:
            if self.is05_utils.compare_api_version(self.apis[CONN_API_KEY]["version"], "v1.1") >= 0:
                self.transport_types[sender] = self.is05_utils.get_transporttype(sender, "sender")
            else:
                self.transport_types[sender] = "urn:x-nmos:transport:rtp"

        if len(self.senders) > 0:
            for sender in self.senders:
                dest = "single/senders/" + sender + "/active/"
                valid, response = self.is05_utils.checkCleanRequestJSON("GET", dest)
                if valid:
                    if len(response) > 0 and isinstance(response["transport_params"][0], dict):
                        self.sender_active_params[sender] = response["transport_params"][0]

    def test_01(self, test):
        """Each Sender has ext_is_07_source_id and ext_is_07_rest_api_url parameters"""

        extParams = ['ext_is_07_source_id', 'ext_is_07_rest_api_url']
        if len(self.senders) > 0:
            for sender in self.senders:
                if sender in self.sender_active_params:
                    all_params = self.sender_active_params[sender].keys()
                    params = [param for param in all_params if param.startswith("ext_")]
                    valid_params = False
                    if self.transport_types[sender] == "urn:x-nmos:transport:websocket":
                        if sorted(params) == sorted(extParams):
                            valid_params = True
                    elif self.transport_types[sender] == "urn:x-nmos:transport:mqtt":
                        if sorted(params) == sorted(extParams):
                            valid_params = True
                    if not valid_params:
                        return test.FAIL("Missing common ext parameters")
            return test.PASS()
        else:
            return test.UNCLEAR("Not tested. No resources found.")

        return test.PASS()

    def test_02(self, test):
        """Each Source has a corresponding IS-05 sender"""

        if len(self.sources) > 0:
            for source in self.sources:
                found_source = False
                for sender in self.sender_active_params:
                    try:
                        if self.sender_active_params[sender]["ext_is_07_source_id"] == source:
                            found_source = True
                    except KeyError as e:
                        return test.FAIL("Sender {} parameters do not contain expected key: {}".format(sender, e))

                if not found_source:
                    return test.FAIL("Source {} has no associated IS-05 sender".format(source))

        return test.PASS()
