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

from ..GenericTest import GenericTest
from ..TestHelper import load_resolved_schema

NODE_API_KEY = "node"
CONN_API_KEY = "connection"
FLOW_REGISTER_KEY = "flow-register"
SENDER_REGISTER_KEY = "sender-register"


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
        self.is04_resources = {"senders": [], "receivers": [], "_requested": [], "sources": [], "flows": []}

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
        """JPEG XS Flows have the required attributes"""

        reg_api = self.apis[FLOW_REGISTER_KEY]

        valid, result = self.get_is04_resources("flows")
        if not valid:
            return test.FAIL(result)

        reg_path = reg_api["spec_path"] + "/flow-attributes"
        reg_schema = load_resolved_schema(reg_path, "flow_video_register.json", path_prefix=False)

        try:
            found_video_jxsv = False
            warn_unrestricted = False
            warn_message = ""

            for flow in self.is04_resources["flows"]:
                if flow["media_type"] != "video/jxsv":
                    continue
                found_video_jxsv = True

                # check required attributes are present
                if "components" not in flow:
                    return test.FAIL("Flow {} MUST indicate the color (sub-)sampling using "
                                     "the 'components' attribute.".format(flow["id"]))
                if "bit_rate" not in flow:
                    return test.FAIL("Flow {} MUST indicate the target bit rate of the codestream using "
                                     "the 'bit_rate' attribute.".format(flow["id"]))

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
        except KeyError as ex:
            return test.FAIL("Expected attribute not found in IS-04 resource: {}".format(ex))

        return test.UNCLEAR("No JPEG XS Flow resources were found on the Node")

    def test_02(self, test):
        """JPEG XS Sources have the required attributes"""

        for resource_type in ["flows", "sources"]:
            valid, result = self.get_is04_resources(resource_type)
            if not valid:
                return test.FAIL(result)

        source_map = {source["id"]: source for source in self.is04_resources["sources"]}

        try:
            found_video_jxsv = False

            for flow in self.is04_resources["flows"]:
                if flow["media_type"] != "video/jxsv":
                    continue
                found_video_jxsv = True

                source = source_map[flow["source_id"]]

                if source["format"] != "urn:x-nmos:format:video":
                    return test.FAIL("Source {} MUST indicate format with value 'urn:x-nmos:format:video'"
                                     .format(source["id"]))

            if found_video_jxsv:
                return test.PASS()

        except KeyError as ex:
            return test.FAIL("Expected attribute not found in IS-04 resource: {}".format(ex))

        return test.UNCLEAR("No JPEG XS Flow resources were found on the Node")

    def test_03(self, test):
        """JPEG XS Senders have the required attributes"""

        reg_api = self.apis[SENDER_REGISTER_KEY]

        for resource_type in ["senders", "flows"]:
            valid, result = self.get_is04_resources(resource_type)
            if not valid:
                return test.FAIL(result)

        flow_map = {flow["id"]: flow for flow in self.is04_resources["flows"]}

        reg_path = reg_api["spec_path"] + "/sender-attributes"
        reg_schema = load_resolved_schema(reg_path, "sender_register.json", path_prefix=False)

        try:
            found_video_jxsv = False
            warn_st2110_22 = False
            warn_message = ""

            for sender in self.is04_resources["senders"]:
                if sender["flow_id"] is None:
                    continue
                if sender["flow_id"] not in flow_map:
                    continue
                flow = flow_map[sender["flow_id"]]
                if flow["media_type"] != "video/jxsv":
                    continue
                found_video_jxsv = True

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
                    return test.FAIL("Sender {} MUST indicate the 'bit_rate' attribute."
                                     .format(sender["id"]))

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
                if warn_st2110_22:
                    continue
                if "st2110_21_sender_type" not in sender:
                    warn_st2110_22 = True
                    warn_message = "Sender {} MUST indicate the ST 2110-21 Sender Type using " \
                                   "the 'st2110_21_sender_type' attribute if it is compliant with ST 2110-22." \
                                   .format(sender["id"])

            if warn_st2110_22:
                return test.WARNING(warn_message)
            if found_video_jxsv:
                return test.PASS()

        except KeyError as ex:
            return test.FAIL("Expected attribute not found in IS-04 resource: {}".format(ex))

        return test.UNCLEAR("No JPEG XS Sender resources were found on the Node")

    def test_04(self, test):
        """JPEG XS Sender manifests have the required parameters"""

        for resource_type in ["senders", "flows"]:
            valid, result = self.get_is04_resources(resource_type)
            if not valid:
                return test.FAIL(result)

        flow_map = {flow["id"]: flow for flow in self.is04_resources["flows"]}
        source_map = {source["id"]: source for source in self.is04_resources["sources"]}

        try:
            found_video_jxsv = False

            for sender in self.is04_resources["senders"]:
                if sender["flow_id"] is None:
                    continue
                if sender["flow_id"] not in flow_map:
                    continue
                flow = flow_map[sender["flow_id"]]
                if flow["media_type"] != "video/jxsv":
                    continue
                found_video_jxsv = True

                source = source_map[flow["source_id"]]

                if "manifest_href" not in sender:
                    return test.FAIL("Sender {} MUST indicate the 'manifest_href' attribute."
                                     .format(sender["id"]))

                url = sender["manifest_href"]
                manifest_href_valid, manifest_href_response = self.do_request("GET", url)
                if not manifest_href_valid or manifest_href_response.status_code != 200:
                    return test.FAIL("Unexpected response from the Node API: {}"
                                     .format(manifest_href_response))

                sdp = manifest_href_response.text

                payload_type = self.rtp_ptype(sdp)
                if not payload_type:
                    return test.FAIL("Unable to locate payload type from rtpmap in SDP file for Sender {}"
                                     .format(sender["id"]))

                found_fmtp = False

                fmtp_line = "a=fmtp:{}".format(payload_type)
                for sdp_line in sdp.split("\n"):
                    sdp_line = sdp_line.replace("\r", "")

                    if not sdp_line.startswith(fmtp_line):
                        continue
                    found_fmtp = True

                    sdp_line = sdp_line[len(fmtp_line):]

                    sdp_format_params = {}
                    for param in sdp_line.split(";"):
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

                    # these SDP parameters are optional in RFC 9134 but required to be included or omitted by BCP-006-01
                    # and correspond to the Flow attributes, if not Unrestricted
                    for name, nmos_name in {"profile": "profile",
                                            "level": "level",
                                            "sublevel": "sublevel"}.items():
                        if name in sdp_format_params:
                            if nmos_name in flow:
                                if sdp_format_params[name] != flow[nmos_name]:
                                    return test.FAIL("SDP '{}' for Sender {} does not match {} in its Flow {}"
                                                     .format(name, sender["id"], nmos_name, flow["id"]))
                            else:
                                return test.FAIL("SDP '{}' for Sender {} is present but {} is missing in its Flow {}"
                                                 .format(name, sender["id"], nmos_name, flow["id"]))
                        else:
                            if nmos_name in flow:
                                return test.FAIL("SDP '{}' for Sender {} is missing but must match {} in its Flow {}"
                                                 .format(name, sender["id"], nmos_name, flow["id"]))

                    # the SDP 'depth' parameter is optional in RFC 9134 but required by BCP-006-01
                    # since the Flow attributes are required by IS-04
                    name, nmos_name = "sampling", "components"
                    if name in sdp_format_params:
                        if not self.check_sampling(flow[nmos_name], flow["frame_width"], flow["frame_height"],
                                                   sdp_format_params[name]):
                            return test.FAIL("SDP '{}' for Sender {} does not match {} in its Flow {}"
                                             .format(name, sender["id"], nmos_name, flow["id"]))
                    else:
                        return test.FAIL("SDP '{}' for Sender {} is missing but must match {} in its Flow {}"
                                         .format(name, sender["id"], nmos_name, flow["id"]))

                    # the SDP 'depth' parameter is optional in RFC 9134 but required by BCP-006-01
                    # since it corresponds to bit_depth in Flow components which is required by IS-04
                    name, nmos_name = "depth", "components"
                    if name in sdp_format_params:
                        for component in flow[nmos_name]:
                            if sdp_format_params[name] != component["bit_depth"]:
                                return test.FAIL("SDP '{}' for Sender {} does not match {} in its Flow {}"
                                                 .format(name, sender["id"], nmos_name, flow["id"]))
                    else:
                        return test.FAIL("SDP '{}' for Sender {} is missing but must match {} in its Flow {}"
                                         .format(name, sender["id"], nmos_name, flow["id"]))

                    # these SDP parameters are optional in RFC 9134 but required by BCP-006-01
                    # since the Flow attributes are required by IS-04
                    for name, nmos_name in {"width": "frame_width",
                                            "height": "frame_height"}.items():
                        if name in sdp_format_params:
                            if sdp_format_params[name] != flow[nmos_name]:
                                return test.FAIL("SDP '{}' for Sender {} does not match {} in its Flow {}"
                                                 .format(name, sender["id"], nmos_name, flow["id"]))
                        else:
                            return test.FAIL("SDP '{}' for Sender {} is missing but must match {} in its Flow {}"
                                             .format(name, sender["id"], nmos_name, flow["id"]))

                    # the SDP 'exactframerate' parameter is optional in RFC 9134 but required by BCP-006-01
                    # since the Flow or Source attribute is required by IS-04
                    name, nmos_name = "exactframerate", "grain_rate"
                    if name in sdp_format_params:
                        if nmos_name in flow:
                            if sdp_format_params[name] != self.exactframerate(flow[nmos_name]):
                                return test.FAIL("SDP '{}' for Sender {} does not match {} in its Flow {}"
                                                 .format(name, sender["id"], nmos_name, flow["id"]))
                        elif sdp_format_params[name] != self.exactframerate(source[nmos_name]):
                            return test.FAIL("SDP '{}' for Sender {} does not match {} in its Source {}"
                                             .format(name, sender["id"], nmos_name, source["id"]))
                    else:
                        return test.FAIL("SDP '{}' for Sender {} is missing but must match {} in its Flow {}"
                                         .format(name, sender["id"], nmos_name, flow["id"]))

                    # the SDP 'colorimetry' parameter is optional in RFC 9134 but required by BCP-006-01
                    # since the Flow attribute is required by IS-04
                    name, nmos_name = "colorimetry", "colorspace"
                    if name in sdp_format_params:
                        if sdp_format_params[name] != flow[nmos_name]:
                            return test.FAIL("SDP '{}' for Sender {} does not match {} in its Flow {}"
                                             .format(name, sender["id"], nmos_name, flow["id"]))
                    else:
                        return test.FAIL("SDP '{}' for Sender {} is missing but must match {} in its Flow {}"
                                         .format(name, sender["id"], nmos_name, flow["id"]))

                    # the SDP 'TCS' parameter is optional in RFC 9134 but required by BCP-006-01
                    # since the Flow attribute has a default of "SDR" in IS-04
                    # (and unlike ST 2110-20, RFC 91334 does not specify a default of "SDR")
                    name, nmos_name = "TCS", "transfer_characteristic"
                    if name in sdp_format_params:
                        if sdp_format_params[name] != flow.get(nmos_name, "SDR"):
                            return test.FAIL("SDP '{}' for Sender {} does not match {} in its Flow {}"
                                             .format(name, sender["id"], nmos_name, flow["id"]))
                    else:
                        return test.FAIL("SDP '{}' for Sender {} is missing but must match {} in its Flow {}"
                                         .format(name, sender["id"], nmos_name, flow["id"]))

                    # the SDP 'interlace' parameter is required to be included or omitted by RFC 9134
                    # and corresponds to the Flow attribute which has a default of "progressive" in IS-04
                    name, nmos_name = "interlace", "interlace_mode"
                    if name in sdp_format_params:
                        if "progressive" == flow.get(nmos_name, "progressive"):
                            return test.FAIL("SDP '{}' for Sender {} does not match {} in its Flow {}"
                                             .format(name, sender["id"], nmos_name, flow["id"]))
                    else:
                        if "progressive" != flow.get(nmos_name, "progressive"):
                            return test.FAIL("SDP '{}' for Sender {} is missing but must match {} in its Flow {}"
                                             .format(name, sender["id"], nmos_name, flow["id"]))

                    # the SDP 'segmented' parameter is required to be included or omitted by RFC 9134
                    # and corresponds to the Flow attribute which has a default of "progressive" in IS-04
                    name, nmos_name = "segmented", "interlace_mode"
                    if name in sdp_format_params:
                        if "interlaced_psf" != flow.get(nmos_name, "progressive"):
                            return test.FAIL("SDP '{}' for Sender {} does not match {} in its Flow {}"
                                             .format(name, sender["id"], nmos_name, flow["id"]))
                    else:
                        if "interlaced_psf" == flow.get(nmos_name, "progressive"):
                            return test.FAIL("SDP '{}' for Sender {} is missing but must match {} in its Flow {}"
                                             .format(name, sender["id"], nmos_name, flow["id"]))

                if not found_fmtp:
                    return test.FAIL("SDP for Sender {} is missing format-specific parameters".format(sender["id"]))

            if found_video_jxsv:
                return test.PASS()

        except KeyError as ex:
            return test.FAIL("Expected attribute not found in IS-04 resource: {}".format(ex))

        return test.UNCLEAR("No JPEG XS Sender resources were found on the Node")

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
