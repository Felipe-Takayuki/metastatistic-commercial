import { createContext, useContext } from "react";
import { api, type DashFilter, type QueryResult } from "../../api";
import { isError, type Resolved } from "../../lib/params";
import { useRemote } from "../../lib/remote";

export interface ParamsCtx {
  filters: DashFilter[];
  values: Record<string, string>;
  /** troca `{{filtros}}` pelos valores atuais */
  resolve: (sql: string) => Resolved;
  setValue: (name: string, value: string) => void;
}

export const ParamsContext = createContext<ParamsCtx>({ filters: [], values: {}, resolve: (sql) => ({ sql }), setValue: () => {} });
export const useParams = () => useContext(ParamsContext);

/** Consulta de um tile: aplica os filtros do dashboard ao SQL; erro de filtro vira erro do tile (sem consultar). */
export function useTileQuery(sql: string) {
  const { resolve } = useParams();
  const r = resolve(sql);
  const final = isError(r) ? "" : r.sql;
  const q = useRemote<QueryResult>(final.trim() ? `q:${final}` : null, () => api.runQuery(final));
  return isError(r) ? { data: undefined, error: r.error, loading: false } : q;
}
