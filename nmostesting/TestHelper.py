# Copyright (C) 2018 Riedel Communications GmbH & Co. KG
#
# Modifications Copyright 2018 British Broadcasting Corporation
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

import asyncio
import ipaddress
import threading
import requests
import websocket
import websockets
import ssl
import os
import jsonref
import netifaces
import paho.mqtt.client as mqtt
import time
import uuid
from copy import copy
from pathlib import Path
from enum import IntEnum
from numbers import Number
from functools import cmp_to_key
from collections.abc import KeysView
from urllib.parse import urlparse
from authlib.jose import jwt

from . import Config as CONFIG


class JsonType(IntEnum):
    NULL = 0
    BOOLEAN = 1
    NUMBER = 2
    STRING = 3
    ARRAY = 4
    OBJECT = 5

    @classmethod
    def of(cls, json):
        if json is None:
            return cls.NULL
        # must check bool before Number
        if isinstance(json, bool):
            return cls.BOOLEAN
        if isinstance(json, Number):
            return cls.NUMBER
        if isinstance(json, str):
            return cls.STRING
        if isinstance(json, list) or isinstance(json, KeysView):
            return cls.ARRAY
        if isinstance(json, dict):
            return cls.OBJECT
        raise TypeError('Non-JSON type')

    @classmethod
    def eq(cls, json1, json2):
        return cls._cmp_json(json1, json2) == 0

    @classmethod
    def lt(cls, json1, json2):
        return cls._cmp_json(json1, json2) < 0

    @classmethod
    def _cmp_json(cls, json1, json2):
        # compare JSON type first
        t1 = cls.of(json1)
        t2 = cls.of(json2)
        if t1 < t2:
            return -1
        if t2 < t1:
            return 1
        # only compare values if types are the same
        return {
            cls.NULL: cls._cmp_null,
            cls.BOOLEAN: cls._cmp_scalar,
            cls.NUMBER: cls._cmp_scalar,
            cls.STRING: cls._cmp_scalar,
            cls.OBJECT: cls._cmp_object,
            cls.ARRAY: cls._cmp_array,
        }[t1](json1, json2)

    @classmethod
    def _cmp_null(cls, lhs, rhs):
        # all nulls are equal
        return 0

    @classmethod
    def _cmp_scalar(cls, lhs, rhs):
        # '<' is supported by bool, Number and str
        if lhs < rhs:
            return -1
        if rhs < lhs:
            return 1
        return 0

    @classmethod
    def _cmp_array(cls, lhs, rhs):
        # in NMOS APIs, JSON arrays usually represent lists or sets in which ordering
        # isn't important, so sort the elements of both arrays before comparing them
        key = cmp_to_key(cls._cmp_json)
        for lval, rval in zip(sorted(lhs, key=key), sorted(rhs, key=key)):
            cmp = cls._cmp_json(lval, rval)
            if cmp != 0:
                return cmp
        if len(lhs) < len(rhs):
            return -1
        if len(rhs) < len(lhs):
            return 1
        return 0

    @classmethod
    def _cmp_object(cls, lhs, rhs):
        for lkey, rkey in zip(sorted(lhs.keys()), sorted(rhs.keys())):
            if lkey < rkey:
                return -1
            if rkey < lkey:
                return 1
            cmp = cls._cmp_json(lhs[lkey], rhs[rkey])
            if cmp != 0:
                return cmp
        if len(lhs) < len(rhs):
            return -1
        if len(rhs) < len(lhs):
            return 1
        return 0


def compare_json(json1, json2):
    """Compares two JSON values for equality"""
    return JsonType.eq(json1, json2)


def has_jsonref(json):
    if isinstance(json, list) or isinstance(json, KeysView):
        for item in json:
            if has_jsonref(item):
                return True
    elif isinstance(json, dict):
        if "$ref" in json:
            return True
        for key in json:
            if has_jsonref(json[key]):
                return True
    return False


def get_default_ip():
    """Get this machine's preferred IPv4 address"""
    if CONFIG.BIND_INTERFACE is None:
        default_gw = netifaces.gateways()['default']
        if netifaces.AF_INET in default_gw:
            preferred_interface = default_gw[netifaces.AF_INET][1]
        else:
            interfaces = netifaces.interfaces()
            preferred_interface = next((i for i in interfaces if i != 'lo'), interfaces[0])
    else:
        preferred_interface = CONFIG.BIND_INTERFACE
    return netifaces.ifaddresses(preferred_interface)[netifaces.AF_INET][0]['addr']


