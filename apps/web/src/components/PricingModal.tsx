import { useEffect, useState } from "react";
import { api, type BillingCycle, type PlanInfo, type PlanUsage, type SubscriptionInfo } from "../api";
import { formatBRL, planName } from "../lib/billing";

interface PricingModalProps {
  onClose: () => void;
}

// Só aparece enquanto /billing/plans não responde; os números oficiais vêm do billing-service.
const DEFAULT_PLANS: PlanInfo[] = [
  {
    id: "free",
    name: "Free",
    description: "Para conhecer a plataforma: análises essenciais para um pesquisador ou grupo pequeno.",
    tier: "community",
    price_monthly: 0,
    price_yearly: 0,
    currency: "brl",
    features: ["Até 3 usuários", "Até 5 datasets (10 MB cada)", "Análises estatísticas essenciais", "Relatórios e dashboards básicos"],
    quotas: { max_users: 3, max_datasets: 5, max_upload_mb: 10 },
  },
  {
    id: "pro",
    name: "Pro",
    description: "Para laboratórios e equipes: mais usuários, datasets maiores e catálogo estatístico completo.",
    tier: "team",
    price_monthly: 24900,
    price_yearly: 0,
    currency: "brl",
    features: [
      "Até 15 usuários",
      "Até 100 datasets (200 MB cada)",
      "Catálogo completo: ANOVA, ANCOVA, não paramétricos e Bayes",
      "Conectores SQL e compartilhamento entre equipes",
      "Exportação multi-formato (HTML, PDF, DOCX)",
    ],
    quotas: { max_users: 15, max_datasets: 100, max_upload_mb: 200 },
  },
];

