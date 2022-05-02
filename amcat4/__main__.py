"""
AmCAT4 REST API
"""
import csv
import io
import logging
import sys
import urllib.request
import argparse

import uvicorn

from amcat4 import auth
from amcat4.api import app
from amcat4.auth import Role, User
from amcat4.config import settings
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
    uvicorn.run(app, host="0.0.0.0", port=args.port)


def create_test_index(_args):
    if Index.select().where(Index.name == SOTU_INDEX):
        print(f"Index {SOTU_INDEX} already exists")
        return
    logging.info("**** Creating test index {} ****".format(SOTU_INDEX))
    admin = User.get(User.email == "admin")
    upload_test_data().set_role(admin, Role.ADMIN)


def create_admin(args):
    username, password = args.username, args.password
    if User.select().where(User.email == username).exists():
        print(f"User {username} already exists")
        return
    logging.warning(f"**** Creating superuser {username}:*****")
    auth.create_user(username, password, Role.ADMIN)


parser = argparse.ArgumentParser(description=__doc__, prog="python -m amcat4")
parser.add_argument("--elastic", help="Elasticsearch host", default=settings.amcat4_elastic_host)

subparsers = parser.add_subparsers(dest="action", title="action", help='Action to perform:', required=True)
p = subparsers.add_parser('run', help='Run the backend API in development mode')
p.add_argument('--no-debug', action='store_true', dest='nodebug',
               help='Disable debug mode (useful for testing downstream clients)')
p.add_argument('-p', '--port', help='Port', default=5000)
p.set_defaults(func=run)

p = subparsers.add_parser('create-test-index', help=f'Create the {SOTU_INDEX} test index')
p.set_defaults(func=create_test_index)

p = subparsers.add_parser('create-admin', help='Create the admin:admin superuser')
p.add_argument("--username", default="admin", help="Username for the new user (default: admin)")
p.add_argument("--password", default="admin", help="Password for the new user (default: admin)")
p.set_defaults(func=create_admin)

args = parser.parse_args()

logging.basicConfig(format='[%(levelname)-7s:%(name)-15s] %(message)s', level=logging.INFO)
es_logger = logging.getLogger('elasticsearch')
es_logger.setLevel(logging.WARNING)
setup_elastic(args.elastic)
initialize_if_needed()

args.func(args)
