from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg://vcos:vcos@127.0.0.1:5432/vcos"
    redis_url: str = "redis://127.0.0.1:6379/0"
    session_ttl_seconds: int = 43_200
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    default_password: str = "changeme"


settings = Settings()
