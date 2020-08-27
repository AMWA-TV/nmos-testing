# Copyright 2018 British Broadcasting Corporation
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


# NMOS Testing Configuration File
# -------------------------------
# Please consult the documentation for instructions on how to adjust these values for common testing setups including
# unicast DNS-SD and HTTPS testing.


# Enable or disable DNS-SD advertisements. Browsing is always permitted.
# The IS-04 Node tests create a mock registry on the network unless the `ENABLE_DNS_SD` parameter is set to `False`.
# If set to `False`, make sure to update the Query API hostname/IP and port via `QUERY_API_HOST` and `QUERY_API_PORT`.
ENABLE_DNS_SD = True

# Set the DNS-SD mode to either 'multicast' or 'unicast'
DNS_SD_MODE = 'multicast'

# Number of seconds to wait after a DNS-SD advert is created for a client to notice and perform an action
DNS_SD_ADVERT_TIMEOUT = 30

# Number of seconds to wait after browsing for a DNS-SD advert before checking the results
DNS_SD_BROWSE_TIMEOUT = 2

# Number of seconds expected between heartbeats for an IS-04 Node
# Note: Currently this is only used for testing IS-04 Nodes. Registry behaviour is expected to match the defaults.
HEARTBEAT_INTERVAL = 5

# Number of seconds to wait before garbage collection for an IS-04 registry
# Note: Currently this is only used for testing IS-04 registries. Node behaviour is expected to match the defaults.
GARBAGE_COLLECTION_TIMEOUT = 12

# Number of seconds to wait for messages to appear via a WebSocket subscription
WS_MESSAGE_TIMEOUT = 2

# Number of seconds to wait for messages to appear via a MQTT subscription
MQTT_MESSAGE_TIMEOUT = 2

# Number of seconds to wait after performing an API action for the results to be fully visible via IS-04
API_PROCESSING_TIMEOUT = 1

# Set a Query API hostname/IP and port for use when operating without DNS-SD
QUERY_API_HOST = "127.0.0.1"
QUERY_API_PORT = 80

# Path to store the specification file cache in. Relative to the base of the testing repository.
CACHE_PATH = 'cache'

# Timeout for any HTTP requests
HTTP_TIMEOUT = 1

# Restrict the maximum number of resources that time consuming tests run against.
# 0 = unlimited for a really thorough test!
MAX_TEST_ITERATIONS = 0

# Test using HTTPS rather than HTTP as per AMWA BCP-003-01
ENABLE_HTTPS = False

# Prefer a specific network interface when making mDNS announcements and similar.
# Example: BIND_INTERFACE = 'ens1f0'
BIND_INTERFACE = None

# Which certificate authority to trust when performing requests in HTTPS mode.
# Defaults to the CA contained within this testing tool
CERT_TRUST_ROOT_CA = "test_data/BCP00301/ca/certs/ca.cert.pem"

# Certificate chains and the corresponding private keys
# Used by the testing tool's mock Node, Registry and System API
CERTS_MOCKS = [
    "test_data/BCP00301/ca/intermediate/certs/ecdsa.mocks.testsuite.nmos.tv.cert.chain.pem",
    "test_data/BCP00301/ca/intermediate/certs/rsa.mocks.testsuite.nmos.tv.cert.chain.pem"
]
KEYS_MOCKS = [
    "test_data/BCP00301/ca/intermediate/private/ecdsa.mocks.testsuite.nmos.tv.key.pem",
    "test_data/BCP00301/ca/intermediate/private/rsa.mocks.testsuite.nmos.tv.key.pem"
]

# Test using authorization as per AMWA IS-10 and BCP-003-02
ENABLE_AUTH = False

