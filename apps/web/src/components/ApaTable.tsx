import { formatCell, type JaspField } from "../lib/format";
import { pivotColumnGroups } from "../lib/pivot";
import { RichText } from "./RichText";

export interface JaspTable {
  title?: string;
  schema: { fields: JaspField[] };
  data: Record<string, unknown>[];
  footnotes?: { symbol?: string; text?: string }[];
  error?: { errorMessage?: string };
}

/** Agrupa notas de mesmo símbolo ("Note." costuma vir em várias linhas) num parágrafo só. */
function groupNotes(notes: NonNullable<JaspTable["footnotes"]>) {
  const groups: { symbol?: string; texts: (string | undefined)[] }[] = [];
  for (const n of notes) {
    const last = groups[groups.length - 1];
    if (last && last.symbol === n.symbol) last.texts.push(n.text);
    else groups.push({ symbol: n.symbol, texts: [n.text] });
  }
  return groups;
}

/** Tabela no estilo APA: três filetes horizontais, sem linhas verticais, notas abaixo. */
export function ApaTable({ table: original }: { table: JaspTable }) {
  const pivoted = pivotColumnGroups(original);   // tabelas "de lado" (testes qui-quadrado, medidas de associação) viram uma linha por teste
  const table = pivoted ? { ...original, schema: { fields: pivoted.fields }, data: pivoted.data } : original;
  const fields = table.schema.fields;
  const leftAlign = (f: JaspField) => f.type === "string";
  return (
    <figure className="apa">
      {table.title && <figcaption className="apa-title"><RichText html={table.title} /></figcaption>}
      <div style={{ overflowX: "auto" }}>
        <table className="apa-table">
          <thead>
            <tr>
              {fields.map((f) => (
                <th key={f.name} className={leftAlign(f) ? "left" : undefined} scope="col"><RichText html={f.title === undefined ? f.name : f.title.trim()} /></th>
              ))}
            </tr>
          </thead>
          <tbody>
            {table.data.map((row, ri) => (
              <tr key={ri} className={row[".isNewGroup"] === true && ri > 0 ? "newgroup" : undefined}>
                {fields.map((f) => {
                  const prev = table.data[ri - 1];
                  const repeated = f.combine && prev && prev[f.name] === row[f.name] && row[".isNewGroup"] !== true;
                  return <td key={f.name} className={leftAlign(f) ? "left" : undefined}>{repeated ? "" : <RichText html={formatCell(row[f.name], f)} />}</td>;
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {table.footnotes && table.footnotes.length > 0 && (
        <div className="apa-notes">
          {groupNotes(table.footnotes).map((g, i) => (
            <div key={i}>
              {g.symbol && <><RichText html={g.symbol} />{" "}</>}
              {g.texts.map((t, j) => <span key={j}><RichText html={t} />{j < g.texts.length - 1 ? " " : ""}</span>)}
            </div>
          ))}
        </div>
      )}
    </figure>
  );
}
