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

from . import Config as CONFIG


def ordered(obj):
    if isinstance(obj, dict):
        return sorted((k, ordered(v)) for k, v in obj.items())
    if isinstance(obj, list):
        return sorted(ordered(x) for x in obj)
    else:
        return obj


def compare_json(json1, json2):
    """Compares two json objects for equality"""
    return ordered(json1) == ordered(json2)


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
