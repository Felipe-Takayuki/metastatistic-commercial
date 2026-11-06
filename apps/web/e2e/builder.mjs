/**
 * E2E do montador "sem SQL": criar gráfico e KPI num dashboard e um gráfico num relatório SEM escrever SQL, ver o SQL gerado,
 * trocar de dataset/cálculo/tipo, alternar para "Escrever SQL" e voltar, e reabrir o montador depois de recarregar.
 * Só usa SQL (não precisa do motor R).
 *   npm run e2e:builder      (E2E_URL=... para outra pilha; E2E_SHOTS=/dir para capturas)
 */
import { api, BASE, session } from "./lib.mjs";

const s = await session();
const { page, check, shot } = s;
// receita por região: Sul 300, Norte 200, Leste 400 (média 150, 100, 200); por grupo: A = 450, B = 450; total 900
const CSV = "regiao,grupo,receita,qtd\nSul,A,100,2\nSul,B,200,4\nNorte,A,50,1\nNorte,B,150,3\nLeste,A,300,5\nLeste,B,100,2\n";
const NAME = "e2e-vendas.csv";
const dashId = () => page.url().match(/#\/dashboards\/([0-9a-f]{32})/)?.[1];
const saved = () => page.locator(".save-status.saved").waitFor({ timeout: 15000 });
const server = async () => (await (await fetch(`${BASE}/api/dashboards/${dashId()}`)).json());
const D = () => page.getByRole("dialog");
const closeModal = async () => { await D().getByRole("button", { name: "Concluir" }).click(); await D().waitFor({ state: "detached" }); };
const generatedSql = async () => { const det = D().locator("details", { hasText: "Ver o SQL gerado" }); if (!(await det.evaluate((e) => e.open))) await det.locator("summary").click(); return (await det.locator("pre").innerText()).trim(); };
const waitSql = (frag) => page.waitForFunction((f) => [...document.querySelectorAll('pre[aria-label="SQL gerado"]')].some((e) => e.textContent.includes(f)), frag, { timeout: 15000 });
const created = [];

try {
  await page.goto(BASE);
  await page.setInputFiles("input[type=file]", { name: NAME, mimeType: "text/csv", buffer: Buffer.from(CSV) });
  await page.getByRole("heading", { name: NAME }).waitFor();
  created.push((await (await fetch(`${BASE}/api/datasets`)).json()).find((d) => d.name === NAME).id);

  // --- gráfico num dashboard, sem tocar em SQL ---
  await page.getByRole("link", { name: "Dashboards" }).click();
  await page.getByRole("button", { name: "Novo dashboard" }).click();
  await page.waitForURL(/#\/dashboards\/[0-9a-f]{32}/);
  const dashboardId = dashId();
  await page.getByRole("button", { name: "+ Gráfico", exact: true }).click();
  await D().waitFor();
  await D().locator("canvas, svg").first().waitFor({ timeout: 15000 });
  check("gráfico novo já aparece desenhado, sem escrever nada (média da 1ª coluna numérica por categoria)", true);
  check("nasce em 'Montar sem SQL' e o editor de SQL não aparece", (await D().getByRole("button", { name: "Montar sem SQL" }).getAttribute("aria-pressed")) === "true" && (await D().locator(".cm-content").count()) === 0);
  check("escolhas iniciais: categorias = regiao, cálculo = média, coluna = receita",
    (await D().getByLabel("Categorias", { exact: true }).inputValue()) === "regiao" && (await D().getByLabel("Cálculo 1", { exact: true }).inputValue()) === "mean" && (await D().getByLabel("Coluna do cálculo 1", { exact: true }).inputValue()) === "receita");
  check("o SQL gerado fica visível (só leitura)", (await generatedSql()).includes('round(avg("receita"), 2) AS "média de receita"') && (await generatedSql()).includes("GROUP BY 1"));
  check("3 categorias (Sul, Norte, Leste)", (await D().getByText("Ver dados (3 linhas)").count()) === 1);
  await shot("b1-grafico");

  await D().getByLabel("Categorias", { exact: true }).selectOption("grupo");
  await D().getByLabel("Cálculo 1", { exact: true }).selectOption("sum");
  await waitSql('sum("receita")');
  await D().getByText("Ver dados (2 linhas)").waitFor({ timeout: 15000 });
  check("trocar categoria e cálculo regera o SQL e o gráfico: soma por grupo (2 linhas)", (await generatedSql()).includes('"grupo"') && (await generatedSql()).includes('sum("receita") AS "soma de receita"'));
  await D().getByRole("button", { name: "+ valor" }).click();
  await D().getByLabel("Cálculo 2", { exact: true }).waitFor();
  await waitSql('AS "média de receita"');
  check("segundo valor no mesmo gráfico (até 3)", (await D().getByLabel("Cálculo 2", { exact: true }).count()) === 1);
  await D().getByRole("button", { name: "Remover valor 2" }).click();

  await D().getByLabel("O que mostrar").selectOption("points");
  await waitSql("LIMIT 5000");
  await D().getByText("Ver dados (6 linhas)").waitFor({ timeout: 15000 });
  check("'Cada linha como um ponto' vira dispersão com as 6 linhas", (await D().getByRole("button", { name: "Dispersão" }).getAttribute("aria-pressed")) === "true");
  await D().getByLabel("O que mostrar").selectOption("summary");
  await D().getByText(/Ver dados \(\d+ linhas\)/).waitFor();
  await closeModal();
  await saved();
  let d = await server();
  const chart = d.tiles.find((t) => t.type === "chart");
  check("servidor guarda as escolhas e o SQL gerado", chart?.builder?.kind === "summary" && chart.builder.dataset_id.length === 32 && chart.sql.startsWith('SELECT "') && chart.builder.measures.length === 1, JSON.stringify(chart?.builder));

  // --- KPI: número de linhas -> soma, sem SQL ---
  await page.getByRole("button", { name: "+ KPI", exact: true }).click();
  await D().waitFor();
  await D().getByText("Prévia: 6", { exact: true }).waitFor({ timeout: 15000 });
  check("KPI novo mostra o número de linhas (6) sem escrever nada", true);
  await D().getByLabel("Cálculo 1", { exact: true }).selectOption("sum");
  await D().getByLabel("Coluna do cálculo 1", { exact: true }).selectOption("receita");
  await D().getByText("Prévia: 900", { exact: true }).waitFor({ timeout: 15000 });
  check("soma de receita = 900", true);
  await shot("b2-kpi");
  await closeModal();
  await saved();
  check("o tile mostra 900", (await page.getByRole("region", { name: /^Tile KPI/ }).locator(".kpi-value").innerText()) === "900");

  // --- alternar para SQL e voltar ---
  await page.getByRole("button", { name: "Editar tile KPI" }).click();
  check("reabrir o tile reabre o montador com as escolhas salvas", (await D().getByLabel("Cálculo 1", { exact: true }).inputValue()) === "sum" && (await D().getByLabel("Coluna do cálculo 1", { exact: true }).inputValue()) === "receita");
  await D().getByRole("button", { name: "Escrever SQL" }).click();
  await D().locator(".cm-content").waitFor();
  check("'Escrever SQL' mantém o SQL gerado como ponto de partida", (await D().locator(".cm-content").innerText()).includes('sum("receita")'));
  await D().locator(".cm-content").click();
  await page.keyboard.press("Control+A");
  await page.keyboard.type('SELECT max(receita) FROM "e2e_vendas"');
  await page.keyboard.press("Control+Enter");
  await D().getByText("Prévia: 300", { exact: true }).waitFor({ timeout: 15000 });
  check("SQL escrito à mão roda como sempre (máximo = 300)", true);
  s.onNextDialog((dlg) => dlg.accept());
  await D().getByRole("button", { name: "Montar sem SQL" }).click();
  await D().getByLabel("Cálculo 1", { exact: true }).waitFor();
  await D().getByText("Prévia: 6", { exact: true }).waitFor({ timeout: 15000 });
  check("voltar a 'Montar sem SQL' pede confirmação, substitui o SQL e recomeça do padrão (6 linhas)", true);
  await closeModal();
  await saved();
  d = await server();
  check("servidor tem de novo as escolhas do montador no KPI", d.tiles.find((t) => t.type === "kpi")?.builder?.measures?.[0]?.fn === "count");

  // --- recarregar: nada se perde ---
  await page.reload();
  await page.getByRole("region", { name: /^Tile Gráfico/ }).locator("canvas, svg").first().waitFor({ timeout: 15000 });
  check("recarregar: gráfico e KPI continuam", (await page.getByRole("region", { name: /^Tile KPI/ }).locator(".kpi-value").innerText()) === "6");

  // --- gráfico num relatório ---
  await page.getByRole("link", { name: "Relatórios" }).click();
  await page.getByRole("button", { name: /Novo relatório/ }).click();
  await page.waitForURL(/#\/reports\/[0-9a-f]{32}/);
  const reportUrl = page.url();
  await page.getByRole("button", { name: "+ Gráfico" }).click();
  await page.locator(".block-frame canvas, .block-frame svg").first().waitFor({ timeout: 15000 });
  check("relatório: bloco de gráfico novo também já nasce desenhado, sem SQL", (await page.getByRole("button", { name: "Montar sem SQL" }).getAttribute("aria-pressed")) === "true");
  await shot("b3-relatorio");
  await saved(); // sair com o autosave pendente abriria o aviso "alterações não salvas"
  await page.goto(BASE);
  await api.del(`/reports/${reportUrl.match(/reports\/([0-9a-f]{32})/)[1]}`);
  await page.goto("about:blank");
  await api.del(`/dashboards/${dashboardId}`);
} catch (e) {
  s.failures.push(`exceção: ${e.message}`);
  console.log(`FAIL exceção: ${e.message}`);
  await shot("b-excecao");
}
await s.finish(async () => {
  for (const id of created) await api.del(`/datasets/${id}`);
});
