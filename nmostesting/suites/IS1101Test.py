# Copyright (C) 2022 Advanced Media Workflow Association
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

COMPAT_API_KEY = "streamcompatibility"


class IS1101Test(GenericTest):
    """
    Runs Node Tests covering IS-11
    """
    def __init__(self, apis, **kwargs):
        # Don't auto-test paths responding with an EDID binary as they don't have a JSON Schema
        omit_paths = [
            "/inputs/{inputId}/edid/base",
            "/inputs/{inputId}/edid/effective",
            "/outputs/{outputId}/edid"
        ]
        GenericTest.__init__(self, apis, omit_paths, **kwargs)
        self.compat_url = self.apis[COMPAT_API_KEY]["url"]