# When using authorization, these variables must contain valid JSON Web Tokens which are suitable for use in the current
# environment. Both tokens must include claims (such as 'x-nmos-node') which provide full read/write permission for
# every API which may be tested. They must each contain different client identifiers (client_id or azp) in order to
# enable testing of BCP-003-02.
AUTH_TOKEN_PUBKEY = "test_data/IS1001/auth_token_pubkey.key"
AUTH_TOKEN_PRIMARY = "eyJhbGciOiJSUzUxMiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ0ZXN0c3VpdGVAbm1vcy50diIsImlhdCI6MTUxNjIzOTAyMiwiaXNzIjoiaHR0cHM6Ly90ZXN0c3VpdGUubm1vcy50diIsImV4cCI6MjUyNDYwODAwMCwiY2xpZW50X2lkIjoiMjJlMWYwZDQtZTI3ZS00YjgyLTljMmYtZDc0NTM4Yjc3N2I2IiwiYXVkIjpbImh0dHBzOi8vKi50ZXN0c3VpdGUubm1vcy50diJdLCJzY29wZSI6Im5vZGUgcmVnaXN0cmF0aW9uIHF1ZXJ5IGNvbm5lY3Rpb24gbmV0Y3RybCBldmVudHMgY2hhbm5lbG1hcHBpbmcgc3lzdGVtIiwieC1ubW9zLW5vZGUiOnsicmVhZCI6WyIqIl0sIndyaXRlIjpbIioiXX0sIngtbm1vcy1yZWdpc3RyYXRpb24iOnsicmVhZCI6WyIqIl0sIndyaXRlIjpbIioiXX0sIngtbm1vcy1xdWVyeSI6eyJyZWFkIjpbIioiXSwid3JpdGUiOlsiKiJdfSwieC1ubW9zLWNvbm5lY3Rpb24iOnsicmVhZCI6WyIqIl0sIndyaXRlIjpbIioiXX0sIngtbm1vcy1uZXRjdHJsIjp7InJlYWQiOlsiKiJdLCJ3cml0ZSI6WyIqIl19LCJ4LW5tb3MtZXZlbnRzIjp7InJlYWQiOlsiKiJdLCJ3cml0ZSI6WyIqIl19LCJ4LW5tb3MtY2hhbm5lbG1hcHBpbmciOnsicmVhZCI6WyIqIl0sIndyaXRlIjpbIioiXX0sIngtbm1vcy1zeXN0ZW0iOnsicmVhZCI6WyIqIl0sIndyaXRlIjpbIioiXX19.mLxnlRAI7lI1NFWUoiU9bZ7SCJtSFn98w9GS88pDL4l0a74EIzdJcYjJrr1AqN3AZgpNDGO4XQuCuCS965y_nsCm8sCeeAo7SCkW_96PQQLADAy1jb4FDTBCgqsn6dVZ6XiH0H32vziY4jawF7OI4uIo4r5ZWYsqGHW17AlCuDHcdvNA9B8OtkaOqC-Na8raakWwVJi1J6AtWUxPIwIxzaDOltE5ni5U8rt47nYP22gS6ERpzi0MVz6jAufdtQ4dcWNq70jgzaXsoPGFzvnPb_mP1ET9U0hLs6FP5Fy-IFxERn0Juj4py-e7LivrsVzAs74tOakGJRYHx83OQ0bXPA"  # noqa E501
AUTH_TOKEN_SECONDARY = "eyJhbGciOiJSUzUxMiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ0ZXN0c3VpdGVAbm1vcy50diIsImlhdCI6MTUxNjIzOTAyMiwiaXNzIjoiaHR0cHM6Ly90ZXN0c3VpdGUubm1vcy50diIsImV4cCI6MjUyNDYwODAwMCwiY2xpZW50X2lkIjoiYWIyOTMzMjctNmZhMC00MmUwLWFmNGMtZTNiZWU5ODY1MDk0IiwiYXVkIjpbImh0dHBzOi8vKi50ZXN0c3VpdGUubm1vcy50diJdLCJzY29wZSI6Im5vZGUgcmVnaXN0cmF0aW9uIHF1ZXJ5IGNvbm5lY3Rpb24gbmV0Y3RybCBldmVudHMgY2hhbm5lbG1hcHBpbmcgc3lzdGVtIiwieC1ubW9zLW5vZGUiOnsicmVhZCI6WyIqIl0sIndyaXRlIjpbIioiXX0sIngtbm1vcy1yZWdpc3RyYXRpb24iOnsicmVhZCI6WyIqIl0sIndyaXRlIjpbIioiXX0sIngtbm1vcy1xdWVyeSI6eyJyZWFkIjpbIioiXSwid3JpdGUiOlsiKiJdfSwieC1ubW9zLWNvbm5lY3Rpb24iOnsicmVhZCI6WyIqIl0sIndyaXRlIjpbIioiXX0sIngtbm1vcy1uZXRjdHJsIjp7InJlYWQiOlsiKiJdLCJ3cml0ZSI6WyIqIl19LCJ4LW5tb3MtZXZlbnRzIjp7InJlYWQiOlsiKiJdLCJ3cml0ZSI6WyIqIl19LCJ4LW5tb3MtY2hhbm5lbG1hcHBpbmciOnsicmVhZCI6WyIqIl0sIndyaXRlIjpbIioiXX0sIngtbm1vcy1zeXN0ZW0iOnsicmVhZCI6WyIqIl0sIndyaXRlIjpbIioiXX19.FY6RksUZSvGFX7Rf-zNJGCdJRRFNXmyfHezmeV2Ze0xVhgkbQM6cyAck3PvMaD3gbWefmiAm_KdWer8WC_-RnX3N9kihHlpLA3cW8rpbVP0Do1ojT-dQuikUKLl5Qo3Agiidgi1-UWwomGWv5Bor4v95pRP2pbq8wy16GplHD-4ccptVgRr7bq5hX-6box6ZH-DazbhOzZsLPF29wBvOWSjH14eB3MOMgq4BQ2qYvs20zHaeibXqoF9bbJsYHCtQpGX9QsWZiw-sGFMUF456GkidPPIGMESgFcySGTEWZVPLOOFBg-22cNzWaxP0B0XAFvPPyLdSfXHWBmyrki2fwQ"  # noqa E501

