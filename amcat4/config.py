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
from typing import Optional
from class_doc import extract_docs_from_cls_obj
from dotenv import load_dotenv
from pydantic import model_validator, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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


class Settings(BaseSettings):
    env_file: Path = Field(
        ".env",
        description="Location of a .env file (if used) relative to working directory",
    )
    host: str = Field(
        "http://localhost:5000",
        description="Host this instance is served at (needed for checking tokens)",
    )

    elastic_password: Optional[str] = Field(
        None,
        description="Elasticsearch password. This the password for the 'elastic' user when Elastic xpack security is enabled",
    )

    elastic_host: Optional[str] = Field(
        None,
        description="Elasticsearch host. Default: https://localhost:9200 if elastic_password is set, http://localhost:9200 otherwise",
    )

    elastic_verify_ssl: Optional[bool] = Field(
        None,
        description="Elasticsearch verify SSL (only used if elastic_password is set). Default: True unless host is localhost)",
    )

    system_index: str = Field(
        "amcat4_system",
        description="Elasticsearch index to store authorization information in",
    )

    auth: AuthOptions = Field(
        AuthOptions.no_auth, description="Do we require authorization?"
    )

    middlecat_url: str = Field(
        "https://middlecat.up.railway.app",
        description="Middlecat server to trust as ID provider",
    )

    admin_email: Optional[str] = Field(
        None,
        description="Email address for a hardcoded admin email (useful for setup and recovery)",
    )

    @model_validator(mode="after")
    def set_ssl(self) -> "Settings":
        if not self.elastic_host:
            self.elastic_host = (
                "https" if self.elastic_password else "http"
            ) + "://localhost:9200"
        if not self.elastic_verify_ssl:
            self.elastic_verify_ssl = self.elastic_host not in {
                "http://localhost:9200",
                "https://localhost:9200",
            }
        return self

    model_config = SettingsConfigDict(env_prefix="amcat4_")


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
        if get_settings().host.startswith(
            "http://"
        ) and not get_settings().host.startswith("http://localhost"):
            return (
                "You have set the host at an http address and enabled authentication."
                "Authentication through middlecat will not work in your browser"
                " without additional steps. See https://github.com/ccs-amsterdam/amcat4py/issues/9"
            )


if __name__ == "__main__":
    # Echo the settings
    for k, v in get_settings().dict().items():
        print(f"{Settings.Config.env_prefix.upper()}{k.upper()}={v}")
