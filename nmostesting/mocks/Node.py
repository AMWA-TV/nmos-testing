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


class Node(object):
    def __init__(self, port_increment):
        self.port = CONFIG.PORT_BASE + 200 + port_increment
        self.id = str(uuid.uuid4())
        self.senders = []
        self.receivers = []
        self.sender_base_data = ''
        self.receiver_base_data = ''
        self.registry_url = ''

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

    def add_senders(self, senders, sender_base_data):
        """
        Takes self.senders from mock registry and adds connection details
        """
        self.sender_base_data = sender_base_data
        for sender in senders:
            sender['transport_file'] = sender['manifest_href']
            sender['transport_params'] = [{"destination_ip": "auto",
                                           "destination_port": "auto",
                                           "rtp_enabled": True,
                                           "source_ip": {
                                               "enum": [get_default_ip()]
                                            },
                                           "source_port": "auto"
                                        }]
            sender['staged'] = { 
                "activation": {
                    "activation_time": None,
                    "mode": None,
                    "requested_time": None
                },
                "master_enable": True,
                "receiver_id": None,
            }
            sender['staged']['transport_params'] = sender['transport_params']
            sender['active'] = {
                                "activation": {
                                    "activation_time": None,
                                    "mode": None,
                                    "requested_time": None
                                },
                                "master_enable": True,
                                "receiver_id": None
                                }
            sender['active']['transport_params'] = sender['transport_params']

            self.senders.append(sender)

    def add_receivers(self, receivers, receiver_base_data):
        """
        Takes self.receivers from mock registry and adds connection details
        """
        self.receiver_base_data = receiver_base_data
        for receiver in receivers:
            receiver['transport_params'] = [{"destination_port": "auto",
                                            "interface_ip": "auto",
                                            "multicast_ip": None,
                                            "rtp_enabled": True,
                                            "source_ip": None
                                            }]
            receiver['staged'] = {"activation": {
                                      "activation_time": None,
                                      "mode": None,
                                      "requested_time": None
                                  },
                                  "master_enable": False,
                                  "sender_id": None,
                                  "transport_file": {
                                      "data": None,
                                      "type": None
                                      }
                                 }
            receiver['staged']['transport_params'] = receiver['transport_params']
            receiver['active'] = {"activation": {
                                      "activation_time": None,
                                      "mode": None,
                                      "requested_time": None
                                      },
                                  "master_enable": False,
                                  "sender_id": None,
                                  "transport_file": {
                                      "data": None,
                                      "type": None
                                      }
                                 }
            receiver['active']['transport_params'] = receiver['transport_params']

            self.receivers.append(receiver)



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
        resource_list = NODE.senders
    elif resource == 'receivers':
        resource_list = NODE.receivers

    base_data = [r['id'] + '/' for r in resource_list]

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

