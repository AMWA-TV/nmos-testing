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

import os
import time
import uuid
import json
import ipaddress
import re

import jsonschema
from flask import Blueprint, make_response, abort, Response, request
from random import randint
from copy import deepcopy
from jinja2 import Template
from .. import Config as CONFIG
from ..TestHelper import get_default_ip, do_request, load_resolved_schema
from ..IS04Utils import IS04Utils
from ..IS10Utils import IS10Utils
from .Auth import PRIMARY_AUTH

MXL_TRANSPORT = "urn:x-nmos:transport:mxl"
MXL_TRANSPORT_PARAM_KEYS = ("mxl_domain_id", "mxl_flow_id")
IS05_SPEC_PATH = os.path.join(CONFIG.CACHE_PATH, "is-05")
IS13_SPEC_PATH = os.path.join(CONFIG.CACHE_PATH, "is-13")
BCP00703_SPEC_PATH = os.path.join(CONFIG.CACHE_PATH, "bcp-007-03")
READ_ONLY_TAG_PREFIXES = (
    "urn:x-nmos:tag:grouphint/",
    "urn:x-nmos:tag:asset:",
)
ANNOTATION_SUBRESOURCE_TYPES = ("device", "flow", "receiver", "sender", "source")


def _resource_transport(resource, resource_id):
    if resource == 'senders':
        return NODE.senders[resource_id]['sender'].get('transport', 'urn:x-nmos:transport:rtp')
    return NODE.receivers[resource_id]['receiver'].get('transport', 'urn:x-nmos:transport:rtp')


def _validate_against_schema(payload, schema):
    """Validate payload against schema. Returns an error message, or None if valid."""
    try:
        checker = jsonschema.FormatChecker(["ipv4", "ipv6", "uri"])
        jsonschema.validate(payload, schema, format_checker=checker)
    except jsonschema.ValidationError as validation_error:
        error_path = ".".join(str(path_element) for path_element in validation_error.absolute_path)
        if error_path:
            return "{} at '{}'".format(validation_error.message, error_path)
        return validation_error.message
    return None


def _get_transport_params_schema_file(resource_kind, transport, version):
    """
    Return (spec_path, file_name) for the transport_params array item schema.
    Raises ValueError if the transport is not supported for the API version.
    """
    if transport.startswith("urn:x-nmos:transport:rtp"):
        transport_suffix = "rtp"
        spec_path = IS05_SPEC_PATH
    elif transport == "urn:x-nmos:transport:mqtt":
        if IS04Utils.compare_api_version(version, "v1.1") < 0:
            raise ValueError("MQTT transport requires IS-05 v1.1 or later")
        transport_suffix = "mqtt"
        spec_path = IS05_SPEC_PATH
    elif transport == "urn:x-nmos:transport:websocket":
        if IS04Utils.compare_api_version(version, "v1.1") < 0:
            raise ValueError("WebSocket transport requires IS-05 v1.1 or later")
        transport_suffix = "websocket"
        spec_path = IS05_SPEC_PATH
    elif transport == MXL_TRANSPORT:
        if IS04Utils.compare_api_version(version, "v1.2") < 0:
            raise ValueError("MXL transport requires IS-05 v1.2 or later")
        return BCP00703_SPEC_PATH, "{}_transport_params_mxl.json".format(resource_kind)
    else:
        raise ValueError("Unsupported transport type '{}'".format(transport))

    if IS04Utils.compare_api_version(version, "v1.0") == 0:
        file_name = "v1.0_{}_transport_params_{}.json".format(resource_kind, transport_suffix)
    else:
        file_name = "{}_transport_params_{}.json".format(resource_kind, transport_suffix)
    return spec_path, file_name


def _validate_staged_patch_schema(resource, resource_id, request_json, version):
    """
    Validate a /staged PATCH body against the IS-05 request schema (and transport
    schemas where applicable) for the given Connection API version.
    Returns (schema_valid, schema_error). Does not reject the request; callers
    record the result so controller tests can report it.
    """
    if request_json is None:
        return False, "Request body is missing or not valid JSON"

    resource_kind = "sender" if resource == "senders" else "receiver"
    if IS04Utils.compare_api_version(version, "v1.0") == 0:
        stage_schema_file = "v1.0-{}-stage-schema.json".format(resource_kind)
    else:
        stage_schema_file = "{}-stage-schema.json".format(resource_kind)
    try:
        stage_schema = load_resolved_schema(IS05_SPEC_PATH, stage_schema_file)
    except (OSError, IOError, FileNotFoundError) as exception:
        return False, "Unable to load IS-05 {} stage schema '{}': {}".format(
            version, stage_schema_file, exception)

    # Validate activation / master_enable / ids the same way for every transport.
    # transport_params are checked separately against the transport-specific schema.
    stage_body = {
        key: value for key, value in request_json.items() if key != "transport_params"
    }
    stage_only_schema = {
        "$schema": "http://json-schema.org/draft-04/schema#",
        "type": "object",
        "additionalProperties": False,
        "properties": {
            key: value for key, value in stage_schema.get("properties", {}).items()
            if key != "transport_params"
        }
    }
    schema_error = _validate_against_schema(stage_body, stage_only_schema)
    if schema_error:
        return False, schema_error

    if "transport_params" not in request_json:
        return True, None

    try:
        spec_path, transport_schema_file = _get_transport_params_schema_file(
            resource_kind, _resource_transport(resource, resource_id), version)
    except ValueError as exception:
        return False, str(exception)

    try:
        transport_leg_schema = load_resolved_schema(spec_path, transport_schema_file)
    except (OSError, IOError, FileNotFoundError) as exception:
        return False, "Unable to load {} transport params schema '{}': {}".format(
            version, transport_schema_file, exception)

    transport_params_schema = {
        "$schema": "http://json-schema.org/draft-04/schema#",
        "type": "array",
        "items": transport_leg_schema
    }
    schema_error = _validate_against_schema(
        request_json["transport_params"], transport_params_schema)
    if schema_error:
        return False, schema_error

    return True, None


