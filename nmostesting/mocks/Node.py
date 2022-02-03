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

from flask import Blueprint, make_response, abort, Response, request, url_for
from random import randint
from copy import deepcopy
from jinja2 import Template
from .. import Config as CONFIG
from ..TestHelper import get_default_ip, do_request
from ..NMOSUtils import NMOSUtils


class Node(object):
    def __init__(self, port_increment):
        self.port = CONFIG.PORT_BASE + 200 + port_increment
        self.id = str(uuid.uuid4())
        self.registry_url = ''
        self.reset()

    def reset(self):
        self.staged_requests = []
        self.receivers = {}
        self.senders = {}

    def get_sender(self, stream_type="video"):
        protocol = "http"
        host = get_default_ip()
        if CONFIG.ENABLE_HTTPS:
            protocol = "https"
            if CONFIG.DNS_SD_MODE == "multicast":
                host = "nmos-mocks.local"
            else:
                host = "mocks.{}".format(CONFIG.DNS_DOMAIN)
        # TODO: Provide the means to downgrade this to a <v1.2 JSON representation
        sender = {
            "id": str(uuid.uuid4()),
            "label": "Dummy Sender",
            "description": "Dummy Sender",
            "version": "50:50",
            "caps": {},
            "tags": {},
            "manifest_href": "{}://{}:{}/{}.sdp".format(protocol, host, self.port, stream_type),
            "flow_id": str(uuid.uuid4()),
            "transport": "urn:x-nmos:transport:rtp.mcast",
            "device_id": str(uuid.uuid4()),
            "interface_bindings": ["eth0"],
            "subscription": {
                "receiver_id": None,
                "active": True
            }
        }
        return sender

    def add_sender(self, sender, sender_ip_address):
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
            'activations': sender_update
        }

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


NODE = Node(1)
NODE_API = Blueprint('node_api', __name__)


@NODE_API.route('/<stream_type>.sdp', methods=["GET"])
def node_sdp(stream_type):
    # TODO: Should we check for an auth token here? May depend on the URL?
    if stream_type == "video":
        template_path = "test_data/IS0401/video.sdp"
    elif stream_type == "audio":
        template_path = "test_data/IS0401/audio.sdp"
    elif stream_type == "data":
        template_path = "test_data/IS0401/data.sdp"
    elif stream_type == "mux":
        template_path = "test_data/IS0401/mux.sdp"
    else:
        abort(404)

    template_file = open(template_path).read()
    template = Template(template_file, keep_trailing_newline=True)

    src_ip = get_default_ip()
    dst_ip = "232.40.50.{}".format(randint(1, 254))
    dst_port = randint(5000, 5999)

    if stream_type == "video":
        interlace = ""
        if CONFIG.SDP_PREFERENCES["video_interlace"] is True:
            interlace = "interlace; "
        # TODO: The SDP_PREFERENCES doesn't include video media type
        sdp_file = template.render(dst_ip=dst_ip, dst_port=dst_port, src_ip=src_ip, media_type="raw",
                                   width=CONFIG.SDP_PREFERENCES["video_width"],
                                   height=CONFIG.SDP_PREFERENCES["video_height"],
                                   interlace=interlace,
                                   exactframerate=CONFIG.SDP_PREFERENCES["video_exactframerate"])
    elif stream_type == "audio":
        # TODO: The SDP_PREFERENCES doesn't include audio media type or sample depth
        sdp_file = template.render(dst_ip=dst_ip, dst_port=dst_port, src_ip=src_ip, media_type="L24",
                                   channels=CONFIG.SDP_PREFERENCES["audio_channels"],
                                   sample_rate=CONFIG.SDP_PREFERENCES["audio_sample_rate"])
    elif stream_type == "data":
        sdp_file = template.render(dst_ip=dst_ip, dst_port=dst_port, src_ip=src_ip)
    elif stream_type == "mux":
        sdp_file = template.render(dst_ip=dst_ip, dst_port=dst_port, src_ip=src_ip)

    response = make_response(sdp_file)
    response.headers["Content-Type"] = "application/sdp"
    return response


@NODE_API.route('/x-nmos', methods=['GET'], strict_slashes=False)
def x_nmos_root():
    base_data = ['connection/']

    return make_response(Response(json.dumps(base_data), mimetype='application/json'))


@NODE_API.route('/x-nmos/connection', methods=['GET'], strict_slashes=False)
def connection_root():
    base_data = ['v1.0/', 'v1.1/']

    return make_response(Response(json.dumps(base_data), mimetype='application/json'))


@NODE_API.route('/x-nmos/connection/<version>', methods=['GET'], strict_slashes=False)
def version(version):
    base_data = ['bulk/', 'single/']

    return make_response(Response(json.dumps(base_data), mimetype='application/json'))


@NODE_API.route('/x-nmos/connection/<version>/single', methods=['GET'], strict_slashes=False)
def single(version):
    base_data = ['senders/', 'receivers/']

    return make_response(Response(json.dumps(base_data), mimetype='application/json'))


