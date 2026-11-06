import { useSyncExternalStore } from "react";

export type Route = { name: "explore" } | { name: "reports" } | { name: "report"; id: string } | { name: "dashboards" } | { name: "dashboard"; id: string } | { name: "users" };

export function parseRoute(hash: string): Route {
  const parts = hash.replace(/^#\/?/, "").split("/").filter(Boolean);
  if (parts[0] === "reports") return parts[1] && /^[0-9a-f]{32}$/.test(parts[1]) ? { name: "report", id: parts[1] } : { name: "reports" };
  if (parts[0] === "dashboards") return parts[1] && /^[0-9a-f]{32}$/.test(parts[1]) ? { name: "dashboard", id: parts[1] } : { name: "dashboards" };
  if (parts[0] === "users") return { name: "users" };
  return { name: "explore" };
}

export const routeHref = (r: Route): string =>
  r.name === "explore" ? "#/" : r.name === "reports" ? "#/reports" : r.name === "report" ? `#/reports/${r.id}` : r.name === "dashboards" ? "#/dashboards" : r.name === "users" ? "#/users" : `#/dashboards/${r.id}`;

export function navigate(r: Route): void {
  location.hash = routeHref(r);
}

const subscribe = (cb: () => void) => {
  addEventListener("hashchange", cb);
  return () => removeEventListener("hashchange", cb);
};

/** Rota atual lida do hash (permite link direto, botão voltar e recarregar a página). */
export function useRoute(): Route {
  const hash = useSyncExternalStore(subscribe, () => location.hash);
  return parseRoute(hash);
}
