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
import requests
import time
import TestHelper

from random import randint
from NMOSUtils import NMOSUtils


class IS05Utils(NMOSUtils):
    def __init__(self, url):
        NMOSUtils.__init__(self, url)

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

            while retries < 5 and not finished:
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
        TAItime = self.get_TAI_time(1)
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

            while retries < 5 and not finished:
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

    def park_resource(self, resource_type, resource_id):
        url = "single/" + resource_type + "/" + resource_id + "/staged"
        data = {"master_enable": False}
        valid, response = self.checkCleanRequestJSON("PATCH", url, data=data)
        if valid:
            staged_params = response['transport_params']
            valid2, response2 = self.check_perform_immediate_activation(resource_type.rstrip("s"),
                                                                        resource_id,
                                                                        staged_params)
            if not valid2:
                return False, response2
        else:
            return False, response

        return True, ""

    def subscribe_resource(self, resource_type, resource_id, subscription_id, multicast=True):
        url = "single/" + resource_type + "/" + resource_id + "/staged"

        data = {"master_enable": True, "transport_params": []}
        if resource_type == "receivers":
            data["transport_file"] = {"data": "", "type": "application/sdp"}
            data["sender_id"] = subscription_id
        else:
            data["receiver_id"] = subscription_id

        param = "multicast_ip"
        if resource_type == "senders":
            param = "destination_ip"

        for i in range(0, self.get_num_paths(resource_id, resource_type.rstrip("s"))):
            if multicast:
                data['transport_params'].append({param: "239.10.53.5"})
            else:
                data['transport_params'].append({param: "127.0.0.1"})

        valid, response = self.checkCleanRequestJSON("PATCH", url, data=data)
        if valid:
            staged_params = response['transport_params']
            valid2, response2 = self.check_perform_immediate_activation(resource_type.rstrip("s"),
                                                                        resource_id,
                                                                        staged_params)
            if not valid2:
                return False, response2
        else:
            return False, response

        return True, ""

    def checkCleanRequest(self, method, dest, data=None, code=200):
        """Checks a request can be made and the resulting json can be parsed"""
        status, response = TestHelper.do_request(method, self.url + dest, data)
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
