# Copyright (C) 2018 British Broadcasting Corporation
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
from ..IS11Utils import IS11Utils

SINIK_MP_API_KEY = "sink-mp"


class IS1101Test(GenericTest):
    """
    Runs IS-11-01-Test
    """

    def __init__(self, apis):
        omit_paths = [
            "/sinks/{sinkId}/edid" # Does not have a schema
        ]
        GenericTest.__init__(self, apis, omit_paths)
        self.url = self.apis[SINIK_MP_API_KEY]["url"]
        self.is11_utils = IS11Utils(self.url)

    def set_up_tests(self):
        self.senders = self.is11_utils.get_senders()
        self.receivers = self.is11_utils.get_receivers()
        self.sinks = self.is11_utils.get_sinks()

    def test_01(self, test):
        """Senders Media Profile's SHOULD initial be empty"""

        return test.NA("To be implemented")

    def test_02(self, test):
        """Senders accept valid Media Profile"""

        return test.NA("To be implemented")

    def test_03(self, test):
        """Senders clears Media Profile on DELETE"""

        return test.NA("To be implemented")

    def test_04(self, test):
        """Receivers are associated to known Sinks"""

        return test.NA("To be implemented")

    def test_05(self, test):
        """Sinks expose a valid EDID"""
        # TODO: Possibly look into https://github.com/jojonas/pyedid

        return test.MANUAL()
