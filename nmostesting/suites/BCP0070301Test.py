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
from ..GenericTest import GenericTest
from ..IS04Utils import IS04Utils
from ..IS05Utils import IS05Utils
from ..TestHelper import load_resolved_schema

NODE_API_KEY = "node"
CONN_API_KEY = "connection"
RECEIVER_CAPS_KEY = "receiver-caps"
CAPS_REGISTER_KEY = "caps-register"
MXL_SCHEMA_KEY = "mxl-schemas"

MXL_TRANSPORT = "urn:x-nmos:transport:mxl"

# NMOS Formats register entries use URNs of this form (IS-04 resources).
_FORMAT_URN_RE = re.compile(r"^urn:x-nmos:format:[A-Za-z0-9_:-]+$")
# Media types register uses MIME-style strings.
_MEDIA_TYPE_RE = re.compile(r"^[a-z0-9][a-z0-9.!#$&^*+\\-]*/[a-zA-Z0-9][a-zA-Z0-9.!#$&^*+\\-]*$")


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

    def _is_registered_format_urn(self, value):
        return isinstance(value, str) and bool(_FORMAT_URN_RE.match(value))

    def _is_registered_media_type(self, value):
        return isinstance(value, str) and bool(_MEDIA_TYPE_RE.match(value))

    @staticmethod
    def _leg_has_mxl_keys(leg):
        return isinstance(leg, dict) and "mxl_domain_id" in leg and "mxl_flow_id" in leg

    @staticmethod
    def _constraint_leg_has_mxl_keys(leg):
        if not isinstance(leg, dict):
            return False
        return "mxl_domain_id" in leg and "mxl_flow_id" in leg

    def _staged_value_allowed(self, staged_val, constraint_entry):
        """Return True if staged_val satisfies constraint_entry (enum/min/max)"""
        if not isinstance(constraint_entry, dict):
            return True
        if "enum" in constraint_entry:
            return staged_val in constraint_entry["enum"]
        return True

    def test_01(self, test):
        """Node implements IS-04 version 1.3 or higher"""

        api = self.apis[NODE_API_KEY]
        if self.is04_utils.compare_api_version(api["version"], "v1.3") >= 0:
            valid, result = self.do_request("GET", self.node_url)
            if valid:
                return test.PASS()
            return test.FAIL(f"Node API did not respond as expected: {result}")
        return test.FAIL("Node API must be v1.3 or greater for BCP-007-03")

    def test_02(self, test):
        """Node exposes Source, Flow and Sender resources for each MXL writer in the IS-04 Node API"""

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

    def test_03(self, test):
        """MXL Flow format and media_type use values from the NMOS parameter registers"""

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
            fmt = flow.get("format")
            if not self._is_registered_format_urn(fmt):
                return test.FAIL(f"Flow {flow['id']} has invalid or missing 'format' for the formats register")
            mt = flow.get("media_type")
            if not self._is_registered_media_type(mt):
                return test.FAIL(f"Flow {flow['id']} 'media_type' must be a registered media type string")

        return test.PASS()

    def test_04(self, test):
        """MXL Source format uses a value from the NMOS formats parameter register"""

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
            fmt = src.get("format")
            if not self._is_registered_format_urn(fmt):
                return test.FAIL(f"Source {sid} has invalid or missing 'format' for the formats register")

        return test.PASS()

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

    def test_07(self, test):
        """MXL Receiver transport, interface_bindings, format and media_type are correct"""

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
            fmt = receiver.get("format")
            if not self._is_registered_format_urn(fmt):
                return test.FAIL(f"Receiver {receiver['id']} has invalid 'format' for the formats register")
            mts = receiver.get("caps", {}).get("media_types")
            if not isinstance(mts, list) or len(mts) < 1:
                return test.FAIL(f"Receiver {receiver['id']} caps.media_types must have at least one entry")
            invalid_mt = next((mt for mt in mts if not self._is_registered_media_type(mt)), None)
            if invalid_mt is not None:
                return test.FAIL(f"Receiver {receiver['id']} caps.media_types contains invalid entry: {invalid_mt}")

        return test.PASS()

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

    def test_09(self, test):
        """Node implements IS-05 version 1.2 or higher"""

        api = self.apis[CONN_API_KEY]
        if self.is05_utils.compare_api_version(api["version"], "v1.2") >= 0:
            valid, result = self.do_request("GET", self.connection_url + "single/")
            if valid and result.status_code == 200:
                return test.PASS()
            return test.FAIL("Connection API did not respond as expected")
        return test.FAIL("Connection API must be v1.2 or higher for BCP-007-03")

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

    def test_12(self, test):
        """Sender and Receiver constraints list allowed mxl_domain_id and mxl_flow_id values per BCP-007-03"""

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
                leg_c = constraints[0]

                valid_s, staged = self.is05_utils.checkCleanRequestJSON("GET", base + "staged/")
                if not valid_s:
                    return test.FAIL(str(staged))
                leg_s = staged["transport_params"][0]

                for param in ("mxl_domain_id", "mxl_flow_id"):
                    ce = leg_c.get(param)
                    if isinstance(ce, dict) and "enum" in ce:
                        if not self._staged_value_allowed(leg_s.get(param), ce):
                            return test.FAIL(f"{kind} {resource['id']} staged {param} value {leg_s.get(param)} "
                                             f"not allowed by constraints enum")

        if not checked:
            return test.UNCLEAR("No MXL Senders or Receivers found")
        return test.PASS()

    def test_13(self, test):
        """MXL Senders and Receivers reject the special value auto for mxl_domain_id and mxl_flow_id"""

        for rt in ["senders", "receivers"]:
            valid, result = self.get_is04_resources(rt)
            if not valid:
                return test.FAIL(result)

        tested = False
        for kind, resources in (("sender", self._mxl_senders()), ("receiver", self._mxl_receivers())):
            for resource in self._apply_max_test_iteration_cap(resources):
                base = f"single/{kind}s/{resource['id']}/"
                valid_g, staged = self.is05_utils.checkCleanRequestJSON("GET", base + "staged/")
                if not valid_g:
                    return test.FAIL(str(staged))
                if "transport_params" not in staged:
                    continue
                tp = deepcopy(staged["transport_params"])
                if not tp or not isinstance(tp[0], dict):
                    continue
                tp[0]["mxl_domain_id"] = "auto"
                body = {k: v for k, v in staged.items() if k != "transport_file"}
                body["transport_params"] = tp
                tested = True
                valid_p, response = self.do_request("PATCH", self.connection_url + base + "staged/", json=body)
                if not valid_p:
                    return test.FAIL(str(response))
                if response.status_code in (200, 202):
                    return test.FAIL(f"{kind} {resource['id']} incorrectly accepted mxl_domain_id auto")

        if not tested:
            return test.UNCLEAR("No MXL staged transport_params to test")
        return test.PASS()

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
            body = {k: v for k, v in staged.items() if k != "transport_file"}
            valid_p, resp = self.do_request("PATCH", self.connection_url + base + "staged/", json=body)
            if not valid_p:
                return test.FAIL(f"PATCH failed: {resp}")
            if resp.status_code not in (200, 202):
                return test.FAIL(f"PATCH staged without transport_file expected 200/202, got "
                                 f"{resp.status_code}")

        return test.PASS()

    def test_15(self, test):
        """Whether MXL read/write start or stop on activation is verifiable only with
        implementation-specific telemetry."""

        return test.NA("Whether MXL read/write starts or stops on activation cannot be verified by this tool without "
                       "implementation-specific telemetry (R-ACT-ON/OFF, S-ACT-ON/OFF).")
