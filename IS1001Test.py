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
from requests import post
from urllib.parse import parse_qs

from GenericTest import GenericTest, NMOSInitException, NMOSTestException
from Config import AUTH_USERNAME, AUTH_PASSWORD, CERT_TRUST_ROOT_CA

AUTH_API_KEY = 'auth'
GRANT_SCOPES = ['is-04', 'is-05']


class IS1001Test(GenericTest):
    """
    Runs IS-10-01-Test.

    Example "Specification" Object:
    {
    'global_schemas': {},
    'data': {
      '/certs': [{
        'method': 'get',
        'body': None,
        'params': None,
        'responses': {
          200: {
            'title': 'Certificate Response',
            '$schema': 'http://json-schema.org/draft-07/schema#',
            'type': 'array',
            'items': {
              'type': 'string'
            },
            'minItems': 1,
            'description': 'Array of certificates to validate Access Token',
          }
        },
      }],
      '/register_client': [{
        'method': 'get',
        'body': None,
        'params': None,
        'responses': {
          200: None
        },
      }, {
        'method': 'post',
        'body': None,
        'params': None,
        'responses': {
          201: {
            'title': 'Register Client Response',
            '$schema': 'http://json-schema.org/draft-07/schema#',
            'properties': {
              'client_secret_expires_at': {
                'type': 'number',
                'description': 'Time at which the client secret will expire or 0 if it will not expire'
              },
              'client_id': {
                'type': 'string',
                'description': 'OAuth 2.0 client identifier string'
              },
              'client_secret': {
                'type': 'string',
                'description': 'OAuth 2.0 client secret string'
              },
              'client_id_issued_at': {
                'type': 'number',
                'description': 'UTC time at which the client identifier was issued'
              },
            },
            'required': ['client_id', 'client_secret_expires_at'],
            'type': 'object',
            'description': 'Object defining successful client registration',
          }
        },
      }],
      '/authorize': [{
        'method': 'get',
        'body': None,
        'params': None,
        'responses': {
          200: None
        },
      }, {
        'method': 'post',
        'body': None,
        'params': None,
        'responses': {
          302: None
        },
      }],
      '/': [{
        'method': 'get',
        'body': None,
        'params': None,
        'responses': {
          200: {
            'type': 'array',
            'title': 'Authorization API base resource',
            'items': {
              'type': 'string',
              'maxItems': 5,
              'uniqueItems': True,
              'enum': ['certs/', 'register_client/', 'token/',
                'authorize/', 'revoke/'
              ],
              'minItems': 5,
            },
            '$schema': 'http://json-schema.org/draft-04/schema#',
            'description': 'Displays the Authorization API base resources',
          }
        },
      }],
      '/revoke': [{
        'method': 'post',
        'body': None,
        'params': None,
        'responses': {
          200: None
        },
      }],
      '/token': [{
        'method': 'post',
        'body': None,
        'params': None,
        'responses': {
          200: {
            'title': 'Token Response',
            '$schema': 'http://json-schema.org/draft-07/schema#',
            'properties': {
              'scope': {
                'type': 'string',
                'description': 'The scope of the Access Token'
              },
              'expires_in': {
                'type': 'integer',
                'description': 'The lifetime in seconds of the access token'
              },
              'access_token': {
                'type': 'string',
                'description': 'Access Token to be used in accessing protected endpoints'
              },
              'token_type': {
                'type': 'string',
                'enum': ['Bearer'],
                'description': 'The type of the Token issued'
              },
              'refresh_token': {
                'type': 'string',
                'description': 'Refresh Token to be used to obtain further Access Tokens'
              },
            },
            'required': ['access_token', 'expires_in', 'token_type'],
            'type': 'object',
            'description': 'OAuth2 Response for the request of a Bearer Token',
          },
          400: {
            'title': 'Token Error Response',
            '$schema': 'http://json-schema.org/draft-07/schema#',
            'properties': {
              'error': {
                'type': 'string',
                'description': 'Error Type'
              },
              'error_uri': {
                'type': 'string',
                'description': 'A URI identifying a human-readable web page with information about the error'
              },
              'error_description': {
                'type': 'string',
                'description': 'Human-readable ASCII text providing additional information'
              }
            },
            'required': ['error'],
            'type': 'object',
            'minItems': 1,
            'description': 'Object defining error type and description',
          }
        },
      }],
    }
  }

  Example "apis" Object:
  {
      'auth': {
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
      }
  }
  """

    def __init__(self, apis):
        super(IS1001Test, self).__init__(apis)
        self.url = self.apis[AUTH_API_KEY]["url"]
        self.bearer_tokens = []
        self.client_data = {}
        self.auth_codes = []
        self.clients = []  # List of all registered clients for deleting during clean-up

    def set_up_tests(self):
        """Add User to Authorization Server"""
        try:
            # NOTE - This is implementation-specific
            signup_data = {
                'username': AUTH_USERNAME,
                'password': AUTH_PASSWORD,
                'is04': 'read',
                'is05': 'write'
            }
            status, response = self.do_request(
                method="POST", url=self.url + 'signup', data=signup_data
            )

            if status is not True:
                raise NMOSInitException("""
                    Ensure a User is already set-up on the Authorization Server that corresponds
                    to the 'AUTH_USERNAME' and 'AUTH_PASSWORD' config options
                """)
        # Catch Exception to allow tests to run
        except Exception as e:
            print(e)

    def tear_down_tests(self):
        """Delete Registered Client from Authorization Server"""
        try:
            # NOTE - This is implementation-specific
            status, response = self._make_auth_request(
                method="GET", url_path='delete_client/' + self.client_data["client_id"], auth="user"
            )
            if status is not True:
                raise NMOSInitException("""
                    Unable to delete registered client from Authorization Server. This may have to be done manually.
                """)
        # Catch Exception to allow tests to run
        except Exception as e:
            print(e)

    def _make_auth_request(self, method, url_path, data=None, auth=None, params=None):
        """Utility function for making requests with Basic Authorization"""
        if auth == "user":
            username = AUTH_USERNAME
            password = AUTH_PASSWORD
        elif auth == "client" and self.client_data:
            username = self.client_data["client_id"]
            password = self.client_data["client_secret"]
        else:
            username, password = None
        return self.do_request(
            method=method, url=self.url + url_path, data=data, auth=(username, password), params=params
        )

    def test_01_register_user(self, test):
        """Test registering a client to the `register_client` endpoint"""

        RECOMMENDED_RESPONSE_FIELDS = ["client_secret", "redirect_uris"]
        ARRAY_RESPONSE_FIELDS = ["redirect_uris", "grant_types", "response_types"]
        LIST_DELIMITER = '\n'

        # Body of client registration request is found in the test_data directory
        with open("test_data/IS1001/register_client_request_data.json") as resource_data:
            request_data = json.load(resource_data)

        status, response = self._make_auth_request(
            method="POST", url_path='register_client', data=request_data, auth="user"
        )

        if status is False and isinstance(response, str):
            return test.FAIL(
                "Failed to register client with Authorization Server using credentials: {}. Failed with: {}"
                .format(request_data, response)
            )

        if response.status_code != 201:
            return test.FAIL(
                "Return Code was {} instead of 201 (in-line with RFC 7591). {}"
                .format(response.status_code, response.json())
            )

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
            if response.status_code == 201:
                self.client_data = response.json()
                return test.PASS()
        except Exception as e:
            return test.FAIL("Status code was {} and Schema validation failed. {}".format(response.status_code, e))

        return test.FAIL("Implementation did not pass the necessary criteria.")

    def test_02_token_password_grant(self, test):
        """Test requesting a Bearer Token using Password Grant from '/token' endpoint"""
        if self.client_data:
            for scope in GRANT_SCOPES:
                request_data = {
                    'username': AUTH_USERNAME,
                    'password': AUTH_PASSWORD,
                    'grant_type': 'password',
                    'scope': scope
                }
                status, response = self._make_auth_request(
                    "POST", 'token', data=request_data, auth="client"
                )

                if status is False and isinstance(response, str):
                    return test.FAIL(
                        "Request for Token using Password Grant and scope {} failed. {}"
                        .format(scope, response)
                    )

                if status and response.status_code != 200:
                    return test.FAIL(
                        "Incorrect status code. Return code {} should be '200'. {}"
                        .format(response.status_code, response.json())
                    )

                token_schema = self.get_schema(AUTH_API_KEY, "POST", '/token', 200)
                try:
                    self.validate_schema(response.json(), token_schema)
                    if response.status_code == 200:
                        self.bearer_tokens.append(response.json())
                        return test.PASS()
                except Exception as e:
                    return test.FAIL(
                        "Status code was {} and Schema validation failed. {}".format(response.status_code, e)
                    )

                return test.FAIL("Implementation did not pass the necessary criteria.")
        else:
            return test.DISABLED("No client data available")

    def test_03_authorize_endpoint(self, test):
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
                # NOTE - This is implementation-specific - this signifies the user's consent to the Auth Server
                data = {
                    "confirm": "true"
                }

                response = post(
                    url=self.url + 'authorize',
                    data=data,
                    params=parameters,
                    allow_redirects=False,
                    auth=(AUTH_USERNAME, AUTH_PASSWORD),
                    verify=CERT_TRUST_ROOT_CA
                )

                try:
                    response.raise_for_status()
                except Exception as e:
                    return test.FAIL("Request failed at `authorize` endpoint: {}".format(e))

                if not response.is_redirect or response.status_code != 302:
                    return test.FAIL(
                        "Request to server did not result in a redirect. Received {} instead of 302."
                        .format(response.status_code)
                    )

                if "location" not in response.headers:
                    return test.FAIL(
                        "'Location' not found in Response headers. Headers = {}".format(response.headers.keys())
                    )
                if "code=" not in response.headers["location"]:
                    return test.FAIL(
                        "'code' not found in Location Header. Location Header = {}".format(response.headers["location"])
                    )
                if "state=" not in response.headers["location"]:
                    return test.FAIL(
                        "'state' not found in Location Header. Location Header = {}"
                        .format(response.headers["location"])
                    )

                redirect_uri, query_string = response.headers["location"].split('?')
                auth_code = parse_qs(query_string)["code"][0]
                state = parse_qs(query_string)["state"][0]

                if not redirect_uri == parameters["redirect_uri"]:
                    return test.FAIL(
                        "Expected {} but got {}".format(parameters["redirect_uri"], redirect_uri)
                    )
                if not state == parameters["state"]:
                    return test.FAIL(
                        "Expected {} but got {}".format(parameters["state"], state)
                    )

                self.auth_codes.append(auth_code)
                return test.PASS()

        else:
            return test.DISABLED("No Client Data available")

    def test_04_token_authorize_grant(self, test):
        """Test requesting a Bearer Token using Auth Code Grant from '/token' endpoint"""

        if self.client_data and self.auth_codes:
            for auth_code in self.auth_codes:

                request_data = {
                    "grant_type": "authorization_code",
                    "code": auth_code,
                    "redirect_uri": self.client_data["redirect_uris"][0],
                    "client_id": self.client_data["client_id"]
                }

                status, response = self._make_auth_request(
                    method="POST", url_path="token", data=request_data, auth="client"
                )

                if status is False and isinstance(response, str):
                    return test.FAIL("Request for Token using Auth Grant failed. {}".format(response))

                if status and response.status_code != 200:
                    return test.FAIL(
                        "Incorrect status code. Return code '{}' should be '200'.\n{}"
                        .format(response.status_code, response.json())
                    )

                token_schema = self.get_schema(AUTH_API_KEY, "POST", '/token', 200)
                try:
                    self.validate_schema(response.json(), token_schema)
                    if response.status_code == 200:
                        self.bearer_tokens.append(response.json())
                        return test.PASS()
                except Exception as e:
                    return test.FAIL(
                        "Status code was {} and Schema validation failed. {}".format(response.status_code, e)
                    )

                return test.FAIL("Implementation did not pass the necessary criteria.")
        else:
            return test.DISABLED("No Auth Codes were present")

    def test_05_token_refresh_grant(self, test):
        """Test requesting a Bearer Token using the Refresh Token Grant from '/token' endpoint"""
        if self.bearer_tokens:
            for bearer_token in self.bearer_tokens:
                refresh_token = bearer_token["refresh_token"]

                request_data = {
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token
                }

                status, response = self._make_auth_request(
                    "POST", url_path="token", data=request_data, auth="client"
                )

                if status is False and isinstance(response, str):
                    return test.FAIL("Request for Token using Auth Grant failed. {}".format(response))

                if status and response.status_code != 200:
                    return test.FAIL(
                        "Incorrect status code. Return code '{}' should be '200'.\n{}"
                        .format(response.status_code, response.json())
                    )

                token_schema = self.get_schema(AUTH_API_KEY, "POST", '/token', 200)
                try:
                    self.validate_schema(response.json(), token_schema)
                    if response.status_code == 200:
                        self.bearer_tokens.append(response.json())
                        return test.PASS()
                except Exception as e:
                    return test.FAIL(
                        "Status code was {} and Schema validation failed. {}".format(response.status_code, e)
                    )

                return test.FAIL("Implementation did not pass the necessary criteria.")
        else:
            return test.DISABLED("No Bearer Tokens were present")

    def bad_post_to_authorize_endpoint(self, data, params, key, value, auth=(AUTH_USERNAME, AUTH_PASSWORD)):
        params_copy = params.copy()
        params_copy[key] = value
        return self.post_to_authorize_endpoint(data, params_copy, auth)

    def post_to_authorize_endpoint(self, data, parameters, auth=(AUTH_USERNAME, AUTH_PASSWORD)):
        return post(
            url=self.url + 'authorize',
            data=data,
            params=parameters,
            allow_redirects=False,
            auth=auth,
            verify=CERT_TRUST_ROOT_CA
        )

    def verify_location_header(self, test, response, input_params, query_key, expected_query_value=None):

        if not response.is_redirect or response.status_code != 302:
            raise NMOSTestException(test.FAIL(
                "Request to server did not result in a redirect. Received {} instead of 302."
                .format(response.status_code)
            ))
        if "location" not in response.headers:
            raise NMOSTestException(test.FAIL(
                "'Location' not found in Response headers. Headers = {}".format(response.headers.keys())
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

        if not redirect_uri == input_params["redirect_uri"]:
            raise NMOSTestException(test.FAIL(
                "Expected {} but got {}".format(input_params["redirect_uri"], redirect_uri)
            ))

        if expected_query_value is None:
            if not actual_query_value == input_params[query_key]:
                raise NMOSTestException(test.FAIL(
                    "Expected {} but got {}".format(input_params[query_key], actual_query_value)
                ))
        else:
            if not actual_query_value == expected_query_value:
                raise NMOSTestException(test.FAIL(
                    "Expected {} but got {}".format(expected_query_value, actual_query_value)
                ))

        if not state == input_params["state"]:
            raise NMOSTestException(test.FAIL(
                "Expected {} but got {}".format(input_params["state"], state)
            ))

    def test_06_authorize_error(self, test):
        """Test Error Response of Authorization Endpoint in line with RFC6749"""

        if self.client_data:
            parameters = {
                "response_type": "code",
                "client_id": self.client_data["client_id"],
                "redirect_uri": self.client_data["redirect_uris"][0],
                "scope": "is-04",
                "state": "xyz"
            }
            # NOTE - This is implementation-specific - this signifies the user's consent to the Auth Server
            request_data = {
                "confirm": "true"
            }

            response = self.post_to_authorize_endpoint(request_data, parameters)
            if response.status_code != 302:
                return test.FAIL(
                    "Correct Request Data didn't return 302 status code. Got {}"
                    .format(response.status_code))

            response = self.bad_post_to_authorize_endpoint(
                data=request_data, params=parameters, key="redirect_uri", value="http://www.bogus.com"
            )
            if response.status_code != 400:
                return test.FAIL(
                    "Incorrect Redirect URI didn't return 400 status code. Got {}. Response: {}"
                    .format(response.status_code, response.json()))
            if not response.headers["Content-Type"] == "application/json":
                return test.FAIL(
                    "Body of Error was not JSON. Content-Type is '{}'".format(response.headers["Content-Type"])
                )
            if "invalid_request" not in response.json()["error"]:
                return test.FAIL(
                    "'invalid_request' not in response for malformed/incorrect redirect_uri. Response: {}"
                    .format(response.json())
                )

            response = self.bad_post_to_authorize_endpoint(
                data=request_data, params=parameters, key="response_type", value="password"
            )
            if response.status_code != 400:
                return test.FAIL(
                    "Incorrect Response Type didn't return 400 status code. Got {}. Response: {}"
                    .format(response.status_code, response.json()))
            if not response.headers["Content-Type"] == "application/json":
                return test.FAIL(
                    "Body of Error was not JSON. Content-Type is '{}'".format(response.headers["Content-Type"])
                )
            if "invalid_grant" not in response.json()["error"]:
                return test.FAIL(
                    "'invalid_grant' not in response for malformed/incorrect redirect_uri. Response: {}"
                    .format(response.json())
                )

            response = self.bad_post_to_authorize_endpoint(
                data=request_data, params=parameters, key="scope", value="bad_scope"
            )
            self.verify_location_header(test, response, parameters, "error", "invalid_scope")

            response = self.bad_post_to_authorize_endpoint(
                data=request_data, params=parameters, key="client_id", value="bad_client"
            )
            self.verify_location_header(test, response, parameters, "error", "invalid_client")

            response = self.bad_post_to_authorize_endpoint(
                data=request_data, params=parameters, key="scope", value="is-04", auth=None
            )
            self.verify_location_header(test, response, parameters, "error", "access_denied")

            return test.PASS()
        else:
            return test.DISABLED("No Client Data available")

    def test_07_token_error(self, test):
        return test.MANUAL("Test Not Implemented")
