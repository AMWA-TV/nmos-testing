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


class Test(object):
    def __init__(self, description):
        self.description = description

    def PASS(self, detail=""):
        return [self.description, "Pass", detail]

    def MANUAL(self, detail=""):
        return [self.description, "Manual", detail]

    def NA(self, detail):
        return [self.description, "N/A", detail]

    def FAIL(self, detail):
        return [self.description, "Fail", detail]
