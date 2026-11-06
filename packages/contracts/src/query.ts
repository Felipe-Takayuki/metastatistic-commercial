export type MeasurementLevel = 'nominal' | 'ordinal' | 'scale';

export interface ColumnMeta {
  name: string;
  type: string;
  measurementLevel?: MeasurementLevel;
  nullable?: boolean;
  description?: string;
}

export interface QuerySpec {
  sql?: string;
  datasetId?: string;
  filters?: unknown[];
  limit?: number;
  offset?: number;
  tenantId?: string;
}

export interface QueryResult {
  columns: ColumnMeta[];
  rows: Record<string, unknown>[];
  rowCount: number;
  executionTimeMs?: number;
}
