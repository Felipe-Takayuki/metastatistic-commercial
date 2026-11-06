/**
 * E2E das transformações (aba "Transformar"): média entre colunas, filtro, fórmula com erro apontando o passo,
 * reordenar, ver SQL, salvar como dataset e reabrir a receita. Só usa SQL (não precisa do motor R).
 *   npm run e2e:transform      (E2E_URL=... para outra pilha; E2E_SHOTS=/dir para capturas)
 */
import { BASE, SHOTS, api, session } from "./lib.mjs";

const s = await session({ allowConsole: { "status of 422": 6 } });
const { page, check, shot } = s;
const NAME = "e2e-notas.csv", SAVED = "e2e-com-media";
const CSV = "id,grupo,nota1,nota2,nota3\n1,A,7,8,9\n2,A,5,,6\n3,B,10,10,10\n4,B,,4,6\n5,A,6,7,8\n6,B,3,5,\n";
const created = [];
const has = async (loc) => (await loc.count()) > 0;
const summary = () => page.getByTestId("tf-summary");
const addStep = async (label) => { await page.getByLabel("Adicionar passo").selectOption({ label }); await page.getByRole("dialog").waitFor(); };
const confirm = async (name = "Adicionar passo") => { await page.getByRole("dialog").getByRole("button", { name, exact: true }).click(); await page.getByRole("dialog").waitFor({ state: "detached" }); };
const cell = async (r, c) => (await page.locator("table").first().locator("tbody tr").nth(r).locator("td").nth(c).innerText()).trim();
const box = (group, name) => group.locator("label.check").filter({ hasText: new RegExp(`^\\s*${name}\\s`) }).getByRole("checkbox");
const stepTexts = async () => page.locator(".step:not(.origin) .step-text").allInnerTexts();

