import re
import requests

from random import randint


class IS05Utils(object):
    def __init__(self, url):
        self.url = url

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

    def do_request(self, method, url, data=None):
        """Perform a basic HTTP request with appropriate error handling"""
        try:
            s = requests.Session()
            req = None
            if data is not None:
                req = requests.Request(method, url, json=data)
            else:
                req = requests.Request(method, url)
            prepped = req.prepare()
            r = s.send(prepped)
            return True, r
        except requests.exceptions.Timeout:
            return False, "Connection timeout"
        except requests.exceptions.TooManyRedirects:
            return False, "Too many redirects"
        except requests.exceptions.ConnectionError as e:
            return False, str(e)
        except requests.exceptions.RequestException as e:
            return False, str(e)

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
