# Copyright (C) 2024 Advanced Media Workflow Association
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

from nmostesting.suites.MS0501Test import MS0501Test
from ..GenericTest import GenericTest, NMOSTestException

from ..IS14Utils import IS14Utils

from .MS0501Test import MS0501Test

CONFIGURATION_API_KEY = "configuration"

class IS1401Test(GenericTest):
    """
    Runs IS-04-01-Test
    """
    def __init__(self, apis, auths, **kwargs):
        GenericTest.__init__(self, apis, auths=auths, **kwargs)
        self.is14_utils = IS14Utils(apis)
        self.is14_utils.load_reference_resources(CONFIGURATION_API_KEY)
        self.ms0501Test = MS0501Test(apis, self.is14_utils)

    def set_up_tests(self):
        pass

    def tear_down_tests(self):
        pass

    def execute_tests(self, test_names):
        """Perform tests defined within this class"""
        # Override to allow 'auto' testing of MS-05 types and classes

        for test_name in test_names:
            self.execute_test(test_name)
            if test_name in ["auto", "all"] and not self.disable_auto:
                # Append datatype and class definition auto tests
                # Validate all standard datatypes and classes advertised by the Class Manager
                try:
                    self.result += self.ms0501Test.auto_tests()
                except NMOSTestException as e:
                    self.result.append(e.args[0])
            
    def test_01(self, test):
        """First test"""
        return test.UNCLEAR("I D K")
