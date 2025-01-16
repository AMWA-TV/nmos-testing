# Copyright (C) 2025 Advanced Media Workflow Association
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

from ..IS12Utils import IS12Utils

from ..GenericTest import GenericTest, NMOSTestException
from .MS0501Test import MS0501Test

NODE_API_KEY = "node"
CONTROL_API_KEY = "ncp"
MS05_API_KEY = "controlframework"


class BCP0080101Test(GenericTest):
    """
    Runs Tests covering BCP-008-01
    """
    def __init__(self, apis, **kwargs):
        GenericTest.__init__(self, apis, **kwargs)
        self.is12_utils = IS12Utils(apis)
        # Instantiate MS0501Tests to access automatic tests
        # Hmmm, should the automatic tests be factored into the utils to allow all
        # MS-05 based test suites to access them?
        self.ms0502Test = MS0501Test(apis, self.is12_utils, **kwargs)
        self.node_url = apis[NODE_API_KEY]["url"]
        self.ncp_url = apis[CONTROL_API_KEY]["url"]

    def set_up_tests(self):
        self.ms0502Test.set_up_tests()
        self.is12_utils.open_ncp_websocket()
        super().set_up_tests()

    # Override basics to include the MS-05 auto tests
    def basics(self):
        results = super().basics()
        try:
            results += self.ms0502Test._auto_tests()
        except NMOSTestException as e:
            results.append(e.args[0])
        except Exception as e:
            results.append(self.uncaught_exception("auto_tests", e))
        return results

    def tear_down_tests(self):
        # Clean up Websocket resources
        self.is12_utils.close_ncp_websocket()

    def test_01(self, test):
        """First Test!!!!!"""
        return test.PASS()
