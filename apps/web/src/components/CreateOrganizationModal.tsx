import { useState, type FormEvent } from "react";
import { api, setActiveTenant, type PlanTier, type TenantInfo } from "../api";
import { useSession } from "./AuthGate";

interface CreateOrganizationModalProps {
  onClose: () => void;
  onCreated?: (tenant: TenantInfo) => void;
}

function generateSlug(text: string): string {
  return text
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 40);
}

const TIERS: { id: PlanTier; name: string; badge: string; desc: string }[] = [
  {
    id: "community",
    name: "Community",
    badge: "Gratuito",
    desc: "Até 3 usuários, 10 datasets e análises estatísticas completas.",
  },
  {
    id: "team",
    name: "Team",
    badge: "Colaborativo",
    desc: "Até 15 usuários, 100 datasets, conectores SQL e suporte prioritário.",
  },
  {
    id: "enterprise",
    name: "Enterprise",
    badge: "Corporativo",
    desc: "Usuários e dados ilimitados, SSO SAML, SCIM 2.0 e FDA Audit Trail.",
  },
];

export function CreateOrganizationModal({ onClose, onCreated }: CreateOrganizationModalProps) {
  const { user } = useSession();
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [slugManual, setSlugManual] = useState(false);
  const [tier, setTier] = useState<PlanTier>("community");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleNameChange = (val: string) => {
    setName(val);
    if (!slugManual) {
      setSlug(generateSlug(val));
    }
  };

  const handleSlugChange = (val: string) => {
    setSlugManual(true);
    setSlug(val.toLowerCase().replace(/[^a-z0-9-]/g, ""));
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    const finalName = name.trim();
    const finalSlug = slug.trim() || generateSlug(finalName);

    if (finalName.length < 2) {
      setError("O nome da empresa deve ter pelo menos 2 caracteres.");
      return;
    }
    if (finalSlug.length < 2) {
      setError("O identificador (slug) deve ter pelo menos 2 caracteres.");
      return;
    }

    setBusy(true);
    setError(null);

    try {
      const created = await api.createTenant({
        name: finalName,
        slug: finalSlug,
        tier,
        owner_id: user?.id || "admin",
        owner_email: user?.username ? `${user.username}@metastatistic.local` : undefined,
      });

      // Salva como tenant ativo
      setActiveTenant({
        id: created.id,
        name: created.name,
        slug: created.slug,
        tier: created.tier,
      });

      if (onCreated) {
        onCreated(created);
      }
      onClose();
    } catch (err) {
      setError((err as Error).message || "Falha ao criar organização.");
      setBusy(false);
    }
  };

  return (
    <div className="modal-backdrop" onKeyDown={(e) => e.key === "Escape" && onClose()}>
      <div
        className="modal card"
        style={{ maxWidth: 540 }}
        role="dialog"
        aria-modal="true"
        aria-label="Criar Nova Empresa / Workspace"
      >
        <div className="modal-head">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
            <path d="M3 21h18" />
            <path d="M9 8h1" />
            <path d="M9 12h1" />
            <path d="M9 16h1" />
            <path d="M14 8h1" />
            <path d="M14 12h1" />
            <path d="M14 16h1" />
            <path d="M5 21V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v16" />
          </svg>
          <strong>Criar Nova Empresa / Workspace</strong>
          <span className="spacer" />
          <button type="button" className="btn ghost sm" onClick={onClose} aria-label="Fechar">
            ✕
          </button>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="modal-body" style={{ padding: "18px 20px", gap: 16 }}>
            {error && (
              <div className="alert" role="alert" style={{ display: "flex", justifyContent: "space-between" }}>
                <span>{error}</span>
                <button type="button" className="btn ghost sm" onClick={() => setError(null)}>
                  ✕
                </button>
              </div>
            )}

            <label className="field">
              <span>
                Nome da Empresa / Organização <span style={{ color: "var(--danger)" }}>*</span>
              </span>
              <input
                type="text"
                value={name}
                onChange={(e) => handleNameChange(e.target.value)}
                placeholder="Ex: Laboratório Bioclin"
                required
                autoFocus
                disabled={busy}
              />
            </label>

            <label className="field">
              <span style={{ display: "flex", justifyContent: "space-between" }}>
                <span>Slug / Subdomínio <span style={{ color: "var(--danger)" }}>*</span></span>
                {slugManual && (
                  <button
                    type="button"
                    className="btn ghost sm"
                    style={{ padding: "0 4px", height: "auto", fontSize: 11 }}
                    onClick={() => {
                      setSlugManual(false);
                      setSlug(generateSlug(name));
                    }}
                  >
                    Auto-sincronizar
                  </button>
                )}
              </span>
              <input
                type="text"
                value={slug}
                onChange={(e) => handleSlugChange(e.target.value)}
                placeholder="laboratorio-bioclin"
                required
                disabled={busy}
              />
              <div className="muted small" style={{ marginTop: 2, display: "flex", alignItems: "center", gap: 4 }}>
                <span>Preview de acesso:</span>
                <span className="chip" style={{ fontSize: 11, background: "var(--surface-2)" }}>
                  {slug ? `${slug}.seudominio.com` : "slug.seudominio.com"}
                </span>
              </div>
            </label>

            <div className="field">
              <span style={{ fontSize: 13, color: "var(--text-secondary)", marginBottom: 4 }}>
                Plano / Tier Inicial
              </span>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {TIERS.map((t) => {
                  const selected = tier === t.id;
                  return (
                    <label
                      key={t.id}
                      style={{
                        display: "flex",
                        alignItems: "flex-start",
                        gap: 12,
                        padding: "10px 14px",
                        borderRadius: "8px",
                        border: selected ? "1.5px solid var(--accent)" : "1px solid var(--border)",
                        background: selected ? "var(--accent-wash)" : "var(--surface-1)",
                        cursor: "pointer",
                        transition: "all .12s",
                      }}
                    >
                      <input
                        type="radio"
                        name="tenant_tier"
                        value={t.id}
                        checked={selected}
                        onChange={() => setTier(t.id)}
                        disabled={busy}
                        style={{ marginTop: 3, accentColor: "var(--accent)" }}
                      />
                      <div style={{ flex: 1 }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 2 }}>
                          <strong style={{ fontSize: 14 }}>{t.name}</strong>
                          <span
                            className="chip"
                            style={{
                              fontSize: 10,
                              textTransform: "uppercase",
                              letterSpacing: "0.04em",
                              background: selected ? "var(--accent)" : "var(--surface-2)",
                              color: selected ? "var(--on-accent)" : "var(--text-muted)",
                            }}
                          >
                            {t.badge}
                          </span>
                        </div>
                        <span className="muted small" style={{ display: "block" }}>
                          {t.desc}
                        </span>
                      </div>
                    </label>
                  );
                })}
              </div>
            </div>
          </div>

          <div
            style={{
              padding: "12px 20px",
              borderTop: "1px solid var(--border)",
              background: "var(--surface-2)",
              display: "flex",
              justifyContent: "flex-end",
              gap: 8,
              borderRadius: "0 0 10px 10px",
            }}
          >
            <button type="button" className="btn ghost" onClick={onClose} disabled={busy}>
              Cancelar
            </button>
            <button type="submit" className="btn primary" disabled={busy || !name.trim()}>
              {busy ? (
                <>
                  <span className="spinner" style={{ width: 14, height: 14 }} />
                  Criando...
                </>
              ) : (
                "Criar Organização"
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
