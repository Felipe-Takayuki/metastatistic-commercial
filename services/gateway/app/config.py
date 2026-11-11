import logging

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

# Valor de desenvolvimento (público no repositório) e o placeholder do chart Helm: nunca aceitos em produção.
DEV_JWT_SECRET = "metastatistic-jwt-super-secret-key-change-in-prod-2026"
INSECURE_JWT_SECRETS = {DEV_JWT_SECRET, "change-this-in-production-to-a-secure-256bit-secret"}
MIN_JWT_SECRET_LENGTH = 32
PRODUCTION_ENVIRONMENTS = {"production", "prod"}



class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False, hide_input_in_errors=True)

    auth_service_url: str = "http://localhost:8002"
    stat_orchestrator_url: str = "http://localhost:8003"
    data_engine_service_url: str = "http://localhost:8004"
    bi_report_service_url: str = "http://localhost:8005"
    export_service_url: str = "http://localhost:8006"
    billing_service_url: str = "http://localhost:8007"
    audit_service_url: str = "http://localhost:8008"
    data_api_url: str = "http://localhost:8000"
    web_url: str = "http://localhost:3000"
    default_tenant_id: str = "default"
    environment: str = "development"
    jwt_secret_key: str = DEV_JWT_SECRET
    port: int = 8080
    host: str = "0.0.0.0"

    @field_validator("jwt_secret_key", mode="before")
    @classmethod
    def _empty_secret_means_default(cls, value):
        # `JWT_SECRET_KEY=` vazio no .env/compose deve se comportar como "não definido", não como segredo vazio.
        return DEV_JWT_SECRET if value is None or str(value).strip() == "" else value

    @property
    def is_production(self) -> bool:
        return self.environment.strip().lower() in PRODUCTION_ENVIRONMENTS

    @model_validator(mode="after")
    def _check_secrets(self):
        if self.is_production:
            if self.jwt_secret_key in INSECURE_JWT_SECRETS or len(self.jwt_secret_key) < MIN_JWT_SECRET_LENGTH:
                raise ValueError(
                    "Configuração insegura com ENVIRONMENT=production: JWT_SECRET_KEY está ausente, é um valor padrão "
                    f"do repositório ou tem menos de {MIN_JWT_SECRET_LENGTH} caracteres. "
                    "Defina uma chave própria (ex.: `openssl rand -hex 32`)."
                )
        elif self.jwt_secret_key == DEV_JWT_SECRET:
            logger.warning("JWT_SECRET_KEY não definido: usando a chave de desenvolvimento (insegura). Defina-a no .env.")
        return self


settings = Settings()
