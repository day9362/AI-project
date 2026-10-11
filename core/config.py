from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg://vcos:vcos@127.0.0.1:5432/vcos"
    redis_url: str = "redis://127.0.0.1:6379/0"
    session_ttl_seconds: int = 43_200
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    default_password: str = "changeme"

    cluster_base_url: str = "https://cluster.simuoss.cn/api"
    cluster_token: str = ""
    cluster_timeout_s: float = 20
    cluster_sync_enabled: bool = True

    fleet_interval_s: int = 5
    slots_interval_s: int = 5
    runs_interval_s: int = 5
    agg_interval_s: int = 30
    alarm_interval_s: int = 10

    drift_c: float = 0.15
    degraded_alarm: bool = True
    sentinel_as_data_anomaly: bool = True


settings = Settings()
