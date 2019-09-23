# NMOS UUID Checker
Command line tool to check that NMOS IS-04 UUIDs persist over a reboot

## Installation
To install the dependencies, run the following on a system with Python 3 and Pip installed:

```
pip3 install -r requirements.txt
```

## Usage
To collect an initial set of UUIDs from the Node, run:

```
python3 uuidChecker.py --ip <is-04-ip-address> --port <is-04-api-port> --version <is-04-version>
```

This will save a file called `uuids.json` in the local directory. Once this exists, reboot your Node. Upon reboot, re-run the same command as above to identify any mismatches between the stored UUIDs and the running state.

In order to re-test, delete the `uuids.json` file and repeat the process.
