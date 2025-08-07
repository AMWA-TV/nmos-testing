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
import uuid
import flask
import urllib
import socket
import base64
import ssl
import threading
import os
import jsonschema
import requests

from flask import Flask, Blueprint, Response, request, jsonify, redirect
from urllib.parse import parse_qs
from ..Config import PORT_BASE, KEYS_MOCKS, ENABLE_HTTPS, CERT_TRUST_ROOT_CA, JWKS_URI, REDIRECT_URI, SCOPE, CACHE_PATH
from ..TestHelper import get_default_ip, get_mocks_hostname, load_resolved_schema, check_content_type
from ..IS10Utils import IS10Utils
from zeroconf import ServiceInfo
from enum import Enum
from werkzeug.serving import make_server
from http import HTTPStatus
from authlib.jose import jwt


GRANT_TYPES = Enum("grant_types", [
    "authorization_code", "implicit", "refresh_token", "password", "client_credentials"])
SCOPES = Enum("scopes", ["connection", "node", "query", "registration", "events", "channelmapping"])
CODE_CHALLENGE_METHODS = Enum("code_challenge_methods", ["plain", "S256"])
TOKEN_ENDPOINT_AUTH_METHODS = Enum("token_endpoint_auth_methods", [
    "none", "client_secret_post", "client_secret_basic", "client_secret_jwt", "private_key_jwt"])
RESPONSE_TYPES = Enum("response_types", ["code", "token"])


class AuthException(Exception):
    def __init__(self, error, description, httpstatus=HTTPStatus.BAD_REQUEST):
        self.httpstatus = httpstatus
        self.error = error
        self.description = description


class AuthServer(object):
    def __init__(self, auth):
        self.server = None
        self.server_thread = None
        self.auth = auth

    def start(self):
        """Start Authorization server"""
        if not self.server_thread:
            ctx = None
            # placeholder for the certificate
            cert_file = "test_data/BCP00301/ca/mock_auth_cert.pem"
            # placeholder for the private key
            key_file = "test_data/BCP00301/ca/mock_auth_private_key.pem"
            # generate RSA key and certificate for the mock secondary Authorization server
            IS10Utils.make_key_cert_files(cert_file, key_file)
            if ENABLE_HTTPS:
                # ssl.create_default_context() provides options that broadly correspond to
                # the requirements of BCP-003-01
                ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
                ctx.load_cert_chain(cert_file, key_file)
                # additionally disable TLS v1.0 and v1.1
                ctx.options &= ssl.OP_NO_TLSv1 | ssl.OP_NO_TLSv1_1
                # BCP-003-01 however doesn't require client certificates, so disable those
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE

            # mock secondary Authorization server
            auth_app = Flask(__name__)
            auth_app.debug = False
            auth_app.config["AUTH_INSTANCE"] = 1
            self.auth.private_keys = [key_file]
            port = self.auth.port
            auth_app.register_blueprint(AUTH_API)

            self.server = make_server("0.0.0.0", port, auth_app, threaded=True, ssl_context=ctx)
            self.server_thread = threading.Thread(
                target=self.server.serve_forever)
            self.server_thread.daemon = True
            self.server_thread.start()

    def shutdown(self):
        """Stop Authorization server"""
        if self.server_thread:
            self.server.shutdown()
            self.server_thread.join()
            self.server_thread = None


