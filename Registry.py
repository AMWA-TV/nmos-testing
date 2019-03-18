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
import flask

from flask import request, jsonify, abort, Blueprint


class RegistryCommon(object):
    def __init__(self):
        self.reset()

    def reset(self):
        self.resources = {"node": {}}


class Registry(object):
    def __init__(self, data_store, port_increment):
        self.common = data_store
        self.port = 5000 + port_increment
        self.reset()

    def reset(self):
        self.last_time = time.time()
        self.last_hb_time = 0
        self.data = []
        self.common.reset()
        self.heartbeats = []
        self.enabled = False

    def add(self, headers, payload):
        self.last_time = time.time()
        self.data.append((self.last_time, {"headers": headers, "payload": payload}))
        if "type" in payload and "data" in payload:
            if payload["type"] not in self.common.resources:
                self.common.resources[payload["type"]] = {}
            if "id" in payload["data"]:
                self.common.resources[payload["type"]][payload["data"]["id"]] = payload["data"]

    def heartbeat(self, headers, payload, node_id):
        self.last_hb_time = time.time()
        self.heartbeats.append((self.last_hb_time, {"headers": headers, "payload": payload, "node_id": node_id}))

    def get_data(self):
        return self.data

    def get_heartbeats(self):
        return self.heartbeats

    def get_port(self):
        return self.port

    def get_resources(self):
        return self.common.resources

    def enable(self):
        self.enabled = True

    def disable(self):
        self.enabled = False


NUM_REGISTRIES = 5
REGISTRY_COMMON = RegistryCommon()
REGISTRIES = [Registry(REGISTRY_COMMON, i+1) for i in range(NUM_REGISTRIES)]
REGISTRY_API = Blueprint('registry_api', __name__)


# IS-04 resources
@REGISTRY_API.route('/x-nmos/registration/<version>/resource', methods=["POST"])
def reg_page(version):
    registry = REGISTRIES[flask.current_app.config["REGISTRY_INSTANCE"]]
    if not registry.enabled:
        abort(500)
    registered = False
    try:
        # Type may not be in the list, so this could throw an exception
        if request.json["data"]["id"] in registry.get_resources()[request.json["type"]]:
            registered = True
    except:
        pass
    registry.add(request.headers, request.json)
    if registered:
        return jsonify(request.json["data"]), 200
    else:
        return jsonify(request.json["data"]), 201


@REGISTRY_API.route('/x-nmos/registration/<version>/health/nodes/<node_id>', methods=["POST"])
def heartbeat(version, node_id):
    registry = REGISTRIES[flask.current_app.config["REGISTRY_INSTANCE"]]
    if not registry.enabled:
        abort(500)
    registry.heartbeat(request.headers, request.get_json(False, True), node_id)
    if node_id in registry.get_resources()["node"]:
        return jsonify({"health": int(time.time())})
    else:
        abort(404)
