#!/usr/bin/python

# Copyright (C) 2019 Advanced Media Workflow Association
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

import argparse
import requests
from urllib.parse import urlparse
import pprint


def url_port_number(url):
    result = urlparse(url)
    try:
        if result.port:
            return result.port
        else:
            return 80
    except ValueError:
        print("IPv6 address could not be parsed: {}".format(url))
        return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ip", required=True, help="IP address or Hostname of DuT")
    parser.add_argument("--port", type=int, required=True, help="Port number of IS-04 API of DuT")
    args = parser.parse_args()

    is04Port = args.port
    is05Port = None
    is08Port = None
    senders = []
    receivers = []
    mac_addresses = []

    base_url = "http://{}:{}/x-nmos/node/v1.2/".format(args.ip, args.port)

    # Self
    url = base_url + "self/"
    response = requests.get(url)
    mac_addresses = response.json()['interfaces']
    for address in mac_addresses:
        if type(address['port_id']) == str:
            address['port_id'] = address['port_id'].replace("-", ":")
        if type(address['chassis_id']) == str:
            address['chassis_id'] = address['chassis_id'].replace("-", ":")

    # Devices
    url = base_url + "devices/"
    response = requests.get(url)
    json_data = response.json()
    for d in json_data[0]["controls"]:
        if d['type'] == "urn:x-nmos:control:sr-ctrl/v1.0":
            is05Port = url_port_number(d['href'])
        if d['type'] == "urn:x-nmos:control:cm-ctrl/v1.0":
            is08Port = url_port_number(d['href'])

    # Senders
    url = base_url + "senders/"
    response = requests.get(url)
    for d in response.json():
        data = {
            "label": d['label'],
            "id": d['id'],
            "sdp": d['manifest_href']
        }
        senders.append(data)

    # Receivers
    url = base_url + "receivers/"
    response = requests.get(url)
    for d in response.json():
        data = {
            "label": d['label'],
            "format": d['format'],
            "id": d['id']
        }
        receivers.append(data)

    # Display Data
    print("IS-04 Port: {}".format(is04Port))
    print("IS-05 Port: {}".format(is05Port))
    print("IS-08 Port: {}".format(is08Port))

    print("Sender IDs:")
    pprint.pprint(senders)
    print("Receiver IDs:")
    pprint.pprint(receivers)
    print("MAC Addresses:")
    pprint.pprint(mac_addresses)

# format MAC with colons
# Add hostname to uuid checker
