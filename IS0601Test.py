
# Copyright (C) 2018 Riedel Communications GmbH & Co. KG
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

import os

from TestHelper import Specification
from Generic import GenericTest


class IS0601Test(GenericTest):
    """
    Runs IS-06-01-Test
    """
    def __init__(self, base_url, api_name, spec_versions, test_version, spec_path):
        GenericTest.__init__(self, base_url, api_name, spec_versions, test_version, spec_path)

    def execute_tests(self):
        super(IS0601Test, self).execute_tests()

    def parse_RAML(self):
        self.netctrl_api = Specification(os.path.join(self.spec_path + '/APIs/NetworkControlAPI.raml'))
