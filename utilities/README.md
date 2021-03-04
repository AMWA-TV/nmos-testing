# NMOS Testing Utilities

A collection of utilities which may aid testing, but are not directly part of the testing tool.

* [<abbr title="Device under Test">DuT</abbr> Data Exporter](dut-data-exporter): Extracts data required for testing TR-1001-1 from the Device under Test
* [Run Test Suites](run-test-suites): Run all appropriate test suites against the Device Under Test, downloading the JSON results file to a local directory
* [Google Sheets Test Result Importer](run-test-suites/gsheetsImport): Imports JSON format test results from the AMWA NMOS Testing Tool into a Google spreadsheet.
* [IS-05 Control](is-05-control): Performs simple interactions with the IS-05 API in order to configure a single Sender or Receiver.
* [mDNS Monitor](mdns-monitor): Maintains a list of specific mDNS service types advertised by unexpected IP addresses.
* [UUID Checker](uuid-checker): Records an NMOS Node's resource UUIDs and compares them to those advertised after a reboot.
