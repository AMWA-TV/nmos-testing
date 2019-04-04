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

from flask import Flask, render_template, flash, request, make_response
from wtforms import Form, validators, StringField, SelectField, SelectMultipleField, IntegerField, HiddenField, FormField, FieldList
from Registry import NUM_REGISTRIES, REGISTRIES, REGISTRY_API
from GenericTest import NMOSInitException
from TestResult import TestStates
from Node import NODE, NODE_API
from Config import CACHE_PATH, SPECIFICATIONS, ENABLE_DNS_SD, DNS_SD_MODE, ENABLE_HTTPS, QUERY_API_HOST, QUERY_API_PORT
from DNS import DNS
from datetime import datetime, timedelta
from junit_xml import TestSuite, TestCase
from enum import IntEnum

import git
import os
import json
import copy
import pickle
import random
import threading
import sys
import platform
import argparse
import time
import traceback
import ipaddress
import socket

import IS0401Test
import IS0402Test
import IS0403Test
import IS0501Test
import IS0502Test
import IS0601Test
import IS0701Test
import IS0801Test
import IS0802Test
import BCP00301Test
import BCP00302Test

FLASK_APPS = []
DNS_SERVER = None

CACHEBUSTER = random.randint(1, 10000)

core_app = Flask(__name__)
core_app.debug = False
core_app.config['SECRET_KEY'] = 'nmos-interop-testing-jtnm'
core_app.config['TEST_ACTIVE'] = False
core_app.register_blueprint(NODE_API)  # Dependency for IS0401Test

for instance in range(NUM_REGISTRIES):
    reg_app = Flask(__name__)
    reg_app.debug = False
    reg_app.config['REGISTRY_INSTANCE'] = instance
    reg_app.register_blueprint(REGISTRY_API)  # Dependency for IS0401Test
    FLASK_APPS.append(reg_app)


