import { useEffect, useState } from "react";
import { api, type AuditEvent } from "../api";
import { ACTION_LABEL, describeEvent, isAlert } from "../lib/audit";

const when = (iso: string) => new Date(iso).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "medium" });

/** Quem fez o quê, mais recente primeiro. Só administradores. */
export function AuditLog() {
  const [events, setEvents] = useState<AuditEvent[] | null>(null);
  const [action, setAction] = useState("");
  const [more, setMore] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = async (append: boolean) => {
    try {
      const page = await api.audit(append ? events?.[events.length - 1]?.id : undefined, action || undefined);
      setEvents(append ? [...(events ?? []), ...page] : page);
      setMore(page.length === 50);
    } catch (e) { setError((e as Error).message); }
  };
  useEffect(() => { void load(false); }, [action]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <>
      <div className="coll-bar">
        <label className="field" style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>Ação
          <select value={action} onChange={(e) => setAction(e.target.value)} aria-label="Filtrar por ação">
            <option value="">Todas</option>
            {Object.entries(ACTION_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </label>
        <button className="btn ghost sm" onClick={() => void load(false)}>Atualizar</button>
      </div>
      {error && <div className="alert" role="alert">{error}</div>}
      {events === null && !error && <div className="empty"><span className="spinner" aria-label="Carregando" /></div>}
      {events && (
        <div className="card" style={{ overflowX: "auto" }}>
          <table className="users-table audit-table">
            <thead><tr><th>Quando</th><th>Quem</th><th>O quê</th></tr></thead>
            <tbody>
              {events.map((e) => (
                <tr key={e.id} data-action={e.action} className={isAlert(e.action) ? "audit-alert" : undefined}>
                  <td className="muted small" style={{ whiteSpace: "nowrap" }}>{when(e.ts)}</td>
                  <td>{e.username ?? <span className="muted">—</span>}</td>
                  <td>{describeEvent(e)}</td>
                </tr>
              ))}
              {events.length === 0 && <tr><td colSpan={3} className="muted">Nenhum evento.</td></tr>}
            </tbody>
          </table>
        </div>
      )}
      {events && more && events.length > 0 && <div><button className="btn" onClick={() => void load(true)}>Carregar mais</button></div>}
    </>
  );
}
