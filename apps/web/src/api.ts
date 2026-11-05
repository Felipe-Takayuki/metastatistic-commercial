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
export interface AnalysisBlock { type: "analysis"; id: string; analysis: string; dataset_id: string; options: Record<string, unknown> }
export type Block = TextBlock | ChartBlock | AnalysisBlock;
export interface Report { id: string; title: string; blocks: Block[]; version: number; created_at: string; updated_at: string }
export interface ReportSummary { id: string; title: string; n_blocks: number; version: number; updated_at: string }

export interface AnalysisStatus {
  workers: number; busy: number; down: number; queued: number; queue_max: number;
  completed: number; rejected: number; inflight: number; timeout_s: number;
  cache: { entries: number; bytes: number; hits: number; misses: number };
}

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
  if (!res.ok) throw new ApiError(detailMessage(body, `Erro ${res.status}`), res.status);
  return body as T;
}

const json = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { "content-type": "application/json" },
  body: JSON.stringify(body),
});

export const api = {
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
  deleteReport: (id: string) => request<void>(`/reports/${id}`, { method: "DELETE" }),
  analysisStatus: () => request<AnalysisStatus>("/analyses/status"),
  runAnalysis: (analysis: string, dataset_id: string, options: Record<string, unknown>) =>
    request<AnalysisResponse>("/analyses/run", json("POST", { analysis, dataset_id, options })),
};