def get_mocks_hostname():
    return "mocks." + CONFIG.DNS_DOMAIN if CONFIG.DNS_SD_MODE == "unicast" else "nmos-mocks.local"


def is_ip_address(arg):
    """True if arg is an IPv4 or IPv6 address"""
    try:
        ipaddress.ip_address(arg)
        return True
    except ValueError:
        return False


def do_request(method, url, headers=None, **kwargs):
    """Perform a basic HTTP request with appropriate error handling"""
    response = None
    try:
        s = requests.Session()

        if not headers:
            headers = {}

        # CORS preflight requests do not use Auth
        is_CORS_preflight = method.upper() == "OPTIONS" and "Access-Control-Request-Method" in headers
        if not is_CORS_preflight and "Authorization" not in headers and CONFIG.ENABLE_AUTH and CONFIG.AUTH_TOKEN:
            headers["Authorization"] = "Bearer " + CONFIG.AUTH_TOKEN

        # all requests must have Origin to qualify as CORS requests
        headers["Origin"] = "null"

        req = requests.Request(method, url, headers={k: v for k, v in headers.items() if v is not None}, **kwargs)
        prepped = s.prepare_request(req)
        settings = s.merge_environment_settings(prepped.url, {}, None, CONFIG.CERT_TRUST_ROOT_CA, None)
        response = s.send(prepped, timeout=CONFIG.HTTP_TIMEOUT, **settings)
        if prepped.url.startswith("https://"):
            if not response.url.startswith("https://"):
                return False, "Redirect changed protocol"
            if response.history is not None:
                for res in response.history:
                    if not res.url.startswith("https://"):
                        return False, "Redirect changed protocol"
        return True, response
    except requests.exceptions.Timeout:
        return False, "Connection timeout"
    except requests.exceptions.TooManyRedirects:
        return False, "Too many redirects"
    except requests.exceptions.ConnectionError as e:
        return False, str(e)
    except requests.exceptions.RequestException as e:
        return False, str(e)
    finally:
        print("{} {} {}".format(method.upper(), url, response.status_code if response is not None else "<no response>"))


def load_resolved_schema(spec_path, file_name=None, schema_obj=None, path_prefix=True):
    """
    Parses JSON as well as resolves any `$ref`s, including references to
    local files and remote (HTTP/S) files.
    """

    # Only one of file_name or schema_obj must be set
    assert bool(file_name) != bool(schema_obj)

    if path_prefix:
        spec_path = os.path.join(spec_path, "APIs/schemas/")
    base_path = os.path.abspath(spec_path)
    if not base_path.endswith("/"):
        base_path = base_path + "/"
    if os.name == "nt":
        base_uri_path = "file:///" + base_path.replace('\\', '/')
    else:
        base_uri_path = "file://" + base_path

    # $id sets the Base URI to be different from the Retrieval URI
    # but we want to load schema files from the cache where possible
    # see https://json-schema.org/understanding-json-schema/structuring.html#base-uri
    def loader(uri):
        # IS-07 is currently the only spec that uses $id in its schemas
        is07_base_uri = "https://www.amwa.tv/event_and_tally/"
        if uri.startswith(is07_base_uri):
            # rather than recreate the cache path from config, cheat by just using the original base URI
            uri = base_uri_path + uri[len(is07_base_uri):]

        return jsonref.jsonloader(uri)

    if file_name:
        json_file = str(Path(base_path) / file_name)
        with open(json_file, "r") as f:
            schema = jsonref.load(f, base_uri=base_uri_path, jsonschema=True, lazy_load=False,
                                  loader=loader)
    elif schema_obj:
        schema = jsonref.replace_refs(schema_obj, base_uri=base_uri_path, jsonschema=True, lazy_load=False,
                                      loader=loader)

    return schema


