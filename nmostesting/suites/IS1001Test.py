# Copyright (C) 2019 Advanced Media Workflow Association
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import json
import socket
import requests
from time import sleep
from urllib.parse import parse_qs
from OpenSSL import crypto

from ..GenericTest import GenericTest, NMOSTestException, NMOSInitException
from .. import Config as CONFIG
from zeroconf_monkey import ServiceBrowser, Zeroconf
from ..MdnsListener import MdnsListener

AUTH_API_KEY = 'auth'
GRANT_SCOPES = ['is-04', 'is-05']


class IS1001Test(GenericTest):
    """
    Runs IS-10-01-Test.

    Example "apis" Object:
    {'auth': {
      'raml': 'AuthorizationAPI.raml',
      'version': 'v1.0',
      'hostname': 'example.co.uk',
      'port': 80,
      'spec_branch': 'v1.0-dev',
      'spec_path': 'cache/is-10',
      'base_url': 'http://example.co.uk:80',
      'name': 'Authorization API',
      'ip': '127.0.1.1',
      'url': 'http://example.co.uk:80/x-nmos/auth/v1.0/',
      'spec': <Specification.Specification object at 0x7f5b3b0719b0>
    }}
  """

    def __init__(self, apis):
        super(IS1001Test, self).__init__(apis)
        if not CONFIG.ENABLE_HTTPS:
            raise NMOSInitException("IS-10 can only be tested when ENABLE_HTTPS is set to True in UserConfig.py")
        self.url = self.apis[AUTH_API_KEY]["url"]
        self.bearer_tokens = []
        self.client_data = {}
        self.auth_codes = []
        self.clients = []  # List of all registered clients for deleting during clean-up

        self.zc = Zeroconf()
        self.zc_listener = MdnsListener(self.zc)

    def set_up_tests(self):
        """Print reminder to Add User to Authorization Server"""

        print("""
            Ensure a User is already set-up on the Authorization Server that corresponds
            to the 'AUTH_USERNAME' and 'AUTH_PASSWORD' config options. They are currently:
            AUTH_USERNAME: '{}'
            AUTH_PASSWORD: '{}'
        """.format(CONFIG.AUTH_USERNAME, CONFIG.AUTH_PASSWORD))

    def tear_down_tests(self):
        """Print reminder to Delete Registered Client from Authorization Server"""

        print("Remember to delete the registered client with username: {}".format(CONFIG.AUTH_USERNAME))

    def _make_auth_request(self, method, url_path, data=None, auth=None, params=None):
        """Utility function for making requests with Basic Authorization"""
        if auth == "user":
            username = CONFIG.AUTH_USERNAME
            password = CONFIG.AUTH_PASSWORD
        elif auth == "client" and self.client_data:
            username = self.client_data["client_id"]
            password = self.client_data["client_secret"]
        else:
            username = password = None
        return self.do_request(method=method, url=self.url + url_path,
                               data=data, auth=(username, password), params=params)

    def _post_to_authorize_endpoint(self, data, parameters, auth="user"):
        """Post to /authorize endpoint, not allowing redirects to be automatically followed"""
        if auth == "user":
            username = CONFIG.AUTH_USERNAME
            password = CONFIG.AUTH_PASSWORD
        elif auth == "client" and self.client_data:
            username = self.client_data["client_id"]
            password = self.client_data["client_secret"]
        else:
            username = password = None
        return requests.post(url=self.url + 'authorize', data=data, params=parameters,
                             allow_redirects=False, auth=(username, password), verify=CONFIG.CERT_TRUST_ROOT_CA)

    def _raise_nmos_exception(self, test, response, string=''):
        """Raise NMOS Exception with HTTP Response Information"""
        raise NMOSTestException(test.FAIL(
            """Request to Auth Server failed. {}.
            Method: {},
            URL: {},
            Request Body: {},
            Status Code: {},
            Response: {}"""
            .format(string, response.request.method, response.url, response.request.body, response.status_code,
                    response.text)
        ))

    def _verify_response(self, test, expected_status, response):
        """Verify if HTTP response status code is valid"""
        if isinstance(response, requests.models.Response):
            try:
                response.raise_for_status()
            except Exception:
                self._raise_nmos_exception(test, response)

        elif isinstance(response, str):
            raise NMOSTestException(test.FAIL(
                "Request to Auth Server failed due to: {}".format(response)))

        if response.status_code != expected_status:
            self._raise_nmos_exception(test, response, "Expected status_code: {}".format(expected_status))

    def _verify_redirect(self, test, response, input_params, query_key, expected_query_value=None):
        """Verify if HTTP response is a valid redirect with given parameters"""

        if not response.is_redirect or response.status_code != 302:
            raise NMOSTestException(test.FAIL(
                "Request to server did not result in a redirect. Received {} instead of 302 when requesting '{}'. {}"
                .format(response.status_code, query_key, response.json())
            ))
        if "location" not in response.headers:
            raise NMOSTestException(test.FAIL(
                "'Location' not found in Response headers when requesting '{}'. Headers = {}"
                .format(query_key, response.headers.keys())
            ))
        if query_key not in response.headers["location"]:
            raise NMOSTestException(test.FAIL(
                "'{}' not found in Location Header. Location Header = {}"
                .format(query_key, response.headers["location"])
            ))
        if "state" not in response.headers["location"]:
            raise NMOSTestException(test.FAIL(
                "'state' not found in Location Header. Location Header = {}"
                .format(response.headers["location"])
            ))

        redirect_uri, query_string = response.headers["location"].split('?')
        parsed_query = parse_qs(query_string)
        actual_query_value = parsed_query[query_key][0]
        if "state" in parsed_query.keys():
            state = parse_qs(query_string)["state"][0]
        else:
            state = None

        if redirect_uri != input_params["redirect_uri"]:
            raise NMOSTestException(test.FAIL(
                "Expected {} but got {}".format(input_params["redirect_uri"], redirect_uri)))

        if state != input_params["state"]:
            raise NMOSTestException(test.FAIL(
                "Expected {} but got {}".format(input_params["state"], state)))

        if query_key != "code":
            if expected_query_value is None:
                if actual_query_value != input_params[query_key]:
                    raise NMOSTestException(test.FAIL(
                        "Expected {} but got {}".format(input_params[query_key], actual_query_value)))
            else:
                if actual_query_value != expected_query_value:
                    raise NMOSTestException(test.FAIL(
                        "Expected {} but got {}".format(expected_query_value, actual_query_value)))
        else:
            return actual_query_value

    def do_dns_sd_advertisement_check(self, test, api, service_type):
        """Auth API advertises correctly via mDNS"""

        if CONFIG.DNS_SD_MODE != "multicast":
            return test.DISABLED("This test cannot be performed when DNS_SD_MODE is not 'multicast'")

        ServiceBrowser(self.zc, service_type, self.zc_listener)
        sleep(CONFIG.DNS_SD_BROWSE_TIMEOUT)
        serv_list = self.zc_listener.get_service_list()
        for service in serv_list:
            port = service.port
            if port != api["port"]:
                continue
            for address in service.addresses:
                address = socket.inet_ntoa(address)
                if address != api["ip"]:
                    continue
                properties = self.convert_bytes(service.properties)
                if "pri" not in properties:
                    return test.FAIL("No 'pri' TXT record found in {} advertisement.".format(api["name"]))
                try:
                    priority = int(properties["pri"])
                    if priority < 0:
                        return test.FAIL("Priority ('pri') TXT record must be greater than zero.")
                    elif priority >= 100:
                        return test.WARNING(
                            "Priority ('pri') TXT record must be less than 100 for a production instance.")
                except Exception:
                    return test.FAIL("Priority ('pri') TXT record is not an integer.")

                if "api_ver" not in properties:
                    return test.FAIL("No 'api_ver' TXT record found in {} advertisement.".format(api["name"]))
                elif api["version"] not in properties["api_ver"].split(","):
                    return test.FAIL("Auth Server does not claim to support version under test.")
                if "api_proto" not in properties:
                    return test.FAIL("No 'api_proto' TXT record found in {} advertisement.".format(api["name"]))
                elif properties["api_proto"] != "https":
                    return test.FAIL("""
                        API protocol ('api_proto') TXT record is {} and not 'https'
                    """.format(properties["api_proto"]))

                return test.WARNING("Authorization Server SHOULD NOT be advertised by mDNS based DNS-SD")
        return test.PASS()

    def test_01(self, test):
        """Registration API advertises correctly via mDNS"""

        api = self.apis[AUTH_API_KEY]
        service_type = "_nmos-auth._tcp.local."

        return self.do_dns_sd_advertisement_check(test, api, service_type)

    def test_02(self, test):
        """Test registering a client to the '/register_client' endpoint"""

        RECOMMENDED_RESPONSE_FIELDS = ["client_secret", "redirect_uris"]
        ARRAY_RESPONSE_FIELDS = ["redirect_uris", "grant_types", "response_types"]
        LIST_DELIMITER = '\n'

        # Body of client registration request is found in the test_data directory
        with open("test_data/IS1001/register_client_request_data.json") as resource_data:
            request_data = json.load(resource_data)

        status, response = self._make_auth_request(method="POST", url_path='register_client',
                                                   data=request_data, auth="user")

        try:
            self._verify_response(test=test, expected_status=201, response=response)
        except NMOSTestException as e:
            raise NMOSTestException(test.FAIL("""
                {}. Ensure a user is registered with the credentials, user: {} password: {}
            """.format(e.args[0].detail, CONFIG.AUTH_USERNAME, CONFIG.AUTH_PASSWORD)))

        for key in request_data:
            # Test that all request data keys are found in response. Added 's' compensates for grant_type/s, etc.
            if not any(i in [key, key + 's'] for i in response.json().keys()):
                return test.FAIL(
                    """'{}' value not in response keys.
                    'The authorization server MUST return all registered metadata about the client'""".format(key)
                )
            # Check that same keys in req and resp have same values
            if key in response.json().keys() and request_data[key] != response.json()[key]:
                return test.WARNING("The response for {} did not match. Request: {} != Response: {}".format(
                    key, request_data[key], response.json()[key])
                )

        # Test that all array fields in response contain a value from the corresponding value in the request
        for field in ARRAY_RESPONSE_FIELDS:
            if field in request_data:
                index = field
            elif field[0:-1] in request_data:
                index = field[0:-1]
            else:
                continue
            # This is in case url-encoded form data is used instead of JSON
            if isinstance(request_data[index], str):
                request_data[index] = request_data[index].split(LIST_DELIMITER)
            if not all(i in request_data[index] for i in response.json()[field]):
                return test.FAIL("'{}' value is not included in the response from the Auth Server. {} not in {}"
                                 .format(field, request_data[index], response.json()[field]))

        if response.json()["token_endpoint_auth_method"] in ["none", None, "None", "null"]:
            return test.WARNING("Token Endpoint Authorization method SHOULD NOT be None")

        if not isinstance(response.json()["scope"], str):
            return test.FAIL("Scope values MUST be a space-delimited string")

        if not set(RECOMMENDED_RESPONSE_FIELDS).issubset(response.json().keys()):
            return test.WARNING("Client registration response SHOULD include: {}".format(RECOMMENDED_RESPONSE_FIELDS))

        register_client_schema = self.get_schema(AUTH_API_KEY, "POST", '/register_client', 201)

        try:
            self.validate_schema(response.json(), register_client_schema)
            self.client_data = response.json()
            return test.PASS()
        except Exception as e:
            return test.FAIL("Status code was {} and Schema validation failed. {}".format(response.status_code, e))

    def test_03(self, test):
        """Test requesting a Bearer Token using Password Grant from '/token' endpoint"""
        if self.client_data:
            for scope in GRANT_SCOPES:
                request_data = {
                    'username': CONFIG.AUTH_USERNAME,
                    'password': CONFIG.AUTH_PASSWORD,
                    'grant_type': 'password',
                    'scope': scope
                }
                status, response = self._make_auth_request("POST", 'token', data=request_data, auth="client")

                self._verify_response(test=test, expected_status=200, response=response)

                token_schema = self.get_schema(AUTH_API_KEY, "POST", '/token', 200)
                try:
                    self.validate_schema(response.json(), token_schema)
                    self.bearer_tokens.append(response.json())
                    return test.PASS()
                except Exception as e:
                    return test.FAIL("Status code was {} and Schema validation failed. {}"
                                     .format(response.status_code, e))
        else:
            return test.DISABLED("No Client Data available")

    def test_04(self, test):
        """Test the '/authorize' endpoint and ability to redirect to registered URI with authorization code"""

        if self.client_data:
            for scope in GRANT_SCOPES:

                state = "xyz"
                parameters = {
                    "response_type": "code",
                    "client_id": self.client_data["client_id"],
                    "redirect_uri": self.client_data["redirect_uris"][0],
                    "scope": scope,
                    "state": state
                }

                # Body of client registration request is found in the test_data directory
                with open("test_data/IS1001/authorization_request_data.json") as resource_data:
                    request_data = json.load(resource_data)

                response = self._post_to_authorize_endpoint(data=request_data, parameters=parameters, auth="user")

                self._verify_response(test=test, expected_status=302, response=response)
                auth_code = self._verify_redirect(test, response, parameters, "code")

                self.auth_codes.append(auth_code)
                return test.PASS()

        else:
            return test.DISABLED("No Client Data available")

    def test_05(self, test):
        """Test requesting a Bearer Token using Auth Code Grant from '/token' endpoint"""

        if self.client_data and self.auth_codes:
            for auth_code in self.auth_codes:

                request_data = {
                    "grant_type": "authorization_code",
                    "code": auth_code,
                    "redirect_uri": self.client_data["redirect_uris"][0],
                    "client_id": self.client_data["client_id"]
                }

                status, response = self._make_auth_request(method="POST", url_path="token",
                                                           data=request_data, auth="client")

                self._verify_response(test=test, expected_status=200, response=response)

                token_schema = self.get_schema(AUTH_API_KEY, "POST", '/token', 200)
                try:
                    self.validate_schema(response.json(), token_schema)
                    self.bearer_tokens.append(response.json())
                    return test.PASS()
                except Exception as e:
                    self._raise_nmos_exception(self, test, response, string=str(e))
        else:
            return test.DISABLED("No Client Data or Auth Codes available")

    def test_06(self, test):
        """Test requesting a Bearer Token using the Refresh Token Grant from '/token' endpoint"""
        if self.bearer_tokens:
            for bearer_token in self.bearer_tokens:
                refresh_token = bearer_token["refresh_token"]

                request_data = {
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token
                }

                status, response = self._make_auth_request("POST", url_path="token", data=request_data, auth="client")

                self._verify_response(test=test, expected_status=200, response=response)

                token_schema = self.get_schema(AUTH_API_KEY, "POST", '/token', 200)
                try:
                    self.validate_schema(response.json(), token_schema)
                    self.bearer_tokens.append(response.json())
                    return test.PASS()
                except Exception as e:
                    self._raise_nmos_exception(self, test, response, string=str(e))
        else:
            return test.DISABLED("No Bearer Tokens available")

    def test_07(self, test):
        """Test '/certs' endpoint for valid certificate"""
        status, response = self.do_request(method="GET", url=self.url + 'certs')

        self._verify_response(test=test, expected_status=200, response=response)

        token_schema = self.get_schema(AUTH_API_KEY, "GET", '/certs', 200)
        try:
            self.validate_schema(response.json(), token_schema)
        except Exception as e:
            self._raise_nmos_exception(self, test, response, string=str(e))

        # Check that the certificate can be loaded and is therefore a valid PEM certificate
        try:
            crypto.load_certificate(crypto.FILETYPE_PEM, response.json()[0])
            return test.PASS()
        except Exception as e:
            self._raise_nmos_exception(self, test, response, string=str(e))

    def test_08(self, test):
        """Test revocation of access tokens at '/revoke' endpoint"""
        if self.bearer_tokens:
            for bearer_token in self.bearer_tokens:
                request_data = {
                    "token": bearer_token["access_token"],
                    "token_type_hint": "access_token"
                }

                status, response = self._make_auth_request(method="POST", url_path='revoke',
                                                           data=request_data, auth="client")

                self._verify_response(test=test, expected_status=200, response=response)

            return test.PASS()
        else:
            return test.DISABLED("No Bearer Tokens Available")

    def _bad_post_to_authorize_endpoint(
            self, data, params, key, value, auth="user"):
        """Post to /authorize endpoint with incorrect URL parameters"""
        params_copy = params.copy()
        params_copy[key] = value
        return self._post_to_authorize_endpoint(data, params_copy, auth)

    def _bad_post_to_token_endpoint(self, data, key, value, auth='client'):
        """Post to /token endpoint with incorrect body parameters"""
        data_copy = data.copy()
        data_copy[key] = value
        return self._make_auth_request(method='POST', url_path='token', data=data_copy, auth=auth)

    def _verify_error_response(self, test, response, status_code, error_value):

        if response.status_code != status_code:
            self._raise_nmos_exception(test, response,
                                       string="Incorrect Status Code Returned. Expected {}".format(status_code))

        ctype_valid, ctype_message = self.check_content_type(response.headers)
        if not ctype_valid:
            self._raise_nmos_exception(test, response, ctype_message)
        # else if ctype_message:
        #     return WARNING somehow...

        token_schema = self.get_schema(AUTH_API_KEY, "POST", '/token', 400)
        try:
            self.validate_schema(response.json(), token_schema)
        except Exception as e:
            self._raise_nmos_exception(self, test, response, string=str(e))

        if error_value not in response.json()["error"]:
            self._raise_nmos_exception(self, test, response, "'{}' not in error response. Response: {}"
                                                             .format(error_value, response.json()["error"]))

    def test_09(self, test):
        """Test Error Response of Authorization Endpoint in line with RFC6749"""

        if self.client_data:
            parameters = {
                "response_type": "code",
                "client_id": self.client_data["client_id"],
                "redirect_uri": self.client_data["redirect_uris"][0],
                "scope": "is-04",
                "state": "xyz"
            }

            # Body of client registration request is found in the test_data directory
            with open("test_data/IS1001/authorization_request_data.json") as resource_data:
                request_data = json.load(resource_data)

            response = self._post_to_authorize_endpoint(request_data, parameters)
            if response.status_code != 302:
                return test.FAIL("Correct Request Data didn't return 302 status code. Got {}"
                                 .format(response.status_code))

            # Incorrect Redirect URI should result in error response
            response = self._bad_post_to_authorize_endpoint(data=request_data, params=parameters,
                                                            key="redirect_uri", value="http://www.bogus.com")
            self._verify_error_response(test, response, 400, "invalid_request")

            # Incorrect Response Type should result in error response
            response = self._bad_post_to_authorize_endpoint(data=request_data, params=parameters,
                                                            key="response_type", value="password")
            self._verify_error_response(test, response, 400, "invalid_grant")

            # No Authorization Header should result in Access Denied error in redirect
            response = self._bad_post_to_authorize_endpoint(data=request_data, params=parameters,
                                                            key="scope", value="is-04", auth=None)
            self._verify_redirect(test, response, parameters, "error", "access_denied")

            # Invalid scope should result in Bad Scope error in redirect
            response = self._bad_post_to_authorize_endpoint(data=request_data, params=parameters,
                                                            key="scope", value="bad_scope")
            self._verify_redirect(test, response, parameters, "error", "invalid_scope")

            # Invalid client should result in Bad Client error in redirect
            response = self._bad_post_to_authorize_endpoint(data=request_data, params=parameters,
                                                            key="client_id", value="bad_client")
            self._verify_redirect(test, response, parameters, "error", "invalid_client")

            # Lack of Resource Owner consent should result in Access Denied error in redirect
            response = self._bad_post_to_authorize_endpoint(data=None, params=parameters, key="scope", value="is-04")
            self._verify_redirect(test, response, parameters, "error", "access_denied")
            return test.PASS()
        else:
            return test.DISABLED("No Client Data available")

    def test_10(self, test):
        """Test Error Response of Token Endpoint in line with RFC6749"""

        if self.auth_codes and self.client_data:
            # Use Authorization Grant flow with an already used Auth Code
            request_data = {
                "grant_type": "authorization_code",
                "code": self.auth_codes[0],
                "redirect_uri": self.client_data["redirect_uris"][0],
                "client_id": self.client_data["client_id"]
            }
            status, response = self._make_auth_request(method="POST", url_path="token",
                                                       data=request_data, auth="client")
            self._verify_error_response(test, response, 400, "invalid_request")

            # Use Pasword Grant flow wih incorrect credentials
            request_data = {
                'username': CONFIG.AUTH_USERNAME,
                'password': CONFIG.AUTH_PASSWORD,
                'grant_type': 'password',
                'scope': "is-04"
            }

            status, response = self._bad_post_to_token_endpoint(data=request_data, key="username", value="bad_username")
            self._verify_error_response(test, response, 400, "invalid_request")

            status, response = self._bad_post_to_token_endpoint(data=request_data, key="grant_type", value="bad_grant")
            self._verify_error_response(test, response, 400, "invalid_grant")

            status, response = self._bad_post_to_token_endpoint(data=request_data, key="scope", value="bad_scope")
            self._verify_error_response(test, response, 400, "invalid_scope")

            status, response = self._bad_post_to_token_endpoint(data=request_data, key="scope",
                                                                value="is-04", auth=None)
            self._verify_error_response(test, response, 401, "invalid_client")
            return test.PASS()
        else:
            return test.DISABLED("No Client Data or Auth Codes available")
