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
The script implements the IS-13 test suite according to the AMWA IS-13 NMOS Annotation
Specification (https://specs.amwa.tv/is-13/). At the end of the test, the initial state
of the tested unit is supposed to be restored but this cannot be garanteed.

Terminology:
* `resource` refers to self, devices, senders or receivers endpoints
* `annotation_property` refers to annotable objects: label, description or tags
"""

from ..GenericTest import GenericTest, NMOSTestException
from ..TestHelper import compare_json

from ..import TestHelper
import re
import copy
import time

ANNOTATION_API_KEY = "annotation"
NODE_API_KEY = "node"

# Constants for label and description related tests
STRING_LENGTH_OVER_MAX_VALUE = ''.join(['X' for i in range(100)])
STRING_LENGTH_MAX_VALUE = STRING_LENGTH_OVER_MAX_VALUE[:64]  # this is the max length tolerated

# Constants for tags related tests
TAGS_LENGTH_OVER_MAX_VALUE = {'location': ['underground'], 'studio': ['42'], 'tech': ['John', 'Mike']}
TAGS_LENGTH_MAX_VALUE = TAGS_LENGTH_OVER_MAX_VALUE.copy()
TAGS_LENGTH_MAX_VALUE.pop('tech')  # must have a max of 5
TAGS_TO_BE_STRIPPED = 'urn:x-nmos:tag:grouphint/v1.0'


def get_ts_from_version(version):
    """ Convert the 'version' object (string) into float """
    return float(re.sub(':', '.', version))


def strip_tags(tags):
    if TAGS_TO_BE_STRIPPED in list(tags.keys()):
        tags.pop(TAGS_TO_BE_STRIPPED)
    return tags


class IS1301Test(GenericTest):
    """
    Runs IS-13-Test
    """

    def __init__(self, apis, **kwargs):
        GenericTest.__init__(self, apis, **kwargs)
        self.annotation_url = self.apis[ANNOTATION_API_KEY]["url"]
        self.node_url = f"{self.apis[ANNOTATION_API_KEY]['base_url']}/x-nmos/node/{self.apis[NODE_API_KEY]['version']}/"

    def get_resource(self, url):
        """ Get a resource """

        valid, r = self.do_request("GET", url)
        if valid and r.status_code == 200:
            try:
                return True, r.json()
            except Exception as e:
                return False, e.msg
        else:
            return False, "GET Request FAIL"

    def compare_resource(self, annotation_property, value1, value2):
        """ Compare strings (or dict for 'tags') """

        if value1[annotation_property] is None:  # this is a reset, value1 is null, skip
            return True, ""

        if annotation_property == "tags":  # tags needs to be stripped
            value2[annotation_property] = strip_tags(value2[annotation_property])
            if not TestHelper.compare_json(value2[annotation_property], value1[annotation_property]):
                return False, f"{annotation_property} value FAIL"

        elif value2[annotation_property] != value1[annotation_property]:
            return False, f"{annotation_property} value FAIL"

        return True, ""

    def set_resource(self, url, node_url, new, prev, msg):
        """ Patch a resource with one ore several object values """
        global prev

        self.log(f"    {msg}")

        annotation_property = list(new.keys())[0]
        valid, resp = self.do_request("PATCH", url, json=new)
        if not valid:
            # raise NMOSTestException(test.WARNING("501 'Not Implemented' status code is not supported below API " "version v1.3", NMOS_WIKI_URL + "/IS-04#nodes-basic-connection-management"))
            return False, "PATCH Request FAIL"

        # pause to accomodate update propagation
        time.sleep(0.1)

        # re-GET
        valid, resp = self.get_resource(url)
        if not valid:
            return False, "Get Request FAIL"
        # check PATCH == GET
        valid, msg = self.compare_resource(annotation_property, new, resp)
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
        valid, msg = self.compare_resource(annotation_property, new, resp)
        if not valid:
            return False, f"new IS-04/node/.../ {msg}"
        # check that the version (timestamp) has increased
        if get_ts_from_version(node_resp['version']) != get_ts_from_version(resp['version']):
            return False, "new IS-04/node/.../version (timestamp) FAIL"

        return True, resp

    def log(self, msg):
        """
        Enable for quick debug only
        """
        # print(msg)
        return

    def create_url(self, base_url, resource):
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


    def do_test_sequence(self, test, resource, annotation_property):
        """
        In addition to the basic annotation API tests, this suite includes the test sequence:
        For each resource:
            For each annotation_property:
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

        url = self.create_url(f"{self.annotation_url}node/", resource)
        if not url:
            msg = f"Can't get annotation url for {resource}"
            self.log(f"    FAIL {msg}")
            return test.FAIL(msg)

        node_url = self.create_url(self.node_url, resource)
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

        msg = f"RESET to default and save: {r}"
        valid, r = self.set_resource(url, node_url, {annotation_property: None}, prev, msg)
        self.log(f"    {msg}")
        if valid:
            default = prev = r
        else:
            self.log("    FAIL")
            return test.FAIL(f"Can't {msg}")

        msg = f"SET MAX value and expected complete response: {r}"
        value = TAGS_LENGTH_MAX_VALUE if annotation_property == "tags" else STRING_LENGTH_MAX_VALUE
        valid, r = self.set_resource(url, node_url, {annotation_property: value}, prev, msg)

        msg = f"SET >MAX value and expect truncated response: {r}"
        value = TAGS_LENGTH_OVER_MAX_VALUE if annotation_property == "tags" else STRING_LENGTH_OVER_MAX_VALUE
        valid, r = self.set_resource(url, node_url, {annotation_property: value}, prev, msg)
        if valid:
            if annotation_property == "tags" and not TestHelper.compare_json(r[annotation_property], TAGS_LENGTH_MAX_VALUE) or r[annotation_property] != STRING_LENGTH_MAX_VALUE:
                return test.FAIL(f"Can't {msg}")

        msg = f"RESET again and compare: {r}"
        valid, r = self.set_resource(url, node_url, {annotation_property: None}, prev, msg)
        if valid:
            if annotation_property == "tags" and not TestHelper.compare_json(default[annotation_property], r[annotation_property]) or default[annotation_property] != r[annotation_property]:
                self.log("    FAIL")
                return test.FAIL("Second reset gives a different default value.")

        msg = f"RESTORE initial values"
        self.set_resource(url, node_url, initial, prev, msg)

        self.log("    PASS")
        return test.PASS()

    def test_01_01(self, test):
        """ Annotation test: self/label (reset to default, set 64-byte value, set >64-byte, check IS04+version)"""
        return self.do_test_sequence(test, "self", "label")

    def test_01_02(self, test):
        """ Annotation test: self/description (reset to default, set 64-byte value, set >64-byte, check IS04+version)"""
        return self.do_test_sequence(test, "self", "description")

    def test_01_03(self, test):
        """ Annotation test: self/tags (reset to default, set 5 tags, set >5 tags, check IS04+version)"""
        return self.do_test_sequence(test, "self", "tags")

    def test_02_01(self, test):
        """ Annotation test: devices/../label (reset to default, set 64-byte value, set >64-byte, check IS04+version)"""
        return self.do_test_sequence(test, "devices", "label")

    def test_02_02(self, test):
        """Annotation test: devices/../description (reset to default, set 5 tags, set >5 tags, check IS04+version)"""
        return self.do_test_sequence(test, "devices", "description")

    def test_02_03(self, test):
        """Annotation test: devices/../tags (reset to default, set 5 tags, set >5 tags, check IS04+version)"""
        return self.do_test_sequence(test, "devices", "tags")

    def test_03_01(self, test):
        """ Annotation test: senders/../label (reset to default, set 64-byte value, set >64-byte, check IS04+version)"""
        return self.do_test_sequence(test, "senders", "label")

    def test_03_02(self, test):
        """Annotation test: senders/../description (reset to default, set 5 tags, set >5 tags, check IS04+version)"""
        return self.do_test_sequence(test, "senders", "description")

    def test_03_03(self, test):
        """Annotation test: sender/sevices/../tags (reset to default, set 5 tags, set >5 tags, check IS04+version)"""
        return self.do_test_sequence(test, "senders", "tags")

    def test_04_01(self, test):
        """ Annotation test: receivers/../label (reset to default, set 64-byte value, set >64-byte, check IS04+version)"""
        return self.do_test_sequence(test, "receivers", "label")

    def test_04_02(self, test):
        """Annotation test: receivers/../description (reset to default, set 5 tags, set >5 tags, check IS04+version)"""
        return self.do_test_sequence(test, "receivers", "description")

    def test_04_03(self, test):
        """Annotation test: receivers/sevices/../tags (reset to default, set 5 tags, set >5 tags, check IS04+version)"""
        return self.do_test_sequence(test, "receivers", "tags")
