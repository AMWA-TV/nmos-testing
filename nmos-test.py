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

from flask import Flask, render_template, flash, request
from wtforms import Form, validators, StringField, SelectField, IntegerField, HiddenField, FormField, FieldList
from Registry import NUM_REGISTRIES, REGISTRIES, REGISTRY_API
from GenericTest import NMOSInitException
from Node import NODE, NODE_API
from Config import CACHE_PATH, SPECIFICATIONS, ENABLE_DNS_SD, DNS_SD_MODE
from DNS import DNS
from datetime import datetime, timedelta
from junit_xml import TestSuite, TestCase

import git
import os
import json
import copy
import pickle
import threading
import sys
import platform
import argparse
import time

import IS0401Test
import IS0402Test
import IS0403Test
import IS0501Test
import IS0502Test
import IS0601Test
import IS0701Test
import IS0801Test

FLASK_APPS = []
DNS_SERVER = None

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


class EndpointForm(Form):
    ip = StringField(label="IP:", validators=[validators.IPAddress(message="Please enter a valid IPv4 address."),
                                              validators.optional()])
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
    test = SelectField(label="Select test:", choices=test_choices)

    # Determine how many sets of IP/Port/Version to display at most
    specs_per_test = [(test_id, TEST_DEFINITIONS[test_id]["specs"]) for test_id in TEST_DEFINITIONS]
    specs_per_test = sorted(specs_per_test, key=lambda x: x[0])
    max_endpoints = 0
    for spec in specs_per_test:
        if len(spec) > max_endpoints:
            max_endpoints = len(spec)
    endpoints = FieldList(FormField(EndpointForm, label=""), min_entries=max_endpoints)

    # Define the secondary test selection dropdown
    test_selection = NonValidatingSelectField(label="Test Selection:", choices=[("all", "all"),
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
                        ip = request.form["endpoints-{}-ip".format(index)]
                        port = request.form["endpoints-{}-port".format(index)]
                        version = request.form["endpoints-{}-version".format(index)]
                        endpoints.append({"ip": ip, "port": port, "version": version})

                    test_selection = request.form["test_selection"]
                    results = run_test(test, endpoints, test_selection)
                    return render_template("result.html", url=results["base_url"], test=results["name"], result=results["result"])
                else:
                    raise flash("Error: This test definition does not exist")
            except Exception as e:
                flash("Error: {}".format(e))
        else:
            flash("Error: {}".format(form.errors))
    elif request.method == "POST":
        flash("Error: A test is currently in progress. Please wait until it has completed or restart the testing tool.")

    return render_template("index.html", form=form)


def run_test(test, endpoints, test_selection="all"):
    if test in TEST_DEFINITIONS:
        test_def = TEST_DEFINITIONS[test]
        apis = {}
        for index, spec in enumerate(test_def["specs"]):
            base_url = "http://{}:{}".format(endpoints[index]["ip"], str(endpoints[index]["port"]))
            spec_key = spec["spec_key"]
            api_key = spec["api_key"]
            apis[api_key] = {
                "raml": SPECIFICATIONS[spec_key]["apis"][api_key]["raml"],
                "base_url": base_url,
                "url": "{}/x-nmos/{}/{}/".format(base_url, api_key, endpoints[index]["version"]),
                "spec_path": CACHE_PATH + '/' + spec_key,
                "version": endpoints[index]["version"],
                "spec": None  # Used inside GenericTest
            }

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
                except Exception as e:
                    print(" * ERROR: Unable to update repository '{}'. If the problem persists, "
                          "please delete the '{}' directory".format(repo_data["repo"], CACHE_PATH))

    if update_last_pull:
        try:
            with open(last_pull_file, "wb") as f:
                pickle.dump(time_now, f)
        except Exception as e:
            print(" * ERROR: Unable to write last pull time to file: {}".format(e))

    print(" * Initialisation complete")


if __name__ == '__main__':
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
            sys.exit(1)

    parser = argparse.ArgumentParser(description='NMOS Test Suite')
    parser.add_argument('--suite', default=None, help="select a test suite to run tests from in non-interactive mode")
    parser.add_argument('--list', action='store_true', help="list available tests for a given suite")
    parser.add_argument('--selection', default="all", help="select a specific test to run, otherwise 'all' will be tested")
    parser.add_argument('--ip', default=list(), nargs="*", help="space separated IP addresses of the APIs under test")
    parser.add_argument('--port', default=list(), nargs="*", type=int, help="space separated ports of the APIs under test")
    parser.add_argument('--version', default=list(), nargs="*", help="space separated versions of the APIs under test")

    args = parser.parse_args()

    if args.suite:
        if args.suite not in TEST_DEFINITIONS:
            print(" * ERROR: The requested test suite '{}' does not exist".format(args.suite))
            sys.exit(-1)
        if args.list:
            tests = enumerate_tests(TEST_DEFINITIONS[args.suite]["class"])
            for test_name in tests:
                print(test_name)
            sys.exit(0)
        if args.selection and args.selection not in enumerate_tests(TEST_DEFINITIONS[args.suite]["class"]):
            print(" * ERROR: Test with name '{}' does not exist in test definition '{}'"
                  .format(args.selection, args.suite))
            sys.exit(-1)
        if len(args.ip) != len(args.port) != len(args.version):
            print(" * ERROR: IPs, ports and versions must contain the same number of elements")
            sys.exit(-1)
        if len(args.ip) != len(TEST_DEFINITIONS[args.suite]["specs"]):
            print(" * ERROR: This test definition expects {} IP(s), port(s) and version(s)"
                  .format(len(TEST_DEFINITIONS[args.suite]["specs"])))
            sys.exit(-1)

    init_spec_cache()

    port = 5001
    for app in FLASK_APPS:
        t = threading.Thread(target=app.run, kwargs={'host': '0.0.0.0', 'port': port, 'threaded': True})
        t.daemon = True
        t.start()
        port += 1

    if ENABLE_DNS_SD and DNS_SD_MODE == "unicast":
        DNS_SERVER = DNS()

    # This call will block until interrupted
    t = threading.Thread(target=core_app.run, kwargs={'host': '0.0.0.0', 'port': 5000, 'threaded': True})
    t.daemon = True
    t.start()

    exit_code = 0  # Worst result. PASS=0, WARN=1, FAIL=2 etc. -1 = other general suite error
    if not args.suite:
        try:
            while True:
                time.sleep(0.2)
        except KeyboardInterrupt:
            pass
    else:
        endpoints = []
        for i in range(len(args.ip)):
            endpoints.append({"ip": args.ip[i], "port": args.port[i], "version": args.version[i]})
        results = run_test(args.suite, endpoints, args.selection)
        test_cases = []
        for test_result in results["result"]:
            test_case = TestCase(test_result[0], elapsed_sec=float(test_result[7].rstrip("s")), timestamp=test_result[6])
            if test_result[1] in ["Manual", "Not Applicable", "Not Implemented"]:
                test_case.add_skipped_info(test_result[4])
            elif test_result[1] in ["Fail"]:
                test_case.add_failure_info(test_result[4], failure_type=test_result[1])
                exit_code = max(exit_code, 2)
            elif test_result[1] in ["Warning"]:
                test_case.add_error_info(test_result[4], error_type=test_result[1])
                exit_code = max(exit_code, 1)
            elif test_result[1] in ["Test Disabled", "Could Not Test"]:
                test_case.is_enabled = False
            elif test_result[1] != "Pass":
                test_case.add_error_info(test_result[4], error_type=test_result[1])
            test_cases.append(test_case)

        ts = TestSuite(results["name"] + ": " + results["base_url"], test_cases)
        file_name = "results.xml"
        with open(file_name, "w") as f:
            TestSuite.to_file(f, [ts], prettyprint=False)
            print(" * Test results written to file: {}".format(file_name))

    print(" * Exiting")
    if DNS_SERVER:
        DNS_SERVER.stop()
    sys.exit(exit_code)
