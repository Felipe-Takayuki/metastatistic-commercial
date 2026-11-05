/**
 * E2E das análises da Fase 4: "Salvar como dataset" (SQL -> dataset derivado), ANOVA em blocos casualizados, correlação,
 * regressão linear, qui-quadrado e um bloco de ANOVA num relatório. Os números esperados vêm do R puro
 * (apps/api/tests/fixtures/r_reference.json, gerado por make_reference.R sobre fixtures sintéticas).
 *   docker compose up -d --build && npm run e2e:analyses        (E2E_SHOTS=/tmp/shots para capturas)
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { api, BASE, session } from "./lib.mjs";

const FIX = join(dirname(fileURLToPath(import.meta.url)), "../../api/tests/fixtures");
const REF = JSON.parse(readFileSync(join(FIX, "r_reference.json"), "utf8"));
const s = await session();
const { page, check, shot } = s;

const f3 = (x) => x.toFixed(3);
const p3 = (x) => x.toFixed(3).replace(/^0/, ""); // APA: p sem zero à esquerda
const created = [];
page.on("request", (r) => { if (process.env.E2E_DEBUG && r.url().includes("/analyses/run")) console.log("  REQ", r.postData()); });
let reportId;

const upload = async (name, text) => {
  await page.setInputFiles("input[type=file]", { name, mimeType: "text/csv", buffer: Buffer.from(text) });
  await page.getByRole("heading", { name }).waitFor();
  created.push(name);
};
const runSql = async (sql) => {
  await page.locator(".cm-content").click();
  await page.keyboard.press("Control+A");
  await page.keyboard.type(sql);
  await page.keyboard.press("Control+Enter");
};
/** Executa a consulta atual e a grava como dataset; o App abre o novo dataset. */
const saveAsDataset = async (name) => {
  await page.getByRole("button", { name: "Salvar como dataset…" }).click();
  await page.getByLabel("Nome do novo dataset").fill(name);
  await page.getByRole("button", { name: "Salvar", exact: true }).click();
  await page.getByRole("heading", { name }).waitFor({ timeout: 30000 });
  created.push(name);
};
const pickAnalysis = async (title) => page.locator(".analysis-picker").getByRole("tab", { name: title, exact: true }).click();
const run = async () => {
  await page.getByRole("button", { name: "Executar análise" }).click();
  await page.locator("table.apa-table").first().waitFor({ timeout: 90000 });
};
const resultText = async () => (await page.locator(".analysis-grid .card").nth(1).innerText()).replace(/\s+/g, " ");
const has = (txt, ...needles) => needles.every((n) => txt.includes(n));

