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

import git
import os
import copy
import pickle
import random
import threading
import sys
import platform
import argparse
import time
import traceback
import inspect
import ipaddress
import socket
import ssl
import subprocess
import pkgutil
import shlex
import re

from flask import Flask, render_template, flash, request, make_response, jsonify
from flask_cors import CORS
from wtforms import Form, validators, StringField, SelectField, SelectMultipleField, IntegerField, HiddenField
from wtforms import FormField, FieldList
from werkzeug.serving import WSGIRequestHandler
from enum import IntEnum
from junit_xml import TestSuite, TestCase
from datetime import datetime, timedelta
from types import SimpleNamespace
from requests.compat import json

from . import Config as CONFIG
from .DNS import DNS
from .GenericTest import NMOSInitException
from . import ControllerTest
from .TestResult import TestStates
from .TestHelper import get_default_ip
from .NMOSUtils import DEFAULT_ARGS
from .CRL import CRL, CRL_API
from .OCSP import OCSP, OCSP_API
from .mocks.Node import NODE, NODE_API
from .mocks.Registry import NUM_REGISTRIES, REGISTRIES, REGISTRY_API
from .mocks.System import NUM_SYSTEMS, SYSTEMS, SYSTEM_API
from .mocks.Auth import AUTH_API, PRIMARY_AUTH, SECONDARY_AUTH
from zeroconf import Zeroconf

# Make ANSI escape character sequences (for producing coloured terminal text) work under Windows
try:
    import colorama
    colorama.init()
except ImportError:
    pass

from .suites import IS0401Test
from .suites import IS0402Test
from .suites import IS0403Test
from .suites import IS0404Test
from .suites import IS0501Test
from .suites import IS0502Test
from .suites import IS0503Test
from .suites import IS0601Test
from .suites import IS0701Test
from .suites import IS0702Test
from .suites import IS0801Test
from .suites import IS0802Test
from .suites import IS0901Test
from .suites import IS0902Test
# from .suites import IS1001Test
from .suites import IS1301Test
from .suites import BCP00301Test
from .suites import BCP0060101Test
from .suites import BCP0060102Test


FLASK_APPS = []
DNS_SERVER = None
TOOL_VERSION = None
CMD_ARGS = None

if not CONFIG.RANDOM_SEED:
    CONFIG.RANDOM_SEED = random.randrange(sys.maxsize)

CACHEBUSTER = random.randint(1, 10000)

core_app = Flask(__name__)
CORS(core_app)
core_app.debug = False
core_app.config['SECRET_KEY'] = 'nmos-interop-testing-jtnm'
core_app.config['TEST_ACTIVE'] = False
core_app.config['PORT'] = CONFIG.PORT_BASE
core_app.config['SECURE'] = False
core_app.register_blueprint(NODE_API)  # Dependency for IS0401Test
core_app.register_blueprint(ControllerTest.TEST_API)
FLASK_APPS.append(core_app)

for instance in range(NUM_REGISTRIES):
    reg_app = Flask(__name__)
    CORS(
        reg_app, origins=['*'],
        allow_headers=['*'],
        expose_headers=['Content-Length',
                        'Link',
                        'Server-Timing',
                        'Timing-Allow-Origin',
                        'Vary',
                        'X-Paging-Limit',
                        'X-Paging-Since',
                        'X-Paging-Until'])
    reg_app.debug = False
    reg_app.config['REGISTRY_INSTANCE'] = instance
    reg_app.config['PORT'] = REGISTRIES[instance].port
    reg_app.config['SECURE'] = CONFIG.ENABLE_HTTPS
    reg_app.register_blueprint(REGISTRY_API)  # Dependency for IS0401Test
    FLASK_APPS.append(reg_app)

for instance in range(NUM_SYSTEMS):
    sys_app = Flask(__name__)
    sys_app.debug = False
    sys_app.config['SYSTEM_INSTANCE'] = instance
    sys_app.config['PORT'] = SYSTEMS[instance].port
    sys_app.config['SECURE'] = CONFIG.ENABLE_HTTPS
    sys_app.register_blueprint(SYSTEM_API)  # Dependency for IS0902Test
    FLASK_APPS.append(sys_app)

sender_app = Flask(__name__)
CORS(sender_app)
sender_app.debug = False
sender_app.config['PORT'] = NODE.port
sender_app.config['SECURE'] = CONFIG.ENABLE_HTTPS
sender_app.register_blueprint(NODE_API)  # Dependency for IS0401Test
FLASK_APPS.append(sender_app)

crl_app = Flask(__name__)
crl_app.debug = False
crl_app.config['PORT'] = CRL.port
crl_app.config['SECURE'] = False
crl_app.register_blueprint(CRL_API)  # CRL server
FLASK_APPS.append(crl_app)

ocsp_app = Flask(__name__)
ocsp_app.debug = False
ocsp_app.config['PORT'] = OCSP.port
ocsp_app.config['SECURE'] = False
ocsp_app.register_blueprint(OCSP_API)  # OCSP server
FLASK_APPS.append(ocsp_app)

# Primary Authorization server
if CONFIG.ENABLE_AUTH:
    auth_app = Flask(__name__)
    auth_app.debug = False
    auth_app.config['AUTH_INSTANCE'] = 0
    auth_app.config['PORT'] = PRIMARY_AUTH.port
    auth_app.config['SECURE'] = CONFIG.ENABLE_HTTPS
    auth_app.register_blueprint(AUTH_API)
    FLASK_APPS.append(auth_app)

