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
The script implements the IS-13 test suite as specified by the nmos-resource-labelling workgroup.
At the end of the test, the initial state of the tested unit is supposed to be restored but this
cannot be garanteed.

In addition to the basic annotation API tests, this suite includes the test sequence:
For each resource type (self, devices, senders, receivers):
    For each annotable object type (label, description, tags):
        - Read initial value
            - store
        - Reset default value by sending null
            - check value + timestamp + is-14/value + is-04 timestamp
            - store
        - Write max-length
            - check value + timestamp + is-14/value + is-04 timestamp
        - Write >max-length
            - check value + timestamp + is-14/value + is-04 timestamp
        - Reset default value again
            - check value + timestamp + is-14/value + is-04 timestamp
            - compare with 1st reset
        - Restore initial value
"""

from ..GenericTest import GenericTest, NMOSTestException
from ..TestHelper import compare_json

from ..import TestHelper
import re
import copy
import time

ANNOTATION_API_KEY = "annotation"
NODE_API_KEY = "node"

RESOURCES = ["self", "devices", "senders", "receivers"]
OBJECTS = ["label", "description", "tags"]

# const for label&description-related tests
STRING_OVER_MAX_VALUE = ''.join(['X' for i in range(100)])
STRING_MAX_VALUE = STRING_OVER_MAX_VALUE[:64]  # this is the max length tolerated

# const for tags-related tests
TAGS_OVER_MAX_VALUE = {'location': ['underground'], 'studio': ['42'], 'tech': ['John', 'Mike']}
TAGS_MAX_VALUE = TAGS_OVER_MAX_VALUE.copy()
TAGS_OVER_MAX_VALUE.pop('tech')  # must have a max of 5
TAGS_TO_BE_SKIPPED = 'urn:x-nmos:tag:grouphint/v1.0'


def get_ts_from_version(version):
    """ Convert the 'version' object (string) into float """
    return float(re.sub(':', '.', version))


def strip_tags(tags):
    if TAGS_TO_BE_SKIPPED in list(tags.keys()):
        tags.pop(TAGS_TO_BE_SKIPPED)
    return tags


class IS1301Test(GenericTest):
    """
    Runs IS-13-Test
    """

    def __init__(self, apis, **kwargs):
        GenericTest.__init__(self, apis, **kwargs)
        self.annotation_url = self.apis[ANNOTATION_API_KEY]["url"]
        self.node_url = f"{self.apis[ANNOTATION_API_KEY]['base_url']}/x-nmos/node/{self.apis[NODE_API_KEY]['version']}/"

    def set_up_tests(self):
        """
        FAKE_ORIG = {
            'description': 'fake_orig_desc',
            'label': 'fake_orig_label',
            'tags': {
                'location': ['fake_location']
            }
        }
        for resource in RESOURCES:
            url = "{}{}{}".format(self.annotation_url, 'node/', resource)
            TestHelper.do_request("PATCH", url, json=FAKE_ORIG)
        """
        pass

    def get_resource(self, url):
        """ Get a resource """

        valid, r = self.do_request("GET", url)
        if valid and r.status_code == 200:
            try:
                return True, r.json()
            except Exception as e:
                return False, e.msg
        else:
            return False, "GET  Resquest FAIL"

    def compare_resource(self, object, new, resp):
        """ Compare string values (or "tags" dict) """

        if new[object] is None:  # this is a reset, new is null, skip
            return True, ""

        if object == "tags":  # tags needs to be stripped
            resp[object] = strip_tags(resp[object])
            if not TestHelper.compare_json(resp[object], new[object]):
                return False, f"{object} value FAIL"

        elif resp[object] != new[object]:
            return False, f"{object} value FAIL"

        return True, ""

    def set_resource(self, url, node_url, new, prev):
        """ Patch a resource with one ore several object values """

        object = list(new.keys())[0]
        valid, resp = TestHelper.do_request("PATCH", url, json=new)
        if not valid:
            return False, "PATCH Resquest FAIL"

        # pause to accomodate update propagation
        time.sleep(0.1)

        # re-GET
        valid, resp = self.get_resource(url)
        if not valid:
            return False, "Get Resquest FAIL"
        # check PATCH == GET
        valid, msg = self.compare_resource(object, new, resp)
        if not valid:
            return False, f"new {msg}"
        # check that the version (timestamp) has increased
        if get_ts_from_version(prev['version']) >= get_ts_from_version(resp['version']):
            return False, "new version (timestamp) FAIL"

        # validate that it is reflected in IS04
        valid, node_resp = self.get_resource(node_url)
        if not valid:
            return False, "GET IS-04 Node FAIL"
        # check PATCH == GET
        valid, msg = self.compare_resource(object, new, resp)
        if not valid:
            return False, f"new IS-04/node/.../ {msg}"
        # check that the version (timestamp) has increased
        if get_ts_from_version(node_resp['version']) != get_ts_from_version(resp['version']):
            return False, "new IS-04/node/.../version (timestamp) FAIL"

        return True, resp

    def log(self, msg):
        print(msg)

    def get_url(self, base_url, resource):
        """
        Build the url for both annotation and node APIs which behaves differently.
        For iterables resources (devices, senders, receivers), return the 1st element.
        """

        url = f"{base_url}{resource}"
        if resource != "self":
            valid, r = self.get_resource(url)
            if valid:
                if isinstance(r[0], str):  # in annotation api
                    index = r[0]
                elif isinstance(r[0], dict):  # in node api
                    index = r[0]['id']
                else:
                    return None
                url = f"{url}/{index}"
            else:
                return None

        return url

    def do_test(self, test, resource, object):
        """
        Perform the test sequence as documented in the file header
        """

        url = self.get_url(f"{self.annotation_url}node/", resource)
        if not url:
            msg = f"Can't get annotation url for {resource}"
            self.log(f"    FAIL {msg}")
            return test.FAIL(msg)

        node_url = self.get_url(self.node_url, resource)
        if not url:
            msg = f"Can't get node url for {resource}"
            self.log(f"    FAIL {msg}")
            return test.FAIL(msg)

        valid, r = self.get_resource(url)
        msg = f"SAVE initial: {r}"
        self.log(f"    {msg}")
        if valid:
            prev = r
            initial = copy.copy(r)
            initial.pop('id')
            initial.pop('version')
            initial['tags'] = strip_tags(initial['tags'])
        else:
            self.log("    FAIL")
            return test.FAIL(f"Can't {msg}")

        valid, r = self.set_resource(url, node_url, {object: None}, prev)
        msg = f"RESET to default and save: {r}"
        self.log(f"    {msg}")
        if valid:
            default = prev = r
        else:
            self.log("    FAIL")
            return test.FAIL(f"Can't {msg}")

        value = TAGS_MAX_VALUE if object == "tags" else STRING_MAX_VALUE
        valid, r = self.set_resource(url, node_url, {object: value}, prev)
        msg = f"SET MAX value and expected complete response: {r}"
        self.log(f"    {msg}")
        if valid:
            prev = r
        else:
            self.log("    FAIL")
            return test.FAIL(f"Can't {msg}")

        value = TAGS_OVER_MAX_VALUE if object == "tags" else STRING_OVER_MAX_VALUE
        valid, r = self.set_resource(url, node_url, {object: value}, prev)
        msg = f"SET >MAX value and expect truncated response: {r}"
        self.log(f"    {msg}")
        if valid:
            prev = r
            self.log(f"    {msg}")
            if object == "tags" and not TestHelper.compare_json(r[object], TAGS_MAX_VALUE) or r[object] != STRING_MAX_VALUE:
                return test.FAIL(f"Can't {msg}")
        else:
            self.log("    FAIL")
            return test.FAIL(f"Can't {msg}")

        valid, r = self.set_resource(url, node_url, {object: None}, prev)
        msg = f"RESET again and compare: {r}"
        self.log(f"    {msg}")
        if valid:
            if object == "tags" and not TestHelper.compare_json(default[object], r[object]) or default[object] != r[object]:
                self.log("    FAIL")
                return test.FAIL("Second reset gives a different default value.")
            prev = r
        else:
            self.log("    FAIL")
            return test.FAIL(f"Can't {msg}")

        # restore initial for courtesy
        self.set_resource(url, node_url, initial, prev)

        self.log("    PASS")
        return test.PASS()

    def test_01_01(self, test):
        """ Annotation test: self/label (reset to default, set 64-byte value, set >64-byte, check IS04+version)"""
        return self.do_test(test, "self", "label")

    def test_01_02(self, test):
        """ Annotation test: self/description (reset to default, set 64-byte value, set >64-byte, check IS04+version)"""
        return self.do_test(test, "self", "description")

    def test_01_03(self, test):
        """ Annotation test: self/tags (reset to default, set 5 tags, set >5 tags, check IS04+version)"""
        return self.do_test(test, "self", "tags")

    def test_02_01(self, test):
        """ Annotation test: devices/../label (reset to default, set 64-byte value, set >64-byte, check IS04+version)"""
        return self.do_test(test, "devices", "label")

    def test_02_02(self, test):
        """Annotation test: devices/../description (reset to default, set 5 tags, set >5 tags, check IS04+version)"""
        return self.do_test(test, "devices", "description")

    def test_02_03(self, test):
        """Annotation test: devices/../tags (reset to default, set 5 tags, set >5 tags, check IS04+version)"""
        return self.do_test(test, "devices", "tags")

    def test_03_01(self, test):
        """ Annotation test: senders/../label (reset to default, set 64-byte value, set >64-byte, check IS04+version)"""
        return self.do_test(test, "senders", "label")

    def test_03_02(self, test):
        """Annotation test: senders/../description (reset to default, set 5 tags, set >5 tags, check IS04+version)"""
        return self.do_test(test, "senders", "description")

    def test_03_03(self, test):
        """Annotation test: sender/sevices/../tags (reset to default, set 5 tags, set >5 tags, check IS04+version)"""
        return self.do_test(test, "senders", "tags")

    def test_04_01(self, test):
        """ Annotation test: receivers/../label (reset to default, set 64-byte value, set >64-byte, check IS04+version)"""
        return self.do_test(test, "receivers", "label")

    def test_04_02(self, test):
        """Annotation test: receivers/../description (reset to default, set 5 tags, set >5 tags, check IS04+version)"""
        return self.do_test(test, "receivers", "description")

    def test_04_03(self, test):
        """Annotation test: receivers/sevices/../tags (reset to default, set 5 tags, set >5 tags, check IS04+version)"""
        return self.do_test(test, "receivers", "tags")