def _is_read_only_annotation_tag(name):
    return any(name.startswith(prefix) for prefix in READ_ONLY_TAG_PREFIXES)


def _mxl_activation_block():
    return {
        "activation_time": None,
        "mode": None,
        "requested_time": None
    }


def _initial_mxl_transport_params():
    return [{
        "mxl_domain_id": None,
        "mxl_flow_id": None
    }]


class Node(object):
    def __init__(self, port_increment):
        self.port = CONFIG.PORT_BASE + 200 + port_increment
        self.id = str(uuid.uuid4())
        self.registry_url = ''
        self.registry_version = ''
        self.reset()

    def reset(self):
        self.staged_requests = []
        self.receivers = {}
        self.senders = {}
        self.patched_sdp = {}
        self.auth_cache = {}
        self.annotation_resources = {}
        self.annotation_requests = []

    def get_sender(self, media_type="video/raw", version="v1.3"):
        protocol = "http"
        host = get_default_ip()
        if CONFIG.ENABLE_HTTPS:
            protocol = "https"
            if CONFIG.DNS_SD_MODE == "multicast":
                host = "nmos-mocks.local"
            else:
                host = "mocks.{}".format(CONFIG.DNS_DOMAIN)

        sender = {
            "id": str(uuid.uuid4()),
            "label": "Dummy Sender",
            "description": "Dummy Sender",
            "version": "50:50",
            "caps": {},
            "tags": {},
            "manifest_href": "{}://{}:{}/{}.sdp".format(protocol, host, self.port, media_type),
            "flow_id": str(uuid.uuid4()),
            "transport": "urn:x-nmos:transport:rtp.mcast",
            "device_id": str(uuid.uuid4()),
            "interface_bindings": ["eth0"],
            "subscription": {
                "receiver_id": None,
                "active": True
            }
        }

        return IS04Utils.downgrade_resource("sender", sender, version)

    def add_sender(self, sender, sender_ip_address, sdp_params={}):
        """
        Takes self.senders from mock registry and adds connection details
        """

        transport_params = [{
            "destination_ip": sender_ip_address,
            "destination_port": 5004,
            "rtp_enabled": True,
            "source_ip": get_default_ip(),
            "source_port": 5004
        }]

        sender_update = {
            'transport_file': sender['manifest_href'],
            'transport_params': transport_params,
            'staged': {
                "activation": {
                    "activation_time": None,
                    "mode": None,
                    "requested_time": None
                },
                "master_enable": True,
                "receiver_id": None,
                'transport_params': transport_params
            },
            'active': {
                "activation": {
                    "activation_time": None,
                    "mode": None,
                    "requested_time": None
                },
                "master_enable": True,
                "receiver_id": None,
                'transport_params': transport_params
            }
        }

        self.senders[sender['id']] = {
            'sender': sender,
            'activations': sender_update,
            'sdp_params': sdp_params
        }

    def delete_sender(self, sender_id):
        self.senders.pop(sender_id)

    def add_receiver(self, receiver):

        staged_transport_params = [{
            "destination_port": "auto",
            "interface_ip": get_default_ip(),
            "multicast_ip": None,
            "rtp_enabled": True,
            "source_ip": None
        }]

        active_transport_params = [{
            "destination_port": 5004,
            "interface_ip": get_default_ip(),
            "multicast_ip": None,
            "rtp_enabled": True,
            "source_ip": None
        }]

        activations = {
            'staged': {
                "activation": {
                    "activation_time": None,
                    "mode": None,
                    "requested_time": None
                },
                "master_enable": False,
                "sender_id": None,
                "transport_file": {
                    "data": None,
                    "type": None
                },
                'transport_params': staged_transport_params
            },
            'active': {
                "activation": {
                    "activation_time": None,
                    "mode": None,
                    "requested_time": None
                },
                "master_enable": False,
                "sender_id": None,
                "transport_file": {
                    "data": None,
                    "type": None
                },
                'transport_params': active_transport_params
            }
        }

        self.receivers[receiver['id']] = {
            'activations': activations,
            'receiver': receiver
        }

    def add_mxl_sender(self, sender, mxl_domain_id):
        """
        Adds IS-05 Connection API state for an MXL Sender registered in the mock Registry.
        """
        transport_params = [{
            "mxl_domain_id": mxl_domain_id,
            "mxl_flow_id": sender['flow_id']
        }]
        connection_state = {
            'transport_params': deepcopy(transport_params),
            'staged': {
                "activation": _mxl_activation_block(),
                "master_enable": True,
                "receiver_id": None,
                'transport_params': deepcopy(transport_params)
            },
            'active': {
                "activation": _mxl_activation_block(),
                "master_enable": True,
                "receiver_id": None,
                'transport_params': deepcopy(transport_params)
            }
        }

        self.senders[sender['id']] = {
            'sender': sender,
            'activations': connection_state,
            'mxl_domain_id': mxl_domain_id
        }

    def add_mxl_receiver(self, receiver, mxl_domain_id):
        """
        Adds IS-05 Connection API state for an MXL Receiver registered in the mock Registry.
        """
        transport_params = _initial_mxl_transport_params()
        activations = {
            'transport_params': deepcopy(transport_params),
            'staged': {
                "activation": _mxl_activation_block(),
                "master_enable": False,
                "sender_id": None,
                'transport_params': deepcopy(transport_params)
            },
            'active': {
                "activation": _mxl_activation_block(),
                "master_enable": False,
                "sender_id": None,
                'transport_params': deepcopy(transport_params)
            }
        }

        self.receivers[receiver['id']] = {
            'activations': activations,
            'receiver': receiver,
            'mxl_domain_id': mxl_domain_id
        }

    def _resolve_mxl_flow_id(self, resource, resource_data, response_data):
        transport_params = response_data['transport_params'][0]
        flow_id = transport_params.get('mxl_flow_id')

        if flow_id != 'auto':
            return flow_id

        if resource == 'senders':
            return resource_data['sender']['flow_id']

        sender_id = response_data.get('sender_id')
        if sender_id and sender_id in self.senders:
            return self.senders[sender_id]['sender']['flow_id']

        return resource_data.get('mxl_flow_id')

    def _resolve_mxl_transport_params(self, resource, resource_data, response_data):
        transport_params = response_data['transport_params'][0]
        resolved_params = {}

        for param_name in MXL_TRANSPORT_PARAM_KEYS:
            param_value = transport_params.get(param_name)

            if resource == 'senders' and param_value in (None, 'auto'):
                if param_name == 'mxl_domain_id':
                    resolved_params[param_name] = resource_data['mxl_domain_id']
                else:
                    resolved_params[param_name] = resource_data['sender']['flow_id']
            elif param_value == 'auto':
                if param_name == 'mxl_domain_id':
                    resolved_params[param_name] = resource_data['mxl_domain_id']
                else:
                    resolved_params[param_name] = self._resolve_mxl_flow_id(resource, resource_data, response_data)
            else:
                resolved_params[param_name] = param_value

        return resolved_params

    def _patch_staged_mxl(self, resource, resource_id, request_json):
        resource_data = self.senders[resource_id] if resource == 'senders' else self.receivers[resource_id]
        activations = resource_data['activations']
        response_data = deepcopy(activations['staged'])
        response_code = 200

        if resource == 'senders':
            resource_type = 'sender'
            connected_resource_id = 'receiver_id'
        else:
            resource_type = 'receiver'
            connected_resource_id = 'sender_id'

        if 'transport_params' in request_json:
            for key, value in request_json['transport_params'][0].items():
                response_data['transport_params'][0][key] = value

        for item in (connected_resource_id, 'activation', 'master_enable'):
            if item in request_json:
                response_data[item] = request_json[item]

        if resource == 'receivers' and response_data['transport_params'][0].get('mxl_flow_id') == 'auto':
            return {'code': 400, 'debug': None,
                    'error': 'Transport param mxl_flow_id does not satisfy constraints.'}, 400

        if request_json.get('activation'):
            response_data['transport_params'][0].update(
                self._resolve_mxl_transport_params(resource, resource_data, response_data))

            response_data['activation']['activation_time'] = IS04Utils.get_TAI_time()

            if response_data['activation']['mode'] == 'activate_immediate':
                response_data['activation']['requested_time'] = None
            else:
                response_code = 202

            subscription_update = resource_data[resource_type]
            subscription_update['subscription']['active'] = response_data['master_enable']
            subscription_update['version'] = IS04Utils.get_TAI_time()

            if subscription_update['subscription']['active'] is True:
                subscription_update['subscription'][connected_resource_id] = response_data[connected_resource_id]
            else:
                subscription_update['subscription'][connected_resource_id] = None

            do_request('POST', self.registry_url + 'x-nmos/registration/' + self.registry_version +
                       '/resource', json={'type': resource_type, 'data': subscription_update})

            activations['active'] = response_data
            activations['transport_params'] = response_data['transport_params']

        staged_data = deepcopy(response_data)
        staged_data['activation'] = _mxl_activation_block()
        activations['staged'] = staged_data

        return response_data, response_code

    def clear_staged_requests(self):
        self.staged_requests = []

    def parse_sdp(self, sdp_data):

        sdp_params = []

        sdp_sections = sdp_data.split("m=")
        sdp_global = sdp_sections[0]
        sdp_media_sections = sdp_sections[1:]
        sdp_groups_line = re.search(r"a=group:DUP (.+)", sdp_global)

        media_lines = []
        if sdp_groups_line:
            sdp_group_names = sdp_groups_line.group(1).split()
            for sdp_media in sdp_media_sections:
                group_name = re.search(r"a=mid:(\S+)", sdp_media)
                if group_name.group(1) in sdp_group_names:
                    media_lines.append("m=" + sdp_media)
        elif len(sdp_media_sections) > 0:
            media_lines.append("m=" + sdp_media_sections[0])

        for index, sdp_data in enumerate(media_lines):
            sdp_param_leg = {}

            media_line = re.search(r"m=([a-z]+) ([0-9]+) RTP/AVP ([0-9]+)", sdp_data)
            sdp_param_leg['destination_port'] = int(media_line.group(2))

            connection_line = re.search(r"c=IN IP[4,6] ([^/\r\n]*)(?:/[0-9]+){0,2}", sdp_data)
            destination_ip = connection_line.group(1)
            if ipaddress.IPv4Address(destination_ip).is_multicast:
                sdp_param_leg['multicast_ip'] = destination_ip
                sdp_param_leg['interface_ip'] = "auto"
            else:
                sdp_param_leg['multicast_ip'] = None
                sdp_param_leg['interface_ip'] = destination_ip

            filter_line = re.search(r"a=source-filter: incl IN IP[4,6] (\S*) (\S*)", sdp_data)
            if filter_line and filter_line.group(2):
                sdp_param_leg['source_ip'] = filter_line.group(2)
            else:
                sdp_param_leg['source_ip'] = None

            format_line = re.search(r"a=fmtp:(\S*\s*)(.*)", sdp_data)

            if format_line and format_line.group(2):
                #  Handle parameter keys that have no value, e.g. 'interlace', and set their value to True
                sdp_param_leg['format'] = {key_value.split('=')[0]:
                                           key_value.split('=', maxsplit=1)[1] if '=' in key_value else True
                                           for key_value in re.split(r'[ \t]*;[ \t]*', format_line.group(2))}

                # Cast the string to an integer value for these parameters
                # ('packetmode' and 'transmode' are JPEG XS parameters)
                int_params = ['width', 'height', 'depth', 'packetmode', 'transmode']
                for param in int_params:
                    if param in sdp_param_leg['format']:
                        sdp_param_leg['format'][param] = int(sdp_param_leg['format'][param])

            sdp_params.append(sdp_param_leg)

        return sdp_params

    def patch_staged(self, resource, resource_id, request_json):
        """
        Updates data for given resource to either stage a connection, activate a staged connection,
        activate a connection without staging or deactivate an active connection
        resource: 'senders' or 'receivers'
        resource_id: nmos id for resource
        request_json: JSON from the PATCH request
        Returns data and status code to send in response to PATCH request
        Updates mock Registry subscription in cases of activation/deactivation
        """
        # Get current staged and active details for resource
        if _resource_transport(resource, resource_id) == MXL_TRANSPORT:
            return self._patch_staged_mxl(resource, resource_id, request_json)

        resource_data = self.senders[resource_id] if resource == 'senders' else self.receivers[resource_id]
        activations = resource_data['activations']
        response_data = deepcopy(activations['staged'])
        response_code = 200

        # NOTE that this Receiver only has a single leg (no ST 2022-7 redundancy)

        # Copy SDP parameters into transport_params in response
        if 'transport_file' in request_json:
            transport_file = request_json['transport_file']
            if transport_file['type'] == 'application/sdp':
                sdp_params = self.parse_sdp(transport_file['data'])

                # Store patched SDP params for later validation in tests
                self.patched_sdp[resource_id] = sdp_params

                sdp_transport_param_keys = ['destination_port',
                                            'multicast_ip',
                                            'interface_ip',
                                            'source_ip']

                sdp_transport_params = {key: value for key, value in sdp_params[0].items()
                                        if key in sdp_transport_param_keys}

                response_data['transport_params'][0] = {**response_data['transport_params'][0],
                                                        **sdp_transport_params,
                                                        'rtp_enabled': True}

        # Overwrite with supplied parameters in transport_params
        if 'transport_params' in request_json:
            transport_params = request_json['transport_params'][0]

            for key, value in transport_params.items():
                response_data['transport_params'][0][key] = transport_params[key]

        # Check response transport params against constraints
        constraints = _get_constraints(resource, resource_id)

        for key, value in constraints.items():
            if key in response_data['transport_params'][0]:
                if value:
                    # There is a constraint for this param and a value in the request to check
                    check = _check_constraint(value, response_data['transport_params'][0][key])
                    if not check:
                        response_data = {'code': 400, 'debug': None,
                                         'error': 'Transport param {} does not satisfy constraints.'.format(key)}
                        response_code = 400
                        return response_data, response_code

        # Get resource specific data
        if resource == 'senders':
            resource_type = 'sender'
            connected_resource_id = 'receiver_id'
            # Set up default transport parameters to fill in autos
            default_params = {'destination_port': 5004, 'source_ip': get_default_ip(), 'source_port': 5004,
                              'destination_ip': activations['transport_params'][0]['destination_ip']}

        elif resource == 'receivers':
            resource_type = 'receiver'
            connected_resource_id = 'sender_id'
            # Set up default transport parameters to fill in auto or missing values
            default_params = {'destination_port': 5004, 'interface_ip': get_default_ip()}

            if 'transport_file' in request_json:
                response_data['transport_file'] = request_json['transport_file']

        # Get other request data
        request_list = [connected_resource_id, 'activation', 'master_enable']
        for item in request_list:
            if item in request_json:
                response_data[item] = request_json[item]

        if not request_json.get('activation'):
            # Just staging so return data
            pass
        else:
            # Activating
            # Check for auto in params and update from defaults
            for key, value in response_data['transport_params'][0].items():
                if value == 'auto':
                    response_data['transport_params'][0][key] = default_params[key]

            # Add activation time
            response_data['activation']['activation_time'] = IS04Utils.get_TAI_time()

            if response_data['activation']['mode'] == 'activate_immediate':
                response_data['activation']['requested_time'] = None
            else:
                # Note: Currently all mock activations are immediate regardless of requested mode
                response_code = 202

            # Create update for IS-04 subscription
            subscription_update = resource_data[resource_type]
            subscription_update['subscription']['active'] = response_data['master_enable']
            subscription_update['version'] = IS04Utils.get_TAI_time()

            if subscription_update['subscription']['active'] is True:
                subscription_update['subscription'][connected_resource_id] = response_data[connected_resource_id]
            else:
                subscription_update['subscription'][connected_resource_id] = None

            # POST updated subscription to registry
            valid, response = do_request('POST', self.registry_url + 'x-nmos/registration/' + self.registry_version +
                                         '/resource', json={'type': resource_type, 'data': subscription_update})

            # Update active data with new data
            activations['active'] = response_data
            activations['transport_params'] = response_data['transport_params']

        # Update staged data with new data
        staged_data = deepcopy(response_data)
        staged_data['activation'] = {"activation_time": None, "mode": None, "requested_time": None}
        activations['staged'] = staged_data

        return response_data, response_code

    def add_annotation(self, reg_type, resource):
        """Remember a registered IS-04 resource so the Annotation API can serve and update it."""
        stored = deepcopy(resource)
        self.annotation_resources[stored["id"]] = {
            "reg_type": reg_type,
            "resource": stored,
            "initial": {
                "label": stored.get("label") or "",
                "description": stored.get("description") or "",
                "tags": deepcopy(stored.get("tags") or {}),
            },
        }

    def clear_annotation_requests(self):
        self.annotation_requests = []

    def annotation_core(self, resource):
        return {
            "id": resource["id"],
            "version": resource["version"],
            "label": resource.get("label", ""),
            "description": resource.get("description", ""),
            "tags": resource.get("tags") or {},
        }

    def annotation_ids(self, reg_type):
        return sorted(
            entry["resource"]["id"] + "/"
            for entry in self.annotation_resources.values()
            if entry["reg_type"] == reg_type
        )

    def annotation_id_for_type(self, reg_type):
        for entry in self.annotation_resources.values():
            if entry["reg_type"] == reg_type:
                return entry["resource"]["id"]
        return None

    def _bump_annotation_version(self, resource):
        previous = resource.get("version")
        resource["version"] = IS04Utils.get_TAI_time()
        if resource["version"] == previous:
            time.sleep(0.01)
            resource["version"] = IS04Utils.get_TAI_time()

    def _register_annotation(self, entry):
        if not self.registry_url or not self.registry_version:
            return
        do_request(
            "POST",
            self.registry_url + "x-nmos/registration/" + self.registry_version + "/resource",
            json={"type": entry["reg_type"], "data": entry["resource"]},
        )

    def restore_annotation(self, resource_id):
        """Put a resource's label, description and tags back to the values it was registered with."""
        entry = self.annotation_resources.get(resource_id)
        if entry is None:
            return
        resource = entry["resource"]
        initial = entry["initial"]
        if (resource.get("label") == initial["label"]
                and resource.get("description") == initial["description"]
                and (resource.get("tags") or {}) == initial["tags"]):
            return
        resource["label"] = initial["label"]
        resource["description"] = initial["description"]
        resource["tags"] = deepcopy(initial["tags"])
        self._bump_annotation_version(resource)
        self._register_annotation(entry)

    def patch_annotation(self, resource_id, patch):
        """
        Apply an Annotation API PATCH.
        Returns (response JSON, HTTP status). Does not record the request.
        """
        entry = self.annotation_resources[resource_id]
        resource = entry["resource"]
        initial = entry["initial"]

        # A tags object that names a read-only tag is rejected as a whole.
        # tags set to null does not name those tags, and leaves them in place.
        if isinstance(patch.get("tags"), dict):
            for name in patch["tags"]:
                if _is_read_only_annotation_tag(name):
                    return {
                        "code": 500,
                        "error": "cannot patch read-only tag: {}".format(name),
                        "debug": None,
                    }, 500

        current_tags = resource.get("tags") or {}
        readonly_tags = {
            name: deepcopy(value)
            for name, value in current_tags.items()
            if _is_read_only_annotation_tag(name)
        }

        for key in ("label", "description", "tags"):
            if key not in patch:
                continue
            value = patch[key]
            if value is None:
                resource.pop(key, None)
            elif key == "tags":
                tags = resource.setdefault("tags", {})
                for name, tag_value in value.items():
                    if tag_value is None:
                        tags.pop(name, None)
                    else:
                        tags[name] = deepcopy(tag_value)
            else:
                resource[key] = value

        if not isinstance(resource.get("label"), str):
            resource["label"] = initial["label"]
        if not isinstance(resource.get("description"), str):
            resource["description"] = initial["description"]
        if not isinstance(resource.get("tags"), dict):
            resource["tags"] = {}
        for name, value in readonly_tags.items():
            resource["tags"].setdefault(name, value)
        for name, value in initial["tags"].items():
            if name not in resource["tags"]:
                resource["tags"][name] = deepcopy(value)

        self._bump_annotation_version(resource)
        self._register_annotation(entry)
        return self.annotation_core(resource), 200

    def check_authorization(self, auth, path, scope, write=False):
        if not CONFIG.ENABLE_AUTH:
            return True, ""

        if "Authorization" in request.headers and request.headers["Authorization"].startswith("Bearer ") \
                and scope in self.auth_cache and \
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