class Auth(object):
    def __init__(self, port_increment, version="v1.0"):
        self.port = PORT_BASE + 9 + port_increment
        self.private_keys = KEYS_MOCKS
        self.version = version
        self.protocol = "http"
        self.host = get_default_ip()
        if ENABLE_HTTPS:
            self.protocol = "https"
            self.host = get_mocks_hostname()
        # authorization code of the authorization code flow
        self.code = None

    def make_mdns_info(self, priority=0, api_ver=None, ip=None):
        """Get an mDNS ServiceInfo object in order to create an advertisement"""
        if api_ver is None:
            api_ver = self.version

        api_proto = self.protocol

        if ip is None:
            ip = get_default_ip()
            hostname = "nmos-mocks.local."
        else:
            hostname = ip.replace(".", "-") + ".local."

        port = self.port

        # TODO: Add another test which checks support for parsing CSV string in api_ver
        txt = {'api_ver': api_ver, 'api_proto': api_proto, 'pri': str(priority)}

        service_type = "_nmos-auth._tcp.local."
        info = ServiceInfo(service_type,
                           "NMOSTestSuite{}{}.{}".format(port, api_proto, service_type),
                           addresses=[socket.inet_aton(ip)], port=port,
                           properties=txt, server=hostname)
        return info

    def make_issuer(self):
        return "{}://{}:{}".format(self.protocol, self.host, self.port)

    def make_metadata(self):
        metadata = {
            "issuer": self.make_issuer(),
            "authorization_endpoint": "{}://{}:{}/testauthorize".format(self.protocol, self.host, self.port),
            "token_endpoint": "{}://{}:{}/testtoken".format(self.protocol, self.host, self.port),
            "jwks_uri": "{}://{}:{}/testjwks".format(self.protocol, self.host, self.port),
            "registration_endpoint": "{}://{}:{}/testregister".format(self.protocol, self.host, self.port),
            "response_types_supported": [
                "code",
                "code token"
            ]
        }
        metadata["grant_types_supported"] = [e.name for e in GRANT_TYPES]
        metadata["scopes_supported"] = [e.name for e in SCOPES]
        metadata["code_challenge_methods_supported"] = [e.name for e in CODE_CHALLENGE_METHODS]
        return metadata

    def generate_jwk(self):
        private_key = IS10Utils.read_RSA_private_key(self.private_keys)
        return IS10Utils.generate_jwk(private_key)

    def generate_token(self, scopes=None, write=False, azp=False, add_claims=True, exp=3600, overrides=None):
        private_key = IS10Utils.read_RSA_private_key(self.private_keys)
        overrides_ = {"iss": "{}://{}:{}".format(self.protocol, self.host, self.port)}
        if overrides:
            overrides_.update(overrides)
        return IS10Utils.generate_token(private_key, scopes, write, azp, add_claims, exp=exp, overrides=overrides_)


# 0 = Primary mock Authorization API
# 1 = Secondary mock Authorization API, which is used for testing resources server on handling
#     access token from different Authorization server
NUM_AUTHS = 2
AUTHS = [Auth(i + 1) for i in range(NUM_AUTHS)]
AUTH_API = Blueprint('auth_pi', __name__)
PRIMARY_AUTH = AUTHS[0]
SECONDARY_AUTH = AUTHS[1]

SPEC_PATH = os.path.join(CACHE_PATH + "/is-10")


@AUTH_API.route('/.well-known/oauth-authorization-server', methods=["GET"])
def auth_metadata():
    auth = AUTHS[flask.current_app.config["AUTH_INSTANCE"]]

    metadata = auth.make_metadata()
    return Response(json.dumps(metadata), mimetype='application/json')


@AUTH_API.route('/testjwks', methods=["GET"])
def auth_jwks():
    auth = AUTHS[flask.current_app.config["AUTH_INSTANCE"]]

    jwks = []
    private_key = IS10Utils.read_RSA_private_key(auth.private_keys)
    if private_key:
        jwk = IS10Utils.generate_jwk(private_key)
        jwks = {"keys": [jwk]}

    return Response(json.dumps(jwks), mimetype='application/json')


