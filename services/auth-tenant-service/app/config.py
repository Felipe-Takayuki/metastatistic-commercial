from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False)

    jwt_secret_key: str = "metastatistic-jwt-super-secret-key-change-in-prod-2026"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440  # 24 horas
    database_url: str = "sqlite:///./auth_tenant.db"
    audit_service_url: str = "http://localhost:8008"  # vazio desativa o envio de eventos
    port: int = 8002
    host: str = "0.0.0.0"


settings = Settings()
