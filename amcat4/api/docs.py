from flask import Blueprint, render_template

import amcat4.api.query
from amcat4.api.common import auto

app_docs = Blueprint('app_docs', __name__)


def context():
    rules = auto.generate()
    groups = [
        {"group": "Querying", "title": " Querying", "doc": amcat4.api.query.__doc__},
        {"group": "index", "title": "Documents", "doc": amcat4.api.index.__doc__},
        {"group": "auth", "title": "Authentication", "doc": amcat4.api.users.__doc__},
        {"group": "users", "title": "Users", "doc": amcat4.api.users.__doc__},
    ]
    for rule in rules:
        rule['method'] = "/".join(set(rule['methods']) & {"POST", "GET", "DELETE", "PUT"})
    for group in groups:
        group["rules"] = [rule for rule in rules if rule.get('group') == group['group']]
    return locals()


def docs_html():
    return render_template("docs.html", **context())


def docs_md():
    return render_template("docs.md", **context())


@app_docs.route("/", methods=['GET'])
def docs():
    return docs_html()
