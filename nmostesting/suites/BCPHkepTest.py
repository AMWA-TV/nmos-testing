# Copyright (C) 2025 Matrox Graphics Inc.
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

# python3 nmos-test.py suite BCP-HKEP --host 127.0.0.1 127.0.0.1 --port 5058 5058 --version v1.3 v1.1

import json
import re
import os

from jsonschema import ValidationError

from ..GenericTest import GenericTest, NMOSTestException
from ..IS04Utils import IS04Utils
from ..IS05Utils import IS05Utils
from ..TestHelper import load_resolved_schema
from ..TestHelper import check_content_type

from pathlib import Path

NODE_API_KEY = "node"
CONNECTION_API_KEY = "connection"
RECEIVER_CAPS_KEY = "receiver-caps"
SENDER_CAPS_KEY = "sender-caps"

# Generic capabilities from any namespace


def cap_without_namespace(s):
    match = re.search(r'^urn:[a-z0-9][a-z0-9-]+:cap:(.*)', s)
    return match.group(1) if match else None


def get_key_value(obj, name):
    regex = re.compile(r'^urn:[a-z0-9][a-z0-9-]+:' + name)
    for key, value in obj.items():
        if regex.fullmatch(key):
            return value
    return obj[name]  # final try without a namespace


def has_key(obj, name):
    regex = re.compile(r'^urn:[a-z0-9][a-z0-9-]+:' + name)
    for key in obj.keys():
        if regex.fullmatch(key):
            return True
    return name in obj  # final try without a namespace