NODE = Node(1)
NODE_API = Blueprint('node_api', __name__)


# Authorization decorator
def check_authorization(func):
    def wrapper(*args, **kwargs):
        write = (request.method == 'PATCH')
        authorized, error_message = NODE.check_authorization(PRIMARY_AUTH,
                                                             request.path,
                                                             scope="x-nmos-connection",
                                                             write=write)
        if authorized is not True:
            abort(authorized, description=error_message)

        return func(*args, **kwargs)
    # Rename wrapper to allow decoration of decorator
    wrapper.__name__ = func.__name__
    return wrapper


def check_annotation_authorization(func):
    def wrapper(*args, **kwargs):
        write = (request.method == "PATCH")
        authorized, error_message = NODE.check_authorization(PRIMARY_AUTH,
                                                             request.path,
                                                             scope="x-nmos-annotation",
                                                             write=write)
        if authorized is not True:
            abort(authorized, description=error_message)

        return func(*args, **kwargs)
    wrapper.__name__ = func.__name__
    return wrapper


def _annotation_json(data, status=200):
    return make_response(Response(json.dumps(data), status=status, mimetype="application/json"))


@NODE_API.route('/x-nmos', methods=['GET'], strict_slashes=False)
def x_nmos_root():
    base_data = ['connection/']
    if NODE.annotation_resources:
        base_data.append('annotation/')

    return make_response(Response(json.dumps(base_data), mimetype='application/json'))


