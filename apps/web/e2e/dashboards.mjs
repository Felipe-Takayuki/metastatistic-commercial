/**
 * E2E dos dashboards: criar, tiles de KPI/gráfico/texto, arrastar e redimensionar na grade, autosave, persistência após
 * recarregar, tela estreita (empilhado), XSS em texto e exclusão. Valores esperados calculados do próprio CSV da fixture.
 *   docker compose up -d --build && npm run e2e:dashboards        (E2E_SHOTS=/tmp/shots para capturas)
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { api, BASE, session } from "./lib.mjs";

const CSV = readFileSync(join(dirname(fileURLToPath(import.meta.url)), "../../api/tests/fixtures/ttest.csv"), "utf8");
const scores = CSV.trim().split("\n").slice(1).map((l) => Number(l.split(",")[0]));
const mean = scores.reduce((a, b) => a + b, 0) / scores.length;
const EVIL = `<img src=x onerror="window.__xss=1">`;

const s = await session({ allowConsole: { "status of 409": 1 } }); // o conflito é provocado de propósito
const { page, check, shot } = s;
const dashId = () => page.url().match(/#\/dashboards\/([0-9a-f]{32})/)?.[1];
const saved = () => page.locator(".save-status.saved").waitFor({ timeout: 15000 });
const tileByName = (label) => page.getByRole("region", { name: new RegExp(`^Tile ${label}`) });
const server = async () => (await (await fetch(`${BASE}/api/dashboards/${dashId()}`)).json());
const setSql = async (sql) => {
  const dlg = page.getByRole("dialog");
  await dlg.getByRole("button", { name: "Escrever SQL" }).click(); // gráficos e KPIs novos nascem no modo "sem SQL"
  await dlg.locator(".cm-content").click();
  await page.keyboard.press("Control+A");
  await page.keyboard.type(sql);
  await page.keyboard.press("Control+Enter");
};
const closeModal = async () => { await page.getByRole("dialog").getByRole("button", { name: "Concluir" }).click(); await page.getByRole("dialog").waitFor({ state: "detached" }); };
/** arrasta com o mouse em passos (a grade só começa a arrastar após alguns pixels) */
const drag = async (from, dx, dy) => {
  const b = await from.boundingBox();
  const x = b.x + b.width / 2, y = b.y + b.height / 2;
  await page.mouse.move(x, y); await page.mouse.down();
  await page.mouse.move(x + dx / 2, y + dy / 2, { steps: 8 }); await page.mouse.move(x + dx, y + dy, { steps: 8 });
  await page.mouse.up();
};

