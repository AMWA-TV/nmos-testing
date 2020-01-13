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

import subprocess

from flask import Blueprint, make_response, request, abort
from . import Config as CONFIG


class OCSPDistributionPoint(object):
    def __init__(self):
        self.port = CONFIG.PORT_BASE + 8  # cf. test_data/BCP00301/ca/intermediate/openssl.cnf


OCSP = OCSPDistributionPoint()
OCSP_API = Blueprint('ocsp', __name__)


@OCSP_API.route('/', methods=["POST"])
def ocsp_response():
    if request.headers["Content-Type"] != "application/ocsp-request":
        abort(400)

    with open("test_data/BCP00301/ca/ocspreq.der", "wb") as f:
        f.write(request.data)

    try:
        subprocess.run(["openssl", "ocsp", "-index", "test_data/BCP00301/ca/intermediate/index.txt",
                        "-rsigner", "test_data/BCP00301/ca/intermediate/certs/intermediate.cert.pem",
                        "-rkey", "test_data/BCP00301/ca/intermediate/private/intermediate.key.pem",
                        "-CA", "test_data/BCP00301/ca/intermediate/certs/ca-chain.cert.pem",
                        "-reqin", "test_data/BCP00301/ca/ocspreq.der",
                        "-respout", "test_data/BCP00301/ca/ocspresp.der"])
    except Exception as e:
        print(" * ERROR: {}".format(e))
        abort(500)

    response = None
    with open("test_data/BCP00301/ca/ocspresp.der", "rb") as f2:
        response = make_response(f2.read())

    response.headers["Content-Type"] = "application/ocsp-response"
    return response
