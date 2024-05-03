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

from ..IS12Utils import IS12Utils

from .MS0502Test import MS0502Test


class IS1202Test(MS0502Test):

    def __init__(self, apis, **kwargs):
        self.is12_utils = IS12Utils(apis)
        MS0502Test.__init__(self, apis, self.is12_utils, **kwargs)

    def set_up_tests(self):
        super().set_up_tests()
        # Don't set up mock resources as not needed
        pass

    def tear_down_tests(self):
        super().tear_down_tests()
        # Clean up Websocket resources
        self.is12_utils.close_ncp_websocket()
