import { useMemo } from "react";
import type { QueryResult } from "../api";
import { buildChart, freeSlot, isNumericType, MAX_SERIES, type ChartSpec, type ChartType } from "../lib/chartSpec";
import { readChartTokens, useResolvedTheme } from "../lib/theme";
import { Chart } from "./Chart";

const TYPES: { value: ChartType; label: string }[] = [
  { value: "bar", label: "Barras" },
  { value: "line", label: "Linhas" },
  { value: "scatter", label: "Dispersão" },
];
const KIND: Record<ChartType, string> = { bar: "barras", line: "linhas", scatter: "dispersão" };

interface Props {
  result: QueryResult;
  spec: ChartSpec | null;
  /** Se informado, mostra os controles (tipo, eixo X, séries). Sem ele o gráfico é só leitura (relatório). */
  onSpec?: (s: ChartSpec) => void;
  height?: number;
  showTitle?: boolean;
  /** Relatórios usam vetor (PDF nítido). Com muitos pontos o SVG fica pesado e volta ao canvas. */
  vector?: boolean;
  onPointClick?: (name: string) => void;
}

export const MAX_VECTOR_POINTS = 3000;

export function ChartView({ result, spec, onSpec, height, showTitle = true, vector = false, onPointClick }: Props) {
  const theme = useResolvedTheme();
  const tokens = useMemo(() => readChartTokens(), [theme]); // eslint-disable-line react-hooks/exhaustive-deps
  const built = useMemo(() => (spec ? buildChart(result, spec, tokens) : null), [result, spec, tokens]);

  if (!spec) return <div className="alert info">Esta consulta não tem uma coluna numérica para o gráfico. Veja a tabela de dados.</div>;

  const toggleY = (col: string, on: boolean) => {
    if (!onSpec) return;
    if (!on) return onSpec({ ...spec, ys: spec.ys.filter((y) => y !== col) }); // slots dos demais ficam como estão
    const slot = freeSlot(spec.slots, spec.ys);
    if (slot !== undefined) onSpec({ ...spec, ys: [...spec.ys, col], slots: { ...spec.slots, [col]: slot } });
  };
  const numericCols = result.columns.filter((c) => isNumericType(c.dtype) && c.name !== spec.x);
  const label = `Gráfico de ${KIND[spec.type]}: ${spec.ys.join(", ")} por ${spec.x}. Os valores completos estão na tabela de dados.`;

  return (
    <>
      {onSpec && (
        <div className="chart-controls no-print">
          <div className="seg" role="group" aria-label="Tipo de gráfico">
            {TYPES.map((t) => <button key={t.value} aria-pressed={spec.type === t.value} onClick={() => onSpec({ ...spec, type: t.value })}>{t.label}</button>)}
          </div>
          <label className="field">Eixo X
            <select value={spec.x} onChange={(e) => onSpec({ ...spec, x: e.target.value, ys: spec.ys.filter((y) => y !== e.target.value) })}>
              {result.columns.map((c) => <option key={c.name} value={c.name}>{c.name}</option>)}
            </select>
          </label>
          <fieldset>
            <legend>Séries (máx. {MAX_SERIES})</legend>
            <div className="series-pick">
              {numericCols.map((c) => {
                const on = spec.ys.includes(c.name);
                return (
                  <label key={c.name} className="check">
                    <input type="checkbox" checked={on} disabled={!on && spec.ys.length >= MAX_SERIES} onChange={(e) => toggleY(c.name, e.target.checked)} />
                    {on && <span className="swatch" style={{ background: tokens.series[spec.slots[c.name]] }} aria-hidden />}
                    {c.name}
                  </label>
                );
              })}
              {numericCols.length === 0 && <span className="muted small">Nenhuma coluna numérica além do eixo X.</span>}
            </div>
          </fieldset>
        </div>
      )}
      {showTitle && spec.ys.length > 0 && <div className="chart-title">{spec.ys.join(", ")} por {spec.x}</div>}
      {built?.problem ? <div className="alert info">{built.problem}</div> : built ? <Chart option={built.option} label={label} height={height} renderer={vector && result.rows.length * spec.ys.length <= MAX_VECTOR_POINTS ? "svg" : "canvas"} onPointClick={onPointClick} /> : null}
    </>
  );
}
