from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False)

    port: int = 8005
    database_url: str = "sqlite:///./data/bi_reports.db"
    data_dir: str = "/data"
    default_tenant_id: str = "default"


settings = Settings()
