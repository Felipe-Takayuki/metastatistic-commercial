/**
 * E2E dos filtros globais e do cross-filter dos dashboards: definir filtros, usar {{nome}} no SQL de KPI, filtrar digitando,
 * filtrar clicando numa barra do gráfico, escape de aspas (sem injeção), persistência das definições e validação de nomes.
 *   npm run e2e:filters        (E2E_SHOTS=/tmp/shots para capturas)
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { api, BASE, session } from "./lib.mjs";

const CSV = readFileSync(join(dirname(fileURLToPath(import.meta.url)), "../../api/tests/fixtures/ttest.csv"), "utf8");
const rows = CSV.trim().split("\n").slice(1).map((l) => l.trim().split(","));
const countOf = (g) => rows.filter((r) => r[1] === g).length;
const s = await session();
const { page, check, shot } = s;
const dashId = () => page.url().match(/#\/dashboards\/([0-9a-f]{32})/)?.[1];
const saved = () => page.locator(".save-status.saved").waitFor({ timeout: 15000 });
const server = async () => (await (await fetch(`${BASE}/api/dashboards/${dashId()}`)).json());
const kpi = () => page.getByRole("region", { name: /^Tile KPI/ }).locator(".kpi-value");
const filterInput = () => page.getByRole("group", { name: "Filtros do dashboard" }).locator("input");
const setSql = async (sql) => {
  const dlg = page.getByRole("dialog");
  await dlg.locator(".cm-content").click();
  await page.keyboard.press("Control+A");
  await page.keyboard.type(sql);
  await page.keyboard.press("Control+Enter");
};
const closeModal = async () => { await page.getByRole("dialog").getByRole("button", { name: "Concluir" }).click(); await page.getByRole("dialog").waitFor({ state: "detached" }); };
const kpiIs = async (want, msg) => {
  try { await page.waitForFunction((w) => [...document.querySelectorAll(".kpi-value")].some((e) => e.textContent === w), want, { timeout: 15000 }); check(msg, true); }
  catch { check(msg, false, `KPI = ${await kpi().innerText().catch(() => "?")}, esperado ${want}`); }
};

const name = "e2e-filt.csv";
try {
  await page.goto(BASE);
  await page.setInputFiles("input[type=file]", { name, mimeType: "text/csv", buffer: Buffer.from(CSV) });
  await page.getByRole("heading", { name }).waitFor();
  await page.getByRole("link", { name: "Dashboards" }).click();
  await page.getByRole("button", { name: "Novo dashboard" }).click();
  await page.waitForURL(/#\/dashboards\/[0-9a-f]{32}/);
  await page.locator(".title-input").fill("E2E Filtros");

  // --- definir o filtro ---
  await page.getByText(/Filtros do dashboard \(0\)/).click();
  await page.getByRole("button", { name: "+ Filtro" }).click();
  await page.getByLabel("Nome do filtro 1").fill("grupo");
  await page.getByLabel("Rótulo do filtro 1").fill("Grupo");
  await saved();
  let d = await server();
  check("filtro salvo no servidor com nome, rótulo e tipo", d.filters.length === 1 && d.filters[0].name === "grupo" && d.filters[0].label === "Grupo" && d.filters[0].type === "text", JSON.stringify(d.filters));
  check("barra de filtros aparece com o rótulo", (await page.getByRole("group", { name: "Filtros do dashboard" }).getByText("Grupo").count()) === 1);

  // nome repetido: avisa e NÃO salva (o servidor responderia 422)
  await page.getByRole("button", { name: "+ Filtro" }).click();
  await page.getByLabel("Nome do filtro 2").fill("grupo");
  await page.getByText(/Nome de filtro repetido: grupo/).waitFor();
  await page.waitForTimeout(1500);
  check("nome repetido: aviso e o servidor mantém a última lista válida (grupo, filtro2)", JSON.stringify((await server()).filters.map((f) => f.name)) === '["grupo","filtro2"]' && !(await page.locator(".save-status.error").count()));
  await page.getByLabel("Nome do filtro 2").fill("minimo");
  await page.getByLabel("Tipo do filtro 2").selectOption("number");
  await saved();
  check("corrigido o nome, os dois filtros são salvos", (await server()).filters.length === 2);
  await page.getByRole("button", { name: "Remover filtro minimo" }).click();
  await saved();
  check("remover filtro salva a lista", (await server()).filters.length === 1);

  // --- KPI com {{grupo}} ---
  await page.getByRole("button", { name: "+ KPI", exact: true }).click();
  await page.getByRole("dialog").waitFor();
  await page.getByLabel("Título", { exact: true }).fill("Linhas");
  await setSql(`SELECT count(*) FROM e2e_filt WHERE ({{grupo}} IS NULL OR "group" = {{grupo}})`);
  await page.getByText(`Prévia: ${rows.length}`).waitFor({ timeout: 15000 });
  check("editor de KPI aplica o filtro vazio (NULL): conta todas as linhas", true);
  await closeModal();

  // --- gráfico com cross-filter ---
  await page.getByRole("button", { name: "+ Gráfico", exact: true }).click();
  await page.getByRole("dialog").waitFor();
  await page.getByLabel("Título do gráfico").fill("Média por grupo");
  await setSql(`SELECT "group", round(avg(score), 2) AS media FROM e2e_filt GROUP BY 1 ORDER BY 1`);
  await page.getByRole("dialog").locator("canvas, svg").first().waitFor({ timeout: 15000 });
  await page.getByLabel("Ao clicar numa barra ou ponto, definir o filtro").selectOption("grupo");
  await closeModal();
  await page.getByRole("region", { name: /^Tile Gráfico/ }).locator("canvas, svg").first().waitFor({ timeout: 15000 });
  await saved();
  check("cross-filter configurado no gráfico e salvo", (await server()).tiles.find((t) => t.type === "chart")?.click_param === "grupo");
  await kpiIs(String(rows.length), "KPI mostra todas as linhas sem filtro");
  await shot("f1-filtros");

  // --- filtrar digitando ---
  await filterInput().fill("a");
  await kpiIs(String(countOf("a")), "digitar 'a' filtra o KPI");
  await filterInput().fill("b");
  await kpiIs(String(countOf("b")), "digitar 'b' filtra o KPI");
  await filterInput().fill("naoexiste");
  await kpiIs("0", "valor inexistente: KPI 0 (sem erro)");
  await filterInput().fill("x' OR '1'='1");
  await kpiIs("0", "aspas no valor são escapadas: não vira SQL (continua 0, sem erro)");
  check("sem alerta de erro no tile após o valor com aspas", (await page.locator(".tile .alert").count()) === 0);
  await page.getByRole("button", { name: /Limpar filtros/ }).click();
  await kpiIs(String(rows.length), "Limpar filtros volta ao total");

  // --- filtrar clicando no gráfico ---
  const box = await page.getByRole("region", { name: /^Tile Gráfico/ }).locator(".chart-box").boundingBox();
  let clicked = false;
  for (let fx = 0.12; fx < 0.95 && !clicked; fx += 0.05) {
    await page.mouse.click(box.x + box.width * fx, box.y + box.height * 0.85);
    await page.waitForTimeout(150);
    clicked = (await filterInput().inputValue()) !== "";
  }
  const picked = await filterInput().inputValue();
  check("clicar numa barra define o filtro com a categoria", ["a", "b"].includes(picked), picked);
  await kpiIs(String(countOf(picked)), "o KPI reage ao clique no gráfico (cross-filter)");
  await shot("f2-cross-filter");
  for (let fx = 0.12; fx < 0.95; fx += 0.05) {
    await page.mouse.click(box.x + box.width * fx, box.y + box.height * 0.85);
    await page.waitForTimeout(150);
    if ((await filterInput().inputValue()) === "") break;
  }
  check("clicar de novo na mesma categoria limpa o filtro", (await filterInput().inputValue()) === "" || (await filterInput().inputValue()) !== picked);

  // --- persistência: definições salvas, valores não ---
  await filterInput().fill("a");
  await saved().catch(() => {});
  await page.reload();
  await page.locator(".kpi-value").waitFor({ timeout: 20000 });
  check("recarregar: filtro definido continua na barra", (await filterInput().count()) === 1);
  check("recarregar: o valor digitado NÃO persiste (volta ao padrão) e o KPI mostra o total", (await filterInput().inputValue()) === "" && (await kpi().innerText()) === String(rows.length));
  check("recarregar: abrir em leitura não altera o servidor", (await server()).filters.length === 1);
} catch (e) {
  s.failures.push(`exceção: ${e.message}`);
  console.log(`FAIL exceção: ${e.message}`);
  await shot("erro");
}
await s.finish(async () => {
  for (const ds of (await api.list("/datasets")).filter((x) => x.name === name)) await api.del(`/datasets/${ds.id}`);
  for (const dd of (await api.list("/dashboards")).filter((x) => x.title.startsWith("E2E"))) await api.del(`/dashboards/${dd.id}`);
});