# Definitions of each set of tests made available from the dropdowns
TEST_DEFINITIONS = {
    "IS-04-01": {
        "name": "IS-04 Node API",
        "specs": [{
            "spec_key": "is-04",
            "api_key": "node"
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
    "IS-05-01": {
        "name": "IS-05 Connection Management API",
        "specs": [{
            "spec_key": 'is-05',
            "api_key": "connection"
        }],
        "class": IS0501Test.IS0501Test
    },
    "IS-05-02": {
        "name": "IS-05 Interaction with Node API",
        "specs": [{
            "spec_key": "is-04",
            "api_key": "node"
        }, {
            "spec_key": "is-05",
            "api_key": "connection"
        }],
        "class": IS0502Test.IS0502Test
    },
    "IS-06-01": {
        "name": "IS-06 Network Control API",
        "specs": [{
            "spec_key": 'is-06',
            "api_key": "netctrl"
        }],
        "class": IS0601Test.IS0601Test
    },
    "IS-07-01": {
        "name": "IS-07 Event & Tally API",
        "specs": [{
            "spec_key": 'is-07',
            "api_key": "events"
        }],
        "class": IS0701Test.IS0701Test
    },
    "IS-08-01": {
        "name": "IS-08 Channel Mapping API",
        "specs": [{
            "spec_key": 'is-08',
            "api_key": "channelmapping"
        }],
        "class": IS0801Test.IS0801Test
    },
    "IS-08-02": {
        "name": "IS-08 Interaction with Node API",
        "specs": [{
            "spec_key": 'is-08',
            "api_key": "channelmapping"
        },  {
            "spec_key": "is-04",
            "api_key": "node"
        }],
        "class": IS0802Test.IS0802Test
    },
    "BCP-003-01": {
        "name": "BCP-003-01 Secure API Communications",
        "specs": [{
            "spec_key": "bcp-003-01",
            "api_key": "bcp-003-01"
        }],
        "class": BCP00301Test.BCP00301Test
    },
    "BCP-003-02": {
        "name": "BCP-003-02 Authorization API",
        "specs": [{
            "spec_key": 'bcp-003-02',
            "api_key": "auth"
        }],
        "class": BCP00302Test.BCP00302Test
    }
}


def enumerate_tests(class_def):
    tests = ["all", "auto"]
    for method_name in dir(class_def):
        if method_name.startswith("test_"):
            method = getattr(class_def, method_name)
            if callable(method):
                tests.append(method_name)
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
        if len(spec) > max_endpoints:
            max_endpoints = len(spec)
    endpoints = FieldList(FormField(EndpointForm, label=""), min_entries=max_endpoints)

    # Define the secondary test selection dropdown
    test_selection = NonValidatingMultipleSelectField(label="Test Selection:", choices=[("all", "all"),
                                                                                        ("auto", "auto")])

    # Hide test data in the web form for dynamic modification of behaviour
    test_data = {}
    for test_id in TEST_DEFINITIONS:
        test_data[test_id] = copy.deepcopy(TEST_DEFINITIONS[test_id])
        test_data[test_id].pop("class")
        test_data[test_id]["tests"] = enumerate_tests(TEST_DEFINITIONS[test_id]["class"])

    hidden_options = HiddenField(default=max_endpoints)
    hidden_tests = HiddenField(default=json.dumps(test_data))
    hidden_specs = HiddenField(default=json.dumps(SPECIFICATIONS))


# Index page
@core_app.route('/', methods=["GET", "POST"])
def index_page():
    form = DataForm(request.form)
    if request.method == "POST" and not core_app.config['TEST_ACTIVE']:
        if form.validate():
            test = request.form["test"]
            try:
                if test in TEST_DEFINITIONS:
                    test_def = TEST_DEFINITIONS[test]
                    endpoints = []
                    for index, spec in enumerate(test_def["specs"]):
                        host = request.form["endpoints-{}-host".format(index)]
                        port = request.form["endpoints-{}-port".format(index)]
                        version = request.form["endpoints-{}-version".format(index)]
                        endpoints.append({"host": host, "port": port, "version": version})

                    test_selection = request.form.getlist("test_selection")
                    results = run_tests(test, endpoints, test_selection)
                    for index, result in enumerate(results["result"]):
                        results["result"][index] = result.output()
                    r = make_response(render_template("result.html", form=form, url=results["base_url"],
                                                      test=results["name"], result=results["result"],
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
        flash("Error: A test is currently in progress. Please wait until it has completed or restart the testing tool.")

    # Prepare configuration strings to display via the UI
    protocol = "HTTP"
    if ENABLE_HTTPS:
        protocol = "HTTPS"
    discovery_mode = None
    if ENABLE_DNS_SD:
        if DNS_SD_MODE == "multicast":
            discovery_mode = "Multicast DNS"
        elif DNS_SD_MODE == "unicast":
            discovery_mode = "Unicast DNS"
        else:
            discovery_mode = "Invalid Configuration"
    else:
        discovery_mode = "Disabled (Using Query API {}:{})".format(QUERY_API_HOST, QUERY_API_PORT)

    r = make_response(render_template("index.html", form=form, config={"discovery": discovery_mode,
                                                                       "protocol": protocol},
                                      cachebuster=CACHEBUSTER))
    r.headers['Cache-Control'] = 'no-cache, no-store'
    return r


def run_tests(test, endpoints, test_selection=["all"]):
    if test in TEST_DEFINITIONS:
        test_def = TEST_DEFINITIONS[test]
        protocol = "http"
        if ENABLE_HTTPS:
            protocol = "https"
        apis = {}
        for index, spec in enumerate(test_def["specs"]):
            base_url = "{}://{}:{}".format(protocol, endpoints[index]["host"], str(endpoints[index]["port"]))
            spec_key = spec["spec_key"]
            api_key = spec["api_key"]
            try:
                ipaddress.ip_address(endpoints[index]["host"])
                ip_address = endpoints[index]["host"]
            except ValueError:
                ip_address = socket.gethostbyname(endpoints[index]["host"])
            apis[api_key] = {
                "base_url": base_url,
                "hostname": endpoints[index]["host"],
                "ip": ip_address,
                "port": int(endpoints[index]["port"]),
                "url": "{}/x-nmos/{}/{}/".format(base_url, api_key, endpoints[index]["version"]),
                "version": endpoints[index]["version"],
                "spec": None  # Used inside GenericTest
            }
            if SPECIFICATIONS[spec_key]["repo"] is not None and api_key in SPECIFICATIONS[spec_key]["apis"]:
                apis[api_key]["spec_path"] = CACHE_PATH + '/' + spec_key
                apis[api_key]["raml"] = SPECIFICATIONS[spec_key]["apis"][api_key]["raml"]

        # Instantiate the test class
        if test == "IS-04-01":
            # This test has an unusual constructor as it requires a registry instance
            test_obj = test_def["class"](apis, REGISTRIES, NODE, DNS_SERVER)
        else:
            test_obj = test_def["class"](apis)

        core_app.config['TEST_ACTIVE'] = True
        try:
            result = test_obj.run_tests(test_selection)
        except Exception as ex:
            print(" * ERROR: {}".format(ex))
            raise ex
        finally:
            core_app.config['TEST_ACTIVE'] = False
        return {"result": result, "name": test_def["name"], "base_url": base_url}
    else:
        raise NMOSInitException("This test definition does not exist")


def init_spec_cache():
    print(" * Initialising specification repositories...")

    if not os.path.exists(CACHE_PATH):
        os.makedirs(CACHE_PATH)

    # Prevent re-pulling of the spec repos too frequently
    time_now = datetime.now()
    last_pull_file = os.path.join(CACHE_PATH + "/last_pull")
    last_pull_time = time_now - timedelta(hours=1)
    update_last_pull = False
    if os.path.exists(last_pull_file):
        try:
            with open(last_pull_file, "rb") as f:
                last_pull_time = pickle.load(f)
        except Exception as e:
            print(" * ERROR: Unable to load last pull time for cache: {}".format(e))

    for repo_key, repo_data in SPECIFICATIONS.items():
        path = os.path.join(CACHE_PATH + '/' + repo_key)
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
                          "please delete the '{}' directory".format(repo_data["repo"], CACHE_PATH))

    if update_last_pull:
        try:
            with open(last_pull_file, "wb") as f:
                pickle.dump(time_now, f)
        except Exception as e:
            print(" * ERROR: Unable to write last pull time to file: {}".format(e))

    print(" * Initialisation complete")


def write_test_results(results, args):
    exit_code = ExitCodes.OK
    test_cases = []
    for test_result in results["result"]:
        test_case = TestCase(test_result.name, elapsed_sec=test_result.elapsed_time,
                             timestamp=test_result.timestamp)
        if test_result.name in args.ignore or test_result.state in [TestStates.DISABLED,
                                                                    TestStates.UNCLEAR,
                                                                    TestStates.MANUAL,
                                                                    TestStates.NA,
                                                                    TestStates.OPTIONAL]:
            test_case.add_skipped_info(test_result.detail)
        elif test_result.state in [TestStates.WARNING, TestStates.FAIL]:
            test_case.add_failure_info(test_result.detail, failure_type=str(test_result.state))
            if test_result.state == TestStates.FAIL:
                exit_code = max(exit_code, ExitCodes.FAIL)
            elif test_result.state == TestStates.WARNING:
                exit_code = max(exit_code, ExitCodes.WARNING)
        elif test_result.state != TestStates.PASS:
            test_case.add_error_info(test_result.detail, error_type=str(test_result.state))
        test_cases.append(test_case)

    ts = TestSuite(results["name"] + ": " + results["base_url"], test_cases)
    with open(args.output, "w") as f:
        TestSuite.to_file(f, [ts], prettyprint=False)
        print(" * Test results written to file: {}".format(args.output))
    return exit_code


def print_test_results(results, args):
    exit_code = ExitCodes.OK
    print("\r\nPrinting test results for suite '{}' using API '{}'".format(results["name"], results["base_url"]))
    print("----------------------------")
    total_time = 0
    for test_result in results["result"]:
        if test_result.state == TestStates.FAIL:
            exit_code = max(exit_code, ExitCodes.FAIL)
        elif test_result.state == TestStates.WARNING:
            exit_code = max(exit_code, ExitCodes.WARNING)
        result_str = "{} ... {}".format(test_result.name, str(test_result.state))
        print(result_str)
        total_time += test_result.elapsed_time
    print("----------------------------")
    print("Ran {} tests in ".format(len(results["result"])) + "{0:.3f}s".format(total_time) + "\r\n")
    return exit_code


def parse_arguments():
    parser = argparse.ArgumentParser(description='NMOS Test Suite')
    parser.add_argument('--suite', default=None, help="select a test suite to run tests from in non-interactive mode")
    parser.add_argument('--list', action='store_true', help="list available tests for a given suite")
    parser.add_argument('--selection', default="all", help="select a specific test to run, otherwise 'all' will be tested")
    parser.add_argument('--host', default=list(), nargs="*", help="space separated hostnames or IPs of the APIs under test")
    parser.add_argument('--port', default=list(), nargs="*", type=int, help="space separated ports of the APIs under test")
    parser.add_argument('--version', default=list(), nargs="*", help="space separated versions of the APIs under test")
    parser.add_argument('--ignore', default=list(), nargs="*", help="space separated test names to ignore the results from")
    parser.add_argument('--output', default=None, help="filename to save JUnit XML format test results to, otherwise print to stdout")
    return parser.parse_args()


def validate_args(args):
    if args.suite:
        if args.suite not in TEST_DEFINITIONS:
            print(" * ERROR: The requested test suite '{}' does not exist".format(args.suite))
            sys.exit(ExitCodes.ERROR)
        if args.list:
            tests = enumerate_tests(TEST_DEFINITIONS[args.suite]["class"])
            for test_name in tests:
                print(test_name)
            sys.exit(ExitCodes.OK)
        if args.selection and args.selection not in enumerate_tests(TEST_DEFINITIONS[args.suite]["class"]):
            print(" * ERROR: Test with name '{}' does not exist in test definition '{}'"
                  .format(args.selection, args.suite))
            sys.exit(ExitCodes.ERROR)
        if len(args.host) != len(args.port) or len(args.host) != len(args.version):
            print(" * ERROR: Hostnames/IPs, ports and versions must contain the same number of elements")
            sys.exit(ExitCodes.ERROR)
        if len(args.host) != len(TEST_DEFINITIONS[args.suite]["specs"]):
            print(" * ERROR: This test definition expects {} Hostnames/IP(s), port(s) and version(s)"
                  .format(len(TEST_DEFINITIONS[args.suite]["specs"])))
            sys.exit(ExitCodes.ERROR)


def start_web_servers():
    port = 5001
    for app in FLASK_APPS:
        t = threading.Thread(target=app.run, kwargs={'host': '0.0.0.0', 'port': port, 'threaded': True})
        t.daemon = True
        t.start()
        port += 1
    t = threading.Thread(target=core_app.run, kwargs={'host': '0.0.0.0', 'port': 5000, 'threaded': True})
    t.daemon = True
    t.start()


def run_noninteractive_tests(args):
    endpoints = []
    for i in range(len(args.host)):
        endpoints.append({"host": args.host[i], "port": args.port[i], "version": args.version[i]})
    try:
        results = run_tests(args.suite, endpoints, [args.selection])
        if args.output:
            exit_code = write_test_results(results, args)
        else:
            exit_code = print_test_results(results, args)
    except Exception as e:
        print(" * ERROR: {}".format(str(e)))
        exit_code = ExitCodes.ERROR
    return exit_code


class ExitCodes(IntEnum):
    ERROR = -1  # General test suite error
    OK = 0  # Normal exit condition, or all tests passed in non-interactive mode
    WARNING = 1  # Worst case test was a warning in non-interactive mode
    FAIL = 2  # Worst case test was a failure in non-interactive mode


if __name__ == '__main__':
    # Check if we're testing unicast DNS discovery, and if so ensure we have elevated privileges
    if ENABLE_DNS_SD and DNS_SD_MODE == "unicast":
        is_admin = False
        if platform.system() == "Windows":
            from ctypes import windll
            if windll.shell32.IsUserAnAdmin():
                is_admin = True
        elif os.geteuid() == 0:
            is_admin = True
        if not is_admin:
            print(" * ERROR: In order to test DNS-SD in unicast mode, the test suite must be run with elevated permissions")
            sys.exit(ExitCodes.ERROR)

    # Parse and validate command line arguments
    args = parse_arguments()
    validate_args(args)

    # Download up to date versions of each API specification
    init_spec_cache()

    # Start the DNS server
    if ENABLE_DNS_SD and DNS_SD_MODE == "unicast":
        DNS_SERVER = DNS()

    # Start the HTTP servers
    start_web_servers()

    exit_code = 0
    if not args.suite:
        # Interactive testing mode. Await user input.
        try:
            while True:
                time.sleep(0.2)
        except KeyboardInterrupt:
            pass
    else:
        # Non-interactive testing mode. Tests carried out automatically.
        exit_code = run_noninteractive_tests(args)

    # Testing complete
    print(" * Exiting")

    # Stop the DNS server
    if DNS_SERVER:
        DNS_SERVER.stop()

    # Exit the application with the desired code
    sys.exit(exit_code)
