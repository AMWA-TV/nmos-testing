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

from GenericTest import GenericTest
from Config import AUTH_USERNAME, AUTH_PASSWORD


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
        print("""
            Ensure a User is already set-up on the Authorization Server that corresponds
            to the 'AUTH_USERNAME' and 'AUTH_PASSWORD' config options
        """)

    def _make_auth_request(self, method, url_path, data=None, auth=(AUTH_USERNAME, AUTH_PASSWORD)):
        """Utility option for making requests with Basic Authorization"""
        return self.do_request(
            method=method, url=self.apis['auth']['url'] + url_path, data=data, auth=auth
        )

    def test_01_register_user(self, test):
        """Test registering a client to the `register_client` endpoint"""

        request_data = {
            'client_name': 'Example Client',
            'client_uri': 'http://www.example.com',
            'scope': 'is04+is05',
            'redirect_uri': self.apis['auth']['url'],
            'grant_type': 'password\nauthorization_code',
            'response_type': 'code',
            'token_endpoint_auth_method': 'client_secret_basic'
        }

        bool_status, response = self._make_auth_request(
            method="POST", url_path='register_client', data=request_data
        )

        print(response.text)

        if bool_status is False:
            return test.FAIL(
                "Failed to register client with Authorization Server using credentials:\n{}".format(request_data)
            )

        if len(response.json()["grant_types"]) == 1:
            return test.WARNING("Auth Server doesn't read newline character as delimiter for Grant Types")

        if response.status_code != 201:
            return test.FAIL("Return Code was {} instead of 201 (in-line with RFC 7591)".format(response.status_code))

        if response.status_code == 201:
            return test.PASS()

    def test_02_token_password_grant(self, test):
        return test.OPTIONAL("Test Not Implemented")

    def test_03_authorize_endpoint(self, test):
        return test.OPTIONAL("Test Not Implemented")

    def test_04_token_authorize_grant(self, test):
        return test.OPTIONAL("Test Not Implemented")

    def test_05_token_refresh_grant(self, test):
        return test.OPTIONAL("Test Not Implemented")

    def test_06_cert_endpoint(self, test):
        return test.OPTIONAL("Test Not Implemented")