# Domain name to use for the local DNS server and mock Node
# This must match the domain name used for certificates in HTTPS mode
DNS_DOMAIN = "testsuite.nmos.tv"

# The testing tool uses multiple ports to run mock services. This sets the lowest of these, which also runs the GUI
# Note that changing this from the default of 5000 also requires changes to supporting files such as
# test_data/BCP00301/ca/intermediate/openssl.cnf and any generated certificates.
# The mock DNS server port cannot be modified from the default of 53.
PORT_BASE = 5000

# A valid unicast/multicast IP address on the local network which media streams can be sent to. This will be passed
# into Sender configuration when testing IS-05.
UNICAST_STREAM_TARGET = "192.0.2.1"
MULTICAST_STREAM_TARGET = "233.252.2.1"

# Perform a GET against the submitted API before carrying out any tests to avoid wasting time if it doesn't exist
PREVALIDATE_API = True

# SDP media parameters which can be modified for devices which do not support the defaults
# SDP testing is not concerned with support for specific media parameters, but must include them in the file
SDP_PREFERENCES = {
    "audio_channels": 2,
    "audio_sample_rate": 48000,
    "video_width": 1920,
    "video_height": 1080,
    "video_interlace": True,
    "video_exactframerate": "25"
}

# Test with an MQTT Broker as per AMWA IS-07
ENABLE_MQTT_BROKER = True

# Where the MQTT Broker is located on the network. Required when 'ENABLE_MQTT_BROKER' is True
MQTT_BROKER_HOSTNAME = "mqtt"
MQTT_BROKER_IP = "127.0.0.1"
MQTT_BROKER_PORT = 1883

# Username and password for connecting to the MQTT Broker
MQTT_USERNAME = None
MQTT_PASSWORD = None

# Definition of each API specification and its versions.
SPECIFICATIONS = {
    "is-04": {
        "repo": "nmos-discovery-registration",
        "versions": ["v1.0", "v1.1", "v1.2", "v1.3"],
        "default_version": "v1.3",
        "apis": {
            "node": {
                "name": "Node API",
                "raml": "NodeAPI.raml"
            },
            "query": {
                "name": "Query API",
                "raml": "QueryAPI.raml"
            },
            "registration": {
                "name": "Registration API",
                "raml": "RegistrationAPI.raml"
            }
        }
    },
    "is-05": {
        "repo": "nmos-device-connection-management",
        "versions": ["v1.0", "v1.1"],
        "default_version": "v1.1",
        "apis": {
            "connection": {
                "name": "Connection API",
                "raml": "ConnectionAPI.raml"
            }
        }
    },
    "is-06": {
        "repo": "nmos-network-control",
        "versions": ["v1.0"],
        "default_version": "v1.0",
        "apis": {
            "netctrl": {
                "name": "Network API",
                "raml": "NetworkControlAPI.raml"
            }
        }
    },
    "is-07": {
        "repo": "nmos-event-tally",
        "versions": ["v1.0"],
        "default_version": "v1.0",
        "apis": {
            "events": {
                "name": "Events API",
                "raml": "EventsAPI.raml"
            }
        }
    },
    "is-08": {
        "repo": "nmos-audio-channel-mapping",
        "versions": ["v1.0"],
        "default_version": "v1.0",
        "apis": {
            "channelmapping": {
                "name": "Channel Mapping API",
                "raml": "ChannelMappingAPI.raml"
            }
        }
    },
    "is-09": {
        "repo": "nmos-system",
        "versions": ["v1.0"],
        "default_version": "v1.0",
        "apis": {
            "system": {
                "name": "System API",
                "raml": "SystemAPI.raml"
            }
        }
    },
    "is-10": {
        "repo": "nmos-authorization",
        "versions": ["v1.0"],
        "default_version": "v1.0",
        "apis": {
            "auth": {
                "name": "Authorization API",
                "raml": "AuthorizationAPI.raml"
            }
        }
    },
    "bcp-003-01": {
        "repo": "nmos-secure-communication",
        "versions": ["v1.0"],
        "default_version": "v1.0",
        "apis": {}
    }
}

try:
    from . import UserConfig  # noqa: F401
except ImportError:
    pass