@NODE_API.route('/x-nmos/connection/<version>/single/<resource>/', methods=["GET"], strict_slashes=False)
def resources(version, resource):
    if resource == 'senders':
        base_data = [r + '/' for r in [*NODE.senders]]
    elif resource == 'receivers':
        base_data = [r + '/' for r in [*NODE.receivers]]

    return make_response(Response(json.dumps(base_data), mimetype='application/json'))


@NODE_API.route('/x-nmos/connection/<version>/single/<resource>/<resource_id>', methods=["GET"], strict_slashes=False)
def connection(version, resource, resource_id):
    if resource != 'senders' and resource != 'receivers':
        abort(404)

    base_data = ["constraints/", "staged/", "active/"]

    if resource == 'senders':
        base_data.append("transportfile/")

    if NMOSUtils.compare_api_version("v1.1", version) <= 0:
        base_data.append("transporttype/")

    return make_response(Response(json.dumps(base_data), mimetype='application/json'))


@NODE_API.route('/x-nmos/connection/<version>/single/<resource>/<resource_id>/constraints',
                methods=["GET"], strict_slashes=False)
def constraints(version, resource, resource_id):
    base_data = [{
        "destination_port": {},
        "rtp_enabled": {},
    }]
    if resource == 'receivers':
        base_data[0]["multicast_ip"] = {}
        base_data[0]["interface_ip"] = {"enum": [get_default_ip()]}
        base_data[0]["source_ip"] = {}
    elif resource == 'senders':
        base_data[0]["destination_ip"] = {}
        base_data[0]["source_port"] = {}
        base_data[0]["source_ip"] = {"enum": [get_default_ip()]}

    return make_response(Response(json.dumps(base_data), mimetype='application/json'))


def _check_constraint(constraint, transport_param):
    """
    Returns True if transport param meets constraint.
    enum: Must be exact match for one of the items in the list
    minimum: Must be greater than given value
    maximum: Must be smaller than given value
    """
    constraint_match = True

    for key, value in constraint.items():
        if key == 'enum' and transport_param not in value:
            constraint_match = False
        elif key == 'minimum' and transport_param < value:
            constraint_match = False
        elif key == 'maximum' and transport_param > value:
            constraint_match = False

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
    # Track requests
    NODE.staged_requests.append({'method': request.method, 'resource': resource, 'resource_id': resource_id,
                                 'data': request.json})

    if resource not in ['senders', 'receivers']:
        abort(404)

    try:
        response_data = {}
        response_code = 200
        resources = NODE.senders if resource == 'senders' else NODE.receivers

        if request.method == 'GET':
            response_data = resources[resource_id]['activations']['staged']

        elif request.method == 'PATCH':
            # Check JSON data only contains allowed values
            allowed_json = ['activation', 'master_enable', 'sender_id', 'receiver_id', 'transport_file',
                            'transport_params']
            for item in request.json:
                if item not in allowed_json:
                    return {'code': 400, 'debug': None, 'error': 'Invalid JSON entry ' + item}, 400

            # Get current staged and active details for resource
            activations = resources[resource_id]['activations']

            # Check transport params against constraints
            if request.json.get('transport_params'):
                response_data['transport_params'] = [{}]
                transport_params = request.json['transport_params']
                constraints_url = 'http://' + get_default_ip() + ':' + str(NODE.port) + \
                    url_for('.constraints', version=version, resource=resource, resource_id=resource_id)
                valid, response = do_request('GET', constraints_url)

                for key, value in response.json()[0].items():
                    if value and key in transport_params[0] and transport_params[0][key] != 'auto':
                        # There is a constraint for this param and a value in the request to check
                        check = _check_constraint(value, transport_params[0][key])
                        if not check:
                            return {'code': 400, 'debug': None, 
                                    'error': 'Transport param {} does not satisfy constraints.'.format(key)}, 400

                        # Save verified non-auto param
                        response_data['transport_params'][0][key] = transport_params[0][key]
                    else:
                        # Save auto or existing staged value
                        staged_param = activations['staged']['transport_params'][0].get(key)
                        response_data['transport_params'][0][key] = transport_params[0].get(key, staged_param)
            else:
                # No transport params in request. Get existing staged params
                response_data['transport_params'] = activations['staged']['transport_params']

            # Set up default transport parameters to fill in auto or missing values
            default_params = {'multicast_ip': None, 'destination_port': 5004, 'source_ip': get_default_ip(),
                              'interface_ip': get_default_ip(), 'rtp_enabled': True, 'source_port': 5004}

            # Update linked sender or receiver if included and get transport file for receivers
            if resource == 'senders':
                resource_type = 'sender'
                response_data['receiver_id'] = request.json.get('receiver_id')

                # Update subscription for POST to mock registry
                subscription_update = resources[resource_id]['sender']
                subscription_update['subscription']['active'] = request.json.get('master_enable',
                                                                                 activations['staged']['master_enable'])
                subscription_update['version'] = NMOSUtils.get_TAI_time()

                if subscription_update['subscription']['active'] is True:
                    receiver_id = request.json.get('receiver_id', activations['staged']['receiver_id'])
                    subscription_update['subscription']['receiver_id'] = receiver_id
                else:
                    subscription_update['subscription']['receiver_id'] = None

                default_params['destination_ip'] = activations['transport_params'][0]['destination_ip']

            elif resource == 'receivers':
                resource_type = 'receiver'
                response_data['sender_id'] = request.json.get('sender_id')
                response_data['transport_file'] = request.json.get('transport_file', {'data': None, 'type': None})

                # Update subscription for POST to mock registry
                subscription_update = resources[resource_id]['receiver']
                subscription_update['subscription']['active'] = request.json.get('master_enable',
                                                                                 activations['staged']['master_enable'])
                subscription_update['version'] = NMOSUtils.get_TAI_time()

                if subscription_update['subscription']['active'] is True:
                    sender_id = request.json.get('sender_id', activations['staged']['sender_id'])
                    subscription_update['subscription']['sender_id'] = sender_id
                else:
                    subscription_update['subscription']['sender_id'] = None

            # Get other request data
            response_data['activation'] = request.json.get('activation', {"activation_time": None, "mode": None,
                                                                          "requested_time": None})
            response_data['master_enable'] = request.json.get('master_enable', True)

            if not request.json.get('activation'):
                # Just staging so return data
                pass

            elif request.json.get('master_enable') is False:
                # Deactivating
                # POST updated subscription to registry
                valid, response = do_request('POST', NODE.registry_url + 'x-nmos/registration/' + version + '/resource',
                                             json={'type': resource_type, 'data': subscription_update})

                response_data['activation']['activation_time'] = NMOSUtils.get_TAI_time()
                response_data['activation']['requested_time'] = None

                # Update active data
                activations['active'] = response_data
                activations['active']['activation'] = {"activation_time": None, "mode": None, "requested_time": None}

            else:
                # Activating
                # Check for empty keys in response_data and fill in from staged
                for key, value in response_data.items():
                    if value is None:
                        response_data[key] = activations['staged'][key]

                # Check for auto in params and update from defaults
                for key, value in response_data['transport_params'][0].items():
                    if value == 'auto':
                        response_data['transport_params'][0][key] = default_params[key]

                # Add activation time
                response_data['activation']['activation_time'] = NMOSUtils.get_TAI_time()

                if response_data['activation']['mode'] == 'activate_immediate':
                    response_data['activation']['requested_time'] = None
                else:
                    # Note: Currently all mock activations are immediate regardless of requested mode
                    response_code = 202

                # POST updated subscription to registry
                valid, response = do_request('POST', NODE.registry_url + 'x-nmos/registration/' + version +'/resource',
                                             json={'type': resource_type, 'data': subscription_update})

                # Update active data with new data
                activations['active'] = response_data
                activations['transport_params'] = response_data['transport_params']

            # Update staged data with new data
            staged_data = deepcopy(response_data)
            staged_data['activation'] = {"activation_time": None, "mode": None, "requested_time": None}
            activations['staged'] = staged_data

    except KeyError:
        abort(404)

    # Return updated data
    return make_response(Response(json.dumps(response_data), status=response_code, mimetype='application/json'))


