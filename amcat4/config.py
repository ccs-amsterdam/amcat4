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
    elastic_host: str = "http://localhost:9200"
    middlecat_url: str = None
    admin_password: str = None
    config_file: Path = None

    class Config:
        env_prefix = "amcat4_"


@functools.lru_cache()
def get_settings():
    # This shouldn't be necessary according to the docs, but without the load_dotenv it doesn't work at
    # least when running with python -m amcat4.config...
    temp = Settings()
    load_dotenv(temp.config_file)
    return Settings()


if __name__ == '__main__':
    # Echo the settings
    for k, v in get_settings().dict().items():
        print(f"{Settings.Config.env_prefix.upper()}{k.upper()}={v}")
