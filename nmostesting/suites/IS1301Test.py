# Copyright (C) 2023 Advanced Media Workflow Association
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

"""
IS-13-01 tests the AMWA IS-13 NMOS Annotation API
(https://specs.amwa.tv/is-13/).

Each annotation-property test tries to restore the Node's previous values, but
that cannot be guaranteed if the implementation rejects the restore PATCH.

Not covered yet:
* Persistence of updates
"""

from copy import deepcopy
import time

from .. import Config as CONFIG
from ..GenericTest import GenericTest, NMOSTestException
from ..NMOSUtils import NMOSUtils
from ..TestResult import TestStates

ANNOTATION_API_KEY = "annotation"
NODE_API_KEY = "node"

ANNOTATION_SERVICE_TYPE_PREFIX = "urn:x-nmos:service:annotation"

# Minimum supported UTF-8 sizes from IS-13 Behaviour: Additional Limitations
# 64 bytes in UTF-8: twenty 3-byte characters and one 4-byte character
STRING_MAX_LENGTH_VALUE = "スタジオＡの第一カメラ用エンコーダー出力🎚"
assert len(STRING_MAX_LENGTH_VALUE.encode("utf-8")) == 64
USER_TAG_PREFIX = "urn:x-nmos:tag:user:"
USER_TAG_VALUE = [STRING_MAX_LENGTH_VALUE]
# Full tag name of 64 bytes including the required user-namespace prefix
USER_TAG_NAME_MAX_LENGTH = USER_TAG_PREFIX + "nmos-testing-a-sixty-four-byte-long-tag-name"
assert len(USER_TAG_NAME_MAX_LENGTH.encode("utf-8")) == 64
USER_TAG_NAMES_FIVE = [f"{USER_TAG_PREFIX}nmos-testing-{i}" for i in range(5)]
USER_TAG_NAME_TWO_VALUES = USER_TAG_PREFIX + "nmos-testing-two-values"
USER_TAG_TWO_VALUES = ["nmos-testing-1", "nmos-testing-2"]
USER_TAG_NAME_INVALID = USER_TAG_PREFIX + "nmos-testing-invalid"
# Tag values must be strings
INVALID_TAG_VALUE = [42]

GROUP_HINT_TAG_NAME = "urn:x-nmos:tag:grouphint/v1.0"
# "<group-name>:<role-in-group>[:<group-scope>]" per the NMOS Parameter Registers
GROUP_HINT_TAG_VALUE = ["nmos-testing:role"]

READ_ONLY_TAG_PREFIXES = (
    "urn:x-nmos:tag:grouphint/",
    "urn:x-nmos:tag:asset:",
)

RESOURCE_TYPES = ("self", "devices", "sources", "flows", "senders", "receivers")
# The Annotation API MAY omit Sources and Flows. Every other Node API type MUST be present.
OPTIONAL_RESOURCE_TYPES = ("sources", "flows")
CORE_PROPERTIES = ("id", "version", "label", "description", "tags")
RESOURCE_ID_PARAMS = {
    "devices": "deviceId",
    "sources": "sourceId",
    "flows": "flowId",
    "senders": "senderId",
    "receivers": "receiverId",
}


def is_read_only_tag(name):
    return any(name.startswith(prefix) for prefix in READ_ONLY_TAG_PREFIXES)


def writable_tags(tags):
    return {name: values for name, values in tags.items() if not is_read_only_tag(name)}


