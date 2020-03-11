# Run Test Suites

Tool to run all test suites supported by the DUT, at the highest version they support.

## Installation
To install the dependencies, run the following on a system with Python 3 and Pip installed:

```
pip3 install -r requirements.txt
```

The NMOS Testing tool must be running somewhere on the network

## Usage

```
python3 runTestSuites.py --test <Testing Tool IP & Port> --ip <DUT IS-04 IP> --port <IS-04 API Port> --version <DUT IS-04 Version>
```

Example
```
python3 runTestSuites.py --test http://localhost:5000 --ip 192.168.40.100 --port 80 --version v1.3
```

It is also possible to run the script in a manual mode, where the test suites to be run and the API ports they should be run against are passed in using the `--config` command line option.
This command can also be used to upload results to a Google Sheet automatically.
