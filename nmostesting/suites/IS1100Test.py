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

from ..GenericTest import GenericTest
from .. import TestHelper
COMPAT_API_KEY = "streamcompatibility"
CONTROLS = "controls"


class IS1100Test(GenericTest):
    """
    Runs Node Tests covering IS-11
    """
    def __init__(self, apis):
        GenericTest.__init__(self, apis)
        self.compat_url = self.apis[COMPAT_API_KEY]["url"]
        self.base_url = self.apis[COMPAT_API_KEY]["base_url"]

    def test_01(self, test):
        """Verify that IS-11 is exposed in the Node API as \
        urn:x-nmos:control:stream-compat/v1.0 at url /x-nmos/streamcompatibility/v1.0/
        """
        valid_res, response = TestHelper.do_request('GET', self.base_url + "/x-nmos/node/v1.3/devices/")
        if valid_res:
            response_json = response.json()
            controls = response_json[0][CONTROLS]
            control_href = ""
            for control in controls:
                if control["type"] == "urn:x-nmos:control:stream-compat/v1.0":
                    control_href = control["href"]
                    break
            if len(control) == 0:
                return test.WARNING("IS-11 API is not available")
            if not control_href.endswith(self.compat_url):
                return test.FAIL("IS-11 URL is invalid")
            return test.PASS()
        return test.FAIL(response)

    def test_02(self, test):
        "Put all senders into inactive state"
        senders_url = self.base_url + "/x-nmos/connection/v1.1/single/senders/"
        _, response = TestHelper.do_request('GET', senders_url)
        if response.status_code != 200:
            return test.FAIL(response.json())
        senders = response.json()
        if len(senders) > 0:
            for sender in senders:
                url = senders_url + sender + "staged/"
                deactivate_json = {
                                'master_enable': False,
                                "activation": {

                                            "mode": "activate_immediate"
                                            }

                               }

                _, response = TestHelper.do_request('PATCH', url, json=deactivate_json)
                if response.status_code != 200 or response.json()["master_enable"] or \
                   response.json()["activation"]["mode"] != "activate_immediate":
                    return test.FAIL(response.json())
            return test.PASS()
        return test.UNCLEAR("Could not find any IS-04 senders to test")

    def test_03(self, test):
        "Put all the receivers into inactive state"
        receivers_url = self.base_url+"/x-nmos/connection/v1.1/single/receivers/"
        _, response = TestHelper.do_request('GET', receivers_url)
        if response.status_code != 200:
            return test.FAIL(response.json())
        receivers = response.json()
        if len(receivers) > 0:
            for receiver in receivers:
                url = receivers_url + receiver + "staged/"
                deactivate_json = {
                                'master_enable': False,
                                "activation": {
                                            "mode": "activate_immediate"
                                            }
                               }
                _, response = TestHelper.do_request('PATCH', url, json=deactivate_json)
                if response.status_code != 200 or response.json()["master_enable"] or \
                        response.json()["activation"]["mode"] != "activate_immediate":
                    return test.FAIL(response.json())

            return test.PASS()

        return test.UNCLEAR("Could not find any IS-04 receivers to test")
