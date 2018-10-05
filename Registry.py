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

import time

from flask import request, jsonify, abort, Blueprint


class Registry(object):
    def __init__(self):
        self.last_time = 0
        self.last_hb_time = 0
        self.data = []
        self.heartbeats = []
        self.enabled = False

    def reset(self):
        self.last_time = time.time()
        self.last_hb_time = 0
        self.data = []
        self.heartbeats = []

    def add(self, headers, payload):
        self.last_time = time.time()
        self.data.append((self.last_time, {"headers": headers, "payload": payload}))

    def heartbeat(self, headers, payload, node_id):
        self.last_hb_time = time.time()
        self.heartbeats.append((self.last_hb_time, {"headers": headers, "payload": payload, "node_id": node_id}))

    def get_data(self):
        return self.data

    def get_heartbeats(self):
        return self.heartbeats

    def enable(self):
        self.enabled = True

    def disable(self):
        self.enabled = False


REGISTRY = Registry()
REGISTRY_API = Blueprint('registry_api', __name__)


# IS-04 resources
@REGISTRY_API.route('/x-nmos/registration/v1.2/resource', methods=["POST"])
def reg_page():
    if not REGISTRY.enabled:
        abort(500)
    REGISTRY.add(request.headers, request.json)
    # TODO: Ensure status code returned is correct
    return jsonify(request.json["data"])


@REGISTRY_API.route('/x-nmos/registration/v1.2/health/nodes/<node_id>', methods=["POST"])
def heartbeat(node_id):
    if not REGISTRY.enabled:
        abort(404)
    REGISTRY.heartbeat(request.headers, request.json, node_id)
    # TODO: Ensure status code returned is correct
    return jsonify({"health": int(time.time())})
