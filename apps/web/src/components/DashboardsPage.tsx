import { useEffect, useState } from "react";
import { api, type DashboardSummary } from "../api";
import { filterByCollection, itemEditable } from "../lib/collections";
import { navigate, routeHref } from "../lib/route";
import { useCan } from "./AuthGate";
import { CollectionsPanel, MoveSelect, useCollections } from "./CollectionsPanel";

const when = (iso: string) => new Date(iso).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });

export function DashboardsPage() {
  const [list, setList] = useState<DashboardSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const canEdit = useCan("editor");
  const { collections, filter, setFilter, reload } = useCollections();

  const load = () => api.listDashboards().then(setList).catch((e) => setError(e.message));
  useEffect(() => { void load(); }, []);

  const create = async () => {
    setBusy(true);
    setError(null);
    try {
      const d = await api.createDashboard("Dashboard sem título", []);
      navigate({ name: "dashboard", id: d.id });
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  };
  const remove = async (d: DashboardSummary) => {
    if (!window.confirm(`Excluir o dashboard "${d.title}"? Isso não pode ser desfeito.`)) return;
    try { await api.deleteDashboard(d.id); await load(); } catch (e) { setError((e as Error).message); }
  };

  const move = async (d: DashboardSummary, to: string | null) => {
    try { await api.moveDashboard(d.id, to); await Promise.all([load(), reload()]); } catch (e) { setError((e as Error).message); }
  };
  const visible = list ? filterByCollection(list, filter) : null;
  const counts = {
    all: list?.length ?? 0, none: list ? filterByCollection(list, "none").length : 0,
    byId: Object.fromEntries(collections.map((c) => [c.id, list ? filterByCollection(list, c.id).length : 0])),
  };

  return (
    <>
      <div className="page-head">
        <h1>Dashboards</h1>
        <span className="spacer" />
        {canEdit && <button className="btn primary" onClick={create} disabled={busy}>Novo dashboard</button>}
      </div>
      {error && <div className="alert" role="alert">{error}</div>}
      {list && (list.length > 0 || collections.length > 0) && <CollectionsPanel collections={collections} filter={filter} counts={counts} onFilter={setFilter} onChanged={async () => { await Promise.all([load(), reload()]); }} onError={setError} />}
      {list === null && !error && <div className="empty"><span className="spinner" aria-label="Carregando" /></div>}
      {list && list.length === 0 && (
        <div className="card empty">
          <h2>Nenhum dashboard ainda</h2>
          <p style={{ margin: "0 auto", maxWidth: 480 }}>Um dashboard reúne KPIs, gráficos e textos numa grade que você arrasta e redimensiona. Cada tile usa uma consulta SQL sobre os seus datasets.</p>
        </div>
      )}
      {list && list.length > 0 && visible?.length === 0 && <p className="muted">Nenhum dashboard nesta coleção.</p>}
      {visible && visible.length > 0 && (
        <ul className="report-list">
          {visible.map((d) => (
            <li key={d.id} className="card report-row">
              <a className="report-link" href={routeHref({ name: "dashboard", id: d.id })}>
                <span className="report-title">{d.title}</span>
                <span className="muted small">{d.n_tiles} {d.n_tiles === 1 ? "tile" : "tiles"} · atualizado em {when(d.updated_at)}{d.owner_name ? ` · por ${d.owner_name}` : ""}</span>
              </a>
              {itemEditable(canEdit, d) && <MoveSelect title={d.title} value={d.collection_id} collections={collections} onMove={(to) => void move(d, to)} />}
              {itemEditable(canEdit, d) && <button className="btn ghost sm" onClick={() => remove(d)} aria-label={`Excluir ${d.title}`}>Excluir</button>}
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
