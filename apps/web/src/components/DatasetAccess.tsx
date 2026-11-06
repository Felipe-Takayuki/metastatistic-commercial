import { useEffect, useState } from "react";
import { api, type AccessConfig, type Dataset, type DirectoryUser } from "../api";
import { useSession } from "./AuthGate";

/** Quem lê o dataset (lista de acesso) e quais linhas cada pessoa vê (regra por atributo). Só dono/administrador. */
export function DatasetAccess({ dataset, onClose, onSaved }: { dataset: Dataset; onClose: () => void; onSaved: () => void }) {
  const { user: me } = useSession();
  const [cfg, setCfg] = useState<AccessConfig | null>(null);
  const [people, setPeople] = useState<DirectoryUser[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    Promise.all([api.getAccess(dataset.id), api.directory()]).then(([c, d]) => { setCfg(c); setPeople(d); }).catch((e) => setError((e as Error).message));
  }, [dataset.id]);

  const save = async () => {
    if (!cfg) return;
    setBusy(true);
    setError(null);
    try { await api.putAccess(dataset.id, cfg); onSaved(); onClose(); } catch (e) { setError((e as Error).message); setBusy(false); }
  };
  const toggle = (id: string) => cfg && setCfg({ ...cfg, user_ids: cfg.user_ids.includes(id) ? cfg.user_ids.filter((x) => x !== id) : [...cfg.user_ids, id] });

  return (
    <div className="modal-backdrop" onKeyDown={(e) => e.key === "Escape" && onClose()}>
      <div className="modal card" style={{ maxWidth: 560 }} role="dialog" aria-modal="true" aria-label={`Acesso a ${dataset.name}`}>
        <div className="modal-head"><strong>Acesso: {dataset.name}</strong><span className="spacer" /><button className="btn ghost sm" onClick={onClose} aria-label="Fechar">✕</button></div>
        <div className="modal-body">
          {error && <div className="alert" role="alert">{error}</div>}
          {!cfg && !error && <span className="spinner" aria-label="Carregando" />}
          {cfg && (
            <>
              <label className="check">
                <input type="checkbox" checked={cfg.restricted} onChange={(e) => setCfg({ ...cfg, restricted: e.target.checked })} />
                <span><strong>Restringir a leitura</strong><br /><span className="muted small">Só o dono, os administradores e as pessoas marcadas veem este dataset (lista, SQL, análises). Sem isto, todos que entram leem.</span></span>
              </label>
              {cfg.restricted && (
                <fieldset className="access-people" aria-label="Quem pode ler">
                  {people.filter((p) => p.id !== me.id).map((p) => (
                    <label key={p.id} className="check"><input type="checkbox" checked={cfg.user_ids.includes(p.id)} onChange={() => toggle(p.id)} /> {p.display_name} <span className="muted small">({p.username})</span></label>
                  ))}
                  {people.length <= 1 && <span className="muted small">Não há outros usuários ativos.</span>}
                </fieldset>
              )}
              <hr />
              <label className="check">
                <input type="checkbox" checked={cfg.rls !== null} onChange={(e) => setCfg({ ...cfg, rls: e.target.checked ? { column: dataset.columns[0]?.name ?? "", attribute: "" } : null })} />
                <span><strong>Filtrar linhas por atributo do usuário</strong><br /><span className="muted small">Cada pessoa vê só as linhas em que a coluna escolhida tem um dos valores do atributo dela (definido por um administrador em Usuários). Quem não tem o atributo não vê nenhuma linha. O dono e os administradores veem tudo.</span></span>
              </label>
              {cfg.rls && (
                <div className="new-user-fields">
                  <label className="field">Coluna
                    <select value={cfg.rls.column} onChange={(e) => setCfg({ ...cfg, rls: { ...cfg.rls!, column: e.target.value } })}>
                      {dataset.columns.map((c) => <option key={c.name} value={c.name}>{c.name}</option>)}
                    </select>
                  </label>
                  <label className="field">Atributo do usuário
                    <input value={cfg.rls.attribute} placeholder="ex.: regiao" onChange={(e) => setCfg({ ...cfg, rls: { ...cfg.rls!, attribute: e.target.value.trim().toLowerCase() } })} />
                  </label>
                </div>
              )}
              <p className="muted small" style={{ margin: 0 }}>Datasets salvos a partir de uma consulta sobre este herdam a restrição.</p>
              <div style={{ display: "flex", gap: 8 }}>
                <button className="btn primary" onClick={save} disabled={busy || (cfg.rls !== null && !cfg.rls.attribute)}>{busy ? <span className="spinner" /> : null} Salvar</button>
                <button className="btn" onClick={onClose}>Cancelar</button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
