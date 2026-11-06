import { useEffect, useState } from "react";
import { api, type Dataset, type ReportSummary } from "../api";
import { exampleBlocks } from "../lib/blocks";
import { filterByCollection, itemEditable } from "../lib/collections";
import { navigate, routeHref } from "../lib/route";
import { useCan } from "./AuthGate";
import { CollectionsPanel, MoveSelect, useCollections } from "./CollectionsPanel";

const when = (iso: string) => new Date(iso).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });

export function ReportsPage({ datasets }: { datasets: Dataset[] }) {
  const [list, setList] = useState<ReportSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const canEdit = useCan("editor");
  const { collections, filter, setFilter, reload } = useCollections();

  const load = () => api.listReports().then(setList).catch((e) => setError(e.message));
  useEffect(() => { void load(); }, []);

  const create = async (example: boolean) => {
    setBusy(true);
    setError(null);
    try {
      const ds = datasets[0];
      const rep = example && ds
        ? await api.createReport(`Análise de ${ds.name.replace(/\.csv$/i, "")}`, exampleBlocks(ds))
        : await api.createReport("Relatório sem título", []);
      navigate({ name: "report", id: rep.id });
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  };

  const remove = async (r: ReportSummary) => {
    if (!window.confirm(`Excluir o relatório "${r.title}"? Isso não pode ser desfeito.`)) return;
    try { await api.deleteReport(r.id); await load(); } catch (e) { setError((e as Error).message); }
  };

  const move = async (r: ReportSummary, to: string | null) => {
    try { await api.moveReport(r.id, to); await Promise.all([load(), reload()]); } catch (e) { setError((e as Error).message); }
  };
  const visible = list ? filterByCollection(list, filter) : null;
  const counts = {
    all: list?.length ?? 0, none: list ? filterByCollection(list, "none").length : 0,
    byId: Object.fromEntries(collections.map((c) => [c.id, list ? filterByCollection(list, c.id).length : 0])),
  };

  return (
    <>
      <div className="page-head">
        <h1>Relatórios</h1>
        <span className="spacer" />
        {canEdit && datasets.length > 0 && <button className="btn" onClick={() => create(true)} disabled={busy}>Criar exemplo com {datasets[0].name}</button>}
        {canEdit && <button className="btn primary" onClick={() => create(false)} disabled={busy}>Novo relatório</button>}
      </div>
      {error && <div className="alert" role="alert">{error}</div>}
      {list && (list.length > 0 || collections.length > 0) && <CollectionsPanel collections={collections} filter={filter} counts={counts} onFilter={setFilter} onChanged={async () => { await Promise.all([load(), reload()]); }} onError={setError} />}
      {list === null && !error && <div className="empty"><span className="spinner" aria-label="Carregando" /></div>}
      {list && list.length === 0 && (
        <div className="card empty">
          <h2>Nenhum relatório ainda</h2>
          <p style={{ margin: "0 auto", maxWidth: 480 }}>
            Um relatório combina texto, gráficos e análises estatísticas num documento que você pode exportar em PDF.
            {datasets.length === 0 ? " Envie um CSV na aba Explorar para começar." : " Comece por um exemplo gerado a partir dos seus dados."}
          </p>
        </div>
      )}
      {list && list.length > 0 && visible?.length === 0 && <p className="muted">Nenhum relatório nesta coleção.</p>}
      {visible && visible.length > 0 && (
        <ul className="report-list">
          {visible.map((r) => (
            <li key={r.id} className="card report-row">
              <a className="report-link" href={routeHref({ name: "report", id: r.id })}>
                <span className="report-title">{r.title}</span>
                <span className="muted small">{r.n_blocks} {r.n_blocks === 1 ? "bloco" : "blocos"} · atualizado em {when(r.updated_at)}{r.owner_name ? ` · por ${r.owner_name}` : ""}</span>
              </a>
              {itemEditable(canEdit, r) && <MoveSelect title={r.title} value={r.collection_id} collections={collections} onMove={(to) => void move(r, to)} />}
              {itemEditable(canEdit, r) && <button className="btn ghost sm" onClick={() => remove(r)} aria-label={`Excluir ${r.title}`}>Excluir</button>}
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
