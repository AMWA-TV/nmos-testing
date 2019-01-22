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
        self.reset()

    def reset(self):
        self.last_time = time.time()
        self.last_hb_time = 0
        self.data = []
        self.resources = {"node": {}}
        self.heartbeats = []
        self.enabled = False

    def add(self, headers, payload):
        self.last_time = time.time()
        self.data.append((self.last_time, {"headers": headers, "payload": payload}))
        if "type" in payload and "data" in payload:
            if payload["type"] not in self.resources:
                self.resources[payload["type"]] = {}
            if "id" in payload["data"]:
                self.resources[payload["type"]][payload["data"]["id"]] = payload["data"]

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
@REGISTRY_API.route('/x-nmos/registration/<version>/resource', methods=["POST"])
def reg_page(version):
    if not REGISTRY.enabled:
        abort(500)
    registered = False
    try:
        # Type may not be in the list, so this could throw an exception
        if request.json["data"]["id"] in REGISTRY.resources[request.json["type"]]:
            registered = True
    except:
        pass
    REGISTRY.add(request.headers, request.json)
    if registered:
        return jsonify(request.json["data"]), 200
    else:
        return jsonify(request.json["data"]), 201


@REGISTRY_API.route('/x-nmos/registration/<version>/health/nodes/<node_id>', methods=["POST"])
def heartbeat(version, node_id):
    if not REGISTRY.enabled:
        abort(404)
    REGISTRY.heartbeat(request.headers, request.json, node_id)
    if node_id in REGISTRY.resources["node"]:
        return jsonify({"health": int(time.time())})
    else:
        abort(404)
