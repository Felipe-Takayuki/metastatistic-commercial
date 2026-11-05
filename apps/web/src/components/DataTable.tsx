import { isNumericType } from "../lib/chartSpec";
import { formatRaw } from "../lib/format";

interface Props {
  columns: { name: string; dtype: string }[];
  rows: unknown[][];
  maxRows?: number;
}

/** Tabela de dados brutos. Conteúdo sempre como texto (React escapa): nomes e valores vêm do CSV. */
export function DataTable({ columns, rows, maxRows = 500 }: Props) {
  const shown = rows.slice(0, maxRows);
  const numeric = columns.map((c) => isNumericType(c.dtype));
  return (
    <>
      <div className="table-wrap">
        <table className="data">
          <thead>
            <tr>
              <th className="num row-idx">#</th>
              {columns.map((c, i) => (
                <th key={c.name} className={numeric[i] ? "num" : undefined}>
                  {c.name}
                  <span className="dtype">{c.dtype}</span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {shown.map((r, ri) => (
              <tr key={ri}>
                <td className="row-idx">{ri + 1}</td>
                {r.map((v, ci) => (
                  <td key={ci} className={`${numeric[ci] ? "num" : ""}${v === null ? " null" : ""}`} title={typeof v === "string" ? v : undefined}>
                    {formatRaw(v)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {rows.length > shown.length && (
        <p className="muted small" style={{ margin: "6px 0 0" }}>
          Mostrando {shown.length.toLocaleString("pt-BR")} de {rows.length.toLocaleString("pt-BR")} linhas.
        </p>
      )}
    </>
  );
}
