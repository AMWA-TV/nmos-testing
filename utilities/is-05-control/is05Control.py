#!/usr/bin/env python3

# Copyright (C) 2020 Advanced Media Workflow Association
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
try:
    # Win32
    from msvcrt import getch
except ImportError:
    # UNIX
    def getch():
        import tty
        import termios
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            return sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)


dummy_data = {
    "receiver_id": None,
    "master_enable": False,
    "activation": {
        "mode": "activate_immediate",
        "requested_time": None
    },
    "transport_params": [
        {
            "destination_ip": "239.50.60.1",
            "destination_port": 50050,
            "rtp_enabled": True
        }
    ]
}

dummy_data_7 = {
    "receiver_id": None,
    "master_enable": False,
    "activation": {
        "mode": "activate_immediate",
        "requested_time": None
    },
    "transport_params": [
        {
            "destination_ip": "239.50.60.1",
            "destination_port": 50050,
            "rtp_enabled": True
        },
        {
            "destination_ip": "239.150.60.1",
            "destination_port": 50150,
            "rtp_enabled": True
        }
    ]
}


def set_master_enable(url, state):
    """Set the master enable config to the state"""
    print('Setting master_enable: {}'.format(state))

    body = create_master_enable_body(state)
    send_request(url, body)

def create_master_enable_body(state):
    return {
        "master_enable": state,
        "activation": {
            "mode": "activate_immediate",
            "requested_time": None
        }
    }    

def set_masters_enable(url, uuids, state):
    """Set the master enable config to the state"""
    print('Setting bulk master_enable: {}'.format(state))

    single_body = create_master_enable_body(state)
    body = [{ "id": uuid, "params": single_body } for uuid in uuids]

    send_bulk_request(url, body)

def configure_sender(url, config):
    print('Configuring Sender')
    send_request(url, config)

def create_receiver_body(sender_id, sdp_data):
    body = {
        "sender_id": sender_id,
        "master_enable": True,
        "activation": {
            "mode": "activate_immediate",
            "requested_time": None
        }
    }

    # Add SDP file data to request payload
    if sdp_data:
        print("Using SDP file")
        body["transport_file"] = {"data": sdp_data, "type": "application/sdp"}

    return body

# For simplicity configuring all receivers with the same sender_id
def configure_receivers(url, receiver_ids, sender_id, sdp_datas):
    if len(receiver_ids) != len(sdp_datas):
        print(" * ERROR: Number of provided SDP files does not match numb er of provided receiver UUIDs")
        return
    body = [{ "id": receiver_id, "params": create_receiver_body(sender_id, sdp_datas[idx]) } for idx,receiver_id in enumerate(receiver_ids)]
    send_bulk_request(url, body)

def configure_receiver(url, sender_id, sdp_data):
    print('Configuring Receiver')

    body = create_receiver_body(sender_id, sdp_data)
    send_request(url, body)

def send_request(url, body):
    try:
        response = requests.patch(url, timeout=2, json=body)
        if response.status_code in [200]:
            print("Successful request")
        else:
            print("Request Failed")
            print(response.status_code)
            print(response.text)
    except Exception as e:
        print(" * ERROR: Unable to patch data to {}".format(url))
        print(e)


