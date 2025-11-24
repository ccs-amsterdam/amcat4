"""
AmCAT4 REST API
"""

import argparse
import asyncio
import csv
import inspect
import io
import logging
import os
import secrets
import sys
import urllib.request
from enum import Enum
from pathlib import Path
from typing import Any, get_args

import uvicorn
from pydantic.fields import FieldInfo
from uvicorn.config import LOGGING_CONFIG

from amcat4.config import AuthOptions, get_settings, validate_settings
from amcat4.connections import amcat_connections, es
from amcat4.models import FieldType, ProjectSettings, Roles
from amcat4.objectstorage.image_processing import create_image_from_url
from amcat4.projects.documents import create_or_update_documents
from amcat4.projects.index import create_project_index, delete_project_index
from amcat4.systemdata.manage import create_or_update_systemdata, delete_systemdata_version
from amcat4.systemdata.roles import list_server_roles, update_server_role

SOTU_INDEX = "state_of_the_union"


async def upload_test_data() -> str:
    url = "https://raw.githubusercontent.com/ccs-amsterdam/example-text-data/master/sotu.csv"
    url_open = urllib.request.urlopen(url)
    csv.field_size_limit(sys.maxsize)
    csvfile = csv.DictReader(io.TextIOWrapper(url_open, encoding="utf-8"))

    img_url = "https://preview.redd.it/president-bill-clintons-cat-socks-sitting-at-the-podium-in-v0-51wrybd3iabe1.jpeg?width=640&crop=smart&auto=webp&s=21b9f7787017f3fa1ab0fdba58839a42ca0a9cd2"
    image = await create_image_from_url(img_url)

    # creates the index info on the sqlite db
    async with amcat_connections():
        await create_or_update_systemdata()
        await create_project_index(
            ProjectSettings(
                id=SOTU_INDEX,
                name="State of the Union Speeches",
                description="State of the Union speeches from 1790 to 2020",
                image=image,
            )
        )

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
        fields: dict[str, FieldType] = {
            "text": "text",
            "title": "text",
            "date": "date",
            "president": "keyword",
            "party": "keyword",
            "year": "integer",
        }
        await create_or_update_documents(SOTU_INDEX, docs, fields)
        return SOTU_INDEX


async def _check_elastic_connection():
    async with amcat_connections():
        if await es().ping():
            logging.info(f"Connect to elasticsearch {get_settings().elastic_host}")


def run(args):
    auth = get_settings().auth
    logging.info(f"Starting server at port {args.port}, debug={not args.nodebug}, auth={auth}")
    if auth == AuthOptions.no_auth:
        logging.warning(
            "Warning: No authentication is set up - everyone who can access this service can view and change all data"
        )
    if validate_settings():
        logging.warning(validate_settings())
    logging.info(
        "To change server config, create an .env file and/or set environment parameters,\n"
        f"{' ' * 26}see README.md, amcat4/config.py or .env.example for more information.\n"
        f"{' ' * 26}You can also run `python -m amcat4 config` to create the .env settings file interactively\n"
    )

    asyncio.run(_check_elastic_connection())
    log_config = "logging.yml" if Path("logging.yml").exists() else LOGGING_CONFIG
    uvicorn.run("amcat4.api:app", host="0.0.0.0", reload=not args.nodebug, port=args.port, log_config=log_config)


def val(val_or_list):
    if isinstance(val_or_list, list):
        if len(val_or_list) == 1:
            return val_or_list[0]
        raise ValueError(f"Cannot extract single value from {val_or_list}")
    return val_or_list


async def migrate_systemdata(args) -> None:
    settings = get_settings()
    async with amcat_connections():
        if not await es().ping():
            logging.error(f"Cannot connect to elasticsearch server {settings.elastic_host}")
            sys.exit(1)

        await create_or_update_systemdata(rm_pending_migrations=args.rm_pending)


async def dangerously_destroy_systemdata(args) -> None:
    settings = get_settings()
    async with amcat_connections():
        if not await es().ping():
            logging.error(f"Cannot connect to elasticsearch server {settings.elastic_host}")
            sys.exit(1)

        version = args.version
        if not version:
            logging.error("You must specify a version to delete using --version")
            sys.exit(1)

        await delete_systemdata_version(int(version))


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
    with open(".env", "w") as f:
        for key, val in env.items():
            f.write(f"{key}={val}\n")
    os.chmod(".env", 0o600)
    print("*** Created .env file ***")


async def create_test_index(_args):
    logging.info("**** Creating test index {} ****".format(SOTU_INDEX))
    await create_or_update_systemdata()
    await delete_project_index(SOTU_INDEX, ignore_missing=True)
    await upload_test_data()


async def add_admin(args):
    logging.info(f"**** Setting {args.email} to ADMIN ****")
    await create_or_update_systemdata()
    await update_server_role(args.email, role=Roles.ADMIN)


async def list_users(_args):
    await create_or_update_systemdata()
    roles = list_server_roles()

    if roles:
        async for role in roles:
            print(f"{role.role}: {role.email}")
    if not roles:
        print("(No users defined yet, use add-admin to add users by email)")


def config_amcat(args):
    settings = get_settings()
    # Not a useful entry in an actual env_file
    print(f"Reading/writing settings from {settings.env_file}")
    for fieldname, fieldinfo in type(settings).model_fields.items():
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
        for fieldname, fieldinfo in type(settings).model_fields.items():
            value = getattr(settings, fieldname)
            if doc := fieldinfo.description:
                f.write(f"# {doc}\n")
            if _isenum(fieldinfo) and fieldinfo.annotation:
                f.write("# Valid options:\n")
                for option in get_args(fieldinfo.annotation):
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
    p.add_argument(
        "--no-rm-pending",
        action="store_false",
        dest="rm_pending",
        default=True,
        help="Do NOT remove pending migrations (by default they ARE removed)",
    )
    p.set_defaults(func=migrate_systemdata)

    p = subparsers.add_parser(
        "dangerously_destroy_systemdata",
        help="DANGER: Delete all systemdata for a given version. Use with caution, and only if you know what you're doing.",
    )
    p.add_argument(
        "-v",
        "--version",
        help="The systemdata version to delete.",
    )
    p.set_defaults(func=dangerously_destroy_systemdata)

    args = parser.parse_args()

    logging.basicConfig(format="[%(levelname)-7s:%(name)-15s] %(message)s", level=logging.INFO)
    es_logger = logging.getLogger("elasticsearch")
    es_logger.setLevel(logging.WARNING)

    if inspect.iscoroutinefunction(args.func):
        asyncio.run(args.func(args))
    else:
        args.func(args)


if __name__ == "__main__":
    main()
