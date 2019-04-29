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

from flask import Blueprint, make_response, abort
from Config import ENABLE_HTTPS
from TestHelper import get_default_ip


class Node(object):
    def __init__(self):
        pass

    def get_sender(self, stream_type="video"):
        protocol = "http"
        if ENABLE_HTTPS:
            protocol = "https"
        # TODO: Provide the means to downgrade this to a <v1.2 JSON representation
        sender = {
            "id": str(uuid.uuid4()),
            "label": "Dummy Sender",
            "description": "Dummy Sender",
            "version": "50:50",
            "caps": {},
            "tags": {},
            "manifest_href": "{}://{}:5000/{}.sdp".format(protocol, get_default_ip(), stream_type),
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


NODE = Node()
NODE_API = Blueprint('node_api', __name__)


@NODE_API.route('/<stream_type>.sdp', methods=["GET"])
def node_video_sdp(stream_type):
    response = None
    if stream_type == "video":
        with open("test_data/IS0401/video.sdp") as f:
            response = make_response(f.read())
    elif stream_type == "audio":
        with open("test_data/IS0401/audio.sdp") as f:
            response = make_response(f.read())
    elif stream_type == "data":
        with open("test_data/IS0401/data.sdp") as f:
            response = make_response(f.read())
    elif stream_type == "mux":
        with open("test_data/IS0401/mux.sdp") as f:
            response = make_response(f.read())
    else:
        abort(404)

    response.headers["Content-Type"] = "application/sdp"
    return response
