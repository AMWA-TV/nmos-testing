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
from random import randint
from jinja2 import Template
from .. import Config as CONFIG
from ..TestHelper import get_default_ip


class Node(object):
    def __init__(self, port_increment):
        self.port = CONFIG.PORT_BASE + 200 + port_increment

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
