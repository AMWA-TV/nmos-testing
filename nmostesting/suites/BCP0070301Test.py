# Copyright (C) 2026 Advanced Media Workflow Association
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
import os
import re
from copy import deepcopy
from pathlib import Path

from jsonschema import ValidationError

from ..GenericTest import GenericTest, NMOSTestException, requires_api_version
from ..IS05Utils import IS05Utils
from ..TestHelper import load_resolved_schema

NODE_API_KEY = "node"
CONN_API_KEY = "connection"
RECEIVER_CAPS_KEY = "receiver-caps"
CAPS_REGISTER_KEY = "caps-register"
FORMATS_REGISTER_KEY = "formats-register"
MEDIA_TYPES_REGISTER_KEY = "media-types-register"
MXL_SCHEMA_KEY = "mxl-schemas"

MXL_TRANSPORT = "urn:x-nmos:transport:mxl"
_MXL_TP_PARAMS = ("mxl_domain_id", "mxl_flow_id")
_PATCH_OK = frozenset((200, 202))


class BCP0070301Test(GenericTest):
    """
    Runs BCP-007-03-01 Tests
    """

    def __init__(self, apis, **kwargs):
        omit_paths = [
            "/single/senders/{senderId}/transportfile",
        ]
        GenericTest.__init__(self, apis, omit_paths, **kwargs)
        self.node_url = self.apis[NODE_API_KEY]["url"]
        self.connection_url = self.apis[CONN_API_KEY]["url"]
        self.is05_utils = IS05Utils(self.connection_url)
        self.is04_resources = {
            "senders": [],
            "receivers": [],
            "_requested": [],
            "sources": [],
            "flows": [],
        }

    # Utility function from IS0502Test
    def get_is04_resources(self, resource_type):
        """Retrieve all Senders or Receivers from a Node API, keeping hold of the returned objects"""
        assert resource_type in ["senders", "receivers", "sources", "flows"]

        # Prevent this being executed twice in one test run
        if resource_type in self.is04_resources["_requested"]:
            return True, ""

        valid, resources = self.do_request("GET", self.node_url + resource_type)
        if not valid:
            return False, f"Node API did not respond as expected: {resources}"

        try:
            for resource in resources.json():
                self.is04_resources[resource_type].append(resource)
            self.is04_resources["_requested"].append(resource_type)
        except json.JSONDecodeError:
            return False, "Non-JSON response returned from Node API"

        return True, ""

    def _mxl_senders(self):
        return [s for s in self.is04_resources["senders"] if s.get("transport") == MXL_TRANSPORT]

    def _mxl_receivers(self):
        return [r for r in self.is04_resources["receivers"] if r.get("transport") == MXL_TRANSPORT]

    def _flow_map(self):
        return {f["id"]: f for f in self.is04_resources["flows"]}

    def _source_map(self):
        return {s["id"]: s for s in self.is04_resources["sources"]}

    def _mxl_flow_ids(self, flow_map=None):
        flow_map = flow_map or self._flow_map()
        return {
            sender["flow_id"]
            for sender in self._mxl_senders()
            if sender.get("flow_id") in flow_map
        }

    def _mxl_source_ids(self, flow_map=None):
        flow_map = flow_map or self._flow_map()
        return {
            flow_map[flow_id]["source_id"]
            for flow_id in self._mxl_flow_ids(flow_map)
            if flow_map[flow_id].get("source_id")
        }

    def _require_is04_resources(self, test, *resource_types):
        for resource_type in resource_types:
            valid, result = self.get_is04_resources(resource_type)
            if not valid:
                raise NMOSTestException(test.FAIL(result))

    def _validate_schema_or_fail(self, test, value, schema, message, doc_url=None):
        try:
            self.validate_schema(value, schema)
        except ValidationError as e:
            if doc_url:
                raise NMOSTestException(test.FAIL(f"{message}: {e}", doc_url))
            raise NMOSTestException(test.FAIL(f"{message}: {e}"))

    def _validate_register_value(self, test, value, schema, reg_api, html_path, message):
        doc_url = (f"https://specs.amwa.tv/nmos-parameter-registers/branches/"
                   f"{reg_api['spec_branch']}{html_path}")
        self._validate_schema_or_fail(test, value, schema, message, doc_url)

    def _fetch_mxl_senders(self, test):
        valid, result = self.get_is04_resources("senders")
        if not valid:
            raise NMOSTestException(test.FAIL(result))
        return self._mxl_senders()

    def _fetch_mxl_receivers(self, test):
        valid, result = self.get_is04_resources("receivers")
        if not valid:
            raise NMOSTestException(test.FAIL(result))
        return self._mxl_receivers()

    def _iter_sampled_mxl_connection_resources(self, mxl_senders, mxl_receivers):
        for kind, resources in (("sender", mxl_senders), ("receiver", mxl_receivers)):
            for resource in self.is05_utils.sampled_list(resources):
                yield kind, resource["id"]

    @staticmethod
    def _fail_unless_single_constraints_leg(test, constraints, kind, resource_id):
        if not isinstance(constraints, list) or len(constraints) != 1:
            raise NMOSTestException(
                test.FAIL(f"{kind} {resource_id} must expose exactly one constraints leg"))

    def _transport_leg_from_data(self, test, data, kind, resource_id, label, *, require_mxl_keys=False):
        tp = data.get("transport_params", [])
        if not isinstance(tp, list) or len(tp) != 1 or not isinstance(tp[0], dict):
            raise NMOSTestException(
                test.FAIL(f"{kind} {resource_id} {label} transport_params must have one leg"))
        leg = tp[0]
        if require_mxl_keys and not self._leg_has_mxl_keys(leg):
            raise NMOSTestException(test.FAIL(
                f"{kind} {resource_id} {label} leg missing mxl_domain_id or mxl_flow_id"))
        return leg

    def _load_bcp00401_receiver_schemas(self):
        api = self.apis[RECEIVER_CAPS_KEY]
        reg_api = self.apis[CAPS_REGISTER_KEY]
        schema = load_resolved_schema(api["spec_path"], "receiver_constraint_sets.json")
        reg_schema_file = str(
            Path(os.path.abspath(reg_api["spec_path"])) / "capabilities/constraint_set.json")
        with open(reg_schema_file, "r") as f:
            reg_schema_obj = json.load(f)
        reg_schema = load_resolved_schema(api["spec_path"], schema_obj=reg_schema_obj)
        return schema, reg_schema

    def _check_mxl_interface_bindings(self, test, resource, kind):
        if resource.get("interface_bindings") != []:
            raise NMOSTestException(
                test.FAIL(f"{kind.capitalize()} {resource['id']} must have interface_bindings []"))

    def _patch_staged_expect(self, test, kind, resource_id, staged, overrides, *,
                             expect_accepted, fail_message, activate=False):
        patch_valid, response = self._patch_mxl_staged(
            kind, resource_id, staged, overrides, activate=activate)
        if not patch_valid:
            raise NMOSTestException(test.FAIL(str(response)))
        accepted = response.status_code in _PATCH_OK
        if expect_accepted and not accepted:
            raise NMOSTestException(test.FAIL(f"{fail_message}, got {response.status_code}"))
        if not expect_accepted and accepted:
            raise NMOSTestException(test.FAIL(fail_message))

    def _formats_register_schema(self):
        reg_path = os.path.join(self.apis[FORMATS_REGISTER_KEY]["spec_path"], "formats")
        return load_resolved_schema(reg_path, "format_register.json", path_prefix=False)

    def _media_types_register_schema(self):
        reg_path = os.path.join(self.apis[MEDIA_TYPES_REGISTER_KEY]["spec_path"], "media-types")
        return load_resolved_schema(reg_path, "media_type_register.json", path_prefix=False)

    @staticmethod
    def _leg_has_mxl_keys(leg):
        return isinstance(leg, dict) and "mxl_domain_id" in leg and "mxl_flow_id" in leg

    @staticmethod
    def _staged_value_satisfies_constraint(staged_val, constraint_entry):
        """Return True if staged_val satisfies an IS-05 constraint record.

        null and auto are permitted on staged by the transport parameter schema;
        constraints only further restrict concrete values (per BCP-007-03 / IS-05).
        """
        if staged_val is None or staged_val == "auto":
            return True
        if not isinstance(constraint_entry, dict):
            return True
        if "enum" in constraint_entry and staged_val not in constraint_entry["enum"]:
            return False
        if "minimum" in constraint_entry and isinstance(staged_val, (int, float)):
            if staged_val < constraint_entry["minimum"]:
                return False
        if "maximum" in constraint_entry and isinstance(staged_val, (int, float)):
            if staged_val > constraint_entry["maximum"]:
                return False
        if "pattern" in constraint_entry and isinstance(staged_val, str):
            if re.fullmatch(constraint_entry["pattern"], staged_val) is None:
                return False
        return True

    @staticmethod
    def _constraints_enum_lists_auto(leg):
        if not isinstance(leg, dict):
            return []
        return [param for param in _MXL_TP_PARAMS
                if isinstance(leg.get(param), dict)
                and "enum" in leg[param]
                and "auto" in leg[param]["enum"]]

    @staticmethod
    def _mxl_param_value_valid(value):
        """True if value is null (unconfigured) or a concrete resolved value."""
        return value is None or (isinstance(value, str) and value != "auto")

    @staticmethod
    def _staged_patch_body_omit_transport_file(staged):
        """Build a PATCH body from GET /staged, omitting transport_file.

        Unset activation objects (all-null fields from GET) are also omitted: many
        implementations reject them on PATCH even though MXL receivers must accept
        requests without transport_file.
        """
        body = {k: v for k, v in staged.items() if k != "transport_file"}
        activation = staged.get("activation")
        if isinstance(activation, dict) and all(v is None for v in activation.values()):
            body.pop("activation", None)
        return body

    @staticmethod
    def _connection_resource_path(kind, resource_id, suffix):
        return f"single/{kind}s/{resource_id}/{suffix}"

    def _patch_mxl_staged(self, kind, resource_id, staged, leg_overrides, activate=False):
        tp = deepcopy(staged.get("transport_params", []))
        if not tp or not isinstance(tp[0], dict):
            return False, "No transport_params leg to patch"
        tp[0].update(leg_overrides)
        body = self._staged_patch_body_omit_transport_file(staged)
        body["transport_params"] = tp
        if activate:
            body["activation"] = {"mode": "activate_immediate"}
        url = self.connection_url + self._connection_resource_path(kind, resource_id, "staged/")
        return self.do_request("PATCH", url, json=body)

    def _mxl_transport_schemas(self):
        mxl_path = self.apis[MXL_SCHEMA_KEY]["spec_path"]
        return (
            load_resolved_schema(mxl_path, "sender_transport_params_mxl.json"),
            load_resolved_schema(mxl_path, "receiver_transport_params_mxl.json"),
        )

    def _get_constraints(self, kind, resource_id):
        path = self._connection_resource_path(kind, resource_id, "constraints/")
        return self.is05_utils.checkCleanRequestJSON("GET", path)

    def _get_staged(self, kind, resource_id):
        path = self._connection_resource_path(kind, resource_id, "staged/")
        return self.is05_utils.checkCleanRequestJSON("GET", path)

    def _get_active(self, kind, resource_id):
        path = self._connection_resource_path(kind, resource_id, "active/")
        return self.is05_utils.checkCleanRequestJSON("GET", path)

    def _require_constraints(self, test, kind, resource_id):
        valid, constraints = self._get_constraints(kind, resource_id)
        if not valid:
            raise NMOSTestException(test.FAIL(f"constraints: {constraints}"))
        return constraints

    def _require_staged(self, test, kind, resource_id):
        valid, staged = self._get_staged(kind, resource_id)
        if not valid:
            raise NMOSTestException(test.FAIL(f"staged: {staged}"))
        return staged

    def _require_active(self, test, kind, resource_id):
        valid, active = self._get_active(kind, resource_id)
        if not valid:
            raise NMOSTestException(test.FAIL(f"active: {active}"))
        return active

    @requires_api_version(NODE_API_KEY, "v1.3")
    def test_02(self, test):
        """Node exposes Source, Flow and Sender resources for each MXL writer"""

        self._require_is04_resources(test, "senders", "flows", "sources")

        flow_map = self._flow_map()
        source_map = self._source_map()

        mxl_senders = self._mxl_senders()
        if not mxl_senders:
            return test.UNCLEAR("No MXL Sender resources found")

        for sender in self.is05_utils.sampled_list(mxl_senders):
            flow_id = sender.get("flow_id")
            if not flow_id:
                return test.FAIL(f"MXL Sender {sender['id']} has no flow_id")
            flow = flow_map.get(flow_id)
            if not flow:
                return test.FAIL(f"MXL Sender {sender['id']} flow_id {flow_id} not found in Flows")
            source_id = flow.get("source_id")
            if not source_id:
                return test.FAIL(f"Flow {flow['id']} has no source_id")
            if source_id not in source_map:
                return test.FAIL(f"Flow {flow['id']} source_id {source_id} not found in Sources")

        return test.PASS()

    @requires_api_version(NODE_API_KEY, "v1.3")
    def test_03(self, test):
        """MXL Flow format and media_type use NMOS parameter register values"""

        format_schema = self._formats_register_schema()
        media_type_schema = self._media_types_register_schema()
        formats_reg = self.apis[FORMATS_REGISTER_KEY]
        media_types_reg = self.apis[MEDIA_TYPES_REGISTER_KEY]

        self._require_is04_resources(test, "senders", "flows")

        flow_map = self._flow_map()
        mxl_flow_ids = self._mxl_flow_ids(flow_map)
        if not mxl_flow_ids:
            return test.UNCLEAR("No Flows linked from MXL Senders")

        for flow_id in self.is05_utils.sampled_list(list(mxl_flow_ids)):
            flow = flow_map[flow_id]
            self._validate_register_value(
                test, flow.get("format"), format_schema, formats_reg,
                "/formats/format_register.html",
                f"Flow {flow['id']} has invalid or missing 'format' for the formats register")
            self._validate_register_value(
                test, flow.get("media_type"), media_type_schema, media_types_reg,
                "/media-types/media_type_register.html",
                f"Flow {flow['id']} 'media_type' must be a registered media type string")

        return test.PASS()

    @requires_api_version(NODE_API_KEY, "v1.3")
    def test_04(self, test):
        """MXL Source format uses a value from the NMOS formats parameter register"""

        format_schema = self._formats_register_schema()
        formats_reg = self.apis[FORMATS_REGISTER_KEY]

        self._require_is04_resources(test, "senders", "flows", "sources")

        source_map = self._source_map()
        source_ids = self._mxl_source_ids()
        if not source_ids:
            return test.UNCLEAR("No Sources linked from MXL Senders")

        for source_id in self.is05_utils.sampled_list(list(source_ids)):
            src = source_map.get(source_id)
            if not src:
                return test.FAIL(f"Source {source_id} not found")
            self._validate_register_value(
                test, src.get("format"), format_schema, formats_reg,
                "/formats/format_register.html",
                f"Source {source_id} has invalid or missing 'format' for the formats register")

        return test.PASS()

    @requires_api_version(NODE_API_KEY, "v1.3")
    def test_05(self, test):
        """MXL Sender transport, interface_bindings and manifest_href are correct"""

        mxl_senders = self._fetch_mxl_senders(test)
        if not mxl_senders:
            return test.UNCLEAR("No MXL Sender resources found")

        for sender in self.is05_utils.sampled_list(mxl_senders):
            self._check_mxl_interface_bindings(test, sender, "sender")
            if "manifest_href" not in sender:
                return test.FAIL(f"Sender {sender['id']} missing manifest_href")
            if sender.get("manifest_href") is not None:
                return test.FAIL(f"Sender {sender['id']} manifest_href must be null for MXL")

        return test.PASS()

    @requires_api_version(CONN_API_KEY, "v1.2")
    @requires_api_version(NODE_API_KEY, "v1.3")
    def test_06(self, test):
        """MXL IS-05 Sender transportfile endpoint returns 404"""

        mxl_senders = self._fetch_mxl_senders(test)
        if not mxl_senders:
            return test.UNCLEAR("No MXL Sender resources found")

        for sender in self.is05_utils.sampled_list(mxl_senders):
            url = self.connection_url + f"single/senders/{sender['id']}/transportfile"
            request_valid, response = self.do_request("GET", url)
            if not request_valid:
                return test.FAIL(f"Request failed for {url}: {response}")
            if response.status_code != 404:
                return test.FAIL(f"MXL Sender {sender['id']} transportfile must return 404, got "
                                 f"{response.status_code}")

        return test.PASS()

    @requires_api_version(NODE_API_KEY, "v1.3")
    def test_07(self, test):
        """MXL Receiver transport, interface_bindings, format and media_type are correct"""

        format_schema = self._formats_register_schema()
        media_type_schema = self._media_types_register_schema()
        formats_reg = self.apis[FORMATS_REGISTER_KEY]
        media_types_reg = self.apis[MEDIA_TYPES_REGISTER_KEY]

        receivers = self._fetch_mxl_receivers(test)
        if not receivers:
            return test.UNCLEAR("No MXL Receiver resources found")

        for receiver in self.is05_utils.sampled_list(receivers):
            self._check_mxl_interface_bindings(test, receiver, "receiver")
            self._validate_register_value(
                test, receiver.get("format"), format_schema, formats_reg,
                "/formats/format_register.html",
                f"Receiver {receiver['id']} has invalid 'format' for the formats register")
            mts = receiver.get("caps", {}).get("media_types")
            if not isinstance(mts, list) or len(mts) < 1:
                return test.FAIL(f"Receiver {receiver['id']} caps.media_types must have at least one entry")
            for mt in mts:
                self._validate_register_value(
                    test, mt, media_type_schema, media_types_reg,
                    "/media-types/media_type_register.html",
                    f"Receiver {receiver['id']} caps.media_types contains invalid entry")

        return test.PASS()

    @requires_api_version(NODE_API_KEY, "v1.3")
    def test_08(self, test):
        """Receiver declares BCP-004-01 constraints"""

        receivers = self._fetch_mxl_receivers(test)
        if not receivers:
            return test.UNCLEAR("No MXL Receiver resources found")

        schema, reg_schema = self._load_bcp00401_receiver_schemas()

        for receiver in self.is05_utils.sampled_list(receivers):
            caps = receiver.get("caps", {})
            if "constraint_sets" not in caps:
                return test.FAIL(f"Receiver {receiver['id']} must include caps.constraint_sets per BCP-004-01")
            self._validate_schema_or_fail(
                test, receiver, schema,
                f"Receiver {receiver['id']} does not comply with BCP-004-01 schema")
            for constraint_set in caps["constraint_sets"]:
                self._validate_schema_or_fail(
                    test, constraint_set, reg_schema,
                    f"Receiver {receiver['id']} constraint_set invalid vs capabilities register")
                found_param = any(
                    not key.startswith("urn:x-nmos:cap:meta:") for key in constraint_set
                )
                if not found_param:
                    return test.FAIL(f"Receiver {receiver['id']} has a constraint set without parameter constraints")

        return test.PASS()

    @requires_api_version(CONN_API_KEY, "v1.2")
    @requires_api_version(NODE_API_KEY, "v1.3")
    def test_10(self, test):
        """MXL Sender and Receiver transport parameters are correct"""

        mxl_senders = self._fetch_mxl_senders(test)
        mxl_receivers = self._fetch_mxl_receivers(test)
        if not mxl_senders and not mxl_receivers:
            return test.UNCLEAR("No MXL Senders or Receivers found")

        for kind, resource_id in self._iter_sampled_mxl_connection_resources(mxl_senders, mxl_receivers):
            constraints = self._require_constraints(test, kind, resource_id)
            self._fail_unless_single_constraints_leg(test, constraints, kind, resource_id)
            if not self._leg_has_mxl_keys(constraints[0]):
                return test.FAIL(f"{kind} {resource_id} constraints[0] missing mxl_domain_id or mxl_flow_id")

            for label, data in (
                ("staged", self._require_staged(test, kind, resource_id)),
                ("active", self._require_active(test, kind, resource_id)),
            ):
                self._transport_leg_from_data(
                    test, data, kind, resource_id, label, require_mxl_keys=True)

        return test.PASS()

    @requires_api_version(CONN_API_KEY, "v1.2")
    @requires_api_version(NODE_API_KEY, "v1.3")
    def test_11(self, test):
        """Transport parameter payloads conform to BCP-007-03 MXL sender and receiver transport parameter schemas"""

        sender_schema, receiver_schema = self._mxl_transport_schemas()

        mxl_senders = self._fetch_mxl_senders(test)
        mxl_receivers = self._fetch_mxl_receivers(test)
        if not mxl_senders and not mxl_receivers:
            return test.UNCLEAR("No MXL Senders or Receivers found")

        schemas = {"sender": sender_schema, "receiver": receiver_schema}
        for kind, resource_id in self._iter_sampled_mxl_connection_resources(mxl_senders, mxl_receivers):
            for label, data in (
                ("staged", self._require_staged(test, kind, resource_id)),
                ("active", self._require_active(test, kind, resource_id)),
            ):
                for leg in data.get("transport_params", []):
                    self._validate_schema_or_fail(
                        test, leg, schemas[kind],
                        f"{kind} {resource_id} {label} transport_params schema")

        return test.PASS()

    @requires_api_version(CONN_API_KEY, "v1.2")
    @requires_api_version(NODE_API_KEY, "v1.3")
    def test_12(self, test):
        """Staged MXL parameters comply with transport schema and per-parameter IS-05 constraints"""

        mxl_senders = self._fetch_mxl_senders(test)
        mxl_receivers = self._fetch_mxl_receivers(test)
        if not mxl_senders and not mxl_receivers:
            return test.UNCLEAR("No MXL Senders or Receivers found")

        sender_schema, receiver_schema = self._mxl_transport_schemas()
        schemas = {"sender": sender_schema, "receiver": receiver_schema}
        for kind, resource_id in self._iter_sampled_mxl_connection_resources(mxl_senders, mxl_receivers):
            constraints = self._require_constraints(test, kind, resource_id)
            self._fail_unless_single_constraints_leg(test, constraints, kind, resource_id)

            staged = self._require_staged(test, kind, resource_id)
            leg = self._transport_leg_from_data(test, staged, kind, resource_id, "staged")

            self._validate_schema_or_fail(
                test, leg, schemas[kind],
                f"{kind} {resource_id} staged transport_params invalid vs transport schema")

            for param in _MXL_TP_PARAMS:
                if (isinstance(constraints[0].get(param), dict)
                        and not self._staged_value_satisfies_constraint(
                            leg.get(param), constraints[0][param])):
                    return test.FAIL(f"{kind} {resource_id} staged {param} value "
                                     f"{leg.get(param)!r} does not satisfy constraints")

        return test.PASS()

    @requires_api_version(CONN_API_KEY, "v1.2")
    @requires_api_version(NODE_API_KEY, "v1.3")
    def test_13(self, test):
        """Constraints MUST NOT list auto for mxl_domain_id or mxl_flow_id"""

        mxl_senders = self._fetch_mxl_senders(test)
        mxl_receivers = self._fetch_mxl_receivers(test)
        if not mxl_senders and not mxl_receivers:
            return test.UNCLEAR("No MXL Senders or Receivers found")

        for kind, resource_id in self._iter_sampled_mxl_connection_resources(mxl_senders, mxl_receivers):
            constraints = self._require_constraints(test, kind, resource_id)
            self._fail_unless_single_constraints_leg(test, constraints, kind, resource_id)
            auto_params = self._constraints_enum_lists_auto(constraints[0])
            if auto_params:
                return test.FAIL(f"{kind} {resource_id} constraints must not list auto for: "
                                 f"{', '.join(auto_params)}")

        return test.PASS()

    @requires_api_version(CONN_API_KEY, "v1.2")
    @requires_api_version(NODE_API_KEY, "v1.3")
    def test_14(self, test):
        """MXL IS-05 Receiver staged PATCH succeeds when transport_file is omitted from the request body"""

        receivers = self._fetch_mxl_receivers(test)
        if not receivers:
            return test.UNCLEAR("No MXL Receiver resources found")

        for receiver in self.is05_utils.sampled_list(receivers):
            resource_id = receiver["id"]
            staged = self._require_staged(test, "receiver", resource_id)
            body = self._staged_patch_body_omit_transport_file(staged)
            patch_valid, resp = self.do_request(
                "PATCH",
                self.connection_url + self._connection_resource_path("receiver", resource_id, "staged/"),
                json=body)
            if not patch_valid:
                return test.FAIL(f"PATCH failed: {resp}")
            if resp.status_code not in _PATCH_OK:
                return test.FAIL(f"PATCH staged without transport_file expected 200/202, got "
                                 f"{resp.status_code}")

        return test.PASS()

    @requires_api_version(CONN_API_KEY, "v1.2")
    @requires_api_version(NODE_API_KEY, "v1.3")
    def test_15(self, test):
        """MXL read/write starts or stops on activation."""

        return test.MANUAL("Whether MXL read/write starts or stops on activation cannot be verified"
                           " automatically by this tool")

    @requires_api_version(NODE_API_KEY, "v1.3")
    def test_16(self, test):
        """Node exposes Receiver resources for MXL readers in the IS-04 Node API"""

        receivers = self._fetch_mxl_receivers(test)
        if not receivers:
            return test.UNCLEAR("No MXL Receiver resources found")

        return test.PASS()

    @requires_api_version(CONN_API_KEY, "v1.2")
    @requires_api_version(NODE_API_KEY, "v1.3")
    def test_17(self, test):
        """MXL transport parameters use null when undetermined; active MUST NOT contain auto"""

        mxl_senders = self._fetch_mxl_senders(test)
        mxl_receivers = self._fetch_mxl_receivers(test)
        if not mxl_senders and not mxl_receivers:
            return test.UNCLEAR("No MXL Senders or Receivers found")

        for kind, resource_id in self._iter_sampled_mxl_connection_resources(mxl_senders, mxl_receivers):
            for label, data in (
                ("staged", self._require_staged(test, kind, resource_id)),
                ("active", self._require_active(test, kind, resource_id)),
            ):
                leg = self._transport_leg_from_data(test, data, kind, resource_id, label)
                for param in _MXL_TP_PARAMS:
                    if param not in leg:
                        return test.FAIL(f"{kind} {resource_id} {label} missing {param}")
                    if label == "active" and not self._mxl_param_value_valid(leg.get(param)):
                        return test.FAIL(f"{kind} {resource_id} active {param} must be null or a concrete value, "
                                         f"got {leg.get(param)!r}")

        return test.PASS()

    @requires_api_version(CONN_API_KEY, "v1.2")
    @requires_api_version(NODE_API_KEY, "v1.3")
    def test_18(self, test):
        """MXL Sender accepts null and resolvable auto for mxl_domain_id and mxl_flow_id"""

        senders = self._fetch_mxl_senders(test)
        if not senders:
            return test.UNCLEAR("No MXL Sender resources found")

        for sender in self.is05_utils.sampled_list(senders):
            sender_id = sender["id"]
            for param in _MXL_TP_PARAMS:
                staged = self._require_staged(test, "sender", sender_id)

                self._patch_staged_expect(
                    test, "sender", sender_id, staged, {param: None},
                    expect_accepted=True, fail_message=f"Sender {sender_id} must accept null for {param}")

                staged = self._require_staged(test, "sender", sender_id)

                self._patch_staged_expect(
                    test, "sender", sender_id, staged, {param: "auto"}, activate=True,
                    expect_accepted=True,
                    fail_message=f"Sender {sender_id} must accept auto for {param} when resolvable")

                active = self._require_active(test, "sender", sender_id)
                leg = self._transport_leg_from_data(test, active, "sender", sender_id, "active")
                if leg.get(param) == "auto":
                    return test.FAIL(f"Sender {sender_id} patched auto for {param} did not resolve on /active")

        return test.PASS()

    @requires_api_version(CONN_API_KEY, "v1.2")
    @requires_api_version(NODE_API_KEY, "v1.3")
    def test_19(self, test):
        """MXL Receiver null and auto semantics for mxl_domain_id and mxl_flow_id"""

        receivers = self._fetch_mxl_receivers(test)
        if not receivers:
            return test.UNCLEAR("No MXL Receiver resources found")

        for receiver in self.is05_utils.sampled_list(receivers):
            resource_id = receiver["id"]

            staged = self._require_staged(test, "receiver", resource_id)

            self._patch_staged_expect(
                test, "receiver", resource_id, staged, {"mxl_flow_id": None},
                expect_accepted=True, fail_message=f"Receiver {resource_id} must accept null for mxl_flow_id")

            staged = self._require_staged(test, "receiver", resource_id)

            self._patch_staged_expect(
                test, "receiver", resource_id, staged, {"mxl_flow_id": "auto"},
                expect_accepted=False, fail_message=f"Receiver {resource_id} must not accept auto for mxl_flow_id")

            staged = self._require_staged(test, "receiver", resource_id)

            self._patch_staged_expect(
                test, "receiver", resource_id, staged, {"mxl_domain_id": None},
                expect_accepted=True, fail_message=f"Receiver {resource_id} must accept null for mxl_domain_id")

            staged = self._require_staged(test, "receiver", resource_id)

            patch_valid, response = self._patch_mxl_staged(
                "receiver", resource_id, staged, {"mxl_domain_id": "auto"}, activate=True)
            if not patch_valid:
                return test.FAIL(str(response))
            if response.status_code in _PATCH_OK:
                active_valid, active = self._get_active("receiver", resource_id)
                if not active_valid:
                    return test.FAIL(str(active))
                leg = self._transport_leg_from_data(test, active, "receiver", resource_id, "active")
                if leg.get("mxl_domain_id") == "auto":
                    return test.FAIL(f"Receiver {resource_id} patched auto for mxl_domain_id "
                                     f"did not resolve on /active")

        return test.PASS()