# Definitions of each set of tests made available from the dropdowns
TEST_DEFINITIONS = {
    "IS-04-01": {
        "name": "IS-04 Node API",
        "specs": [{
            "spec_key": "is-04",
            "api_key": "node"
        }],
        "extra_specs": [{
            "spec_key": "bcp-002-01",
            "api_key": "grouphint"
        }, {
            "spec_key": "bcp-002-02",
            "api_key": "asset"
        }, {
            "spec_key": "bcp-004-01",
            "api_key": "receiver-caps"
        }, {
            "spec_key": "nmos-parameter-registers",
            "api_key": "caps-register"
        }],
        "class": IS0401Test.IS0401Test
    },
    "IS-04-02": {
        "name": "IS-04 Registry APIs",
        "specs": [{
            "spec_key": "is-04",
            "api_key": "registration"
        }, {
            "spec_key": "is-04",
            "api_key": "query"
        }],
        "class": IS0402Test.IS0402Test
    },
    "IS-04-03": {
        "name": "IS-04 Node API (Peer to Peer)",
        "specs": [{
            "spec_key": "is-04",
            "api_key": "node"
        }],
        "class": IS0403Test.IS0403Test
    },
    "IS-04-04": {
        "name": "IS-04 Controller",
        "specs": [{
            "spec_key": "controller-tests",
            "api_key": "testquestion"
        }, {
            "spec_key": "is-04",
            "api_key": "query",
            "disable_fields": ["host", "port"]
        }],
        "class": IS0404Test.IS0404Test
    },
    "IS-05-01": {
        "name": "IS-05 Connection Management API",
        "specs": [{
            "spec_key": "is-05",
            "api_key": "connection"
        }],
        "class": IS0501Test.IS0501Test
    },
    "IS-05-02": {
        "name": "IS-05 Interaction with IS-04",
        "specs": [{
            "spec_key": "is-04",
            "api_key": "node"
        }, {
            "spec_key": "is-05",
            "api_key": "connection"
        }],
        "class": IS0502Test.IS0502Test
    },
    "IS-05-03": {
        "name": "IS-05 Controller",
        "specs": [{
            "spec_key": "controller-tests",
            "api_key": "testquestion"
        }, {
            "spec_key": "is-04",
            "api_key": "query",
            "disable_fields": ["host", "port"]
        }, {
            "spec_key": "is-05",
            "api_key": "connection",
            "disable_fields": ["host", "port"]
        }],
        "class": IS0503Test.IS0503Test
    },
    "IS-06-01": {
        "name": "IS-06 Network Control API",
        "specs": [{
            "spec_key": "is-06",
            "api_key": "netctrl"
        }],
        "class": IS0601Test.IS0601Test
    },
    "IS-07-01": {
        "name": "IS-07 Event & Tally API",
        "specs": [{
            "spec_key": "is-07",
            "api_key": "events"
        }],
        "class": IS0701Test.IS0701Test
    },
    "IS-07-02": {
        "name": "IS-07 Interaction with IS-04 and IS-05",
        "specs": [{
            "spec_key": "is-04",
            "api_key": "node"
        }, {
            "spec_key": "is-05",
            "api_key": "connection"
        }, {
            "spec_key": "is-07",
            "api_key": "events"
        }],
        "class": IS0702Test.IS0702Test
    },
    "IS-08-01": {
        "name": "IS-08 Channel Mapping API",
        "specs": [{
            "spec_key": "is-08",
            "api_key": "channelmapping"
        }],
        "class": IS0801Test.IS0801Test,
        "selector": True
    },
    "IS-08-02": {
        "name": "IS-08 Interaction with IS-04",
        "specs": [{
            "spec_key": "is-04",
            "api_key": "node",
            "disable_fields": ["selector"]
        }, {
            "spec_key": "is-08",
            "api_key": "channelmapping"
        }],
        "class": IS0802Test.IS0802Test,
        "selector": True
    },
    "IS-09-01": {
        "name": "IS-09 System API",
        "specs": [{
            "spec_key": "is-09",
            "api_key": "system"
        }],
        "class": IS0901Test.IS0901Test
    },
    "IS-09-02": {
        "name": "IS-09 System API Discovery",
        "specs": [{
            "spec_key": "is-04",
            "api_key": "node",
            "disable_fields": ["port", "version"]
        }, {
            "spec_key": "is-09",
            "api_key": "system",
            "disable_fields": ["host", "port"]
        }],
        "class": IS0902Test.IS0902Test
    },
    # IS-10 testing is disabled until testing can be refactored to deal with commercial servers
    # "IS-10-01": {
    #     "name": "IS-10 Authorization API",
    #     "specs": [{
    #         "spec_key": "is-10",
    #         "api_key": "auth"
    #     }],
    #     "class": IS1001Test.IS1001Test
    # },
    "IS-13-01": {
        "name": "IS-13 Annotation API",
        "specs": [{
            "spec_key": "is-13",
            "api_key": "annotation"
        }],
        "class": IS1301Test.IS1301Test,
    },
    "BCP-003-01": {
        "name": "BCP-003-01 Secure Communication",
        "specs": [{
            "spec_key": "bcp-003-01",
            "api_key": "secure"
        }],
        "class": BCP00301Test.BCP00301Test
    },
    "BCP-006-01-01": {
        "name": "BCP-006-01 NMOS With JPEG XS",
        "specs": [{
            "spec_key": "is-04",
            "api_key": "node"
        }],
        "extra_specs": [{
            "spec_key": "nmos-parameter-registers",
            "api_key": "flow-register"
        }, {
            "spec_key": "nmos-parameter-registers",
            "api_key": "sender-register"
        }],
        "class": BCP0060101Test.BCP0060101Test
    },
    "BCP-006-01-02": {
        "name": "BCP-006-01 Controller",
        "specs": [{
            "spec_key": "controller-tests",
            "api_key": "testquestion"
        }, {
            "spec_key": "is-04",
            "api_key": "query",
            "disable_fields": ["host", "port"]
        }, {
            "spec_key": "is-05",
            "api_key": "connection",
            "disable_fields": ["host", "port"]
        }],
        "class": BCP0060102Test.BCP0060102Test
    },
}


