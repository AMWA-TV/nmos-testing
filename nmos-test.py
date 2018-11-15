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
from Registry import REGISTRY, REGISTRY_API

import git
import os
import json
import copy

import IS0401Test
import IS0402Test
import IS0501Test
import IS0401_0501Test
import IS0601Test
import IS0701Test

app = Flask(__name__)
app.debug = True  # TODO: Set to False for production use
app.config['SECRET_KEY'] = 'nmos-interop-testing-jtnm'
app.config['TEST_ACTIVE'] = False
app.register_blueprint(REGISTRY_API)  # Dependency for IS0401Test

CACHE_PATH = 'cache'
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
    }
}
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
    "IS-05-01": {
        "name": "IS-05 Connection Management API",
        "specs": [{
            "spec_key": 'is-05',
            "api_key": "connection"
        }],
        "class": IS0501Test.IS0501Test
    },
    "IS-05-01-04-1": {
        "name": "IS-05 Integration with Node API",
        "specs": [{
            "spec_key": "is-04",
            "api_key": "node"
        }, {
            "spec_key": "is-05",
            "api_key": "connection"
        }],
        "class": IS0401_0501Test.IS04010501Test
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
@app.route('/', methods=["GET", "POST"])
def index_page():
    form = DataForm(request.form)
    if request.method == "POST" and not app.config['TEST_ACTIVE']:
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
                        "spec_versions": SPECIFICATIONS[spec_key]["versions"],
                        "spec_path": CACHE_PATH + '/' + spec_key,
                        "version": version
                    }

                    if spec_count == 0:
                        spec_versions = SPECIFICATIONS[spec_key]["versions"]
                        spec_path = CACHE_PATH + '/' + spec_key
                        api_version = version

                    spec_count += 1

                test_selection = request.form["test_selection"]

                if test == "IS-04-01":
                    test_obj = IS0401Test.IS0401Test(apis, spec_versions, api_version, spec_path, REGISTRY)
                elif test == "IS-04-02":
                    test_obj = IS0402Test.IS0402Test(apis, spec_versions, api_version, spec_path)
                elif test == "IS-05-01":
                    test_obj = IS0501Test.IS0501Test(apis, spec_versions, api_version, spec_path)
                elif test == "IS-06-01":
                    test_obj = IS0601Test.IS0601Test(apis, spec_versions, api_version, spec_path)
                elif test == "IS-07-01":
                    test_obj = IS0701Test.IS0701Test(apis, spec_versions, api_version, spec_path)

                if test_obj:
                    app.config['TEST_ACTIVE'] = True
                    try:
                        result = test_obj.run_tests(test_selection)
                    except Exception as ex:
                        raise ex
                    finally:
                        app.config['TEST_ACTIVE'] = False
                    return render_template("result.html", url=base_url, test=test, result=result)
            else:
                flash("Error: This test definition does not exist")
        else:
            flash("Error: {}".format(form.errors))
    elif request.method == "POST":
        flash("Error: A test is currently in progress. Please wait until it has completed or restart the testing tool.")

    return render_template("index.html", form=form)


if __name__ == '__main__':
    print(" * Initialising specification repositories...")

    if not os.path.exists(CACHE_PATH):
        os.makedirs(CACHE_PATH)

    for repo_key, repo_data in SPECIFICATIONS.items():
        path = os.path.join(CACHE_PATH + '/' + repo_key)
        if not os.path.exists(path):
            repo = git.Repo.clone_from('https://github.com/AMWA-TV/' + repo_data["repo"] + '.git', path)
        else:
            repo = git.Repo(path)
            repo.git.reset('--hard')
            if not app.debug:
                repo.remotes.origin.pull()

    print(" * Initialisation complete")

    app.run(host='0.0.0.0', threaded=True)
