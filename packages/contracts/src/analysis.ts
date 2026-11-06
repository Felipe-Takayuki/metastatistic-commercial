export type AnalysisEngine = 'r' | 'py';

export interface TableAPA {
  title: string;
  headers: string[];
  rows: (string | number | null)[][];
  footnotes?: string[];
  note?: string;
}

export interface AnalysisSpec {
  id?: string;
  type: string;
  engine: AnalysisEngine;
  datasetId: string;
  variables: Record<string, unknown>;
  options?: Record<string, unknown>;
  tenantId?: string;
}

export interface AnalysisResult {
  id: string;
  spec: AnalysisSpec;
  status: 'pending' | 'running' | 'completed' | 'failed';
  tables?: TableAPA[];
  figures?: Array<{
    id: string;
    title: string;
    url?: string;
    data?: unknown;
  }>;
  rawOutput?: string;
  error?: string;
  createdAt: string;
  completedAt?: string;
}
