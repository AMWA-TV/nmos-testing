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
import uuid
import functools

from flask import request, jsonify, abort, Blueprint, Response
from threading import Event, Lock

from ..IS10Utils import IS10Utils
from ..Config import PORT_BASE, ENABLE_AUTH, \
    WEBSOCKET_PORT_BASE, ENABLE_HTTPS, SPECIFICATIONS
from authlib.jose import jwt
from ..IS04Utils import IS04Utils
from ..TestHelper import SubscriptionWebsocketWorker, get_default_ip, get_mocks_hostname
from .Auth import PRIMARY_AUTH


class RegistryCommon(object):
    def __init__(self):
        self.reset()

    def reset(self):
        self.resources = {"node": {}, "subscription": {}}


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
        self.subscription_lock = Lock()
        self.reset()
        self.subscription_websockets = {}
        self.query_api_id = str(uuid.uuid4())
        self.requested_query_api_version = "v1.3"

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
        self.auth_cache = {}

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
                claims = jwt.decode(token, PRIMARY_AUTH.generate_jwk())
                if "client_id" in claims:
                    return claims["client_id"]
                elif "azp" in claims:
                    return claims["azp"]
            except KeyError:
                return None
            except Exception:
                return None
        return None

    def check_authorization(self, auth, path, scope, write=False):
        if scope in self.auth_cache and \
                ((write and self.auth_cache[scope]["Write"]) or self.auth_cache[scope]["Read"]):
            return True, ""

        authorized, error_message = IS10Utils.check_authorization(auth,
                                                                  path,
                                                                  scope=scope,
                                                                  write=write)
        if authorized:
            if scope not in self.auth_cache:
                self.auth_cache[scope] = {"Read": True, "Write": write}
            else:
                self.auth_cache[scope]["Read"] = True
                self.auth_cache[scope]["Write"] = self.auth_cache[scope]["Write"] or write
        return authorized, error_message

    # Query API subscription support methods

    def subscribe_to_query_api(self, version, subscription_request, secure=False):
        """creates a subscription and starts a Subscription WebSocket"""
        resource_type = self._get_resource_type(subscription_request["resource_path"])

        resource_types = ['node', 'device', 'source', 'flow', 'sender', 'receiver']

        if resource_type not in resource_types:
            raise SubscriptionException("Unknown resource type:" + resource_type
                                        + " from resource path:" + subscription_request["resource_path"])

        try:
            # Guard against concurrent subscription creation
            self.subscription_lock.acquire()

            subscription = next(iter([subscription for id, subscription in self.get_resources()['subscription'].items()
                                if self._get_resource_type(subscription['resource_path']) == resource_type
                                and subscription['max_update_rate_ms'] == subscription_request['max_update_rate_ms']
                                and subscription['persist'] == subscription_request['persist']
                                and subscription['secure'] == subscription_request['secure']]), None)

            if subscription:
                return subscription, False

            websocket_port = WEBSOCKET_PORT_BASE + len(self.subscription_websockets)
            websocket_server = SubscriptionWebsocketWorker('0.0.0.0', websocket_port, resource_type, secure)
            websocket_server.set_queue_sync_data_grain_callback(self.queue_sync_data_grain)
            websocket_server.start()

            subscription_id = str(uuid.uuid4())

            protocol = 'wss' if secure else 'ws'

            host = get_mocks_hostname() if secure else get_default_ip()

            subscription = {'id': subscription_id,
                            'max_update_rate_ms': subscription_request['max_update_rate_ms'],
                            'params': subscription_request['params'],
                            'persist': subscription_request['persist'],
                            'resource_path': subscription_request['resource_path'],
                            'secure': secure,
                            'ws_href': protocol + '://' + host + ':' + str(websocket_port)
                            + '/x-nmos/query/' + version + '/subscriptions/' + subscription_id,
                            'version': IS04Utils.get_TAI_time()}

            self.subscription_websockets[subscription_id] = {'server': websocket_server, 'api_version': version}

            self.get_resources()['subscription'][subscription_id] = subscription
        finally:
            self.subscription_lock.release()

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
            # Guard against concurrent subscription creation
            self.subscription_lock.acquire()

            subscription_ids = [id for id, subscription in self.get_resources()['subscription'].items()
                                if self._get_resource_type(subscription['resource_path']) == resource_type]

            timestamp = IS04Utils.get_TAI_time()

            for subscription_id in subscription_ids:
                data_grain = {'grain_type': 'event',
                              'source_id': self.query_api_id,
                              'flow_id': subscription_id,
                              'origin_timestamp': timestamp,
                              'sync_timestamp': timestamp,
                              'creation_timestamp': timestamp,
                              'rate': {'denominator': 1, 'numerator': 0},
                              'duration': {'denominator': 1, 'numerator': 0},
                              'grain': {'type': 'urn:x-nmos:format:data.event',
                                        'topic': '/' + resource_type + 's/', 'data': []}}

                api_version = self.subscription_websockets[subscription_id]['api_version']

                for resource_id in resource_ids:
                    data = {'path': resource_id}
                    if pre_resources.get(resource_id):
                        data['pre'] = IS04Utils.downgrade_resource(resource_type,
                                                                   pre_resources[resource_id],
                                                                   api_version)
                    if post_resources.get(resource_id):
                        data['post'] = IS04Utils.downgrade_resource(resource_type,
                                                                    post_resources[resource_id],
                                                                    api_version)
                    data_grain["grain"]["data"].append(data)

                self.subscription_websockets[subscription_id]['server'].queue_message(json.dumps(data_grain))

        except KeyError as err:
            print('No subscription for resource type: {0}'.format(err))
        finally:
            self.subscription_lock.release()

    def _close_subscription_websockets(self):
        """ closing websockets will automatically disconnect clients and stop websockets """
        try:
            # Guard against concurrent subscription creation
            self.subscription_lock.acquire()

            for id, subscription_websocket in list(self.subscription_websockets.items()):
                subscription_websocket['server'].close()
                del self.subscription_websockets[id]
        finally:
            self.subscription_lock.release()


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
    authorized, error_message = registry.check_authorization(PRIMARY_AUTH,
                                                             request.path,
                                                             scope="x-nmos-registration")
    if authorized is not True:
        abort(authorized, description=error_message)

    base_data = [version + '/' for version in SPECIFICATIONS["is-04"]["versions"]]

    return Response(json.dumps(base_data), mimetype='application/json')


