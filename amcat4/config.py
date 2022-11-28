"""
AmCAT4 Configuration

We generally read configuration from 3 sources:
- Environment variables
- Command line flags (from __main__.py)
- A .env file, either in the current working directory or in a location specified
  by the --config-file flag or AMCAT4_CONFIG_FILE environment variable
"""

from pydantic import BaseSettings
# This shouldn't be necessary according to the docs, but without the load_dotenv it doesn't work at
# least when running with python -m amcat4.config...
from dotenv import load_dotenv
load_dotenv()


class Settings(BaseSettings):
    elastic_host: str = "http://localhost:9200"

    class Config:
        env_prefix = "amcat4_"


def get_settings():
    settings = Settings()


if __name__ == '__main__':
    for k, v in settings.dict().items():
        print(f"{Settings.Config.env_prefix.upper()}{k.upper()}={v}")
