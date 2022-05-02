from pydantic import BaseSettings


class Settings(BaseSettings):
    amcat4_elastic_host: str = "http://localhost:9200"
    amcat4_db_name: str = "amcat4.db"


settings = Settings()