@NODE_API.route('/x-nmos/connection', methods=['GET'], strict_slashes=False)
@check_authorization
def connection_root():
    base_data = [version + '/' for version in CONFIG.SPECIFICATIONS["is-05"]["versions"]]

    return make_response(Response(json.dumps(base_data), mimetype='application/json'))


@NODE_API.route('/x-nmos/connection/<version>', methods=['GET'], strict_slashes=False)
@check_authorization
def version(version):
    base_data = ['bulk/', 'single/']

    return make_response(Response(json.dumps(base_data), mimetype='application/json'))


@NODE_API.route('/x-nmos/connection/<version>/single', methods=['GET'], strict_slashes=False)
@check_authorization
def single(version):
    base_data = ['senders/', 'receivers/']

    return make_response(Response(json.dumps(base_data), mimetype='application/json'))


@NODE_API.route('/x-nmos/connection/<version>/single/<resource>/', methods=["GET"], strict_slashes=False)
@check_authorization
def resources(version, resource):
    if resource == 'senders':
        base_data = [r + '/' for r in [*NODE.senders]]
    elif resource == 'receivers':
        base_data = [r + '/' for r in [*NODE.receivers]]

    return make_response(Response(json.dumps(base_data), mimetype='application/json'))


@NODE_API.route('/x-nmos/connection/<version>/single/<resource>/<resource_id>', methods=["GET"], strict_slashes=False)
@check_authorization
def connection(version, resource, resource_id):
    if resource != 'senders' and resource != 'receivers':
        abort(404)

    base_data = ["constraints/", "staged/", "active/"]

    if resource == 'senders':
        base_data.append("transportfile/")

    if IS04Utils.compare_api_version("v1.1", version) <= 0:
        base_data.append("transporttype/")

    return make_response(Response(json.dumps(base_data), mimetype='application/json'))


