from pathlib import Path

from amcat4annotator.api import app_annotator
from flask import Flask
from flask_cors import CORS

from amcat4.api.common import MyJSONEncoder, auto
from amcat4.api.docs import app_docs
from amcat4.api.index import app_index
from amcat4.api.query import app_query
from amcat4.api.users import app_users

template_path = (Path(__file__) / "../../../templates").resolve()
app = Flask(__name__, template_folder=str(template_path))
auto.init_app(app)

app.json_encoder = MyJSONEncoder
CORS(app)
app.register_blueprint(app_index)
app.register_blueprint(app_query)
app.register_blueprint(app_users)
app.register_blueprint(app_docs)

# "Plugins"
app.register_blueprint(app_annotator, url_prefix='/annotator')

