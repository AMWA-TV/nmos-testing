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
import time

from flask import Blueprint, make_response, abort, Response
from random import randint
from jinja2 import Template
from .. import Config as CONFIG
from ..TestHelper import get_default_ip, do_request
from ..NMOSUtils import NMOSUtils

class Node(object):
    def __init__(self, port_increment):
        self.port = CONFIG.PORT_BASE + 200 + port_increment
        self.id = str(uuid.uuid4())
        self.registry_url = ''
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
            "destination_port": "5004",
            "rtp_enabled": True,
            "source_ip": get_default_ip(),
            "source_port": "5004"
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

    def remove_senders(self):
        self.senders = {}

    def add_receiver(self, receiver):

        transport_params = [{
            "destination_port": "auto",
            "interface_ip": "auto",
            "multicast_ip": None,
            "rtp_enabled": True,
            "source_ip": None
        }]

        activations = {
            'transport_params':transport_params,
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
                'transport_params': transport_params
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
                'transport_params': transport_params
            }
        }            

        self.receivers[receiver['id']] = {
            'activations': activations,
            'receiver': receiver
        }

    def remove_receivers(self):
        self.receivers = {}

    def remove_receiver(self, receiver_id):
        self.receivers.pop(receiver_id)

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
    if resource == 'senders':
        base_data = ["constraints/", "staged/", "active/", "transportfile/", "transporttype/"]
    elif resource == 'receivers':
        base_data = ["constraints/", "staged/", "active/", "transporttype/"]

    return make_response(Response(json.dumps(base_data), mimetype='application/json'))

@NODE_API.route('/x-nmos/connection/<version>/single/<resource>/<resource_id>/constraints', methods=["GET"], strict_slashes=False)
def constraints(version, resource, resource_id):
    base_data = [{
        "destination_ip": {},
        "destination_port": {},
        "multicast_ip": {},
        "rtp_enabled": {},
        "source_ip": {
            "enum": [get_default_ip()]
        },
        "source_port": {}
    }]

    return make_response(Response(json.dumps(base_data), mimetype='application/json'))


def _create_activation_update(receiver, master_enable, activation=None):

    sender = NODE.senders[receiver['sender_id']] if receiver else None

    transport_params_update = {
        'connection_authorisation': False,
        'connection_uri': 'events API on device?' if master_enable and receiver else None,
        'ext_is_07_rest_api_url': 'events API on sources?' if master_enable and receiver else None,
        'ext_is_07_source_id': 'source id?' if master_enable and receiver else None,
        'multicast_ip': sender['activations']['transport_params'][0]['destination_ip'] if master_enable and sender else None,
        'destination_port': sender['activations']['transport_params'][0]['destination_port'] if master_enable and sender else None
    }

    transport_params = receiver.get('transport_params') if receiver else None
    transport_file = receiver.get('transport_file') if receiver and 'transport_file' in receiver else {'data': None, 'type': None}
    sender_id = receiver.get('sender_id') if receiver else None

    updated_transport_params = dict(transport_params[0], **transport_params_update) if transport_params else transport_params_update

    activation_update = {
        "activation": {
            "activation_time": time.time() if activation else "", 
            "mode": activation['mode'] if activation else "", 
            "requested_time": None
        },
        'master_enable': master_enable,
        'sender_id': sender_id,
        'transport_file': transport_file,
        'transport_params': [ updated_transport_params ]
    }

    return activation_update

def _update_receiver_subscription(receiver, active, sender_id):

    receiver_update = {
        'subscription': {'active': active, 'sender_id': sender_id},
        'version': NMOSUtils.create_resource_version()
    }

    return dict(receiver, **receiver_update)