@NODE_API.route('/x-nmos/connection/<version>/single/<resource>/<resource_id>/active',
                methods=["GET"], strict_slashes=False)
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
def transport_type(version, resource, resource_id):
    # TODO fetch from resource info
    base_data = "urn:x-nmos:transport:rtp"

    return make_response(Response(json.dumps(base_data), mimetype='application/json'))


@NODE_API.route('/x-nmos/connection/<version>/single/<resource>/<resource_id>/transportfile',
                methods=["GET"], strict_slashes=False)
def transport_file(version, resource, resource_id):
    # GET should either redirect to the location of the transport file or return it directly
    try:
        if resource == 'senders':
            template_path = "test_data/controller/video.sdp"

            template_file = open(template_path).read()
            template = Template(template_file, keep_trailing_newline=True)

            sender = NODE.senders[resource_id]
            destination_ip = sender['activations']['transport_params'][0]['destination_ip']
            destination_port = sender['activations']['transport_params'][0]['destination_port']
            source_ip = sender['activations']['transport_params'][0]['source_ip']

            interlace = ""
            if CONFIG.SDP_PREFERENCES["video_interlace"] is True:
                interlace = "interlace; "
            # TODO: The SDP_PREFERENCES doesn't include video media type
            sdp_file = template.render(dst_ip=destination_ip,
                                       dst_port=destination_port,
                                       src_ip=source_ip,
                                       media_type="raw",
                                       width=CONFIG.SDP_PREFERENCES["video_width"],
                                       height=CONFIG.SDP_PREFERENCES["video_height"],
                                       interlace=interlace,
                                       exactframerate=CONFIG.SDP_PREFERENCES["video_exactframerate"])

            response = make_response(sdp_file, 200)
            response.headers["Content-Type"] = "application/sdp"

            return response

        # Unknown resource type
        abort(404)
    except KeyError:
        # Requested a resource that doesn't exist
        abort(404)
