export type Measurement = "nominal" | "ordinal" | "scale";

export interface Column {
  name: string;
  dtype: string;
  measurement: Measurement;
  n_distinct: number | null;
}
export interface Dataset {
  id: string;
  name: string;
  table_name: string;
  n_rows: number;
  columns: Column[];
  created_at: string;
  owner_name?: string | null;
  can_edit?: boolean; // ausente = pode (o servidor sempre manda)
}
export interface QueryResult {
  columns: { name: string; dtype: string }[];
  rows: unknown[][];
  row_count: number;
  truncated: boolean;
  elapsed_ms: number;
}
export interface AnalysisResponse {
  status: string;
  results: Record<string, unknown>;
}

export interface ChartConfig {
  type: "bar" | "line" | "scatter";
  x: string;
  ys: string[];
  /** coluna -> posição fixa (0..2) na paleta */
  slots: Record<string, number>;
}
export interface TextBlock { type: "text"; id: string; markdown: string }
export interface ChartBlock { type: "chart"; id: string; title: string; sql: string; chart: ChartConfig | null }
export interface AnalysisBlock { type: "analysis"; id: string; analysis: string; dataset_id: string; options: Record<string, unknown>; show_notes?: boolean }
export type Block = TextBlock | ChartBlock | AnalysisBlock;
export interface Report { id: string; title: string; blocks: Block[]; version: number; created_at: string; updated_at: string; owner_name?: string | null; collection_id?: string | null; can_edit?: boolean }
export interface ReportSummary { id: string; title: string; n_blocks: number; version: number; updated_at: string; owner_name?: string | null; collection_id?: string | null; can_edit?: boolean }

export interface TileLayout { x: number; y: number; w: number; h: number }
export type TextTile = TextBlock & { layout: TileLayout };
export type ChartTile = ChartBlock & { layout: TileLayout; click_param?: string | null };
export interface KpiTile { type: "kpi"; id: string; title: string; sql: string; decimals: number; prefix: string; suffix: string; layout: TileLayout }
export type AnalysisTile = AnalysisBlock & { layout: TileLayout };
export type Tile = TextTile | ChartTile | KpiTile | AnalysisTile;
export interface DashFilter { name: string; label: string; type: "text" | "number" | "date"; default: string }
export interface Dashboard { id: string; title: string; tiles: Tile[]; filters: DashFilter[]; version: number; created_at: string; updated_at: string; owner_name?: string | null; collection_id?: string | null; can_edit?: boolean }
export interface DashboardSummary { id: string; title: string; n_tiles: number; version: number; updated_at: string; owner_name?: string | null; collection_id?: string | null; can_edit?: boolean }
export interface Collection { id: string; name: string; owner_name: string | null; n_reports: number; n_dashboards: number; can_edit: boolean }

export interface AnalysisStatus {
  workers: number; busy: number; down: number; queued: number; queue_max: number;
  completed: number; rejected: number; inflight: number; timeout_s: number;
  cache: { entries: number; bytes: number; hits: number; misses: number };
}

export type Role = "viewer" | "editor" | "admin";
export interface User { id: string; username: string; display_name: string; role: Role; active: boolean }
export interface AuthStatus { auth_enabled: boolean; needs_setup: boolean; user: User | null }

/** Disparado quando a API responde 401 fora das telas de login: a sessão acabou e o AuthGate volta ao login. */
export const UNAUTHORIZED_EVENT = "ms:unauthorized";

export class ApiError extends Error {
  constructor(message: string, public status: number) {
    super(message);
  }
}

/** FastAPI devolve `detail` como string (nossos erros) ou lista (validação do pydantic). */
function detailMessage(body: unknown, fallback: string): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((d) => (d as { msg?: string }).msg ?? "invalid value").join("; ");
  return fallback;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`/api${path}`, init);
  } catch {
    throw new ApiError("Não foi possível conectar à API. Ela está no ar?", 0);
  }
  if (res.status === 204) return undefined as T;
  const body = await res.json().catch(() => null);
  if (res.status === 401 && !path.startsWith("/auth/")) dispatchEvent(new Event(UNAUTHORIZED_EVENT));
  if (!res.ok) throw new ApiError(detailMessage(body, `Erro ${res.status}`), res.status);
  return body as T;
}

