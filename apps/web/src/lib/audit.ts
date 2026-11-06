import type { AuditEvent } from "../api";

export const ACTION_LABEL: Record<string, string> = {
  setup: "Primeiro acesso", login: "Entrou", login_failed: "Login falhou", login_locked: "Login bloqueado", logout: "Saiu",
  change_password: "Trocou a senha", create_user: "Criou usuário", update_user: "Alterou usuário", delete_user: "Excluiu usuário",
  create: "Criou", delete: "Excluiu", move: "Moveu", rename: "Renomeou", set_access: "Mudou o acesso", denied: "Acesso negado",
};
export const KIND_LABEL: Record<string, string> = { user: "usuário", dataset: "dataset", report: "relatório", dashboard: "dashboard", collection: "coleção" };

export const actionLabel = (a: string): string => ACTION_LABEL[a] ?? a;

/** "Criou relatório · Meu relatório" — o item e o detalhe, sem repetir quando faltam. */
export function describeEvent(e: AuditEvent): string {
  const what = e.kind ? `${actionLabel(e.action)} ${KIND_LABEL[e.kind] ?? e.kind}` : actionLabel(e.action);
  return e.detail ? `${what} · ${e.detail}` : what;
}

/** Acontecimentos que merecem destaque na tela (algo deu errado ou foi barrado). */
export const isAlert = (a: string): boolean => a === "denied" || a === "login_failed" || a === "login_locked";
