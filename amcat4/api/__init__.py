
from flask import Flask
from flask_cors import CORS

from amcat4.api.common import MyJSONEncoder
from amcat4.api.query import app_query
from amcat4.api.users import app_users
from amcat4.api.index import app_index

app = Flask(__name__)
app.json_encoder = MyJSONEncoder
CORS(app)
app.register_blueprint(app_index)
app.register_blueprint(app_query)
app.register_blueprint(app_users)
