# NMOS IS-05 Control

Command line tool to control an NMOS IS-05 Sender or Receiver.

Allows you to:
* Enable/Disable `master_enable`
* Set sender config
* Set Receiver config

## Installation
To install the dependencies, run the following on a system with Python 3 and Pip installed:

```
pip3 install -r requirements.txt
```

## Usage

```
$ python3 is05Control.py -h

usage: is05Control.py [-h] --ip IP [--port PORT] [--version VERSION] [-s] [-r]
                      [--request REQUEST] [--sdp SDP] -u UUID

optional arguments:
  -h, --help            show this help message and exit
  --ip IP               IP address or Hostname of DuT
  --port PORT           Port number of IS-05 API of DuT
  --version VERSION     Version of IS-05 API of DuT
  -s, --sender          Configure NMOS Sender
  -r, --receiver        Configure NMOS Receiver
  --request REQUEST     JSON data to be sent in the request to configure
                        sender
  --sdp SDP             SDP file to be sent in the request to configure
                        receiver
  -u UUID, --uuid UUID  UUID of resource to be configured
```

Example call to change receiver
```
python3 is05Control.py --ip <hostname or IP> --port <IS-05 Port> --version <IS-05 Version> --receiver --uuid <Receiver ID> --request tune-receiver-to-reference.json --sdp video-1080i-7.sdp
```

Example call to enable sender
```
python3 is05Control.py --ip <hostname or IP> --port <IS-05 Port> --version <IS-05 Version> --sender --uuid <Sender ID> --request sender-to-20-1080i-7.json
```

Inside the script the IS-05 device can be controlled with the following keys
```
Press 'e' to set master_enable True
Press 'd' to set master_enable False
Press 'c' to set Sender or Receiver to valid config
Press 'u' to set Sender or Receiver to dummy config
Press '7' to set 2022-7 Sender to dummy config
Waiting for input...
```
