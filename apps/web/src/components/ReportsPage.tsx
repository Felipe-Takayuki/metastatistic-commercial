import { useEffect, useState } from "react";
import { api, type Dataset, type ReportSummary } from "../api";
import { exampleBlocks } from "../lib/blocks";
import { navigate, routeHref } from "../lib/route";
import { useCan } from "./AuthGate";

const when = (iso: string) => new Date(iso).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });

export function ReportsPage({ datasets }: { datasets: Dataset[] }) {
  const [list, setList] = useState<ReportSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const canEdit = useCan("editor");

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

  return (
    <>
      <div className="page-head">
        <h1>Relatórios</h1>
        <span className="spacer" />
        {canEdit && datasets.length > 0 && <button className="btn" onClick={() => create(true)} disabled={busy}>Criar exemplo com {datasets[0].name}</button>}
        {canEdit && <button className="btn primary" onClick={() => create(false)} disabled={busy}>Novo relatório</button>}
      </div>
      {error && <div className="alert" role="alert">{error}</div>}
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
      {list && list.length > 0 && (
        <ul className="report-list">
          {list.map((r) => (
            <li key={r.id} className="card report-row">
              <a className="report-link" href={routeHref({ name: "report", id: r.id })}>
                <span className="report-title">{r.title}</span>
                <span className="muted small">{r.n_blocks} {r.n_blocks === 1 ? "bloco" : "blocos"} · atualizado em {when(r.updated_at)}</span>
              </a>
              {canEdit && <button className="btn ghost sm" onClick={() => remove(r)} aria-label={`Excluir ${r.title}`}>Excluir</button>}
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
