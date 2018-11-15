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


class IS04010501Test(GenericTest):
    """
    Runs Tests covering both IS-0401 and IS-0501
    """
    def __init__(self, apis, spec_versions, test_version, spec_path):
        GenericTest.__init__(self, apis, spec_versions, test_version, spec_path)
        self.node_url = self.apis["node"]["url"]
        self.connection_url = self.apis["connection"]["url"]

    def test_01(self):
        """At least one Device is showing an IS-05 control advertisement"""
        pass

    def test_02(self):
        """Receivers shown in CM API matches those shown in Node API"""
        pass

    def test_03(self):
        """Senders shown in CM API matches those shown in Node API"""
        pass

    def test_04(self):
        """Activation of a receiver increments the version timestamp"""
        pass

    def test_05(self):
        """Activation of a sender increments the version timestamp"""
        pass

    def test_06(self):
        """Check that version 1.2 or greater of the node API is available"""
