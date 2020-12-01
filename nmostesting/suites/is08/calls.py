# Copyright (C) 2019 Advanced Media Workflow Association
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


from ...TestHelper import do_request
from ...GenericTest import NMOSTestException
from .testConfig import globalConfig


class Call:

    def __init__(self, url):
        self.url = url
        self.expectedCode = 200
        self.test = globalConfig.test
        self._responseObject = None
        self._method = None
        self.responseSchema = None

    def get(self):
        return self._genericRequestProcess("get")

    def post(self, data):
        return self._genericRequestProcess("post", data)

    def delete(self):
        return self._genericRequestProcess("delete")

    def _genericRequestProcess(self, method, data=None):
        self._method = method
        (self._callSucceeded, self._responseObject) = do_request(method, self.url, json=data)
        return self._processResponseObject()

    def _processResponseObject(self):
        self._checkForErrors()
        self._checkStatusCode()
        self._checkResponseSchema()
        if self.expectedCode != 204:
            return self._getJSON()
        else:
            return None

    def _checkForErrors(self):
        if not self._callSucceeded:
            raise NMOSTestException(self.test.FAIL(self._responseObject))

    def _checkStatusCode(self):
        if self.expectedCode is not None:
            statusCode = self._responseObject.status_code

            if statusCode != self.expectedCode:
                res = self.test.FAIL("Unexpected response code {} from url {}, expected {}"
                                     .format(statusCode, self.url, self.expectedCode))
                raise NMOSTestException(res)

    def _checkResponseSchema(self):
        if self.responseSchema is not None:
            globalConfig.testSuite.check_response(
                self.responseSchema,
                self._method,
                self._responseObject
            )

    def _getJSON(self):
        try:
            response = self._responseObject.json()
        except ValueError:
            raise NMOSTestException(self.test.FAIL("Invalid JSON received from {}".format(self.url)))
        return response