let name = "e2e-dash.csv";
try {
  await page.goto(BASE);
  await page.setInputFiles("input[type=file]", { name, mimeType: "text/csv", buffer: Buffer.from(CSV) });
  await page.getByRole("heading", { name }).waitFor();

  // --- criar ---
  await page.getByRole("link", { name: "Dashboards" }).click();
  check("lista vazia mostra a explicação", (await page.getByText("Nenhum dashboard ainda").count()) === 1 || (await page.locator(".report-row").count()) >= 0);
  await page.getByRole("button", { name: "Novo dashboard" }).click();
  await page.waitForURL(/#\/dashboards\/[0-9a-f]{32}/);
  await page.locator(".title-input").waitFor();
  await page.locator(".title-input").fill("E2E Painel de vendas");
  check("dashboard novo abre em modo de edição", await page.getByRole("button", { name: "Concluir edição" }).isVisible());

  // --- KPI ---
  await page.getByRole("button", { name: "+ KPI", exact: true }).click();
  await page.getByRole("dialog").waitFor();
  await page.getByLabel("Título", { exact: true }).fill("Média do score");
  await setSql("SELECT avg(score) FROM e2e_dash");
  await page.getByLabel("Casas decimais").fill("2");
  await page.getByLabel("Sufixo").fill(" pts");
  const want = `${mean.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} pts`;
  await page.getByText(`Prévia: ${want}`).waitFor({ timeout: 15000 });
  check("KPI: prévia no editor com casas, sufixo e vírgula decimal", true);
  await closeModal();
  check("KPI: valor no tile igual à média do CSV", (await tileByName("KPI").locator(".kpi-value").innerText()) === want, await tileByName("KPI").innerText());

  // --- gráfico ---
  await page.getByRole("button", { name: "+ Gráfico", exact: true }).click();
  await page.getByRole("dialog").waitFor();
  await page.getByLabel("Título do gráfico").fill("Média por grupo");
  await setSql(`SELECT "group", round(avg(score), 2) AS media FROM e2e_dash GROUP BY 1 ORDER BY 1`);
  await page.getByRole("dialog").locator("canvas, svg").first().waitFor({ timeout: 15000 });
  await closeModal();
  await tileByName("Gráfico").locator("canvas, svg").first().waitFor({ timeout: 15000 });
  check("gráfico: desenhado dentro do tile, com o título no cabeçalho", (await tileByName("Gráfico").locator(".tile-title").innerText()) === "Média por grupo");

  // --- texto + XSS ---
  await page.getByRole("button", { name: "+ Texto", exact: true }).click();
  await page.getByRole("dialog").waitFor();
  await page.getByLabel("Texto do bloco (Markdown)").fill(`# Notas\n\nTexto com **negrito** e ${EVIL}.`);
  await closeModal();
  const txt = tileByName("Texto");
  check("texto: Markdown renderizado", (await txt.locator("h2").innerText()) === "Notas" && (await txt.locator("strong").count()) === 1);
  check("texto: HTML aparece como texto literal e nada foi executado", (await txt.locator("img").count()) === 0 && (await txt.innerText()).includes(EVIL) && (await page.evaluate(() => window.__xss)) === undefined);
  await saved();
  let d = await server();
  check("servidor tem os 3 tiles e o título", d.tiles.length === 3 && d.title === "E2E Painel de vendas", JSON.stringify(d.tiles.map((t) => t.type)));
  await shot("d1-edicao");

  // --- arrastar o KPI para a direita e redimensionar o gráfico ---
  const kpi0 = d.tiles.find((t) => t.type === "kpi").layout;
  await drag(tileByName("KPI").locator(".tile-head"), 520, 0);
  await saved();
  d = await server();
  const kpi1 = d.tiles.find((t) => t.type === "kpi").layout;
  check("arrastar o KPI muda a posição e é salvo no servidor", kpi1.x > kpi0.x || kpi1.y !== kpi0.y, `${JSON.stringify(kpi0)} -> ${JSON.stringify(kpi1)}`);
  const chart0 = d.tiles.find((t) => t.type === "chart").layout;
  const handle = tileByName("Gráfico").locator(".react-resizable-handle-se");
  await tileByName("Gráfico").hover();
  await drag(handle, -160, 120);
  await saved();
  d = await server();
  const chart1 = d.tiles.find((t) => t.type === "chart").layout;
  check("redimensionar o gráfico muda largura/altura e é salvo", chart1.w !== chart0.w || chart1.h !== chart0.h, `${JSON.stringify(chart0)} -> ${JSON.stringify(chart1)}`);
  check("nenhum tile sai da grade de 12 colunas nem se sobrepõe", d.tiles.every((t) => t.layout.x + t.layout.w <= 12) &&
    d.tiles.every((a, i) => d.tiles.every((b, j) => i >= j || a.layout.x + a.layout.w <= b.layout.x || b.layout.x + b.layout.w <= a.layout.x || a.layout.y + a.layout.h <= b.layout.y || b.layout.y + b.layout.h <= a.layout.y)));
  await shot("d2-arrastado");

  // --- recarregar: modo leitura, mesmos valores e posições ---
  const before = d.tiles.map((t) => [t.id, t.layout]);
  await page.reload();
  await page.locator(".kpi-value").waitFor({ timeout: 20000 });
  check("recarregar: abre em modo leitura com título como h1", (await page.locator(".report-h1").innerText()) === "E2E Painel de vendas" && (await page.getByRole("button", { name: "Editar" }).isVisible()));
  check("recarregar: KPI com o mesmo valor", (await page.locator(".kpi-value").innerText()) === want);
  await tileByName("Gráfico").locator("canvas, svg").first().waitFor({ timeout: 15000 });
  check("recarregar: gráfico desenhado", true);
  check("modo leitura: sem botões de editar/excluir nos tiles e sem alças de redimensionar", (await page.locator(".tile-head button").count()) === 0 && (await page.locator(".react-resizable-handle:visible").count()) === 0);
  const same = JSON.stringify((await server()).tiles.map((t) => [t.id, t.layout])) === JSON.stringify(before);
  check("abrir em modo leitura não altera nem 'compacta' as posições salvas", same);
  await page.waitForTimeout(800); // a grade anima ao medir a largura; só depois mede a posição de referência
  const b1 = await tileByName("KPI").boundingBox();
  await drag(tileByName("KPI").locator(".tile-head").first(), 200, 100);
  await page.waitForTimeout(500);
  const b2 = await tileByName("KPI").boundingBox();
  check("modo leitura: arrastar não move nada", Math.abs(b1.x - b2.x) < 2 && Math.abs(b1.y - b2.y) < 2, `${JSON.stringify(b1)} -> ${JSON.stringify(b2)}`);
  check("modo leitura: arrastar não altera o servidor", JSON.stringify((await server()).tiles.map((t) => [t.id, t.layout])) === JSON.stringify(before));
  await shot("d3-leitura");

  // --- tela estreita: empilha em coluna única ---
  await page.setViewportSize({ width: 420, height: 900 });
  await page.waitForTimeout(600);
  const xs = await page.locator(".dash-stack .tile").evaluateAll((els) => els.map((e) => Math.round(e.getBoundingClientRect().left)));
  check("tela estreita: 3 tiles empilhados na mesma coluna", xs.length === 3 && new Set(xs).size === 1, xs.join(","));
  check("tela estreita: sem rolagem horizontal da página", await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1));
  await shot("d4-estreito");
  await page.setViewportSize({ width: 1360, height: 1250 });

  // --- excluir tile (com confirmação) e o dashboard ---
  await page.getByRole("button", { name: "Editar" }).click();
  s.onNextDialog((dlg) => dlg.dismiss());
  await tileByName("Texto").getByRole("button", { name: /Excluir tile/ }).click();
  check("cancelar a confirmação mantém o tile", (await page.getByRole("region", { name: /^Tile/ }).count()) === 3);
  s.onNextDialog((dlg) => dlg.accept());
  await tileByName("Texto").getByRole("button", { name: /Excluir tile/ }).click();
  await saved();
  check("confirmar exclui o tile e o servidor reflete", (await server()).tiles.length === 2);

  // conflito: outra aba salva primeiro -> esta NÃO sobrescreve
  const id = dashId(), cur = await server();
  await fetch(`${BASE}/api/dashboards/${id}`, { method: "PUT", headers: { "content-type": "application/json" }, body: JSON.stringify({ title: "E2E da outra aba", tiles: cur.tiles, version: cur.version }) });
  await page.locator(".title-input").fill("E2E esta aba");
  await page.getByText(/salvo em outra aba/).waitFor({ timeout: 15000 });
  check("conflito: aviso claro e o trabalho da outra aba NÃO foi sobrescrito", (await server()).title === "E2E da outra aba");

  await page.getByRole("link", { name: "← Dashboards" }).click();
  await page.locator(".report-row").first().waitFor();
  check("lista mostra título e nº de tiles", (await page.locator(".report-row", { hasText: "E2E da outra aba" }).innerText()).includes("2 tiles"));
  s.onNextDialog((dlg) => dlg.accept());
  await page.locator(".report-row", { hasText: "E2E da outra aba" }).getByRole("button", { name: /Excluir/ }).click();
  await page.waitForFunction(() => !document.body.innerText.includes("E2E da outra aba"));
  check("excluir remove o dashboard da lista", true);
} catch (e) {
  s.failures.push(`exceção: ${e.message}`);
  console.log(`FAIL exceção: ${e.message}`);
  await shot("erro");
}
await s.finish(async () => {
  for (const ds of (await api.list("/datasets")).filter((x) => x.name === name)) await api.del(`/datasets/${ds.id}`);
  for (const d of (await api.list("/dashboards")).filter((x) => x.title.startsWith("E2E"))) await api.del(`/dashboards/${d.id}`);
});
