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

# IS-13-02 exercises a Controller against a mock Node that advertises and serves the
# Annotation API. The cases follow IS-13 v1.0-dev: discovery from the Node services
# array, setting and resetting label, writing a urn:x-nmos:tag:user: tag, and seeing
# a label change through the Query API.

import inspect
import random
import textwrap
import time
import uuid
from copy import deepcopy

from .. import Config as CONFIG
from ..ControllerTest import ControllerTest, TestingFacadeException
from ..GenericTest import NMOSInitException, NMOSTestException
from ..NMOSUtils import NMOSUtils
from ..TestResult import Test

ANNOTATION_API_KEY = "annotation"

NEW_LABEL = "nmos-testing label"
RESET_LABEL = "nmos-testing reset me"
OBSERVE_LABEL = "nmos-testing live update"
USER_TAG_NAME = "urn:x-nmos:tag:user:favourite-colour"
USER_TAG_VALUE = ["teal"]
OBSERVE_ANSWER_SECONDS = 30
SENDERS = (
    {'label': 's1/weller', 'description': 'Mock sender 1'},
    {'label': 's2/foxton', 'description': 'Mock sender 2'},
    {'label': 's3/buckler', 'description': 'Mock sender 3'},
)


class IS1302Test(ControllerTest):
    """
    Controller tests for the IS-13 Annotation API
    """

    def __init__(self, apis, registries, node, dns_server, **kwargs):
        ControllerTest.__init__(self, apis, registries, node, dns_server, **kwargs)

    def set_up_tests(self):
        # One Sender is on the Node that advertises the Annotation API.
        # Each other Sender is on its own Node, which does not.
        annotated_index = self.generate_random_indices(
            len(SENDERS), min_index_count=1, max_index_count=1)[0]
        annotated = SENDERS[annotated_index]
        plain = [sender for index, sender in enumerate(SENDERS) if index != annotated_index]

        self.senders = [{
            'label': annotated['label'],
            'description': annotated['description'],
            'registered': True,
        }]
        self.receivers = []

        ControllerTest.set_up_tests(self)
        self.annotated_sender = self.senders[0]

        test = Test("Register the Annotation API", "set_up_tests")
        try:
            self._serve_annotation_api(test)
            self.plain_senders = self._register_plain_senders(test, plain)
        except NMOSTestException as exception:
            raise NMOSInitException(exception.args[0].detail)

    def _serve_annotation_api(self, test):
        """Advertise the Annotation API on the mock Node and serve that Node's resources."""
        resources = self.primary_registry.get_resources()
        node_data = deepcopy(resources.get("node", {}).get(self.node.id))
        if not node_data:
            raise NMOSTestException(test.FAIL("Mock Node is not in the Registry"))

        version = self._annotation_version()
        node_data["version"] = NMOSUtils.get_TAI_time()
        node_data["services"] = [{
            "href": self.mock_node_base_url + "x-nmos/annotation/" + version + "/",
            "type": "urn:x-nmos:service:annotation/" + version,
            "authorization": CONFIG.ENABLE_AUTH,
        }]
        self.post_resource(test, "node", node_data, codes=[200])

        resources = self.primary_registry.get_resources()
        device_ids = set()
        for device in resources.get("device", {}).values():
            if device.get("node_id") == self.node.id:
                device_ids.add(device["id"])
                self.node.add_annotation("device", device)
        for reg_type in ("source", "flow", "sender", "receiver"):
            for resource in resources.get(reg_type, {}).values():
                if resource.get("device_id") in device_ids:
                    self.node.add_annotation(reg_type, resource)
        self.node.add_annotation("node", resources["node"][self.node.id])

    def tear_down_tests(self):
        self.node.annotation_resources = {}
        self.node.clear_annotation_requests()
        ControllerTest.tear_down_tests(self)

    def _annotation_version(self):
        return self.apis.get(ANNOTATION_API_KEY, {}).get("version") or "v1.0"

    def _sender_patch_path(self, sender_id):
        return "/x-nmos/annotation/{}/node/senders/{}".format(self._annotation_version(), sender_id)

    def _register_plain_senders(self, test, senders):
        """Register one Node per Sender. Those Nodes do not advertise the Annotation API."""
        registered = []
        for sender in senders:
            time.sleep(0.1)
            node_id = str(uuid.uuid4())
            device_id = str(uuid.uuid4())
            source_id = str(uuid.uuid4())
            flow_id = str(uuid.uuid4())
            sender_id = str(uuid.uuid4())
            version = NMOSUtils.get_TAI_time()

            node_data = deepcopy(self.rtp_test_data["node"])
            node_data["id"] = node_id
            node_data["label"] = "AMWA Test Suite Node"
            node_data["description"] = "AMWA Test Suite Node"
            node_data["version"] = version
            node_data["services"] = []
            self.post_resource(test, "node", node_data, codes=[201])

            device_data = deepcopy(self.rtp_test_data["device"])
            device_data["id"] = device_id
            device_data["label"] = "AMWA Test Device"
            device_data["description"] = "AMWA Test Device"
            device_data["node_id"] = node_id
            device_data["controls"] = []
            device_data["senders"] = [sender_id]
            device_data["receivers"] = []
            device_data["version"] = version
            self.post_resource(test, "device", device_data, codes=[201])

            source_data = deepcopy(self.rtp_test_data["source"])
            source_data["id"] = source_id
            source_data["label"] = "AMWA Test Source"
            source_data["description"] = "AMWA Test Source"
            source_data["device_id"] = device_id
            source_data["version"] = version
            self.post_resource(test, "source", source_data, codes=[201])

            flow_data = deepcopy(self.rtp_test_data["flow"])
            flow_data["id"] = flow_id
            flow_data["label"] = "AMWA Test Flow"
            flow_data["description"] = "AMWA Test Flow"
            flow_data["device_id"] = device_id
            flow_data["source_id"] = source_id
            flow_data["version"] = version
            self.post_resource(test, "flow", flow_data, codes=[201])

            sender_data = deepcopy(self.rtp_test_data["sender"])
            sender_data["id"] = sender_id
            sender_data["label"] = sender['label']
            sender_data["description"] = sender['description']
            sender_data["device_id"] = device_id
            sender_data["flow_id"] = flow_id
            sender_data["version"] = version
            self.post_resource(test, "sender", sender_data, codes=[201])

            registered.append({
                "id": sender_id,
                "label": sender['label'],
                "description": sender['description'],
                "display_answer": self._format_device_metadata(
                    sender['label'], sender['description'], sender_id),
            })
        return registered

    def _registry_sender(self, test, sender_id):
        sender = self.primary_registry.get_resources().get("sender", {}).get(sender_id)
        if sender is None:
            raise NMOSTestException(test.FAIL("Sender {} is not in the mock Registry".format(sender_id)))
        return sender

    def _require_sender_patch(self, test, sender_id):
        patches = [request for request in self.node.annotation_requests if request["method"] == "PATCH"]
        if len(patches) < 1:
            raise NMOSTestException(test.FAIL("No PATCH request was received by the Annotation API"))
        if len(patches) > 1:
            raise NMOSTestException(test.FAIL("Multiple PATCH requests were received by the Annotation API"))

        patch = patches[0]
        if patch.get("schema_valid") is False:
            schema_error = patch.get("schema_error") or "unknown validation error"
            raise NMOSTestException(test.FAIL(
                "PATCH request body does not comply with the IS-13 schema: {}".format(schema_error)))
        if patch.get("status") != 200:
            raise NMOSTestException(test.FAIL(
                "Annotation API rejected the PATCH with HTTP {}".format(patch.get("status"))))
        if patch.get("path", "").endswith("/"):
            raise NMOSTestException(test.FAIL("PATCH URL has a trailing slash"))

        expected_path = self._sender_patch_path(sender_id)
        if patch.get("path") != expected_path:
            raise NMOSTestException(test.FAIL(
                "PATCH was sent to {} rather than {}".format(patch.get("path"), expected_path)))
        return patch

    def _require_unchanged(self, test, before, after, fields):
        for field in fields:
            if before.get(field) != after.get(field):
                raise NMOSTestException(test.FAIL(
                    "PATCH changed {}: was {!r}, now {!r}".format(field, before.get(field), after.get(field))))
        if after.get("version") == before.get("version"):
            raise NMOSTestException(test.FAIL("Sender version did not change after the PATCH"))

    def test_01(self, test):
        """
        Identify which Senders can be annotated
        """
        # The NCuT finds the Annotation API from the Node services entry
        # urn:x-nmos:service:annotation/{version}. One registered Sender belongs to a Node
        # that advertises it. Each other Sender belongs to its own Node, which does not.

        try:
            question = """\
                       The Annotation API is advertised on a Node's services array, with a type of \
                       urn:x-nmos:service:annotation/ followed by the API version.

                       Refresh the NCuT and select the Senders whose label you can edit.

                       Once you have made your selection press 'Submit'. If you cannot edit any of them, \
                       press 'Submit' without making a selection.
                       """
            candidates = sorted(
                [self.annotated_sender] + self.plain_senders,
                key=lambda sender: sender['label'])
            possible_answers = [{
                'answer_id': 'answer_' + str(index),
                'display_answer': sender['display_answer'],
                'resource': {
                    'id': sender['id'],
                    'label': sender['label'],
                    'description': sender['description'],
                },
            } for index, sender in enumerate(candidates)]
            expected_answers = [
                'answer_' + str(index) for index, sender in enumerate(candidates)
                if sender['id'] == self.annotated_sender['id']
            ]

            actual_answers = self.testing_facade_utils.invoke_testing_facade(
                question, possible_answers, test_type="multi_choice")['answer_response']

            if sorted(actual_answers) != sorted(expected_answers):
                return test.FAIL('Incorrect Sender identified')
            return test.PASS('Sender with an Annotation API correctly identified')
        except TestingFacadeException as exception:
            return test.UNCLEAR(exception.args[0])

    def test_02(self, test):
        """
        Set a Sender label via the Annotation API
        """
        sender = self.annotated_sender
        try:
            self.node.clear_annotation_requests()
            before = self._registry_sender(test, sender['id'])

            question = textwrap.dedent("""\
                The NCuT should be able to set a Sender's label through the Annotation API. \
                The description and tags stay as they are.

                Set the label of this Sender to exactly:

                {}

                {}

                Click the 'Next' button once the label has been saved.
                """).format(NEW_LABEL, sender['display_answer'])

            metadata = {'sender': {
                'id': sender['id'],
                'label': NEW_LABEL,
                'description': sender['description'],
            }}
            self.testing_facade_utils.invoke_testing_facade(
                question, [], test_type="action", metadata=metadata)

            patch = self._require_sender_patch(test, sender['id'])
            if patch['data'].get('label') != NEW_LABEL:
                return test.FAIL('PATCH label was {!r}'.format(patch['data'].get('label')))

            after = self._registry_sender(test, sender['id'])
            if after.get('label') != NEW_LABEL:
                return test.FAIL('Registry label was {!r}'.format(after.get('label')))
            self._require_unchanged(test, before, after, ('description', 'tags'))
            return test.PASS('Sender label updated')
        except TestingFacadeException as exception:
            return test.UNCLEAR(exception.args[0])
        finally:
            self.node.restore_annotation(sender['id'])

    def test_03(self, test):
        """
        Set a user-namespace tag via the Annotation API
        """
        sender = self.annotated_sender
        try:
            self.node.clear_annotation_requests()
            before = self._registry_sender(test, sender['id'])

            question = textwrap.dedent("""\
                The NCuT should be able to set a tag in the urn:x-nmos:tag:user: namespace. \
                The label and description stay as they are.

                On this Sender, set the tag

                {}

                to the single value {}

                {}

                Click the 'Next' button once the tag has been saved.
                """).format(USER_TAG_NAME, USER_TAG_VALUE[0], sender['display_answer'])

            metadata = {'sender': {
                'id': sender['id'],
                'label': sender['label'],
                'description': sender['description'],
            }}
            self.testing_facade_utils.invoke_testing_facade(
                question, [], test_type="action", metadata=metadata)

            patch = self._require_sender_patch(test, sender['id'])
            tags = patch['data'].get('tags')
            if not isinstance(tags, dict) or tags.get(USER_TAG_NAME) != USER_TAG_VALUE:
                return test.FAIL('PATCH did not set {} to {}'.format(USER_TAG_NAME, USER_TAG_VALUE))

            after = self._registry_sender(test, sender['id'])
            expected_tags = dict(before.get('tags') or {})
            expected_tags[USER_TAG_NAME] = USER_TAG_VALUE
            if after.get('tags') != expected_tags:
                return test.FAIL('Registry tags were {!r}'.format(after.get('tags')))
            self._require_unchanged(test, before, after, ('label', 'description'))
            return test.PASS('User tag updated')
        except TestingFacadeException as exception:
            return test.UNCLEAR(exception.args[0])
        finally:
            self.node.restore_annotation(sender['id'])

    def test_04(self, test):
        """
        Reset a Sender label via the Annotation API
        """
        sender = self.annotated_sender
        try:
            self.node.patch_annotation(sender['id'], {'label': RESET_LABEL})
            self.node.clear_annotation_requests()
            before = self._registry_sender(test, sender['id'])

            question = textwrap.dedent("""\
                The NCuT should be able to reset a Sender's label. The PATCH sends null for the label, \
                and the Node restores the label it had at registration.

                Refresh the NCuT. This Sender's label is currently "{}".

                {}

                Reset that label.

                Click the 'Next' button once the label has been reset.
                """).format(
                    RESET_LABEL,
                    self._format_device_metadata(RESET_LABEL, sender['description'], sender['id']))

            metadata = {'sender': {
                'id': sender['id'],
                'label': sender['label'],
                'description': sender['description'],
            }}
            self.testing_facade_utils.invoke_testing_facade(
                question, [], test_type="action", metadata=metadata)

            patch = self._require_sender_patch(test, sender['id'])
            if 'label' not in patch['data'] or patch['data'].get('label') is not None:
                return test.FAIL('Reset must PATCH label set to null')

            after = self._registry_sender(test, sender['id'])
            if after.get('label') != sender['label']:
                return test.FAIL('Registry label was {!r} after reset'.format(after.get('label')))
            self._require_unchanged(test, before, after, ('description', 'tags'))
            return test.PASS('Sender label reset')
        except TestingFacadeException as exception:
            return test.UNCLEAR(exception.args[0])
        finally:
            self.node.restore_annotation(sender['id'])

    def test_05(self, test):
        """
        Controller shows a label change made through the Annotation API
        """
        # A successful PATCH increments version and is registered, so a Controller subscribed to the
        # Query API can see the new label.

        sender = self.annotated_sender
        try:
            question = textwrap.dedent("""\
                The NCuT should update its view when a Sender's label changes in the Registry.

                Find this Sender and watch its label.

                {}

                Click the 'Next' button once you are watching it.
                """).format(sender['display_answer'])
            metadata = {'sender': {
                'id': sender['id'],
                'label': sender['label'],
                'description': sender['description'],
            }}
            self.testing_facade_utils.invoke_testing_facade(
                question, [], test_type="action", metadata=metadata)

            question = textwrap.dedent("""\
                This Sender's label will change to "{}" at a random moment within the next 15 seconds.

                As soon as the NCuT shows that label, click the 'Next' button.

                The button must be clicked within {} seconds of the label changing.
                """).format(OBSERVE_LABEL, OBSERVE_ANSWER_SECONDS)

            test_method_name = inspect.currentframe().f_code.co_name
            method = getattr(self, test_method_name)
            metadata = {'sender': {
                'id': sender['id'],
                'label': OBSERVE_LABEL,
                'description': sender['description'],
            }}
            sent_json = self.testing_facade_utils.send_testing_facade_questions(
                test_method_name, inspect.getdoc(method), question, [],
                test_type="action", multipart_test=1, metadata=metadata)

            self.testing_facade_utils.exit_test_event_clear()
            self.testing_facade_utils.exit_test_event_wait(random.randint(5, 15))
            self.node.patch_annotation(sender['id'], {'label': OBSERVE_LABEL})
            expected_time = time.time()

            response = self.testing_facade_utils.wait_for_testing_facade(sent_json['question_id'], 'action')
            if response['time_received'] < expected_time:
                return test.FAIL('Label had not yet changed')
            if response['time_received'] > expected_time + OBSERVE_ANSWER_SECONDS:
                seconds = int(response['time_received'] - expected_time)
                return test.FAIL('Label changed {} seconds before the button was clicked'.format(seconds))
            after = self._registry_sender(test, sender['id'])
            if after.get('label') != OBSERVE_LABEL:
                return test.FAIL('Registry label was {!r}'.format(after.get('label')))
            return test.PASS('Label change shown by the NCuT')
        except TestingFacadeException as exception:
            return test.UNCLEAR(exception.args[0])
        finally:
            self.node.restore_annotation(sender['id'])
