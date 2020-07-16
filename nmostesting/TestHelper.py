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

import threading
import requests
import websocket
import os
import jsonref
import netifaces
from copy import copy
from pathlib import Path
from enum import IntEnum
from numbers import Number
from functools import cmp_to_key
from collections.abc import KeysView

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


def do_request(method, url, **kwargs):
    """Perform a basic HTTP request with appropriate error handling"""
    try:
        s = requests.Session()
        req = requests.Request(method, url, **kwargs)
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

    loader = jsonref.JsonLoader(cache_results=False)

    if file_name:
        json_file = str(Path(base_path) / file_name)
        with open(json_file, "r") as f:
            schema = jsonref.load(f, base_uri=base_uri_path, loader=loader, jsonschema=True)
    elif schema_obj:
        # Work around an exception when there's nothing to resolve using an object
        if "$ref" in schema_obj:
            schema = jsonref.JsonRef.replace_refs(schema_obj, base_uri=base_uri_path, loader=loader, jsonschema=True)
        else:
            schema = schema_obj

    return schema


class WebsocketWorker(threading.Thread):
    """Websocket Client Worker Thread"""

    def __init__(self, ws_href):
        """
        Initializer
        :param ws_href: websocket url (string)
        """
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
        self.error_occured = False
        self.connected = False
        self.error_message = ""

    def run(self):
        self.ws.run_forever(sslopt={"ca_certs": CONFIG.CERT_TRUST_ROOT_CA})

    def on_open(self):
        self.connected = True

    def on_message(self, message):
        self.messages.append(message)

    def on_close(self):
        self.connected = False

    def on_error(self, error):
        self.error_occured = True
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
        return self.error_occured

    def get_error_message(self):
        return self.error_message

    def clear_messages(self):
        self.messages.clear()
