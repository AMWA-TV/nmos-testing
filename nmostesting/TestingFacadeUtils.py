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

import asyncio
import time
import json
import inspect
from threading import Event

from . import Config as CONFIG
from .TestHelper import do_request, get_default_ip

from flask import Flask, Blueprint, request

TESTING_FACADE_API_KEY = "testquestion"
QUERY_API_KEY = "query"
CONN_API_KEY = "connection"
REG_API_KEY = "registration"

CALLBACK_ENDPOINT = "/x-nmos/testanswer/<version>"

# asyncio queue for passing Testing Facade answer responses back to tests
_event_loop = asyncio.new_event_loop()
asyncio.set_event_loop(_event_loop)
_answer_response_queue = asyncio.Queue()

# use exit Event to quit tests early that involve waiting for senders/connections
exitTestEvent = Event()

app = Flask(__name__)
TEST_API = Blueprint('test_api', __name__)


class TestingFacadeException(Exception):
    """Exception thrown due to comms or data errors between NMOS Testing and Testing Facade"""
    pass


@TEST_API.route(CALLBACK_ENDPOINT, methods=['POST'])
def receive_answer(version):

    if request.method == 'POST':
        if 'question_id' not in request.json:
            return 'Invalid JSON received', 400

        answer_json = request.json
        answer_json['time_received'] = time.time()
        _event_loop.call_soon_threadsafe(_answer_response_queue.put_nowait, answer_json)

        # Interrupt any 'sleeps' that are still active
        exitTestEvent.set()

    return '', 202


class TestingFacadeUtils(object):
    """
    Testing initial set up of new test suite for controller testing
    """
    def __init__(self, apis):
        self.apis = apis
        if CONFIG.ENABLE_HTTPS and TESTING_FACADE_API_KEY in apis:
            # Comms with Testing Facade are http only
            if apis[TESTING_FACADE_API_KEY]["base_url"] is not None:
                apis[TESTING_FACADE_API_KEY]["base_url"] \
                    = apis[TESTING_FACADE_API_KEY]["base_url"].replace("https", "http")
            if apis[TESTING_FACADE_API_KEY]["url"] is not None:
                apis[TESTING_FACADE_API_KEY]["url"] \
                    = apis[TESTING_FACADE_API_KEY]["url"].replace("https", "http")
        qa_api_version = self.apis[TESTING_FACADE_API_KEY]["version"] \
            if TESTING_FACADE_API_KEY in apis and "version" in self.apis[TESTING_FACADE_API_KEY] else "v1.0"
        self.answer_uri = "http://" + get_default_ip() + ":" + str(CONFIG.PORT_BASE) + \
            CALLBACK_ENDPOINT.replace('<version>', qa_api_version)

    def reset(self):
        # Reset the state of the Testing Facade
        if TESTING_FACADE_API_KEY in self.apis:
            do_request("POST", self.apis[TESTING_FACADE_API_KEY]["url"], json={"clear": "True"})

    async def get_answer_response(self, timeout):
        # Add API processing time to specified timeout
        # Otherwise, if timeout is None then disable timeout mechanism
        timeout = timeout + (2 * CONFIG.API_PROCESSING_TIMEOUT) if timeout is not None else None

        return await asyncio.wait_for(_answer_response_queue.get(), timeout=timeout)

    def send_testing_facade_questions(
            self,
            test_method_name,
            test_method_description,
            question,
            answers,
            test_type,
            multipart_test=None,
            metadata=None):
        """
        Send question and answers to Testing Facade
        question:   text to be presented to Test User
        answers:    list of all possible answers
        test_type:  "single_choice" - one and only one answer
                    "multi_choice" - multiple answers
                    "action" - Test User asked to click button
        multipart_test: indicates test uses multiple questions. Default None, should be increasing
                    integers with each subsequent call within the same test
        metadata: Test details to assist fully automated testing
        """

        timeout = CONFIG.CONTROLLER_TESTING_TIMEOUT

        question_id = test_method_name if not multipart_test else test_method_name + '_' + str(multipart_test)

        json_out = {
            "test_type": test_type,
            "question_id": question_id,
            "name": test_method_name,
            "description": test_method_description,
            "question": question,
            "answers": answers,
            "timeout": timeout,
            "answer_uri": self.answer_uri,
            "metadata": metadata
        }
        # Send questions to Testing Facade API endpoint then wait
        if TESTING_FACADE_API_KEY in self.apis:
            valid, response = do_request("POST", self.apis[TESTING_FACADE_API_KEY]["url"], json=json_out)

            if not valid or response.status_code != 202:
                raise TestingFacadeException("Problem contacting Testing Facade: "
                                             + response.text if valid else response)

            return json_out

        raise TestingFacadeException("Testing facade API not specified")

    def wait_for_testing_facade(self, question_id, test_type):

        # Wait for answer response or question timeout in seconds. A timeout of None will wait indefinitely
        timeout = CONFIG.CONTROLLER_TESTING_TIMEOUT

        try:
            answer_response = _event_loop.run_until_complete(self.get_answer_response(timeout))
        except asyncio.TimeoutError:
            raise TestingFacadeException("Test timed out")

        # Basic integrity check for response json
        if answer_response['question_id'] is None:
            raise TestingFacadeException("Integrity check failed: result format error: "
                                         + json.dump(answer_response))

        if answer_response['question_id'] != question_id:
            raise TestingFacadeException(
                "Integrity check failed: cannot compare result of " + question_id +
                " with expected result for " + answer_response['question_id'])

        # Multi_choice question submitted without any answers should be an empty list
        if test_type == 'multi_choice' and answer_response['answer_response'] is None:
            answer_response['answer_response'] = []

        return answer_response

    def invoke_testing_facade(self, question, answers, test_type,
                              multipart_test=None, metadata=None,
                              test_method_name=None):
        # Get the name of the calling test method to use as an identifier
        test_method_name = test_method_name if test_method_name\
            else inspect.currentframe().f_back.f_code.co_name

        method = getattr(inspect.currentframe().f_back.f_locals["self"], test_method_name)
        test_method_description = inspect.getdoc(method)

        json_out = self.send_testing_facade_questions(
            test_method_name, test_method_description, question, answers, test_type, multipart_test, metadata)

        return self.wait_for_testing_facade(json_out['question_id'], test_type)

    def exit_test_event_clear(self):
        exitTestEvent.clear()

    def exit_test_event_wait(self, time_delay):
        exitTestEvent.wait(time_delay)
