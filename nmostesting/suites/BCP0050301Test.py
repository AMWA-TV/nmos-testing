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
import os

from jsonschema import ValidationError
from pathlib import Path

from ..GenericTest import GenericTest, NMOSTestException
from ..IS04Utils import IS04Utils
from ..IS05Utils import IS05Utils
from ..TestHelper import load_resolved_schema
from ..TestHelper import check_content_type

NODE_API_KEY = "node"
CONNECTION_API_KEY = "connection"
RECEIVER_CAPS_KEY = "receiver-caps"
SENDER_CAPS_KEY = "sender-caps"

privacy_protocol = 'ext_privacy_protocol'
privacy_mode = 'ext_privacy_mode'
privacy_iv = 'ext_privacy_iv'
privacy_key_generator = 'ext_privacy_key_generator'
privacy_key_version = 'ext_privacy_key_version'
privacy_key_id = 'ext_privacy_key_id'
privacy_ecdh_sender_public_key = 'ext_privacy_ecdh_sender_public_key'
privacy_ecdh_receiver_public_key = 'ext_privacy_ecdh_receiver_public_key'
privacy_ecdh_curve = 'ext_privacy_ecdh_curve'

sdp_privacy_protocol = 'protocol'
sdp_privacy_mode = 'mode'
sdp_privacy_iv = 'iv'
sdp_privacy_key_generator = 'key_generator'
sdp_privacy_key_version = 'key_version'
sdp_privacy_key_id = 'key_id'

privacy_capability = "cap:transport:privacy"


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