def _get_constraints(resource, resource_id):
    """
    Returns basic constraint set for senders or receivers
    """
    if _resource_transport(resource, resource_id) == MXL_TRANSPORT:
        return {"mxl_domain_id": {}, "mxl_flow_id": {}}

    constraints = {"destination_port": {}, "rtp_enabled": {}}

    if resource == 'receivers':
        constraints["multicast_ip"] = {}
        constraints["interface_ip"] = {"enum": [get_default_ip()]}
        constraints["source_ip"] = {}

    elif resource == 'senders':
        constraints["destination_ip"] = {}
        constraints["source_port"] = {}
        constraints["source_ip"] = {"enum": [get_default_ip()]}

    return constraints


@NODE_API.route('/x-nmos/connection/<version>/single/<resource>/<resource_id>/constraints',
                methods=["GET"], strict_slashes=False)
@check_authorization
def constraints(version, resource, resource_id):
    base_data = [_get_constraints(resource, resource_id)]

    return make_response(Response(json.dumps(base_data), mimetype='application/json'))


def _check_constraint(constraint, transport_param):
    """
    Returns True if transport param meets constraint.
    enum: Must be exact match for one of the items in the list
    minimum: Must be greater than given value
    maximum: Must be smaller than given value
    auto values will return True
    """
    constraint_match = True

    for key, value in constraint.items():
        if key == 'enum' and transport_param not in value:
            constraint_match = False
        elif key == 'minimum' and transport_param < value:
            constraint_match = False
        elif key == 'maximum' and transport_param > value:
            constraint_match = False

    if transport_param == 'auto':
        constraint_match = True

    return constraint_match


