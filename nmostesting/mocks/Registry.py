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
from ..Config import PORT_BASE, AUTH_TOKEN_PUBKEY, ENABLE_AUTH, AUTH_TOKEN_ISSUER
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


class BCP00302Exception(Exception):
    pass


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
        self.auth_clients = {}

    def add(self, headers, payload, version):
        self.last_time = time.time()
        self.add_event.set()
        self.data.posts.append((self.last_time, {"headers": headers, "payload": payload, "version": version}))
        if "type" in payload and "data" in payload:
            if payload["type"] not in self.common.resources:
                self.common.resources[payload["type"]] = {}
            if "id" in payload["data"]:
                client_id = self._get_client_id(headers)
                if payload["data"]["id"] in self.auth_clients and self.auth_clients[payload["data"]["id"]] != client_id:
                    raise BCP00302Exception
                self.auth_clients[payload["data"]["id"]] = client_id
                self.common.resources[payload["type"]][payload["data"]["id"]] = payload["data"]

    def delete(self, headers, payload, version, resource_type, resource_id):
        self.last_time = time.time()
        self.delete_event.set()
        self.data.deletes.append((self.last_time, {"headers": headers, "payload": payload, "version": version,
                                                   "type": resource_type, "id": resource_id}))
        if resource_type in self.common.resources:
            client_id = self._get_client_id(headers)
            if resource_id in self.auth_clients and self.auth_clients[resource_id] != client_id:
                raise BCP00302Exception
            self.common.resources[resource_type].pop(resource_id, None)

    def heartbeat(self, headers, payload, version, node_id):
        self.last_hb_time = time.time()
        client_id = self._get_client_id(headers)
        if node_id in self.auth_clients and self.auth_clients[node_id] != client_id:
            raise BCP00302Exception
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

    def _get_client_id(self, headers):
        if ENABLE_AUTH:
            try:
                if not request.headers["Authorization"].startswith("Bearer "):
                    return False
                token = request.headers["Authorization"].split(" ")[1]
                claims = jwt.decode(token, open(AUTH_TOKEN_PUBKEY).read())
                if "client_id" in claims:
                    return claims["client_id"]
                elif "azp" in claims:
                    return claims["azp"]
            except KeyError:
                return None
            except Exception:
                return None
        return None

    def _check_path_match(self, path, path_wildcards):
        path_match = False
        for path_wildcard in path_wildcards:
            pattern = path_wildcard.replace("*", ".*")
            if re.search(pattern, path):
                path_match = True
                break
        return path_match

    def check_authorized(self, headers, path, write=False):
        if ENABLE_AUTH:
            try:
                if not request.headers["Authorization"].startswith("Bearer "):
                    return 400
                token = request.headers["Authorization"].split(" ")[1]
                claims = jwt.decode(token, open(AUTH_TOKEN_PUBKEY).read())
                claims.validate()
                if claims["iss"] != AUTH_TOKEN_ISSUER:
                    return 401
                # TODO: Check 'aud' claim matches 'mocks.<domain>'
                if not self._check_path_match(path, claims["x-nmos-registration"]["read"]):
                    return 403
                if write:
                    if not self._check_path_match(path, claims["x-nmos-registration"]["write"]):
                        return 403
            except KeyError:
                # TODO: Add debug which can be returned in the error response JSON
                return 400
            except Exception:
                # TODO: Add debug which can be returned in the error response JSON
                return 400
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
    authorized = registry.check_authorized(request.headers, request.path)
    if authorized is not True:
        abort(authorized)
    base_data = ["resource/", "health/"]
    # Using json.dumps to support older Flask versions http://flask.pocoo.org/docs/1.0/security/#json-security
    return Response(json.dumps(base_data), mimetype='application/json')


@REGISTRY_API.route('/x-nmos/registration/<version>/resource', methods=["POST"])
def post_resource(version):
    registry = REGISTRIES[flask.current_app.config["REGISTRY_INSTANCE"]]
    if not registry.enabled:
        abort(500)
    authorized = registry.check_authorized(request.headers, request.path, True)
    if authorized is not True:
        abort(authorized)
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
    try:
        registry.add(request.headers, request.json, version)
    except BCP00302Exception:
        abort(403)
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
    authorized = registry.check_authorized(request.headers, request.path, True)
    if authorized is not True:
        abort(authorized)
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
    try:
        registry.delete(request.headers, request.data, version, resource_type, resource_id)
    except BCP00302Exception:
        abort(403)
    if registered:
        return "", 204
    else:
        abort(404)


@REGISTRY_API.route('/x-nmos/registration/<version>/health/nodes/<node_id>', methods=["POST"])
def heartbeat(version, node_id):
    registry = REGISTRIES[flask.current_app.config["REGISTRY_INSTANCE"]]
    if not registry.enabled:
        abort(500)
    authorized = registry.check_authorized(request.headers, request.path, True)
    if authorized is not True:
        abort(authorized)
    if node_id in registry.get_resources()["node"]:
        # store raw request payload, in order to check for empty request bodies later
        try:
            registry.heartbeat(request.headers, request.data, version, node_id)
        except BCP00302Exception:
            abort(403)
        return jsonify({"health": int(time.time())})
    else:
        abort(404)


@REGISTRY_API.route('/x-nmos/query/<version>', methods=["GET"], strict_slashes=False)
def query(version):
    registry = REGISTRIES[flask.current_app.config["REGISTRY_INSTANCE"]]
    if not registry.enabled:
        abort(503)
    authorized = registry.check_authorized(request.headers, request.path)
    if authorized is not True:
        abort(authorized)

    resources = ['devices', 'flows', 'nodes', 'receivers', 'senders', 'sources', 'subscriptions']
    base_data = []
    for resource in resources:
        base_data.append(flask.url_for('.query_resource', version=version, resource=resource))

    return Response(json.dumps(base_data), mimetype='application/json')


@REGISTRY_API.route('/x-nmos/query/<version>/<resource>', methods=["GET"], strict_slashes=False)
def query_resource(version, resource):
    registry = REGISTRIES[flask.current_app.config["REGISTRY_INSTANCE"]]
    if not registry.enabled:
        abort(503)
    authorized = registry.check_authorized(request.headers, request.path)
    if authorized is not True:
        abort(authorized)

    resource_type = resource.rstrip("s")
    base_data = []
    try:
        # Type may not be in the list, so this could throw an exception
        data = registry.get_resources()[resource_type]
        for key, value in data.items():
            base_data.append(value)
    except Exception:
        pass

    return Response(json.dumps(base_data), mimetype='application/json')


@REGISTRY_API.route('/x-nmos/query/<version>/<resource>/<resource_id>', methods=['GET'], strict_slashes=False)
def get_resource(version, resource, resource_id):
    registry = REGISTRIES[flask.current_app.config["REGISTRY_INSTANCE"]]
    if not registry.enabled:
        abort(503)
    authorized = registry.check_authorized(request.headers, request.path)
    if authorized is not True:
        abort(authorized)

    resource_type = resource.rstrip("s")
    base_data = []
    try:
        # Type may not be in the list, so this could throw an exception
        data = registry.get_resources()[resource_type][resource_id]
    except Exception:
        pass

    return Response(json.dumps(base_data), mimetype='application/json')


@REGISTRY_API.route('/', methods=["GET"], strict_slashes=False)
def base():
    base_data = ["I'm a mock registry"]
    return Response(json.dumps(base_data), mimetype='application/json')
