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
import time
import codecs
import base64

from flask import Blueprint, Response, request, jsonify, redirect
from urllib.parse import parse_qs
from ..Config import DNS_DOMAIN, PORT_BASE, KEYS_MOCKS
from ..TestHelper import get_default_ip, get_mocks_hostname, generate_token, \
    read_RSA_private_key, generate_jwk
from zeroconf_monkey import ServiceInfo
from enum import Enum


GRANT_TYPES = Enum("grant_types", ["authorization_code", "implicit", "refresh_token", "password", "client_credentials"])
SCOPES = Enum("scopes", ["connection", "node", "query", "registration", "events", "channelmapping"])
CODE_CHALLENGE_METHODS = Enum("code_challenge_methods", ["plain", "S256"])
TOKEN_ENDPOINT_AUTH_METHODS = Enum("token_endpoint_auth_methods", [
                                   "none", "client_secret_post", "client_secret_basic", "client_secret_jwt", "private_key_jwt"])


class Auth(object):
    def __init__(self, port_increment, version="v1.0"):
        self.port = PORT_BASE + 9 + port_increment
        self.scopes = []
        self.private_keys = KEYS_MOCKS
        self.version = version

    def make_mdns_info(self, priority=0, api_ver=None, ip=None):
        """Get an mDNS ServiceInfo object in order to create an advertisement"""
        if api_ver is None:
            api_ver = self.version

        api_proto = 'https'

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
        host = get_default_ip()
        protocol = "https"
        host = get_mocks_hostname()
        return "{}://{}:{}".format(protocol, host, self.port)

    def make_metadata(self):
        host = get_default_ip()
        protocol = "https"
        host = get_mocks_hostname()
        metadata = {
            "issuer": self.make_issuer(),
            "authorization_endpoint": "{}://{}:{}/auth".format(protocol, host, self.port),
            "token_endpoint": "{}://{}:{}/token".format(protocol, host, self.port),
            "jwks_uri": "{}://{}:{}/jwks".format(protocol, host, self.port),
            "registration_endpoint": "{}://{}:{}/register".format(protocol, host, self.port),
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
        private_key = read_RSA_private_key(self.private_keys)
        return generate_jwk(private_key)

    def generate_token(self, scopes=None, write=False, azp=False, add_claims=True, overrides=None):
        protocol = "https"
        host = get_mocks_hostname()
        private_key = read_RSA_private_key(self.private_keys)
        overrides_ = {"iss": "{}://{}:{}".format(protocol, host, self.port)}
        if overrides:
            overrides_.update(overrides)
        return generate_token(private_key, scopes, write, azp, add_claims, overrides=overrides_)


# 0 = Primary mock Authorization API
# 1 = Secondary mock Authorization API, which is used for testing resources server on handling
#     access token from different Authorization server
NUM_AUTHS = 2
AUTHS = [Auth(i + 1) for i in range(NUM_AUTHS)]
AUTH_API = Blueprint('auth_pi', __name__)
PRIMARY_AUTH = AUTHS[0]
SECONDARY_AUTH = AUTHS[1]


@ AUTH_API.route('/.well-known/oauth-authorization-server', methods=["GET"])
def auth_metadata():
    auth = AUTHS[flask.current_app.config["AUTH_INSTANCE"]]

    metadata = auth.make_metadata()
    return Response(json.dumps(metadata), mimetype='application/json')


@ AUTH_API.route('/jwks', methods=["GET"])
def auth_jwks():
    auth = AUTHS[flask.current_app.config["AUTH_INSTANCE"]]

    jwks = []
    private_key = read_RSA_private_key(auth.private_keys)
    if private_key:
        jwk = generate_jwk(private_key)
        jwks = {"keys": [jwk]}

    return Response(json.dumps(jwks), mimetype='application/json')


@ AUTH_API.route('/register', methods=["POST"])
def auth_register():
    # hmm, TODO register_client_request schema validation

    # extending validation to cover those not in schema
    # hmm, maybe more to do
    redirect_uris = []
    if "redirect_uris" in request.json:
        redirect_uris.append(request.json["redirect_uris"])

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

    # pretending open client registration
    response = {
        # REQUIRED
        "client_id": str(uuid.uuid4()),
        "client_name": request.json["client_name"],
        "client_secret_expires_at": 0,
        # OPTIONAL
        "redirect_uris": redirect_uris,
        "grant_types": grant_types,
        "response_types": response_types,
        "scope": scopes,
        "token_endpoint_auth_method": token_endpoint_auth_method
    }

    if token_endpoint_auth_method == TOKEN_ENDPOINT_AUTH_METHODS.client_secret_basic.name:
        response["client_secret"] = str(uuid.uuid4())

    if "client_uri" in request.json:
        client_uri = request.json["client_uri"]
        response["client_uri"] = client_uri

    jwks_uri = None
    if "jwks_uri" in request.json:
        jwks_uri = request.json["jwks_uri"]
        response["jwks_uri"] = jwks_uri

    # hmm, more to test
    if token_endpoint_auth_method == TOKEN_ENDPOINT_AUTH_METHODS.private_key_jwt.name and not jwks_uri:
        error_message = {"code": 400,
                         "error": "Missing jwks_uri"}
        return Response(json.dumps(error_message), status=error_message["code"], mimetype='application/json')

    # hmm, TODO register_client_response schema validation

    return jsonify(response), 201


@ AUTH_API.route('/auth', methods=["GET"])
def auth_auth():
    # pretending authorization code flow
    # i.e. no validation done, just redirect a random authorization code back to client
    auth = AUTHS[flask.current_app.config["AUTH_INSTANCE"]]

    auth.scopes = request.args['scope'].split()
    vars = {'state': request.args['state'], 'code': str(uuid.uuid4())}
    return redirect("{}?{}".format(request.args['redirect_uri'], urllib.parse.urlencode(vars)))


@ AUTH_API.route('/token', methods=["POST"])
def auth_token():
    # no validation done yet, just create a token based on the given scopes
    auth = AUTHS[flask.current_app.config["AUTH_INSTANCE"]]

    client_id = None
    scopes = []
    request_data = request.get_data()
    if request_data:
        # extract scope and client_id from query parameters
        query = json.loads(json.dumps(parse_qs(request_data.decode('ascii'))))
        if "scope" in query:
            scopes = query["scope"][0].split()
        # Public client or using private_key_jwt has client_id in query
        if "client_id" in query:
            client_id = query["client_id"][0]

    # hmm, TODO Confidential client, client_id and client_secret in header
    auth_header = request.headers.get("Authorization", None)
    if auth_header:
        parts = auth_header.split()
        if len(parts) == 2 and parts[0].lower() == "basic":
            client_id_client_secret = base64.b64decode(parts[1]).decode('ascii')
            client_id_client_secret_array = client_id_client_secret.split(":")
            if len(client_id_client_secret_array) == 2:
                client_id = client_id_client_secret_array[0]
                client_secret = client_id_client_secret_array[1]

    expires_in = 60
    token = auth.generate_token(scopes, True, overrides={
        "client_id": client_id,
        "exp": int(time.time() + expires_in)})

    response = {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": expires_in
    }

    return jsonify(response), 200
