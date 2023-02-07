"""
AmCAT4 Configuration

We read configuration from 2 sources, in order of precedence (higher is more priority)
- Environment variables
- A .env file, either in the current working directory or in a location specified
  by the AMCAT4_CONFIG_FILE environment variable
"""
import functools
from enum import Enum
from pathlib import Path

from class_doc import extract_docs_from_cls_obj
from dotenv import load_dotenv
from pydantic import BaseSettings, validator
from pydantic_settings import with_attrs_docs


class AuthOptions(str, Enum):
    #: everyone (that can reach the server) can do anything they want
    no_auth = "no_auth"

    #: everyone can use the server, dependent on index-level guest_role authorization settings
    allow_guests = "allow_guests"

    #: everyone can use the server, if they have a valid middlecat login,
    #: and dependent on index-level guest_role authorization settings
    allow_authenticated_guests = "allow_authenticated_guests"

    #: only people with a valid middlecat login and an explicit server role can use the server
    authorized_users_only = "authorized_users_only"

    @classmethod
    def validate(cls, value: str):
        if value not in cls.__members__:
            options = ", ".join(AuthOptions.__members__.keys())
            return f"{value} is not a valid authorization option. Choose one of {{{options}}}"


# As far as I know, there is no elegant built-in way to set to __doc__ of an enum?
for field, doc in extract_docs_from_cls_obj(AuthOptions).items():
    AuthOptions[field].__doc__ = "\n".join(doc)


@with_attrs_docs
class Settings(BaseSettings):
    #: Location of a .env file (if used) relative to working directory
    env_file: Path = ".env"

    #: Host this instance is served at (needed for checking tokens)
    host: str = "http://localhost:5000"

    #: Elasticsearch password. This the password for the 'elastic' user when Elastic xpack security is enabled
    elastic_password: str = None

    #: Elasticsearch host. Default: https://localhost:9200 if elastic_password is set, http://localhost:9200 otherwise
    elastic_host: str = None

    #: Elasticsearch verify SSL (only used if elastic_password is set). Default: True unless host is localhost)
    elastic_verify_ssl: bool = None

    #: Elasticsearch index to store authorization information in
    system_index = "amcat4_system"

    #: Do we require authorization?
    auth: AuthOptions = AuthOptions.no_auth

    #: Middlecat server to trust as ID provider
    middlecat_url: str = "https://middlecat.up.railway.app"

    #: Email address for a hardcoded admin email (useful for setup and recovery)
    admin_email: str = None

    class Config:
        env_prefix = "amcat4_"

    @validator('elastic_host', always=True)
    def set_elastic_host(cls, v, values, **kwargs):
        if not v:
            v = "https://localhost:9200" if values['elastic_password'] else "http://localhost:9200"
        return v

    @validator('elastic_verify_ssl', always=True)
    def set_elastic_ssl(cls, v, values, **kwargs):
        if not v:
            v = not values['elastic_host'] in ("http://localhost:9200", "https://localhost:9200")
        return v


@functools.lru_cache()
def get_settings():
    # This shouldn't be necessary according to the docs, but without the load_dotenv it doesn't work at
    # least when running with python -m amcat4.config...
    temp = Settings()
    # WvA: For some reason, it always seems to override environment variables?
    load_dotenv(temp.env_file, override=False)
    return Settings()


if __name__ == '__main__':
    # Echo the settings
    for k, v in get_settings().dict().items():
        print(f"{Settings.Config.env_prefix.upper()}{k.upper()}={v}")