@NODE_API.route('/x-nmos/connection/<version>/single/<resource>/<resource_id>/staged', methods=["GET", "PATCH"], strict_slashes=False)
def staged(version, resource, resource_id):
    """
    GET returns current staged data for given resource
    PATCH updates data for given resource, either staging a connection, activating a staged connection, 
    activating a connection without staging or deactivating an active connection
    Updates data then POSTs updated receiver to registry
    """
    if resource == 'senders':
        resource_list = NODE.senders
    elif resource == 'receivers':
        resource_list = NODE.receivers

    try: 
        resource_index = [i for i, r in enumerate(resource_list) if r['id'] == resource_id][0]
    except IndexError:
        # Requested a resource that doesn't exist
        abort(404)
    
    if request.method == 'PATCH':
        resource_details = resource_list.pop(resource_index)
        base_data = {"activation": {"activation_time": "", "mode": "", "requested_time": None}}
        
        if "sender_id" in request.json:
            # Either patching to staged or directly to activated
            sender = [s for s in NODE.senders if s['id'] == request.json['sender_id']][0]
            # Data for response
            base_data['master_enable'] = request.json['master_enable']
            base_data['sender_id'] = request.json['sender_id']
            base_data['transport_file'] = sender['transport_file']
            base_data['transport_params'] = request.json['transport_params']
            base_data['transport_params'][0]['connection_authorisation'] = False

            if "activation" in request.json:
                # Activating without staging first
                # Base data for response
                base_data["activation"]["activation_time"] = time.time()
                base_data['activation']['mode'] = request.json['activation']['mode']
                # Update resource data 
                resource_details['active']['activation'] = base_data['activation']
                resource_details['active']['master_enable'] = True
                resource_details['active']['sender_id'] = request.json['sender_id']
                resource_details['active']['transport_file'] = sender['transport_file']
                resource_details['active']['transport_params'] = request.json['transport_params']
                resource_details['active']['transport_params'][0]['connection_authorisation'] = False
                resource_details['active']['transport_params'][0]['connection_uri'] = 'events API on device?'
                resource_details['active']['transport_params'][0]['ext_is_07_rest_api_url'] = 'events API on sources?'
                resource_details['active']['transport_params'][0]['ext_is_07_source_id'] = 'source id?'
                # Set up receiver details to be sent to registry
                request_data = NODE.receiver_base_data
                request_data['description'] = resource_details['description']
                request_data['label'] = resource_details['label']
                request_data['id'] = resource_details['id']
                request_data['device_id'] = resource_details['device_id']
                request_data['subscription'] = {'active': True, 'sender_id': request.json['sender_id']}
                # POST updated receiver to registry
                do_request("POST", NODE.registry_url + 'x-nmos/registration/v1.3/resource', json={"type": "receiver", "data": request_data})
            else:
                # Staging
                # Update resource data but nothing should change in registry
                resource_details['staged']['master_enable'] = request.json['master_enable']
                resource_details['staged']['sender_id'] = request.json['sender_id']
                resource_details['staged']['transport_file'] = sender['transport_file']
                resource_details['staged']['transport_params'] = request.json['transport_params']
                resource_details['staged']['transport_params'][0]['connection_authorisation'] = False
                resource_details['staged']['transport_params'][0]['connection_uri'] = 'events API on device?'
                resource_details['staged']['transport_params'][0]['ext_is_07_rest_api_url'] = 'events API on sources?'
                resource_details['staged']['transport_params'][0]['ext_is_07_source_id'] = 'source id?'

        elif "activation" in request.json:
            # Either patching to activate after staging or deactivating
            if 'mode' in request.json['activation'] and request.json['activation'] ['mode']== 'activate_immediate':
                if resource_details['staged']['master_enable'] == True:
                    # Activating after staging
                    # Base data for response
                    base_data["activation"]["activation_time"] = time.time()
                    base_data['activation']['mode'] = request.json['activation']['mode']
                    base_data['master_enable'] = True
                    base_data['sender_id'] = resource_details['staged']['sender_id']
                    base_data['transport_file'] = resource_details['staged']['transport_file']
                    base_data['transport_params'] = resource_details['staged']['transport_params']
                    base_data['transport_params'][0]['connection_authorisation'] = False
                    # Update resource data to add active info
                    resource_details['active']['master_enable'] = True
                    resource_details['active']["activation"]["activation_time"] = time.time()
                    resource_details['active']["activation"]['mode'] = request.json['activation']['mode']
                    resource_details['active']['sender_id'] = resource_details['staged']['sender_id']
                    resource_details['active']['transport_file'] = resource_details['staged']['transport_file']
                    resource_details['active']['transport_params'] = resource_details['staged']['transport_params']
                    resource_details['active']['transport_params'][0]['connection_authorisation'] = False
                    # Remove staged info
                    resource_details['staged']['master_enable'] = False
                    resource_details['staged']['sender_id'] = None
                    resource_details['staged']['transport_file'] = {'data': None, 'type': None}
                    resource_details['staged']['transport_params'][0]['connection_authorisation'] = False
                    resource_details['staged']['transport_params'][0]['connection_uri'] = None
                    resource_details['staged']['transport_params'][0]['ext_is_07_rest_api_url'] = None
                    resource_details['staged']['transport_params'][0]['ext_is_07_source_id'] = None
                    # Set up receiver details to be sent to registry
                    request_data = NODE.receiver_base_data
                    request_data['description'] = resource_details['description']
                    request_data['label'] = resource_details['label']
                    request_data['id'] = resource_details['id']
                    request_data['device_id'] = resource_details['device_id']
                    request_data['subscription'] = {'active': True, 'sender_id': resource_details['active']['sender_id']}
                    # POST updated receiver to registry
                    do_request("POST", NODE.registry_url + 'x-nmos/registration/v1.3/resource', json={"type": "receiver", "data": request_data})
        
                else:
                    # Deactivating
                    # Data for response
                    base_data["activation"]["activation_time"] = time.time()
                    base_data['activation']['mode'] = request.json['activation']['mode']
                    base_data['master_enable'] = False
                    base_data['sender_id'] = resource_details['active']['sender_id']
                    base_data['transport_file'] = resource_details['active']['transport_file']
                    base_data['transport_params'] = resource_details['active']['transport_params']
                    # Update resource data to reset active details
                    resource_details['active']['master_enable'] = False
                    resource_details['active']["activation"]["activation_time"] = None
                    resource_details['active']["activation"]['mode'] = None
                    resource_details['active']['transport_params'] = resource_details['active']['transport_params']
                    resource_details['active']['sender_id'] = None
                    resource_details['active']['transport_file'] = {'data': None, 'type': None}
                    resource_details['active']['transport_params'][0]['connection_authorisation'] = False
                    resource_details['active']['transport_params'][0]['connection_uri'] = None
                    resource_details['active']['transport_params'][0]['ext_is_07_rest_api_url'] = None
                    resource_details['active']['transport_params'][0]['ext_is_07_source_id'] = None
                    # Set up receiver details to be sent to registry
                    request_data = NODE.receiver_base_data
                    request_data['description'] = resource_details['description']
                    request_data['label'] = resource_details['label']
                    request_data['id'] = resource_details['id']
                    request_data['device_id'] = resource_details['device_id']
                    request_data['subscription'] = {'active': False, 'sender_id': None}
                    # POST updated receiver to registry
                    do_request("POST", NODE.registry_url + 'x-nmos/registration/v1.3/resource', json={"type": "receiver", "data": request_data})

            else:
                print("!!!!!!!!!!!!!! I don't know how we got here")
                print(request.json)
        # Add resource back to list after changes have been made
        resource_list.append(resource_details)
    
    elif request.method == 'GET':
        # Need to fetch json of actual current 'staged' info
            base_data = resource_list[resource_index]['staged']

    return make_response(Response(json.dumps(base_data), mimetype='application/json'))

@NODE_API.route('/x-nmos/connection/<version>/single/<resource>/<resource_id>/active', methods=["GET"], strict_slashes=False)
def active(version, resource, resource_id):
    if resource == 'senders':
        resource_list = NODE.senders
    elif resource == 'receivers':
        resource_list = NODE.receivers

    try: 
        resource_index = [i for i, r in enumerate(resource_list) if r['id'] == resource_id][0]
    except IndexError:
        # Requested a resource that doesn't exist
        abort(404)
    
    base_data = resource_list[resource_index]['active']

    return make_response(Response(json.dumps(base_data), mimetype='application/json'))

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
        resource_index = [i for i, s in enumerate(NODE.senders) if s['id'] == resource_id][0]
    except IndexError:
        # Requested a resource that doesn't exist
        abort(404)
    
    file = NODE.senders[resource_index]['transport_file']
    # return redirect(file, code=307)
    return make_response(Response(json.dumps(file), mimetype='application/json'))
