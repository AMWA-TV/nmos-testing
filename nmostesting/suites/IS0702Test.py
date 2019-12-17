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
from ..IS04Utils import IS04Utils
from ..IS05Utils import IS05Utils
from ..IS07Utils import IS07Utils

EVENTS_API_KEY = "events"
NODE_API_KEY = "node"
CONN_API_KEY = "connection"


class IS0702Test(GenericTest):
    """
    Runs IS-07-02-Test
    """
    def __init__(self, apis):
        GenericTest.__init__(self, apis)
        self.events_url = self.apis[EVENTS_API_KEY]["url"]
        self.connection_url = self.apis[CONN_API_KEY]["url"]
        self.node_url = self.apis[NODE_API_KEY]["url"]
        self.is04_utils = IS04Utils(self.node_url)
        self.is05_utils = IS05Utils(self.connection_url)
        self.is07_utils = IS07Utils(self.events_url)

    def set_up_tests(self):
        self.is05_senders = self.is05_utils.get_senders()
        self.is07_sources = self.is07_utils.get_sources_states_and_types()
        self.is04_sources = self.is04_utils.get_sources()
        self.is04_flows = self.is04_utils.get_flows()
        self.is04_senders = self.is04_utils.get_senders()
        self.transport_types = {}
        self.sender_active_params = {}
        self.senders_to_test = {}
        self.sources_to_test = {}

        for sender in self.is04_senders:
            flow = self.is04_senders[sender]["flow_id"]
            if flow in self.is04_flows:
                source = self.is04_flows[flow]["source_id"]
                if source in self.is04_sources:
                    if 'event_type' in self.is04_sources[source]:
                        self.senders_to_test[sender] = self.is04_senders[sender]
                        self.sources_to_test[source] = self.is04_sources[source]

        for sender in self.is05_senders:
            if self.is05_utils.compare_api_version(self.apis[CONN_API_KEY]["version"], "v1.1") >= 0:
                self.transport_types[sender] = self.is05_utils.get_transporttype(sender, "sender")
            else:
                self.transport_types[sender] = "urn:x-nmos:transport:rtp"

        if len(self.is05_senders) > 0:
            for sender in self.is05_senders:
                dest = "single/senders/" + sender + "/active"
                valid, response = self.is05_utils.checkCleanRequestJSON("GET", dest)
                if valid:
                    if len(response) > 0 and isinstance(response["transport_params"][0], dict):
                        self.sender_active_params[sender] = response["transport_params"][0]

    def test_01(self, test):
        """Each Sender has the required ext parameters"""

        ext_params_websocket = ['ext_is_07_source_id', 'ext_is_07_rest_api_url']
        ext_params_mqtt = ['ext_is_07_rest_api_url']
        if len(self.senders_to_test.keys()) > 0:
            for sender in self.senders_to_test:
                if sender in self.sender_active_params:
                    all_params = self.sender_active_params[sender].keys()
                    params = [param for param in all_params if param.startswith("ext_")]
                    valid_params = False
                    if self.transport_types[sender] == "urn:x-nmos:transport:websocket":
                        if sorted(params) == sorted(ext_params_websocket):
                            valid_params = True
                    elif self.transport_types[sender] == "urn:x-nmos:transport:mqtt":
                        if sorted(params) == sorted(ext_params_mqtt):
                            valid_params = True
                    if not valid_params:
                        return test.FAIL("Missing required ext parameters for Sender {}".format(sender))
                else:
                    return test.FAIL("Sender {} not found in Connection API".format(sender))
            return test.PASS()
        else:
            return test.UNCLEAR("Not tested. No resources found.")

    def test_02(self, test):
        """Each Source has a corresponding IS-05 sender"""

        if len(self.is07_sources) > 0:
            if len(self.sources_to_test.keys()) > 0:
                for source in self.is07_sources:
                    if source in self.sources_to_test:
                        found_source = False
                        for sender in self.senders_to_test:
                            if sender in self.sender_active_params:
                                try:
                                    if self.sender_active_params[sender]["ext_is_07_source_id"] == source:
                                        found_source = True
                                except KeyError as e:
                                    return test.FAIL("Sender {} parameters do not contain expected key: {}"
                                                     .format(sender, e))
                        if not found_source:
                            return test.FAIL("Source {} has no associated IS-05 sender".format(source))
                return test.PASS()
            else:
                return test.FAIL("No sources found in IS-04 Node API")
        else:
            return test.UNCLEAR("Not tested. No resources found.")
