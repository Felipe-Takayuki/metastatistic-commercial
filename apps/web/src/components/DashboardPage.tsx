import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import ReactGridLayout, { useContainerWidth, verticalCompactor } from "react-grid-layout";
import "react-grid-layout/css/styles.css";
import { api, ApiError, type Dashboard, type DashFilter, type Dataset, type Tile } from "../api";
import { applyLayout, GRID_COLS, GRID_GAP, newTile, readingOrder, ROW_HEIGHT, STACK_BELOW, toGrid, type TileType } from "../lib/dashboard";
import { filterProblems, reconcileValues, substitute } from "../lib/params";
import { routeHref } from "../lib/route";
import { Saver, type SaveStatus } from "../lib/saver";
import { useCan } from "./AuthGate";
import { FilterBar, FiltersEditor } from "./dashboard/Filters";
import { ParamsContext, type ParamsCtx } from "./dashboard/params";
import { TILE_LABEL, TileBody, TileEditor, tileHeading } from "./dashboard/TileViews";

const STATUS_TEXT: Record<SaveStatus, string> = { saved: "Salvo", dirty: "Alterações não salvas…", saving: "Salvando…", error: "Erro ao salvar", conflict: "Conflito" };

/** Carrega o dashboard e entrega ao editor. Recarregar (após conflito) remonta o editor com o estado do servidor. */
export function DashboardPage({ id, datasets }: { id: string; datasets: Dataset[] }) {
  const [dash, setDash] = useState<Dashboard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loads, setLoads] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setDash(null);
    setError(null);
    api.getDashboard(id).then((d) => !cancelled && setDash(d)).catch((e) => !cancelled && setError(e.message));
    return () => { cancelled = true; };
  }, [id, loads]);

  if (error) return <div className="card empty"><h2>Não foi possível abrir o dashboard</h2><p>{error}</p><a className="btn" href={routeHref({ name: "dashboards" })}>Voltar aos dashboards</a></div>;
  if (!dash) return <div className="empty"><span className="spinner" aria-label="Carregando" /></div>;
  return <DashboardEditor key={`${dash.id}:${loads}`} initial={dash} datasets={datasets} onReload={() => setLoads((n) => n + 1)} />;
}

