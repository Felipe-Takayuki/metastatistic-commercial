import { useEffect, useState } from "react";
import { api, type Dataset, type Measurement, type QueryResult } from "../api";
import { DataTable } from "./DataTable";

const LEVELS: { value: Measurement; label: string }[] = [
  { value: "nominal", label: "Nominal" },
  { value: "ordinal", label: "Ordinal" },
  { value: "scale", label: "Escalar" },
];

interface Props {
  dataset: Dataset;
  onChange: (ds: Dataset) => void;
  onError: (msg: string) => void;
}

export function DataTab({ dataset, onChange, onError }: Props) {
  const [preview, setPreview] = useState<QueryResult | null>(null);

  useEffect(() => {
    let cancelled = false;
    setPreview(null);
    api.preview(dataset.id, 100).then((r) => !cancelled && setPreview(r)).catch((e) => !cancelled && onError(e.message));
    return () => { cancelled = true; };
  }, [dataset.id, onError]);

  const setLevel = async (col: string, level: Measurement) => {
    try {
      onChange(await api.setMeasurement(dataset.id, { [col]: level }));
    } catch (e) {
      onError((e as Error).message);
    }
  };

  return (
    <>
      <section>
        <h2 style={{ fontSize: 15, marginBottom: 4 }}>Colunas</h2>
        <p className="muted small" style={{ margin: "0 0 10px" }}>
          O nível de medida define como a análise trata cada coluna: <strong>nominal/ordinal</strong> viram categorias (fator), <strong>escalar</strong> vira número.
        </p>
        <div className="schema">
          {dataset.columns.map((c) => (
            <div key={c.name} className="col-card">
              <span className="name" title={c.name}>{c.name}</span>
              <span className="small muted"><span className="chip">{c.dtype}</span>{c.n_distinct !== null && <> · {c.n_distinct} valores distintos</>}</span>
              <select value={c.measurement} onChange={(e) => setLevel(c.name, e.target.value as Measurement)} aria-label={`Nível de medida de ${c.name}`}>
                {LEVELS.map((l) => <option key={l.value} value={l.value}>{l.label}</option>)}
              </select>
            </div>
          ))}
        </div>
      </section>
      <section>
        <h2 style={{ fontSize: 15, marginBottom: 10 }}>Prévia <span className="muted" style={{ fontWeight: 400 }}>(primeiras 100 linhas)</span></h2>
        {preview ? <DataTable columns={preview.columns} rows={preview.rows} /> : <div className="spinner" aria-label="Carregando" />}
      </section>
    </>
  );
}
