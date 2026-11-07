from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False)

    port: int = 8004
    host: str = "0.0.0.0"
    data_dir: str = "/data"
    query_memory_limit: str = "512MB"
    query_threads: int = 2
    query_timeout_s: float = 30.0
    query_row_limit: int = 10000
    allowed_tenants: list[str] = ["*"]


settings = Settings()
