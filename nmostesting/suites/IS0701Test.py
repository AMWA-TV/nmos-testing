# Copyright (C) 2018 British Broadcasting Corporation
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

from requests.compat import json

from ..GenericTest import GenericTest

EVENTS_API_KEY = "events"


class IS0701Test(GenericTest):
    """
    Runs IS-07-01-Test
    """
    def __init__(self, apis):
        GenericTest.__init__(self, apis)
        self.events_url = self.apis[EVENTS_API_KEY]["url"]
        self.sources = {}

    def do_collect_sources(self, test):
        """Collect a copy of each of the sources' type and state"""
        if len(self.sources) > 0:
            return

        sources_url = self.events_url + "sources"
        valid_sources, sources = self.do_request("GET", sources_url)
        if not valid_sources or sources.status_code != 200:
            raise NMOSTestException(test.FAIL("Unexpected response from Events API: {}".format(sources)))

        try:
            for source in sources.json():
                source_id = source[:-1]
                self.sources[source_id] = {}
                for sub_path in ["state", "type"]:
                    valid_sub, sub = self.do_request("GET", "{}/{}/{}".format(sources_url, source_id, sub_path))
                    if not valid_sub or sub.status_code != 200:
                        raise NMOSTestException(test.FAIL("Unexpected response from Events API: {}".format(sub)))
                    self.sources[source_id][sub_path] = sub.json()
        except json.JSONDecodeError:
            raise NMOSTestException(test.FAIL("Non-JSON response returned from Events API"))
        except ValueError:
            raise NMOSTestException(test.FAIL("Invalid response returned from Events API"))

    def test_01(self, test):
        """Each Source state identity includes the correct ID"""
        self.do_collect_sources(test)

        if len(self.sources) == 0:
            return test.UNCLEAR("No sources were returned from Events API")

        try:
            for source_id in self.sources:
                if source_id != self.sources[source_id]["state"]["identity"]["source_id"]:
                    return test.FAIL("Source {} state has incorrect source_id".format(source_id))
        except KeyError:
            return test.FAIL("Source {} state JSON data is invalid".format(source_id))

        return test.PASS()

    def test_02(self, test):
        """Each Source state identity does not include a Flow ID"""
        self.do_collect_sources(test)

        if len(self.sources) == 0:
            return test.UNCLEAR("No sources were returned from Events API")

        try:
            for source_id in self.sources:
                if "flow_id" in self.sources[source_id]["state"]["identity"]:
                    return test.FAIL("Source {} state has flow_id which is not permitted".format(source_id))
        except KeyError:
            return test.FAIL("Source {} state JSON data is invalid".format(source_id))

        return test.PASS()
