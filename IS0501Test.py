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
import os
import re
import time
from jsonschema import ValidationError, SchemaError, RefResolver, Draft4Validator
from random import randint

import TestHelper
from TestResult import Test
from GenericTest import GenericTest


class IS0501Test(GenericTest):
    """
    Runs IS-05-01-Test
    """

    def __init__(self, base_url, apis, spec_versions, test_version, spec_path):
        GenericTest.__init__(self, base_url, apis, spec_versions, test_version, spec_path)
        self.url = self.apis["connection"]["url"]
        self.senders = self.get_senders()
        self.receivers = self.get_receivers()

    def test_01(self):
        """Api root matches the spec"""
        test = Test("Api root matches the spec")
        expected = ["single/", "bulk/"]
        dest = ""
        valid, result = self.checkCleanRequestJSON("GET", dest)
        if valid:
            msg = "Got the wrong json from {} - got {}. Please check json matches the spec, including trailing slashes" \
                .format(dest, result)
            if TestHelper.compare_json(expected, result):
                return test.PASS()
            else:
                return test.FAIL(msg)
        else:
            return test.FAIL(result)

    def test_02(self):
        """Single endpoint root matches the spec"""
        test = Test("Single endpoint root matches the spec")
        expected = ["receivers/", "senders/"]
        dest = "single/"
        valid, result = self.checkCleanRequestJSON("GET", dest)
        if valid:
            msg = "Got the wrong json from {} - got {}. Please check json matches the spec, including trailing slashes" \
                .format(dest, result)
            if TestHelper.compare_json(expected, result):
                return test.PASS()
            else:
                return test.FAIL(msg)
        else:
            return test.FAIL(result)

    def test_03(self):
        """Root of /single/senders/ matches the spec"""
        test = Test("Root of /single/senders/ matches the spec")
        dest = "single/senders/"
        valid, response = self.checkCleanRequestJSON("GET", dest)
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
                                return test.FAIL(umsg)
                        else:
                            return test.FAIL(smsg)
                    return test.PASS()
                else:
                    return test.NA("Not tested. No resources found.")
            else:
                return test.FAIL(amsg)
        else:
            return test.FAIL(response)

    def test_04(self):
        """Root of /single/receivers/ matches the spec"""
        test = Test("Root of /single/receivers/ matches the spec")
        dest = "single/receivers/"
        valid, response = self.checkCleanRequestJSON("GET", dest)
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
                                return test.FAIL(umsg)
                        else:
                            return test.FAIL(smsg)
                    return test.PASS()
                else:
                    return test.NA("Not tested. No resources found.")
            else:
                return test.FAIL(amsg)
        else:
            return test.FAIL(response)

    def test_05(self):
        """Index of /single/senders/<uuid>/ matches the spec"""
        test = Test("Index of /single/senders/<uuid>/ matches the spec")
        if len(self.senders) > 0:
            for sender in self.senders:
                dest = "single/senders/" + sender + "/"
                valid, response = self.checkCleanRequestJSON("GET", dest)
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
                        return test.FAIL(msg)
                else:
                    return test.FAIL(response)
            return test.PASS()
        else:
            return test.NA("Not tested. No resources found.")

    def test_06(self):
        """Index of /single/receivers/<uuid>/ matches the spec"""
        test = Test("Index of /single/receivers/<uuid>/ matches the spec")
        if len(self.receivers) > 0:
            for receiver in self.receivers:
                dest = "single/receivers/" + receiver + "/"
                valid, response = self.checkCleanRequestJSON("GET", dest)
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
                        return test.FAIL(msg)
                else:
                    return test.FAIL(response)
            return test.PASS()
        else:
            return test.NA("Not tested. No resources found.")

    def test_07(self):
        """Return of /single/senders/<uuid>/constraints/ meets the schema"""
        test = Test("Return of /single/senders/<uuid>/constraints/ meets the schema")
        if len(self.senders) > 0:
            for sender in self.senders:
                dest = "single/senders/" + sender + "/constraints/"
                schema = self.get_schema("connection", "GET", "/single/senders/{senderId}/constraints", 200)
                valid, msg = self.compare_to_schema(schema, dest)
                if valid:
                    pass
                else:
                    return test.FAIL(msg)
            return test.PASS()
        else:
            return test.NA("Not tested. No resources found.")

    def test_08(self):
        """Return of /single/receivers/<uuid>/constraints/ meets the schema"""
        test = Test("Return of /single/receivers/<uuid>/constraints/ meets the schema")
        if len(self.receivers) > 0:
            for receiver in self.receivers:
                dest = "single/receivers/" + receiver + "/constraints/"
                schema = self.get_schema("connection", "GET", "/single/receivers/{receiverId}/constraints", 200)
                valid, msg = self.compare_to_schema(schema, dest)
                if valid:
                    pass
                else:
                    return test.FAIL(msg)
            return test.PASS()
        else:
            return test.NA("Not tested. No resources found.")

    def test_09(self):
        """All params listed in /single/senders/<uuid>/constraints/ matches /staged/ and /active/"""
        test = Test("All params listed in /single/senders/<uuid>/constraints/ matches /staged/ and /active/")
        if len(self.senders) > 0:
            valid, response = self.check_params_match("senders", self.senders)
            if valid:
                return test.PASS()
            else:
                if "Not tested. No resources found." in response:
                    return test.NA(response)
                else:
                    return test.FAIL(response)
        else:
            return test.NA("Not tested. No resources found.")

    def test_10(self):
        """All params listed in /single/receivers/<uuid>/constraints/ matches /staged/ and /active/"""
        test = Test("All params listed in /single/receivers/<uuid>/constraints/ matches /staged/ and /active/")
        if len(self.receivers) > 0:
            valid, response = self.check_params_match("receivers", self.receivers)
            if valid:
                return test.PASS()
            else:
                if "Not tested. No resources found." in response:
                    return test.NA(response)
                else:
                    return test.FAIL(response)
        else:
            return test.NA("Not tested. No resources found.")

    def test_11(self):
        """Senders are using valid combination of parameters"""
        test = Test("Senders are using valid combination of parameters")

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
                    valid, response = self.checkCleanRequestJSON("GET", dest)
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
                                return test.FAIL("Invalid combination of parameters on constraints endpoint.")
                        else:
                            return test.FAIL("Invalid response: {}".format(response))
                    else:
                        return test.FAIL(response)
                except IndexError:
                    return test.FAIL("Expected an array from {}, got {}".format(dest, response))
                except AttributeError:
                    return test.FAIL("Expected constraints array at {} to contain dicts, got {}".format(dest, response))
            return test.PASS()
        else:
            return test.NA("Not tested. No resources found.")

    def test_12(self):
        """Receiver are using valid combination of parameters"""
        test = Test("Receiver are using valid combination of parameters")

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
                    valid, response = self.checkCleanRequestJSON("GET", dest)
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
                                return test.FAIL("Invalid combination of parameters on constraints endpoint.")
                        else:
                            return test.FAIL("Invalid response: {}".format(response))
                    else:
                        return test.FAIL(response)
                except IndexError:
                    return test.FAIL("Expected an array from {}, got {}".format(dest, response))
                except AttributeError:
                    return test.FAIL("Expected constraints array at {} to contain dicts, got {}".format(dest, response))
            return test.PASS()
        else:
            return test.NA("Not tested. No resources found.")

    def test_13(self):
        """Return of /single/senders/<uuid>/staged/ meets the schema"""
        test = Test("Return of /single/senders/<uuid>/staged/ meets the schema")
        if len(self.senders) > 0:
            for sender in self.senders:
                dest = "single/senders/" + sender + "/staged/"
                schema = self.get_schema("connection", "GET", "/single/senders/{senderId}/staged", 200)
                valid, msg = self.compare_to_schema(schema, dest)
                if valid:
                    pass
                else:
                    return test.FAIL(msg)
            return test.PASS()
        else:
            return test.NA("Not tested. No resources found.")

    def test_14(self):
        """Return of /single/receivers/<uuid>/staged/ meets the schema"""
        test = Test("Return of /single/receivers/<uuid>/staged/ meets the schema")
        if len(self.receivers) > 0:
            for receiver in self.receivers:
                dest = "single/receivers/" + receiver + "/staged/"
                schema = self.get_schema("connection", "GET", "/single/receivers/{receiverId}/staged", 200)
                valid, msg = self.compare_to_schema(schema, dest)
                if valid:
                    pass
                else:
                    return test.FAIL(msg)
            return test.PASS()
        else:
            return test.NA("Not tested. No resources found.")

    def test_15(self):
        """Staged parameters for senders comply with constraints"""
        test = Test("Staged parameters for senders comply with constraints")
        if len(self.senders) > 0:
            valid, response = self.check_staged_complies_with_constraints("sender", self.senders)
            if valid:
                return test.PASS()
            else:
                return test.FAIL(response)
        else:
            return test.NA("Not tested. No resources found.")

    def test_16(self):
        """Staged parameters for receivers comply with constraints"""
        test = Test("Staged parameters for receivers comply with constraints")
        if len(self.receivers) > 0:
            valid, response = self.check_staged_complies_with_constraints("receiver", self.receivers)
            if valid:
                return test.PASS()
            else:
                return test.FAIL(response)
        else:
            return test.NA("Not tested. No resources found.")

    def test_17(self):
        """Sender patch response schema is valid"""
        test = Test("Sender patch response schema is valid")
        if len(self.senders) > 0:
            valid, response = self.check_patch_response_schema_valid("sender", self.senders)
            if valid:
                return test.PASS()
            else:
                return test.FAIL(response)
        else:
            return test.NA("Not tested. No resources found.")

    def test_18(self):
        """Receiver patch response schema is valid"""
        test = Test("Receiver patch response schema is valid")
        if len(self.receivers) > 0:
            valid, response = self.check_patch_response_schema_valid("receiver", self.receivers)
            if valid:
                return test.PASS()
            else:
                return test.FAIL(response)
        else:
            return test.NA("Not tested. No resources found.")

    def test_19(self):
        """Sender invalid patch is refused"""
        test = Test("Sender invalid patch is refused")
        if len(self.senders) > 0:
            valid, response = self.check_refuses_invalid_patch("sender", self.senders)
            if valid:
                return test.PASS()
            else:
                return test.FAIL(response)
        else:
            return test.NA("Not tested. No resources found.")

    def test_20(self):
        """Receiver invalid patch is refused"""
        test = Test("Receiver invalid patch is refused")
        if len(self.receivers) > 0:
            valid, response = self.check_refuses_invalid_patch("receiver", self.receivers)
            if valid:
                return test.PASS()
            else:
                return test.FAIL(response)
        else:
            return test.NA("Not tested. No resources found.")

    def test_21(self):
        """Sender id on staged receiver is changeable"""
        test = Test("Sender id on staged receiver is changeable")
        if len(self.receivers) > 0:
            for receiver in self.receivers:
                url = "single/receivers/" + receiver + "/staged"
                id = str(uuid.uuid4())
                data = {"sender_id": id}
                valid, response = self.checkCleanRequestJSON("PATCH", url, data=data)
                if valid:
                    valid2, response2 = self.checkCleanRequestJSON("GET", url + "/")
                    if valid2:
                        try:
                            senderId = response['sender_id']
                            msg = "Failed to change sender_id at {}, expected {}, got {}".format(url, id, senderId)
                            if senderId == id:
                                pass
                            else:
                                return test.FAIL(msg)
                        except KeyError:
                            return test.FAIL("Did not find sender_id in response from {}".format(url))
                    else:
                        return test.FAIL(response2)
                else:
                    return test.FAIL(response)
            return test.PASS()
        else:
            return test.NA("Not tested. No resources found.")

    def test_22(self):
        """Receiver id on staged sender is changeable"""
        test = Test("Receiver id on staged sender is changeable")
        if len(self.senders) > 0:
            for sender in self.senders:
                url = "single/senders/" + sender + "/staged"
                id = str(uuid.uuid4())
                data = {"receiver_id": id}
                valid, response = self.checkCleanRequestJSON("PATCH", url, data=data)
                if valid:
                    valid2, response2 = self.checkCleanRequestJSON("GET", url + "/")
                    if valid2:
                        try:
                            receiverId = response['receiver_id']
                            msg = "Failed to change receiver_id at {}, expected {}, got {}".format(url, id, receiverId)
                            if receiverId == id:
                                pass
                            else:
                                return test.FAIL(msg)
                        except KeyError:
                            return test.FAIL("Did not find receiver_id in response from {}".format(url))
                    else:
                        return test.FAIL(response2)
                else:
                    return test.FAIL(response)
            return test.PASS()
        else:
            return test.NA("Not tested. No resources found.")

    def test_23(self):
        """Sender transport parameters are changeable"""
        test = Test("Sender transport parameters are changeable")
        if len(self.senders) > 0:
            for sender in self.senders:
                valid, values = self.generate_destination_ports("sender", sender)
                if valid:
                    valid2, response2 = self.check_change_transport_param("sender", self.senders,
                                                                          "destination_port", values, sender)
                    if valid2:
                        pass
                    else:
                        return test.FAIL(response2)
                else:
                    return test.FAIL(values)
            return test.PASS()
        else:
            return test.NA("Not tested. No resources found.")

    def test_24(self):
        """Receiver transport parameters are changeable"""
        test = Test("Receiver transport parameters are changeable")
        if len(self.receivers) > 0:
            for receiver in self.receivers:
                valid, values = self.generate_destination_ports("receiver", receiver)
                if valid:
                    valid2, response2 = self.check_change_transport_param("receiver", self.receivers,
                                                                          "destination_port", values, receiver)
                    if valid2:
                        pass
                    else:
                        return test.FAIL(response2)
                else:
                    return test.FAIL(values)
            return test.PASS()
        else:
            return test.NA("Not tested. No resources found.")

    def test_25(self):
        """Immediate activation of a sender is possible"""
        test = Test("Immediate activation of a sender is possible")
        if len(self.senders) > 0:
            for sender in self.senders:
                valid, response = self.check_activation("sender", sender, self.check_perform_immediate_activation)
                if valid:
                    pass
                else:
                    return test.FAIL(response)
            return test.PASS()
        else:
            return test.NA("Not tested. No resources found.")

    def test_26(self):
        """Immediate activation of a receiver is possible"""
        test = Test("Immediate activation of a receiver is possible")
        if len(self.receivers) > 0:
            for receiver in self.receivers:
                valid, response = self.check_activation("receiver", receiver, self.check_perform_immediate_activation)
                if valid:
                    pass
                else:
                    return test.FAIL(response)
            return test.PASS()
        else:
            return test.NA("Not tested. No resources found.")

    def test_27(self):
        """Relative activation of a sender is possible"""
        test = Test("Relative activation of a sender is possible")
        if len(self.senders) > 0:
            for sender in self.senders:
                valid, response = self.check_activation("sender", sender, self.check_perform_relative_activation)
                if valid:
                    pass
                else:
                    return test.FAIL(response)
            return test.PASS(response)
        else:
            return test.NA("Not tested. No resources found.")

    def test_28(self):
        """Relative activation of a receiver is possible"""
        test = Test("Relative activation of a receiver is possible")
        if len(self.receivers) > 0:
            for receiver in self.receivers:
                valid, response = self.check_activation("receiver", receiver,
                                                        self.check_perform_relative_activation)
                if valid:
                    pass
                else:
                    return test.FAIL(response)
            return test.PASS(response)
        else:
            return test.NA("Not tested. No resources found.")

    def test_29(self):
        """Absolute activation of a sender is possible"""
        test = Test("Absolute activation of a sender is possible")
        if len(self.senders) > 0:
            for sender in self.senders:
                valid, response = self.check_activation("sender", sender, self.check_perform_absolute_activation)
                if valid:
                    pass
                else:
                    return test.FAIL(response)
            return test.PASS(response)
        else:
            return test.NA("Not tested. No resources found.")

    def test_30(self):
        """Absolute activation of a receiver is possible"""
        test = Test("Absolute activation of a receiver is possible")
        if len(self.receivers) > 0:
            for receiver in self.receivers:
                valid, response = self.check_activation("receiver", receiver,
                                                        self.check_perform_absolute_activation)
                if valid:
                    pass
                else:
                    return test.FAIL(response)
            return test.PASS(response)
        else:
            return test.NA("Not tested. No resources found.")

    def test_31(self):
        """Sender active response schema is valid"""
        test = Test("Sender active response schema is valid")
        if len(self.senders):
            for sender in self.senders:
                activeUrl = "single/senders/" + sender + "/active"
                schema = self.get_schema("connection", "GET", "/single/senders/{senderId}/active", 200)
                valid, response = self.compare_to_schema(schema, activeUrl)
                if valid:
                    pass
                else:
                    return test.FAIL(response)
            return test.PASS()
        else:
            return test.NA("Not tested. No resources found.")

    def test_32(self):
        """Receiver active response schema is valid"""
        test = Test("Receiver active response schema is valid")
        if len(self.receivers):
            for receiver in self.receivers:
                activeUrl = "single/receivers/" + receiver + "/active"
                schema = self.get_schema("connection", "GET", "/single/receivers/{receiverId}/active", 200)
                valid, response = self.compare_to_schema(schema, activeUrl)
                if valid:
                    pass
                else:
                    return test.FAIL(response)
            return test.PASS()
        else:
            return test.NA("Not tested. No resources found.")

    def test_33(self):
        """/bulk/ endpoint returns correct JSON"""
        test = Test("/bulk/ endpoint returns correct JSON")
        url = "bulk/"
        valid, response = self.checkCleanRequestJSON("GET", url)
        if valid:
            expected = ['senders/', 'receivers/']
            msg = "Got wrong response from {}, expected an array containing {}, got {}".format(url, expected, response)
            if expected == response:
                return test.PASS()
            else:
                return test.FAIL(msg)
        else:
            return test.FAIL(response)

    def test_34(self):
        """GET on /bulk/senders returns 405"""
        test = Test("GET on /bulk/senders returns 405")
        url = "bulk/senders"
        valid, response = self.checkCleanRequestJSON("GET", url, code=405)
        if valid:
            return test.PASS()
        else:
            return test.FAIL(response)

    def test_35(self):
        """GET on /bulk/receivers returns 405"""
        test = Test("GET on /bulk/receivers returns 405")
        url = "bulk/receivers"
        valid, response = self.checkCleanRequestJSON("GET", url, code=405)
        if valid:
            return test.PASS()
        else:
            return test.FAIL(response)

    def test_36(self):
        """Bulk interface can be used to change destination port on all senders"""
        test = Test("Bulk interface can be used to change destination port on all senders")
        if len(self.senders) > 0:
            valid, response = self.check_bulk_stage("sender", self.senders)
            if valid:
                return test.PASS()
            else:
                return test.FAIL(response)
        else:
            return test.NA("Not tested. No resources found.")

    def test_37(self):
        """Bulk interface can be used to change destination port on all receivers"""
        test = Test("Bulk interface can be used to change destination port on all receivers")
        if len(self.receivers) > 0:
            valid, response = self.check_bulk_stage("receiver", self.receivers)
            if valid:
                return test.PASS()
            else:
                return test.FAIL(response)
        else:
            return test.NA("Not tested. No resources found.")

    def test_38(self):
        """Number of legs matches on constraints, staged and active endpoint for senders"""
        test = Test("Number of legs matches on constraints, staged and active endpoint for senders")
        if len(self.senders) > 0:
            for sender in self.senders:
                url = "single/senders/{}/".format(sender)
                valid, response = self.check_num_legs(url, "sender", sender)
                if valid:
                    pass
                else:
                    return test.FAIL(response)
            return test.PASS()
        else:
            return test.NA("Not tested. No resources found.")

    def test_39(self):
        """Number of legs matches on constraints, staged and active endpoint for receivers"""
        test = Test("Number of legs matches on constraints, staged and active endpoint for receivers")
        if len(self.receivers) > 0:
            for receiver in self.receivers:
                url = "single/receivers/{}/".format(receiver)
                valid, response = self.check_num_legs(url, "receiver", receiver)
                if valid:
                    pass
                else:
                    return test.FAIL(response)
            return test.PASS()
        else:
            return test.NA("Not tested. No resources found.")

    def check_num_legs(self, url, type, uuid):
        """Checks the number of legs present on a given sender/receiver"""
        max = 2
        min = 1
        constraintsUrl = url + "constraints/"
        stagedUrl = url + "staged/"
        activeUrl = url + "active/"
        valid1, constraints = self.checkCleanRequestJSON("GET", constraintsUrl)
        if valid1:
            valid2, staged = self.checkCleanRequestJSON("GET", stagedUrl)
            if valid2:
                valid3, active = self.checkCleanRequestJSON("GET", activeUrl)
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
                        return False, "Number of legs in constraints and staged is different for {} {}".format(type,
                                                                                                               uuid)

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
            r = requests.post(url, json=data)
            msg = "Expected a 200 response from {}, got {}".format(url, r.status_code)
            if r.status_code == 200:
                pass
            else:
                return False, msg
        except requests.exceptions.RequestException as e:
            return False, str(e)

        schema = self.get_schema("connection", "POST", "/bulk/" + port + "s", 200)
        try:
            Draft4Validator(schema).validate(r.json())
        except ValidationError as e:
            return False, "Response to post at {} did not validate against schema: {}".format(url, str(e))
        except:
            return False, "Invalid JSON received {}".format(r.text)

        # Check the parameters have actually changed
        for portInst in portList:
            activeUrl = "single/" + port + "s/" + portInst + "/staged/"

            valid, response = self.checkCleanRequestJSON("GET", activeUrl)
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
        valid, response = self.checkCleanRequestJSON("GET", stagedUrl)
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
                      "Expected {}, got {}".format(expected, params)
                return False, msg
        else:
            return False, response

    def check_perform_immediate_activation(self, port, portId, stagedParams):
        # Request an immediate activation
        stagedUrl = "single/" + port + "s/" + portId + "/staged"
        activeUrl = "single/" + port + "s/" + portId + "/active"
        data = {"activation": {"mode": "activate_immediate"}}
        valid, response = self.checkCleanRequestJSON("PATCH", stagedUrl, data=data)
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
            if requested is None:
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
                valid3, response3 = self.checkCleanRequestJSON("GET", activeUrl)
                if valid3:
                    for i in range(0, self.get_num_paths(portId, port)):
                        try:
                            activePort = response3['transport_params'][i]['destination_port']
                        except KeyError:
                            return False, "Could not find active destination_port entry on leg {} from {}, " \
                                          "got {}".format(i, activeUrl, response3)
                        except TypeError:
                            return False, "Expected a dict to be returned from {} on leg {}, got a {}: {}".format(
                                activeUrl, i, type(response3), response3)
                        try:
                            stagedPort = stagedParams[i]['destination_port']
                        except KeyError:
                            return False, "Could not find staged destination_port entry on leg {} from {}, " \
                                          "got {}".format(i, stagedUrl, stagedParams)
                        except TypeError:
                            return False, "Expected a dict to be returned from {} on leg {}, got a {}: {}".format(
                                stagedUrl, i, type(response3), stagedParams)
                        msg = "Transport parameters did not transition to active during an imeddiate activation"
                        if stagedPort == activePort:
                            pass
                        else:
                            return False, msg

                    msg = "Activation mode was not set to `activate_immediate` at {} " \
                          "after an immediate activation".format(activeUrl)
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
        valid, response = self.checkCleanRequestJSON("PATCH", stagedUrl, data=data, code=202)
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
                valid2, activeParams = self.checkCleanRequestJSON("GET", activeUrl)
                if valid2:
                    for i in range(0, self.get_num_paths(portId, port)):
                        try:
                            activePort = activeParams['transport_params'][i]['destination_port']
                        except KeyError:
                            return False, "Could not find active destination_port entry on leg {} from {}, " \
                                          "got {}".format(i, activeUrl, activeParams)
                        except TypeError:
                            return False, "Expected a dict to be returned from {} on leg {}, " \
                                          "got a {}: {}".format(activeUrl, i, type(activeParams), activeParams)
                        try:
                            stagedPort = stagedParams[i]['destination_port']
                        except KeyError:
                            return False, "Could not find staged destination_port entry on leg {} from {}, " \
                                          "got {}".format(i, stagedUrl, stagedParams)
                        except TypeError:
                            return False, "Expected a dict to be returned from {} on leg {}, " \
                                          "got a {}: {}".format(stagedUrl, i, type(activeParams), stagedParams)
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
                                return False, "Activation mode was not set to `activate_scheduled_relative` at {} " \
                                              "after a relative activation".format(activeUrl)
                        except KeyError:
                            return False, "Expected 'mode' key in 'activation' object."

                else:
                    return False, activeParams
            return False, "Transport parameters did not transition to active during an relative activation " \
                          "(Retries: {})".format(str(retries))
        else:
            return False, response

    def check_perform_absolute_activation(self, port, portId, stagedParams):
        # request an absolute activation
        stagedUrl = "single/" + port + "s/" + portId + "/staged"
        activeUrl = "single/" + port + "s/" + portId + "/active"
        TAItime = TestHelper.getTAITime(1)
        data = {"activation": {"mode": "activate_scheduled_absolute", "requested_time": TAItime}}
        valid, response = self.checkCleanRequestJSON("PATCH", stagedUrl, data=data, code=202)
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
            time.sleep(2)

            retries = 0
            finished = False

            while retries < 3 and not finished:
                # Check the values now on /active
                valid2, activeParams = self.checkCleanRequestJSON("GET", activeUrl)
                if valid2:
                    for i in range(0, self.get_num_paths(portId, port)):
                        try:
                            activePort = activeParams['transport_params'][i]['destination_port']
                        except KeyError:
                            return False, "Could not find active destination_port entry on leg {} from {}, " \
                                          "got {}".format(i, activeUrl, activeParams)
                        except TypeError:
                            return False, "Expected a dict to be returned from {} on leg {}, got a {}: " \
                                          "{}".format(activeUrl, i, type(activeParams), activeParams)
                        try:
                            stagedPort = stagedParams[i]['destination_port']
                        except KeyError:
                            return False, "Could not find staged destination_port entry on leg {} from {}, " \
                                          "got {}".format(i, stagedUrl, stagedParams)
                        except TypeError:
                            return False, "Expected a dict to be returned from {} on leg {}, got a {}: " \
                                          "{}".format(stagedUrl, i, type(activeParams), stagedParams)
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
                                return False, "Activation mode was not set to `activate_scheduled_absolute` at {} " \
                                              "after a absolute activation".format(activeUrl)
                        except KeyError:
                            return False, "Expected 'mode' key in 'activation' object."
                else:
                    return False, activeParams
            return False, "Transport parameters did not transition to active during an absolute activation " \
                          "(Retries: {})".format(str(retries))
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
            valid2, r = self.checkCleanRequestJSON("PATCH", stagedUrl, data=data)
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
        valid, constraints = self.checkCleanRequestJSON("GET", url)
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
        valid, response = self.checkCleanRequestJSON("PATCH", url, data=data)
        if valid:
            valid2, response2 = self.checkCleanRequestJSON("GET", url + "/")
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
            valid, response = self.checkCleanRequestJSON("PATCH", url, data=data, code=400)
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
            valid, response = self.checkCleanRequestJSON("PATCH", url, data=data)
            if valid:
                schema = self.get_schema("connection", "PATCH", "/single/" + port + "s/{" + port + "Id}/staged", 200)
                try:
                    Draft4Validator(schema).validate(response)
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
            valid, response = self.checkCleanRequestJSON("GET", dest)
            if valid:
                schema = self.load_schema("v1.0_" + port + "_transport_params_rtp.json")
                resolver = RefResolver(self.file_prefix + os.path.join(self.spec_path + '/APIs/schemas/'),
                                       schema)
                constraints_valid, constraints_response = self.checkCleanRequestJSON("GET", "single/" + port + "s/" +
                                                                                 myPort + "/constraints/")
                if constraints_valid:
                    count = 0
                    try:
                        for params in response['transport_params']:
                            schema.update(constraints_response[count])
                            try:
                                Draft4Validator(schema['items']['properties'], resolver=resolver).validate(params)
                            except ValidationError as e:
                                return False, "Staged endpoint does not comply with constraints in leg {}: " \
                                              "{}".format(count, str(e))
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
            r_valid, r_response = self.checkCleanRequestJSON("GET", rDest)
            s_valid, s_response = self.checkCleanRequestJSON("GET", sDest)
            a_valid, a_response = self.checkCleanRequestJSON("GET", aDest)
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
                                            return False, "Staged parameters contain non-dicts in array position " \
                                                          "{}".format(count)
                                        except KeyError:
                                            return False, "Staged parameters do not contain transport_params"
                                        try:
                                            activeParams = a_response['transport_params'][count].keys()
                                        except AttributeError:
                                            # Found something that we couldn't get keys from, not a dict then...
                                            return False, "Active parameters contain non-dicts in array position " \
                                                          "{}".format(count)
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
        """Compares the response from an endpoint to a schema"""
        valid, response = self.checkCleanRequest("GET", endpoint, code=status_code)
        if valid:
            return self.check_response(schema, "GET", response)
        else:
            return False, "Invalid response while getting data: " + response

    def checkCleanRequest(self, method, dest, data=None, code=200):
        """Checks a request can be made and the resulting json can be parsed"""
        status, response = self.do_request(method, self.url + dest, data)
        if not status:
            return status, response

        message = "Expected status code {} from {}, got {}.".format(code, dest, response.status_code)
        if response.status_code == code:
            return True, response
        else:
            return False, message

    def checkCleanRequestJSON(self, method, dest, data=None, code=200):
        valid, response = self.checkCleanRequest(method, dest, data, code)
        if valid:
            try:
                return True, response.json()
            except:
                # Failed parsing JSON
                return False, "Invalid JSON received"
        else:
            return valid, response
