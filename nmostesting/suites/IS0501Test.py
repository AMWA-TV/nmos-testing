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
import subprocess
import tempfile
import os
from jsonschema import ValidationError, SchemaError

from ..GenericTest import GenericTest
from ..IS05Utils import IS05Utils
from ..TestHelper import load_resolved_schema, check_content_type

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
    def __init__(self, apis, **kwargs):
        # Don't auto-test /transportfile as it is permitted to generate a 404 when master_enable is false
        omit_paths = [
            "/single/senders/{senderId}/transportfile"
        ]
        GenericTest.__init__(self, apis, omit_paths, **kwargs)
        self.url = self.apis[CONN_API_KEY]["url"]
        self.is05_utils = IS05Utils(self.url)

    def set_up_tests(self):
        self.senders = self.is05_utils.get_senders()
        self.receivers = self.is05_utils.get_receivers()
        self.transport_types = {}
        for sender in self.senders:
            if self.is05_utils.compare_api_version(self.apis[CONN_API_KEY]["version"], "v1.1") >= 0:
                self.transport_types[sender] = self.is05_utils.get_transporttype(sender, "sender")
            else:
                self.transport_types[sender] = "urn:x-nmos:transport:rtp"
        for receiver in self.receivers:
            if self.is05_utils.compare_api_version(self.apis[CONN_API_KEY]["version"], "v1.1") >= 0:
                self.transport_types[receiver] = self.is05_utils.get_transporttype(receiver, "receiver")
            else:
                self.transport_types[receiver] = "urn:x-nmos:transport:rtp"

    def test_01(self, test):
        """API root matches the spec"""

        return test.NA("Replaced by 'auto' test")

    def test_02(self, test):
        """Single endpoint root matches the spec"""

        return test.NA("Replaced by 'auto' test")

    def test_03(self, test):
        """Root of /single/senders/ matches the spec"""

        return test.NA("Replaced by 'auto' test")

    def test_04(self, test):
        """Root of /single/receivers/ matches the spec"""

        return test.NA("Replaced by 'auto' test")

    def test_05(self, test):
        """Index of /single/senders/{senderId}/ matches the spec"""

        return test.NA("Replaced by 'auto' test")

    def test_06(self, test):
        """Index of /single/receivers/{receiverId}/ matches the spec"""

        return test.NA("Replaced by 'auto' test")

    def test_07(self, test):
        """Return of /single/senders/{senderId}/constraints/ meets the schema"""

        return test.NA("Replaced by 'auto' test")

    def test_08(self, test):
        """Return of /single/receivers/{receiverId}/constraints/ meets the schema"""

        return test.NA("Replaced by 'auto' test")

    def test_09(self, test):
        """All params listed in /single/senders/{senderId}/constraints/ matches /staged/ and /active/"""

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

    def test_09_01(self, test):
        """All params listed in /single/senders/{senderId}/active/ match their corresponding SDP files"""

        if len(self.senders) > 0:
            access_error = False
            for sender in self.senders:
                if self.transport_types[sender] == "urn:x-nmos:transport:rtp":
                    valid, response = self.is05_utils.check_sdp_matches_params(sender)
                    if not valid:
                        return test.FAIL("SDP file for Sender {} does not match the transport_params: {}"
                                         .format(sender, response))
                    elif response.status_code != 200:
                        access_error = True
            if access_error:
                return test.UNCLEAR("One or more of the tested transport files returned a 404 HTTP code. Please "
                                    "ensure 'master_enable' is set to true for all Senders and re-test.")
            return test.PASS()
        else:
            return test.UNCLEAR("Not tested. No resources found.")

    def test_10(self, test):
        """All params listed in /single/receivers/{receiverId}/constraints/ matches /staged/ and /active/"""

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

    def test_11(self, test):
        """Senders are using valid combination of parameters"""

        rtpGeneralParams = ['source_ip', 'destination_ip', 'destination_port', 'source_port', 'rtp_enabled']
        fecParams = ['fec_enabled', 'fec_destination_ip', 'fec_mode', 'fec_type',
                     'fec_block_width', 'fec_block_height', 'fec1D_destination_port',
                     'fec1D_source_port', 'fec2D_destination_port', 'fec2D_source_port']
        fecParams = fecParams + rtpGeneralParams
        rtcpParams = ['rtcp_enabled', 'rtcp_destination_ip', 'rtcp_destination_port',
                      'rtcp_source_port']
        rtpCombinedParams = rtcpParams + fecParams
        rtcpParams = rtcpParams + rtpGeneralParams
        websocketParams = ['connection_uri', 'connection_authorization']
        mqttParams = ['destination_host', 'destination_port', 'broker_topic', 'broker_protocol', 'broker_authorization',
                      'connection_status_broker_topic']

        if len(self.senders) > 0:
            for sender in self.senders:
                dest = "single/senders/" + sender + "/constraints/"
                try:
                    valid, response = self.is05_utils.checkCleanRequestJSON("GET", dest)
                    if valid:
                        if len(response) > 0 and isinstance(response[0], dict):
                            all_params = response[0].keys()
                            params = [param for param in all_params if not param.startswith("ext_")]
                            valid_params = False
                            if self.transport_types[sender] == "urn:x-nmos:transport:rtp":
                                if sorted(params) == sorted(rtpGeneralParams) or \
                                   sorted(params) == sorted(fecParams) or \
                                   sorted(params) == sorted(rtcpParams) or \
                                   sorted(params) == sorted(rtpCombinedParams):
                                    valid_params = True
                            elif self.transport_types[sender] == "urn:x-nmos:transport:websocket":
                                if sorted(params) == sorted(websocketParams):
                                    valid_params = True
                            elif self.transport_types[sender] == "urn:x-nmos:transport:mqtt":
                                if sorted(params) == sorted(mqttParams):
                                    valid_params = True
                            if not valid_params:
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

    def test_11_01(self, test):
        """Sender /active parameters do not use the keyword 'auto'"""
        if len(self.senders) > 0:
            for sender in self.senders:
                dest = "single/senders/" + sender + "/active/"
                valid, response = self.is05_utils.checkCleanRequestJSON("GET", dest)
                if valid:
                    for leg in response["transport_params"]:
                        if "auto" in leg.values():
                            return test.FAIL("Found keyword 'auto' in one or more 'active' parameters for Sender {}"
                                             .format(sender))
                else:
                    return test.FAIL(response)
            return test.PASS()
        else:
            return test.UNCLEAR("Not tested. No resources found.")

    def test_11_02(self, test):
        """Patched 'auto' values are translated on '/active' endpoint for all senders"""
        rtpGeneralAutoParams = [
            'source_ip',
            'destination_ip',
            'source_port',
            'destination_port'
        ]
        fecAutoParams = [
            'fec_destination_ip',
            'fec1D_destination_port',
            'fec2D_destination_port',
            'fec1D_source_port',
            'fec2D_source_port'
        ]
        rtcpAutoParams = [
            'rtcp_destination_ip',
            'rtcp_destination_port',
            'rtcp_source_port'
        ]
        rtpAutoParams = rtpGeneralAutoParams + fecAutoParams + rtcpAutoParams
        websocketAutoParams = [
            'connection_uri',
            'connection_authorization'
        ]
        mqttAutoParams = [
            'destination_host',
            'destination_port',
            'broker_protocol',
            'broker_authorization'
        ]
        autoParams = rtpAutoParams + websocketAutoParams + mqttAutoParams
        return self.patch_auto_params(test, self.senders, "senders", autoParams)

    def test_12(self, test):
        """Receiver are using valid combination of parameters"""

        rtpGeneralParams = ['source_ip', 'multicast_ip', 'interface_ip', 'destination_port', 'rtp_enabled']
        fecParams = ['fec_enabled', 'fec_destination_ip', 'fec_mode',
                     'fec1D_destination_port', 'fec2D_destination_port']
        fecParams = fecParams + rtpGeneralParams
        rtcpParams = ['rtcp_enabled', 'rtcp_destination_ip', 'rtcp_destination_port']
        rtpCombinedParams = rtcpParams + fecParams
        rtcpParams = rtcpParams + rtpGeneralParams
        websocketParams = ['connection_uri', 'connection_authorization']
        mqttParams = ['source_host', 'source_port', 'broker_topic', 'broker_protocol', 'broker_authorization',
                      'connection_status_broker_topic']

        if len(self.receivers) > 0:
            for receiver in self.receivers:
                dest = "single/receivers/" + receiver + "/constraints/"
                try:
                    valid, response = self.is05_utils.checkCleanRequestJSON("GET", dest)
                    if valid:
                        if len(response) > 0 and isinstance(response[0], dict):
                            all_params = response[0].keys()
                            params = [param for param in all_params if not param.startswith("ext_")]
                            valid_params = False
                            if self.transport_types[receiver] == "urn:x-nmos:transport:rtp":
                                if sorted(params) == sorted(rtpGeneralParams) or \
                                   sorted(params) == sorted(fecParams) or \
                                   sorted(params) == sorted(rtcpParams) or \
                                   sorted(params) == sorted(rtpCombinedParams):
                                    valid_params = True
                            elif self.transport_types[receiver] == "urn:x-nmos:transport:websocket":
                                if sorted(params) == sorted(websocketParams):
                                    valid_params = True
                            elif self.transport_types[receiver] == "urn:x-nmos:transport:mqtt":
                                if sorted(params) == sorted(mqttParams):
                                    valid_params = True
                            if not valid_params:
                                return test.FAIL("Invalid combination of parameters on constraints endpoint.")
                        else:
                            return test.FAIL("Invalid response: {}".format(response))
                    else:
                        return test.FAIL(response)
                except IndexError:
                    return test.FAIL("Expected an array from {}, got {}".format(dest, response))
                except AttributeError:
                    return test.FAIL("Expected constraints array at {} to contain dicts, got {}"
                                     .format(dest, response))
            return test.PASS()
        else:
            return test.UNCLEAR("Not tested. No resources found.")

    def test_12_01(self, test):
        """Receiver /active parameters do not use the keyword 'auto'"""
        if len(self.receivers) > 0:
            for receiver in self.receivers:
                dest = "single/receivers/" + receiver + "/active/"
                valid, response = self.is05_utils.checkCleanRequestJSON("GET", dest)
                if valid:
                    for leg in response["transport_params"]:
                        if "auto" in leg.values():
                            return test.FAIL("Found keyword 'auto' in one or more 'active' parameters for Receiver {}"
                                             .format(receiver))
                else:
                    return test.FAIL(response)
            return test.PASS()
        else:
            return test.UNCLEAR("Not tested. No resources found.")

    def test_12_02(self, test):
        """Patched 'auto' values are translated on '/active' endpoint for all receivers"""
        rtpGeneralAutoParams = [
            'interface_ip',
            'destination_port'
        ]
        fecAutoParams = [
            'fec_destination_ip',
            'fec_mode',
            'fec1D_destination_port',
            'fec2D_destination_port'
        ]
        rtcpAutoParams = [
            'rtcp_destination_ip',
            'rtcp_destination_port'
        ]
        rtpAutoParams = rtpGeneralAutoParams + fecAutoParams + rtcpAutoParams
        websocketAutoParams = [
            'connection_authorization'
        ]
        mqttAutoParams = [
            'source_host',
            'source_port',
            'broker_protocol',
            'broker_authorization'
        ]
        autoParams = rtpAutoParams + websocketAutoParams + mqttAutoParams
        return self.patch_auto_params(test, self.receivers, "receivers", autoParams)

    def test_13(self, test):
        """Return of /single/senders/{senderId}/staged/ meets the schema"""

        if len(self.senders) > 0:
            warn = ""
            for sender in self.senders:
                dest = "single/senders/" + sender + "/staged/"
                schema = self.get_schema(CONN_API_KEY, "GET", "/single/senders/{senderId}/staged", 200)
                valid, msg = self.compare_to_schema(schema, dest)
                if valid:
                    if msg and not warn:
                        warn = msg
                else:
                    return test.FAIL(msg)
            if warn:
                return test.WARNING(warn)
            else:
                return test.PASS()
        else:
            return test.UNCLEAR("Not tested. No resources found.")

    def test_14(self, test):
        """Return of /single/receivers/{receiverId}/staged/ meets the schema"""

        if len(self.receivers) > 0:
            warn = ""
            for receiver in self.receivers:
                dest = "single/receivers/" + receiver + "/staged/"
                schema = self.get_schema(CONN_API_KEY, "GET", "/single/receivers/{receiverId}/staged", 200)
                valid, msg = self.compare_to_schema(schema, dest)
                if valid:
                    if msg and not warn:
                        warn = msg
                else:
                    return test.FAIL(msg)
            if warn:
                return test.WARNING(warn)
            else:
                return test.PASS()
        else:
            return test.UNCLEAR("Not tested. No resources found.")

    def test_15(self, test):
        """Staged parameters for senders comply with constraints"""

        if len(self.senders) > 0:
            valid, response = self.check_staged_complies_with_constraints("sender", self.senders)
            if valid:
                return test.PASS()
            else:
                return test.FAIL(response)
        else:
            return test.UNCLEAR("Not tested. No resources found.")

    def test_16(self, test):
        """Staged parameters for receivers comply with constraints"""

        if len(self.receivers) > 0:
            valid, response = self.check_staged_complies_with_constraints("receiver", self.receivers)
            if valid:
                return test.PASS()
            else:
                return test.FAIL(response)
        else:
            return test.UNCLEAR("Not tested. No resources found.")

    def test_17(self, test):
        """Sender patch response meets the schema"""

        if len(self.senders) > 0:
            valid, response = self.check_patch_response_valid("sender", self.senders)
            if valid:
                return test.PASS()
            else:
                return test.FAIL(response)
        else:
            return test.UNCLEAR("Not tested. No resources found.")

    def test_18(self, test):
        """Receiver patch response meets the schema"""

        if len(self.receivers) > 0:
            valid, response = self.check_patch_response_valid("receiver", self.receivers)
            if valid:
                return test.PASS()
            else:
                return test.FAIL(response)
        else:
            return test.UNCLEAR("Not tested. No resources found.")

    def test_19(self, test):
        """Sender invalid patch is refused"""

        if len(self.senders) > 0:
            valid, response = self.is05_utils.check_refuses_invalid_patch("sender", self.senders)
            if valid:
                return test.PASS()
            else:
                return test.FAIL(response)
        else:
            return test.UNCLEAR("Not tested. No resources found.")

    def test_20(self, test):
        """Receiver invalid patch is refused"""

        if len(self.receivers) > 0:
            valid, response = self.is05_utils.check_refuses_invalid_patch("receiver", self.receivers)
            if valid:
                return test.PASS()
            else:
                return test.FAIL(response)
        else:
            return test.UNCLEAR("Not tested. No resources found.")

    def test_21(self, test):
        """Sender id on staged receiver is changeable"""

        if len(self.receivers) > 0:
            for receiver in self.receivers:
                url = "single/receivers/" + receiver + "/staged"
                for id in [str(uuid.uuid4()), None]:
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

    def test_22(self, test):
        """Receiver id on staged sender is changeable"""

        if len(self.senders) > 0:
            for sender in self.senders:
                url = "single/senders/" + sender + "/staged"
                for id in [str(uuid.uuid4()), None]:
                    data = {"receiver_id": id}
                    valid, response = self.is05_utils.checkCleanRequestJSON("PATCH", url, data=data)
                    if valid:
                        valid2, response2 = self.is05_utils.checkCleanRequestJSON("GET", url + "/")
                        if valid2:
                            try:
                                receiverId = response['receiver_id']
                                msg = "Failed to change receiver_id at {}, expected {}, got {}".format(url,
                                                                                                       id,
                                                                                                       receiverId)
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

    def test_23(self, test):
        """Sender transport parameters are changeable"""

        if len(self.senders) > 0:
            for sender in self.senders:
                valid, values = self.is05_utils.generate_changeable_param("sender", sender,
                                                                          self.transport_types[sender])
                paramName = self.is05_utils.changeable_param_name(self.transport_types[sender])
                if valid:
                    valid2, response2 = self.is05_utils.check_change_transport_param("sender", self.senders,
                                                                                     paramName, values, sender)
                    if valid2:
                        pass
                    else:
                        return test.FAIL(response2)
                else:
                    return test.FAIL(values)
            return test.PASS()
        else:
            return test.UNCLEAR("Not tested. No resources found.")

    def test_23_01(self, test):
        """Senders accept a patch request with empty leg(s) in transport parameters"""

        if len(self.senders) > 0:
            valid, response = self.check_patch_empty_transport_params("sender", self.senders)
            if valid:
                return test.PASS()
            else:
                return test.FAIL(response)
        else:
            return test.UNCLEAR("Not tested. No resources found.")

    def test_24(self, test):
        """Receiver transport parameters are changeable"""

        if len(self.receivers) > 0:
            for receiver in self.receivers:
                valid, values = self.is05_utils.generate_changeable_param("receiver", receiver,
                                                                          self.transport_types[receiver])
                paramName = self.is05_utils.changeable_param_name(self.transport_types[receiver])
                if valid:
                    valid2, response2 = self.is05_utils.check_change_transport_param("receiver", self.receivers,
                                                                                     paramName, values, receiver)
                    if valid2:
                        pass
                    else:
                        return test.FAIL(response2)
                else:
                    return test.FAIL(values)
            return test.PASS()
        else:
            return test.UNCLEAR("Not tested. No resources found.")

    def test_24_01(self, test):
        """Receivers accept a patch request with empty leg(s) in transport parameters"""

        if len(self.receivers) > 0:
            valid, response = self.check_patch_empty_transport_params("receiver", self.receivers)
            if valid:
                return test.PASS()
            else:
                return test.FAIL(response)
        else:
            return test.UNCLEAR("Not tested. No resources found.")

    def test_25(self, test):
        """Immediate activation of a sender is possible"""

        if len(self.senders) > 0:
            warn = ""
            for sender in self.is05_utils.sampled_list(self.senders):
                valid, response = self.is05_utils.check_activation("sender", sender,
                                                                   self.is05_utils.check_perform_immediate_activation,
                                                                   self.transport_types[sender],
                                                                   True)
                if valid:
                    if response and not warn:
                        warn = response
                    if self.transport_types[sender] == "urn:x-nmos:transport:rtp":
                        valid2, response2 = self.is05_utils.check_sdp_matches_params(sender)
                        if not valid2 or response2.status_code != 200:
                            return test.FAIL("SDP file for Sender {} does not match the transport_params: {}"
                                             .format(sender, response2))
                else:
                    return test.FAIL(response)
            if warn:
                return test.WARNING(warn)
            else:
                return test.PASS()
        else:
            return test.UNCLEAR("Not tested. No resources found.")

    def test_26(self, test):
        """Immediate activation of a receiver is possible"""

        if len(self.receivers) > 0:
            warn = ""
            for receiver in self.is05_utils.sampled_list(self.receivers):
                valid, response = self.is05_utils.check_activation("receiver", receiver,
                                                                   self.is05_utils.check_perform_immediate_activation,
                                                                   self.transport_types[receiver])
                if valid:
                    if response and not warn:
                        warn = response
                else:
                    return test.FAIL(response)
            if warn:
                return test.WARNING(warn)
            else:
                return test.PASS()
        else:
            return test.UNCLEAR("Not tested. No resources found.")

    def test_27(self, test):
        """Relative activation of a sender is possible"""

        if len(self.senders) > 0:
            warn = ""
            for sender in self.is05_utils.sampled_list(self.senders):
                valid, response = self.is05_utils.check_activation("sender", sender,
                                                                   self.is05_utils.check_perform_relative_activation,
                                                                   self.transport_types[sender],
                                                                   True)
                if valid:
                    if response and not warn:
                        warn = response
                    if self.transport_types[sender] == "urn:x-nmos:transport:rtp":
                        valid2, response2 = self.is05_utils.check_sdp_matches_params(sender)
                        if not valid2 or response2.status_code != 200:
                            return test.FAIL("SDP file for Sender {} does not match the transport_params: {}"
                                             .format(sender, response2))
                else:
                    return test.FAIL(response)
            if warn:
                return test.WARNING(warn)
            else:
                return test.PASS()
        else:
            return test.UNCLEAR("Not tested. No resources found.")

    def test_28(self, test):
        """Relative activation of a receiver is possible"""

        if len(self.receivers) > 0:
            warn = ""
            for receiver in self.is05_utils.sampled_list(self.receivers):
                valid, response = self.is05_utils.check_activation("receiver", receiver,
                                                                   self.is05_utils.check_perform_relative_activation,
                                                                   self.transport_types[receiver])
                if valid:
                    if response and not warn:
                        warn = response
                else:
                    return test.FAIL(response)
            if warn:
                return test.WARNING(warn)
            else:
                return test.PASS()
        else:
            return test.UNCLEAR("Not tested. No resources found.")

    def test_29(self, test):
        """Absolute activation of a sender is possible"""

        if len(self.senders) > 0:
            warn = ""
            for sender in self.is05_utils.sampled_list(self.senders):
                valid, response = self.is05_utils.check_activation("sender", sender,
                                                                   self.is05_utils.check_perform_absolute_activation,
                                                                   self.transport_types[sender],
                                                                   True)
                if valid:
                    if response and not warn:
                        warn = response
                    if self.transport_types[sender] == "urn:x-nmos:transport:rtp":
                        valid2, response2 = self.is05_utils.check_sdp_matches_params(sender)
                        if not valid2 or response2.status_code != 200:
                            return test.FAIL("SDP file for Sender {} does not match the transport_params: {}"
                                             .format(sender, response2))
                else:
                    return test.FAIL(response)
            if warn:
                return test.WARNING(warn)
            else:
                return test.PASS()
        else:
            return test.UNCLEAR("Not tested. No resources found.")

    def test_30(self, test):
        """Absolute activation of a receiver is possible"""

        if len(self.receivers) > 0:
            warn = ""
            for receiver in self.is05_utils.sampled_list(self.receivers):
                valid, response = self.is05_utils.check_activation("receiver", receiver,
                                                                   self.is05_utils.check_perform_absolute_activation,
                                                                   self.transport_types[receiver])
                if valid:
                    if response and not warn:
                        warn = response
                else:
                    return test.FAIL(response)
            if warn:
                return test.WARNING(warn)
            else:
                return test.PASS()
        else:
            return test.UNCLEAR("Not tested. No resources found.")

    def test_31(self, test):
        """Sender active response schema is valid"""

        if len(self.senders):
            warn = ""
            for sender in self.senders:
                activeUrl = "single/senders/" + sender + "/active"
                schema = self.get_schema(CONN_API_KEY, "GET", "/single/senders/{senderId}/active", 200)
                valid, msg = self.compare_to_schema(schema, activeUrl)
                if valid:
                    if msg and not warn:
                        warn = msg
                else:
                    return test.FAIL(msg)
            if warn:
                return test.WARNING(warn)
            else:
                return test.PASS()
        else:
            return test.UNCLEAR("Not tested. No resources found.")

    def test_32(self, test):
        """Receiver active response schema is valid"""

        if len(self.receivers):
            warn = ""
            for receiver in self.receivers:
                activeUrl = "single/receivers/" + receiver + "/active"
                schema = self.get_schema(CONN_API_KEY, "GET", "/single/receivers/{receiverId}/active", 200)
                valid, msg = self.compare_to_schema(schema, activeUrl)
                if valid:
                    if msg and not warn:
                        warn = msg
                else:
                    return test.FAIL(msg)
            if warn:
                return test.WARNING(warn)
            else:
                return test.PASS()
        else:
            return test.UNCLEAR("Not tested. No resources found.")

    def test_33(self, test):
        """/bulk/ endpoint returns correct JSON"""

        return test.NA("Replaced by 'auto' test")

    def test_34(self, test):
        """GET on /bulk/senders returns 405"""

        url = "bulk/senders"
        error_code = 405
        valid, response = self.is05_utils.checkCleanRequest("GET", url, codes=[error_code])
        if valid:
            valid, message = self.check_error_response("GET", response, error_code)
            if valid:
                return test.PASS()
            else:
                return test.FAIL(message)
        else:
            return test.FAIL(response)

    def test_35(self, test):
        """GET on /bulk/receivers returns 405"""

        url = "bulk/receivers"
        error_code = 405
        valid, response = self.is05_utils.checkCleanRequest("GET", url, codes=[error_code])
        if valid:
            valid, message = self.check_error_response("GET", response, error_code)
            if valid:
                return test.PASS()
            else:
                return test.FAIL(message)
        else:
            return test.FAIL(response)

    def test_36(self, test):
        """Bulk interface can be used to change destination port on all senders"""

        if len(self.senders) > 0:
            valid, response = self.check_bulk_stage("sender", self.senders)
            if valid:
                return test.PASS()
            else:
                return test.FAIL(response)
        else:
            return test.UNCLEAR("Not tested. No resources found.")

    def test_37(self, test):
        """Bulk interface can be used to change destination port on all receivers"""

        if len(self.receivers) > 0:
            valid, response = self.check_bulk_stage("receiver", self.receivers)
            if valid:
                return test.PASS()
            else:
                return test.FAIL(response)
        else:
            return test.UNCLEAR("Not tested. No resources found.")

    def test_38(self, test):
        """Number of legs matches on constraints, staged and active endpoint for senders"""

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

    def test_39(self, test):
        """Number of legs matches on constraints, staged and active endpoint for receivers"""

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

    def test_40(self, test):
        """Only valid transport types for a given API version are advertised"""

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
                    if self.transport_types[sender] not in VALID_TRANSPORTS[api["version"]]:
                        return test.FAIL("Sender {} indicates an invalid transport type of {}"
                                         .format(sender, self.transport_types[sender]))
                for receiver in self.receivers:
                    if self.transport_types[receiver] not in VALID_TRANSPORTS[api["version"]]:
                        return test.FAIL("Receiver {} indicates an invalid transport type of {}"
                                         .format(receiver, self.transport_types[receiver]))
                return test.PASS()
            else:
                return test.UNCLEAR("Not tested. No resources found.")

    def test_41(self, test):
        """SDP transport files pass SDPoker tests"""

        rtp_senders = []
        dup_senders = []
        for sender in self.senders:
            if self.transport_types[sender] == "urn:x-nmos:transport:rtp":
                rtp_senders.append(sender)
                # Check whether this sender uses stream duplication
                url = "single/senders/{}/active".format(sender)
                valid, response = self.is05_utils.checkCleanRequestJSON("GET", url)
                if valid:
                    try:
                        if len(response["transport_params"]) == 2:
                            dup_senders.append(sender)
                    except (KeyError, TypeError):
                        return test.FAIL("Unable to identify 'transport_params' from IS-05 active resource for Sender "
                                         "{}".format(sender))
                else:
                    return test.FAIL("Unable to identify 'transport_params' from IS-05 active resource for Sender {}"
                                     .format(sender))

        if len(rtp_senders) == 0:
            return test.UNCLEAR("Not tested. No resources found.")

        # Check SDPoker version
        sdpoker_min_version = "0.3.0"
        try:
            cmd_string = "sdpoker --version"
            output = subprocess.check_output(cmd_string, stderr=subprocess.STDOUT, shell=True)
            running_ver = output.decode("utf-8").split(".")
            expected_ver = sdpoker_min_version.split(".")
            if (running_ver[0] < expected_ver[0] or
                    (running_ver[0] == expected_ver[0] and running_ver[1] < expected_ver[1]) or
                    (running_ver[0] == expected_ver[0] and running_ver[1] == expected_ver[1] and
                        running_ver[2] < expected_ver[2])):
                return test.FAIL("SDPoker version is too old. Please update to version {}".format(sdpoker_min_version))
        except (subprocess.CalledProcessError, IndexError):
            return test.DISABLED("SDPoker may be unavailable on this system. Please see the README for "
                                 "installation instructions.")

        # First pass to check for errors
        access_error = False

        sdp_files = {}
        try:
            # Download SDP files
            for sender in rtp_senders:
                path = "single/senders/{}/transportfile".format(sender)
                url = self.url + path
                valid, response = self.do_request("GET", url)
                if valid and response.status_code == 200:
                    file, temp_path = tempfile.mkstemp()
                    for chunk in response.iter_content(chunk_size=128):
                        os.write(file, chunk)
                    os.close(file)
                    sdp_files[sender] = temp_path
                elif valid and response.status_code == 404:
                    access_error = True
                else:
                    return test.FAIL("Unexpected response from Connection API "
                                     "downloading SDP file for Sender {}: {}".format(sender, response))

            for sender in sdp_files:
                dup_params = ""
                if sender in dup_senders:
                    dup_params = " --duplicate true"
                try:
                    cmd_string = "sdpoker --shaping true{} {}".format(dup_params, sdp_files[sender])
                    output = subprocess.check_output(cmd_string, stderr=subprocess.STDOUT, shell=True)
                    decoded_output = output.decode("utf-8")
                    if "Error" in decoded_output:
                        # This case exits with a zero error code so can't be handled in the exception
                        # These usually start with "{ StatusCodeError:" or "Error:"
                        return test.FAIL("SDPoker error for Sender {} transport file: {}"
                                         .format(sender, decoded_output))
                except subprocess.CalledProcessError as e:
                    output = str(e.output, "utf-8")
                    return test.FAIL("SDPoker error for Sender {} transport file: {}".format(sender, output))

            # Second pass to check for warnings
            for sender in sdp_files:
                dup_params = ""
                if sender in dup_senders:
                    dup_params = " --duplicate true"
                try:
                    cmd_string = "sdpoker --shaping true --whitespace true --should true " \
                                "--checkEndings true{} {}".format(dup_params, sdp_files[sender])
                    output = subprocess.check_output(cmd_string, stderr=subprocess.STDOUT, shell=True)
                    decoded_output = output.decode("utf-8")
                    if "Error" in decoded_output:
                        # This case exits with a zero error code so can't be handled in the exception
                        # These usually start with "{ StatusCodeError:" or "Error:"
                        return test.FAIL("SDPoker error for Sender {} transport file: {}"
                                         .format(sender, decoded_output))
                except subprocess.CalledProcessError as e:
                    output = str(e.output, "utf-8")
                    return test.WARNING("SDPoker warning for Sender {} transport file: {}".format(sender, output))

            if access_error:
                return test.UNCLEAR("One or more of the tested transport files returned a 404 HTTP code. Please "
                                    "ensure 'master_enable' is set to true for all Senders and re-test.")

        finally:
            for sender in sdp_files:
                os.remove(sdp_files[sender])

        return test.PASS()

    def test_42(self, test):
        """Transport files use the expected Content-Type"""

        access_error = False
        for sender in self.senders:
            if self.transport_types[sender] == "urn:x-nmos:transport:rtp":
                url = self.url + "single/senders/{}/transportfile".format(sender)
                valid, response = self.do_request("GET", url)
                if valid and response.status_code == 200:
                    valid, message = check_content_type(response.headers, ["application/sdp"])
                    if valid and message != "":
                        return test.FAIL(message)
                    elif not valid:
                        return test.WARNING(message)
                elif valid and response.status_code == 404:
                    access_error = True
                else:
                    return test.FAIL("Unexpected response from Connection API")

        if len(self.senders) == 0:
            return test.UNCLEAR("Not tested. No resources found.")

        if access_error:
            return test.UNCLEAR("One or more of the tested transport files returned a 404 HTTP code. Please "
                                "ensure 'master_enable' is set to true for all Senders and re-test.")

        return test.PASS()

    def check_bulk_stage(self, port, portList):
        """Test changing staged parameters on the bulk interface"""
        url = self.url + "bulk/" + port + "s"
        data = []
        ports = {}
        for portInst in portList:
            valid, response = self.is05_utils.generate_changeable_param(port, portInst, self.transport_types[portInst])
            paramName = self.is05_utils.changeable_param_name(self.transport_types[portInst])
            if valid:
                ports[portInst] = response
                toAdd = {}
                toAdd['id'] = portInst
                toAdd['params'] = {}
                toAdd['params']['transport_params'] = []
                for portNum in ports[portInst]:
                    toAdd['params']['transport_params'].append({paramName: portNum})
                if len(toAdd["params"]["transport_params"]) == 0:
                    del toAdd["params"]["transport_params"]
                data.append(toAdd)
            else:
                return False, response
        valid, r = self.do_request("POST", url, json=data)
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
            self.validate_schema(r.json(), schema)
        except ValidationError as e:
            return False, "Response to post at {} did not validate against schema: {}".format(url, str(e))
        except Exception:
            return False, "Invalid JSON received {}".format(r.text)

        # Check the parameters have actually changed
        for portInst in portList:
            paramName = self.is05_utils.changeable_param_name(self.transport_types[portInst])
            url = "single/" + port + "s/" + portInst + "/staged/"

            valid, response = self.is05_utils.checkCleanRequestJSON("GET", url)
            if valid:
                for i in range(0, self.is05_utils.get_num_paths(portInst, port)):
                    try:
                        value = response['transport_params'][i][paramName]
                    except KeyError:
                        return False, "Could not find `{}` parameter at {} on leg {}, got{}".format(
                            paramName, url, i, response)
                    portNum = ports[portInst][i]
                    msg = "Problem updating {} value in bulk update, expected {} got {}".format(paramName, portNum,
                                                                                                value)
                    if value == portNum:
                        pass
                    else:
                        return False, msg
            else:
                return False, response
        return True, ""

    def check_patch_response_valid(self, port, portList):
        """Check the response to an empty patch request complies with the schema"""
        for myPort in portList:
            url = "single/" + port + "s/" + myPort + "/staged"
            data = {}
            valid, response = self.is05_utils.checkCleanRequestJSON("PATCH", url, data=data)
            if valid:
                schema = self.get_schema(CONN_API_KEY, "PATCH", "/single/" + port + "s/{" + port + "Id}/staged", 200)
                try:
                    self.validate_schema(response, schema)
                except ValidationError as e:
                    return False, "Response to empty patch to {} does not comply with schema: {}".format(url, str(e))
            else:
                return False, response
        return True, ""

    def check_patch_empty_transport_params(self, port, portList):
        """Check a patch request with empty leg(s) in transport parameters is accepted"""
        for myPort in portList:
            url = "single/" + port + "s/" + myPort + "/staged"
            data = {"transport_params": []}
            paths = self.is05_utils.get_num_paths(myPort, port)
            for i in range(0, paths):
                data["transport_params"].append({})
            valid, response = self.is05_utils.checkCleanRequestJSON("PATCH", url, data=data)
            if valid:
                pass
            else:
                return False, response
        return True, ""

    def check_staged_complies_with_constraints(self, port, portList):
        """Check that the staged endpoint is using parameters that meet
        the contents of the /constraints endpoint"""
        for myPort in portList:
            dest = "single/" + port + "s/" + myPort + "/staged/"
            valid, response = self.is05_utils.checkCleanRequestJSON("GET", dest)
            file_suffix = None
            if self.transport_types[myPort] == "urn:x-nmos:transport:rtp":
                file_suffix = "_transport_params_rtp.json"
            elif self.transport_types[myPort] == "urn:x-nmos:transport:mqtt":
                file_suffix = "_transport_params_mqtt.json"
            elif self.transport_types[myPort] == "urn:x-nmos:transport:websocket":
                file_suffix = "_transport_params_websocket.json"
            if valid:
                try:
                    schema_items = load_resolved_schema(self.apis[CONN_API_KEY]["spec_path"],
                                                        port + file_suffix)
                    schema = {
                        "$schema": "http://json-schema.org/draft-04/schema#",
                        "type": "array",
                        "items": schema_items
                    }
                except FileNotFoundError:
                    schema = load_resolved_schema(self.apis[CONN_API_KEY]["spec_path"],
                                                  "v1.0_" + port + file_suffix)
                url = "single/" + port + "s/" + myPort + "/constraints/"
                constraints_valid, constraints_response = self.is05_utils.checkCleanRequestJSON("GET", url)

                if constraints_valid:
                    count = 0
                    try:
                        for params in response['transport_params']:
                            try:
                                schema.update(constraints_response[count])
                            except IndexError:
                                return False, "Number of 'legs' in constraints does not match the number in " \
                                              "transport_params"
                            schema["items"]["$schema"] = "http://json-schema.org/draft-04/schema#"
                            try:
                                self.validate_schema(params, schema["items"])
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
        valid, response = self.is05_utils.checkCleanRequest("GET", endpoint, codes=[status_code])
        if valid:
            return self.check_response(schema, "GET", response)
        else:
            return False, "Invalid response while getting data: " + response

    def patch_auto_params(self, test, resources, resourceType, autoParams):
        """
        Patch all params to 'auto' from autoParams list to all resources (id-list) of type resourceType
        ("senders" / "receivers") and validate response
        """
        if len(resources) > 0:
            for resource in resources:
                dest_staged = "single/" + resourceType + "/" + resource + "/staged/"
                dest_active = "single/" + resourceType + "/" + resource + "/active/"

                valid, response = self.is05_utils.checkCleanRequestJSON("GET", dest_staged)
                if valid:
                    patchData = {
                        "transport_params": list(),
                        "activation": {
                            "mode": "activate_immediate"
                        }
                    }
                    try:
                        for leg in response["transport_params"]:
                            patchDataLeg = {}
                            for param in leg:
                                if param in autoParams:
                                    patchDataLeg[param] = "auto"
                            patchData["transport_params"].append(patchDataLeg)
                    except KeyError:
                        return test.FAIL("Did not find 'transport_params' in response from {}"
                                         .format(dest_staged))

                    valid_patch, response_patch = self.is05_utils.checkCleanRequestJSON("PATCH",
                                                                                        dest_staged,
                                                                                        data=patchData)
                    if valid_patch:
                        pass
                    else:
                        return test.FAIL(response_patch)

                    valid_active, response_active = self.is05_utils.checkCleanRequestJSON("GET", dest_active)
                    if valid_active:
                        try:
                            for leg in response_active["transport_params"]:
                                for param in leg:
                                    if param in autoParams and leg[param] == "auto":
                                        return test.FAIL("Patched 'auto' for '{}' did not translate on "
                                                         "'/active' endpoint".format(param))
                        except KeyError:
                            return test.FAIL("Did not find 'transport_params' in response from {}"
                                             .format(dest_active))
                    else:
                        return test.FAIL(response_active)
                else:
                    return test.FAIL(response)
            return test.PASS()
        else:
            return test.UNCLEAR("Not tested. No resources found.")
