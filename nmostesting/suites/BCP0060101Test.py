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

import json

from ..GenericTest import GenericTest

NODE_API_KEY = "node"
CONN_API_KEY = "connection"


class BCP0060101Test(GenericTest):
    """
    Runs Node Tests covering BCP-006-01
    """
    def __init__(self, apis):
        # Don't auto-test /transportfile as it is permitted to generate a 404 when master_enable is false
        omit_paths = [
            "/single/senders/{senderId}/transportfile"
        ]
        GenericTest.__init__(self, apis, omit_paths)
        self.node_url = self.apis[NODE_API_KEY]["url"]
        self.connection_url = self.apis[CONN_API_KEY]["url"]

    def test_01(self, test):
        """JPEG XS Flows have the required attributes"""

        url = self.node_url + "flows"
        valid, response = self.do_request("GET", url)

        if valid and response.status_code == 200:
            try:
                flows = response.json()

                found_video_jxsv = False
                warn_unrestricted = False
                warn_message = ""

                for flow in flows:
                    if flow["media_type"] != "video/jxsv":
                        continue
                    found_video_jxsv = True
                    if "components" not in flow:
                        return test.FAIL("Flow {} MUST indicate the color (sub-)sampling using "
                                         "the 'components' attribute.".format(flow["id"]))
                    if "bit_rate" not in flow:
                        return test.FAIL("Flow {} MUST indicate the target bit rate of the codestream using "
                                         "the 'bit_rate' attribute.".format(flow["id"]))
                    if warn_unrestricted:
                        continue
                    if "profile" not in flow:
                        warn_unrestricted = True
                        warn_message = "Flow {} MUST indicate the JPEG XS profile using " \
                            "the 'profile' attribute unless it is Unrestricted.".format(flow["id"])
                    elif "level" not in flow:
                        warn_unrestricted = True
                        warn_message = "Flow {} MUST indicate the JPEG XS level using " \
                            "the 'level' attribute unless it is Unrestricted.".format(flow["id"])
                    elif "sublevel" not in flow:
                        warn_unrestricted = True
                        warn_message = "Flow {} MUST indicate the JPEG XS sublevel using " \
                            "the 'sublevel' attribute unless it is Unrestricted.".format(flow["id"])

                if warn_unrestricted:
                    return test.WARNING(warn_message)
                if found_video_jxsv:
                    return test.PASS()
            except json.JSONDecodeError:
                return test.FAIL("Non-JSON response returned from Node API")
            except KeyError as e:
                return test.FAIL("Expected key '{}' not found in response from {}".format(str(e), url))

        return test.UNCLEAR("No JPEG XS Flow resources were found on the Node")
