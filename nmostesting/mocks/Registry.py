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
import uuid
import functools

from flask import request, jsonify, abort, Blueprint, Response
from threading import Event
from ..Config import PORT_BASE, AUTH_TOKEN_PUBKEY, ENABLE_AUTH, AUTH_TOKEN_ISSUER, WEBSOCKET_PORT_BASE
from authlib.jose import jwt
from ..NMOSUtils import NMOSUtils
from ..TestHelper import SubscriptionWebsocketWorker, get_default_ip


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


class SubscriptionException(Exception):
    pass


class BCP00302Exception(Exception):
    pass


class Registry(object):
    def __init__(self, data_store, port_increment):
        self.common = data_store
        self.port = PORT_BASE + 100 + port_increment  # cf. test_data/IS0401/dns_records.zone
        self.add_event = Event()
        self.delete_event = Event()
        self.reset()
        self.subscriptions = {}
        # Query API Id for subscriptions. Hmm is this not defined somewhere already?
        self.query_api_id = str(uuid.uuid4())

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
        self.query_api_called = False
        self.paging_limit = 100
        self.pagination_used = False

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

                # Is this is an existing resource that's being updated - will be None if doesn't already exist
                existing_resource = self.common.resources[payload["type"]].get(payload["data"]["id"])

                self.common.resources[payload["type"]][payload["data"]["id"]] = payload["data"]

                self._queue_single_data_grain(
                    payload["type"], payload["data"]["id"], existing_resource, payload["data"])

    def delete(self, headers, payload, version, resource_type, resource_id):
        self.last_time = time.time()
        self.delete_event.set()
        self.data.deletes.append((self.last_time, {"headers": headers, "payload": payload, "version": version,
                                                   "type": resource_type, "id": resource_id}))
        if resource_type in self.common.resources:
            client_id = self._get_client_id(headers)
            if resource_id in self.auth_clients and self.auth_clients[resource_id] != client_id:
                raise BCP00302Exception
            self._queue_single_data_grain(
                resource_type, resource_id, self.common.resources[resource_type][resource_id], None)
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
        self._close_subscription_websockets()

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

    # Query API subscription support methods

    def subscribe_to_query_api(self, version, resource_path):
        """creates a subscription and starts a Subscription WebSocket"""

        resource_type = self._get_resource_type(resource_path)

        resource_types = ['node', 'device', 'source', 'flow', 'sender', 'receiver']

        if resource_type not in resource_types:
            raise SubscriptionException("Unknown resource type:" + resource_type
                                        + " from resource path:" + resource_path)

        # return existing subscription for this resource type if it already exists
        if resource_type in self.subscriptions:
            return self.subscriptions[resource_type], False  # subscription_created=False

        websocket_port = WEBSOCKET_PORT_BASE + resource_types.index(resource_type)
        websocket_server = SubscriptionWebsocketWorker('0.0.0.0', websocket_port, resource_type)
        websocket_server.set_queue_sync_data_grain_callback(self.queue_sync_data_grain)
        websocket_server.start()

        subscription_id = str(uuid.uuid4())
        subscription = {'id': subscription_id,
                        'resource_path': resource_path,
                        'websocket': websocket_server,
                        'query_api_id': self.query_api_id,
                        'ws_href': 'ws://' + get_default_ip() + ':' + str(websocket_port)
                        + '/x-nmos/query/' + version + '/subscriptions/' + subscription_id,
                        'location': '/x-nmos/query/' + version + '/subscriptions/' + subscription_id}
        self.subscriptions[resource_type] = subscription

        return subscription, True  # subscription_created=True

    def _get_resource_type(self, resource_path):
        """ Extract Resource Type from Resource Path """
        remove_query = resource_path.split('?')[0]  # remove query parameters
        remove_slashes = remove_query.strip('/')  # strip leading and trailing slashes
        return remove_slashes.rstrip('s')  # remove trailing 's'

    def queue_sync_data_grain(self, resource_type):
        """ queues sync data grain to be sent by subscription websocket for resource_type"""

        resource_data = self.get_resources()[resource_type]

        self._create_and_queue_data_grains(resource_type, resource_data.keys(), resource_data, resource_data)

    def _queue_single_data_grain(self, resource_type, resource_id, pre_resource, post_resource):
        """ queues data grain to be sent by subscription websocket for resource_type """

        self._create_and_queue_data_grains(
            resource_type, [resource_id], {resource_id: pre_resource}, {resource_id: post_resource})

    def _create_and_queue_data_grains(self, resource_type, resource_ids, pre_resources, post_resources):
        """ creates a data grain and queues on subscription websocket for resource_type"""

        try:
            subscription = self.subscriptions[resource_type]

            timestamp = NMOSUtils.get_TAI_time()

            data_grain = {'grain_type': 'event',
                          'source_id': subscription['query_api_id'],
                          'flow_id': subscription["id"],
                          'origin_timestamp': timestamp,
                          'sync_timestamp': timestamp,
                          'creation_timestamp': timestamp,
                          'rate': {'denominator': 1, 'numerator': 0},
                          'duration': {'denominator': 1, 'numerator': 0},
                          'grain': {'type': 'urn:x-nmos:format:data.event',
                                    'topic': '/' + resource_type + 's/', 'data': []}}

            for resource_id in resource_ids:
                data = {'path': resource_id}
                if pre_resources.get(resource_id):
                    data['pre'] = pre_resources[resource_id]
                if post_resources.get(resource_id):
                    data['post'] = post_resources[resource_id]
                data_grain["grain"]["data"].append(data)

            subscription['websocket'].queue_message(json.dumps(data_grain))

        except KeyError as err:
            print('No subscription for resource type: {0}'.format(err))

    def _close_subscription_websockets(self):
        """ closing websockets will automatically disconnect clients and stop websockets """

        print('Closing registry subscription websockets')
        for subscription in self.subscriptions.values():
            subscription['websocket'].close()

        self.subscriptions = {}


