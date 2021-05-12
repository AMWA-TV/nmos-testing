import random
import requests
from flask import Flask, render_template, make_response, abort, request
from wtforms import Form, validators, StringField, IntegerField

CACHEBUSTER = random.randint(1, 10000)

app = Flask(__name__)

@app.route('/', methods=['GET', 'POST'])
def index():

    form = EndpointForm(request.form)
    test_selection = {}
    test_url = ''

    if request.method == 'POST':
        if form.validate():
            test_url = "http://{}:{}".format(request.form['host'], str(request.form['port']))

            valid, response = do_request("GET", test_url)
            if not valid:
                raise NMOSInitException("No API found at {}".format(test_url))
            elif response.status_code != 200:
                raise NMOSInitException("No API found or unexpected error at {} ({})".format(test_url, response.status_code))
            else:
                valid, test_list = do_request("GET", test_url + '/test_selection')

                test_selection = test_list.json()
    else:
        host = ''
        port = ''

    r = make_response(render_template("index.html", form=form, test_url=test_url, 
                                      tests=test_selection, 
                                      cachebuster=CACHEBUSTER))
    r.headers['Cache-Control'] = 'no-cache, no-store'

    return r



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


class EndpointForm(Form):
    host = StringField(label="Test Suite IP/Hostname:", validators=[validators.optional()])
    port = IntegerField(label="Port:", validators=[validators.NumberRange(min=0, max=65535,
                                                                          message="Please enter a valid port number "
                                                                                  "(0-65535)."),
                                                   validators.optional()])
                                            