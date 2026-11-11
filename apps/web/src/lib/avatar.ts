export const AVATAR_TYPES = ["image/png", "image/jpeg", "image/webp", "image/gif"];
export const AVATAR_MAX_BYTES = 2 * 1024 * 1024; // igual ao limite da API (apps/api/app/avatars.py)
export const AVATAR_ACCEPT = AVATAR_TYPES.join(",");

/** Mensagem de problema com a imagem escolhida, ou null se estiver ok (a API valida de novo pelos bytes). */
export function avatarProblem(file: Pick<File, "type" | "size">): string | null {
  if (!AVATAR_TYPES.includes(file.type)) return "Use uma imagem PNG, JPEG, WebP ou GIF.";
  if (file.size === 0) return "O arquivo está vazio.";
  if (file.size > AVATAR_MAX_BYTES) return `A imagem tem ${(file.size / 1024 / 1024).toFixed(1)} MB; o máximo é ${AVATAR_MAX_BYTES / 1024 / 1024} MB.`;
  return null;
}

/** "Maria da Silva" -> "MS" (primeira e última palavra); usado quando a pessoa não tem foto. */
export function initials(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return "?";
  const first = words[0][0];
  const last = words.length > 1 ? words[words.length - 1][0] : "";
  return (first + last).toLocaleUpperCase("pt-BR");
}
