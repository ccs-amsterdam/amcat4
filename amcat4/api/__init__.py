
from flask import Flask, jsonify, g
from flask_cors import CORS

from amcat4.api.common import multi_auth, MyJSONEncoder
from amcat4.api.query import app_query
from .index import app_index

app = Flask(__name__)
app.json_encoder = MyJSONEncoder
CORS(app)
app.register_blueprint(app_index)
app.register_blueprint(app_query)


@app.route("/auth/token/", methods=['GET'])
@multi_auth.login_required
def get_token():
    """
    Create a new token for the authenticated user
    """
    token = g.current_user.create_token()
    return jsonify({"token": token.decode('ascii')})