def generate_token(scopes=None, write=False, azp=False, add_claims=True, overrides=None, private_key=None):
    if scopes is None:
        scopes = []
    header = {"typ": "JWT", "alg": "RS512"}
    payload = {"iss": "{}".format(CONFIG.AUTH_TOKEN_ISSUER),
               "sub": "testsuite@nmos.tv",
               "aud": ["https://*.{}".format(CONFIG.DNS_DOMAIN), "https://*.local"],
               "exp": int(time.time() + 3600),
               "iat": int(time.time()),
               "scope": " ".join(scopes)}
    if azp:
        payload["azp"] = str(uuid.uuid4())
    else:
        payload["client_id"] = str(uuid.uuid4())
    nmos_claims = {}
    if add_claims:
        for api in scopes:
            nmos_claims["x-nmos-{}".format(api)] = {"read": ["*"]}
            if write:
                nmos_claims["x-nmos-{}".format(api)]["write"] = ["*"]
    payload.update(nmos_claims)
    if overrides:
        payload.update(overrides)
    if private_key is None:
        key = open(CONFIG.AUTH_TOKEN_PRIVKEY).read()
    else:
        key = private_key
    token = jwt.encode(header, payload, key).decode()
    return token


class WebsocketWorker(threading.Thread):
    """Websocket Client Worker Thread"""

    def __init__(self, ws_href):
        """
        Initializer
        :param ws_href: websocket url (string)
        """
        if CONFIG.ENABLE_AUTH and CONFIG.AUTH_TOKEN and "access_token" not in ws_href:
            if "?" in ws_href:
                ws_href += "&access_token={}".format(CONFIG.AUTH_TOKEN)
            else:
                ws_href += "?access_token={}".format(CONFIG.AUTH_TOKEN)
        threading.Thread.__init__(self, daemon=True)
        self.ws_href = ws_href
        try:
            self.ws = websocket.WebSocketApp(ws_href,
                                             on_message=self.on_message,
                                             on_close=self.on_close,
                                             on_open=self.on_open,
                                             on_error=self.on_error)
        except AttributeError:
            print(" * ERROR: You have the wrong Python websocket module installed. "
                  "Please uninstall 'websocket' and install 'websocket-client'")
            raise
        self.messages = list()
        self.error_occurred = False
        self.connected = False
        self.error_message = ""

    def run(self):
        url = urlparse(self.ws.url)
        # strip the trailing dot of the hostname to prevent SSL certificate hostname mismatch
        hostname = url.hostname.rstrip('.')
        # sslopt needs to be Falsey when not doing Secure WebSocket
        sslopt = {"ca_certs": CONFIG.CERT_TRUST_ROOT_CA, "server_hostname": hostname} if url.scheme == "wss" else {}
        self.ws.run_forever(sslopt=sslopt)

    def on_open(self, ws):
        self.connected = True

    def on_message(self, ws, message):
        self.messages.append(message)

    def on_close(self, ws, close_status, close_message):
        self.connected = False

    def on_error(self, ws, error):
        self.error_occurred = True
        self.error_message = error
        self.connected = False

    def close(self):
        self.ws.close()

    def send(self, message):
        if self.connected is True:
            self.ws.send(message)

    def is_open(self):
        return self.connected

    def get_messages(self):
        msg_cpy = copy(self.messages)
        self.clear_messages()  # Reset message list after reading
        return msg_cpy

    def did_error_occur(self):
        return self.error_occurred

    def get_error_message(self):
        return self.error_message

    def clear_messages(self):
        self.messages.clear()


