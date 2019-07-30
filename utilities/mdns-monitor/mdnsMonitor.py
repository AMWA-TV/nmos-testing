#!/usr/bin/python

# Copyright (C) 2019 Advanced Media Workflow Association
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

import time
import os
import queue

from zeroconf_monkey import ServiceBrowser, Zeroconf
from socket import inet_ntoa
from threading import Thread

MONITOR_TYPES = ["_nmos-registration._tcp", "_nmos-register._tcp", "_nmos-query._tcp", "_nmos-system._tcp"]
IP_WHITELIST = ["172.29.80.195", "172.29.80.196"]


class Listener:
    def __init__(self):
        self.services = {}
        self._resolve_queue = queue.Queue()

    def add_service(self, zeroconf, srv_type, name):
        self._resolve_queue.put((srv_type, name, zeroconf))
        resolveThread = Thread(target=self._resolve_service_details)
        resolveThread.daemon = True
        resolveThread.start()

    def _resolve_service_details(self):
        parameters = self._resolve_queue.get()
        srv_type = parameters[0]
        name = parameters[1]
        zeroconf = parameters[2]
        info = zeroconf.get_service_info(srv_type, name)
        self._update_record(srv_type, name, info)
        self._resolve_queue.task_done()

    def _update_record(self, srv_type, name, info):
        try:
            self.services[srv_type][name] = info
        except KeyError:
            self.services[srv_type] = {}
            self.services[srv_type][name] = info

    def remove_service(self, zeroconf, srv_type, name):
        try:
            self.services[srv_type].pop(name, None)
        except KeyError:
            pass

    def print_services(self):
        os.system("clear")
        for srv_type in self.services:
            print("Unexpected services of type '{}'".format(srv_type))
            for name in sorted(self.services[srv_type]):
                 info = self.services[srv_type][name]
                 if info:
                     address = inet_ntoa(info.address)
                     if address not in IP_WHITELIST:
                         self._print_entry(name, info)
                 else:
                     self._print_entry(name)
            print("")

    def _print_entry(self, name, info=None):
        print(" - {}".format(name))
        if info is not None:
            address = inet_ntoa(info.address)
            print("     Address: {}, Port: {}, TXT: {}".format(address, info.port, info.properties))
        else:
            print("     Unresolvable")


zeroconf = Zeroconf()
listener = Listener()

for srv_type in MONITOR_TYPES:
    browser = ServiceBrowser(zeroconf, srv_type + ".local.", listener)

try:
    while True:
        listener.print_services()
        time.sleep(1)
except KeyboardInterrupt:
    pass
finally:
    print("* Shutting down, please wait...")
    zeroconf.close()
