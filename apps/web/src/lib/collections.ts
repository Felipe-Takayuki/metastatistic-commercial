/** Filtro das listas de relatórios/dashboards: "all" = tudo, "none" = sem coleção, ou o id de uma coleção. */
export type CollectionFilter = "all" | "none" | string;

export function filterByCollection<T extends { collection_id?: string | null }>(items: T[], filter: CollectionFilter): T[] {
  if (filter === "all") return items;
  if (filter === "none") return items.filter((i) => !i.collection_id);
  return items.filter((i) => i.collection_id === filter);
}

/** Um filtro que aponta para uma coleção que não existe mais (excluída) volta a "all". */
export const validFilter = (filter: CollectionFilter, ids: string[]): CollectionFilter =>
  filter === "all" || filter === "none" || ids.includes(filter) ? filter : "all";

/** O usuário (com papel de editor ou mais) pode alterar este item? `can_edit` ausente conta como sim. */
export const itemEditable = (roleCanEdit: boolean, item: { can_edit?: boolean }): boolean => roleCanEdit && item.can_edit !== false;
