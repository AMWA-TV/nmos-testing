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
from wtforms import Form, validators, StringField, SelectField

import argparse

import IS0401Test
import IS0501Test

app = Flask(__name__)
app.debug = True
app.config['SECRET_KEY'] = 'nmos-interop-testing-jtnm'

NODE_URL = "http://<node_ip>:<node_port>/x-nmos/node/v1.2/"


class DataForm(Form):
    url = StringField("Full URL: ", validators=[validators.DataRequired(message="URL is required"),
                                                validators.regexp(
                                                    "http:\/\/(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)([0-9]{1,4}|[1-5][0-9]{4}|6[0-4][0-9]{3}|65[0-4][0-9]{2}|655[0-2][0-9]|6553[0-5]):[0-9]{1,5}\/x-nmos\/(node\/v1.[0-2]|connection\/v1.0)\/$",
                                                    message="URL has to be in format: "
                                                            "http://<ip>:<port>/x-nmos/node/v1.[0-2]/ "
                                                            "for IS-04 or "
                                                            "http://<ip>:<port>/x-nmos/connection/v1.0/ "
                                                            "for IS-05 tests")],
                      default=NODE_URL)
    test = SelectField(label="Select test", choices=[("IS-04-01", "IS-04-01: Node"),
                                                     ("IS-05-01", "IS-05-01: API")])


@app.route('/', methods=["GET", "POST"])
def index_page():
    form = DataForm(request.form)
    if request.method == "POST":
        url = request.form["url"]
        test = request.form["test"]
        if form.validate():
            if test == "IS-04-01":
                test_obj = IS0401Test.IS0401Test(url, QUERY_URL)
                result = test_obj.run_tests()
                return render_template("result.html", url=url, test=test, result=result)
            elif test == "IS-05-01":
                test_obj = IS0501Test.IS0501Test(url)
                result = test_obj.run_tests()
                return render_template("result.html", url=url, test=test, result=result)
            else:
                return render_template("result.html", url=url, test=test, result="UKNOWN")
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