class IS1301Test(GenericTest):
    """
    Runs IS-13-01-Test
    """

    def __init__(self, apis, **kwargs):
        GenericTest.__init__(self, apis, **kwargs)
        self.annotation_url = self.apis[ANNOTATION_API_KEY]["url"]
        self.node_url = self.apis[NODE_API_KEY]["url"]

    def spec_link(self, page):
        branch = self.apis[ANNOTATION_API_KEY]["spec_branch"]
        return f"https://specs.amwa.tv/is-13/branches/{branch}/docs/{page}"

    def validation_link(self):
        return self.spec_link("APIs.html#api-validation")

    def discovery_link(self):
        return self.spec_link("Interoperability_-_IS-04.html#discovery")

    def consistent_link(self):
        return self.spec_link("Interoperability_-_IS-04.html#consistent-resources")

    def version_link(self):
        return self.spec_link("Interoperability_-_IS-04.html#version-increments")

    def reset_link(self):
        return self.spec_link("Behaviour.html#resetting-values")

    def read_only_link(self):
        return self.spec_link("Behaviour.html#read-only-tags")

    def limit_link(self):
        return self.spec_link("Behaviour.html#additional-limitations")

    def successful_link(self):
        return self.spec_link("Behaviour.html#successful-response")

    def get_json(self, test, url, api_name):
        """GET JSON from url or raise NMOSTestException. Returns the parsed body."""
        valid, response = self.do_request("GET", url)
        if not valid:
            raise NMOSTestException(test.FAIL(f"GET {url} failed: {response}"))
        if response.status_code != 200:
            raise NMOSTestException(test.FAIL(
                f"GET {url} returned HTTP {response.status_code}, expected 200"))
        try:
            return response.json()
        except Exception as ex:
            raise NMOSTestException(test.FAIL(f"GET {url} did not return JSON ({api_name}): {ex}"))

    def parse_resource_ids(self, test, url, entries):
        """Return resource ids from a Node API or Annotation API list body."""
        if not isinstance(entries, list):
            raise NMOSTestException(test.FAIL(f"Resource list at {url} is not an array"))
        resource_ids = []
        for entry in entries:
            if isinstance(entry, str):
                resource_ids.append(entry.rstrip("/"))
            elif isinstance(entry, dict) and "id" in entry:
                resource_ids.append(entry["id"])
            else:
                raise NMOSTestException(test.FAIL(
                    f"Unexpected list entry at {url}: {entry!r}"))
        return resource_ids

    def list_resource_ids(self, test, resource_type):
        """
        Return Annotation API resource IDs for a list type.
        Raise NA if the list of an optional resource type is empty, or UNCLEAR for other types.
        """
        annotation_list_url = f"{self.annotation_url}node/{resource_type}"
        annotation_list = self.get_json(test, annotation_list_url, ANNOTATION_API_KEY)
        if not annotation_list:
            if resource_type in OPTIONAL_RESOURCE_TYPES:
                raise NMOSTestException(test.NA(
                    f"The Annotation API does not include {resource_type}", link=self.consistent_link()))
            raise NMOSTestException(test.UNCLEAR(
                f"No {resource_type} found at {annotation_list_url}"))
        return self.parse_resource_ids(test, annotation_list_url, annotation_list)

    def iter_resource_urls(self, test, resource_type):
        """
        Yield matching Annotation API and Node API URLs.
        List resources are limited by CONFIG.MAX_TEST_ITERATIONS (0 = all).
        """
        annotation_list_url = f"{self.annotation_url}node/{resource_type}"
        node_list_url = f"{self.node_url}{resource_type}"
        if resource_type == "self":
            yield annotation_list_url, node_list_url
            return
        for resource_id in NMOSUtils.sampled_list(self.list_resource_ids(test, resource_type)):
            yield f"{annotation_list_url}/{resource_id}", f"{node_list_url}/{resource_id}"

    def patch_schema_path(self, resource_type):
        if resource_type == "self":
            return "/node/self"
        return f"/node/{resource_type}/{{{RESOURCE_ID_PARAMS[resource_type]}}}"

    def check_resource_values(self, test, resource, check_values, link, source):
        """Fail when resource does not contain the expected annotation values.

        For tags, only the named keys in check_values['tags'] are compared.
        A missing tag matches an expected value of None (a reset that removes the tag).
        """
        for name, expected in check_values.items():
            if name == "tags":
                tags = resource.get("tags") or {}
                for tag_name, tag_values in expected.items():
                    if tags.get(tag_name) != tag_values:
                        raise NMOSTestException(test.FAIL(
                            f"{source} tags[{tag_name!r}] is {tags.get(tag_name)!r}, expected {tag_values!r}",
                            link=link))
            elif resource.get(name) != expected:
                raise NMOSTestException(test.FAIL(
                    f"{source} {name} is {resource.get(name)!r}, expected {expected!r}",
                    link=link))

    def get_and_check(self, test, resource_type, annotation_url, node_url):
        annotation = self.get_json(test, annotation_url, ANNOTATION_API_KEY)
        node = self.get_json(test, node_url, NODE_API_KEY)
        for name in CORE_PROPERTIES:
            if annotation.get(name) != node.get(name):
                raise NMOSTestException(test.FAIL(
                    f"{resource_type}: Annotation API {name} is {annotation.get(name)!r}, "
                    f"Node API {name} is {node.get(name)!r}",
                    link=self.version_link() if name == "version" else self.consistent_link()))

    def patch_and_check(self, test, resource_type, annotation_url, node_url, patch_body, check_values, link,
                        requirement="MUST"):
        """
        PATCH the Annotation API, then check the PATCH response and both subsequent GETs.
        check_values is the resulting annotation values. Nulls in patch_body request a reset, so the
        response is compared to check_values rather than to the request body.
        requirement: 'MUST' fails on HTTP error. Otherwise a valid 500 rejection warns for 'SHOULD'
        or reports the feature as not implemented for 'MAY', and any other error fails.
        Raises NMOSTestException. Returns the Annotation API and Node API GET bodies after the PATCH.
        """
        prev = self.get_json(test, annotation_url, ANNOTATION_API_KEY)
        prev_version = prev.get("version")
        if not isinstance(prev_version, str):
            raise NMOSTestException(test.FAIL(
                f"GET {annotation_url} response version is not a string: {prev_version!r}"))

        valid, response = self.do_request("PATCH", annotation_url, json=patch_body)
        if not valid:
            raise NMOSTestException(test.FAIL(f"PATCH {annotation_url} failed: {response}", link=link))
        if response.status_code != 200:
            detail = (f"PATCH {annotation_url} returned HTTP {response.status_code}, expected 200. "
                      f"Body: {getattr(response, 'text', '')}")
            # A request that the API cannot process is rejected with 500
            if requirement == "MUST" or response.status_code != 500:
                raise NMOSTestException(test.FAIL(detail, link=link))
            valid_error, message = self.check_error_response("PATCH", response, 500)
            if not valid_error:
                raise NMOSTestException(test.FAIL(
                    f"PATCH {annotation_url} returned HTTP 500 but the error body failed checks: {message}",
                    link=link))
            if requirement == "SHOULD":
                raise NMOSTestException(test.WARNING(detail, link=link))
            if requirement == "MAY":
                raise NMOSTestException(test.OPTIONAL(detail, link=link))
            # Unreachable for the 'MUST', 'SHOULD' and 'MAY' requirements
            raise NMOSTestException(test.FAIL(detail, link=link))

        schema = self.get_schema(ANNOTATION_API_KEY, "PATCH", self.patch_schema_path(resource_type), 200)
        if not schema:
            raise NMOSTestException(test.MANUAL(
                f"Test suite unable to locate PATCH 200 schema for {self.patch_schema_path(resource_type)}"))
        valid_body, message = self.check_response(schema, "PATCH", response)
        if not valid_body:
            raise NMOSTestException(test.FAIL(
                f"PATCH {annotation_url} response failed schema or header checks: {message}",
                link=self.successful_link()))

        try:
            patched = response.json()
        except Exception as ex:
            raise NMOSTestException(test.FAIL(
                f"PATCH {annotation_url} did not return JSON: {ex}", link=self.successful_link()))
        if not isinstance(patched, dict):
            raise NMOSTestException(test.FAIL(
                f"PATCH {annotation_url} response is not an object", link=self.successful_link()))
        patched_version = patched.get("version")
        if not isinstance(patched_version, str):
            raise NMOSTestException(test.FAIL(
                f"PATCH {annotation_url} response version is not a string: {patched_version!r}",
                link=self.successful_link()))

        if NMOSUtils.compare_resource_version(patched_version, prev_version) <= 0:
            raise NMOSTestException(test.FAIL(
                f"PATCH {annotation_url} response version did not increase "
                f"(before {prev_version}, response {patched_version})",
                link=self.successful_link()))

        self.check_resource_values(test, patched, check_values, link, "PATCH response")

        annotation = self.get_json(test, annotation_url, ANNOTATION_API_KEY)

        time.sleep(CONFIG.API_PROCESSING_TIMEOUT)

        node = self.get_json(test, node_url, NODE_API_KEY)

        self.check_resource_values(test, annotation, check_values, link, "Annotation API")
        self.check_resource_values(test, node, check_values, self.consistent_link(), "Node API")

        for name in CORE_PROPERTIES:
            if annotation.get(name) != patched.get(name):
                raise NMOSTestException(test.FAIL(
                    f"Annotation API {name} is {annotation.get(name)!r}, "
                    f"PATCH response had {patched.get(name)!r}",
                    link=self.successful_link()))
            if node.get(name) != patched.get(name):
                raise NMOSTestException(test.FAIL(
                    f"Node API {name} is {node.get(name)!r}, "
                    f"PATCH response had {patched.get(name)!r}",
                    link=self.version_link() if name == "version" else self.consistent_link()))

        return annotation, node

    def do_label_or_description_sequence(self, test, resource_type, annotation_property, requirement):
        """
        Reset the property, write a 64-byte non-ASCII value, reset again and compare, then restore.
        """
        result = None
        for annotation_url, node_url in self.iter_resource_urls(test, resource_type):
            initial_value = self.get_json(test, annotation_url, ANNOTATION_API_KEY).get(annotation_property)
            after_reset = None
            try:
                after_reset, _ = self.patch_and_check(
                    test, resource_type, annotation_url, node_url,
                    {annotation_property: None},
                    {},
                    self.reset_link(),
                    requirement)
                if after_reset.get(annotation_property) is None:
                    raise NMOSTestException(test.FAIL(
                        f"After reset, {annotation_property} must be a string, not null",
                        link=self.reset_link()))

                self.patch_and_check(
                    test, resource_type, annotation_url, node_url,
                    {annotation_property: STRING_MAX_LENGTH_VALUE},
                    {annotation_property: STRING_MAX_LENGTH_VALUE},
                    self.limit_link(),
                    requirement)

                self.patch_and_check(
                    test, resource_type, annotation_url, node_url,
                    {annotation_property: None},
                    {annotation_property: after_reset.get(annotation_property)},
                    self.reset_link(),
                    requirement)
            except NMOSTestException as e:
                if e.args[0].state == TestStates.FAIL:
                    raise
                result = result or e.args[0]
            # Attempt to restore the state
            if after_reset is not None and after_reset.get(annotation_property) != initial_value:
                self.do_request("PATCH", annotation_url, json={annotation_property: initial_value})

        return result or test.PASS()

    def do_tags_sequence(self, test, resource_type, tag_names, requirement, tag_values=USER_TAG_VALUE):
        """Write 1 or more user-namespace tags with tag_values, then remove them."""
        tags_patch = {name: deepcopy(tag_values) for name in tag_names}
        result = None
        for annotation_url, node_url in self.iter_resource_urls(test, resource_type):
            try:
                self.patch_and_check(
                    test, resource_type, annotation_url, node_url,
                    {"tags": tags_patch},
                    {"tags": tags_patch},
                    self.limit_link(),
                    requirement)
                # Attempt to restore the state
                self.do_request("PATCH", annotation_url, json={"tags": {name: None for name in tag_names}})
            except NMOSTestException as e:
                if e.args[0].state == TestStates.FAIL:
                    raise
                result = result or e.args[0]

        return result or test.PASS()

    def check_tags_match_after_reset(self, test, after_reset, after_second, node):
        after_reset_tags = after_reset.get("tags") or {}
        after_second_tags = after_second.get("tags") or {}
        if after_second_tags != after_reset_tags:
            raise NMOSTestException(test.FAIL(
                f"After reset, tags {after_second_tags!r} do not match the values after the first reset "
                f"{after_reset_tags!r}",
                link=self.reset_link()))
        node_tags = node.get("tags") or {}
        if node_tags != after_reset_tags:
            raise NMOSTestException(test.FAIL(
                f"Node API tags {node_tags!r} do not match the values after the first reset {after_reset_tags!r}",
                link=self.consistent_link()))

    def do_named_tag_reset_sequence(self, test, resource_type):
        """Reset a named tag, write it, reset again and compare the whole tags object."""
        tag_name = USER_TAG_PREFIX + "nmos-testing-reset"
        for annotation_url, node_url in self.iter_resource_urls(test, resource_type):
            after_reset, _ = self.patch_and_check(
                test, resource_type, annotation_url, node_url,
                {"tags": {tag_name: None}},
                {},
                self.reset_link())

            self.patch_and_check(
                test, resource_type, annotation_url, node_url,
                {"tags": {tag_name: deepcopy(USER_TAG_VALUE)}},
                {"tags": {tag_name: USER_TAG_VALUE}},
                self.limit_link())

            after_second, node = self.patch_and_check(
                test, resource_type, annotation_url, node_url,
                {"tags": {tag_name: None}},
                {"tags": {tag_name: (after_reset.get("tags") or {}).get(tag_name)}},
                self.reset_link())
            self.check_tags_match_after_reset(test, after_reset, after_second, node)

        return test.PASS()

    def do_all_tags_reset_sequence(self, test, resource_type):
        """Reset all tags, write one user tag, reset all again and compare, then restore any removed tags."""
        tag_name = USER_TAG_PREFIX + "nmos-testing-reset-all"
        for annotation_url, node_url in self.iter_resource_urls(test, resource_type):
            initial = self.get_json(test, annotation_url, ANNOTATION_API_KEY)
            after_reset, node_after_reset = self.patch_and_check(
                test, resource_type, annotation_url, node_url,
                {"tags": None},
                {},
                self.reset_link())
            for name, values in (initial.get("tags") or {}).items():
                if not is_read_only_tag(name):
                    continue
                if (after_reset.get("tags") or {}).get(name) != values:
                    raise NMOSTestException(test.FAIL(
                        f"Read-only tag {name!r} changed after PATCH tags null",
                        link=self.read_only_link()))
                if (node_after_reset.get("tags") or {}).get(name) != values:
                    raise NMOSTestException(test.FAIL(
                        f"Node API read-only tag {name!r} changed after PATCH tags null",
                        link=self.consistent_link()))

            self.patch_and_check(
                test, resource_type, annotation_url, node_url,
                {"tags": {tag_name: deepcopy(USER_TAG_VALUE)}},
                {"tags": {tag_name: USER_TAG_VALUE}},
                self.limit_link())

            after_second, node = self.patch_and_check(
                test, resource_type, annotation_url, node_url,
                {"tags": None},
                {},
                self.reset_link())
            self.check_tags_match_after_reset(test, after_reset, after_second, node)
            # Attempt to restore the state
            initial_writable_tags = writable_tags(initial.get("tags") or {})
            if initial_writable_tags != writable_tags(after_second.get("tags") or {}):
                self.do_request("PATCH", annotation_url, json={"tags": initial_writable_tags})

        return test.PASS()

    def test_00(self, test):
        """Node API advertises the Annotation API as a service"""
        node_self = self.get_json(test, f"{self.node_url}self", NODE_API_KEY)
        services = node_self.get("services")
        if not isinstance(services, list):
            raise NMOSTestException(test.FAIL(
                "Node self resource has no services array",
                link=self.discovery_link()))

        expected_type = f"{ANNOTATION_SERVICE_TYPE_PREFIX}/{self.apis[ANNOTATION_API_KEY]['version']}"
        matches = [s for s in services if isinstance(s, dict) and s.get("type") == expected_type]
        if not matches:
            raise NMOSTestException(test.WARNING(
                f"Node self services array does not advertise {expected_type}",
                link=self.discovery_link()))

        for service in matches:
            href = service.get("href")
            if href and NMOSUtils.compare_urls(href, self.annotation_url):
                return test.PASS()

        hrefs = [s.get("href") for s in matches]
        raise NMOSTestException(test.FAIL(
            f"Annotation service href {hrefs} does not match the API under test {self.annotation_url}",
            link=self.discovery_link()))

    def test_01(self, test):
        """Annotation and Node API resources match for self, devices, sources, flows, senders and receivers"""
        checked = 0
        for resource_type in RESOURCE_TYPES:
            annotation_list_url = f"{self.annotation_url}node/{resource_type}"
            node_list_url = f"{self.node_url}{resource_type}"
            if resource_type == "self":
                self.get_and_check(test, resource_type, annotation_list_url, node_list_url)
                checked += 1
                continue

            annotation_ids = self.parse_resource_ids(
                test, annotation_list_url,
                self.get_json(test, annotation_list_url, ANNOTATION_API_KEY))
            node_ids = self.parse_resource_ids(
                test, node_list_url, self.get_json(test, node_list_url, NODE_API_KEY))
            missing_from_node = sorted(set(annotation_ids) - set(node_ids))
            if missing_from_node:
                raise NMOSTestException(test.FAIL(
                    f"{resource_type}: Annotation API ids {missing_from_node} are not present in the Node API",
                    link=self.consistent_link()))
            # Sources and Flows have a get-out: the Annotation API MAY omit them, including all of them.
            missing_from_annotation = sorted(set(node_ids) - set(annotation_ids))
            if missing_from_annotation and resource_type not in OPTIONAL_RESOURCE_TYPES:
                raise NMOSTestException(test.FAIL(
                    f"{resource_type}: Node API ids {missing_from_annotation} are not present in the Annotation API",
                    link=self.consistent_link()))

            node_id_set = set(node_ids)
            common_ids = [resource_id for resource_id in annotation_ids if resource_id in node_id_set]
            for resource_id in NMOSUtils.sampled_list(common_ids):
                self.get_and_check(
                    test, resource_type,
                    f"{annotation_list_url}/{resource_id}", f"{node_list_url}/{resource_id}")
                checked += 1
        if checked == 0:
            return test.UNCLEAR("No resources found to compare")
        return test.PASS()

    def test_02(self, test):
        """Node self label: reset, write 64 bytes, reset again (MUST)"""
        return self.do_label_or_description_sequence(test, "self", "label", "MUST")

    def test_03(self, test):
        """Node self description: reset, write 64 bytes, reset again (SHOULD)"""
        return self.do_label_or_description_sequence(test, "self", "description", "SHOULD")

    def test_04(self, test):
        """Node self tags: write 1 user-namespace tag of 64-byte name and value (MUST)"""
        return self.do_tags_sequence(test, "self", [USER_TAG_NAME_MAX_LENGTH], "MUST")

    def test_05(self, test):
        """Node self tags: write 5 user-namespace tags (SHOULD)"""
        return self.do_tags_sequence(test, "self", USER_TAG_NAMES_FIVE, "SHOULD")

    def test_06(self, test):
        """Node self tags: write 1 user-namespace tag with 2 values (MAY)"""
        return self.do_tags_sequence(test, "self", [USER_TAG_NAME_TWO_VALUES], "MAY", USER_TAG_TWO_VALUES)

    def test_07(self, test):
        """Node self tags: named tag reset, write, reset again (MUST)"""
        return self.do_named_tag_reset_sequence(test, "self")

    def test_08(self, test):
        """Node self tags: reset all, write one user tag, reset again (MUST)"""
        return self.do_all_tags_reset_sequence(test, "self")

    def test_09(self, test):
        """Device label: reset, write 64 bytes, reset again (MUST)"""
        return self.do_label_or_description_sequence(test, "devices", "label", "MUST")

    def test_10(self, test):
        """Device description: reset, write 64 bytes, reset again (SHOULD)"""
        return self.do_label_or_description_sequence(test, "devices", "description", "SHOULD")

    def test_11(self, test):
        """Device tags: write 1 user-namespace tag of 64-byte name and value (MUST)"""
        return self.do_tags_sequence(test, "devices", [USER_TAG_NAME_MAX_LENGTH], "MUST")

    def test_12(self, test):
        """Device tags: write 5 user-namespace tags (SHOULD)"""
        return self.do_tags_sequence(test, "devices", USER_TAG_NAMES_FIVE, "SHOULD")

    def test_13(self, test):
        """Device tags: write 1 user-namespace tag with 2 values (MAY)"""
        return self.do_tags_sequence(test, "devices", [USER_TAG_NAME_TWO_VALUES], "MAY", USER_TAG_TWO_VALUES)

    def test_14(self, test):
        """Device tags: named tag reset, write, reset again (MUST)"""
        return self.do_named_tag_reset_sequence(test, "devices")

    def test_15(self, test):
        """Device tags: reset all, write one user tag, reset again (MUST)"""
        return self.do_all_tags_reset_sequence(test, "devices")

    def test_16(self, test):
        """Source label: reset, write 64 bytes, reset again (MUST)"""
        return self.do_label_or_description_sequence(test, "sources", "label", "MUST")

    def test_17(self, test):
        """Source description: reset, write 64 bytes, reset again (SHOULD)"""
        return self.do_label_or_description_sequence(test, "sources", "description", "SHOULD")

    def test_18(self, test):
        """Source tags: write 1 user-namespace tag of 64-byte name and value (MUST)"""
        return self.do_tags_sequence(test, "sources", [USER_TAG_NAME_MAX_LENGTH], "MUST")

    def test_19(self, test):
        """Source tags: write 5 user-namespace tags (SHOULD)"""
        return self.do_tags_sequence(test, "sources", USER_TAG_NAMES_FIVE, "SHOULD")

    def test_20(self, test):
        """Source tags: write 1 user-namespace tag with 2 values (MAY)"""
        return self.do_tags_sequence(test, "sources", [USER_TAG_NAME_TWO_VALUES], "MAY", USER_TAG_TWO_VALUES)

    def test_21(self, test):
        """Source tags: named tag reset, write, reset again (MUST)"""
        return self.do_named_tag_reset_sequence(test, "sources")

    def test_22(self, test):
        """Source tags: reset all, write one user tag, reset again (MUST)"""
        return self.do_all_tags_reset_sequence(test, "sources")

    def test_23(self, test):
        """Flow label: reset, write 64 bytes, reset again (MUST)"""
        return self.do_label_or_description_sequence(test, "flows", "label", "MUST")

    def test_24(self, test):
        """Flow description: reset, write 64 bytes, reset again (SHOULD)"""
        return self.do_label_or_description_sequence(test, "flows", "description", "SHOULD")

    def test_25(self, test):
        """Flow tags: write 1 user-namespace tag of 64-byte name and value (MUST)"""
        return self.do_tags_sequence(test, "flows", [USER_TAG_NAME_MAX_LENGTH], "MUST")

    def test_26(self, test):
        """Flow tags: write 5 user-namespace tags (SHOULD)"""
        return self.do_tags_sequence(test, "flows", USER_TAG_NAMES_FIVE, "SHOULD")

    def test_27(self, test):
        """Flow tags: write 1 user-namespace tag with 2 values (MAY)"""
        return self.do_tags_sequence(test, "flows", [USER_TAG_NAME_TWO_VALUES], "MAY", USER_TAG_TWO_VALUES)

    def test_28(self, test):
        """Flow tags: named tag reset, write, reset again (MUST)"""
        return self.do_named_tag_reset_sequence(test, "flows")

    def test_29(self, test):
        """Flow tags: reset all, write one user tag, reset again (MUST)"""
        return self.do_all_tags_reset_sequence(test, "flows")

    def test_30(self, test):
        """Sender label: reset, write 64 bytes, reset again (MUST)"""
        return self.do_label_or_description_sequence(test, "senders", "label", "MUST")

    def test_31(self, test):
        """Sender description: reset, write 64 bytes, reset again (SHOULD)"""
        return self.do_label_or_description_sequence(test, "senders", "description", "SHOULD")

    def test_32(self, test):
        """Sender tags: write 1 user-namespace tag of 64-byte name and value (MUST)"""
        return self.do_tags_sequence(test, "senders", [USER_TAG_NAME_MAX_LENGTH], "MUST")

    def test_33(self, test):
        """Sender tags: write 5 user-namespace tags (SHOULD)"""
        return self.do_tags_sequence(test, "senders", USER_TAG_NAMES_FIVE, "SHOULD")

    def test_34(self, test):
        """Sender tags: write 1 user-namespace tag with 2 values (MAY)"""
        return self.do_tags_sequence(test, "senders", [USER_TAG_NAME_TWO_VALUES], "MAY", USER_TAG_TWO_VALUES)

    def test_35(self, test):
        """Sender tags: named tag reset, write, reset again (MUST)"""
        return self.do_named_tag_reset_sequence(test, "senders")

    def test_36(self, test):
        """Sender tags: reset all, write one user tag, reset again (MUST)"""
        return self.do_all_tags_reset_sequence(test, "senders")

    def test_37(self, test):
        """Receiver label: reset, write 64 bytes, reset again (MUST)"""
        return self.do_label_or_description_sequence(test, "receivers", "label", "MUST")

    def test_38(self, test):
        """Receiver description: reset, write 64 bytes, reset again (SHOULD)"""
        return self.do_label_or_description_sequence(test, "receivers", "description", "SHOULD")

    def test_39(self, test):
        """Receiver tags: write 1 user-namespace tag of 64-byte name and value (MUST)"""
        return self.do_tags_sequence(test, "receivers", [USER_TAG_NAME_MAX_LENGTH], "MUST")

    def test_40(self, test):
        """Receiver tags: write 5 user-namespace tags (SHOULD)"""
        return self.do_tags_sequence(test, "receivers", USER_TAG_NAMES_FIVE, "SHOULD")

    def test_41(self, test):
        """Receiver tags: write 1 user-namespace tag with 2 values (MAY)"""
        return self.do_tags_sequence(test, "receivers", [USER_TAG_NAME_TWO_VALUES], "MAY", USER_TAG_TWO_VALUES)

    def test_42(self, test):
        """Receiver tags: named tag reset, write, reset again (MUST)"""
        return self.do_named_tag_reset_sequence(test, "receivers")

    def test_43(self, test):
        """Receiver tags: reset all, write one user tag, reset again (MUST)"""
        return self.do_all_tags_reset_sequence(test, "receivers")

    def test_44(self, test):
        """Read-only tags are not updated by PATCH (group hint / asset tags)"""
        checked = 0
        result = None
        for resource_type in RESOURCE_TYPES:
            try:
                resource_urls = list(self.iter_resource_urls(test, resource_type))
            except NMOSTestException as e:
                if e.args[0].state == TestStates.FAIL:
                    raise
                if e.args[0].state not in (TestStates.UNCLEAR, TestStates.NA):
                    result = result or e.args[0]
                continue
            for annotation_url, node_url in resource_urls:
                initial = self.get_json(test, annotation_url, ANNOTATION_API_KEY)
                read_only = {name: values for name, values in (initial.get("tags") or {}).items()
                             if is_read_only_tag(name)}
                for name, values in read_only.items():
                    # A valid value means a rejected PATCH is due to the tag being read-only
                    new_values = GROUP_HINT_TAG_VALUE if name == GROUP_HINT_TAG_NAME else ["nmos-testing"]
                    valid, response = self.do_request(
                        "PATCH", annotation_url, json={"tags": {name: new_values}})
                    if not valid:
                        raise NMOSTestException(test.FAIL(f"PATCH {annotation_url} failed: {response}"))
                    # Rejecting an update of a read-only tag is optional. When the API does reject it,
                    # the response is 500 and the tag is left unchanged.
                    if response.status_code != 500:
                        after = self.get_json(test, annotation_url, ANNOTATION_API_KEY)
                        time.sleep(CONFIG.API_PROCESSING_TIMEOUT)
                        node = self.get_json(test, node_url, NODE_API_KEY)
                        after_values = (after.get("tags") or {}).get(name)
                        node_values = (node.get("tags") or {}).get(name)
                        changed = after_values != values or node_values != values
                        # Attempt to restore the state
                        if changed:
                            self.do_request("PATCH", annotation_url, json={"tags": {name: values}})
                        result = result or test.WARNING(
                            f"PATCH of read-only tag {name!r} on {resource_type} returned HTTP "
                            f"{response.status_code}. The specification permits rejecting this update with 500."
                            + (" The tag value changed; a restore PATCH was attempted." if changed else ""),
                            link=self.read_only_link())
                        continue
                    valid_error, message = self.check_error_response("PATCH", response, 500)
                    if not valid_error:
                        raise NMOSTestException(test.FAIL(
                            f"PATCH of read-only tag {name!r} on {resource_type} returned HTTP 500 "
                            f"but the error body failed checks: {message}",
                            link=self.read_only_link()))

                    after = self.get_json(test, annotation_url, ANNOTATION_API_KEY)
                    if (after.get("tags") or {}).get(name) != values:
                        raise NMOSTestException(test.FAIL(
                            f"Read-only tag {name!r} on {resource_type} changed after a rejected PATCH",
                            link=self.read_only_link()))
                    time.sleep(CONFIG.API_PROCESSING_TIMEOUT)
                    node = self.get_json(test, node_url, NODE_API_KEY)
                    if (node.get("tags") or {}).get(name) != values:
                        raise NMOSTestException(test.FAIL(
                            f"Node API read-only tag {name!r} on {resource_type} changed after a rejected PATCH",
                            link=self.consistent_link()))
                    checked += 1
        if result:
            return result
        if checked == 0:
            return test.UNCLEAR(
                "No BCP-002-01 group hint or BCP-002-02 asset tags found on sampled resources")
        return test.PASS()

    def test_45(self, test):
        """Invalid tag values are rejected by PATCH"""
        checked = 0
        result = None
        name = USER_TAG_NAME_INVALID
        for resource_type in RESOURCE_TYPES:
            try:
                resource_urls = list(self.iter_resource_urls(test, resource_type))
            except NMOSTestException as e:
                if e.args[0].state == TestStates.FAIL:
                    raise
                if e.args[0].state not in (TestStates.UNCLEAR, TestStates.NA):
                    result = result or e.args[0]
                continue
            for annotation_url, node_url in resource_urls:
                valid, response = self.do_request(
                    "PATCH", annotation_url, json={"tags": {name: INVALID_TAG_VALUE}})
                if not valid:
                    raise NMOSTestException(test.FAIL(f"PATCH {annotation_url} failed: {response}"))
                if response.status_code >= 400:
                    valid_error, message = self.check_error_response("PATCH", response, response.status_code)
                    if not valid_error:
                        raise NMOSTestException(test.FAIL(
                            f"PATCH of invalid tag value on {resource_type} returned HTTP "
                            f"{response.status_code} but the error body failed checks: {message}"))
                elif response.status_code == 200:
                    schema_path = self.patch_schema_path(resource_type)
                    schema = self.get_schema(ANNOTATION_API_KEY, "PATCH", schema_path, 200)
                    if not schema:
                        raise NMOSTestException(test.MANUAL(
                            f"Test suite unable to locate PATCH 200 schema for {schema_path}"))
                    valid_body, message = self.check_response(schema, "PATCH", response)
                    if not valid_body:
                        raise NMOSTestException(test.FAIL(
                            f"PATCH of invalid tag value on {resource_type} returned HTTP 200 "
                            f"but the response failed schema or header checks: {message}",
                            link=self.successful_link()))

                after = self.get_json(test, annotation_url, ANNOTATION_API_KEY)
                if (after.get("tags") or {}).get(name) == INVALID_TAG_VALUE:
                    raise NMOSTestException(test.FAIL(
                        f"Annotation API {resource_type} tag {name!r} has the invalid value "
                        f"{INVALID_TAG_VALUE!r} after PATCH", link=self.validation_link()))
                time.sleep(CONFIG.API_PROCESSING_TIMEOUT)
                node = self.get_json(test, node_url, NODE_API_KEY)
                if (node.get("tags") or {}).get(name) == INVALID_TAG_VALUE:
                    raise NMOSTestException(test.FAIL(
                        f"Node API {resource_type} tag {name!r} has the invalid value "
                        f"{INVALID_TAG_VALUE!r} after PATCH", link=self.validation_link()))

                if response.status_code != 400:
                    result = result or test.WARNING(
                        f"PATCH of invalid tag value on {resource_type} returned HTTP "
                        f"{response.status_code}, expected 400", link=self.validation_link())
                    # Attempt to restore the state
                    if name in (after.get("tags") or {}):
                        self.do_request("PATCH", annotation_url, json={"tags": {name: None}})
                checked += 1
        if result:
            return result
        if checked == 0:
            return test.UNCLEAR("No resources found to PATCH")
        return test.PASS()