# IS-04 resources
@REGISTRY_API.route('/x-nmos/registration/<version>', methods=["GET"], strict_slashes=False)
def base_resource(version):
    registry = REGISTRIES[flask.current_app.config["REGISTRY_INSTANCE"]]
    if not registry.enabled:
        abort(503)
    authorized, error_message = registry.check_authorization(PRIMARY_AUTH,
                                                             request.path,
                                                             scope="x-nmos-registration")

    if authorized is not True:
        abort(authorized, description=error_message)
    base_data = ["resource/", "health/"]
    # Using json.dumps to support older Flask versions http://flask.pocoo.org/docs/1.0/security/#json-security

    return Response(json.dumps(base_data), mimetype='application/json')


@REGISTRY_API.route('/x-nmos/registration/<version>/resource', methods=["POST"])
def post_resource(version):
    registry = REGISTRIES[flask.current_app.config["REGISTRY_INSTANCE"]]
    if not registry.enabled:
        abort(500)
    authorized, error_message = registry.check_authorization(PRIMARY_AUTH,
                                                             request.path,
                                                             scope="x-nmos-registration",
                                                             write=True)

    if authorized is not True:
        abort(authorized, description=error_message)
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
    authorized, error_message = registry.check_authorization(PRIMARY_AUTH,
                                                             request.path,
                                                             scope="x-nmos-registration",
                                                             write=True)

    if authorized is not True:
        abort(authorized, description=error_message)
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
    authorized, error_message = registry.check_authorization(PRIMARY_AUTH,
                                                             request.path,
                                                             scope="x-nmos-registration",
                                                             write=True)

    if authorized is not True:
        abort(authorized, description=error_message)
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
    authorized, error_message = registry.check_authorization(PRIMARY_AUTH,
                                                             request.path,
                                                             scope="x-nmos-query")

    if authorized is not True:
        abort(authorized, description=error_message)

    base_data = [version + '/' for version in SPECIFICATIONS["is-04"]["versions"]]

    return Response(json.dumps(base_data), mimetype='application/json')


@REGISTRY_API.route('/x-nmos/query/<version>', methods=["GET"], strict_slashes=False)
def query(version):
    registry = REGISTRIES[flask.current_app.config["REGISTRY_INSTANCE"]]
    if not registry.enabled:
        abort(503)
    authorized, error_message = registry.check_authorization(PRIMARY_AUTH,
                                                             request.path,
                                                             scope="x-nmos-query")

    if authorized is not True:
        abort(authorized, description=error_message)

    registry.requested_query_api_version = version

    base_data = ['devices/', 'flows/', 'nodes/', 'receivers/', 'senders/', 'sources/', 'subscriptions/']

    return Response(json.dumps(base_data), mimetype='application/json')


