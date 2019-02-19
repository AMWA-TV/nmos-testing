# NMOS API Testing Tool

This tool creates a simple web service which tests implementations of the NMOS APIs.

The following test sets are currently supported:
*   IS-04 Node API
*   IS-04 Registry APIs
*   IS-04 Node API (Peer to Peer)
*   IS-05 Connection Management API
*   IS-05 Interaction with IS-04
*   IS-06 Network Control API
*   IS-07 Event & Tally API
*   IS-08 Channel Mapping API

When testing any of the above APIs it is important that they contain representative data. The test results will generate 'N/A' results if no testable entities can be located. In addition, if device support many modes of operation (including multiple video/audio formats) it is strongly recommended to re-test them in multiple modes.

**Attention:**
*   The IS-04 Node tests create a mock registry on the network unless the Config.py ENABLE_MDNS parameter is set to False. It is critical that these tests are only run in isolated network segments away from production Nodes and registries. Only one Node can be tested at a single time.
*   For IS-05 tests #29 and #30 (absolute activation), make sure the time of the test device and the time of the device hosting the tests is synchronized.

## Usage

```
$ python3 nmos-test.py
```

This tool provides a simple web service which is available on `http://localhost:5000`.
Provide the URL of the relevant API under test (see the detailed description on the webpage) and select a test from the checklist. The result of the test will be shown after a few seconds.

## External Dependencies

*   Python 3

Python packages:
*   flask
*   wtforms
*   jsonschema
*   zeroconf-monkey
*   requests
*   netifaces
*   gitpython
*   ramlfications
*   jsonref
*   websocket-client

## Known Issues

### Ramlfications Parsing

Ramlfications trips up over the 'traits' used in some of the NMOS specifications. Until this is resolved in the library, we overwrite cases of this keyword in the RAML files.

## Adding New Tests

This test suite is intended to be straightforward to extend. If you encounter an implementation which is operating outside of the specification and the current test suite does not identify this behaviour, please consider adding a test as follows:

1.  First, raise an Issue against this repository. Even if you do not have the time to write additional tests, a good explanation of the issue identified could allow someone else to do so on your behalf.
2.  Once an issue has been raised, feel free to assign it to yourself. We would welcome any Pull Requests which add to the set of tests available. Once a Pull Request is raised, one of the specification maintainers will review it before including it in the test suite.

## Test Suite Structure

All test classes inherit from 'GenericTest' which implements some basic schema checks on GET/HEAD/OPTIONS methods from the specification. It also provides access to a 'Specification' object which contains a parsed version of the API RAML, and provides access to schemas for the development of additional tests.

Each manually defined test is expected to be defined as a method starting with 'test_'. This will allow it to be automatically discovered and run by the test suite. The return type for each test must be the result of calling one of the following methods on an object of class Test. An example is included below:

```python
from TestHelper import Test

def test_my_stuff(self):
    test = Test("My test description")

    if test_passed:
        # Pass the test
        return test.PASS()
    elif test_failed:
        # Fail the test
        return test.FAIL("Reason for failure")
    elif test_manual:
        # Test must be performed manually
        return test.MANUAL()
    elif test_na:
        # Test is not applicable to this implementation
        return test.NA("Reason for non-testing")
    elif test_optional:
        # Test found an optional aspect of the spec which wasn't implemented
        return test.OPTIONAL("What wasn't implemented, and why you might require it")
```

The following methods may be of use within a given test definition.

**Requesting from an API**
```python
self.do_request(method, url, data)
```
Returns a tuple of the request status (True/False) and a Requests library Response object.

**Testing an API's response**
```python
self.check_response(api_name, schema, method, response)
```
Return a tuple of the test status (True/False) and a string indicating the error in the case this is False.

**Accessing response schemas**
```python
self.get_schema(api_name, method, path, status_code)
```
Returns a JSON schema, or None if it is unavailable.

## Testing a New Specification

When adding tests for a completely new API, the first set of basic tests have already been written for you. Provided a specification is available in the standard NMOS layout (using RAML 1.0), the test suite can automatically download and interpret it. Simply create a new test file which looks like the following:

```python
from GenericTest import GenericTest


class MyNewSpecTest(GenericTest):
    """
    Runs MyNewSpecTest
    """
    def __init__(self, apis):
        GenericTest.__init__(self, apis)
```
