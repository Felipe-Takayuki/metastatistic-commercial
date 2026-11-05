/**
 * Teste de regressão no navegador (Playwright headless) contra a pilha no ar.
 *
 *   docker compose up -d --build            # interface em :8080
 *   npm run e2e                             # ou E2E_URL=http://127.0.0.1:5173 (vite dev)
 *   E2E_SHOTS=/tmp/shots npm run e2e        # salva capturas de tela
 *
 * Cria datasets próprios (prefixo "e2e-") e remove só eles ao final; não mexe nos seus.
 * Valores esperados do teste t: stats::t.test do R sobre apps/api/tests/fixtures/ttest.csv.
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { api, BASE, session } from "./lib.mjs";

const FIXTURE = join(dirname(fileURLToPath(import.meta.url)), "../../api/tests/fixtures/ttest.csv");
// O DROP TABLE do teste provoca de propósito UM 422; o navegador o registra como console.error.
const s = await session({ allowConsole: { "status of 422": 1 } });
const { page, check, shot } = s;

const upload = async (name, text) => {
  await page.setInputFiles("input[type=file]", { name, mimeType: "text/csv", buffer: Buffer.from(text) });
  await page.getByRole("heading", { name }).waitFor();
};
const runSql = async (sql) => {
  await page.locator(".cm-content").click();
  await page.keyboard.press("Control+A");
  await page.keyboard.type(sql);
  await page.keyboard.press("Control+Enter");
};
const text = async (sel) => (await page.locator(sel).first().innerText()).replace(/\s+/g, " ");

const created = [];
try {
  await page.goto(BASE);

  // --- upload + aba Dados ---
  await upload("e2e-ttest.csv", readFileSync(FIXTURE, "utf8"));
  created.push("e2e-ttest.csv");
  check("upload mostra o dataset e 80 linhas", (await text(".page-head")).includes("80 linhas"));
  await page.locator("table.data tbody tr").first().waitFor(); // a prévia carrega de forma assíncrona
  check("aba Dados lista as 2 colunas", (await page.locator(".col-card").count()) === 2);
  check("prévia traz as 80 linhas", (await page.locator("table.data tbody tr").count()) === 80);
  await shot("1-dados");

  // --- SQL: gráfico, tabela, e SQL proibido ---
  await page.getByRole("tab", { name: "Consulta SQL" }).click();
  await runSql('SELECT "group", round(avg(score), 2) AS media FROM e2e_ttest GROUP BY 1 ORDER BY 1');
  await page.locator(".chart-box canvas").waitFor();
  check("gráfico de barras desenhado com título", (await text(".chart-title")) === "media por group");
  await shot("2-sql-grafico");
  await page.getByRole("tab", { name: "Tabela" }).click();
  check("aba Tabela mostra os 2 grupos", (await page.locator(".card table.data tbody tr").count()) === 2);
  await runSql("DROP TABLE e2e_ttest");
  await page.locator(".alert[role=alert]").waitFor();
  check("SQL de escrita é recusado com mensagem", (await text(".alert[role=alert]")).includes("read-only"));

  // --- Análise: números iguais ao R ---
  await page.getByRole("tab", { name: "Análise estatística" }).click();
  check("agrupamento padrão é a coluna de 2 níveis", (await page.locator("select").nth(1).inputValue()) === "group");
  // Motor "lento": a resposta demora ~9,5 s. O usuário deve ser avisado (nada de spinner mudo) e o resultado ainda chegar.
  await page.route("**/api/analyses/run", async (route) => { await new Promise((r) => setTimeout(r, 9500)); await route.continue(); });
  await page.getByRole("button", { name: "Executar análise" }).click();
  await page.getByText("Ainda calculando").waitFor({ timeout: 12000 });
  // depois do 1º ciclo de consulta (2 s) o aviso deixa de ser genérico e mostra a situação real do motor (/analyses/status)
  await page.getByText(/\d+ de \d+ motores? ocupados?/).waitFor({ timeout: 8000 });
  check("análise lenta: o aviso mostra workers ocupados e a regra de uma análise por vez", /Cada motor executa uma análise por vez/.test(await page.locator('[role="status"]').first().innerText()));
  await page.locator("table.apa-table").first().waitFor({ timeout: 60000 });
  check("análise lenta: o resultado chega e o aviso some", (await page.getByText("Ainda calculando").count()) === 0);
  await page.unroute("**/api/analyses/run");
  const ttest = await text("table.apa-table");
  check("Student: t=-2.628, df=78.000, p=.010", ["Student", "-2.628", "78.000", ".010"].every((s) => ttest.includes(s)), ttest);
  check("Welch: df=72.720", ttest.includes("Welch") && ttest.includes("72.720"), ttest);
  check("tabela APA sem a coluna interna 'v' como cabeçalho", !/^\s*v\s/.test(ttest));
  await shot("3-analise");

  // --- agrupamento inválido (3 níveis) bloqueia a execução ---
  await upload("e2e-tres.csv", "score,g\n" + Array.from({ length: 30 }, (_, i) => `${i},${"abc"[i % 3]}`).join("\n"));
  created.push("e2e-tres.csv");
  await page.getByRole("tab", { name: "Análise estatística" }).click();
  check("agrupamento com 3 níveis: aviso e botão desabilitado",
    (await page.getByText("tem 3 níveis").count()) === 1 && (await page.getByRole("button", { name: "Executar análise" }).isDisabled()));
  await shot("4-agrupamento-invalido");

  // --- XSS: cabeçalho e valores de CSV nunca viram HTML ---
  const evil = `<img src=x onerror="window.__xss=1">`;
  const q = (s) => `"${s.replace(/"/g, '""')}"`;
  await upload("e2e-xss.csv", `${q(`k${evil}`)},${q(`v${evil}`)}\n${q(evil)},5\n${q(`b${evil}`)},9\n`);
  created.push("e2e-xss.csv");
  await page.locator("table.data th", { hasText: "<img src=x" }).first().waitFor(); // a prévia carrega de forma assíncrona
  check("Dados: nome da coluna aparece como texto literal", (await page.locator("table.data th", { hasText: "<img src=x" }).count()) > 0);
  await page.getByRole("tab", { name: "Consulta SQL" }).click();
  await runSql("SELECT * FROM e2e_xss");
  await page.locator(".chart-box canvas").waitFor();
  // Varre o gráfico com o mouse até o tooltip aparecer e lê o texto DO ELEMENTO do tooltip (não da página).
  const box = await page.locator(".chart-box").boundingBox();
  const tooltip = page.locator('.chart-box div[style*="box-shadow"]');
  let tipText = "";
  for (let fx = 0.04; fx < 0.97 && !tipText.includes("<img"); fx += 0.02) {
    await page.mouse.move(box.x + box.width * fx, box.y + box.height * 0.8);
    await page.waitForTimeout(60);
    if (await tooltip.first().isVisible().catch(() => false)) tipText = await tooltip.first().innerText();
  }
  check("tooltip do gráfico apareceu e exibe o HTML como texto literal", tipText.includes('<img src=x onerror="window.__xss=1">'), JSON.stringify(tipText));
  check("o tooltip não contém elementos HTML injetados", (await tooltip.first().locator("img, script").count()) === 0);
  await shot("5-xss");
  check("nenhum script de CSV foi executado", (await page.evaluate(() => window.__xss)) === undefined);
} catch (e) {
  s.failures.push(`exceção: ${e.message}`);
  console.log(`FAIL exceção: ${e.message}`);
  await shot("erro");
}
await s.finish(async () => {
  const list = await api.list("/datasets");
  for (const d of list.filter((d) => created.includes(d.name))) await api.del(`/datasets/${d.id}`);
});
