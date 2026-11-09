import { useEffect, useState } from "react";
import { api, type BillingCycle, type PlanInfo, type SubscriptionInfo } from "../api";

interface PricingModalProps {
  onClose: () => void;
}

const DEFAULT_PLANS: PlanInfo[] = [
  {
    id: "community",
    name: "Community",
    description: "Ideal para pesquisadores individuais e pequenas equipes acadêmicas.",
    tier: "community",
    price_monthly: 0,
    price_yearly: 0,
    currency: "usd",
    features: [
      "Até 3 usuários",
      "Até 10 datasets",
      "500 MB de armazenamento",
      "Análise estatística completa R Worker (Engine A)",
      "Visualização e Dashboards básicos",
      "Exportação em HTML e Markdown",
    ],
    quotas: {
      max_users: 3,
      max_datasets: 10,
      max_storage_mb: 500,
    },
  },
  {
    id: "team",
    name: "Team",
    description: "Para laboratórios de pesquisa, clínicas e equipes em crescimento.",
    tier: "team",
    price_monthly: 4900,
    price_yearly: 49000,
    currency: "usd",
    features: [
      "Até 15 usuários",
      "Até 100 datasets",
      "10 GB de armazenamento",
      "Conectores SQL nativos (PostgreSQL, MySQL, Snowflake)",
      "Compartilhamento seguro entre equipes e coleções",
      "Exportação multi-formato (HTML, PDF, DOCX)",
      "Suporte prioritário por email",
    ],
    quotas: {
      max_users: 15,
      max_datasets: 100,
      max_storage_mb: 10240,
    },
  },
  {
    id: "enterprise",
    name: "Enterprise",
    description: "Para hospitais, CROs farmacêuticas e corporações com conformidade rigorosa.",
    tier: "enterprise",
    price_monthly: 29900,
    price_yearly: 299000,
    currency: "usd",
    features: [
      "Usuários e Datasets ilimitados",
      "Armazenamento ilimitado",
      "Single Sign-On corporativo (SSO SAML / OIDC)",
      "Provisionamento automático SCIM 2.0 (Okta, Entra ID)",
      "Trilha de Auditoria Imutável (FDA 21 CFR Part 11)",
      "Engine B proprietário de alta performance (100k+ linhas)",
      "SLA garantido de 99.9% e suporte 24/7",
    ],
    quotas: {
      max_users: -1,
      max_datasets: -1,
      max_storage_mb: -1,
    },
  },
];

