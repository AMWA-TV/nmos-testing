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

NODE_API_KEY = "node"
CONN_API_KEY = "connection"


class BCP0060101Test(GenericTest):
    """
    Runs Node Tests covering BCP-006-01
    """
    def __init__(self, apis):
        # Don't auto-test /transportfile as it is permitted to generate a 404 when master_enable is false
        omit_paths = [
            "/single/senders/{senderId}/transportfile"
        ]
        GenericTest.__init__(self, apis, omit_paths)
        self.node_url = self.apis[NODE_API_KEY]["url"]
        self.connection_url = self.apis[CONN_API_KEY]["url"]
