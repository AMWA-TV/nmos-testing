# NMOS IS-05 Control

Command line tool to control an NMOS IS-05 Sender or Receiver.

Allows you to:
* Enable/Disable `master_enable`
* Set Sender config
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
  --request REQUEST     JSON data to be sent in the request to configure sender
  --sdp SDP             SDP file to be queried from a Sender (write) or be sent to a Receiver (read)
  -u UUID, --uuid UUID  UUID of resource to be configured
```

Inside the script the IS-05 device can be controlled with the following keys
```
Press 'e' to set master_enable True
Press 'd' to set master_enable False
Press 'c' to set a valid config on a Sender or a Receiver
Press 'u' to set a dummy config on a Sender or a Receiver
Press '7' to set 2022-7 Sender to dummy config
Press 's' to get SDP file (and save to  "./latest.sdp" from a Sender)
Waiting for input...
```

## Example: create a media connection

1. Connect to a sender:

```
python3 is05Control.py --ip <hostname or IP> --port <IS-05 Port> --version <IS-05 Version> --sender --uuid <Sender ID> --request sender-to-20-1080i-7.json --sdp new.sdp
```

2. Enable (`e`)
3. Push a valid RTP config (`c`)
4. Save SDP file (`s`)
5. Connect to a receiver:

```
python3 is05Control.py --ip <hostname or IP> --port <IS-05 Port> --version <IS-05 Version> --receiver --uuid <Receiver ID> --sdp new.sdp
```

6. Enable (`e`)
7. Push the new SDP (`c`)
