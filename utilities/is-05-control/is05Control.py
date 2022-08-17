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

    body = {
        "master_enable": state,
        "activation": {
            "mode": "activate_immediate",
            "requested_time": None
        }
    }

    send_patch_request(url, body)


def configure_sender(url, config):
    print('Configuring Sender')
    send_patch_request(url, config)


def configure_receiver(url, sender_id, sdp_data):
    print('Configuring Receiver')

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

    send_patch_request(url, body)

def send_get_request(url):
    try:
        response = requests.get(url, timeout=2)
        if response.status_code in [200]:
            print("Successful GET request\n")
            rep=response.headers['content-type']
            if 'json' in rep:
                return response.json()
            elif 'sdp' in rep:
                return response.text
            else:
                print(response)
                return response
        else:
            print("GET Request Failed\n")
            print(response.status_code)
            print(response.text)
    except Exception as e:
        print(" * ERROR: Unable to get data to {}".format(url))
        print(e)

def send_patch_request(url, body):
    try:
        response = requests.patch(url, timeout=2, json=body)
        if response.status_code in [200]:
            print("Successful PATCH request. Response body:\n")
            print(json.dumps(response.json(), indent=4))
        else:
            print("PATCH Request Failed\n")
            print(response.status_code)
            print(response.text)
    except Exception as e:
        print(" * ERROR: Unable to patch data to {}".format(url))
        print(e)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ip", required=True, help="IP address or Hostname of DuT")
    parser.add_argument("--port", type=int, default=80, help="Port number of IS-05 API of DuT")
    parser.add_argument("--version", default="v1.1", help="Version of IS-05 API of DuT")
    parser.add_argument("-s", "--sender", action="store_true", help="Configure NMOS Sender")
    parser.add_argument("-r", "--receiver", action="store_true", help="Configure NMOS Receiver")
    parser.add_argument("--request", help="JSON data to be sent in the request to configure sender")
    parser.add_argument("--sdp", help="SDP file to be queried from a Sender (write) or be sent to a Receiver (read)")
    parser.add_argument("-u", "--uuid", required=True, help="UUID of resource to be configured")
    args = parser.parse_args()

    # Configure for Sender or Receiver
    if args.sender:
        print("Configuring NMOS Sender using IS-05")
        url = "http://{}:{}/x-nmos/connection/{}/single/senders/{}".format(
            args.ip,
            args.port,
            args.version,
            args.uuid
        )
    elif args.receiver:
        print("Configuring NMOS Receiver using IS-05")
        url = "http://{}:{}/x-nmos/connection/{}/single/receivers/{}".format(
            args.ip,
            args.port,
            args.version,
            args.uuid
        )
    else:
        print("Please select either Sender or Receiver mode")
        sys.exit()

    print(url)
    url_staged = url + '/staged'
    url_transport = url + '/transportfile'

    # Read PATCH request JSON
    if args.request:
        if os.path.exists(args.request):
            with open(args.request, "r") as json_file:
                request_payload = json.load(json_file)
        else:
            print("Request file \"{}\" does not exist".format(args.request))
            sys.exit()

    # Check SDP file
    sdp_filename = args.sdp if args.sdp else "latest.sdp"

    # Read dummy SDP file
    with open("dummy-sdp.sdp", "r") as sdp_file:
        dummy_sdp_payload = sdp_file.read()

    while(True):
        print('\nPress \'e\' to set master_enable True')
        print('Press \'d\' to set master_enable False')
        print('Press \'c\' to set a valid config on a Sender or a Receiver')
        print('Press \'u\' to set a dummy config on a Sender or a Receiver')
        print('Press \'7\' to set 2022-7 Sender to dummy config')
        print('Press \'s\' to get SDP file (and save to "./{}" from a Sender)'.format(sdp_filename))

        print('Waiting for input...\n')
        # Check for escape character
        ch = getch()
        if ch in [b'\x03', b'q', '\x03', 'q', 'Q']:
            break

        # Reload

        if ch == 'e':
            set_master_enable(url_staged, True)
        elif ch == 'd':
            set_master_enable(url_staged, False)
        elif ch == 'c':
            if args.sender:
                configure_sender(url_staged, request_payload)
            else:
                if os.path.exists(sdp_filename):
                    with open(sdp_filename, "r") as sdp_file:
                        sdp_payload = sdp_file.read()
                        configure_receiver(url_staged, "1e1c78ae-1dd2-11b2-8044-cc988b8696a2", sdp_payload)
                else:
                    print("SDP file not found: {}".format(sdp_filename))
        elif ch == 'u':
            if args.sender:
                configure_sender(url_staged, dummy_data)
            else:
                configure_receiver(url_staged, "aaaaaaaa-1dd2-11b2-8044-cc988b8696a2", dummy_sdp_payload)
        elif ch == '7':
            if args.sender:
                configure_sender(url_staged, dummy_data_7)
        elif ch == 's':
            if args.sender:
                sdp = send_get_request(url_transport)
                print(sdp)
                with open(sdp_filename, "w") as sdp_file:
                    sdp_file.write(sdp)
                print("----------------------> Saved to ./{}".format(sdp_filename))
            else:
                rep = send_get_request(url_staged)
                print(rep ["transport_file"]["data"])

    print('Escape character found')
