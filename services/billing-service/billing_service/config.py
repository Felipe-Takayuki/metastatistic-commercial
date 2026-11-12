import logging
import re
from typing import Any, Dict

from pydantic import field_validator, model_validator
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

# Valores de desenvolvimento (públicos no repositório): nunca aceitos em produção.
DEV_STRIPE_SECRET_KEY = "sk_test_metastatistic_dev_key"
DEV_STRIPE_PUBLISHABLE_KEY = "pk_test_metastatistic_dev_key"
DEV_STRIPE_WEBHOOK_SECRET = "whsec_metastatistic_dev_secret"
PRODUCTION_ENVIRONMENTS = {"production", "prod"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False, hide_input_in_errors=True, populate_by_name=True)

    environment: str = "development"
    port: int = 8007
    host: str = "0.0.0.0"
    # BILLING_DATABASE_URL existe para o modo "platform" (vários serviços no mesmo processo, que não podem dividir DATABASE_URL)
    database_url: str = Field(default="sqlite:///./data/billing.db", validation_alias=AliasChoices("BILLING_DATABASE_URL", "DATABASE_URL"))
    auth_service_url: str = "http://localhost:8002"

    # Stripe Keys & Secrets
    stripe_secret_key: str = DEV_STRIPE_SECRET_KEY
    stripe_publishable_key: str = DEV_STRIPE_PUBLISHABLE_KEY
    stripe_webhook_secret: str = DEV_STRIPE_WEBHOOK_SECRET
    stripe_mock_mode: bool = True  # Allows deterministic mock sessions & webhook checks in dev/tests

    # URL pública do app (APP_URL). Quando definida, as URLs de retorno do Stripe (sucesso, cancelamento e portal) partem dela;
    # BILLING_*_URL_DEFAULT explícitas continuam valendo. Sem APP_URL, valem os padrões de desenvolvimento abaixo.
    app_url: str = ""

    # IDs de preço do Stripe (criados no painel). STRIPE_PRICE_ID (um preço só, nome usado em outros projetos) vale como o preço
    # MENSAL do plano Team, a menos que STRIPE_PRICE_TEAM_MONTHLY exista. Sem nada definido ficam os IDs de exemplo
    # (price_team_monthly...), que só funcionam no modo mock.
    stripe_price_id: str = ""
    stripe_price_team_monthly: str = ""
    stripe_price_team_yearly: str = ""
    stripe_price_enterprise_monthly: str = ""
    stripe_price_enterprise_yearly: str = ""

    # Frontend Redirection URLs
    billing_success_url_default: str = "http://localhost:3000/billing/success?session_id={CHECKOUT_SESSION_ID}"
    billing_cancel_url_default: str = "http://localhost:3000/billing/canceled"
    billing_return_url_default: str = "http://localhost:3000/billing"

    @field_validator("stripe_secret_key", "stripe_publishable_key", "stripe_webhook_secret", mode="before")
    @classmethod
    def _empty_means_default(cls, value, info):
        # Variável vazia no .env/compose = "não definida" (usa o valor de desenvolvimento), não credencial vazia.
        if value is None or str(value).strip() == "":
            return cls.model_fields[info.field_name].default
        return value

    @model_validator(mode="after")
    def _derive_redirect_urls(self):
        base = self.app_url.strip().rstrip("/")
        if base:
            if not re.match(r"^https?://", base):
                base = "https://" + base   # APP_URL=app.exemplo.com -> https://app.exemplo.com (o Stripe exige URL absoluta)
            derived = {
                "billing_success_url_default": base + "/?billing=success&session_id={CHECKOUT_SESSION_ID}",
                "billing_cancel_url_default": base + "/?billing=canceled",
                "billing_return_url_default": base + "/",
            }
            for field, value in derived.items():
                if field not in self.model_fields_set:   # o que veio explícito (env/argumento) ganha de APP_URL
                    setattr(self, field, value)
        return self

    @property
    def is_production(self) -> bool:
        return self.environment.strip().lower() in PRODUCTION_ENVIRONMENTS

    @model_validator(mode="after")
    def _check_production(self):
        if self.is_production:
            problems = []
            if self.stripe_mock_mode:
                problems.append(
                    "STRIPE_MOCK_MODE=true (no modo mock o webhook aceita qualquer Stripe-Signature, permitindo "
                    "promover um tenant de graça)"
                )
            if self.stripe_secret_key == DEV_STRIPE_SECRET_KEY or "placeholder" in self.stripe_secret_key:
                problems.append("STRIPE_SECRET_KEY ausente ou de desenvolvimento")
            if self.stripe_webhook_secret == DEV_STRIPE_WEBHOOK_SECRET:
                problems.append("STRIPE_WEBHOOK_SECRET ausente ou de desenvolvimento")
            if problems:
                raise ValueError(
                    "Configuração insegura com ENVIRONMENT=production: " + "; ".join(problems) + ". "
                    "Defina as credenciais reais do Stripe e STRIPE_MOCK_MODE=false."
                )
        elif self.stripe_mock_mode:
            logger.warning("STRIPE_MOCK_MODE ativo: cobranças e webhooks simulados (apenas desenvolvimento).")
        if not self.stripe_mock_mode:
            missing = [name for name, price in stripe_price_ids(self).items() if price == PLACEHOLDER_PRICES[name]]
            if missing:
                logger.warning(
                    "Stripe real ligado, mas estes preços ainda são IDs de exemplo (o checkout deles não vai funcionar): %s. "
                    "Defina STRIPE_PRICE_ID (Team mensal) ou STRIPE_PRICE_TEAM_MONTHLY/_YEARLY e STRIPE_PRICE_ENTERPRISE_MONTHLY/_YEARLY.",
                    ", ".join(missing),
                )
        return self


