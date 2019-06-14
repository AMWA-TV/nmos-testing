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

from GenericTest import GenericTest
from Config import AUTH_USERNAME, AUTH_PASSWORD

AUTH_API_KEY = "auth"


class IS1001Test(GenericTest):
    """
    Runs IS-10-01-Test.

    Example "Specififcaiton" Object:
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
        GenericTest.__init__(self, apis)

        self.url = self.apis[AUTH_API_KEY]["url"]
        self.bearer_token = None
        self.client_data = None

    def set_up_tests(self):
        try:
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
                raise Exception

        except Exception:
            print("""
                Ensure a User is already set-up on the Authorization Server that corresponds
                to the 'AUTH_USERNAME' and 'AUTH_PASSWORD' config options
            """)

    def tear_down_tests(self):
        try:
            self._make_auth_request(method="GET", url_path='delete_client/' + self.client_data.client_id)
        except Exception:
            pass

    def _make_auth_request(self, method, url_path, data=None, auth=(AUTH_USERNAME, AUTH_PASSWORD)):
        """Utility option for making requests with Basic Authorization"""
        return self.do_request(
            method=method, url=self.url + url_path, data=data, auth=auth
        )

    def test_01_register_user(self, test):
        """Test registering a client to the `register_client` endpoint"""

        RECOMMENDED_RESPONSE_FIELDS = ["client_secret", "redirect_uris"]
        ARRAY_RESPONSE_FIELDS = ["redirect_uris", "grant_types", "response_types"]
        LIST_DELIMITER = '\n'

        with open("test_data/IS1001/register_client_request_data.json") as resource_data:
            request_data = json.load(resource_data)

        status, response = self._make_auth_request(
            method="POST", url_path='register_client', data=request_data
        )

        print(response.json())  # For Testing

        if status is False:
            return test.FAIL(
                "Failed to register client with Authorization Server using credentials: {}".format(request_data)
            )

        if response.status_code != 201:
            return test.FAIL("Return Code was {} instead of 201 (in-line with RFC 7591)".format(response.status_code))

        for key in request_data:
            # Test that all request data keys are found in response. Added 's' compensates for grant_type/s, etc.
            if not any(i in [key, key + 's'] for i in response.json().keys()):
                return test.FAIL(
                    """'{}' value not in response keys.
                    'The authorization server MUST return all registered metadata about the client'""".format(key)
                )
            # Check that same keys in req and resp have same values
            if key in response.json().keys() and request_data[key] != response.json()[key]:
                print('{} != {}'.format(request_data[key], response.json()[key]))
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
            return test.FAIL("Scope values must be a space-delimited string")

        if not set(RECOMMENDED_RESPONSE_FIELDS).issubset(response.json().keys()):
            return test.WARNING("Client registration response SHOULD include: {}".format(RECOMMENDED_RESPONSE_FIELDS))

        register_client_schema = self.get_schema(AUTH_API_KEY, "POST", '/register_client', 201)
        self.validate_schema(response.json(), register_client_schema)

        if response.status_code == 201:
            self.client_data = response.json()
            return test.PASS()

    def test_02_token_password_grant(self, test):
        return test.OPTIONAL("Test Not Implemented")

    def test_03_authorize_endpoint(self, test):
        return test.OPTIONAL("Test Not Implemented")

    def test_04_token_authorize_grant(self, test):
        return test.OPTIONAL("Test Not Implemented")

    def test_05_token_refresh_grant(self, test):
        return test.OPTIONAL("Test Not Implemented")
