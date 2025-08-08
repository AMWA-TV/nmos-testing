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

import uuid
import json
import ipaddress
import re

from flask import Blueprint, make_response, abort, Response, request
from random import randint
from copy import deepcopy
from jinja2 import Template
from .. import Config as CONFIG
from ..TestHelper import get_default_ip, do_request
from ..IS04Utils import IS04Utils
from ..IS10Utils import IS10Utils
from .Auth import PRIMARY_AUTH


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
        constraints = _get_constraints(resource)

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


NODE = Node(1)
NODE_API = Blueprint('node_api', __name__)


@NODE_API.route('/x-nmos', methods=['GET'], strict_slashes=False)
def x_nmos_root():
    base_data = ['connection/']

    return make_response(Response(json.dumps(base_data), mimetype='application/json'))


@NODE_API.route('/x-nmos/connection', methods=['GET'], strict_slashes=False)
def connection_root():
    base_data = ['v1.0/', 'v1.1/']

    authorized, error_message = IS10Utils.check_authorization(PRIMARY_AUTH,
                                                              request.path,
                                                              scopes=["x-nmos-connection"])
    if authorized is not True:
        abort(authorized, description=error_message)

    return make_response(Response(json.dumps(base_data), mimetype='application/json'))


@NODE_API.route('/x-nmos/connection/<version>', methods=['GET'], strict_slashes=False)
def version(version):
    base_data = ['bulk/', 'single/']

    authorized, error_message = IS10Utils.check_authorization(PRIMARY_AUTH,
                                                              request.path,
                                                              scopes=["x-nmos-connection"])
    if authorized is not True:
        abort(authorized, description=error_message)

    return make_response(Response(json.dumps(base_data), mimetype='application/json'))


@NODE_API.route('/x-nmos/connection/<version>/single', methods=['GET'], strict_slashes=False)
def single(version):
    base_data = ['senders/', 'receivers/']

    authorized, error_message = IS10Utils.check_authorization(PRIMARY_AUTH,
                                                              request.path,
                                                              scopes=["x-nmos-connection"])
    if authorized is not True:
        abort(authorized, description=error_message)

    return make_response(Response(json.dumps(base_data), mimetype='application/json'))


@NODE_API.route('/x-nmos/connection/<version>/single/<resource>/', methods=["GET"], strict_slashes=False)
def resources(version, resource):
    authorized, error_message = IS10Utils.check_authorization(PRIMARY_AUTH,
                                                              request.path,
                                                              scopes=["x-nmos-connection"])
    if authorized is not True:
        abort(authorized, description=error_message)

    if resource == 'senders':
        base_data = [r + '/' for r in [*NODE.senders]]
    elif resource == 'receivers':
        base_data = [r + '/' for r in [*NODE.receivers]]

    return make_response(Response(json.dumps(base_data), mimetype='application/json'))


@NODE_API.route('/x-nmos/connection/<version>/single/<resource>/<resource_id>', methods=["GET"], strict_slashes=False)
def connection(version, resource, resource_id):
    authorized, error_message = IS10Utils.check_authorization(PRIMARY_AUTH,
                                                              request.path,
                                                              scopes=["x-nmos-connection"])
    if authorized is not True:
        abort(authorized, description=error_message)

    if resource != 'senders' and resource != 'receivers':
        abort(404)

    base_data = ["constraints/", "staged/", "active/"]

    if resource == 'senders':
        base_data.append("transportfile/")

    if IS04Utils.compare_api_version("v1.1", version) <= 0:
        base_data.append("transporttype/")

    return make_response(Response(json.dumps(base_data), mimetype='application/json'))


def _get_constraints(resource):
    """
    Returns basic constraint set for senders or receivers
    """
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
def constraints(version, resource, resource_id):
    authorized, error_message = IS10Utils.check_authorization(PRIMARY_AUTH,
                                                              request.path,
                                                              scopes=["x-nmos-connection"])
    if authorized is not True:
        abort(authorized, description=error_message)

    base_data = [_get_constraints(resource)]

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
def staged(version, resource, resource_id):
    """
    GET returns current staged data for given resource
    PATCH updates data for given resource, either staging a connection, activating a staged connection,
    activating a connection without staging or deactivating an active connection
    Updates data then POSTs updated resource to registry
    """
    authorized, error_message = IS10Utils.check_authorization(PRIMARY_AUTH,
                                                              request.path,
                                                              scopes=["x-nmos-connection"],
                                                              write=request.method == 'PATCH')
    if authorized is not True:
        abort(authorized, description=error_message)

    # Track requests
    NODE.staged_requests.append({'method': request.method, 'resource': resource, 'resource_id': resource_id,
                                 'data': request.get_json(silent=True)})

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
            for item in request.get_json():
                if item not in allowed_json:
                    return {'code': 400, 'debug': None, 'error': 'Invalid JSON entry ' + item}, 400

            # Update details for resource
            response_data, response_code = NODE.patch_staged(resource, resource_id, request.json)

    except KeyError:
        abort(404)

    # Return updated data
    return make_response(Response(json.dumps(response_data), status=response_code, mimetype='application/json'))


@NODE_API.route('/x-nmos/connection/<version>/single/<resource>/<resource_id>/active',
                methods=["GET"], strict_slashes=False)
def active(version, resource, resource_id):
    authorized, error_message = IS10Utils.check_authorization(PRIMARY_AUTH,
                                                              request.path,
                                                              scopes=["x-nmos-connection"])
    if authorized is not True:
        abort(authorized, description=error_message)
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
def transport_type(version, resource, resource_id):
    authorized, error_message = IS10Utils.check_authorization(PRIMARY_AUTH,
                                                              request.path,
                                                              scopes=["x-nmos-connection"])
    if authorized is not True:
        abort(authorized, description=error_message)
    # TODO fetch from resource info
    base_data = "urn:x-nmos:transport:rtp"

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
def transport_file(version, resource, resource_id):
    authorized, error_message = IS10Utils.check_authorization(PRIMARY_AUTH,
                                                              request.path,
                                                              scopes=["x-nmos-connection"])
    if authorized is not True:
        abort(authorized, description=error_message)
    # GET should either redirect to the location of the transport file or return it directly
    try:
        if resource == 'senders':
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
