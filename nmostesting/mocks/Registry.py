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
import json
import re

from flask import request, jsonify, abort, Blueprint, Response
from threading import Event
from ..Config import PORT_BASE, AUTH_TOKEN_PUBKEY, ENABLE_AUTH
from authlib.jose import jwt


class RegistryCommon(object):
    def __init__(self):
        self.reset()

    def reset(self):
        self.resources = {"node": {}}


class RegistryData(object):
    def __init__(self, port):
        self.port = port
        self.posts = []
        self.deletes = []
        self.heartbeats = []


class Registry(object):
    def __init__(self, data_store, port_increment):
        self.common = data_store
        self.port = PORT_BASE + 100 + port_increment  # cf. test_data/IS0401/dns_records.zone
        self.add_event = Event()
        self.delete_event = Event()
        self.reset()

    def reset(self):
        self.last_time = time.time()
        self.last_hb_time = 0
        self.data = RegistryData(self.port)
        self.common.reset()
        self.enabled = False
        self.test_first_reg = False
        self.add_event.clear()
        self.delete_event.clear()

    def add(self, headers, payload, version):
        self.last_time = time.time()
        self.add_event.set()
        self.data.posts.append((self.last_time, {"headers": headers, "payload": payload, "version": version}))
        if "type" in payload and "data" in payload:
            if payload["type"] not in self.common.resources:
                self.common.resources[payload["type"]] = {}
            if "id" in payload["data"]:
                self.common.resources[payload["type"]][payload["data"]["id"]] = payload["data"]

    def delete(self, headers, payload, version, resource_type, resource_id):
        self.last_time = time.time()
        self.delete_event.set()
        self.data.deletes.append((self.last_time, {"headers": headers, "payload": payload, "version": version,
                                                   "type": resource_type, "id": resource_id}))
        if resource_type in self.common.resources:
            self.common.resources[resource_type].pop(resource_id, None)

    def heartbeat(self, headers, payload, version, node_id):
        self.last_hb_time = time.time()
        self.data.heartbeats.append((self.last_hb_time, {"headers": headers, "payload": payload, "version": version,
                                                         "node_id": node_id}))

    def get_data(self):
        return self.data

    def get_resources(self):
        return self.common.resources

    def enable(self, first_reg=False):
        self.test_first_reg = first_reg
        self.enabled = True

    def disable(self):
        self.test_first_reg = False
        self.enabled = False

    def wait_for_registration(self, timeout):
        self.add_event.wait(timeout)

    def wait_for_delete(self, timeout):
        self.delete_event.wait(timeout)

    def has_registrations(self):
        return self.add_event.is_set()

    def _check_path_match(self, path, path_wildcards):
        path_match = False
        for path_wildcard in path_wildcards:
            pattern = path_wildcard.replace("*", ".*")
            if re.search(pattern, path):
                path_match = True
                break
        return path_match

    def check_authorized(self, headers, path, write=False):
        # TODO: Add support for BCP-003-02 checks
        if ENABLE_AUTH:
            try:
                if not request.headers["Authorization"].startswith("Bearer "):
                    return False
                token = request.headers["Authorization"].split(" ")[1]
                claims = jwt.decode(token, open(AUTH_TOKEN_PUBKEY).read())
                claims.validate()
                if not self._check_path_match(path, claims["x-nmos-registration"]["read"]):
                    return False
                if write:
                    if not self._check_path_match(path, claims["x-nmos-registration"]["write"]):
                        return False
            except KeyError:
                # TODO: Add debug which can be returned in the error response JSON
                return False
            except Exception:
                return False
        return True


# 0 = Invalid request testing registry
# 1 = Primary testing registry
# 2+ = Failover testing registries
NUM_REGISTRIES = 6
REGISTRY_COMMON = RegistryCommon()
REGISTRIES = [Registry(REGISTRY_COMMON, i + 1) for i in range(NUM_REGISTRIES)]
REGISTRY_API = Blueprint('registry_api', __name__)


# IS-04 resources
@REGISTRY_API.route('/x-nmos/registration/<version>', methods=["GET"], strict_slashes=False)
def base_resource(version):
    registry = REGISTRIES[flask.current_app.config["REGISTRY_INSTANCE"]]
    if not registry.enabled:
        abort(503)
    if not registry.check_authorized(request.headers, request.path):
        # TODO: Review error code based upon https://github.com/AMWA-TV/nmos-authorization-practice/issues/1
        abort(401)
    base_data = ["resource/", "health/"]
    # Using json.dumps to support older Flask versions http://flask.pocoo.org/docs/1.0/security/#json-security
    return Response(json.dumps(base_data), mimetype='application/json')


@REGISTRY_API.route('/x-nmos/registration/<version>/resource', methods=["POST"])
def post_resource(version):
    registry = REGISTRIES[flask.current_app.config["REGISTRY_INSTANCE"]]
    if not registry.enabled:
        abort(500)
    if not registry.check_authorized(request.headers, request.path, True):
        # TODO: Review error code based upon https://github.com/AMWA-TV/nmos-authorization-practice/issues/1
        abort(401)
    if not registry.test_first_reg:
        registered = False
        try:
            # Type may not be in the list, so this could throw an exception
            if request.json["data"]["id"] in registry.get_resources()[request.json["type"]]:
                registered = True
        except Exception:
            pass
    else:
        registered = True
    registry.add(request.headers, request.json, version)
    location = "/x-nmos/registration/{}/resource/{}/{}".format(version, request.json["type"],
                                                               request.json["data"]["id"])
    if registered:
        return jsonify(request.json["data"]), 200, {"Location": location}
    else:
        return jsonify(request.json["data"]), 201, {"Location": location}


@REGISTRY_API.route('/x-nmos/registration/<version>/resource/<resource_type>/<resource_id>', methods=["DELETE"])
def delete_resource(version, resource_type, resource_id):
    registry = REGISTRIES[flask.current_app.config["REGISTRY_INSTANCE"]]
    if not registry.enabled:
        abort(500)
    if not registry.check_authorized(request.headers, request.path, True):
        # TODO: Review error code based upon https://github.com/AMWA-TV/nmos-authorization-practice/issues/1
        abort(401)
    resource_type = resource_type.rstrip("s")
    if not registry.test_first_reg:
        registered = False
        try:
            # Type may not be in the list, so this could throw an exception
            if resource_id in registry.get_resources()[resource_type]:
                registered = True
        except Exception:
            pass
    else:
        registered = True
        if resource_type == "node":
            # Once we have seen a DELETE for a Node, ensure we respond with a 201 to future POSTs
            registry.test_first_reg = False
    registry.delete(request.headers, request.data, version, resource_type, resource_id)
    if registered:
        return "", 204
    else:
        abort(404)


@REGISTRY_API.route('/x-nmos/registration/<version>/health/nodes/<node_id>', methods=["POST"])
def heartbeat(version, node_id):
    registry = REGISTRIES[flask.current_app.config["REGISTRY_INSTANCE"]]
    if not registry.enabled:
        abort(500)
    if not registry.check_authorized(request.headers, request.path, True):
        # TODO: Review error code based upon https://github.com/AMWA-TV/nmos-authorization-practice/issues/1
        abort(401)
    if node_id in registry.get_resources()["node"]:
        # store raw request payload, in order to check for empty request bodies later
        registry.heartbeat(request.headers, request.data, version, node_id)
        return jsonify({"health": int(time.time())})
    else:
        abort(404)
