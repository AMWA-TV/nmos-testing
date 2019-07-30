# mDNS Monitor
Command line tool to monitor for and flag unexpected mDNS announcements.

## Installation
To install the dependencies, run the following on a system with Python 3 and Pip installed:

```
pip3 install -r requirements.txt
```

## Usage
First, edit the `MONITOR_TYPES` and `IP_WHITELIST` parameters in the script to ensure that the desired service types are monitored, and that whitelisted IPs are excluded from monitoring.

To begin monitoring of the desired service types, run:

```
python3 mdnsMonitor.py
```

The script will maintain an on-screen list of any unexpected advertisements present on the network.
