# Copyright (C) 2024 Matrox Graphics Inc.
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
from ..IS05Utils import IS05Utils
from ..TestHelper import load_resolved_schema
from ..TestHelper import check_content_type
from ..TestResult import Test


NODE_API_KEY = "node"
CONNECTION_API_KEY = "connection"
SOURCE_REGISTER_KEY = "source-register"
FLOW_REGISTER_KEY = "flow-register"
SENDER_REGISTER_KEY = "sender-register"

media_type_constraint = "urn:x-nmos:cap:format:media_type"


def urn_without_namespace(s):
    match = re.search(r'^urn:[a-z0-9][a-z0-9-]+:(.*)', s)
    return match.group(1) if match else None


def get_key_value(obj, name):
    regex = re.compile(r'^urn:[a-z0-9][a-z0-9-]+:' + name + r'$')
    for key, value in obj.items():
        if regex.fullmatch(key):
            return value
    return obj[name]  # final try without a namespace


def has_key(obj, name):
    regex = re.compile(r'^urn:[a-z0-9][a-z0-9-]+:' + name + r'$')
    for key in obj.keys():
        if regex.fullmatch(key):
            return True
    return name in obj  # final try without a namespace


class BCP0070201Test(GenericTest):
    """
    Runs Node Tests covering NMOS With IPMX/USB
    """

    def __init__(self, apis, **kwargs):
        # Don't auto-test /transportfile as it is permitted to generate a 404 when master_enable is false
        omit_paths = [
            "/single/senders/{senderId}/transportfile",
            "/single/senders/{senderId}/staged",
            "/single/senders/{senderId}/active",
            "/single/senders/{senderId}/constraints",
            "/single/senders/{senderId}/transporttype",
            "/single/receivers/{receiverId}/staged",
            "/single/receivers/{receiverId}/active",
            "/single/receivers/{receiverId}/constraints",
            "/single/receivers/{receiverId}/transporttype",
        ]
        GenericTest.__init__(self, apis, omit_paths, **kwargs)
        self.node_url = self.apis[NODE_API_KEY]["url"]
        self.connection_url = self.apis[CONNECTION_API_KEY]["url"]
        self.is04_resources = {"senders": {}, "receivers": {}, "_requested": [], "sources": {}, "flows": {}}
        self.is05_resources = {
            "senders": [],
            "receivers": [],
            "_requested": [],
            "transport_types": {},
            "transport_files": {}}
        self.is04_utils = IS04Utils(self.node_url)
        self.is05_utils = IS05Utils(self.connection_url)
        self.test = Test("default")

    # Utility function from IS0502Test
    def get_is04_resources(self, resource_type):
        """Retrieve all Senders or Receivers from a Node API, keeping hold of the returned objects"""
        assert resource_type in ["senders", "receivers", "sources", "flows"]

        # Prevent this being executed twice in one test run
        if resource_type in self.is04_resources["_requested"]:
            return True, ""

        path_url = resource_type
        full_url = self.node_url + path_url
        valid, resources = self.do_request("GET", full_url)
        if not valid:
            return False, "Node API did not respond as expected: {}".format(resources)
        schema = self.get_schema(NODE_API_KEY, "GET", "/" + path_url, resources.status_code)
        valid, message = self.check_response(schema, "GET", resources)
        if not valid:
            raise NMOSTestException(self.test.FAIL(message))

        try:
            for resource in resources.json():
                self.is04_resources[resource_type][resource["id"]] = resource
            self.is04_resources["_requested"].append(resource_type)
        except json.JSONDecodeError:
            return False, "Non-JSON response returned from Node API"

        return True, ""

    def get_is05_partial_resources(self, resource_type):
        """Retrieve all Senders or Receivers from a Connection API, keeping hold of the returned IDs"""
        assert resource_type in ["senders", "receivers"]

        # Prevent this being executed twice in one test run
        if resource_type in self.is05_resources["_requested"]:
            return True, ""

        path_url = "single/" + resource_type
        full_url = self.connection_url + path_url
        valid, resources = self.do_request("GET", full_url)
        if not valid:
            return False, "Connection API did not respond as expected: {}".format(resources)

        schema = self.get_schema(CONNECTION_API_KEY, "GET", "/" + path_url, resources.status_code)
        valid, message = self.check_response(schema, "GET", resources)
        if not valid:
            raise NMOSTestException(self.test.FAIL(message))

        # The following call to is05_utils.get_transporttype does not validate against the IS-05 schemas,
        # which is good for allowing extended transport. The transporttype-response-schema.json schema is
        # broken as it does not allow additional transport, nor x-nmos ones, nor vendor specific ones.
        try:
            for resource in resources.json():
                resource_id = resource.rstrip("/")
                self.is05_resources[resource_type].append(resource_id)
                if self.is05_utils.compare_api_version(self.apis[CONNECTION_API_KEY]["version"], "v1.1") >= 0:
                    transport_type = self.is05_utils.get_transporttype(resource_id, resource_type.rstrip("s"))
                    self.is05_resources["transport_types"][resource_id] = transport_type
                else:
                    self.is05_resources["transport_types"][resource_id] = "urn:x-nmos:transport:rtp"
                if resource_type == "senders":
                    transport_file = self.is05_utils.get_transportfile(resource_id)
                    self.is05_resources["transport_files"][resource_id] = transport_file
            self.is05_resources["_requested"].append(resource_type)
        except json.JSONDecodeError:
            return False, "Non-JSON response returned from Node API"

        return True, ""

    def check_response_without_transport_params(self, schema, method, response):
        """Confirm that a given Requests response conforms to the expected schema and has any expected headers
        without considering the 'transport_params' attribute"""
        ctype_valid, ctype_message = check_content_type(response.headers)
        if not ctype_valid:
            return False, ctype_message

        cors_valid, cors_message = self.check_CORS(method, response.headers)
        if not cors_valid:
            return False, cors_message

        fields_to_ignore = ["transport_params"]

        data = response.json()

        filtered_data = {k: v for k, v in data.items() if k not in fields_to_ignore}

        filtered_data["transport_params"] = []

        try:
            self.validate_schema(filtered_data, schema)
        except ValidationError as e:
            return False, "Response schema validation error {}".format(e)
        except json.JSONDecodeError:
            return False, "Invalid JSON received"

        return True, ctype_message

    def getSchemaFromTransport(self, target, transport, type):

        if target != "sender" and target != "receiver":
            raise NMOSTestException("target of getSchemaFromTransport must be 'sender'' or 'receiver'")

        if type != "params" and type != "constraints":
            raise NMOSTestException("type of getSchemaFromTransport must be 'params'' or 'constraints'")

        reg_schema = None

        if urn_without_namespace(transport) in ('transport:usb',):
            base_reg_api = self.apis[CONNECTION_API_KEY]
            base_reg_path = base_reg_api["spec_path"] + "/APIs/schemas"
            reg_api = self.apis["usb-transport"]
            reg_path = reg_api["spec_path"] + "/APIs/schemas"
            reg_schema = load_resolved_schema(reg_path, "{}_transport_{}_usb.json".format(
                target, type), path_prefix=False, search_paths=[base_reg_path])

        elif urn_without_namespace(transport) in ('transport:rtp', 'transport:rtp.mcast', 'transport:rtp.ucast'):
            base_reg_api = self.apis[CONNECTION_API_KEY]
            base_reg_path = base_reg_api["spec_path"] + "/APIs/schemas"
            if type == "constraints":
                reg_schema = load_resolved_schema(
                    base_reg_path, "constraints-schema-rtp.json", path_prefix=False, search_paths=[])
            else:
                reg_schema = load_resolved_schema(
                    base_reg_path, "{}_transport_{}_rtp.json".format(target, type), path_prefix=False, search_paths=[])

        return reg_schema

    def test_01(self, test):
        """Check that version 1.3+ the Node API and version 1.1+ of the Connection API are available"""

        self.test = test

        # REFERENCE: A Node compliant with this specification MUST implement IS-04 v1.3 or higher
        # and IS-05 v1.1 or higher
        api = self.apis[NODE_API_KEY]
        if self.is04_utils.compare_api_version(api["version"], "v1.3") >= 0:
            valid, result = self.do_request("GET", self.node_url)
            if not valid:
                return test.FAIL("Node API did not respond as expected: {}".format(result))
        else:
            return test.FAIL("Node API must be running v1.3 or newer in order to run this test suite")

        api = self.apis[CONNECTION_API_KEY]
        if self.is04_utils.compare_api_version(api["version"], "v1.1") >= 0:
            valid, result = self.do_request("GET", self.node_url)
            if not valid:
                return test.FAIL("Connection API did not respond as expected: {}".format(result))
        else:
            return test.FAIL("Connection API must be running v1.1 or newer in order to run this test suite")

        return test.PASS()

    def test_02(self, test):
        """USB Flows have the required attributes"""

        self.test = test

        self.do_test_node_api_v1_3(test)

        reg_api = self.apis[FLOW_REGISTER_KEY]

        valid, result = self.get_is04_resources("flows")
        if not valid:
            return test.FAIL(result)

        reg_path = reg_api["spec_path"] + "/flow-attributes"
        reg_schema = load_resolved_schema(reg_path, "flow_data_register.json", path_prefix=False)

        try:
            flow_map = {flow["id"]: flow for flow in self.is04_resources["flows"].values()}

            usb_flows = [flow for flow in self.is04_resources["flows"].values()
                         if flow["format"] == "urn:x-nmos:format:data"
                         and flow["media_type"] == "application/usb"]

            for mux_flow in [flow for flow in self.is04_resources["flows"].values()
                             if flow["format"] == "urn:x-nmos:format:mux"]:
                for parent_flow in mux_flow["parents"]:
                    if flow_map[parent_flow]["format"] == "urn:x-nmos:format:data":
                        if flow_map[parent_flow]["media_type"] == "application/usb":
                            return test.FAIL("flow {}: USB data flow cannot be parent of a mux Flow".format(
                                parent_flow))

            for flow in usb_flows:
                # There are no required attributes
                # Check values against the schema
                try:
                    self.validate_schema(flow, reg_schema)
                except ValidationError as e:
                    return test.FAIL("flow {}: does not comply with the schema for Data Flow additional and "
                                     "extensible attributes defined in the NMOS Parameter Registers: "
                                     "{}".format(flow["id"], str(e)),
                                     "https://specs.amwa.tv/nmos-parameter-registers/branches/{}"
                                     "/flow-attributes/flow_data_register.html"
                                     .format(reg_api["spec_branch"]))

            if len(usb_flows) > 0:
                return test.PASS()

        except KeyError as ex:
            return test.FAIL("Expected attribute not found in IS-04 resource: {}".format(ex))

        return test.UNCLEAR("No USB Flow resources were found on the Node")

    def test_03(self, test):
        """USB Sources have the required attributes"""

        self.test = test

        self.do_test_node_api_v1_3(test)

        reg_api = self.apis[SOURCE_REGISTER_KEY]

        for resource_type in ["flows", "sources"]:
            valid, result = self.get_is04_resources(resource_type)
            if not valid:
                return test.FAIL(result)

        reg_path = reg_api["spec_path"] + "/source-attributes"
        reg_schema = load_resolved_schema(reg_path, "source_register.json", path_prefix=False)

        source_map = {source["id"]: source for source in self.is04_resources["sources"].values()}
        flow_map = {flow["id"]: flow for flow in self.is04_resources["flows"].values()}

        try:
            usb_flows = [flow for flow in self.is04_resources["flows"].values()
                         if flow["format"] == "urn:x-nmos:format:data"
                         and flow["media_type"] == "application/usb"]

            for mux_flow in [flow for flow in self.is04_resources["flows"].values()
                             if flow["format"] == "urn:x-nmos:format:mux"]:
                for parent_flow in mux_flow["parents"]:
                    if flow_map[parent_flow]["format"] == "urn:x-nmos:format:data":
                        if flow_map[parent_flow]["media_type"] == "application/usb":
                            return test.FAIL("flow {}: USB data flow cannot be parent of a mux Flow".format(
                                parent_flow))

            for flow in usb_flows:
                source = source_map[flow["source_id"]]

                if source["format"] != "urn:x-nmos:format:data":
                    return test.FAIL("source {}: MUST indicate format with value 'urn:x-nmos:format:data'"
                                     .format(source["id"]))

                # There are no required attributes
                # Check values against the schema
                try:
                    self.validate_schema(source, reg_schema)
                except ValidationError as e:
                    return test.FAIL("source {}: does not comply with the schema for Source additional and "
                                     "extensible attributes defined in the NMOS Parameter Registers: "
                                     "{}".format(source["id"], str(e)),
                                     "https://specs.amwa.tv/nmos-parameter-registers/branches/{}"
                                     "/source-attributes/source_register.html"
                                     .format(reg_api["spec_branch"]))

                # Check that the optional 'usb_devices' attribute has proper structure
                if has_key(source, "usb_devices"):
                    ok, msg = check_usb_devices_attribute(get_key_value(source, "usb_devices"))
                    if not ok:
                        return test.FAIL("source {}: invalid 'usb_devices' attribute, error {}".format(
                            source["id"], msg))

            if len(usb_flows) > 0:
                return test.PASS()

        except KeyError as ex:
            return test.FAIL("Expected attribute not found in IS-04 resource: {}".format(ex))

        return test.UNCLEAR("No USB Flow resources were found on the Node")

    def test_04(self, test):
        """USB Senders have the required attributes"""

        self.test = test

        self.do_test_node_api_v1_3(test)

        reg_api = self.apis[SENDER_REGISTER_KEY]

        for resource_type in ["senders", "flows"]:
            valid, result = self.get_is04_resources(resource_type)
            if not valid:
                return test.FAIL(result)

        flow_map = {flow["id"]: flow for flow in self.is04_resources["flows"].values()}

        reg_path = reg_api["spec_path"] + "/sender-attributes"
        reg_schema = load_resolved_schema(reg_path, "sender_register.json", path_prefix=False)

        try:
            usb_senders = [sender for sender in self.is04_resources["senders"].values() if sender["flow_id"]
                           and sender["flow_id"] in flow_map
                           and flow_map[sender["flow_id"]]["format"] == "urn:x-nmos:format:data"
                           and flow_map[sender["flow_id"]]["media_type"] == "application/usb"]

            warn_message = ""

            for sender in usb_senders:
                # check required attributes are present
                if "transport" not in sender:
                    return test.FAIL("sender {}: MUST indicate the 'transport' attribute."
                                     .format(sender["id"]))

                if urn_without_namespace(sender["transport"]) != "transport:usb":
                    return test.FAIL("sender {}: 'transport' attribute MUST indicate 'urn:*:transport:usb'"
                                     .format(sender["id"]))

                # check values of all additional attributes against the schema
                try:
                    self.validate_schema(sender, reg_schema)
                except ValidationError as e:
                    return test.FAIL("sender {}: does not comply with the schema for Sender additional and "
                                     "extensible attributes defined in the NMOS Parameter Registers: "
                                     "{}".format(sender["id"], str(e)),
                                     "https://specs.amwa.tv/nmos-parameter-registers/branches/{}"
                                     "/sender-attributes/sender_register.html"
                                     .format(reg_api["spec_branch"]))

                # Recommended to expose capabilities
                if "constraint_sets" in sender["caps"]:

                    # make sure sender capabilities are not confused with receivers ones
                    if "media_types" in sender["caps"] or "event_types" in sender["caps"]:
                        return test.FAIL("sender {}: capabilities MUST NOT have 'media_types' or 'event_types'"
                                         " attributes that are specific to receivers".format(sender["id"]))

                    # discard constraints sets that are known to not be USB
                    usb_constraint_sets = []

                    for constraint_set in sender["caps"]["constraint_sets"]:
                        if (media_type_constraint in constraint_set and "enum" in constraint_set[media_type_constraint]
                           and "application/usb" not in constraint_set[media_type_constraint]["enum"]):
                            continue

                        usb_constraint_sets.append(constraint_set)

                    for constraint_set in usb_constraint_sets:
                        constraint = "urn:x-nmos:cap:transport:usb_class"
                        if has_key(constraint_set, constraint):
                            ok, msg = check_usb_class_capability(get_key_value(constraint_set, constraint))
                            if not ok:
                                return test.FAIL("sender {}: invalid {} capabilities, error {}.".format(
                                    sender["id"], constraint, msg))
                        else:
                            warn_message += "|sender {}: SHOULD declare {} capabilities".format(
                                sender["id"], constraint)
                else:
                    warn_message += "|sender {}: SHOULD declare its capabilities".format(sender["id"])

            if len(usb_senders) > 0:
                if warn_message != "":
                    return test.WARNING(warn_message)
                else:
                    return test.PASS()

        except KeyError as ex:
            return test.FAIL("Expected attribute not found in IS-04 resource: {}".format(ex))

        return test.UNCLEAR("No USB Sender resources were found on the Node")

    def test_05(self, test):
        """USB Sender manifests have the required parameters"""

        self.test = test

        self.do_test_node_api_v1_3(test)

        for resource_type in ["senders", "flows"]:
            valid, result = self.get_is04_resources(resource_type)
            if not valid:
                return test.FAIL(result)

        flow_map = {flow["id"]: flow for flow in self.is04_resources["flows"].values()}

        try:
            usb_senders = [sender for sender in self.is04_resources["senders"].values() if sender["flow_id"]
                           and sender["flow_id"] in flow_map
                           and flow_map[sender["flow_id"]]["format"] == "urn:x-nmos:format:data"
                           and flow_map[sender["flow_id"]]["media_type"] == "application/usb"]

            access_error = False
            for sender in usb_senders:

                if "transport" not in sender:
                    return test.FAIL("sender {}: MUST indicate the 'transport' attribute."
                                     .format(sender["id"]))

                if urn_without_namespace(sender["transport"]) != "transport:usb":
                    return test.FAIL("sender {}: transport attribute MUST indicate the 'urn:*:transport:usb'"
                                     .format(sender["id"]))

                if "manifest_href" not in sender:
                    return test.FAIL("sender {}: MUST indicate the 'manifest_href' attribute."
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
                sdp_lines = [sdp_line.replace("\r", "") for sdp_line in sdp.split("\n")]

                found_media = 0
                found_setup = 0
                for sdp_line in sdp_lines:
                    media = re.search(r"^m=(.+) (.+) (.+) (.+)$", sdp_line)
                    if not media:
                        setup = re.search(r"^a=setup:passive$", sdp_line)
                        if setup:
                            found_setup += 1
                        continue
                    found_media += 1

                    if media.group(1) != "application":
                        return test.FAIL("sender {}: SDP transport file <media> MUST be 'application'".format(
                            sender["id"]))

                    try:
                        _ = int(media.group(2))
                    except ValueError:
                        return test.FAIL("sender {}: SDP transport file <port> MUST be an integer".format(sender["id"]))

                    if media.group(3) != "TCP":
                        return test.FAIL("sender {}: SDP transport file <proto> MUST be 'TCP'".format(sender["id"]))

                    if media.group(4) != "usb":
                        return test.FAIL("sender {}: SDP transport file <fmt> MUST be 'usb'".format(sender["id"]))

                if found_media == 0:
                    return test.FAIL("sender {}: SDP transport file is missing a media description line".format(
                        sender["id"]))

                if found_media > 2:
                    return test.FAIL("sender {}: at most two media description lines MUST"
                                     " be used with redundancy in the SDP transport file".format(sender["id"]))

                if found_setup != found_media:
                    return test.FAIL("sender {}: there MUST be as many 'a=setup:passive' lines as there are"
                                     " media description lines in the SDP transport file".format(sender["id"]))

            if access_error:
                return test.UNCLEAR("One or more of the tested Senders had null or empty 'manifest_href' or "
                                    "returned a 404 HTTP code. Please ensure all Senders are enabled and re-test.")

            if len(usb_senders) > 0:
                return test.PASS()

        except KeyError as ex:
            return test.FAIL("Expected attribute not found in IS-04 resource: {}".format(ex))

        return test.UNCLEAR("No USB Sender resources were found on the Node")

    def test_06(self, test):
        """USB Receivers have the required attributes"""

        self.test = test

        self.do_test_node_api_v1_3(test)

        valid, result = self.get_is04_resources("receivers")
        if not valid:
            return test.FAIL(result)

        media_type_constraint = "urn:x-nmos:cap:format:media_type"

        recommended_constraints = {
            "urn:x-nmos:cap:transport:usb_class": "USB class",
        }

        try:
            usb_receivers = [receiver for receiver in self.is04_resources["receivers"].values()
                             if receiver["format"] == "urn:x-nmos:format:data"
                             and "media_types" in receiver["caps"]
                             and "application/usb" in receiver["caps"]["media_types"]]

            # a mux receiver cannot have a constraint set with media_type set to application/usb
            for receiver in [receiver for receiver in self.is04_resources["receivers"].values()
                             if receiver["format"] == "urn:x-nmos:format:mux"]:
                if "constraint_sets" in receiver["caps"]:
                    for constraint_set in receiver["caps"]["constraint_sets"]:
                        if "urn:x-nmos:cap:format:media_type" in constraint_set:
                            if "enum" in constraint_set["urn:x-nmos:cap:format:media_type"]:
                                if "application/usb" in constraint_set["urn:x-nmos:cap:format:media_type"]["enum"]:
                                    return test.FAIL("receiver {}: of 'mux' format MUST NOT have constraint sets having"
                                                     " 'media_type' set to 'application/usb'.".format(receiver["id"]))

            warn_message = ""

            for receiver in usb_receivers:

                # check required attributes are present
                if "transport" not in receiver:
                    return test.FAIL("receiver {}: MUST indicate the 'transport' attribute."
                                     .format(receiver["id"]))

                if urn_without_namespace(receiver["transport"]) != "transport:usb":
                    return test.FAIL("receiver {}: 'transport' attribute MUST indicate 'urn:*:transport:usb'.".format(
                        receiver["id"]))

                if "urn:x-nmos:tag:grouphint/v1.0" in receiver["tags"]:
                    grouphint = receiver["tags"]["urn:x-nmos:tag:grouphint/v1.0"]
                    if len(grouphint) != 1:
                        return test.FAIL("receiver {}: 'urn:x-nmos:tag:grouphint/v1.0' tag array MUST contain"
                                         " a single value.".format(receiver["id"]))
                    if not check_grouphint(grouphint[0]):
                        return test.FAIL("receiver {}: 'urn:x-nmos:tag:grouphint/v1.0' tag array MUST"
                                         " use a 'DATA' role.".format(receiver["id"]))

                if "constraint_sets" not in receiver["caps"]:
                    return test.FAIL("receiver {}: MUST indicate constraints in accordance with BCP-004-01 using "
                                     "the 'caps' attribute 'constraint_sets'.".format(receiver["id"]))

                # exclude constraint sets for other media types
                usb_constraint_sets = [constraint_set for constraint_set in receiver["caps"]["constraint_sets"]
                                       if receiver["format"] == "urn:x-nmos:format:data"
                                       and (media_type_constraint not in constraint_set
                                       or ("enum" in constraint_set[media_type_constraint]
                                            and "application/usb" in constraint_set[media_type_constraint]["enum"]))]

                if len(usb_constraint_sets) == 0:
                    return test.FAIL("receiver {}: MUST indicate constraints in accordance with BCP-004-01 using "
                                     "the 'caps' attribute 'constraint_sets'.".format(receiver["id"]))

                # check recommended attributes are present
                for constraint_set in usb_constraint_sets:
                    for constraint, target in recommended_constraints.items():
                        if not has_key(constraint_set, constraint):
                            warn_message += "|receiver {}: SHOULD indicate the supported {} using the " \
                                "'{}' parameter constraint.".format(receiver["id"], target, constraint)

            if len(usb_receivers) > 0:
                if warn_message != "":
                    return test.WARNING(warn_message)
                else:
                    return test.PASS()

        except KeyError as ex:
            return test.FAIL("Expected attribute not found in IS-04 resource: {}".format(ex))

        return test.UNCLEAR("No USB Receiver resources were found on the Node")

    def test_07(self, test):
        """USB Receiver parameter constraints have valid values"""

        self.test = test

        self.do_test_node_api_v1_3(test)

        valid, result = self.get_is04_resources("receivers")
        if not valid:
            return test.FAIL(result)

        media_type_constraint = "urn:x-nmos:cap:format:media_type"

        try:
            usb_receivers = [receiver for receiver in self.is04_resources["receivers"].values()
                             if receiver["format"] == "urn:x-nmos:format:data"
                             and "media_types" in receiver["caps"]
                             and "application/usb" in receiver["caps"]["media_types"]]

            warn_message = ""

            for receiver in usb_receivers:

                # check required attributes are present
                if "constraint_sets" not in receiver["caps"]:
                    return test.FAIL("receiver {}: MUST indicate constraints in accordance with BCP-004-01 using "
                                     "the 'caps' attribute 'constraint_sets'.".format(receiver["id"]))

                # exclude constraint sets for other media types
                usb_constraint_sets = [constraint_set for constraint_set in receiver["caps"]["constraint_sets"]
                                       if receiver["format"] == "urn:x-nmos:format:data"
                                       and (media_type_constraint not in constraint_set
                                            or ("enum" in constraint_set[media_type_constraint]
                                                and "application/usb" in
                                                constraint_set[media_type_constraint]["enum"]))]

                if len(usb_constraint_sets) == 0:
                    return test.FAIL("receiver {}: MUST indicate constraints in accordance with BCP-004-01 using "
                                     "the 'caps' attribute 'constraint_sets'.".format(receiver["id"]))

                # check recommended attributes are present
                for constraint_set in usb_constraint_sets:
                    constraint = "urn:x-nmos:cap:transport:usb_class"
                    if has_key(constraint_set, constraint):
                        ok, msg = check_usb_class_capability(get_key_value(constraint_set, constraint))
                        if not ok:
                            return test.FAIL("receiver {}: invalid {} capabilities, error {}.".format(
                                receiver["id"], constraint, msg))
                    else:
                        warn_message += "|receiver {}: SHOULD declare {} capabilities.".format(
                            receiver["id"], constraint)
                        continue

            if len(usb_receivers) > 0:
                if warn_message != "":
                    return test.WARNING(warn_message)
                else:
                    return test.PASS()

        except KeyError as ex:
            return test.FAIL("Expected attribute not found in IS-04 resource: {}".format(ex))

        return test.UNCLEAR("No USB Receiver resources were found on the Node")

    def do_test_node_api_v1_3(self, test):
        """
        Precondition check of the API version.
        Raises an NMOSTestException when the Node API version is less than v1.3
        """
        api = self.apis[NODE_API_KEY]
        if self.is04_utils.compare_api_version(api["version"], "v1.3") < 0:
            raise NMOSTestException(test.NA("This test cannot be run against Node API below version v1.3."))

    def do_test_connection_api_v1_1(self, test):
        """
        Precondition check of the API version.
        Raises an NMOSTestException when the Connection API version is less than v1.1
        """
        api = self.apis[CONNECTION_API_KEY]
        if self.is04_utils.compare_api_version(api["version"], "v1.1") < 0:
            raise NMOSTestException(test.NA("This test cannot be run against Connection API below version v1.1."))

    def test_10(self, test):
        """ Check that senders staged and active transport parameters are valid"""

        self.test = test

        self.do_test_connection_api_v1_1(test)

        valid, result = self.get_is04_resources("senders")
        if not valid:
            return test.FAIL(result)

        valid, result = self.get_is05_partial_resources("senders")
        if not valid:
            return test.FAIL(result)

        usb_senders = [sender for sender in self.is04_resources["senders"].values()
                       if urn_without_namespace(sender["transport"]) in ('transport:usb',)]

        warn_message = ""

        for sender in usb_senders:

            reg_schema = self.getSchemaFromTransport("sender", sender["transport"], "params")

            if reg_schema is not None:
                url = "single/senders/{}/staged".format(sender["id"])
                valid, response = self.is05_utils.checkCleanRequest("GET", url)
                if valid:

                    schema = self.get_schema(CONNECTION_API_KEY, "GET",
                                             "/single/senders/{senderId}/staged", response.status_code)
                    valid, msg = self.check_response_without_transport_params(schema, "GET", response)
                    if not valid:
                        return test.FAIL("sender {}: request to staged transport parameters is not"
                                         " valid against schemas, error {}".format(sender["id"], msg))

                    staged = response.json()

                    if "transport_params" in staged and len(staged["transport_params"]) > 2:
                        return test.FAIL("sender {}: at most two staged transport parameters legs MUST"
                                         " be used with redundancy".format(sender["id"]))
                    try:
                        for params in staged["transport_params"]:
                            self.validate_schema(params, reg_schema)
                    except ValidationError as e:
                        return test.FAIL("sender {}: staged transport parameters do not match schema, error {}".format(
                            sender["id"], e))
                else:
                    return test.FAIL("sender {}: request to staged transport parameters is not valid".format(
                        sender["id"]))

                url = "single/senders/{}/active".format(sender["id"])
                valid, response = self.is05_utils.checkCleanRequest("GET", url)
                if valid:

                    schema = self.get_schema(CONNECTION_API_KEY, "GET",
                                             "/single/senders/{senderId}/active", response.status_code)
                    valid, msg = self.check_response_without_transport_params(schema, "GET", response)
                    if not valid:
                        return test.FAIL("sender {}: request to active transport parameters is not"
                                         " valid against schemas, error {}".format(sender["id"], msg))

                    active = response.json()

                    if "transport_params" in active and len(active["transport_params"]) > 2:
                        return test.FAIL("sender {}: at most two active transport parameters legs MUST"
                                         " be used with redundancy".format(sender["id"]))

                    try:
                        for params in active["transport_params"]:
                            self.validate_schema(params, reg_schema)
                    except ValidationError as e:
                        return test.FAIL("sender {}: active transport parameters do not match schema, error {}".format(
                            sender["id"], e))
                else:
                    return test.FAIL("sender {}: request to active transport parameters is not valid".format(
                        sender["id"]))
            else:
                warn_message += "|unknown transport {}".format(sender["transport"])

        if len(usb_senders) > 0:
            if warn_message != "":
                return test.WARNING(warn_message)
            else:
                return test.PASS()

        return test.UNCLEAR("No USB Sender resources were found on the Node")

    def test_11(self, test):
        """ Check that senders transport parameters constraints are valid"""

        self.test = test

        self.do_test_connection_api_v1_1(test)

        valid, result = self.get_is04_resources("senders")
        if not valid:
            return test.FAIL(result)

        valid, result = self.get_is05_partial_resources("senders")
        if not valid:
            return test.FAIL(result)

        usb_senders = [sender for sender in self.is04_resources["senders"].values()
                       if urn_without_namespace(sender["transport"]) in ('transport:usb',)]

        warn_message = ""

        for sender in usb_senders:

            reg_schema = self.getSchemaFromTransport("sender", sender["transport"], "constraints")

            if reg_schema is not None:
                url = "single/senders/{}/constraints".format(sender["id"])
                valid, response = self.is05_utils.checkCleanRequest("GET", url)
                if valid:

                    # There is nothing to validate in the response as there are only constraints
                    constraints = response.json()

                    if len(constraints) > 2:
                        return test.FAIL("sender {}: at most two constraints transport parameters legs MUST"
                                         " be used with redundancy".format(sender["id"]))
                    try:
                        for params in constraints:
                            self.validate_schema(params, reg_schema)
                    except ValidationError as e:
                        return test.FAIL("sender {}: transport parameters constraints do not"
                                         " match schema, error {}".format(sender["id"], e))
                else:
                    return test.FAIL("sender {}: request to transport parameters constraints is not valid".format(
                        sender["id"]))
            else:
                warn_message += "|unknown transport {}".format(sender["transport"])

            # Now check that the elements of the constraints, stages and active all match
            url = "single/senders/{}/staged".format(sender["id"])
            valid, response = self.is05_utils.checkCleanRequest("GET", url)
            if not valid:
                return test.FAIL("sender {}: cannot get staged parameters".format(sender["id"]))
            staged = response.json()

            url = "single/senders/{}/active".format(sender["id"])
            valid, response = self.is05_utils.checkCleanRequest("GET", url)
            if not valid:
                return test.FAIL("sender {}: cannot get active parameters".format(sender["id"]))
            active = response.json()

            if (len(constraints) != len(staged["transport_params"])
                    or len(constraints) != len(active["transport_params"])):
                return test.FAIL("sender {}: staged, active and constraints arrays are inconsistent".format(
                    sender["id"]))

            # across staged, active and constraints
            i = 0
            for c_params in constraints:
                s_params = staged["transport_params"][i]
                a_params = active["transport_params"][i]

                for c in c_params.keys():
                    if (c not in s_params.keys()) or (c not in a_params.keys()):
                        return test.FAIL("sender {}: staged, active and constraints parameters are inconsistent".format(
                            sender["id"]))

                i = i + 1

            # across legs
            for c_params in constraints:
                for c in c_params.keys():
                    if (c not in constraints[0].keys()):
                        return test.FAIL("sender {}: constraints parameters are inconsistent".format(sender["id"]))

            for s_params in staged["transport_params"]:
                for c in s_params.keys():
                    if (c not in staged["transport_params"][0].keys()):
                        return test.FAIL("sender {}: staged parameters are inconsistent".format(sender["id"]))

            for a_params in active["transport_params"]:
                for c in a_params.keys():
                    if (c not in active["transport_params"][0].keys()):
                        return test.FAIL("sender {}: active parameters are inconsistent".format(sender["id"]))

            # now check transport minimum requirements
            i = 0
            for c_params in constraints:

                if urn_without_namespace(sender["transport"]) in ("transport:usb",):
                    valid, msg = checkSenderTransportParametersUsb(
                        sender["transport"], c_params, staged["transport_params"][i], active["transport_params"][i])
                    if not valid:
                        return test.FAIL("sender {}: active transport parameters is not"
                                         " valid against minimum requirements, error {}".format(sender["id"], msg))

                i = i + 1

        if len(usb_senders) > 0:
            if warn_message != "":
                return test.WARNING(warn_message)
            else:
                return test.PASS()

        return test.UNCLEAR("No USB Sender resources were found on the Node")

    def test_12(self, test):
        """ Check that receivers staged and active transport parameters are valid"""

        self.test = test

        self.do_test_connection_api_v1_1(test)

        valid, result = self.get_is04_resources("receivers")
        if not valid:
            return test.FAIL(result)

        valid, result = self.get_is05_partial_resources("receivers")
        if not valid:
            return test.FAIL(result)

        usb_receivers = [receiver for receiver in self.is04_resources["receivers"].values()
                         if urn_without_namespace(receiver["transport"]) in ('transport:usb',)]

        warn_message = ""

        for receiver in usb_receivers:

            reg_schema = self.getSchemaFromTransport("receiver", receiver["transport"], "params")

            if reg_schema is not None:
                url = "single/receivers/{}/staged".format(receiver["id"])
                valid, response = self.is05_utils.checkCleanRequest("GET", url)
                if valid:

                    schema = self.get_schema(CONNECTION_API_KEY, "GET",
                                             "/single/receivers/{receiverId}/staged", response.status_code)
                    valid, msg = self.check_response_without_transport_params(schema, "GET", response)
                    if not valid:
                        return test.FAIL("receiver {}: request to staged transport parameters is not"
                                         " valid against schemas, error {}".format(receiver["id"], msg))

                    staged = response.json()

                    if "transport_params" in staged and len(staged["transport_params"]) > 2:
                        return test.FAIL("receiver {}: at most two staged transport parameters legs MUST"
                                         " be used with redundancy".format(receiver["id"]))
                    try:
                        for params in staged["transport_params"]:
                            self.validate_schema(params, reg_schema)
                    except ValidationError as e:
                        return test.FAIL("receiver {}: staged transport parameters do not"
                                         " match schema, error {}".format(receiver["id"], e))
                else:
                    return test.FAIL("receiver {}: request to staged transport parameters is not valid".format(
                        receiver["id"]))

                url = "single/receivers/{}/active".format(receiver["id"])
                valid, response = self.is05_utils.checkCleanRequest("GET", url)
                if valid:

                    schema = self.get_schema(CONNECTION_API_KEY, "GET",
                                             "/single/receivers/{receiverId}/active", response.status_code)
                    valid, msg = self.check_response_without_transport_params(schema, "GET", response)
                    if not valid:
                        return test.FAIL("receiver {}: request to active transport parameters is not"
                                         " valid against schemas, error {}".format(receiver["id"], msg))

                    active = response.json()

                    if "transport_params" in active and len(active["transport_params"]) > 2:
                        return test.FAIL("receiver {}: at most two active transport parameters legs MUST"
                                         " be used with redundancy".format(receiver["id"]))
                    try:
                        for params in active["transport_params"]:
                            self.validate_schema(params, reg_schema)
                    except ValidationError as e:
                        return test.FAIL("receiver {}: active transport parameters do not"
                                         " match schema, error {}".format(receiver["id"], e))
                else:
                    return test.FAIL("receiver {}: request to active transport parameters is not valid".format(
                        receiver["id"]))
            else:
                warn_message += "|unknown transport {}".format(receiver["transport"])

        if len(usb_receivers) > 0:
            if warn_message != "":
                return test.WARNING(warn_message)
            else:
                return test.PASS()

        return test.UNCLEAR("No USB Receiver resources were found on the Node")

    def test_13(self, test):
        """
        Check that receivers transport parameters constraints are valid and that per transport
        minimum requirement are met.
        """

        self.test = test

        self.do_test_connection_api_v1_1(test)

        valid, result = self.get_is04_resources("receivers")
        if not valid:
            return test.FAIL(result)

        valid, result = self.get_is05_partial_resources("receivers")
        if not valid:
            return test.FAIL(result)

        usb_receivers = [receiver for receiver in self.is04_resources["receivers"].values()
                         if urn_without_namespace(receiver["transport"]) in ('transport:usb',)]

        warn_message = ""

        for receiver in usb_receivers:

            reg_schema = self.getSchemaFromTransport("receiver", receiver["transport"], "constraints")

            if reg_schema is not None:
                url = "single/receivers/{}/constraints".format(receiver["id"])
                valid, response = self.is05_utils.checkCleanRequest("GET", url)
                if valid:

                    # There is nothing to validate in the response as there are only constraints
                    constraints = response.json()

                    if len(constraints) > 2:
                        return test.FAIL("receiver {}: at most two constraints transport parameters legs MUST"
                                         " be used with redundancy".format(receiver["id"]))
                    try:
                        for params in constraints:
                            self.validate_schema(params, reg_schema)
                    except ValidationError as e:
                        return test.FAIL("receiver {}: transport parameters constraints do not"
                                         " match schema, error {}".format(receiver["id"], e))
                else:
                    return test.FAIL("receiver {}: request to transport parameters constraints is not valid".format(
                        receiver["id"]))
            else:
                warn_message += "|unknown transport {}".format(receiver["transport"])

            # Now check that the elements of the constraints, stages and active all match
            url = "single/receivers/{}/staged".format(receiver["id"])
            valid, response = self.is05_utils.checkCleanRequest("GET", url)
            if not valid:
                return test.FAIL("receiver {}: cannot get staged parameters".format(receiver["id"]))
            staged = response.json()

            url = "single/receivers/{}/active".format(receiver["id"])
            valid, response = self.is05_utils.checkCleanRequest("GET", url)
            if not valid:
                return test.FAIL("receiver {}: cannot get active parameters".format(receiver["id"]))
            active = response.json()

            if (len(constraints) != len(staged["transport_params"])
                    or len(constraints) != len(active["transport_params"])):
                return test.FAIL("receiver {}: staged, active and constraints arrays are inconsistent".format(
                    receiver["id"]))

            # across staged, active and constraints
            i = 0
            for c_params in constraints:
                s_params = staged["transport_params"][i]
                a_params = active["transport_params"][i]

                # Use active as a reference
                for c in a_params.keys():
                    if (c not in c_params.keys()) or (c not in s_params.keys()):
                        return test.FAIL("receiver {}: staged, active and constraints parameters are inconsistent"
                                         .format(receiver["id"]))

                i = i + 1

            # across legs
            for c_params in constraints:
                for c in c_params.keys():
                    if (c not in constraints[0].keys()):
                        return test.FAIL("receiver {}: constraints parameters are inconsistent".format(receiver["id"]))

            for s_params in staged["transport_params"]:
                for c in s_params.keys():
                    if (c not in staged["transport_params"][0].keys()):
                        return test.FAIL("receiver {}: staged parameters are inconsistent".format(receiver["id"]))

            for a_params in active["transport_params"]:
                for c in a_params.keys():
                    if (c not in active["transport_params"][0].keys()):
                        return test.FAIL("receiver {}: active parameters are inconsistent".format(receiver["id"]))

            # now check transport minimum requirements
            i = 0
            for c_params in constraints:

                valid, msg = checkReceiverTransportParametersUsb(
                    receiver["transport"], c_params, staged["transport_params"][i], active["transport_params"][i])
                if not valid:
                    return test.FAIL("receiver {}: active transport parameters is not"
                                     " valid against minimum requirements, error {}".format(receiver["id"], msg))

                i = i + 1

        if len(usb_receivers) > 0:
            if warn_message != "":
                return test.WARNING(warn_message)
            else:
                return test.PASS()

        return test.UNCLEAR("No USB Receiver resources were found on the Node")


def check_grouphint(gh):

    halves = gh.split(":")

    if len(halves) != 2:
        return False
    if not halves[1].startswith("DATA"):
        return False

    return True


def check_usb_devices_attribute(usb_devices):

    if usb_devices is None:
        # Optional attribute
        return True, None

    if not isinstance(usb_devices, list):
        return False, "usb_devices must be an array."

    for idx, device in enumerate(usb_devices):
        if not isinstance(device, dict):
            return False, f"USB device at index {idx} must be a dictionary."

        # Validate ipmx_bus_id
        ipmx_bus_id = device.get("ipmx_bus_id")
        if not (isinstance(ipmx_bus_id, list) and len(ipmx_bus_id) == 64 and
                all(isinstance(i, int) and 0 <= i <= 255 for i in ipmx_bus_id)):
            return False, f"Invalid ipmx_bus_id at index {idx}: {ipmx_bus_id}"

        # Validate device_class
        device_class = device.get("class")
        if not (isinstance(device_class, list) and
                all(isinstance(c, int) and 0 <= c <= 255 for c in device_class)):
            return False, f"Invalid class at index {idx}: {device_class}"

        # Validate vendor
        vendor = device.get("vendor")
        if not (isinstance(vendor, int) and 0 <= vendor <= 0xFFFF):
            return False, f"Invalid vendor ID at index {idx}: {vendor}"

        # Validate product
        product = device.get("product")
        if not (isinstance(product, int) and 0 <= product <= 0xFFFF):
            return False, f"Invalid product ID at index {idx}: {product}"

        # Validate serial
        serial = device.get("serial")
        if not isinstance(serial, str):
            return False, f"Invalid serial at index {idx}: {serial}"

    return True, None


def check_usb_class_capability(usb_class_capability):

    if "enum" in usb_class_capability and not all(isinstance(c, int)
                                                  and 0 <= c <= 255 for c in usb_class_capability["enum"]):
        return False, "MUST be integers in the range 0 to 255"
    if "minimum" in usb_class_capability and (not isinstance(usb_class_capability["minimum"], int)
                                              or usb_class_capability["minimum"] < 0
                                              or usb_class_capability["minimum"] > 255):
        return False, "MUST be integers in the range 0 to 255"
    if "maximum" in usb_class_capability and (not isinstance(usb_class_capability["maximum"], int)
                                              or usb_class_capability["maximum"] < 0
                                              or usb_class_capability["maximum"] > 255):
        return False, "MUST be integers in the range 0 to 255"
    if "minimum" in usb_class_capability and "maximum" not in usb_class_capability:
        return False, "MUST be integers in the range 0 to 255"
    if "maximum" in usb_class_capability and "minimum" not in usb_class_capability:
        return False, "MUST be integers in the range 0 to 255"

    return True, ""


def checkSenderTransportParametersUsb(transport, constraints, staged, active):

    required = ('source_ip', 'source_port')

    for p in required:
        if p not in constraints.keys():
            return False, "required transport parameter {} not found in constraints".format(p)
        if p not in staged.keys():
            return False, "required transport parameter {} not found in staged".format(p)
        if p not in active.keys():
            return False, "required transport parameter {} not found in active".format(p)

    for p in constraints.keys():
        if not p.startswith("ext_") and p not in required:
            return False, "unknown transport parameter {} in constraints".format(p)
    for p in staged.keys():
        if not p.startswith("ext_") and p not in required:
            return False, "unknown transport parameter {} in staged".format(p)
    for p in active.keys():
        if not p.startswith("ext_") and p not in required:
            return False, "unknown transport parameter {} in active".format(p)

    return True, None


def checkReceiverTransportParametersUsb(transport, constraints, staged, active):

    required = ('source_ip', 'source_port', 'interface_ip')

    for p in required:
        if p not in constraints.keys():
            return False, "required transport parameter {} not found in constraints".format(p)
        if p not in staged.keys():
            return False, "required transport parameter {} not found in staged".format(p)
        if p not in active.keys():
            return False, "required transport parameter {} not found in active".format(p)

    for p in constraints.keys():
        if not p.startswith("ext_") and p not in required:
            return False, "unknown transport parameter {} in constraints".format(p)
    for p in staged.keys():
        if not p.startswith("ext_") and p not in required:
            return False, "unknown transport parameter {} in staged".format(p)
    for p in active.keys():
        if not p.startswith("ext_") and p not in required:
            return False, "unknown transport parameter {} in active".format(p)

    return True, None
