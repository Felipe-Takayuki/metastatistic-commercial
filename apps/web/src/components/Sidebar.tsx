import { useRef, useState } from "react";
import type { Dataset } from "../api";

interface Props {
  datasets: Dataset[];
  selectedId: string | null;
  busy: boolean;
  onSelect: (id: string) => void;
  onUpload: (files: File[]) => void;
  onDelete: (ds: Dataset) => void;
  canEdit: boolean;
}

export function Sidebar({ datasets, selectedId, busy, onSelect, onUpload, onDelete, canEdit }: Props) {
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const pick = (list: FileList | null) => {
    if (list && list.length) onUpload(Array.from(list));
    if (input.current) input.current.value = "";
  };
  return (
    <aside className="sidebar" aria-label="Datasets">
      <div className="section-label">Datasets</div>
      {canEdit && <div
        className={`dropzone${over ? " over" : ""}`}
        role="button"
        tabIndex={0}
        onClick={() => input.current?.click()}
        onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), input.current?.click())}
        onDragOver={(e) => { e.preventDefault(); setOver(true); }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => { e.preventDefault(); setOver(false); pick(e.dataTransfer.files); }}
      >
        {busy ? <span className="spinner" aria-label="Enviando" /> : <><strong>Enviar CSV</strong><span className="small">clique ou arraste o arquivo</span></>}
        <input ref={input} type="file" accept=".csv,text/csv" multiple hidden onChange={(e) => pick(e.target.files)} />
      </div>}
      {datasets.length === 0 ? (
        <p className="muted small" style={{ margin: 0 }}>Nenhum dataset ainda.</p>
      ) : (
        <ul className="ds-list">
          {datasets.map((d) => (
            <li key={d.id} className="ds-item" data-active={d.id === selectedId}>
              <button className="ds-pick" onClick={() => onSelect(d.id)} aria-current={d.id === selectedId}>
                <span className="ds-name" title={d.name}>{d.name}</span>
                <span className="ds-meta">{d.n_rows.toLocaleString("pt-BR")} linhas · {d.columns.length} colunas</span>
              </button>
              {canEdit && d.can_edit !== false && <button className="btn ghost sm ds-del" onClick={() => onDelete(d)} aria-label={`Excluir ${d.name}`} title="Excluir">✕</button>}
            </li>
          ))}
        </ul>
      )}
    </aside>
  );
}
