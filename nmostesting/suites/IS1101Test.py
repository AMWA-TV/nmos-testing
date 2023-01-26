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

from requests.compat import json

from ..GenericTest import GenericTest
from ..IS11Utils import IS11Utils

COMPAT_API_KEY = "streamcompatibility"


class IS1101Test(GenericTest):
    """
    Runs Node Tests covering IS-11
    """
    def __init__(self, apis, **kwargs):
        # Don't auto-test paths responding with an EDID binary as they don't have a JSON Schema
        omit_paths = [
            "/inputs/{inputId}/edid/base",
            "/inputs/{inputId}/edid/effective",
            "/outputs/{outputId}/edid"
        ]
        GenericTest.__init__(self, apis, omit_paths)
        self.compat_url = self.apis[COMPAT_API_KEY]["url"]
        self.is11_utils = IS11Utils(self.compat_url)

    def set_up_tests(self):
        self.senders = self.is11_utils.get_senders()
        self.receivers = self.is11_utils.get_receivers()

    def test_01(self, test):
        """A sender rejects Active Constraints with unsupported Parameter Constraint URNs"""

        if len(self.senders) == 0:
            return test.UNCLEAR("Not tested. No senders found.")

        senderId = self.senders[0]

        try:
            url = "senders/{}/constraints/active".format(senderId)
            data = {"constraint_sets": [{"urn:x-nmos:cap:not:existing": {"enum": [""]}}]}
            valid, response = self.is11_utils.checkCleanRequestJSON("PUT", url, data, 400)
            if valid:
                return test.PASS()
            else:
                return test.FAIL(response)

        except json.JSONDecodeError:
            return test.FAIL("Non-JSON response returned from Node API")
        except KeyError as e:
            return test.FAIL("Unable to find expected key: {}".format(e))
