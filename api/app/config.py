from pydantic_settings import BaseSettings
from pydantic import PostgresDsn

class Settings(BaseSettings):
    database_url: PostgresDsn

    class Config:
        env_file = ".env"

settings = Settings()
