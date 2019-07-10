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
*   IS-08 Interaction with IS-04
*   IS-09 System API
*   IS-10 Authorization API
*   BCP-003-01 Secure API Communications
*   BCP-003-02 Authorization API (see IS-10)

When testing any of the above APIs it is important that they contain representative data. The test results will generate 'Could Not Test' results if no testable entities can be located. In addition, if device support many modes of operation (including multiple video/audio formats) it is strongly recommended to re-test them in multiple modes.

**Attention:**
*   The IS-04 Node tests create mock registry mDNS announcements on the network unless the `Config.py` `ENABLE_DNS_SD` parameter is set to `False`, or the `DNS_SD_MODE` parameter is set to `'unicast'`. It is critical that these tests are only run in isolated network segments away from production Nodes and registries. Only one Node can be tested at a single time. If `ENABLE_DNS_SD` is set to `False`, make sure to update the Query API hostname/IP and port via `QUERY_API_HOST` and `QUERY_API_PORT` in the `Config.py`.
*   For IS-05 tests #29 and #30 (absolute activation), make sure the time of the test device and the time of the device hosting the tests is synchronized.

## Usage

Ensure pip3 is installed and up to date. Then install the dependencies:

```shell
# Upgrade pip3 to newest version to allow correct installation of requirements
pip3 install --upgrade pip
# Install the dependencies
pip3 install -r requirements.txt
```

Start the service as follows:

```shell
# Start the Test Suite
python3 nmos-test.py
```

This tool provides a simple web service which is available on `http://localhost:5000`.
Provide the URL of the relevant API under test (see the detailed description on the webpage) and select a test suite from the checklist. The result of the tests will be shown after a few seconds.

The result of each test case will be one of the following:

