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

# Enable or disable DNS-SD advertisements. Browsing is always permitted.
# The IS-04 Node tests create a mock registry on the network unless the `ENABLE_DNS_SD` parameter is set to `False`.
# If set to `False`, make sure to update the Query API hostname/IP and port via `QUERY_API_HOST` and `QUERY_API_PORT`.
ENABLE_DNS_SD = True

# Set the DNS-SD mode to either 'multicast' or 'unicast'
DNS_SD_MODE = 'multicast'

# Number of seconds to wait after a DNS-SD advert is created for a client to notice and perform an action
DNS_SD_ADVERT_TIMEOUT = 5

# Number of seconds expected between heartbeats
HEARTBEAT_INTERVAL = 5

# Number of seconds to wait for the garbage collection
GARBAGE_COLLECTION_TIMEOUT = 12

# Number of seconds to wait for messages to appear via a WebSocket subscription
WS_MESSAGE_TIMEOUT = 1

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
# Example: DEFAULT_INTERFACE = 'ens1f0'
DEFAULT_INTERFACE = None

# Which certificate authority to trust when performing requests in HTTPS mode.
# Defaults to the CA contained within this test suite
CERT_TRUST_ROOT_CA = "test_data/BCP00301/ca/certs/ca.cert.pem"

# Certificate chains and the corresponding private keys
CERTS_MOCKS = [
    "test_data/BCP00301/ca/intermediate/certs/ecdsa.mocks.testsuite.nmos.tv.cert.chain.pem",
    "test_data/BCP00301/ca/intermediate/certs/rsa.mocks.testsuite.nmos.tv.cert.chain.pem"
]
KEYS_MOCKS = [
    "test_data/BCP00301/ca/intermediate/private/ecdsa.mocks.testsuite.nmos.tv.key.pem",
    "test_data/BCP00301/ca/intermediate/private/rsa.mocks.testsuite.nmos.tv.key.pem"
]

# Definition of each API specification and its versions.
SPECIFICATIONS = {
    "is-04": {
        "repo": "nmos-discovery-registration",
        "versions": ["v1.0", "v1.1", "v1.2", "v1.3"],
        "default_version": "v1.2",
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
        "default_version": "v1.0",
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
    "bcp-003-01": {
        "repo": None,
        "versions": ["v1.0"],
        "default_version": "v1.0",
        "apis": {
            "secure": {}
        }
    },
    "bcp-003-02": {
        "repo": "nmos-api-security",
        "versions": ["v1.0"],
        "default_version": "v1.0",
        "apis": {
            "auth": {
                "name": "Authorization API",
                "raml": "AuthorizationAPI.raml"
            }
        }
    }
}
