import { useCallback, useEffect, useState } from "react";
import { api, type Collection } from "../api";
import { validFilter, type CollectionFilter } from "../lib/collections";
import { useCan } from "./AuthGate";

/** Carrega as coleções e mantém o filtro escolhido válido. */
export function useCollections() {
  const [collections, setCollections] = useState<Collection[]>([]);
  const [filter, setFilter] = useState<CollectionFilter>("all");
  const reload = useCallback(async () => {
    const list = await api.listCollections();
    setCollections(list);
    setFilter((f) => validFilter(f, list.map((c) => c.id)));
  }, []);
  useEffect(() => { void reload().catch(() => undefined); }, [reload]);
  return { collections, filter, setFilter, reload };
}

interface Props {
  collections: Collection[];
  filter: CollectionFilter;
  counts: { all: number; none: number; byId: Record<string, number> };
  onFilter: (f: CollectionFilter) => void;
  onChanged: () => Promise<void> | void;
  onError: (msg: string) => void;
}

/** Faixa de coleções (pastas planas): escolher, criar, renomear e excluir. */
export function CollectionsPanel({ collections, filter, counts, onFilter, onChanged, onError }: Props) {
  const canCreate = useCan("editor");
  const current = collections.find((c) => c.id === filter);
  const run = async (fn: () => Promise<unknown>) => { try { await fn(); await onChanged(); } catch (e) { onError((e as Error).message); } };

  const create = () => {
    const name = window.prompt("Nome da nova coleção:");
    if (name?.trim()) void run(async () => onFilter((await api.createCollection(name)).id));
  };
  const rename = (c: Collection) => {
    const name = window.prompt("Novo nome da coleção:", c.name);
    if (name?.trim() && name.trim() !== c.name) void run(() => api.renameCollection(c.id, name));
  };
  const remove = (c: Collection) => {
    if (window.confirm(`Excluir a coleção "${c.name}"? Os itens dela voltam para "Sem coleção"; nada é apagado.`)) void run(() => api.deleteCollection(c.id));
  };

  const chip = (id: CollectionFilter, label: string, n: number) => (
    <button key={id} className="chip btn-chip coll-chip" aria-pressed={filter === id} onClick={() => onFilter(id)}>{label} <span className="muted">{n}</span></button>
  );

  return (
    <div className="coll-bar" role="group" aria-label="Coleções">
      {chip("all", "Todos", counts.all)}
      {chip("none", "Sem coleção", counts.none)}
      {collections.map((c) => chip(c.id, c.name, counts.byId[c.id] ?? 0))}
      {canCreate && <button className="btn ghost sm" onClick={create}>+ Nova coleção</button>}
      {current?.can_edit && (
        <>
          <button className="btn ghost sm" onClick={() => rename(current)}>Renomear</button>
          <button className="btn ghost sm" onClick={() => remove(current)}>Excluir coleção</button>
        </>
      )}
    </div>
  );
}

/** "Mover para…" de um item (só aparece quando o usuário pode alterá-lo). */
export function MoveSelect({ title, value, collections, onMove }: { title: string; value: string | null | undefined; collections: Collection[]; onMove: (id: string | null) => void }) {
  return (
    <select className="move-select" aria-label={`Coleção de ${title}`} value={value ?? ""} onChange={(e) => onMove(e.target.value || null)}>
      <option value="">Sem coleção</option>
      {collections.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
    </select>
  );
}
