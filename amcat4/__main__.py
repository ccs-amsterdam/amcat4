"""
AmCAT4 REST API
"""

import argparse
import csv
import io
import json
import logging
import os
import secrets
import sys
from typing import Any
import urllib.request
from enum import Enum
from collections import defaultdict
import elasticsearch.helpers

import uvicorn
from pydantic.fields import FieldInfo

from amcat4 import index
from amcat4.config import get_settings, AuthOptions, validate_settings
from amcat4.elastic import connect_elastic, get_system_version, ping
from amcat4.index import GLOBAL_ROLES, create_index, set_global_role, Role, list_global_users, upload_documents
from amcat4.models import ElasticType, FieldType

SOTU_INDEX = "state_of_the_union"


def upload_test_data() -> str:
    url = "https://raw.githubusercontent.com/ccs-amsterdam/example-text-data/master/sotu.csv"
    url_open = urllib.request.urlopen(url)
    csv.field_size_limit(sys.maxsize)
    csvfile = csv.DictReader(io.TextIOWrapper(url_open, encoding="utf-8"))

    # creates the index info on the sqlite db
    create_index(SOTU_INDEX)

    docs = [
        dict(
            title="{Year}: {President}".format(**row),
            text=row["Text"],
            date=row["Date"],
            president=row["President"],
            year=row["Year"],
            party=row["Party"],
        )
        for row in csvfile
    ]
    fields: dict[str, FieldType] = {"president": "keyword", "party": "keyword", "year": "integer"}
    upload_documents(SOTU_INDEX, docs, fields)
    return SOTU_INDEX


def run(args):
    auth = get_settings().auth
    logging.info(f"Starting server at port {args.port}, debug={not args.nodebug}, auth={auth}")
    if auth == AuthOptions.no_auth:
        logging.warning(
            "Warning: No authentication is set up - " "everyone who can access this service can view and change all data"
        )
    if validate_settings():
        logging.warning(validate_settings())
    logging.info(
        "To change server config, create an .env file and/or set environment parameters,\n"
        f"{' '*26}see README.md, amcat4/config.py or .env.example for more information.\n"
        f"{' '*26}You can also run `python -m amcat4 config` to create the .env settings file interactively\n"
    )
    if ping():
        logging.info(f"Connect to elasticsearch {get_settings().elastic_host}")
    uvicorn.run("amcat4.api:app", host="0.0.0.0", reload=not args.nodebug, port=args.port)


def val(val_or_list):
    if isinstance(val_or_list, list):
        if len(val_or_list) == 1:
            return val_or_list[0]
        raise ValueError(f"Cannot extract single value from {val_or_list}")
    return val_or_list


def migrate_index(_args) -> None:
    settings = get_settings()
    elastic = connect_elastic()
    if not elastic.ping():
        logging.error(f"Cannot connect to elasticsearch server {settings.elastic_host}")
        sys.exit(1)
    if not elastic.indices.exists(index=settings.system_index):
        logging.info("System index does not exist yet. It will be created automatically if you run the server")
        sys.exit(1)
    # Check index format version
    version = get_system_version(elastic)
    logging.info(f"{settings.elastic_host}::{settings.system_index} is at version {version or 0}")
    if version == 1:
        logging.info("Nothing to do")
    else:
        logging.info("Migrating to version 1")
        fields = ["index", "email", "role"]
        indices: defaultdict[str, dict[str, str]] = defaultdict(dict)

        for entry in elasticsearch.helpers.scan(elastic, index=settings.system_index, fields=fields, _source=False):
            index, email, role = [val(entry["fields"][field]) for field in fields]
            indices[index][email] = role
        if GLOBAL_ROLES not in indices:
            indices[GLOBAL_ROLES] = {}
        try:
            elastic.indices.delete(index=settings.system_index)
            for index, roles_dict in indices.items():
                guest_role = roles_dict.pop("_guest", None)
                roles_dict.pop("ADMIN", None)
                roles = [{"email": email, "role": role} for (email, role) in roles_dict.items()]
                doc: dict[str, Any] = dict(name=index, guest_role=guest_role, roles=roles)
                if index == GLOBAL_ROLES:
                    doc["version"] = 1
                elastic.index(index=settings.system_index, id=index, document=doc)
        except Exception:
            try:
                open("roles.csv", "w").write(json.dumps(indices, indent=2))
                dest = "roles.csv"
            except Exception:
                print(json.dumps(indices, indent=2))
                dest = "screen"
            logging.exception(
                "Something went wrong in migrating, and the old system index is probably lost. Sorry!"
                f"The authorization information is written to {dest}, I hope this can be fixed..."
            )
            sys.exit(1)


def base_env():
    return dict(
        amcat4_secret_key=secrets.token_hex(nbytes=32),
        amcat4_middlecat_url="https://middlecat.net",
    )