def enumerate_tests(class_def, describe=False):
    if describe:
        tests = ["all: Runs all tests in the suite",
                 "auto: Basic API tests derived directly from the specification RAML"]
    else:
        tests = ["all", "auto"]
    for method_name in dir(class_def):
        if method_name.startswith("test_"):
            method = getattr(class_def, method_name)
            if callable(method):
                description = method_name
                if describe:
                    try:
                        docstring = inspect.getdoc(method).replace('\n', ' ').replace('\r', '')
                        description += ": " + docstring
                        if len(docstring) > 160:
                            print(" * WARNING: {}.{} description is too long (> 160 characters)"
                                  .format(class_def.__name__, method_name))
                    except AttributeError:
                        print(" * ERROR: {}.{} is missing a description".format(class_def.__name__, method_name))
                tests.append(description)
    return tests


class NonValidatingSelectField(SelectField):
    def pre_validate(self, form):
        pass


class NonValidatingMultipleSelectField(SelectMultipleField):
    def pre_validate(self, form):
        pass


class EndpointForm(Form):
    host = StringField(label="IP/Hostname:", validators=[validators.optional()])
    port = IntegerField(label="Port:", validators=[validators.NumberRange(min=0, max=65535,
                                                                          message="Please enter a valid port number "
                                                                                  "(0-65535)."),
                                                   validators.optional()])
    version = NonValidatingSelectField(label="API Version:", choices=[("v1.0", "v1.0"),
                                                                      ("v1.1", "v1.1"),
                                                                      ("v1.2", "v1.2"),
                                                                      ("v1.3", "v1.3")])
    selector = StringField(label="API Selector:", validators=[validators.optional()])


class DataForm(Form):
    # Define the primary test selection dropdown
    test_choices = [(test_id, TEST_DEFINITIONS[test_id]["name"]) for test_id in TEST_DEFINITIONS]
    test_choices = sorted(test_choices, key=lambda x: x[0])
    test = SelectField(label="Test Suite:", choices=test_choices)

    # Determine how many sets of IP/Port/Version to display at most
    specs_per_test = [(test_id, TEST_DEFINITIONS[test_id]["specs"]) for test_id in TEST_DEFINITIONS]
    specs_per_test = sorted(specs_per_test, key=lambda x: x[0])
    max_endpoints = 0
    for spec in specs_per_test:
        if len(spec[1]) > max_endpoints:
            max_endpoints = len(spec[1])
    endpoints = FieldList(FormField(EndpointForm, label=""), min_entries=max_endpoints)

    # Define the secondary test selection dropdown
    test_selection = NonValidatingMultipleSelectField(label="Test Selection:", choices=[("all", "all"),
                                                                                        ("auto", "auto")])

    # Hide test data in the web form for dynamic modification of behaviour
    test_data = {}
    for test_id in TEST_DEFINITIONS:
        test_data[test_id] = copy.deepcopy(TEST_DEFINITIONS[test_id])
        test_data[test_id].pop("class")
        test_data[test_id]["test_methods"] = enumerate_tests(TEST_DEFINITIONS[test_id]["class"])
        test_data[test_id]["test_descriptions"] = enumerate_tests(TEST_DEFINITIONS[test_id]["class"], describe=True)

    hidden_options = HiddenField(default=max_endpoints)
    hidden_tests = HiddenField(default=json.dumps(test_data))
    hidden_specs = HiddenField(default=json.dumps(CONFIG.SPECIFICATIONS))


# Index page
@core_app.route('/', methods=["GET", "POST"])
def index_page():
    global CMD_ARGS
    form = DataForm(request.form)
    if request.method == "POST" and not core_app.config['TEST_ACTIVE']:
        if form.validate():
            test = request.form["test"]
            try:
                if test in TEST_DEFINITIONS:
                    test_def = TEST_DEFINITIONS[test]
                    # selectors must be explicitly enabled on the test suite
                    selector = "selector" in test_def and test_def["selector"]
                    endpoints = []
                    for index, spec in enumerate(test_def["specs"]):
                        # "disable_fields" is optional, none are disabled by default
                        disable_fields = spec["disable_fields"] if "disable_fields" in spec else []
                        endpoint = {}
                        for field in ["host", "port", "version", "selector"]:
                            if field in disable_fields or (field == "selector" and not selector):
                                endpoint[field] = None
                            else:
                                endpoint[field] = request.form.get("endpoints-{}-{}".format(index, field), None)
                        endpoints.append(endpoint)

                    test_selection = request.form.getlist("test_selection")
                    results = run_tests(test, endpoints, test_selection)
                    json_output = format_test_results(results, endpoints, "json", CMD_ARGS)
                    for index, result in enumerate(results["result"]):
                        results["result"][index] = result.output()
                    r = make_response(render_template("result.html", form=form, urls=results["urls"],
                                                      test=test_def["name"], result=results["result"],
                                                      json=json_output, config=_export_config(),
                                                      cachebuster=CACHEBUSTER))
                    r.headers['Cache-Control'] = 'no-cache, no-store'
                    return r
                else:
                    flash("Error: This test definition does not exist")
            except Exception as e:
                traceback.print_exc()
                flash("Error: {}".format(e))
        else:
            flash("Error: {}".format(form.errors))
    elif request.method == "POST":
        print(" * Unable to start new test run. Time since current test run began: {}"
              .format(timedelta(seconds=time.time() - core_app.config['TEST_ACTIVE'])))
        flash("Error: A test is currently in progress. Please wait until it has completed or restart the testing tool.")

    # Prepare configuration strings to display via the UI
    protocol = "HTTP"
    if CONFIG.ENABLE_HTTPS:
        protocol = "HTTPS"
    authorization = "Disabled"
    if CONFIG.ENABLE_AUTH:
        authorization = "Enabled"
    discovery_mode = None
    if CONFIG.ENABLE_DNS_SD:
        if CONFIG.DNS_SD_MODE == "multicast":
            discovery_mode = "Multicast DNS"
        elif CONFIG.DNS_SD_MODE == "unicast":
            discovery_mode = "Unicast DNS"
        else:
            discovery_mode = "Invalid Configuration"
    else:
        discovery_mode = "Disabled (Using Query API {}:{})".format(CONFIG.QUERY_API_HOST, CONFIG.QUERY_API_PORT)
    max_test_iterations = CONFIG.MAX_TEST_ITERATIONS or "Unlimited"
    r = make_response(render_template("index.html", form=form, config=_export_config(),
                                      pretty_config={"discovery": discovery_mode,
                                                     "protocol": protocol,
                                                     "authorization": authorization,
                                                     "max_test_iterations": max_test_iterations},
                                      cachebuster=CACHEBUSTER))
    r.headers['Cache-Control'] = 'no-cache, no-store'
    return r


