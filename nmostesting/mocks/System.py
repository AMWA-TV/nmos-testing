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
import flask

from flask import Blueprint, Response, abort, request, jsonify
from ..Config import PORT_BASE


class System(object):
    def __init__(self, port_increment):
        self.port = PORT_BASE + 300 + port_increment
        self.reset()

    def reset(self):
        self.requests = {}
        self.enabled = False

    def enable(self):
        self.enabled = True

    def disable(self):
        self.enabled = False


# 0 = Invalid request testing System API
# 1 = Primary testing System API
# 2+ = Failover testing System APIs
NUM_SYSTEMS = 6
SYSTEMS = [System(i + 1) for i in range(NUM_SYSTEMS)]
SYSTEM_API = Blueprint('system_api', __name__)


# IS-09 resources
@SYSTEM_API.route('/x-nmos/system/<version>', methods=["GET"], strict_slashes=False)
def base_resource(version):
    system = SYSTEMS[flask.current_app.config["SYSTEM_INSTANCE"]]
    if not system.enabled:
        abort(500)
    base_data = ["global/"]
    # Using json.dumps to support older Flask versions http://flask.pocoo.org/docs/1.0/security/#json-security
    return Response(json.dumps(base_data), mimetype='application/json')


@SYSTEM_API.route('/x-nmos/system/<version>/global', methods=["GET"], strict_slashes=False)
def system_global(version):
    system = SYSTEMS[flask.current_app.config["SYSTEM_INSTANCE"]]
    if not system.enabled:
        abort(500)
    system.requests[request.remote_addr] = version
    response = {
        "id": "3b8be755-08ff-452b-b217-c9151eb21193",
        "version": "1441700172:318426300",
        "label": "ZBQ System",
        "description": "System Global Information for ZBQ",
        "tags": {},
        "is04": {
            "heartbeat_interval": 8
        },
        "ptp": {
            "announce_receipt_timeout": 2,
            "domain_number": 57
        },
        "syslogv2": {
            "hostname": "biglogger.ebu.ch",
            "port": 3477
        }
    }
    return jsonify(response)
