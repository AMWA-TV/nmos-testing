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

from ..import TestHelper
import re
import copy
import time

IS13_SPEC_VERSION = "v1.0-dev"
IS13_SPEC_URL = f"https://specs.amwa.tv/is-13/branches/{IS13_SPEC_VERSION}/docs"

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
                return r.json()
            except Exception as e:
                raise(f"Can't parse response as json {e.msg}")
        else:
            return None

    def compare_resource(self, annotation_property, value1, value2):
        """ Compare strings (or dict for 'tags') """

        if value2[annotation_property] is None:  # this is a reset, value2 is null, skip
            return True

        if annotation_property == "tags":  # tags needs to be stripped
            value2[annotation_property] = strip_tags(value2[annotation_property])
            return TestHelper.compare_json(value2[annotation_property], value1[annotation_property])

        return value2[annotation_property] == value1[annotation_property]

    def set_resource(self, test, url, node_url, value, prev, expected, msg, link):
        """ Patch a resource with one ore several object values """

        self.log(f"    {msg}")

        annotation_property = list(value.keys())[0]
        valid, resp = self.do_request("PATCH", url, json=value)
        if not valid:
            raise NMOSTestException(test.FAIL("PATCH Request FAIL", link=f"{IS13_SPEC_URL}/Behaviour.html#setting-values"))
        # TODO: if put_response.status_code == 500:

        # pause to accomodate update propagation
        time.sleep(0.1)

        # re-GET
        resp = self.get_resource(url)
        if not resp:
            raise NMOSTestException(test.FAIL(f"GET /{ANNOTATION_API_KEY} FAIL"))
        # check PATCH == GET
        if not self.compare_resource(annotation_property, resp, expected):
            raise NMOSTestException(test.FAIL(f"Compare req vs expect FAIL - {msg}", link=link))
        # check that the version (timestamp) has increased
        if get_ts_from_version(prev['version']) >= get_ts_from_version(resp['version']):
            raise NMOSTestException(test.FAIL(f"Version update FAIL \
                                              ({get_ts_from_version(prev['version'])} !>= {get_ts_from_version(resp['version'])})", \
                                              link=f"{IS13_SPEC_URL}/Behaviour.html#successful-response>"))

        # validate that it is reflected in IS04
        node_resp = self.get_resource(node_url)
        if not node_resp:
            raise NMOSTestException(test.FAIL(f"GET /{NODE_API_KEY} FAIL"))
        # check PATCH == GET
        if not self.compare_resource(annotation_property, resp, expected):
            raise NMOSTestException(test.FAIL(f"Compare /annotation vs /node FAIL {msg}",
                                              link=f"{IS13_SPEC_URL}/Interoperability_-_IS-04.html#consistent-resources"))
        # check that the version (timestamp) has increased
        if get_ts_from_version(node_resp['version']) != get_ts_from_version(resp['version']):
            raise NMOSTestException(test.FAIL(f"Compare /annotation Version vs /node FAIL {msg}",
                                              link=f"{IS13_SPEC_URL}/Interoperability_-_IS-04.html#version-increments"))

        return resp

    def log(self, msg):
        """
        Enable for quick debug only
        """
        # print(msg)
        return

    def create_url(self, test, base_url, resource):
        """
        Build the url for both annotation and node APIs which behaves differently.
        For iterables resources (devices, senders, receivers), return the 1st element.
        """

        url = f"{base_url}{resource}"
        r = self.get_resource(url)
        if r:
            if resource != "self":
                if isinstance(r[0], str):  # in annotation api
                    index = r[0]
                elif isinstance(r[0], dict):  # in node api
                    index = r[0]['id']
                else:
                    raise NMOSTestException(test.FAIL(f"Unexpected resource found @ {url}"))
                url = f"{url}/{index}"
        else:
            raise NMOSTestException(test.FAIL(f"No resource found @ {url}"))

        return url

    def copy_resource(self, resource):
        """ Strip and copy resource """

        r = copy.copy(resource)
        r.pop('id')
        r.pop('version')
        r['tags'] = strip_tags(r['tags'])

        return r

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

        url = self.create_url(test, f"{self.annotation_url}node/", resource)
        node_url = self.create_url(test, self.node_url, resource)

        # Save initial resource value
        resp = self.get_resource(url)
        initial = self.copy_resource(resp)

        msg = "Reset to default and save."
        link = f"{IS13_SPEC_URL}/Behaviour.html#resetting-values"
        default = resp = self.set_resource(test, url, node_url, {annotation_property: None}, resp,
                                           {annotation_property: None}, msg, link)

        msg = "Set max-length value and return complete response."
        link = f"{IS13_SPEC_URL}/Behaviour.html#setting-values"
        value = TAGS_LENGTH_MAX_VALUE if annotation_property == "tags" else STRING_LENGTH_MAX_VALUE
        resp = self.set_resource(test, url, node_url, {annotation_property: value}, resp,
                                 {annotation_property: value}, msg, link)

        msg = "Exceed max-length value and return truncated response"
        link = f"{IS13_SPEC_URL}/Behaviour.html#additional-limitations"
        value = TAGS_LENGTH_OVER_MAX_VALUE if annotation_property == "tags" else STRING_LENGTH_OVER_MAX_VALUE
        expected = TAGS_LENGTH_MAX_VALUE if annotation_property == "tags" else STRING_LENGTH_MAX_VALUE
        resp = self.set_resource(test, url, node_url, {annotation_property: value}, resp,
                                 {annotation_property: expected}, msg, link)

        msg = "Reset again and compare with default."
        link = f"{IS13_SPEC_URL}/Behaviour.html#resetting-values"
        resp = self.set_resource(test, url, node_url, {annotation_property: None}, resp, default,
                                 msg, link)

        msg = "Restore initial values."
        link = "{IS13_SPEC_URL}/Behaviour.html#setting-values"
        self.set_resource(test, url, node_url, initial, resp, msg, link)

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
