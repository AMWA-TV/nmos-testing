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
from wtforms import Form, validators, StringField, SelectField, IntegerField, HiddenField
from Registry import REGISTRY, REGISTRY_API

import git
import os
import json
import copy

import IS0401Test
import IS0402Test
import IS0501Test
import IS0601Test
import IS0701Test

app = Flask(__name__)
app.debug = True  # TODO: Set to False for production use
app.config['SECRET_KEY'] = 'nmos-interop-testing-jtnm'
app.config['TEST_ACTIVE'] = False
app.register_blueprint(REGISTRY_API)  # Dependency for IS0401Test

CACHE_PATH = 'cache'
SPEC_REPOS = [
    ('is-04', 'nmos-discovery-registration'),
    ('is-05', 'nmos-device-connection-management'),
    ('is-06', 'nmos-network-control'),
    ('is-07', 'nmos-event-tally')
]
TEST_DEFINITIONS = {
    "IS-04-01": {"name": "IS-04 Node API",
                 "versions": ["v1.0", "v1.1", "v1.2", "v1.3"],
                 "default_version": "v1.2",
                 "input_labels": ["Node API"],
                 "spec_key": 'is-04',
                 "class": IS0401Test.IS0401Test},
    "IS-04-02": {"name": "IS-04 Registry APIs",
                 "versions": ["v1.0", "v1.1", "v1.2", "v1.3"],
                 "default_version": "v1.2",
                 "input_labels": ["Registration API", "Query API"],
                 "spec_key": 'is-04',
                 "class": IS0402Test.IS0402Test},
    "IS-05-01": {"name": "IS-05 Connection Management API",
                 "versions": ["v1.0", "v1.1"],
                 "default_version": "v1.0",
                 "input_labels": ["Connection API"],
                 "spec_key": 'is-05',
                 "class": IS0501Test.IS0501Test},
    "IS-06-01": {"name": "IS-06 Network Control API",
                 "versions": ["v1.0"],
                 "default_version": "v1.0",
                 "input_labels": ["Network API"],
                 "spec_key": 'is-06',
                 "class": IS0601Test.IS0601Test},
    "IS-07-01": {"name": "IS-07 Event & Tally API",
                 "versions": ["v1.0"],
                 "default_version": "v1.0",
                 "input_labels": ["Event API"],
                 "spec_key": 'is-07',
                 "class": IS0701Test.IS0701Test}
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

class DataForm(Form):
    choices = [(test_id, TEST_DEFINITIONS[test_id]["name"]) for test_id in TEST_DEFINITIONS]
    choices = sorted(choices, key=lambda x: x[0])
    test = SelectField(label="Select test:", choices=choices)
    ip = StringField(label="IP:", validators=[validators.IPAddress(message="Please enter a valid IPv4 address.")])
    port = IntegerField(label="Port:", validators=[validators.NumberRange(min=0, max=65535,
                                                                          message="Please enter a valid port number "
                                                                                  "(0-65535).")])
    ip_sec = StringField(label="IP:", validators=[validators.IPAddress(message="Please enter a valid IPv4 address."),
                                                  validators.optional()])
    port_sec = IntegerField(label="Port:", validators=[validators.NumberRange(min=0, max=65535,
                                                                              message="Please enter a valid port "
                                                                                      "number (0-65535)."),
                                                       validators.optional()])
    version = SelectField(label="API Version:", choices=[("v1.0", "v1.0"),
                                                         ("v1.1", "v1.1"),
                                                         ("v1.2", "v1.2"),
                                                         ("v1.3", "v1.3")])
    test_selection = NonValidatingSelectField(label="Test Selection:", choices=[("all", "all"),
                                                                                ("auto", "auto")])

    # Hide test data in the web form for dynamic modification of behaviour
    hidden_data = {}
    for test_id in TEST_DEFINITIONS:
        hidden_data[test_id] = copy.copy(TEST_DEFINITIONS[test_id])
        hidden_data[test_id].pop("class")
        hidden_data[test_id]["tests"] = ["all", "auto"] + enumerate_tests(TEST_DEFINITIONS[test_id]["class"])
    hidden = HiddenField(default=json.dumps(hidden_data))


# Index page
@app.route('/', methods=["GET", "POST"])
def index_page():
    form = DataForm(request.form)
    if request.method == "POST" and not app.config['TEST_ACTIVE']:
        test = request.form["test"]
        ip = request.form["ip"]
        port = request.form["port"]
        ip_sec = request.form["ip_sec"]
        port_sec = request.form["port_sec"]
        version = request.form["version"]
        test_selection = request.form["test_selection"]
        base_url = "http://{}:{}".format(ip, str(port))
        base_url_sec = "http://{}:{}".format(ip_sec, str(port_sec))
        if form.validate():
            if test in TEST_DEFINITIONS:
                spec_versions = TEST_DEFINITIONS[test]["versions"]
                spec_path = CACHE_PATH + '/' + TEST_DEFINITIONS[test]["spec_key"]

            if test == "IS-04-01":
                apis = {"node": {"raml": "NodeAPI.raml",
                                 "base_url": base_url,
                                 "url": "{}/x-nmos/node/{}/".format(base_url, version)}}
                test_obj = IS0401Test.IS0401Test(apis, spec_versions, version, spec_path, REGISTRY)
            elif test == "IS-04-02":
                apis = {"registration": {"raml": "RegistrationAPI.raml",
                                         "base_url": base_url,
                                         "url": "{}/x-nmos/registration/{}/".format(base_url, version)},
                        "query": {"raml": "QueryAPI.raml",
                                  "base_url": base_url_sec,
                                  "url": "{}/x-nmos/query/{}/".format(base_url_sec, version)}}
                test_obj = IS0402Test.IS0402Test(apis, spec_versions, version, spec_path)
            elif test == "IS-05-01":
                apis = {"connection": {"raml": "ConnectionAPI.raml",
                                       "base_url": base_url,
                                       "url": "{}/x-nmos/connection/{}/".format(base_url, version)}}
                test_obj = IS0501Test.IS0501Test(apis, spec_versions, version, spec_path)
            elif test == "IS-06-01":
                apis = {"netctrl": {"raml": "NetworkControlAPI.raml",
                                    "base_url": base_url,
                                    "url": "{}/x-nmos/netctrl/{}/".format(base_url, version)}}
                test_obj = IS0601Test.IS0601Test(apis, spec_versions, version, spec_path)
            elif test == "IS-07-01":
                apis = {"events": {"raml": "EventsAPI.raml",
                                   "base_url": base_url,
                                   "url": "{}/x-nmos/events/{}/".format(base_url, version)}}
                test_obj = IS0701Test.IS0701Test(apis, spec_versions, version, spec_path)

            if test_obj:
                app.config['TEST_ACTIVE'] = True
                try:
                    result = test_obj.run_tests(test_selection)
                except Exception as ex:
                    print(" * ERROR: {}".format(ex))
                    raise ex
                finally:
                    app.config['TEST_ACTIVE'] = False
                return render_template("result.html", url=base_url, test=test, result=result)
        else:
            flash("Error: {}".format(form.errors))
    elif request.method == "POST":
        flash("Error: A test is currently in progress. Please wait until it has completed or restart the testing tool.")

    return render_template("index.html", form=form)


if __name__ == '__main__':
    print(" * Initialising specification repositories...")

    if not os.path.exists(CACHE_PATH):
        os.makedirs(CACHE_PATH)

    for repo_data in SPEC_REPOS:
        path = os.path.join(CACHE_PATH + '/' + repo_data[0])
        if not os.path.exists(path):
            repo = git.Repo.clone_from('https://github.com/AMWA-TV/' + repo_data[1] + '.git', path)
        else:
            repo = git.Repo(path)
            repo.git.reset('--hard')
            if not app.debug:
                repo.remotes.origin.pull()

    print(" * Initialisation complete")

    app.run(host='0.0.0.0', threaded=True)
