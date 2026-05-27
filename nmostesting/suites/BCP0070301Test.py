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

from .. import Config as CONFIG
from ..GenericTest import GenericTest, requires_api_version
from ..IS04Utils import IS04Utils
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
        self.is04_utils = IS04Utils(self.node_url)
        self.is05_utils = IS05Utils(self.connection_url)
        self.is04_resources = {
            "senders": [],
            "receivers": [],
            "_requested": [],
            "sources": [],
            "flows": [],
        }

    def get_is04_resources(self, resource_type):
        assert resource_type in ["senders", "receivers", "sources", "flows"]

        if resource_type in self.is04_resources["_requested"]:
            return True, ""

        valid, resources = self.do_request("GET", self.node_url + resource_type)
        if not valid:
            return False, f"Node API did not respond as expected: {resources}"

        try:
            self.is04_resources[resource_type].extend(resources.json())
            self.is04_resources["_requested"].append(resource_type)
        except json.JSONDecodeError:
            return False, "Non-JSON response returned from Node API"

        return True, ""

    def _mxl_senders(self):
        return [s for s in self.is04_resources["senders"] if s.get("transport") == MXL_TRANSPORT]

    def _mxl_receivers(self):
        return [r for r in self.is04_resources["receivers"] if r.get("transport") == MXL_TRANSPORT]

    def _apply_max_test_iteration_cap(self, items):
        n = CONFIG.MAX_TEST_ITERATIONS
        if n and n > 0:
            return items[:n]
        return items

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
    def _constraint_leg_has_mxl_keys(leg):
        if not isinstance(leg, dict):
            return False
        return "mxl_domain_id" in leg and "mxl_flow_id" in leg

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
    def _leg_values_contain_auto(legs):
        if not isinstance(legs, list):
            return False
        for leg in legs:
            if isinstance(leg, dict) and "auto" in leg.values():
                return True
        return False

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

    def _patch_mxl_staged(self, kind, resource_id, staged, leg_overrides, activate=False):
        base = f"single/{kind}s/{resource_id}/"
        tp = deepcopy(staged.get("transport_params", []))
        if not tp or not isinstance(tp[0], dict):
            return False, "No transport_params leg to patch"
        tp[0].update(leg_overrides)
        body = self._staged_patch_body_omit_transport_file(staged)
        body["transport_params"] = tp
        if activate:
            body["activation"] = {"mode": "activate_immediate"}
        return self.do_request("PATCH", self.connection_url + base + "staged/", json=body)

    def _get_staged(self, kind, resource_id):
        base = f"single/{kind}s/{resource_id}/"
        return self.is05_utils.checkCleanRequestJSON("GET", base + "staged/")

    def _get_active(self, kind, resource_id):
        base = f"single/{kind}s/{resource_id}/"
        return self.is05_utils.checkCleanRequestJSON("GET", base + "active/")

    @requires_api_version(NODE_API_KEY, "v1.3")
    def test_02(self, test):
        """Node exposes Source, Flow and Sender resources for each MXL writer"""

        for rt in ["senders", "flows", "sources"]:
            valid, result = self.get_is04_resources(rt)
            if not valid:
                return test.FAIL(result)

        flow_map = {f["id"]: f for f in self.is04_resources["flows"]}
        source_map = {s["id"]: s for s in self.is04_resources["sources"]}

        mxl_senders = self._mxl_senders()
        if not mxl_senders:
            return test.UNCLEAR("No MXL Sender resources found")

        for sender in self._apply_max_test_iteration_cap(mxl_senders):
            fid = sender.get("flow_id")
            if not fid:
                return test.FAIL(f"MXL Sender {sender['id']} has no flow_id")
            flow = flow_map.get(fid)
            if not flow:
                return test.FAIL(f"MXL Sender {sender['id']} flow_id {fid} not found in Flows")
            sid = flow.get("source_id")
            if not sid:
                return test.FAIL(f"Flow {flow['id']} has no source_id")
            if sid not in source_map:
                return test.FAIL(f"Flow {flow['id']} source_id {sid} not found in Sources")

        return test.PASS()

    @requires_api_version(NODE_API_KEY, "v1.3")
    def test_03(self, test):
        """MXL Flow format and media_type use NMOS parameter register values"""

        format_schema = self._formats_register_schema()
        media_type_schema = self._media_types_register_schema()
        formats_reg = self.apis[FORMATS_REGISTER_KEY]
        media_types_reg = self.apis[MEDIA_TYPES_REGISTER_KEY]

        for rt in ["senders", "flows"]:
            valid, result = self.get_is04_resources(rt)
            if not valid:
                return test.FAIL(result)

        flow_map = {f["id"]: f for f in self.is04_resources["flows"]}
        mxl_flow_ids = set()
        for sender in self._mxl_senders():
            fid = sender.get("flow_id")
            if fid and fid in flow_map:
                mxl_flow_ids.add(fid)

        if not mxl_flow_ids:
            return test.UNCLEAR("No Flows linked from MXL Senders")

        for fid in self._apply_max_test_iteration_cap(list(mxl_flow_ids)):
            flow = flow_map[fid]
            try:
                self.validate_schema(flow.get("format"), format_schema)
            except ValidationError as e:
                return test.FAIL(
                    f"Flow {flow['id']} has invalid or missing 'format' for the formats register: {e}",
                    f"https://specs.amwa.tv/nmos-parameter-registers/branches/{formats_reg['spec_branch']}/formats/",
                )
            try:
                self.validate_schema(flow.get("media_type"), media_type_schema)
            except ValidationError as e:
                return test.FAIL(
                    f"Flow {flow['id']} 'media_type' must be a registered media type string: {e}",
                    f"https://specs.amwa.tv/nmos-parameter-registers/branches/{media_types_reg['spec_branch']}/media-types/",
                )

        return test.PASS()

    @requires_api_version(NODE_API_KEY, "v1.3")
    def test_04(self, test):
        """MXL Source format uses a value from the NMOS formats parameter register"""

        format_schema = self._formats_register_schema()
        formats_reg = self.apis[FORMATS_REGISTER_KEY]

        for rt in ["senders", "flows", "sources"]:
            valid, result = self.get_is04_resources(rt)
            if not valid:
                return test.FAIL(result)

        flow_map = {f["id"]: f for f in self.is04_resources["flows"]}
        source_map = {s["id"]: s for s in self.is04_resources["sources"]}

        source_ids = set()
        for sender in self._mxl_senders():
            fid = sender.get("flow_id")
            if fid and fid in flow_map:
                sid = flow_map[fid].get("source_id")
                if sid:
                    source_ids.add(sid)

        if not source_ids:
            return test.UNCLEAR("No Sources linked from MXL Senders")

        for sid in self._apply_max_test_iteration_cap(list(source_ids)):
            src = source_map.get(sid)
            if not src:
                return test.FAIL(f"Source {sid} not found")
            try:
                self.validate_schema(src.get("format"), format_schema)
            except ValidationError as e:
                return test.FAIL(
                    f"Source {sid} has invalid or missing 'format' for the formats register: {e}",
                    f"https://specs.amwa.tv/nmos-parameter-registers/branches/{formats_reg['spec_branch']}/formats/",
                )

        return test.PASS()

    @requires_api_version(NODE_API_KEY, "v1.3")
    def test_05(self, test):
        """MXL Sender transport, interface_bindings and manifest_href are correct"""

        valid, result = self.get_is04_resources("senders")
        if not valid:
            return test.FAIL(result)

        mxl_senders = self._mxl_senders()
        if not mxl_senders:
            return test.UNCLEAR("No MXL Sender resources found")

        for sender in self._apply_max_test_iteration_cap(mxl_senders):
            if sender.get("transport") != MXL_TRANSPORT:
                return test.FAIL(f"Sender {sender['id']} must use transport {MXL_TRANSPORT}")
            ib = sender.get("interface_bindings")
            if not isinstance(ib, list) or ib != []:
                return test.FAIL(f"Sender {sender['id']} must have interface_bindings []")
            if "manifest_href" not in sender:
                return test.FAIL(f"Sender {sender['id']} missing manifest_href")
            if sender.get("manifest_href") is not None:
                return test.FAIL(f"Sender {sender['id']} manifest_href must be null for MXL")

        return test.PASS()

    @requires_api_version(CONN_API_KEY, "v1.2")
    @requires_api_version(NODE_API_KEY, "v1.3")
    def test_06(self, test):
        """MXL IS-05 Sender transportfile endpoint returns 404"""

        valid, result = self.get_is04_resources("senders")
        if not valid:
            return test.FAIL(result)

        mxl_senders = self._mxl_senders()
        if not mxl_senders:
            return test.UNCLEAR("No MXL Sender resources found")

        for sender in self._apply_max_test_iteration_cap(mxl_senders):
            url = self.connection_url + f"single/senders/{sender['id']}/transportfile"
            valid_r, response = self.do_request("GET", url)
            if not valid_r:
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

        valid, result = self.get_is04_resources("receivers")
        if not valid:
            return test.FAIL(result)

        receivers = self._mxl_receivers()
        if not receivers:
            return test.UNCLEAR("No MXL Receiver resources found")

        for receiver in self._apply_max_test_iteration_cap(receivers):
            if receiver.get("transport") != MXL_TRANSPORT:
                return test.FAIL(f"Receiver {receiver['id']} must use transport {MXL_TRANSPORT}")
            ib = receiver.get("interface_bindings")
            if not isinstance(ib, list) or ib != []:
                return test.FAIL(f"Receiver {receiver['id']} must have interface_bindings []")
            try:
                self.validate_schema(receiver.get("format"), format_schema)
            except ValidationError as e:
                return test.FAIL(
                    f"Receiver {receiver['id']} has invalid 'format' for the formats register: {e}",
                    f"https://specs.amwa.tv/nmos-parameter-registers/branches/{formats_reg['spec_branch']}/formats/",
                )
            mts = receiver.get("caps", {}).get("media_types")
            if not isinstance(mts, list) or len(mts) < 1:
                return test.FAIL(f"Receiver {receiver['id']} caps.media_types must have at least one entry")
            for mt in mts:
                try:
                    self.validate_schema(mt, media_type_schema)
                except ValidationError as e:
                    return test.FAIL(
                        f"Receiver {receiver['id']} caps.media_types contains invalid entry: {e}",
                        f"https://specs.amwa.tv/nmos-parameter-registers/branches/{media_types_reg['spec_branch']}/media-types/",
                    )

        return test.PASS()

    @requires_api_version(NODE_API_KEY, "v1.3")
    def test_08(self, test):
        """Receiver declares BCP-004-01 constraints"""

        api = self.apis[RECEIVER_CAPS_KEY]
        reg_api = self.apis[CAPS_REGISTER_KEY]

        valid, result = self.get_is04_resources("receivers")
        if not valid:
            return test.FAIL(result)

        receivers = self._mxl_receivers()
        if not receivers:
            return test.UNCLEAR("No MXL Receiver resources found")

        schema = load_resolved_schema(api["spec_path"], "receiver_constraint_sets.json")
        reg_schema_file = str(Path(os.path.abspath(reg_api["spec_path"])) / "capabilities/constraint_set.json")
        with open(reg_schema_file, "r") as f:
            reg_schema_obj = json.load(f)
        reg_schema = load_resolved_schema(api["spec_path"], schema_obj=reg_schema_obj)

        for receiver in self._apply_max_test_iteration_cap(receivers):
            caps = receiver.get("caps", {})
            if "constraint_sets" not in caps:
                return test.FAIL(f"Receiver {receiver['id']} must include caps.constraint_sets per BCP-004-01")
            try:
                self.validate_schema(receiver, schema)
            except ValidationError as e:
                return test.FAIL(f"Receiver {receiver['id']} does not comply with BCP-004-01 schema: {e}")
            for constraint_set in caps["constraint_sets"]:
                try:
                    self.validate_schema(constraint_set, reg_schema)
                except ValidationError as e:
                    return test.FAIL(f"Receiver {receiver['id']} constraint_set invalid vs capabilities register: {e}")
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

        for rt in ["senders", "receivers"]:
            valid, result = self.get_is04_resources(rt)
            if not valid:
                return test.FAIL(result)

        checked = False
        for kind, resources in (("sender", self._mxl_senders()), ("receiver", self._mxl_receivers())):
            for resource in self._apply_max_test_iteration_cap(resources):
                checked = True
                base = f"single/{kind}s/{resource['id']}/"

                valid_c, constraints = self.is05_utils.checkCleanRequestJSON("GET", base + "constraints/")
                if not valid_c:
                    return test.FAIL(f"constraints: {constraints}")
                if not isinstance(constraints, list) or len(constraints) != 1:
                    return test.FAIL(f"{kind} {resource['id']} must expose exactly one constraints leg")
                if not self._constraint_leg_has_mxl_keys(constraints[0]):
                    return test.FAIL(f"{kind} {resource['id']} constraints[0] missing mxl_domain_id or mxl_flow_id")

                valid_s, staged = self.is05_utils.checkCleanRequestJSON("GET", base + "staged/")
                if not valid_s:
                    return test.FAIL(f"staged: {staged}")
                tp = staged.get("transport_params")
                if not isinstance(tp, list) or len(tp) != 1:
                    return test.FAIL(f"{kind} {resource['id']} staged transport_params must have exactly one leg")
                if not self._leg_has_mxl_keys(tp[0]):
                    return test.FAIL(f"{kind} {resource['id']} staged leg missing mxl_domain_id or mxl_flow_id")

                valid_a, active = self.is05_utils.checkCleanRequestJSON("GET", base + "active/")
                if not valid_a:
                    return test.FAIL(f"active: {active}")
                atp = active.get("transport_params")
                if not isinstance(atp, list) or len(atp) != 1:
                    return test.FAIL(f"{kind} {resource['id']} active transport_params must have exactly one leg")
                if not self._leg_has_mxl_keys(atp[0]):
                    return test.FAIL(f"{kind} {resource['id']} active leg missing mxl_domain_id or mxl_flow_id")

        if not checked:
            return test.UNCLEAR("No MXL Senders or Receivers found")
        return test.PASS()

    @requires_api_version(CONN_API_KEY, "v1.2")
    @requires_api_version(NODE_API_KEY, "v1.3")
    def test_11(self, test):
        """Transport parameter payloads conform to BCP-007-03 MXL sender and receiver transport parameter schemas"""

        mxl_path = self.apis[MXL_SCHEMA_KEY]["spec_path"]
        sender_schema = load_resolved_schema(mxl_path, "sender_transport_params_mxl.json")
        receiver_schema = load_resolved_schema(mxl_path, "receiver_transport_params_mxl.json")

        for rt in ["senders", "receivers"]:
            valid, result = self.get_is04_resources(rt)
            if not valid:
                return test.FAIL(result)

        checked = False
        for kind, resources, schema in (
                ("sender", self._mxl_senders(), sender_schema),
                ("receiver", self._mxl_receivers(), receiver_schema),
        ):
            for resource in self._apply_max_test_iteration_cap(resources):
                checked = True
                base = f"single/{kind}s/{resource['id']}/"
                for endpoint in ("staged", "active"):
                    valid_j, data = self.is05_utils.checkCleanRequestJSON("GET", base + endpoint + "/")
                    if not valid_j:
                        return test.FAIL(str(data))
                    for leg in data.get("transport_params", []):
                        try:
                            self.validate_schema(leg, schema)
                        except ValidationError as e:
                            return test.FAIL(f"{kind} {resource['id']} {endpoint} transport_params schema: {e}")

        if not checked:
            return test.UNCLEAR("No MXL Senders or Receivers found")
        return test.PASS()

    @requires_api_version(CONN_API_KEY, "v1.2")
    @requires_api_version(NODE_API_KEY, "v1.3")
    def test_12(self, test):
        """Staged MXL parameters comply with transport schema and per-parameter IS-05 constraints"""

        for rt in ["senders", "receivers"]:
            valid, result = self.get_is04_resources(rt)
            if not valid:
                return test.FAIL(result)

        checked = False
        for kind, resources, schema in (
                ("sender", self._mxl_senders(),
                 load_resolved_schema(self.apis[MXL_SCHEMA_KEY]["spec_path"],
                                      "sender_transport_params_mxl.json")),
                ("receiver", self._mxl_receivers(),
                 load_resolved_schema(self.apis[MXL_SCHEMA_KEY]["spec_path"],
                                      "receiver_transport_params_mxl.json")),
        ):
            for resource in self._apply_max_test_iteration_cap(resources):
                checked = True

                valid_c, constraints = self.is05_utils.checkCleanRequestJSON(
                    "GET", f"single/{kind}s/{resource['id']}/constraints/")
                if not valid_c:
                    return test.FAIL(str(constraints))
                if not isinstance(constraints, list) or len(constraints) != 1:
                    return test.FAIL(f"{kind} {resource['id']} must expose exactly one constraints leg")

                valid_s, staged = self.is05_utils.checkCleanRequestJSON(
                    "GET", f"single/{kind}s/{resource['id']}/staged/")
                if not valid_s:
                    return test.FAIL(str(staged))
                if not isinstance(staged.get("transport_params"), list) or len(staged["transport_params"]) != 1:
                    return test.FAIL(f"{kind} {resource['id']} staged transport_params must have exactly one leg")

                try:
                    self.validate_schema(staged["transport_params"][0], schema)
                except ValidationError as e:
                    return test.FAIL(f"{kind} {resource['id']} staged transport_params invalid vs transport "
                                     f"schema: {e}")

                for param in _MXL_TP_PARAMS:
                    if (isinstance(constraints[0].get(param), dict)
                            and not self._staged_value_satisfies_constraint(
                                staged["transport_params"][0].get(param), constraints[0][param])):
                        return test.FAIL(f"{kind} {resource['id']} staged {param} value "
                                         f"{staged['transport_params'][0].get(param)!r} does not satisfy constraints")

        if not checked:
            return test.UNCLEAR("No MXL Senders or Receivers found")
        return test.PASS()

    @requires_api_version(CONN_API_KEY, "v1.2")
    @requires_api_version(NODE_API_KEY, "v1.3")
    def test_13(self, test):
        """Constraints MUST NOT list auto for mxl_domain_id or mxl_flow_id"""

        for rt in ["senders", "receivers"]:
            valid, result = self.get_is04_resources(rt)
            if not valid:
                return test.FAIL(result)

        checked = False
        for kind, resources in (("sender", self._mxl_senders()), ("receiver", self._mxl_receivers())):
            for resource in self._apply_max_test_iteration_cap(resources):
                checked = True
                base = f"single/{kind}s/{resource['id']}/"
                valid_c, constraints = self.is05_utils.checkCleanRequestJSON("GET", base + "constraints/")
                if not valid_c:
                    return test.FAIL(str(constraints))
                if not isinstance(constraints, list) or len(constraints) != 1:
                    return test.FAIL(f"{kind} {resource['id']} must expose exactly one constraints leg")
                auto_params = self._constraints_enum_lists_auto(constraints[0])
                if auto_params:
                    return test.FAIL(f"{kind} {resource['id']} constraints must not list auto for: "
                                     f"{', '.join(auto_params)}")

        if not checked:
            return test.UNCLEAR("No MXL Senders or Receivers found")
        return test.PASS()

    @requires_api_version(CONN_API_KEY, "v1.2")
    @requires_api_version(NODE_API_KEY, "v1.3")
    def test_14(self, test):
        """MXL IS-05 Receiver staged PATCH succeeds when transport_file is omitted from the request body"""

        valid, result = self.get_is04_resources("receivers")
        if not valid:
            return test.FAIL(result)

        receivers = self._mxl_receivers()
        if not receivers:
            return test.UNCLEAR("No MXL Receiver resources found")

        for receiver in self._apply_max_test_iteration_cap(receivers):
            base = f"single/receivers/{receiver['id']}/"
            valid_g, staged = self.is05_utils.checkCleanRequestJSON("GET", base + "staged/")
            if not valid_g:
                return test.FAIL(str(staged))
            body = self._staged_patch_body_omit_transport_file(staged)
            valid_p, resp = self.do_request("PATCH", self.connection_url + base + "staged/", json=body)
            if not valid_p:
                return test.FAIL(f"PATCH failed: {resp}")
            if resp.status_code not in (200, 202):
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

        valid, result = self.get_is04_resources("receivers")
        if not valid:
            return test.FAIL(result)

        if not self._mxl_receivers():
            return test.UNCLEAR("No MXL Receiver resources found")

        return test.PASS()

    @requires_api_version(CONN_API_KEY, "v1.2")
    @requires_api_version(NODE_API_KEY, "v1.3")
    def test_17(self, test):
        """MXL transport parameters use null when undetermined; active MUST NOT contain auto"""

        for rt in ["senders", "receivers"]:
            valid, result = self.get_is04_resources(rt)
            if not valid:
                return test.FAIL(result)

        checked = False
        for kind, resources in (("sender", self._mxl_senders()), ("receiver", self._mxl_receivers())):
            for resource in self._apply_max_test_iteration_cap(resources):
                checked = True
                rid = resource["id"]
                for endpoint in ("staged", "active"):
                    valid_j, data = self.is05_utils.checkCleanRequestJSON(
                        "GET", f"single/{kind}s/{rid}/{endpoint}/")
                    if not valid_j:
                        return test.FAIL(str(data))
                    tp = data.get("transport_params", [])
                    if endpoint == "active" and self._leg_values_contain_auto(tp):
                        return test.FAIL(f"{kind} {rid} active transport_params must not contain auto")
                    if not isinstance(tp, list) or len(tp) != 1 or not isinstance(tp[0], dict):
                        return test.FAIL(f"{kind} {rid} {endpoint} transport_params must have one leg")
                    for param in _MXL_TP_PARAMS:
                        val = tp[0].get(param)
                        if param not in tp[0]:
                            return test.FAIL(f"{kind} {rid} {endpoint} missing {param}")
                        if endpoint == "active" and val == "auto":
                            return test.FAIL(f"{kind} {rid} active {param} must not be auto")
                        if endpoint == "active" and not self._mxl_param_value_valid(val):
                            return test.FAIL(f"{kind} {rid} active {param} must be null or a concrete value, "
                                             f"got {val!r}")

        if not checked:
            return test.UNCLEAR("No MXL Senders or Receivers found")
        return test.PASS()

    @requires_api_version(CONN_API_KEY, "v1.2")
    @requires_api_version(NODE_API_KEY, "v1.3")
    def test_18(self, test):
        """MXL Sender accepts null and resolvable auto for mxl_domain_id and mxl_flow_id"""

        valid, result = self.get_is04_resources("senders")
        if not valid:
            return test.FAIL(result)

        senders = self._mxl_senders()
        if not senders:
            return test.UNCLEAR("No MXL Sender resources found")

        for sender in self._apply_max_test_iteration_cap(senders):
            sid = sender["id"]
            for param in _MXL_TP_PARAMS:
                valid_g, staged = self._get_staged("sender", sid)
                if not valid_g:
                    return test.FAIL(str(staged))

                valid_p, response = self._patch_mxl_staged("sender", sid, staged, {param: None})
                if not valid_p:
                    return test.FAIL(str(response))
                if response.status_code not in _PATCH_OK:
                    return test.FAIL(f"Sender {sid} must accept null for {param}, got {response.status_code}")

                valid_g, staged = self._get_staged("sender", sid)
                if not valid_g:
                    return test.FAIL(str(staged))

                valid_p, response = self._patch_mxl_staged("sender", sid, staged, {param: "auto"}, activate=True)
                if not valid_p:
                    return test.FAIL(str(response))
                if response.status_code not in _PATCH_OK:
                    return test.FAIL(f"Sender {sid} must accept auto for {param} when resolvable, "
                                     f"got {response.status_code}")

                valid_a, active = self._get_active("sender", sid)
                if not valid_a:
                    return test.FAIL(str(active))
                atp = active.get("transport_params", [])
                if not isinstance(atp, list) or len(atp) != 1:
                    return test.FAIL(f"Sender {sid} active transport_params must have one leg")
                if atp[0].get(param) == "auto":
                    return test.FAIL(f"Sender {sid} patched auto for {param} did not resolve on /active")

        return test.PASS()

    @requires_api_version(CONN_API_KEY, "v1.2")
    @requires_api_version(NODE_API_KEY, "v1.3")
    def test_19(self, test):
        """MXL Receiver null and auto semantics for mxl_domain_id and mxl_flow_id"""

        valid, result = self.get_is04_resources("receivers")
        if not valid:
            return test.FAIL(result)

        receivers = self._mxl_receivers()
        if not receivers:
            return test.UNCLEAR("No MXL Receiver resources found")

        for receiver in self._apply_max_test_iteration_cap(receivers):
            rid = receiver["id"]

            valid_g, staged = self._get_staged("receiver", rid)
            if not valid_g:
                return test.FAIL(str(staged))

            valid_p, response = self._patch_mxl_staged("receiver", rid, staged, {"mxl_flow_id": None})
            if not valid_p:
                return test.FAIL(str(response))
            if response.status_code not in _PATCH_OK:
                return test.FAIL(f"Receiver {rid} must accept null for mxl_flow_id, got {response.status_code}")

            valid_g, staged = self._get_staged("receiver", rid)
            if not valid_g:
                return test.FAIL(str(staged))

            valid_p, response = self._patch_mxl_staged("receiver", rid, staged, {"mxl_flow_id": "auto"})
            if not valid_p:
                return test.FAIL(str(response))
            if response.status_code in _PATCH_OK:
                return test.FAIL(f"Receiver {rid} must not accept auto for mxl_flow_id")

            valid_g, staged = self._get_staged("receiver", rid)
            if not valid_g:
                return test.FAIL(str(staged))

            valid_p, response = self._patch_mxl_staged("receiver", rid, staged, {"mxl_domain_id": None})
            if not valid_p:
                return test.FAIL(str(response))
            if response.status_code not in _PATCH_OK:
                return test.FAIL(f"Receiver {rid} must accept null for mxl_domain_id, got {response.status_code}")

            valid_g, staged = self._get_staged("receiver", rid)
            if not valid_g:
                return test.FAIL(str(staged))

            valid_p, response = self._patch_mxl_staged(
                "receiver", rid, staged, {"mxl_domain_id": "auto"}, activate=True)
            if not valid_p:
                return test.FAIL(str(response))
            if response.status_code in _PATCH_OK:
                valid_a, active = self._get_active("receiver", rid)
                if not valid_a:
                    return test.FAIL(str(active))
                atp = active.get("transport_params", [])
                if not isinstance(atp, list) or len(atp) != 1:
                    return test.FAIL(f"Receiver {rid} active transport_params must have one leg")
                if atp[0].get("mxl_domain_id") == "auto":
                    return test.FAIL(f"Receiver {rid} patched auto for mxl_domain_id did not resolve on /active")

        return test.PASS()
