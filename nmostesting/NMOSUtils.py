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

import time
import functools
import random
from urllib.parse import urlparse
from requests.compat import json


from . import Config as CONFIG
from . import TestHelper

# The UTC leap seconds table below was extracted from the information provided at
# http://www.ietf.org/timezones/data/leap-seconds.list
#
# The order has been reversed.
# The NTP epoch seconds have been converted to Unix epoch seconds. The difference between
# the NTP epoch at 1 Jan 1900 and the Unix epoch at 1 Jan 1970 is 2208988800 seconds
UTC_LEAP = [
    # || UTC SEC  |  TAI SEC - 1 ||
    (1483228800, 1483228836),  # 1 Jan 2017, 37 leap seconds
    (1435708800, 1435708835),  # 1 Jul 2015, 36 leap seconds
    (1341100800, 1341100834),  # 1 Jul 2012, 35 leap seconds
    (1230768000, 1230768033),  # 1 Jan 2009, 34 leap seconds
    (1136073600, 1136073632),  # 1 Jan 2006, 33 leap seconds
    (915148800, 915148831),  # 1 Jan 1999, 32 leap seconds
    (867715200, 867715230),  # 1 Jul 1997, 31 leap seconds
    (820454400, 820454429),  # 1 Jan 1996, 30 leap seconds
    (773020800, 773020828),  # 1 Jul 1994, 29 leap seconds
    (741484800, 741484827),  # 1 Jul 1993, 28 leap seconds
    (709948800, 709948826),  # 1 Jul 1992, 27 leap seconds
    (662688000, 662688025),  # 1 Jan 1991, 26 leap seconds
    (631152000, 631152024),  # 1 Jan 1990, 25 leap seconds
    (567993600, 567993623),  # 1 Jan 1988, 24 leap seconds
    (489024000, 489024022),  # 1 Jul 1985, 23 leap seconds
    (425865600, 425865621),  # 1 Jul 1983, 22 leap seconds
    (394329600, 394329620),  # 1 Jul 1982, 21 leap seconds
    (362793600, 362793619),  # 1 Jul 1981, 20 leap seconds
    (315532800, 315532818),  # 1 Jan 1980, 19 leap seconds
    (283996800, 283996817),  # 1 Jan 1979, 18 leap seconds
    (252460800, 252460816),  # 1 Jan 1978, 17 leap seconds
    (220924800, 220924815),  # 1 Jan 1977, 16 leap seconds
    (189302400, 189302414),  # 1 Jan 1976, 15 leap seconds
    (157766400, 157766413),  # 1 Jan 1975, 14 leap seconds
    (126230400, 126230412),  # 1 Jan 1974, 13 leap seconds
    (94694400, 94694411),  # 1 Jan 1973, 12 leap seconds
    (78796800, 78796810),  # 1 Jul 1972, 11 leap seconds
    (63072000, 63072009),  # 1 Jan 1972, 10 leap seconds
]

DEFAULT_ARGS = {
    "list_suites": False,
    "describe_suites": False,
    "list_tests": False,
    "describe_tests": False,
    "host": [],
    "port": [],
    "version": [],
    "selector": [],
    "ignore": [],
    "output": None,
    "selection": "all"
}


