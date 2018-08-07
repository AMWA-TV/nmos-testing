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


import requests
import uuid
import json
import os
import re
import time
from jsonschema import ValidationError, SchemaError, RefResolver, Draft4Validator
from random import randint

import TestHelper

SCHEMA_LOCAL = "schemas/"
HEADERS = {'Content-Type': 'application/json'}

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


class IS0501Test:
    """
    Runs IS-05-01-Test
    Result-format:

    #TestNumber#    #TestDescription#   #Succeeded?#    #Reason#
    """

    def __init__(self, url):
        self.url = url
        self.result = list()
        self.senders = self.get_senders()
        self.receivers = self.get_receivers()
        self.file_prefix = "file:///" if os.name == "nt" else "file:"

    def run_tests(self):
        self.result.append(self.test_01())
        self.result.append(self.test_02())
        self.result.append(self.test_03())
        self.result.append(self.test_04())
        self.result.append(self.test_05())
        self.result.append(self.test_06())
        self.result.append(self.test_07())
        self.result.append(self.test_08())
        self.result.append(self.test_09())
        self.result.append(self.test_10())
        self.result.append(self.test_11())
        self.result.append(self.test_12())
        self.result.append(self.test_13())
        self.result.append(self.test_14())
        self.result.append(self.test_15())
        self.result.append(self.test_16())
        self.result.append(self.test_17())
        self.result.append(self.test_18())
        self.result.append(self.test_19())
        self.result.append(self.test_20())
        self.result.append(self.test_21())
        self.result.append(self.test_22())
        self.result.append(self.test_23())
        self.result.append(self.test_24())
        self.result.append(self.test_25())
        self.result.append(self.test_26())
        self.result.append(self.test_27())
        self.result.append(self.test_28())
        self.result.append(self.test_29())
        self.result.append(self.test_30())
        self.result.append(self.test_31())
        self.result.append(self.test_32())
        self.result.append(self.test_33())
        self.result.append(self.test_34())
        self.result.append(self.test_35())
        self.result.append(self.test_36())
        self.result.append(self.test_37())
        self.result.append(self.test_38())
        self.result.append(self.test_39())
        return self.result

    def test_01(self):
        """Api root matches the spec"""
        test_number = "01"
        test_description = "Api root matches the spec"
        expected = ["single/", "bulk/"]
        dest = ""
        valid, result = self.checkCleanGet(dest)
        if valid:
            msg = "Got the wrong json from {} - got {}. Please check json matches the spec, including trailing slashes" \
                .format(dest, result)
            if TestHelper.compare_json(expected, result):
                return test_number, test_description, "Pass", ""
            else:
                return test_number, test_description, "Fail", msg
        else:
            return test_number, test_description, "Fail", result

    def test_02(self):
        """Single endpoint root matches the spec"""
        test_number = "02"
        test_description = "Single endpoint root matches the spec"
        expected = ["receivers/", "senders/"]
        dest = "single/"
        valid, result = self.checkCleanGet(dest)
        if valid:
            msg = "Got the wrong json from {} - got {}. Please check json matches the spec, including trailing slashes" \
                .format(dest, result)
            if TestHelper.compare_json(expected, result):
                return test_number, test_description, "Pass", ""
            else:
                return test_number, test_description, "Fail", msg
        else:
            return test_number, test_description, "Fail", result

    def test_03(self):
        """Root of /single/senders/ matches the spec"""
        test_number = "03"
        test_description = "Root of /single/senders/ matches the spec"
        dest = "single/senders/"
        valid, response = self.checkCleanGet(dest)
        smsg = "UUIDs missing trailing slashes in response from {}".format(dest)
        umsg = "Response from {} containts invalid UUIDs".format(dest)
        amsg = "Expected an array from {}, got {}".format(dest, type(response))
        if valid:
            if isinstance(response, list):
                if len(response) > 0:
                    for value in response:
                        # Check each UUID has a trailing slash as per the spec
                        if value[-1] == "/":
                            try:
                                uuid.UUID(value[:-1])
                            except ValueError:
                                # Found something that isn't a valid UUID
                                return test_number, test_description, "Fail", umsg
                        else:
                            return test_number, test_description, "Fail", smsg
                    return test_number, test_description, "Pass", ""
                else:
                    return test_number, test_description, "N/A", "Not tested. No resources found."
            else:
                return test_number, test_description, "Fail", amsg
        else:
            return test_number, test_description, "Fail", response

    def test_04(self):
        """Root of /single/receivers/ matches the spec"""
        test_number = "04"
        test_description = "Root of /single/receivers/ matches the spec"
        dest = "single/receivers/"
        valid, response = self.checkCleanGet(dest)
        smsg = "UUIDs missing trailing slashes in response from {}".format(dest)
        umsg = "Response from {} containts invalid UUIDs".format(dest)
        amsg = "Expected an array from {}, got {}".format(dest, type(response))
        if valid:
            if isinstance(response, list):
                if len(response) > 0:
                    for value in response:
                        # Check each UUID has a trailing slash as per the spec
                        if value[-1] == "/":
                            try:
                                uuid.UUID(value[:-1])
                            except ValueError:
                                # Found something that isn't a valid UUID
                                return test_number, test_description, "Fail", umsg
                        else:
                            return test_number, test_description, "Fail", smsg
                    return test_number, test_description, "Pass", ""
                else:
                    return test_number, test_description, "N/A", "Not tested. No resources found."
            else:
                return test_number, test_description, "Fail", amsg
        else:
            return test_number, test_description, "Fail", response

    def test_05(self):
        """Index of /single/senders/<uuid>/ matches the spec"""
        test_number = "05"
        test_description = "Index of /single/senders/<uuid>/ matches the spec"
        if len(self.senders) > 0:
            for sender in self.senders:
                dest = "single/senders/" + sender + "/"
                valid, response = self.checkCleanGet(dest)
                expected = [
                    "constraints/",
                    "staged/",
                    "active/",
                    "transportfile/"
                ]
                msg = "Sender root at {} response incorrect, expected :{}, got {}".format(dest, expected, response)
                if valid:
                    if TestHelper.compare_json(expected, response):
                        pass
                    else:
                        return test_number, test_description, "Fail", msg
                else:
                    return test_number, test_description, "Fail", response
            return test_number, test_description, "Pass", ""
        else:
            return test_number, test_description, "N/A", "Not tested. No resources found."

    def test_06(self):
        """Index of /single/receivers/<uuid>/ matches the spec"""
        test_number = "06"
        test_description = "Index of /single/receivers/<uuid>/ matches the spec"
        if len(self.receivers) > 0:
            for receiver in self.receivers:
                dest = "single/receivers/" + receiver + "/"
                valid, response = self.checkCleanGet(dest)
                expected = [
                    "constraints/",
                    "staged/",
                    "active/"
                ]
                msg = "Receiver root at {} response incorrect, expected :{}, got {}".format(dest, expected, response)
                if valid:
                    if TestHelper.compare_json(expected, response):
                        pass
                    else:
                        return test_number, test_description, "Fail", msg
                else:
                    return test_number, test_description, "Fail", response
            return test_number, test_description, "Pass", ""
        else:
            return test_number, test_description, "N/A", "Not tested. No resources found."

    def test_07(self):
        """Return of /single/senders/<uuid>/constraints/ meets the schema"""
        test_number = "07"
        test_description = "Return of /single/senders/<uuid>/constraints/ meets the schema"
        if len(self.senders) > 0:
            for sender in self.senders:
                dest = "single/senders/" + sender + "/constraints/"
                valid, msg = self.compare_to_schema("v1.0-constraints-schema.json", dest)
                if valid:
                    pass
                else:
                    return test_number, test_description, "Fail", msg
            return test_number, test_description, "Pass", ""
        else:
            return test_number, test_description, "N/A", "Not tested. No resources found."

    def test_08(self):
        """Return of /single/receivers/<uuid>/constraints/ meets the schema"""
        test_number = "08"
        test_description = "Return of /single/receivers/<uuid>/constraints/ meets the schema"
        if len(self.receivers) > 0:
            for receiver in self.receivers:
                dest = "single/receivers/" + receiver + "/constraints/"
                valid, msg = self.compare_to_schema("v1.0-constraints-schema.json", dest)
                if valid:
                    pass
                else:
                    return test_number, test_description, "Fail", msg
            return test_number, test_description, "Pass", ""
        else:
            return test_number, test_description, "N/A", "Not tested. No resources found."

    def test_09(self):
        """All params listed in /single/senders/<uuid>/constraints/ matches /staged/ and /active/"""
        test_number = "09"
        test_description = "All params listed in /single/senders/<uuid>/constraints/ matches /staged/ and /active/"
        if len(self.senders) > 0:
            valid, response = self.check_params_match("senders", self.senders)
            if valid:
                return test_number, test_description, "Pass", ""
            else:
                if "Not tested. No resources found." in response:
                    return test_number, test_description, "N/A", response
                else:
                    return test_number, test_description, "Fail", response
        else:
            return test_number, test_description, "N/A", "Not tested. No resources found."

    def test_10(self):
        """All params listed in /single/receivers/<uuid>/constraints/ matches /staged/ and /active/"""
        test_number = "10"
        test_description = "All params listed in /single/receivers/<uuid>/constraints/ matches /staged/ and /active/"
        if len(self.receivers) > 0:
            valid, response = self.check_params_match("receivers", self.receivers)
            if valid:
                return test_number, test_description, "Pass", ""
            else:
                if "Not tested. No resources found." in response:
                    return test_number, test_description, "N/A", response
                else:
                    return test_number, test_description, "Fail", response
        else:
            return test_number, test_description, "N/A", "Not tested. No resources found."

    def test_11(self):
        """Senders are using valid combination of parameters"""
        test_number = "11"
        test_description = "Senders are using valid combination of parameters"

        generalParams = ['source_ip', 'destination_ip', 'destination_port', 'source_port', 'rtp_enabled']
        fecParams = ['fec_enabled', 'fec_destination_ip', 'fec_mode', 'fec_type',
                     'fec_block_width', 'fec_block_height', 'fec1D_destination_port',
                     'fec1D_source_port', 'fec2D_destination_port', 'fec2D_source_port']
        fecParams = fecParams + generalParams
        rtcpParams = ['rtcp_enabled', 'rtcp_destination_ip', 'rtcp_destination_port',
                      'rtcp_source_port']
        combinedParams = rtcpParams + fecParams
        rtcpParams = rtcpParams + generalParams

        if len(self.senders) > 0:
            for sender in self.senders:
                dest = "single/senders/" + sender + "/constraints/"
                try:
                    valid, response = self.checkCleanGet(dest)
                    if valid:
                        if len(response) > 0 and isinstance(response[0], dict):
                            params = response[0].keys()
                            if sorted(params) == sorted(generalParams):
                                pass
                            elif sorted(params) == sorted(fecParams):
                                pass
                            elif sorted(params) == sorted(rtcpParams):
                                pass
                            elif sorted(params) == sorted(combinedParams):
                                pass
                            else:
                                return test_number, test_description, "Fail", "Invalid combination of parameters on constraints endpoint."
                        else:
                            return test_number, test_description, "Fail", "Invalid response: {}".format(response)
                    else:
                        return test_number, test_description, "Fail", response
                except IndexError:
                    return test_number, test_description, "Fail", "Expected an array from {}, got {}".format(dest, response)
                except AttributeError:
                    return test_number, test_description, "Fail", "Expected constraints array at {} to contain dicts, got {}".format(
                        dest, response)
            return test_number, test_description, "Pass", ""
        else:
            return test_number, test_description, "N/A", "Not tested. No resources found."

    def test_12(self):
        """Receiver are using valid combination of parameters"""
        test_number = "12"
        test_description = "Receiver are using valid combination of parameters"

        generalParams = ['source_ip', 'multicast_ip', 'interface_ip', 'destination_port', 'rtp_enabled']
        fecParams = ['fec_enabled', 'fec_destination_ip', 'fec_mode',
                     'fec1D_destination_port', 'fec2D_destination_port']
        fecParams = fecParams + generalParams
        rtcpParams = ['rtcp_enabled', 'rtcp_destination_ip', 'rtcp_destination_port']
        combinedParams = rtcpParams + fecParams
        rtcpParams = rtcpParams + generalParams

        if len(self.receivers) > 0:
            for receiver in self.receivers:
                dest = "single/receivers/" + receiver + "/constraints/"
                try:
                    valid, response = self.checkCleanGet(dest)
                    if valid:
                        if len(response) > 0 and isinstance(response[0], dict):
                            params = response[0].keys()
                            if sorted(params) == sorted(generalParams):
                                pass
                            elif sorted(params) == sorted(fecParams):
                                pass
                            elif sorted(params) == sorted(rtcpParams):
                                pass
                            elif sorted(params) == sorted(combinedParams):
                                pass
                            else:
                                return test_number, test_description, "Fail", "Invalid combination of parameters on constraints endpoint."
                        else:
                            return test_number, test_description, "Fail", "Invalid response: {}".format(response)
                    else:
                        return test_number, test_description, "Fail", response
                except IndexError:
                    return test_number, test_description, "Fail", "Expected an array from {}, got {}".format(dest, response)
                except AttributeError:
                    return test_number, test_description, "Fail", "Expected constraints array at {} to contain dicts, got {}".format(
                        dest, response)
            return test_number, test_description, "Pass", ""
        else:
            return test_number, test_description, "N/A", "Not tested. No resources found."

    def test_13(self):
        """Return of /single/senders/<uuid>/staged/ meets the schema"""
        test_number = "13"
        test_description = "Return of /single/senders/<uuid>/staged/ meets the schema"
        if len(self.senders) > 0:
            for sender in self.senders:
                dest = "single/senders/" + sender + "/staged/"
                valid, msg = self.compare_to_schema("v1.0-sender-response-schema.json", dest)
                if valid:
                    pass
                else:
                    return test_number, test_description, "Fail", msg
            return test_number, test_description, "Pass", ""
        else:
            return test_number, test_description, "N/A", "Not tested. No resources found."

    def test_14(self):
        """Return of /single/receivers/<uuid>/staged/ meets the schema"""
        test_number = "14"
        test_description = "Return of /single/receivers/<uuid>/staged/ meets the schema"
        if len(self.receivers) > 0:
            for receiver in self.receivers:
                dest = "single/receivers/" + receiver + "/staged/"
                valid, msg = self.compare_to_schema("v1.0-receiver-response-schema.json", dest)
                if valid:
                    pass
                else:
                    return test_number, test_description, "Fail", msg
            return test_number, test_description, "Pass", ""
        else:
            return test_number, test_description, "N/A", "Not tested. No resources found."

    def test_15(self):
        """Staged parameters for senders comply with constraints"""
        test_number = "15"
        test_description = "Staged parameters for senders comply with constraints"
        if len(self.senders) > 0:
            valid, response = self.check_staged_complies_with_constraints("sender", self.senders)
            if valid:
                return test_number, test_description, "Pass"
            else:
                return test_number, test_description, "Fail", response
        else:
            return test_number, test_description, "N/A", "Not tested. No resources found."

    def test_16(self):
        """Staged parameters for receivers comply with constraints"""
        test_number = "16"
        test_description = "Staged parameters for receivers comply with constraints"
        if len(self.receivers) > 0:
            valid, response = self.check_staged_complies_with_constraints("receiver", self.receivers)
            if valid:
                return test_number, test_description, "Pass"
            else:
                return test_number, test_description, "Fail", response
        else:
            return test_number, test_description, "N/A", "Not tested. No resources found."

    def test_17(self):
        """Sender patch response schema is valid"""
        test_number = "17"
        test_description = "Sender patch response schema is valid"
        if len(self.senders) > 0:
            valid, response = self.check_patch_response_schema_valid("sender", self.senders)
            if valid:
                return test_number, test_description, "Pass"
            else:
                return test_number, test_description, "Fail", response
        else:
            return test_number, test_description, "N/A", "Not tested. No resources found."

    def test_18(self):
        """Receiver patch response schema is valid"""
        test_number = "18"
        test_description = "Receiver patch response schema is valid"
        if len(self.receivers) > 0:
            valid, response = self.check_patch_response_schema_valid("receiver", self.receivers)
            if valid:
                return test_number, test_description, "Pass"
            else:
                return test_number, test_description, "Fail", response
        else:
            return test_number, test_description, "N/A", "Not tested. No resources found."

    def test_19(self):
        """Sender invalid patch is refused"""
        test_number = "19"
        test_description = "Sender invalid patch is refused"
        if len(self.senders) > 0:
            valid, response = self.check_refuses_invalid_patch("sender", self.senders)
            if valid:
                return test_number, test_description, "Pass"
            else:
                return test_number, test_description, "Fail", response
        else:
            return test_number, test_description, "N/A", "Not tested. No resources found."

    def test_20(self):
        """Receiver invalid patch is refused"""
        test_number = "20"
        test_description = "Receiver invalid patch is refused"
        if len(self.receivers) > 0:
            valid, response = self.check_refuses_invalid_patch("receiver", self.receivers)
            if valid:
                return test_number, test_description, "Pass"
            else:
                return test_number, test_description, "Fail", response
        else:
            return test_number, test_description, "N/A", "Not tested. No resources found."

    def test_21(self):
        """Sender id on staged receiver is changeable"""
        test_number = "21"
        test_description = "Sender id on staged receiver is changeable"
        if len(self.receivers) > 0:
            for receiver in self.receivers:
                url = "single/receivers/" + receiver + "/staged"
                id = str(uuid.uuid4())
                data = {"sender_id": id}
                valid, response = self.checkCleanPatch(url, data)
                if valid:
                    valid2, response2 = self.checkCleanGet(url + "/")
                    if valid2:
                        try:
                            senderId = response['sender_id']
                            msg = "Failed to change sender_id at {}, expected {}, got {}".format(url, id, senderId)
                            if senderId == id:
                                pass
                            else:
                                return test_number, test_description, "Fail", msg
                        except KeyError:
                            return test_number, test_description, "Fail", "Did not find sender_id in response from {}" \
                                .format(url)
                    else:
                        return test_number, test_description, "Fail", response2
                else:
                    return test_number, test_description, "Fail", response
            return test_number, test_description, "Pass", ""
        else:
            return test_number, test_description, "N/A", "Not tested. No resources found."

    def test_22(self):
        """Receiver id on staged sender is changeable"""
        test_number = "22"
        test_description = "Receiver id on staged sender is changeable"
        if len(self.senders) > 0:
            for sender in self.senders:
                url = "single/senders/" + sender + "/staged"
                id = str(uuid.uuid4())
                data = {"receiver_id": id}
                valid, response = self.checkCleanPatch(url, data)
                if valid:
                    valid2, response2 = self.checkCleanGet(url + "/")
                    if valid2:
                        try:
                            receiverId = response['receiver_id']
                            msg = "Failed to change receiver_id at {}, expected {}, got {}".format(url, id, receiverId)
                            if receiverId == id:
                                pass
                            else:
                                return test_number, test_description, "Fail", msg
                        except KeyError:
                            return test_number, test_description, "Fail", "Did not find receiver_id in response from {}" \
                                .format(url)
                    else:
                        return test_number, test_description, "Fail", response2
                else:
                    return test_number, test_description, "Fail", response
            return test_number, test_description, "Pass", ""
        else:
            return test_number, test_description, "N/A", "Not tested. No resources found."

    def test_23(self):
        """Sender transport parameters are changeable"""
        test_number = "23"
        test_description = "Sender transport parameters are changeable"
        if len(self.senders) > 0:
            for sender in self.senders:
                valid, values = self.generate_destination_ports("sender", sender)
                if valid:
                    valid2, response2 = self.check_change_transport_param("sender", self.senders,
                                                                          "destination_port", values, sender)
                    if valid2:
                        pass
                    else:
                        return test_number, test_description, "Fail", response2
                else:
                    return test_number, test_description, "Fail", values
            return test_number, test_description, "Pass", ""
        else:
            return test_number, test_description, "N/A", "Not tested. No resources found."

    def test_24(self):
        """Receiver transport parameters are changeable"""
        test_number = "24"
        test_description = "Receiver transport parameters are changeable"
        if len(self.receivers) > 0:
            for receiver in self.receivers:
                valid, values = self.generate_destination_ports("receiver", receiver)
                if valid:
                    valid2, response2 = self.check_change_transport_param("receiver", self.receivers,
                                                                          "destination_port", values, receiver)
                    if valid2:
                        pass
                    else:
                        return test_number, test_description, "Fail", response2
                else:
                    return test_number, test_description, "Fail", values
            return test_number, test_description, "Pass", ""
        else:
            return test_number, test_description, "N/A", "Not tested. No resources found."

    def test_25(self):
        """Immediate activation of a sender is possible"""
        test_number = "25"
        test_description = "Immediate activation of a sender is possible"
        if len(self.senders) > 0:
            for sender in self.senders:
                valid, response = self.check_activation("sender", sender, self.check_perform_immediate_activation)
                if valid:
                    pass
                else:
                    return test_number, test_description, "Fail", response
            return test_number, test_description, "Pass", ""
        else:
            return test_number, test_description, "N/A", "Not tested. No resources found."

    def test_26(self):
        """Immediate activation of a receiver is possible"""
        test_number = "26"
        test_description = "Immediate activation of a receiver is possible"
        if len(self.receivers) > 0:
            for receiver in self.receivers:
                valid, response = self.check_activation("receiver", receiver, self.check_perform_immediate_activation)
                if valid:
                    pass
                else:
                    return test_number, test_description, "Fail", response
            return test_number, test_description, "Pass", ""
        else:
            return test_number, test_description, "N/A", "Not tested. No resources found."

    def test_27(self):
        """Relative activation of a sender is possible"""
        test_number = "27"
        test_description = "Relative activation of a sender is possible"
        if len(self.senders) > 0:
            for sender in self.senders:
                valid, response = self.check_activation("sender", sender, self.check_perform_relative_activation)
                if valid:
                    pass
                else:
                    return test_number, test_description, "Fail", response
            return test_number, test_description, "Pass", response
        else:
            return test_number, test_description, "N/A", "Not tested. No resources found."

    def test_28(self):
        """Relative activation of a receiver is possible"""
        test_number = "28"
        test_description = "Relative activation of a receiver is possible"
        if len(self.receivers) > 0:
            for receiver in self.receivers:
                valid, response = self.check_activation("receiver", receiver,
                                                        self.check_perform_relative_activation)
                if valid:
                    pass
                else:
                    return test_number, test_description, "Fail", response
            return test_number, test_description, "Pass", response
        else:
            return test_number, test_description, "N/A", "Not tested. No resources found."

    def test_29(self):
        """Absolute activation of a sender is possible"""
        test_number = "29"
        test_description = "Absolute activation of a sender is possible"
        if len(self.senders) > 0:
            for sender in self.senders:
                valid, response = self.check_activation("sender", sender, self.check_perform_absolute_activation)
                if valid:
                    pass
                else:
                    return test_number, test_description, "Fail", response
            return test_number, test_description, "Pass", response
        else:
            return test_number, test_description, "N/A", "Not tested. No resources found."

    def test_30(self):
        """Absolute activation of a receiver is possible"""
        test_number = "30"
        test_description = "Absolute activation of a receiver is possible"
        if len(self.receivers) > 0:
            for receiver in self.receivers:
                valid, response = self.check_activation("receiver", receiver,
                                                        self.check_perform_absolute_activation)
                if valid:
                    pass
                else:
                    return test_number, test_description, "Fail", response
            return test_number, test_description, "Pass", response
        else:
            return test_number, test_description, "N/A", "Not tested. No resources found."

    def test_31(self):
        """Sender active response schema is valid"""
        test_number = "31"
        test_description = "Sender active response schema is valid"
        if len(self.senders):
            for sender in self.senders:
                activeUrl = "single/senders/" + sender + "/active"
                valid, response = self.compare_to_schema("v1.0-sender-response-schema.json", activeUrl)
                if valid:
                    pass
                else:
                    return test_number, test_description, "Fail", response
            return test_number, test_description, "Pass", ""
        else:
            return test_number, test_description, "N/A", "Not tested. No resources found."

    def test_32(self):
        """Receiver active response schema is valid"""
        test_number = "32"
        test_description = "Receiver active response schema is valid"
        if len(self.receivers):
            for receiver in self.receivers:
                activeUrl = "single/receivers/" + receiver + "/active"
                valid, response = self.compare_to_schema("v1.0-receiver-response-schema.json", activeUrl)
                if valid:
                    pass
                else:
                    return test_number, test_description, "Fail", response
            return test_number, test_description, "Pass", ""
        else:
            return test_number, test_description, "N/A", "Not tested. No resources found."

    def test_33(self):
        """/bulk/ endpoint returns correct JSON"""
        test_number = "33"
        test_description = "/bulk/ endpoint returns correct JSON"
        url = "bulk/"
        valid, response = self.checkCleanGet(url)
        if valid:
            expected = ['senders/', 'receivers/']
            msg = "Got wrong response from {}, expected an array containing {}, got {}".format(url, expected, response)
            if expected == response:
                return test_number, test_description, "Pass", ""
            else:
                return test_number, test_description, "Fail", msg
        else:
            return test_number, test_description, "Fail", response

    def test_34(self):
        """GET on /bulk/senders returns 405"""
        test_number = "34"
        test_description = "GET on /bulk/senders returns 405"
        url = "bulk/senders"
        valid, response = self.checkCleanGet(url, 405)
        if valid:
            return test_number, test_description, "Pass", ""
        else:
            return test_number, test_description, "Fail", response

    def test_35(self):
        """GET on /bulk/receivers returns 405"""
        test_number = "35"
        test_description = "GET on /bulk/receivers returns 405"
        url = "bulk/receivers"
        valid, response = self.checkCleanGet(url, 405)
        if valid:
            return test_number, test_description, "Pass", ""
        else:
            return test_number, test_description, "Fail", response

    def test_36(self):
        """Bulk interface can be used to change destination port on all senders"""
        test_number = "36"
        test_description = "Bulk interface can be used to change destination port on all senders"
        if len(self.senders) > 0:
            valid, response = self.check_bulk_stage("sender", self.senders)
            if valid:
                return test_number, test_description, "Pass", ""
            else:
                return test_number, test_description, "Fail", response
        else:
            return test_number, test_description, "N/A", "Not tested. No resources found."

    def test_37(self):
        """Bulk interface can be used to change destination port on all receivers"""
        test_number = "37"
        test_description = "Bulk interface can be used to change destination port on all receivers"
        if len(self.receivers) > 0:
            valid, response = self.check_bulk_stage("receiver", self.receivers)
            if valid:
                return test_number, test_description, "Pass", ""
            else:
                return test_number, test_description, "Fail", response
        else:
            return test_number, test_description, "N/A", "Not tested. No resources found."

    def test_38(self):
        """Number of legs matches on constraints, staged and active endpoint for senders"""
        test_number = "38"
        test_description = "Number of legs matches on constraints, staged and active endpoint for senders"
        if len(self.senders) > 0:
            for sender in self.senders:
                url = "single/senders/{}/".format(sender)
                valid, response = self.check_num_legs(url, "sender", sender)
                if valid:
                    pass
                else:
                    return test_number, test_description, "Fail", response
            return test_number, test_description, "Pass", ""
        else:
            return test_number, test_description, "N/A", "Not tested. No resources found."

    def test_39(self):
        """Number of legs matches on constraints, staged and active endpoint for receivers"""
        test_number = "39"
        test_description = "Number of legs matches on constraints, staged and active endpoint for receivers"
        if len(self.receivers) > 0:
            for receiver in self.receivers:
                url = "single/receivers/{}/".format(receiver)
                valid, response = self.check_num_legs(url, "receiver", receiver)
                if valid:
                    pass
                else:
                    return test_number, test_description, "Fail", response
            return test_number, test_description, "Pass", ""
        else:
            return test_number, test_description, "N/A", "Not tested. No resources found."

    def check_num_legs(self, url, type, uuid):
        """Checks the number of legs present on a given sender/receiver"""
        max = 2
        min = 1
        constraintsUrl = url + "constraints/"
        stagedUrl = url + "staged/"
        activeUrl = url + "active/"
        valid1, constraints = self.checkCleanGet(constraintsUrl)
        if valid1:
            valid2, staged = self.checkCleanGet(stagedUrl)
            if valid2:
                valid3, active = self.checkCleanGet(activeUrl)
                if valid3:
                    try:
                        stagedParams = staged['transport_params']
                    except TypeError:
                        return False, "Expected an object to be returned from {}, got {}: {}".format(stagedUrl,
                                                                                                     type(staged),
                                                                                                     staged)
                    except KeyError:
                        return False, "Could not find transport params in object from {}, got {}".format(stagedUrl,
                                                                                                         staged)
                    try:
                        activeParams = active['transport_params']
                    except TypeError:
                        return False, "Expected an object to be returned from {}, got {}: {}".format(activeUrl,
                                                                                                     type(active),
                                                                                                     active)
                    except KeyError:
                        return False, "Could not find transport params in object from {}, got {}".format(activeUrl,
                                                                                                         active)
                    if len(constraints) <= max:
                        pass
                    else:
                        return False, "{} {} has too many legs".format(type, uuid)
                    if len(constraints) >= min:
                        pass
                    else:
                        return False, "{} {} has too few legs".format(type, uuid)
                    if len(constraints) == len(stagedParams):
                        pass
                    else:
                        return False, "Number of legs in constraints and staged is different for {} {}".format(type, uuid)

                    if len(constraints) == len(activeParams):
                        pass
                    else:
                        return False, "Number of legs in constraints and active is different for {} {}".format(type,
                                                                                                               uuid)

                    return True, ""
                else:
                    return False, active
            else:
                return False, staged
        else:
            return False, constraints

    def check_bulk_stage(self, port, portList):
        """Test changing staged parameters on the bulk interface"""
        url = self.url + "bulk/" + port + "s"
        data = []
        ports = {}
        for portInst in portList:
            valid, response = self.generate_destination_ports(port, portInst)
            if valid:
                ports[portInst] = response
                toAdd = {}
                toAdd['id'] = portInst
                toAdd['params'] = {}
                toAdd['params']['transport_params'] = []
                for portNum in ports[portInst]:
                    toAdd['params']['transport_params'].append({"destination_port": portNum})
                data.append(toAdd)
            else:
                return False, response
        try:
            r = requests.post(url, data=json.dumps(data), headers=HEADERS)
            msg = "Expected a 200 response from {}, got {}".format(url, r.status_code)
            if r.status_code == 200:
                pass
            else:
                return False, msg
        except requests.exceptions.RequestException as e:
            return False, str(e)

        schema = self.load_schema("v1.0-bulk-stage-confirm.json")
        resolver = RefResolver(self.file_prefix + os.path.join(os.path.dirname(__file__), "schemas") + "/",
                               schema)
        try:
            Draft4Validator(schema, resolver=resolver).validate(r.json())
        except ValidationError as e:
            return False, "Response to post at {} did not validate against schema: {}".format(url, str(e))
        except:
            return False, "Invalid JSON received {}".format(r.text)

        # Check the parameters have actually changed
        for portInst in portList:
            activeUrl = "single/" + port + "s/" + portInst + "/staged/"

            valid, response = self.checkCleanGet(activeUrl)
            if valid:
                for i in range(0, self.get_num_paths(portInst, port)):
                    try:
                        value = response['transport_params'][i]['destination_port']
                    except KeyError:
                        return False, "Could not find `destination_port` parameter at {} on leg {}, got{}".format(
                            activeUrl, i,
                            response)
                    portNum = ports[portInst][i]
                    msg = "Problem updating destination_port value in bulk update, expected {} got {}".format(portNum,
                                                                                                              value)
                    if value == portNum:
                        pass
                    else:
                        return False, msg
            else:
                return False, response
        return True, ""

    def check_staged_activation_params_default(self, port, portId):
        # Check that the staged activation parameters have returned to their default values
        stagedUrl = "single/" + port + "s/" + portId + "/staged"
        valid, response = self.checkCleanGet(stagedUrl)
        if valid:
            expected = {"mode": None, "requested_time": None, "activation_time": None}
            try:
                params = response['activation']
            except KeyError:
                return False, "Could not find a receiver_id entry in response from {}, got {}".format(stagedUrl,
                                                                                                      response)
            except TypeError:
                return False, "Expected a dict to be returned from {}, got a {}: {}".format(stagedUrl, type(response),
                                                                                            response)
            if params == expected:
                return True, ""
            else:
                msg = "Activation parameters in staged have not returned to their defaults after activation. " \
                      "Expected {}, got {}".format(
                    expected, params)
                return False, msg
        else:
            return False, response

    def check_perform_immediate_activation(self, port, portId, stagedParams):
        # Request an immediate activation
        stagedUrl = "single/" + port + "s/" + portId + "/staged"
        activeUrl = "single/" + port + "s/" + portId + "/active"
        data = {"activation": {"mode": "activate_immediate"}}
        valid, response = self.checkCleanPatch(stagedUrl, data)
        if valid:
            try:
                mode = response['activation']['mode']
                requested = response['activation']['requested_time']
                activation = response['activation']['activation_time']
            except KeyError:
                return False, "Could not find all activation entries from {}, got {}".format(stagedUrl, response)
            except TypeError:
                return False, "Expected a dict to be returned from {}, got a {}: {}".format(stagedUrl, type(response),
                                                                                            response)
            mmsg = "Unexpected mode returned: expected `activate_immediate`, got {}".format(mode)
            rmsg = "Expected null requested time for immediate activation, got {}".format(requested)
            amsg = "Expected an activation time matching the regex ^[0-9]+:[0-9]+$, but got {}".format(activation)
            if mode == "activate_immediate":
                pass
            else:
                return False, mmsg
            if requested == None:
                pass
            else:
                return False, rmsg
            try:
                if re.match("^[0-9]+:[0-9]+$", activation) is not None:
                    pass
                else:
                    return False, amsg
            except TypeError:
                return False, amsg

            valid2, response2 = self.check_staged_activation_params_default(port, portId)
            if valid2:
                # Check the values now on /active
                valid3, response3 = self.checkCleanGet(activeUrl)
                if valid3:
                    for i in range(0, self.get_num_paths(portId, port)):
                        try:
                            activePort = response3['transport_params'][i]['destination_port']
                        except KeyError:
                            return False, "Could not find active destination_port entry on leg {} from {}, got {}".format(
                                i,
                                activeUrl,
                                response3)
                        except TypeError:
                            return False, "Expected a dict to be returned from {} on leg {}, got a {}: {}".format(
                                activeUrl, i,
                                type(response3),
                                response3)
                        try:
                            stagedPort = stagedParams[i]['destination_port']
                        except KeyError:
                            return False, "Could not find staged destination_port entry on leg {} from {}, got {}".format(
                                i,
                                stagedUrl,
                                stagedParams)
                        except TypeError:
                            return False, "Expected a dict to be returned from {} on leg {}, got a {}: {}".format(
                                stagedUrl, i,
                                type(response3),
                                stagedParams)
                        msg = "Transport parameters did not transition to active during an imeddiate activation"
                        if stagedPort == activePort:
                            pass
                        else:
                            return False, msg

                    msg = "Activation mode was not set to `activate_immediate` at {} after an immediate activation".format(
                        activeUrl)
                    if response3['activation']['mode'] == "activate_immediate":
                        pass
                    else:
                        return False, msg
                else:
                    return False, response3
            else:
                return False, response2
        else:
            return False, response
        return True, ""

    def check_perform_relative_activation(self, port, portId, stagedParams):
        # Request an relative activation
        stagedUrl = "single/" + port + "s/" + portId + "/staged"
        activeUrl = "single/" + port + "s/" + portId + "/active"
        data = {"activation": {"mode": "activate_scheduled_relative", "requested_time": "0:2"}}
        valid, response = self.checkCleanPatch(stagedUrl, data, 202)
        if valid:
            try:
                mode = response['activation']['mode']
                requested = response['activation']['requested_time']
                activation = response['activation']['activation_time']
            except KeyError:
                return False, "Could not find all activation entries from {}, got {}".format(stagedUrl, response)
            except TypeError:
                return False, "Expected a dict to be returned from {}, got a {}: {}".format(stagedUrl, type(response),
                                                                                            response)
            mmsg = "Expected mode `activate_sechduled_relative` for relative activation, got {}".format(mode)
            rmsg = "Expected requested time `0:2` for relative activation, got {}".format(requested)
            amsg = "Expected activation time to match regex ^[0-9]+:[0-9]+$, got {}".format(activation)
            if mode == "activate_scheduled_relative":
                pass
            else:
                return False, mmsg
            if requested == "0:2":
                pass
            else:
                return False, rmsg
            if re.match("^[0-9]+:[0-9]+$", activation) is not None:
                pass
            else:
                return False, amsg
            time.sleep(0.2)

            retries = 0
            finished = False

            while retries < 3 and not finished:
                # Check the values now on /active
                valid2, activeParams = self.checkCleanGet(activeUrl)
                if valid2:
                    for i in range(0, self.get_num_paths(portId, port)):
                        try:
                            activePort = activeParams['transport_params'][i]['destination_port']
                        except KeyError:
                            return False, "Could not find active destination_port entry on leg {} from {}, got {}".format(i,
                                                                                                                          activeUrl,
                                                                                                                          activeParams)
                        except TypeError:
                            return False, "Expected a dict to be returned from {} on leg {}, got a {}: {}".format(activeUrl,
                                                                                                                  i,
                                                                                                                  type(
                                                                                                                      activeParams),
                                                                                                                  activeParams)
                        try:
                            stagedPort = stagedParams[i]['destination_port']
                        except KeyError:
                            return False, "Could not find staged destination_port entry on leg {} from {}, got {}".format(i,
                                                                                                                          stagedUrl,
                                                                                                                          stagedParams)
                        except TypeError:
                            return False, "Expected a dict to be returned from {} on leg {}, got a {}: {}".format(stagedUrl,
                                                                                                                  i,
                                                                                                                  type(
                                                                                                                      activeParams),
                                                                                                                  stagedParams)
                        if stagedPort == activePort:
                            finished = True
                        else:
                            retries = retries + 1
                            time.sleep(0.2)

                    if finished:
                        try:
                            if activeParams['activation']['mode'] == "activate_scheduled_relative":
                                if retries > 0:
                                    return True, "(Retries: {})".format(str(retries))
                                else:
                                    return True, ""
                            else:
                                return False, "Activation mode was not set to `activate_scheduled_relative` at {} after a relative activation".format(
                                    activeUrl)
                        except KeyError:
                            return False, "Expected 'mode' key in 'activation' object."

                else:
                    return False, activeParams
            return False, "Transport parameters did not transition to active during an relative activation (Retries: {})".format(str(retries))
        else:
            return False, response

    def check_perform_absolute_activation(self, port, portId, stagedParams):
        # request an absolute activation
        stagedUrl = "single/" + port + "s/" + portId + "/staged"
        activeUrl = "single/" + port + "s/" + portId + "/active"
        TAItime = self.getTAITime(0.1)
        data = {"activation": {"mode": "activate_scheduled_absolute", "requested_time": TAItime}}
        valid, response = self.checkCleanPatch(stagedUrl, data, 202)
        if valid:
            try:
                mode = response['activation']['mode']
                requested = response['activation']['requested_time']
                activation = response['activation']['activation_time']
            except KeyError:
                return False, "Could not find all activation entries from {}, got {}".format(stagedUrl, response)
            except TypeError:
                return False, "Expected a dict to be returned from {}, got a {}: {}".format(stagedUrl, type(response),
                                                                                            response)
            mmsg = "Expected mode `activate_sechduled_absolute` for relative activation, got {}".format(mode)
            rmsg = "Expected requested time `{}` for relative activation, got {}".format(TAItime, requested)
            amsg = "Expected activation time to match regex ^[0-9]+:[0-9]+$, got {}".format(activation)
            try:
                if response['activation']['mode'] == "activate_scheduled_absolute":
                    pass
                else:
                    return False, mmsg
            except KeyError:
                return False, "Expected 'mode' key in 'activation' object."
            try:
                if response['activation']['requested_time'] == TAItime:
                    pass
                else:
                    return False, rmsg
            except KeyError:
                return False, "Expected 'requested_time' key in 'activation' object."
            try:
                if re.match("^[0-9]+:[0-9]+$", response['activation']['activation_time']) is not None:
                    pass
                else:
                    return False, amsg
            except KeyError:
                return False, "Expected 'activation_time' key in 'activation' object."
            # Allow extra time for processing between getting time and making request
            time.sleep(1)

            retries = 0
            finished = False

            while retries < 3 and not finished:
                # Check the values now on /active
                valid2, activeParams = self.checkCleanGet(activeUrl)
                if valid2:
                    for i in range(0, self.get_num_paths(portId, port)):
                        try:
                            activePort = activeParams['transport_params'][i]['destination_port']
                        except KeyError:
                            return False, "Could not find active destination_port entry on leg {} from {}, got {}".format(i,
                                                                                                                          activeUrl,
                                                                                                                          activeParams)
                        except TypeError:
                            return False, "Expected a dict to be returned from {} on leg {}, got a {}: {}".format(activeUrl,
                                                                                                                  i,
                                                                                                                  type(
                                                                                                                      activeParams),
                                                                                                                  activeParams)
                        try:
                            stagedPort = stagedParams[i]['destination_port']
                        except KeyError:
                            return False, "Could not find staged destination_port entry on leg {} from {}, got {}".format(i,
                                                                                                                          stagedUrl,
                                                                                                                          stagedParams)
                        except TypeError:
                            return False, "Expected a dict to be returned from {} on leg {}, got a {}: {}".format(stagedUrl,
                                                                                                                  i,
                                                                                                                  type(
                                                                                                                      activeParams),
                                                                                                                  stagedParams)
                        if activePort == stagedPort:
                            finished = True
                        else:
                            retries = retries + 1
                            time.sleep(1)

                    if finished:
                        try:
                            if activeParams['activation']['mode'] == "activate_scheduled_absolute":
                                if retries > 0:
                                    return True, "(Retries: {})".format(str(retries))
                                else:
                                    return True, ""
                            else:
                                return False, "Activation mode was not set to `activate_scheduled_absolute` at {} after a absolute activation".format(
                                    activeUrl)
                        except KeyError:
                            return False, "Expected 'mode' key in 'activation' object."
                else:
                    return False, activeParams
            return False, "Transport parameters did not transition to active during an absolute activation (Retries: {})".format(str(retries))
        else:
            return False, response

    def check_activation(self, port, portId, activationMethod):
        """Checks that when an immediate activation is called staged parameters are moved
        to active and the activation is correctly displayed in the /active endpoint"""
        # Set a new destination port in staged
        valid, destinationPort = self.generate_destination_ports(port, portId)
        if valid:
            stagedUrl = "single/" + port + "s/" + portId + "/staged"
            data = {"transport_params": []}
            for i in range(0, self.get_num_paths(portId, port)):
                data['transport_params'].append({"destination_port": destinationPort[i]})
            valid2, r = self.checkCleanPatch(stagedUrl, data)
            if valid2:
                try:
                    stagedParams = r['transport_params']
                except KeyError:
                    return False, "Could not find `transport_params` entry in response from {}".format(stagedUrl)
                except TypeError:
                    return False, "Expected a dict to be returned from {}, got a {}".format(stagedUrl,
                                                                                            type(stagedParams))
                return activationMethod(port, portId, stagedParams)
            else:
                return False, r
        else:
            return False, destinationPort

    def generate_destination_ports(self, port, portId):
        """Uses a port's constraints to generate an allowable destination
        ports for it"""
        url = "single/" + port + "s/" + portId + "/constraints/"
        valid, constraints = self.checkCleanGet(url)
        if valid:
            toReturn = []
            try:
                for entry in constraints:
                    if "enum" in entry['destination_port']:
                        values = entry['destination_port']['enum']
                        toReturn.append(values[randint(0, len(values) - 1)])
                    else:
                        if "minimum" in entry['destination_port']:
                            min = entry['destination_port']['minimum']
                        else:
                            min = 5000
                        if "maximum" in entry['destination_port']:
                            max = entry['destination_port']['maximum']
                        else:
                            max = 49151
                        toReturn.append(randint(min, max))
                return True, toReturn
            except TypeError:
                return False, "Expected a dict to be returned from {}, got a {}: {}".format(url, type(constraints),
                                                                                            constraints)
        else:
            return False, constraints

    def check_change_transport_param(self, port, portList, paramName, paramValues, myPort):
        """Check that we can update a transport parameter"""
        url = "single/" + port + "s/" + myPort + "/staged"
        data = {}
        data['transport_params'] = []
        paths = self.get_num_paths(myPort, port)
        for i in range(0, paths):
            data['transport_params'].append({})
            data['transport_params'][i][paramName] = paramValues[i]
        valid, response = self.checkCleanPatch(url, data)
        if valid:
            valid2, response2 = self.checkCleanGet(url + "/")
            if valid2:
                try:
                    response3 = response2['transport_params']
                except KeyError:
                    return False, "Could not find transport_params in response from {}, got {}".format(url, response2)
                except TypeError:
                    return False, "Expected a dict to be returned from {}, got a {}: {}".format(url, type(response2),
                                                                                                response2)
                count = 0
                try:
                    for item in response3:
                        expected = paramValues[count]
                        actual = item[paramName]
                        msg = "Could not change {} parameter at {}, expected {}, got {}".format(paramName, url,
                                                                                                expected,
                                                                                                actual)
                        if actual == expected:
                            pass
                        else:
                            return False, msg
                        count = count + 1
                except TypeError:
                    return False, "Expected a dict to be returned from {}, got a {}: {}".format(url, type(response3),
                                                                                                response3)
            else:
                return False, response2
        else:
            return False, response
        return True, ""

    def check_refuses_invalid_patch(self, port, portList):
        """Check that invalid patch requests to /staged are met with an HTTP 400"""
        data = {"bad": "data"}
        for myPort in portList:
            url = "single/" + port + "s/" + myPort + "/staged"
            valid, response = self.checkCleanPatch(url, data, code=400)
            if valid:
                pass
            else:
                return False, response
        return True, ""

    def check_patch_response_schema_valid(self, port, portList):
        """Check the response to an empty patch request complies with the schema"""
        for myPort in portList:
            url = "single/" + port + "s/" + myPort + "/staged"
            data = {}
            valid, response = self.checkCleanPatch(url, data)
            if valid:
                schema = self.load_schema("v1.0-" + port + "-response-schema.json")
                resolver = RefResolver(self.file_prefix + os.path.join(os.path.dirname(__file__), "schemas") + "/",
                                       schema)
                try:
                    Draft4Validator(schema, resolver=resolver).validate(response)
                except ValidationError as e:
                    return False, "Response to empty patch to {} does not comply with schema: {}".format(url, str(e))
            else:
                return False, response
        return True, ""

    def check_staged_complies_with_constraints(self, port, portList):
        """Check that the staged endpoint is using parameters that meet
        the constents of the /constraints endpoint"""
        for myPort in portList:
            dest = "single/" + port + "s/" + myPort + "/staged/"
            valid, response = self.checkCleanGet(dest)
            if valid:
                schema = self.load_schema("v1.0_" + port + "_transport_params_rtp.json")
                resolver = RefResolver(self.file_prefix + os.path.join(os.path.dirname(__file__), "schemas") + "/",
                                       schema)
                constraints_valid, constraints_response = self.checkCleanGet("single/" + port + "s/" + myPort + "/constraints/")
                if constraints_valid:
                    count = 0
                    try:
                        for params in response['transport_params']:
                            schema.update(constraints_response[count])
                            try:
                                Draft4Validator(schema['items']['properties'], resolver=resolver).validate(params)
                            except ValidationError as e:
                                return False, "Staged endpoint does not comply with constraints in leg {}: {}".format(count,
                                                                                                                      str(
                                                                                                                          e))
                            except SchemaError as e:
                                return False, "Invalid schema resulted from combining constraints in leg {}: {}".format(
                                    count,
                                    str(e))
                            count = count + 1
                    except KeyError:
                        return False, "Expected 'tranport_params' key in constraints."
                else:
                    return False, constraints_response
            else:
                return False, response
        return True, ""

    def check_params_match(self, port, portList):
        """Generic test for checking params listed in the /constraints endpoint
        are listed in in the /staged and /active endpoints"""
        for myPort in portList:
            rDest = "single/" + port + "/" + myPort + "/constraints/"
            sDest = "single/" + port + "/" + myPort + "/staged/"
            aDest = "single/" + port + "/" + myPort + "/active/"
            r_valid, r_response = self.checkCleanGet(rDest)
            s_valid, s_response = self.checkCleanGet(sDest)
            a_valid, a_response = self.checkCleanGet(aDest)
            count = 0
            amsg = "Expected an array to be returned {} but got {}".format(rDest, r_response)
            omsg = "Expected array entries to be dictionaries at {} but got {}".format(rDest, r_response)
            # Check the response is a list
            if r_valid:
                if s_valid:
                    if a_valid:
                        if isinstance(r_response, list):
                            if len(r_response) > 0:
                                for entry in r_response:
                                    if isinstance(entry, dict):
                                        constraintParams = entry.keys()
                                        try:
                                            stagedParams = s_response['transport_params'][count].keys()
                                        except AttributeError:
                                            # Found something that we couldn't get keys from, not a dict then...
                                            return False, "Staged parameters contain non-dicts in array position {}".format(
                                                count)
                                        except KeyError:
                                            return False, "Staged parameters do not contain transport_params"
                                        try:
                                            activeParams = a_response['transport_params'][count].keys()
                                        except AttributeError:
                                            # Found something that we couldn't get keys from, not a dict then...
                                            return False, "Active parameters contain non-dicts in array position {}".format(
                                                count)
                                        except KeyError:
                                            return False, "Active parameters do not contain transport_params"
                                        smsg = "Staged parameter set does not match parameters in constraints"
                                        amsg = "Active parameter set does not match parameters in constraints"
                                        if len(r_response) == len(s_response['transport_params']):
                                            pass
                                        else:
                                            return False, "Number of legs differs between staged and constraints"

                                        if len(r_response) == len(a_response['transport_params']):
                                            pass
                                        else:
                                            return False, "Number of legs differs between active and constraints"

                                        if TestHelper.compare_json(constraintParams, stagedParams):
                                            pass
                                        else:
                                            return False, smsg

                                        if TestHelper.compare_json(constraintParams, activeParams):
                                            pass
                                        else:
                                            return False, amsg
                                        count = count + 1
                                    else:
                                        return False, omsg
                            else:
                                return False, "Not tested. No resources found."
                        else:
                            return False, amsg
                    else:
                        return False, a_response
                else:
                    return False, s_response
            else:
                return False, r_response
        return True, ""

    def get_senders(self):
        """Gets a list of the available senders on the API"""
        toReturn = []
        try:
            r = requests.get(self.url + "single/senders/")
            try:
                for value in r.json():
                    toReturn.append(value[:-1])
            except ValueError:
                pass
        except requests.exceptions.RequestException:
            pass
        return toReturn

    def get_receivers(self):
        """Gets a list of the available receivers on the API"""
        toReturn = []
        try:
            r = requests.get(self.url + "single/receivers/")
            try:
                for value in r.json():
                    toReturn.append(value[:-1])
            except ValueError:
                pass
        except requests.exceptions.RequestException:
            pass
        return toReturn

    def getTAITime(self, offset=0.0):
        """Get the current TAI time as a colon seperated string"""
        myTime = time.time() + offset
        secs = int(myTime)
        nanos = int((myTime - secs) * 1e9)
        ippTime = self.from_UTC(secs, nanos)
        return str(ippTime[0]) + ":" + str(ippTime[1])

    def from_UTC(self, secs, nanos, is_leap=False):
        leap_sec = 0
        for tbl_sec, tbl_tai_sec_minus_1 in UTC_LEAP:
            if secs >= tbl_sec:
                leap_sec = (tbl_tai_sec_minus_1 + 1) - tbl_sec
                break
        return secs + leap_sec + is_leap, nanos

    def load_schema(self, path):
        """Used to load in schemas"""
        real_path = os.path.join(os.path.dirname(__file__), SCHEMA_LOCAL, path)
        f = open(real_path, "r")
        return json.loads(f.read())

    def get_num_paths(self, port, portType):
        """Returns the number or redundant paths on a port"""
        url = self.url + "single/" + portType + "s/" + port + "/constraints/"
        try:
            r = requests.get(url)
            try:
                rjson = r.json()
                return len(rjson)
            except ValueError:
                return 0
        except requests.exceptions.RequestException:
            return 0

    def compare_to_schema(self, schema, endpoint, status_code=200):
        """Compares the response form an endpoint to a schema"""
        schema = self.load_schema(schema)
        resolver = RefResolver(self.file_prefix + os.path.join(os.path.dirname(__file__), "schemas") + "/", schema)
        valid, response = self.checkCleanGet(endpoint, status_code)
        if valid:
            try:
                Draft4Validator(schema, resolver=resolver).validate(response)
                return True, ""
            except ValidationError as e:
                return False, "Response from {} did not meet schema: {}".format(endpoint, str(e))
        else:
            return False, "Invalid response while getting data: " + response

    def checkCleanGet(self, dest, code=200):
        """Checks that JSON can be got from dest and be parsed"""
        try:
            r = requests.get(self.url + dest)
            message = "Expected status code {} from {}, got {}.".format(code, dest, r.status_code)
            if r.status_code == code:
                try:
                    return True, r.json()
                except:
                    # Failed parsing JSON
                    msg = "Failed decoding JSON from {}, got {}. Please check JSON syntax".format(
                        dest,
                        r.text
                    )
                    return False, msg
            else:
                return False, message
        except requests.exceptions.Timeout:
            return False, "Connection timeout"
        except requests.exceptions.TooManyRedirects:
            return False, "Too many redirects"
        except requests.exceptions.RequestException as e:
            return False, str(e)

    def checkCleanPatch(self, dest, data, code=200):
        """Checks a PATCH can be made and the resulting json can be parsed"""
        try:
            r = requests.patch(self.url + dest, headers=HEADERS, data=json.dumps(data))
            message = "Expected status code {} from {}, got {}.".format(code, dest, r.status_code)
            if r.status_code == code:
                try:
                    return True, r.json()
                except:
                    # Failed parsing JSON
                    msg = "Failed decoding JSON from {}, got {}. Please check JSON syntax".format(
                        dest,
                        r.text
                    )
                    return False, msg
            else:
                return False, message
        except requests.exceptions.Timeout:
            return False, "Connection timeout"
        except requests.exceptions.TooManyRedirects:
            return False, "Too many redirects"
        except requests.exceptions.RequestException as e:
            return False, str(e)
