import { BarChart, LineChart, ScatterChart } from "echarts/charts";
import { GridComponent, LegendComponent, TooltipComponent } from "echarts/components";
import * as echarts from "echarts/core";
import { CanvasRenderer, SVGRenderer } from "echarts/renderers";
import { useEffect, useRef } from "react";

echarts.use([BarChart, LineChart, ScatterChart, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer, SVGRenderer]);

interface Props {
  option: Record<string, unknown>;
  height?: number;
  /** Descrição para leitores de tela; os valores completos estão sempre na aba Tabela. */
  label: string;
  loading?: boolean;
  /** "svg" = vetorial (nítido no PDF/impressão); "canvas" = melhor com muitos pontos. */
  renderer?: "canvas" | "svg";
  /** Clique numa barra/ponto: recebe o nome da categoria (eixo X). Usado pelo cross-filter dos dashboards. */
  onPointClick?: (name: string) => void;
}

export function Chart({ option, height = 360, label, loading, renderer = "canvas", onPointClick }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const chart = useRef<echarts.ECharts | null>(null);
  const optionRef = useRef(option);
  const clickRef = useRef(onPointClick);
  clickRef.current = onPointClick;

  useEffect(() => {
    const el = host.current!;
    const c = echarts.init(el, undefined, { renderer });
    chart.current = c;
    const ro = new ResizeObserver(() => c.resize());
    ro.observe(el);
    c.setOption(optionRef.current, true);
    c.on("click", (e: { name?: unknown }) => { if (e.name !== undefined && e.name !== "") clickRef.current?.(String(e.name)); });
    return () => { ro.disconnect(); c.dispose(); chart.current = null; };
  }, [renderer]);

  useEffect(() => {
    optionRef.current = option;
    chart.current?.setOption(option, true); // true = substitui (troca de tipo/séries sem sobras)
  }, [option]);

  return <div ref={host} className={`chart-box${loading ? " loading" : ""}${onPointClick ? " clickable" : ""}`} style={{ height }} role="img" aria-label={label} />;
}
