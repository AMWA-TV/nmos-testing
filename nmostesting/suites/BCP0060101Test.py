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


class BCP0060101Test(GenericTest):
    """
    Runs Node Tests covering BCP-006-01
    """
    def __init__(self, apis, auths, **kwargs):
        # Don't auto-test /transportfile as it is permitted to generate a 404 when master_enable is false
        omit_paths = [
            "/single/senders/{senderId}/transportfile"
        ]
        GenericTest.__init__(self, apis, omit_paths, auths=auths, **kwargs)
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
            return test.FAIL("Node API must be running v1.3 or greater to fully implement BCP-006-01")

    def test_02(self, test):
        """JPEG XS Flows have the required attributes"""

        self.do_test_node_api_v1_1(test)

        v1_3 = self.is04_utils.compare_api_version(self.apis[NODE_API_KEY]["version"], "v1.3") >= 0

        reg_api = self.apis[FLOW_REGISTER_KEY]

        valid, result = self.get_is04_resources("flows")
        if not valid:
            return test.FAIL(result)

        reg_path = reg_api["spec_path"] + "/flow-attributes"
        reg_schema = load_resolved_schema(reg_path, "flow_video_register.json", path_prefix=False)

        try:
            jxsv_flows = [flow for flow in self.is04_resources["flows"] if flow["media_type"] == "video/jxsv"]

            warn_na = False
            warn_unrestricted = False
            warn_message = ""

            for flow in jxsv_flows:
                # check required attributes are present
                if "components" not in flow:
                    if v1_3:
                        return test.FAIL("Flow {} MUST indicate the color (sub-)sampling using "
                                         "the 'components' attribute.".format(flow["id"]))
                    else:
                        warn_na = True

                if "bit_rate" not in flow:
                    if v1_3:
                        return test.FAIL("Flow {} MUST indicate the target bit rate of the codestream using "
                                         "the 'bit_rate' attribute.".format(flow["id"]))
                    else:
                        warn_na = True

                # check values of all additional attributes against the schema
                # e.g. 'components', 'profile', 'level', 'sublevel' and 'bit_rate'
                try:
                    self.validate_schema(flow, reg_schema)
                except ValidationError as e:
                    return test.FAIL("Flow {} does not comply with the schema for Video Flow additional and "
                                     "extensible attributes defined in the NMOS Parameter Registers: "
                                     "{}".format(flow["id"], str(e)),
                                     "https://specs.amwa.tv/nmos-parameter-registers/branches/{}"
                                     "/flow-attributes/flow_video_register.html"
                                     .format(reg_api["spec_branch"]))

                # check recommended attributes are present
                if "profile" not in flow:
                    if v1_3 and not warn_unrestricted:
                        warn_unrestricted = True
                        warn_message = "Flow {} MUST indicate the JPEG XS profile using " \
                                       "the 'profile' attribute unless it is Unrestricted.".format(flow["id"])
                if "level" not in flow:
                    if v1_3 and not warn_unrestricted:
                        warn_unrestricted = True
                        warn_message = "Flow {} MUST indicate the JPEG XS level using " \
                                       "the 'level' attribute unless it is Unrestricted.".format(flow["id"])
                if "sublevel" not in flow:
                    if v1_3 and not warn_unrestricted:
                        warn_unrestricted = True
                        warn_message = "Flow {} MUST indicate the JPEG XS sublevel using " \
                                       "the 'sublevel' attribute unless it is Unrestricted.".format(flow["id"])

            if warn_na:
                return test.NA("Additional Flow attributes such as 'bit_rate' are required "
                               "with 'video/jxsv' from IS-04 v1.3")
            if warn_unrestricted:
                return test.WARNING(warn_message)

            if len(jxsv_flows) > 0:
                return test.PASS()

        except KeyError as ex:
            return test.FAIL("Expected attribute not found in IS-04 resource: {}".format(ex))

        return test.UNCLEAR("No JPEG XS Flow resources were found on the Node")

    def test_03(self, test):
        """JPEG XS Sources have the required attributes"""

        self.do_test_node_api_v1_1(test)

        for resource_type in ["flows", "sources"]:
            valid, result = self.get_is04_resources(resource_type)
            if not valid:
                return test.FAIL(result)

        source_map = {source["id"]: source for source in self.is04_resources["sources"]}

        try:
            jxsv_flows = [flow for flow in self.is04_resources["flows"] if flow["media_type"] == "video/jxsv"]

            for flow in jxsv_flows:
                source = source_map[flow["source_id"]]

                if source["format"] != "urn:x-nmos:format:video":
                    return test.FAIL("Source {} MUST indicate format with value 'urn:x-nmos:format:video'"
                                     .format(source["id"]))

            if len(jxsv_flows) > 0:
                return test.PASS()

        except KeyError as ex:
            return test.FAIL("Expected attribute not found in IS-04 resource: {}".format(ex))

        return test.UNCLEAR("No JPEG XS Flow resources were found on the Node")

    def test_04(self, test):
        """JPEG XS Senders have the required attributes"""

        self.do_test_node_api_v1_1(test)

        v1_3 = self.is04_utils.compare_api_version(self.apis[NODE_API_KEY]["version"], "v1.3") >= 0

        reg_api = self.apis[SENDER_REGISTER_KEY]

        for resource_type in ["senders", "flows"]:
            valid, result = self.get_is04_resources(resource_type)
            if not valid:
                return test.FAIL(result)

        flow_map = {flow["id"]: flow for flow in self.is04_resources["flows"]}

        reg_path = reg_api["spec_path"] + "/sender-attributes"
        reg_schema = load_resolved_schema(reg_path, "sender_register.json", path_prefix=False)

        try:
            jxsv_senders = [sender for sender in self.is04_resources["senders"] if sender["flow_id"]
                            and sender["flow_id"] in flow_map
                            and flow_map[sender["flow_id"]]["media_type"] == "video/jxsv"]

            warn_na = False
            warn_st2110_22 = False
            warn_message = ""

            for sender in jxsv_senders:
                # check required attributes are present
                if "transport" not in sender:
                    return test.FAIL("Sender {} MUST indicate the 'transport' attribute."
                                     .format(sender["id"]))
                if sender["transport"] not in {"urn:x-nmos:transport:rtp",
                                               "urn:x-nmos:transport:rtp.ucast",
                                               "urn:x-nmos:transport:rtp.mcast"}:
                    return test.FAIL("Sender {} MUST indicate 'transport' with one of the following values "
                                     "'urn:x-nmos:transport:rtp', 'urn:x-nmos:transport:rtp.ucast', or "
                                     "'urn:x-nmos:transport:rtp.mcast'"
                                     .format(sender["id"]))
                if "bit_rate" not in sender:
                    if v1_3:
                        return test.FAIL("Sender {} MUST indicate the 'bit_rate' attribute."
                                         .format(sender["id"]))
                    else:
                        warn_na = True

                # check values of all additional attributes against the schema
                # e.g. 'bit_rate', 'packet_transmission_mode' and 'st2110_21_sender_type'
                try:
                    self.validate_schema(sender, reg_schema)
                except ValidationError as e:
                    return test.FAIL("Sender {} does not comply with the schema for Sender additional and "
                                     "extensible attributes defined in the NMOS Parameter Registers: "
                                     "{}".format(sender["id"], str(e)),
                                     "https://specs.amwa.tv/nmos-parameter-registers/branches/{}"
                                     "/sender-attributes/sender_register.html"
                                     .format(reg_api["spec_branch"]))

                # check recommended attributes are present
                if "st2110_21_sender_type" not in sender:
                    if v1_3 and not warn_st2110_22:
                        warn_st2110_22 = True
                        warn_message = "Sender {} MUST indicate the ST 2110-21 Sender Type using " \
                                       "the 'st2110_21_sender_type' attribute if it is compliant with ST 2110-22." \
                                       .format(sender["id"])

            if warn_na:
                return test.NA("Additional Sender attributes such as 'bit_rate' are required "
                               "with 'video/jxsv' from IS-04 v1.3")
            if warn_st2110_22:
                return test.WARNING(warn_message)

            if len(jxsv_senders) > 0:
                return test.PASS()

        except KeyError as ex:
            return test.FAIL("Expected attribute not found in IS-04 resource: {}".format(ex))

        return test.UNCLEAR("No JPEG XS Sender resources were found on the Node")

    def test_05(self, test):
        """JPEG XS Sender manifests have the required parameters"""

        self.do_test_node_api_v1_1(test)

        v1_3 = self.is04_utils.compare_api_version(self.apis[NODE_API_KEY]["version"], "v1.3") >= 0

        for resource_type in ["senders", "flows"]:
            valid, result = self.get_is04_resources(resource_type)
            if not valid:
                return test.FAIL(result)

        flow_map = {flow["id"]: flow for flow in self.is04_resources["flows"]}
        source_map = {source["id"]: source for source in self.is04_resources["sources"]}

        try:
            jxsv_senders = [sender for sender in self.is04_resources["senders"] if sender["flow_id"]
                            and sender["flow_id"] in flow_map
                            and flow_map[sender["flow_id"]]["media_type"] == "video/jxsv"]

            access_error = False
            for sender in jxsv_senders:
                flow = flow_map[sender["flow_id"]]
                source = source_map[flow["source_id"]]

                if "manifest_href" not in sender:
                    return test.FAIL("Sender {} MUST indicate the 'manifest_href' attribute."
                                     .format(sender["id"]))

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
                    return test.FAIL("Unexpected response from manifest_href '{}': {}"
                                     .format(href, manifest_href_response))

                sdp = manifest_href_response.text

                payload_type = self.rtp_ptype(sdp)
                if not payload_type:
                    return test.FAIL("Unable to locate payload type from rtpmap in SDP file for Sender {}"
                                     .format(sender["id"]))

                sdp_lines = [sdp_line.replace("\r", "") for sdp_line in sdp.split("\n")]

                found_fmtp = False
                for sdp_line in sdp_lines:
                    fmtp = re.search(r"^a=fmtp:{} (.+)$".format(payload_type), sdp_line)
                    if not fmtp:
                        continue
                    found_fmtp = True

                    sdp_format_params = {}
                    for param in fmtp.group(1).split(";"):
                        name, _, value = param.strip().partition("=")
                        if name in ["interlace", "segmented"] and _:
                            return test.FAIL("SDP '{}' for Sender {} incorrectly includes an '='"
                                             .format(name, sender["id"]))
                        if name in ["depth", "width", "height", "packetmode", "transmode"]:
                            try:
                                value = int(value)
                            except ValueError:
                                return test.FAIL("SDP '{}' for Sender {} is not an integer"
                                                 .format(name, sender["id"]))
                        sdp_format_params[name] = value

                    # these SDP parameters are optional in RFC 9134 but are required by BCP-006-01
                    # and, from v1.3, must correspond to the Flow attributes, if not Unrestricted
                    for name, nmos_name in {"profile": "profile",
                                            "level": "level",
                                            "sublevel": "sublevel"}.items():
                        if name in sdp_format_params:
                            if nmos_name in flow:
                                if sdp_format_params[name] != flow[nmos_name]:
                                    return test.FAIL("SDP '{}' for Sender {} does not match {} in its Flow {}"
                                                     .format(name, sender["id"], nmos_name, flow["id"]))
                            elif v1_3:
                                return test.FAIL("SDP '{}' for Sender {} is present but {} is missing in its Flow {}"
                                                 .format(name, sender["id"], nmos_name, flow["id"]))
                        elif nmos_name in flow:
                            return test.FAIL("SDP '{}' for Sender {} is missing but must match {} in its Flow {}"
                                             .format(name, sender["id"], nmos_name, flow["id"]))

                    # this SDP parameter is optional in RFC 9134 but is required by BCP-006-01
                    # and, from v1.3, must correspond to the Flow attribute
                    name, nmos_name = "sampling", "components"
                    if name in sdp_format_params:
                        if nmos_name in flow:
                            if not self.check_sampling(flow[nmos_name], flow["frame_width"], flow["frame_height"],
                                                       sdp_format_params[name]):
                                return test.FAIL("SDP '{}' for Sender {} does not match {} in its Flow {}"
                                                 .format(name, sender["id"], nmos_name, flow["id"]))
                        elif v1_3:
                            return test.FAIL("SDP '{}' for Sender {} is present but {} is missing in its Flow {}"
                                             .format(name, sender["id"], nmos_name, flow["id"]))
                    else:
                        return test.FAIL("SDP '{}' for Sender {} is missing and must match {} in its Flow {} "
                                         "from v1.3".format(name, sender["id"], nmos_name, flow["id"]))

                    # this SDP parameter is optional in RFC 9134 but is required by BCP-006-01
                    # and, from v1.3, must correspond to the Flow attribute
                    name, nmos_name = "depth", "components"
                    if name in sdp_format_params:
                        if nmos_name in flow:
                            for component in flow[nmos_name]:
                                if sdp_format_params[name] != component["bit_depth"]:
                                    return test.FAIL("SDP '{}' for Sender {} does not match {} in its Flow {}"
                                                     .format(name, sender["id"], nmos_name, flow["id"]))
                        elif v1_3:
                            return test.FAIL("SDP '{}' for Sender {} is present but {} is missing in its Flow {}"
                                             .format(name, sender["id"], nmos_name, flow["id"]))
                    else:
                        return test.FAIL("SDP '{}' for Sender {} is missing and must match {} in its Flow {} "
                                         "from v1.3".format(name, sender["id"], nmos_name, flow["id"]))

                    # these SDP parameters are optional in RFC 9134 but are required by BCP-006-01
                    # and, from v1.1, must correspond to the Flow attributes
                    for name, nmos_name in {"width": "frame_width",
                                            "height": "frame_height"}.items():
                        if name in sdp_format_params:
                            if nmos_name in flow:
                                if sdp_format_params[name] != flow[nmos_name]:
                                    return test.FAIL("SDP '{}' for Sender {} does not match {} in its Flow {}"
                                                     .format(name, sender["id"], nmos_name, flow["id"]))
                            else:
                                return test.FAIL("SDP '{}' for Sender {} is present but {} is missing in its Flow {}"
                                                 .format(name, sender["id"], nmos_name, flow["id"]))
                        else:
                            return test.FAIL("SDP '{}' for Sender {} is missing and must match {} in its Flow {} "
                                             "from v1.1".format(name, sender["id"], nmos_name, flow["id"]))

                    # this SDP parameter is optional in RFC 9134 but is required by BCP-006-01
                    # and, from v1.1, must correspond to the Flow or Source attribute
                    name, nmos_name = "exactframerate", "grain_rate"
                    if name in sdp_format_params:
                        if nmos_name in flow:
                            if sdp_format_params[name] != self.exactframerate(flow[nmos_name]):
                                return test.FAIL("SDP '{}' for Sender {} does not match {} in its Flow {}"
                                                 .format(name, sender["id"], nmos_name, flow["id"]))
                        elif nmos_name in source:
                            if sdp_format_params[name] != self.exactframerate(source[nmos_name]):
                                return test.FAIL("SDP '{}' for Sender {} does not match {} in its Source {}"
                                                 .format(name, sender["id"], nmos_name, source["id"]))
                        else:
                            return test.FAIL("SDP '{}' for Sender {} is present but {} is missing in its Flow {}"
                                             .format(name, sender["id"], nmos_name, flow["id"]))
                    else:
                        return test.FAIL("SDP '{}' for Sender {} is missing and must match {} in its Flow {} "
                                         "from v1.1".format(name, sender["id"], nmos_name, flow["id"]))

                    # this SDP parameter is optional in RFC 9134 but is required by BCP-006-01
                    # and, from v1.1, must correspond to the Flow attribute
                    name, nmos_name = "colorimetry", "colorspace"
                    if name in sdp_format_params:
                        if nmos_name in flow:
                            if sdp_format_params[name] != flow[nmos_name]:
                                return test.FAIL("SDP '{}' for Sender {} does not match {} in its Flow {}"
                                                 .format(name, sender["id"], nmos_name, flow["id"]))
                        else:
                            return test.FAIL("SDP '{}' for Sender {} is present but {} is missing in its Flow {}"
                                             .format(name, sender["id"], nmos_name, flow["id"]))
                    else:
                        return test.FAIL("SDP '{}' for Sender {} is missing and must match {} in its Flow {} "
                                         "from v1.1".format(name, sender["id"], nmos_name, flow["id"]))

                    # this SDP parameter is optional in RFC 9134 but is required by BCP-006-01
                    # and, from v1.1, must correspond to the Flow attribute which has a default of "SDR"
                    # (and unlike ST 2110-20, RFC 91334 does not specify a default)
                    name, nmos_name = "TCS", "transfer_characteristic"
                    if name in sdp_format_params:
                        if sdp_format_params[name] != flow.get(nmos_name, "SDR"):
                            return test.FAIL("SDP '{}' for Sender {} does not match {} in its Flow {}"
                                             .format(name, sender["id"], nmos_name, flow["id"]))
                    else:
                        return test.FAIL("SDP '{}' for Sender {} is missing and must match {} in its Flow {} "
                                         "from v1.1".format(name, sender["id"], nmos_name, flow["id"]))

                    # this SDP parameter is required to be included or omitted by RFC 9134
                    # and, from v1.1, must correspond to the Flow attribute which has a default of "progressive"
                    name, nmos_name = "interlace", "interlace_mode"
                    if name in sdp_format_params:
                        if "progressive" == flow.get(nmos_name, "progressive"):
                            return test.FAIL("SDP '{}' for Sender {} does not match {} in its Flow {}"
                                             .format(name, sender["id"], nmos_name, flow["id"]))
                    else:
                        if "progressive" != flow.get(nmos_name, "progressive"):
                            return test.FAIL("SDP '{}' for Sender {} is missing but must match {} in its Flow {}"
                                             .format(name, sender["id"], nmos_name, flow["id"]))

                    # this SDP parameter is required to be included or omitted by RFC 9134
                    # and, from v1.1, must correspond to the Flow attribute which has a default of "progressive"
                    name, nmos_name = "segmented", "interlace_mode"
                    if name in sdp_format_params:
                        if "interlaced_psf" != flow.get(nmos_name, "progressive"):
                            return test.FAIL("SDP '{}' for Sender {} does not match {} in its Flow {}"
                                             .format(name, sender["id"], nmos_name, flow["id"]))
                    else:
                        if "interlaced_psf" == flow.get(nmos_name, "progressive"):
                            return test.FAIL("SDP '{}' for Sender {} is missing but must match {} in its Flow {}"
                                             .format(name, sender["id"], nmos_name, flow["id"]))

                    # this SDP parameter is required in RFC 9134
                    # and, from v1.3, must correspond to the Sender attribute which has a default of "codestream"
                    name, nmos_name = "packetmode", "packet_transmission_mode"
                    if name in sdp_format_params:
                        k, t = sdp_format_params[name], sdp_format_params.get("transmode", 1)
                        if v1_3 and self.packet_transmission_mode(k, t) != sender.get(nmos_name, "codestream"):
                            return test.FAIL("SDP '{}' for Sender {} does not match {} in the Sender"
                                             .format(name, sender["id"], nmos_name))
                    else:
                        return test.FAIL("SDP '{}' for Sender {} is missing and must match {} in the Sender "
                                         "from v1.3".format(name, sender["id"], nmos_name))

                    # this SDP parameter is required if the Sender is compliant with ST 2110-22
                    # and, from v1.3, must correspond to the Sender attribute
                    name, nmos_name = "TP", "st2110_21_sender_type"
                    if name in sdp_format_params:
                        if nmos_name in sender:
                            if sdp_format_params[name] != sender[nmos_name]:
                                return test.FAIL("SDP '{}' for Sender {} does not match {} in the Sender"
                                                 .format(name, sender["id"], nmos_name))
                        elif v1_3:
                            return test.FAIL("SDP '{}' for Sender {} is present but {} is missing in the Sender"
                                             .format(name, sender["id"], nmos_name))
                    elif nmos_name in sender:
                        return test.FAIL("SDP '{}' for Sender {} is missing but must match {} in the Sender"
                                         .format(name, sender["id"], nmos_name))

                if not found_fmtp:
                    return test.FAIL("SDP for Sender {} is missing format-specific parameters".format(sender["id"]))

                # this SDP line is required if the Sender is compliant with ST 2110-22
                # and, from v1.3, must correspond to the Sender attribute
                name, nmos_name = "b=<brtype>:<brvalue>", "bit_rate"
                found_bandwidth = False
                for sdp_line in sdp_lines:
                    bandwidth = re.search(r"^b=(.+):(.+)$", sdp_line)
                    if not bandwidth:
                        continue
                    found_bandwidth = True

                    if bandwidth.group(1) != "AS":
                        return test.FAIL("SDP '<brtype>' for Sender {} is not 'AS'"
                                         .format(sender["id"]))

                    value = bandwidth.group(2)
                    try:
                        value = int(value)
                    except ValueError:
                        return test.FAIL("SDP '<brvalue>' for Sender {} is not an integer"
                                         .format(sender["id"]))

                    if nmos_name in sender:
                        if value != sender[nmos_name]:
                            return test.FAIL("SDP '{}' for Sender {} does not match {} in the Sender"
                                             .format(name, sender["id"], nmos_name))
                    elif v1_3:
                        return test.FAIL("SDP '{}' for Sender {} is present but {} is missing in the Sender"
                                         .format(name, sender["id"], nmos_name))

                if nmos_name in sender and not found_bandwidth:
                    return test.FAIL("SDP '{}' for Sender {} is missing but must match {} in the Sender"
                                     .format(name, sender["id"], nmos_name))

            if access_error:
                return test.UNCLEAR("One or more of the tested Senders had null or empty 'manifest_href' or "
                                    "returned a 404 HTTP code. Please ensure all Senders are enabled and re-test.")

            if len(jxsv_senders) > 0:
                return test.PASS()

        except KeyError as ex:
            return test.FAIL("Expected attribute not found in IS-04 resource: {}".format(ex))

        return test.UNCLEAR("No JPEG XS Sender resources were found on the Node")

    def test_06(self, test):
        """JPEG XS Receivers have the required attributes"""

        self.do_test_node_api_v1_1(test)

        valid, result = self.get_is04_resources("receivers")
        if not valid:
            return test.FAIL(result)

        media_type_constraint = "urn:x-nmos:cap:format:media_type"
        # BCP-006-01 recommends indicating "constraints as precisely as possible".
        # ISO/IEC 21122 says "profiles, levels and sublevels specify restrictions on codestreams [and may be]
        # used to indicate interoperability points".
        # The transmission mode and packetization mode defined by RFC 9134 are also fundamental, since
        # some implementations will only handle codestream packetization.
        # BCP-006-01 lists other appropriate parameter constraints as well; all are checked in test_07.
        recommended_constraints = {
            "urn:x-nmos:cap:format:profile": "profile",
            "urn:x-nmos:cap:format:level": "level",
            "urn:x-nmos:cap:format:sublevel": "sublevel",
            "urn:x-nmos:cap:transport:packet_transmission_mode": "packet transmission mode"
        }

        try:
            jxsv_receivers = [receiver for receiver in self.is04_resources["receivers"]
                              if "media_types" in receiver["caps"]
                              and "video/jxsv" in receiver["caps"]["media_types"]]

            warn_unrestricted = False
            warn_message = ""

            for receiver in jxsv_receivers:
                # check required attributes are present
                if "transport" not in receiver:
                    return test.FAIL("Receiver {} MUST indicate the 'transport' attribute."
                                     .format(receiver["id"]))
                if receiver["transport"] not in {"urn:x-nmos:transport:rtp",
                                                 "urn:x-nmos:transport:rtp.ucast",
                                                 "urn:x-nmos:transport:rtp.mcast"}:
                    return test.FAIL("Receiver {} MUST indicate 'transport' with one of the following values "
                                     "'urn:x-nmos:transport:rtp', 'urn:x-nmos:transport:rtp.ucast', or "
                                     "'urn:x-nmos:transport:rtp.mcast'"
                                     .format(receiver["id"]))
                if "constraint_sets" not in receiver["caps"]:
                    return test.FAIL("Receiver {} MUST indicate constraints in accordance with BCP-004-01 using "
                                     "the 'caps' attribute 'constraint_sets'.".format(receiver["id"]))

                # exclude constraint sets for other media types
                jxsv_constraint_sets = [constraint_set for constraint_set in receiver["caps"]["constraint_sets"]
                                        if media_type_constraint not in constraint_set
                                        or ("enum" in constraint_set[media_type_constraint]
                                            and "video/jxsv" in constraint_set[media_type_constraint]["enum"])]

                if len(jxsv_constraint_sets) == 0:
                    return test.FAIL("Receiver {} MUST indicate constraints in accordance with BCP-004-01 using "
                                     "the 'caps' attribute 'constraint_sets'.".format(receiver["id"]))

                # check recommended attributes are present
                for constraint_set in jxsv_constraint_sets:
                    for constraint, target in recommended_constraints.items():
                        if constraint not in constraint_set:
                            if not warn_unrestricted:
                                warn_unrestricted = True
                                warn_message = "Receiver {} SHOULD indicate the supported JPEG XS {} using the " \
                                               "'{}' parameter constraint.".format(receiver["id"], target, constraint)

            if warn_unrestricted:
                return test.WARNING(warn_message)

            if len(jxsv_receivers) > 0:
                return test.PASS()

        except KeyError as ex:
            return test.FAIL("Expected attribute not found in IS-04 resource: {}".format(ex))

        return test.UNCLEAR("No JPEG XS Receiver resources were found on the Node")

    def test_07(self, test):
        """JPEG XS Receiver parameter constraints have valid values"""

        self.do_test_node_api_v1_1(test)

        valid, result = self.get_is04_resources("receivers")
        if not valid:
            return test.FAIL(result)

        flow_reg_path = self.apis[FLOW_REGISTER_KEY]["spec_path"] + "/flow-attributes"
        base_properties = load_resolved_schema(flow_reg_path, "flow_video_base_register.json",
                                               path_prefix=False)["properties"]
        jxsv_properties = load_resolved_schema(flow_reg_path, "flow_video_jxsv_register.json",
                                               path_prefix=False)["properties"]
        sender_path = self.apis[SENDER_REGISTER_KEY]["spec_path"] + "/sender-attributes"
        sender_properties = load_resolved_schema(sender_path, "sender_register.json",
                                                 path_prefix=False)["properties"]

        media_type_constraint = "urn:x-nmos:cap:format:media_type"

        enum_constraints = {
            "urn:x-nmos:cap:format:profile": jxsv_properties["profile"]["enum"],
            "urn:x-nmos:cap:format:level": jxsv_properties["level"]["enum"],
            "urn:x-nmos:cap:format:sublevel": jxsv_properties["sublevel"]["enum"],
            "urn:x-nmos:cap:format:colorspace": base_properties["colorspace"]["enum"],
            "urn:x-nmos:cap:format:transfer_characteristic": base_properties["transfer_characteristic"]["enum"],
            # sampling corresponds to Flow 'components' so there isn't a Flow schema to use
            "urn:x-nmos:cap:format:color_sampling": [
                # Red-Green-Blue-Alpha
                "RGBA",
                # Red-Green-Blue
                "RGB",
                # Non-constant luminance YCbCr
                "YCbCr-4:4:4",
                "YCbCr-4:2:2",
                "YCbCr-4:2:0",
                "YCbCr-4:1:1",
                # Constant luminance YCbCr
                "CLYCbCr-4:4:4",
                "CLYCbCr-4:2:2",
                "CLYCbCr-4:2:0",
                # Constant intensity ICtCp
                "ICtCp-4:4:4",
                "ICtCp-4:2:2",
                "ICtCp-4:2:0",
                # XYZ
                "XYZ",
                # Key signal represented as a single component
                "KEY",
                # Sampling signaled by the payload
                "UNSPECIFIED"
            ],
            "urn:x-nmos:cap:transport:packet_transmission_mode": sender_properties["packet_transmission_mode"]["enum"],
            "urn:x-nmos:cap:transport:st2110_21_sender_type": sender_properties["st2110_21_sender_type"]["enum"],
        }

        try:
            jxsv_receivers = [receiver for receiver in self.is04_resources["receivers"]
                              if "media_types" in receiver["caps"]
                              and "video/jxsv" in receiver["caps"]["media_types"]]

            for receiver in jxsv_receivers:
                # check required attributes are present
                if "constraint_sets" not in receiver["caps"]:
                    # FAIL reported by test_05
                    continue

                # exclude constraint sets for other media types
                jxsv_constraint_sets = [constraint_set for constraint_set in receiver["caps"]["constraint_sets"]
                                        if media_type_constraint not in constraint_set
                                        or ("enum" in constraint_set[media_type_constraint]
                                            and "video/jxsv" in constraint_set[media_type_constraint]["enum"])]

                if len(jxsv_constraint_sets) == 0:
                    # FAIL reported by test_05
                    continue

                # check recommended attributes are present
                for constraint_set in jxsv_constraint_sets:
                    for constraint, enum_values in enum_constraints.items():
                        if constraint in constraint_set and "enum" in constraint_set[constraint]:
                            for enum_value in constraint_set[constraint]["enum"]:
                                if enum_value not in enum_values:
                                    return test.FAIL("Receiver {} uses an invalid value for '{}': {}"
                                                     .format(receiver["id"], constraint, enum_value))

            if len(jxsv_receivers) > 0:
                return test.PASS()

        except KeyError as ex:
            return test.FAIL("Expected attribute not found in IS-04 resource: {}".format(ex))

        return test.UNCLEAR("No JPEG XS Receiver resources were found on the Node")

    # Utility function from IS0502Test
    def exactframerate(self, grain_rate):
        """Format an NMOS grain rate like the SDP video format-specific parameter 'exactframerate'"""
        d = grain_rate.get("denominator", 1)
        if d == 1:
            return "{}".format(grain_rate.get("numerator"))
        else:
            return "{}/{}".format(grain_rate.get("numerator"), d)

    # Utility function from IS0502Test
    def rtp_ptype(self, sdp_file):
        """Extract the payload type from an SDP file string"""
        payload_type = None
        for sdp_line in sdp_file.split("\n"):
            sdp_line = sdp_line.replace("\r", "")
            try:
                payload_type = int(re.search(r"^a=rtpmap:(\d+) ", sdp_line).group(1))
            except Exception:
                pass
        return payload_type

    # Utility function from IS0502Test
    def check_sampling(self, flow_components, flow_width, flow_height, sampling):
        """Check SDP video format-specific parameter 'sampling' matches Flow 'components'"""
        # SDP sampling should be like:
        # "RGBA", "RGB", "YCbCr-J:a:b", "CLYCbCr-J:a:b", "ICtCp-J:a:b", "XYZ", "KEY"
        components, _, sampling = sampling.partition("-")

        # Flow component names should be like:
        # "R", "G", "B", "A", "Y", "Cb", "Cr", "Yc", "Cbc", "Crc", "I", "Ct", "Cp", "X", "Z", "Key"
        if components == "CLYCbCr":
            components = "YcCbcCrc"
        if components == "KEY":
            components = "Key"

        sampler = None
        if not sampling or sampling == "4:4:4":
            sampler = (1, 1)
        elif sampling == "4:2:2":
            sampler = (2, 1)
        elif sampling == "4:2:0":
            sampler = (2, 2)
        elif sampling == "4:1:1":
            sampler = (4, 1)

        for component in flow_components:
            if component["name"] not in components:
                return False
            components = components.replace(component["name"], "")
            # subsampled components are "Cb", "Cr", "Cbc", "Crc", "Ct", "Cp"
            c = component["name"].startswith("C")
            if component["width"] != flow_width / (sampler[0] if c else 1) or \
                    component["height"] != flow_height / (sampler[1] if c else 1):
                return False

        return components == ""

    def packet_transmission_mode(self, packetmode, transmode):
        """Format the SDP 'packetmode' and 'transmode' as a Flow 'packet_transmission_mode'"""
        if packetmode == 0 and transmode == 1:
            return "codestream"
        elif packetmode == 1 and transmode == 1:
            return "slice_sequential"
        elif packetmode == 1 and transmode == 0:
            return "slice_out_of_order"
        else:
            return "INVALID"

    def do_test_node_api_v1_1(self, test):
        """
        Precondition check of the API version.
        Raises an NMOSTestException when the Node API version is less than v1.1
        """
        api = self.apis[NODE_API_KEY]
        if self.is04_utils.compare_api_version(api["version"], "v1.1") < 0:
            raise NMOSTestException(test.NA("This test cannot be run against Node API below version v1.1."))