class MQTTClientWorker:
    """MQTT Client Worker"""
    def __init__(self, host, port, secure=False, username=None, password=None, topics=[]):
        """
        Initializer
        :param host: broker hostname (string)
        :param port: broker port (int)
        :param secure: use TLS (bool)
        :param username: broker username (string)
        :param password: broker password (string)
        :param topics: list of topics to subscribe to (list of string)
        """
        self.host = host
        self.port = port
        self.error_occurred = False
        self.connected = False
        self.error_message = ""
        # MQTT 5 is required so that we can set retainAsPublished
        # when subscribing to test whether messages have retain flags set
        self.client = mqtt.Client(protocol=mqtt.MQTTv5)
        self.client.on_connect = lambda client, userdata, flags, rc, properties=None: self.on_connect(flags, rc)
        self.client.on_disconnect = lambda client, userdata, rc: self.on_disconnect(rc)
        self.client.on_message = lambda client, userdata, msg: self.on_message(msg)
        self.client.on_subscribe = lambda client, userdata, mid, *args: self.on_subscribe(mid)
        self.client.on_log = lambda client, userdata, level, buf: self.on_log(level, buf)
        if secure:
            self.client.tls_set(CONFIG.CERT_TRUST_ROOT_CA)
        if username or password:
            self.client.username_pw_set(username, password)
        self.topics = topics
        self.pending_subs = set()
        self.messages = []

    def start(self):
        self.client.connect_async(self.host, self.port)
        self.client.loop_start()

    def close(self):
        self.client.loop_stop()

    def on_connect(self, flags, rc):
        if len(self.topics) == 0:
            self.connected = True
        else:
            for topic in self.topics:
                result, message_id = self.client.subscribe(topic, options=mqtt.SubscribeOptions(retainAsPublished=True))
                if result != mqtt.MQTT_ERR_SUCCESS:
                    raise Exception("failed to subscribe to MQTT topic {}: {}".format(topic, result))
                self.pending_subs.add(message_id)

    def on_subscribe(self, message_id):
        if message_id in self.pending_subs:
            self.pending_subs.remove(message_id)
            if len(self.pending_subs) == 0:
                self.connected = True
        else:
            print("Unexpected suback message ID: {}".format(message_id))

    def is_open(self):
        return self.connected

    def get_error_message(self):
        return self.error_message

    def did_error_occur(self):
        return self.error_occurred

    def get_latest_message(self, topic):
        for message in reversed(self.messages):
            if message.topic == topic:
                return message
        return None

    def on_disconnect(self, rc):
        self.connected = False
        if rc != mqtt.MQTT_ERROR_SUCCESS:
            self.error_occurred = True
            self.error_message = "disconnected with rc {}".format(rc)

    def on_message(self, message):
        self.messages.append(message)

    def on_log(self, level, buf):
        if level == mqtt.MQTT_LOG_ERR:
            self.error_occurred = True
            self.error_message = buf
        print("MQTT log: {}: {}".format(level, buf))


class SubscriptionWebsocketWorker(threading.Thread):
    """Subscription Server Worker Thread"""

    async def consumer_handler(self, websocket, path):
        async for message in websocket:
            # ignore incoming websocket messages
            pass

    async def producer_handler(self, websocket, path):
        # handle multiple client connections per socket
        self._connected_clients.add(websocket)

        # when websocket client first connects we immediately queue a 'sync' data grain message to be sent
        self._loop.call_soon_threadsafe(self.queue_sync_data_grain_callback, self._resource_type)

        # will automatically exit loop when websocket client disconnects or server closed
        while True:
            message = await self._message_queue.get()
            # broadcast to all connected clients
            await asyncio.wait([ws.send(message) for ws in self._connected_clients])

    async def handler(self, websocket, path):
        consumer_task = asyncio.ensure_future(self.consumer_handler(websocket, path))
        producer_task = asyncio.ensure_future(self.producer_handler(websocket, path))

        done, pending = await asyncio.wait([consumer_task, producer_task], return_when=asyncio.FIRST_COMPLETED)

        for task in pending:
            task.cancel()

    def __init__(self, host, port, resource_type, secure):
        """
        Initializer
        :param resource_type: type of resource to which we are subscribing
        :param host: host ip for websocket server (string)
        :param port: port for websocket server (int)
        """
        threading.Thread.__init__(self, daemon=True)

        self._resource_type = resource_type

        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        self._message_queue = asyncio.Queue()
        self._connected_clients = set()

        ctx = None
        if secure:
            ctx = ssl.create_default_context()
            for cert, key in zip(CONFIG.CERTS_MOCKS, CONFIG.KEYS_MOCKS):
                ctx.load_cert_chain(cert, key)
            # additionally disable TLS v1.0 and v1.1
            ctx.options &= ssl.OP_NO_TLSv1 | ssl.OP_NO_TLSv1_1
            # BCP-003-01 however doesn't require client certificates, so disable those
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

        self._ws_server = self._loop.run_until_complete(websockets.serve(self.handler, host, port, ssl=ctx))

    def run(self):
        self._loop.run_forever()

    def queue_message(self, message):
        self._loop.call_soon_threadsafe(self._message_queue.put_nowait, message)

    def close(self):
        print('Closing websocket for ' + self._resource_type)
        self._ws_server.close()

    def set_queue_sync_data_grain_callback(self, callback):
        """callback to queue sync data grain message with 1 parameter: resource_type (string) """
        self.queue_sync_data_grain_callback = callback