class NMOSUtils(object):

    # Seedable instance of random for deterministic testing
    RANDOM = random.Random()

    def __init__(self, url):
        self.url = url

    @staticmethod
    def from_UTC(secs, nanos, is_leap=False):
        """Convert a UTC time into a TAI time"""
        leap_sec = 0
        for tbl_sec, tbl_tai_sec_minus_1 in UTC_LEAP:
            if secs >= tbl_sec:
                leap_sec = (tbl_tai_sec_minus_1 + 1) - tbl_sec
                break
        return secs + leap_sec + is_leap, nanos

    @staticmethod
    def get_TAI_time(offset=0.0):
        """Get the current TAI time as a colon-separated string"""
        myTime = time.time() + offset
        secs = int(myTime)
        nanos = int((myTime - secs) * 1e9)
        ippTime = NMOSUtils.from_UTC(secs, nanos)
        return str(ippTime[0]) + ":" + str(ippTime[1])

    @staticmethod
    def compare_resource_version(ver1, ver2):
        """Returns 1 if ver1>ver2, 0 if ver1=ver2, and -1 if ver1<ver2"""
        ver1_bits = ver1.split(":")
        ver2_bits = ver2.split(":")

        # Compare seconds
        if int(ver1_bits[0]) > int(ver2_bits[0]):
            return 1
        elif int(ver2_bits[0]) > int(ver1_bits[0]):
            return -1

        # Compare nanoseconds
        if int(ver1_bits[1]) > int(ver2_bits[1]):
            return 1
        elif int(ver2_bits[1]) > int(ver1_bits[1]):
            return -1
        else:
            return 0

    @staticmethod
    def compare_api_version(ver1, ver2):
        """Returns 1 if ver1>ver2, 0 if ver1=ver2, and -1 if ver1<ver2"""
        ver1_bits = ver1.strip("v").split(".")
        ver2_bits = ver2.strip("v").split(".")

        # Compare major
        if int(ver1_bits[0]) > int(ver2_bits[0]):
            return 1
        elif int(ver2_bits[0]) > int(ver1_bits[0]):
            return -1

        # Compare minor
        if int(ver1_bits[1]) > int(ver2_bits[1]):
            return 1
        elif int(ver2_bits[1]) > int(ver1_bits[1]):
            return -1
        else:
            return 0

    @staticmethod
    def compare_urls(url1, url2):
        """Check that two URLs to a given API are sufficiently similar"""

        url1_parsed = urlparse(url1.rstrip("/"))
        url2_parsed = urlparse(url2.rstrip("/"))

        for attr in ["scheme", "path"]:
            if getattr(url1_parsed, attr) != getattr(url2_parsed, attr):
                return False
        for attr in ["hostname"]:
            if getattr(url1_parsed, attr).lower().rstrip('.') != getattr(url2_parsed, attr).lower().rstrip('.'):
                return False

        # Ports can be None if they are the default for the scheme
        ports = [url1_parsed.port, url2_parsed.port]
        comparisons = [url1_parsed, url2_parsed]
        for index, url in enumerate(comparisons):
            if url.port is None and url.scheme == "http":
                ports[index] = 80
            elif url.port is None and url.scheme == "https":
                ports[index] = 443

        if ports[0] != ports[1]:
            return False

        return True

    @staticmethod
    def sampled_list(resource_list):
        if CONFIG.MAX_TEST_ITERATIONS > 0:
            return NMOSUtils.RANDOM.sample(resource_list, min(CONFIG.MAX_TEST_ITERATIONS, len(resource_list)))
        else:
            return resource_list

    @staticmethod
    def sort_versions(versions_list):
        return sorted(versions_list, key=functools.cmp_to_key(NMOSUtils.compare_api_version))

    @staticmethod
    def do_test_device_control(test, node_url, type, href, authorization):
        """At least one Device is showing the given control advertisement matching the API under test"""

        valid, devices = TestHelper.do_request("GET", node_url + "devices")
        if not valid:
            return test.FAIL("Node API did not respond as expected: {}".format(devices))

        found_type = False
        found_api = False
        try:
            for device in devices.json():
                controls = device["controls"]
                for control in controls:
                    if control["type"] == type:
                        found_type = True
                        if NMOSUtils.compare_urls(href, control["href"]) and \
                                authorization is control.get("authorization", False):
                            found_api = True
        except json.JSONDecodeError:
            return test.FAIL("Non-JSON response returned from Node API")
        except KeyError:
            return test.FAIL("One or more Devices were missing the 'controls' attribute")

        if found_api:
            return test.PASS()
        elif found_type:
            return test.FAIL("Found one or more Device controls, but no href and authorization mode matched the "
                             "API under test")
        else:
            return test.FAIL("Unable to find any Devices which expose the control type '{}'".format(type))
