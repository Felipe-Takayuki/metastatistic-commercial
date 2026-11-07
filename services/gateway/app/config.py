from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False)

    auth_service_url: str = "http://localhost:8002"
    stat_orchestrator_url: str = "http://localhost:8003"
    data_engine_service_url: str = "http://localhost:8004"
    data_api_url: str = "http://localhost:8000"
    web_url: str = "http://localhost:3000"
    default_tenant_id: str = "default"
    jwt_secret_key: str = "metastatistic-jwt-super-secret-key-change-in-prod-2026"
    port: int = 8080
    host: str = "0.0.0.0"


settings = Settings()
