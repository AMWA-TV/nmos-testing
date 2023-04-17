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

import sys

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

# Provide an upstream DNS server for requests not handled by the mock DNS server, when in 'unicast' DNS-SD mode
# For example, '127.0.0.53'.
DNS_UPSTREAM_IP = None

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

# Number of seconds to wait before timing out Controller test. Set to 0 to disable timeout mechanism
CONTROLLER_TESTING_TIMEOUT = 600

# Set a Query API hostname/IP and port for use when operating without DNS-SD
QUERY_API_HOST = "127.0.0.1"
QUERY_API_PORT = 80

# Set a port for the Testing Façade for use with the Controller Testing suites
TESTING_FACADE_PORT = 5001

# Path to store the specification file cache in. Relative to the base of the testing repository.
CACHE_PATH = 'cache'

# Timeout for any HTTP requests
HTTP_TIMEOUT = 1

# Restrict the maximum number of resources or test points that time-consuming tests run against.
# 0 = unlimited (all available resources or test points) for a really thorough test!
MAX_TEST_ITERATIONS = 0

# Test using HTTPS rather than HTTP as per AMWA BCP-003-01
ENABLE_HTTPS = False

# Prefer a specific network interface when making mDNS announcements and similar.
# Example: BIND_INTERFACE = 'ens1f0'
BIND_INTERFACE = None

# Which certificate authority to trust when performing requests in HTTPS mode.
# Defaults to the CA contained within this testing tool
CERT_TRUST_ROOT_CA = "test_data/BCP00301/ca/certs/ca.cert.pem"

# certificate authority private key
# Used by the testing tool's mock Auth to generate certificate
KEY_TRUST_ROOT_CA = "test_data/BCP00301/ca/private/ca.key.pem"

# Certificate chains and the corresponding private keys
# Used by the testing tool's mock Node, Registry, System and Authorization API
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

# The following token is set by the application at runtime and should be left as 'None'
AUTH_TOKEN = None

# When testing private_key_jwt OAuth client, mock Auth server uses the jwks_uri to locate the client
# JSON Web Key Set (JWKS) endpoint for the client JWKS to validate the client JWT (client_assertion)
# when fetching the bearer token
# This is used by the /token endpoint and must be set up before test
JWKS_URI = None

# When testing Authorization Code Grant OAuth client, mock Auth server redirects the user-agent back to the client
# with the authorization code. This is used by the /authorize endpoint, if no redirect_uri provided by the client
REDIRECT_URI = None

# The scope of the access request, this is used by the /token endpoint, if no scope provided by the client
# Supported scopes are "connection", "node", "query", "registration", "events", "channelmapping"
# Scope is space-separated list of scope names, e.g. "connection node events"
SCOPE = None

# Domain name to use for the local DNS server and mock Node
# This must match the domain name used for certificates in HTTPS mode
DNS_DOMAIN = "testsuite.nmos.tv"

# The testing tool uses multiple ports to run mock services. This sets the lowest of these, which also runs the GUI
# Note that changing this from the default of 5000 also requires changes to supporting files such as
# test_data/BCP00301/ca/intermediate/openssl.cnf and any generated certificates.
# The mock DNS server port cannot be modified from the default of 53.
PORT_BASE = 5000

# As part of the Controller tests the Mock Registry will create Subscription WebSockets on subscription requests
# This will create up to 6 WebSocket servers starting at WEBSOCKET_PORT_BASE up to WEBSOCKET_PORT_BASE + 5
WEBSOCKET_PORT_BASE = 6000

# Set a RANDOM_SEED to an integer value to make testing deterministic and repeatable.
RANDOM_SEED = None

# A valid unicast/multicast IP address on the local network which media streams can be sent to. This will be passed
# into Sender configuration when testing IS-05.
# The default values are from the IANA-registered TEST-NET-1 and MCAST-TEST-NET ranges. To avoid unintended network
# traffic, override these with values appropriate for your network or set up a black hole route for these addresses.
UNICAST_STREAM_TARGET = "192.0.2.1"
MULTICAST_STREAM_TARGET = "233.252.0.1"

# Perform a GET against the submitted API before carrying out any tests to avoid wasting time if it doesn't exist
PREVALIDATE_API = True

# SDP media parameters which can be modified for devices which do not support the defaults
# SDP testing is not concerned with support for specific media parameters, but must include them in the file
SDP_PREFERENCES = {
    # audio/L16, audio/L24, audio/L32
    "channels": 2,
    "sample_rate": 48000,
    "packet_time": 1,
    "max_packet_time": 1,
    # video/raw, etc.
    "width": 1920,
    "height": 1080,
    "interlace": True,
    "exactframerate": "25",
    "depth": 10,
    "sampling": "YCbCr-4:2:2",
    "colorimetry": "BT709",
    "RANGE": None,
    "TCS": "SDR",
    "TP": "2110TPW",
    # video/jxsv
    "profile": "High444.12",
    "level": "2k-1",
    "sublevel": "Sublev3bpp",
    "bit_rate": 109000
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

# Bash shell to use for running testssl.sh
TEST_SSL_BASH = "bash"

# Definition of each API specification and its versions.
SPECIFICATIONS = {
    "is-04": {
        "repo": "is-04",
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
        "repo": "is-05",
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
        "repo": "is-06",
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
        "repo": "is-07",
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
        "repo": "is-08",
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
        "repo": "is-09",
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
        "repo": "is-10",
        "versions": ["v1.0"],
        "default_version": "v1.0",
        "apis": {
            "auth": {
                "name": "Authorization API",
                "raml": "AuthorizationAPI.raml"
            }
        }
    },
    "bcp-002-01": {
        "repo": "bcp-002-01",
        "versions": ["v1.0"],
        "default_version": "v1.0",
        "apis": {
            "grouphint": {
                "name": "Natural Grouping"
            }
        }
    },
    "bcp-002-02": {
        "repo": "bcp-002-02",
        "versions": ["v1.0"],
        "default_version": "v1.0",
        "apis": {
            "asset": {
                "name": "Asset Distinguishing Information"
            }
        }
    },
    "bcp-003-01": {
        "repo": "bcp-003-01",
        "versions": ["v1.0"],
        "default_version": "v1.0",
        "apis": {}
    },
    "bcp-004-01": {
        "repo": "bcp-004-01",
        "versions": ["v1.0"],
        "default_version": "v1.0",
        "apis": {
            "receiver-caps": {
                "name": "Receiver Capabilities"
            }
        }
    },
    "nmos-parameter-registers": {
        "repo": "nmos-parameter-registers",
        "versions": ["main"],
        "default_version": "main",
        "apis": {
            "caps-register": {
                "name": "Capabilities Register"
            },
            "flow-register": {
                "name": "Flow Attributes Register"
            },
            "sender-register": {
                "name": "Sender Attributes Register"
            }
        }
    },
    "controller-tests": {
        "repo": None,
        "versions": ["v1.0"],
        "default_version": "v1.0",
        "apis": {
            "testquestion": {
                "name": "Testing Façade"
            }
        }
    }
}

try:
    keys = SDP_PREFERENCES.keys()
    from . import UserConfig  # noqa: F401
    if SDP_PREFERENCES.keys() != keys:
        print(" * ERROR: Check SDP_PREFERENCES keys in UserConfig.py")
        sys.exit(-1)
except ImportError:
    pass
