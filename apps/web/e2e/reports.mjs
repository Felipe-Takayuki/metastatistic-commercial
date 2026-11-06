/**
 * E2E dos relatórios: criar, editar os 3 tipos de bloco, reordenar, autosave, persistência após recarregar,
 * XSS em Markdown, exportar PDF (conteúdo inspecionado com pdftotext), conflito entre duas abas e exclusão.
 *   docker compose up -d --build && npm run e2e:reports        (E2E_SHOTS=/tmp/shots para capturas)
 */
import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, statSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { api, BASE, SHOTS, session } from "./lib.mjs";

const FIXTURE = join(dirname(fileURLToPath(import.meta.url)), "../../api/tests/fixtures/ttest.csv");
const s = await session({ allowConsole: { "status of 409": 1, "status of 404": 1 } });
const { page, check, shot } = s;
const TITLE = "E2E Relatório de vendas";
const EVIL = `<img src=x onerror="window.__xss=1">`;
const MD = `# Resumo\n\nTexto com **negrito** e ${EVIL}.\n\n[ruim](javascript:window.__xss=1) e [bom](https://exemplo.com)\n`;
const frame = (i) => page.locator(".block-frame").nth(i);
const saved = (p = page) => p.locator(".save-status.saved").waitFor({ timeout: 15000 });
const reportId = () => page.url().match(/#\/reports\/([0-9a-f]{32})/)?.[1];
const types = () => page.locator(".block-type").allInnerTexts();
let id, createdDataset = false;

const assertContent = async (p, label) => {
  check(`${label}: título como h1`, (await p.locator(".report-h1").innerText()) === TITLE);
  check(`${label}: Markdown renderizado (h2 e negrito)`, (await p.locator(".markdown h2").first().innerText()) === "Resumo" && (await p.locator(".markdown strong").count()) === 1);
  check(`${label}: HTML do Markdown aparece como texto, sem <img>/<script> nem link javascript:`,
    (await p.locator(".report-doc img").count()) === 0 && (await p.locator('a[href^="javascript" i]').count()) === 0 && (await p.locator(".markdown").first().innerText()).includes(EVIL));
  check(`${label}: link http(s) virou âncora segura`, (await p.locator('a[href="https://exemplo.com"][rel~="noopener"]').count()) === 1);
  check(`${label}: gráfico desenhado com título do bloco`, (await p.locator(".chart-box canvas, .chart-box svg").count()) === 1 && (await p.locator(".block-title").innerText()) === "Média por grupo");
  const t = (await p.locator("table.apa-table").first().innerText()).replace(/\s+/g, " ");
  check(`${label}: análise com os números do R (t=-2.628, df=78.000)`, t.includes("-2.628") && t.includes("78.000"), t);
  const yChart = (await p.locator(".chart-box").boundingBox()).y, yTable = (await p.locator("table.apa-table").first().boundingBox()).y;
  check(`${label}: ordem salva (análise antes do gráfico)`, yTable < yChart);
};

try {
  // --- dados de apoio ---
  await page.goto(BASE);
  await page.setInputFiles("input[type=file]", { name: "e2e-ttest.csv", mimeType: "text/csv", buffer: readFileSync(FIXTURE) });
  await page.getByRole("heading", { name: "e2e-ttest.csv" }).waitFor();
  createdDataset = true;

  // --- criar relatório ---
  await page.getByRole("link", { name: "Relatórios" }).click();
  await page.getByRole("button", { name: "Novo relatório" }).click();
  await page.waitForURL(/#\/reports\/[0-9a-f]{32}/);
  id = reportId();
  await page.locator(".title-input").waitFor(); // a página do relatório é carregada sob demanda
  check("relatório novo abre em modo de edição, com título editável", await page.locator(".title-input").isVisible());
  await page.locator(".title-input").fill(TITLE);

  // --- bloco de texto ---
  await page.getByRole("button", { name: "+ Texto" }).click();
  await page.getByLabel("Texto do bloco (Markdown)").fill(MD);
  check("pré-visualização: h2, sem <img>, sem link javascript:, link seguro",
    (await page.locator(".md-preview h2").innerText()) === "Resumo" && (await page.locator(".md-preview img").count()) === 0 &&
    (await page.locator('.md-preview a[href^="javascript" i]').count()) === 0 && (await page.locator('.md-preview a[href="https://exemplo.com"]').count()) === 1);

  // --- bloco de gráfico ---
  await page.getByRole("button", { name: "+ Gráfico" }).click();
  await frame(1).getByPlaceholder("Ex.: Receita média por região").fill("Média por grupo");
  await frame(1).getByRole("button", { name: "Escrever SQL" }).click(); // gráfico novo nasce no modo "sem SQL"
  await frame(1).locator(".cm-content").click();
  await page.keyboard.press("Control+A");
  await page.keyboard.type('SELECT "group", round(avg(score), 2) AS media FROM e2e_ttest GROUP BY 1 ORDER BY 1');
  await page.keyboard.press("Control+Enter");
  await frame(1).locator("canvas, svg").waitFor();
  check("gráfico do bloco: barras com controles de série", (await frame(1).getByRole("button", { name: "Barras" }).getAttribute("aria-pressed")) === "true");

  // --- bloco de análise ---
  await page.getByRole("button", { name: "+ Análise" }).click();
  await frame(2).getByLabel("Dataset").selectOption({ label: "e2e-ttest.csv" });
  check("análise: agrupamento de 2 níveis escolhido por padrão", (await frame(2).getByLabel("Variável de agrupamento (2 grupos)").inputValue()) === "group");
  await frame(2).getByRole("button", { name: "Executar análise" }).click();
  await frame(2).locator("table.apa-table").first().waitFor({ timeout: 60000 });
  await shot("r1-edicao");

  // --- reordenar + autosave ---
  await frame(2).getByRole("button", { name: "Mover bloco para cima" }).click();
  const order = await types();
  check("reordenar: análise subiu para 2º", order.length === 3 && /análise/i.test(order[1]) && /gráfico/i.test(order[2]), order.join(" | "));
  await saved();
  check("autosave: status 'Salvo'", /Salvo/.test(await page.locator(".save-status").innerText()));

  // --- visualizar ---
  await page.getByRole("button", { name: "Concluir edição" }).click();
  await page.locator(".chart-box canvas, .chart-box svg").waitFor();
  await page.locator("table.apa-table").first().waitFor();
  await assertContent(page, "visualização");
  await shot("r2-visualizacao");

  // --- recarregar: persistência de verdade (vem do servidor) ---
  await page.reload();
  await page.locator(".report-h1").waitFor();
  await page.locator(".chart-box canvas, .chart-box svg").waitFor();
  await page.locator("table.apa-table").first().waitFor({ timeout: 60000 });
  check("após recarregar abre em modo leitura (há blocos)", (await page.locator(".block-frame").count()) === 0);
  await assertContent(page, "após recarregar");
  check("nenhum script do Markdown foi executado", (await page.evaluate(() => window.__xss)) === undefined);

  // --- PDF: impressão limpa (só o documento) ---
  await page.emulateMedia({ media: "print" });
  const dir = mkdtempSync(join(tmpdir(), "e2e-pdf-"));
  const pdf = join(dir, "relatorio.pdf");
  await page.pdf({ path: pdf, format: "A4", printBackground: true });
  await page.emulateMedia({ media: null });
  const txt = execFileSync("pdftotext", ["-layout", pdf, "-"], { encoding: "utf8" });
  const pages = Number(/Pages:\s+(\d+)/.exec(execFileSync("pdfinfo", [pdf], { encoding: "utf8" }))?.[1]);
  check("PDF válido e não trivial", readFileSync(pdf).subarray(0, 4).toString() === "%PDF" && statSync(pdf).size > 20_000 && pages >= 1, `${statSync(pdf).size} bytes, ${pages} pág.`);
  check("PDF contém título, texto, tabela APA e números", [TITLE, "Resumo", "Independent Samples T-Test", "-2.628", "78.000", "Média por grupo"].every((x) => txt.includes(x)), txt.slice(0, 400));
  check("PDF não contém a interface (menu, barra de ferramentas, controles)", !["Exportar PDF", "Concluir edição", "Metastatistic", "Explorar", "Ver dados", "← Relatórios"].some((x) => txt.includes(x)), txt.slice(0, 400));
  check("PDF mostra o HTML do Markdown como texto", txt.includes("<img src=x"));
  // rótulos 9.97 / 11.08 existem SÓ no gráfico (a tabela traz 9.970 / 11.084): extraíveis => gráfico é vetor, não imagem borrada
  check("PDF: gráfico é vetorial (rótulos do gráfico extraíveis como texto)", /(^|\s)9\.97(\s|$)/m.test(txt) && /(^|\s)11\.08(\s|$)/m.test(txt));
  if (SHOTS) execFileSync("pdftoppm", ["-png", "-r", "70", "-f", "1", "-l", "1", pdf, join(SHOTS, "r3-pdf")]);

  // --- botão Exportar PDF: força tema claro e restaura depois ---
  await page.getByRole("button", { name: /Tema:/ }).click(); // auto -> claro
  await page.getByRole("button", { name: /Tema:/ }).click(); // claro -> escuro
  check("tema escuro ativo antes de exportar", (await page.evaluate(() => document.documentElement.getAttribute("data-theme"))) === "dark");
  await page.evaluate(() => { window.print = () => { window.__printedTheme = document.documentElement.getAttribute("data-theme"); dispatchEvent(new Event("afterprint")); }; });
  await page.getByRole("button", { name: "Exportar PDF" }).click();
  await page.waitForFunction(() => window.__printedTheme !== undefined, null, { timeout: 5000 });
  check("exportar imprime em tema CLARO mesmo com a interface escura", (await page.evaluate(() => window.__printedTheme)) === "light");
  check("depois de imprimir, o tema escuro do usuário é restaurado", (await page.evaluate(() => document.documentElement.getAttribute("data-theme"))) === "dark");
  await page.getByRole("button", { name: /Tema:/ }).click(); // escuro -> auto (estado original)

  // --- excluir bloco (confirmação) ---
  await page.getByRole("button", { name: "Editar" }).click();
  s.onNextDialog((d) => d.dismiss());
  await frame(0).getByRole("button", { name: "Excluir bloco" }).click();
  check("cancelar a confirmação mantém o bloco", (await page.locator(".block-frame").count()) === 3);
  s.onNextDialog((d) => d.accept());
  await frame(0).getByRole("button", { name: "Excluir bloco" }).click();
  check("confirmar exclui o bloco", (await page.locator(".block-frame").count()) === 2);
  await saved();

  // --- conflito entre duas abas ---
  const tabB = await s.newPage();
  await tabB.goto(`${BASE}/#/reports/${id}`);
  await tabB.locator(".report-h1").waitFor();
  await tabB.getByRole("button", { name: "Editar" }).click();
  await tabB.locator(".title-input").fill("E2E título da aba B");
  await saved(tabB);
  await page.locator(".title-input").fill("E2E título da aba A");
  await page.getByRole("alert").filter({ hasText: "outra aba" }).waitFor({ timeout: 15000 });
  check("conflito: aviso claro de que as edições NÃO foram salvas", (await page.locator(".save-status").innerText()).includes("Conflito"));
  const server = await (await fetch(`${BASE}/api/reports/${id}`)).json();
  check("conflito: o trabalho da aba B no servidor NÃO foi sobrescrito", server.title === "E2E título da aba B", server.title);
  await shot("r4-conflito");
  await page.getByRole("button", { name: "Recarregar a versão salva" }).click();
  await page.locator(".title-input, .report-h1").first().waitFor();
  check("recarregar mostra a versão salva pela aba B", (await page.locator(".report-h1, .title-input").first().evaluate((e) => e.value ?? e.textContent)) === "E2E título da aba B");
  await tabB.close();

  // --- relatório inexistente ---
  await page.goto(`${BASE}/#/reports/${"f".repeat(32)}`);
  await page.getByText("Não foi possível abrir o relatório").waitFor();
  check("relatório inexistente: mensagem e volta à lista", (await page.getByRole("link", { name: "Voltar aos relatórios" }).count()) === 1);

  // --- lista e exclusão ---
  await page.goto(`${BASE}/#/reports`);
  const row = page.locator(".report-row", { hasText: "E2E título da aba B" });
  await row.waitFor();
  check("lista mostra título e nº de blocos", (await row.innerText()).includes("2 blocos"));
  await shot("r5-lista");
  s.onNextDialog((d) => d.accept());
  await row.getByRole("button", { name: /Excluir/ }).click();
  await row.waitFor({ state: "detached" });
  check("excluir remove o relatório da lista e do servidor", (await fetch(`${BASE}/api/reports/${id}`)).status === 404);
  id = undefined;
} catch (e) {
  s.failures.push(`exceção: ${e.message}`);
  console.log(`FAIL exceção: ${e.message}`);
  await shot("r-erro");
}
await s.finish(async () => {
  if (id) await api.del(`/reports/${id}`);
  for (const r of (await api.list("/reports")).filter((r) => r.title.startsWith("E2E"))) await api.del(`/reports/${r.id}`);
  if (createdDataset) for (const d of (await api.list("/datasets")).filter((d) => d.name === "e2e-ttest.csv")) await api.del(`/datasets/${d.id}`);
});
