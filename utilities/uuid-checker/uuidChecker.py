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

parser = argparse.ArgumentParser()
parser.add_argument("--ip", required=True)
parser.add_argument("--port", type=int, required=True)
args = parser.parse_args()

if os.path.exists("uuids.json"):
    print(" * Found existing UUIDs file. Comparing with Node")
    first_run = False
else:
    print(" * No existing UUIDs file found. Fetching fresh from Node")
    first_run = True

fetched_uuids = {"self": None, "devices": [], "sources": [], "flows": [],
                 "senders": [], "receivers": []}
for path in fetched_uuids.keys():
    try:
        url = "http://{}:{}/x-nmos/node/v1.2/{}".format(args.ip, args.port, path)
        response = requests.get(url, timeout=2)
        if path == "self":
            print("Host: {}".format(response.json()["description"]))
            fetched_uuids[path] = response.json()["id"]
        else:
            for resource in response.json():
                fetched_uuids[path].append(resource["id"])
    except Exception:
        print(" * ERROR: Unable to fetch data from {}".format(url))

if first_run:
    with open("uuids.json", "w") as json_file:
        json.dump(fetched_uuids, json_file)
else:
    test_result = True
    with open("uuids.json", "r") as json_file:
        previous_uuids = json.load(json_file)

    for path in fetched_uuids.keys():
        if path == "self":
            if fetched_uuids[path] != previous_uuids[path]:
                print("* Current Node ID '{}' does not match previous Node ID '{}'"
                      .format(fetched_uuids[path], previous_uuids[path]))
                test_result = False
        else:
            if sorted(fetched_uuids[path]) != sorted(previous_uuids[path]):
                print("* Current {} '{}' do not match previous {} '{}'"
                      .format(path.capitalize(), sorted(fetched_uuids[path]),
                              path.capitalize(), sorted(previous_uuids[path])))
                test_result = False

    if test_result is True:
        print(" * TEST PASSED")
    else:
        print(" * TEST FAILED")
