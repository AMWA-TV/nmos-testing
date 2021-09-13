# Copyright 2017 British Broadcasting Corporation
#
# Modifications Copyright 2018 Riedel Communications GmbH & Co. KG
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

from .NMOSUtils import NMOSUtils
from . import TestHelper


class IS11Utils(NMOSUtils):
    def __init__(self, url):
        NMOSUtils.__init__(self, url)

    # TODO(prince-chrism): Move to NMOSUtils since I copied the implementation from IS-05
    def _get_resource(self, list_endpoint):
        """Gets a list of the available resource at the list endpoint"""

        toReturn = []
        valid, r = TestHelper.do_request("GET", self.url + list_endpoint)
        if valid and r.status_code == 200:
            try:
                for value in r.json():
                    toReturn.append(value[:-1])
            except ValueError:
                pass
        return toReturn

    def get_senders(self):
        """Gets a list of the available senders from the API"""
        return self._get_resource("senders/")

    def get_receivers(self):
        """Gets a list of the available receivers from the API"""
        return self._get_resource("receivers/")

    def get_sinks(self):
        """Gets a list of the available sink from the API"""
        return self._get_resource("sinks/")
