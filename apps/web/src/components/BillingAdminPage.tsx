import { useEffect, useState } from "react";
import { api, type AdminSummary } from "../api";
import { eventLabel, formatBRL } from "../lib/billing";
import { useCan } from "./AuthGate";

const when = (iso: string) => new Date(iso).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "medium" });
const num = (n: number | null) => (n === null ? "—" : n.toLocaleString("pt-BR"));

/** Painel do SaaS (só o administrador da plataforma): usuários por plano, assinaturas ativas, MRR de teste e últimos eventos do Stripe. */
export function BillingAdminPage() {
  const isAdmin = useCan("admin");
  const [data, setData] = useState<AdminSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const load = () => api.getBillingAdminSummary().then((d) => { setData(d); setError(null); }).catch((e) => setError(e.message));
  useEffect(() => { if (isAdmin) void load(); }, [isAdmin]);

  const reconcile = async () => {
    setNote(null);
    try {
      const r = await api.reconcileBilling();
      setNote(r.mode === "mock" ? (r.detail ?? "Stripe simulado.") : `${r.checked} assinaturas conferidas, ${r.fixes.length} correção(ões)${r.fixes.length ? ": " + r.fixes.map((f) => f.action).join("; ") : "."}`);
      await load();
    } catch (e) { setError((e as Error).message); }
  };

  if (!isAdmin) return <div className="card empty"><h2>Sem permissão</h2><p>Apenas o administrador da plataforma vê o painel de assinaturas.</p></div>;

  return (
    <>
      <div className="page-head">
        <h1>Assinaturas</h1>
        {data?.mock_mode
          ? <span className="chip" title="STRIPE_MOCK_MODE=true: checkout e webhooks simulados, sem chamar o Stripe">Stripe simulado (mock)</span>
          : data?.test_mode && <span className="chip" title="Chaves de teste do Stripe: nenhum valor é cobrado de verdade">Stripe em modo de teste</span>}
        <span className="spacer" />
        <button className="btn ghost sm" onClick={() => void reconcile()} title="Compara as assinaturas do Stripe com as do sistema e corrige divergências">Reconciliar com o Stripe</button>
        <button className="btn ghost sm" onClick={() => void load()}>Atualizar</button>
      </div>
      {error && <div className="alert" role="alert">{error}</div>}
      {note && <div className="muted small" role="status" style={{ marginBottom: 8 }}>{note}</div>}
      {data && (data.failed_events > 0 || data.stuck_events > 0) && (
        <div className="alert" role="alert">
          {data.failed_events > 0 && <>{data.failed_events} webhook(s) falharam e aguardam a retentativa do Stripe. </>}
          {data.stuck_events > 0 && <>{data.stuck_events} webhook(s) estão “em processamento” há mais de 5 minutos.</>}
        </div>
      )}
      {!data && !error && <div className="empty"><span className="spinner" aria-label="Carregando" /></div>}
      {data && (
        <>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(190px, 1fr))", gap: 12, marginBottom: 16 }}>
            <Stat label="Assinaturas ativas" value={num(data.active_subscriptions)} hint={data.past_due_subscriptions ? `${data.past_due_subscriptions} com pagamento em atraso` : "nenhuma em atraso"} id="stat-active" />
            <Stat label="MRR de teste" value={formatBRL(data.mrr_cents)} hint="soma das mensalidades ativas" id="stat-mrr" />
            <Stat label="Usuários" value={num(data.users_total)} hint="em todas as organizações" id="stat-users" />
          </div>

          <h2 style={{ fontSize: 15, margin: "8px 0" }}>Usuários por plano</h2>
          <div className="card" style={{ overflowX: "auto", marginBottom: 16 }}>
            <table className="users-table" data-testid="by-plan">
              <thead><tr><th>Plano</th><th>Organizações</th><th>Usuários</th></tr></thead>
              <tbody>
                {data.by_plan.map((p) => (
                  <tr key={p.plan_id}><td><strong>{p.name}</strong></td><td>{num(p.tenants)}</td><td>{num(p.users)}</td></tr>
                ))}
              </tbody>
            </table>
          </div>

          <h2 style={{ fontSize: 15, margin: "8px 0" }}>Últimos eventos do Stripe</h2>
          <div className="card" style={{ overflowX: "auto" }}>
            <table className="users-table" data-testid="events">
              <thead><tr><th>Recebido</th><th>Evento</th><th>Organização</th><th>Situação</th><th>Detalhe</th></tr></thead>
              <tbody>
                {data.last_events.map((e) => (
                  <tr key={e.event_id}>
                    <td className="muted small" style={{ whiteSpace: "nowrap" }}>{when(e.received_at)}</td>
                    <td title={e.event_id}>{eventLabel(e.event_type)}</td>
                    <td className="muted small">{e.tenant_id ?? "—"}</td>
                    <td><span className="chip">{e.status}</span></td>
                    <td className="muted small">{e.detail ?? ""}</td>
                  </tr>
                ))}
                {data.last_events.length === 0 && <tr><td colSpan={5} className="muted">Nenhum evento recebido ainda.</td></tr>}
              </tbody>
            </table>
          </div>
        </>
      )}
    </>
  );
}

function Stat({ label, value, hint, id }: { label: string; value: string; hint: string; id: string }) {
  return (
    <div className="card" style={{ padding: 16 }} data-testid={id}>
      <div className="muted small">{label}</div>
      <div style={{ fontSize: 26, fontWeight: 700, letterSpacing: "-0.02em", margin: "4px 0" }}>{value}</div>
      <div className="muted small">{hint}</div>
    </div>
  );
}
