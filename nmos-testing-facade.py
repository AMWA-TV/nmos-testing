# Copyright (C) 2021 Advanced Media Workflow Association
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

import random
import requests
import json
import time
from flask import Flask, render_template, make_response, request
from flask_socketio import SocketIO
from testingfacade.DataStore import data
from nmostesting import Config as CONFIG

app = Flask(__name__, static_folder="testingfacade/static", template_folder="testingfacade/templates")
socketio = SocketIO(app)

CACHEBUSTER = random.randint(1, 10000)


@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'GET':
        if data.getStatus() == 'Test':
            r = make_response(render_template("index.html", test_type=data.getTest(), question=data.getQuestion(),
                                              answers=data.getAnswers(), name=data.getName(),
                                              description=data.getDescription(), response_url=data.getUrl(),
                                              time_received=data.getTime(), timeout=data.getTimeout(),
                                              all_data=data.getJson(), cachebuster=CACHEBUSTER))
        else:
            r = make_response(render_template("index.html", question=None, answers=None,
                                              name=None, description=None, cachebuster=CACHEBUSTER))
        r.headers['Cache-Control'] = 'no-cache, no-store'
        return r

    else:
        form = request.form.to_dict()
        json_data = json.loads(form['all_data'])
        answer_json = {'question_id': json_data['question_id'], 'answer_response': None}

        if 'answer' in form:
            if json_data['test_type'] == 'multi_choice':
                answer_json['answer_response'] = request.form.getlist('answer')
            elif json_data['test_type'] == 'single_choice':
                answer_json['answer_response'] = form['answer']

        if 'answer' in form or 'Next' in form or 'all_data' in form:
            # POST to test suite to confirm answer available
            valid, response = do_request('POST', form['response_url'], json=answer_json)

            return response.reason, response.status_code

        return 'Unexpected form data', 400


@app.route('/x-nmos/testquestion/<version>', methods=['POST'], strict_slashes=False)
def testing_facade_post(version):
    # Should be json from Test Suite with questions
    json_list = ['test_type', 'question_id', 'name', 'description', 'question', 'answers', 'answer_uri']
    json_data = request.json
    json_data['time_received'] = time.time()

    if 'clear' in json_data and json_data['clear'] == 'True':
        # End of current tests, clear data store
        data.clear()
    else:
        # Should be a new question
        for entry in json_list:
            if entry not in request.json:
                return "Missing {}".format(entry), 400
        # All required entries are present so update data
        data.setJson(json_data)

    socketio.emit('update', json_data)

    return '', 202


def do_request(method, url, **kwargs):
    """Perform a basic HTTP request with appropriate error handling"""
    try:
        s = requests.Session()
        # The only place we add headers is auto OPTIONS for CORS, which should not check Auth
        if "headers" in kwargs and kwargs["headers"] is None:
            del kwargs["headers"]

        req = requests.Request(method, url, **kwargs)
        prepped = s.prepare_request(req)
        settings = s.merge_environment_settings(prepped.url, {}, None, None, None)
        response = s.send(prepped, timeout=1, **settings)
        if prepped.url.startswith("https://"):
            if not response.url.startswith("https://"):
                return False, "Redirect changed protocol"
            if response.history is not None:
                for res in response.history:
                    if not res.url.startswith("https://"):
                        return False, "Redirect changed protocol"
        return True, response
    except requests.exceptions.Timeout:
        return False, "Connection timeout"
    except requests.exceptions.TooManyRedirects:
        return False, "Too many redirects"
    except requests.exceptions.ConnectionError as e:
        return False, str(e)
    except requests.exceptions.RequestException as e:
        return False, str(e)


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=CONFIG.TESTING_FACADE_PORT)
    socketio.run(app)
