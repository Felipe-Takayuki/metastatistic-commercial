import type { Role } from "../api";

export const ROLE_LABEL: Record<Role, string> = { viewer: "Leitor", editor: "Editor", admin: "Administrador" };
export const ROLE_HELP: Record<Role, string> = {
  viewer: "vê dados, relatórios e dashboards e roda consultas e análises",
  editor: "também cria, altera e exclui datasets, relatórios e dashboards",
  admin: "também gerencia usuários",
};
const ORDER: Role[] = ["viewer", "editor", "admin"];

/** `role` inclui `needed`? (cada papel contém o anterior). A API é quem impõe; isto só esconde o que não funcionaria. */
export const roleCan = (role: Role | undefined, needed: Role): boolean => role !== undefined && ORDER.indexOf(role) >= ORDER.indexOf(needed);

export const MIN_PASSWORD = 8;

/** Mensagem de problema na senha/usuário, ou null se estiver ok (a API valida de novo). */
export function credentialProblem(username: string, password: string): string | null {
  const name = username.trim();
  if (name.length < 3 || name.length > 60 || /\s/.test(name)) return "O usuário deve ter de 3 a 60 caracteres, sem espaços.";
  if (password.length < MIN_PASSWORD) return `A senha deve ter pelo menos ${MIN_PASSWORD} caracteres.`;
  return null;
}
