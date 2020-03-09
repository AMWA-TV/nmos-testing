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

    def check_num_legs(self, url, type, uuid):
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

    def check_perform_immediate_activation(self, port, portId, stagedParams, changedParam):
        # Request an immediate activation
        stagedUrl = "single/" + port + "s/" + portId + "/staged"
        activeUrl = "single/" + port + "s/" + portId + "/active"
        valid, response = self.perform_activation(port, portId)
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
            if mode == IMMEDIATE_ACTIVATION:
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
                            activeParam = response3['transport_params'][i][changedParam]
                        except KeyError:
                            return False, "Could not find active {} entry on leg {} from {}, " \
                                          "got {}".format(changedParam, i, activeUrl, response3)
                        except TypeError:
                            return False, "Expected a dict to be returned from {} on leg {}, got a {}: {}".format(
                                activeUrl, i, type(response3), response3)
                        try:
                            stagedParam = stagedParams[i][changedParam]
                        except KeyError:
                            return False, "Could not find staged {} entry on leg {} from {}, " \
                                          "got {}".format(changedParam, i, stagedUrl, stagedParams)
                        except TypeError:
                            return False, "Expected a dict to be returned from {} on leg {}, got a {}: {}".format(
                                stagedUrl, i, type(response3), stagedParams)
                        msg = "Transport parameters did not transition to active during an immediate activation"
                        if (stagedParam == activeParam if stagedParam != "auto" else "auto" != activeParam):
                            pass
                        else:
                            return False, msg

                    msg = "Activation mode was not set to `activate_immediate` at {} " \
                          "after an immediate activation".format(activeUrl)
                    if response3['activation']['mode'] == IMMEDIATE_ACTIVATION:
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

    def check_perform_relative_activation(self, port, portId, stagedParams, changedParam):
        # Request an relative activation 2 nanoseconds in the future
        stagedUrl = "single/" + port + "s/" + portId + "/staged"
        activeUrl = "single/" + port + "s/" + portId + "/active"
        valid, response = self.perform_activation(port, portId, SCHEDULED_RELATIVE_ACTIVATION, "0:2")
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
            if mode == SCHEDULED_RELATIVE_ACTIVATION:
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
            time.sleep(0.5)

            retries = 0
            finished = False

            while retries < 5 and not finished:
                # Check the values now on /active
                valid2, activeParams = self.checkCleanRequestJSON("GET", activeUrl)
                if valid2:
                    for i in range(0, self.get_num_paths(portId, port)):
                        try:
                            activeParam = activeParams['transport_params'][i][changedParam]
                        except KeyError:
                            return False, "Could not find active {} entry on leg {} from {}, " \
                                          "got {}".format(changedParam, i, activeUrl, activeParams)
                        except TypeError:
                            return False, "Expected a dict to be returned from {} on leg {}, " \
                                          "got a {}: {}".format(activeUrl, i, type(activeParams), activeParams)
                        try:
                            stagedParam = stagedParams[i][changedParam]
                        except KeyError:
                            return False, "Could not find staged {} entry on leg {} from {}, " \
                                          "got {}".format(changedParam, i, stagedUrl, stagedParams)
                        except TypeError:
                            return False, "Expected a dict to be returned from {} on leg {}, " \
                                          "got a {}: {}".format(stagedUrl, i, type(activeParams), stagedParams)
                        if (stagedParam == activeParam if stagedParam != "auto" else "auto" != activeParam):
                            finished = True
                        else:
                            retries = retries + 1
                            time.sleep(CONFIG.API_PROCESSING_TIMEOUT)

                    if finished:
                        try:
                            if activeParams['activation']['mode'] == SCHEDULED_RELATIVE_ACTIVATION:
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

    def check_perform_absolute_activation(self, port, portId, stagedParams, changedParam):
        # request an absolute activation
        stagedUrl = "single/" + port + "s/" + portId + "/staged"
        activeUrl = "single/" + port + "s/" + portId + "/active"
        TAItime = self.get_TAI_time(1)
        valid, response = self.perform_activation(port, portId, SCHEDULED_ABSOLUTE_ACTIVATION, TAItime)
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
                if response['activation']['mode'] == SCHEDULED_ABSOLUTE_ACTIVATION:
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

            while retries < 5 and not finished:
                # Check the values now on /active
                valid2, activeParams = self.checkCleanRequestJSON("GET", activeUrl)
                if valid2:
                    for i in range(0, self.get_num_paths(portId, port)):
                        try:
                            activeParam = activeParams['transport_params'][i][changedParam]
                        except KeyError:
                            return False, "Could not find active {} entry on leg {} from {}, " \
                                          "got {}".format(changedParam, i, activeUrl, activeParams)
                        except TypeError:
                            return False, "Expected a dict to be returned from {} on leg {}, got a {}: " \
                                          "{}".format(activeUrl, i, type(activeParams), activeParams)
                        try:
                            stagedParam = stagedParams[i][changedParam]
                        except KeyError:
                            return False, "Could not find staged {} entry on leg {} from {}, " \
                                          "got {}".format(changedParam, i, stagedUrl, stagedParams)
                        except TypeError:
                            return False, "Expected a dict to be returned from {} on leg {}, got a {}: " \
                                          "{}".format(stagedUrl, i, type(activeParams), stagedParams)
                        if (stagedParam == activeParam if stagedParam != "auto" else "auto" != activeParam):
                            finished = True
                        else:
                            retries = retries + 1
                            time.sleep(CONFIG.API_PROCESSING_TIMEOUT)

                    if finished:
                        try:
                            if activeParams['activation']['mode'] == SCHEDULED_ABSOLUTE_ACTIVATION:
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
            valid2, r = self.checkCleanRequestJSON("PATCH", stagedUrl, data=data)
            if valid2:
                try:
                    stagedParams = r['transport_params']
                except KeyError:
                    return False, "Could not find `transport_params` entry in response from {}".format(stagedUrl)
                except TypeError:
                    return False, "Expected a dict to be returned from {}, got a {}".format(stagedUrl,
                                                                                            type(stagedParams))
                if len(stagedParams) != legs:
                    return False, "Expected {} `transport_params` in response from {}".format(legs, stagedUrl)
                for i in range(0, legs):
                    if paramName not in stagedParams[i] or stagedParams[i][paramName] != paramValues[i]:
                        return False, "Expected `transport_params` {} `{}` to be {} in response from {}" \
                                      .format(i, paramName, paramValues[i], stagedUrl)
                return activationMethod(port, portId, stagedParams, paramName)
            else:
                return False, r
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
            except TypeError:
                return False, "Expected a dict to be returned from {}, got a {}: {}".format(url, type(constraints),
                                                                                            constraints)
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
            except TypeError:
                return False, "Expected a dict to be returned from {}, got a {}: {}".format(url, type(constraints),
                                                                                            constraints)
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
            except TypeError:
                return False, "Expected a dict to be returned from {}, got a {}: {}".format(url, type(constraints),
                                                                                            constraints)
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
        sdp_valid, sdp_response = self.checkCleanRequest("GET", sdpDest)
        if a_valid:
            if sdp_valid:
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
                else:
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
        return True, ""

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

    def checkCleanRequest(self, method, dest, data=None, code=200):
        """Checks a request can be made and the resulting json can be parsed"""
        status, response = TestHelper.do_request(method, self.url + dest, json=data)
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
            except Exception:
                # Failed parsing JSON
                return False, "Invalid JSON received"
        else:
            return valid, response
