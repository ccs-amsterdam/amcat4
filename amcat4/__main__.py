"""
AmCAT4 REST API
"""
import csv
import io
import logging
import sys
import urllib.request
import argparse

from amcat4 import auth
from amcat4.api import app
from amcat4.api.common import MyJSONEncoder
from amcat4.api.docs import docs_html, docs_md, context
from amcat4.auth import Role, User
from amcat4.db import initialize_if_needed
from amcat4.elastic import setup_elastic, upload_documents
from amcat4.index import create_index, Index

SOTU_INDEX = "state_of_the_union"


def upload_test_data() -> Index:
    url = "https://raw.githubusercontent.com/ccs-amsterdam/example-text-data/master/sotu.csv"
    url_open = urllib.request.urlopen(url)
    csv.field_size_limit(sys.maxsize)
    csvfile = csv.DictReader(io.TextIOWrapper(url_open, encoding='utf-8'))

    # creates the index info on the sqlite db
    index = create_index(SOTU_INDEX)

    docs = [dict(title="{Year}: {President}".format(**row),
                 text=row['Text'],
                 date=row['Date'],
                 president=row['President'],
                 year=row['Year'],
                 party=row['Party'])
            for row in csvfile]
    columns = {"president": "keyword", "party": "keyword", "year": "int"}
    upload_documents(SOTU_INDEX, docs, columns)
    return index


def run(args):
    logging.info(f"Starting server at port {args.port}, debug={not args.nodebug}")
    app.run(debug=not args.nodebug, port=args.port)


def create_test_index(_args):
    if Index.select().where(Index.name == SOTU_INDEX):
        print(f"Index {SOTU_INDEX} already exists")
        return
    logging.info("**** Creating test index {} ****".format(SOTU_INDEX))
    admin = User.get(User.email == "admin")
    upload_test_data().set_role(admin, Role.ADMIN)


def create_admin(_args):
    if User.select().where(User.email == "admin").exists():
        print("User admin already exists")
        return
    logging.warning("**** Creating superuser admin:admin ****")
    auth.create_user("admin", "admin", Role.ADMIN)


def document(args):
    with app.app_context():
        if args.format == "html":
            print(docs_html())
        elif args.format == "md":
            print(docs_md())
        elif args.format == "json":
            rules = context()
            print(MyJSONEncoder(indent=4).encode(rules))
        else:
            raise ValueError(args.format)


parser = argparse.ArgumentParser(description=__doc__, prog="python -m amcat4")
parser.add_argument("--elastic", help="Elasticsearch host", default="localhost:9200")

subparsers = parser.add_subparsers(dest="action", title="action", help='Action to perform:', required=True)
p = subparsers.add_parser('run', help='Run the backend API in development mode')
p.add_argument('--no-debug', action='store_true', dest='nodebug',
               help='Disable debug mode (useful for testing downstream clients)')
p.add_argument('-p', '--port', help='Port', default=5000)
p.set_defaults(func=run)

p = subparsers.add_parser('create-test-index', help=f'Create the {SOTU_INDEX} test index')
p.set_defaults(func=create_test_index)

p = subparsers.add_parser('create-admin', help='Create the admin:admin superuser')
p.set_defaults(func=create_admin)

p = subparsers.add_parser('document', help='Create the admin:admin superuser')
p.add_argument("--format", choices=["html", "json", "md"], default="md", help="Output format (default: markdown)")
p.set_defaults(func=document)

args = parser.parse_args()

logging.basicConfig(format='[%(levelname)-7s:%(name)-15s] %(message)s', level=logging.INFO)
es_logger = logging.getLogger('elasticsearch')
es_logger.setLevel(logging.WARNING)
setup_elastic(args.elastic)
initialize_if_needed()

args.func(args)
