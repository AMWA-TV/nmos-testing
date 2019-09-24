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

from threading import Thread
from queue import Queue


class MdnsListener(object):
    def __init__(self, zeroconf):
        self.zeroconf = zeroconf
        self.services = list()
        self.resolve_queue = Queue()

    def add_service(self, zeroconf, srv_type, name):
        self.resolve_queue.put((srv_type, name))
        t = Thread(target=self.worker)
        t.daemon = True
        t.start()

    def remove_service(self, zeroconf, srv_type, name):
        pass

    def get_service_list(self):
        self.resolve_queue.join()
        return self.services

    def worker(self):
        item = self.resolve_queue.get()
        info = self.zeroconf.get_service_info(item[0], item[1])
        if info is not None:
            self.services.append(info)
        self.resolve_queue.task_done()
