# NMOS IS-05 Control
Command line tool to control an NMOS IS-05 Sender or Receiver. 

## Installation
To install the dependencies, run the following on a system with Python 3 and Pip installed:

```
pip3 install -r requirements.txt
```

## Usage

```
$ python3 is05Control.py -h
usage: is05Control.py [-h] --ip IP --port PORT [--sender] [--receiver] [-e]
                      [-d] -r REQUEST [-s SDP] -u UUID

optional arguments:
  -h, --help            show this help message and exit
  --ip IP               IP address or Hostname of DuT
  --port PORT           Port number of IS-05 API of DuT
  --sender              Configure NMOS Sender
  --receiver            Configure NMOS Receiver
  -e, --enable          Set master_enable=True
  -d, --disable         Set master_enable=False
  -r REQUEST, --request REQUEST
                        Patch file to be sent in the request
  -s SDP, --sdp SDP     SDP file to be sent in the request
  -u UUID, --uuid UUID  UUID of resource to be configured
```

Example call to change receiver
```
python3 is05Control.py --receiver --ip <hostname or IP> --port 80 --uuid <Receiver ID> --request example_receiver_patch.json --sdp sdp.sdp
```

Example call to enable sender
```
python3 is05Control.py --sender --ip <hostname or IP> --port 80 --uuid <Sender ID> --request example_sender_patch.json
```

NOTE: R&D proxy cannot handle PATCH request, so make sure no_proxy value is set correctly

