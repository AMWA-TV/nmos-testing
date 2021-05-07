import random
from flask import Flask, render_template, make_response, abort


CACHEBUSTER = random.randint(1, 10000)

app = Flask(__name__)

@app.route('/', methods=['GET'])
def index():
    r = make_response(render_template("index.html", cachebuster=CACHEBUSTER))
    r.headers['Cache-Control'] = 'no-cache, no-store'

    return r