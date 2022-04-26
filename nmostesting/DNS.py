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

import socket

from dnslib import DNSRecord, RCODE
from dnslib.server import DNSServer
from dnslib.zoneresolver import ZoneResolver
from jinja2 import Template
from threading import Event

from .TestHelper import get_default_ip
from . import Config as CONFIG


class ForwardingZoneResolver(ZoneResolver):
    def __init__(self, zone, glob=False):
        ZoneResolver.__init__(self, zone, glob)
        self.upstream = CONFIG.DNS_UPSTREAM_IP
        self.upstream_port = 53
        self.timeout = None

    def resolve(self, request, handler):
        reply = ZoneResolver.resolve(self, request, handler)

        if reply.header.rcode == RCODE.NXDOMAIN and self.upstream:
            try:
                if handler.protocol == 'udp':
                    proxy_r = request.send(self.upstream, self.upstream_port,
                                           timeout=self.timeout)
                else:
                    proxy_r = request.send(self.upstream, self.upstream_port,
                                           tcp=True, timeout=self.timeout)
                reply = DNSRecord.parse(proxy_r)
            except socket.timeout:
                reply.header.rcode = RCODE.SERVFAIL

        return reply


class WatchingResolver(ForwardingZoneResolver):
    def __init__(self, zone, glob=False):
        ForwardingZoneResolver.__init__(self, zone, glob)
        self.watching = {}
        self.expected_queries = {}

    def wait_for_query(self, record_type, record_names, timeout):
        wait_event = Event()
        if record_type not in self.watching:
            self.watching[record_type] = {}
        for record_name in record_names:
            self.watching[record_type][record_name] = wait_event
        wait_event.wait(timeout)
        for record_name in record_names:
            self.watching[record_type][record_name] = None

    def set_expected_query(self, record_type, record_names):
        if record_type not in self.expected_queries:
            self.expected_queries[record_type] = {}
        for record_name in record_names:
            self.expected_queries[record_type][record_name] = 0

    def is_query_received(self):
        for record_type in self.expected_queries:
            for record_name in self.expected_queries[record_type]:
                if self.expected_queries[record_type][record_name]:
                    return True
        return False

    def resolve(self, request, handler):
        qtype = request.q.qtype
        qname = str(request.q.qname)

        try:
            self.expected_queries[qtype][qname] += 1
        except (KeyError, AttributeError):
            pass

        try:
            self.watching[qtype][qname].set()
        except (KeyError, AttributeError):
            pass
        return ForwardingZoneResolver.resolve(self, request, handler)


class DNS(object):
    def __init__(self):
        self.default_ip = get_default_ip()
        self.resolver = None
        self.server = None
        self.base_zone_data = None
        self.reset()

    def wait_for_query(self, record_type, record_name, timeout):
        self.resolver.wait_for_query(record_type, record_name, timeout)

    def set_expected_query(self, record_type, record_names):
        self.resolver.set_expected_query(record_type, record_names)

    def is_query_received(self):
        return self.resolver.is_query_received()

    def load_zone(self, api_version, api_protocol, api_authorization, zone_name, port_base):
        zone_file = open(zone_name).read()
        template = Template(zone_file)
        zone_data = template.render(ip_address=self.default_ip, api_ver=api_version, api_proto=api_protocol,
                                    api_auth=str(api_authorization).lower(), domain=CONFIG.DNS_DOMAIN,
                                    port_base=port_base)
        self.resolver = WatchingResolver(self.base_zone_data + zone_data)
        self.stop()
        print(" * Loading DNS zone file '{}' with api_ver={}".format(zone_name, api_version))
        self.start()

    def reset(self):
        zone_file = open("test_data/core/dns_base.zone").read()
        template = Template(zone_file)

        extra_services = {}
        if CONFIG.ENABLE_AUTH:
            auth_proto = "https" if CONFIG.ENABLE_HTTPS else "http"
            extra_services["auth"] = {
                "host": CONFIG.AUTH_SERVER_HOSTNAME,
                "ip": CONFIG.AUTH_SERVER_IP,
                "port": CONFIG.AUTH_SERVER_PORT,
                "txt": ["api_ver=v1.0", "api_proto={}".format(auth_proto), "pri=0"]
            }
        if CONFIG.ENABLE_MQTT_BROKER:
            extra_services["mqtt"] = {
                "host": CONFIG.MQTT_BROKER_HOSTNAME,
                "ip": CONFIG.MQTT_BROKER_IP,
                "port": CONFIG.MQTT_BROKER_PORT,
                "txt": ["api_proto=mqtt", "api_auth=false"]
            }

        self.base_zone_data = template.render(ip_address=self.default_ip, domain=CONFIG.DNS_DOMAIN,
                                              extra_services=extra_services)
        self.resolver = WatchingResolver(self.base_zone_data)
        self.stop()
        print(" * Loading DNS zone base file")
        self.start()

    def start(self):
        if not self.server:
            print(" * Starting DNS server on {}:53".format(self.default_ip))
            try:
                self.server = DNSServer(self.resolver, port=53, address=self.default_ip)
                self.server.start_thread()
            except Exception as e:
                print(" * ERROR: Unable to bind to port 53. DNS server could not start: {}".format(e))

    def stop(self):
        if self.server:
            print(" * Stopping DNS server on {}:53".format(self.default_ip))
            self.server.stop()
            self.server = None