# 0 = Invalid request testing registry
# 1 = Primary testing registry
# 2+ = Failover testing registries
NUM_REGISTRIES = 6
REGISTRY_COMMON = RegistryCommon()
REGISTRIES = [Registry(REGISTRY_COMMON, i + 1) for i in range(NUM_REGISTRIES)]
REGISTRY_API = Blueprint('registry_api', __name__)


@REGISTRY_API.route('/x-nmos', methods=["GET"], strict_slashes=False)
def x_nmos():
    registry = REGISTRIES[flask.current_app.config["REGISTRY_INSTANCE"]]
    if not registry.enabled:
        abort(503)

    base_data = ['query/', 'registration/']

    return Response(json.dumps(base_data), mimetype='application/json')


@REGISTRY_API.route('/x-nmos/registration', methods=["GET"], strict_slashes=False)
def registration_root():
    registry = REGISTRIES[flask.current_app.config["REGISTRY_INSTANCE"]]
    if not registry.enabled:
        abort(503)
    authorized = registry.check_authorized(request.headers, request.path)
    if authorized is not True:
        abort(authorized)

    base_data = ['v1.0/', 'v1.1/', 'v1.2/', 'v1.3/']

    return Response(json.dumps(base_data), mimetype='application/json')


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
    location = "/x-nmos/registration/{}/resource/{}s/{}".format(version, request.json["type"],
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
    except KeyError:
        abort(404)
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


@REGISTRY_API.route('/x-nmos/query', methods=["GET"], strict_slashes=False)
def query_root():
    registry = REGISTRIES[flask.current_app.config["REGISTRY_INSTANCE"]]
    if not registry.enabled:
        abort(503)
    authorized = registry.check_authorized(request.headers, request.path)
    if authorized is not True:
        abort(authorized)

    base_data = ['v1.0/', 'v1.1/', 'v1.2/', 'v1.3/']

    return Response(json.dumps(base_data), mimetype='application/json')


@REGISTRY_API.route('/x-nmos/query/<version>', methods=["GET"], strict_slashes=False)
def query(version):
    registry = REGISTRIES[flask.current_app.config["REGISTRY_INSTANCE"]]
    if not registry.enabled:
        abort(503)
    authorized = registry.check_authorized(request.headers, request.path)
    if authorized is not True:
        abort(authorized)

    base_data = ['devices/', 'flows/', 'nodes/', 'receivers/', 'senders/', 'sources/', 'subscriptions/']

    return Response(json.dumps(base_data), mimetype='application/json')


def compare_resources(resource1, resource2):
    try:
        return NMOSUtils.compare_resource_version(resource1['version'], resource2['version'])
    except Exception as e:
        print(e)
        return 0


@REGISTRY_API.route('/x-nmos/query/<version>/<resource>', methods=["GET"], strict_slashes=False)
def query_resource(version, resource):
    registry = REGISTRIES[flask.current_app.config["REGISTRY_INSTANCE"]]
    if not registry.enabled:
        abort(503)
    authorized = registry.check_authorized(request.headers, request.path)
    if authorized is not True:
        abort(authorized)

    MIN_SINCE = "0:0"
    MAX_UNTIL = "9999999999:9999999"

    base_data = []

    if request.args.get('paging.since') or request.args.get('paging.until'):
        registry.pagination_used = True

    since = request.args.get('paging.since') if request.args.get('paging.since') else MIN_SINCE
    until = request.args.get('paging.until') if request.args.get('paging.until') else MAX_UNTIL
    new_until = until

    try:
        valid_resource_types = ['device', 'flow', 'node', 'receiver', 'sender', 'source', 'subscription']

        resource_type = resource.rstrip("s")

        if resource_type not in valid_resource_types:
            error_message = {"code": 404,
                             "error": "Invalid resource",
                             "debug": resource_type}
            return Response(json.dumps(error_message), status=404, mimetype='application/json')

        registry.query_api_called = True

        # Check to see if resource is being requested as a query
        if request.args.get('id'):
            resource_id = request.args.get('id')
            base_data.append(registry.get_resources()[resource_type][resource_id])
        else:
            data = registry.get_resources()[resource_type]

            # only paginate for version v1.3 and up
            if NMOSUtils.compare_api_version("v1.1", version) > 0:
                for key, value in data.items():
                    base_data.append(value)
            else:
                data_list = [d for k, d in data.items()]
                sorted_list = sorted(data_list, key=functools.cmp_to_key(compare_resources))

                result_count = 0
                for value in sorted_list:
                    if NMOSUtils.compare_resource_version(value['version'], since) >= 0 \
                            and NMOSUtils.compare_resource_version(until, value['version']) > 0:
                        if result_count < registry.paging_limit:
                            base_data.append(value)
                            result_count += 1
                        else:
                            new_until = value['version']
                            break

    except Exception:
        pass

    response = Response(json.dumps(base_data), mimetype='application/json')

    # add pagination headers for v1.1 and up
    if NMOSUtils.compare_api_version("v1.1", version) <= 0:
        link = ""
        if new_until != MAX_UNTIL:
            link += "<http://localhost:5102/x-nmos/query/v1.3/" + resource_type + "s/?paging.since=" + new_until \
                + "&paging.limit=" + str(registry.paging_limit) + ">; rel=\"next\""

        if since != MIN_SINCE:
            if link != "":
                link += ","
            link += "<http://localhost:5102/x-nmos/query/v1.3/" + resource_type + "s/?paging.since=0:0&paging.limit=" \
                + str(registry.paging_limit) + ">; rel=\"first\""

        if link != "":
            response.headers["Link"] = link
        response.headers["X-Paging-Limit"] = registry.paging_limit
        response.headers["X-Paging-Since"] = since
        response.headers["X-Paging-Until"] = new_until
        response.headers["X-Ancestry-Generations"] = 1

    return response


@REGISTRY_API.route('/x-nmos/query/<version>/<resource>/<resource_id>', methods=['GET'], strict_slashes=False)
def get_resource(version, resource, resource_id):
    registry = REGISTRIES[flask.current_app.config["REGISTRY_INSTANCE"]]
    if not registry.enabled:
        abort(503)
    authorized = registry.check_authorized(request.headers, request.path)
    if authorized is not True:
        abort(authorized)

    registry.query_api_called = True

    resource_type = resource.rstrip("s")
    data = []
    try:
        data = registry.get_resources()[resource_type][resource_id]
    except Exception:
        abort(404)
        pass

    return Response(json.dumps(data), mimetype='application/json')


@REGISTRY_API.route('/x-nmos/query/<version>/subscriptions', methods=["POST"])
def post_subscription(version):

    registry = REGISTRIES[flask.current_app.config["REGISTRY_INSTANCE"]]
    if not registry.enabled:
        abort(503)
    authorized = registry.check_authorized(request.headers, request.path)
    if authorized is not True:
        abort(authorized)

    subscription_request = request.json

    subscription_response = {}
    created = False

    try:
        subscription, created = registry.subscribe_to_query_api(version, subscription_request["resource_path"])

        # Note: 'secure' not required in request, but is required in response
        secure = subscription_request['secure'] if 'secure' in subscription_request else False

        subscription_response = {'id': subscription["id"],
                                 'max_update_rate_ms': subscription_request['max_update_rate_ms'],
                                 'params': subscription_request['params'],
                                 'persist': subscription_request['persist'],
                                 'resource_path': subscription['resource_path'],
                                 'secure': secure,
                                 'ws_href': subscription['ws_href']}

    except SubscriptionException as e:
        print('Subscription failed: ' + e.args[0])

    status_code = 201 if created else 200

    return jsonify(subscription_response), status_code, {"Location": subscription.get('location')}


@REGISTRY_API.route('/', methods=["GET"], strict_slashes=False)
def base():
    base_data = ["I'm a mock registry"]
    return Response(json.dumps(base_data), mimetype='application/json')
