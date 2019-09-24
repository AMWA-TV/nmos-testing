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

from flask import Blueprint, make_response
from .Config import PORT_BASE


class CRLDistributionPoint(object):
    def __init__(self):
        self.port = PORT_BASE + 7  # cf. test_data/BCP00301/ca/intermediate/openssl.cnf


CRL = CRLDistributionPoint()
CRL_API = Blueprint('crl', __name__)


@CRL_API.route('/intermediate.crl.pem', methods=["GET"])
def crl_pem():
    response = None
    with open("test_data/BCP00301/ca/intermediate/crl/intermediate.crl.pem") as f:
        response = make_response(f.read())

    response.headers["Content-Type"] = "text/plain"
    return response
