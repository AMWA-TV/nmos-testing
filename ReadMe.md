# Riedel NMOS Test Tool

This tool creates a simple web service to test against the JTNM February 2018 "Dirty Hands" NMOS checklist.

Currently NMOS-IS-04-01 (Basic) and NMOS-IS-05-01 (Basic) tests are integrated.

**Attention:**
The NMOS-IS-04-01 test only works if the target node is in registered mode. The registration service endpoint has to be specified on program startup (see section "Usage"). For testing purposes a reference implementation of the RDS is provided by the BBC (https://github.com/bbc/nmos-discovery-registration-ri).

## Usage:
Required command line parameters:

--query_ip: the ip of the query service on which the node is currently registered (RDS) 

--query_port: the port of the query service on which the node is currently registered (RDS) 

e.g. python nmos-test.py --query_ip=172.56.123.5 --query-port=4480

This tool provides a simple web service which is available on http://localhost:5000.
Provide the NodeUrl (see the detailed description on the webpage) and select a checklist.
The result of the the test will be shown after a couple seconds.

Tested with Firefox 58 and Chrome 63.

##  External dependencies:
- Python3

Python packages:
- flask 
- wtforms
- jsonschema
- zeroconf
- requests

