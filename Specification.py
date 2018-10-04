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

import os
import json
import ramlfications

class Specification(object):
    def __init__(self, file_path):
        self.data = {}
        self.global_schemas = {}

        self._fix_schemas(file_path)
        api_raml = ramlfications.parse(file_path, "config.ini")

        self._extract_global_schemas(api_raml)

        for resource in api_raml.resources:
            resource_data = {'method': resource.method,
                             'params': resource.uri_params,
                             'body': None,
                             'responses': {}}
            if resource.body is not None:
                for attr in resource.body:
                    if attr.mime_type == "schema":
                        resource_data['body'] = self._deref_schema(os.path.dirname(file_path), schema=attr.raw)
                        break
            for response in resource.responses:
                if response.code not in resource_data["responses"]:
                    resource_data["responses"][response.code] = None

                schema_loc = self._extract_response_schema(response)

                if isinstance(schema_loc, dict):
                    resource_data["responses"][response.code] = self._deref_schema(
                                                                     os.path.dirname(file_path),
                                                                     schema=schema_loc)
                elif schema_loc in self.global_schemas:
                    resource_data["responses"][response.code] = self._deref_schema(
                                                                     os.path.dirname(file_path),
                                                                     schema=self.global_schemas[schema_loc])

            if resource.path not in self.data:
                self.data[resource.path] = [resource_data]
            else:
                self.data[resource.path].append(resource_data)

    def _fix_schemas(self, file_path):
        """Fixes RAML files to match ramlfications expectations (bugs)"""
        lines = []
        in_schemas = False
        try:
            with open(file_path) as raml:
                line = raml.readline()
                while line:
                    if in_schemas and not line.startswith(" "):
                        in_schemas = False
                    if in_schemas and "- " not in line:
                        line = "  - " + line.lstrip()
                    if line.startswith("schemas:") or line.startswith("types:"):
                        in_schemas = True
                    lines.append(line)
                    line = raml.readline()
            with open(file_path, "w") as raml:
                raml.writelines("".join(lines))
        except IOError as e:
            print("Error modifying RAML. Some schemas may not be loaded: {}".format(e))

    def _extract_global_schemas(self, api_raml):
        """Find schemas defined at the top of the RAML file and store them in global_schemas"""
        if api_raml.schemas:
            # Standard ramlfications method for finding schemas
            for schema in api_raml.schemas:
                keys = list(schema.keys())
                self.global_schemas[keys[0]] = schema[keys[0]]
        elif "types" in api_raml.raw:
            # Handle RAML 1.0 parsing manually as ramlfications doesn't support it
            for schema in api_raml.raw["types"]:
                keys = list(schema.keys())
                self.global_schemas[keys[0]] = schema[keys[0]]

    def _extract_response_schema(self, response):
        """Find schemas defined for a given API response and return the file path or global schema name"""
        schema_loc = None
        if not response.body:
            # Handle parsing errors in ramlfications manually, notably for schemas in RAML 1.0
            if response.code in response.raw and response.raw[response.code] is not None:
                if "body" in response.raw[response.code]:
                    if "type" in response.raw[response.code]["body"]:
                        schema_loc = response.raw[response.code]["body"]["type"]
        else:
            for entry in response.body:
                schema_loc = entry.schema
                if not schema_loc:
                    if "type" in entry.raw:
                        schema_loc = entry.raw["type"]
        return schema_loc

    def _deref_schema(self, dir, name=None, schema=None):
        """Resolve $ref cases to the correct files in schema JSON"""
        # TODO: Is the python jsonschema RefResolver capable of doing this on its own?
        def process(obj):
            if isinstance(obj, dict):
                if len(obj) == 1 and "$ref" in obj:
                    return self._deref_schema(dir, name=obj['$ref'])
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

    def get_schema(self, method, path, response_code):
        """Get the response schema for a given method, path and response code if available"""
        if path in self.data:
            for response in self.data[path]:
                if response["method"].upper() == method.upper():
                    if response["responses"][response_code]:
                        return response["responses"][response_code]
        return None

    def get_reads(self):
        """Get all API resources which support read based HTTP methods"""
        resources = []
        for resource in self.data:
            for method_def in self.data[resource]:
                if method_def['method'] in ['get', 'head', 'options']:
                    resources.append((resource, method_def))
        resources = sorted(resources, key=lambda x: x[0])
        return resources

    def get_writes(self):
        """Get all API resources which support write based HTTP methods"""
        resources = []
        for resource in self.data:
            for method_def in self.data[resource]:
                if method_def['method'] in ['post', 'put', 'patch', 'delete']:
                    resources.append((resource, method_def))
        resources = sorted(resources, key=lambda x: x[0])
        return resources
