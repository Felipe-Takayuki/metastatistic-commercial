/**
 * E2E do tile de análise estatística no dashboard (motor JASP): escolher dataset/variáveis no diálogo, ver o resultado no tile
 * (números do R), persistir, reabrir, e conviver com KPI/gráfico na mesma grade.
 *   npm run e2e:dash-analysis        (E2E_SHOTS=/tmp/shots para capturas)
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { api, BASE, session } from "./lib.mjs";

const CSV = readFileSync(join(dirname(fileURLToPath(import.meta.url)), "../../api/tests/fixtures/ttest.csv"), "utf8");
// o passo "dataset excluído" provoca de propósito um 404 (dataset) e um 422 (análise) no navegador
const s = await session({ allowConsole: { "status of 404": 3, "status of 422": 3 } });
const { page, check, shot } = s;
const dashId = () => page.url().match(/#\/dashboards\/([0-9a-f]{32})/)?.[1];
const saved = () => page.locator(".save-status.saved").waitFor({ timeout: 15000 });
const server = async () => (await (await fetch(`${BASE}/api/dashboards/${dashId()}`)).json());
const tile = () => page.getByRole("region", { name: /^Tile Análise/ });

const name = "e2e-dan.csv";
try {
  await page.goto(BASE);
  await page.setInputFiles("input[type=file]", { name, mimeType: "text/csv", buffer: Buffer.from(CSV) });
  await page.getByRole("heading", { name }).waitFor();
  await page.getByRole("link", { name: "Dashboards" }).click();
  await page.getByRole("button", { name: "Novo dashboard" }).click();
  await page.waitForURL(/#\/dashboards\/[0-9a-f]{32}/);
  await page.locator(".title-input").fill("E2E Análise no dashboard");

  await page.getByRole("button", { name: "+ Análise", exact: true }).click();
  const dlg = page.getByRole("dialog");
  await dlg.waitFor();
  await dlg.getByLabel(/^Dataset/).selectOption({ label: name });
  check("diálogo: teste t com as variáveis escolhidas por padrão", (await dlg.getByLabel(/^Variável de agrupamento/).inputValue()) === "group");
  check("diálogo: avisa que filtros não se aplicam à análise", (await dlg.getByText(/filtros do dashboard não se aplicam/i).count()) === 1);
  await dlg.getByRole("button", { name: "Executar análise" }).click();
  await dlg.locator("table.apa-table").first().waitFor({ timeout: 90000 });
  const dtxt = (await dlg.locator("table.apa-table").first().innerText()).replace(/\s+/g, " ");
  check("diálogo: resultado do teste t (t=-2.628, gl=78)", ["-2.628", "78.000"].every((x) => dtxt.includes(x)), dtxt);
  await dlg.getByRole("button", { name: "Concluir" }).click();
  await dlg.waitFor({ state: "detached" });

  await tile().locator("table.apa-table").first().waitFor({ timeout: 90000 });
  const txt = (await tile().innerText()).replace(/\s+/g, " ");
  check("tile: resultado igual ao R (Student t=-2.628, df=78.000, p=.010)", ["-2.628", "78.000", ".010"].every((x) => txt.includes(x)), txt.slice(0, 300));
  check("tile: cabeçalho traz o nome da análise", (await tile().locator(".tile-title").innerText()).includes("Teste t"));

  // convive com um KPI na mesma grade
  await page.getByRole("button", { name: "+ KPI", exact: true }).click();
  await page.getByRole("dialog").waitFor();
  await page.getByRole("dialog").getByRole("button", { name: "Concluir" }).click();
  await page.getByRole("dialog").waitFor({ state: "detached" });
  await saved();
  let d = await server();
  const a = d.tiles.find((t) => t.type === "analysis");
  check("servidor guarda a definição (análise, dataset e opções), não o resultado", !!a && a.analysis === "TTestIndependentSamples" && a.dataset_id.length === 32 && a.options.dependent?.[0] === "score" && !("results" in a), JSON.stringify(a)?.slice(0, 200));
  check("os 2 tiles não se sobrepõem", d.tiles.length === 2 && (() => { const [p, q] = d.tiles.map((t) => t.layout); return p.y + p.h <= q.y || q.y + q.h <= p.y || p.x + p.w <= q.x || q.x + q.w <= p.x; })());
  await shot("a1-edicao");

  await page.reload();
  await tile().locator("table.apa-table").first().waitFor({ timeout: 90000 });
  check("recarregar: o tile reexecuta e mostra o mesmo resultado", (await tile().innerText()).includes("-2.628"));
  check("modo leitura: sem botões de edição no tile", (await tile().getByRole("button").count()) === 0);
  await shot("a2-leitura");

  // dataset excluído: o tile avisa em vez de quebrar
  for (const ds of (await api.list("/datasets")).filter((x) => x.name === name)) await api.del(`/datasets/${ds.id}`);
  await page.reload();
  await page.locator(".tile").first().waitFor({ timeout: 20000 });
  await page.waitForTimeout(1500);
  const after = (await tile().innerText()).replace(/\s+/g, " ");
  console.log("  (mensagem do tile com dataset excluído:", JSON.stringify(after.slice(0, 160)), ")");
  check("dataset excluído: o tile mostra um erro legível (sem tabela, sem travar a página)", (await tile().locator("table.apa-table").count()) === 0 && /dataset|not found|erro|não/i.test(after), after.slice(0, 200));
} catch (e) {
  s.failures.push(`exceção: ${e.message}`);
  console.log(`FAIL exceção: ${e.message}`);
  await shot("erro");
}
await s.finish(async () => {
  for (const ds of (await api.list("/datasets")).filter((x) => x.name === name)) await api.del(`/datasets/${ds.id}`);
  for (const dd of (await api.list("/dashboards")).filter((x) => x.title.startsWith("E2E"))) await api.del(`/dashboards/${dd.id}`);
});