export function PricingModal({ onClose }: PricingModalProps) {
  const cycle: BillingCycle = "monthly"; // só há cobrança mensal
  const [plans, setPlans] = useState<PlanInfo[]>(DEFAULT_PLANS);
  const [subscription, setSubscription] = useState<SubscriptionInfo | null>(null);
  const [usage, setUsage] = useState<PlanUsage | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionBusy, setActionBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    async function loadData() {
      try {
        const [fetchedPlans, fetchedSub, fetchedUsage] = await Promise.allSettled([
          api.getBillingPlans(),
          api.getSubscription(),
          api.getPlanUsage(),
        ]);

        if (mounted) {
          if (fetchedPlans.status === "fulfilled" && fetchedPlans.value.length > 0) {
            setPlans(fetchedPlans.value);
          }
          if (fetchedSub.status === "fulfilled" && fetchedSub.value) {
            setSubscription(fetchedSub.value);
          }
          if (fetchedUsage.status === "fulfilled") setUsage(fetchedUsage.value);
        }
      } catch (err) {
        if (mounted) {
          setError((err as Error).message || "Falha ao carregar informações de faturamento.");
        }
      } finally {
        if (mounted) setLoading(false);
      }
    }
    void loadData();
    return () => {
      mounted = false;
    };
  }, []);

  const handleUpgrade = async (planId: string) => {
    setActionBusy(planId);
    setError(null);
    try {
      const res = await api.createCheckoutSession(planId, cycle);
      const targetUrl = res.url || res.checkout_url;
      if (targetUrl) {
        window.location.href = targetUrl;
      } else {
        setError("Não foi possível gerar a URL de checkout. Tente novamente.");
        setActionBusy(null);
      }
    } catch (err) {
      setError((err as Error).message || "Erro ao iniciar a assinatura.");
      setActionBusy(null);
    }
  };

  const handlePortal = async () => {
    setActionBusy("portal");
    setError(null);
    try {
      const res = await api.createPortalSession(window.location.href);
      const portalUrl = res.url || res.portal_url;
      if (portalUrl) {
        window.location.href = portalUrl;
      } else {
        setError("Não foi possível abrir o portal do cliente Stripe.");
        setActionBusy(null);
      }
    } catch (err) {
      setError((err as Error).message || "Erro ao abrir o portal de assinatura.");
      setActionBusy(null);
    }
  };

  const currentTier = subscription?.tier || "community";
  const paid = currentTier !== "community";

  return (
    <div
      className="modal-backdrop"
      onKeyDown={(e) => e.key === "Escape" && onClose()}
      role="presentation"
    >
      <div
        className="modal card wide"
        role="dialog"
        aria-modal="true"
        aria-label="Planos e assinatura Metastatistic"
        style={{ maxWidth: 760 }}
      >
        <div className="modal-head">
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect x="2" y="5" width="20" height="14" rx="2" />
              <line x1="2" y1="10" x2="22" y2="10" />
            </svg>
            <strong>Planos e assinatura</strong>
          </div>
          <span className="spacer" />
          {loading && (
            <span className="spinner" aria-label="Carregando dados..." style={{ width: 14, height: 14 }} />
          )}
          {!loading && subscription && (
            <span
              className="chip"
              data-testid="current-plan"
              style={{
                textTransform: "uppercase",
                letterSpacing: "0.05em",
                fontWeight: 600,
                fontSize: 11,
                background: paid ? "var(--accent-wash)" : "var(--surface-2)",
                color: paid ? "var(--accent)" : "var(--text-secondary)",
              }}
            >
              Plano atual: {planName(currentTier)}
              {subscription.status === "past_due" ? " · pagamento em atraso" : ""}
              {subscription.cancel_at_period_end ? " · cancela no fim do ciclo" : ""}
            </span>
          )}
          <button className="btn ghost sm" onClick={onClose} aria-label="Fechar modal">
            ✕
          </button>
        </div>

        <div className="modal-body" style={{ padding: "20px 24px", gap: 20 }}>
          {error && (
            <div className="alert" role="alert" style={{ display: "flex", justifyContent: "space-between" }}>
              <span>{error}</span>
              <button className="btn ghost sm" onClick={() => setError(null)}>✕</button>
            </div>
          )}

          {usage && (
            <div className={usage.near_limit ? "alert" : "muted small"} data-testid="plan-usage" style={{ margin: 0 }}>
              Uso da organização: {usage.datasets.used}{usage.datasets.limit ? ` de ${usage.datasets.limit}` : ""} datasets ·{" "}
              {usage.storage_mb.used.toLocaleString("pt-BR")}{usage.storage_mb.limit ? ` de ${usage.storage_mb.limit}` : ""} MB de armazenamento
              {usage.near_limit ? " — perto do limite do plano." : "."}
            </div>
          )}

          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(270px, 1fr))",
              gap: 16,
              alignItems: "stretch",
            }}
          >
            {plans.map((plan) => {
              const isCurrent = currentTier === plan.tier;
              const isPro = plan.id === "pro";
              const price = plan.price_monthly;
              const periodLabel = price === 0 ? "para sempre" : "/mês";

              return (
                <div
                  key={plan.id}
                  className="card"
                  data-testid={`plan-${plan.id}`}
                  style={{
                    position: "relative",
                    display: "flex",
                    flexDirection: "column",
                    padding: 20,
                    borderRadius: 10,
                    border: isPro
                      ? "2px solid var(--accent)"
                      : isCurrent
                      ? "2px solid var(--series-3)"
                      : "1px solid var(--border)",
                    background: "var(--surface-1)",
                    boxShadow: isPro ? "0 4px 20px rgba(0,0,0,0.08)" : "none",
                  }}
                >
                  {isPro && (
                    <div
                      style={{
                        position: "absolute",
                        top: -11,
                        left: "50%",
                        transform: "translateX(-50%)",
                        background: "var(--accent)",
                        color: "var(--on-accent)",
                        fontSize: 10,
                        fontWeight: 700,
                        padding: "2px 10px",
                        borderRadius: 12,
                        textTransform: "uppercase",
                        letterSpacing: "0.06em",
                      }}
                    >
                      Recomendado
                    </div>
                  )}

                  <div style={{ marginBottom: 12 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <h3 style={{ margin: 0, fontSize: 18, fontWeight: 700 }}>{plan.name}</h3>
                      {isCurrent && (
                        <span
                          className="chip"
                          style={{
                            fontSize: 10,
                            background: "var(--series-3)",
                            color: "#fff",
                            fontWeight: 600,
                          }}
                        >
                          Ativo
                        </span>
                      )}
                    </div>
                    <p style={{ margin: "6px 0 0", fontSize: 12, color: "var(--text-secondary)", minHeight: 32 }}>
                      {plan.description}
                    </p>
                  </div>

                  <div style={{ margin: "10px 0 16px" }}>
                    <span style={{ fontSize: 32, fontWeight: 750, letterSpacing: "-0.02em" }}>
                      {formatBRL(price)}
                    </span>
                    <span style={{ fontSize: 13, color: "var(--text-muted)", marginLeft: 4 }}>
                      {periodLabel}
                    </span>
                  </div>

                  <hr style={{ border: "none", borderTop: "1px solid var(--grid)", margin: "0 0 16px" }} />

                  <div style={{ flex: 1, marginBottom: 20 }}>
                    <div style={{ fontSize: 12, fontWeight: 600, color: "var(--text-secondary)", marginBottom: 8 }}>
                      Recursos inclusos:
                    </div>
                    <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: 8 }}>
                      {plan.features.map((feature, idx) => (
                        <li
                          key={idx}
                          style={{
                            display: "flex",
                            alignItems: "flex-start",
                            gap: 8,
                            fontSize: 12,
                            lineHeight: 1.4,
                            color: "var(--text-primary)",
                          }}
                        >
                          <span style={{ color: "var(--series-3)", fontWeight: "bold", fontSize: 14 }}>✓</span>
                          <span>{feature}</span>
                        </li>
                      ))}
                    </ul>
                  </div>

                  <div>
                    {isCurrent ? (
                      <button className="btn ghost sm" style={{ width: "100%", cursor: "default", opacity: 0.8 }} disabled>
                        ✓ Plano atual
                      </button>
                    ) : plan.id === "free" ? (
                      <button className="btn ghost sm" style={{ width: "100%", cursor: "default", opacity: 0.6 }} disabled>
                        Incluído
                      </button>
                    ) : (
                      <button
                        className={`btn sm ${isPro ? "primary" : ""}`}
                        style={{ width: "100%" }}
                        onClick={() => handleUpgrade(plan.id)}
                        disabled={actionBusy !== null}
                      >
                        {actionBusy === plan.id ? (
                          <>
                            <span className="spinner" style={{ marginRight: 6 }} />
                            Processando...
                          </>
                        ) : (
                          `Assinar o ${plan.name}`
                        )}
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>

          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              flexWrap: "wrap",
              gap: 12,
              paddingTop: 12,
              borderTop: "1px solid var(--grid)",
            }}
          >
            <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
              Cobrança mensal em reais, processada pelo Stripe Checkout. Cancele quando quiser em “Gerenciar assinatura”.
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              {paid && (
                <button
                  className="btn sm"
                  onClick={handlePortal}
                  disabled={actionBusy !== null}
                  title="Gerenciar cartão, faturas e cancelamento no portal do Stripe"
                >
                  {actionBusy === "portal" ? (
                    <>
                      <span className="spinner" style={{ marginRight: 6 }} />
                      Abrindo...
                    </>
                  ) : (
                    "Gerenciar assinatura"
                  )}
                </button>
              )}
              <button className="btn ghost sm" onClick={onClose}>
                Fechar
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
