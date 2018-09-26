# Copyright (C) 2018 Riedel Communications GmbH & Co. KG
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

import ramlfications
import os
import json

def ordered(obj):
    if isinstance(obj, dict):
        return sorted((k, ordered(v)) for k, v in obj.items())
    if isinstance(obj, list):
        return sorted(ordered(x) for x in obj)
    else:
        return obj


def compare_json(json1, json2):
    """Compares two json objects for equality"""
    return ordered(json1) == ordered(json2)


class MdnsListener(object):
    def __init__(self):
        self.services = list()

    def add_service(self, zeroconf, type, name):
        info = zeroconf.get_service_info(type, name)
        if info is not None:
            self.services.append(info)

    def get_service_list(self):
        return self.services


class Specification(object):
    def __init__(self, file_path):
        self.data = {}
        api_raml = ramlfications.parse(file_path, "config.ini")
        self.global_schemas = api_raml.schemas[0]
        for resource in api_raml.resources:
            resource_data = {'method': resource.method,
                             'params': resource.uri_params,
                             'body': None,
                             'responses': {}}
            if resource.body is not None:
                for attr in resource.body:
                    if attr.mime_type == "schema":
                        resource_data['body'] = self.deref_schema(os.path.dirname(file_path), schema=attr.raw)
                        break
            for response in resource.responses:
                resource_data["responses"][response.code] = None
                if response.body:
                    for entry in response.body:
                        if isinstance(entry.schema, dict):
                            resource_data["responses"][response.code] = self.deref_schema(os.path.dirname(file_path), schema=entry.schema)
                        elif entry.schema in self.global_schemas:
                            resource_data["responses"][response.code] = self.deref_schema(os.path.dirname(file_path), schema=self.global_schemas[entry.schema])
                        else:
                            resource_data["responses"][response.code] = None
                        break
            self.data[resource.path] = resource_data

    def deref_schema(self, dir, name=None, schema=None):
        def process(obj):
            if isinstance(obj, dict):
                if len(obj) == 1 and "$ref" in obj:
                    return self.deref_schema(dir, name=obj['$ref'])
                return {k: process(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [process(x) for x in obj]
            else:
                return obj

        local = {}
        if name:
            filename = "{}/{}".format(dir, name)
            with open(filename, 'r') as fh:
                local = process(json.load(fh))
            return local
        else:
            return process(schema)

    def get_path(self, path):
        path_parts = path.split('/')
        for resource in self.data:
            resource_parts = resource.split('/')
            for part in path_parts:
                for rpart in resource_parts:
                    if part == rpart:
                        pass
                    elif rpart in resource.uri_params:
                        pass

            path_builder = '/'
            count = 0

            count += 1
            path_builder += part

            if len(path_parts) == count:
                pass

            if resource.startswith(path_builder):
                pass

        # TODO: Exchange {} cases for what's in the path

    def get_reads(self):
        resources = []
        for resource in self.data:
            if self.data[resource]['method'] in ['get', 'head', 'options']:
                resources.append((resource, self.data[resource]))
        return resources

    def get_writes(self):
        resources = []
        for resource in self.data:
            if self.data[resource]['method'] in ['post', 'put', 'patch', 'delete']:
                resources.append((resource, self.data[resource]))
        return resources
