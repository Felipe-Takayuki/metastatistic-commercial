/**
 * E2E da aba Perfil (foto de perfil). Exige pilha NOVA com AUTH_ENABLED=true (como o e2e:auth):
 *   AUTH_ENABLED=true DATA_DIR=$(mktemp -d) uvicorn app.main:app --port 8010      (em apps/api)
 *   API_URL=http://127.0.0.1:8010 npm run dev &                                    (em apps/web, porta 5173)
 *   E2E_URL=http://127.0.0.1:5173 npm run e2e:profile
 * Com STORAGE_BACKEND=s3 + Garage no ar, a foto vai para o bucket; sem isso, para o disco.
 */
import { deflateSync } from "node:zlib";
import { BASE, session } from "./lib.mjs";

const s = await session({ allowConsole: { "status of 401": 5, "status of 404": 3, "status of 422": 1 } });
const { page, check, shot } = s;
const PASS = "senha-forte-1";

// PNG 8x8 vermelho, gerado na hora (sem arquivo de fixture)
function png() {
  const crc = (buf) => { let c, t = []; for (let n = 0; n < 256; n++) { c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1; t[n] = c >>> 0; } let r = 0xffffffff; for (const b of buf) r = t[(r ^ b) & 255] ^ (r >>> 8); return (r ^ 0xffffffff) >>> 0; };
  const chunk = (type, data) => { const len = Buffer.alloc(4); len.writeUInt32BE(data.length); const td = Buffer.concat([Buffer.from(type), data]); const c = Buffer.alloc(4); c.writeUInt32BE(crc(td)); return Buffer.concat([len, td, c]); };
  const ihdr = Buffer.alloc(13); ihdr.writeUInt32BE(8, 0); ihdr.writeUInt32BE(8, 4); ihdr[8] = 8; ihdr[9] = 2;
  const row = Buffer.concat([Buffer.from([0]), Buffer.from(Array(8).fill([220, 40, 40]).flat())]);
  const raw = Buffer.concat(Array(8).fill(row));
  return Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]), chunk("IHDR", ihdr), chunk("IDAT", deflateSync(raw)), chunk("IEND", Buffer.alloc(0))]);
}

try {
  const setup = await page.request.post(`${BASE}/api/auth/setup`, { data: { username: "perfil", password: PASS, display_name: "Maria da Silva" } });
  check("administrador criado pela API", setup.status() === 201);
  await page.goto(BASE);
  await page.locator(".topbar").waitFor();
  check("cadastro já abre a sessão", true);

  check("chip da barra mostra iniciais sem foto", (await page.locator(".user-chip .avatar").innerText()).trim() === "MS");
  await page.getByRole("link", { name: "Perfil", exact: true }).click();
  await page.getByRole("heading", { name: "Perfil", exact: true }).waitFor();
  check("aba Perfil abre em #/profile", page.url().endsWith("#/profile"));
  check("sem foto: não oferece 'Remover foto'", (await page.getByRole("button", { name: "Remover foto" }).count()) === 0);
  await shot("profile-empty");

  // arquivo inválido: recusado no navegador, sem ir à API
  await page.locator('input[type="file"]').setInputFiles({ name: "x.txt", mimeType: "text/plain", buffer: Buffer.from("oi") });
  check("tipo inválido mostra aviso", (await page.getByRole("alert").innerText()).includes("PNG, JPEG, WebP ou GIF"));

  // envio de verdade
  await page.locator('input[type="file"]').setInputFiles({ name: "eu.png", mimeType: "image/png", buffer: png() });
  await page.getByRole("status").filter({ hasText: "Foto atualizada" }).waitFor();
  await page.locator(".profile-avatar img").waitFor();
  check("foto aparece no perfil", (await page.locator(".profile-avatar img").evaluate((i) => i.naturalWidth)) === 8);
  check("foto aparece também na barra superior", (await page.locator(".user-chip img").count()) === 1);
  check("agora oferece 'Remover foto'", (await page.getByRole("button", { name: "Remover foto" }).count()) === 1);
  await shot("profile-with-photo");

  await page.reload();
  await page.locator(".profile-avatar img").waitFor();
  check("foto sobrevive ao recarregar (veio do armazenamento)", true);

  await page.getByRole("button", { name: "Remover foto" }).click();
  await page.getByRole("status").filter({ hasText: "Foto removida" }).waitFor();
  check("remover volta às iniciais", (await page.locator(".profile-avatar").innerText()).trim() === "MS");
} catch (e) {
  s.check("execução sem exceção", false, String(e));
}
await s.finish();
