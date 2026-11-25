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
        print("URL could not be parsed: {}".format(url))
        return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ip", required=True, help="IP address or Hostname of DuT")
    parser.add_argument("--port", type=int, required=True, help="Port number of IS-04 API of DuT")
    parser.add_argument("--version", default="v1.2", help="Version of IS-04 API of DuT")
    args = parser.parse_args()

    is04Port = args.port
    is05Port = None
    is08Port = None
    node_id = None
    senders = []
    receivers = []
    mac_addresses = []

    base_url = "http://{}:{}/x-nmos/node/{}/".format(args.ip, args.port, args.version)

    # Self
    url = base_url + "self/"
    response = requests.get(url)
    mac_addresses = response.json()["interfaces"]
    for address in mac_addresses:
        if isinstance(address["port_id"], str):
            address["port_id"] = address["port_id"].replace("-", ":")
        if isinstance(address["chassis_id"], str):
            address["chassis_id"] = address["chassis_id"].replace("-", ":")
    node_id = response.json()["id"]
    print("Host: {}".format(response.json()["description"]))

    # Devices. We assume that the same port is used for all IS-05/08 instances
    url = base_url + "devices/"
    response = requests.get(url)
    json_data = response.json()
    for device in json_data:
        for control in device["controls"]:
            if control["type"].startswith("urn:x-nmos:control:sr-ctrl"):
                is05Port = url_port_number(control["href"])
            if control["type"].startswith("urn:x-nmos:control:cm-ctrl"):
                is08Port = url_port_number(control["href"])

    # Senders
    url = base_url + "senders/"
    response = requests.get(url)
    for d in response.json():
        data = {
            "label": d["label"],
            "id": d["id"],
            "sdp": d["manifest_href"]
        }
        senders.append(data)

    # Receivers
    url = base_url + "receivers/"
    response = requests.get(url)
    for d in response.json():
        data = {
            "label": d["label"],
            "format": d["format"],
            "id": d["id"]
        }
        receivers.append(data)

    # Display Data
    print("IS-04 Port: {}".format(is04Port))
    print("IS-05 Port: {}".format(is05Port))
    print("IS-08 Port: {}".format(is08Port))

    print("Node ID: {}".format(node_id))
    print("Sender IDs:")
    pprint.pprint(senders)
    print("Receiver IDs:")
    pprint.pprint(receivers)
    print("MAC Addresses:")
    pprint.pprint(mac_addresses)
