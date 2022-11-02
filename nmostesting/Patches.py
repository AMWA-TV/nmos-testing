# Copyright (C) 2018 British Broadcasting Corporation and
# Copyright (C) 2015 Spotify AB
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
import jsonref


# Work around ramlfications Windows compatibility issues and loader caching. The following method is modified from
# the original in https://github.com/spotify/ramlfications/blob/master/ramlfications/loader.py
# Copyright (c) 2015 Spotify AB
def _parse_json(self, jsonfile, base_path):
    """
    Parses JSON as well as resolves any `$ref`s, including references to
    local files and remote (HTTP/S) files.
    """
    base_path = os.path.abspath(base_path)
    if not base_path.endswith("/"):
        base_path = base_path + "/"
    if os.name == "nt":
        base_uri_path = "file:///" + base_path.replace('\\', '/')
    else:
        base_uri_path = "file://" + base_path

    # $id sets the Base URI to be different from the Retrieval URI
    # but we want to load schema files from the cache where possible
    # see https://json-schema.org/understanding-json-schema/structuring.html#base-uri
    def loader(uri):
        # IS-07 is currently the only spec that uses $id in its schemas
        is07_base_uri = "https://www.amwa.tv/event_and_tally/"
        if uri.startswith(is07_base_uri):
            # rather than recreate the cache path from config, cheat by just using the original base URI
            uri = base_uri_path + uri[len(is07_base_uri):]

        return jsonref.jsonloader(uri)

    with open(jsonfile, "r") as f:
        schema = jsonref.load(f, base_uri=base_uri_path, jsonschema=True, lazy_load=False,
                              loader=loader)
    return schema
