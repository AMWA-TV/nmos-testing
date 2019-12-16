# Copyright (C) 2019 Advanced Media Workflow Association
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

from . import TestHelper

from .NMOSUtils import NMOSUtils


class IS07Utils(NMOSUtils):
    def __init__(self, url):
        NMOSUtils.__init__(self, url)

    def get_sources_states_and_types(self):
        """Gets a list of the available source objects with state and type on the API"""
        toReturn = {}
        sources_url = self.url + "sources/"
        valid_sources, sources = TestHelper.do_request("GET", sources_url)
        if valid_sources:
            for source in sources.json():
                source_id = source[:-1]
                toReturn[source_id] = {}
                for sub_path in ["state", "type"]:
                    valid_sub, sub = TestHelper.do_request("GET", "{}/{}/{}".format(sources_url, source_id, sub_path))
                    if valid_sub:
                        toReturn[source_id][sub_path] = sub.json()
        return toReturn
