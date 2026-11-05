import { ApaTable, type JaspTable } from "./ApaTable";
import { RichText } from "./RichText";

type Obj = Record<string, unknown>;
interface Meta { name: string; type?: string; title?: string; meta?: Meta[] }

const isObj = (v: unknown): v is Obj => typeof v === "object" && v !== null && !Array.isArray(v);
const isTable = (n: Obj): n is Obj & JaspTable => isObj(n.schema) && Array.isArray(n.data);
const isImage = (n: Obj): n is Obj & { data: string } => typeof n.data === "string" && n.data.startsWith("data:image/");

/** A ordem de exibição vem de `.meta` (as chaves do objeto chegam em ordem alfabética). */
function order(meta: Meta[] | undefined, children: Obj): Meta[] {
  if (meta && meta.length) return meta.filter((m) => m.name in children);
  return Object.keys(children).filter((k) => !k.startsWith(".")).map((name) => ({ name }));
}

function Element({ node, meta }: { node: unknown; meta?: Meta }) {
  if (!isObj(node)) return null;
  const err = isObj(node.error) ? node.error.errorMessage : undefined;
  if (typeof err === "string") return <div className="alert" role="alert">{(node.title as string) ? `${node.title}: ` : ""}{err}</div>;

  if (isTable(node)) return node.data.length === 0 ? null : <ApaTable table={node} />; // tabela vazia = opção desligada
  if (isImage(node))
    return (
      <figure className="apa">
        {typeof node.title === "string" && <figcaption className="apa-title">{node.title}</figcaption>}
        <img className="plot-img" src={node.data} alt={typeof node.title === "string" ? `Gráfico: ${node.title}` : "Gráfico estatístico"} width={Number(node.width) || undefined} height={Number(node.height) || undefined} />
      </figure>
    );
  if (isObj(node.collection)) {
    const kids = order(meta?.meta, node.collection);
    const rendered = kids.map((m) => <Element key={m.name} node={(node.collection as Obj)[m.name]} meta={m} />);
    return (
      <section className="result-section">
        {typeof node.title === "string" && node.title && <h3>{node.title}</h3>}
        {rendered}
      </section>
    );
  }
  if (typeof node.text === "string") return <p><RichText html={node.text} /></p>;
  return null;
}

/** Renderiza a árvore de resultados do jaspResults (tabelas, contêineres, gráficos, texto). */
export function ResultView({ results }: { results: Obj }) {
  const metas = Array.isArray(results[".meta"]) ? (results[".meta"] as Meta[]) : undefined;
  return <>{order(metas, results).map((m) => <Element key={m.name} node={results[m.name]} meta={m} />)}</>;
}
