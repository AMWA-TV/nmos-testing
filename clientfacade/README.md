## Installation & Usage

`python3 ClientFacade.py`

Should be available on 127.0.0.1:5001

## Test processes

### Semi-automated tests:

1. Run nmos-test.py and choose JTNM Client Tests 
3. Run ClientFacade.py to launch Client Façade. Client Façade will periodically check for new test questions/answers
4. On NMOS Testing Tool enter IP address and Port where Client Façade is running
5. Choose tests and click Run
6. Test suite POSTs json with test details to Client Façade API endpoint '/x-nmos/client-testing'

```
{
    'test_type': 'radio' (single answer), 'checkbox' (potentially multiple answers) or 'action' (instructions only)
    'name': name from test method,
    'description': docstring from test method,
    'question': question from question variable in test method (str),
    'answers': answers from answers variable in test method (list),
    'time_sent': time.time(),
    'timeout': time in seconds for test suite to wait for answer to be POSTed to url_for_response
    'url_for_response': url of test suite API endpoint to signal an answer has been posted,
    'answer_response': empty string,
    'time_answered': empty string
}
```
    Then waits for period of timeout to receive a POST to the url_for_response API endpoint 

7. Client Façade saves the json in a data store and presents question, answers and timer to Test User.
8. Client Façade will POST to url_for_response with updated json including chosen answer(s) in answer_response
9. Test suite url_for_response endpoint saves json and signals to NMOS Testing Tool that answer has been received. Answer is verified and result registered.
10. Test suite moves on to next test and repeats 6-9 until all chosen tests are completed.
11. After last test, test suite will POST a clear request to the client testing API to empty the data store
12. Results are displayed on NMOS Testing Tool

### Fully automated tests:
Will need to have endpoint for 'x-nmos/client-testing' to receive questions and some method of storing the json. Then add the answer_response and POST back to url_for_response

## Notes

### NMOS Testing Tool Test Selection
Note that the "auto" test selection, although present, doesn't do anything presently as there is no RAML associated with the client tests.

### Known Issues
There are few known issues that can occur if the NMOS Testing Tool, or the Client Façade are unexpectedly stopped/restarted while tests are in progress
* Restarting the NMOS Testing Tool and re-running the JT-NM Client tests will necessitate a browser refresh of the Client Façade to update the Test Question being displayed
* If the NMOS Testing Tool is closed in the middle of testing, and the Client Façade is allowed to timeout the current question, the Client Façade will get stuck in a refresh loop

Other issues
* With checkbox tests in the Client Façade you currently have to select at least one option before it will move to the next test. Selecting zero options will not allow you to proceed
* The Mock Registry is currently open to registrations from any NMOS Node. Therefore NMOS Nodes on your network searching for a Registry are likely to register with the Mock Registry.