def compare_resources(resource1, resource2):
    try:
        return IS04Utils.compare_resource_version(resource1['version'], resource2['version'])
    except Exception as e:
        print(e)
        return 0


@REGISTRY_API.route('/x-nmos/query/<version>/<resource>', methods=["GET"], strict_slashes=False)
def query_resource(version, resource):
    registry = REGISTRIES[flask.current_app.config["REGISTRY_INSTANCE"]]
    if not registry.enabled:
        abort(503)
    authorized, error_message = registry.check_authorization(PRIMARY_AUTH,
                                                             request.path,
                                                             scope="x-nmos-query")

    if authorized is not True:
        abort(authorized, description=error_message)

    registry.requested_query_api_version = version

    # NOTE: Advanced Query Syntax (RQL) is not currently supported
    # Only paging and id parameters have been implemented in the Basic Query Syntax
    # All other Basic Query Syntax parameters will be ignored, such that this endpoint will currently either:
    # * return all resources of a specified type subject to paging constraints
    # * e.g. http://<host>:<port>/x-nmos/query/<version>/nodes will return all registered nodes
    # * or return a specific resource according to the resource id
    # * e.g. http://<host>:<port>/x-nmos/query/<version>/nodes?id=<resource_id> will return a single registered node

    MIN_SINCE = "0:0"
    MAX_UNTIL = IS04Utils.get_TAI_time()

    base_data = []

    if request.args.get('paging.since') or request.args.get('paging.until'):
        registry.pagination_used = True

    since = request.args.get('paging.since') or MIN_SINCE
    until = request.args.get('paging.until') or MAX_UNTIL
    limit = min(int(request.args.get('paging.limit') or registry.paging_limit), registry.paging_limit)

    if IS04Utils.compare_resource_version(since, until) > 0:
        # If since is after until, it's a bad request
        abort(400)

    valid_resource_types = ['device', 'flow', 'node', 'receiver', 'sender', 'source', 'subscription']

    resource_type = resource.rstrip("s")

    if resource_type not in valid_resource_types:
        error_message = {"code": 404,
                         "error": "Invalid resource",
                         "debug": resource_type}
        return Response(json.dumps(error_message), status=404, mimetype='application/json')

    registry.query_api_called = True

    # Reject RQL queries
    for param in request.args:
        if param.startswith('query.rql'):
            abort(501)

    # Check to see if resource is being requested as a query
    if request.args.get('id'):
        resource_id = request.args.get('id')
        base_data.append(IS04Utils.downgrade_resource(resource_type,
                                                      registry.get_resources()[resource_type][resource_id],
                                                      version))
    else:
        data = registry.get_resources()[resource_type]

        # only paginate for version v1.1 and up
        if IS04Utils.compare_api_version("v1.1", version) > 0:
            for key, value in data.items():
                base_data.append(IS04Utils.downgrade_resource(resource_type, value, version))
        else:
            data_list = [IS04Utils.downgrade_resource(resource_type, d, version) for k, d in data.items()]
            sorted_list = sorted(data_list, key=functools.cmp_to_key(compare_resources))

            # Only if until is after the start of the resource list
            if len(sorted_list) > 0 and IS04Utils.compare_resource_version(until, sorted_list[0]['version']) > 0:
                since_index = 0
                until_index = 0

                # find since index
                for value in sorted_list:
                    if IS04Utils.compare_resource_version(since, value['version']) > 0:
                        since_index += 1

                # find until index
                for value in sorted_list:
                    if IS04Utils.compare_resource_version(until, value['version']) > 0:
                        until_index += 1

                if request.args.get('paging.until') and not request.args.get('paging.since'):
                    since_index = max(since_index, until_index - limit)
                else:
                    until_index = min(until_index, since_index + limit)

                base_data = sorted_list[since_index:until_index]

                # Calculate new since and until for inclusion in 'prev' and 'next' links
                since = sorted_list[since_index]['version'] if since_index < len(sorted_list) else until
                until = sorted_list[until_index]['version'] if until_index < len(sorted_list) else MAX_UNTIL

    response = Response(json.dumps(base_data), mimetype='application/json')

    # add pagination headers for v1.1 and up
    if IS04Utils.compare_api_version("v1.1", version) <= 0:
        protocol = "http"
        host = get_default_ip()
        port = str(registry.get_data().port)
        if ENABLE_HTTPS:
            protocol = "https"

        link = "<" + protocol + "://" + host + ":" + port \
            + "/x-nmos/query/" + version + "/" + resource_type + "s/?paging.since=" + until \
            + "&paging.limit=" + str(limit) + ">; rel=\"next\""

        link += ",<" + protocol + "://" + host + ":" + port \
            + "/x-nmos/query/" + version + "/" + resource_type + "s/?paging.until=" + since \
            + "&paging.limit=" + str(limit) + ">; rel=\"prev\""

        link += ",<" + protocol + "://" + host + ":" + port \
            + "/x-nmos/query/" + version + "/" + resource_type + "s/?paging.since=0:0&paging.limit=" \
            + str(limit) + ">; rel=\"first\""

        response.headers["Link"] = link
        response.headers["X-Paging-Limit"] = limit
        response.headers["X-Paging-Since"] = since
        response.headers["X-Paging-Until"] = until

    return response


