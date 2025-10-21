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
from typing import Annotated, Any
from class_doc import extract_docs_from_cls_obj
from dotenv import load_dotenv
from pydantic import model_validator, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_PREFIX = "amcat4_"


class AuthOptions(str, Enum):
    #: everyone (that can reach the server) can do anything they want
    no_auth = "no_auth"

    #: everyone can use the server, dependent on index-level guest_role authorization settings
    allow_guests = "allow_guests"

    #: everyone can use the server, if they have a valid middlecat login,
    #: and dependent on index-level guest_role authorization settings
    allow_authenticated_guests = "allow_authenticated_guests"

    @classmethod
    def validate(cls, value: str):
        if value not in cls.__members__:
            options = ", ".join(AuthOptions.__members__.keys())
            return f"{value} is not a valid authorization option. Choose one of {{{options}}}"


# Set the __doc__ attribute of each AuthOptions enum member using extract_docs_from_cls_obj
for field, doc in extract_docs_from_cls_obj(AuthOptions).items():
    AuthOptions[field].__doc__ = "\n".join(doc)


class Settings(BaseSettings):
    env_file: Annotated[
        Path,
        Field(
            description="Location of a .env file (if used) relative to working directory",
        ),
    ] = Path(".env")
    host: Annotated[
        str,
        Field(
            description="Host this instance is served at (needed for checking tokens)",
        ),
    ] = "http://localhost:5000"

    elastic_password: Annotated[
        str | None,
        Field(
            description=(
                "Elasticsearch password. This the password for the 'elastic' user when Elastic xpack security is enabled"
            )
        ),
    ] = None

    elastic_host: Annotated[
        str | None,
        Field(
            description=(
                "Elasticsearch host. "
                "Default: https://localhost:9200 if elastic_password is set, http://localhost:9200 otherwise"
            )
        ),
    ] = None

    elastic_verify_ssl: Annotated[
        bool | None,
        Field(
            description=(
                "Elasticsearch verify SSL (only used if elastic_password is set). Default: True unless host is localhost)"
            ),
        ),
    ] = None

    system_index: Annotated[
        str,
        Field(
            description="Elasticsearch index to store authorization information in",
        ),
    ] = "amcat4_system"

    auth: Annotated[AuthOptions, Field(description="Do we require authorization?")] = AuthOptions.no_auth

    middlecat_url: Annotated[
        str,
        Field(
            description="Middlecat server to trust as ID provider",
        ),
    ] = "https://middlecat.net"

    admin_email: Annotated[
        str | None,
        Field(
            description="Email address for a hardcoded admin email (useful for setup and recovery)",
        ),
    ] = None

    minio_host: Annotated[str | None, Field()] = None
    minio_tls: Annotated[bool, Field()] = False
    minio_access_key: Annotated[str | None, Field()] = None
    minio_secret_key: Annotated[str | None, Field()] = None

    @model_validator(mode="after")
    def set_ssl(self: Any) -> "Settings":
        if not self.elastic_host:
            self.elastic_host = ("https" if self.elastic_password else "http") + "://localhost:9200"
        if not self.elastic_verify_ssl:
            self.elastic_verify_ssl = self.elastic_host not in {
                "http://localhost:9200",
                "https://localhost:9200",
            }
        return self

    model_config = SettingsConfigDict(env_prefix=ENV_PREFIX)


@functools.lru_cache()
def get_settings() -> Settings:
    # This shouldn't be necessary according to the docs, but without the load_dotenv it doesn't work at
    # least when running with python -m amcat4.config...
    temp = Settings()
    # WvA: For some reason, it always seems to override environment variables?
    load_dotenv(temp.env_file, override=False)
    return Settings()


def validate_settings():
    if get_settings().auth != "no_auth":
        if get_settings().host.startswith("http://") and not get_settings().host.startswith("http://localhost"):
            return (
                "You have set the host at an http address and enabled authentication."
                "Authentication through middlecat will not work in your browser"
                " without additional steps. See https://github.com/ccs-amsterdam/amcat4py/issues/9"
            )


if __name__ == "__main__":
    # Echo the settings
    for k, v in get_settings().model_dump().items():
        print(f"{ENV_PREFIX.upper()}{k.upper()}={v}")
