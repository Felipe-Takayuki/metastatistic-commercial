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

/** "regiao=Sul,Norte; setor=A" -> {regiao: "Sul,Norte", setor: "A"}. Valores podem ter vírgulas; `;` separa atributos. */
export function parseAttributes(text: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const part of text.split(";")) {
    const i = part.indexOf("=");
    if (i < 0) continue;
    const name = part.slice(0, i).trim().toLowerCase();
    const value = part.slice(i + 1).split(",").map((v) => v.trim()).filter(Boolean).join(",");
    if (name && value) out[name] = value;
  }
  return out;
}

export const formatAttributes = (attrs: Record<string, string> | undefined): string =>
  Object.entries(attrs ?? {}).map(([k, v]) => `${k}=${v}`).join("; ");
