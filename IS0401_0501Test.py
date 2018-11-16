# Copyright 2018 British Broadcasting Corporation
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

import requests

from TestResult import Test
from GenericTest import GenericTest

NODE_API_KEY = "node"
CONN_API_KEY = "connection"


class IS04010501Test(GenericTest):
    """
    Runs Tests covering both IS-0401 and IS-0501
    """
    def __init__(self, apis):
        # Don't auto-test /transportfile as it is permitted to generate a 404 when master_enable is false
        omit_paths = [
            "/single/senders/{senderId}/transportfile"
        ]
        GenericTest.__init__(self, apis, omit_paths)
        self.node_url = self.apis[NODE_API_KEY]["url"]
        self.connection_url = self.apis[CONN_API_KEY]["url"]

    def test_01_device_control_present(self):
        """At least one Device is showing an IS-05 control advertisement"""
        pass

    def test_02_is04_is05_rx_match(self):
        """Receivers shown in CM API matches those shown in Node API"""
        pass

    def test_03_is04_is05_tx_match(self):
        """Senders shown in CM API matches those shown in Node API"""
        pass

    def test_04_rx_activate_updates_ver(self):
        """Activation of a receiver increments the version timestamp"""
        pass

    def test_05_tx_activate_updates_ver(self):
        """Activation of a sender increments the version timestamp"""
        pass

    def test_06_node_api_1_2_or_greater(self):
        """Check that version 1.2 or greater of the node API is available"""
