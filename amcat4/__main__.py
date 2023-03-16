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
from enum import Enum

import uvicorn
from pydantic.fields import ModelField

from amcat4 import index
from amcat4.config import get_settings, AuthOptions, Settings, validate_settings
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
    auth = get_settings().auth
    logging.info(f"Starting server at port {args.port}, debug={not args.nodebug}, auth={auth}")
    if auth == AuthOptions.no_auth:
        logging.warning("Warning: No authentication is set up - "
                        "everyone who can access this service can view and change all data")
    if validate_settings():
        logging.warning(validate_settings())
    logging.info("To change server config, create an .env file and/or set environment parameters,\n"
                 f"{' '*26}see README.md, amcat4/config.py or .env.example for more information.\n"
                 f"{' '*26}You can also run `python -m amcat4 config` to create the .env settings file interactively\n")
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
    # env_file is not a useful setting in the .env file itself, only as environment variable
    env_file_location = settings.pop('env_file')
    print(f"Reading/writing settings from {env_file_location}")
    for field in Settings.__fields__.values():
        if field.name not in settings:
            continue
        v = settings[field.name]
        validation_function = AuthOptions.validate if field.name == "auth" else None
        v = menu(field, v, validation_function=validation_function)
        if v is ABORTED:
            return
        if v is not UNCHANGED:
            settings[field.name] = v

    with open(".env", 'w') as f:
        for key, val in settings.items():
            field = Settings.__fields__[key]
            if doc := field.field_info.description:
                f.write(f"# {doc}\n")
            if issubclass(field.type_, Enum):
                f.write("# Valid options:\n")
                for option in field.type_:
                    doc = option.__doc__.replace("\n", " ")
                    f.write(f"# - {option.name}: {doc}\n")
            if val is None:
                f.write(f"#amcat4_{key}=\n\n")
            else:
                f.write(f"amcat4_{key}={val}\n\n")
    os.chmod(".env", 0o600)
    print(f"*** Written {bold('.env')} file to {env_file_location} ***")


def bold(x):
    return '\033[1m' + str(x) + '\033[0m'


ABORTED = object()
UNCHANGED = object()


def menu(field: ModelField, v, validation_function=None):
    print(f"\n{bold(field.name)}: {field.field_info.description}")
    if issubclass(field.type_, Enum):
        print("  Possible choices:")
        for option in field.type_:
            print(f"  - {option.name}: {option.__doc__}")
        print()
    print(f"The current value for {bold(field.name)} is {bold(v)}.")
    while True:
        try:
            value = input("Enter a new value, press [enter] to leave unchanged, or press [control+c] to abort: ")
        except KeyboardInterrupt:
            return ABORTED
        if not value.strip():
            return UNCHANGED
        if validation_function and (message := validation_function(value)):
            print(f"\nInvalid value: {message}")
            continue
        return value


def main():
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

    p = subparsers.add_parser('config', help='Configure amcat4 settings in an interactive menu.')
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


if __name__ == '__main__':
    main()
