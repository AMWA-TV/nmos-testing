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
import os
import json
import sys

parser = argparse.ArgumentParser()
parser.add_argument("--ip", required=True, help="IP address or Hostname of DuT")
parser.add_argument("--port", type=int, required=True, help="Port number of IS-05 API of DuT")
parser.add_argument("--sender", action="store_true", help="Configure NMOS Sender")
parser.add_argument("--receiver", action="store_true", help="Configure NMOS Receiver")
parser.add_argument("-e", "--enable", action="store_true", help="Set master_enable=True")
parser.add_argument("-d", "--disable", action="store_true", help="Set master_enable=False")
parser.add_argument("-r", "--request", required=True, help="Patch file to be sent in the request")
parser.add_argument("-s", "--sdp", help="SDP file to be sent in the request")
parser.add_argument("-u", "--uuid", required=True, help="UUID of resource to be configured")
args = parser.parse_args()

# Configure for Sender or Receiver
if args.sender:
    print("Configuring NMOS Sender using IS-05")
    url = "http://{}:{}/x-nmos/connection/v1.0/single/senders/{}/staged".format(args.ip, args.port, args.uuid)
elif args.receiver:
    print("Configuring NMOS Receiver using IS-05")
    url = "http://{}:{}/x-nmos/connection/v1.0/single/receivers/{}/staged".format(args.ip, args.port, args.uuid)
else:
    print("Please select either Sender or Receiver mode")
    sys.exit()

# Read PATCH request JSON
if os.path.exists(args.request):
    with open(args.request, "r") as json_file:
        request_payload = json.load(json_file)
else:
    print("Request file \"{}\" does not exist".format(args.request))
    sys.exit()

if args.enable:
    request_payload["master_enable"] = True
elif args.disable:
    request_payload["master_enable"] = False
print("master_enable: {}".format(request_payload["master_enable"]))


# Read SDP file and add to request payload
if args.sdp:
    if os.path.exists(args.sdp):
        with open(args.sdp, "r") as sdp_file:
            sdp_payload = sdp_file.read()
    if sdp_payload and args.receiver:
        print("Using SDP file")
        request_payload["transport_file"] = {"data": sdp_payload, "type": "application/sdp"}

print(request_payload)

try:
    response = requests.patch(url, timeout=2, json=request_payload)
    if response:
        print("Successful request")
    else:
        print("Request Failed")
        print(response.status_code)
        print(response.text)
except Exception as e:
    print(" * ERROR: Unable to patch data to {}".format(url))
    print(e)