def create_env(args):
    if os.path.exists(".env"):
        print("*** File .env already exists, quitting ***")
        sys.exit(1)

    env = base_env()
    if args.admin_email:
        env["amcat4_admin_email"] = args.admin_email
    if args.admin_password:
        env["amcat4_admin_password"] = args.admin_password
    if args.no_admin_password:
        env["amcat4_admin_password"] = ""
    with open(".env", "w") as f:
        for key, val in env.items():
            f.write(f"{key}={val}\n")
    os.chmod(".env", 0o600)
    print("*** Created .env file ***")


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
    users = list_global_users()

    # sorted changes the output type of list_global_users?
    # users = sorted(list_global_users(), key=lambda ur: (ur[1], ur[0]))
    if users:
        for user, role in users.items():
            print(f"{role.name:10}: {user}")
    if not (users or admin_password):
        print("(No users defined yet, set AMCAT4_ADMIN_PASSWORD in environment use add-admin to add users by email)")


def config_amcat(args):
    settings = get_settings()
    # Not a useful entry in an actual env_file
    print(f"Reading/writing settings from {settings.env_file}")
    for fieldname, fieldinfo in settings.model_fields.items():
        if fieldname == "env_file":
            continue

        validation_function = AuthOptions.validate if fieldname == "auth" else None
        value = getattr(settings, fieldname)
        value = menu(fieldname, fieldinfo, value, validation_function=validation_function)
        if value is ABORTED:
            return
        if value is not UNCHANGED:
            setattr(settings, fieldname, value)

    with settings.env_file.open("w") as f:
        for fieldname, fieldinfo in settings.model_fields.items():
            value = getattr(settings, fieldname)
            if doc := fieldinfo.description:
                f.write(f"# {doc}\n")
            if _isenum(fieldinfo) and fieldinfo.annotation:
                f.write("# Valid options:\n")
                for option in fieldinfo.annotation:
                    doc = option.__doc__.replace("\n", " ")
                    f.write(f"# - {option.name}: {doc}\n")
            if val is None:
                f.write(f"#amcat4_{fieldname}=\n\n")
            else:
                f.write(f"amcat4_{fieldname}={value}\n\n")
    os.chmod(".env", 0o600)
    print(f"*** Written {bold('.env')} file to {settings.env_file} ***")


def bold(x):
    return "\033[1m" + str(x) + "\033[0m"


ABORTED = object()
UNCHANGED = object()


def _isenum(fieldinfo: FieldInfo) -> bool:
    try:
        return issubclass(fieldinfo.annotation, Enum) if fieldinfo.annotation is not None else False
    except TypeError:
        return False


def menu(fieldname: str, fieldinfo: FieldInfo, value, validation_function=None):
    print(f"\n{bold(fieldname)}: {fieldinfo.description}")
    if _isenum(fieldinfo) and fieldinfo.annotation:
        print("  Possible choices:")
        options: Any = fieldinfo.annotation
        for option in options:
            print(f"  - {option.name}: {option.__doc__}")
        print()
    print(f"The current value for {bold(fieldname)} is {bold(value)}.")
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

    subparsers = parser.add_subparsers(dest="action", title="action", help="Action to perform:", required=True)
    p = subparsers.add_parser("run", help="Run the backend API in development mode")
    p.add_argument(
        "--no-debug",
        action="store_true",
        dest="nodebug",
        help="Disable debug mode (useful for testing downstream clients)",
    )
    p.add_argument("-p", "--port", help="Port", default=5000)
    p.set_defaults(func=run)

    p = subparsers.add_parser("create-env", help="Create the .env file with a random secret key")
    p.add_argument("-a", "--admin_email", help="The email address of the admin user.")
    p.add_argument("-p", "--admin_password", help="The password of the built-in admin user.")
    p.add_argument("-P", "--no-admin_password", action="store_true", help="Disable admin password")

    p.set_defaults(func=create_env)

    p = subparsers.add_parser("config", help="Configure amcat4 settings in an interactive menu.")
    p.set_defaults(func=config_amcat)

    p = subparsers.add_parser("add-admin", help="Add a global admin")
    p.add_argument("email", help="The email address of the admin user.")
    p.set_defaults(func=add_admin)

    p = subparsers.add_parser("list-users", help="List global users")
    p.set_defaults(func=list_users)

    p = subparsers.add_parser("create-test-index", help=f"Create the {SOTU_INDEX} test index")
    p.set_defaults(func=create_test_index)

    p = subparsers.add_parser("migrate", help="Migrate the system index to the current version")
    p.set_defaults(func=migrate_index)

    args = parser.parse_args()

    logging.basicConfig(format="[%(levelname)-7s:%(name)-15s] %(message)s", level=logging.INFO)
    es_logger = logging.getLogger("elasticsearch")
    es_logger.setLevel(logging.WARNING)

    args.func(args)


if __name__ == "__main__":
    main()
