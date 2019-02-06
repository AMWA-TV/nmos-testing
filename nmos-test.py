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
from Node import NODE, NODE_API
from Config import CACHE_PATH, SPECIFICATIONS, ENABLE_DNS_SD, DNS_SD_MODE
from datetime import datetime, timedelta
from dnslib.server import DNSServer
from dnslib.zoneresolver import ZoneResolver

import git
import os
import json
import copy
import pickle
import threading
import sys
import netifaces

import IS0401Test
import IS0402Test
import IS0403Test
import IS0501Test
import IS0502Test
import IS0601Test
import IS0701Test
import IS0801Test

FLASK_APPS = []

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
    tests = []
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
        test_data[test_id]["tests"] = ["all", "auto"] + enumerate_tests(TEST_DEFINITIONS[test_id]["class"])

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
            if test in TEST_DEFINITIONS:
                test_def = TEST_DEFINITIONS[test]
                apis = {}
                spec_count = 0
                for spec in test_def["specs"]:
                    ip = request.form["endpoints-{}-ip".format(spec_count)]
                    port = request.form["endpoints-{}-port".format(spec_count)]
                    version = request.form["endpoints-{}-version".format(spec_count)]
                    base_url = "http://{}:{}".format(ip, str(port))

                    spec_key = spec["spec_key"]
                    api_key = spec["api_key"]
                    apis[api_key] = {
                        "raml": SPECIFICATIONS[spec_key]["apis"][api_key]["raml"],
                        "base_url": base_url,
                        "url": "{}/x-nmos/{}/{}/".format(base_url, api_key, version),
                        "spec_path": CACHE_PATH + '/' + spec_key,
                        "version": version,
                        "spec": None  # Used inside GenericTest
                    }

                    spec_count += 1

                test_selection = request.form["test_selection"]

                # Instantiate the test class
                test_obj = None
                if test == "IS-04-01":
                    # This test has an unusual constructor as it requires a registry instance
                    test_obj = test_def["class"](apis, REGISTRIES, NODE)
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
                return render_template("result.html", url=base_url, test=test_def["name"], result=result)
            else:
                flash("Error: This test definition does not exist")
        else:
            flash("Error: {}".format(form.errors))
    elif request.method == "POST":
        flash("Error: A test is currently in progress. Please wait until it has completed or restart the testing tool.")

    return render_template("index.html", form=form)


if __name__ == '__main__':
    if ENABLE_DNS_SD and DNS_SD_MODE == "unicast" and os.geteuid() != 0:
        print(" * ERROR: In order to test DNS-SD in unicast mode, the test suite must be run with elevated permissions")
        sys.exit(1)

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

    port = 5001
    for app in FLASK_APPS:
        t = threading.Thread(target=app.run, kwargs={'host': '0.0.0.0', 'port': port, 'threaded': True})
        t.daemon = True
        t.start()
        port += 1

    dns_server = None
    if ENABLE_DNS_SD and DNS_SD_MODE == "unicast":
        print(" * Starting DNS server")
        default_gw_interface = netifaces.gateways()['default'][netifaces.AF_INET][1]
        default_ip = netifaces.ifaddresses(default_gw_interface)[netifaces.AF_INET][0]['addr']
        zone_file = open("test_data/IS0401/dns.zone").read()
        zone_file.replace("127.0.0.1", default_ip)
        resolver = ZoneResolver(zone_file)
        try:
            dns_server = DNSServer(resolver, port=53, address="0.0.0.0")
            dns_server.start_thread()
        except Exception as e:
            print(" * ERROR: Unable to bind to port 53. DNS server could not start: {}".format(e))

    # This call will block until interrupted
    core_app.run(host='0.0.0.0', port=5000, threaded=True)

    print(" * Exiting")
    if dns_server:
        dns_server.stop()
