import { useSyncExternalStore } from "react";
import type { ChartTokens } from "./chartSpec";

/** Lê os tokens CSS atuais (claro/escuro) para o ECharts, que precisa de cores concretas. */
export function readChartTokens(): ChartTokens {
  const cs = getComputedStyle(document.documentElement);
  const v = (name: string) => cs.getPropertyValue(name).trim();
  return {
    surface: v("--surface-1"), text: v("--text-primary"), textSecondary: v("--text-secondary"),
    grid: v("--grid"), axis: v("--axis"), series: [v("--series-1"), v("--series-2"), v("--series-3")],
  };
}

export type ThemeMode = "auto" | "light" | "dark";

export function loadThemeMode(): ThemeMode {
  try {
    const m = localStorage.getItem("theme");
    return m === "light" || m === "dark" ? m : "auto";
  } catch {
    return "auto";
  }
}

export function applyThemeMode(mode: ThemeMode): void {
  if (mode === "auto") document.documentElement.removeAttribute("data-theme");
  else document.documentElement.setAttribute("data-theme", mode);
  try {
    localStorage.setItem("theme", mode);
  } catch { /* modo privado: funciona sem persistir */ }
}

/** "light" | "dark" efetivo (tema forçado ou preferência do SO); re-renderiza quando muda. */
export function useResolvedTheme(): "light" | "dark" {
  const query = "(prefers-color-scheme: dark)";
  const subscribe = (cb: () => void) => {
    const mo = new MutationObserver(cb);
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    const mq = matchMedia(query);
    mq.addEventListener("change", cb);
    return () => { mo.disconnect(); mq.removeEventListener("change", cb); };
  };
  const snapshot = () => {
    const forced = document.documentElement.getAttribute("data-theme");
    return forced === "dark" || (forced !== "light" && matchMedia(query).matches) ? "dark" : "light";
  };
  return useSyncExternalStore(subscribe, snapshot);
}
