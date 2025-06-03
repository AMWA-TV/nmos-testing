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

# python3 nmos-test.py suite BCP-004-02 --host 127.0.0.1 127.0.0.1 --port 5058 5058 --version v1.3 v1.1

import json
import re
import os

from jsonschema import ValidationError

from ..GenericTest import GenericTest, NMOSTestException
from ..IS04Utils import IS04Utils
from ..IS05Utils import IS05Utils
from ..TestHelper import load_resolved_schema
from ..TestHelper import check_content_type
from ..TestResult import Test

from pathlib import Path

NODE_API_KEY = "node"
CONNECTION_API_KEY = "connection"
RECEIVER_CAPS_KEY = "receiver-caps"
SENDER_CAPS_KEY = "sender-caps"


# Generic capabilities from any namespace
def cap_without_namespace(s):
    match = re.search(r'^urn:[a-z0-9][a-z0-9-]+:cap:(.*)', s)
    return match.group(1) if match else None


class BCP0040201Test(GenericTest):
    """
    Runs Node Tests covering sender and receiver capabilities
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

    def test_01(self, test):
        """Check that version 1.3 or greater of the Node API is available"""

        self.test = test

        api = self.apis[NODE_API_KEY]
        if self.is04_utils.compare_api_version(api["version"], "v1.3") >= 0:
            valid, result = self.do_request("GET", self.node_url)
            if valid:
                return test.PASS()
            else:
                return test.FAIL("Node API did not respond as expected: {}".format(result))
        else:
            return test.FAIL("Node API must be running v1.3 or greater in order to run this test suite")

    def test_02(self, test):
        """Check Sender Capabilities"""

        self.test = test

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

        no_constraint_sets = True

        warning = ""

        if len(self.is04_resources["senders"].values()) == 0:
            return test.UNCLEAR("No Senders were found on the Node")

        for sender in self.is04_resources["senders"].values():

            # Make sure Senders do not use the Receiver's specific "media_types" attribute in their caps
            if "media_types" in sender["caps"]:
                warning += ("|Sender {} caps has an unnecessary 'media_types' attribute "
                            "that is not used with sender capabilities".format(sender["id"]))

            # Make sure Senders do not use the Receiver's specific "event_types" attribute in their caps
            if "event_types" in sender["caps"]:
                warning += ("|Sender {} caps has an unnecessary 'event_types' attribute "
                            "that is not used with sender capabilities".format(sender["id"]))

            if "constraint_sets" in sender["caps"]:

                no_constraint_sets = False

                try:
                    self.validate_schema(sender, schema)
                except ValidationError as e:
                    return test.FAIL("Sender {} does not comply with schema, error {}".format(sender["id"], e))

                try:
                    caps_version = sender["caps"]["version"]
                    core_version = sender["version"]

                    if self.is04_utils.compare_resource_version(caps_version, core_version) > 0:
                        return test.FAIL("Sender {} caps version is later than resource version".format(sender["id"]))

                except BaseException:
                    return test.FAIL("Sender {} caps do not have a version attribute".format(sender["id"]))

                has_label = None
                warn_label = False

                for constraint_set in sender["caps"]["constraint_sets"]:
                    try:
                        self.validate_schema(constraint_set, reg_schema)
                    except ValidationError as e:
                        return test.FAIL("Sender {} constraint_sets do not comply with schema, error {}".format(
                            sender["id"], e))

                    has_current_label = "urn:x-nmos:cap:meta:label" in constraint_set

                    # Ensure consistent labeling across all constraint_sets
                    if has_label is None:
                        has_label = has_current_label
                    elif has_label != has_current_label:
                        warn_label = True

                    has_pattern_attribute = False
                    for param_constraint in constraint_set:

                        try:
                            # enumeration do not allow empty arrays by schema, disallow empty range by test
                            if not cap_without_namespace(param_constraint).startswith("meta:"):
                                has_pattern_attribute = True
                                if "minimum" in param_constraint and "maximum" in param_constraint:
                                    if compare_min_larger_than_max(param_constraint):
                                        warning += "|" + \
                                            "Sender {} parameter constraint {} has an invalid empty range".format(
                                                sender["id"], param_constraint)

                            # parameter constraints in the x-nmos namespace should be listed in the
                            # Capabilities register
                            if param_constraint.startswith(
                                    "urn:x-nmos:") and param_constraint not in reg_schema_obj["properties"]:
                                warning += ("|Sender {} parameter constraint {}"
                                            " is not registered ".format(sender["id"], param_constraint))

                        except BaseException:
                            return test.FAIL(
                                "Sender {} has an invalid parameter constraint {}".format(
                                    sender["id"], param_constraint))

                    if not has_pattern_attribute:
                        return test.FAIL(
                            "Sender {} has an illegal constraint set without any parameter attribute".format(
                                sender["id"]))

                if warn_label:
                    warning += ("|Sender {} constraint_sets should either 'urn:x-nmos:cap:meta:label' "
                                "for all constraint sets or none".format(sender["id"]))

        if no_constraint_sets:
            return test.OPTIONAL("No BCP-004-02 'constraint_sets' were identified in Sender caps")

        if warning != "":
            return test.WARNING(warning)
        else:
            return test.PASS()


def compare_min_larger_than_max(param_constraint):

    min_val = param_constraint["minimum"]
    max_val = param_constraint["maximum"]

    if isinstance(min_val, int) and isinstance(max_val, int):
        return min_val > max_val
    elif isinstance(min_val, float) and isinstance(max_val, float):
        return min_val > max_val
    elif isinstance(min_val, (int, float)) and isinstance(max_val, (int, float)):
        return float(min_val) > float(max_val)
    elif isinstance(min_val, dict) and isinstance(max_val, dict):
        min_num = min_val["numerator"]
        max_num = max_val["numerator"]
        min_den = min_val.get("denominator", 1)
        max_den = max_val.get("denominator", 1)
        return (min_num * max_den) > (max_num * min_den)

    return False
