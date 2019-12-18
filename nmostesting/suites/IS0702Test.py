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

import re

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
        """Each Source has a corresponding sender in IS-04 and IS-05"""

        api = self.apis[EVENTS_API_KEY]

        if len(self.is07_sources) > 0:
            warn_topic = False
            warn_message = ""
            for source_id in self.is07_sources:
                if source_id in self.sources_to_test:
                    found_sender = None
                    for sender_id in self.senders_to_test:
                        flow_id = self.senders_to_test[sender_id]["flow_id"]
                        if flow_id in self.is04_flows:
                            if source_id == self.is04_flows[flow_id]["source_id"]:
                                found_sender = self.senders_to_test[sender_id]
                                break
                    if found_sender is not None:
                        if found_sender["id"] in self.sender_active_params:
                            try:
                                params = self.sender_active_params[found_sender["id"]]
                                if found_sender["transport"] == "urn:x-nmos:transport:websocket":
                                    if params["ext_is_07_source_id"] != source_id:
                                        return test.FAIL("IS-05 sender {} does not indicate the correct "
                                                         "'ext_is_07_source_id': {}"
                                                         .format(found_sender["id"], source_id))
                                elif found_sender["transport"] == "urn:x-nmos:transport:mqtt":
                                    topic = re.search("^x-nmos/events/(.+)/sources/(.+)$", params["broker_topic"])
                                    if not topic:
                                        warn_topic = True
                                        warn_message = "IS-05 sender {} does not follow the recommended convention " \
                                            "in 'broker_topic': {}".format(found_sender["id"], source_id)
                                    elif topic.group(2) != source_id:
                                        warn_topic = True
                                        warn_message = "IS-05 sender {} does not indicate the correct source " \
                                            "in 'broker_topic': {}".format(found_sender["id"], source_id)
                                    elif topic.group(1) != api["version"]:
                                        warn_topic = True
                                        warn_message = "IS-05 sender {} does not indicate the correct API version " \
                                            "in 'broker_topic': {}".format(found_sender["id"], api["version"])
                                else:
                                    return test.FAIL("IS-05 sender {} has an unsupported transport {}"
                                                     .format(found_sender["id"], found_sender["transport"]))
                            except KeyError as e:
                                return test.FAIL("Sender {} parameters do not contain expected key: {}"
                                                 .format(found_sender["id"], e))
                        else:
                            return test.FAIL("Source {} has no associated IS-05 sender".format(source_id))
                    else:
                        return test.FAIL("Source {} has no associated IS-04 sender".format(source_id))
                else:
                    return test.FAIL("Source {} not found in Node API".format(source_id))
            if warn_topic:
                return test.WARNING(warn_message,
                                    "https://amwa-tv.github.io/nmos-event-tally/branches/{}"
                                    "/docs/5.1._Transport_-_MQTT.html#32-broker_topic"
                                    .format(api["spec_branch"]))
            else:
                return test.PASS()
        else:
            return test.UNCLEAR("Not tested. No resources found.")

    def test_03(self, test):
        """Websocket senders on the same device have the same connection_uri and connection_authorization parameters"""

        if len(self.is07_sources) > 0:
            resources_tested = False
            senders_by_device = {}
            for source_id in self.is07_sources:
                if source_id in self.sources_to_test:
                    for sender_id in self.senders_to_test:
                        flow_id = self.senders_to_test[sender_id]["flow_id"]
                        if flow_id in self.is04_flows:
                            if source_id == self.is04_flows[flow_id]["source_id"]:
                                found_sender = self.senders_to_test[sender_id]
                                if found_sender["transport"] == "urn:x-nmos:transport:websocket":
                                    if found_sender["device_id"] not in senders_by_device:
                                        senders_dict = {}
                                        senders_dict[found_sender["id"]] = found_sender
                                        senders_by_device[found_sender["device_id"]] = senders_dict
                                    else:
                                        senders_dict = senders_by_device[found_sender["device_id"]]
                                        senders_dict[found_sender["id"]] = found_sender

            for device_id in senders_by_device:
                device_connection_uri = None
                device_connection_authorization = None
                senders_dict = senders_by_device[device_id]
                for sender_id in senders_dict:
                    found_sender = senders_dict[sender_id]
                    if found_sender["id"] in self.sender_active_params:
                        resources_tested = True
                        try:
                            params = self.sender_active_params[found_sender["id"]]
                            sender_connection_uri = params["connection_uri"]
                            sender_connection_authorization = params["connection_authorization"]

                            if device_connection_uri is None:
                                device_connection_uri = sender_connection_uri
                            else:
                                if device_connection_uri != sender_connection_uri:
                                    return test.FAIL("Sender {} does not have the same connection_uri "
                                                     "parameter within the same device"
                                                     .format(found_sender["id"]))
                            if device_connection_authorization is None:
                                device_connection_authorization = sender_connection_authorization
                            else:
                                if device_connection_authorization != sender_connection_authorization:
                                    return test.FAIL("Sender {} does not have the same "
                                                     "connection_authorization parameter within "
                                                     "the same device".format(found_sender["id"]))
                        except KeyError as e:
                            return test.FAIL("Sender {} parameters do not contain expected key: {}"
                                             .format(found_sender["id"], e))
                    else:
                        return test.FAIL("Source {} has no associated IS-05 sender".format(source_id))
            if resources_tested:
                return test.PASS()
            else:
                return test.UNCLEAR("Not tested. No websocket sender resources found.")
        else:
            return test.UNCLEAR("Not tested. No resources found.")
