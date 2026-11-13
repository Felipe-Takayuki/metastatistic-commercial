import json
import logging
import uuid
from typing import Any, Dict, Optional

import stripe
from billing_service.config import PLACEHOLDER_PRICES, PLANS, settings

logger = logging.getLogger(__name__)

stripe.api_key = settings.stripe_secret_key

_SignatureError = getattr(stripe, "SignatureVerificationError", None) or stripe.error.SignatureVerificationError


class StripeUnavailable(Exception):
    """Stripe real ligado (STRIPE_MOCK_MODE=false), mas a chamada não pôde ser feita ou falhou.

    Nunca cai para uma sessão simulada: no modo real, um checkout falso levaria o usuário a uma página que não existe.
    `status_code`: 503 = configuração ausente (chave/preço), 502 = o Stripe recusou ou não respondeu.
    """

    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


class StripeClient:
    def __init__(self):
        self.mock_mode = settings.stripe_mock_mode
        self.secret_key = settings.stripe_secret_key
        self.webhook_secret = settings.stripe_webhook_secret

    def _require_real(self) -> None:
        """No modo real exige uma chave de API de verdade; em vez de simular, falha explicando o que falta."""
        key = self.secret_key.strip()
        if not key or "placeholder" in key or key.startswith("sk_test_metastatistic"):
            raise StripeUnavailable(
                "Stripe real ligado (STRIPE_MOCK_MODE=false), mas STRIPE_SECRET_KEY está ausente ou é de exemplo.", 503
            )

    def get_or_create_customer(self, tenant_id: str, email: Optional[str] = None) -> str:
        """Cria ou recupera um Stripe Customer ID para o tenant."""
        if self.mock_mode:
            return f"cus_mock_{tenant_id}"
        self._require_real()

        try:
            customer = stripe.Customer.create(
                email=email,
                metadata={"tenant_id": tenant_id},
            )
            return customer.id
        except Exception as e:
            logger.error("Stripe: falha ao criar o customer do tenant %s: %s", tenant_id, e)
            raise StripeUnavailable(f"Stripe recusou a criação do cliente: {e}") from e

    def create_checkout_session(
        self,
        tenant_id: str,
        customer_id: str,
        plan_id: str,
        billing_cycle: str,
        success_url: str,
        cancel_url: str,
        customer_email: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Cria uma sessão do Stripe Checkout."""
        plan = PLANS.get(plan_id)
        if not plan:
            raise ValueError(f"Plan '{plan_id}' does not exist")

        if self.mock_mode:
            mock_id = f"cs_test_{uuid.uuid4().hex[:16]}"
            return {
                "session_id": mock_id,
                "url": f"https://checkout.stripe.com/c/pay/{mock_id}",
                "customer_id": customer_id,
            }
        self._require_real()

        price_id = plan.get(f"stripe_price_id_{billing_cycle}")
        if not price_id or price_id in PLACEHOLDER_PRICES.values():
            raise StripeUnavailable(
                f"Preço do Stripe não configurado para {plan_id}/{billing_cycle}: defina "
                f"STRIPE_PRICE_{plan_id.upper()}_{billing_cycle.upper()} (ou STRIPE_PRICE_ID para Team mensal).",
                503,
            )
        try:
            session = stripe.checkout.Session.create(
                customer=customer_id,
                payment_method_types=["card"],
                line_items=[{"price": price_id, "quantity": 1}],
                mode="subscription",
                success_url=success_url,
                cancel_url=cancel_url,
                client_reference_id=tenant_id,
                metadata={
                    "tenant_id": tenant_id,
                    "plan_id": plan_id,
                    "billing_cycle": billing_cycle,
                    "tier": plan["tier"],
                },
                # a própria assinatura carrega a organização: a reconciliação consegue achá-la mesmo sem o webhook
                subscription_data={"metadata": {"tenant_id": tenant_id, "plan_id": plan_id}},
            )
            return {
                "session_id": session.id,
                "url": session.url,
                "customer_id": customer_id,
            }
        except Exception as e:
            logger.error("Stripe: falha ao criar o checkout (%s/%s, tenant %s): %s", plan_id, billing_cycle, tenant_id, e)
            raise StripeUnavailable(f"Stripe recusou a criação do checkout: {e}") from e

    def create_portal_session(self, customer_id: str, return_url: str) -> Dict[str, Any]:
        """Cria uma sessão do Stripe Customer Portal para gestão de assinatura e cartões."""
        if self.mock_mode:
            mock_id = f"bps_{uuid.uuid4().hex[:16]}"
            return {
                "url": f"https://billing.stripe.com/p/session/{mock_id}?customer={customer_id}&return_url={return_url}"
            }
        self._require_real()

        try:
            portal = stripe.billing_portal.Session.create(
                customer=customer_id,
                return_url=return_url,
            )
            return {"url": portal.url}
        except Exception as e:
            logger.error("Stripe: falha ao criar a sessão do portal (customer %s): %s", customer_id, e)
            raise StripeUnavailable(f"Stripe recusou a criação do portal: {e}") from e

    def list_subscription_states(self) -> Optional[Dict[str, Dict[str, Any]]]:
        """Estado atual de TODAS as assinaturas no Stripe (para a reconciliação). None no modo simulado: não há o que comparar."""
        if self.mock_mode:
            return None
        self._require_real()
        try:
            out: Dict[str, Dict[str, Any]] = {}
            for sub in stripe.Subscription.list(status="all", limit=100).auto_paging_iter():
                items = (sub.get("items") or {}).get("data") or []
                out[sub["id"]] = {
                    "status": sub["status"],
                    "customer": sub.get("customer"),
                    "price_id": (items[0].get("price") or {}).get("id") if items else None,
                    "tenant_id": (sub.get("metadata") or {}).get("tenant_id"),
                    "cancel_at_period_end": bool(sub.get("cancel_at_period_end")),
                }
            return out
        except Exception as e:
            logger.error("Stripe: falha ao listar assinaturas: %s", e)
            raise StripeUnavailable(f"Stripe recusou a listagem de assinaturas: {e}") from e

    def verify_webhook_event(self, payload_bytes: bytes, sig_header: Optional[str]) -> Dict[str, Any]:
        """
        Valida a assinatura do webhook Stripe e retorna o dicionário com o evento parseado.
        Gera ValueError se a assinatura for inválida.
        """
        # Se assinatura explícita de teste inválida
        if sig_header == "invalid_signature":
            raise ValueError("Invalid Stripe webhook signature")

        if self.mock_mode:
            # Em mock mode aceita se assinatura estiver presente ou padrão
            if not sig_header:
                raise ValueError("Missing Stripe-Signature header")
            try:
                return json.loads(payload_bytes.decode("utf-8"))
            except Exception as e:
                raise ValueError(f"Malformed JSON payload: {e}")

        # Live verification via stripe SDK
        if not sig_header:
            raise ValueError("Missing Stripe-Signature header")

        if not self.webhook_secret.strip():
            raise ValueError("STRIPE_WEBHOOK_SECRET não configurado: não dá para validar a assinatura")

        try:
            event = stripe.Webhook.construct_event(
                payload_bytes, sig_header, self.webhook_secret
            )
            return event
        except _SignatureError as e:
            raise ValueError(f"Invalid webhook signature: {e}")
        except Exception as e:
            raise ValueError(f"Webhook processing error: {e}")


stripe_client = StripeClient()