export function PricingModal({ onClose }: PricingModalProps) {
  const [cycle, setCycle] = useState<BillingCycle>("monthly");
  const [plans, setPlans] = useState<PlanInfo[]>(DEFAULT_PLANS);
  const [subscription, setSubscription] = useState<SubscriptionInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionBusy, setActionBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    async function loadData() {
      try {
        const [fetchedPlans, fetchedSub] = await Promise.allSettled([
          api.getBillingPlans(),
          api.getSubscription(),
        ]);

        if (mounted) {
          if (fetchedPlans.status === "fulfilled" && fetchedPlans.value.length > 0) {
            setPlans(fetchedPlans.value);
          }
          if (fetchedSub.status === "fulfilled" && fetchedSub.value) {
            setSubscription(fetchedSub.value);
          }
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
      setError((err as Error).message || "Erro ao iniciar processo de upgrade.");
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
      setError((err as Error).message || "Erro ao abrir portal de assinatura.");
      setActionBusy(null);
    }
  };

  const currentTier = subscription?.tier || "community";

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
        aria-label="Planos e Faturamento MetaStatistic"
        style={{ maxWidth: 980 }}
      >
        <div className="modal-head">
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect x="2" y="5" width="20" height="14" rx="2" />
              <line x1="2" y1="10" x2="22" y2="10" />
            </svg>
            <strong>Planos & Assinatura MetaStatistic</strong>
          </div>
          <span className="spacer" />
          {loading && (
            <span className="spinner" aria-label="Carregando dados..." style={{ width: 14, height: 14 }} />
          )}
          {!loading && subscription && (
            <span
              className="chip"
              style={{
                textTransform: "uppercase",
                letterSpacing: "0.05em",
                fontWeight: 600,
                fontSize: 11,
                background: currentTier === "community" ? "var(--surface-2)" : "var(--accent-wash)",
                color: currentTier === "community" ? "var(--text-secondary)" : "var(--accent)",
              }}
            >
              Plano Atual: {currentTier}
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

          {/* Toggle de Ciclo de Faturamento */}
          <div style={{ display: "flex", justifyContent: "center", alignItems: "center", gap: 12 }}>
            <span style={{ fontSize: 13, fontWeight: 500, color: cycle === "monthly" ? "var(--text-primary)" : "var(--text-muted)" }}>
              Mensal
            </span>
            <div
              style={{
                display: "inline-flex",
                background: "var(--surface-2)",
                padding: "3px",
                borderRadius: "20px",
                border: "1px solid var(--border)",
              }}
            >
              <button
                type="button"
                className={`btn sm ${cycle === "monthly" ? "primary" : "ghost"}`}
                style={{ borderRadius: "16px", padding: "4px 14px", height: "auto" }}
                onClick={() => setCycle("monthly")}
              >
                Mensal
              </button>
              <button
                type="button"
                className={`btn sm ${cycle === "yearly" ? "primary" : "ghost"}`}
                style={{ borderRadius: "16px", padding: "4px 14px", height: "auto" }}
                onClick={() => setCycle("yearly")}
              >
                Anual <span style={{ fontSize: 11, opacity: 0.9 }}>(-17%)</span>
              </button>
            </div>
            <span style={{ fontSize: 13, fontWeight: 500, color: cycle === "yearly" ? "var(--text-primary)" : "var(--text-muted)" }}>
              Anual <span className="chip" style={{ fontSize: 10, background: "var(--accent-wash)", color: "var(--accent)" }}>2 meses grátis</span>
            </span>
          </div>

          {/* Grid de Planos */}
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
              const isTeam = plan.id === "team";
              const price = cycle === "monthly" ? plan.price_monthly : plan.price_yearly;
              const formattedPrice = price === 0 ? "$0" : `$${(price / 100).toFixed(0)}`;
              const periodLabel = price === 0 ? "gratuito" : cycle === "monthly" ? "/mês" : "/ano";

              return (
                <div
                  key={plan.id}
                  className="card"
                  style={{
                    position: "relative",
                    display: "flex",
                    flexDirection: "column",
                    padding: 20,
                    borderRadius: 10,
                    border: isTeam
                      ? "2px solid var(--accent)"
                      : isCurrent
                      ? "2px solid var(--series-3)"
                      : "1px solid var(--border)",
                    background: isTeam ? "var(--surface-1)" : "var(--surface-1)",
                    boxShadow: isTeam ? "0 4px 20px rgba(0,0,0,0.08)" : "none",
                  }}
                >
                  {isTeam && (
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
                      Mais Popular
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
                      {formattedPrice}
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
                      <button
                        className="btn ghost sm"
                        style={{ width: "100%", cursor: "default", opacity: 0.8 }}
                        disabled
                      >
                        ✓ Plano Atual
                      </button>
                    ) : plan.id === "community" ? (
                      <button
                        className="btn ghost sm"
                        style={{ width: "100%", cursor: "default", opacity: 0.6 }}
                        disabled
                      >
                        Incluído
                      </button>
                    ) : (
                      <button
                        className={`btn sm ${isTeam ? "primary" : ""}`}
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
                          `Fazer Upgrade para ${plan.name}`
                        )}
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>

          {/* Rodapé com Gerenciador de Assinatura */}
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
              Pagamentos processados com segurança via Stripe Checkout com criptografia TLS de 256 bits.
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              {currentTier !== "community" && (
                <button
                  className="btn sm"
                  onClick={handlePortal}
                  disabled={actionBusy !== null}
                  title="Gerenciar cartão de crédito, faturas e cancelamento via Stripe"
                >
                  {actionBusy === "portal" ? (
                    <>
                      <span className="spinner" style={{ marginRight: 6 }} />
                      Abrindo...
                    </>
                  ) : (
                    "Gerenciar Assinatura"
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
