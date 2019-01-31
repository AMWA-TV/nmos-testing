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
import time

class Test(object):
    def __init__(self, description, name=None):
        self.description = description
        self.name = name
        if not self.name:
            # Get name of calling function
            self.name = inspect.stack()[1][3]
        self.timer = time.time()

    def _time_elapsed(self):
        return "{0:.3f}s".format(time.time() - self.timer)

    # Pass: Successful test case
    def PASS(self, detail="", link=None):
        return [self.name, "Pass", "bg-success", self.description, detail, link, self._time_elapsed()]

    # Warning: Not a failure, but the API being tested is responding or configured in a way which is
    # not recommended in most cases
    def WARNING(self, detail="", link=None):
        return [self.name, "Warning", "bg-warning", self.description, detail, link, self._time_elapsed()]

    # Manual: Test suite does not currently test this feature, so it must be tested manually
    def MANUAL(self, detail="", link=None):
        return [self.name, "Manual", "bg-primary", self.description, detail, link, self._time_elapsed()]

    # Not Applicable: Test is not applicable, e.g. due to the version of the specification being tested
    def NA(self, detail, link=None):
        return [self.name, "Not Applicable", "bg-secondary", self.description, detail, link, self._time_elapsed()]

    # Fail: Required feature of the specification has been found to be implemented incorrectly
    def FAIL(self, detail, link=None):
        return [self.name, "Fail", "bg-danger", self.description, detail, link, self._time_elapsed()]

    # Optional: Recommended/optional feature of the specifications has been found to be not implemented
    # Detail message should explain the effect of this feature being unimplemented
    def OPTIONAL(self, detail, link=None):
        return [self.name, "Not Implemented", "bg-warning", self.description, detail, link, self._time_elapsed()]

    # Disabled: Test is disabled due to test suite configuration; change the config or test manually
    def DISABLED(self, detail="", link=None):
        return [self.name, "Test Disabled", "bg-warning", self.description, detail, link, self._time_elapsed()]

    # Unclear: Test was not run due to prior responses from the API, which may be OK, or indicate a fault
    def UNCLEAR(self, detail="", link=None):
        return [self.name, "Could Not Test", "bg-warning", self.description, detail, link, self._time_elapsed()]
