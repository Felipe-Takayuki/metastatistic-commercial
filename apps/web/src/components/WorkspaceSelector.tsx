import { useEffect, useRef, useState } from "react";
import {
  getActiveTenant,
  getRecentTenants,
  setActiveTenant,
  TENANT_CHANGED_EVENT,
  type ActiveTenant,
  type PlanTier,
} from "../api";
import { CreateOrganizationModal } from "./CreateOrganizationModal";
import { InviteMemberModal } from "./InviteMemberModal";

const TIER_COLORS: Record<PlanTier, { bg: string; color: string; border: string }> = {
  community: { bg: "var(--surface-2)", color: "var(--text-secondary)", border: "var(--border)" },
  team: { bg: "var(--accent-wash)", color: "var(--accent)", border: "color-mix(in srgb, var(--accent) 30%, transparent)" },
  enterprise: { bg: "var(--accent)", color: "var(--on-accent)", border: "var(--accent)" },
};

export function WorkspaceSelector() {
  const [active, setActive] = useState<ActiveTenant>(getActiveTenant);
  const [recentList, setRecentList] = useState<ActiveTenant[]>(getRecentTenants);
  const [isOpen, setIsOpen] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [inviteOpen, setInviteOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  // Sincroniza quando o tenant ativo mudar em qualquer lugar
  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent<ActiveTenant>).detail;
      if (detail) {
        setActive(detail);
      } else {
        setActive(getActiveTenant());
      }
      setRecentList(getRecentTenants());
    };
    window.addEventListener(TENANT_CHANGED_EVENT, handler);
    return () => window.removeEventListener(TENANT_CHANGED_EVENT, handler);
  }, []);

  // Fechar dropdown ao clicar fora ou pressionar Escape
  useEffect(() => {
    if (!isOpen) return;
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setIsOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen]);

  const handleSwitchTenant = (tenant: ActiveTenant) => {
    setActiveTenant(tenant);
    setIsOpen(false);
  };

  const tier = active.tier || "community";
  const tierStyle = TIER_COLORS[tier] || TIER_COLORS.community;

  // Garante que o workspace padrão ("Metastatistic") também esteja acessível na lista
  const defaultTenant: ActiveTenant = {
    id: "default",
    name: "Metastatistic (Padrão)",
    slug: "default",
    tier: "community",
  };

  const allAvailable = [
    defaultTenant,
    ...recentList.filter((r) => r.id !== "default"),
  ];

  return (
    <div className="workspace-selector-container" ref={containerRef} style={{ position: "relative" }}>
      {/* Botão Trigger na Topbar */}
      <button
        type="button"
        className="btn sm"
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          background: "var(--surface-2)",
          borderColor: isOpen ? "var(--accent)" : "var(--border)",
          padding: "4px 10px",
          height: 32,
        }}
        onClick={() => setIsOpen((prev) => !prev)}
        aria-haspopup="true"
        aria-expanded={isOpen}
        title="Alternar organização / workspace"
      >
        {/* Ícone de Workspace */}
        <svg
          width="15"
          height="15"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden
          style={{ opacity: 0.85 }}
        >
          <path d="M3 21h18" />
          <path d="M9 8h1" />
          <path d="M9 12h1" />
          <path d="M9 16h1" />
          <path d="M14 8h1" />
          <path d="M14 12h1" />
          <path d="M14 16h1" />
          <path d="M5 21V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v16" />
        </svg>

        {/* Nome do Workspace */}
        <span
          style={{
            maxWidth: 140,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
            fontWeight: 600,
            fontSize: 13,
          }}
        >
          {active.name}
        </span>

        {/* Badge do Tier */}
        <span
          className="chip"
          style={{
            fontSize: 10,
            textTransform: "uppercase",
            fontWeight: 600,
            letterSpacing: "0.04em",
            padding: "1px 6px",
            background: tierStyle.bg,
            color: tierStyle.color,
            border: `1px solid ${tierStyle.border}`,
          }}
        >
          {tier}
        </span>

        {/* Chevron */}
        <svg
          width="12"
          height="12"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden
          style={{
            transform: isOpen ? "rotate(180deg)" : "none",
            transition: "transform .15s ease",
            opacity: 0.6,
          }}
        >
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>

      {/* Menu Dropdown */}
      {isOpen && (
        <div
          className="card"
          style={{
            position: "absolute",
            top: "calc(100% + 6px)",
            left: 0,
            minWidth: 260,
            zIndex: 100,
            boxShadow: "0 10px 30px rgba(0, 0, 0, 0.28)",
            padding: "8px 0",
            display: "flex",
            flexDirection: "column",
          }}
          role="menu"
        >
          {/* Header com Dados da Organização Atual */}
          <div style={{ padding: "8px 14px", borderBottom: "1px solid var(--border)" }}>
            <div style={{ fontSize: 11, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.04em" }}>
              Organização Ativa
            </div>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: 2 }}>
              <strong style={{ fontSize: 14 }}>{active.name}</strong>
              <span
                className="chip"
                style={{
                  fontSize: 10,
                  textTransform: "uppercase",
                  background: tierStyle.bg,
                  color: tierStyle.color,
                  border: `1px solid ${tierStyle.border}`,
                }}
              >
                {tier}
              </span>
            </div>
            {active.slug && (
              <div className="muted small" style={{ fontSize: 11, marginTop: 2 }}>
                slug: <span className="mono">{active.slug}</span>
              </div>
            )}
          </div>

          {/* Ações Rápidas */}
          <div style={{ padding: "6px 8px", display: "flex", flexDirection: "column", gap: 2 }}>
            <button
              type="button"
              className="btn ghost sm"
              style={{
                justifyContent: "flex-start",
                width: "100%",
                padding: "6px 8px",
                fontSize: 13,
              }}
              onClick={() => {
                setIsOpen(false);
                setInviteOpen(true);
              }}
            >
              👥 Convidar Membros
            </button>
            <button
              type="button"
              className="btn ghost sm"
              style={{
                justifyContent: "flex-start",
                width: "100%",
                padding: "6px 8px",
                fontSize: 13,
              }}
              onClick={() => {
                setIsOpen(false);
                setCreateOpen(true);
              }}
            >
              🏢 Nova Organização
            </button>
          </div>

          {/* Lista de Alternar Workspace */}
          {allAvailable.length > 0 && (
            <>
              <div
                style={{
                  padding: "6px 14px 4px",
                  fontSize: 11,
                  color: "var(--text-muted)",
                  textTransform: "uppercase",
                  letterSpacing: "0.04em",
                  borderTop: "1px solid var(--border)",
                  marginTop: 2,
                }}
              >
                Alternar Workspace
              </div>
              <div style={{ maxHeight: 180, overflowY: "auto", padding: "0 8px" }}>
                {allAvailable.map((t) => {
                  const isCurrent = t.id === active.id;
                  const itemTier = t.tier || "community";
                  const itemTierStyle = TIER_COLORS[itemTier] || TIER_COLORS.community;
                  return (
                    <button
                      key={t.id}
                      type="button"
                      className="btn ghost sm"
                      style={{
                        width: "100%",
                        justifyContent: "space-between",
                        padding: "6px 8px",
                        marginBottom: 2,
                        background: isCurrent ? "var(--surface-2)" : "transparent",
                        fontWeight: isCurrent ? 600 : 400,
                      }}
                      onClick={() => handleSwitchTenant(t)}
                    >
                      <span
                        style={{
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                          maxWidth: 160,
                          textAlign: "left",
                        }}
                      >
                        {isCurrent ? "✓ " : ""}{t.name}
                      </span>
                      <span
                        className="chip"
                        style={{
                          fontSize: 9.5,
                          textTransform: "uppercase",
                          padding: "1px 5px",
                          background: itemTierStyle.bg,
                          color: itemTierStyle.color,
                        }}
                      >
                        {itemTier}
                      </span>
                    </button>
                  );
                })}
              </div>
            </>
          )}
        </div>
      )}

      {/* Modais */}
      {createOpen && (
        <CreateOrganizationModal
          onClose={() => setCreateOpen(false)}
          onCreated={(newTenant) => {
            setActive({
              id: newTenant.id,
              name: newTenant.name,
              slug: newTenant.slug,
              tier: newTenant.tier,
            });
          }}
        />
      )}

      {inviteOpen && (
        <InviteMemberModal
          onClose={() => setInviteOpen(false)}
          tenant={active}
        />
      )}
    </div>
  );
}
