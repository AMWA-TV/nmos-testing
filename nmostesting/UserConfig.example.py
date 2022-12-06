# Copyright (C) 2020 Advanced Media Workflow Association
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

from . import Config as CONFIG

# Copy this file to "UserConfig.py" to change configuration values.

# Example of setting ENABLE_HTTPS, any value from Config.py can be overridden using the same pattern.
CONFIG.ENABLE_HTTPS = False

# Example of overriding specific values in SDP_PREFERENCES.
CONFIG.SDP_PREFERENCES = {
    **CONFIG.SDP_PREFERENCES,
    "channels": 4,
    "exactframerate": "30000/1001"
}
