#Riedel NMOS Test Tool

This tool creates a simple web service to test against the JTNM February 2018 "Dirty Hands" NMOS checklist.

Currently NMOS-IS-04-01 (Basic) and NMOS-IS-05-01 (Basic) tests are integrated.


##Usage:
Required command line parameters:

--query_ip: the ip of the query service on which the node is currently registered

--query_port: theh port of the query service on which the node is currently registered

e.g. ./nmos-test.py --query_ip=172.56.123.5 --query-port=4480

This tool provides a simple web service which is available on http://localhost:5000.
Provide the NodeUrl (see the detailed description on the webpage) and select a checklist.
The result of the the test will be shown after a couple seconds.

##External dependencies:
- flask 
- wtforms
- jsonschema
- netifaces
- zeroconf