def send_bulk_request(url, body):
    print("Sending bulk request to", url)
    try:
        response = requests.post(url, timeout=2, json=body)
        if response.status_code in [200]:
            parsed_response = response.json()
            if type(parsed_response) is list:
                for resource_post_result in parsed_response:
                    if resource_post_result["code"] == 200:
                        print("Successfully updated resource", resource_post_result["id"])
                    else:
                        print(" * ERROR: ", resource_post_result)
            else:
                print("Successful request")
        else:
            print("Request Failed")
            print(response.status_code)
            print(response.text)
    except Exception as e:
        print(" * ERROR: Unable to post data to {}".format(url))
        print(e)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ip", required=True, help="IP address or Hostname of DuT")
    parser.add_argument("--port", type=int, default=80, help="Port number of IS-05 API of DuT")
    parser.add_argument("--version", default="v1.1", help="Version of IS-05 API of DuT")
    parser.add_argument("-s", "--sender", action="store_true", help="Configure NMOS Sender")
    parser.add_argument("-ss", "--senders", action="store_true", help="Configure NMOS Senders by bulk operation")
    parser.add_argument("-r", "--receiver", action="store_true", help="Configure NMOS Receiver")
    parser.add_argument("-rr", "--receivers", action="store_true", help="Configure NMOS Receivers by bulk operation")
    parser.add_argument("--request", help="JSON data to be sent in the request to configure sender")
    parser.add_argument("--sdp", action="append", help="SDP file to be sent in the request to configure receiver (parameter can be provided several times for multiple SDPs)")
    parser.add_argument("-u", "--uuid",  action="append", required=True, help="UUID of resource to be configured (parameter can be provided several times for multiple UUIDs)")
    args = parser.parse_args()

    # Configure for Sender or Receiver
    if args.sender:
        print("Configuring NMOS Sender using IS-05")
        url = "http://{}:{}/x-nmos/connection/{}/single/senders/{}/staged".format(
            args.ip,
            args.port,
            args.version,
            args.uuid[0]
        )
    elif args.senders:
        print("Configuring NMOS Senders using IS-05 bulk operation")
        url = "http://{}:{}/x-nmos/connection/{}/bulk/senders".format(
            args.ip,
            args.port,
            args.version,
        )
    elif args.receiver:
        print("Configuring NMOS Receiver using IS-05")
        url = "http://{}:{}/x-nmos/connection/{}/single/receivers/{}/staged".format(
            args.ip,
            args.port,
            args.version,
            args.uuid[0]
        )
    elif args.receivers:
        print("Configuring NMOS Receivers using IS-05 bulk operation")
        url = "http://{}:{}/x-nmos/connection/{}/bulk/receivers".format(
            args.ip,
            args.port,
            args.version,
        )
    else:
        print("Please select either Sender(s) or Receiver(s) mode")
        sys.exit()

    print(url)

    # Read PATCH request JSON
    if args.request:
        if os.path.exists(args.request):
            with open(args.request, "r") as json_file:
                request_payload = json.load(json_file)
        else:
            print("Request file \"{}\" does not exist".format(args.request))
            sys.exit()

    # Read SDP file
    sdp_datas = []
    if args.sdp:
        for single_sdp in args.sdp:
            if os.path.exists(single_sdp):
                with open(single_sdp, "r") as sdp_file:
                    sdp_datas.append(sdp_file.read())
            else:
                print("SDP file \"{}\" does not exist".format(single_sdp))
                sys.exit()

    # Read dummy SDP file
    with open("dummy-sdp.sdp", "r") as sdp_file:
        dummy_sdp_payload = sdp_file.read()

    while True:
        print('\nPress \'e\' to set master_enable True')
        print('Press \'d\' to set master_enable False')
        print('Press \'c\' to set Sender or Receiver to valid config')
        print('Press \'u\' to set Sender or Receiver to dummy config')
        print('Press \'7\' to set 2022-7 Sender to dummy config')

        print('Waiting for input...\n')
        # Check for escape character
        ch = getch()
        if ch in [b'\x03', b'q', '\x03', 'q', 'Q']:
            break

        if ch == 'e':
            if args.senders or args.receivers:
                set_masters_enable(url, args.uuid, True)
            else:
                set_master_enable(url, True)
        elif ch == 'd':
            if args.senders or args.receivers:
                set_masters_enable(url, args.uuid, False)
            else:
                set_master_enable(url, False)
        elif ch == 'c':
            if args.sender or args.senders:
                configure_sender(url, request_payload)
            elif args.receiver:
                configure_receiver(url, "1e1c78ae-1dd2-11b2-8044-cc988b8696a2", sdp_datas[0])
            else:
                configure_receivers(url, args.uuid, "1e1c78ae-1dd2-11b2-8044-cc988b8696a2", sdp_datas)
        elif ch == 'u':
            if args.sender:
                configure_sender(url, dummy_data)
            elif args.receiver:
                configure_receiver(url, "xxxxxxxx-1dd2-xxxx-8044-cc988b8696a2", dummy_sdp_payload)
            else:
                print("Bulk update to dummy config is not supported yet")
        elif ch == '7':
            if args.sender:
                configure_sender(url, dummy_data_7)

    print('Escape character found')