const json = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { "content-type": "application/json" },
  body: JSON.stringify(body),
});

export const api = {
  authStatus: () => request<AuthStatus>("/auth/status"),
  setup: (username: string, password: string, display_name: string) => request<User>("/auth/setup", json("POST", { username, password, display_name })),
  login: (username: string, password: string) => request<User>("/auth/login", json("POST", { username, password })),
  logout: () => request<void>("/auth/logout", { method: "POST" }),
  changePassword: (current: string, next: string) => request<void>("/auth/password", json("POST", { current, new: next })),
  listUsers: () => request<User[]>("/users"),
  createUser: (u: { username: string; password: string; display_name: string; role: Role }) => request<User>("/users", json("POST", u)),
  patchUser: (id: string, patch: Partial<Pick<User, "display_name" | "role" | "active">> & { password?: string }) => request<User>(`/users/${id}`, json("PATCH", patch)),
  deleteUser: (id: string) => request<void>(`/users/${id}`, { method: "DELETE" }),
  listDatasets: () => request<Dataset[]>("/datasets"),
  uploadDataset: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<Dataset>("/datasets", { method: "POST", body: form });
  },
  deleteDataset: (id: string) => request<void>(`/datasets/${id}`, { method: "DELETE" }),
  setMeasurement: (id: string, measurement: Record<string, Measurement>) =>
    request<Dataset>(`/datasets/${id}`, json("PATCH", { measurement })),
  preview: (id: string, limit = 100) => request<QueryResult>(`/datasets/${id}/preview?limit=${limit}`),
  createDatasetFromQuery: (name: string, sql: string) => request<Dataset>("/datasets/from-query", json("POST", { name, sql })),
  runQuery: (sql: string) => request<QueryResult>("/queries/run", json("POST", { sql })),
  listReports: () => request<ReportSummary[]>("/reports"),
  createReport: (title: string, blocks: Block[]) => request<Report>("/reports", json("POST", { title, blocks })),
  getReport: (id: string) => request<Report>(`/reports/${id}`),
  saveReport: (id: string, title: string, blocks: Block[], version: number) =>
    request<Report>(`/reports/${id}`, json("PUT", { title, blocks, version })),
  moveReport: (id: string, collection_id: string | null) => request<void>(`/reports/${id}/collection`, json("PUT", { collection_id })),
  moveDashboard: (id: string, collection_id: string | null) => request<void>(`/dashboards/${id}/collection`, json("PUT", { collection_id })),
  listCollections: () => request<Collection[]>("/collections"),
  createCollection: (name: string) => request<Collection>("/collections", json("POST", { name })),
  renameCollection: (id: string, name: string) => request<Collection>(`/collections/${id}`, json("PATCH", { name })),
  deleteCollection: (id: string) => request<void>(`/collections/${id}`, { method: "DELETE" }),
  deleteReport: (id: string) => request<void>(`/reports/${id}`, { method: "DELETE" }),
  listDashboards: () => request<DashboardSummary[]>("/dashboards"),
  createDashboard: (title: string, tiles: Tile[], filters: DashFilter[] = []) => request<Dashboard>("/dashboards", json("POST", { title, tiles, filters })),
  getDashboard: (id: string) => request<Dashboard>(`/dashboards/${id}`),
  saveDashboard: (id: string, title: string, tiles: Tile[], filters: DashFilter[], version: number) =>
    request<Dashboard>(`/dashboards/${id}`, json("PUT", { title, tiles, filters, version })),
  deleteDashboard: (id: string) => request<void>(`/dashboards/${id}`, { method: "DELETE" }),
  analysisStatus: () => request<AnalysisStatus>("/analyses/status"),
  runAnalysis: (analysis: string, dataset_id: string, options: Record<string, unknown>) =>
    request<AnalysisResponse>("/analyses/run", json("POST", { analysis, dataset_id, options })),
};
