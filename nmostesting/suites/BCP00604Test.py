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
import re

from jsonschema import ValidationError

from ..GenericTest import GenericTest, NMOSTestException
from ..IS04Utils import IS04Utils
from ..TestHelper import load_resolved_schema

NODE_API_KEY = "node"
FLOW_REGISTER_KEY = "flow-register"
SENDER_REGISTER_KEY = "sender-register"


class BCP00604Test(GenericTest):
    """
    Runs Node Tests covering BCP-006-04
    """

    def __init__(self, apis, **kwargs):
        # Don't auto-test /transportfile as it is permitted to generate a 404 when master_enable is false
        omit_paths = ["/single/senders/{senderId}/transportfile"]
        GenericTest.__init__(self, apis, omit_paths, **kwargs)
        self.node_url = self.apis[NODE_API_KEY]["url"]
        self.is04_resources = {"senders": [], "receivers": [], "_requested": [], "sources": [], "flows": []}
        self.is04_utils = IS04Utils(self.node_url)

    # Utility function from IS0502Test
    def get_is04_resources(self, resource_type):
        """Retrieve all Senders or Receivers from a Node API, keeping hold of the returned objects"""
        assert resource_type in ["senders", "receivers", "sources", "flows"]

        # Prevent this being executed twice in one test run
        if resource_type in self.is04_resources["_requested"]:
            return True, ""

        valid, resources = self.do_request("GET", self.node_url + resource_type)
        if not valid:
            return False, "Node API did not respond as expected: {}".format(resources)

        try:
            for resource in resources.json():
                self.is04_resources[resource_type].append(resource)
            self.is04_resources["_requested"].append(resource_type)
        except json.JSONDecodeError:
            return False, "Non-JSON response returned from Node API"

        return True, ""
    
    def has_required_flow_attr(self, flow):
        return flow.get("format") == "urn:x-nmos:format:mux" and flow.get("media_type") == "video/MP2T"

    def has_required_source_attr(self, source):
        return source.get("format") == "urn:x-nmos:format:mux"

    def has_required_receiver_attr(self, recv):
        return recv.get("format") == "urn:x-nmos:format:mux" and "video/MP2T" in recv.get("caps", {}).get("media_types")

    def test_01(self, test):
        """Check that version 1.3 or greater of the Node API is available"""

        api = self.apis[NODE_API_KEY]
        if self.is04_utils.compare_api_version(api["version"], "v1.3") >= 0:
            valid, result = self.do_request("GET", self.node_url)
            if valid:
                return test.PASS()
            else:
                return test.FAIL("Node API did not respond as expected: {}".format(result))
        else:
            return test.FAIL("Node API must be running v1.3 or greater to fully implement BCP-006-04")

    def test_02(self, test):
        """MPEG-TS Sources linked to a mux flow have the required attributes"""

        valid, result = self.get_is04_resources("sources")
        if not valid:
            return test.FAIL(result)
        
        valid, result = self.get_is04_resources("flows")
        if not valid:
            return test.FAIL(result)

        sources_linked_to_mux_flows = [f["source_id"] for f in self.is04_resources["flows"] if self.has_required_flow_attr(f)]

        try: 
            valid_mpeg_ts_sources = [s for s in self.is04_resources["sources"] if self.has_required_source_attr(s) and s["id"] in sources_linked_to_mux_flows]
        except KeyError as ex:
            return test.FAIL("Expected attribute not found in IS-04 resource: {}".format(ex))

        if len(valid_mpeg_ts_sources) > 0:
            return test.PASS() 
        else:
            return test.UNCLEAR("No MPEG-TS Sources resources were found on the Node")

    def test_03(self, test):
        """MPEG-TS Flows have the required attributes"""

        valid, result = self.get_is04_resources("flows")
        if not valid:
            return test.FAIL(result)

        try: 
            valid_mpeg_ts_flows = [f for f in self.is04_resources["flows"] if self.has_required_flow_attr(f)]
        except KeyError as ex:
            return test.FAIL("Expected attribute not found in IS-04 resource: {}".format(ex))

        # TODO validate schema

        if len(valid_mpeg_ts_flows) > 0:
            return test.PASS() 
        else:
            return test.UNCLEAR("No MPEG-TS Flow resources were found on the Node")

    def test_04(self, test):
        """MPEG-TS Senders have the required attributes and is assosicated with a mux flow"""

        valid, result = self.get_is04_resources("senders")
        if not valid:
            return test.FAIL(result)
       
        valid, result = self.get_is04_resources("flows")
        if not valid:
            return test.FAIL(result)
        
        # TODO: Validate IS-05 Transport
        # TODO: Check for Bit Rate attribute
        # TODO: Check that manifest_href returns an SDP

        valid_flow_ids = [f["id"] for f in self.is04_resources["flows"] if self.has_required_flow_attr(f)]

        try: 
            valid_mpeg_ts_senders = [s for s in self.is04_resources["senders"] if s["flow_id"] in valid_flow_ids and s["manifest_href"]]
        except KeyError as ex:
            return test.FAIL("Expected attribute not found in IS-04 resource: {}".format(ex))

        if len(valid_mpeg_ts_senders) > 0:
            print(valid_mpeg_ts_senders)
            return test.PASS() 
        else:
            return test.UNCLEAR("No MPEG-TS Flow resources were found on the Node")

    def test_05(self, test):
        """MPEG-TS Receivers have the required attributes"""

        valid, result = self.get_is04_resources("receivers")
        if not valid:
            return test.FAIL(result)

        # TODO: Validate IS-05 Transport
        # TODO: Check for Transport Bit Rate capability

        try: 
            valid_mpeg_ts_receivers = [r for r in self.is04_resources["receivers"] if self.has_required_receiver_attr(r)]
        except KeyError as ex:
            return test.FAIL("Expected attribute not found in IS-04 resource: {}".format(ex))

        if len(valid_mpeg_ts_receivers) > 0:
            return test.PASS() 
        else:
            return test.UNCLEAR("No MPEG-TS Receiver resources were found on the Node")
