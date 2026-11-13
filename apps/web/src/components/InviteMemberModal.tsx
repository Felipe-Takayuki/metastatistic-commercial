import { useEffect, useState, type FormEvent } from "react";
import { api, getActiveTenant, type ActiveTenant, type InvitationResponse, type TenantMember } from "../api";

interface InviteMemberModalProps {
  onClose: () => void;
  tenant?: ActiveTenant;
}

const ROLES: { id: string; label: string; desc: string }[] = [
  { id: "admin", label: "Administrador", desc: "Acesso total, gerencia membros e configurações." },
  { id: "statistician", label: "Estatístico", desc: "Configura e executa modelos, testes e análises estatísticas." },
  { id: "analyst", label: "Analista", desc: "Cria e edita datasets, consultas SQL e relatórios." },
  { id: "viewer", label: "Visualizador", desc: "Acesso de somente leitura aos relatórios e dashboards." },
];

const TIER_LIMITS: Record<string, { label: string; maxUsers: number; hint: string }> = {
  community: { label: "Free", maxUsers: 3, hint: "Limite de até 3 membros no plano Free." },
  team: { label: "Pro", maxUsers: 15, hint: "Limite de até 15 membros no plano Pro." },
  enterprise: { label: "Enterprise", maxUsers: 999999, hint: "Usuários ilimitados no plano Enterprise." },
};

