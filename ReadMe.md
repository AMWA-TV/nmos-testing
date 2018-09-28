>**Work in Progress!!** We intend to contribute this back under the AMWA GitHub organisation once it reaches an initial usable state.


# NMOS API Testing Tool

This tool creates a simple web service which tests implementations of the NMOS APIs.

The following tests sets are currently supported:
*   IS-04 Node API
*   IS-04 Registry APIs
*   IS-05 Connection Management API
*   IS-06 Network Control API

**Attention:**
*   The IS-04 Node tests create a mock registry on the network. It is critical that these are only run in isolated network segments away from production Nodes and registries. Only one Node can be tested at a single time.
*   For IS-05 tests #29 and #30 (absolute activation), make sure the time of the test device and the time of the device hosting the tests is synchronized.

## Usage:
```
$ python3 nmos-test.py
```

This tool provides a simple web service which is available on `http://localhost:5000`.
Provide the URL of the relevant API under test (see the detailed description on the webpage) and select a test from the checklist. The result of the test will be shown after a few seconds.

## External dependencies:
-   Python 3

Python packages:
-   flask
-   wtforms
-   jsonschema
-   zeroconf
-   requests
-   gitpython
-   ramlifications

## Known Issues
Ramlfications trips up over the 'traits' used in some of the NMOS specifications. Until we can resolve this properly, the following can be used as a workaround.

In file 'ramlfications/utils.py', insert the following code into the top of the function '_remove_duplicates' which starts at line 495:

```
    if not resource_params:
        return None

```
