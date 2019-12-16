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

import fractions
import re

from requests.compat import json

from ..GenericTest import GenericTest, NMOSTestException

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
        except KeyError as e:
            return test.FAIL("Source {} JSON data did not include the expected key: {}".format(source_id, e))

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
        except KeyError as e:
            return test.FAIL("Source {} JSON data did not include the expected key: {}".format(source_id, e))

        return test.PASS()

    def test_03(self, test):
        """Each Source type 'type' is a base type of the state 'event_type'"""
        self.do_collect_sources(test)

        if len(self.sources) == 0:
            return test.UNCLEAR("No sources were returned from Events API")

        try:
            for source_id in self.sources:
                base_type = self.sources[source_id]["state"]["event_type"].split("/")[0]
                if base_type != self.sources[source_id]["type"]["type"]:
                    return test.FAIL("Source {} state does not match the base type".format(source_id))
        except KeyError as e:
            return test.FAIL("Source {} JSON data did not include the expected key: {}".format(source_id, e))

        return test.PASS()

    def test_04_01(self, test):
        """Each number Source type describes a valid set of allowed values"""
        self.do_collect_sources(test)

        found_number = False

        try:
            for source_id in self.sources:
                source = self.sources[source_id]
                if "number" != source["type"]["type"]:
                    continue
                # all 'enum' types define the allowed values
                if "values" in source["type"]:
                    continue
                found_number = True

                min = self.get_number(source["type"]["min"])
                max = self.get_number(source["type"]["max"])

                if min > max:
                    return test.FAIL("Source {} maximum value is less than the minimum".format(source_id))

                # check 'step'
                if "step" in source["type"]:
                    step = self.get_number(source["type"]["step"])
                    if 0 != (max - min) % step:
                        return test.WARNING("Source {} max - min is not an integer multiple of the step"
                                            .format(source_id))
        except KeyError as e:
            return test.FAIL("Source {} JSON data did not include the expected key: {}".format(source_id, e))
        except ZeroDivisionError as e:
            return test.FAIL("Source {} scale of zero is not allowed: {}".format(source_id, e))

        if not found_number:
            return test.UNCLEAR("No 'number' sources were returned from Events API")

        return test.PASS()

    def test_04_02(self, test):
        """Each string Source type describes a valid set of allowed values"""
        self.do_collect_sources(test)

        found_string = False

        try:
            for source_id in self.sources:
                source = self.sources[source_id]
                if "string" != source["type"]["type"]:
                    continue
                # all 'enum' types define the allowed values
                if "values" in source["type"]:
                    continue
                found_string = True

                if "min_length" in source["type"] and "max_length" in source["type"]:
                    min_length = source["type"]["min_length"]
                    max_length = source["type"]["max_length"]
                    if min_length > max_length:
                        return test.FAIL("Source {} minimum length is longer than the maximum"
                                         .format(source_id))

                if "pattern" in source["type"]:
                    pattern = source["type"]["pattern"]
                    re.compile(pattern)
        except KeyError as e:
            return test.FAIL("Source {} JSON data did not include the expected key: {}".format(source_id, e))
        except re.error:
            return test.FAIL("Source {} type pattern is invalid".format(source_id))

        if not found_string:
            return test.UNCLEAR("No 'string' sources were returned from Events API")

        return test.PASS()

    def test_05(self, test):
        """Each enum Source type describes a valid set of allowed values"""
        self.do_collect_sources(test)

        found_enum = False

        try:
            for source_id in self.sources:
                source = self.sources[source_id]
                # all 'enum' types define the allowed values
                if "values" not in source["type"]:
                    continue
                found_enum = True

                values = source["type"]["values"]
                if len(values) == 0:
                    return test.FAIL("Source {} type defines no allowed values".format(source_id))
                if len(set([_["value"] for _ in values])) != len(values):
                    return test.WARNING("Source {} type includes a duplicate in the allowed values".format(source_id))
        except KeyError as e:
            return test.FAIL("Source {} JSON data did not include the expected key: {}".format(source_id, e))

        if not found_enum:
            return test.UNCLEAR("No 'enum' sources were returned from Events API")

        return test.PASS()

    def test_06_01(self, test):
        """Each number Source state payload 'value' and 'scale' represent one of the allowed values"""
        self.do_collect_sources(test)

        found_number = False

        try:
            for source_id in self.sources:
                source = self.sources[source_id]
                if "number" != source["type"]["type"]:
                    continue
                # all 'enum' types define the allowed values
                if "values" in source["type"]:
                    continue
                found_number = True

                payload = self.get_number(source["state"]["payload"])

                min = self.get_number(source["type"]["min"])
                # check 'min' inclusive
                if min > payload:
                    return test.FAIL("Source {} state payload is less than the minimum".format(source_id))

                max = self.get_number(source["type"]["max"])
                # check 'max' inclusive
                if max < payload:
                    return test.FAIL("Source {} state payload is greater than the maximum".format(source_id))

                # check 'step'
                if "step" in source["type"]:
                    step = self.get_number(source["type"]["step"])
                    if 0 != (payload - min) % step:
                        return test.WARNING("Source {} state payload is not an integer multiple of the step"
                                            .format(source_id))
        except KeyError as e:
            return test.FAIL("Source {} JSON data did not include the expected key: {}".format(source_id, e))
        except ZeroDivisionError as e:
            return test.FAIL("Source {} scale of zero is not allowed: {}".format(source_id, e))

        if not found_number:
            return test.UNCLEAR("No 'number' sources were returned from Events API")

        return test.PASS()

    def test_06_02(self, test):
        """Each string Source state payload 'value' is one of the allowed values"""
        self.do_collect_sources(test)

        found_string = False

        try:
            for source_id in self.sources:
                source = self.sources[source_id]
                if "string" != source["type"]["type"]:
                    continue
                # all 'enum' types define the allowed values
                if "values" in source["type"]:
                    continue
                found_string = True

                value = source["state"]["payload"]["value"]

                if "min_length" in source["type"]:
                    min_length = source["type"]["min_length"]
                    if min_length > len(value):
                        return test.FAIL("Source {} state payload is shorter than the minimum length"
                                         .format(source_id))

                if "max_length" in source["type"]:
                    max_length = source["type"]["max_length"]
                    if max_length < len(value):
                        return test.FAIL("Source {} state payload is longer than the maximum length"
                                         .format(source_id))

                if "pattern" in source["type"]:
                    pattern = source["type"]["pattern"]
                    if re.match(pattern, value) is None:
                        return test.FAIL("Source {} state payload does not match the pattern".format(source_id))
        except KeyError as e:
            return test.FAIL("Source {} JSON data did not include the expected key: {}".format(source_id, e))
        except re.error:
            return test.FAIL("Source {} type pattern is invalid".format(source_id))

        if not found_string:
            return test.UNCLEAR("No 'string' sources were returned from Events API")

        return test.PASS()

    def test_06_03(self, test):
        """Each boolean Source state payload 'value' is one of the allowed values"""
        self.do_collect_sources(test)

        found_boolean = False

        try:
            for source_id in self.sources:
                source = self.sources[source_id]
                if "boolean" != source["type"]["type"]:
                    continue
                # all 'enum' types define the allowed values
                if "values" in source["type"]:
                    continue
                found_boolean = True

                # nothing to do, since schema check is enough
        except KeyError as e:
            return test.FAIL("Source {} JSON data did not include the expected key: {}".format(source_id, e))

        if not found_boolean:
            return test.UNCLEAR("No 'boolean' sources were returned from Events API")

        return test.PASS()

    def test_07(self, test):
        """Each enum Source state payload 'value' is one of the allowed values"""
        self.do_collect_sources(test)

        found_enum = False

        try:
            for source_id in self.sources:
                source = self.sources[source_id]
                # all 'enum' types define the allowed values
                if "values" not in source["type"]:
                    continue
                found_enum = True

                value = source["state"]["payload"]["value"]

                if value not in [_["value"] for _ in source["type"]["values"]]:
                    return test.FAIL("Source {} state payload is not an allowed value".format(source_id))

                if "number" == source["type"]["type"] and "scale" in source["state"]["payload"]:
                    return test.FAIL("Source {} state payload has a 'scale', which is invalid for number 'enum' types"
                                     .format(source_id))
        except KeyError as e:
            return test.FAIL("Source {} JSON data did not include the expected key: {}".format(source_id, e))

        if not found_enum:
            return test.UNCLEAR("No 'enum' sources were returned from Events API")

        return test.PASS()

    def test_08(self, test):
        """Each number Source type 'scale' values and state payload 'scale' are consistent"""
        self.do_collect_sources(test)

        found_number = False

        try:
            for source_id in self.sources:
                source = self.sources[source_id]
                if "number" != source["type"]["type"]:
                    continue
                # all 'enum' types define the allowed values
                if "values" in source["type"]:
                    continue
                found_number = True

                scale = source["type"]["scale"] if "scale" in source["type"] else self.get_scale(source["type"]["min"])

                if self.get_scale(source["type"]["min"]) != scale:
                    return test.WARNING("Source {} type 'min' scaleis inconsistent with 'scale'"
                                        .format(source_id))

                if self.get_scale(source["type"]["max"]) != scale:
                    return test.WARNING("Source {} type 'max' scale is inconsistent with 'min' scale"
                                        .format(source_id))

                if "step" in source["type"]:
                    if self.get_scale(source["type"]["step"]) != scale:
                        return test.WARNING("Source {} type 'step' scale is inconsistent with 'min' and 'max' scale"
                                            .format(source_id))

                payload_scale = self.get_scale(source["state"]["payload"])
                if payload_scale != scale:
                    return test.WARNING("Source {} state payload 'scale' is inconsistent with type 'scale' values"
                                        .format(source_id))

        except KeyError as e:
            return test.FAIL("Source {} JSON data did not include the expected key: {}".format(source_id, e))

        if not found_number:
            return test.UNCLEAR("No 'number' sources were returned from Events API")

        return test.PASS()

    def get_scale(self, payload):
        return 1 if "scale" not in payload else payload["scale"]

    def get_number(self, payload):
        return fractions.Fraction(fractions.Fraction(payload["value"]), self.get_scale(payload))