function DashboardEditor({ initial, datasets, onReload }: { initial: Dashboard; datasets: Dataset[]; onReload: () => void }) {
  const [title, setTitle] = useState(initial.title);
  const [tiles, setTiles] = useState<Tile[]>(initial.tiles);
  const [filters, setFilters] = useState<DashFilter[]>(initial.filters);
  const [values, setValues] = useState<Record<string, string>>(() => reconcileValues(initial.filters, {}));
  const filtersRef = useRef(initial.filters);
  const canEdit = useCan("editor");
  const [mode, setMode] = useState<"edit" | "view">(initial.tiles.length === 0 && canEdit ? "edit" : "view");
  const [editingId, setEditingId] = useState<string | null>(null);
  // SQL do tile em edição NO MOMENTO em que o editor abriu. O tile de fundo usa este valor até o editor fechar: sem isso
  // cada tecla digitada reexecutaria a consulta (com SQL pela metade, falhando e sobrecarregando o banco).
  const frozenSql = useRef<{ id: string; sql: string } | null>(null);
  const openEditor = (t: Tile) => { frozenSql.current = t.type === "chart" || t.type === "kpi" ? { id: t.id, sql: t.sql } : null; setEditingId(t.id); };
  const closeEditor = () => { frozenSql.current = null; setEditingId(null); };
  const [status, setStatus] = useState<{ s: SaveStatus; msg?: string }>({ s: "saved" });
  const titleRef = useRef(initial.title);
  const tilesRef = useRef(initial.tiles);
  const version = useRef(initial.version);
  const { width, containerRef, mounted } = useContainerWidth();

  const saver = useMemo(
    () => new Saver<{ title: string; tiles: Tile[]; filters: DashFilter[] }>(
      async (p) => { version.current = (await api.saveDashboard(initial.id, p.title, p.tiles, p.filters, version.current)).version; },
      (s, msg) => setStatus({ s, msg }),
      (e) => (e instanceof ApiError && e.status === 409 ? "conflict" : "retry"),
    ),
    [initial.id],
  );

  const commit = useCallback((patch: { title?: string; tiles?: Tile[]; filters?: DashFilter[] }) => {
    if (patch.tiles === tilesRef.current && patch.title === undefined && patch.filters === undefined) return; // nada mudou: não marca como alterado
    titleRef.current = patch.title ?? titleRef.current;
    tilesRef.current = patch.tiles ?? tilesRef.current;
    filtersRef.current = patch.filters ?? filtersRef.current;
    setTitle(titleRef.current);
    setTiles(tilesRef.current);
    setFilters(filtersRef.current);
    if (patch.filters) setValues((v) => reconcileValues(patch.filters!, v));
    // Lista de filtros inválida (nome vazio/repetido) ficaria 422 no servidor: não agenda salvamento até corrigir.
    if (filterProblems(filtersRef.current).length === 0) saver.schedule({ title: titleRef.current.trim() || "Dashboard sem título", tiles: tilesRef.current, filters: filtersRef.current });
  }, [saver]);

  const params = useMemo<ParamsCtx>(() => ({
    filters, values,
    resolve: (sql) => substitute(sql, filters, values),
    setValue: (name, value) => setValues((v) => (name in v ? { ...v, [name]: value } : v)),
  }), [filters, values]);

  useEffect(() => () => { void saver.flush(); }, [saver]);
  useEffect(() => {
    const warn = (e: BeforeUnloadEvent) => { if (saver.hasUnsaved) { e.preventDefault(); e.returnValue = ""; } };
    addEventListener("beforeunload", warn);
    return () => removeEventListener("beforeunload", warn);
  }, [saver]);

  const editing = mode === "edit";
  const stacked = width < STACK_BELOW;
  const editingTile = tiles.find((t) => t.id === editingId) ?? null;

  const onLayoutChange = useCallback((layout: readonly { i: string; x: number; y: number; w: number; h: number }[]) => {
    if (mode !== "edit") return; // no modo leitura a grade pode se normalizar sozinha; isso não é edição do usuário
    commit({ tiles: applyLayout(tilesRef.current, layout) });
  }, [mode, commit]);

  const add = (type: TileType) => {
    const t = newTile(type, tilesRef.current, datasets);
    commit({ tiles: [...tilesRef.current, t] });
    openEditor(t);
  };
  const remove = (t: Tile) => {
    if (!window.confirm("Excluir este tile? Isso não pode ser desfeito.")) return;
    if (editingId === t.id) closeEditor();
    commit({ tiles: tilesRef.current.filter((x) => x.id !== t.id) });
  };
  const changeFilters = (next: DashFilter[]) => {
    // filtro removido: os gráficos que o definiam ao clicar deixam de apontar para ele
    const names = new Set(next.map((f) => f.name));
    const cleaned = tilesRef.current.map((t) => (t.type === "chart" && t.click_param && !names.has(t.click_param) ? { ...t, click_param: null } : t));
    commit({ filters: next, tiles: cleaned.some((t, i) => t !== tilesRef.current[i]) ? cleaned : tilesRef.current });
  };
  const update = (t: Tile) => commit({ tiles: tilesRef.current.map((x) => (x.id === t.id ? t : x)) });

  useEffect(() => {
    if (!editingTile) return;
    const esc = (e: KeyboardEvent) => e.key === "Escape" && closeEditor();
    addEventListener("keydown", esc);
    return () => removeEventListener("keydown", esc);
  }, [editingTile]);

  const frame = (t: Tile) => (
    <>
      <header className={`tile-head${editing ? " editing" : ""}`}>
        <span className="tile-title">{tileHeading(t) || (editing ? <span className="muted">{TILE_LABEL[t.type]} sem título</span> : null)}</span>
        {editing && (
          <>
            <button className="btn ghost sm no-drag" onClick={() => openEditor(t)} aria-label={`Editar tile ${TILE_LABEL[t.type]}`} title="Editar conteúdo">✎</button>
            <button className="btn ghost sm no-drag" onClick={() => remove(t)} aria-label={`Excluir tile ${TILE_LABEL[t.type]}`} title="Excluir tile">✕</button>
          </>
        )}
      </header>
      <div className="tile-body"><TileBody tile={frozenSql.current?.id === t.id && (t.type === "chart" || t.type === "kpi") ? { ...t, sql: frozenSql.current.sql } : t} /></div>
    </>
  );

  return (
    <ParamsContext.Provider value={params}>
    <div className="dash-page">
      <div className="report-toolbar no-print">
        <a className="btn ghost sm" href={routeHref({ name: "dashboards" })}>← Dashboards</a>
        <span className="spacer" />
        <span className={`save-status ${status.s}`} role="status" aria-live="polite">
          {STATUS_TEXT[status.s]}
          {status.s === "error" && <> · <button className="link-btn" onClick={() => void saver.flush()}>tentar de novo</button></>}
        </span>
        {editing ? <button className="btn primary sm" onClick={() => { closeEditor(); setMode("view"); }}>Concluir edição</button> : canEdit && <button className="btn sm" onClick={() => setMode("edit")}>Editar</button>}
      </div>

      {status.s === "conflict" && (
        <div className="alert no-print" role="alert" style={{ marginBottom: 14 }}>
          Este dashboard foi salvo em outra aba ou janela depois que você o abriu. Para não sobrescrever aquele trabalho, suas últimas edições <strong>não foram salvas</strong>.{" "}
          <button className="link-btn" onClick={onReload}>Recarregar a versão salva</button>
        </div>
      )}
      {status.s === "error" && status.msg && <div className="alert no-print" role="alert" style={{ marginBottom: 14 }}>{status.msg}</div>}

      {editing ? (
        <input className="title-input" value={title} maxLength={200} aria-label="Título do dashboard" placeholder="Título do dashboard"
          onChange={(e) => commit({ title: e.target.value })} onBlur={() => !title.trim() && commit({ title: "Dashboard sem título" })} />
      ) : (
        <h1 className="report-h1">{title}</h1>
      )}

      {editing && (
        <div className="add-blocks no-print" role="group" aria-label="Adicionar tile">
          <span className="muted small">Adicionar:</span>
          <button className="btn sm" onClick={() => add("kpi")}>+ KPI</button>
          <button className="btn sm" onClick={() => add("chart")}>+ Gráfico</button>
          <button className="btn sm" onClick={() => add("text")}>+ Texto</button>
          <button className="btn sm" onClick={() => add("analysis")}>+ Análise</button>
          {stacked && <span className="muted small">Tela estreita: os tiles aparecem empilhados; para mudar posições, use uma tela mais larga.</span>}
        </div>
      )}

      {editing && <FiltersEditor filters={filters} onChange={changeFilters} />}
      <FilterBar filters={filters} values={values} onChange={params.setValue} />

      {tiles.length === 0 && !editing && <p className="muted">Este dashboard está vazio. {canEdit && <> Clique em <strong>Editar</strong> para adicionar tiles.</>}</p>}

      <div ref={containerRef} className="dash-grid">
        {mounted && stacked && (
          <div className="dash-stack">
            {readingOrder(tiles).map((t) => (
              <section key={t.id} className="tile" style={{ height: t.layout.h * ROW_HEIGHT + (t.layout.h - 1) * GRID_GAP }} aria-label={`Tile ${TILE_LABEL[t.type]}`}>{frame(t)}</section>
            ))}
          </div>
        )}
        {mounted && !stacked && tiles.length > 0 && (
          <ReactGridLayout
            width={width}
            layout={toGrid(tiles)}
            gridConfig={{ cols: GRID_COLS, rowHeight: ROW_HEIGHT, margin: [GRID_GAP, GRID_GAP], containerPadding: [0, 0], maxRows: Infinity }}
            dragConfig={{ enabled: editing, bounded: false, handle: ".tile-head", cancel: ".no-drag", threshold: 3 }}
            resizeConfig={{ enabled: editing, handles: ["se"] }}
            compactor={verticalCompactor}
            onLayoutChange={onLayoutChange}
          >
            {tiles.map((t) => <section key={t.id} className="tile" aria-label={`Tile ${TILE_LABEL[t.type]}`}>{frame(t)}</section>)}
          </ReactGridLayout>
        )}
      </div>

      {editingTile && (
        <div className="modal-backdrop no-print" onMouseDown={(e) => e.target === e.currentTarget && closeEditor()}>
          <div className={`modal card${editingTile.type === "analysis" ? " wide" : ""}`} role="dialog" aria-modal="true" aria-label={`Editar tile ${TILE_LABEL[editingTile.type]}`}>
            <header className="modal-head">
              <strong>Editar tile: {TILE_LABEL[editingTile.type]}</strong>
              <span className="spacer" />
              <button className="btn primary sm" onClick={closeEditor}>Concluir</button>
            </header>
            <div className="modal-body"><TileEditor tile={editingTile} onChange={update} datasets={datasets} /></div>
          </div>
        </div>
      )}
    </div>
    </ParamsContext.Provider>
  );
}