export function InviteMemberModal({ onClose, tenant: propTenant }: InviteMemberModalProps) {
  const activeTenant = propTenant ?? getActiveTenant();
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("analyst");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [members, setMembers] = useState<TenantMember[]>([]);
  const [loadingMembers, setLoadingMembers] = useState(true);
  const [invitation, setInvitation] = useState<InvitationResponse | null>(null);
  const [copied, setCopied] = useState(false);

  const tierKey = activeTenant.tier || "community";
  const tierInfo = TIER_LIMITS[tierKey] || TIER_LIMITS.community;

  useEffect(() => {
    let unmounted = false;
    api.listTenantMembers(activeTenant.id)
      .then((m) => {
        if (!unmounted) setMembers(m);
      })
      .catch(() => {
        // ignora se ainda não tiver membros listáveis
      })
      .finally(() => {
        if (!unmounted) setLoadingMembers(false);
      });
    return () => {
      unmounted = true;
    };
  }, [activeTenant.id]);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!email.trim() || !email.includes("@")) {
      setError("Por favor, informe um endereço de e-mail válido.");
      return;
    }

    setBusy(true);
    setError(null);

    try {
      const res = await api.createTenantInvitation(activeTenant.id, email.trim(), role);
      setInvitation(res);
      setEmail("");
    } catch (err) {
      setError((err as Error).message || "Não foi possível enviar o convite.");
    } finally {
      setBusy(false);
    }
  };

  const inviteUrl = invitation
    ? `${window.location.origin}/?invitation=${encodeURIComponent(invitation.token)}`
    : "";

  const handleCopy = async () => {
    if (!inviteUrl) return;
    try {
      await navigator.clipboard.writeText(inviteUrl);
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);
    } catch {
      // fallback
    }
  };

  const isAtLimit = !loadingMembers && tierInfo.maxUsers < 999999 && members.length >= tierInfo.maxUsers;

  return (
    <div className="modal-backdrop" onKeyDown={(e) => e.key === "Escape" && onClose()}>
      <div
        className="modal card"
        style={{ maxWidth: 520 }}
        role="dialog"
        aria-modal="true"
        aria-label="Convidar Colaborador"
      >
        <div className="modal-head">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
            <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
            <circle cx="9" cy="7" r="4" />
            <line x1="19" y1="8" x2="19" y2="14" />
            <line x1="22" y1="11" x2="16" y2="11" />
          </svg>
          <strong>Convidar Membro para o Workspace</strong>
          <span className="spacer" />
          <button type="button" className="btn ghost sm" onClick={onClose} aria-label="Fechar">
            ✕
          </button>
        </div>

        <div className="modal-body" style={{ padding: "18px 20px", gap: 16 }}>
          {/* Informações da Organização */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              padding: "10px 14px",
              background: "var(--surface-2)",
              borderRadius: "8px",
              border: "1px solid var(--border)",
            }}
          >
            <div>
              <div style={{ fontSize: 11, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.04em" }}>
                Workspace Ativo
              </div>
              <strong style={{ fontSize: 14 }}>{activeTenant.name}</strong>
            </div>
            <div style={{ textAlign: "right" }}>
              <span
                className="chip"
                style={{
                  fontSize: 11,
                  textTransform: "uppercase",
                  background: tierKey === "enterprise" ? "var(--accent)" : "var(--surface-1)",
                  color: tierKey === "enterprise" ? "var(--on-accent)" : "var(--text-secondary)",
                }}
              >
                Plano {tierInfo.label}
              </span>
              <div className="muted small" style={{ marginTop: 2, fontSize: 11 }}>
                {!loadingMembers ? `${members.length} / ${tierInfo.maxUsers >= 999999 ? "∞" : tierInfo.maxUsers} membros` : "Carregando..."}
              </div>
            </div>
          </div>

          {/* Alerta de Cota */}
          <div
            className={`alert ${isAtLimit ? "" : "info"}`}
            role="alert"
            style={{ fontSize: 12.5, padding: "8px 12px" }}
          >
            {isAtLimit
              ? `Atenção: Seu workspace atingiu o limite de ${tierInfo.maxUsers} usuários do plano ${tierInfo.label}. Faça upgrade de plano para convidar mais membros.`
              : tierInfo.hint}
          </div>

          {error && (
            <div className="alert" role="alert" style={{ display: "flex", justifyContent: "space-between" }}>
              <span>{error}</span>
              <button type="button" className="btn ghost sm" onClick={() => setError(null)}>
                ✕
              </button>
            </div>
          )}

          {/* Resultado do Convite */}
          {invitation ? (
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                gap: 12,
                padding: "14px",
                background: "var(--accent-wash)",
                border: "1px solid color-mix(in srgb, var(--accent) 30%, transparent)",
                borderRadius: "8px",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ fontSize: 18 }}>🎉</span>
                <strong style={{ fontSize: 13, color: "var(--text-primary)" }}>
                  Convite criado com sucesso para {invitation.email}!
                </strong>
              </div>
              <p className="small muted" style={{ margin: 0 }}>
                Envie o link de ativação abaixo para o colaborador se juntar ao workspace como{" "}
                <strong>{ROLES.find((r) => r.id === invitation.role)?.label || invitation.role}</strong>:
              </p>

              <div style={{ display: "flex", gap: 8 }}>
                <input
                  type="text"
                  readOnly
                  value={inviteUrl}
                  style={{
                    flex: 1,
                    fontSize: 12,
                    fontFamily: "var(--mono)",
                    background: "var(--surface-1)",
                  }}
                  onFocus={(e) => e.target.select()}
                />
                <button
                  type="button"
                  className={`btn ${copied ? "primary" : "sm"}`}
                  onClick={handleCopy}
                  style={{ minWidth: 90 }}
                >
                  {copied ? "✓ Copiado!" : "Copiar"}
                </button>
              </div>

              <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 4 }}>
                <button
                  type="button"
                  className="btn ghost sm"
                  onClick={() => setInvitation(null)}
                >
                  + Convidar outro membro
                </button>
                <button
                  type="button"
                  className="btn primary sm"
                  onClick={onClose}
                >
                  Concluir
                </button>
              </div>
            </div>
          ) : (
            <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              <label className="field">
                <span>E-mail do Colega / Colaborador</span>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="colega@empresa.com"
                  required
                  autoFocus
                  disabled={busy || isAtLimit}
                />
              </label>

              <div className="field">
                <span style={{ fontSize: 13, color: "var(--text-secondary)", marginBottom: 4 }}>
                  Papel no Workspace
                </span>
                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  {ROLES.map((r) => {
                    const selected = role === r.id;
                    return (
                      <label
                        key={r.id}
                        style={{
                          display: "flex",
                          alignItems: "flex-start",
                          gap: 10,
                          padding: "8px 12px",
                          borderRadius: "6px",
                          border: selected ? "1.5px solid var(--accent)" : "1px solid var(--border)",
                          background: selected ? "var(--accent-wash)" : "var(--surface-1)",
                          cursor: isAtLimit ? "not-allowed" : "pointer",
                        }}
                      >
                        <input
                          type="radio"
                          name="member_role"
                          value={r.id}
                          checked={selected}
                          onChange={() => setRole(r.id)}
                          disabled={busy || isAtLimit}
                          style={{ marginTop: 2, accentColor: "var(--accent)" }}
                        />
                        <div>
                          <strong style={{ fontSize: 13 }}>{r.label}</strong>
                          <span className="muted small" style={{ display: "block", fontSize: 11.5 }}>
                            {r.desc}
                          </span>
                        </div>
                      </label>
                    );
                  })}
                </div>
              </div>

              <div
                style={{
                  display: "flex",
                  justifyContent: "flex-end",
                  gap: 8,
                  marginTop: 6,
                }}
              >
                <button type="button" className="btn ghost" onClick={onClose} disabled={busy}>
                  Cancelar
                </button>
                <button
                  type="submit"
                  className="btn primary"
                  disabled={busy || isAtLimit || !email.trim()}
                >
                  {busy ? (
                    <>
                      <span className="spinner" style={{ width: 14, height: 14 }} />
                      Enviando...
                    </>
                  ) : (
                    "Gerar Convite"
                  )}
                </button>
              </div>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
