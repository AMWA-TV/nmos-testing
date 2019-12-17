# Copyright 2017 British Broadcasting Corporation
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


class IS04Utils(NMOSUtils):
    def __init__(self, url):
        NMOSUtils.__init__(self, url)

    def get_self(self):
        """Get node self resource from the Node API"""

        valid_resource, resource = TestHelper.do_request("GET", self.url + "self")
        if valid_resource and resource.status_code == 200:
            return resource.json()

    def get_devices(self):
        """Get node devices from the Node API"""

        return self.get_resources(self.url + "devices")

    def get_sources(self):
        """Get node sources from the Node API"""

        return self.get_resources(self.url + "sources")

    def get_flows(self):
        """Get node flows from the Node API"""

        return self.get_resources(self.url + "flows")

    def get_senders(self):
        """Get node senders from the Node API"""

        return self.get_resources(self.url + "senders")

    def get_receivers(self):
        """Get node receivers from the Node API"""

        return self.get_resources(self.url + "receivers")

    def get_resources(self, url):
        """Get node resources from the Node API"""

        toReturn = {}
        valid_resources, resources = TestHelper.do_request("GET", url)
        if valid_resources and resources.status_code == 200:
            for res in resources.json():
                toReturn[res["id"]] = res

        return toReturn
