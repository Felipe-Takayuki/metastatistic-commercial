from typing import Any, Dict
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False)

    port: int = 8007
    host: str = "0.0.0.0"
    database_url: str = "sqlite:///./data/billing.db"
    auth_service_url: str = "http://localhost:8002"

    # Stripe Keys & Secrets
    stripe_secret_key: str = "sk_test_metastatistic_dev_key"
    stripe_publishable_key: str = "pk_test_metastatistic_dev_key"
    stripe_webhook_secret: str = "whsec_metastatistic_dev_secret"
    stripe_mock_mode: bool = True  # Allows deterministic mock sessions & webhook checks in dev/tests

    # Frontend Redirection URLs
    billing_success_url_default: str = "http://localhost:3000/billing/success?session_id={CHECKOUT_SESSION_ID}"
    billing_cancel_url_default: str = "http://localhost:3000/billing/canceled"
    billing_return_url_default: str = "http://localhost:3000/billing"


settings = Settings()

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
        "stripe_price_id_monthly": "price_team_monthly",
        "stripe_price_id_yearly": "price_team_yearly",
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
        "stripe_price_id_monthly": "price_enterprise_monthly",
        "stripe_price_id_yearly": "price_enterprise_yearly",
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
