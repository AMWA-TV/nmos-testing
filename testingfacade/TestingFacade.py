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
from flask import Flask, render_template, make_response, abort, request, Response, url_for
from DataStore import data


CACHEBUSTER = random.randint(1, 10000)

app = Flask(__name__)

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'GET':
        if data.getStatus() == 'Test':
            r = make_response(render_template("index.html", test_type=data.getTest(), question=data.getQuestion(), 
                                              answers=data.getAnswers(), name=data.getName(), 
                                              description=data.getDescription(), response_url=data.getUrl(),
                                              time_sent=data.getTime(), timeout=data.getTimeout(),
                                              all_data=data.getJson(), cachebuster=CACHEBUSTER))
        else:
            r = make_response(render_template("index.html", question=None, answers=None, 
                                              name=None, description=None, cachebuster=CACHEBUSTER))
        r.headers['Cache-Control'] = 'no-cache, no-store'
        return r

    else:
        form = request.form.to_dict()

        if 'answer' in form:
            json_data = json.loads(form['all_data'])

            if json_data['test_type'] == 'checkbox':
                json_data['answer_response'] = request.form.getlist('answer')
            else:    
                json_data['answer_response'] = form['answer']

            json_data['time_answered'] = time.time()

            # POST to test suite to confirm answer available
            valid, response = do_request('POST', form['response_url'], json=json_data)
        elif 'Next' in form:
            # Test question was instuctions to be confirmed
            json_data = json.loads(form['all_data'])
            json_data['answer_response'] = 'Next'
            json_data['time_answered'] = time.time()
            # POST to test suite to confirm answer available
            valid, response = do_request('POST', form['response_url'], json=json_data)
        else:
            if 'all_data' in form:
                # Form was submitted but no answer(s) chosen
                valid, response = do_request('POST', form['response_url'], json=json.loads(form['all_data']))
            return False, "No answer submitted"

        return 'Answer set'

@app.route('/x-nmos/testing-facade/<version>', methods=['POST'], strict_slashes=False)
def testing_facade_post(version):
    # Should be json from Test Suite with questions
    json_list = ['test_type', 'name', 'description', 'question', 'answers', 'time_sent', 'url_for_response']

    if 'clear' in request.json and request.json['clear'] == 'True':
        # End of current tests, clear data store
        data.clear()
    elif 'answer_response' in request.json and request.json['answer_response'] != "":
        # Answer was given, check details compared to question POST to verify answering correct question
        for entry in json_list:
            method = getattr(data, 'get' + entry.split('_')[0].capitalize())
            current = method()
            if current != request.json[entry]:
                return False, "{} : {} doesn't match current question details".format(entry, request.json[entry])
        # All details are consistent so update the data store to contain the answer
        data.setAnswer(request.json['answer_response'])
        # POST to test suite to indicate answer has been set
        valid, response = do_request('POST', request.json['url_for_response'], json={})
    else:
        # Should be a new question
        for entry in json_list:
            if entry not in request.json:
                return False, "Missing {}".format(entry)
        # All required entries are present so update data
        data.setJson(request.json)
    return 'OK'

@app.route('/controller_questions/', methods=['GET'], strict_slashes=False)
def controller_questions_get():
    return Response(data.getJson(), mimetype='application/json')


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
    app.run(host='0.0.0.0', port=5001)