@AUTH_API.route('/testregister', methods=["POST"])
def auth_register():
    try:
        # register_client_request schema validation
        schema = load_resolved_schema(SPEC_PATH, "register_client_request.json")
        jsonschema.validate(request.json, schema)

        # extending validation to cover those not in the schema
        redirect_uris = []
        if "redirect_uris" in request.json:
            redirect_uris = request.json["redirect_uris"]

        token_endpoint_auth_method = TOKEN_ENDPOINT_AUTH_METHODS.client_secret_basic.name
        if "token_endpoint_auth_method" in request.json:
            token_endpoint_auth_method = request.json["token_endpoint_auth_method"]

        grant_types = [GRANT_TYPES.authorization_code]
        if "grant_types" in request.json:
            grant_types = request.json["grant_types"]

        response_types = ["code token"]
        if "response_types" in request.json:
            response_types = request.json["response_types"]

        scopes = []
        if "scope" in request.json:
            scopes = request.json["scope"]

        client_uri = None
        if "client_uri" in request.json:
            client_uri = request.json["client_uri"]

        jwks_uri = None
        if "jwks_uri" in request.json:
            jwks_uri = request.json["jwks_uri"]

        # hmm, maybe more to test
        if token_endpoint_auth_method == TOKEN_ENDPOINT_AUTH_METHODS.private_key_jwt.name and not jwks_uri:
            raise AuthException("invalid_request", "missing jwks_uri")

        if GRANT_TYPES.authorization_code in grant_types and not redirect_uris:
            raise AuthException("invalid_request", "missing redirect_uris")

        scopes_ = scopes.split()
        scope_found = IS10Utils.is_any_contain(scopes_, SCOPES)
        if not scope_found:
            raise AuthException("invalid_scope", "scope: {} are not supported".format(scopes_))

        # allowing open client registration
        response = {
            "client_id": str(uuid.uuid4()),
            "client_name": request.json["client_name"],
            "client_secret_expires_at": 0,
            "redirect_uris": redirect_uris,
            "grant_types": grant_types,
            "response_types": response_types,
            "scope": scopes,
            "token_endpoint_auth_method": token_endpoint_auth_method
        }

        if token_endpoint_auth_method == TOKEN_ENDPOINT_AUTH_METHODS.client_secret_basic.name:
            response["client_secret"] = str(uuid.uuid4())

        if client_uri:
            response["client_uri"] = client_uri

        if jwks_uri:
            response["jwks_uri"] = jwks_uri

        return jsonify(response), HTTPStatus.CREATED.value

    except jsonschema.ValidationError as e:
        error_message = {"code": HTTPStatus.BAD_REQUEST.value,
                         "error": "invalid_request",
                         "error_description": e.message}
        return Response(json.dumps(error_message), status=error_message["code"], mimetype='application/json')
    except AuthException as e:
        error_message = {"code": e.httpstatus.value,
                         "error": e.error,
                         "error_description": e.description}
        return Response(json.dumps(error_message), status=e.httpstatus.value, mimetype='application/json')


@AUTH_API.route('/testauthorize', methods=["GET"])
def auth_auth():
    auth = AUTHS[flask.current_app.config["AUTH_INSTANCE"]]
    try:
        # this endpoint uses for the authorization code flow
        # see https://tools.ietf.org/html/rfc6749#section-4.1.1
        # Required parameters
        #   response_type == code
        #   client_id
        # Optional parameters
        #   redirect_uri
        #   scope
        # Recommended parameters
        #   state

        # hmm, no client authorization done, just redirects a random authorization code back to the client
        # TODO: add web pages for client authorization for the future

        # "If the request fails due to a missing, invalid, or mismatching
        # redirection URI, or if the client identifier is missing or invalid,
        # the authorization server SHOULD inform the resource owner of the
        # error and MUST NOT automatically redirect the user-agent to the
        # invalid redirection URI."
        # see https://tools.ietf.org/html/rfc6749#section-4.1.2.1
        error = None
        error_description = None
        redirect_uri = REDIRECT_URI
        if "redirect_uri" in request.args:
            redirect_uri = request.args["redirect_uri"]
            # TODO: check is the redirect_uri in the registered redirect_uris
        if not redirect_uri:
            raise AuthException("invalid_request", "missing redirect_uri")

        if "client_id" not in request.args:
            raise AuthException("invalid_request", "missing client_id")

        if "response_type" not in request.args:
            error = "invalid_request"
            error_description = "missing response_type"
        else:
            response_type = request.args["response_type"]
            if response_type != RESPONSE_TYPES.code.name:
                error = "invalid_request"
                error_description = "response_type not code"

        if "scope" in request.args:
            scopes = request.args["scope"].split()
            scope_found = IS10Utils.is_any_contain(scopes, SCOPES)
            if not scope_found:
                error = "invalid_request"
                error_description = "scope: {} are not supported".format(scopes)

        vars = {}
        if error:
            vars["error"] = error
            if error_description:
                vars["error_description"] = error_description
        else:
            # create a random authorization code
            # test it when client exchanges it for a bearer token
            auth.code = str(uuid.uuid4())
            vars = {"code": auth.code}

        if "state" in request.args:
            vars["state"] = request.args["state"]

        return redirect("{}?{}".format(redirect_uri, urllib.parse.urlencode(vars)))

    except AuthException as e:
        error_message = {"code": e.httpstatus.value,
                         "error": e.error,
                         "error_description": e.description}
        return Response(json.dumps(error_message), status=e.httpstatus.value, mimetype='application/json')


