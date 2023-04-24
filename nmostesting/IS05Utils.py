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

import re
import time

from random import randint
from . import TestHelper
from .NMOSUtils import NMOSUtils
from . import Config as CONFIG

IMMEDIATE_ACTIVATION = 'activate_immediate'
SCHEDULED_ABSOLUTE_ACTIVATION = 'activate_scheduled_absolute'
SCHEDULED_RELATIVE_ACTIVATION = 'activate_scheduled_relative'


class IS05Utils(NMOSUtils):
    def __init__(self, url):
        NMOSUtils.__init__(self, url)

    def get_valid_transports(self, api_version):
        """Identify the valid transport types for a given version of IS-05"""
        valid_transports = ["urn:x-nmos:transport:rtp",
                            "urn:x-nmos:transport:rtp.mcast",
                            "urn:x-nmos:transport:rtp.ucast",
                            "urn:x-nmos:transport:dash"]
        if self.compare_api_version(api_version, "v1.1") >= 0:
            valid_transports.append("urn:x-nmos:transport:websocket")
            valid_transports.append("urn:x-nmos:transport:mqtt")
        return valid_transports

    def check_num_legs(self, url, res_type, uuid):
        """Checks the number of legs present on a given sender/receiver"""
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

                    if len(constraints) >= min:
                        pass
                    else:
                        return False, "{} {} has too few legs".format(res_type, uuid)
                    if len(constraints) == len(stagedParams):
                        pass
                    else:
                        return False, "Number of legs in constraints and staged is different for {} {}".format(res_type,
                                                                                                               uuid)

                    if len(constraints) == len(activeParams):
                        pass
                    else:
                        return False, "Number of legs in constraints and active is different for {} {}".format(res_type,
                                                                                                               uuid)

                    return True, ""
                else:
                    return False, active
            else:
                return False, staged
        else:
            return False, constraints

    def check_staged_activation_params_default(self, port, portId):
        # Check that the staged activation parameters have returned to their default values
        stagedUrl = "single/" + port + "s/" + portId + "/staged"
        valid, staged = self.checkCleanRequestJSON("GET", stagedUrl)
        if valid:
            expected = {"mode": None, "requested_time": None, "activation_time": None}
            try:
                params = staged['activation']
            except KeyError:
                return False, "Could not find a receiver_id entry in response from {}, got {}".format(stagedUrl,
                                                                                                      staged)
            except TypeError:
                return False, "Expected a dict to be returned from {}, got a {}: {}".format(stagedUrl, type(staged),
                                                                                            staged)
            if params == expected:
                return True, ""
            else:
                msg = "Activation parameters in staged have not returned to their defaults after activation. " \
                      "Expected {}, got {}".format(expected, params)
                return False, msg
        else:
            return False, staged

    def perform_activation(self, port, portId, activateMode=IMMEDIATE_ACTIVATION, activateTime=None, masterEnable=None):
        # Request an immediate activation
        stagedUrl = "single/" + port + "s/" + portId + "/staged"
        data = {"activation": {"mode": activateMode}}
        code = 200
        if activateMode != IMMEDIATE_ACTIVATION:
            data["activation"]["requested_time"] = activateTime
            code = 202
        if masterEnable is not None:
            data["master_enable"] = masterEnable
        return self.checkCleanRequestJSON("PATCH", stagedUrl, data=data, code=code)

    def _check_perform_activation(self, port, portId, stageParams, changedParam, activationName="immediate",
                                  activateMode=IMMEDIATE_ACTIVATION, activateTime=None, activateSleep=0):
        stagedUrl = "single/" + port + "s/" + portId + "/staged"
        activeUrl = "single/" + port + "s/" + portId + "/active"
        valid, stage = self.perform_activation(port, portId, activateMode, activateTime)
        if valid:
            # Check the values in the /staged PATCH response

            try:
                stageMode = stage['activation']['mode']
                stageRequested = stage['activation']['requested_time']
                stageActivation = stage['activation']['activation_time']
            except KeyError:
                return False, "Could not find all activation entries from {}, " \
                              "got {}".format(stagedUrl, stage)
            except TypeError:
                return False, "Expected a dict to be returned from {}, " \
                              "got a {}: {}".format(stagedUrl, type(stage), stage)
            if stageMode == activateMode:
                pass
            else:
                return False, "Expected mode `{}` for {} activation, " \
                              "got {}".format(activateMode, activationName, stageMode)
            if stageRequested == activateTime:
                pass
            else:
                return False, "Expected requested time `{}` for {} activation, " \
                              "got {}".format(activateTime or "null", activationName, stageRequested)
            if stageActivation and re.match("^[0-9]+:[0-9]+$", stageActivation) is not None:
                pass
            else:
                return False, "Expected activation time to match regex ^[0-9]+:[0-9]+$, " \
                              "got {}".format(stageActivation)

            # For immediate activations, check the values now on /staged

            if activateMode == IMMEDIATE_ACTIVATION:
                validImmediate, stagedImmediate = self.check_staged_activation_params_default(port, portId)
                if not validImmediate:
                    return False, stagedImmediate

            if activateSleep > 0:
                time.sleep(activateSleep)

            # Check the values now on /active

            # API and Testing Tool clocks need to be synchronized to test absolute scheduled activations
            # so allow a couple of retries for scheduled activations and report late activations as a WARNING
            maxTries = 1 if activateMode == IMMEDIATE_ACTIVATION else 3
            tries = 0
            ready = False

            while tries < maxTries:
                tries = tries + 1
                valid2, active = self.checkCleanRequestJSON("GET", activeUrl)
                if valid2:
                    ready = True
                    for i in range(0, self.get_num_paths(portId, port)):
                        try:
                            activeParam = active['transport_params'][i][changedParam]
                        except KeyError:
                            return False, "Could not find active {} entry on leg {} from {}, " \
                                          "got {}".format(changedParam, i, activeUrl, active)
                        except TypeError:
                            return False, "Expected a dict to be returned from {} on leg {}, " \
                                          "got a {}: {}".format(activeUrl, i, type(active), active)
                        try:
                            stageParam = stageParams[i][changedParam]
                        except KeyError:
                            return False, "Could not find staged {} entry on leg {} from {}, " \
                                          "got {}".format(changedParam, i, stagedUrl, stageParams)
                        except TypeError:
                            return False, "Expected a dict to be returned from {} on leg {}, " \
                                          "got a {}: {}".format(stagedUrl, i, type(active), stageParams)
                        if (stageParam == activeParam if stageParam != "auto" else "auto" != activeParam):
                            # changed param is ready, though maybe it was already so also check activation entries
                            pass
                        else:
                            ready = False

                    if ready:
                        try:
                            activeMode = active['activation']['mode']
                            activeRequested = active['activation']['requested_time']
                            activeActivation = active['activation']['activation_time']
                        except KeyError:
                            return False, "Could not find all activation entries from {}, " \
                                          "got {}".format(activeUrl, active)
                        except TypeError:
                            return False, "Expected a dict to be returned from {}, " \
                                          "got a {}: {}".format(activeUrl, type(active), active)

                        if activeMode == activateMode and activeActivation \
                                and (activateMode == IMMEDIATE_ACTIVATION or activeRequested == activateTime) \
                                and self.compare_resource_version(activeActivation, stageActivation) >= 0:
                            if tries > 1:
                                # True with a message means WARNING!
                                return True, "Activation entries were set at {} later than expected. " \
                                             "This could just indicate the API and Testing Tool clocks are " \
                                             "not synchronized. (Tries: {})".format(activeUrl, tries)
                            else:
                                return True, ""
                else:
                    return False, active
                time.sleep(CONFIG.API_PROCESSING_TIMEOUT)
            if ready:
                return False, "Activation entries were not set at {} after {} activation{}" \
                              .format(activeUrl, activationName, " (Tries: {})".format(tries) if tries > 1 else "")
            return False, "Transport parameters did not transition to {} after {} activation{}" \
                          .format(activeUrl, activationName, " (Tries: {})".format(tries) if tries > 1 else "")
        else:
            return False, stage

    def check_perform_immediate_activation(self, port, portId, stagedParams, changedParam):
        return self._check_perform_activation(port, portId, stagedParams, changedParam)

    def check_perform_relative_activation(self, port, portId, stagedParams, changedParam):
        return self._check_perform_activation(port, portId, stagedParams, changedParam,
                                              "relative", SCHEDULED_RELATIVE_ACTIVATION,
                                              "0:200000000", 0.2)

    def check_perform_absolute_activation(self, port, portId, stagedParams, changedParam):
        # As stated in the README, the time of the test device and the time of the device hosting the tests
        # needs to be synchronized in order to test absolute activation, but allow a 0.1 seconds difference...
        MAX_TIME_SYNC_OFFSET = 0.1
        return self._check_perform_activation(port, portId, stagedParams, changedParam,
                                              "absolute", SCHEDULED_ABSOLUTE_ACTIVATION,
                                              self.get_TAI_time(1), 1 + MAX_TIME_SYNC_OFFSET)

    def check_activation(self, port, portId, activationMethod, transportType, masterEnable=None):
        """Checks that when an immediate activation is called staged parameters are moved
        to active and the activation is correctly displayed in the /active endpoint"""
        # Set a new value for a transport_param for each leg in staged
        valid, paramValues = self.generate_changeable_param(port, portId, transportType)
        paramName = self.changeable_param_name(transportType)
        if valid:
            stagedUrl = "single/" + port + "s/" + portId + "/staged"
            data = {"transport_params": []}
            if masterEnable is not None:
                data["master_enable"] = masterEnable
            legs = self.get_num_paths(portId, port)
            for i in range(0, legs):
                data['transport_params'].append({paramName: paramValues[i]})
            if len(data["transport_params"]) == 0:
                del data["transport_params"]
            valid2, stage = self.checkCleanRequestJSON("PATCH", stagedUrl, data=data)
            if valid2:
                try:
                    stageParams = stage['transport_params']
                except KeyError:
                    return False, "Could not find `transport_params` entry in response from {}".format(stagedUrl)
                except TypeError:
                    return False, "Expected a dict to be returned from {}, got a {}".format(stagedUrl,
                                                                                            type(stageParams))
                if len(stageParams) != legs:
                    return False, "Expected {} `transport_params` in response from {}".format(legs, stagedUrl)
                for i in range(0, legs):
                    if paramName not in stageParams[i] or stageParams[i][paramName] != paramValues[i]:
                        return False, "Expected `transport_params` {} `{}` to be {} in response from {}" \
                                      .format(i, paramName, paramValues[i], stagedUrl)
                return activationMethod(port, portId, stageParams, paramName)
            else:
                return False, stage
        else:
            return False, paramValues

    def generate_changeable_param(self, port, portId, transportType):
        """Use a port's constraints to generate a changeable parameter"""
        if transportType == "urn:x-nmos:transport:websocket":
            return self.generate_connection_uris(port, portId)
        elif transportType == "urn:x-nmos:transport:mqtt":
            return self.generate_broker_topics(port, portId)
        else:
            return self.generate_destination_ports(port, portId)

    def changeable_param_name(self, transportType):
        """Identify the parameter name which will be used to change IS-05 configuration"""
        if transportType == "urn:x-nmos:transport:websocket":
            return "connection_uri"
        elif transportType == "urn:x-nmos:transport:mqtt":
            return "broker_topic"
        else:
            return "destination_port"

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
            except (TypeError, ValueError):
                return False, "Invalid response from {}, got: {}".format(url, constraints)
            except KeyError as e:
                return False, "Expected key '{}' not found in response from {}".format(str(e), url)
        else:
            return False, constraints

    def generate_connection_uris(self, port, portId):
        """Generates a fake connection URI, or re-uses one from the advertised constraints"""
        url = "single/" + port + "s/" + portId + "/constraints/"
        valid, constraints = self.checkCleanRequestJSON("GET", url)
        if valid:
            toReturn = []
            try:
                for entry in constraints:
                    if "enum" in entry['connection_uri']:
                        values = entry['connection_uri']['enum']
                        toReturn.append(values[randint(0, len(values) - 1)])
                    else:
                        scheme = "ws"
                        if CONFIG.ENABLE_HTTPS:
                            scheme = "wss"
                        toReturn.append("{}://{}:{}".format(scheme, TestHelper.get_default_ip(), CONFIG.PORT_BASE))
                return True, toReturn
            except (TypeError, ValueError):
                return False, "Invalid response from {}, got: {}".format(url, constraints)
            except KeyError as e:
                return False, "Expected key '{}' not found in response from {}".format(str(e), url)
        else:
            return False, constraints

    def generate_broker_topics(self, port, portId):
        """Generates a fake broker topic, or re-uses one from the advertised constraints"""
        url = "single/" + port + "s/" + portId + "/constraints/"
        valid, constraints = self.checkCleanRequestJSON("GET", url)
        if valid:
            toReturn = []
            try:
                for entry in constraints:
                    if "enum" in entry['broker_topic']:
                        values = entry['broker_topic']['enum']
                        toReturn.append(values[randint(0, len(values) - 1)])
                    else:
                        toReturn.append("test_broker_topic")
                return True, toReturn
            except (TypeError, ValueError):
                return False, "Invalid response from {}, got: {}".format(url, constraints)
            except KeyError as e:
                return False, "Expected key '{}' not found in response from {}".format(str(e), url)
        else:
            return False, constraints

    def check_change_transport_param(self, port, portList, paramName, paramValues, myPort):
        """Check that we can update a transport parameter"""
        url = "single/" + port + "s/" + myPort + "/staged"
        data = {'transport_params': []}
        paths = self.get_num_paths(myPort, port)
        for i in range(0, paths):
            data['transport_params'].append({})
            data['transport_params'][i][paramName] = paramValues[i]
        if len(data["transport_params"]) == 0:
            del data["transport_params"]
        valid, stage = self.checkCleanRequestJSON("PATCH", url, data=data)
        if valid:
            valid2, staged = self.checkCleanRequestJSON("GET", url + "/")
            if valid2:
                try:
                    stagedParams = staged['transport_params']
                except KeyError:
                    return False, "Could not find transport_params in response from {}, got {}".format(url, staged)
                except TypeError:
                    return False, "Expected a dict to be returned from {}, got a {}: {}".format(url, type(staged),
                                                                                                staged)
                count = 0
                try:
                    for item in stagedParams:
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
                    return False, "Expected a dict to be returned from {}, got a {}: {}".format(url,
                                                                                                type(stagedParams),
                                                                                                stagedParams)
            else:
                return False, staged
        else:
            return False, stage
        return True, ""

    def check_refuses_invalid_patch(self, port, portList):
        """Check that invalid patch requests to /staged are met with an HTTP 400"""
        data = {"bad": "data"}
        for myPort in portList:
            url = "single/" + port + "s/" + myPort + "/staged"
            valid, stage = self.checkCleanRequestJSON("PATCH", url, data=data, code=400)
            if valid:
                pass
            else:
                return False, stage
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

    def check_sdp_matches_params(self, portId):
        """Checks that the SDP file for an RTP Sender matches the transport_params"""
        aDest = "single/senders/" + portId + "/active/"
        sdpDest = "single/senders/" + portId + "/transportfile/"
        a_valid, a_response = self.checkCleanRequestJSON("GET", aDest)
        sdp_valid, sdp_response = self.checkCleanRequest("GET", sdpDest, codes=[200, 404])
        if a_valid:
            if sdp_valid:
                if sdp_response.status_code != 200:
                    return True, sdp_response
                sdp_sections = sdp_response.text.split("m=")
                sdp_global = sdp_sections[0]
                sdp_media_sections = sdp_sections[1:]
                sdp_groups_line = re.search(r"a=group:DUP (.+)", sdp_global)
                tp_compare = []
                if sdp_groups_line:
                    sdp_group_names = sdp_groups_line.group(1).split()
                    for sdp_media in sdp_media_sections:
                        group_name = re.search(r"a=mid:(\S+)", sdp_media)
                        if group_name.group(1) in sdp_group_names:
                            tp_compare.append("m=" + sdp_media)
                elif len(sdp_media_sections) > 0:
                    tp_compare.append("m=" + sdp_media_sections[0])
                if len(tp_compare) != len(a_response["transport_params"]):
                    return False, "Number of SDP groups do not match the length of the 'transport_params' array"
                for index, sdp_data in enumerate(tp_compare):
                    transport_params = a_response["transport_params"][index]
                    media_line = re.search(r"m=([a-z]+) ([0-9]+) RTP/AVP ([0-9]+)", sdp_data)
                    if media_line.group(2) != str(transport_params["destination_port"]):
                        return False, "SDP destination port {} does not match transport_params: {}" \
                                      .format(media_line.group(2), transport_params["destination_port"])
                    connection_line = re.search(r"c=IN IP[4,6] ([^/\r\n]*)(?:/[0-9]+){0,2}", sdp_data)
                    if connection_line.group(1) != transport_params["destination_ip"]:
                        return False, "SDP destination IP {} does not match transport_params: {}" \
                                      .format(connection_line.group(1), transport_params["destination_ip"])
                    filter_line = re.search(r"a=source-filter: incl IN IP[4,6] (\S*) (\S*)", sdp_data)
                    if filter_line and filter_line.group(2) != transport_params["source_ip"]:
                        return False, "SDP source-filter IP {} does not match transport_params: {}" \
                                      .format(filter_line.group(2), transport_params["source_ip"])
                    elif filter_line and filter_line.group(1) != transport_params["destination_ip"]:
                        return False, "SDP source-filter multicast IP {} does not match transport_params {}" \
                                      .format(filter_line.group(1), transport_params["destination_ip"])
            else:
                return False, sdp_response
        else:
            return False, a_response
        return True, sdp_response

    def get_senders(self):
        """Gets a list of the available senders on the API"""
        toReturn = []
        valid, r = TestHelper.do_request("GET", self.url + "single/senders/")
        if valid and r.status_code == 200:
            try:
                for value in r.json():
                    toReturn.append(value[:-1])
            except ValueError:
                pass
        return toReturn

    def get_receivers(self):
        """Gets a list of the available receivers on the API"""
        toReturn = []
        valid, r = TestHelper.do_request("GET", self.url + "single/receivers/")
        if valid and r.status_code == 200:
            try:
                for value in r.json():
                    toReturn.append(value[:-1])
            except ValueError:
                pass
        return toReturn

    def get_transporttype(self, port, portType):
        """Get the transport type for a given Sender or Receiver"""
        toReturn = None
        valid, r = TestHelper.do_request("GET", self.url + "single/" + portType + "s/" + port + "/transporttype")
        if valid and r.status_code == 200:
            try:
                toReturn = r.json()
            except ValueError:
                pass
        return toReturn

    def get_transportfile(self, port):
        """Get the transport file for a given Sender"""
        toReturn = None
        valid, r = TestHelper.do_request("GET", self.url + "single/senders/" + port + "/transportfile")
        if valid and r.status_code == 200:
            toReturn = r.text
        return toReturn

    def get_num_paths(self, port, portType):
        """Returns the number or redundant paths on a port"""
        url = self.url + "single/" + portType + "s/" + port + "/constraints/"
        valid, r = TestHelper.do_request("GET", url)
        if valid:
            try:
                rjson = r.json()
                return len(rjson)
            except ValueError:
                return 0
        else:
            return 0

    def park_resource(self, resource_type, resource_id):
        url = "single/" + resource_type + "/" + resource_id + "/staged"
        data = {"master_enable": False}
        valid, response = self.checkCleanRequestJSON("PATCH", url, data)
        if valid:
            try:
                response.get('transport_params')
            except KeyError:
                return False, "Staged resource did not return 'transport_params' in PATCH response"
            valid2, response2 = self.perform_activation(resource_type.rstrip("s"),
                                                        resource_id)
            if not valid2:
                return False, response2
        else:
            return False, response

        return True, ""

    def subscribe_resource(self, resource_type, resource_id, subscription_id, multicast=True):
        url = "single/" + resource_type + "/" + resource_id + "/staged"

        data = {"master_enable": True, "transport_params": []}
        if resource_type == "receivers":
            data["sender_id"] = subscription_id
        else:
            data["receiver_id"] = subscription_id

        param = "multicast_ip"
        if resource_type == "senders":
            param = "destination_ip"

        for i in range(0, self.get_num_paths(resource_id, resource_type.rstrip("s"))):
            if multicast:
                data['transport_params'].append({param: CONFIG.MULTICAST_STREAM_TARGET})
            else:
                data['transport_params'].append({param: CONFIG.UNICAST_STREAM_TARGET})

        if len(data["transport_params"]) == 0:
            del data["transport_params"]

        valid, response = self.checkCleanRequestJSON("PATCH", url, data=data)
        if valid:
            valid2, response2 = self.perform_activation(resource_type.rstrip("s"),
                                                        resource_id)
            if not valid2:
                return False, response2
        else:
            return False, response

        return True, ""

    def checkCleanRequest(self, method, dest, data=None, codes=[200]):
        """Checks a request can be made"""
        status, response = TestHelper.do_request(method, self.url + dest, json=data)
        if not status:
            return status, response

        message = "Expected status code {} from {}, got {}.".format(codes[0], dest, response.status_code)
        if response.status_code in codes:
            return True, response
        else:
            return False, message

    def checkCleanRequestJSON(self, method, dest, data=None, code=200):
        """Checks a request can be made and the resulting json can be parsed"""
        valid, response = self.checkCleanRequest(method, dest, data, [code])
        if valid:
            try:
                return True, response.json()
            except Exception:
                # Failed parsing JSON
                return False, "Invalid JSON received"
        else:
            return valid, response
