import { lazy, Suspense, useCallback, useEffect, useState } from "react";
import { api, type Dataset } from "./api";
import { DataTab } from "./components/DataTab";
import { Sidebar } from "./components/Sidebar";
import { ReportsPage } from "./components/ReportsPage";
import { clearRemoteCache } from "./lib/remote";
import { routeHref, useRoute } from "./lib/route";
import { sampleCsv } from "./lib/sample";
import { applyThemeMode, loadThemeMode, type ThemeMode } from "./lib/theme";

// ECharts e CodeMirror (~1 MB) só são baixados quando a aba é aberta.
const ReportPage = lazy(() => import("./components/ReportPage").then((m) => ({ default: m.ReportPage })));
const SqlTab = lazy(() => import("./components/SqlTab").then((m) => ({ default: m.SqlTab })));
const AnalysisTab = lazy(() => import("./components/AnalysisTab").then((m) => ({ default: m.AnalysisTab })));

type Tab = "data" | "sql" | "analysis";
const TABS: { id: Tab; label: string }[] = [
  { id: "data", label: "Dados" },
  { id: "sql", label: "Consulta SQL" },
  { id: "analysis", label: "Análise estatística" },
];
const THEME_LABEL: Record<ThemeMode, string> = { auto: "Tema: automático", light: "Tema: claro", dark: "Tema: escuro" };
const NEXT_THEME: Record<ThemeMode, ThemeMode> = { auto: "light", light: "dark", dark: "auto" };

const remember = (key: string, value: string | null) => {
  try { value === null ? localStorage.removeItem(key) : localStorage.setItem(key, value); } catch { /* sem persistência */ }
};
const recall = (key: string) => { try { return localStorage.getItem(key); } catch { return null; } };

export default function App() {
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(() => recall("dataset"));
  const [tab, setTab] = useState<Tab>("data");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [theme, setTheme] = useState<ThemeMode>(loadThemeMode);
  const route = useRoute();

  useEffect(() => applyThemeMode(theme), [theme]);

  const refresh = useCallback(async (select?: string) => {
    try {
      clearRemoteCache(); // dados mudaram (upload/exclusão): resultados em cache podem estar velhos
      const list = await api.listDatasets();
      setDatasets(list);
      setSelectedId((cur) => {
        const next = select ?? (list.some((d) => d.id === cur) ? cur : list[0]?.id ?? null);
        remember("dataset", next);
        return next;
      });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => { void refresh(); }, [refresh]);

  const upload = async (files: File[]) => {
    setBusy(true);
    setError(null);
    let last: string | undefined;
    const failures: string[] = [];
    for (const f of files) {
      try { last = (await api.uploadDataset(f)).id; } catch (e) { failures.push(`${f.name}: ${(e as Error).message}`); }
    }
    if (failures.length) setError(failures.join(" · "));
    await refresh(last);
    if (last) setTab("data");
    setBusy(false);
  };

  const loadSample = () => upload([new File([sampleCsv()], "vendas_exemplo.csv", { type: "text/csv" })]);

  const remove = async (ds: Dataset) => {
    if (!window.confirm(`Excluir "${ds.name}"? Isso não pode ser desfeito.`)) return;
    try { await api.deleteDataset(ds.id); await refresh(); } catch (e) { setError((e as Error).message); }
  };

  const updateDataset = (ds: Dataset) => {
    clearRemoteCache(); // o nível de medida muda o resultado das análises
    setDatasets((list) => list.map((d) => (d.id === ds.id ? ds : d)));
  };
  const onError = useCallback((m: string) => setError(m), []);
  const selected = datasets.find((d) => d.id === selectedId) ?? null;

  return (
    <div className={`app${route.name === "explore" ? "" : " no-sidebar"}`}>
      <header className="topbar">
        <div className="brand">
          <svg width="22" height="22" viewBox="0 0 32 32" aria-hidden>
            <rect x="5" y="15" width="5" height="12" rx="1.5" fill="var(--series-1)" />
            <rect x="13.5" y="7" width="5" height="20" rx="1.5" fill="var(--series-2)" />
            <rect x="22" y="11" width="5" height="16" rx="1.5" fill="var(--series-3)" />
          </svg>
          Metastatistic
        </div>
        <nav className="topnav" aria-label="Seções">
          <a href={routeHref({ name: "explore" })} aria-current={route.name === "explore" ? "page" : undefined}>Explorar</a>
          <a href={routeHref({ name: "reports" })} aria-current={route.name !== "explore" ? "page" : undefined}>Relatórios</a>
        </nav>
        <span className="spacer" />
        <button className="btn ghost sm" onClick={() => setTheme(NEXT_THEME[theme])} title="Alternar tema">{THEME_LABEL[theme]}</button>
      </header>

      {route.name === "explore" && <Sidebar datasets={datasets} selectedId={selectedId} busy={busy} onSelect={(id) => { setSelectedId(id); remember("dataset", id); }} onUpload={upload} onDelete={remove} />}

      <main className="main">
        <div className="main-inner">
          {error && (
            <div className="alert" role="alert" style={{ display: "flex", gap: 12 }}>
              <span style={{ flex: 1 }}>{error}</span>
              <button className="btn ghost sm" onClick={() => setError(null)} aria-label="Fechar aviso">✕</button>
            </div>
          )}

          {route.name === "report" ? (
            <Suspense fallback={<div className="empty"><span className="spinner" aria-label="Carregando" /></div>}>
              <ReportPage key={route.id} id={route.id} datasets={datasets} />
            </Suspense>
          ) : route.name === "reports" ? (
            <ReportsPage datasets={datasets} />
          ) : loading ? (
            <div className="empty"><span className="spinner" aria-label="Carregando" /></div>
          ) : !selected ? (
              <div className="card empty">
                <h2>Comece com um conjunto de dados</h2>
                <p style={{ margin: "0 auto 18px", maxWidth: 460 }}>
                  Envie um CSV pela barra lateral para explorar com SQL, montar gráficos e rodar análises estatísticas (testes t, com mais a caminho).
                </p>
                <button className="btn primary" onClick={loadSample} disabled={busy}>{busy ? <span className="spinner" /> : null} Carregar dados de exemplo</button>
              </div>
            ) : (
              <>
                <div className="page-head">
                  <h1>{selected.name}</h1>
                  <span className="muted small">{selected.n_rows.toLocaleString("pt-BR")} linhas · {selected.columns.length} colunas · tabela SQL <span className="chip">{selected.table_name}</span></span>
                </div>
                <div className="tabs" role="tablist">
                  {TABS.map((t) => (
                    <button key={t.id} className="tab" role="tab" aria-selected={tab === t.id} onClick={() => setTab(t.id)}>{t.label}</button>
                  ))}
                </div>
                {tab === "data" && <DataTab dataset={selected} onChange={updateDataset} onError={onError} />}
                <Suspense fallback={<div className="empty"><span className="spinner" aria-label="Carregando" /></div>}>
                  {tab === "sql" && <SqlTab dataset={selected} datasets={datasets} onDatasetCreated={async (ds) => { await refresh(ds.id); setTab("data"); }} />}
                  {tab === "analysis" && <AnalysisTab key={selected.id} dataset={selected} />}
                </Suspense>
              </>
          )}
        </div>
      </main>
    </div>
  );
}
