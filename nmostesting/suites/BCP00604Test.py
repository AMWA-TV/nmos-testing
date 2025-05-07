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

from jsonschema import ValidationError

from ..GenericTest import GenericTest
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
        GenericTest.__init__(self, apis, **kwargs)
        self.node_url = self.apis[NODE_API_KEY]["url"]
        self.is04_resources = {
            "senders": [],
            "receivers": [],
            "_requested": [],
            "sources": [],
            "flows": [],
        }
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
        """The Source associated with a mux Flow MUST have its `format` attribute set to `urn:x-nmos:format:mux`"""

        valid, result = self.get_is04_resources("sources")
        if not valid:
            return test.FAIL(result)

        valid, result = self.get_is04_resources("flows")
        if not valid:
            return test.FAIL(result)

        mux_sources = [source for source in self.is04_resources.get("sources") if self.has_required_source_attr(source)]
        if len(mux_sources) == 0:
            return test.FAIL("No Sources with format=urn:x-nmos:format:mux were found on the Node")

        mux_flows = [flow for flow in self.is04_resources.get("flows") if self.has_required_flow_attr(flow)]
        if len(mux_flows) == 0:
            return test.FAILURE(
                "No Flows with format=urn:x-nmos:format:mux and media_type=video/MP2T were found on the Node"
            )

        # check that all mux_sources are linked to a mux flow
        for source in mux_sources:
            if source.get("id") not in [flow.get("source_id") for flow in mux_flows]:
                return test.FAIL("Mux Source {} is not linked to a mux flow".format(source.get("id")))

        return test.PASS()

    def test_03(self, test):
        """MPEG-TS Flows have the required attributes"""

        valid, result = self.get_is04_resources("flows")
        if not valid:
            return test.FAIL(result)

        mp2t_flows = [f for f in self.is04_resources.get("flows") if self.has_required_flow_attr(f)]
        if len(mp2t_flows) == 0:
            return test.FAIL(
                "No Flows with format=urn:x-nmos:format:mux and media_type=video/MP2T were found on the Node"
            )

        reg_api = self.apis[FLOW_REGISTER_KEY]
        reg_path = reg_api["spec_path"] + "/flow-attributes"
        reg_schema = load_resolved_schema(reg_path, "flow_video_register.json", path_prefix=False)

        for flow in mp2t_flows:
            try:
                self.validate_schema(flow, reg_schema)
            except ValidationError as e:
                return test.FAIL(
                    "Flow {} does not comply with the schema for Video Flow additional and "
                    "extensible attributes defined in the NMOS Parameter Registers: "
                    "{}".format(flow["id"], str(e)),
                    "https://specs.amwa.tv/nmos-parameter-registers/branches/{}"
                    "/flow-attributes/flow_video_register.html".format(reg_api["spec_branch"]),
                )

        return test.PASS()

    def test_04(self, test):
        """MPEG-TS Senders have the required attributes and is assosicated with a mux flow"""

        valid, result = self.get_is04_resources("senders")
        if not valid:
            return test.FAIL(result)

        valid, result = self.get_is04_resources("flows")
        if not valid:
            return test.FAIL(result)

        # Currently the test does not cover other transports than RTP
        tested_transports = [
            "urn:x-nmos:transport:rtp",
            "urn:x-nmos:transport:rtp.mcast",
            "urn:x-nmos:transport:rtp.ucast",
        ]

        reg_api = self.apis[SENDER_REGISTER_KEY]
        reg_path = reg_api["spec_path"] + "/sender-attributes"
        reg_schema = load_resolved_schema(reg_path, "sender_register.json", path_prefix=False)

        mp2t_flows = [f["id"] for f in self.is04_resources["flows"] if self.has_required_flow_attr(f)]
        if len(mp2t_flows) == 0:
            return test.FAIL(
                "No Flows with format=urn:x-nmos:format:mux and media_type=video/MP2T were found on the Node"
            )

        mp2t_senders = [s for s in self.is04_resources.get("senders") if s.get("flow_id") in mp2t_flows]
        if len(mp2t_senders) == 0:
            return test.FAIL("No Senders associate with a mux flow found on the Node")

        mp2t_rtp_senders = [s for s in mp2t_senders if s.get("transport") in tested_transports]

        if len(mp2t_rtp_senders) == 0:
            return test.NA(
                "Could not test. No MP2T Sender with RTP transport found. "
                "All IS-05 transports are valid for BCP-006-04, but this test currently only covers RTP."
            )

        access_error = False
        for sender in mp2t_rtp_senders:

            try:
                self.validate_schema(sender, reg_schema)
            except ValidationError as e:
                return test.FAIL(
                    "Sender {} does not comply with the schema for Sender additional and "
                    "extensible attributes defined in the NMOS Parameter Registers: "
                    "{}".format(sender["id"], str(e)),
                    "https://specs.amwa.tv/nmos-parameter-registers/branches/{}"
                    "/sender-attributes/sender_register.html".format(reg_api["spec_branch"]),
                )

            if "transport" not in sender:
                return test.FAIL("Sender {} MUST indicate the 'transport' attribute.".format(sender["id"]))

            if "bit_rate" not in sender:
                return test.FAIL("Sender {} MUST indicate the 'bit_rate' attribute.".format(sender["id"]))

            if "manifest_href" not in sender:
                return test.FAIL("Sender {} MUST indicate the 'manifest_hrf' attribute.".format(sender["id"]))
            href = sender["manifest_href"]
            if not href:
                access_error = True
                continue

            manifest_href_valid, manifest_href_response = self.do_request("GET", href)
            if manifest_href_valid and manifest_href_response.status_code == 200:
                pass
            elif manifest_href_valid and manifest_href_response.status_code == 404:
                access_error = True
                continue
            else:
                return test.FAIL("Unexpected response from manifest_href '{}': {}".format(href, manifest_href_response))

            sdp = manifest_href_response.text
            if not sdp:
                access_error = True
                continue

        if access_error:
            return test.UNCLEAR(
                "One or more of the tested Senders had null or empty 'manifest_href' or "
                "returned a 404 HTTP code. Please ensure all Senders are enabled and re-test."
            )

        return test.PASS()

    def test_05(self, test):
        """MPEG-TS Receivers have the required attributes"""

        valid, result = self.get_is04_resources("receivers")
        if not valid:
            return test.FAIL(result)

        # Currently the test does not cover other transports than RTP
        tested_transports = [
            "urn:x-nmos:transport:rtp",
            "urn:x-nmos:transport:rtp.mcast",
            "urn:x-nmos:transport:rtp.ucast",
        ]

        mp2t_receivers = [r for r in self.is04_resources.get("receivers") if self.has_required_receiver_attr(r)]
        if len(mp2t_receivers) == 0:
            return test.FAIL(
                "No Receivers with format=urn:x-nmos:format:mux "
                "and media_type=video/MP2T in caps were found on the Node"
            )

        mp2t_rtp_receivers = [s for s in mp2t_receivers if s.get("transport") in tested_transports]

        if len(mp2t_rtp_receivers) == 0:
            return test.NA(
                "Could not test. No MP2T Receiver with RTP transport found. "
                "This test suite currently only supports RTP."
            )

        media_type_constraint = "urn:x-nmos:cap:format:media_type"
        recommended_constraints = {
            "urn:x-nmos:cap:transport:bit_rate": "bit_rate",
        }

        warn_unrestricted = False
        warn_message = ""

        for receiver in mp2t_receivers:
            if "transport" not in receiver:
                return test.FAIL("Receiver {} MUST indicate the 'transport' attribute.".format(receiver["id"]))

            if "constraint_sets" not in receiver["caps"]:
                warn_unrestricted = True
                warn_message = "No Transport Bit Rate parameter constraint published by receiver {}".format(
                    receiver["id"]
                )
                continue

            mp2t_constraint_sets = [
                constraint_set
                for constraint_set in receiver["caps"]["constraint_sets"]
                if media_type_constraint not in constraint_set
                or (
                    "enum" in constraint_set[media_type_constraint]
                    and "video/MP2T" in constraint_set[media_type_constraint]["enum"]
                )
            ]

            # check recommended attributes are present
            for constraint_set in mp2t_constraint_sets:
                for constraint, _target in recommended_constraints.items():
                    if constraint not in constraint_set:
                        if not warn_unrestricted:
                            warn_unrestricted = True
                            warn_message = "No Transport Bit Rate parameter constraint published by receiver {}".format(
                                receiver["id"]
                            )

        if warn_unrestricted:
            return test.WARNING(warn_message)

        return test.PASS()