| Pass | Reason |
| - | - |
| ![Pass](https://place-hold.it/128x32/28a745.png?text=Pass&fontsize=12&bold) | Successful test case. |
| ![Fail](https://place-hold.it/128x32/dc3545.png?text=Fail&fontsize=12&bold) | Required feature of the specification has been found to be implemented incorrectly. |
| ![Warning](https://place-hold.it/128x32/ffc107.png?text=Warning&fontsize=12&bold) | Not a failure, but the API being tested is responding or configured in a way which is not recommended in most cases. |
| ![Test Disabled](https://place-hold.it/128x32/ffc107.png?text=Test%20Disabled&fontsize=12&bold) | Test is disabled due to test suite configuration; change the config or test manually. |
| ![Could Not Test](https://place-hold.it/128x32/ffc107.png?text=Could%20Not%20Test&fontsize=12&bold) | Test was not run due to prior responses from the API, which may be OK, or indicate a fault. |
| ![Not Implemented](https://place-hold.it/128x32/ffc107.png?text=Not%20Implemented&fontsize=12&bold) | Recommended/optional feature of the specifications has been found to be not implemented. |
| ![Manual](https://place-hold.it/128x32/007bff.png?text=Manual&fontsize=12&bold) | Test suite does not currently test this feature, so it must be tested manually. |
| ![Not Applicable](https://place-hold.it/128x32/6c757d.png?text=Not%20Applicable&fontsize=12&bold) | Test is not applicable, e.g. due to the version of the specification being tested. |

### Testing Unicast discovery

In order to test unicast discovery, the test suite launches its own mock DNS server which your Node will need to be pointing at in order to correctly discover the mock registries. The following steps should be completed to operate in this mode:

*   Ensure the `DNS_SD_MODE` in the test tool's `Config.py` file is set to `'unicast'` before running the testing tool.
*   Configure the DNS search domain for your Node to be `testsuite.nmos.tv` (either manually or by providing this to your Node via DHCP).
*   Configure the DNS server IP address for your Node to be the IP address of the host which is running the testing tool (either manually or by providing this to your Node via DHCP).

Unicast DNS advertisements for registries only become available once tests are running. As a result the unit under test may need prompting to re-scan the DNS server for records at this point. The `DNS_SD_ADVERT_TIMEOUT` config parameter may be used to increase the period which the test suite waits for in this situation.

If your network requires the use of the proxy server, you may find it necessary to disable this configuration on the host running the test suite and on the unit under test when using unicast DNS. This is because any requests to fully qualified hostnames are likely to be directed to your proxy server, which will be unable to resolve them.

### Testing BCP-003-01 TLS

Testing of certain aspects of BCP-003-01 makes use of an external tool 'testssl.sh'. Please see [testssl/README.md](testssl/README.md) for installation instructions.

In order to ease testing of TLS with the various specifications, sample certificates are provided in this repository. Please see [test_data/BCP00301/README.md](test_data/BCP00301/README.md) for their details and installation guidance.

### Testing IS-10 Authorization

When testing IS-10 / BCP-003-02 implementations, ensure that a user is registered with the Authorization Server with a username and password that corresponds with the `AUTH_USERNAME` and `AUTH_PASSWORD` config options in the `Config.py` file. These values should be changed to sensible values before running the IS-10 tests.

When testing the authorization code grant, the means by which consent is given by the resource owner will be implementation-specific. The contents of the file `/test_data/IS1001/authorization_request_data.json` will be used as the body of the request to the authorization endpoint. Please edit this to comply with the implementation under test.

### Testing of SDP files

IS-05 test_41 checks that SDP files conform to the expectations of ST.2110. In order to enable these tests, please ensure that [SDPoker](https://github.com/Streampunk/sdpoker) is available on your system.

### Non-Interative Mode

The test suite supports non-interactive operation in order use it within continuous integration systems. An example of this usage can be seen below:

```shell
# List the available test suites
python3 nmos-test.py --list-suites

# List the available tests for a given test suite
python3 nmos-test.py suite IS-04-02 --list-tests

# Run just the 'auto' tests for the given suite, saving the output as a JUnit XML file
python3 nmos-test.py suite IS-04-02 --selection auto --host 128.66.12.5 128.66.12.6 --port 80 80 --version v1.2 v1.2 --ignore auto_5 auto_6 --output results.xml
```

To display additional information about the available command-line options:

```shell
# Show the usage
python3 nmos-test.py -h

# Show the specific options for the 'suite' command
python3 nmos-test.py suite -h
```

## External Dependencies

*   Python 3
*   Git
*   [testssl.sh](https://testssl.sh) (required for BCP-003-01 testing)
*   [OpenSSL](https://www.openssl.org/) (required for BCP-003-01 OCSP testing)
*   [SDPoker](https://github.com/Streampunk/sdpoker) (required for IS-05 SDP testing)
*   See [requirements.txt](requirements.txt) for additional packages

## Known Issues

### Ramlfications Parsing

Ramlfications trips up over the 'traits' used in some of the NMOS specifications. Until this is resolved in the library, we overwrite cases of this keyword in the RAML files.

## Adding New Tests

This test suite is intended to be straightforward to extend. If you encounter an implementation which is operating outside of the specification and the current test suite does not identify this behaviour, please consider adding a test as follows:

1.  First, raise an Issue against this repository. Even if you do not have the time to write additional tests, a good explanation of the issue identified could allow someone else to do so on your behalf.
2.  Once an issue has been raised, feel free to assign it to yourself. We would welcome any Pull Requests which add to the set of tests available. Once a Pull Request is raised, one of the specification maintainers will review it before including it in the test suite.

## Test Suite Structure

All test classes inherit from `GenericTest` which implements some basic schema checks on GET/HEAD/OPTIONS methods from the specification. It also provides access to a 'Specification' object which contains a parsed version of the API RAML, and provides access to schemas for the development of additional tests.

Each manually defined test case is expected to be defined as a method starting with `test_`, taking an object of class `Test`. This will allow it to be automatically discovered and run by the test suite.
The return type for each test case must be the result of calling one of the methods on the `Test` object shown below.

*   The first argument, `details`, is used to specify the reason for the test result.
  It is required for `FAIL`, `OPTIONAL` (Not Implemented), or `NA` (Not Applicable), and is recommended for all cases other than a straightforward `PASS`.

*   The second argument, `link`, is optional. It may be used to specify a link to more information, such as to a sub-heading on one of the NMOS Wiki [Specifications](https://github.com/AMWA-TV/nmos/wiki/Specifications) pages.
  It is recommended especially to provide further explanation of the effect of an `OPTIONAL` feature being unimplemented.

Examples of each result are included below:

```python
from TestResult import Test

def test_my_stuff(self, test):
    """My test description"""

    # Test code
    if test_passed:
        return test.PASS()
    elif test_failed:
        return test.FAIL("Reason for failure")
    elif test_warning:
        return test.WARNING("Reason the API configuration or response is not recommended")
    elif test_disabled:
        return test.DISABLED("Explanation of why the test is disabled and e.g. how to change the test suite "
                             "config to allow it to be run")
    elif test_could_not_test:
        return test.UNCLEAR("Explanation of what prior responses prevented this test being run")
    elif test_not_implemented:
        return test.OPTIONAL("Explanation of what wasn't implemented, and why you might require it",
                             "https://github.com/AMWA-TV/nmos/wiki/Specifications#what-is-required-vs-optional")
    elif test_manual:
        return test.MANUAL("Explanation of why the test is not (yet) tested automatically, and e.g. how to "
                           "run it manually")
    elif test_not_applicable:
        return test.NA("Explanation of why the test is not applicable, e.g. due to the version of the "
                       "specification being tested")
```

The following methods may be of use within a given test definition.

**Requesting from an API**
```python
# All keyword parameters are optional
# Where 'json' is the body of the request in json and 'data' is the body as url encoded form data
self.do_request(method, url, json=json, data=data, headers=headers, auth=auth)
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