try {
  await page.goto(BASE);

  // --- dataset de origem + "Salvar como dataset": coluna derivada `bloco` (1,2,3,4,1,2,3,4…) ---
  await upload("e2e-dbc-raw.csv", readFileSync(join(FIX, "dbc_raw.csv"), "utf8"));
  await page.getByRole("tab", { name: "Consulta SQL" }).click();
  await runSql('SELECT ((row_number() OVER () - 1) % 4) + 1 AS bloco, * FROM e2e_dbc_raw');
  await page.getByRole("tab", { name: "Tabela" }).click();
  await page.locator(".card table.data tbody tr").first().waitFor();
  check("consulta com coluna derivada devolve as 32 linhas", (await page.locator(".card table.data tbody tr").count()) === 32);
  await saveAsDataset("e2e-dbc");
  check("dataset derivado criado com 32 linhas", (await page.locator(".page-head").innerText()).includes("32 linhas"));
  await page.locator(".col-card").first().waitFor();
  const cols = await page.locator(".col-card").allInnerTexts();
  check("a coluna derivada `bloco` é a 1ª e vem como ordinal", /bloco/.test(cols[0]) && /ordinal/i.test(cols[0]), cols[0]);
  await shot("a1-dataset-derivado");

  // --- ANOVA em blocos casualizados (modelo ADITIVO: sem interação) ---
  await page.getByRole("tab", { name: "Análise estatística" }).click();
  await pickAnalysis("ANOVA");
  await page.getByLabel("Variável dependente (escalar)").selectOption("produtividade");
  await page.getByLabel(/^tratamento/).check();
  await page.getByLabel(/^bloco/).check();
  check("ANOVA: sem interações por padrão", !(await page.getByLabel("Incluir interações entre os fatores").isChecked()));
  await run();
  let t = await resultText();
  const A = REF.anova;
  check("ANOVA: tratamento F, p e gl iguais ao R", has(t, f3(A.trat.F), p3(A.trat.p)), t.slice(0, 600));
  check("ANOVA: bloco F e p iguais ao R", has(t, f3(A.bloco.F), p3(A.bloco.p)));
  check("ANOVA: resíduos com 21 gl (modelo aditivo, não saturado)", /Residuals\s+[\d.,]+\s+21(\.000)?\b/.test(t) || t.includes("21.000"), t.slice(0, 600));
  check("ANOVA: nenhuma linha de interação", !t.includes("✻"));
  check("ANOVA: sem mensagem de erro do JASP", !/residual df|error/i.test(t));
  await shot("a2-anova");

  // interação ligada: aparece a linha tratamento ✻ bloco? (1 obs. por célula -> o JASP recusa; só confirmamos que a UI mostra algo)
  // --- Correlação ---
  await pickAnalysis("Correlação");
  for (const v of ["produtividade", "altura", "diametro"]) await page.getByLabel(new RegExp(`^${v}`)).check();
  await run();
  t = await resultText();
  const c = REF.corr[0];
  check("Correlação: r de Pearson produtividade×altura igual ao R", has(t, f3(c.pearson).replace(/^0/, "")) || has(t, f3(c.pearson)), t.slice(0, 500));
  await shot("a3-correlacao");

  // --- Regressão linear ---
  await pickAnalysis("Regressão linear");
  await page.getByLabel("Variável dependente (escalar)").selectOption("produtividade");
  await page.getByLabel(/^altura/).check();
  await page.getByLabel(/^diametro/).check();
  await run();
  t = await resultText();
  const R = REF.reg;
  check("Regressão: R² e F iguais ao R", has(t, f3(R.R2).replace(/^0/, "")) || has(t, f3(R.R2)), t.slice(0, 500));
  check("Regressão: F(2, 29) igual ao R", has(t, f3(R.F)), t.slice(0, 500));
  await shot("a4-regressao");

  // --- Teste t pareado (altura × diametro) ---
  await pickAnalysis("Teste t pareado");
  await page.getByLabel("1ª medida (escalar)").selectOption("altura");
  await page.getByLabel("2ª medida (escalar)").selectOption("diametro");
  await page.getByLabel("Wilcoxon (postos sinalizados)").check();
  await run();
  t = await resultText();
  const P = REF.paired;
  check("t pareado: t, gl e diferença média iguais ao R", has(t, f3(P.t), " 31 ", f3(P.mean_diff)), t.slice(0, 500));
  check("t pareado: nomes das duas medidas na tabela", has(t, "altura", "diametro"), t.slice(0, 300));
  await shot("a3b-t-pareado");

  // --- Teste t de uma amostra (produtividade vs 200) ---
  await pickAnalysis("Teste t de uma amostra");
  await page.getByLabel(/^produtividade/).check();
  await page.getByLabel("Valor de referência").fill("200");
  await run();
  t = await resultText();
  const O = REF.onesample;
  check("t de uma amostra: t, gl e p iguais ao R", has(t, f3(O.t), " 31 ", p3(O.p)), t.slice(0, 500));
  await shot("a3c-t-uma-amostra");

  // --- Estatísticas descritivas ---
  await pickAnalysis("Estatísticas descritivas");
  await page.getByLabel(/^produtividade/).check();
  await run();
  t = await resultText();
  const D = REF.desc;
  check("descritivas: média, desvio padrão, mediana, mínimo e máximo iguais ao R", has(t, f3(D.mean), f3(D.sd), f3(D.median), f3(D.min), f3(D.max)), t.slice(0, 600));
  check("descritivas: nenhuma célula vira [object Object]", !t.includes("[object Object]") && !t.includes('{"'), t.slice(0, 400));
  await shot("a3d-descritivas");

  // --- Qui-quadrado: dataset derivado com CASE (faixa) ---
  await upload("e2e-faixa-src.csv", readFileSync(join(FIX, "ttest.csv"), "utf8"));
  await page.getByRole("tab", { name: "Consulta SQL" }).click();
  await runSql(`SELECT "group" AS grupo, CASE WHEN score < 9 THEN 'baixo' WHEN score < 11 THEN 'medio' ELSE 'alto' END AS faixa FROM e2e_faixa_src`);
  await page.getByRole("tab", { name: "Tabela" }).click();
  await page.locator(".card table.data tbody tr").first().waitFor();
  await saveAsDataset("e2e-faixas");
  await page.getByRole("tab", { name: "Análise estatística" }).click();
  await pickAnalysis("Qui-quadrado (tabela de contingência)");
  check("Qui-quadrado: linhas e colunas escolhidas por padrão (2 categóricas)",
    (await page.getByLabel(/^Linhas/).inputValue()) !== "" && (await page.getByLabel(/^Colunas/).inputValue()) !== "");
  await page.getByLabel(/^Linhas/).selectOption("grupo");
  await page.getByLabel(/^Colunas/).selectOption("faixa");
  await run();
  t = await resultText();
  const X = REF.chi;
  check("Qui-quadrado: X², gl e p iguais ao R", has(t, f3(X.X2), p3(X.p)), t.slice(0, 600));
  const tests = page.locator("figure.apa").filter({ hasText: "Chi-Squared Tests" });
  const rows = (await tests.locator("tbody tr").allInnerTexts()).map((r) => r.replace(/\s+/g, " ").trim());
  check("Qui-quadrado: tabela de testes transposta (uma linha por teste: Χ² e N), sem cabeçalhos repetidos",
    rows.length === 2 && /^[ΧX]²/.test(rows[0]) && rows[1].startsWith("N") && (await tests.locator("thead th", { hasText: "Value" }).count()) === 1, rows.join(" | "));
  check("Qui-quadrado: linha do N mostra 80 (inteiro), não 80.000", /^N\s+80$/.test(rows[1] ?? ""), rows[1]);
  await shot("a5-qui-quadrado");

  // --- Bloco de ANOVA num relatório ---
  await page.getByRole("link", { name: "Relatórios" }).click();
  await page.getByRole("button", { name: "Novo relatório" }).click();
  await page.waitForURL(/#\/reports\/[0-9a-f]{32}/);
  reportId = page.url().match(/#\/reports\/([0-9a-f]{32})/)?.[1];
  await page.locator(".title-input").fill("E2E Relatório ANOVA");
  await page.getByRole("button", { name: "+ Análise", exact: true }).click();
  const frame = page.locator(".block-frame").nth(0);
  await frame.getByLabel(/^Análise/).selectOption({ label: "ANOVA" });
  await frame.getByLabel("Dataset").selectOption({ label: "e2e-dbc" });
  await frame.getByLabel("Variável dependente (escalar)").selectOption("produtividade");
  await frame.getByLabel(/^tratamento/).check();
  await frame.getByLabel(/^bloco/).check();
  await frame.getByRole("button", { name: "Executar análise" }).click();
  await frame.locator("table.apa-table").first().waitFor({ timeout: 90000 });
  let bt = (await frame.locator(".analysis-out").innerText()).replace(/\s+/g, " ");
  check("bloco de relatório: ANOVA com os números do R", has(bt, f3(A.trat.F), f3(A.bloco.F)), bt.slice(0, 400));
  await page.locator(".save-status.saved").waitFor({ timeout: 15000 });

  // recarrega: vira modo leitura e reexecuta a ANOVA salva (análise + dataset + opções persistidos)
  await page.reload();
  await page.locator(".report-doc table.apa-table").first().waitFor({ timeout: 90000 });
  bt = (await page.locator(".report-doc").innerText()).replace(/\s+/g, " ");
  check("relatório recarregado: a ANOVA salva reaparece com os números do R", has(bt, f3(A.trat.F), f3(A.bloco.F)), bt.slice(0, 400));
  await shot("a6-relatorio-anova");
} catch (e) {
  s.failures.push(`exceção: ${e.message}`);
  console.log(`FAIL exceção: ${e.message}`);
  await shot("erro");
}
await s.finish(async () => {
  for (const d of (await api.list("/datasets")).filter((d) => created.includes(d.name))) await api.del(`/datasets/${d.id}`);
  if (reportId) await api.del(`/reports/${reportId}`);
});
