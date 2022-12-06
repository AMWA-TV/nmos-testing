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

                if "manifest_href" not in sender:
                    return test.FAIL("Sender {} MUST indicate the 'manifest_href' attribute."
                                     .format(sender["id"]))

                url = sender["manifest_href"]
                manifest_href_valid, manifest_href_response = self.do_request("GET", url)
                if not manifest_href_valid or manifest_href_response.status_code != 200:
                    return test.FAIL(
                        "Unexpected response from the Node API: {}".format(manifest_href_response))

                sdp = manifest_href_response.text

                payload_type = self.rtp_ptype(sdp)
                if not payload_type:
                    return test.FAIL(
                        "Unable to locate payload type from rtpmap in SDP file for Sender {}"
                        .format(sender["id"]))

                fmtp_line = "a=fmtp:{}".format(payload_type)
                for sdp_line in sdp.split("\n"):
                    sdp_line = sdp_line.replace("\r", "")

                    if sdp_line.startswith(fmtp_line):
                        sdp_format_params = {}
                        sdp_line = sdp_line[len(fmtp_line):]
                        for param in sdp_line.split(";"):
                            param_components = param.strip().split("=")
                            sdp_format_params[param_components[0]] = param_components[1] \
                                if len(param_components) > 1 else True

                        for prop in ["profile", "level", "sublevel"]:
                            if prop in flow and flow[prop] != sdp_format_params[prop]:
                                return test.FAIL("Video Flow {} {} does not match that found in SDP for "
                                                 "Sender {}".format(flow["id"], prop, sender["id"]))

                        if flow["frame_width"] != int(sdp_format_params["width"]):
                            return test.FAIL("Video Flow {} frame_width does not match that found in SDP for "
                                             "Sender {}".format(flow["id"], sender["id"]))

                        if flow["frame_height"] != int(sdp_format_params["height"]):
                            return test.FAIL("Video Flow {} frame_height does not match that found in SDP for "
                                             "Sender {}".format(flow["id"], sender["id"]))

                        if flow["colorspace"] != sdp_format_params["colorimetry"]:
                            return test.FAIL("Video Flow {} colorspace does not match that found in SDP for "
                                             "Sender {}".format(flow["id"], sender["id"]))

                        if flow["interlace_mode"] == "interlaced_tff" and "interlace" not in sdp_format_params:
                            return test.FAIL("Video Flow {} interlace_mode does not match that found in SDP for "
                                             "Sender {}".format(flow["id"], sender["id"]))

                        if "exactframerate" not in sdp_format_params:
                            return test.FAIL("SDP for Sender {} misses format parameter 'exactframerate'"
                                             .format(sender["id"]))

                        framerate_components = sdp_format_params["exactframerate"].split("/")
                        framerate_numerator = int(framerate_components[0])
                        framerate_denominator = int(framerate_components[1]) \
                            if len(framerate_components) > 1 else 1

                        if flow["grain_rate"]["numerator"] != framerate_numerator or \
                                flow["grain_rate"]["denominator"] != framerate_denominator:
                            return test.FAIL("Video Flow {} grain_rate does not match that found in SDP for "
                                             "Sender {}".format(flow["id"], sender["id"]))

                        if "sampling" not in sdp_format_params:
                            return test.FAIL("SDP for Sender {} misses format parameter 'sampling'"
                                             .format(sender["id"]))

                        sampling_format = sdp_format_params["sampling"].split("-")
                        components = sampling_format[0]
                        if components in ["YCbCr", "ICtCp", "RGB"]:
                            if len(flow["components"]) != 3:
                                return test.FAIL("Video Flow {} components do not match those found in SDP for "
                                                 "Sender {}".format(flow["id"], sender["id"]))
                            if len(sampling_format) > 1:
                                sampling = sampling_format[1]
                            else:
                                sampling = None
                            for component in flow["components"]:
                                if component["name"] not in components:
                                    return test.FAIL("Video Flow component {} does not match the SDP sampling "
                                                     "for Sender {}".format(component["name"], sender["id"]))
                                if component["bit_depth"] != int(sdp_format_params["depth"]):
                                    return test.FAIL("Video Flow component {} does not match the SDP depth "
                                                     "for Sender {}".format(component["name"], sender["id"]))
                                sampling_error = False
                                if sampling == "4:4:4" or sampling is None or component["name"] in ["Y", "I"]:
                                    if component["width"] != flow["frame_width"] or \
                                            component["height"] != flow["frame_height"]:
                                        sampling_error = True
                                elif sampling == "4:2:2":
                                    if component["width"] != (flow["frame_width"] / 2) or \
                                            component["height"] != flow["frame_height"]:
                                        sampling_error = True
                                elif sampling == "4:2:0":
                                    if component["width"] != (flow["frame_width"] / 2) or \
                                            component["height"] != (flow["frame_height"] / 2):
                                        sampling_error = True
                                if sampling_error:
                                    return test.FAIL("Video Flow {} components do not match the expected "
                                                     "dimensions for Sender sampling {}"
                                                     .format(flow["id"], sampling))

            if found_video_jxsv:
                return test.PASS()

        except KeyError as ex:
            return test.FAIL("Expected attribute not found in IS-04 resource: {}".format(ex))

        return test.UNCLEAR("No JPEG XS Sender resources were found on the Node")

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