@AUTH_API.route('/testtoken', methods=["POST"])
def auth_token():
    auth = AUTHS[flask.current_app.config["AUTH_INSTANCE"]]
    try:
        scopes = []

        ctype_valid, ctype_message = check_content_type(request.headers, "application/x-www-form-urlencoded")
        if not ctype_valid:
            raise AuthException("invalid_request", ctype_message)

        request_data = request.get_data()
        if request_data:
            query = json.loads(json.dumps(parse_qs(request_data.decode('utf-8'))))

            grant_type = None
            if "grant_type" in query:
                grant_type = query["grant_type"][0]
                if grant_type not in [e.name for e in GRANT_TYPES]:
                    raise AuthException("unsupported_grant_type", "grant_type is not supported")

            code = query["code"][0] if "code" in query else None

            redirect_uri = query["redirect_uri"][0] if "redirect_uri" in query else None

            client_id = query["client_id"][0] if "client_id" in query else None

            refresh_token = query["refresh_token"][0] if "refresh_token" in query else None

            # Scope query parameter is OPTIONAL https://datatracker.ietf.org/doc/html/rfc6749#section-6
            scopes = query["scope"][0].split() if "scope" in query else SCOPE.split() if SCOPE else []
            if scopes:
                scope_found = IS10Utils.is_any_contain(scopes, SCOPES)
                if not scope_found:
                    raise AuthException("invalid_scope", "scope: {} are not supported".format(scopes))

            if grant_type:
                # Authorization Code Grant
                # see https://tools.ietf.org/html/rfc6749#section-4.1.3
                # Required parameters
                #   grant_type == authorization_code
                #   code
                #   redirect_uri
                #   client_id
                if grant_type == GRANT_TYPES.authorization_code.name:
                    if not code:
                        raise AuthException("invalid_request", "missing authorization code")
                    elif code != auth.code:
                        raise AuthException("invalid_grant", "invalid authorization code")
                    elif not redirect_uri:
                        raise AuthException("invalid_request", "missing redirect_uri")
                    elif not client_id:
                        raise AuthException("invalid_request", "missing client_id")
                    auth.code = None  # clear the authorization code after use

                # Client Credentials Grant
                # see https://tools.ietf.org/html/rfc6749#section-4.4.2
                # Required parameters
                #   grant_type == client_credentials
                # Optional parameters
                #   scope
                elif grant_type == GRANT_TYPES.client_credentials.name:
                    pass

                # Refreshing an Access Token
                # see https://tools.ietf.org/html/rfc6749#section-6
                # Required parameters
                #   grant_type == refresh_token
                #   refresh_token
                # Optional parameters
                #   scope
                elif grant_type == GRANT_TYPES.refresh_token.name:
                    if not refresh_token:
                        raise AuthException("invalid_request", "missing refresh_token")
                else:
                    raise AuthException("unsupported_grant_type", "grant_type is not supported")
            else:
                raise AuthException("invalid_request", "missing grant_type")

            # test if using private_key_jwt for client authentication
            # see https://tools.ietf.org/html/rfc7523#section-2.2
            if "client_assertion_type" in query:
                client_assertion_type = query["client_assertion_type"][0]
                if client_assertion_type == "urn:ietf:params:oauth:client-assertion-type:jwt-bearer":
                    if "client_assertion" not in query:
                        raise AuthException("invalid_request",
                                            "missing client_assertion for private_key_jwt client authentication")
                    else:
                        print(" * Fetching client jwks to validate the client_assertion for client authentication")
                        client_assertion = query["client_assertion"][0]
                        # fetch the client public keys to validate the client_assertion for client authentication
                        jwks_uri = JWKS_URI
                        if jwks_uri:
                            try:
                                jwks_response = requests.get(
                                    jwks_uri, verify=CERT_TRUST_ROOT_CA if ENABLE_HTTPS else False)
                                jwks = jwks_response.json()
                                # jwks schema validation
                                schema = load_resolved_schema(SPEC_PATH, "jwks_schema.json")
                                jsonschema.validate(jwks, schema)
                                claims = jwt.decode(client_assertion, key=jwks)
                                claims.validate()
                            except jsonschema.ValidationError as e:
                                raise AuthException(
                                    "invalid_request",
                                    "unable to extract client jwks for private_key_jwt client authentication, \
                                    schema error: {}".format(e.message))
                            except Exception:
                                raise AuthException(
                                    "invalid_request",
                                    "unable to extract client jwks for private_key_jwt client authentication")
                        else:
                            raise AuthException("invalid_request",
                                                "missing jwks_uri for private_key_jwt client authentication")
                else:
                    raise AuthException("unsupported_grant_type",
                                        "missing client_assertion_type used for private_key_jwt client authentication")

        # for the Confidential client, client_id and client_secret are embedded in the Authorization header
        auth_header = request.headers.get("Authorization", None)
        if auth_header:
            parts = auth_header.split()
            if len(parts) == 2 and parts[0].lower() == "basic":
                client_id_client_secret = base64.b64decode(parts[1]).decode('ascii')
                client_id_client_secret_array = client_id_client_secret.split(":")
                if len(client_id_client_secret_array) == 2:
                    client_id = client_id_client_secret_array[0]
                    # TODO: if client has done the client registration, then the client_secret can be used for
                    # client authentication
                    # client_secret = client_id_client_secret_array[1]
                else:
                    raise AuthException("invalid_request",
                                        "missing client_id or client_secret from authorization header")
            else:
                raise AuthException("invalid_client", "invalid authorization header")

        # client_id MUST be provided by all types of client
        if not client_id:
            raise AuthException("invalid_request", "missing client_id")

        expires_in = 60
        token = auth.generate_token(scopes, True, exp=expires_in, overrides={"client_id": client_id})

        # Successful Response
        # see https://tools.ietf.org/html/rfc6749#section-5.1
        response = {
            "access_token": token,
            "token_type": "bearer",
            "expires_in": expires_in
        }
        if grant_type == GRANT_TYPES.authorization_code.name or grant_type == GRANT_TYPES.refresh_token.name:
            refresh_token = auth.generate_token(scopes, True, exp=expires_in)
            response["refresh_token"] = refresh_token

        return jsonify(response), HTTPStatus.OK.value

    except AuthException as e:
        # Error Response
        # see https://tools.ietf.org/html/rfc6749#section-5.2
        error_message = {"code": e.httpstatus.value,
                         "error": e.error,
                         "error_description": e.description}
        return Response(json.dumps(error_message), status=e.httpstatus.value, mimetype='application/json')
