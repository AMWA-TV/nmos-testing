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


import uuid
import os
from jsonschema import ValidationError, SchemaError, RefResolver, Draft4Validator

import TestHelper
from TestResult import Test
from GenericTest import GenericTest
from IS05Utils import IS05Utils

CONN_API_KEY = "connection"

VALID_TRANSPORTS = {
    "v1.0": ["urn:x-nmos:transport:rtp"],
    "v1.1": ["urn:x-nmos:transport:rtp",
             "urn:x-nmos:transport:mqtt",
             "urn:x-nmos:transport:websocket"]
}


class IS0501Test(GenericTest):
    """
    Runs IS-05-01-Test
    """

    def __init__(self, apis):
        # Don't auto-test /transportfile as it is permitted to generate a 404 when master_enable is false
        omit_paths = [
            "/single/senders/{senderId}/transportfile"
        ]
        GenericTest.__init__(self, apis, omit_paths)
        self.url = self.apis[CONN_API_KEY]["url"]
        self.is05_utils = IS05Utils(self.url)
        self.senders = self.is05_utils.get_senders()
        self.receivers = self.is05_utils.get_receivers()

    def test_01(self):
        """Api root matches the spec"""
        test = Test("Api root matches the spec")
        expected = ["single/", "bulk/"]
        dest = ""
        valid, result = self.is05_utils.checkCleanRequestJSON("GET", dest)
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
        valid, result = self.is05_utils.checkCleanRequestJSON("GET", dest)
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
        valid, response = self.is05_utils.checkCleanRequestJSON("GET", dest)
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
                    return test.UNCLEAR("Not tested. No resources found.")
            else:
                return test.FAIL(amsg)
        else:
            return test.FAIL(response)

    def test_04(self):
        """Root of /single/receivers/ matches the spec"""
        test = Test("Root of /single/receivers/ matches the spec")
        dest = "single/receivers/"
        valid, response = self.is05_utils.checkCleanRequestJSON("GET", dest)
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
                    return test.UNCLEAR("Not tested. No resources found.")
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
                valid, response = self.is05_utils.checkCleanRequestJSON("GET", dest)
                expected = [
                    "constraints/",
                    "staged/",
                    "active/",
                    "transportfile/"
                ]
                api = self.apis[CONN_API_KEY]
                if self.is05_utils.compare_api_version(api["version"], "v1.1") >= 0:
                    expected.append("transporttype/")
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
            return test.UNCLEAR("Not tested. No resources found.")

    def test_06(self):
        """Index of /single/receivers/<uuid>/ matches the spec"""
        test = Test("Index of /single/receivers/<uuid>/ matches the spec")
        if len(self.receivers) > 0:
            for receiver in self.receivers:
                dest = "single/receivers/" + receiver + "/"
                valid, response = self.is05_utils.checkCleanRequestJSON("GET", dest)
                expected = [
                    "constraints/",
                    "staged/",
                    "active/"
                ]
                api = self.apis[CONN_API_KEY]
                if self.is05_utils.compare_api_version(api["version"], "v1.1") >= 0:
                    expected.append("transporttype/")
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
            return test.UNCLEAR("Not tested. No resources found.")

    def test_07(self):
        """Return of /single/senders/<uuid>/constraints/ meets the schema"""
        test = Test("Return of /single/senders/<uuid>/constraints/ meets the schema")
        if len(self.senders) > 0:
            for sender in self.senders:
                dest = "single/senders/" + sender + "/constraints/"
                schema = self.get_schema(CONN_API_KEY, "GET", "/single/senders/{senderId}/constraints", 200)
                valid, msg = self.compare_to_schema(schema, dest)
                if valid:
                    pass
                else:
                    return test.FAIL(msg)
            return test.PASS()
        else:
            return test.UNCLEAR("Not tested. No resources found.")

    def test_08(self):
        """Return of /single/receivers/<uuid>/constraints/ meets the schema"""
        test = Test("Return of /single/receivers/<uuid>/constraints/ meets the schema")
        if len(self.receivers) > 0:
            for receiver in self.receivers:
                dest = "single/receivers/" + receiver + "/constraints/"
                schema = self.get_schema(CONN_API_KEY, "GET", "/single/receivers/{receiverId}/constraints", 200)
                valid, msg = self.compare_to_schema(schema, dest)
                if valid:
                    pass
                else:
                    return test.FAIL(msg)
            return test.PASS()
        else:
            return test.UNCLEAR("Not tested. No resources found.")

    def test_09(self):
        """All params listed in /single/senders/<uuid>/constraints/ matches /staged/ and /active/"""
        test = Test("All params listed in /single/senders/<uuid>/constraints/ matches /staged/ and /active/")
        if len(self.senders) > 0:
            valid, response = self.is05_utils.check_params_match("senders", self.senders)
            if valid:
                return test.PASS()
            else:
                if "Not tested. No resources found." in response:
                    return test.UNCLEAR(response)
                else:
                    return test.FAIL(response)
        else:
            return test.UNCLEAR("Not tested. No resources found.")

    def test_10(self):
        """All params listed in /single/receivers/<uuid>/constraints/ matches /staged/ and /active/"""
        test = Test("All params listed in /single/receivers/<uuid>/constraints/ matches /staged/ and /active/")
        if len(self.receivers) > 0:
            valid, response = self.is05_utils.check_params_match("receivers", self.receivers)
            if valid:
                return test.PASS()
            else:
                if "Not tested. No resources found." in response:
                    return test.UNCLEAR(response)
                else:
                    return test.FAIL(response)
        else:
            return test.UNCLEAR("Not tested. No resources found.")

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
                    valid, response = self.is05_utils.checkCleanRequestJSON("GET", dest)
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
            return test.UNCLEAR("Not tested. No resources found.")

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
                    valid, response = self.is05_utils.checkCleanRequestJSON("GET", dest)
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
            return test.UNCLEAR("Not tested. No resources found.")

    def test_13(self):
        """Return of /single/senders/<uuid>/staged/ meets the schema"""
        test = Test("Return of /single/senders/<uuid>/staged/ meets the schema")
        if len(self.senders) > 0:
            for sender in self.senders:
                dest = "single/senders/" + sender + "/staged/"
                schema = self.get_schema(CONN_API_KEY, "GET", "/single/senders/{senderId}/staged", 200)
                valid, msg = self.compare_to_schema(schema, dest)
                if valid:
                    pass
                else:
                    return test.FAIL(msg)
            return test.PASS()
        else:
            return test.UNCLEAR("Not tested. No resources found.")

    def test_14(self):
        """Return of /single/receivers/<uuid>/staged/ meets the schema"""
        test = Test("Return of /single/receivers/<uuid>/staged/ meets the schema")
        if len(self.receivers) > 0:
            for receiver in self.receivers:
                dest = "single/receivers/" + receiver + "/staged/"
                schema = self.get_schema(CONN_API_KEY, "GET", "/single/receivers/{receiverId}/staged", 200)
                valid, msg = self.compare_to_schema(schema, dest)
                if valid:
                    pass
                else:
                    return test.FAIL(msg)
            return test.PASS()
        else:
            return test.UNCLEAR("Not tested. No resources found.")

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
            return test.UNCLEAR("Not tested. No resources found.")

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
            return test.UNCLEAR("Not tested. No resources found.")

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
            return test.UNCLEAR("Not tested. No resources found.")

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
            return test.UNCLEAR("Not tested. No resources found.")

    def test_19(self):
        """Sender invalid patch is refused"""
        test = Test("Sender invalid patch is refused")
        if len(self.senders) > 0:
            valid, response = self.is05_utils.check_refuses_invalid_patch("sender", self.senders)
            if valid:
                return test.PASS()
            else:
                return test.FAIL(response)
        else:
            return test.UNCLEAR("Not tested. No resources found.")

    def test_20(self):
        """Receiver invalid patch is refused"""
        test = Test("Receiver invalid patch is refused")
        if len(self.receivers) > 0:
            valid, response = self.is05_utils.check_refuses_invalid_patch("receiver", self.receivers)
            if valid:
                return test.PASS()
            else:
                return test.FAIL(response)
        else:
            return test.UNCLEAR("Not tested. No resources found.")

    def test_21(self):
        """Sender id on staged receiver is changeable"""
        test = Test("Sender id on staged receiver is changeable")
        if len(self.receivers) > 0:
            for receiver in self.receivers:
                url = "single/receivers/" + receiver + "/staged"
                id = str(uuid.uuid4())
                data = {"sender_id": id}
                valid, response = self.is05_utils.checkCleanRequestJSON("PATCH", url, data=data)
                if valid:
                    valid2, response2 = self.is05_utils.checkCleanRequestJSON("GET", url + "/")
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
            return test.UNCLEAR("Not tested. No resources found.")

    def test_22(self):
        """Receiver id on staged sender is changeable"""
        test = Test("Receiver id on staged sender is changeable")
        if len(self.senders) > 0:
            for sender in self.senders:
                url = "single/senders/" + sender + "/staged"
                id = str(uuid.uuid4())
                data = {"receiver_id": id}
                valid, response = self.is05_utils.checkCleanRequestJSON("PATCH", url, data=data)
                if valid:
                    valid2, response2 = self.is05_utils.checkCleanRequestJSON("GET", url + "/")
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
            return test.UNCLEAR("Not tested. No resources found.")

    def test_23(self):
        """Sender transport parameters are changeable"""
        test = Test("Sender transport parameters are changeable")
        if len(self.senders) > 0:
            for sender in self.senders:
                valid, values = self.is05_utils.generate_destination_ports("sender", sender)
                if valid:
                    valid2, response2 = self.is05_utils.check_change_transport_param("sender", self.senders,
                                                                                     "destination_port", values, sender)
                    if valid2:
                        pass
                    else:
                        return test.FAIL(response2)
                else:
                    return test.FAIL(values)
            return test.PASS()
        else:
            return test.UNCLEAR("Not tested. No resources found.")

    def test_24(self):
        """Receiver transport parameters are changeable"""
        test = Test("Receiver transport parameters are changeable")
        if len(self.receivers) > 0:
            for receiver in self.receivers:
                valid, values = self.is05_utils.generate_destination_ports("receiver", receiver)
                if valid:
                    valid2, response2 = self.is05_utils.check_change_transport_param("receiver", self.receivers,
                                                                                     "destination_port", values,
                                                                                     receiver)
                    if valid2:
                        pass
                    else:
                        return test.FAIL(response2)
                else:
                    return test.FAIL(values)
            return test.PASS()
        else:
            return test.UNCLEAR("Not tested. No resources found.")

    def test_25(self):
        """Immediate activation of a sender is possible"""
        test = Test("Immediate activation of a sender is possible")
        if len(self.senders) > 0:
            for sender in self.is05_utils.sampled_list(self.senders):
                valid, response = self.is05_utils.check_activation("sender", sender,
                                                                   self.is05_utils.check_perform_immediate_activation)
                if valid:
                    pass
                else:
                    return test.FAIL(response)
            return test.PASS()
        else:
            return test.UNCLEAR("Not tested. No resources found.")

    def test_26(self):
        """Immediate activation of a receiver is possible"""
        test = Test("Immediate activation of a receiver is possible")
        if len(self.receivers) > 0:
            for receiver in self.is05_utils.sampled_list(self.receivers):
                valid, response = self.is05_utils.check_activation("receiver", receiver,
                                                                   self.is05_utils.check_perform_immediate_activation)
                if valid:
                    pass
                else:
                    return test.FAIL(response)

            return test.PASS()
        else:
            return test.UNCLEAR("Not tested. No resources found.")

    def test_27(self):
        """Relative activation of a sender is possible"""
        test = Test("Relative activation of a sender is possible")
        if len(self.senders) > 0:
            for sender in self.is05_utils.sampled_list(self.senders):
                valid, response = self.is05_utils.check_activation("sender", sender,
                                                                   self.is05_utils.check_perform_relative_activation)
                if valid:
                    pass
                else:
                    return test.FAIL(response)
            return test.PASS(response)
        else:
            return test.UNCLEAR("Not tested. No resources found.")

    def test_28(self):
        """Relative activation of a receiver is possible"""
        test = Test("Relative activation of a receiver is possible")
        if len(self.receivers) > 0:
            for receiver in self.is05_utils.sampled_list(self.receivers):
                valid, response = self.is05_utils.check_activation("receiver", receiver,
                                                                   self.is05_utils.check_perform_relative_activation)
                if valid:
                    pass
                else:
                    return test.FAIL(response)
            return test.PASS(response)
        else:
            return test.UNCLEAR("Not tested. No resources found.")

    def test_29(self):
        """Absolute activation of a sender is possible"""
        test = Test("Absolute activation of a sender is possible")
        if len(self.senders) > 0:
            for sender in self.is05_utils.sampled_list(self.senders):
                valid, response = self.is05_utils.check_activation("sender", sender,
                                                                   self.is05_utils.check_perform_absolute_activation)
                if valid:
                    pass
                else:
                    return test.FAIL(response)
            return test.PASS(response)
        else:
            return test.UNCLEAR("Not tested. No resources found.")

    def test_30(self):
        """Absolute activation of a receiver is possible"""
        test = Test("Absolute activation of a receiver is possible")
        if len(self.receivers) > 0:
            for receiver in self.is05_utils.sampled_list(self.receivers):
                valid, response = self.is05_utils.check_activation("receiver", receiver,
                                                                   self.is05_utils.check_perform_absolute_activation)
                if valid:
                    pass
                else:
                    return test.FAIL(response)
            return test.PASS(response)
        else:
            return test.UNCLEAR("Not tested. No resources found.")

    def test_31(self):
        """Sender active response schema is valid"""
        test = Test("Sender active response schema is valid")
        if len(self.senders):
            for sender in self.senders:
                activeUrl = "single/senders/" + sender + "/active"
                schema = self.get_schema(CONN_API_KEY, "GET", "/single/senders/{senderId}/active", 200)
                valid, response = self.compare_to_schema(schema, activeUrl)
                if valid:
                    pass
                else:
                    return test.FAIL(response)
            return test.PASS()
        else:
            return test.UNCLEAR("Not tested. No resources found.")

    def test_32(self):
        """Receiver active response schema is valid"""
        test = Test("Receiver active response schema is valid")
        if len(self.receivers):
            for receiver in self.receivers:
                activeUrl = "single/receivers/" + receiver + "/active"
                schema = self.get_schema(CONN_API_KEY, "GET", "/single/receivers/{receiverId}/active", 200)
                valid, response = self.compare_to_schema(schema, activeUrl)
                if valid:
                    pass
                else:
                    return test.FAIL(response)
            return test.PASS()
        else:
            return test.UNCLEAR("Not tested. No resources found.")

    def test_33(self):
        """/bulk/ endpoint returns correct JSON"""
        test = Test("/bulk/ endpoint returns correct JSON")
        url = "bulk/"
        valid, response = self.is05_utils.checkCleanRequestJSON("GET", url)
        if valid:
            expected = ['senders/', 'receivers/']
            msg = "Got wrong response from {}, expected an array containing {}, got {}".format(url, expected, response)
            if TestHelper.compare_json(expected, response):
                return test.PASS()
            else:
                return test.FAIL(msg)
        else:
            return test.FAIL(response)

    def test_34(self):
        """GET on /bulk/senders returns 405"""
        test = Test("GET on /bulk/senders returns 405")
        url = "bulk/senders"
        valid, response = self.is05_utils.checkCleanRequestJSON("GET", url, code=405)
        if valid:
            return test.PASS()
        else:
            return test.FAIL(response)

    def test_35(self):
        """GET on /bulk/receivers returns 405"""
        test = Test("GET on /bulk/receivers returns 405")
        url = "bulk/receivers"
        valid, response = self.is05_utils.checkCleanRequestJSON("GET", url, code=405)
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
            return test.UNCLEAR("Not tested. No resources found.")

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
            return test.UNCLEAR("Not tested. No resources found.")

    def test_38(self):
        """Number of legs matches on constraints, staged and active endpoint for senders"""
        test = Test("Number of legs matches on constraints, staged and active endpoint for senders")
        if len(self.senders) > 0:
            for sender in self.senders:
                url = "single/senders/{}/".format(sender)
                valid, response = self.is05_utils.check_num_legs(url, "sender", sender)
                if valid:
                    pass
                else:
                    return test.FAIL(response)
            return test.PASS()
        else:
            return test.UNCLEAR("Not tested. No resources found.")

    def test_39(self):
        """Number of legs matches on constraints, staged and active endpoint for receivers"""
        test = Test("Number of legs matches on constraints, staged and active endpoint for receivers")
        if len(self.receivers) > 0:
            for receiver in self.receivers:
                url = "single/receivers/{}/".format(receiver)
                valid, response = self.is05_utils.check_num_legs(url, "receiver", receiver)
                if valid:
                    pass
                else:
                    return test.FAIL(response)
            return test.PASS()
        else:
            return test.UNCLEAR("Not tested. No resources found.")

    def test_40(self):
        """Only valid transport types for a given API version are advertised"""
        test = Test("Only valid transport types for a given API version are advertised")
        api = self.apis[CONN_API_KEY]
        if self.is05_utils.compare_api_version(api["version"], "v1.0") == 0:
            # Ensure rtp_enabled in present in each transport_params entry to confirm it's RTP
            if len(self.senders) or len(self.receivers):
                for sender in self.senders:
                    url = "single/senders/{}/active".format(sender)
                    valid, response = self.is05_utils.checkCleanRequestJSON("GET", url)
                    if valid:
                        if "rtp_enabled" not in response["transport_params"][0]:
                            return test.FAIL("Sender {} does not appear to use the RTP transport".format(sender))
                    else:
                        return test.FAIL("Unexpected response from active resource for Sender {}".format(sender))
                for receiver in self.receivers:
                    url = "single/receivers/{}/active".format(receiver)
                    valid, response = self.is05_utils.checkCleanRequestJSON("GET", url)
                    if valid:
                        if "rtp_enabled" not in response["transport_params"][0]:
                            return test.FAIL("Receiver {} does not appear to use the RTP transport".format(receiver))
                    else:
                        return test.FAIL("Unexpected response from active resource for Receiver {}".format(receiver))
                return test.PASS()
            else:
                return test.UNCLEAR("Not tested. No resources found.")
        else:
            if len(self.senders) or len(self.receivers):
                for sender in self.senders:
                    url = "single/senders/{}/transporttype".format(sender)
                    valid, response = self.is05_utils.checkCleanRequestJSON("GET", url)
                    if valid:
                        if response not in VALID_TRANSPORTS[api["version"]]:
                            return test.FAIL("Sender {} indicates an invalid transport type of {}".format(sender,
                                                                                                          response))
                    else:
                        return test.FAIL("Unexpected response from transporttype resource for Sender {}".format(sender))
                for receiver in self.receivers:
                    url = "single/receivers/{}/transporttype".format(receiver)
                    valid, response = self.is05_utils.checkCleanRequestJSON("GET", url)
                    if valid:
                        if response not in VALID_TRANSPORTS[api["version"]]:
                            return test.FAIL("Receiver {} indicates an invalid transport type of {}".format(receiver,
                                                                                                            response))
                    else:
                        return test.FAIL("Unexpected response from transporttype resource for Receiver {}".format(receiver))
                return test.PASS()
            else:
                return test.UNCLEAR("Not tested. No resources found.")

    def check_bulk_stage(self, port, portList):
        """Test changing staged parameters on the bulk interface"""
        url = self.url + "bulk/" + port + "s"
        data = []
        ports = {}
        for portInst in portList:
            valid, response = self.is05_utils.generate_destination_ports(port, portInst)
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
        valid, r = self.do_request("POST", url, data)
        if valid:
            msg = "Expected a 200 response from {}, got {}".format(url, r.status_code)
            if r.status_code == 200:
                pass
            else:
                return False, msg
        else:
            return False, r

        schema = self.get_schema(CONN_API_KEY, "POST", "/bulk/" + port + "s", 200)
        try:
            Draft4Validator(schema).validate(r.json())
        except ValidationError as e:
            return False, "Response to post at {} did not validate against schema: {}".format(url, str(e))
        except:
            return False, "Invalid JSON received {}".format(r.text)

        # Check the parameters have actually changed
        for portInst in portList:
            activeUrl = "single/" + port + "s/" + portInst + "/staged/"

            valid, response = self.is05_utils.checkCleanRequestJSON("GET", activeUrl)
            if valid:
                for i in range(0, self.is05_utils.get_num_paths(portInst, port)):
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

    def check_patch_response_schema_valid(self, port, portList):
        """Check the response to an empty patch request complies with the schema"""
        for myPort in portList:
            url = "single/" + port + "s/" + myPort + "/staged"
            data = {}
            valid, response = self.is05_utils.checkCleanRequestJSON("PATCH", url, data=data)
            if valid:
                schema = self.get_schema(CONN_API_KEY, "PATCH", "/single/" + port + "s/{" + port + "Id}/staged", 200)
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
            valid, response = self.is05_utils.checkCleanRequestJSON("GET", dest)
            if valid:
                try:
                    schema = self.load_schema(CONN_API_KEY, port + "_transport_params_rtp.json")
                except FileNotFoundError:
                    schema = self.load_schema(CONN_API_KEY, "v1.0_" + port + "_transport_params_rtp.json")
                resolver = RefResolver(self.file_prefix + os.path.abspath(self.apis[CONN_API_KEY]["spec_path"] +
                                                                          '/APIs/schemas/') + os.sep,
                                       schema)
                constraints_valid, constraints_response = self.is05_utils.checkCleanRequestJSON("GET", "single/" +
                                                                                                port + "s/" + myPort +
                                                                                                "/constraints/")
                if constraints_valid:
                    count = 0
                    try:
                        for params in response['transport_params']:
                            try:
                                schema.update(constraints_response[count])
                            except IndexError:
                                return False, "Number of 'legs' in constraints does not match the number in " \
                                              "transport_params"
                            try:
                                Draft4Validator(schema['items'], resolver=resolver).validate(params)
                            except ValidationError as e:
                                return False, "Staged endpoint does not comply with constraints in leg {}: " \
                                              "{}".format(count, str(e))
                            except SchemaError as e:
                                return False, "Invalid schema resulted from combining constraints in leg {}: {}".format(
                                    count,
                                    str(e))
                            count = count + 1
                    except KeyError:
                        return False, "Expected 'transport_params' key in '/staged'."
                else:
                    return False, constraints_response
            else:
                return False, response
        return True, ""

    def compare_to_schema(self, schema, endpoint, status_code=200):
        """Compares the response from an endpoint to a schema"""
        valid, response = self.is05_utils.checkCleanRequest("GET", endpoint, code=status_code)
        if valid:
            return self.check_response(CONN_API_KEY, schema, "GET", response)
        else:
            return False, "Invalid response while getting data: " + response
