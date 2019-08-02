# Device Under Test Data Exporter

Tool to gather data from DuT such as Receiver/Sender ID, IS-05/08 Port Numbers and Interface MAC addresses. The gathered data will be printed to the screen.

## Installation
To install the dependencies, run the following on a system with Python 3 and Pip installed:

```
pip3 install -r requirements.txt
```

## Usage

```
python3 dutDataExporter.py --ip <is-04-ip-address> --port <is-04-api-port>
```