@REGISTRY_API.route('/x-nmos/query/<version>/<resource>/<resource_id>', methods=['GET'], strict_slashes=False)
def get_resource(version, resource, resource_id):
    registry = REGISTRIES[flask.current_app.config["REGISTRY_INSTANCE"]]
    if not registry.enabled:
        abort(503)
    authorized, error_message = registry.check_authorization(PRIMARY_AUTH,
                                                             request.path,
                                                             scope="x-nmos-query")

    if authorized is not True:
        abort(authorized, description=error_message)

    registry.requested_query_api_version = version
    registry.query_api_called = True

    resource_type = resource.rstrip("s")
    data = []
    try:
        data = IS04Utils.downgrade_resource(resource_type,
                                            registry.get_resources()[resource_type][resource_id],
                                            version)
    except Exception:
        abort(404)
        pass

    return Response(json.dumps(data), mimetype='application/json')


@REGISTRY_API.route('/x-nmos/query/<version>/subscriptions', methods=["POST"])
def post_subscription(version):

    registry = REGISTRIES[flask.current_app.config["REGISTRY_INSTANCE"]]
    if not registry.enabled:
        abort(503)
    authorized, error_message = registry.check_authorization(PRIMARY_AUTH,
                                                             request.path,
                                                             scope="x-nmos-query",
                                                             write=True)

    if authorized is not True:
        abort(authorized, description=error_message)

    registry.requested_query_api_version = version
    subscription_request = request.json

    subscription_response = {}
    created = False

    try:
        # Note: 'secure' not required in request, but is required in response
        secure = subscription_request['secure'] if 'secure' in subscription_request else ENABLE_HTTPS

        # The current implementation of WebSockets in this mock Registry does not support query parameters in request
        if len(subscription_request['params']) > 0:
            abort(501)

        subscription, created = registry.subscribe_to_query_api(version, subscription_request, secure)

        subscription_response = {'id': subscription["id"],
                                 'max_update_rate_ms': subscription['max_update_rate_ms'],
                                 'params': subscription['params'],
                                 'persist': subscription['persist'],
                                 'resource_path': subscription['resource_path'],
                                 'secure': subscription['secure'],
                                 'ws_href': subscription['ws_href']}

    except SubscriptionException:
        abort(400)

    status_code = 201 if created else 200

    location = '/x-nmos/query/' + version + '/subscriptions/' + subscription["id"]

    return jsonify(subscription_response), status_code, {"Location": location}


@REGISTRY_API.route('/x-nmos/query/<version>/subscriptions/<subscription_id>', methods=["DELETE"])
def delete_subscription(version, subscription_id):

    registry = REGISTRIES[flask.current_app.config["REGISTRY_INSTANCE"]]
    if not registry.enabled:
        abort(503)
    authorized, error_message = registry.check_authorization(PRIMARY_AUTH,
                                                             request.path,
                                                             scope="x-nmos-query",
                                                             write=True)

    if authorized is not True:
        abort(authorized, description=error_message)

    registry.requested_query_api_version = version

    try:
        subscription = registry.get_resources()['subscription'].get(subscription_id)

        # Error - Subscription does not exist
        if not subscription:
            abort(404)

        # Error - Attempting to delete a subscription that is managed by the Registry
        if not subscription['persist']:
            abort(403)

        # Close subscription WebSocket server and remove from resources
        registry.subscription_websockets[subscription_id]['server'].close()
        del registry.subscription_websockets[subscription_id]
        del registry.get_resources()['subscription'][subscription_id]

    except SubscriptionException:
        abort(400)

    return "", 204


@REGISTRY_API.route('/', methods=["GET"], strict_slashes=False)
def base():
    base_data = ["I'm a mock registry"]
    return Response(json.dumps(base_data), mimetype='application/json')