def run_tests(test, endpoints, test_selection=["all"]):
    if test in TEST_DEFINITIONS:
        test_def = TEST_DEFINITIONS[test]
        protocol = "http"
        if CONFIG.ENABLE_HTTPS:
            protocol = "https"
        apis = {}
        tested_urls = []
        for index, spec in enumerate(test_def["specs"]):
            spec_key = spec["spec_key"]
            api_key = spec["api_key"]
            if endpoints[index]["host"] == "" or endpoints[index]["port"] == "":
                raise NMOSInitException("All IP/Hostname and Port fields must be completed")
            if endpoints[index]["host"] is not None and endpoints[index]["port"] is not None:
                base_url = "{}://{}:{}".format(protocol, endpoints[index]["host"], str(endpoints[index]["port"]))
            else:
                base_url = None
            if base_url is not None:
                url = base_url + "/"
                if api_key in CONFIG.SPECIFICATIONS[spec_key]["apis"]:
                    url += "x-nmos/{}/".format(api_key)
                    if endpoints[index]["version"] is not None:
                        url += "{}/".format(endpoints[index]["version"])
                if endpoints[index]["selector"] not in [None, ""]:
                    url += "{}/".format(endpoints[index]["selector"])
                tested_urls.append(url)
            else:
                url = None
            if endpoints[index]["host"] is not None:
                try:
                    ipaddress.ip_address(endpoints[index]["host"])
                    ip_address = endpoints[index]["host"]
                except ValueError:
                    ip_address = socket.gethostbyname(endpoints[index]["host"])
            else:
                ip_address = None
            if endpoints[index]["port"] is not None:
                port = int(endpoints[index]["port"])
            else:
                port = None
            apis[api_key] = {
                "base_url": base_url,
                "hostname": endpoints[index]["host"],
                "ip": ip_address,
                "port": port,
                "url": url,
                "version": endpoints[index]["version"],
                "selector": endpoints[index]["selector"],
                "spec": None,  # Used inside GenericTest
                "spec_path": CONFIG.CACHE_PATH + '/' + spec_key
            }
            if CONFIG.SPECIFICATIONS[spec_key]["repo"] is not None \
                    and api_key in CONFIG.SPECIFICATIONS[spec_key]["apis"]:
                spec_api = CONFIG.SPECIFICATIONS[spec_key]["apis"][api_key]
                apis[api_key]["name"] = spec_api["name"]
                if "raml" in spec_api:
                    apis[api_key]["raml"] = spec_api["raml"]

        # extra specs
        for spec in test_def["extra_specs"] if "extra_specs" in test_def else []:
            spec_key = spec["spec_key"]
            api_key = spec["api_key"]
            apis[api_key] = {
                "version": CONFIG.SPECIFICATIONS[spec_key]["default_version"],  # For now
                "spec": None,  # Used inside GenericTest
                "spec_path": CONFIG.CACHE_PATH + '/' + spec_key
            }
            if CONFIG.SPECIFICATIONS[spec_key]["repo"] is not None \
                    and api_key in CONFIG.SPECIFICATIONS[spec_key]["apis"]:
                spec_api = CONFIG.SPECIFICATIONS[spec_key]["apis"][api_key]
                apis[api_key]["name"] = spec_api["name"]
                if "raml" in spec_api:
                    apis[api_key]["raml"] = spec_api["raml"]

        # Instantiate the test class
        test_obj = test_def["class"](apis,
                                     systems=SYSTEMS,
                                     registries=REGISTRIES,
                                     node=NODE,
                                     dns_server=DNS_SERVER,
                                     auths=[PRIMARY_AUTH, SECONDARY_AUTH])

        core_app.config['TEST_ACTIVE'] = time.time()
        try:
            result = test_obj.run_tests(test_selection)
        except Exception as ex:
            print(" * ERROR: {}".format(ex))
            raise ex
        finally:
            core_app.config['TEST_ACTIVE'] = False
        return {"result": result, "def": test_def, "urls": tested_urls, "suite": test}
    else:
        raise NMOSInitException("This test definition does not exist")


