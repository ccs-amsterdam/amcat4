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
from amcat4.config import get_settings
from amcat4.elastic import upload_documents
from amcat4.index import create_index, set_global_role, Role, list_global_users

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


def base_env():
    return dict(
        amcat4_secret_key=secrets.token_hex(nbytes=32),
        amcat4_middlecat_url="https://middlecat.up.netlify.app",
    )


def create_env(args):
    if os.path.exists('.env'):
        print('*** File .env already exists, quitting ***')
        sys.exit(1)

    env = base_env()
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


def list_users(_args):
    admin_password = get_settings().admin_password
    if admin_password:
        print("ADMIN     : admin (password set via environment AMCAT4_ADMIN_PASSWORD)")
    users = sorted(list_global_users(), key=lambda ur: (ur[1], ur[0]))
    if users:
        for (user, role) in users:
            print(f"{role.name:10}: {user}")
    if not (users or admin_password):
        print("(No users defined yet, set AMCAT4_ADMIN_PASSWORD in environment use add-admin to add users by email)")


def config_amcat(args):
    settings = get_settings().dict()
    # location of env should stay the same so it is found on restart
    del settings["env_file"]
    # if .env does not exist yet, secret_key should be created
    if not os.path.exists('.env'):
        settings["secret_key"] = base_env()["amcat4_secret_key"]
    if args.name:
        # some variables should not be changed by the user (currently just secret_key)
        do_not_change = ["secret_key"] + list(filter(lambda x: x != args.name, settings.keys()))
    else:
        do_not_change = ["secret_key"]
    for k, v in settings.items():
        # some variables probably shouldn't be changed by the user (currently just secret_key)
        if k not in do_not_change:
            v = menu(k, v)
            if v == "aborted":
                settings = "aborted"
                break
            else:
                if str(k) == "admin_email" and v is not None:
                    set_global_role(v, Role.ADMIN)
                settings[k] = v

    if settings != "aborted":
        with open(".env", 'w') as f:
            for key, val in settings.items():
                if val is not None:
                    f.write(f"amcat4_{key}={val}\n")
        os.chmod(".env", 0o600)
        print(f"*** Changed {bold('.env')} file ***")


def bold(x):
    return '\033[1m' + str(x) + '\033[0m'


def menu(k, v):
    choice = input(f"The current value for {bold(k)} is {bold(v)}. Do you want to change it (Yes/{bold('No')}/Cancel)?")
    # remain on same line to hide settings from onlookers
    sys.stdout.write("\033[F\033[K")
    if choice in ("No", "NO", "N", "n", ""):
        return v
    elif choice in ("Yes", "YES", "Y", "y"):
        v = input(f"Enter new value for {k}:")
        sys.stdout.write("\033[F\033[K")
        return v
    elif choice in ("Cancel", "CANCEL", "C", "c"):
        return "aborted"
    else:
        print("Choose one of Yes/No/Cancel")
        menu(k, v)


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

p = subparsers.add_parser('config', help='Configure (all) settings in amcat4 in an interactive menu.')
p.add_argument("-n", "--name", help="Name of a specific setting that should be changed.")
p.set_defaults(func=config_amcat)

p = subparsers.add_parser('add-admin', help='Add a global admin')
p.add_argument("email", help="The email address of the admin user.")
p.set_defaults(func=add_admin)

p = subparsers.add_parser('list-users', help='List global users')
p.set_defaults(func=list_users)


p = subparsers.add_parser('create-test-index', help=f'Create the {SOTU_INDEX} test index')
p.set_defaults(func=create_test_index)

args = parser.parse_args()

logging.basicConfig(format='[%(levelname)-7s:%(name)-15s] %(message)s', level=logging.INFO)
es_logger = logging.getLogger('elasticsearch')
es_logger.setLevel(logging.WARNING)

args.func(args)