@NODE_API.route('/x-nmos/connection/<version>/single/<resource>/<resource_id>/staged',
                methods=["GET", "PATCH"], strict_slashes=False)
@check_authorization
def staged(version, resource, resource_id):
    """
    GET returns current staged data for given resource
    PATCH updates data for given resource, either staging a connection, activating a staged connection,
    activating a connection without staging or deactivating an active connection
    Updates data then POSTs updated resource to registry
    """
    # Track requests. Schema validation outcome is attached for PATCH so controller
    # tests can report invalid request bodies without the mock rejecting them.
    request_json = request.get_json(silent=True)
    request_record = {'method': request.method, 'resource': resource, 'resource_id': resource_id,
                      'data': request_json}
    NODE.staged_requests.append(request_record)

    try:
        if resource == 'senders':
            resources = NODE.senders
            allowed_json = ['activation', 'master_enable', 'receiver_id', 'transport_params']
        elif resource == 'receivers':
            resources = NODE.receivers
            allowed_json = ['activation', 'master_enable', 'sender_id', 'transport_file', 'transport_params']
        else:
            abort(404)

        if request.method == 'GET':
            response_data = resources[resource_id]['activations']['staged']
            response_code = 200

        elif request.method == 'PATCH':
            # Check JSON data only contains allowed values
            for item in request_json:
                if item not in allowed_json:
                    return {'code': 400, 'debug': None, 'error': 'Invalid JSON entry ' + item}, 400

            schema_valid, schema_error = _validate_staged_patch_schema(
                resource, resource_id, request_json, version)
            request_record['schema_valid'] = schema_valid
            request_record['schema_error'] = schema_error

            # Update details for resource
            response_data, response_code = NODE.patch_staged(resource, resource_id, request_json)

    except KeyError:
        abort(404)

    # Return updated data
    return make_response(Response(json.dumps(response_data), status=response_code, mimetype='application/json'))


