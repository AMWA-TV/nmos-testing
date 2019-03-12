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
*   The IS-04 Node tests create mock registry mDNS announcements on the network unless the `Config.py` `ENABLE_DNS_SD` parameter is set to `False`, or the `DNS_SD_MODE` parameter is set to `'unicast'`. It is critical that these tests are only run in isolated network segments away from production Nodes and registries. Only one Node can be tested at a single time. If `ENABLE_DNS_SD` is set to `False`, make sure to update the Query API hostname/IP and port via `QUERY_API_HOST` and `QUERY_API_PORT` in the `Config.py`.
*   For IS-05 tests #29 and #30 (absolute activation), make sure the time of the test device and the time of the device hosting the tests is synchronized.

## Usage

Install the dependencies with `pip3 install -r requirements.txt` and start the service as follows:

```shell
python3 nmos-test.py
```

This tool provides a simple web service which is available on `http://localhost:5000`.
Provide the URL of the relevant API under test (see the detailed description on the webpage) and select a test suite from the checklist. The result of the tests will be shown after a few seconds.

The result of each test case will be one of the following:

| Pass | Reason |
| - | - |
| ![Pass](https://place-hold.it/128x32/28a745.png?text=Pass&fontsize=12&bold)| Successful test case. | 
| ![Fail](https://place-hold.it/128x32/dc3545.png?text=Fail&fontsize=12&bold) | Required feature of the specification has been found to be implemented incorrectly. |
| ![Warning](https://place-hold.it/128x32/ffc107.png?text=Warning&fontsize=12&bold) | Not a failure, but the API being tested is responding or configured in a way which is not recommended in most cases. |
| ![Test Disabled](https://place-hold.it/128x32/ffc107.png?text=Test%20Disabled&fontsize=12&bold) | Test is disabled due to test suite configuration; change the config or test manually. |
| ![Could Not Test](https://place-hold.it/128x32/ffc107.png?text=Could%20Not%20Test&fontsize=12&bold) | Test was not run due to prior responses from the API, which may be OK, or indicate a fault. |
| ![Not Implemented](https://place-hold.it/128x32/ffc107.png?text=Not%20Implemented&fontsize=12&bold) | Recommended/optional feature of the specifications has been found to be not implemented. |
| ![Manual](https://place-hold.it/128x32/007bff.png?text=Manual&fontsize=12&bold) | Test suite does not currently test this feature, so it must be tested manually. |
| ![Not Applicable](https://place-hold.it/128x32/6c757d.png?text=Not%20Applicable&fontsize=12&bold) | Test is not applicable, e.g. due to the version of the specification being tested. |

### Testing Unicast discovery

In order to test unicast discovery, ensure the `DNS_SD_MODE` is set to `'unicast'`. Additionally, ensure that the unit under test has its search domain set to 'testsuite.nmos.tv' and the DNS server IP to the IP address of the server which is running the test suite instance.

### Non-Interative Mode

The test suite supports non-interactive operation in order use it within continuous integration systems. An example of this usage can be seen below:

```shell
# List the available tests for a given test definition
python3 nmos-test.py --suite IS-04-02 --list

# Run a test set, saving the output as a JUnit XML file
python3 nmos-test.py --suite IS-04-02 --selection auto --ip 128.66.12.5 128.66.12.6 --port 80 80 --version v1.2 v1.2 --ignore auto_5 auto_6 --output results.xml
```

## External Dependencies

*   Python 3
*   Git
*   See [requirements.txt](requirements.txt) for additional packages

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
from TestResult import Test

def test_my_stuff(self):
    test = Test("My test description")
    # Test code
    if test_passed:
        return test.PASS("Successful test case.")
    elif test_failed:
        return test.FAIL("Required feature of the specification has been found to be "
                         "implemented incorrectly")
    elif test_warning:
        return test.WARNING("Not a failure, but the API being tested is responding "
                            "or configured in a way which is not recommended in most cases.")
    elif test_disabled:
        return test.DISABLED("Test is disabled due to test suite configuration; change the "
                             "config or test manually.")
    elif test_could_not_test:
        return test.UNCLEAR("Test was not run due to prior responses from the API, which "
                            "may be OK, or indicate a fault.")
    elif test_not_implemented:
        return test.OPTIONAL("Recommended/optional feature of the specifications has been "
                             "found to be not implemented.")
    elif test_manual:
        return test.MANUAL("Test suite does not currently test this feature, so it must be "
                           "tested manually.")
    elif test_not_applicable:
        return test.NA("Test is not applicable, e.g. due to the version of the specification "
                       "being tested.")
```

The following methods may be of use within a given test definition.

**Requesting from an API**
```python
self.do_request(method, url, data)
```
Returns a tuple of the request status (True/False) and a Requests library Response object.

**Testing an API's response**
```python
self.check_response(schema, method, response)
```
Return a tuple of the test status (True/False) and a string indicating the error in the case this is False.

**Accessing response schemas**
```python
self.get_schema(api_name, method, path, status_code)
```
Returns a JSON schema, or None if it is unavailable.

**Validating a JSON schema**
```python
self.validate_schema(payload, schema)
```
Raises an exception upon validation failure.

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
