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

from Crypto.PublicKey import RSA
from authlib.jose import jwt, JsonWebKey

import re
import time
import uuid
from datetime import datetime, timedelta, timezone

from .NMOSUtils import NMOSUtils
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtensionOID, NameOID
from flask import request
from .TestHelper import get_default_ip, get_mocks_hostname

from . import Config as CONFIG


class IS10Utils(NMOSUtils):
    def __init__(self, url):
        NMOSUtils.__init__(self, url)

    @staticmethod
    def read_RSA_private_key(private_key_files):
        """Load the 1st RSA private key from the given private key files"""
        for private_key_file in private_key_files:
            private_key = open(private_key_file, "r").read()
            if private_key.find("BEGIN RSA PRIVATE KEY") != -1:
                return private_key
        return None

    @staticmethod
    def generate_jwk(rsa_private_key):
        """Generate the JWK for a given RSA private key"""
        rsa_key = RSA.importKey(rsa_private_key)
        public_key = rsa_key.publickey().exportKey(format="PEM")
        return JsonWebKey.import_key(public_key, {"kty": "RSA", "use": "sig",
                                                  "key_ops": "verify", "alg": "RS512"}).as_dict()

    @staticmethod
    def generate_token(rsa_private_key, scopes=None, write=False, azp=False, add_claims=True, exp=3600, overrides=None):
        """Generate the access token with the given parameters"""
        if scopes is None:
            scopes = []
        header = {"typ": "JWT", "alg": "RS512"}
        protocol = "http"
        host = get_default_ip()
        if CONFIG.ENABLE_HTTPS:
            protocol = "https"
            host = get_mocks_hostname()
        payload = {"iss": "{}://{}".format(protocol, host),
                   "sub": "test@{}".format(CONFIG.DNS_DOMAIN),
                   "aud": ["{}://*.{}".format(protocol, CONFIG.DNS_DOMAIN), "{}://*.local".format(protocol)],
                   "exp": int(time.time() + exp),
                   "iat": int(time.time()),
                   "scope": " ".join(scopes)}
        if azp:
            payload["azp"] = str(uuid.uuid4())
        else:
            payload["client_id"] = str(uuid.uuid4())
        nmos_claims = {}
        if add_claims:
            for api in scopes:
                nmos_claims["x-nmos-{}".format(api)] = {"read": ["*"]}
                if write:
                    nmos_claims["x-nmos-{}".format(api)]["write"] = ["*"]
        payload.update(nmos_claims)
        if overrides:
            payload.update(overrides)
        token = jwt.encode(header, payload, rsa_private_key).decode()
        return token

    @staticmethod
    def make_key_cert_files(cert_file, key_file):
        """Create a 10 years CA Root signed certificate for the mock server """
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

        cacert = open(CONFIG.CERT_TRUST_ROOT_CA, "r").read()
        ca_cert = x509.load_pem_x509_certificate(cacert.encode("utf-8"))

        subject = x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, "GB"),
            x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "England"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "NMOS Testing Ltd"),  # noqa: E741
            x509.NameAttribute(NameOID.COMMON_NAME, "mocks.{}".format(CONFIG.DNS_DOMAIN)),
        ])

        public_key = private_key.public_key()
        now = datetime.now(timezone.utc)
        try:
            issuer_ski = ca_cert.extensions.get_extension_for_oid(
                ExtensionOID.SUBJECT_KEY_IDENTIFIER
            ).value
            aki = x509.AuthorityKeyIdentifier.from_issuer_subject_key_identifier(issuer_ski)
        except x509.ExtensionNotFound:
            aki = x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_cert.public_key())

        builder = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(ca_cert.subject)
            .public_key(public_key)
            .serial_number(x509.random_serial_number())
            .not_valid_before(now)
            .not_valid_after(now + timedelta(days=10 * 365))
            .add_extension(
                x509.SubjectKeyIdentifier.from_public_key(public_key), critical=False
            )
            .add_extension(aki, critical=False)
            .add_extension(
                x509.BasicConstraints(ca=False, path_length=None), critical=False
            )
            .add_extension(
                x509.KeyUsage(
                    digital_signature=True,
                    key_encipherment=True,
                    content_commitment=False,
                    data_encipherment=False,
                    key_agreement=False,
                    encipher_only=False,
                    decipher_only=False,
                    key_cert_sign=False,
                    crl_sign=False,
                ),
                critical=True,
            )
            .add_extension(
                x509.SubjectAlternativeName(
                    [
                        x509.DNSName("mocks.{}".format(CONFIG.DNS_DOMAIN)),
                        x509.DNSName("nmos-mocks.local"),
                    ]
                ),
                critical=False,
            )
        )

        capkey = open(CONFIG.KEY_TRUST_ROOT_CA, "r").read()
        ca_private_key = serialization.load_pem_private_key(
            capkey.encode("utf-8"), password=None
        )
        cert = builder.sign(ca_private_key, hashes.SHA256())

        if cert_file is not None:
            with open(cert_file, "wt") as f:
                f.write(cert.public_bytes(serialization.Encoding.PEM).decode("utf-8"))
                f.write(cacert)
        if key_file is not None:
            with open(key_file, "wb") as f:
                pem = private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.TraditionalOpenSSL,
                    encryption_algorithm=serialization.NoEncryption(),
                )
                f.write(pem)

    @staticmethod
    def is_any_contain(list, enum):
        """Is any of the list items found in the enum list """
        for item in list:
            if item in [e.name for e in enum]:
                return True
        return False

    @staticmethod
    def check_authorization(auth, path, scope="x-nmos-registration", write=False):
        def _check_path_match(path, path_wildcards):
            path_match = False
            for path_wildcard in path_wildcards:
                pattern = path_wildcard.replace("*", ".*")
                if re.search(pattern, path):
                    path_match = True
                    break
            return path_match

        if CONFIG.ENABLE_AUTH:
            try:
                if "Authorization" not in request.headers:
                    return 400, "Authorization header not found"
                if not request.headers["Authorization"].startswith("Bearer "):
                    return 400, "Bearer not found in Authorization header"
                token = request.headers["Authorization"].split(" ")[1]
                claims = jwt.decode(token, auth.generate_jwk())
                claims.validate()
                if claims["iss"] != auth.make_issuer():
                    return 401, f"Unexpected issuer, expected: {auth.make_issuer()}, actual: {claims['iss']}"
                # TODO: Check 'aud' claim matches 'mocks.<domain>'
                if not _check_path_match(path, claims[scope]["read"]):
                    return 403, f"Paths mismatch for {scope} read claims"
                if write and not _check_path_match(path, claims[scope]["write"]):
                    return 403, f"Paths mismatch for {scope} write claims"
            except KeyError as err:
                return 400, f"KeyError: {err}"
            except Exception as err:
                return 400, f"Exception: {err}"
        return True, ""
