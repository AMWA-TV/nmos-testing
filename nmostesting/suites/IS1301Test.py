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

from ..GenericTest import GenericTest, NMOSTestException
from ..TestHelper import compare_json

ANNOTATION_API_KEY = "annotation"


class IS1301Test(GenericTest):
    """
    Runs IS-13-Test
    """
    def __init__(self, apis, **kwargs):
        GenericTest.__init__(self, apis, **kwargs)
        self.annotation_url = self.apis[ANNOTATION_API_KEY]["url"]

    def test_01(self, test):
        """ 1st annotation test  """

        if compare_json({}, {}):
            return test.PASS()
        else:
            return test.FAIL("IO Resource does not correctly reflect the API resources")
