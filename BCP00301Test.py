# Copyright (C) 2018 British Broadcasting Corporation
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
import json

from GenericTest import GenericTest, NMOSTestException, NMOSInitException
from Config import ENABLE_HTTPS
from TestResult import Test

BCP_API_KEY = "bcp-003-01"
TMPFILE = "tls-report.json"


class BCP00301Test(GenericTest):
    """
    Runs BCP-003-01-Test
    """
    def __init__(self, apis):
        GenericTest.__init__(self, apis)
        if not ENABLE_HTTPS:
            raise NMOSInitException("BCP-003-01 can only be tested when ENABLE_HTTPS is set to True in Config.py")

    def perform_test_ssl(self, test, args=None):
        if os.path.exists(TMPFILE):
            os.remove(TMPFILE)
        if args is None:
            args = []
        try:
            ret = subprocess.run(["testssl/testssl.sh", "--jsonfile", TMPFILE, "--warnings", "off"] + args +
                                 ["{}:{}".format(self.apis[BCP_API_KEY]["hostname"], self.apis[BCP_API_KEY]["port"])])
        except Exception as e:
            raise NMOSTestException(test.DISABLED("Unable to execute testssl.sh. Please see the README for "
                                                  "installation instructions: {}".format(e)))
        return ret.returncode

    def test_01(self):
        test = Test("TLS Protocols")
        ret = self.perform_test_ssl(test, ["-p"])
        if ret != 0:
            return test.FAIL("Unable to test. See the console for further information.")
        else:
            with open(TMPFILE) as tls_data:
                tls_data = json.load(tls_data)
                for report in tls_data:
                    if report["id"] in ["SSLv2", "SSLv3", "TLS1", "TLS1_1"] and "not offered" not in report["finding"]:
                        return test.FAIL("Protocol {} must not be offered".format(report["id"].replace("_", ".")))
                    elif report["id"] in ["TLS1_2"] and report["finding"] != "offered":
                        return test.FAIL("Protocol {} must be offered".format(report["id"].replace("_", ".")))
                    elif report["id"] in ["TLS1_3"] and report["finding"] != "offered":
                        return test.WARNING("Protocol {} should be offered".format(report["id"].replace("_", ".")))
            return test.PASS()

    def test_02(self):
        test = Test("TLS Ciphers")
        ret = self.perform_test_ssl(test, ["-E"])
        if ret != 0:
            return test.FAIL("Unable to test. See the console for further information.")
        else:
            with open(TMPFILE) as tls_data:
                tls_data = json.load(tls_data)
                tls1_3_supported = False
                for report in tls_data:
                    tls1_2_shall = ["TLS_ECDHE_ECDSA_WITH_AES_128_CCM_8"]
                    tls1_2_should = ["TLS_ECDHE_ECDSA_WITH_AES_128_GCM_SHA256",
                                     "TLS_ECDHE_ECDSA_WITH_AES_256_GCM_SHA384",
                                     "TLS_ECDHE_ECDSA_WITH_AES_128_CBC_SHA256",
                                     "TLS_ECDHE_ECDSA_WITH_AES_256_CBC_SHA384",
                                     "TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256",
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
                return test.FAIL("Implementation the following TLS 1.2 ciphers is required: {}"
                                 .format(",".join(tls1_2_shall)))
            elif tls1_3_supported and len(tls1_3_shall) > 0:
                return test.FAIL("Implementation the following TLS 1.3 ciphers is required: {}"
                                 .format(",".join(tls1_3_shall)))
            elif len(tls1_2_should) > 0:
                return test.WARNING("Implementation the following TLS 1.2 ciphers is recommended: {}"
                                    .format(",".join(tls1_2_should)))
            elif tls1_3_supported and len(tls1_3_should) > 0:
                return test.WARNING("Implementation the following TLS 1.3 ciphers is recommended: {}"
                                    .format(",".join(tls1_3_should)))
            else:
                return test.PASS()