class BCP0050301Test(GenericTest):
    """
    Runs Node Tests covering Privacy Encryption Protocol (PEP)
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
        self.is05_resources = {"senders": [], "receivers": [], "_requested": [],
                               "transport_types": {}, "transport_files": {}}
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
        # which is good fow allowing extended transport. The transporttype-response-schema.json schema is
        # broken as it does not allow additional transport, nor x-nmos ones, nor vendor spcecific ones.
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
        """Check that version 1.3+ the Node API and version 1.1+ of the Connection API are available"""

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
        """ Check that senders transport parameters having 'ext_privacy' parameters are valid """

        reg_api = self.apis["ext-transport-parameters-register"]
        reg_path = reg_api["spec_path"] + "/transport-parameters"

        valid, result = self.get_is04_resources("senders")
        if not valid:
            return test.FAIL(result)

        valid, result = self.get_is05_partial_resources("senders")
        if not valid:
            return test.FAIL(result)

        warning = ""
        all_active = True  # proven otherwise

        iv = dict()

        if len(self.is04_resources["senders"].values()) == 0:
            return test.UNCLEAR("No Senders were found on the Node")

        no_privacy_senders = True

        for sender in self.is04_resources["senders"].values():

            # REFERENCE: A Sender compliant with this specification MUST provide a privacy Sender attribute to
            # indicate that privacy encryption and the PEP protocol are used by the Sender.
            #
            # being compliant with BCP-005-03 (IPMX/PEP).
            if not has_key(sender, "privacy"):
                continue

            no_privacy_senders = False

            reg_schema = load_resolved_schema(reg_path, "ext-constraints-schema.json", path_prefix=False)

            if reg_schema is not None:
                url = "single/senders/{}/constraints".format(sender["id"])
                valid, response = self.is05_utils.checkCleanRequest("GET", url)
                if valid:

                    # There is nothing to validate in the response as there are only constraints
                    constraints = response.json()

                    try:
                        for params in constraints:
                            params = {k: v for k, v in params.items() if k.startswith("ext_privacy")}
                            self.validate_schema(params, reg_schema)
                    except ValidationError as e:
                        return test.FAIL("sender {} : transport parameters constraints do not match schema, error {}"
                                         .format(sender["id"], e))
                else:
                    return test.FAIL("sender {} : request to transport parameters constraints is not valid"
                                     .format(sender["id"]))
            else:
                test.ERROR("Cannot load ext-constraints-schema.json")

            # Now check that the elements of the constraints, stages and active all match
            reg_schema = load_resolved_schema(reg_path, "sender_transport_params_ext_register.json", path_prefix=False)
            if reg_schema is None:
                test.ERROR("Cannot load sender_transport_params_ext_register.json")

            url = "single/senders/{}/staged".format(sender["id"])
            valid, response = self.is05_utils.checkCleanRequest("GET", url)
            if not valid:
                return test.FAIL("sender {} : cannot get sender staged parameters".format(sender["id"]))
            staged = response.json()

            try:
                for params in staged['transport_params']:
                    params = {k: v for k, v in params.items() if k.startswith("ext_privacy")}
                    self.validate_schema(params, reg_schema)
            except ValidationError as e:
                return test.FAIL("sender {} : staged transport parameters do not match schema, error {}"
                                 .format(sender["id"], e))

            url = "single/senders/{}/active".format(sender["id"])
            valid, response = self.is05_utils.checkCleanRequest("GET", url)
            if not valid:
                return test.FAIL("sender {} : cannot get sender active parameters".format(sender["id"]))
            active = response.json()

            try:
                for params in active['transport_params']:
                    params = {k: v for k, v in params.items() if k.startswith("ext_privacy")}
                    self.validate_schema(params, reg_schema)
            except ValidationError as e:
                return test.FAIL("sender {} : active transport parameters do not match schema, error {}"
                                 .format(sender["id"], e))

            if (len(constraints) != len(staged["transport_params"]) or
                    len(constraints) != len(active["transport_params"])):
                return test.FAIL("sender {} : staged, active and constraints arrays are inconsistent"
                                 .format(sender["id"]))

            # across staged, active and constraints
            i = 0
            for c_params in constraints:
                s_params = staged["transport_params"][i]
                a_params = active["transport_params"][i]

                for c in c_params.keys():
                    if (c not in s_params.keys()) or (c not in a_params.keys()):
                        return test.FAIL("sender {} : staged, active and constraints parameters are inconsistent"
                                         .format(sender["id"]))

                i = i + 1

            # across legs
            for c_params in constraints:
                for c in c_params.keys():
                    if (c not in constraints[0].keys()):
                        return test.FAIL("sender {} : constraints parameters are inconsistent".format(sender["id"]))

            for s_params in staged["transport_params"]:
                for c in s_params.keys():
                    if (c not in staged["transport_params"][0].keys()):
                        return test.FAIL("sender {} : staged parameters are inconsistent".format(sender["id"]))

            for a_params in active["transport_params"]:
                for c in a_params.keys():
                    if (c not in active["transport_params"][0].keys()):
                        return test.FAIL("sender {} : active parameters are inconsistent".format(sender["id"]))

            # now check transport minimum requirements
            i = 0
            for c_params in constraints:

                valid, msg = checkSenderTransportParametersPEP(
                    sender["transport"],
                    c_params, staged["transport_params"][i],
                    active["transport_params"][i])
                if not valid:
                    return test.FAIL("sender {} : active transport parameters is not valid against minimum requirements"
                                     ", error {}".format(sender["id"], msg))

                valid, generic, elliptic, msg = self.hasSenderTransportParametersPEP(
                    sender["transport"],
                    c_params,
                    staged["transport_params"][i],
                    active["transport_params"][i])
                if not valid:
                    return test.FAIL("sender {} : active transport parameters is not valid against minimum requirements"
                                     ", error {}".format(sender["id"], msg))

                if generic:

                    ok, msg = self.check_generic_attribute_values(
                        True,
                        sender,
                        c_params,
                        staged["transport_params"][i],
                        active["transport_params"][i],
                        elliptic,
                        active["master_enable"])
                    if not ok:
                        return test.FAIL("sender {} : invalid privacy encryption attribute value, error {}"
                                         .format(sender["id"], msg))
                    if msg != "":
                        warning += "|" + msg

                    null_mode = (privacy_mode in constraints[i] and
                                 "enum" in constraints[i][privacy_mode] and
                                 "NULL" in constraints[i][privacy_mode]["enum"])

                    # check sender capability if present
                    if "constraint_sets" in sender["caps"]:
                        for constraint_set in sender["caps"]["constraint_sets"]:
                            if has_key(constraint_set, privacy_capability):
                                capability = get_key_value(constraint_set, privacy_capability)
                                if "enum" in capability:
                                    enums = capability["enum"]
                                    if len(enums) != 1:
                                        return test.FAIL("sender {} : invalid privacy capabilities {}"
                                                         .format(sender["id"], capability))
                                    for value in enums:
                                        if not isinstance(value, bool):
                                            return test.FAIL("sender {} : privacy capability must be of type bool"
                                                             .format(sender["id"]))
                                        if value and null_mode is True:
                                            return test.FAIL("sender {} : privacy capability must match "
                                                             "privacy transport parameters".format(sender["id"]))
                                        if not value and null_mode is False:
                                            return test.FAIL("sender {} : privacy capability must match "
                                                             "privacy transport parameters".format(sender["id"]))

                    # REFERENCE: If the Sender's privacy attribute is false, the ext_privacy_protocol and
                    # ext_privacy_mode transport parameters MUST be "NULL". If the Sender's privacy attribute
                    # is true, the ext_privacy_protocol and ext_privacy_mode transport parameters MUST NOT be
                    # "NULL".
                    if get_key_value(sender, "privacy") == null_mode:
                        return test.FAIL("sender {} : privacy attribute must match "
                                         "privacy transport parameters".format(sender["id"]))

                    # check uniqueness of iv among all the senders (not matter what PSK is used)
                    params = active["transport_params"][i]

                    if params[privacy_iv] in iv:
                        warning += ("|" + "sender {} : invalid duplicated iv attribute {}").format(
                            sender["id"], params[privacy_iv])
                    else:
                        iv[params[privacy_iv]] = None  # must be unique among all senders
                else:

                    # REFERENCE: For transport protocols using an SDP transport file: a Sender MUST communicate
                    # privacy encryption parameters in the SDP transport file associated with a privacy-encrypted
                    # stream, and MUST also communicate these parameters using the extended NMOS transport parameters.
                    # For transport protocols that do not use an SDP transport file: a Sender or Receiver MUST
                    # communicate the privacy encryption parameters using the extended NMOS transport parameters.
                    #
                    # REFERENCE: A Sender implementing privacy encryption and the PEP protocol MUST provide IS-05
                    # ext_privacy_* extended transport parameters and associated constraints that specify the extent
                    # of support for the features defined in TR-10-13.
                    return test.FAIL("sender {} : missing privacy transport parameters".format(sender["id"]))

                i = i + 1

            # attributes must match across legs
            ok, msg = self.check_across_legs(True, sender, constraints,
                                             staged["transport_params"], active["transport_params"], elliptic)
            if not ok:
                return test.FAIL("sender {} : invalid privacy capability, error {}".format(sender["id"], msg))
            if msg != "":
                warning += "|" + msg

            # We do require an active sender to get final parameters and to know if there is
            # really no SDP transport file
            if active["master_enable"]:

                # in an NMOS environment the SDP privacy attribute is required if an
                # SDP transport file is used check SDP transport file matching transport
                # parameters, check RTP Extension header declaration
                if "manifest_href" in sender and sender["manifest_href"] is not None:

                    href = sender["manifest_href"]

                    manifest_href_valid, manifest_href_response = self.do_request("GET", href)
                    if not manifest_href_valid or (manifest_href_response.status_code != 200 and
                                                   manifest_href_response.status_code != 404):
                        return test.FAIL("sender {} : unexpected response from manifest_href '{}': {}"
                                         .format(sender["id"], href, manifest_href_response))
                    elif manifest_href_valid and manifest_href_response.status_code == 404:
                        return test.UNCLEAR("sender {} : one or more of the tested Senders had returned a 404 HTTP"
                                            "code. Please ensure all Senders are enabled and re-test."
                                            .format(sender["id"]))
                    else:
                        sdp_lines = [sdp_line.replace("\r", "") for sdp_line in manifest_href_response.text.split("\n")]

                        ok, msg = self.check_privacy_attribute(True, sender, len(constraints),
                                                               constraints[0], active["transport_params"][0], sdp_lines)
                        if not ok:
                            return test.FAIL("sender {} : invalid privacy capability, error {}"
                                             .format(sender["id"], msg))
                        if msg != "":
                            warning += "|" + msg
            else:
                all_active = False

        if not all_active:
            return test.UNCLEAR("One or more of the tested Senders has master_enable set to false."
                                " Please ensure all Senders are enabled and re-test.")

        if no_privacy_senders:
            return test.OPTIONAL("No BCP-005-03 (IPMX/PEP) Sender found")

        if warning != "":
            return test.WARNING(warning)
        else:
            return test.PASS()

    def test_03(self, test):
        """ Check that senders transport parameters having 'ext_privacy' parameters are properly validated
            on activation against constraints """

        reg_api = self.apis["ext-transport-parameters-register"]
        reg_path = reg_api["spec_path"] + "/transport-parameters"

        valid, result = self.get_is04_resources("senders")
        if not valid:
            return test.FAIL(result)

        valid, result = self.get_is05_partial_resources("senders")
        if not valid:
            return test.FAIL(result)

        warning = ""

        if len(self.is04_resources["senders"].values()) == 0:
            return test.UNCLEAR("No Senders were found on the Node")

        no_privacy_senders = True

        for sender in self.is04_resources["senders"].values():

            # REFERENCE: A Sender compliant with this specification MUST provide a privacy Sender attribute to
            # indicate that privacy encryption and the PEP protocol are used by the Sender.
            #
            # being compliant with BCP-005-03 (IPMX/PEP).
            if not has_key(sender, "privacy"):
                continue

            no_privacy_senders = False

            reg_schema = load_resolved_schema(reg_path, "ext-constraints-schema.json", path_prefix=False)

            if reg_schema is not None:
                url = "single/senders/{}/constraints".format(sender["id"])
                valid, response = self.is05_utils.checkCleanRequest("GET", url)
                if valid:

                    # There is nothing to validate in the response as there are only constraints
                    constraints = response.json()

                    try:
                        for params in constraints:
                            params = {k: v for k, v in params.items() if k.startswith("ext_privacy")}
                            self.validate_schema(params, reg_schema)
                    except ValidationError as e:
                        return test.FAIL("sender {} : transport parameters constraints do not match schema, error {}"
                                         .format(sender["id"], e))
                else:
                    return test.FAIL("sender {} : request to transport parameters constraints is not valid"
                                     .format(sender["id"]))
            else:
                test.ERROR("Cannot load ext-constraints-schema.json")

            # Now check that the elements of the constraints, stages and active all match
            reg_schema = load_resolved_schema(reg_path, "sender_transport_params_ext_register.json", path_prefix=False)
            if reg_schema is None:
                test.ERROR("Cannot load sender_transport_params_ext_register.json")

            url = "single/senders/{}/staged".format(sender["id"])
            valid, response = self.is05_utils.checkCleanRequest("GET", url)
            if not valid:
                return test.FAIL("sender {} : cannot get sender staged parameters".format(sender["id"]))
            staged = response.json()

            try:
                for params in staged['transport_params']:
                    params = {k: v for k, v in params.items() if k.startswith("ext_privacy")}
                    self.validate_schema(params, reg_schema)
            except ValidationError as e:
                return test.FAIL("sender {} : staged transport parameters do not match schema, error {}"
                                 .format(sender["id"], e))

            url = "single/senders/{}/active".format(sender["id"])
            valid, response = self.is05_utils.checkCleanRequest("GET", url)
            if not valid:
                return test.FAIL("sender {} : cannot get sender active parameters".format(sender["id"]))
            active = response.json()

            try:
                for params in active['transport_params']:
                    params = {k: v for k, v in params.items() if k.startswith("ext_privacy")}
                    self.validate_schema(params, reg_schema)
            except ValidationError as e:
                return test.FAIL("sender {} : active transport parameters do not match schema, error {}"
                                 .format(sender["id"], e))

            if len(constraints) != (len(staged["transport_params"]) or
                                    len(constraints) != len(active["transport_params"])):
                return test.FAIL("sender {} : staged, active and constraints arrays are inconsistent"
                                 .format(sender["id"]))

            # now check transport minimum requirements
            i = 0
            for c_params in constraints:

                valid, msg = checkSenderTransportParametersPEP(
                    sender["transport"],
                    c_params,
                    staged["transport_params"][i],
                    active["transport_params"][i])
                if not valid:
                    return test.FAIL("sender {} : active transport parameters is not valid against minimum requirements"
                                     ", error {}".format(sender["id"], msg))
                valid, generic, elliptic, msg = self.hasSenderTransportParametersPEP(
                    sender["transport"],
                    c_params,
                    staged["transport_params"][i],
                    active["transport_params"][i])
                if not valid:
                    return test.FAIL("sender {} : active transport parameters is not valid against minimum requirements"
                                     ", error {}".format(sender["id"], msg))

                null_mode = (privacy_mode in constraints[i] and
                             "enum" in constraints[i][privacy_mode] and
                             "NULL" in constraints[i][privacy_mode]["enum"])

                if generic:

                    if active["master_enable"]:

                        # It must be possible to change any privacy attribute if active to its current value
                        # as re-activation
                        for name in c_params.keys():
                            if name.startswith("ext_privacy_"):
                                valid, response = self.updateSenderParameter(
                                    sender,
                                    True,
                                    name,
                                    active["transport_params"][i][name],
                                    staged["transport_params"])
                                if not valid:
                                    return test.FAIL("sender {} : fail re-activation, response {}"
                                                     .format(sender["id"], response))
                                else:
                                    pass
                    else:

                        # It must be possible to change any privacy attribute if inactive to its current value except
                        # for ext_privacy_ecdh_sender_public_key on a Sender and ext_privacy_ecdh_receiver_public_key
                        # on a Receiver as an activation with master_enable set to false regenerate those values.
                        for name in c_params.keys():
                            if name.startswith("ext_privacy_") and name != "ext_privacy_ecdh_sender_public_key":
                                valid, response = self.updateSenderParameter(
                                    sender,
                                    False,
                                    name,
                                    active["transport_params"][i][name],
                                    staged["transport_params"])
                                if not valid:
                                    return test.FAIL("sender {} : failed activation, response {}"
                                                     .format(sender["id"], response))
                                else:
                                    pass

                        # It must not be possible to change any privacy attribute if inactive to an invalid
                        # value if a constraint is declared
                        for name in c_params.keys():
                            if name.startswith("ext_privacy_"):
                                if "enum" in c_params[name]:
                                    valid, response = self.updateSenderParameter(
                                        sender,
                                        False,
                                        name,
                                        "this-is-an-invalid-value",
                                        staged["transport_params"])
                                    if valid:
                                        return test.FAIL("sender {} : dit not fail activation as expected, response {}"
                                                         .format(sender["id"], response))
                                    else:
                                        pass

                        # It must be possible to change any privacy attribute if inactive to any value of
                        # the associated constraints except for ext_privacy_ecdh_sender_public_key on a
                        # Sender and ext_privacy_ecdh_receiver_public_key on a Receiver as an activation
                        # with master_enable set to false regenerate those values.
                        for name in c_params.keys():
                            if name.startswith("ext_privacy_") and name != "ext_privacy_ecdh_sender_public_key":
                                if "enum" in c_params[name]:
                                    for value in c_params[name]["enum"]:
                                        valid, response = self.updateSenderParameter(
                                            sender,
                                            False,
                                            name,
                                            value,
                                            staged["transport_params"])
                                        if not valid:
                                            return test.FAIL("sender {} : failed activation, response {}"
                                                             .format(sender["id"], response))
                                        else:
                                            pass

                        # REFERENCE: An NMOS API MUST NOT allow to change the state (enabled or disabled) of
                        # privacy encryption.
                        #
                        # It must not be possible to disable privacy encryption unless already disabled
                        if not null_mode:

                            valid, response = self.updateSenderParameter(
                                sender,
                                False,
                                privacy_protocol,
                                "NULL",
                                staged["transport_params"])
                            if valid:
                                return test.FAIL("sender {} : did not fail activation as expected, response {}"
                                                 .format(sender["id"], response))
                            else:
                                pass

                            valid, response = self.updateSenderParameter(
                                sender,
                                False,
                                privacy_mode,
                                "NULL",
                                staged["transport_params"])
                            if valid:
                                return test.FAIL("sender {} : did not fail activation as expected, response {}"
                                                 .format(sender["id"], response))
                            else:
                                pass

                i = i + 1

        if no_privacy_senders:
            return test.OPTIONAL("No BCP-005-03 (IPMX/PEP) Sender found")

        if warning != "":
            return test.WARNING(warning)
        else:
            return test.PASS()

    def test_04(self, test):
        """ Check that receivers transport parameters having 'ext_privacy' parameters are valid """

        reg_api = self.apis["ext-transport-parameters-register"]
        reg_path = reg_api["spec_path"] + "/transport-parameters"

        valid, result = self.get_is04_resources("receivers")
        if not valid:
            return test.FAIL(result)

        valid, result = self.get_is05_partial_resources("receivers")
        if not valid:
            return test.FAIL(result)

        warning = ""
        all_active = True  # proven otherwise

        if len(self.is04_resources["receivers"].values()) == 0:
            return test.UNCLEAR("No Receivers were found on the Node")

        no_privacy_receivers = True

        for receiver in self.is04_resources["receivers"].values():

            reg_schema = load_resolved_schema(reg_path, "ext-constraints-schema.json", path_prefix=False)

            if reg_schema is not None:
                url = "single/receivers/{}/constraints".format(receiver["id"])
                valid, response = self.is05_utils.checkCleanRequest("GET", url)
                if valid:

                    # There is nothing to validate in the response as there are only constraints
                    constraints = response.json()

                    try:
                        for params in constraints:
                            params = {k: v for k, v in params.items() if k.startswith("ext_privacy")}
                            self.validate_schema(params, reg_schema)
                    except ValidationError as e:
                        return test.FAIL("receiver {} : transport parameters constraints do not match schema, error {}"
                                         .format(receiver["id"], e))
                else:
                    return test.FAIL("receiver {} : request to transport parameters constraints is not valid"
                                     .format(receiver["id"]))
            else:
                test.ERROR("Cannot load ext-constraints-schema.json")

            # Now check that the elements of the constraints, stages and active all match
            reg_schema = load_resolved_schema(reg_path,
                                              "receiver_transport_params_ext_register.json"
                                              "", path_prefix=False)
            if reg_schema is None:
                test.ERROR("Cannot load receiver_transport_params_ext_register.json")

            url = "single/receivers/{}/staged".format(receiver["id"])
            valid, response = self.is05_utils.checkCleanRequest("GET", url)
            if not valid:
                return test.FAIL("receiver {} : cannot get receiver staged parameters".format(receiver["id"]))
            staged = response.json()

            try:
                for params in staged['transport_params']:
                    params = {k: v for k, v in params.items() if k.startswith("ext_privacy")}
                    self.validate_schema(params, reg_schema)
            except ValidationError as e:
                return test.FAIL("receiver {} : staged transport parameters do not match schema, error {}"
                                 .format(receiver["id"], e))

            url = "single/receivers/{}/active".format(receiver["id"])
            valid, response = self.is05_utils.checkCleanRequest("GET", url)
            if not valid:
                return test.FAIL("receiver {} : cannot get receiver active parameters".format(receiver["id"]))
            active = response.json()

            try:
                for params in active['transport_params']:
                    params = {k: v for k, v in params.items() if k.startswith("ext_privacy")}
                    self.validate_schema(params, reg_schema)
            except ValidationError as e:
                return test.FAIL("receiver {} : active transport parameters do not match schema, error {}"
                                 .format(receiver["id"], e))

            if len(constraints) != (len(staged["transport_params"]) or
                                    len(constraints) != len(active["transport_params"])):
                return test.FAIL("receiver {} : staged, active and constraints arrays are inconsistent"
                                 .format(receiver["id"]))

            # across staged, active and constraints
            i = 0
            for c_params in constraints:
                s_params = staged["transport_params"][i]
                a_params = active["transport_params"][i]

                for c in c_params.keys():
                    if (c not in s_params.keys()) or (c not in a_params.keys()):
                        return test.FAIL("receiver {} : staged, active and constraints parameters are inconsistent"
                                         .format(receiver["id"]))

                i = i + 1

            # across legs
            for c_params in constraints:
                for c in c_params.keys():
                    if (c not in constraints[0].keys()):
                        return test.FAIL("receiver {} : constraints parameters are inconsistent"
                                         .format(receiver["id"]))

            for s_params in staged["transport_params"]:
                for c in s_params.keys():
                    if (c not in staged["transport_params"][0].keys()):
                        return test.FAIL("receiver {} : staged parameters are inconsistent".format(receiver["id"]))

            for a_params in active["transport_params"]:
                for c in a_params.keys():
                    if (c not in active["transport_params"][0].keys()):
                        return test.FAIL("receiver {} : active parameters are inconsistent".format(receiver["id"]))

            # now check transport minimum requirements
            privacy = False

            i = 0
            for c_params in constraints:

                valid, msg = checkReceiverTransportParametersPEP(
                    receiver["transport"],
                    c_params,
                    staged["transport_params"][i],
                    active["transport_params"][i])
                if not valid:
                    return test.FAIL("receiver {} : active transport parameters is not valid against "
                                     "minimum requirements, error {}".format(receiver["id"], msg))
                valid, generic, elliptic, msg = self.hasReceiverTransportParametersPEP(
                    receiver["transport"],
                    c_params,
                    staged["transport_params"][i],
                    active["transport_params"][i])
                if not valid:
                    return test.FAIL("receiver {} : active transport parameters is not valid against"
                                     " minimum requirements, error {}".format(receiver["id"], msg))

                if generic:

                    privacy = True

                    ok, msg = self.check_generic_attribute_values(
                        False,
                        receiver,
                        c_params,
                        staged["transport_params"][i],
                        active["transport_params"][i],
                        elliptic,
                        active["master_enable"])
                    if not ok:
                        return test.FAIL("receiver {} : invalid privacy encryption attribute value, error {}"
                                         .format(receiver["id"], msg))
                    if msg != "":
                        warning += "|" + msg

                    null_mode = (privacy_mode in constraints[i] and
                                 "enum" in constraints[i][privacy_mode] and
                                 "NULL" in constraints[i][privacy_mode]["enum"])

                    # check receiver capability if present
                    if "constraint_sets" in receiver["caps"]:
                        for constraint_set in receiver["caps"]["constraint_sets"]:
                            if has_key(constraint_set, privacy_capability):
                                capability = get_key_value(constraint_set, privacy_capability)
                                if "enum" in capability:
                                    enums = capability["enum"]
                                    if len(enums) != 1:
                                        return test.FAIL("receiver {} : invalid privacy capabilities {}"
                                                         .format(receiver["id"], capability))
                                    for value in enums:
                                        if not isinstance(value, bool):
                                            return test.FAIL("receiver {} : privacy capability must be of type bool"
                                                             .format(receiver["id"]))
                                        if value and null_mode is True:
                                            return test.FAIL("receiver {} : privacy capability must match"
                                                             " privacy transport parameters".format(receiver["id"]))
                                        if not value and null_mode is False:
                                            return test.FAIL("receiver {} : privacy capability must match"
                                                             " privacy transport parameters".format(receiver["id"]))

                i = i + 1

            # attributes must match across legs
            ok, msg = self.check_across_legs(
                True,
                receiver,
                constraints,
                staged["transport_params"],
                active["transport_params"],
                elliptic)
            if not ok:
                return test.FAIL("receiver {} : invalid privacy capability, error {}".format(receiver["id"], msg))
            if msg != "":
                warning += "|" + msg

            # We do require an active receiver to get final parameters and to know if there
            # is really no SDP transport file
            if privacy:

                no_privacy_receivers = False

                if active["master_enable"]:

                    # in an NMOS environment the SDP privacy attribute is required if an SDP transport file is used
                    # check SDP transport file matching transport parameters, check RTP Extension header declaration
                    if active["transport_file"]["data"] is not None:

                        sdp_lines = [sdp_line.replace("\r", "")
                                     for sdp_line in active["transport_file"]["data"].split("\n")]

                        ok, msg = self.check_privacy_attribute(
                            False,
                            receiver,
                            len(constraints),
                            constraints[0],
                            active["transport_params"][0],
                            sdp_lines)
                        if not ok:
                            return test.FAIL("receiver {} : invalid privacy capability, error {}"
                                             .format(receiver["id"], msg))
                        if msg != "":
                            warning += "|" + msg
                else:
                    all_active = False

        if not all_active:
            return test.UNCLEAR("One or more of the tested Receivers has master_enable set to false."
                                " Please ensure all Receivers are enabled and re-test.")

        if no_privacy_receivers:
            return test.OPTIONAL("No BCP-005-03 (IPMX/PEP) Receiver found")

        if warning != "":
            return test.WARNING(warning)
        else:
            return test.PASS()

    def test_05(self, test):
        """ Check that receiver transport parameters having 'ext_privacy' parameters are properly validated
            on activation against constraints """

        reg_api = self.apis["ext-transport-parameters-register"]
        reg_path = reg_api["spec_path"] + "/transport-parameters"

        valid, result = self.get_is04_resources("receivers")
        if not valid:
            return test.FAIL(result)

        valid, result = self.get_is05_partial_resources("receivers")
        if not valid:
            return test.FAIL(result)

        warning = ""

        if len(self.is04_resources["receivers"].values()) == 0:
            return test.UNCLEAR("No Receivers were found on the Node")

        no_privacy_receivers = True

        for receiver in self.is04_resources["receivers"].values():

            reg_schema = load_resolved_schema(reg_path, "ext-constraints-schema.json", path_prefix=False)

            if reg_schema is not None:
                url = "single/receivers/{}/constraints".format(receiver["id"])
                valid, response = self.is05_utils.checkCleanRequest("GET", url)
                if valid:

                    # There is nothing to validate in the response as there are only constraints
                    constraints = response.json()

                    try:
                        for params in constraints:
                            params = {k: v for k, v in params.items() if k.startswith("ext_privacy")}
                            self.validate_schema(params, reg_schema)
                    except ValidationError as e:
                        return test.FAIL("receiver {} : transport parameters constraints do not match"
                                         " schema, error {}".format(receiver["id"], e))
                else:
                    return test.FAIL("receiver {} : request to transport parameters constraints is not valid"
                                     .format(receiver["id"]))
            else:
                test.ERROR("Cannot load ext-constraints-schema.json")

            # Now check that the elements of the constraints, stages and active all match
            reg_schema = load_resolved_schema(reg_path,
                                              "receiver_transport_params_ext_register.json",
                                              path_prefix=False)
            if reg_schema is None:
                test.ERROR("Cannot load receiver_transport_params_ext_register.json")

            url = "single/receivers/{}/staged".format(receiver["id"])
            valid, response = self.is05_utils.checkCleanRequest("GET", url)
            if not valid:
                return test.FAIL("receiver {} : cannot get receiver staged parameters".format(receiver["id"]))
            staged = response.json()

            try:
                for params in staged['transport_params']:
                    params = {k: v for k, v in params.items() if k.startswith("ext_privacy")}
                    self.validate_schema(params, reg_schema)
            except ValidationError as e:
                return test.FAIL("receiver {} : staged transport parameters do not match schema, error {}"
                                 .format(receiver["id"], e))

            url = "single/receivers/{}/active".format(receiver["id"])
            valid, response = self.is05_utils.checkCleanRequest("GET", url)
            if not valid:
                return test.FAIL("receiver {} : cannot get receiver active parameters".format(receiver["id"]))
            active = response.json()

            try:
                for params in active['transport_params']:
                    params = {k: v for k, v in params.items() if k.startswith("ext_privacy")}
                    self.validate_schema(params, reg_schema)
            except ValidationError as e:
                return test.FAIL("receiver {} : active transport parameters do not match schema, error {}"
                                 .format(receiver["id"], e))

            if (len(constraints) != len(staged["transport_params"]) or
                    len(constraints) != len(active["transport_params"])):
                return test.FAIL("receiver {} : staged, active and constraints arrays are inconsistent"
                                 .format(receiver["id"]))

            # now check transport minimum requirements
            i = 0
            for c_params in constraints:

                valid, msg = checkReceiverTransportParametersPEP(
                    receiver["transport"],
                    c_params,
                    staged["transport_params"][i],
                    active["transport_params"][i])
                if not valid:
                    return test.FAIL("receiver {} : active transport parameters is not valid against"
                                     " minimum requirements, error {}".format(receiver["id"], msg))
                valid, generic, elliptic, msg = self.hasReceiverTransportParametersPEP(
                    receiver["transport"],
                    c_params,
                    staged["transport_params"][i],
                    active["transport_params"][i])
                if not valid:
                    return test.FAIL("receiver {} : active transport parameters is not valid against"
                                     " minimum requirements, error {}".format(receiver["id"], msg))

                null_mode = (privacy_mode in constraints[i] and
                             "enum" in constraints[i][privacy_mode] and
                             "NULL" in constraints[i][privacy_mode]["enum"])

                if generic:

                    no_privacy_receivers = False

                    if active["master_enable"]:

                        # It must be possible to change any privacy attribute if active to its current
                        # value as re-activation
                        for name in c_params.keys():
                            if name.startswith("ext_privacy_"):
                                valid, response = self.updateReceiverParameter(
                                    receiver,
                                    True,
                                    name,
                                    active["transport_params"][i][name],
                                    staged["transport_params"])
                                if not valid:
                                    return test.FAIL("receiver {} : fail re-activation, response {}"
                                                     .format(receiver["id"], response))
                                else:
                                    pass
                    else:

                        # It must be possible to change any privacy attribute if inactive to its current value except
                        # for ext_privacy_ecdh_sender_public_key on a Sender and ext_privacy_ecdh_receiver_public_key
                        # on a Receiver as an activation with master_enable set to false regenerate those values.
                        for name in c_params.keys():
                            if name.startswith("ext_privacy_") and name != "ext_privacy_ecdh_receiver_public_key":
                                valid, response = self.updateReceiverParameter(
                                    receiver,
                                    False,
                                    name,
                                    active["transport_params"][i][name],
                                    staged["transport_params"])
                                if not valid:
                                    return test.FAIL("receiver {} : failed activation, response {}"
                                                     .format(receiver["id"], response))
                                else:
                                    pass

                        # REFERENCE: A Receiver MUST fail activation if the provided key_id is not provisioned in the
                        # device or is not listed in the Receiver's ext_privacy_key_id transport parameter constraints.
                        # >>> Note: The test suite cannot activate an inactive Receiver, the best we can do it to set
                        #           invalid values while inactive assuming that the parameters are considered
                        #           individually independently of the value of master_enable.
                        #
                        # It must not be possible to change any privacy attribute if inactive to an invalid value
                        # if a constraint is declared
                        for name in c_params.keys():
                            if name.startswith("ext_privacy_"):
                                if "enum" in c_params[name]:
                                    valid, response = self.updateReceiverParameter(
                                        receiver,
                                        False,
                                        name,
                                        "this-is-an-invalid-value",
                                        staged["transport_params"])
                                    if valid:
                                        return test.FAIL("receiver {} : dit not fail activation as expected"
                                                         ", response {}".format(receiver["id"], response))
                                    else:
                                        pass

                        # It must be possible to change any privacy attribute if inactive to any value
                        # of the associated constraints except for ext_privacy_ecdh_sender_public_key on
                        # a Sender and ext_privacy_ecdh_receiver_public_key on a Receiver as an activation
                        # with master_enable set to false regenerate those values.
                        for name in c_params.keys():
                            if name.startswith("ext_privacy_") and name != "ext_privacy_ecdh_receiver_public_key":
                                if "enum" in c_params[name]:
                                    for value in c_params[name]["enum"]:
                                        valid, response = self.updateReceiverParameter(
                                            receiver,
                                            False,
                                            name,
                                            value,
                                            staged["transport_params"])
                                        if not valid:
                                            return test.FAIL("receiver {} : failed activation, response {}"
                                                             .format(receiver["id"], response))
                                        else:
                                            pass

                        # REFERENCE: An NMOS API MUST NOT allow to change the state (enabled or disabled) of
                        # privacy encryption.
                        #
                        # It must not be possible to disable privacy encryption unless already disabled
                        if not null_mode:

                            valid, response = self.updateReceiverParameter(
                                receiver,
                                False,
                                privacy_protocol,
                                "NULL",
                                staged["transport_params"])
                            if valid:
                                return test.FAIL("receiver {} : did not fail activation as expected, response {}"
                                                 .format(receiver["id"], response))
                            else:
                                pass

                            valid, response = self.updateReceiverParameter(
                                receiver,
                                False,
                                privacy_mode,
                                "NULL",
                                staged["transport_params"])
                            if valid:
                                return test.FAIL("receiver {} : did not fail activation as expected, response {}"
                                                 .format(receiver["id"], response))
                            else:
                                pass

                i = i + 1

        if no_privacy_receivers:
            return test.OPTIONAL("No BCP-005-03 (IPMX/PEP) Receiver found")

        if warning != "":
            return test.WARNING(warning)
        else:
            return test.PASS()

    def test_06(self, test):
        """ Check that senders ECDH private/public key is regenerated on an activation
            with master_enable set to false """

        reg_api = self.apis["ext-transport-parameters-register"]
        reg_path = reg_api["spec_path"] + "/transport-parameters"

        valid, result = self.get_is04_resources("senders")
        if not valid:
            return test.FAIL(result)

        valid, result = self.get_is05_partial_resources("senders")
        if not valid:
            return test.FAIL(result)

        warning = ""

        if len(self.is04_resources["senders"].values()) == 0:
            return test.UNCLEAR("No Senders were found on the Node")

        no_privacy_senders = True

        for sender in self.is04_resources["senders"].values():

            # REFERENCE: A Sender compliant with this specification MUST provide a privacy Sender attribute to
            # indicate that privacy encryption and the PEP protocol are used by the Sender.
            #
            # being compliant with BCP-005-03 (IPMX/PEP).
            if not has_key(sender, "privacy"):
                continue

            no_privacy_senders = False

            reg_schema = load_resolved_schema(reg_path, "ext-constraints-schema.json", path_prefix=False)

            if reg_schema is not None:
                url = "single/senders/{}/constraints".format(sender["id"])
                valid, response = self.is05_utils.checkCleanRequest("GET", url)
                if valid:

                    # There is nothing to validate in the response as there are only constraints
                    constraints = response.json()

                    try:
                        for params in constraints:
                            params = {k: v for k, v in params.items() if k.startswith("ext_privacy")}
                            self.validate_schema(params, reg_schema)
                    except ValidationError as e:
                        return test.FAIL("sender {} : transport parameters constraints do not match schema, error {}"
                                         .format(sender["id"], e))
                else:
                    return test.FAIL("sender {} : request to transport parameters constraints is not valid"
                                     .format(sender["id"]))
            else:
                test.ERROR("Cannot load ext-constraints-schema.json")

            # Now check that the elements of the constraints, stages and active all match
            reg_schema = load_resolved_schema(reg_path, "sender_transport_params_ext_register.json", path_prefix=False)
            if reg_schema is None:
                test.ERROR("Cannot load sender_transport_params_ext_register.json")

            url = "single/senders/{}/staged".format(sender["id"])
            valid, response = self.is05_utils.checkCleanRequest("GET", url)
            if not valid:
                return test.FAIL("sender {} : cannot get sender staged parameters".format(sender["id"]))
            staged = response.json()

            try:
                for params in staged['transport_params']:
                    params = {k: v for k, v in params.items() if k.startswith("ext_privacy")}
                    self.validate_schema(params, reg_schema)
            except ValidationError as e:
                return test.FAIL("sender {} : staged transport parameters do not match schema, error {}"
                                 .format(sender["id"], e))

            url = "single/senders/{}/active".format(sender["id"])
            valid, response = self.is05_utils.checkCleanRequest("GET", url)
            if not valid:
                return test.FAIL("sender {} : cannot get sender active parameters".format(sender["id"]))
            active = response.json()

            try:
                for params in active['transport_params']:
                    params = {k: v for k, v in params.items() if k.startswith("ext_privacy")}
                    self.validate_schema(params, reg_schema)
            except ValidationError as e:
                return test.FAIL("sender {} : active transport parameters do not match schema, error {}"
                                 .format(sender["id"], e))

            if (len(constraints) != len(staged["transport_params"])
                    or len(constraints) != len(active["transport_params"])):
                return test.FAIL("sender {} : staged, active and constraints arrays are inconsistent"
                                 .format(sender["id"]))

            # now check transport minimum requirements
            i = 0
            for c_params in constraints:

                valid, msg = checkSenderTransportParametersPEP(
                    sender["transport"],
                    c_params,
                    staged["transport_params"][i],
                    active["transport_params"][i])
                if not valid:
                    return test.FAIL("sender {} : active transport parameters is not valid against"
                                     " minimum requirements, error {}".format(sender["id"], msg))
                valid, generic, elliptic, msg = self.hasSenderTransportParametersPEP(
                    sender["transport"],
                    c_params,
                    staged["transport_params"][i],
                    active["transport_params"][i])
                if not valid:
                    return test.FAIL("sender {} : active transport parameters is not valid against"
                                     " minimum requirements, error {}".format(sender["id"], msg))

                null_curve = (privacy_ecdh_curve in constraints[i] and
                              "enum" in constraints[i][privacy_ecdh_curve] and
                              "NULL" in constraints[i][privacy_ecdh_curve]["enum"])

                if generic and elliptic:

                    if null_curve:
                        return test.DISABLED("sender {} : ECDH mode not supported".format(sender["id"]))

                    if active["master_enable"]:
                        return test.DISABLED("sender {} : testing ECDH private/public keys pair regeneration require"
                                             " inactive senders".format(sender["id"]))

                    previous_key = active["transport_params"][i][privacy_ecdh_sender_public_key]

                    valid, response = self.updateSenderParameter(
                        sender,
                        False,
                        privacy_ecdh_sender_public_key,
                        previous_key,
                        staged["transport_params"])
                    if not valid:
                        return test.FAIL("sender {} : fail activation, response {}".format(sender["id"], response))

                    reg_schema = load_resolved_schema(reg_path, "ext-constraints-schema.json", path_prefix=False)

                    if reg_schema is not None:
                        url = "single/senders/{}/constraints".format(sender["id"])
                        valid, response = self.is05_utils.checkCleanRequest("GET", url)
                        if valid:

                            # There is nothing to validate in the response as there are only constraints
                            new_constraints = response.json()

                            try:
                                for params in new_constraints:
                                    params = {k: v for k, v in params.items() if k.startswith("ext_privacy")}
                                    self.validate_schema(params, reg_schema)
                            except ValidationError as e:
                                return test.FAIL("sender {} : transport parameters constraints do not match schema"
                                                 ", error {}".format(sender["id"], e))
                        else:
                            return test.FAIL("sender {} : request to transport parameters constraints is not valid"
                                             .format(sender["id"]))
                    else:
                        test.ERROR("Cannot load ext-constraints-schema.json")

                    # Now check that the elements of the constraints, stages and active all match
                    url = "single/senders/{}/staged".format(sender["id"])
                    valid, response = self.is05_utils.checkCleanRequest("GET", url)
                    if not valid:
                        return test.FAIL("sender {} : cannot get sender staged parameters".format(sender["id"]))
                    new_staged = response.json()

                    url = "single/senders/{}/active".format(sender["id"])
                    valid, response = self.is05_utils.checkCleanRequest("GET", url)
                    if not valid:
                        return test.FAIL("sender {} : cannot get sender active parameters".format(sender["id"]))
                    new_active = response.json()

                    if (len(new_constraints) != len(new_staged["transport_params"])
                            or len(new_constraints) != len(new_active["transport_params"])):
                        return test.FAIL("sender {} : staged, active and constraints arrays are inconsistent"
                                         .format(sender["id"]))

                    if previous_key == new_staged["transport_params"][i][privacy_ecdh_sender_public_key]:
                        return test.FAIL("sender {} : ECDH private/public key {} not regenerated on staged endpoint"
                                         " at de-activation".format(sender["id"], previous_key))

                    if previous_key == new_active["transport_params"][i][privacy_ecdh_sender_public_key]:
                        return test.FAIL("sender {} : ECDH private/public key {} not regenerated on active endpoint"
                                         " at de-activation".format(sender["id"], previous_key))

                i = i + 1

        if no_privacy_senders:
            return test.OPTIONAL("No BCP-005-03 (IPMX/PEP) Sender found")

        if warning != "":
            return test.WARNING(warning)
        else:
            return test.PASS()

    def test_07(self, test):
        """ Check that receivers ECDH private/public key is regenerated on an activation
            with master_enable set to false """

        reg_api = self.apis["ext-transport-parameters-register"]
        reg_path = reg_api["spec_path"] + "/transport-parameters"

        valid, result = self.get_is04_resources("receivers")
        if not valid:
            return test.FAIL(result)

        valid, result = self.get_is05_partial_resources("receivers")
        if not valid:
            return test.FAIL(result)

        warning = ""

        if len(self.is04_resources["receivers"].values()) == 0:
            return test.UNCLEAR("No Receivers were found on the Node")

        no_privacy_receivers = True

        for receiver in self.is04_resources["receivers"].values():

            reg_schema = load_resolved_schema(reg_path, "ext-constraints-schema.json", path_prefix=False)

            if reg_schema is not None:
                url = "single/receivers/{}/constraints".format(receiver["id"])
                valid, response = self.is05_utils.checkCleanRequest("GET", url)
                if valid:

                    # There is nothing to validate in the response as there are only constraints
                    constraints = response.json()

                    try:
                        for params in constraints:
                            params = {k: v for k, v in params.items() if k.startswith("ext_privacy")}
                            self.validate_schema(params, reg_schema)
                    except ValidationError as e:
                        return test.FAIL("receiver {} : transport parameters constraints do not match schema"
                                         ", error {}".format(receiver["id"], e))
                else:
                    return test.FAIL("receiver {} : request to transport parameters constraints is not valid"
                                     .format(receiver["id"]))
            else:
                test.ERROR("Cannot load ext-constraints-schema.json")

            # Now check that the elements of the constraints, stages and active all match
            reg_schema = load_resolved_schema(reg_path,
                                              "receiver_transport_params_ext_register.json",
                                              path_prefix=False)
            if reg_schema is None:
                test.ERROR("Cannot load receiver_transport_params_ext_register.json")

            url = "single/receivers/{}/staged".format(receiver["id"])
            valid, response = self.is05_utils.checkCleanRequest("GET", url)
            if not valid:
                return test.FAIL("receiver {} : cannot get receiver staged parameters".format(receiver["id"]))
            staged = response.json()

            try:
                for params in staged['transport_params']:
                    params = {k: v for k, v in params.items() if k.startswith("ext_privacy")}
                    self.validate_schema(params, reg_schema)
            except ValidationError as e:
                return test.FAIL("receiver {} : staged transport parameters do not match schema, error {}"
                                 .format(receiver["id"], e))

            url = "single/receivers/{}/active".format(receiver["id"])
            valid, response = self.is05_utils.checkCleanRequest("GET", url)
            if not valid:
                return test.FAIL("receiver {} : cannot get receiver active parameters".format(receiver["id"]))
            active = response.json()

            try:
                for params in active['transport_params']:
                    params = {k: v for k, v in params.items() if k.startswith("ext_privacy")}
                    self.validate_schema(params, reg_schema)
            except ValidationError as e:
                return test.FAIL("receiver {} : active transport parameters do not match schema, error {}"
                                 .format(receiver["id"], e))

            if (len(constraints) != len(staged["transport_params"])
                    or len(constraints) != len(active["transport_params"])):
                return test.FAIL("receiver {} : staged, active and constraints arrays are inconsistent"
                                 .format(receiver["id"]))

            # now check transport minimum requirements
            i = 0
            for c_params in constraints:

                valid, msg = checkReceiverTransportParametersPEP(
                    receiver["transport"],
                    c_params,
                    staged["transport_params"][i],
                    active["transport_params"][i])
                if not valid:
                    return test.FAIL("receiver {} : active transport parameters is not valid against"
                                     " minimum requirements, error {}".format(receiver["id"], msg))
                valid, generic, elliptic, msg = self.hasReceiverTransportParametersPEP(
                    receiver["transport"],
                    c_params,
                    staged["transport_params"][i],
                    active["transport_params"][i])
                if not valid:
                    return test.FAIL("receiver {} : active transport parameters is not valid against"
                                     " minimum requirements, error {}".format(receiver["id"], msg))

                null_curve = (privacy_ecdh_curve in constraints[i] and
                              "enum" in constraints[i][privacy_ecdh_curve] and
                              "NULL" in constraints[i][privacy_ecdh_curve]["enum"])

                if generic:
                    no_privacy_receivers = False

                if generic and elliptic:

                    if null_curve:
                        return test.DISABLED("receiver {} : ECDH mode not supported".format(receiver["id"]))

                    if active["master_enable"]:
                        return test.DISABLED("receiver {} : testing ECDH private/public keys pair regeneration require"
                                             " inactive receivers".format(receiver["id"]))

                    previous_key = active["transport_params"][i][privacy_ecdh_receiver_public_key]

                    valid, response = self.updateReceiverParameter(
                        receiver,
                        False,
                        privacy_ecdh_receiver_public_key,
                        previous_key,
                        staged["transport_params"])
                    if not valid:
                        return test.FAIL("receiver {} : fail activation, response {}".format(receiver["id"], response))

                    reg_schema = load_resolved_schema(reg_path, "ext-constraints-schema.json", path_prefix=False)

                    if reg_schema is not None:
                        url = "single/receivers/{}/constraints".format(receiver["id"])
                        valid, response = self.is05_utils.checkCleanRequest("GET", url)
                        if valid:

                            # There is nothing to validate in the response as there are only constraints
                            new_constraints = response.json()

                            try:
                                for params in new_constraints:
                                    params = {k: v for k, v in params.items() if k.startswith("ext_privacy")}
                                    self.validate_schema(params, reg_schema)
                            except ValidationError as e:
                                return test.FAIL("receiver {} : transport parameters constraints do not match schema"
                                                 ", error {}".format(receiver["id"], e))
                        else:
                            return test.FAIL("receiver {} : request to transport parameters constraints is not valid"
                                             .format(receiver["id"]))
                    else:
                        test.ERROR("Cannot load ext-constraints-schema.json")

                    # Now check that the elements of the constraints, stages and active all match
                    url = "single/receivers/{}/staged".format(receiver["id"])
                    valid, response = self.is05_utils.checkCleanRequest("GET", url)
                    if not valid:
                        return test.FAIL("receiver {} : cannot get receiver staged parameters".format(receiver["id"]))
                    new_staged = response.json()

                    url = "single/receivers/{}/active".format(receiver["id"])
                    valid, response = self.is05_utils.checkCleanRequest("GET", url)
                    if not valid:
                        return test.FAIL("receiver {} : cannot get receiver active parameters".format(receiver["id"]))
                    new_active = response.json()

                    if (len(new_constraints) != len(new_staged["transport_params"])
                            or len(new_constraints) != len(new_active["transport_params"])):
                        return test.FAIL("receiver {} : staged, active and constraints arrays are inconsistent"
                                         .format(receiver["id"]))

                    if previous_key == new_staged["transport_params"][i][privacy_ecdh_receiver_public_key]:
                        return test.FAIL("receiver {} : ECDH private/public key {} not regenerated on staged endpoint"
                                         " at de-activation".format(receiver["id"], previous_key))

                    if previous_key == new_active["transport_params"][i][privacy_ecdh_receiver_public_key]:
                        return test.FAIL("receiver {} : ECDH private/public key {} not regenerated on active endpoint"
                                         " at de-activation".format(receiver["id"], previous_key))

                i = i + 1

        if no_privacy_receivers:
            return test.OPTIONAL("No BCP-005-03 (IPMX/PEP) Receiver found")

        if warning != "":
            return test.WARNING(warning)
        else:
            return test.PASS()

    def updateSenderParameter(self, sender, master_enable, name, value, staged):

        if len(staged) == 1:

            data = {
                "master_enable": master_enable,
                "activation": {
                    "mode": "activate_immediate"
                },
                "transport_params": [
                    {name: value}
                ]
            }

        else:

            data = {
                "master_enable": master_enable,
                "activation": {
                    "mode": "activate_immediate"
                },
                "transport_params": [
                    {name: value},
                    {name: value}
                ]
            }

        url = "single/senders/{}/staged".format(sender["id"])
        valid, response = self.is05_utils.checkCleanRequest("PATCH", url, data=data)

        return valid, response

    def test_08(self, test):
        """Check PEP Senders"""

        api = self.apis[SENDER_CAPS_KEY]

        reg_api = self.apis["caps-register"]
        reg_path = reg_api["spec_path"] + "/capabilities"

        # REFERENCE: A Node that is capable of transmitting privacy-encrypted streams using the
        # Privacy Encryption Protocol MUST expose Source, Flow, and Sender resources in the IS-04
        # Node API
        valid, result = self.get_is04_resources("senders")
        if not valid:
            return test.FAIL(result)

        schema = load_resolved_schema(api["spec_path"], "sender_constraint_sets.json")

        reg_schema_file = str(Path(os.path.abspath(reg_path)) / "constraint_set.json")
        with open(reg_schema_file, "r") as f:
            reg_schema_obj = json.load(f)
        reg_schema = load_resolved_schema(api["spec_path"], schema_obj=reg_schema_obj)

        no_privacy_senders = True
        access_error = False

        warning = ""

        if len(self.is04_resources["senders"].values()) == 0:
            return test.UNCLEAR("No Senders were found on the Node")

        for sender in self.is04_resources["senders"].values():

            # being compliant with BCP-005-03 (IPMX/PEP).
            if has_key(sender, "privacy"):

                no_privacy_senders = False

                # this if the state of the sender
                privacy = get_key_value(sender, "privacy")

                # These are the states EXPLICITLY allowed by the sender's capabilities.
                only_allow_true = None
                only_allow_false = None

                # REFERENCE: A Sender MAY provide a `urn:x-nmos:cap:transport:privacy` capability to indicate that
                #            privacy encryption protocol is supported.
                #
                # If only_allow_true and only_allow_true are None is indicates that capabilities were not provided.
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
                                "Sender {} constraint_sets do not comply with registered schema, error {}".format(
                                    sender["id"], e))

                        # Ignore disabled constraint sets
                        if ("urn:x-nmos:cap:meta:enabled" in constraint_set and
                                not constraint_set["urn:x-nmos:cap:meta:enabled"]):
                            continue

                        # Explicit declarations only
                        if has_key(constraint_set, "cap:transport:privacy"):
                            param_constraint = get_key_value(constraint_set, "cap:transport:privacy")
                            if "enum" in param_constraint:
                                if (True in param_constraint["enum"]) and (False not in param_constraint["enum"]):
                                    only_allow_false = False
                                    if only_allow_true is None:
                                        only_allow_true = True
                                if (False in param_constraint["enum"]) and (True not in param_constraint["enum"]):
                                    only_allow_true = False
                                    if only_allow_false is None:
                                        only_allow_false = True

                                # REFERENCE: The urn:x-nmos:cap:transport:privacy capability MUST NOT allow
                                # both true and false values.
                                if len(param_constraint["enum"]) != 1:
                                    return test.FAIL(
                                        "Sender {} has an invalid 'privacy' capabilities "
                                        "which is must be either 'true' or 'false'".format(
                                            sender["id"]))
                            else:
                                only_allow_true = False
                                only_allow_false = False

                                # REFERENCE: The urn:x-nmos:cap:transport:privacy capability MUST NOT allow
                                # both true and false values.
                                return test.FAIL(
                                    "Sender {} has an invalid 'privacy' capabilities "
                                    "which is must be either 'true' or 'false'".format(
                                        sender["id"]))

                # Check that the sender state does not contradict its explicit capabilities
                if only_allow_true is not None:
                    # If so it must be consistent
                    if only_allow_true and not privacy:
                        return test.FAIL(
                            "Sender {} has an invalid 'privacy' state {} "
                            "which is not allowed by the Sender's capabilities only allowing 'true'".format(
                                sender["id"], privacy))

                if only_allow_false is not None:
                    # If so it must be consistent
                    if only_allow_false and privacy:
                        return test.FAIL(
                            "Sender {} has an invalid 'privacy' state {} "
                            "which is not allowed by the Sender's capabilities only allowing 'false'".format(
                                sender["id"], privacy))

                # Check SDP transport file. As per IS04 sender.json schema this attribute is required.
                if "manifest_href" not in sender:
                    return test.FAIL("Sender {} MUST indicate the 'manifest_href' attribute."
                                     .format(sender["id"]))

                # REFERENCE: If an SDP transport file is not currently available because the Sender is inactive, this
                #            attribute indicates whether or not such an SDP transport file would contain an `privacy`
                #            attribute if the Sender were active at that time.
                #
                # There may be no SDP transport file because the sender it inactive or because the transport used by
                # the Sender does not support an SDP transport file. In both case we'll return an UNCLEAR status to
                # indicate "could not test".
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

                found_privacy = False
                for sdp_line in sdp_lines:
                    privacy_attribute = re.search(r"^a=privacy:(.+)$", sdp_line)
                    if privacy_attribute:
                        found_privacy = True

                # SDP transport file must match with capabilities
                if only_allow_true is not None:
                    # REFERENCE: If the `urn:x-nmos:cap:transport:privacy` capability only allows the value `true`, then
                    #            the Sender's associated SDP transport file MUST have an `privacy` attribute.
                    if only_allow_true and not found_privacy:
                        return test.FAIL(
                            "Sender {} has an invalid SDP transport file without an 'privacy' attribute "
                            "which is not allowed by the Sender's capabilities only allowing 'true'".format(
                                sender["id"]))

                if only_allow_false is not None:
                    # REFERENCE: If the `urn:x-nmos:cap:transport:privacy` capability only allows the value `false`,
                    #            then the Sender's associated SDP transport file MUST NOT have an `privacy` attribute.
                    if only_allow_false and found_privacy:
                        return test.FAIL(
                            "Sender {} has an invalid SDP transport file with an 'privacy' attribute "
                            "which is not allowed by the Sender's capabilities only allowing 'false'".format(
                                sender["id"]))

                # REFERENCE: For transport protocols using an SDP transport file: a Sender MUST communicate privacy
                # encryption parameters in the SDP transport file associated with a privacy-encrypted stream, and
                # MUST also communicate these parameters using the extended NMOS transport parameters.
                #
                # REFERENCE: This attribute MUST be true if a privacy attribute is present in the Sender's SDP transport
                # file, and MUST be false if no privacy attributes are present.
                #
                # sender state must match with SDP transport file
                if privacy != found_privacy:
                    return test.FAIL(
                        "Sender {} has an invalid SDP transport file {} an 'privacy' attribute "
                        "which does not match with the Sender privacy attribute {}".format(
                            sender["id"], "with" if found_privacy else "without", privacy))

        if access_error:
            return test.UNCLEAR("One or more of the tested Senders had null or empty 'manifest_href' or "
                                "returned a 404 HTTP code. Please ensure all Senders are enabled and re-test.")
        if no_privacy_senders:
            return test.OPTIONAL("No BCP-005-03 (IPMX/PEP) Sender found")

        if warning != "":
            return test.WARNING(warning)
        else:
            return test.PASS()

    def test_09(self, test):
        """Check PEP Receivers"""

        api = self.apis[RECEIVER_CAPS_KEY]

        reg_api = self.apis["caps-register"]
        reg_path = reg_api["spec_path"] + "/capabilities"

        #  REFERENCE: A Node that is capable of receiving privacy-encrypted streams using the
        #  Privacy Encryption Protocol MUST expose Receiver resources in the IS-04 Node API.
        valid, result = self.get_is04_resources("receivers")
        if not valid:
            return test.FAIL(result)

        schema = load_resolved_schema(api["spec_path"], "receiver_constraint_sets.json")

        reg_schema_file = str(Path(os.path.abspath(reg_path)) / "constraint_set.json")
        with open(reg_schema_file, "r") as f:
            reg_schema_obj = json.load(f)
        reg_schema = load_resolved_schema(api["spec_path"], schema_obj=reg_schema_obj)

        no_privacy_receivers = True
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
                            "Receiver {} constraint_sets do not comply with registered schema, error {}".format(
                                receiver["id"], e))

                    # Ignore disabled constraint sets
                    if ("urn:x-nmos:cap:meta:enabled" in constraint_set and
                            not constraint_set["urn:x-nmos:cap:meta:enabled"]):
                        continue

                    # REFERENCE: A Receiver SHOULD provide a `urn:x-nmos:cap:transport:privacy` capability to indicate
                    #            its support for Senders that use privacy encryption protocol.
                    if has_key(constraint_set, "cap:transport:privacy"):
                        no_privacy_receivers = False

        if no_constraint_sets:
            return test.OPTIONAL("No Receiver describing BCP-004-01 Capabilities found")

        if no_privacy_receivers:
            return test.OPTIONAL("No BCP-005-03 (IPMX/PEP) Receiver found")

        if warning != "":
            return test.WARNING(warning)
        else:
            return test.PASS()

    def updateReceiverParameter(self, receiver, master_enable, name, value, staged):

        if len(staged) == 1:

            data = {
                "master_enable": master_enable,
                "activation": {
                    "mode": "activate_immediate"
                },
                "transport_params": [
                    {name: value}
                ]
            }

        else:

            data = {
                "master_enable": master_enable,
                "activation": {
                    "mode": "activate_immediate"
                },
                "transport_params": [
                    {name: value},
                    {name: value}
                ]
            }

        url = "single/receivers/{}/staged".format(receiver["id"])
        valid, response = self.is05_utils.checkCleanRequest("PATCH", url, data=data)

        return valid, response

    def hasSenderTransportParametersPEP(self, transport, constraints, staged, active):

        pep_required = (privacy_protocol, privacy_mode, privacy_iv, privacy_key_generator, privacy_key_version,
                        privacy_key_id)
        ecdh_required = (privacy_ecdh_sender_public_key, privacy_ecdh_receiver_public_key, privacy_ecdh_curve)

        has_generic = False
        has_elliptic = False

        for k in constraints.keys():
            if k.startswith("ext_privacy_"):
                for p in pep_required:
                    if p not in constraints.keys():
                        return False, False, False, "required transport parameter {} not found in constraints".format(p)
                    if p not in staged.keys():
                        return False, False, False, "required transport parameter {} not found in staged".format(p)
                    if p not in active.keys():
                        return False, False, False, "required transport parameter {} not found in active".format(p)

                protocols = getPrivacyProtocolFromTransport(transport)

                if staged["ext_privacy_protocol"] not in protocols:
                    return False, False, False, "invalid PEP protocol {}, expecting one of {} ".format(
                        staged["ext_privacy_protocol"], protocols)
                if active["ext_privacy_protocol"] not in protocols:
                    return False, False, False, "invalid PEP protocol {}, expecting one of {} ".format(
                        active["ext_privacy_protocol"], protocols)

                has_generic = True

                break  # check once

        for k in constraints.keys():
            if k.startswith("ext_privacy_ecdh_"):
                for p in ecdh_required:
                    if p not in constraints.keys():
                        return False, False, False, "required transport parameter {} not found in constraints".format(p)
                    if p not in staged.keys():
                        return False, False, False, "required transport parameter {} not found in staged".format(p)
                    if p not in active.keys():
                        return False, False, False, "required transport parameter {} not found in active".format(p)

                has_elliptic = True

                break  # check once

        return True, has_generic, has_elliptic, None

    def hasReceiverTransportParametersPEP(self, transport, constraints, staged, active):

        pep_required = (privacy_protocol, privacy_mode, privacy_iv, privacy_key_generator, privacy_key_version,
                        privacy_key_id)
        ecdh_required = (privacy_ecdh_sender_public_key, privacy_ecdh_receiver_public_key, privacy_ecdh_curve)

        has_generic = False
        has_elliptic = False

        for k in constraints.keys():
            if k.startswith("ext_privacy_"):
                for p in pep_required:
                    if p not in constraints.keys():
                        return False, False, False, "required transport parameter {} not found in constraints".format(p)
                    if p not in staged.keys():
                        return False, False, False, "required transport parameter {} not found in staged".format(p)
                    if p not in active.keys():
                        return False, False, False, "required transport parameter {} not found in active".format(p)

                protocols = getPrivacyProtocolFromTransport(transport)

                if staged["ext_privacy_protocol"] not in protocols:
                    return False, False, False, "invalid PEP protocol {}, expecting one of {} ".format(
                        staged["ext_privacy_protocol"], protocols)
                if active["ext_privacy_protocol"] not in protocols:
                    return False, False, False, "invalid PEP protocol {}, expecting one of {} ".format(
                        active["ext_privacy_protocol"], protocols)

                has_generic = True

                break  # check once

        for k in constraints.keys():
            if k.startswith("ext_privacy_ecdh_"):
                for p in ecdh_required:
                    if p not in constraints.keys():
                        return False, False, False, "required transport parameter {} not found in constraints".format(p)
                    if p not in staged.keys():
                        return False, False, False, "required transport parameter {} not found in staged".format(p)
                    if p not in active.keys():
                        return False, False, False, "required transport parameter {} not found in active".format(p)

                has_elliptic = True

                break  # check once

        return True, has_generic, has_elliptic, None

    def check_generic_attribute_values(self, is_sender, sender_receiver, constraints, staged, active,
                                       elliptic, master_enable):

        # REFERENCE: Each ext_privacy_* transport parameter MUST have an associated constraint that
        # either indicates that the parameter is unconstrained, allowing any valid value, or that it
        # is constrained to a specific set of values. A parameter identified as read-only in the
        # parameter definitions table MUST always be constrained to a single value. A Sender/Receiver
        # MUST fail activation if any IS-05 ext_privacy_* transport parameter violates its defined
        # constraints.
        #
        # The constraints endpoint of the parameters ext_privacy_protocol and ext_privacy_mode on both
        # Senders and Receivers MUST enumerate all supported protocols and modes. These parameters MUST
        # NOT be unconstrained, and their constraints MUST NOT change when the master_enable attribute
        # of a Sender/Receiver active endpoint is true.
        #
        # The constraints endpoint of the parameter ext_privacy_ecdh_curve on both Senders and Receivers
        # MUST enumerate all supported curves. This parameter MUST NOT be unconstrained, and its constraints
        # MUST NOT change when the master_enable attribute of a Sender/Receiver active endpoint is true.

        warning = ""

        if is_sender:
            identity = "sender"
        else:
            identity = "receiver"

        null_protocol = False

        # check 'protocol' constraints
        allowed_protocols = ("RTP", "RTP_KV", "USB", "USB_KV", "NULL")

        # protocol parameter must have a constraint the describe the protocols supported or NULL
        if "enum" not in constraints[privacy_protocol]:
            return False, "{} {} : {} constraint must list all the supported protocols or NULL".format(
                identity, sender_receiver["id"], privacy_protocol)

        enums = constraints[privacy_protocol]["enum"]

        # At least one protocol must be allowed
        if len(enums) == 0:
            return False, "{} {} : {} constraint must allow at least one value".format(
                identity, sender_receiver["id"], privacy_protocol)

        # Each allowed protocol must be a string and one of the allowed protocols of the specification.
        for c in enums:
            if not isinstance(c, str):
                return False, "{} {} : {} constraint value must be string".format(
                    identity, sender_receiver["id"], privacy_protocol)
            if c not in allowed_protocols:
                return False, "{} {} : {} constraint value must be one of {}".format(
                    identity, sender_receiver["id"], privacy_protocol, allowed_protocols)

        # REFERENCE: The protocol parameter MUST be one of the following: "RTP", "RTP_KV",
        # "USB", "USB_KV", or "NULL".
        #
        # REFERENCE: If privacy encryption is disabled or not supported by a Sender/Receiver,
        # and the ext_privacy_* transport parameters are present, the "NULL" protocol MUST be
        # used for the ext_privacy_protocol transport parameter in the active and staged endpoints
        # to indicate that privacy encryption is not available or is disabled. The associated
        # constraints MUST allow only the "NULL" protocol when the ext_privacy_protocol parameter
        # is "NULL".

        # If NULL is allowed, it must be the only one allowed
        if "NULL" in enums:
            null_protocol = True
            if len(enums) != 1:
                return False, "{} {} : {} constraint cannot allow other values if 'NULL' is allowed".format(
                    identity, sender_receiver["id"], privacy_protocol)
        # if not NULL then verify against the transport being used
        else:
            if sender_receiver["transport"] in ("urn:x-nmos:transport:rtp",
                                                "urn:x-nmos:transport:rtp.mcast" and "urn:x-nmos:transport:rtp.ucast"):

                # REFERENCE: The "RTP" protocol MUST be supported by all devices implementing TR-10-13 for the
                # urn:x-nmos:transport:rtp, urn:x-nmos:transport:rtp.mcast, and urn:x-nmos:transport:rtp.ucast
                # transports.

                # for RTP based transport, the RTP protocol adaptation MUST be supported
                if "RTP" not in enums:
                    return False, "{} {} : {} constraint value must allow 'RTP' for transport {}".format(
                        identity, sender_receiver["id"], privacy_protocol, sender_receiver["transport"])
                # for an RTP based transport only the RTP and RTP_KV adaptations are allowed
                for c in enums:
                    if c not in ("RTP", "RTP_KV"):
                        msg = "{} {} : {} constraint value must be one of 'RTP', 'RTP_KV' for transport {}".format(
                            identity, sender_receiver["id"], privacy_protocol, sender_receiver["transport"])
                        return False, msg

            if urn_without_namespace(sender_receiver["transport"]) in ("transport:usb"):

                # REFERENCE: The "USB_KV" protocol MUST be supported by all devices implementing TR-10-13
                # and TR-10-14 for the urn:x-nmos:transport:usb transport.
                #
                # for USB based transport, the USB_KV protocol adaptation MUST be supported
                if "USB_KV" not in enums:
                    return False, "{} {} : {} constraint value must allow 'USB_KV' for transport {}".format(
                        identity, sender_receiver["id"], privacy_protocol, sender_receiver["transport"])
                # for a USB based transport only the USB and USB_KV adaptations are allowed
                for c in enums:
                    if c not in ("USB", "USB_KV"):
                        msg = "{} {} : {} constraint value must be one of 'USB', 'USB_KV' for transport {}".format(
                            identity, sender_receiver["id"], privacy_protocol, sender_receiver["transport"])
                        return False, msg

        # check that 'protocol' staged and active values are within constraints
        if staged[privacy_protocol] not in enums:
            return False, "{} {} : {} staged value {} is not within constraints {}".format(
                identity, sender_receiver["id"], privacy_protocol, staged[privacy_protocol], enums)
        if active[privacy_protocol] not in enums:
            msg = "{} {} : {} active value {} is not within constraints {}".format(
                identity, sender_receiver["id"], privacy_protocol, staged[privacy_protocol], enums)
            return False, msg

        ecdh = False

        if elliptic:

            # REFERENCE: The ecdh_curve parameter MUST be one of the following: "secp256r1",
            # "secp521r1", "25519", "448", or "NULL".
            #
            # if ECDH privacy parameters are present
            allowed_curves = ("secp256r1", "secp521r1", "25519", "448", "NULL")

            # ecdh_curve parameter must have a constraint the describe the protocols supported or NULL
            if "enum" not in constraints[privacy_ecdh_curve]:
                return False, "{} {} : {} constraint must list all the supported curves".format(
                    identity, sender_receiver["id"], privacy_ecdh_curve)

            # Note: the enum is allowed to have no value for the ECDH curve
            enums = constraints[privacy_ecdh_curve]["enum"]

            # Each allowed curve must be a string and one of the allowed curves of the specification.
            for c in enums:
                if not isinstance(c, str):
                    return False, "{} {} : {} constraint value must be string".format(
                        identity, sender_receiver["id"], privacy_ecdh_curve)
                if c not in allowed_curves:
                    return False, "{} {} : {} constraint value must be one of {}".format(
                        identity, sender_receiver["id"], privacy_ecdh_curve, allowed_curves)

            # REFERENCE: If the ECDH modes are not supported by a Sender/Receiver and the ext_privacy_* transport
            # parameters are present, the "NULL" curve MUST be used for the ext_privacy_ecdh_curve transport
            # parameter in the active and staged endpoints to indicate that ECDH modes are not available. The
            # associated constraints MUST allow only the "NULL" curve when the ext_privacy_ecdh_curve parameter
            # is "NULL".
            #
            # If NULL is allowed, it must be the only one allowed
            if "NULL" in enums:
                if len(enums) != 1:
                    return False, "{} {} : {} constraint cannot have other values if 'NULL' is allowed".format(
                        identity, sender_receiver["id"], privacy_ecdh_curve)
            else:

                # REFERENCE: The "secp256r1" ecdh_curve MUST be supported by all devices that implement ECDH modes.
                if "secp256r1" not in enums:
                    return False, "{} {} : {} constraint value must allow 'secp256r1'".format(
                        identity, sender_receiver["id"], privacy_ecdh_curve)

                ecdh = True

            # check that 'ecdh_curve' staged and active values are within constraints
            if staged[privacy_ecdh_curve] not in enums:
                return False, "{} {} : {} staged value {} is not within constraints {}".format(
                    identity, sender_receiver["id"], privacy_ecdh_curve, staged[privacy_ecdh_curve], enums)
            if active[privacy_ecdh_curve] not in enums:
                return False, "{} {} : {} active value {} is not within constraints {}".format(
                    identity, sender_receiver["id"], privacy_ecdh_curve, staged[privacy_ecdh_curve], enums)

        # check 'mode' constraints.
        if ecdh:
            allowed_rtp_modes = ("AES-128-CTR", "AES-256-CTR", "AES-128-CTR_CMAC-64", "AES-256-CTR_CMAC-64",
                                 "AES-128-CTR_CMAC-64-AAD", "AES-256-CTR_CMAC-64-AAD", "ECDH_AES-128-CTR",
                                 "ECDH_AES-256-CTR", "ECDH_AES-128-CTR_CMAC-64", "ECDH_AES-256-CTR_CMAC-64",
                                 "ECDH_AES-128-CTR_CMAC-64-AAD", "ECDH_AES-256-CTR_CMAC-64-AAD")
            allowed_usb_modes = ("AES-128-CTR_CMAC-64-AAD", "AES-256-CTR_CMAC-64-AAD",
                                 "ECDH_AES-128-CTR_CMAC-64-AAD", "ECDH_AES-256-CTR_CMAC-64-AAD")
        else:
            # ECDH modes must not be allowed if an ECDH curve is not supported
            allowed_rtp_modes = ("AES-128-CTR", "AES-256-CTR", "AES-128-CTR_CMAC-64", "AES-256-CTR_CMAC-64",
                                 "AES-128-CTR_CMAC-64-AAD", "AES-256-CTR_CMAC-64-AAD")
            allowed_usb_modes = ("AES-128-CTR_CMAC-64-AAD", "AES-256-CTR_CMAC-64-AAD")

        allowed_modes = tuple(set(allowed_rtp_modes + allowed_usb_modes))

        # mode parameter must have a constraint the describe the modes supported or NULL
        if "enum" not in constraints[privacy_mode]:
            return False, "{} {} : {} constraint must list all the supported modes or NULL".format(
                identity, sender_receiver["id"], privacy_mode)

        enums = constraints[privacy_mode]["enum"]

        # At least one mode must be allowed
        if len(enums) == 0:
            return False, "{} {} : {} constraint must allow at least one value".format(
                identity, sender_receiver["id"], privacy_mode)

        # Each allowed mode must be a string and one of the allowed modes of the specification.
        for c in enums:
            if not isinstance(c, str):
                return False, "{} {} : {} constraint value must be string".format(
                    identity, sender_receiver["id"], privacy_mode)
            if c not in allowed_modes:
                return False, "{} {} : {} constraint value must be one of {}".format(
                    identity, sender_receiver["id"], privacy_mode, allowed_modes)

        # REFERENCE: If privacy encryption is disabled or not supported by a Sender/Receiver, and the
        # ext_privacy_* transport parameters are present, the "NULL" mode MUST be used for the
        # ext_privacy_mode transport parameter in the active and staged endpoints to indicate that
        # privacy encryption is not available or is disabled. The associated constraints MUST allow
        # only the "NULL" mode when the ext_privacy_mode parameter is "NULL".
        #
        # If NULL is allowed, it must be the only one allowed and must match with protocol
        if "NULL" in enums:
            if not null_protocol:
                return False, "{} {} : {} constraint must match protocol if 'NULL' is allowed".format(
                    identity, sender_receiver["id"], privacy_mode)
            if len(enums) != 1:
                return False, "{} {} : {} constraint cannot have other values if 'NULL' is allowed".format(
                    identity, sender_receiver["id"], privacy_mode)
        # if not NULL then verify against the protocol adaptation being used
        else:
            if all(item in ("RTP", "RTP_KV") for item in constraints[privacy_protocol]["enum"]):

                # REFERENCE: The "AES-128-CTR" mode MUST be supported by all devices implementing the
                # "RTP" or "RTP_KV" protocols.
                #
                # for RTP, RTP_KV adaptations the AES-128-CTR mode MUST be supported
                if "AES-128-CTR" not in enums:
                    return False, "{} {} : {} constraint value must allow 'AES-128-CTR' for protocol {}".format(
                        identity, sender_receiver["id"], privacy_mode, constraints[privacy_protocol]["enum"])

                # REFERENCE: The mode parameter MUST be one of the following: "AES-128-CTR", "AES-256-CTR",
                # "AES-128-CTR_CMAC-64", "AES-256-CTR_CMAC-64", "AES-128-CTR_CMAC-64-AAD", "AES-256-CTR_CMAC-64-AAD",
                # "ECDH_AES-128-CTR", "ECDH_AES-256-CTR", "ECDH_AES-128-CTR_CMAC-64", "ECDH_AES-256-CTR_CMAC-64",
                # "ECDH_AES-128-CTR_CMAC-64-AAD", or "ECDH_AES-256-CTR_CMAC-64-AAD".
                #
                # for RTP, RTP_KV adaptations the mode MUST be on of the RTP modes
                for c in enums:
                    if c not in allowed_rtp_modes:
                        return False, "{} {} : {} constraint value must be one of {} for protocol {}".format(
                            identity, sender_receiver["id"], privacy_mode, allowed_modes,
                            constraints[privacy_protocol]["enum"])

            if all(item in ("USB", "USB_KV") for item in constraints[privacy_protocol]["enum"]):

                # REFERENCE: The "AES-128-CTR_CMAC-64-AAD" mode MUST be supported by all devices implementing
                # the "USB" or "USB_KV" protocols.
                #
                # for USB, USB_KV adaptations the AES-128-CTR_CMAC-64-AAD mode MUST be supported
                if "AES-128-CTR_CMAC-64-AAD" not in enums:
                    msg = "{} {} : {} constraint value must allow 'AES-128-CTR_CMAC-64-AAD' for protocol {}".format(
                        identity, sender_receiver["id"], privacy_mode, constraints[privacy_protocol]["enum"])
                    return False, msg

                # REFERENCE: The mode parameter MUST be one of the following: "AES-128-CTR_CMAC-64-AAD",
                # "AES-256-CTR_CMAC-64-AAD", "ECDH_AES-128-CTR_CMAC-64-AAD", or "ECDH_AES-256-CTR_CMAC-64-AAD".
                #
                # for USB, USB_KV adaptations the mode MUST be on of the USB modes
                for c in enums:
                    if c not in allowed_usb_modes:
                        return False, "{} {} : {} constraint value must be one of {} for protocol {}".format(
                            identity, sender_receiver["id"], privacy_mode, allowed_usb_modes,
                            constraints[privacy_protocol]["enum"])

        # check that 'mode' staged and active values are within constraints
        if staged[privacy_mode] not in enums:
            return False, "{} {} : {} staged value {} is not within constraints {}".format(
                identity, sender_receiver["id"], privacy_mode, staged[privacy_mode], enums)
        if active[privacy_mode] not in enums:
            return False, "{} {} : {} active value {} is not within constraints {}".format(
                identity, sender_receiver["id"], privacy_mode, staged[privacy_mode], enums)

        if is_sender:
            # The iv parameter constraints MUST allow only one value an be properly formatted
            if "enum" not in constraints[privacy_iv]:
                return False, "{} {} : {} constraint must allow exactly one value for read-only parameters".format(
                    identity, sender_receiver["id"], privacy_iv)
            enums = constraints[privacy_iv]["enum"]
            if len(enums) != 1:
                return False, "{} {} : {} constraint must allow exactly one value for read-only parameters".format(
                    identity, sender_receiver["id"], privacy_iv)
            if not isinstance(enums[0], str):
                return False, "{} {} : {} constraint value must be string".format(
                    identity, sender_receiver["id"], privacy_iv)
            if len(enums[0]) != 16 or not all(char in "0123456789abcdefABCDEF" for char in enums[0]):
                return False, "{} {} : {} constraint must be a 64 bit hexadecimal value".format(
                    identity, sender_receiver["id"], privacy_iv)
            # check that staged and active values are within constraints
            if staged[privacy_iv] not in enums:
                return False, "{} {} : {} staged value {} is not within constraints {}".format(
                    identity, sender_receiver["id"], privacy_iv, staged[privacy_iv], enums)
            if active[privacy_iv] not in enums:
                return False, "{} {} : {} active value {} is not within constraints {}".format(
                    identity, sender_receiver["id"], privacy_iv, staged[privacy_iv], enums)
        else:
            # for the Receiver the iv parameter constraints SHOULD allow any value and internally verify for
            # proper size and hexadecimal
            if "enum" in constraints[privacy_iv]:
                warning += "|" + "{} {} : {} constraint should allow any value".format(
                    identity, sender_receiver["id"], privacy_iv)
            if "pattern" in constraints[privacy_iv] and constraints[privacy_iv]["pattern"] != "^[0-9a-fA-F]{16}$":
                warning += "|" + "{} {} : {} constraint pattern should be '^[0-9a-fA-F]{{16}}$'".format(
                    identity, sender_receiver["id"], privacy_iv)
            if len(staged[privacy_iv]) < 2 or not all(char in "0123456789abcdefABCDEF" for char in staged[privacy_iv]):
                return False, "{} {} : {} staged value {} is not within constraints {}".format(
                    identity, sender_receiver["id"], privacy_iv, staged[privacy_iv], enums)
            if len(active[privacy_iv]) < 2 or not all(char in "0123456789abcdefABCDEF" for char in active[privacy_iv]):
                return False, "{} {} : {} active value {} is not within constraints {}".format(
                    identity, sender_receiver["id"], privacy_iv, staged[privacy_iv], enums)

        if is_sender:
            # The key_generator parameter constraints MUST allow only one value an be properly formatted
            if "enum" not in constraints[privacy_key_generator]:
                return False, "{} {} : {} constraint must allow exactly one value for read-only parameters".format(
                    identity, sender_receiver["id"], privacy_key_generator)
            enums = constraints[privacy_key_generator]["enum"]
            if len(enums) != 1:
                return False, "{} {} : {} constraint must allow exactly one value for read-only parameters".format(
                    identity, sender_receiver["id"], privacy_key_generator)
            if not isinstance(enums[0], str):
                return False, "{} {} : {} constraint value must be string".format(
                    identity, sender_receiver["id"], privacy_key_generator)
            if len(enums[0]) != 32 or not all(char in "0123456789abcdefABCDEF" for char in enums[0]):
                return False, "{} {} : {} constraint must be a 128 bit hexadecimal value".format(
                    identity, sender_receiver["id"], privacy_key_generator)
        else:
            # for the Receiver the key_generator parameter constraints SHOULD allow any value and internally verify for
            #  proper size and hexadecimal
            if "enum" in constraints[privacy_key_generator]:
                warning += "|" + "{} {} : {} constraint should allow any value".format(
                    identity, sender_receiver["id"], privacy_key_generator)
            if ("pattern" in constraints[privacy_key_generator] and
                    constraints[privacy_key_generator]["pattern"] != "^[0-9a-fA-F]{32}$"):
                warning += "|" + "{} {} : {} constraint pattern should be '^[0-9a-fA-F]{{32}}$'".format(
                    identity, sender_receiver["id"], privacy_key_generator)
            if len(staged[privacy_key_generator]) < 2 or not all(char in "0123456789abcdefABCDEF"
                                                                 for char in staged[privacy_key_generator]):
                return False, "{} {} : {} staged value {} is not within constraints {}".format(
                    identity, sender_receiver["id"], privacy_key_generator, staged[privacy_key_generator], enums)
            if len(active[privacy_key_generator]) < 2 or not all(char in "0123456789abcdefABCDEF"
                                                                 for char in active[privacy_key_generator]):
                return False, "{} {} : {} active value {} is not within constraints {}".format(
                    identity, sender_receiver["id"], privacy_key_generator, staged[privacy_key_generator], enums)

        if is_sender:
            # The key_version parameter constraints MUST allow only one value an be properly formatted
            if "enum" not in constraints[privacy_key_version]:
                return False, "{} {} : {} constraint must allow exactly one value for read-only parameters".format(
                    identity, sender_receiver["id"], privacy_key_version)
            enums = constraints[privacy_key_version]["enum"]
            if len(enums) != 1:
                return False, "{} {} : {} constraint must allow exactly one value for read-only parameters".format(
                    identity, sender_receiver["id"], privacy_key_version)
            if not isinstance(enums[0], str):
                return False, "{} {} : {} constraint value must be string".format(
                    identity, sender_receiver["id"], privacy_key_version)
            if len(enums[0]) != 8 or not all(char in "0123456789abcdefABCDEF" for char in enums[0]):
                return False, "{} {} : {} constraint must be a 32 bit hexadecimal value".format(
                    identity, sender_receiver["id"], privacy_key_version)
        else:
            # for the Receiver the key_version parameter constraints SHOULD allow any value and internally verify for
            # proper size and hexadecimal
            if "enum" in constraints[privacy_key_version]:
                warning += "|" + "{} {} : {} constraint should allow any value".format(
                    identity, sender_receiver["id"], privacy_key_version)
            if ("pattern" in constraints[privacy_key_version]
                    and constraints[privacy_key_version]["pattern"] != "^[0-9a-fA-F]{8}$"):
                warning += "|" + "{} {} : {} constraint pattern should be '^[0-9a-fA-F]{{8}}$'".format(
                    identity, sender_receiver["id"], privacy_key_version)
            if len(staged[privacy_key_version]) < 2 or not all(char in "0123456789abcdefABCDEF"
                                                               for char in staged[privacy_key_version]):
                return False, "{} {} : {} staged value {} is not within constraints {}".format(
                    identity, sender_receiver["id"], privacy_key_version, staged[privacy_key_version], enums)
            if len(active[privacy_key_version]) < 2 or not all(char in "0123456789abcdefABCDEF"
                                                               for char in active[privacy_key_version]):
                return False, "{} {} : {} active value {} is not within constraints {}".format(
                    identity, sender_receiver["id"], privacy_key_version, staged[privacy_key_version], enums)

        if is_sender:
            # REFERENCE: Each Sender using privacy encryption MUST be associated with a provisioned
            # PSK via its key_id.
            #
            # The key_id parameter constraints MUST allow only one value an be properly formatted
            if "enum" not in constraints[privacy_key_id]:
                return False, "{} {} : {} constraint must allow exactly one value for read-only parameters".format(
                    identity, sender_receiver["id"], privacy_key_id)
            enums = constraints[privacy_key_id]["enum"]
            if len(enums) != 1:
                return False, "{} {} : {} constraint must allow exactly one value for read-only parameters".format(
                    identity, sender_receiver["id"], privacy_key_id)
            if not isinstance(enums[0], str):
                return False, "{} {} : {} constraint value must be string".format(
                    identity, sender_receiver["id"], privacy_key_id)
            if len(enums[0]) != 16 or not all(char in "0123456789abcdefABCDEF" for char in enums[0]):
                return False, "{} {} : {} constraint must be a 64 bit hexadecimal value".format(
                    identity, sender_receiver["id"], privacy_key_id)

            # REFERENCE: A Sender MUST populate the ext_privacy_key_id extended transport parameter in
            # the IS-05 active, staged and constraints endpoints with the key_id of its associated PSK.
            #
            # check that 'privacy_key_id' staged and active values are within constraints
            if staged[privacy_key_id] not in enums:
                return False, "{} {} : {} staged value {} is not within constraints {}".format(
                    identity, sender_receiver["id"], privacy_key_id, staged[privacy_key_id], enums)
            if active[privacy_key_id] not in enums:
                msg = "{} {} : {} active value {} is not within constraints {}".format(
                    identity, sender_receiver["id"], privacy_key_id, staged[privacy_key_id], enums)
                return False, msg

        else:
            # REFERENCE: Each Receiver using privacy encryption MUST be associated with a set of
            # provisioned PSKs, identified by their key_id values.
            #
            # for a Receiver all known key_id MUST be listed
            if "enum" not in constraints[privacy_key_id]:
                return False, "{} {} : {} constraint must allow at least one value".format(
                    identity, sender_receiver["id"], privacy_key_id)
            enums = constraints[privacy_key_id]["enum"]
            if len(enums) == 0:
                return False, "{} {} : {} constraint must allow at least one value".format(
                    identity, sender_receiver["id"], privacy_key_id)
            #
            for c in enums:
                if not isinstance(c, str):
                    return False, "{} {} : {} constraint value must be string".format(
                        identity, sender_receiver["id"], privacy_key_id)
                if len(c) != 16 or not all(char in "0123456789abcdefABCDEF" for char in c):
                    return False, "{} {} : {} constraint must be a 64 bit hexadecimal value".format(
                        identity, sender_receiver["id"], privacy_key_id)

            # REFERENCE: A Receiver MUST populate the ext_privacy_key_id extended transport parameter
            # in the IS-05 constraints endpoint with all acceptable key_id values. At activation time,
            # a Receiver using privacy encryption becomes associated with one of the provisioned PSKs
            # through the ext_privacy_key_id extended transport parameter.
            if master_enable:
                if staged[privacy_key_id] not in enums:
                    return False, "{} {} : {} staged value {} is not within constraints {}".format(
                        identity, sender_receiver["id"], privacy_key_id, staged[privacy_key_id], enums)
                if active[privacy_key_id] not in enums:
                    msg = "{} {} : {} active value {} is not within constraints {}".format(
                        identity, sender_receiver["id"], privacy_key_id, staged[privacy_key_id], enums)
                    return False, msg

        if elliptic:
            if ecdh:
                if is_sender:
                    if "enum" not in constraints[privacy_ecdh_sender_public_key]:
                        msg = "{} {} : {} constraint must allow exactly one value for read-only parameters".format(
                            identity, sender_receiver["id"], privacy_ecdh_sender_public_key)
                        return False, msg
                    enums = constraints[privacy_ecdh_sender_public_key]["enum"]
                    if len(enums) != 1:
                        msg = "{} {} : {} constraint must allow exactly one value for read-only parameters".format(
                            identity, sender_receiver["id"], privacy_ecdh_sender_public_key)
                        return False, msg
                    if not isinstance(enums[0], str):
                        return False, "{} {} : {} constraint value must be string".format(
                            identity, sender_receiver["id"], privacy_ecdh_sender_public_key)
                    # check for minimum length of 2 for "00" but left the upper bound open as it depends on many factors
                    if len(enums[0]) < 2 or not all(char in "0123456789abcdefABCDEF" for char in enums[0]):
                        return False, "{} {} : {} constraint must be an hexadecimal value".format(
                            identity, sender_receiver["id"], privacy_ecdh_sender_public_key)
                else:
                    if "enum" in constraints[privacy_ecdh_sender_public_key]:
                        warning += "|" + "{} {} : {} constraint should allow any value".format(
                            identity, sender_receiver["id"], privacy_ecdh_sender_public_key)
                    if ("pattern" in constraints[privacy_ecdh_sender_public_key]
                            and constraints[privacy_ecdh_sender_public_key]["pattern"] != "^[0-9a-fA-F]{2,}$"):
                        warning += "|" + "{} {} : {} constraint pattern should be '^[0-9a-fA-F]{{2,}}$'".format(
                            identity, sender_receiver["id"], privacy_ecdh_sender_public_key)
                    if (len(staged[privacy_ecdh_sender_public_key]) < 2
                            or not all(char in "0123456789abcdefABCDEF"
                                       for char in staged[privacy_ecdh_sender_public_key])):
                        return False, "{} {} : {} staged value {} is not within constraints {}".format(
                            identity, sender_receiver["id"], privacy_ecdh_sender_public_key,
                            staged[privacy_ecdh_sender_public_key], enums)
                    if (len(active[privacy_ecdh_sender_public_key]) < 2
                            or not all(char in "0123456789abcdefABCDEF"
                                       for char in active[privacy_ecdh_sender_public_key])):
                        return False, "{} {} : {} active value {} is not within constraints {}".format(
                            identity, sender_receiver["id"], privacy_ecdh_sender_public_key,
                            staged[privacy_ecdh_sender_public_key], enums)

                if not is_sender:
                    if "enum" not in constraints[privacy_ecdh_receiver_public_key]:
                        msg = "{} {} : {} constraint must allow exactly one value for read-only parameters".format(
                            identity, sender_receiver["id"], privacy_ecdh_receiver_public_key)
                        return False, msg
                    enums = constraints[privacy_ecdh_receiver_public_key]["enum"]
                    if len(enums) != 1:
                        msg = "{} {} : {} constraint must allow exactly one value for read-only parameters".format(
                            identity, sender_receiver["id"], privacy_ecdh_receiver_public_key)
                        return False, msg
                    if not isinstance(enums[0], str):
                        return False, "{} {} : {} constraint value must be string".format(
                            identity, sender_receiver["id"], privacy_ecdh_receiver_public_key)
                    # check for minimum length of 2 for "00" but left the upper bound open as it depends on many factors
                    if len(enums[0]) < 2 or not all(char in "0123456789abcdefABCDEF" for char in enums[0]):
                        return False, "{} {} : {} constraint must be an hexadecimal value".format(
                            identity, sender_receiver["id"], privacy_ecdh_receiver_public_key)
                else:
                    if "enum" in constraints[privacy_ecdh_receiver_public_key]:
                        warning += "|" + "{} {} : {} constraint should allow any value".format(
                            identity, sender_receiver["id"], privacy_ecdh_receiver_public_key)
                    if ("pattern" in constraints[privacy_ecdh_receiver_public_key]
                            and constraints[privacy_ecdh_receiver_public_key]["pattern"] != "^[0-9a-fA-F]{2,}$"):
                        warning += "|" + "{} {} : {} constraint pattern should be '^[0-9a-fA-F]{{2,}}$'".format(
                            identity, sender_receiver["id"], privacy_ecdh_receiver_public_key)
                    if (len(staged[privacy_ecdh_receiver_public_key]) < 2
                            or not all(char in "0123456789abcdefABCDEF"
                                       for char in staged[privacy_ecdh_receiver_public_key])):
                        return False, "{} {} : {} staged value {} is not within constraints {}".format(
                            identity, sender_receiver["id"], privacy_ecdh_receiver_public_key,
                            staged[privacy_ecdh_receiver_public_key], enums)
                    if (len(active[privacy_ecdh_receiver_public_key]) < 2
                            or not all(char in "0123456789abcdefABCDEF"
                                       for char in active[privacy_ecdh_receiver_public_key])):
                        return False, "{} {} : {} active value {} is not within constraints {}".format(
                            identity, sender_receiver["id"], privacy_ecdh_receiver_public_key,
                            staged[privacy_ecdh_receiver_public_key], enums)
            else:
                # if the parameter is present but ECDH is not supported, then if a constraint is provided it
                # MUST be "00" or empty
                if "enum" in constraints[privacy_ecdh_sender_public_key]:
                    enums = constraints[privacy_ecdh_sender_public_key]["enum"]
                    if len(enums) > 1:
                        msg = "{} {} : {} constraint must not allow more than the 00 value" \
                              " for unsupported ECDH mode".format(
                                  identity, sender_receiver["id"], privacy_ecdh_sender_public_key)
                        return False, msg
                    if len(enums) != 0:
                        if not isinstance(enums[0], str):
                            return False, "{} {} : {} constraint value must be string".format(
                                identity, sender_receiver["id"], privacy_ecdh_sender_public_key)
                        if len(enums[0]) != 2 or not all(char in "0123456789abcdefABCDEF" for char in enums[0]):
                            return False, "{} {} : {} constraint must be an 8 bit hexadecimal null value".format(
                                identity, sender_receiver["id"], privacy_ecdh_sender_public_key)
                # if the parameter is present but ECDH is not supported, then if a constraint is provided it
                # MUST be "00" or empty
                if "enum" in constraints[privacy_ecdh_receiver_public_key]:
                    enums = constraints[privacy_ecdh_receiver_public_key]["enum"]
                    if len(enums) > 1:
                        msg = "{} {} : {} constraint must not allow more than the 00 value" \
                              " for unsupported ECDH mode".format(
                                  identity, sender_receiver["id"], privacy_ecdh_receiver_public_key)
                        return False, msg
                    if len(enums) != 0:
                        if not isinstance(enums[0], str):
                            return False, "{} {} : {} constraint value must be string".format(
                                identity, sender_receiver["id"], privacy_ecdh_receiver_public_key)
                        if len(enums[0]) != 2 or not all(char in "0123456789abcdefABCDEF" for char in enums[0]):
                            return False, "{} {} : {} constraint must be an 8 bit hexadecimal null value".format(
                                identity, sender_receiver["id"], privacy_ecdh_receiver_public_key)

        # a warning is a success with a message
        return True, warning

    def check_across_legs(self, is_sender, sender_receiver, constraints, staged, active, elliptic):

        warning = ""

        if is_sender:
            identity = "sender"
        else:
            identity = "receiver"

        if not isinstance(constraints, list) or not isinstance(staged, list) or not isinstance(active, list):
            raise Exception("expecting arrays")

        i = 0
        for leg in constraints:
            for k in leg.keys():
                if constraints[i][k] != constraints[0][k]:
                    return False, "{} {} : {} parameter constraints value of leg {} not matching leg 0".format(
                        identity, sender_receiver["id"], k, i)
                if staged[i][k] != staged[0][k]:
                    return False, "{} {} : {} staged parameter value of leg {} not matching leg 0".format(
                        identity, sender_receiver["id"], k, i)
                if active[i][k] != active[0][k]:
                    return False, "{} {} : {} staged parameter value of leg {} not matching leg 0".format(
                        identity, sender_receiver["id"], k, i)

            i += 1

        if warning == "":
            return True, ""
        else:
            return False, warning

    def check_privacy_attribute(self, is_sender, sender_receiver, legs, constraints, active, sdp_lines):

        if is_sender:
            identity = "sender"
        else:
            identity = "receiver"

        found_session = 0
        found_media = 0
        session_level = True

        for sdp_line in sdp_lines:

            media = re.search(r"^m=(.+)$", sdp_line)
            if media:
                session_level = False
                continue

            privacy = re.search(r"^a=privacy:(.+)$", sdp_line)
            if privacy:

                if session_level:
                    found_session += 1
                else:
                    found_media += 1

                sdp_privacy_params = {}
                for param in privacy.group(1).split(";"):
                    name, _, value = param.strip().partition("=")
                    if name not in [sdp_privacy_protocol, sdp_privacy_mode, sdp_privacy_iv, sdp_privacy_key_generator,
                                    sdp_privacy_key_version, sdp_privacy_key_id]:
                        return False, "{} {} : privacy attribute parameter {} is invalid".format(
                            identity, sender_receiver["id"], name)
                    sdp_privacy_params[name] = value

                # check against constraints
                if sdp_privacy_params[sdp_privacy_protocol] not in constraints[privacy_protocol]["enum"]:
                    return False, "{} {} : privacy attribute parameter {} value {} is not within constraints {}".format(
                        identity, sender_receiver["id"], name, sdp_privacy_params[sdp_privacy_protocol],
                        constraints[privacy_protocol]["enum"])
                if sdp_privacy_params[sdp_privacy_mode] not in constraints[privacy_mode]["enum"]:
                    return False, "{} {} : privacy attribute parameter {} value {} is not within constraints {}".format(
                        identity, sender_receiver["id"], name, sdp_privacy_params[sdp_privacy_mode],
                        constraints[privacy_mode]["enum"])
                if sdp_privacy_params[sdp_privacy_key_id] not in constraints[privacy_key_id]["enum"]:
                    return False, "{} {} : privacy attribute parameter {} value {} is not within constraints {}".format(
                        identity, sender_receiver["id"], name, sdp_privacy_params[sdp_privacy_key_id],
                        constraints[privacy_key_id]["enum"])

                if is_sender:
                    if sdp_privacy_params[sdp_privacy_iv] not in constraints[privacy_iv]["enum"]:
                        msg = "{} {} : privacy attribute parameter {} value {} is not within constraints {}".format(
                            identity, sender_receiver["id"], name, sdp_privacy_params[sdp_privacy_iv],
                            constraints[privacy_iv]["enum"])
                        return False, msg
                    if sdp_privacy_params[sdp_privacy_key_generator] not in constraints[privacy_key_generator]["enum"]:
                        msg = "{} {} : privacy attribute parameter {} value {} is not within constraints {}".format(
                            identity, sender_receiver["id"], name, sdp_privacy_params[sdp_privacy_key_generator],
                            constraints[privacy_key_generator]["enum"])
                        return False, msg
                    if sdp_privacy_params[sdp_privacy_key_version] not in constraints[privacy_key_version]["enum"]:
                        msg = "{} {} : privacy attribute parameter {} value {} is not within constraints {}".format(
                            identity, sender_receiver["id"], name, sdp_privacy_params[sdp_privacy_key_version],
                            constraints[privacy_key_version]["enum"])
                        return False, msg
                else:
                    if (len(sdp_privacy_params[sdp_privacy_iv]) != 16
                        or not all(char in "0123456789abcdefABCDEF"
                                   for char in sdp_privacy_params[sdp_privacy_iv])):
                        return False, "{} {} : privacy attribute parameter {} value {} is not valid".format(
                            identity, sender_receiver["id"], name, sdp_privacy_params[sdp_privacy_iv])
                    if (len(sdp_privacy_params[sdp_privacy_key_generator]) != 32
                        or not all(char in "0123456789abcdefABCDEF"
                                   for char in sdp_privacy_params[sdp_privacy_key_generator])):
                        return False, "{} {} : privacy attribute parameter {} value {} is not valid".format(
                            identity, sender_receiver["id"], name, sdp_privacy_params[sdp_privacy_key_generator])
                    if (len(sdp_privacy_params[sdp_privacy_key_version]) != 8
                        or not all(char in "0123456789abcdefABCDEF"
                                   for char in sdp_privacy_params[sdp_privacy_key_version])):
                        return False, "{} {} : privacy attribute parameter {} value {} is not valid".format(
                            identity, sender_receiver["id"], name, sdp_privacy_params[sdp_privacy_key_version])

                # check against active values
                if sdp_privacy_params[sdp_privacy_protocol] != active[privacy_protocol]:
                    msg = "{} {} : privacy attribute parameter {} value {} is not matching active value {}".format(
                        identity, sender_receiver["id"], name, sdp_privacy_params[sdp_privacy_protocol],
                        active[privacy_protocol])
                    return False, msg
                if sdp_privacy_params[sdp_privacy_mode] != active[privacy_mode]:
                    msg = "{} {} : privacy attribute parameter {} value {} is not matching active value {}".format(
                        identity, sender_receiver["id"], name, sdp_privacy_params[sdp_privacy_mode],
                        active[privacy_mode])
                    return False, msg
                if sdp_privacy_params[sdp_privacy_key_id] != active[privacy_key_id]:
                    msg = "{} {} : privacy attribute parameter {} value {} is not matching active value {}".format(
                        identity, sender_receiver["id"], name, sdp_privacy_params[sdp_privacy_key_id],
                        active[privacy_key_id])
                    return False, msg
                if sdp_privacy_params[sdp_privacy_iv] != active[privacy_iv]:
                    msg = "{} {} : privacy attribute parameter {} value {} is not matching active value {}".format(
                        identity, sender_receiver["id"], name, sdp_privacy_params[sdp_privacy_iv], active[privacy_iv])
                    return False, msg
                if sdp_privacy_params[sdp_privacy_key_generator] != active[privacy_key_generator]:
                    msg = "{} {} : privacy attribute parameter {} value {} is not matching active value {}".format(
                        identity, sender_receiver["id"], name, sdp_privacy_params[sdp_privacy_key_generator],
                        active[privacy_key_generator])
                    return False, msg
                if sdp_privacy_params[sdp_privacy_key_version] != active[privacy_key_version]:
                    msg = "{} {} : privacy attribute parameter {} value {} is not matching active value {}".format(
                        identity, sender_receiver["id"], name, sdp_privacy_params[sdp_privacy_key_version],
                        active[privacy_key_version])
                    return False, msg

        if ((found_session > 1) or (found_media != 0 and found_media != legs)
                or (found_session == 0 and found_media == 0)):
            msg = "{} {} : missing privacy session/media attribute(s) in SDP transport file, " \
                "found {} session level, {} media level, has {} legs".format(
                    identity, sender_receiver["id"], found_session, found_media, legs)
            return False, msg

        # check RTP extension headers for RTP protocol adaptation
        if active[privacy_protocol] in ("RTP", "RTP_KV"):

            found_short = False
            found_full = False

            for sdp_line in sdp_lines:
                extmap = re.search(r"^a=extmap:[0-9]+/([a-z]+) (.+)$", sdp_line)
                if extmap:
                    if (extmap.group(1) != "sendonly"
                        and (extmap.group(2) == "urn:ietf:params:rtp-hdrext:PEP-Full-IV-Counter"
                             or extmap.group(2) != "urn:ietf:params:rtphdrext:PEP-Short-IV-Counter"
                             or extmap.group(2) == "urn:ietf:params:rtp-hdrext:HDCP-Full-IV-Counter-metadata"
                             or extmap.group(2) != "urn:ietf:params:rtphdrext:HDCP-Short-IV-Counter-metadata")):
                        return False, "{} {} : extmap is invalid, direction is {} and must be sendonly.".format(
                            identity, sender_receiver["id"], extmap.group(1))
                    if (extmap.group(2) == "urn:ietf:params:rtp-hdrext:PEP-Full-IV-Counter"
                            or extmap.group(2) == "urn:ietf:params:rtp-hdrext:HDCP-Full-IV-Counter-metadata"):
                        found_full = True
                    if (extmap.group(2) == "urn:ietf:params:rtp-hdrext:PEP-Short-IV-Counter"
                            or extmap.group(2) == "urn:ietf:params:rtp-hdrext:HDCP-Short-IV-Counter-metadata"):
                        found_short = True

            # This is a SHOULD for VSF/PEP specification made MUST by the NMOS specification to
            # enhance interoperability.
            if not found_short or not found_full:
                return False, "{} {} : extmap attributes for PEP extension headers are missing".format(
                    identity, sender_receiver["id"])

        return True, ""


# REFERENCE: A Sender/Receiver implementing TR-10-13 MUST provide the following extended transport parameters
# in the IS-05 active, staged and constraints endpoints: ext_privacy_protocol, ext_privacy_mode, ext_privacy_iv,
# ext_privacy_key_generator, ext_privacy_key_version, and ext_privacy_key_id. A Sender/Receiver implementing
# TR-10-13 and supporting ECDH modes MUST also provide the following extended transport parameters in the IS-05
# active, staged, and constraints endpoints: ext_privacy_ecdh_sender_public_key, ext_privacy_ecdh_receiver_public_key,
# and ext_privacy_ecdh_curve.
def checkSenderTransportParametersPEP(transport, constraints, staged, active):

    pep_required = ('ext_privacy_protocol', 'ext_privacy_mode', 'ext_privacy_iv', 'ext_privacy_key_generator',
                    'ext_privacy_key_version', 'ext_privacy_key_id')
    ecdh_required = ('ext_privacy_ecdh_sender_public_key', 'ext_privacy_ecdh_receiver_public_key',
                     'ext_privacy_ecdh_curve')

    for k in constraints.keys():
        if k.startswith("ext_privacy_"):
            for p in pep_required:
                if p not in constraints.keys():
                    return False, "required transport parameter {} not found in constraints".format(p)
                if p not in staged.keys():
                    return False, "required transport parameter {} not found in staged".format(p)
                if p not in active.keys():
                    return False, "required transport parameter {} not found in active".format(p)

            protocols = getPrivacyProtocolFromTransport(transport)

            if staged["ext_privacy_protocol"] not in protocols:
                return False, "invalid PEP protocol {}, expecting one of {} ".format(
                    staged["ext_privacy_protocol"], protocols)
            if active["ext_privacy_protocol"] not in protocols:
                return False, "invalid PEP protocol {}, expecting one of {} ".format(
                    active["ext_privacy_protocol"], protocols)

            break  # check once

    for k in constraints.keys():
        if k.startswith("ext_privacy_ecdh_"):
            for p in ecdh_required:
                if p not in constraints.keys():
                    return False, "required transport parameter {} not found in constraints".format(p)
                if p not in staged.keys():
                    return False, "required transport parameter {} not found in staged".format(p)
                if p not in active.keys():
                    return False, "required transport parameter {} not found in active".format(p)
            break  # check once

    return True, None


# REFERENCE: A Sender/Receiver implementing TR-10-13 MUST provide the following extended transport parameters
# in the IS-05 active, staged and constraints endpoints: ext_privacy_protocol, ext_privacy_mode, ext_privacy_iv,
# ext_privacy_key_generator, ext_privacy_key_version, and ext_privacy_key_id. A Sender/Receiver implementing
# TR-10-13 and supporting ECDH modes MUST also provide the following extended transport parameters in the IS-05
# active, staged, and constraints endpoints: ext_privacy_ecdh_sender_public_key, ext_privacy_ecdh_receiver_public_key,
# and ext_privacy_ecdh_curve.
def checkReceiverTransportParametersPEP(transport, constraints, staged, active):

    pep_required = ('ext_privacy_protocol', 'ext_privacy_mode', 'ext_privacy_iv', 'ext_privacy_key_generator',
                    'ext_privacy_key_version', 'ext_privacy_key_id')
    ecdh_required = ('ext_privacy_ecdh_sender_public_key', 'ext_privacy_ecdh_receiver_public_key',
                     'ext_privacy_ecdh_curve')

    for k in constraints.keys():
        if k.startswith("ext_privacy_"):
            for p in pep_required:
                if p not in constraints.keys():
                    return False, "required transport parameter {} not found in constraints".format(p)
                if p not in staged.keys():
                    return False, "required transport parameter {} not found in staged".format(p)
                if p not in active.keys():
                    return False, "required transport parameter {} not found in active".format(p)

            protocols = getPrivacyProtocolFromTransport(transport)

            if staged["ext_privacy_protocol"] not in protocols:
                return False, "invalid PEP protocol {}, expecting one of {} ".format(
                    staged["ext_privacy_protocol"], protocols)
            if active["ext_privacy_protocol"] not in protocols:
                return False, "invalid PEP protocol {}, expecting one of {} ".format(
                    active["ext_privacy_protocol"], protocols)

            break  # check once

    for k in constraints.keys():
        if k.startswith("ext_privacy_ecdh_"):
            for p in ecdh_required:
                if p not in constraints.keys():
                    return False, "required transport parameter {} not found in constraints".format(p)
                if p not in staged.keys():
                    return False, "required transport parameter {} not found in staged".format(p)
                if p not in active.keys():
                    return False, "required transport parameter {} not found in active".format(p)
            break  # check once

    return True, None


def getPrivacyProtocolFromTransport(transport):

    transport = urn_without_namespace(transport)

    if transport in ('transport:ndi'):
        return ("NULL")
    elif transport in ('transport:usb'):
        return ("NULL", "USB", "USB_KV")
    elif transport in ('transport:rtp', 'transport:rtp.mcast', 'transport:rtp.ucast'):
        return ("NULL", "RTP", "RTP_KV")

    return None
