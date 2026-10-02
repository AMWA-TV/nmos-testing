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
STRING_MAX_LENGTH_VALUE = "X" * 64
USER_TAG_PREFIX = "urn:x-nmos:tag:user:"
USER_TAG_VALUE = ["Y" * 64]
# Full tag name of 64 bytes including the required user-namespace prefix
USER_TAG_NAME_MAX_LENGTH = USER_TAG_PREFIX + "Z" * (64 - len(USER_TAG_PREFIX.encode("utf-8")))
USER_TAG_NAMES_FIVE = [f"{USER_TAG_PREFIX}nmos-testing-{i}" for i in range(5)]

READ_ONLY_TAG_PREFIXES = (
    "urn:x-nmos:tag:grouphint/",
    "urn:x-nmos:tag:asset:",
)

RESOURCE_TYPES = ("self", "devices", "sources", "flows", "senders", "receivers")
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

    def list_resource_ids(self, test, resource_type):
        """Return Annotation API resource IDs for a list type, or raise UNCLEAR if the list is empty."""
        annotation_list_url = f"{self.annotation_url}node/{resource_type}"
        annotation_list = self.get_json(test, annotation_list_url, ANNOTATION_API_KEY)
        if not annotation_list:
            raise NMOSTestException(test.UNCLEAR(
                f"No {resource_type} found at {annotation_list_url}"))

        resource_ids = []
        for entry in annotation_list:
            if isinstance(entry, str):
                resource_ids.append(entry.rstrip("/"))
            elif isinstance(entry, dict) and "id" in entry:
                resource_ids.append(entry["id"])
            else:
                raise NMOSTestException(test.FAIL(
                    f"Unexpected list entry at {annotation_list_url}: {entry!r}"))
        return resource_ids

    def iter_resource_urls(self, test, resource_type):
        """
        Yield matching Annotation API and Node API URLs.
        List resources are limited by CONFIG.MAX_TEST_ITERATIONS (0 = all).
        """
        annotation_list_url = f"{self.annotation_url}node/{resource_type}"
        node_list_url = f"{self.node_url}{resource_type}"
        if resource_type == "self":
            yield f"{annotation_list_url}/", f"{node_list_url}/"
            return
        for resource_id in NMOSUtils.sampled_list(self.list_resource_ids(test, resource_type)):
            yield f"{annotation_list_url}/{resource_id}/", f"{node_list_url}/{resource_id}/"

    def patch_schema_path(self, resource_type):
        if resource_type == "self":
            return "/node/self"
        return f"/node/{resource_type}/{{{RESOURCE_ID_PARAMS[resource_type]}}}"

    def restore_annotations(self, url, initial, extra_tag_names=None):
        """Best-effort restore of label, description and writable tags."""
        extra_tag_names = extra_tag_names or []
        tags_patch = {name: None for name in extra_tag_names}
        tags_patch.update(writable_tags(initial.get("tags", {})))
        body = {
            "label": initial.get("label"),
            "description": initial.get("description"),
            "tags": tags_patch
        }
        self.do_request("PATCH", url, json=body)

    def patch_and_check(self, test, resource_type, annotation_url, node_url, patch_body, check_values, link,
                        requirement="MUST"):
        """
        PATCH the Annotation API, then check the Annotation and Node APIs.
        check_values is a dict of annotation properties that MUST match after the PATCH.
        For tags, only the named keys in check_values['tags'] are compared.
        requirement: 'MUST' fails on HTTP error; 'SHOULD' warns.
        Raises NMOSTestException. Returns the Annotation GET body after the PATCH.
        """
        prev = self.get_json(test, annotation_url, ANNOTATION_API_KEY)

        valid, response = self.do_request("PATCH", annotation_url, json=patch_body)
        if not valid:
            raise NMOSTestException(test.FAIL(f"PATCH {annotation_url} failed: {response}", link=link))
        if response.status_code != 200:
            detail = (f"PATCH {annotation_url} returned HTTP {response.status_code}, expected 200. "
                      f"Body: {getattr(response, 'text', '')}")
            if requirement == "SHOULD":
                raise NMOSTestException(test.WARNING(detail, link=link))
            raise NMOSTestException(test.FAIL(detail, link=link))

        schema = self.get_schema(ANNOTATION_API_KEY, "PATCH", self.patch_schema_path(resource_type), 200)
        if not schema:
            raise NMOSTestException(test.MANUAL(
                f"Test suite unable to locate PATCH 200 schema for {self.patch_schema_path(resource_type)}"))
        valid_body, message = self.check_response(schema, "PATCH", response)
        if not valid_body:
            raise NMOSTestException(test.FAIL(
                f"PATCH {annotation_url} response failed schema or header checks: {message}",
                link=self.spec_link("Behaviour.html#successful-response")))

        time.sleep(CONFIG.API_PROCESSING_TIMEOUT)

        annotation = self.get_json(test, annotation_url, ANNOTATION_API_KEY)
        node = self.get_json(test, node_url, NODE_API_KEY)

        if annotation.get("id") != node.get("id"):
            raise NMOSTestException(test.FAIL(
                f"Annotation resource id {annotation.get('id')} does not match Node API id {node.get('id')}",
                link=self.spec_link("Interoperability_-_IS-04.html#consistent-resources")))

        if NMOSUtils.compare_resource_version(annotation["version"], prev["version"]) <= 0:
            raise NMOSTestException(test.FAIL(
                f"Annotation version did not increase after PATCH "
                f"(before {prev['version']}, after {annotation['version']})",
                link=self.spec_link("Behaviour.html#successful-response")))

        if annotation["version"] != node["version"]:
            raise NMOSTestException(test.FAIL(
                f"Annotation version {annotation['version']} does not match Node API version {node['version']}",
                link=self.spec_link("Interoperability_-_IS-04.html#version-increments")))

        for name, expected in check_values.items():
            if name == "tags":
                for tag_name, tag_values in expected.items():
                    if annotation.get("tags", {}).get(tag_name) != tag_values:
                        raise NMOSTestException(test.FAIL(
                            f"Annotation tags[{tag_name!r}] is {annotation.get('tags', {}).get(tag_name)!r}, "
                            f"expected {tag_values!r}",
                            link=link))
                    if node.get("tags", {}).get(tag_name) != tag_values:
                        raise NMOSTestException(test.FAIL(
                            f"Node API tags[{tag_name!r}] is {node.get('tags', {}).get(tag_name)!r}, "
                            f"expected {tag_values!r}",
                            link=self.spec_link("Interoperability_-_IS-04.html#consistent-resources")))
            else:
                if annotation.get(name) != expected:
                    raise NMOSTestException(test.FAIL(
                        f"Annotation {name} is {annotation.get(name)!r}, expected {expected!r}",
                        link=link))
                if node.get(name) != expected:
                    raise NMOSTestException(test.FAIL(
                        f"Node API {name} is {node.get(name)!r}, expected {expected!r}",
                        link=self.spec_link("Interoperability_-_IS-04.html#consistent-resources")))

        return annotation

    def do_label_or_description_sequence(self, test, resource_type, annotation_property, requirement):
        """
        Reset the property, write a 64-byte value, reset again and compare, then restore.
        """
        reset_link = self.spec_link("Behaviour.html#resetting-values")
        limit_link = self.spec_link("Behaviour.html#additional-limitations")
        for annotation_url, node_url in self.iter_resource_urls(test, resource_type):
            initial = self.get_json(test, annotation_url, ANNOTATION_API_KEY)
            try:
                after_reset = self.patch_and_check(
                    test, resource_type, annotation_url, node_url,
                    {annotation_property: None},
                    {},
                    reset_link,
                    requirement)
                if after_reset.get(annotation_property) is None:
                    raise NMOSTestException(test.FAIL(
                        f"After reset, {annotation_property} must be a string, not null",
                        link=reset_link))

                self.patch_and_check(
                    test, resource_type, annotation_url, node_url,
                    {annotation_property: STRING_MAX_LENGTH_VALUE},
                    {annotation_property: STRING_MAX_LENGTH_VALUE},
                    limit_link,
                    requirement)

                self.patch_and_check(
                    test, resource_type, annotation_url, node_url,
                    {annotation_property: None},
                    {annotation_property: after_reset.get(annotation_property)},
                    reset_link,
                    requirement)
            finally:
                self.restore_annotations(annotation_url, initial)

        return test.PASS()

    def do_tags_sequence(self, test, resource_type, tag_names, requirement):
        """Write 1 or 5 user-namespace tags of the required minimum size, then restore."""
        tags_patch = {name: deepcopy(USER_TAG_VALUE) for name in tag_names}
        for annotation_url, node_url in self.iter_resource_urls(test, resource_type):
            initial = self.get_json(test, annotation_url, ANNOTATION_API_KEY)
            try:
                self.patch_and_check(
                    test, resource_type, annotation_url, node_url,
                    {"tags": tags_patch},
                    {"tags": tags_patch},
                    self.spec_link("Behaviour.html#additional-limitations"),
                    requirement)
            finally:
                self.restore_annotations(annotation_url, initial, list(tag_names))

        return test.PASS()

    def check_tags_match_after_reset(self, test, after_reset, after_second, node, reset_link):
        after_reset_tags = after_reset.get("tags") or {}
        after_second_tags = after_second.get("tags") or {}
        if after_second_tags != after_reset_tags:
            raise NMOSTestException(test.FAIL(
                f"After reset, tags {after_second_tags!r} do not match the values after the first reset "
                f"{after_reset_tags!r}",
                link=reset_link))
        node_tags = node.get("tags") or {}
        if node_tags != after_reset_tags:
            raise NMOSTestException(test.FAIL(
                f"Node API tags {node_tags!r} do not match the values after the first reset {after_reset_tags!r}",
                link=self.spec_link("Interoperability_-_IS-04.html#consistent-resources")))

    def do_named_tag_reset_sequence(self, test, resource_type):
        """Reset a named tag, write it, reset again and compare the whole tags object, then restore."""
        reset_link = self.spec_link("Behaviour.html#resetting-values")
        limit_link = self.spec_link("Behaviour.html#additional-limitations")
        tag_name = USER_TAG_PREFIX + "nmos-testing-reset"
        for annotation_url, node_url in self.iter_resource_urls(test, resource_type):
            initial = self.get_json(test, annotation_url, ANNOTATION_API_KEY)
            try:
                after_reset = self.patch_and_check(
                    test, resource_type, annotation_url, node_url,
                    {"tags": {tag_name: None}},
                    {},
                    reset_link)

                self.patch_and_check(
                    test, resource_type, annotation_url, node_url,
                    {"tags": {tag_name: deepcopy(USER_TAG_VALUE)}},
                    {"tags": {tag_name: USER_TAG_VALUE}},
                    limit_link)

                after_second = self.patch_and_check(
                    test, resource_type, annotation_url, node_url,
                    {"tags": {tag_name: None}},
                    {"tags": {tag_name: (after_reset.get("tags") or {}).get(tag_name)}},
                    reset_link)
                node = self.get_json(test, node_url, NODE_API_KEY)
                self.check_tags_match_after_reset(test, after_reset, after_second, node, reset_link)
            finally:
                self.restore_annotations(annotation_url, initial, [tag_name])

        return test.PASS()

    def do_all_tags_reset_sequence(self, test, resource_type):
        """Reset all tags, write one user tag, reset all again and compare, then restore."""
        reset_link = self.spec_link("Behaviour.html#resetting-values")
        limit_link = self.spec_link("Behaviour.html#additional-limitations")
        readonly_link = self.spec_link("Behaviour.html#read-only-tags")
        tag_name = USER_TAG_PREFIX + "nmos-testing-reset-all"
        for annotation_url, node_url in self.iter_resource_urls(test, resource_type):
            initial = self.get_json(test, annotation_url, ANNOTATION_API_KEY)
            try:
                after_reset = self.patch_and_check(
                    test, resource_type, annotation_url, node_url,
                    {"tags": None},
                    {},
                    reset_link)
                node_after_reset = self.get_json(test, node_url, NODE_API_KEY)
                for name, values in (initial.get("tags") or {}).items():
                    if not is_read_only_tag(name):
                        continue
                    if (after_reset.get("tags") or {}).get(name) != values:
                        raise NMOSTestException(test.FAIL(
                            f"Read-only tag {name!r} changed after PATCH tags null",
                            link=readonly_link))
                    if (node_after_reset.get("tags") or {}).get(name) != values:
                        raise NMOSTestException(test.FAIL(
                            f"Node API read-only tag {name!r} changed after PATCH tags null",
                            link=self.spec_link("Interoperability_-_IS-04.html#consistent-resources")))

                self.patch_and_check(
                    test, resource_type, annotation_url, node_url,
                    {"tags": {tag_name: deepcopy(USER_TAG_VALUE)}},
                    {"tags": {tag_name: USER_TAG_VALUE}},
                    limit_link)

                after_second = self.patch_and_check(
                    test, resource_type, annotation_url, node_url,
                    {"tags": None},
                    {},
                    reset_link)
                node = self.get_json(test, node_url, NODE_API_KEY)
                self.check_tags_match_after_reset(test, after_reset, after_second, node, reset_link)
            finally:
                self.restore_annotations(annotation_url, initial, [tag_name])

        return test.PASS()

    def test_00(self, test):
        """Node API advertises the Annotation API as a service"""
        node_self = self.get_json(test, f"{self.node_url}self/", NODE_API_KEY)
        services = node_self.get("services")
        if not isinstance(services, list):
            raise NMOSTestException(test.FAIL(
                "Node self resource has no services array",
                link=self.spec_link("Interoperability_-_IS-04.html#discovery")))

        matches = [s for s in services
                   if isinstance(s, dict) and str(s.get("type", "")).startswith(ANNOTATION_SERVICE_TYPE_PREFIX)]
        if not matches:
            raise NMOSTestException(test.WARNING(
                "Node self services array does not advertise urn:x-nmos:service:annotation",
                link=self.spec_link("Interoperability_-_IS-04.html#discovery")))

        for service in matches:
            href = service.get("href")
            if href and NMOSUtils.compare_urls(href, self.annotation_url):
                return test.PASS()

        hrefs = [s.get("href") for s in matches]
        raise NMOSTestException(test.FAIL(
            f"Annotation service href {hrefs} does not match the API under test {self.annotation_url}",
            link=self.spec_link("Interoperability_-_IS-04.html#discovery")))

    def test_01(self, test):
        """Annotation and Node API resource IDs match for self, devices, sources, flows, senders and receivers"""
        checked = 0
        for resource_type in RESOURCE_TYPES:
            try:
                resource_urls = list(self.iter_resource_urls(test, resource_type))
            except NMOSTestException as ex:
                # Skip types with no resources; fail on real GET errors
                result = ex.args[0] if ex.args else None
                if result is not None and getattr(result, "state", None) == TestStates.UNCLEAR:
                    continue
                raise
            for annotation_url, node_url in resource_urls:
                annotation = self.get_json(test, annotation_url, ANNOTATION_API_KEY)
                node = self.get_json(test, node_url, NODE_API_KEY)
                if annotation.get("id") != node.get("id"):
                    raise NMOSTestException(test.FAIL(
                        f"{resource_type}: Annotation id {annotation.get('id')} != Node API id {node.get('id')}",
                        link=self.spec_link("Interoperability_-_IS-04.html#consistent-resources")))
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
        """Node self tags: named tag reset, write, reset again (MUST)"""
        return self.do_named_tag_reset_sequence(test, "self")

    def test_07(self, test):
        """Node self tags: reset all, write one user tag, reset again (MUST)"""
        return self.do_all_tags_reset_sequence(test, "self")

    def test_08(self, test):
        """Device label: reset, write 64 bytes, reset again (MUST)"""
        return self.do_label_or_description_sequence(test, "devices", "label", "MUST")

    def test_09(self, test):
        """Device description: reset, write 64 bytes, reset again (SHOULD)"""
        return self.do_label_or_description_sequence(test, "devices", "description", "SHOULD")

    def test_10(self, test):
        """Device tags: write 1 user-namespace tag of 64-byte name and value (MUST)"""
        return self.do_tags_sequence(test, "devices", [USER_TAG_NAME_MAX_LENGTH], "MUST")

    def test_11(self, test):
        """Device tags: write 5 user-namespace tags (SHOULD)"""
        return self.do_tags_sequence(test, "devices", USER_TAG_NAMES_FIVE, "SHOULD")

    def test_12(self, test):
        """Device tags: named tag reset, write, reset again (MUST)"""
        return self.do_named_tag_reset_sequence(test, "devices")

    def test_13(self, test):
        """Device tags: reset all, write one user tag, reset again (MUST)"""
        return self.do_all_tags_reset_sequence(test, "devices")

    def test_14(self, test):
        """Sender label: reset, write 64 bytes, reset again (MUST)"""
        return self.do_label_or_description_sequence(test, "senders", "label", "MUST")

    def test_15(self, test):
        """Sender description: reset, write 64 bytes, reset again (SHOULD)"""
        return self.do_label_or_description_sequence(test, "senders", "description", "SHOULD")

    def test_16(self, test):
        """Sender tags: write 1 user-namespace tag of 64-byte name and value (MUST)"""
        return self.do_tags_sequence(test, "senders", [USER_TAG_NAME_MAX_LENGTH], "MUST")

    def test_17(self, test):
        """Sender tags: write 5 user-namespace tags (SHOULD)"""
        return self.do_tags_sequence(test, "senders", USER_TAG_NAMES_FIVE, "SHOULD")

    def test_18(self, test):
        """Sender tags: named tag reset, write, reset again (MUST)"""
        return self.do_named_tag_reset_sequence(test, "senders")

    def test_19(self, test):
        """Sender tags: reset all, write one user tag, reset again (MUST)"""
        return self.do_all_tags_reset_sequence(test, "senders")

    def test_20(self, test):
        """Receiver label: reset, write 64 bytes, reset again (MUST)"""
        return self.do_label_or_description_sequence(test, "receivers", "label", "MUST")

    def test_21(self, test):
        """Receiver description: reset, write 64 bytes, reset again (SHOULD)"""
        return self.do_label_or_description_sequence(test, "receivers", "description", "SHOULD")

    def test_22(self, test):
        """Receiver tags: write 1 user-namespace tag of 64-byte name and value (MUST)"""
        return self.do_tags_sequence(test, "receivers", [USER_TAG_NAME_MAX_LENGTH], "MUST")

    def test_23(self, test):
        """Receiver tags: write 5 user-namespace tags (SHOULD)"""
        return self.do_tags_sequence(test, "receivers", USER_TAG_NAMES_FIVE, "SHOULD")

    def test_24(self, test):
        """Receiver tags: named tag reset, write, reset again (MUST)"""
        return self.do_named_tag_reset_sequence(test, "receivers")

    def test_25(self, test):
        """Receiver tags: reset all, write one user tag, reset again (MUST)"""
        return self.do_all_tags_reset_sequence(test, "receivers")

    def test_26(self, test):
        """Read-only tags are not updated by PATCH (group hint / asset tags)"""
        checked = 0
        link = self.spec_link("Behaviour.html#read-only-tags")
        for resource_type in RESOURCE_TYPES:
            try:
                resource_urls = list(self.iter_resource_urls(test, resource_type))
            except NMOSTestException as ex:
                result = ex.args[0] if ex.args else None
                if result is not None and getattr(result, "state", None) == TestStates.UNCLEAR:
                    continue
                raise
            for annotation_url, node_url in resource_urls:
                initial = self.get_json(test, annotation_url, ANNOTATION_API_KEY)
                read_only = {name: values for name, values in initial.get("tags", {}).items()
                             if is_read_only_tag(name)}
                for name, values in read_only.items():
                    valid, response = self.do_request(
                        "PATCH", annotation_url, json={"tags": {name: ["nmos-testing"]}})
                    if not valid:
                        raise NMOSTestException(test.FAIL(f"PATCH {annotation_url} failed: {response}"))
                    if response.status_code != 500:
                        raise NMOSTestException(test.FAIL(
                            f"PATCH of read-only tag {name!r} on {resource_type} returned HTTP "
                            f"{response.status_code}, expected 500",
                            link=link))
                    valid_error, message = self.check_error_response("PATCH", response, 500)
                    if not valid_error:
                        raise NMOSTestException(test.FAIL(
                            f"PATCH of read-only tag {name!r} on {resource_type} returned HTTP 500 "
                            f"but the error body failed checks: {message}",
                            link=link))

                    time.sleep(CONFIG.API_PROCESSING_TIMEOUT)
                    after = self.get_json(test, annotation_url, ANNOTATION_API_KEY)
                    if after.get("tags", {}).get(name) != values:
                        raise NMOSTestException(test.FAIL(
                            f"Read-only tag {name!r} on {resource_type} changed after a rejected PATCH",
                            link=link))
                    node = self.get_json(test, node_url, NODE_API_KEY)
                    if node.get("tags", {}).get(name) != values:
                        raise NMOSTestException(test.FAIL(
                            f"Node API read-only tag {name!r} on {resource_type} changed after a rejected PATCH",
                            link=self.spec_link("Interoperability_-_IS-04.html#consistent-resources")))
                    checked += 1
        if checked == 0:
            return test.UNCLEAR(
                "No BCP-002-01 group hint or BCP-002-02 asset tags found on sampled resources")
        return test.PASS()
