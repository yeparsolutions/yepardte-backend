# app/core/config.py
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Base de datos
    DATABASE_URL: str

    # JWT
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    # DTECore
    DTECORE_URL: str = ""
    DTECORE_API_KEY: str = ""

    # CORS
    FRONTEND_URL: str = "http://localhost:3000"

    # Cifrado firma digital
    ENCRYPTION_KEY: str = ""

    class Config:
        env_file = ".env"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
