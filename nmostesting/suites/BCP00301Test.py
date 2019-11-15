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

import os
import subprocess
from requests.compat import json
import ssl
import socket
import ipaddress

from ..GenericTest import GenericTest, NMOSTestException, NMOSInitException
from .. import Config as CONFIG

BCP_API_KEY = "bcp-003-01"
TMPFILE = "tls-report.json"


class BCP00301Test(GenericTest):
    """
    Runs BCP-003-01-Test
    """
    def __init__(self, apis):
        GenericTest.__init__(self, apis)
        if not CONFIG.ENABLE_HTTPS:
            raise NMOSInitException("BCP-003-01 can only be tested when ENABLE_HTTPS is set to True in Config.py")
        self.report_json = {}

    def perform_test_ssl(self, test, args=None):
        if os.path.exists(TMPFILE):
            os.remove(TMPFILE)
        if args is None:
            args = []
        arg_key = " ".join(args)
        if arg_key in self.report_json:
            return self.report_json[arg_key]
        else:
            try:
                ret = subprocess.run(["testssl/testssl.sh",
                                      "--jsonfile",
                                      TMPFILE,
                                      "--warnings",
                                      "off",
                                      "--openssl-timeout",
                                      str(CONFIG.HTTP_TIMEOUT),
                                      "--add-ca",
                                      CONFIG.CERT_TRUST_ROOT_CA
                                      ] + args + ["{}:{}".format(self.apis[BCP_API_KEY]["hostname"],
                                                                 self.apis[BCP_API_KEY]["port"])]
                                     )
                if ret.returncode == 0:
                    with open(TMPFILE) as tls_data:
                        self.report_json[arg_key] = json.load(tls_data)
                    return self.report_json[arg_key]
            except Exception as e:
                raise NMOSTestException(test.DISABLED("Unable to execute testssl.sh. Please see the README for "
                                                      "installation instructions: {}".format(e)))
        return None

    def test_01_tls_protocols(self, test):
        """TLS Protocols"""

        tls_data = self.perform_test_ssl(test, ["-p"])
        if tls_data is None:
            return test.DISABLED("Unable to test. See the console for further information.")
        else:
            for report in tls_data:
                if report["id"] in ["SSLv2", "SSLv3", "TLS1", "TLS1_1"] and "not offered" not in report["finding"]:
                    return test.FAIL("Protocol {} must not be offered".format(report["id"].replace("_", ".")))
                elif report["id"] in ["TLS1_2"] and not report["finding"].startswith("offered"):
                    return test.FAIL("Protocol {} must be offered".format(report["id"].replace("_", ".")))
                elif report["id"] in ["TLS1_3"] and not report["finding"].startswith("offered"):
                    return test.OPTIONAL("Protocol {} should be offered".format(report["id"].replace("_", ".")),
                                         "https://amwa-tv.github.io/nmos-api-security"
                                         "/best-practice-secure-comms.html#tls-versions")
            return test.PASS()

    def test_02_tls_ciphers(self, test):
        """TLS Ciphers"""

        tls_data = self.perform_test_ssl(test, ["-E"])
        if tls_data is None:
            return test.DISABLED("Unable to test. See the console for further information.")
        else:
            tls1_3_supported = False
            tls1_2_shall = ["TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256"]
            tls1_2_should = ["TLS_ECDHE_ECDSA_WITH_AES_128_GCM_SHA256",
                             "TLS_ECDHE_ECDSA_WITH_AES_256_GCM_SHA384",
                             "TLS_ECDHE_ECDSA_WITH_AES_128_CBC_SHA256",
                             "TLS_ECDHE_ECDSA_WITH_AES_256_CBC_SHA384",
                             "TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384",
                             "TLS_DHE_RSA_WITH_AES_128_GCM_SHA256",
                             "TLS_DHE_RSA_WITH_AES_256_GCM_SHA384",
                             "TLS_ECDHE_RSA_WITH_AES_128_CBC_SHA256",
                             "TLS_ECDHE_RSA_WITH_AES_256_CBC_SHA384",
                             "TLS_DHE_RSA_WITH_AES_128_CBC_SHA256",
                             "TLS_DHE_RSA_WITH_AES_256_CBC_SHA256"]
            tls1_3_shall = ["TLS_AES_128_GCM_SHA256"]
            tls1_3_should = ["TLS_AES_256_GCM_SHA384",
                             "TLS_CHACHA20_POLY1305_SHA256"]
            for report in tls_data:
                if report["finding"].startswith("TLS 1.2"):
                    cipher = report["finding"].split()[-1]
                    if cipher in tls1_2_shall:
                        tls1_2_shall.remove(cipher)
                    elif cipher in tls1_2_should:
                        tls1_2_should.remove(cipher)
                elif report["finding"].startswith("TLS 1.3"):
                    tls1_3_supported = True
                    cipher = report["finding"].split()[-1]
                    if cipher in tls1_3_shall:
                        tls1_3_shall.remove(cipher)
                    elif cipher in tls1_3_should:
                        tls1_3_should.remove(cipher)
            if len(tls1_2_shall) > 0:
                return test.FAIL("Implementation of the following TLS 1.2 ciphers is required: {}"
                                 .format(",".join(tls1_2_shall)))
            elif tls1_3_supported and len(tls1_3_shall) > 0:
                return test.FAIL("Implementation of the following TLS 1.3 ciphers is required: {}"
                                 .format(",".join(tls1_3_shall)))
            elif len(tls1_2_should) > 0:
                return test.OPTIONAL("Implementation of the following TLS 1.2 ciphers is recommended: {}"
                                     .format(",".join(tls1_2_should)), "https://amwa-tv.github.io/nmos-api-security"
                                     "/best-practice-secure-comms.html#tls-12-cipher-suites")
            elif tls1_3_supported and len(tls1_3_should) > 0:
                return test.OPTIONAL("Implementation of the following TLS 1.3 ciphers is recommended: {}"
                                     .format(",".join(tls1_3_should)), "https://amwa-tv.github.io/nmos-api-security"
                                     "/best-practice-secure-comms.html#tls-13-cipher-suites")
            else:
                return test.PASS()

    def test_03_cn_san(self, test):
        """Certificate does not use IP addresses in CN/SANs"""

        tls_data = self.perform_test_ssl(test, ["-S"])
        if tls_data is None:
            return test.DISABLED("Unable to test. See the console for further information.")
        else:
            common_name = None
            for report in tls_data:
                if report["id"].split()[0] == "cert_commonName":
                    common_name = report["finding"]
                    try:
                        ipaddress.ip_address(report["finding"])
                        return test.WARNING("CN is an IP address: {}".format(report["finding"]),
                                            "https://amwa-tv.github.io/nmos-api-security"
                                            "/best-practice-secure-comms.html"
                                            "#x509-certificates-and-certificate-authority")
                    except ValueError:
                        pass
                elif report["id"].split()[0] == "cert_subjectAltName":
                    if report["finding"].startswith("No SAN"):
                        return test.OPTIONAL("No SAN was found in the certificate",
                                             "https://amwa-tv.github.io/nmos-api-security"
                                             "/best-practice-secure-comms.html"
                                             "#x509-certificates-and-certificate-authority")
                    else:
                        alt_names = report["finding"].split()
                        if common_name not in alt_names:
                            return test.OPTIONAL("CN {} was not found in the SANs".format(common_name),
                                                 "https://amwa-tv.github.io/nmos-api-security"
                                                 "/best-practice-secure-comms.html"
                                                 "#x509-certificates-and-certificate-authority")
                        for name in alt_names:
                            try:
                                ipaddress.ip_address(name)
                                return test.WARNING("SAN is an IP address: {}".format(name),
                                                    "https://amwa-tv.github.io/nmos-api-security"
                                                    "/best-practice-secure-comms.html"
                                                    "#x509-certificates-and-certificate-authority")
                            except ValueError:
                                pass

            if common_name is None:
                return test.UNCLEAR("Unable to find CN in the testssl report")

            return test.PASS()

    def test_04_hsts(self, test):
        """HSTS Header"""

        tls_data = self.perform_test_ssl(test, ["-h"])
        if tls_data is None:
            return test.DISABLED("Unable to test. See the console for further information.")
        else:
            hsts_supported = False
            for report in tls_data:
                if report["id"] == "HSTS_time":
                    if report["severity"] == "OK":
                        hsts_supported = True
                    else:
                        hsts_supported = report["finding"]
            if hsts_supported is True:
                return test.PASS()
            elif hsts_supported is False:
                return test.OPTIONAL("Strict Transport Security (HSTS) should be supported",
                                     "https://amwa-tv.github.io/nmos-api-security"
                                     "/best-practice-secure-comms.html#http-server")
            else:
                return test.FAIL("Error in HSTS header: {}".format(hsts_supported))

    def test_05_revocation(self, test):
        """Certificate revocation method is available"""

        tls_data = self.perform_test_ssl(test, ["-S"])
        if tls_data is None:
            return test.DISABLED("Unable to test. See the console for further information.")
        else:
            for report in tls_data:
                if report["id"].split()[0] == "cert_revocation":
                    if report["severity"] == "HIGH":
                        return test.FAIL("No certificate revocation method was provided by the server")

            return test.PASS()

    def test_06_ocsp_stapling(self, test):
        """OCSP Stapling"""

        tls_data = self.perform_test_ssl(test, ["-S"])
        if tls_data is None:
            return test.DISABLED("Unable to test. See the console for further information.")
        else:
            ocsp_found = False
            for report in tls_data:
                if report["id"].split()[0] == "OCSP_stapling":
                    if report["finding"] == "not offered":
                        return test.OPTIONAL("OCSP stapling is not offered by this server",
                                             "https://amwa-tv.github.io/nmos-api-security"
                                             "/best-practice-secure-comms.html"
                                             "#x509-certificates-and-certificate-authority")
                elif report["id"].split()[0] == "cert_ocspURL":
                    if report["finding"].startswith("http"):
                        ocsp_found = True

            if not ocsp_found:
                return test.UNCLEAR("Unable to find OCSP stapling results in the testssl report")

            return test.PASS()

    def test_07_verify_host(self, test):
        """Certificate is valid and matches the host under test"""

        try:
            context = ssl.create_default_context(cafile=CONFIG.CERT_TRUST_ROOT_CA)
            hostname = self.apis[BCP_API_KEY]["hostname"]
            sock = context.wrap_socket(socket.socket(), server_hostname=hostname)
            sock.settimeout(CONFIG.HTTP_TIMEOUT)
            # Verification of certificate and CN/SAN matches is performed during connect
            sock.connect((hostname, self.apis[BCP_API_KEY]["port"]))
            sock.close()
            return test.PASS()
        except ssl.CertificateError as e:
            return test.FAIL("Certificate verification error: {}".format(e))
        except Exception as e:
            return test.FAIL(str(e))

    def test_08_rsa_ecdsa(self, test):
        """Server exposes both an RSA and ECDSA certificate"""

        tls_data = self.perform_test_ssl(test, ["-S"])
        if tls_data is None:
            return test.DISABLED("Unable to test. See the console for further information.")
        else:
            rsa_found = False
            ecdsa_found = False
            for report in tls_data:
                if report["id"].split()[0] == "cert_keySize":
                    if report["finding"].startswith("RSA"):
                        rsa_found = True
                    elif report["finding"].startswith("EC"):
                        ecdsa_found = True

            if not ecdsa_found:
                return test.WARNING("Server is not providing an ECDSA certificate")
            if not rsa_found:
                return test.WARNING("Server is not providing an RSA certificate")

            return test.PASS()

    def test_09_trust_chain(self, test):
        """Server exposes a valid chain of trust including a certificate and intermediate"""

        tls_data = self.perform_test_ssl(test, ["-S"])
        if tls_data is None:
            return test.DISABLED("Unable to test. See the console for further information.")
        else:
            for report in tls_data:
                if report["id"].split()[0] == "cert_chain_of_trust":
                    if report["severity"] != "OK":
                        return test.FAIL("One or more certificates have an incomplete chain of trust")

            return test.PASS()