def init_spec_cache():
    print(" * Initialising specification repositories...")

    if not os.path.exists(CONFIG.CACHE_PATH):
        os.makedirs(CONFIG.CACHE_PATH)

    # Prevent re-pulling of the spec repos too frequently
    time_now = datetime.now()
    last_pull_file = os.path.join(CONFIG.CACHE_PATH + "/last_pull")
    last_pull_time = time_now - timedelta(hours=1)
    update_last_pull = False
    if os.path.exists(last_pull_file):
        try:
            with open(last_pull_file, "rb") as f:
                last_pull_time = pickle.load(f)
        except Exception as e:
            print(" * ERROR: Unable to load last pull time for cache: {}".format(e))

    for repo_key, repo_data in CONFIG.SPECIFICATIONS.items():
        path = os.path.join(CONFIG.CACHE_PATH + '/' + repo_key)
        if repo_data["repo"] is None:
            continue
        if not os.path.exists(path):
            print(" * Initialising repository '{}'".format(repo_data["repo"]))
            repo = git.Repo.clone_from('https://github.com/AMWA-TV/' + repo_data["repo"] + '.git', path)
            update_last_pull = True
        else:
            repo = git.Repo(path)
            repo.git.reset('--hard')
            # Only pull if we haven't in the last hour
            if (last_pull_time + timedelta(hours=1)) <= time_now:
                print(" * Pulling latest files for repository '{}'".format(repo_data["repo"]))
                try:
                    repo.remotes.origin.pull()
                    update_last_pull = True
                except Exception:
                    print(" * ERROR: Unable to update repository '{}'. If the problem persists, "
                          "please delete the '{}' directory".format(repo_data["repo"], CONFIG.CACHE_PATH))

    if update_last_pull:
        try:
            with open(last_pull_file, "wb") as f:
                pickle.dump(time_now, f)
        except Exception as e:
            print(" * ERROR: Unable to write last pull time to file: {}".format(e))

    print(" * Initialisation complete")


def _check_test_result(test_result, results):
    if test_result is None:
        print(
            "The following results currently are being returned: {}"
            .format([result.name for result in results["result"] if result != test_result])
        )
        raise AttributeError("""
            None object returned as result from one of the tests. Please see the terminal output.
        """)


def _export_config():
    current_config = {"VERSION": TOOL_VERSION}
    exclude_params = ['SPECIFICATIONS']
    for param in dir(CONFIG):
        if re.match("^[A-Z][A-Z0-9_]*$", param) and param not in exclude_params:
            current_config[param] = getattr(CONFIG, param)
    return current_config


def format_test_results(results, endpoints, format, args):
    formatted = None
    total_time = 0
    max_name_len = 0
    ignored_tests = []
    if "suite" in vars(args):
        ignored_tests = args.ignore
    for test_result in results["result"]:
        _check_test_result(test_result, results)
        total_time += test_result.elapsed_time
        max_name_len = max(max_name_len, len(test_result.name))
    if format == "json":
        formatted = {
            "suite": results["suite"],
            "timestamp": time.time(),
            "duration": total_time,
            "results": [],
            "config": _export_config(),
            "endpoints": endpoints
        }
        for test_result in results["result"]:
            formatted["results"].append({
                "name": test_result.name,
                "state": str(TestStates.DISABLED if test_result.name in ignored_tests else test_result.state),
                "detail": test_result.detail,
                "duration": test_result.elapsed_time
            })
        formatted = json.dumps(formatted, sort_keys=True, indent=4)
    elif format == "junit":
        test_cases = []
        for test_result in results["result"]:
            test_case = TestCase(test_result.name, classname=results["suite"],
                                 elapsed_sec=test_result.elapsed_time, timestamp=test_result.timestamp)
            if test_result.name in ignored_tests or test_result.state in [
                TestStates.DISABLED,
                TestStates.UNCLEAR,
                TestStates.MANUAL,
                TestStates.NA,
                TestStates.OPTIONAL
            ]:
                test_case.add_skipped_info(test_result.detail)
            elif test_result.state in [TestStates.WARNING, TestStates.FAIL]:
                test_case.add_failure_info(test_result.detail, failure_type=str(test_result.state))
            elif test_result.state != TestStates.PASS:
                test_case.add_error_info(test_result.detail, error_type=str(test_result.state))
            test_cases.append(test_case)
        formatted = TestSuite(results["def"]["name"] + ": " + ", ".join(results["urls"]), test_cases)
    elif format == "console":
        formatted = "\r\nPrinting test results for suite '{}' using API(s) '{}'\r\n" \
                    .format(results["suite"], ", ".join(results["urls"]))
        formatted += "----------------------------\r\n"
        for test_result in results["result"]:
            num_extra_dots = max_name_len - len(test_result.name)
            test_state = str(TestStates.DISABLED if test_result.name in ignored_tests else test_result.state)
            formatted += "{} ...{} {}\r\n".format(test_result.name, ("." * num_extra_dots), test_state)
        formatted += "----------------------------\r\n"
        formatted += "Ran {} tests in ".format(len(results["result"])) + "{0:.3f}s".format(total_time) + "\r\n"
    return formatted


def identify_exit_code(results, args):
    exit_code = ExitCodes.OK
    for test_result in results["result"]:
        if test_result.name in args.ignore:
            pass
        elif test_result.state == TestStates.FAIL:
            exit_code = max(exit_code, ExitCodes.FAIL)
        elif test_result.state == TestStates.WARNING:
            exit_code = max(exit_code, ExitCodes.WARNING)
    return exit_code


