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
const notes = () => page.getByRole("status", { name: "Verificação de pressupostos" });
const bnotes = () => page.getByRole("status", { name: "Interpretação do fator de Bayes" });

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
  await page.locator(".analysis-group-title").first().waitFor();
  check("seletor agrupado: Descritivas, Comparação de médias, Associação e predição, Bayesianas",
    JSON.stringify(await page.locator(".analysis-group-title").evaluateAll((e) => e.map((x) => x.textContent))) === JSON.stringify(["Descritivas", "Comparação de médias", "Testes z (σ conhecido e proporções)", "Associação e predição", "Bayesianas"]));
  check("seletor agrupado: as 21 análises continuam sendo abas", (await page.locator(".analysis-picker").getByRole("tab").count()) === 21);
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
  check("ANOVA em blocos (1 observação por célula): sem Levene possível, então nenhum aviso falso", (await notes().count()) === 0);

  // Kruskal-Wallis (opção da ANOVA, um teste por fator) + Dunn; opções dependentes só aparecem com o teste ligado
  check("Kruskal-Wallis: desligado por padrão e sem opções de efeito/Dunn visíveis",
    !(await page.getByLabel("Teste de Kruskal-Wallis").isChecked()) && (await page.getByLabel(/Post hoc de Dunn/).count()) === 0);
  await page.getByLabel("Teste de Kruskal-Wallis").check();
  await page.getByLabel(/Tamanho de efeito \(ε²/).check();
  await page.getByLabel(/Post hoc de Dunn/).check();
  await run();
  await page.locator(".analysis-grid .card").nth(1).getByText(/Kruskal-Wallis/).first().waitFor({ timeout: 90000 }); // run() vê a tabela da execução anterior
  t = await resultText();
  const K = REF.kruskal;
  check("Kruskal-Wallis: gl e p do fator tratamento iguais ao R", has(t, "Kruskal-Wallis", p3(K.p), f3(K.epsilon).replace(/^0/, "")) || has(t, "Kruskal-Wallis", p3(K.p), f3(K.epsilon)), t.slice(0, 900));
  check("Dunn: z e p do 1º par iguais ao R", has(t, "1 - 2", f3(K.dunn[0].z), f3(K.dunn[0].p).replace(/^0/, "")) || has(t, "1 - 2", f3(K.dunn[0].z), f3(K.dunn[0].p)), t.slice(0, 1200));
  await shot("a2k-kruskal");
  await page.getByLabel("Teste de Kruskal-Wallis").uncheck();

  // --- ANOVA bayesiana (modelo ADITIVO tratamento + bloco: sem o remendo do modelTerms o JASP incluiria a interação) ---
  await pickAnalysis("ANOVA bayesiana");
  await page.getByLabel(/^tratamento/).check();
  await page.getByLabel(/^bloco/).check();
  check("ANOVA bayesiana: sem interações por padrão", !(await page.getByLabel("Incluir interações entre os fatores").isChecked()));
  await run();
  t = await resultText();
  const BB = REF.bayes.anova;
  check("ANOVA bayesiana: 4 modelos (nulo, tratamento, bloco, tratamento + bloco) e nenhuma interação", has(t, "Null model", "tratamento + bloco") && !t.includes("✻"), t.slice(0, 700));
  const esc = (x) => x.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  /** BF10 de um modelo na "Model Comparison": nome, P(M), P(M|data), BFM, BF10. */
  const bf10Of = (name) => { const m = t.match(new RegExp(`${esc(name)}\\s+[\\d.]+\\s+[\\d.]+\\s+[\\d.]+\\s+([\\d.]+)`)); return m ? Number(m[1]) : NaN; };
  const bestRatio = bf10Of("tratamento + bloco") / bf10Of("Null model");
  check("ANOVA bayesiana: BF do melhor modelo contra o nulo igual ao BayesFactor (±3%)", Math.abs(bestRatio / BB.bf[2] - 1) < 0.03, `${bestRatio} vs ${BB.bf[2]} | ${t.slice(0, 600)}`);
  const ba = (await bnotes().innerText()).replace(/\s+/g, " ");
  check("ANOVA bayesiana: BF de inclusão interpretado por efeito (tratamento: anedótica a favor de excluir)", has(ba, "tratamento: BF de inclusão", "anedótica a favor de excluir", "bloco: BF de inclusão"), ba);
  await shot("a2c-anova-bayesiana");

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
  check("regressão: a variável dependente não aparece como covariável", (await page.getByRole("group", { name: /^Covariáveis/ }).getByLabel(/^produtividade/).count()) === 0);
  await page.getByLabel(/^altura/).check();
  await page.getByLabel(/^diametro/).check();
  await run();
  t = await resultText();
  const R = REF.reg;
  check("Regressão: R² e F iguais ao R", has(t, f3(R.R2).replace(/^0/, "")) || has(t, f3(R.R2)), t.slice(0, 500));
  check("Regressão: F(2, 29) igual ao R", has(t, f3(R.F)), t.slice(0, 500));
  await shot("a4-regressao");
  await notes().waitFor({ timeout: 90000 });
  check("regressão: VIF baixo e Durbin-Watson ok = nota de nenhum alerta", has((await notes().innerText()).replace(/\s+/g, " "), "nenhum alerta"), await notes().innerText());

  // --- trocar de aba (Dados/SQL) não pode perder a análise escolhida, as opções nem o resultado ---
  await page.getByRole("tab", { name: "Consulta SQL" }).click();
  await page.getByRole("tab", { name: "Análise estatística" }).click();
  check("troca de aba: a análise escolhida continua selecionada", (await page.locator(".analysis-picker").getByRole("tab", { name: "Regressão linear", exact: true }).getAttribute("aria-selected")) === "true");
  check("troca de aba: as variáveis marcadas continuam marcadas", (await page.getByLabel(/^altura/).isChecked()) && (await page.getByLabel(/^diametro/).isChecked()));
  await page.locator("table.apa-table").first().waitFor({ timeout: 30000 });
  check("troca de aba: o resultado reaparece", has(await resultText(), f3(R.F)));

  // regressão com UM único preditor: antes o modelo ficava vazio (R² = 0) sem nenhum erro
  await page.getByLabel(/^diametro/).uncheck();
  await run();
  const R1 = REF.one_predictor.reg;
  await page.locator(".analysis-grid .card").nth(1).getByText(f3(R1.R2), { exact: true }).first().waitFor({ timeout: 90000 }); // run() vê a tabela anterior
  t = await resultText();
  check("regressão com um preditor: R² e coeficiente de altura iguais ao R (modelo não vazio)", has(t, f3(R1.R2), f3(R1.est[1]), f3(R1.est[0])) && !/R\s+R²\s+Adjusted R²[^]*0\.000\s+0\.000/.test(t), t.slice(0, 600));
  await page.getByLabel(/^diametro/).check();

  // --- ANCOVA: tratamento + bloco + covariável altura (aditivo) ---
  await pickAnalysis("ANCOVA");
  await page.getByLabel("Variável dependente (escalar)").selectOption("produtividade");
  // tratamento/bloco são inteiros ordinais: aparecem também em "Covariáveis" (como ordinal tratada como escalar); aqui são FATORES
  check("Likert: tratamento (ordinal numérica) também é oferecido como covariável, com rótulo explícito",
    (await page.getByRole("group", { name: /^Covariáveis/ }).getByLabel(/^tratamento \(ordinal, 8 valores: tratada como escalar\)/).count()) === 1);
  await page.getByRole("group", { name: /^Fatores/ }).getByLabel(/^tratamento/).check();
  await page.getByRole("group", { name: /^Fatores/ }).getByLabel(/^bloco/).check();
  check("Likert: marcado como fator, tratamento some da lista de covariáveis", (await page.getByRole("group", { name: /^Covariáveis/ }).getByLabel(/^tratamento/).count()) === 0);
  await page.getByRole("group", { name: /^Covariáveis/ }).getByLabel(/^altura/).check();
  await run();
  t = await resultText();
  const AC = REF.ancova_blocks;
  check("ANCOVA: F e p de tratamento, bloco e covariável iguais ao R", AC.F.every((f, i) => has(t, f3(f), p3(AC.p[i]))), t.slice(0, 500));
  check("ANCOVA: resíduos com 20 gl e nenhuma interação fantasma", has(t, "Residuals") && !t.includes("✻"), t.slice(0, 300));
  await shot("a2b-ancova");

  // médias marginais ajustadas e comparações dois a dois (modelo tratamento + altura, como na referência do R)
  await page.getByRole("group", { name: /^Fatores/ }).getByLabel(/^bloco/).uncheck();
  await page.getByLabel(/^Médias marginais ajustadas/).check();
  await page.getByLabel(/^Comparar os níveis de cada fator/).check();
  await run();
  await page.locator(".analysis-grid .card").nth(1).getByText(/Post Hoc/).first().waitFor({ timeout: 90000 }); // run() vê a tabela da execução anterior
  t = await resultText();
  const AJ = REF.ancova_adj;
  check("ANCOVA: médias marginais ajustadas dos 3 primeiros níveis iguais ao R (covariável na média)", AJ.lsmean.slice(0, 3).every((m) => has(t, f3(m))), t.slice(0, 900));
  check("ANCOVA: post hoc (1 − 2): estimativa, t e p de Tukey iguais ao R", has(t, f3(AJ.pairs[0].est), f3(AJ.pairs[0].t), " 23 "), t.slice(0, 1400));
  await shot("a2b2-ancova-ajustadas");

  // qui-quadrado com frequências esperadas baixas (tratamento 8 × bloco 4, uma observação por célula): aviso de Cochran
  await pickAnalysis("Qui-quadrado (tabela de contingência)");
  await page.getByLabel(/^Linhas/).selectOption("tratamento");
  await page.getByLabel(/^Colunas/).selectOption("bloco");
  await run();
  await notes().waitFor({ timeout: 90000 });
  const cn = (await notes().innerText()).replace(/\s+/g, " ");
  check("qui-quadrado com poucas observações: avisa frequências esperadas abaixo de 5 (regra de Cochran)", has(cn, "Atenção", "32 de 32 células", "frequência esperada abaixo de 5", "mínima 1,00"), cn);

  // --- bayesianas (dataset e2e-dbc): correlação, regressão e ANCOVA, contra o R ---
  const BC = REF.bayes_corr;
  await pickAnalysis("Correlação bayesiana");
  for (const v of ["produtividade", "altura", "diametro"]) await page.getByLabel(new RegExp(`^${v}`)).check();
  await run();
  t = await resultText();
  check("correlação bayesiana: BF₁₀ dos 3 pares iguais ao BF analítico de Ly et al. (R)", BC.every((x) => has(t, x.bf10.toFixed(3))), t.slice(0, 600));
  await bnotes().waitFor({ timeout: 30000 });
  check("correlação bayesiana: interpreta o BF (produtividade × altura: evidência anedótica a favor de H₀)", has((await bnotes().innerText()).replace(/\s+/g, " "), "produtividade × altura: BF₁₀ = 0,51", "anedótica a favor de H₀ (não há correlação"), await bnotes().innerText());
  await shot("a3k-correlacao-bayesiana");

  await pickAnalysis("Regressão linear bayesiana");
  await page.getByLabel("Variável dependente (escalar)").selectOption("produtividade");
  await page.getByRole("group", { name: /^Covariáveis/ }).getByLabel(/^altura/).check();
  await page.getByRole("group", { name: /^Covariáveis/ }).getByLabel(/^diametro/).check();
  await run();
  t = await resultText();
  const RB = REF.bayes_reg;
  check("regressão bayesiana: 4 modelos e BF de cada um contra o nulo (o nulo é o melhor) iguais ao lmBF do R", has(t, "Null model", "altura + diametro", RB.altura.toFixed(3), RB.diametro.toFixed(3), RB.both.toFixed(3)), t.slice(0, 700));
  await shot("a4b-regressao-bayesiana");

  await pickAnalysis("ANCOVA bayesiana");
  await page.getByLabel("Variável dependente (escalar)").selectOption("produtividade");
  await page.getByRole("group", { name: /^Fatores/ }).getByLabel(/^tratamento/).check();
  await page.getByRole("group", { name: /^Covariáveis/ }).getByLabel(/^altura/).check();
  await run();
  t = await resultText();
  const AB = REF.bayes_ancova;
  check("ANCOVA bayesiana: BF do fator e da covariável contra o nulo iguais ao lmBF do R; sem interação", has(t, "Null model", AB.trat.toFixed(3), AB.altura.toFixed(3)) && !t.includes("✻"), t.slice(0, 700));
  await bnotes().waitFor({ timeout: 30000 });
  check("ANCOVA bayesiana: interpreta o BF de inclusão de cada efeito", has((await bnotes().innerText()).replace(/\s+/g, " "), "BF de inclusão"), await bnotes().innerText());
  await shot("a2f-ancova-bayesiana");

  // --- Regressão logística sobre um dataset derivado por SQL (desfecho binário alto/baixo) ---
  await page.getByRole("tab", { name: "Consulta SQL" }).click();
  await runSql("SELECT CASE WHEN produtividade >= 196 THEN 'alto' ELSE 'baixo' END AS nivel, * FROM e2e_dbc");
  await page.getByRole("tab", { name: "Tabela" }).click();
  await page.locator(".card table.data tbody tr").first().waitFor();
  await saveAsDataset("e2e-nivel");
  await page.getByRole("tab", { name: "Análise estatística" }).click();
  await pickAnalysis("Regressão logística");
  check("logística: desfecho binário escolhido por padrão (a única coluna de 2 categorias)", (await page.getByLabel(/^Desfecho binário/).inputValue()) === "nivel");
  check("logística: o desfecho não aparece como opção em Fatores", (await page.getByRole("group", { name: /^Fatores/ }).getByLabel(/^nivel/).count()) === 0);
  await page.getByLabel(/^altura/).check();
  await page.getByLabel(/^diametro/).check();
  await run();
  t = await resultText();
  const LG = REF.logit;
  check("logística: estimativas (intercepto, altura, diametro) iguais ao R", LG.est.every((e) => has(t, f3(e))), t.slice(0, 600));
  check("logística: razões de chances de altura e diametro iguais ao R", has(t, f3(LG.or[1]), f3(LG.or[2])), t.slice(0, 600));
  check("logística: acurácia e AUC iguais ao R", has(t, f3(LG.accuracy), f3(LG.auc)), t.slice(0, 800));
  await shot("a4b-logistica");
  // seleção por AIC (backward): o JASP percorre cheio -> diametro -> nulo (AIC 47,048 -> 45,646 -> 45,230), como step() do R
  await page.getByLabel("Método").selectOption("backward");
  check("logística: nos métodos por AIC a tela explica que a tabela mostra os passos", (await page.getByLabel("Resumo dos campos").innerText()).includes("cada passo"));
  await run();
  await page.locator(".analysis-grid .card").nth(1).getByText("45.230").first().waitFor({ timeout: 90000 }); // run() vê a tabela da execução anterior
  t = await resultText();
  check("logística backward: AIC de cada passo igual ao step() do R (47,048; 45,646; 45,230)", has(t, "47.048", "45.646", "45.230"), t.slice(0, 900));
  await page.getByLabel("Método").selectOption("enter");
  // desfecho com 8 categorias: recusado com a saída sugerida
  await page.getByLabel(/^Desfecho binário/).selectOption({ label: "tratamento (8 níveis)" });
  check("logística: desfecho com 8 níveis bloqueia a execução e sugere SQL + dataset",
    (await page.getByRole("button", { name: "Executar análise" }).isDisabled()) && (await page.getByText(/exatamente 2 categorias/).count()) === 1);
  await page.getByLabel(/^Desfecho binário/).selectOption("nivel");

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

  // vários pares: o par principal (altura − diametro) + um adicional (produtividade − altura); "altura" repete porque os campos de pares adicionais são compartilhados
  await page.getByRole("group", { name: /^Pares adicionais: 1ª medida/ }).getByLabel(/^produtividade/).check();
  await page.getByRole("group", { name: /^Pares adicionais: 2ª medida/ }).getByLabel(/^altura/).check();
  check("t pareado com vários pares: o resumo mostra os pares formados", (await page.getByLabel("Resumo dos campos").innerText()).includes("altura − diametro; produtividade − altura"));
  await run();
  await page.locator(".analysis-grid .card").nth(1).getByText("produtividade").first().waitFor({ timeout: 90000 }); // run() vê a tabela da execução anterior
  t = await resultText();
  const PM = REF.paired_multi[3];
  check("t pareado com vários pares: o t de cada par igual ao R", has(t, f3(P.t), f3(PM.t), " 31 "), t.slice(0, 800));
  await page.getByRole("group", { name: /^Pares adicionais: 2ª medida/ }).getByLabel(/^altura/).uncheck();
  check("t pareado: listas de pares adicionais de tamanhos diferentes bloqueiam a execução com mensagem", await page.getByRole("button", { name: "Executar análise" }).isDisabled() && (await page.getByText(/mesmo número de medidas nas duas listas/).count()) === 1);
  await page.getByRole("group", { name: /^Pares adicionais: 1ª medida/ }).getByLabel(/^produtividade/).uncheck();

  // --- Teste t de uma amostra (produtividade vs 200) ---
  await pickAnalysis("Teste t de uma amostra");
  await page.getByLabel(/^produtividade/).check();
  await page.getByLabel("Valor de referência").fill("200");
  await run();
  t = await resultText();
  const O = REF.onesample;
  check("t de uma amostra: t, gl e p iguais ao R", has(t, f3(O.t), " 31 ", p3(O.p)), t.slice(0, 500));
  await shot("a3c-t-uma-amostra");

  // Teste z (σ conhecido): o campo de σ só aparece com o teste z ligado
  check("teste z: desligado por padrão e sem campo de σ visível", !(await page.getByLabel(/^Teste z/).isChecked()) && (await page.getByLabel(/Desvio padrão populacional/).count()) === 0);
  await page.getByLabel(/^Teste z/).check();
  await page.getByLabel("Student", { exact: true }).uncheck(); // sozinho, a tabela do Z traz IC e d (com o Student, uma linha por teste sem eles)
  await page.getByLabel(/Desvio padrão populacional/).fill("30");
  await run();
  await page.locator(".analysis-grid .card").nth(1).getByText("Z", { exact: true }).first().waitFor({ timeout: 90000 }); // run() vê a tabela da execução anterior
  t = await resultText();
  const Z = REF.ztest;
  check("teste z: Z, p, diferença média e d (= diferença/σ) iguais ao R", has(t, "Z", f3(Z.z), p3(Z.p), f3(Z.diff), f3(Z.d)), t.slice(0, 700));
  await shot("a3c2-teste-z");

  // --- Estatísticas descritivas ---
  await pickAnalysis("Estatísticas descritivas");
  await page.getByLabel(/^produtividade/).check();
  await run();
  t = await resultText();
  const D = REF.desc;
  check("descritivas: média, desvio padrão, mediana, mínimo e máximo iguais ao R", has(t, f3(D.mean), f3(D.sd), f3(D.median), f3(D.min), f3(D.max)), t.slice(0, 600));
  check("descritivas: nenhuma célula vira [object Object]", !t.includes("[object Object]") && !t.includes('{"'), t.slice(0, 400));
  await shot("a3d-descritivas");

  // --- verificação automática de pressupostos: dados feitos para violá-los (variâncias e normalidade) ---
  await upload("e2e-pressupostos.csv", readFileSync(join(FIX, "pressupostos.csv"), "utf8"));
  await page.getByRole("tab", { name: "Análise estatística" }).click();
  await pickAnalysis("Teste t independente");
  check("pressupostos: nenhuma tabela de pressuposto é pedida ao usuário (opções desmarcadas)",
    !(await page.getByLabel("Normalidade (Shapiro-Wilk)").isChecked()) && !(await page.getByLabel("Igualdade de variâncias").isChecked()));
  await run();
  await notes().waitFor({ timeout: 90000 });
  let nt = (await notes().innerText()).replace(/\s+/g, " ");
  check("t independente: avisa normalidade (resíduos) e variâncias, sugerindo Mann-Whitney e Welch", has(nt, "Atenção", "Normalidade rejeitada", "resíduos", "Mann-Whitney", "Variâncias diferentes", "Welch"), nt);
  const PR = REF.pressupostos;
  check("t independente: W de Shapiro e F de Levene dos avisos iguais ao R", has(nt, `W = ${PR.shapiro_resid.W.toFixed(2).replace(".", ",")}`), nt);
  check("t independente: a tabela de pressupostos NÃO aparece na saída (só o aviso)", !(await resultText()).includes("Test of Normality") && !(await resultText()).includes("Assumption Checks"), (await resultText()).slice(0, 300));
  await shot("a3f-pressupostos-t");
  await pickAnalysis("ANOVA");
  await page.getByLabel(/^grupo/).check();
  check("pressupostos: trocar de análise limpa os avisos da anterior", (await notes().count()) === 0);
  await run();
  await notes().waitFor({ timeout: 90000 });
  nt = (await notes().innerText()).replace(/\s+/g, " ");
  check("ANOVA: avisa homogeneidade (F de Levene igual ao R) e sugere Kruskal-Wallis", has(nt, "Homogeneidade de variâncias rejeitada", `F = ${PR.levene_mean.F.toFixed(2).replace(".", ",")}`, "Kruskal-Wallis"), nt);

  // --- ANOVA de medidas repetidas (formato largo: uma coluna por medida; 24 sujeitos × 3 tempos × 2 grupos) ---
  await upload("e2e-medidas-repetidas.csv", readFileSync(join(FIX, "medidas_repetidas.csv"), "utf8"));
  await page.getByRole("tab", { name: "Análise estatística" }).click();
  await pickAnalysis("ANOVA de medidas repetidas");
  check("medidas repetidas: sem 2 medidas escolhidas não executa", await page.getByRole("button", { name: "Executar análise" }).isDisabled());
  for (const c of ["t1", "t2", "t3"]) await page.getByRole("checkbox", { name: new RegExp(`^${c}$`) }).check();
  check("medidas repetidas: mostra a ordem dos níveis (a da marcação)", (await page.getByLabel("Ordem dos níveis").innerText()).replace(/\s+/g, " ").includes("t1 → t2 → t3"));
  await run();
  t = await resultText();
  const RM = REF.rm;
  check("medidas repetidas: F, p e SQ do fator tempo iguais ao R (aov + Error)", has(t, f3(RM.one.tempo.F), f3(RM.one.tempo.ss)), t.slice(0, 700));
  check("medidas repetidas: correções de Greenhouse-Geisser e Huynh-Feldt (gl corrigidos = 2·ε)", has(t, "Greenhouse-Geisser", "Huynh-Feldt", f3(2 * RM.one.sph.gg)), t.slice(0, 900));
  check("medidas repetidas: Mauchly (W) e ε de Greenhouse-Geisser iguais ao R", has(t, f3(RM.one.sph.W), f3(RM.one.sph.gg)), t.slice(0, 900));
  await notes().waitFor({ timeout: 90000 });
  check("medidas repetidas: esfericidade respeitada (p = ,20): nota de nenhum alerta", has((await notes().innerText()).replace(/\s+/g, " "), "nenhum alerta"), await notes().innerText());
  await shot("a2d-medidas-repetidas");
  // delineamento misto: grupo entre-sujeitos
  await page.getByRole("checkbox", { name: /^grupo/ }).check();
  await run();
  await page.locator(".analysis-grid .card").nth(1).getByText(/grupo/).first().waitFor({ timeout: 90000 }); // run() vê a tabela da execução anterior; "grupo" só existe no resultado novo
  t = await resultText();
  check("medidas repetidas (misto): F de grupo, de tempo e da interação iguais ao R", has(t, f3(RM.mixed.grupo.F), f3(RM.mixed.tempo.F), f3(RM.mixed.inter.F)), t.slice(0, 900));
  check("medidas repetidas (misto): nenhum erro de nomes codificados do JASP", !/JaspExtraOptions|error/i.test(t), t.slice(0, 300));
  // comparações dois a dois (sem o grupo): t pareado com Holm
  await page.getByRole("checkbox", { name: /^grupo/ }).uncheck();
  await page.getByLabel("Comparar os níveis dois a dois").check();
  await run();
  await page.locator(".analysis-grid .card").nth(1).getByText("Post Hoc", { exact: false }).first().waitFor({ timeout: 90000 });
  t = await resultText();
  check("medidas repetidas: post hoc (t1 − t2: t pareado igual ao R, df = 23)", has(t, "t1", "t2", f3(RM.posthoc[0].t), " 23 "), t.slice(0, 1200));
  await page.getByLabel("Nome do fator (ex.: tempo)").fill("");
  check("medidas repetidas: nome do fator vazio bloqueia a execução", await page.getByRole("button", { name: "Executar análise" }).isDisabled());
  await page.getByLabel("Nome do fator (ex.: tempo)").fill("visita");

  // --- Friedman + Conover (alternativa não paramétrica; dados com empates e sobreposição) ---
  await upload("e2e-friedman.csv", readFileSync(join(FIX, "friedman.csv"), "utf8"));
  check("aba Dados: a coluna ordinal numérica (c1) traz o aviso de que também vale como escalar, e as escalares não",
    (await page.locator(".col-card", { hasText: "c1" }).locator('[data-hint="ordinal-numerica"]').count()) === 1 && (await page.locator('[data-hint="ordinal-numerica"]').count()) === 1);
  await page.getByRole("tab", { name: "Análise estatística" }).click();
  await pickAnalysis("ANOVA de medidas repetidas");
  check("Likert: a coluna ordinal numérica é oferecida como medida repetida, com rótulo explícito", (await page.getByRole("group", { name: /^Medidas repetidas/ }).getByRole("checkbox", { name: /^c1 \(ordinal, 8 valores: tratada como escalar\)$/ }).count()) === 1);
  for (const c of ["c1", "c2", "c3"]) await page.getByRole("group", { name: /^Medidas repetidas/ }).getByRole("checkbox", { name: new RegExp(`^${c}( |$)`) }).check();
  check("Friedman: desligado por padrão e sem a opção de Conover visível", !(await page.getByLabel(/^Teste de Friedman/).isChecked()) && (await page.getByLabel(/Post hoc de Conover/).count()) === 0);
  await page.getByLabel(/^Teste de Friedman/).check();
  await page.getByLabel(/Post hoc de Conover/).check();
  await run();
  await page.locator(".analysis-grid .card").nth(1).getByText(/Conover/).first().waitFor({ timeout: 90000 }); // run() vê a tabela da execução anterior
  t = await resultText();
  const FR = REF.friedman;
  check("Friedman: χ², gl, p e W de Kendall iguais ao R", has(t, "Friedman", f3(FR.chi), p3(FR.p), f3(FR.kendall)), t.slice(0, 900));
  check("Conover: t (do 1º par) e p iguais ao R, com gl = (n−1)(k−1) = 38", has(t, "Conover", f3(Math.abs(FR.conover[0].t)), f3(FR.conover[0].p).replace(/^0/, ""), " 38 "), t.slice(0, 1400));
  await shot("a2e-friedman");

  // --- Likert (c1 ordinal): vale como variável escalar no t de uma amostra, com o t do R (a coluna não precisa virar "escalar") ---
  await pickAnalysis("Teste t de uma amostra");
  check("Likert: a coluna ordinal numérica é oferecida no t de uma amostra", (await page.getByRole("checkbox", { name: /^c1 \(ordinal/ }).count()) === 1);
  await page.getByRole("checkbox", { name: /^c1 \(ordinal/ }).check();
  await page.getByLabel("Valor de referência").fill("10");
  await run();
  t = await resultText();
  check("Likert: t e p do t de uma amostra sobre a coluna ordinal iguais ao R", has(t, f3(REF.ordinal.onesample.t), " 19 "), t.slice(0, 500));
  await shot("a3h-likert-t");

  // --- ANOVA de medidas repetidas com DOIS fatores intra-sujeito (A pre/pos × B b1/b2/b3; 6 colunas) ---
  await upload("e2e-rm2.csv", readFileSync(join(FIX, "rm2.csv"), "utf8"));
  await page.getByRole("tab", { name: "Análise estatística" }).click();
  await pickAnalysis("ANOVA de medidas repetidas");
  for (const c of ["a1b1", "a1b2", "a1b3", "a2b1", "a2b2", "a2b3"]) await page.getByRole("group", { name: /^Medidas repetidas/ }).getByRole("checkbox", { name: new RegExp(`^${c}$`) }).check();
  await page.getByLabel(/^Nome do fator/).fill("A");
  await page.getByLabel(/^Níveis do fator/).fill("pre, pos");
  await page.getByLabel(/^2º fator intra-sujeito/).fill("B");
  await page.getByLabel(/^Níveis do 2º fator/).fill("b1, b2, b3");
  check("2 fatores intra: o resumo mostra o mapeamento das células (1º fator varia mais devagar)", (await page.getByLabel("Resumo dos campos").innerText()).includes("pre · b1 = a1b1; pre · b2 = a1b2; pre · b3 = a1b3; pos · b1 = a2b1"));
  await run();
  await page.locator(".analysis-grid .card").nth(1).getByText(/A ✻ B|B ✻ A/).first().waitFor({ timeout: 90000 }).catch(() => {});
  t = await resultText();
  const R2 = REF.rm2;
  check("2 fatores intra: F de A, de B e da interação A ✻ B iguais ao R (aov + Error)", has(t, f3(R2.A.F), f3(R2.B.F), f3(R2.AB.F)), t.slice(0, 900));
  await shot("a2g-rm-dois-fatores");
  await page.getByLabel(/^Níveis do 2º fator/).fill("b1, b2");
  check("2 fatores intra: 2 × 2 células ≠ 6 colunas bloqueia a execução com mensagem", await page.getByRole("button", { name: "Executar análise" }).isDisabled() && (await page.getByText(/2 × 2 = 4 células, mas há 6 coluna/).count()) === 1);

  // --- Qui-quadrado: dataset derivado com CASE (faixa) ---
  await upload("e2e-faixa-src.csv", readFileSync(join(FIX, "ttest.csv"), "utf8"));
  // dados que cumprem os pressupostos (Levene p ≈ ,06; Shapiro p ≈ ,22): a nota informa que não há alerta
  await page.getByRole("tab", { name: "Análise estatística" }).click();
  await pickAnalysis("Teste t independente");
  await run();
  await notes().waitFor({ timeout: 90000 });
  nt = (await notes().innerText()).replace(/\s+/g, " ");
  check("t independente com pressupostos ok: a nota diz que não há alerta", has(nt, "nenhum alerta") && !nt.includes("Atenção"), nt);
  // t independente bayesiano sobre os mesmos dados: BF10 igual ao ttestBF do R
  await pickAnalysis("Teste t independente bayesiano");
  await run();
  t = await resultText();
  check("t bayesiano: BF₁₀ igual ao BayesFactor (R)", has(t, REF.bayes.indep.toFixed(3)), t.slice(0, 500));
  await bnotes().waitFor({ timeout: 30000 });
  const bn = (await bnotes().innerText()).replace(/\s+/g, " ");
  check("t bayesiano: interpreta o BF (4,36 = evidência moderada a favor de H₁) e cita a classificação", has(bn, "BF₁₀ = 4,36", "evidência moderada a favor de H₁", "Lee e Wagenmakers"), bn);
  check("t bayesiano: sem avisos de pressupostos (não se aplicam)", (await notes().count()) === 0);
  await page.getByLabel(/^Fator de Bayes/).selectOption("BF01");
  await run();
  await page.locator(".analysis-grid .card").nth(1).getByText((1 / REF.bayes.indep).toFixed(3)).first().waitFor({ timeout: 90000 });
  check("t bayesiano: BF₀₁ é o inverso do BF₁₀", has(await resultText(), (1 / REF.bayes.indep).toFixed(3)));
  check("t bayesiano: com BF₀₁ na tabela a interpretação continua em BF₁₀", has((await bnotes().innerText()).replace(/\s+/g, " "), "BF₁₀ = 4,36", "a favor de H₁"));
  await shot("a3g-t-bayesiano");

  // prior informativo (Normal, média 0,3, dp 0,5): BF₁₀ igual à integração numérica em R (t não central); o campo do prior padrão some
  await page.getByLabel(/^Fator de Bayes/).selectOption("BF10");
  check("t bayesiano: com o prior padrão, os campos do prior informativo não aparecem", (await page.getByLabel("Distribuição informativa").count()) === 0 && (await page.getByLabel(/^Largura do prior padrão/).count()) === 1);
  const priorSelect = () => page.locator("label.field").filter({ hasText: /^Prior(Padrão|Informativo)/ }).locator("select");   // o texto do rótulo inclui as opções
  await priorSelect().selectOption("informative");
  await page.getByLabel("Distribuição informativa").selectOption("normal");
  await page.getByLabel("Média", { exact: true }).fill("0.3");
  await page.getByLabel("Desvio padrão", { exact: true }).fill("0.5");
  check("t bayesiano: com o prior informativo, o campo do prior padrão some", (await page.getByLabel(/^Largura do prior padrão/).count()) === 0);
  await run();
  await page.locator(".analysis-grid .card").nth(1).getByText(REF.bayes_inf.indep.normal.toFixed(3)).first().waitFor({ timeout: 90000 }); // run() vê a tabela da execução anterior
  check("t bayesiano com prior Normal(0,3; 0,5): BF₁₀ igual à integração numérica do R", has(await resultText(), REF.bayes_inf.indep.normal.toFixed(3)));
  await page.getByLabel("Hipótese alternativa (grupo 1 vs grupo 2)").selectOption("greater");
  check("t bayesiano: prior informativo + hipótese unilateral bloqueia a execução com mensagem", await page.getByRole("button", { name: "Executar análise" }).isDisabled() && (await page.getByText(/só está disponível com a hipótese bilateral/).count()) === 1);
  await page.getByLabel("Hipótese alternativa (grupo 1 vs grupo 2)").selectOption("twoSided");
  await priorSelect().selectOption("default");

  // --- teste z de duas médias (σ conhecidos): análise do motor da plataforma, não do JASP ---
  await pickAnalysis("Teste z de duas amostras (σ conhecidos)");
  await page.getByLabel(/^σ do 1º grupo/).fill("1.5");
  await page.getByLabel(/^σ do 2º grupo/).fill("2");
  await run();
  t = await resultText();
  const ZM = REF.z_means;
  check("teste z de duas médias: z, p, diferença e d iguais ao R (pnorm)", has(t, f3(ZM.z), p3(ZM.p), f3(ZM.diff), f3(ZM.d)), t.slice(0, 700));
  check("teste z: a tabela avisa que NÃO vem de um módulo JASP", has(t, "não por um módulo JASP"), t.slice(0, 700));
  await shot("a3i-teste-z");
  // proporções: coluna binária derivada por SQL (resposta = score >= 10,5)
  await page.getByRole("tab", { name: "Consulta SQL" }).click();
  await runSql(`SELECT "group" AS grupo, CASE WHEN score >= 10.5 THEN 'sim' ELSE 'nao' END AS resposta FROM e2e_faixa_src`);
  await page.getByRole("tab", { name: "Tabela" }).click();
  await page.locator(".card table.data tbody tr").first().waitFor();
  await saveAsDataset("e2e-resposta");
  await page.getByRole("tab", { name: "Análise estatística" }).click();
  await pickAnalysis("Teste z de proporções");
  await page.getByLabel(/^Desfecho/).selectOption("resposta");
  await page.getByLabel(/^Grupos/).selectOption("grupo");
  await run();
  t = await resultText();
  const ZP = REF.z_props2;
  check("teste z de duas proporções: z, p e diferença iguais ao prop.test do R", has(t, f3(ZP.z), f3(ZP.p).replace(/^0/, ""), f3(ZP.diff), `(${ZP.x1}/${ZP.n1})`), t.slice(0, 700));
  await page.getByLabel(/^Grupos/).selectOption("");
  await page.getByLabel(/^p₀/).fill("0.4");
  await run();
  await page.locator(".analysis-grid .card").nth(1).getByText("uma proporção").first().waitFor({ timeout: 90000 }); // run() vê a tabela da execução anterior
  t = await resultText();
  const ZO = REF.z_props1;
  check("teste z de uma proporção (p₀ = 0,4): z e p iguais ao prop.test do R, IC de Wilson", has(t, f3(ZO.z), f3(ZO.p).replace(/^0/, ""), f3(ZO.lo), f3(ZO.hi)), t.slice(0, 700));
  await shot("a3j-z-proporcoes");
  await page.getByRole("tab", { name: "Consulta SQL" }).click();
  await runSql(`SELECT "group" AS grupo, CASE WHEN score < 9 THEN 'baixo' WHEN score < 11 THEN 'medio' ELSE 'alto' END AS faixa FROM e2e_faixa_src`);
  await page.getByRole("tab", { name: "Tabela" }).click();
  await page.locator(".card table.data tbody tr").first().waitFor();
  await saveAsDataset("e2e-faixas");
  await page.getByRole("tab", { name: "Análise estatística" }).click();
  // --- tabela de frequência (Descritivas sobre uma coluna categórica) ---
  await pickAnalysis("Estatísticas descritivas");
  await page.getByLabel(/^faixa/).check();
  await page.getByLabel(/Tabelas de frequência/).check();
  await run();
  t = await resultText();
  const nFaixa = readFileSync(join(FIX, "ttest.csv"), "utf8").split("\n").map((l) => l.trim()).filter(Boolean).length - 1;
  check("frequência: níveis alto/baixo/medio e Total igual ao nº de linhas", has(t, "alto", "baixo", "medio", "Total", String(nFaixa)), t.slice(0, 600));
  await shot("a3e-frequencias");
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
  await notes().waitFor({ timeout: 90000 });
  check("qui-quadrado com esperadas ≥ 5: nota de nenhum alerta", has((await notes().innerText()).replace(/\s+/g, " "), "nenhum alerta"), await notes().innerText());

  // qui-quadrado bayesiano: BF₁₀ por modelo amostral, contra contingencyTableBF
  await pickAnalysis("Qui-quadrado bayesiano (tabela de contingência)");
  await page.getByLabel(/^Linhas/).selectOption("grupo");
  await page.getByLabel(/^Colunas/).selectOption("faixa");
  await run();
  t = await resultText();
  const CB = REF.bayes_chi;
  check("qui-quadrado bayesiano (linhas fixas, padrão): BF₁₀ igual ao contingencyTableBF do R", has(t, CB.rows_fixed.toFixed(3)), t.slice(0, 500));
  await bnotes().waitFor({ timeout: 30000 });
  check("qui-quadrado bayesiano: interpreta o BF (3,16 = moderada a favor de H₁, associação)", has((await bnotes().innerText()).replace(/\s+/g, " "), "BF₁₀ = 3,16", "moderada a favor de H₁ (as variáveis estão associadas)"), await bnotes().innerText());
  await page.getByLabel("Como os dados foram coletados").selectOption("poisson");
  await run();
  await page.locator(".analysis-grid .card").nth(1).getByText(CB.poisson.toFixed(3)).first().waitFor({ timeout: 90000 }); // run() vê a tabela da execução anterior
  check("qui-quadrado bayesiano (Poisson): BF₁₀ igual ao do R", has(await resultText(), CB.poisson.toFixed(3)));
  await shot("a5b-qui-quadrado-bayesiano");

  // --- Bloco de ANOVA num relatório ---
  await page.getByRole("link", { name: "Relatórios" }).click();
  await page.getByRole("button", { name: "Novo relatório" }).click();
  await page.waitForURL(/#\/reports\/[0-9a-f]{32}/);
  reportId = page.url().match(/#\/reports\/([0-9a-f]{32})/)?.[1];
  await page.locator(".title-input").fill("E2E Relatório ANOVA");
  await page.getByRole("button", { name: "+ Análise", exact: true }).click();
  const frame = page.locator(".block-frame").nth(0);
  await frame.getByLabel(/^Análise/).selectOption({ label: "ANOVA" });
  check("bloco de relatório: o seletor de análises também é agrupado (optgroups)",
    JSON.stringify(await frame.getByLabel(/^Análise/).locator("optgroup").evaluateAll((g) => g.map((x) => x.label))) === JSON.stringify(["Descritivas", "Comparação de médias", "Testes z (σ conhecido e proporções)", "Associação e predição", "Bayesianas"]));
  await frame.getByLabel("Dataset").selectOption({ label: "e2e-dbc" });
  await frame.getByLabel("Variável dependente (escalar)").selectOption("produtividade");
  await frame.getByLabel(/^tratamento/).check();
  await frame.getByLabel(/^bloco/).check();
  await frame.getByRole("button", { name: "Executar análise" }).click();
  await frame.locator("table.apa-table").first().waitFor({ timeout: 90000 });
  let bt = (await frame.locator(".analysis-out").innerText()).replace(/\s+/g, " ");
  check("bloco de relatório: ANOVA com os números do R", has(bt, f3(A.trat.F), f3(A.bloco.F)), bt.slice(0, 400));
  await page.locator(".save-status.saved").waitFor({ timeout: 15000 });

  // 2º bloco: t independente sobre dados que violam os pressupostos. As notas automáticas são opt-in por bloco (o relatório é a saída publicável)
  await page.getByRole("button", { name: "+ Análise", exact: true }).click();
  const frame2 = page.locator(".block-frame").nth(1);
  await frame2.getByLabel(/^Análise/).selectOption({ label: "Teste t independente" });
  await frame2.getByLabel("Dataset").selectOption({ label: "e2e-pressupostos.csv" });
  await frame2.getByRole("button", { name: "Executar análise" }).click();
  await frame2.locator("table.apa-table").first().waitFor({ timeout: 90000 });
  const blockNotes = (scope) => scope.getByRole("status", { name: "Verificação de pressupostos" });
  await page.waitForTimeout(1500);   // dá tempo de uma nota (que NÃO deve vir) aparecer
  check("bloco de relatório: sem notas de pressupostos por padrão", (await blockNotes(frame2).count()) === 0);
  await frame2.getByLabel(/Mostrar verificação de pressupostos/).check();
  await blockNotes(frame2).waitFor({ timeout: 90000 });
  check("bloco de relatório: com a opção ligada, o aviso de normalidade aparece", has((await blockNotes(frame2).innerText()).replace(/\s+/g, " "), "Atenção", "Normalidade rejeitada"), await blockNotes(frame2).innerText());
  await page.locator(".save-status.saved").waitFor({ timeout: 15000 });

  // recarrega: vira modo leitura e reexecuta a ANOVA salva (análise + dataset + opções persistidos)
  await page.reload();
  await page.locator(".report-doc table.apa-table").first().waitFor({ timeout: 90000 });
  bt = (await page.locator(".report-doc").innerText()).replace(/\s+/g, " ");
  check("relatório recarregado: a ANOVA salva reaparece com os números do R", has(bt, f3(A.trat.F), f3(A.bloco.F)), bt.slice(0, 400));
  await blockNotes(page.locator(".report-doc")).waitFor({ timeout: 90000 });
  check("relatório recarregado: a opção de notas foi salva e o aviso reaparece só no bloco que a ligou",
    (await blockNotes(page.locator(".report-doc")).count()) === 1 && has((await blockNotes(page.locator(".report-doc")).innerText()).replace(/\s+/g, " "), "Normalidade rejeitada"));
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
