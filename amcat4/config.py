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
from pydantic import BaseSettings
from dotenv import load_dotenv


class AuthOptions(str, Enum):
    # everyone (that can reach the server) can do anything they want
    no_auth = "no_auth"
    # everyone can use the server, dependent on index-level guest_role authorization settings
    allow_guests = "allow_guests"
    # everyone can use the server, if they have a valid middlecat login,
    # and dependent on index-level guest_role authorization settings
    allow_authenticated_guests = "allow_authenticated_guests"
    # only people with a valid middlecat login and an explicit server role can use the server
    authorized_users_only = "authorized_users_only"


class Settings(BaseSettings):
    # Location of a .env file (if used) relative to working directory
    env_file: Path = ".env"
    # Host this instance is served at (needed for checking tokens)
    host: str = "http://localhost:5000"
    # Elasticsearch host
    elastic_host: str = "http://localhost:9200"
    # Elasticsearch index to store authorization information in
    system_index = "amcat4_system"
    # Do we require authorization?
    auth: AuthOptions = AuthOptions.no_auth
    # Middlecat server to trust as ID provider
    middlecat_url: str = "https://middlecat.up.railway.app"
    # Email address for a hardcoded admin email (useful for setup and recovery)
    admin_email: str = None

    class Config:
        env_prefix = "amcat4_"


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
