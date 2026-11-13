import type { PlanTier } from "../api";

/** Centavos -> "R$ 249,00" (o billing-service guarda os valores em centavos). */
export const formatBRL = (cents: number): string =>
  (cents / 100).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });

/** Nome comercial do tier interno: community = Free, team = Pro. */
export const planName = (tier: PlanTier | string): string =>
  tier === "community" ? "Free" : tier === "team" ? "Pro" : tier === "enterprise" ? "Enterprise" : String(tier);

export const EVENT_LABEL: Record<string, string> = {
  "checkout.session.completed": "Checkout concluído",
  "customer.subscription.updated": "Assinatura atualizada",
  "customer.subscription.deleted": "Assinatura cancelada",
  "invoice.payment_failed": "Pagamento falhou",
  "invoice.payment_succeeded": "Pagamento confirmado",
};

export const eventLabel = (type: string): string => EVENT_LABEL[type] ?? type;
