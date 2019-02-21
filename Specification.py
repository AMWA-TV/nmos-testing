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

from Patches import _parse_json


try:
    # Patch ramlfications for Windows support
    ramlfications.loader.RAMLLoader._parse_json = _parse_json
except AttributeError:
    pass


class Specification(object):
    def __init__(self, file_path):
        self.data = {}
        self.global_schemas = {}

        self._fix_schemas(file_path)
        api_raml = ramlfications.parse(file_path, "config.ini")

        self._extract_global_schemas(api_raml)

        # Iterate over each path+method defined in the API
        for resource in api_raml.resources:
            resource_data = {'method': resource.method,
                             'params': resource.uri_params,
                             'body': self._extract_body_schema(resource, file_path),
                             'responses': {}}

            # Add a list for the resource path if we don't have one yet
            if resource.path not in self.data:
                self.data[resource.path] = list()

            # Extract the schemas for the different response codes
            for response in resource.responses:
                # Note: Must check we don't overwrite an existing schema here by checking if it is None or not
                if response.code not in resource_data["responses"] or resource_data["responses"][response.code] is None:
                    resource_data["responses"][response.code] = self._extract_response_schema(response, file_path)

            # Register the collected data in the Specification object
            self.data[resource.path].append(resource_data)

    def _fix_schemas(self, file_path):
        """Fixes RAML files to match ramlfications expectations (bugs)"""
        lines = []
        in_schemas = False
        type_name = None
        try:
            with open(file_path) as raml:
                # Read in a single line of RAML
                line = raml.readline()
                while line:
                    if in_schemas and not line.startswith(" "):
                        # Detect that we've reached the first line after the schemas/types section
                        in_schemas = False

                    if in_schemas and "!include" not in line:
                        # This is a correct RAML 1.0 type definition
                        type_name = line
                    elif in_schemas and type_name is not None:
                        # Make the RAML 1.0 type definition look more like RAML 0.8 to aid parsing
                        line = "  - " + type_name.strip() + " " + line.replace("type:", "").lstrip()
                        type_name = None
                    elif in_schemas and "- " not in line:
                        # Add a leading dash to type/schema definitions to ensure they can be read by ramlfications
                        line = "  - " + line.lstrip()

                    if line.startswith("schemas:") or line.startswith("types:"):
                        # We've hit the global schema/type definition section
                        in_schemas = True

                    if line.startswith("traits:"):
                        # Remove traits to work around an issue with ramlfications util.py '_remove_duplicates'
                        line = "bugfix:\r\n"

                    if type_name is None:
                        # Assuming we're not in the middle of fixing a RAML 1.0 type def, add the line to the output RAML
                        lines.append(line)

                    # Read the next line of the RAML file
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

    def _extract_body_schema(self, resource, file_path):
        """Locate the schema for the request body if one exists"""
        body_schema = None
        if resource.body is not None:
            for attr in resource.body:
                if attr.mime_type == "schema":
                    body_schema = self._deref_schema(os.path.dirname(file_path), schema=attr.raw)
                    break
        return body_schema

    def _extract_response_schema(self, response, file_path):
        """Find schemas defined for a given API response and return the file path or global schema name"""
        schema_loc = None
        if not response.body:
            # Handle parsing errors in ramlfications manually, notably for schemas in RAML 1.0
            try:
                schema_loc = response.raw[response.code]["body"]["type"]
            except (KeyError, TypeError):
                pass
        else:
            for entry in response.body:
                schema_loc = entry.schema
                if not schema_loc:
                    if "type" in entry.raw:
                        schema_loc = entry.raw["type"]

        if isinstance(schema_loc, dict):
            return self._deref_schema(os.path.dirname(file_path), schema=schema_loc)
        elif schema_loc in self.global_schemas:
            return self._deref_schema(os.path.dirname(file_path), schema=self.global_schemas[schema_loc])
        else:
            return None

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