PLACEHOLDER_PRICES = {
    "team_monthly": "price_team_monthly",
    "team_yearly": "price_team_yearly",
    "enterprise_monthly": "price_enterprise_monthly",
    "enterprise_yearly": "price_enterprise_yearly",
}


def stripe_price_ids(s: Settings) -> Dict[str, str]:
    """ID de preço efetivo de cada plano pago/ciclo: o específico, depois (só Team mensal) STRIPE_PRICE_ID, depois o exemplo."""
    return {
        "team_monthly": s.stripe_price_team_monthly.strip() or s.stripe_price_id.strip() or PLACEHOLDER_PRICES["team_monthly"],
        "team_yearly": s.stripe_price_team_yearly.strip() or PLACEHOLDER_PRICES["team_yearly"],
        "enterprise_monthly": s.stripe_price_enterprise_monthly.strip() or PLACEHOLDER_PRICES["enterprise_monthly"],
        "enterprise_yearly": s.stripe_price_enterprise_yearly.strip() or PLACEHOLDER_PRICES["enterprise_yearly"],
    }


settings = Settings()
_PRICES = stripe_price_ids(settings)

PLANS: Dict[str, Dict[str, Any]] = {
    "community": {
        "id": "community",
        "name": "Community Open-Source",
        "description": "Essential statistical analysis & BI for individuals and small research teams",
        "tier": "community",
        "price_monthly": 0,
        "price_yearly": 0,
        "currency": "usd",
        "stripe_price_id_monthly": None,
        "stripe_price_id_yearly": None,
        "features": ["jasp_engine", "csv_import", "sqlite_export"],
        "quotas": {
            "max_users": 3,
            "max_datasets": 10,
            "max_storage_mb": 500,
            "rate_limit_per_min": 60,
        },
    },
    "team": {
        "id": "team",
        "name": "Team Commercial",
        "description": "Collaborative analysis, team sharing, external PostgreSQL and higher limits",
        "tier": "team",
        "price_monthly": 4900,  # $49.00 USD in cents
        "price_yearly": 49000,  # $490.00 USD in cents (2 months free)
        "currency": "usd",
        "stripe_price_id_monthly": _PRICES["team_monthly"],
        "stripe_price_id_yearly": _PRICES["team_yearly"],
        "features": ["jasp_engine", "csv_import", "postgres_connector", "team_sharing"],
        "quotas": {
            "max_users": 15,
            "max_datasets": 100,
            "max_storage_mb": 10000,
            "rate_limit_per_min": 300,
        },
    },
    "enterprise": {
        "id": "enterprise",
        "name": "Enterprise High-Scale",
        "description": "Dual-engine (Python AGPL-free + R), SAML SSO, SCIM 2.0, audit trail and VIP queues",
        "tier": "enterprise",
        "price_monthly": 29900,  # $299.00 USD in cents
        "price_yearly": 299000,  # $2990.00 USD in cents
        "currency": "usd",
        "stripe_price_id_monthly": _PRICES["enterprise_monthly"],
        "stripe_price_id_yearly": _PRICES["enterprise_yearly"],
        "features": [
            "jasp_engine",
            "proprietary_engine",
            "all_connectors",
            "sso_saml",
            "audit_log",
            "unlimited",
        ],
        "quotas": {
            "max_users": 1_000_000,
            "max_datasets": 1_000_000,
            "max_storage_mb": 10_000_000,
            "rate_limit_per_min": 5000,
        },
    },
}
