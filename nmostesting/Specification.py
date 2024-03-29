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
import ramlfications

from .Patches import _parse_json
from .TestHelper import load_resolved_schema

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

            # Record if parent resource GET method should provide a "child resources" response
            path_components = resource.path.split("/")
            # only need the parent "child resources" response if the last path segment is a parameter
            if path_components[-1].startswith('{'):
                parent_path = "/".join(path_components[0:-1])
                # if the API doesn't support the parent path, won't be able to determine parameter values
                if parent_path in self.data:
                    for method_def in self.data[parent_path]:
                        # if the parent doesn't support GET, won't be able to determine parameter values
                        if method_def['method'] == 'get':
                            method_def['child_resources'] = True

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
                        type_name = None

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

                    if line.startswith("traits:") or line.startswith("securitySchemes:"):
                        # Remove traits to work around an issue with ramlfications util.py '_remove_duplicates'
                        line = "bugfix:\r\n"

                    if type_name is None:
                        # Assuming we're not in the middle of fixing a RAML 1.0 type def, add the line to the
                        # output RAML
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
        elif "types" in api_raml.raw and api_raml.raw["types"] is not None:
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
                    apis_path = os.path.dirname(file_path)
                    spec_path = os.path.dirname(apis_path)
                    body_schema = load_resolved_schema(spec_path, schema_obj=attr.raw)
                    break
        return body_schema

    def _extract_response_schema(self, response, file_path):
        """Find schemas defined for a given API response and return the schema object"""
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

        apis_path = os.path.dirname(file_path)
        spec_path = os.path.dirname(apis_path)
        if isinstance(schema_loc, dict):
            return load_resolved_schema(spec_path, schema_obj=schema_loc)
        elif schema_loc in self.global_schemas and self.global_schemas[schema_loc] is not None:
            return load_resolved_schema(spec_path, schema_obj=self.global_schemas[schema_loc])
        else:
            return None

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

    def get_methods(self, path):
        """Get all methods which exist for a given path if available"""
        methods = []
        if path in self.data:
            for response in self.data[path]:
                # Don't return methods which are specified to return Method Not Allowed
                if 405 not in response['responses']:
                    methods.append(response['method'].upper())
        return methods