def write_test_results(results, endpoints, args):
    if args.output.endswith(".xml"):
        formatted = format_test_results(results, endpoints, "junit", args)
    else:
        formatted = format_test_results(results, endpoints, "json", args)
    with open(args.output, "w") as f:
        if args.output.endswith(".xml"):
            # pretty-print to help out Jenkins (and us humans), which struggles otherwise
            TestSuite.to_file(f, [formatted], prettyprint=True)
        else:
            f.write(formatted)
        print(" * Test results written to file: {}".format(args.output))
    return identify_exit_code(results, args)


def print_test_results(results, endpoints, args):
    print(format_test_results(results, endpoints, "console", args))
    return identify_exit_code(results, args)


def parse_arguments():
    parser = argparse.ArgumentParser(description='NMOS Test Suite')
    parser.add_argument('--list-suites', action='store_true', help="list available test suites")
    parser.add_argument('--describe-suites', action='store_true', help="describe the available test suites")

    subparsers = parser.add_subparsers()
    suite_parser = subparsers.add_parser("suite", help="select a test suite to run tests from in non-interactive mode")
    suite_parser.add_argument("suite",
                              help="select a test suite to run tests from in non-interactive mode")
    suite_parser.add_argument('--list-tests', action='store_true',
                              help="list available tests for a given suite")
    suite_parser.add_argument('--describe-tests', action='store_true',
                              help="describe the available tests for a given suite")
    suite_parser.add_argument('--selection', default=DEFAULT_ARGS["selection"],
                              help="select a specific test to run, otherwise 'all' will be tested")
    suite_parser.add_argument('--host', default=DEFAULT_ARGS["host"], nargs="*",
                              help="space separated hostnames or IPs of the APIs under test")
    suite_parser.add_argument('--port', default=DEFAULT_ARGS["port"], nargs="*", type=int,
                              help="space separated ports of the APIs under test")
    suite_parser.add_argument('--version', default=DEFAULT_ARGS["version"], nargs="*",
                              help="space separated versions of the APIs under test")
    suite_parser.add_argument('--selector', default=DEFAULT_ARGS["selector"], nargs="*",
                              help="space separated device selector names of the APIs under test")
    suite_parser.add_argument('--ignore', default=DEFAULT_ARGS["ignore"], nargs="*",
                              help="space separated test names to ignore the results from")
    suite_parser.add_argument('--output', default=DEFAULT_ARGS["output"],
                              help="filename to save test results to (ending .xml or .json), otherwise print to stdout")

    return parser.parse_args()


def validate_args(args, access_type="cli"):
    """Validate input arguments. access_type is 'cli' for command line tool and 'http' for api use"""
    msg = ""
    return_type = ExitCodes.OK
    if args.list_suites:
        for test_suite in sorted(TEST_DEFINITIONS):
            msg += test_suite + '\n'
    elif args.describe_suites:
        for test_suite in sorted(TEST_DEFINITIONS):
            msg += test_suite + ": " + TEST_DEFINITIONS[test_suite]["name"] + '\n'
    elif "suite" in vars(args):
        if args.suite not in TEST_DEFINITIONS:
            msg = "ERROR: The requested test suite '{}' does not exist".format(args.suite)
            return_type = ExitCodes.ERROR
        elif args.list_tests:
            tests = enumerate_tests(TEST_DEFINITIONS[args.suite]["class"])
            for test_name in tests:
                msg += test_name + '\n'
        elif args.describe_tests:
            tests = enumerate_tests(TEST_DEFINITIONS[args.suite]["class"], describe=True)
            for test_description in tests:
                msg += test_description + '\n'
        elif getattr(args, "selection", "all") not in enumerate_tests(TEST_DEFINITIONS[args.suite]["class"]):
            msg = "ERROR: Test with name '{}' does not exist in test suite '{}'".format(args.selection,
                                                                                        args.suite)
            return_type = ExitCodes.ERROR
        elif not args.host or not args.port or not args.version:
            msg = "ERROR: No Hostname(s)/IP address(es) or Port(s) or Version(s) specified"
            return_type = ExitCodes.ERROR
        elif len(args.host) != len(args.port) or len(args.host) != len(args.version):
            msg = "ERROR: Hostname(s)/IP address(es), Port(s) and Version(s) must contain the same number of elements"
            return_type = ExitCodes.ERROR
        elif "selector" in TEST_DEFINITIONS[args.suite] and TEST_DEFINITIONS[args.suite]["selector"] is True and not \
                args.selector:
            msg = "ERROR: No Selector(s) specified"
            return_type = ExitCodes.ERROR
        elif "selector" in TEST_DEFINITIONS[args.suite] and TEST_DEFINITIONS[args.suite]["selector"] is True and \
                len(args.host) != len(args.selector):
            msg = "ERROR: Hostname(s)/IP address(es), Port(s), Version(s) and Selector(s) must contain the same " \
                  "number of elements"
            return_type = ExitCodes.ERROR
        elif len(args.host) != len(TEST_DEFINITIONS[args.suite]["specs"]):
            msg = "ERROR: This test suite expects {} Hostname(s)/IP address(es), Port(s) and Version(s)".format(
                len(TEST_DEFINITIONS[args.suite]["specs"]))
            return_type = ExitCodes.ERROR
        elif args.output and not args.output.endswith("xml") and not args.output.endswith("json"):
            msg = "ERROR: Output file must end with '.xml' or '.json'"
            return_type = ExitCodes.ERROR
    elif access_type == "http" and "suite" not in vars(args):
        msg = "ERROR: 'suite' parameter not found in body of request"
        return_type = ExitCodes.ERROR
    return arg_return(access_type, return_type, msg)


