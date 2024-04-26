# Copyright (C) 2024 Advanced Media Workflow Association
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

from ..GenericTest import GenericTest


class IS1401Test(GenericTest):
    """
    Runs IS-04-01-Test
    """
    def __init__(self, apis, auths, **kwargs):
        GenericTest.__init__(self, apis, auths=auths, **kwargs)

    def set_up_tests(self):
        pass

    def tear_down_tests(self):
        pass

    def test_01(self, test):
        """First test"""

        return test.UNCLEAR("Noting was tested.")
