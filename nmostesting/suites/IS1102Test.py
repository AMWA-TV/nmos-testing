# Copyright (C) 2021 Advanced Media Workflow Association
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
from ..GenericTest import GenericTest
from ..IS11Utils import IS11Utils
from ..IS04Utils import IS04Utils
from ..IS05Utils import IS05Utils

NODE_API_KEY = "node"
CONN_API_KEY = "connection"
SINIK_MP_API_KEY = "sink-mp"


class IS1102Test(GenericTest):
    """
    Runs IS-11-02-Test
    """
    def __init__(self, apis):
        omit_paths = [
            "/single/senders/{senderId}/transportfile", # permitted to generate a 404 when master_enable is false
            "/sinks/{sinkId}/edid" # Does not have a schema
        ]
        GenericTest.__init__(self, apis, omit_paths)
        self.url = self.apis[SINIK_MP_API_KEY]["url"]
        self.connection_url = self.apis[CONN_API_KEY]["url"]
        self.node_url = self.apis[NODE_API_KEY]["url"]
        self.is04_utils = IS04Utils(self.node_url)
        self.is05_utils = IS05Utils(self.connection_url)
        self.is11_utils = IS11Utils(self.url)

    def set_up_tests(self):
        self.is04_senders = self.is04_utils.get_senders()
        self.is05_senders = self.is05_utils.get_senders()
        self.is11_senders = self.is11_utils.get_senders()

        self.is04_sources = self.is04_utils.get_sources()
        self.is04_flows = self.is04_utils.get_flows()

        self.senders_to_test = {}
        self.senders_active = {}

        for smp_sender in self.is11_senders:
            for node_sender in self.is04_senders:
                if smp_sender == node_sender:
                    self.senders_to_test[smp_sender] = self.is04_senders[smp_sender]

    def test_01(self, test):
        """Check that version 1.2 or greater of the Node API is available"""

        api = self.apis[NODE_API_KEY]
        if self.is04_utils.compare_api_version(api["version"], "v1.2") >= 0:
            valid, result = self.do_request("GET", self.node_url)
            if valid:
                return test.PASS()
            else:
                return test.FAIL("Node API did not respond as expected: {}".format(result))
        else:
            return test.FAIL("Node API must be running v1.2 or greater")

    def test_02(self, test):
        """At least one Device is showing an IS-05 control advertisement matching the API under test"""

        valid, fail_message = self.is11_utils.check_for_api_control(
            self.node_url, self.connection_url, "urn:x-nmos:control:sr-ctrl/{}".format(self.apis[CONN_API_KEY]["version"]), self.authorization)
        if not valid:
            return test.FAIL(fail_message)

        return test.PASS()

    def test_03(self, test):
        """At least one Device is showing an IS-11 control advertisement matching the API under test"""

        valid, fail_message = self.is11_utils.check_for_api_control(
            self.node_url, self.url, "urn:x-nmos:control:sink-mp/{}".format(self.apis[SINIK_MP_API_KEY]["version"]), self.authorization)
        if not valid:
            return test.FAIL(fail_message)

        return test.PASS()

    def test_04(self, test):
        """Senders shown in Sink Metadata Processing API have corresponding resource in Node and Connection APIs"""

        if len(self.is11_senders) <= 0:
            return test.UNCLEAR("Not tested. No resources found.")

        missing_is04_resouce = []
        missing_is05_resouce = []

        for sender in self.is11_senders:
            if sender not in self.is04_senders:
                missing_is04_resouce.append(sender)
            if sender not in self.is05_senders:
                missing_is05_resouce.append(sender)

        if len(missing_is04_resouce) > 0 or len(missing_is05_resouce) > 0:
            return test.FAIL("Unable to find all resources in IS-04 and IS-05") # TODO(prince-chrismc): Print missing guids?

        return test.PASS()

    def test_05(self, test):
        """Applying Media Profiles on a sender increments the IS-04 version timestamp"""

        return test.NA("To be implemented")

    def test_06(self, test):
        """External deactivation of a sender updates the IS-04 subscription and version timestamp"""

        return test.MANUAL()

    def test_07(self, test):
        """External deactivation of a sender updates the IS-05 master_enabled"""

        return test.MANUAL()

    def test_99(self, test):
        """IS-11 Sink's EDID parameters match IS-04 Source, Flow, and Sender"""

        return test.NA("To be implemented")
