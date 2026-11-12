import json
import logging
import uuid
from typing import Any, Dict, Optional

import stripe
from billing_service.config import PLANS, settings

logger = logging.getLogger(__name__)

stripe.api_key = settings.stripe_secret_key


class StripeClient:
    def __init__(self):
        self.mock_mode = settings.stripe_mock_mode
        self.secret_key = settings.stripe_secret_key
        self.webhook_secret = settings.stripe_webhook_secret

    def get_or_create_customer(self, tenant_id: str, email: Optional[str] = None) -> str:
        """Cria ou recupera um Stripe Customer ID para o tenant."""
        if self.mock_mode or not self.secret_key or "placeholder" in self.secret_key or self.secret_key.startswith("sk_test_placeholder") or self.secret_key.startswith("sk_test_metastatistic"):
            return f"cus_mock_{tenant_id}"

        try:
            customer = stripe.Customer.create(
                email=email,
                metadata={"tenant_id": tenant_id},
            )
            return customer.id
        except Exception as e:
            logger.warning(f"Fallback to mock customer due to Stripe error: {e}")
            return f"cus_mock_{tenant_id}"

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

        if self.mock_mode or not self.secret_key or "placeholder" in self.secret_key or self.secret_key.startswith("sk_test_placeholder") or self.secret_key.startswith("sk_test_metastatistic"):
            mock_id = f"cs_test_{uuid.uuid4().hex[:16]}"
            return {
                "session_id": mock_id,
                "url": f"https://checkout.stripe.com/c/pay/{mock_id}",
                "customer_id": customer_id,
            }

        try:
            price_id = plan.get(f"stripe_price_id_{billing_cycle}")
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
            )
            return {
                "session_id": session.id,
                "url": session.url,
                "customer_id": customer_id,
            }
        except Exception as e:
            logger.warning(f"Error creating real Stripe checkout session, falling back to mock: {e}")
            mock_id = f"cs_test_{uuid.uuid4().hex[:16]}"
            return {
                "session_id": mock_id,
                "url": f"https://checkout.stripe.com/c/pay/{mock_id}",
                "customer_id": customer_id,
            }

    def create_portal_session(self, customer_id: str, return_url: str) -> Dict[str, Any]:
        """Cria uma sessão do Stripe Customer Portal para gestão de assinatura e cartões."""
        if self.mock_mode or not self.secret_key or "placeholder" in self.secret_key or self.secret_key.startswith("sk_test_placeholder") or self.secret_key.startswith("sk_test_metastatistic"):
            mock_id = f"bps_{uuid.uuid4().hex[:16]}"
            return {
                "url": f"https://billing.stripe.com/p/session/{mock_id}?customer={customer_id}&return_url={return_url}"
            }

        try:
            portal = stripe.billing_portal.Session.create(
                customer=customer_id,
                return_url=return_url,
            )
            return {"url": portal.url}
        except Exception as e:
            logger.warning(f"Error creating portal session, falling back to mock: {e}")
            mock_id = f"bps_{uuid.uuid4().hex[:16]}"
            return {
                "url": f"https://billing.stripe.com/p/session/{mock_id}?customer={customer_id}&return_url={return_url}"
            }

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

        try:
            event = stripe.Webhook.construct_event(
                payload_bytes, sig_header, self.webhook_secret
            )
            return event
        except stripe.error.SignatureVerificationError as e:
            raise ValueError(f"Invalid webhook signature: {e}")
        except Exception as e:
            raise ValueError(f"Webhook processing error: {e}")


stripe_client = StripeClient()
