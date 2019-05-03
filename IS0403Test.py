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

import time
import socket

from zeroconf_monkey import ServiceBrowser, Zeroconf
from MdnsListener import MdnsListener
from GenericTest import GenericTest, NMOS_WIKI_URL
from IS04Utils import IS04Utils

NODE_API_KEY = "node"


class IS0403Test(GenericTest):
    """
    Runs IS-04-03-Test
    """
    def __init__(self, apis):
        GenericTest.__init__(self, apis)
        self.node_url = self.apis[NODE_API_KEY]["url"]
        self.is04_utils = IS04Utils(self.node_url)

    def set_up_tests(self):
        self.zc = Zeroconf()
        self.zc_listener = MdnsListener(self.zc)

    def tear_down_tests(self):
        if self.zc:
            self.zc.close()
            self.zc = None

    def test_01_node_mdns_with_txt(self, test):
        """Node advertises a Node type mDNS announcement with ver_* TXT records
        in the absence of a Registration API"""

        ServiceBrowser(self.zc, "_nmos-node._tcp.local.", self.zc_listener)
        time.sleep(1)
        node_list = self.zc_listener.get_service_list()
        for node in node_list:
            address = socket.inet_ntoa(node.address)
            port = node.port
            if "/{}:{}/".format(address, port) in self.node_url:
                properties = self.convert_bytes(node.properties)
                for ver_txt in ["ver_slf", "ver_src", "ver_flw", "ver_dvc", "ver_snd", "ver_rcv"]:
                    if ver_txt not in properties:
                        return test.FAIL("No '{}' TXT record found in Node API advertisement.".format(ver_txt))
                    try:
                        version = int(properties[ver_txt])
                        if version < 0:
                            return test.FAIL("Version ('{}') TXT record must be greater than or equal to zero."
                                             .format(ver_txt))
                        elif version > 255:
                            return test.WARNING("Version ('{}') TXT record must be less than or equal to 255."
                                                .format(ver_txt))
                    except Exception:
                        return test.FAIL("Version ('{}') TXT record is not an integer.".format(ver_txt))

                api = self.apis[NODE_API_KEY]
                if self.is04_utils.compare_api_version(api["version"], "v1.1") >= 0:
                    if "api_ver" not in properties:
                        return test.FAIL("No 'api_ver' TXT record found in Node API advertisement.")
                    elif api["version"] not in properties["api_ver"].split(","):
                        return test.FAIL("Node does not claim to support version under test.")

                    if "api_proto" not in properties:
                        return test.FAIL("No 'api_proto' TXT record found in Node API advertisement.")
                    elif properties["api_proto"] != self.protocol:
                        return test.FAIL("API protocol ('api_proto') TXT record is not '{}'.".format(self.protocol))

                return test.PASS()

        return test.FAIL("No matching mDNS announcement found for Node. Peer to peer mode will not function correctly.",
                         NMOS_WIKI_URL + "/IS-04#nodes-peer-to-peer-mode")

    def test_02_node_mdns_txt_increment(self, test):
        """Node increments its ver_* TXT records when its matching Node API resources change"""

        return test.MANUAL()
