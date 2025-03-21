# Copyright (C) 2025 Advanced Media Workflow Association
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

import os
from requests.compat import json
from jsonschema import ValidationError
from pathlib import Path

from ..GenericTest import GenericTest
from ..IS04Utils import IS04Utils
from ..TestHelper import load_resolved_schema

NODE_API_KEY = "node"
RECEIVER_CAPS_KEY = "receiver-caps"
CAPS_REGISTER_KEY = "caps-register"


class BCP00401Test(GenericTest):
    """
    Runs BCP-004-01-Test
    """
    def __init__(self, apis, **kwargs):
        GenericTest.__init__(self, apis, disable_auto=True, **kwargs)
        self.node_url = self.apis[NODE_API_KEY]["url"]
        self.is04_utils = IS04Utils(self.node_url)

    def set_up_tests(self):
        pass

    def tear_down_tests(self):
        pass

    def test_01(self, test):
        """Node API implements BCP-004-01 Receiver Capabilities"""

        api = self.apis[RECEIVER_CAPS_KEY]
        reg_api = self.apis[CAPS_REGISTER_KEY]

        receivers_valid, receivers_response = self.do_request("GET", self.node_url + "receivers")

        schema = load_resolved_schema(api["spec_path"], "receiver_constraint_sets.json")
        # workaround to load the Capabilities register schema as if with load_resolved_schema directly
        # but with the base_uri of the Receiver Capabilities schemas
        reg_schema_file = str(Path(os.path.abspath(reg_api["spec_path"])) / "capabilities/constraint_set.json")
        with open(reg_schema_file, "r") as f:
            reg_schema_obj = json.load(f)
        reg_schema = load_resolved_schema(api["spec_path"], schema_obj=reg_schema_obj)

        no_receivers = True
        no_constraint_sets = True
        if receivers_valid and receivers_response.status_code == 200:
            try:
                for receiver in receivers_response.json():
                    no_receivers = False
                    if "constraint_sets" in receiver["caps"]:
                        no_constraint_sets = False
                        try:
                            self.validate_schema(receiver, schema)
                        except ValidationError as e:
                            return test.FAIL("Receiver {} does not comply with the BCP-004-01 schema: "
                                             "{}".format(receiver["id"], str(e)),
                                             "https://specs.amwa.tv/bcp-004-01/branches/{}"
                                             "/docs/Receiver_Capabilities.html"
                                             "#validating-parameter-constraints-and-constraint-sets"
                                             .format(api["spec_branch"]))
                        for constraint_set in receiver["caps"]["constraint_sets"]:
                            try:
                                self.validate_schema(constraint_set, reg_schema)
                            except ValidationError as e:
                                return test.FAIL("Receiver {} does not comply with the Capabilities register schema: "
                                                 "{}".format(receiver["id"], str(e)),
                                                 "https://specs.amwa.tv/bcp-004-01/branches/{}"
                                                 "/docs/Receiver_Capabilities.html"
                                                 "#behaviour-receivers"
                                                 .format(api["spec_branch"]))
                            found_param_constraint = False
                            for param_constraint in constraint_set:
                                if not param_constraint.startswith("urn:x-nmos:cap:meta:"):
                                    found_param_constraint = True
                                    break
                            if not found_param_constraint:
                                return test.FAIL("Receiver {} caps includes a constraint set without any "
                                                 "parameter constraints".format(receiver["id"]),
                                                 "https://specs.amwa.tv/bcp-004-01/branches/{}"
                                                 "/docs/Receiver_Capabilities.html"
                                                 "#constraint-sets"
                                                 .format(api["spec_branch"]))
            except json.JSONDecodeError:
                return test.FAIL("Non-JSON response returned from Node API")
            except KeyError as e:
                return test.FAIL("Unable to find expected key in the Receiver: {}".format(e))

        if no_receivers:
            return test.UNCLEAR("No Receivers were found on the Node")
        elif no_constraint_sets:
            return test.OPTIONAL("No BCP-004-01 'constraint_sets' were identified in Receiver caps",
                                 "https://specs.amwa.tv/bcp-004-01/branches/{}"
                                 "/docs/Receiver_Capabilities.html#listing-constraint-sets"
                                 .format(api["spec_branch"]))
        else:
            return test.PASS()

    def test_02(self, test):
        """Receiver 'caps' version is valid"""

        api = self.apis[RECEIVER_CAPS_KEY]

        receivers_valid, receivers_response = self.do_request("GET", self.node_url + "receivers")

        no_receivers = True
        no_caps_version = True
        if receivers_valid and receivers_response.status_code == 200:
            try:
                for receiver in receivers_response.json():
                    no_receivers = False
                    if "version" in receiver["caps"]:
                        no_caps_version = False
                        caps_version = receiver["caps"]["version"]
                        core_version = receiver["version"]
                        if self.is04_utils.compare_resource_version(caps_version, core_version) > 0:
                            return test.FAIL("Receiver {} caps version is later than resource version"
                                             .format(receiver["id"]),
                                             "https://specs.amwa.tv/bcp-004-01/branches/{}"
                                             "/docs/Receiver_Capabilities.html#behaviour-receivers"
                                             .format(api["spec_branch"]))
            except json.JSONDecodeError:
                return test.FAIL("Non-JSON response returned from Node API")
            except KeyError as e:
                return test.FAIL("Unable to find expected key in the Receiver: {}".format(e))

        if no_receivers:
            return test.UNCLEAR("No Receivers were found on the Node")
        elif no_caps_version:
            return test.OPTIONAL("No Receiver caps versions were found",
                                 "https://specs.amwa.tv/bcp-004-01/branches/{}"
                                 "/docs/Receiver_Capabilities.html#capabilities-version"
                                 .format(api["spec_branch"]))
        else:
            return test.PASS()

    def test_03(self, test):
        """Receiver 'caps' parameter constraints should be listed in the Capabilities register"""

        api = self.apis[RECEIVER_CAPS_KEY]
        reg_api = self.apis[CAPS_REGISTER_KEY]

        # load the Capabilities register schema as JSON as we're only interested in the list of properties
        reg_schema_file = str(Path(os.path.abspath(reg_api["spec_path"])) / "capabilities/constraint_set.json")
        with open(reg_schema_file, "r") as f:
            reg_schema_obj = json.load(f)

        receivers_valid, receivers_response = self.do_request("GET", self.node_url + "receivers")

        no_receivers = True
        no_constraint_sets = True
        warn_unregistered = ""
        if receivers_valid and receivers_response.status_code == 200:
            try:
                for receiver in receivers_response.json():
                    no_receivers = False
                    if "constraint_sets" in receiver["caps"]:
                        no_constraint_sets = False
                        for constraint_set in receiver["caps"]["constraint_sets"]:
                            # keys in each constraint set must be either parameter constraints
                            # or constraint set metadata, both of which are listed in the schema
                            for param_constraint in constraint_set:
                                if param_constraint not in reg_schema_obj["properties"] and not warn_unregistered:
                                    warn_unregistered = "Receiver {} caps includes an unregistered " \
                                        "parameter constraint '{}'".format(receiver["id"], param_constraint)
            except json.JSONDecodeError:
                return test.FAIL("Non-JSON response returned from Node API")
            except KeyError as e:
                return test.FAIL("Unable to find expected key in the Receiver: {}".format(e))

        if no_receivers:
            return test.UNCLEAR("No Receivers were found on the Node")
        elif no_constraint_sets:
            return test.OPTIONAL("No BCP-004-01 'constraint_sets' were identified in Receiver caps",
                                 "https://specs.amwa.tv/bcp-004-01/branches/{}"
                                 "/docs/Receiver_Capabilities.html#listing-constraint-sets"
                                 .format(api["spec_branch"]))
        elif warn_unregistered:
            return test.WARNING(warn_unregistered,
                                "https://specs.amwa.tv/bcp-004-01/branches/{}"
                                "/docs/Receiver_Capabilities.html#defining-parameter-constraints"
                                .format(api["spec_branch"]))
        else:
            return test.PASS()

    def test_04(self, test):
        """Node API implements BCP-004-01 Receiver Capabilities constraint set labels"""
        return self.do_test_constraint_set_meta(test, "label", "human-readable labels", warn_not_all=True)

    def test_05(self, test):
        """Node API implements BCP-004-01 Receiver Capabilities constraint set preferences"""
        return self.do_test_constraint_set_meta(test, "preference", "preferences")

    def test_06(self, test):
        """Node API implements BCP-004-01 Receiver Capabilities enabled/disabled constraint sets"""
        return self.do_test_constraint_set_meta(test, "enabled", "enabled/disabled flags")

    def do_test_constraint_set_meta(self, test, meta, description, warn_not_all=False):
        api = self.apis[RECEIVER_CAPS_KEY]

        receivers_valid, receivers_response = self.do_request("GET", self.node_url + "receivers")

        no_receivers = True
        no_constraint_sets = True
        no_meta = True
        all_meta = True
        if receivers_valid and receivers_response.status_code == 200:
            try:
                for receiver in receivers_response.json():
                    no_receivers = False
                    if "constraint_sets" in receiver["caps"]:
                        no_constraint_sets = False
                        for constraint_set in receiver["caps"]["constraint_sets"]:
                            if "urn:x-nmos:cap:meta:" + meta in constraint_set:
                                no_meta = False
                            else:
                                all_meta = False
            except json.JSONDecodeError:
                return test.FAIL("Non-JSON response returned from Node API")
            except KeyError as e:
                return test.FAIL("Unable to find expected key in the Receiver: {}".format(e))

        if no_receivers:
            return test.UNCLEAR("No Receivers were found on the Node")
        elif no_constraint_sets:
            return test.OPTIONAL("No BCP-004-01 'constraint_sets' were identified in Receiver caps",
                                 "https://specs.amwa.tv/bcp-004-01/branches/{}"
                                 "/docs/Receiver_Capabilities.html#listing-constraint-sets"
                                 .format(api["spec_branch"]))
        elif no_meta:
            return test.OPTIONAL("No BCP-004-01 'constraint_sets' have {}".format(description),
                                 "https://specs.amwa.tv/bcp-004-01/branches/{}"
                                 "/docs/Receiver_Capabilities.html#constraint-set-{}"
                                 .format(api["spec_branch"], meta))
        elif warn_not_all and not all_meta:
            return test.WARNING("Only some BCP-004-01 'constraint_sets' have {}".format(description),
                                "https://specs.amwa.tv/bcp-004-01/branches/{}"
                                "/docs/Receiver_Capabilities.html#constraint-set-{}"
                                .format(api["spec_branch"], meta))
        else:
            return test.PASS()

    def test_07(self, test):
        """Receiver 'caps' parameter constraints should be used with the correct format"""

        # general_constraints = [
        #     "urn:x-nmos:cap:format:media_type",
        #     "urn:x-nmos:cap:format:grain_rate",
        #     "urn:x-nmos:cap:format:bit_rate",
        #     "urn:x-nmos:cap:transport:bit_rate",
        #     "urn:x-nmos:cap:transport:st2110_21_sender_type"
        # ]
        video_specific_constraints = [
            "urn:x-nmos:cap:format:frame_width",
            "urn:x-nmos:cap:format:frame_height",
            "urn:x-nmos:cap:format:interlace_mode",
            "urn:x-nmos:cap:format:colorspace",
            "urn:x-nmos:cap:format:transfer_characteristic",
            "urn:x-nmos:cap:format:color_sampling",
            "urn:x-nmos:cap:format:component_depth",
            "urn:x-nmos:cap:format:profile",
            "urn:x-nmos:cap:format:level",
            "urn:x-nmos:cap:format:sublevel",
            "urn:x-nmos:cap:transport:packet_transmission_mode"
        ]
        audio_specific_constraints = [
            "urn:x-nmos:cap:format:channel_count",
            "urn:x-nmos:cap:format:sample_rate",
            "urn:x-nmos:cap:format:sample_depth",
            "urn:x-nmos:cap:transport:packet_time",
            "urn:x-nmos:cap:transport:max_packet_time"
        ]
        data_specific_constraints = [
            "urn:x-nmos:cap:format:event_type"
        ]
        format_specific_constraints = {
            "urn:x-nmos:format:video": video_specific_constraints,
            "urn:x-nmos:format:audio": audio_specific_constraints,
            "urn:x-nmos:format:data": data_specific_constraints,
            "urn:x-nmos:format:mux": []
        }

        api = self.apis[RECEIVER_CAPS_KEY]

        receivers_valid, receivers_response = self.do_request("GET", self.node_url + "receivers")

        no_receivers = True
        no_constraint_sets = True
        warn_format = ""
        if receivers_valid and receivers_response.status_code == 200:
            try:
                for receiver in receivers_response.json():
                    no_receivers = False
                    if "constraint_sets" in receiver["caps"]:
                        no_constraint_sets = False
                        format = receiver["format"]
                        wrong_constraints = [c for f in format_specific_constraints if f != format
                                             for c in format_specific_constraints[f]]
                        for constraint_set in receiver["caps"]["constraint_sets"]:
                            for param_constraint in constraint_set:
                                if param_constraint in wrong_constraints and not warn_format:
                                    warn_format = "Receiver {} caps includes a parameter constraint '{}' " \
                                        "that is not relevant for {}".format(receiver["id"], param_constraint, format)
            except json.JSONDecodeError:
                return test.FAIL("Non-JSON response returned from Node API")
            except KeyError as e:
                return test.FAIL("Unable to find expected key in the Receiver: {}".format(e))

        if no_receivers:
            return test.UNCLEAR("No Receivers were found on the Node")
        elif no_constraint_sets:
            return test.OPTIONAL("No BCP-004-01 'constraint_sets' were identified in Receiver caps",
                                 "https://specs.amwa.tv/bcp-004-01/branches/{}"
                                 "/docs/Receiver_Capabilities.html#listing-constraint-sets"
                                 .format(api["spec_branch"]))
        elif warn_format:
            return test.WARNING(warn_format)
        else:
            return test.PASS()

    def test_08(self, test):
        """Receiver 'caps' media type constraints should be used consistently"""

        media_type = "urn:x-nmos:cap:format:media_type"

        api = self.apis[RECEIVER_CAPS_KEY]

        receivers_valid, receivers_response = self.do_request("GET", self.node_url + "receivers")

        no_receivers = True
        no_constraint_sets = True
        if receivers_valid and receivers_response.status_code == 200:
            try:
                for receiver in receivers_response.json():
                    no_receivers = False
                    caps = receiver["caps"]
                    if "media_types" in caps and "constraint_sets" in caps:
                        no_constraint_sets = False
                        media_types = caps["media_types"]
                        for constraint_set in caps["constraint_sets"]:
                            if media_type in constraint_set:
                                if "enum" in constraint_set[media_type]:
                                    if not set(constraint_set[media_type]["enum"]).issubset(set(media_types)):
                                        return test.FAIL("Receiver {} caps includes a value for the parameter "
                                                         "constraint '{}' that is excluded by 'media_types'"
                                                         .format(receiver["id"], media_type))
            except json.JSONDecodeError:
                return test.FAIL("Non-JSON response returned from Node API")
            except KeyError as e:
                return test.FAIL("Unable to find expected key in the Receiver: {}".format(e))

        if no_receivers:
            return test.UNCLEAR("No Receivers were found on the Node")
        elif no_constraint_sets:
            return test.OPTIONAL("No BCP-004-01 'constraint_sets' were identified in Receiver caps",
                                 "https://specs.amwa.tv/bcp-004-01/branches/{}"
                                 "/docs/Receiver_Capabilities.html#listing-constraint-sets"
                                 .format(api["spec_branch"]))
        else:
            return test.PASS()
