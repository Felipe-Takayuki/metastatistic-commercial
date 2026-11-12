from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False, populate_by_name=True)

    # AUDIT_DATABASE_URL existe para o modo "platform" (vários serviços no mesmo processo, que não podem dividir DATABASE_URL)

    database_url: str = Field(default="sqlite:///./audit.db", validation_alias=AliasChoices("AUDIT_DATABASE_URL", "DATABASE_URL"))
    port: int = 8008
    host: str = "0.0.0.0"


settings = Settings()
