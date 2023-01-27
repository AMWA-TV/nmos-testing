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

from authlib.jose import jwk
from Crypto.PublicKey import RSA
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from flask import Blueprint, Response, request, jsonify, render_template, redirect
from OpenSSL import crypto
from urllib.parse import parse_qs
from ..Config import ENABLE_HTTPS, DNS_DOMAIN, PORT_BASE, DNS_SD_MODE, CERT_TRUST_ROOT_CA, KEY_TRUST_ROOT_CA
from ..TestHelper import get_default_ip, generate_token


class Auth(object):
    def __init__(self):
        self.port = PORT_BASE + 9
        self.scopes = []
        self.key = None

    def generate_cert(self, cert_file, key_file):
        # create a key pair
        k = crypto.PKey()
        k.generate_key(crypto.TYPE_RSA, 2048)

        # create cert
        cert = crypto.X509()
        cert.set_version(2)
        cert.get_subject().C = "GB"
        cert.get_subject().ST = "England"
        cert.get_subject().O = "NMOS Testing Ltd"
        ca_cert_subject = cert.get_subject()
        ca_cert_subject.CN = "ca.testsuite.nmos.tv"
        cert.set_issuer(ca_cert_subject)
        cert.get_subject().CN = "mocks.testsuite.nmos.tv"
        cert.set_serial_number(x509.random_serial_number())
        cert.gmtime_adj_notBefore(0)
        cert.gmtime_adj_notAfter(10*365*24*60*60)
        cert.set_pubkey(k)
        # get Root CA key
        capkey = open(KEY_TRUST_ROOT_CA, "r").read()
        ca_pkey = crypto.load_privatekey(crypto.FILETYPE_PEM, capkey)
        # get Root CA cert
        cacert = open(CERT_TRUST_ROOT_CA, "r").read()
        ca_cert = crypto.load_certificate(crypto.FILETYPE_PEM, cacert)
        # create cert extension
        san = ["DNS:mocks.{}".format(DNS_DOMAIN), "DNS: nmos-mocks.local"]
        cert_ext = []
        cert_ext.append(crypto.X509Extension(b'subjectKeyIdentifier', False, b'hash', cert))
        cert_ext.append(crypto.X509Extension(b'authorityKeyIdentifier', False, b'keyid,issuer:always', issuer=ca_cert))
        cert_ext.append(crypto.X509Extension(b'basicConstraints', False, b'CA:FALSE'))
        cert_ext.append(crypto.X509Extension(b'keyUsage', True, b'digitalSignature, keyEncipherment'))
        cert_ext.append(crypto.X509Extension(b'subjectAltName', False, ','.join(san).encode()))
        cert.add_extensions(cert_ext)

        # sign cert with Intermediate CA key
        cert.sign(ca_pkey, 'sha256')

        # write chain certificate file
        if cert_file is not None:
            with open(cert_file, "wt") as f:
                f.write(crypto.dump_certificate(crypto.FILETYPE_PEM, cert).decode("utf-8"))
                f.write(cacert)
        # write private key file
        if key_file is not None:
            with open(key_file, "wb") as f:
                pem = k.to_cryptography_key().private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.TraditionalOpenSSL,
                    encryption_algorithm=serialization.NoEncryption()
                )
                f.write(pem)

    def make_metadata(self):
        protocol = "http"
        host = get_default_ip()
        if ENABLE_HTTPS:
            protocol = "https"
            if DNS_SD_MODE == "multicast":
                host = "nmos-mocks.local"
            else:
                host = "mocks.{}".format(DNS_DOMAIN)

        metadata = {
            "issuer": "{}://{}:{}".format(protocol, host, self.port),
            "authorization_endpoint": "{}://{}:{}/auth".format(protocol, host, self.port),
            "token_endpoint": "{}://{}:{}/token".format(protocol, host, self.port),
            "jwks_uri": "{}://{}:{}/jwks".format(protocol, host, self.port),
            "registration_endpoint": "{}://{}:{}/register".format(protocol, host, self.port),
            "grant_types_supported": [
                "authorization_code",
                "implicit",
                "refresh_token",
                "password",
                "client_credentials"
            ],
            "response_types_supported": [
                "code",
                "code token"
            ],
            "scopes_supported": [
                "connection",
                "node",
                "query",
                "registration",
                "events",
                "channelmapping"
            ],
            "code_challenge_methods_supported": [
                "plain",
                "S256"
            ]
        }
        return metadata

    def generate_token(self, scopes):
        protocol = "http"
        if ENABLE_HTTPS:
            protocol = "https"
            if DNS_SD_MODE == "multicast":
                host = "nmos-mocks.local"
            else:
                host = "mocks.{}".format(DNS_DOMAIN)

        pkey = open(self.key, "r").read()
        token = generate_token(scopes, True, overrides={
            "iss": "{}://{}:{}".format(protocol, host, self.port)}, private_key=pkey)
        return token

    def shutdown(self):
        func = request.environ.get('werkzeug.server.shutdown')
        if func is None:
            raise RuntimeError('Not running with the Werkzeug Server')
        func()


