import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError, type Block, type Dataset, type Report } from "../api";
import { itemEditable } from "../lib/collections";
import { moveBlock, newBlock, type BlockType } from "../lib/blocks";
import { routeHref } from "../lib/route";
import { Saver, type SaveStatus } from "../lib/saver";
import { useCan } from "./AuthGate";
import { AnalysisBlockEditor, AnalysisBlockView } from "./report/AnalysisBlock";
import { BlockFrame } from "./report/BlockFrame";
import { ChartBlockEditor, ChartBlockView } from "./report/ChartBlock";
import { TextBlockEditor, TextBlockView } from "./report/TextBlock";

const LABEL: Record<BlockType, string> = { text: "Texto", chart: "Gráfico (SQL)", analysis: "Análise: teste t independente" };
const STATUS_TEXT: Record<SaveStatus, string> = { saved: "Salvo", dirty: "Alterações não salvas…", saving: "Salvando…", error: "Erro ao salvar", conflict: "Conflito" };

/** Carrega o relatório e entrega ao editor. Recarregar (após conflito) remonta o editor com o estado do servidor. */
export function ReportPage({ id, datasets }: { id: string; datasets: Dataset[] }) {
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loads, setLoads] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setReport(null);
    setError(null);
    api.getReport(id).then((r) => !cancelled && setReport(r)).catch((e) => !cancelled && setError(e.message));
    return () => { cancelled = true; };
  }, [id, loads]);

  if (error) return <div className="card empty"><h2>Não foi possível abrir o relatório</h2><p>{error}</p><a className="btn" href={routeHref({ name: "reports" })}>Voltar aos relatórios</a></div>;
  if (!report) return <div className="empty"><span className="spinner" aria-label="Carregando" /></div>;
  return <ReportEditor key={`${report.id}:${loads}`} initial={report} datasets={datasets} onReload={() => setLoads((n) => n + 1)} />;
}

interface EditorProps { initial: Report; datasets: Dataset[]; onReload: () => void }

