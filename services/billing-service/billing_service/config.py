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

    # ID do preço mensal (em R$) do plano Pro, criado no painel do Stripe em modo de teste. STRIPE_PRICE_ID e
    # STRIPE_PRICE_PRO_MONTHLY são sinônimos (o específico ganha). Sem nenhum fica o ID de exemplo (price_pro_monthly),
    # que só funciona no modo mock.
    stripe_price_id: str = ""
    stripe_price_pro_monthly: str = ""

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
                    "Defina STRIPE_PRICE_ID (ou STRIPE_PRICE_PRO_MONTHLY) com o ID do preço mensal do plano Pro.",
                    ", ".join(missing),
                )
        return self


PLACEHOLDER_PRICES = {
    "pro_monthly": "price_pro_monthly",
}


def stripe_price_ids(s: Settings) -> Dict[str, str]:
    """ID de preço efetivo de cada plano pago: o específico, depois STRIPE_PRICE_ID, depois o exemplo (só no mock)."""
    return {
        "pro_monthly": s.stripe_price_pro_monthly.strip() or s.stripe_price_id.strip() or PLACEHOLDER_PRICES["pro_monthly"],
    }


settings = Settings()
_PRICES = stripe_price_ids(settings)

# Catálogo vendido: Free e Pro, assinatura mensal em reais (centavos). `tier` é o nome interno que o auth-tenant-service,
# o gateway e o stat-orchestrator já usam (community = Free, team = Pro); `enterprise` segue existindo como contrato sob medida,
# fora do Stripe. As cotas daqui são as exibidas na tela de planos; quem as aplica é o auth-tenant-service (`TIER_QUOTAS`), que a API consulta.
PLANS: Dict[str, Dict[str, Any]] = {
    "free": {
        "id": "free",
        "name": "Free",
        "description": "Para conhecer a plataforma: análises estatísticas essenciais para um pesquisador ou grupo pequeno.",
        "tier": "community",
        "price_monthly": 0,
        "price_yearly": 0,
        "currency": "brl",
        "stripe_price_id_monthly": None,
        "stripe_price_id_yearly": None,
        "features": [
            "Até 3 usuários",
            "Até 5 datasets (10 MB cada)",
            "Análises estatísticas essenciais",
            "Relatórios e dashboards básicos",
        ],
        "quotas": {
            "max_users": 3,
            "max_datasets": 5,
            "max_upload_mb": 10,
            "max_storage_mb": 50,
            "rate_limit_per_min": 60,
        },
    },
    "pro": {
        "id": "pro",
        "name": "Pro",
        "description": "Para laboratórios e equipes: mais usuários, datasets maiores e catálogo estatístico completo.",
        "tier": "team",
        "price_monthly": 24900,  # R$ 249,00 em centavos
        "price_yearly": 0,       # só cobrança mensal
        "currency": "brl",
        "stripe_price_id_monthly": _PRICES["pro_monthly"],
        "stripe_price_id_yearly": None,
        "features": [
            "Até 15 usuários",
            "Até 100 datasets (200 MB cada)",
            "Catálogo completo: ANOVA, ANCOVA, não paramétricos e Bayes",
            "Conectores SQL e compartilhamento entre equipes",
            "Exportação multi-formato (HTML, PDF, DOCX)",
        ],
        "quotas": {
            "max_users": 15,
            "max_datasets": 100,
            "max_upload_mb": 200,
            "max_storage_mb": 10000,
            "rate_limit_per_min": 300,
        },
    },
}