try {
  const up = await fetch(`${BASE}/api/datasets`, { method: "POST", body: (() => { const f = new FormData(); f.append("file", new Blob([CSV], { type: "text/csv" }), NAME); return f; })() });
  const ds = await up.json();
  created.push(ds.id);
  await page.goto(BASE);
  await page.locator(".ds-item", { hasText: NAME }).click();
  await page.getByRole("tab", { name: "Transformar" }).click();
  await summary().waitFor();
  check("sem passos: o resultado é a origem (6 linhas, 5 colunas)", (await summary().innerText()).startsWith("6 linhas · 5 colunas"));

  // --- 1) média entre colunas ---
  await addStep("Média, soma, mín. ou máx. entre colunas");
  const dlg = page.getByRole("dialog");
  check("o formulário só oferece colunas numéricas e sugere um nome livre", (await dlg.getByLabel("Nome da nova coluna").inputValue()) === "media");
  const group = dlg.getByRole("group", { name: "Colunas numéricas" });
  await box(group, "id").uncheck();
  check("sem 2 colunas marcadas o botão fica desabilitado e diz o que falta", (await dlg.getByRole("button", { name: "Adicionar passo", exact: true }).isDisabled()) && (await dlg.getByRole("status").innerText()).includes("2 colunas"));
  for (const c of ["nota1", "nota2", "nota3"]) await box(group, c).check();
  await confirm();
  await page.waitForFunction(() => document.querySelector('[data-testid="tf-summary"]')?.textContent?.includes("6 colunas"));
  check("nova coluna: 6 colunas", (await summary().innerText()).includes("6 linhas · 6 colunas"));
  check("(7+8+9)/3 = 8 na 1ª linha; vazios são ignorados: (5+6)/2 = 5,5 na 2ª", (await cell(0, 6)) === "8" && (await cell(1, 6)).replace(",", ".") === "5.5", `${await cell(0, 6)} | ${await cell(1, 6)}`);
  check("o passo aparece descrito em português", (await stepTexts())[0] === '"media" = média de nota1, nota2, nota3');

  // --- 2) filtro ---
  await addStep("Filtrar linhas");
  await dlg.getByLabel("Coluna da condição 1").selectOption("grupo");
  await dlg.getByLabel("Valor da condição 1").fill("A");
  await confirm();
  await page.waitForFunction(() => document.querySelector('[data-testid="tf-summary"]')?.textContent?.startsWith("3 linhas"));
  check("filtro grupo = A deixa 3 linhas", true);

  // --- 3) fórmula com coluna inexistente: o erro aponta o passo e a prévia não some ---
  await addStep("Fórmula livre");
  await dlg.getByLabel("Nome da nova coluna").fill("dobro");
  await dlg.getByLabel("Fórmula").fill("nota9 * 2");
  await confirm();
  await page.getByRole("alert").waitFor();
  const err = await page.getByRole("alert").first().innerText();
  check("erro aponta o passo e a coluna (\"Passo 3 (formula): coluna não encontrada…\")", err.startsWith("Passo 3 (formula)") && err.includes("nota9"), err);
  check("o passo com erro fica destacado e o botão Salvar bloqueado", (await has(page.locator(".step.failing"))) && (await page.getByRole("button", { name: "Salvar como dataset" }).isDisabled()));
  await shot("tf-erro");
  await page.getByLabel("Editar passo 3").click();
  await page.getByRole("dialog").getByLabel("Fórmula").fill("nota1 * 2");
  await confirm("Aplicar");
  await page.waitForFunction(() => !document.querySelector(".step.failing") && document.querySelector('[data-testid="tf-summary"]'));
  check("corrigido o passo, o erro some", !(await has(page.locator(".step.failing"))) && (await summary().innerText()).includes("3 linhas · 7 colunas"));
  check("fórmula: nota1 * 2 = 14 na 1ª linha", (await cell(0, 7)) === "14", await cell(0, 7));

  // --- 4) reordenar: filtrar DEPOIS de criar a coluna dá o mesmo resultado; desce o filtro ---
  await page.getByLabel("Descer passo 2").click();
  check("descer o passo troca a ordem na lista", (await stepTexts())[1].startsWith('"dobro"') && (await stepTexts())[2].startsWith("Filtrar"));
  check("e o resultado continua com 3 linhas", (await summary().innerText()).includes("3 linhas"));

  // --- 5) ver SQL ---
  await page.getByRole("button", { name: "Ver SQL" }).click();
  const sql = await page.getByLabel("SQL gerado").innerText();
  check("Ver SQL mostra uma etapa (CTE) por passo", sql.includes("__s0") && sql.includes("__s3") && sql.includes("list_avg"), sql.slice(0, 120));
  await page.getByRole("button", { name: "Ocultar SQL" }).click();

  // --- 6) salvar como dataset ---
  await page.getByLabel("Nome do novo dataset").fill(SAVED);
  await page.getByRole("button", { name: "Salvar como dataset" }).click();
  await page.getByRole("heading", { name: SAVED }).waitFor();
  const list = await api.list("/datasets");
  const saved = list.find((d) => d.name === SAVED);
  if (saved) created.push(saved.id);
  check("o dataset novo aparece com 3 linhas e as 7 colunas", !!saved && saved.n_rows === 3 && saved.columns.length === 7, JSON.stringify(saved && [saved.n_rows, saved.columns.length]));
  check("e já abre na aba Dados", await has(page.getByRole("heading", { name: "Colunas" })));
  await shot("tf-salvo");

  // --- 7) reabrir a receita a partir do dataset salvo ---
  await page.getByRole("tab", { name: "Transformar" }).click();
  await page.getByRole("button", { name: "Reabrir receita" }).waitFor();
  check("dataset criado por receita oferece reabri-la", (await page.getByText("criado por uma receita de 3 passos").count()) === 1);
  await page.getByRole("button", { name: "Reabrir receita" }).click();
  await page.waitForFunction(() => document.querySelectorAll(".step:not(.origin)").length === 3);
  check("os 3 passos voltam, sobre a origem original", (await stepTexts()).length === 3 && (await page.locator(".step.origin").innerText()).includes(NAME));
  check("e o resultado é o mesmo (3 linhas)", (await summary().innerText()).includes("3 linhas"));

  // --- 8) o rascunho sobrevive à troca de aba ---
  await page.getByRole("tab", { name: "Dados" }).click();
  await page.getByRole("tab", { name: "Transformar" }).click();
  check("trocar de aba não perde os passos", (await stepTexts()).length === 3);
  await page.getByRole("button", { name: "Desfazer todos os passos" }).click();
  check("desfazer volta à origem", (await stepTexts()).length === 0);

  // --- 9) por grupo e janela (8.3) ---
  const groupBy = (g) => box(page.getByRole("dialog").getByRole("group", { name: "Agrupar por" }), g);
  await addStep("Média, soma… do grupo, repetida em cada linha");
  await page.getByRole("dialog").getByLabel("Coluna", { exact: true }).selectOption("nota1");
  await groupBy("grupo").check();
  await confirm();
  await page.waitForFunction(() => document.querySelector('[data-testid="tf-summary"]')?.textContent?.includes("6 linhas · 6 colunas"));
  check("média do grupo repetida em cada linha: A = (7+5+6)/3 = 6; B = (10+3)/2 = 6,5 (vazio ignorado)", (await cell(0, 6)) === "6" && (await cell(2, 6)) === "6.5" && (await cell(3, 6)) === "6.5", `${await cell(0, 6)} ${await cell(2, 6)} ${await cell(3, 6)}`);
  check("o número de linhas não muda (6)", (await summary().innerText()).startsWith("6 linhas"));
  await addStep("Posição no ranking");
  await page.getByRole("dialog").getByLabel("Coluna a classificar").selectOption("nota1");
  await groupBy("grupo").check();
  await confirm();
  await page.waitForFunction(() => document.querySelector('[data-testid="tf-summary"]')?.textContent?.includes("7 colunas"));
  check("ranking por grupo: 7 = 1º e 5 = 3º no grupo A; vazio fica sem posição", (await cell(0, 7)) === "1" && (await cell(1, 7)) === "3" && (await cell(3, 7)) === "—", `${await cell(0, 7)} ${await cell(1, 7)} ${await cell(3, 7)}`);
  await addStep("Acumulado ou média móvel");
  await page.getByRole("dialog").getByLabel("Coluna", { exact: true }).selectOption("nota3");
  await page.getByRole("dialog").getByRole("button", { name: "+ critério" }).click();
  await groupBy("grupo").check();
  await confirm();
  await page.waitForFunction(() => document.querySelector('[data-testid="tf-summary"]')?.textContent?.includes("8 colunas"));
  check("soma acumulada por grupo na ordem do id: A = 9, 15, 23", (await cell(0, 8)) === "9" && (await cell(1, 8)) === "15" && (await cell(4, 8)) === "23", `${await cell(0, 8)} ${await cell(1, 8)} ${await cell(4, 8)}`);
  check("a ordem original das linhas é preservada (ids 1 a 6)", (await Promise.all([0, 1, 2, 3, 4, 5].map((r) => cell(r, 1)))).join(",") === "1,2,3,4,5,6");
  check("os 3 passos aparecem descritos em português", (await stepTexts()).join(" | ") === '"media_grupo" = média de nota1 por grupo | "posicao" = posição de nota1 (maior = 1) por grupo | "acumulado" = soma acumulada de nota3, ordem id ↑ por grupo');
  await shot("tf-grupo");
} catch (e) {
  s.failures.push(`exceção: ${e.message}`);
  console.log(`FAIL exceção: ${e.message}`);
  await shot("tf-excecao");
}
await s.finish(async () => {
  for (const id of created) await api.del(`/datasets/${id}`);
});
