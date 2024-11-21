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

from ..IS14Utils import IS14Utils
from .MS0502Test import MS0502Test


class IS1402Test(MS0502Test):
    """
    Runs Invasive Tests covering MS-05 and IS-12
    """
    def __init__(self, apis, **kwargs):
        MS0502Test.__init__(self, apis, IS14Utils(apis), **kwargs)

    def set_up_tests(self):
        super().set_up_tests()

    def tear_down_tests(self):
        super().tear_down_tests()