class BCPHkepTest(GenericTest):
    """
    Runs Node Tests covering sender and receiver with IPMX/HKEP
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
        self.is05_resources = {"senders": [], "receivers": [],
                               "_requested": [], "transport_types": {}, "transport_files": {}}
        self.is04_utils = IS04Utils(self.node_url)
        self.is05_utils = IS05Utils(self.connection_url)

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
            raise NMOSTestException(message)

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
            raise NMOSTestException(message)

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
        """Confirm that a given Requests response conforms to the expected schema and has any expected headers without
          considering the 'transport_params' attribute"""
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

    def test_01(self, test):
        """Check that version 1.3+ the Node API and version 1.1+ of the Connection API are available"""

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
        """Check HKEP Senders"""

        api = self.apis[SENDER_CAPS_KEY]

        reg_api = self.apis["caps-register"]
        reg_path = reg_api["spec_path"] + "/capabilities"

        valid, result = self.get_is04_resources("senders")
        if not valid:
            return test.FAIL(result)

        schema = load_resolved_schema(api["spec_path"], "sender_constraint_sets.json")

        reg_schema_file = str(Path(os.path.abspath(reg_path)) / "constraint_set.json")
        with open(reg_schema_file, "r") as f:
            reg_schema_obj = json.load(f)
        reg_schema = load_resolved_schema(api["spec_path"], schema_obj=reg_schema_obj)

        no_hkep_senders = True
        access_error = False

        warning = ""

        if len(self.is04_resources["senders"].values()) == 0:
            return test.UNCLEAR("No Senders were found on the Node")

        for sender in self.is04_resources["senders"].values():

            # Only test if the sender declare being compliant with BCP-???-??? (IPMX/HKEP)
            if has_key(sender, "hkep"):

                no_hkep_senders = False

                # this if the state of the sender
                hkep = get_key_value(sender, "hkep")

                # These are the states EXPLICITLY allowed by the sender's capabilities.
                only_allow_true = None
                only_allow_false = None

                if "constraint_sets" in sender["caps"]:

                    try:
                        self.validate_schema(sender, schema)
                    except ValidationError as e:
                        return test.FAIL("Sender {} does not comply with schema, error {}".format(sender["id"], e))

                    for constraint_set in sender["caps"]["constraint_sets"]:

                        try:
                            self.validate_schema(constraint_set, reg_schema)
                        except ValidationError as e:
                            return test.FAIL(
                                "Sender {} constraint_sets do not comply with schema, error {}".format(
                                    sender["id"], e))

                        # Ignore disabled constraint sets
                        if ("urn:x-nmos:cap:meta:enabled" in constraint_set and
                                not constraint_set["urn:x-nmos:cap:meta:enabled"]):
                            continue

                        # Explicit declarations only
                        if has_key(constraint_set, "cap:transport:hkep"):
                            param_constraint = get_key_value(constraint_set, "cap:transport:hkep")
                            if "enum" in param_constraint:
                                if (True in param_constraint["enum"]) and (False not in param_constraint["enum"]):
                                    only_allow_false = False
                                    if only_allow_true is None:
                                        only_allow_true = True
                                if (False in param_constraint["enum"]) and (True not in param_constraint["enum"]):
                                    only_allow_true = False
                                    if only_allow_false is None:
                                        only_allow_false = True
                            else:
                                only_allow_true = False
                                only_allow_false = False

                # Check that the sender state does not contradict its explicit capabilities
                if only_allow_true is not None:
                    if only_allow_true and not hkep:
                        return test.FAIL(
                            "Sender {} has an invalid 'hkep' state {} "
                            "which is not allowed by the Sender's capabilities only allowing 'true'".format(
                                sender["id"], hkep))

                if only_allow_false is not None:
                    if only_allow_false and hkep:
                        return test.FAIL(
                            "Sender {} has an invalid 'hkep' state {} "
                            "which is not allowed by the Sender's capabilities only allowing 'false'".format(
                                sender["id"], hkep))

                # Check SDP transport file
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
                    return test.FAIL("Sender {} unexpected response from manifest_href '{}': {}"
                                     .format(sender["id"], href, manifest_href_response))

                sdp = manifest_href_response.text
                sdp_lines = [sdp_line.replace("\r", "") for sdp_line in sdp.split("\n")]

                found_hkep = False
                for sdp_line in sdp_lines:
                    hkep_attribute = re.search(r"^a=hkep:(.+)$", sdp_line)
                    if hkep_attribute:
                        found_hkep = True

                # SDP transport file must match with capabilities
                if only_allow_true is not None:
                    if only_allow_true and not found_hkep:
                        return test.FAIL(
                            "Sender {} has an invalid SDP transport file without an 'hkep' attribute "
                            "which is not allowed by the Sender's capabilities only allowing 'true'".format(
                                sender["id"]))

                if only_allow_false is not None:
                    if only_allow_false and found_hkep:
                        return test.FAIL(
                            "Sender {} has an invalid SDP transport file with an 'hkep' attribute "
                            "which is not allowed by the Sender's capabilities only allowing 'false'".format(
                                sender["id"]))

                # sender state must match with SDP transport file
                if hkep != found_hkep:
                    return test.FAIL(
                        "Sender {} has an invalid SDP transport file {} an 'hkep' attribute "
                        "which does not match with the Sender hkep attribute {}".format(
                            sender["id"], "with" if found_hkep else "without", hkep))

        if access_error:
            return test.UNCLEAR("One or more of the tested Senders had null or empty 'manifest_href' or "
                                "returned a 404 HTTP code. Please ensure all Senders are enabled and re-test.")
        if no_hkep_senders:
            return test.OPTIONAL("No BCP-???-?? (IPMX/HKEP) Sender found")

        if warning != "":
            return test.WARNING(warning)
        else:
            return test.PASS()

    def test_03(self, test):
        """Check HKEP Receivers"""

        api = self.apis[RECEIVER_CAPS_KEY]

        reg_api = self.apis["caps-register"]
        reg_path = reg_api["spec_path"] + "/capabilities"

        valid, result = self.get_is04_resources("receivers")
        if not valid:
            return test.FAIL(result)

        schema = load_resolved_schema(api["spec_path"], "receiver_constraint_sets.json")

        reg_schema_file = str(Path(os.path.abspath(reg_path)) / "constraint_set.json")
        with open(reg_schema_file, "r") as f:
            reg_schema_obj = json.load(f)
        reg_schema = load_resolved_schema(api["spec_path"], schema_obj=reg_schema_obj)

        no_hkep_receivers = True
        no_constraint_sets = True

        warning = ""

        if len(self.is04_resources["receivers"].values()) == 0:
            return test.UNCLEAR("No Receivers were found on the Node")

        for receiver in self.is04_resources["receivers"].values():

            if "constraint_sets" in receiver["caps"]:

                no_constraint_sets = False

                try:
                    self.validate_schema(receiver, schema)
                except ValidationError as e:
                    return test.FAIL("Receiver {} does not comply with schema, error {}".format(receiver["id"], e))

                for constraint_set in receiver["caps"]["constraint_sets"]:

                    try:
                        self.validate_schema(constraint_set, reg_schema)
                    except ValidationError as e:
                        return test.FAIL(
                            "Receiver {} constraint_sets do not comply with schema, error {}".format(
                                receiver["id"], e))

                    # Ignore disabled constraint sets
                    if ("urn:x-nmos:cap:meta:enabled" in constraint_set and
                            not constraint_set["urn:x-nmos:cap:meta:enabled"]):
                        continue

                    # Explicit declarations only
                    if has_key(constraint_set, "cap:transport:hkep"):
                        no_hkep_receivers = False

        if no_constraint_sets:
            return test.OPTIONAL("No Receiver describing BCP-004-01 Capabilities found")

        if no_hkep_receivers:
            return test.OPTIONAL("No BCP-???-?? (IPMX/HKEP) Receiver found")

        if warning != "":
            return test.WARNING(warning)
        else:
            return test.PASS()
