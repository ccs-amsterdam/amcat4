"""
AmCAT4 Configuration

We read configuration from 3 sources, in order of precedence (higher is more priority)
- Command line flags (from __main__.py)
- Environment variables (also read from .env in the working directory)
- A amcat.env file, either in the current working directory or in a location specified
  by the --config-file flag or AMCAT4_CONFIG_FILE environment variable
"""
import functools
from pathlib import Path
from pydantic import BaseSettings
from dotenv import load_dotenv


class Settings(BaseSettings):
    # Location of a .env file (if used) relative to working directory
    env_file: Path = ".env"
    # Host this instance is served at (needed for checking tokens)
    host: str = "http://localhost:5000"
    # Elasticsearch host
    elastic_host: str = "http://localhost:9200"
    # Elasticsearch index to store authorization information in
    system_index = "amcat4_system"
    # Middlecat server to trust as ID provider
    middlecat_url: str = None
    # Password for a global admin user (useful for setup and recovery)
    admin_password: str = None
    # Key used to create admin tokens. Please change in production if admin password is used!
    key: str = "PLEASE CHANGE IN PRODUCTION IF USING ADMIN PASSWORD"

    class Config:
        env_prefix = "amcat4_"


@functools.lru_cache()
def get_settings():
    # This shouldn't be necessary according to the docs, but without the load_dotenv it doesn't work at
    # least when running with python -m amcat4.config...
    temp = Settings()
    load_dotenv(temp.env_file)
    return Settings()


if __name__ == '__main__':
    # Echo the settings
    for k, v in get_settings().dict().items():
        print(f"{Settings.Config.env_prefix.upper()}{k.upper()}={v}")