@NODE_API.route('/x-nmos/connection/<version>/single/<resource>/<resource_id>/staged', methods=["GET", "PATCH"], strict_slashes=False)
def staged(version, resource, resource_id):
    """
    GET returns current staged data for given resource
    PATCH updates data for given resource, either staging a connection, activating a staged connection, 
    activating a connection without staging or deactivating an active connection
    Updates data then POSTs updated receiver to registry
    """
    NODE.staged_requests.append({'method': request.method, 'resource': resource, 'resource_id': resource_id, 'data': request.json})

    try:
        # Hmmmm, patching of Senders currently results in a 404 error
        if resource == 'senders':
            resources = NODE.senders
        elif resource == 'receivers':
            resources = NODE.receivers

        if request.method == 'PATCH':
        
            activations = resources[resource_id]['activations']
            receiver = resources[resource_id]['receiver']
        
            if request.json.get("sender_id"):
                # Either patching to staged or directly to activated
                # Data for response
                activation_update = _create_activation_update(request.json, True, request.json.get('activation'))

                if "activation" in request.json:
                    # Activating without staging first
                    activations['active'] = activation_update

                    # Add subscription details to receiver
                    receiver = _update_receiver_subscription(receiver, True, request.json['sender_id'])

                    # POST updated receiver to registry
                    do_request("POST", NODE.registry_url + 'x-nmos/registration/v1.3/resource', json={"type": "receiver", "data": receiver})
                else:
                    # Staging
                    # Update activations but nothing should change in registry
                    activations['staged'] = activation_update

            elif request.json.get("activation"):
                # Either patching to activate after staging or deactivating
                if request.json['activation'].get('mode') == 'activate_immediate':
                    if activations['staged']['master_enable'] == True:
                        # Activating after staging
                        activation_update = _create_activation_update(activations['staged'], True, request.json.get('activation'))

                        activations['active'] = activation_update
                        activations['staged'] = _create_activation_update(None, False)

                        # Add subscription details to receiver
                        receiver = _update_receiver_subscription(receiver, True, activations['active']['sender_id'])

                        # POST updated receiver to registry
                        do_request("POST", NODE.registry_url + 'x-nmos/registration/v1.3/resource', json={"type": "receiver", "data": receiver})
        
                    else:
                        # Deactivating
                        activation_update = _create_activation_update(activations['active'], False, request.json.get('activation'))

                        activations['active'] = activation_update

                        # Add subscription details to receiver
                        receiver = _update_receiver_subscription(receiver, False, None)
                    
                        # POST updated receiver to registry
                        do_request("POST", NODE.registry_url + 'x-nmos/registration/v1.3/resource', json={"type": "receiver", "data": receiver})

                else:
                    # shouldn't have got here
                    abort(500)

        elif request.method == 'GET':
            # Need to fetch json of actual current 'staged' info
            activation_update = resources[resource_id]['activations']['staged']
    except KeyError:
        # something went wrong
        abort(500)

    return make_response(Response(json.dumps(activation_update), mimetype='application/json'))

@NODE_API.route('/x-nmos/connection/<version>/single/<resource>/<resource_id>/active', methods=["GET"], strict_slashes=False)
def active(version, resource, resource_id):
    try: 
        if resource == 'senders':
            base_data = NODE.senders[resource_id]['activations']['active']
        elif resource == 'receivers':
            base_data = NODE.receivers[resource_id]['activations']['active']

        return make_response(Response(json.dumps(base_data), mimetype='application/json'))
    except KeyError:
        abort(404)

@NODE_API.route('/x-nmos/connection/<version>/single/<resource>/<resource_id>/transporttype', methods=["GET"], strict_slashes=False)
def transport_type(version, resource, resource_id):
    # TODO fetch from resource info
    base_data = "urn:x-nmos:transport:websocket"
    # alternatively "urn:x-nmos:transport:rtp.mcast"

    return make_response(Response(json.dumps(base_data), mimetype='application/json'))

@NODE_API.route('/x-nmos/connection/<version>/single/<resource>/<resource_id>/transportfile', methods=["GET"], strict_slashes=False)
def transport_file(version, resource, resource_id):
    # GET should either redirect to the location of the transport file or return it directly (easy-nmos requests to this endpoint return 404)
    try: 
        if resource == 'senders':
            with open("test_data/NC01/video.sdp") as f:
                sender = NODE.senders[resource_id]
                destination_ip = sender['activations']['transport_params'][0]['destination_ip']
                source_ip = sender['activations']['transport_params'][0]['source_ip']

                # substitute source and destination ips into the video.sdp template
                sdp_data = f.read()
                formatted_data = sdp_data.format(source_ip, destination_ip, destination_ip, source_ip)

            response = make_response(formatted_data, 200)
            response.headers["Content-Type"] = "application/sdp"

            return response

        elif resource == 'receivers':
            file_name = NODE.receivers[resource_id]['activations']['transport_file']
        
            return make_response(Response(json.dumps(sdp_data), mimetype='application/json'))

        #unknown resource type
        abort(404)
    except KeyError:
        # Requested a resource that doesn't exist
        abort(404)
