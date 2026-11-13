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
# array, setting and resetting a Sender label, writing a urn:x-nmos:tag:user: tag,
# setting a Receiver description and resetting one of its tags, and seeing a label
# change through the Query API.

import inspect
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
NEW_DESCRIPTION = "nmos-testing description"
RECEIVER_TAG_VALUE = ["olive"]
OVERRIDE_TAG_VALUE = ["chocolate"]
OTHER_TAG_NAME = "urn:x-nmos:tag:user:favourite-number"
NO_VALUE_ANSWER = "(no value)"
OBSERVE_ANSWER_SECONDS = 30
SENDERS = (
    {'label': 's1/weller', 'description': 'Mock sender 1'},
    {'label': 's2/foxton', 'description': 'Mock sender 2'},
    {'label': 's3/buckler', 'description': 'Mock sender 3'},
)
RECEIVER = {'label': 'r1/brookes', 'description': 'Mock receiver 1'}


class IS1302Test(ControllerTest):
    """
    Controller tests for the IS-13 Annotation API
    """

    def __init__(self, apis, registries, node, dns_server, **kwargs):
        ControllerTest.__init__(self, apis, registries, node, dns_server, **kwargs)

    def set_up_tests(self):
        # One Sender and the Receiver are on the Node that advertises the Annotation API.
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
        self.receivers = [{
            'label': RECEIVER['label'],
            'description': RECEIVER['description'],
            'connectable': True,
            'registered': True,
        }]
        self.other_tag_value = [str(NMOSUtils.RANDOM.randint(1, 99))]

        ControllerTest.set_up_tests(self)
        self.annotated_sender = self.senders[0]
        self.annotated_receiver = self.receivers[0]

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
        # Controllers MUST support hrefs both with and without a trailing slash,
        # so make a seeded choice between the two
        trailing_slash = NMOSUtils.RANDOM.random() < 0.5
        node_data["version"] = NMOSUtils.get_TAI_time()
        node_data["services"] = [{
            "href": self.mock_node_base_url + "x-nmos/annotation/" + version + ("/" if trailing_slash else ""),
            "type": "urn:x-nmos:service:annotation/" + version,
            "authorization": CONFIG.ENABLE_AUTH,
        }]
        self.post_resource(test, "node", node_data, codes=[200])

        receiver_data = deepcopy(resources["receiver"][self.annotated_receiver["id"]])
        receiver_data["tags"] = {USER_TAG_NAME: RECEIVER_TAG_VALUE, OTHER_TAG_NAME: self.other_tag_value}
        receiver_data["version"] = NMOSUtils.get_TAI_time()
        self.post_resource(test, "receiver", receiver_data, codes=[200])

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

    def _patch_path(self, reg_type, resource_id):
        return "/x-nmos/annotation/{}/node/{}s/{}".format(self._annotation_version(), reg_type, resource_id)

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

    def _registry_resource(self, test, reg_type, resource_id):
        resource = self.primary_registry.get_resources().get(reg_type, {}).get(resource_id)
        if resource is None:
            raise NMOSTestException(test.FAIL("{} {} is not in the mock Registry".format(
                reg_type.capitalize(), resource_id)))
        return resource

    def _require_patch(self, test, reg_type, resource_id):
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

        expected_path = self._patch_path(reg_type, resource_id)
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
            raise NMOSTestException(test.FAIL("Resource version did not change after the PATCH"))

    def _require_displayed_value(self, test, question, values, expected, metadata):
        """Ask which of the values the NCuT shows, and fail unless it is the expected one."""
        values = list(values)
        NMOSUtils.RANDOM.shuffle(values)
        possible_answers = [{'answer_id': 'answer_' + str(index), 'display_answer': value}
                            for index, value in enumerate(values)]
        actual_answer = self.testing_facade_utils.invoke_testing_facade(
            question, possible_answers, test_type="single_choice", multipart_test=1, metadata=metadata,
            test_method_name=inspect.currentframe().f_back.f_code.co_name)['answer_response']
        if actual_answer != 'answer_' + str(values.index(expected)):
            raise NMOSTestException(test.FAIL('NCuT does not show the value held by the Node'))

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
            before = self._registry_resource(test, 'sender', sender['id'])

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

            patch = self._require_patch(test, 'sender', sender['id'])
            if patch['data'].get('label') != NEW_LABEL:
                return test.FAIL('PATCH label was {!r}'.format(patch['data'].get('label')))

            after = self._registry_resource(test, 'sender', sender['id'])
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
            before = self._registry_resource(test, 'sender', sender['id'])

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

            patch = self._require_patch(test, 'sender', sender['id'])
            tags = patch['data'].get('tags')
            if not isinstance(tags, dict) or tags.get(USER_TAG_NAME) != USER_TAG_VALUE:
                return test.FAIL('PATCH did not set {} to {}'.format(USER_TAG_NAME, USER_TAG_VALUE))

            after = self._registry_resource(test, 'sender', sender['id'])
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
            before = self._registry_resource(test, 'sender', sender['id'])

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

            patch = self._require_patch(test, 'sender', sender['id'])
            if 'label' not in patch['data'] or patch['data'].get('label') is not None:
                return test.FAIL('Reset must PATCH label set to null')

            after = self._registry_resource(test, 'sender', sender['id'])
            if after.get('label') != sender['label']:
                return test.FAIL('Registry label was {!r} after reset'.format(after.get('label')))
            self._require_unchanged(test, before, after, ('description', 'tags'))

            question = textwrap.dedent("""\
                The NCuT should show the label held by the Node, which can differ from the value \
                that was requested.

                What label does the NCuT now show for this Sender?
                """)
            self._require_displayed_value(
                test, question, [sender['label'], RESET_LABEL, NO_VALUE_ANSWER], sender['label'], metadata)
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
            self.testing_facade_utils.exit_test_event_wait(NMOSUtils.RANDOM.randint(5, 15))
            self.node.patch_annotation(sender['id'], {'label': OBSERVE_LABEL})
            expected_time = time.time()

            response = self.testing_facade_utils.wait_for_testing_facade(sent_json['question_id'], 'action')
            if response['time_received'] < expected_time:
                return test.FAIL('Label had not yet changed')
            if response['time_received'] > expected_time + OBSERVE_ANSWER_SECONDS:
                seconds = int(response['time_received'] - expected_time)
                return test.FAIL('Label changed {} seconds before the button was clicked'.format(seconds))
            after = self._registry_resource(test, 'sender', sender['id'])
            if after.get('label') != OBSERVE_LABEL:
                return test.FAIL('Registry label was {!r}'.format(after.get('label')))
            return test.PASS('Label change shown by the NCuT')
        except TestingFacadeException as exception:
            return test.UNCLEAR(exception.args[0])
        finally:
            self.node.restore_annotation(sender['id'])

    def test_06(self, test):
        """
        Set a Receiver description via the Annotation API
        """
        receiver = self.annotated_receiver
        try:
            self.node.clear_annotation_requests()
            before = self._registry_resource(test, 'receiver', receiver['id'])

            question = textwrap.dedent("""\
                The NCuT should be able to set a Receiver's description through the Annotation API. \
                The label and tags stay as they are.

                Set the description of this Receiver to exactly:

                {}

                {}

                Click the 'Next' button once the description has been saved.
                """).format(NEW_DESCRIPTION, receiver['display_answer'])

            metadata = {'receiver': {
                'id': receiver['id'],
                'label': receiver['label'],
                'description': NEW_DESCRIPTION,
            }}
            self.testing_facade_utils.invoke_testing_facade(
                question, [], test_type="action", metadata=metadata)

            patch = self._require_patch(test, 'receiver', receiver['id'])
            if patch['data'].get('description') != NEW_DESCRIPTION:
                return test.FAIL('PATCH description was {!r}'.format(patch['data'].get('description')))

            after = self._registry_resource(test, 'receiver', receiver['id'])
            if after.get('description') != NEW_DESCRIPTION:
                return test.FAIL('Registry description was {!r}'.format(after.get('description')))
            self._require_unchanged(test, before, after, ('label', 'tags'))
            return test.PASS('Receiver description updated')
        except TestingFacadeException as exception:
            return test.UNCLEAR(exception.args[0])
        finally:
            self.node.restore_annotation(receiver['id'])

    def test_07(self, test):
        """
        Reset a Receiver tag via the Annotation API
        """
        receiver = self.annotated_receiver
        try:
            self.node.patch_annotation(receiver['id'], {'tags': {USER_TAG_NAME: OVERRIDE_TAG_VALUE}})
            self.node.clear_annotation_requests()
            before = self._registry_resource(test, 'receiver', receiver['id'])

            question = textwrap.dedent("""\
                The NCuT should be able to reset one of a Receiver's tags. The PATCH sends null for that tag, \
                and the Node restores the value it had at registration. The other tags stay as they are.

                Refresh the NCuT. This Receiver's {} tag is currently {}.

                {}

                Reset that tag.

                Click the 'Next' button once the tag has been reset.
                """).format(USER_TAG_NAME, OVERRIDE_TAG_VALUE[0], receiver['display_answer'])

            metadata = {'receiver': {
                'id': receiver['id'],
                'label': receiver['label'],
                'description': receiver['description'],
            }}
            self.testing_facade_utils.invoke_testing_facade(
                question, [], test_type="action", metadata=metadata)

            patch = self._require_patch(test, 'receiver', receiver['id'])
            tags = patch['data'].get('tags')
            if 'tags' in patch['data'] and tags is None:
                return test.FAIL('PATCH reset all tags rather than only {}'.format(USER_TAG_NAME))
            if not isinstance(tags, dict) or USER_TAG_NAME not in tags or tags[USER_TAG_NAME] is not None:
                return test.FAIL('Reset must PATCH {} set to null'.format(USER_TAG_NAME))

            after = self._registry_resource(test, 'receiver', receiver['id'])
            expected_tags = dict(before.get('tags') or {})
            expected_tags[USER_TAG_NAME] = RECEIVER_TAG_VALUE
            if after.get('tags') != expected_tags:
                return test.FAIL('Registry tags were {!r} after reset'.format(after.get('tags')))
            self._require_unchanged(test, before, after, ('label', 'description'))

            question = textwrap.dedent("""\
                The NCuT should show the tag value held by the Node, which can differ from the value \
                that was requested.

                What value does the NCuT now show for this Receiver's {} tag?
                """).format(USER_TAG_NAME)
            self._require_displayed_value(
                test, question, [RECEIVER_TAG_VALUE[0], OVERRIDE_TAG_VALUE[0], NO_VALUE_ANSWER],
                RECEIVER_TAG_VALUE[0], metadata)
            return test.PASS('Receiver tag reset')
        except TestingFacadeException as exception:
            return test.UNCLEAR(exception.args[0])
        finally:
            self.node.restore_annotation(receiver['id'])
