/** Utilitários comuns dos testes e2e (Playwright headless contra a pilha no ar). */
import { chromium } from "playwright-core";
import { existsSync, mkdirSync, readdirSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

export const BASE = process.env.E2E_URL ?? "http://127.0.0.1:8080";
export const SHOTS = process.env.E2E_SHOTS;
if (SHOTS) mkdirSync(SHOTS, { recursive: true });

function chromiumPath() {
  if (process.env.CHROMIUM_PATH) return process.env.CHROMIUM_PATH;
  const root = join(homedir(), ".cache", "ms-playwright");
  if (!existsSync(root)) return undefined;
  for (const [prefix, rel] of [["chromium_headless_shell", "chrome-headless-shell-linux64/chrome-headless-shell"], ["chromium-", "chrome-linux64/chrome"]]) {
    const dir = readdirSync(root).find((d) => d.startsWith(prefix));
    if (dir && existsSync(join(root, dir, rel))) return join(root, dir, rel);
  }
  return undefined;
}

/**
 * @param allowConsole  { "trecho da mensagem": máximo de ocorrências } — erros de console esperados (ex.: 422/409 provocados de propósito)
 */
export async function session({ allowConsole = {} } = {}) {
  const browser = await chromium.launch({ executablePath: chromiumPath() });
  const context = await browser.newContext({ viewport: { width: 1360, height: 1250 }, colorScheme: "light" });
  const page = await context.newPage();
  const problems = [];
  const failures = [];
  let nextDialog = null;

  const watch = (p) => {
    p.on("console", (m) => ["error", "warning"].includes(m.type()) && problems.push(`console.${m.type()}: ${m.text()}`));
    p.on("pageerror", (e) => problems.push(`pageerror: ${e.message}`));
    p.on("dialog", (d) => {
      if (nextDialog) { const fn = nextDialog; nextDialog = null; fn(d); } // diálogo esperado (ex.: confirmar exclusão)
      else { problems.push(`dialog inesperado: ${d.message()}`); d.dismiss(); }
    });
  };
  watch(page);

  return {
    browser, context, page, failures,
    /** abre outra aba no mesmo contexto (com o mesmo monitoramento de erros) */
    async newPage() { const p = await context.newPage(); watch(p); return p; },
    /** o próximo diálogo (confirm/alert) é tratado por `fn`; qualquer outro falha o teste */
    onNextDialog(fn) { nextDialog = fn; },
    check(name, ok, detail = "") {
      console.log(`${ok ? "  ok " : "FAIL "} ${name}${!ok && detail ? ` — ${detail}` : ""}`);
      if (!ok) failures.push(name);
    },
    async shot(name, p = page) { if (SHOTS) { await p.waitForTimeout(300); await p.screenshot({ path: join(SHOTS, `${name}.png`) }); } },
    /** compara os erros de console com os permitidos; qualquer excedente/outro erro conta como falha */
    consoleVerdict() {
      const counts = {};
      const unexpected = problems.filter((m) => {
        const key = Object.keys(allowConsole).find((k) => m.includes(k));
        if (!key) return true;
        counts[key] = (counts[key] ?? 0) + 1;
        return counts[key] > allowConsole[key];
      });
      return unexpected;
    },
    async finish(cleanup) {
      try { await cleanup?.(); } finally { await browser.close(); }
      const unexpected = this.consoleVerdict();
      this.check("sem erros/avisos de console nem diálogos inesperados", unexpected.length === 0, unexpected.join(" | "));
      console.log(this.failures.length ? `\n${this.failures.length} falha(s): ${this.failures.join("; ")}` : "\nTudo certo.");
      process.exit(this.failures.length ? 1 : 0);
    },
  };
}

export const api = {
  async list(path) { return (await fetch(`${BASE}/api${path}`)).json().catch(() => []); },
  async del(path) { await fetch(`${BASE}/api${path}`, { method: "DELETE" }); },
};
