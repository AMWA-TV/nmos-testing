# Copyright (C) 2018 Riedel Communications GmbH & Co. KG
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
from wtforms import Form, validators, StringField, SelectField, IntegerField

import argparse

import IS0401Test
import IS0501Test

app = Flask(__name__)
app.debug = True
app.config['SECRET_KEY'] = 'nmos-interop-testing-jtnm'

NODE_URL = "http://<node_ip>:<node_port>/x-nmos/node/v1.2/"


class DataForm(Form):
    test = SelectField(label="Select test:", choices=[("IS-04-01", "IS-04-01: Node API"), ("IS-05-01", "IS-05-01: ConnectionMgmt API")])
    ip = StringField(label="Ip:", validators=[validators.IPAddress(message="Please enter a valid IPv4 address.")])
    port = IntegerField(label="Port:", validators=[validators.NumberRange(min=0, max=65535,
                                                                          message="Please enter a valid port number (0-65535).")])
    version = SelectField(label="API Version:", choices=[("v1.0", "v1.0"),
                                                        ("v1.1", "v1.1"),
                                                        ("v1.2", "v1.2")])


@app.route('/', methods=["GET", "POST"])
def index_page():
    form = DataForm(request.form)
    if request.method == "POST":
        test = request.form["test"]
        ip = request.form["ip"]
        port = request.form["port"]
        version = request.form["version"]
        if form.validate():
            if test == "IS-04-01":
                url = "http://{}:{}/x-nmos/node/{}/".format(ip, str(port), version)
                test_obj = IS0401Test.IS0401Test(url, QUERY_URL)
                result = test_obj.run_tests()
                return render_template("result.html", url=url, test=test, result=result)
            else:  # test == "IS-05-01"
                url = "http://{}:{}/x-nmos/connection/{}/".format(ip, str(port), version)
                test_obj = IS0501Test.IS0501Test(url)
                result = test_obj.run_tests()
                return render_template("result.html", url=url, test=test, result=result)
        else:
            flash("Error: {}".format(form.errors))

    return render_template("index.html", form=form)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Riedel NMOS Interop Test Tool")
    parser.add_argument("--query_ip", help="String. IPv4 address of the query service (RDS).", required=True)
    parser.add_argument("--query_port", help="Integer. Port of the query service (RDS).", required=True)
    args = parser.parse_args()
    QUERY_URL = "http://{}:{}/x-nmos/query".format(args.query_ip, args.query_port)
    app.run(host='0.0.0.0')
