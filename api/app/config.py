from pydantic_settings import BaseSettings
from pydantic import PostgresDsn
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"

class Settings(BaseSettings):
    database_url: PostgresDsn
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 10080  # Default to 7 days

    class Config:
        env_file = ENV_PATH
        case_sensitive = False
        extra = "ignore"
        
settings = Settings()
