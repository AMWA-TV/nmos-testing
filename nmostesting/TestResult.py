# Copyright (C) 2018 British Broadcasting Corporation
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

import inspect
import datetime
import time

from enum import Enum


class TestStates(Enum):
    PASS = 0
    WARNING = 1
    FAIL = 2
    MANUAL = 3
    NA = 4
    OPTIONAL = 5
    DISABLED = 6
    UNCLEAR = 7

    def __init__(self, *args):
        self.names = ["Pass", "Warning", "Fail", "Manual", "Not Applicable", "Not Implemented", "Test Disabled",
                      "Could Not Test"]
        self.classes = ["bg-success", "bg-warning", "bg-danger", "bg-primary", "bg-secondary", "bg-warning",
                        "bg-warning", "bg-warning"]

    def __str__(self):
        return self.names[self.value]

    @property
    def css_class(self):
        return self.classes[self.value]


class TestResult(object):
    def __init__(self, name, state, description, detail, link, timestamp, elapsed_time):
        self.name = name
        self.state = state
        self.description = description
        self.detail = detail
        self.link = link
        self.timestamp = timestamp
        self.elapsed_time = elapsed_time

    def output(self):
        return [self.name, str(self.state), self.state.css_class, self.description, self.detail, self.link,
                self.timestamp, "{0:.3f}s".format(self.elapsed_time)]


class Test(object):
    def __init__(self, description, name=None):
        self.description = description
        self.name = name
        if not self.name:
            # Get name of calling function
            self.name = inspect.stack()[1][3]
        self.timer = time.time()

    def _current_time(self):
        return datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]

    def _time_elapsed(self):
        return time.time() - self.timer

    # Pass: Successful test case
    def PASS(self, detail="", link=None):
        return TestResult(self.name, TestStates.PASS, self.description, detail, link, self._current_time(),
                          self._time_elapsed())

    # Warning: Not a failure, but the API being tested is responding or configured in a way which is
    # not recommended in most cases
    def WARNING(self, detail="", link=None):
        return TestResult(self.name, TestStates.WARNING, self.description, detail, link, self._current_time(),
                          self._time_elapsed())

    # Manual: Test suite does not currently test this feature, so it must be tested manually
    def MANUAL(self, detail="", link=None):
        return TestResult(self.name, TestStates.MANUAL, self.description, detail, link, self._current_time(),
                          self._time_elapsed())

    # Not Applicable: Test is not applicable, e.g. due to the version of the specification being tested
    def NA(self, detail, link=None):
        return TestResult(self.name, TestStates.NA, self.description, detail, link, self._current_time(),
                          self._time_elapsed())

    # Fail: Required feature of the specification has been found to be implemented incorrectly
    def FAIL(self, detail, link=None):
        return TestResult(self.name, TestStates.FAIL, self.description, detail, link, self._current_time(),
                          self._time_elapsed())

    # Optional: Recommended/optional feature of the specifications has been found to be not implemented
    # Detail message should explain the effect of this feature being unimplemented
    def OPTIONAL(self, detail, link=None):
        return TestResult(self.name, TestStates.OPTIONAL, self.description, detail, link, self._current_time(),
                          self._time_elapsed())

    # Disabled: Test is disabled due to test suite configuration; change the config or test manually
    def DISABLED(self, detail="", link=None):
        return TestResult(self.name, TestStates.DISABLED, self.description, detail, link, self._current_time(),
                          self._time_elapsed())

    # Unclear: Test was not run due to prior responses from the API, which may be OK, or indicate a fault
    def UNCLEAR(self, detail="", link=None):
        return TestResult(self.name, TestStates.UNCLEAR, self.description, detail, link, self._current_time(),
                          self._time_elapsed())
