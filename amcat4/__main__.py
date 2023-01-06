"""
AmCAT4 REST API
"""
import argparse
import csv
import io
import logging
import os
import secrets
import sys
import urllib.request

import uvicorn

from amcat4 import index
from amcat4.elastic import upload_documents
from amcat4.index import create_index, set_global_role, Role

SOTU_INDEX = "state_of_the_union"


def upload_test_data() -> str:
    url = "https://raw.githubusercontent.com/ccs-amsterdam/example-text-data/master/sotu.csv"
    url_open = urllib.request.urlopen(url)
    csv.field_size_limit(sys.maxsize)
    csvfile = csv.DictReader(io.TextIOWrapper(url_open, encoding='utf-8'))

    # creates the index info on the sqlite db
    create_index(SOTU_INDEX)

    docs = [dict(title="{Year}: {President}".format(**row),
                 text=row['Text'],
                 date=row['Date'],
                 president=row['President'],
                 year=row['Year'],
                 party=row['Party'])
            for row in csvfile]
    columns = {"president": "keyword", "party": "keyword", "year": "double"}
    upload_documents(SOTU_INDEX, docs, columns)
    return SOTU_INDEX


def run(args):
    logging.info(f"Starting server at port {args.port}, debug={not args.nodebug}")
    uvicorn.run("amcat4.api:app", host="0.0.0.0", reload=not args.nodebug, port=args.port)


def create_env(args):
    if os.path.exists('.env'):
        print('*** File .env already exists, quitting ***')
        sys.exit(1)

    env = dict(
        amcat4_secret_key=secrets.token_hex(nbytes=32),
        amcat4_middlecat_host="https://middlecat.up.netlify.app",
    )
    if args.admin_email:
        env['amcat4_admin_email'] = args.admin_email
    if args.admin_password:
        env['amcat4_admin_password'] = args.admin_password
    if args.no_admin_password:
        env['amcat4_admin_password'] = ""
    with open('.env', 'w') as f:
        for key, val in env.items():
            f.write(f"{key}={val}\n")
    os.chmod('.env', 0o600)
    print('*** Created .env file ***')


def create_test_index(_args):
    logging.info("**** Creating test index {} ****".format(SOTU_INDEX))
    index.delete_index(SOTU_INDEX, ignore_missing=True)
    upload_test_data()


def add_admin(args):
    logging.info(f"**** Setting {args.email} to ADMIN ****")
    set_global_role(args.email, Role.ADMIN)


parser = argparse.ArgumentParser(description=__doc__, prog="python -m amcat4")

subparsers = parser.add_subparsers(dest="action", title="action", help='Action to perform:', required=True)
p = subparsers.add_parser('run', help='Run the backend API in development mode')
p.add_argument('--no-debug', action='store_true', dest='nodebug',
               help='Disable debug mode (useful for testing downstream clients)')
p.add_argument('-p', '--port', help='Port', default=5000)
p.set_defaults(func=run)

p = subparsers.add_parser('create-env', help='Create the .env file with a random secret key')
p.add_argument("-a", "--admin_email", help="The email address of the admin user.")
p.add_argument("-p", "--admin_password", help="The password of the built-in admin user.")
p.add_argument("-P", "--no-admin_password", action='store_true', help="Disable admin password")

p.set_defaults(func=create_env)


p = subparsers.add_parser('add-admin', help='Add a global admin')
p.add_argument("email", help="The email address of the admin user.")
p.set_defaults(func=add_admin)

p = subparsers.add_parser('create-test-index', help=f'Create the {SOTU_INDEX} test index')
p.set_defaults(func=create_test_index)

args = parser.parse_args()

logging.basicConfig(format='[%(levelname)-7s:%(name)-15s] %(message)s', level=logging.INFO)
es_logger = logging.getLogger('elasticsearch')
es_logger.setLevel(logging.WARNING)

args.func(args)