def arg_return(access_type, return_type, msg=""):
    if access_type == "http":
        if msg.endswith('\n'):
            msg = msg[:-1]
        return msg, return_type
    elif msg:
        msg = " * " + msg
        print(msg)
        if return_type == ExitCodes.OK:
            sys.exit(return_type)
        elif return_type == ExitCodes.ERROR:
            sys.exit(return_type)


class PortLoggingHandler(WSGIRequestHandler):
    def log(self, type, message, *args):
        # Conform to Combined Log Format, replacing Referer with the Host header or the local server address
        url_scheme = "http" if self.server.ssl_context is None else "https"
        if hasattr(self, "headers"):
            host = self.headers.get("Host", "{}:{}".format(self.server.server_address[0],
                                                           self.server.server_address[1]))
            user_agent = self.headers.get("User-Agent", "")
        else:
            host = "{}:{}".format(self.server.server_address[0], self.server.server_address[1])
            user_agent = ""
        referer = "{}://{}".format(url_scheme, host)
        message += ' "{}" "{}"'.format(referer, user_agent)
        super().log(type, message, *args)


def start_web_servers():
    ctx = None
    if CONFIG.ENABLE_HTTPS:
        # ssl.create_default_context() provides options that broadly correspond to the requirements of BCP-003-01
        ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        for cert, key in zip(CONFIG.CERTS_MOCKS, CONFIG.KEYS_MOCKS):
            ctx.load_cert_chain(cert, key)
        # additionally disable TLS v1.0 and v1.1
        ctx.options &= ssl.OP_NO_TLSv1 | ssl.OP_NO_TLSv1_1
        # BCP-003-01 however doesn't require client certificates, so disable those
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

    web_threads = []
    for app in FLASK_APPS:
        port = app.config['PORT']
        secure = app.config['SECURE']
        t = threading.Thread(target=app.run, kwargs={'host': '0.0.0.0', 'port': port, 'threaded': True,
                                                     'ssl_context': ctx if secure else None,
                                                     'request_handler': PortLoggingHandler})
        t.daemon = True
        t.start()
        web_threads.append(t)

    # Wait for all threads to get going
    time.sleep(1)
    for thread in web_threads:
        if not thread.is_alive():
            print(" * ERROR: One or more web servers could not start. The port may already be in use")
            sys.exit(ExitCodes.ERROR)


def run_noninteractive_tests(args):
    endpoints = []
    for i in range(len(args.host)):
        if args.host[i] == "null":
            args.host[i] = None
        if args.port[i] == 0:
            args.port[i] = None
        if args.version[i] == "null":
            args.version[i] = None
        selector = None
        if len(args.selector) == len(args.host) and args.selector[i] != "null":
            selector = args.selector[i]
        endpoints.append({"host": args.host[i], "port": args.port[i], "version": args.version[i],
                          "selector": selector})
    try:
        results = run_tests(args.suite, endpoints, [args.selection])
        if args.output:
            exit_code = write_test_results(results, endpoints, args)
        else:
            exit_code = print_test_results(results, endpoints, args)
    except Exception as e:
        print(" * ERROR: {}".format(str(e)))
        exit_code = ExitCodes.ERROR
    return exit_code


def check_internal_requirements():
    corrections = {"gitpython": "git",
                   "pyopenssl": "OpenSSL",
                   "websocket-client": "websocket",
                   "paho-mqtt": "paho",
                   "Flask-Cors": "flask_cors",
                   "pycryptodome": "Crypto"}
    installed_pkgs = [pkg[1] for pkg in pkgutil.iter_modules()]
    with open("requirements.txt") as requirements_file:
        for requirement in requirements_file.readlines():
            requirement_name = requirement.strip().split(">")[0]
            if requirement_name in corrections:
                corrected_req = corrections[requirement_name]
            else:
                corrected_req = requirement_name.replace("-", "_")
            if corrected_req not in installed_pkgs:
                print(" * ERROR: Could not find Python requirement '{}'".format(requirement_name))
                sys.exit(ExitCodes.ERROR)


def check_external_requirements():
    deps = {
        "sdpoker": ("sdpoker --version", "0.3.0"),
        "testssl": ("{} testssl/testssl.sh -v".format(shlex.quote(CONFIG.TEST_SSL_BASH)), "3.0.7")
    }
    for dep_name, dep_ver in deps.items():
        try:
            output = subprocess.check_output(dep_ver[0], stderr=subprocess.STDOUT, shell=True)
            if dep_ver[1] not in str(output):
                print(" * WARNING: Version of '{}' does not match the expected '{}'".format(dep_name, dep_ver[1]))
        except subprocess.CalledProcessError:
            print(" * WARNING: Could not find an installation of '{}'. Some tests will be disabled.".format(dep_name))


class ExitCodes(IntEnum):
    ERROR = -1  # General test suite error
    OK = 0  # Normal exit condition, or all tests passed in non-interactive mode
    WARNING = 1  # Worst case test was a warning in non-interactive mode
    FAIL = 2  # Worst case test was a failure in non-interactive mode