AUTH = Auth()
AUTH_API = Blueprint('auth', __name__)


# special route to shutdown Auth Server
@ AUTH_API.route('/shutdown', methods=['POST'])
def shutdown():
    AUTH.shutdown()
    return 'Auth Server shutting down...'


@ AUTH_API.route('/.well-known/oauth-authorization-server', methods=["GET"])
def auth_metadata():
    metadata = AUTH.make_metadata()
    return Response(json.dumps(metadata), mimetype='application/json')


@ AUTH_API.route('/jwks', methods=["GET"])
def auth_jwks():
    # get public key from RSA private key
    pkey = open(AUTH.key, "r").read()
    rsa_key = RSA.importKey(pkey)
    public_key = rsa_key.publickey().exportKey('PEM')

    jwk_obj = jwk.dumps(public_key, kty='RSA', use="sig", key_ops="verify", alg="RS512", kid="mock.auth.kid")
    jwks = {"keys": [jwk_obj]}
    return Response(json.dumps(jwks), mimetype='application/json')


@ AUTH_API.route('/register', methods=["POST"])
def auth_register():
    # pretending open client registration
    response = {
        # REQUIRED
        "client_id": str(uuid.uuid4()),
        "client_name": request.json["client_name"],
        "client_secret": str(uuid.uuid4()),
        "client_secret_expires_at": 0,
        # OPTIONAL
        "redirect_uris": request.json["redirect_uris"],
        "grant_types": request.json["grant_types"],
        "response_types": request.json["response_types"],
        "scope": request.json["scope"],
        "token_endpoint_auth_method": request.json["token_endpoint_auth_method"]
    }

    return jsonify(response), 201


@ AUTH_API.route('/auth', methods=["GET"])
def auth_auth():
    # pretending authorization code flow
    # i.e. no validation done, just redirect a random authorization code back to client
    AUTH.scopes = request.args['scope'].split(" ")
    print("/auth AUTH.scopes: {}".format(AUTH.scopes))
    vars = {'state': request.args['state'], 'code': str(uuid.uuid4())}
    return redirect("{}?{}".format(request.args['redirect_uri'], urllib.parse.urlencode(vars)))


@ AUTH_API.route('/token', methods=["POST"])
def auth_token():
    # no validation done, just create a token based on the given scopes
    scopes = AUTH.scopes
    request_data = request.get_data()
    if request_data is not None:
        print(request.data)
        json_data = json.loads(json.dumps(parse_qs(request_data.decode('ascii'))))
        if 'scope' in json_data:
            scopes = json_data["scope"][0].split(" ")
    token = AUTH.generate_token(scopes)

    response = {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": 3600
    }

    return jsonify(response), 200
