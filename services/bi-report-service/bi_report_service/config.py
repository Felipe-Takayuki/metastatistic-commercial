from pathlib import Path
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False, populate_by_name=True)

    port: int = 8005
    # BI_DATABASE_URL existe para o modo "platform" (vários serviços no mesmo processo, que não podem dividir DATABASE_URL)
    database_url: str = Field(default="sqlite:///./data/bi_reports.db", validation_alias=AliasChoices("BI_DATABASE_URL", "DATABASE_URL"))
    data_dir: str = "/data"
    default_tenant_id: str = "default"


settings = Settings()