function ReportEditor({ initial, datasets, onReload }: EditorProps) {
  const [title, setTitle] = useState(initial.title);
  const [blocks, setBlocks] = useState<Block[]>(initial.blocks);
  const canEdit = itemEditable(useCan("editor"), initial);
  const [mode, setMode] = useState<"edit" | "view">(initial.blocks.length === 0 && canEdit ? "edit" : "view");
  const [status, setStatus] = useState<{ s: SaveStatus; msg?: string }>({ s: "saved" });
  const titleRef = useRef(initial.title);
  const blocksRef = useRef(initial.blocks);
  const version = useRef(initial.version);

  const saver = useMemo(
    () => new Saver<{ title: string; blocks: Block[] }>(
      async (p) => { version.current = (await api.saveReport(initial.id, p.title, p.blocks, version.current)).version; },
      (s, msg) => setStatus({ s, msg }),
      (e) => (e instanceof ApiError && e.status === 409 ? "conflict" : "retry"),
    ),
    [initial.id],
  );

  // Estado em refs também: vários blocos podem alterar no mesmo ciclo (efeitos de preenchimento) sem um sobrescrever o outro.
  const commit = useCallback((patch: { title?: string; blocks?: Block[] }) => {
    titleRef.current = patch.title ?? titleRef.current;
    blocksRef.current = patch.blocks ?? blocksRef.current;
    setTitle(titleRef.current);
    setBlocks(blocksRef.current);
    saver.schedule({ title: titleRef.current.trim() || "Relatório sem título", blocks: blocksRef.current });
  }, [saver]);

  const updateBlock = useCallback((b: Block) => commit({ blocks: blocksRef.current.map((x) => (x.id === b.id ? b : x)) }), [commit]);

  useEffect(() => () => { void saver.flush(); }, [saver]); // ao sair da página, salva o que faltar
  useEffect(() => {
    const warn = (e: BeforeUnloadEvent) => { if (saver.hasUnsaved) { e.preventDefault(); e.returnValue = ""; } };
    addEventListener("beforeunload", warn);
    return () => removeEventListener("beforeunload", warn);
  }, [saver]);

  const remove = (b: Block) => window.confirm("Excluir este bloco? Isso não pode ser desfeito.") && commit({ blocks: blocksRef.current.filter((x) => x.id !== b.id) });
  const move = (i: number, d: -1 | 1) => commit({ blocks: moveBlock(blocksRef.current, i, d) });
  const add = (t: BlockType) => commit({ blocks: [...blocksRef.current, newBlock(t, blocksRef.current, datasets)] });

  /** PDF pelo navegador: força o tema claro (impressão com fundo escuro é ilegível), espera os gráficos redesenharem e imprime. */
  const exportPdf = () => {
    const root = document.documentElement;
    const prevTheme = root.getAttribute("data-theme");
    const prevTitle = document.title;
    root.setAttribute("data-theme", "light");
    document.title = titleRef.current || "Relatório";
    const restore = () => {
      if (prevTheme === null) root.removeAttribute("data-theme"); else root.setAttribute("data-theme", prevTheme);
      document.title = prevTitle;
      removeEventListener("afterprint", restore);
    };
    addEventListener("afterprint", restore);
    setTimeout(() => window.print(), 600);
  };

  const editing = mode === "edit";
  const conflict = status.s === "conflict";

  return (
    <div className="report-page">
      <div className="report-toolbar no-print">
        <a className="btn ghost sm" href={routeHref({ name: "reports" })}>← Relatórios</a>
        <span className="spacer" />
        <span className={`save-status ${status.s}`} role="status" aria-live="polite">
          {STATUS_TEXT[status.s]}
          {status.s === "error" && <> · <button className="link-btn" onClick={() => void saver.flush()}>tentar de novo</button></>}
        </span>
        {editing ? (
          <button className="btn primary sm" onClick={() => setMode("view")}>Concluir edição</button>
        ) : (
          <>
            {canEdit && <button className="btn sm" onClick={() => setMode("edit")}>Editar</button>}
            <button className="btn primary sm" onClick={exportPdf}>Exportar PDF</button>
          </>
        )}
      </div>

      {conflict && (
        <div className="alert no-print" role="alert" style={{ marginBottom: 14 }}>
          Este relatório foi salvo em outra aba ou janela depois que você o abriu. Para não sobrescrever aquele trabalho, suas últimas edições <strong>não foram salvas</strong>.{" "}
          <button className="link-btn" onClick={onReload}>Recarregar a versão salva</button>
        </div>
      )}
      {status.s === "error" && status.msg && <div className="alert no-print" role="alert" style={{ marginBottom: 14 }}>{status.msg}</div>}

      <article className="report-doc">
        {editing ? (
          <input className="title-input" value={title} maxLength={200} aria-label="Título do relatório" placeholder="Título do relatório"
            onChange={(e) => commit({ title: e.target.value })} onBlur={() => !title.trim() && commit({ title: "Relatório sem título" })} />
        ) : (
          <h1 className="report-h1">{title}</h1>
        )}

        {blocks.length === 0 && !editing && <p className="muted">Este relatório está vazio.{canEdit && <> Clique em <strong>Editar</strong> para adicionar blocos.</>}</p>}

        {blocks.map((b, i) =>
          editing ? (
            <BlockFrame key={b.id} label={LABEL[b.type]} index={i} count={blocks.length} onMove={(d) => move(i, d)} onDelete={() => remove(b)}>
              {b.type === "text" && <TextBlockEditor block={b} onChange={updateBlock} />}
              {b.type === "chart" && <ChartBlockEditor block={b} onChange={updateBlock} />}
              {b.type === "analysis" && <AnalysisBlockEditor block={b} datasets={datasets} onChange={updateBlock} />}
            </BlockFrame>
          ) : b.type === "text" ? <TextBlockView key={b.id} block={b} />
            : b.type === "chart" ? <ChartBlockView key={b.id} block={b} />
            : <AnalysisBlockView key={b.id} block={b} />,
        )}

        {editing && (
          <div className="add-blocks no-print" role="group" aria-label="Adicionar bloco">
            <span className="muted small">Adicionar:</span>
            <button className="btn sm" onClick={() => add("text")}>+ Texto</button>
            <button className="btn sm" onClick={() => add("chart")}>+ Gráfico</button>
            <button className="btn sm" onClick={() => add("analysis")}>+ Análise</button>
          </div>
        )}
      </article>
    </div>
  );
}
