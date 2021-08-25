# Copyright (C) 2021 Advanced Media Workflow Association
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

import time
import json

class DataStore:
    """
    Store json with test question details for use with NMOS Controller test suite and Testing Facade
    """

    def __init__(self):
        self.test_type = None
        self.question_id = None
        self.name = None
        self.description = None
        self.question = None
        self.answers = None
        self.time_sent = None
        self.timeout = None
        self.url_for_response = None
        self.answer_response = None
        self.time_answered = None
        self.status = "Empty"
        self.metadata = None

    def clear(self):
        self.test_type = None
        self.question_id = None
        self.name = None
        self.description = None
        self.question = None
        self.answers = None
        self.time_sent = None
        self.timeout = None
        self.url_for_response = None
        self.answer_response = None
        self.time_answered = None
        self.status = "Empty"
        self.metadata = None

    def getStatus(self):
        return self.status

    def setJson(self, json_str):
        self.status = "Test"
        self.test_type = json_str["test_type"]
        self.question_id = json_str["question_id"]
        self.name = json_str["name"]
        self.description = json_str["description"]
        self.question = json_str["question"]
        self.answers = json_str["answers"]
        self.time_sent = json_str["time_sent"]
        self.timeout = json_str['timeout']
        self.url_for_response = json_str["url_for_response"]
        self.answer_response = json_str["answer_response"]
        self.time_answered = json_str["time_answered"]
        self.metadata = json_str["metadata"]

    def getJson(self):
        json_data = {
            "test_type": self.test_type,
            "question_id": self.question_id,
            "name": self.name,
            "description": self.description,
            "question": self.question,
            "answers": self.answers,
            "time_sent": self.time_sent,
            "timeout": self.timeout,
            "url_for_response": self.url_for_response,
            "answer_response": self.answer_response,
            "time_answered": self.time_answered,
            "metadata": self.metadata
        }
        return json.dumps(json_data)

    def setAnswer(self, answer):
        self.answer_response = answer
        self.time_answered = time.time()

    def getTest(self):
        return self.test_type
    
    def getQuestionID(self):
        return self.question_id
    
    def getName(self):
        return self.name

    def getDescription(self):
        return self.description

    def getQuestion(self):
        return self.question

    def getAnswers(self):
        return self.answers

    def getTime(self):
        return self.time_sent
    
    def getTimeout(self):
        return self.timeout

    def getUrl(self):
        return self.url_for_response

    def getMetadata(self):
        return self.metadata

data = DataStore()