@NODE_API.route('/x-nmos/connection/<version>/single/<resource>/<resource_id>/active',
                methods=["GET"], strict_slashes=False)
@check_authorization
def active(version, resource, resource_id):
    try:
        if resource == 'senders':
            base_data = NODE.senders[resource_id]['activations']['active']
        elif resource == 'receivers':
            base_data = NODE.receivers[resource_id]['activations']['active']

        return make_response(Response(json.dumps(base_data), mimetype='application/json'))
    except KeyError:
        abort(404)


@NODE_API.route('/x-nmos/connection/<version>/single/<resource>/<resource_id>/transporttype',
                methods=["GET"], strict_slashes=False)
@check_authorization
def transport_type(version, resource, resource_id):
    try:
        if _resource_transport(resource, resource_id) == MXL_TRANSPORT:
            base_data = MXL_TRANSPORT
        else:
            base_data = "urn:x-nmos:transport:rtp"
    except KeyError:
        abort(404)

    return make_response(Response(json.dumps(base_data), mimetype='application/json'))


def _generate_sdp(media_type, media_subtype, src_ip, dst_ip, dst_port, sdp_params):
    template_path = None
    if media_type == 'video':
        if media_subtype == 'raw':
            template_path = "test_data/sdp/video.sdp"
        elif media_subtype == 'jxsv':
            template_path = "test_data/sdp/video-jxsv.sdp"
        elif media_subtype == 'smpte291':
            template_path = "test_data/sdp/data.sdp"
        elif media_subtype == 'SMPTE2022-6':
            template_path = "test_data/sdp/mux.sdp"
    elif media_type == 'audio':
        if media_subtype in ['L16', 'L24', 'L32']:
            template_path = "test_data/sdp/audio.sdp"

    if not template_path:
        abort(404)

    template_file = open(template_path).read()
    template = Template(template_file, keep_trailing_newline=True)

    # Not all keywords are used in all templates but that's OK
    return template.render({**sdp_params,
                            'src_ip': src_ip,
                            'dst_ip': dst_ip,
                            'dst_port': dst_port,
                            'media_subtype': media_subtype
                            })


@NODE_API.route('/<media_type>/<media_subtype>.sdp', methods=["GET"])
def node_sdp(media_type, media_subtype):

    sdp_file = _generate_sdp(media_type=media_type,
                             media_subtype=media_subtype,
                             src_ip=get_default_ip(),
                             dst_ip="232.40.50.{}".format(randint(1, 254)),
                             dst_port=randint(5000, 5999),
                             sdp_params=CONFIG.SDP_PREFERENCES)

    response = make_response(sdp_file)
    response.headers['Content-Type'] = 'application/sdp'
    return response