@core_app.route('/api', methods=["GET", "POST"])
def api():
    if request.method == "GET":
        example_dict = {}
        example_dict["description"] = "An example of the body to POST to this endpoint might include:"
        example_dict["suite"] = "IS-04-01"
        example_dict["host"] = ["127.0.0.1"]
        example_dict["port"] = [80]
        example_dict["version"] = ["v1.2"]
        example_dict["selector"] = [None]
        example_dict["output"] = "xml"
        example_dict["ignore"] = ["test_23"]
        return jsonify(example_dict), 200
    elif core_app.config['TEST_ACTIVE'] is not False:
        return jsonify("""Error: A test is currently in progress.
                        Please wait until it has completed or restart the testing tool."""), 400
    if not request.is_json:
        return jsonify("Error: Request mimetype is not set to a JSON specific type with a valid JSON Body"), 400
    if not request.get_json(silent=True):
        return jsonify("Error: Ensure the body of the request is valid JSON and non-empty"), 400
    request_data = dict(DEFAULT_ARGS, **request.json)
    request_args = SimpleNamespace(**request_data)
    return_message, return_type = validate_args(request_args, access_type="http")
    if return_message:
        if return_type == ExitCodes.OK:
            return jsonify(return_message.split('\n')), 200
        else:
            return jsonify(return_message), 400
    data_format = request_args.output if request_args.output is not None else "json"
    if "." in data_format:
        filename, data_format = data_format.split(".")
    try:
        results = run_api_tests(request_args, data_format)
        if data_format == "json":
            return jsonify(results), 200
        else:
            return results, 200, {"Content-Type": "text/xml; charset=utf-8"}
    except Exception as e:
        print(e)
        results = traceback.format_exc()
        return results, 400


@core_app.route('/config', methods=["GET", "PATCH"])
def config():
    if request.method == "GET":
        return jsonify(_export_config())
    elif request.method == "PATCH":
        try:
            if not request.is_json:
                return jsonify("Error: Request mimetype is not set to a JSON specific type with a valid JSON Body"), 400
            if not request.get_json(silent=True):
                return jsonify("Error: Ensure the body of the request is valid JSON and non-empty"), 400
            request_data = request.json
            if not isinstance(request_data, dict):
                return jsonify("Error: Body must be of type object/dict"), 400
            for config_param in request_data:
                setattr(CONFIG, config_param, request_data[config_param])
            return jsonify(_export_config()), 200
        except Exception:
            return jsonify("Error: Config Update Failed"), 400


def run_api_tests(args, data_format):
    endpoints = []
    for i in range(len(args.host)):
        if args.port[i] == 0:
            args.port[i] = None
        selector = None
        if len(args.selector) == len(args.host):
            selector = args.selector[i]
        endpoints.append({"host": args.host[i], "port": args.port[i], "version": args.version[i],
                          "selector": selector})
    results = run_tests(args.suite, endpoints, [args.selection])
    if data_format == "xml":
        formatted_test_results = format_test_results(results, endpoints, "junit", args)
        return TestSuite.to_xml_string([formatted_test_results], prettyprint=True)
    else:
        formatted_test_results = format_test_results(results, endpoints, "json", args)
        return json.loads(formatted_test_results)


def main(args):
    global CMD_ARGS, DNS_SERVER, TOOL_VERSION
    # Check if we're testing unicast DNS discovery, and if so ensure we have elevated privileges
    if CONFIG.ENABLE_DNS_SD and CONFIG.DNS_SD_MODE == "unicast":
        is_admin = False
        if platform.system() == "Windows":
            from ctypes import windll
            if windll.shell32.IsUserAnAdmin():
                is_admin = True
        elif os.geteuid() == 0:
            is_admin = True
        if not is_admin:
            print(" * ERROR: In order to test DNS-SD in unicast mode, the test suite must be run "
                  "with elevated permissions")
            sys.exit(ExitCodes.ERROR)

    # Check that all dependencies are installed
    check_internal_requirements()
    check_external_requirements()

    # Parse and validate command line arguments
    CMD_ARGS = parse_arguments()
    validate_args(CMD_ARGS)

    # Download up to date versions of each API specification
    init_spec_cache()

    # Identify current testing tool version
    try:
        repo = git.Repo(".")
        TOOL_VERSION = repo.git.rev_parse(repo.head.object.hexsha, short=7)
    except git.exc.InvalidGitRepositoryError:
        TOOL_VERSION = "Unknown"

    # Start the DNS server
    if CONFIG.ENABLE_DNS_SD and CONFIG.DNS_SD_MODE == "unicast":
        DNS_SERVER = DNS()

    # Advertise the primary mock Authorization server to allow the Node to find it
    if CONFIG.ENABLE_AUTH and CONFIG.DNS_SD_MODE == "multicast":
        primary_auth_info = PRIMARY_AUTH.make_mdns_info()
        zc = Zeroconf()
        zc.register_service(primary_auth_info)

    # Start the HTTP servers
    start_web_servers()

    print(" * Testing tool running on 'http://{}:{}'. Version '{}'"
          .format(get_default_ip(), core_app.config['PORT'], TOOL_VERSION))

    # Give an API or client that is already running a chance to use the mock services
    # before running any test cases
    if CONFIG.MOCK_SERVICES_WARM_UP_DELAY:
        print(" * Waiting for {} seconds to allow discovery of mock services"
              .format(CONFIG.MOCK_SERVICES_WARM_UP_DELAY))
        time.sleep(CONFIG.MOCK_SERVICES_WARM_UP_DELAY)

    exit_code = 0
    if "suite" not in vars(CMD_ARGS):
        # Interactive testing mode. Await user input.
        try:
            while True:
                time.sleep(0.2)
        except KeyboardInterrupt:
            pass
    else:
        # Non-interactive testing mode. Tests carried out automatically.
        exit_code = run_noninteractive_tests(CMD_ARGS)

    # Testing complete
    print(" * Exiting")

    # Remove the primary mock Authorization server advertisement
    if CONFIG.ENABLE_AUTH and CONFIG.DNS_SD_MODE == "multicast":
        zc.unregister_service(primary_auth_info)

    # Stop the DNS server
    if DNS_SERVER:
        DNS_SERVER.stop()

    # Exit the application with the desired code
    sys.exit(exit_code)