@NODE_API.route('/x-nmos/connection/<version>/single/<resource>/<resource_id>/transportfile',
                methods=["GET"], strict_slashes=False)
@check_authorization
def transport_file(version, resource, resource_id):
    # GET should either redirect to the location of the transport file or return it directly
    try:
        if resource == 'senders':
            if _resource_transport(resource, resource_id) == MXL_TRANSPORT:
                abort(404)

            sender = NODE.senders[resource_id]
            sdp_params = {**CONFIG.SDP_PREFERENCES, **sender.get('sdp_params', {})}

            media_type = sdp_params.get('media_type', 'video/raw')

            media_type, media_subtype = media_type.split("/")

            sdp_file = _generate_sdp(media_type=media_type,
                                     media_subtype=media_subtype,
                                     src_ip=sender['activations']['transport_params'][0]['source_ip'],
                                     dst_ip=sender['activations']['transport_params'][0]['destination_ip'],
                                     dst_port=sender['activations']['transport_params'][0]['destination_port'],
                                     sdp_params=sdp_params)

            response = make_response(sdp_file, 200)
            response.headers['Content-Type'] = 'application/sdp'

            return response

        # Unknown resource type
        abort(404)
    except KeyError:
        # Requested a resource that doesn't exist
        abort(404)


def _record_annotation_request(resource_type, resource_id, body, status, schema_valid=None, schema_error=None):
    record = {
        "method": request.method,
        "path": request.path,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "data": body,
        "status": status,
    }
    if request.method == "PATCH":
        record["schema_valid"] = schema_valid
        record["schema_error"] = schema_error
    NODE.annotation_requests.append(record)


def _annotation_patch_response(resource_type, resource_id):
    body = request.get_json(silent=True)
    schema_file = "resource_core_patch.json"
    try:
        schema = load_resolved_schema(IS13_SPEC_PATH, schema_file)
    except (OSError, IOError, FileNotFoundError) as exception:
        load_error = "Unable to load IS-13 patch schema '{}': {}".format(schema_file, exception)
        response = {"code": 500, "error": load_error, "debug": None}
        _record_annotation_request(resource_type, resource_id, body, 500, False, load_error)
        return _annotation_json(response, 500)

    schema_error = _validate_against_schema(body, schema)
    if schema_error:
        response = {"code": 400, "error": schema_error, "debug": None}
        _record_annotation_request(resource_type, resource_id, body, 400, False, schema_error)
        return _annotation_json(response, 400)

    response, status = NODE.patch_annotation(resource_id, body)
    _record_annotation_request(resource_type, resource_id, body, status, True, None)
    return _annotation_json(response, status)


@NODE_API.route('/x-nmos/annotation', methods=['GET'], strict_slashes=False)
@check_annotation_authorization
def annotation_root():
    base_data = [version + '/' for version in CONFIG.SPECIFICATIONS["is-13"]["versions"]]

    return _annotation_json(base_data)


@NODE_API.route('/x-nmos/annotation/<version>', methods=['GET'], strict_slashes=False)
@check_annotation_authorization
def annotation_version(version):
    base_data = ['node/']

    return _annotation_json(base_data)


@NODE_API.route('/x-nmos/annotation/<version>/node', methods=['GET'], strict_slashes=False)
@check_annotation_authorization
def annotation_node(version):
    base_data = ['self/', 'sources/', 'flows/', 'devices/', 'senders/', 'receivers/']

    return _annotation_json(base_data)


@NODE_API.route('/x-nmos/annotation/<version>/node/self', methods=['GET', 'PATCH'], strict_slashes=False)
@check_annotation_authorization
def annotation_self(version):
    resource_id = NODE.annotation_id_for_type("node")
    if resource_id is None:
        return _annotation_json({"code": 500, "error": "Self resource not found", "debug": None}, 500)
    if request.method == "GET":
        _record_annotation_request("self", resource_id, None, 200)
        return _annotation_json(NODE.annotation_core(NODE.annotation_resources[resource_id]["resource"]))
    return _annotation_patch_response("self", resource_id)


@NODE_API.route('/x-nmos/annotation/<version>/node/<resource_type>', methods=['GET'], strict_slashes=False)
@check_annotation_authorization
def annotation_resources(version, resource_type):
    reg_type = resource_type.rstrip("s")
    if reg_type not in ANNOTATION_SUBRESOURCE_TYPES:
        abort(404)
    return _annotation_json(NODE.annotation_ids(reg_type))


@NODE_API.route('/x-nmos/annotation/<version>/node/<resource_type>/<resource_id>',
                methods=['GET', 'PATCH'], strict_slashes=False)
@check_annotation_authorization
def annotation_resource(version, resource_type, resource_id):
    reg_type = resource_type.rstrip("s")
    entry = NODE.annotation_resources.get(resource_id)
    if reg_type not in ANNOTATION_SUBRESOURCE_TYPES or entry is None or entry["reg_type"] != reg_type:
        abort(404)
    if request.method == "GET":
        _record_annotation_request(resource_type, resource_id, None, 200)
        return _annotation_json(NODE.annotation_core(entry["resource"]))
    return _annotation_patch_response(resource_type, resource_id)
