# BACKLOG do catálogo (atualizado na 6.8; as seções por fatia abaixo trazem o detalhe)

Pedidos do usuário ainda abertos:
- [ ] **Teste z de duas amostras** (comparar duas médias com σ conhecido) — **não existe no JASP instalado**; pedido em 2026-11-05. O teste z de **uma** amostra já está na 6.7 (opção `zTest` do t de uma amostra).
- [ ] **Teste z de proporções** (uma e duas amostras) — não existe no JASP (o mais próximo é o `BinomialTest` exato, jaspFrequencies). Decisão pendente: expor o binomial/ABTest do JASP ou implementar o z fora do JASP (quebra a regra "motor = JASP real", ver memória do projeto).

Resolvido na 6.11: dados ordinais numéricos (Likert) em papéis escalares, e regressão com um único preditor (bug do motor).

Outros itens abertos: (ANOVA de medidas repetidas feita na 6.9 e Friedman na 6.10; faltam vários fatores intra-sujeito); correlação/regressão/ANCOVA/qui-quadrado bayesianos; Wilcoxon bayesiano e priors informativos; t pareado com vários pares; ANCOVA com post hoc e médias marginais; logística com seleção de método; estimativa de efeito a posteriori nos testes t bayesianos; pressupostos para correlação/regressão/qui-quadrado; avisos de pressupostos em relatório/dashboard.

---

# Fase 6 (projeto) — catálogo estatístico, fatias 6.1 e 6.2 ✅ (2026-11-05)

Corresponde ao "primeiro lote de análises" da Fase 2 do PLAN.md. Antes: teste t independente, ANOVA, correlação, regressão linear e qui-quadrado.
Com a 6.1 o catálogo tinha **8 análises**; a 6.2 (seção final) levou a **10** (ANCOVA e regressão logística) (aparecem no seletor da aba Análise, nos blocos de relatório e nos tiles de dashboard):

| Análise | Módulo JASP | Observações |
|---|---|---|
| **Teste t pareado** (`TTestPairedSamples`) | jaspTTests | duas medidas escalares → opção `pairs` (um par); Student/Wilcoxon, diferença média, d de Cohen, hipótese alternativa, Shapiro das diferenças, Q-Q |
| **Teste t de uma amostra** (`TTestOneSample`) | jaspTTests | uma ou mais variáveis vs. valor de referência; Student/Wilcoxon, alternativa |
| **Estatísticas descritivas** (`Descriptives`) | jaspDescriptives | N, ausentes, média, mediana, moda, soma, DP, variância, EP, CV, IQR, amplitude, mín/máx, quartis, assimetria, curtose, Shapiro, IC da média; "separar por" um fator; histograma, boxplot, Q-Q |

## Mudanças no motor
- `engine.R`: `Descriptives` entra no registro fechado e ganha análise de aquecimento (o worker agora aquece 5 módulos; `/health → modules` mostra `Descriptives: ok`). Pareado e uma amostra já estavam registrados.
- Front (`lib/analyses.ts`): campos de variável podem ser **`local`** (só da interface, não vão ao JASP) e há `parseVars` para reconstruí-los a partir das opções salvas. O pareado usa isso: duas caixas "1ª/2ª medida" ↔ `pairs: [[a, b]]`.
- `formatCell` passou a entender **células com formato próprio** (`{value, type, format}`: mediana/mínimo/máximo das descritivas). Antes apareceria `[object Object]`. Objeto desconhecido agora vira JSON, nunca `[object Object]`.

## Conferido contra o R puro (referências em `r_reference.json`, regeneradas por `make_reference.R`)
- t pareado: t, gl, p, diferença média, IC, d de Cohen, p unilateral e **Wilcoxon exato** (p = 4,66e-10).
- t de uma amostra: t, gl, p, IC, d, p unilateral, Wilcoxon (p = 0,5000475).
- Descritivas: N, média, DP, variância, EP, soma, amplitude, mediana, mín, máx; e "separar por" (4 blocos × 8).
- Armadilhas descobertas: (1) o JASP usa p **exato** no Wilcoxon (sem empates, n < 50), então a referência é `wilcox.test()` padrão, não `exact = FALSE`; (2) no t de uma amostra o JASP mostra a **diferença** em relação ao valor de referência e o IC **da diferença** (o R mostra a média e o IC da média).

## Verificado
`pytest` 174 (5 novos de integração com o motor real), `vitest` 131 (11 novos), `e2e:all` = 6 suítes verdes (a de análises ganhou t pareado, uma amostra e descritivas pela interface).

## Pendências
- t pareado com **vários pares** (hoje um par por análise).
- Sem Kruskal-Wallis, ANCOVA, regressão logística, ANOVA de medidas repetidas, modelos bayesianos, frequências (tabelas de frequência simples), gráficos de descritivas customizados.
- **Verificação automática de pressupostos** com avisos na saída (item do PLAN): hoje o usuário precisa marcar "Normalidade"/"Igualdade de variâncias".

---

# Fatia 6.2 — ANCOVA e regressão logística ✅

| Análise | Módulo | Observações |
|---|---|---|
| **ANCOVA** (`Ancova`) | jaspAnova | fatores + covariáveis; `modelTerms` = efeitos principais (covariáveis só como efeito principal) + interações **entre fatores** se pedidas; descritivas, Levene, Q-Q, η²/η² parcial/ω² |
| **Regressão logística** (`RegressionLogistic`) | jaspRegression | desfecho com **exatamente 2 categorias** (o JASP modela a 2ª, por ordem alfabética); estimativas de Wald, razão de chances, IC (Wald, na escala da razão de chances), matriz de confusão, acurácia, AUC, sensibilidade/especificidade/precisão, ROC |

## Mudanças no motor
- `engine.R`: `Ancova` e `RegressionLogistic` entram no registro fechado. O **remendo do `modelTerms` agora vale também para `Ancova`** (sem ele, fator + bloco + covariável voltava com a tabela toda nula, pelo mesmo motivo da ANOVA: o QML repovoa as interações). Na logística, `modelTerms` é **uma lista de modelos** (como na regressão linear): os formatos "um termo por preditor" quebram com `attempt to select less than one element`.
- Front: `ANCOVA_DEF` e `LOGISTIC_DEF`; a logística recusa desfecho com ≠ 2 categorias e **ensina a saída** (criar a variável com `CASE WHEN … THEN 'alto' ELSE 'baixo' END` e "Salvar como dataset").
- UX: nas listas de caixas, as colunas já escolhidas em outro campo **somem** (o desfecho não aparece mais em "Fatores", nem a dependente em "Covariáveis").

## Conferido contra o R puro
- ANCOVA: gl, SQ, F e p de tratamento/bloco/covariável (`drop1` com contrastes soma-zero = SQ tipo II/III do JASP) em dois modelos (fator+covariável; fator+bloco+covariável com 20 gl de resíduo).
- Logística (`glm` binomial): coeficientes, EP, z, p, razão de chances, **IC de Wald** (o JASP usa Wald, não perfil de verossimilhança), deviance, AIC, BIC, gl, acurácia, AUC e as 4 células da matriz de confusão.

## Verificado
`pytest` 177 (3 novos de integração com o motor real), `vitest` 138 (7 novos), `e2e:all` = 6 suítes verdes (a de análises cobre ANCOVA, logística sobre dataset derivado por SQL, desfecho de 8 níveis bloqueado, e as listas sem a variável já usada).

## Pendências
- ANCOVA sem post hoc, sem médias marginais ajustadas, sem teste de homogeneidade das inclinações (interação fator × covariável).
- Logística sem seleção de método (backward/forward/stepwise), sem interações, sem pesos.
- ~~A aba Análise perde a análise e as opções ao trocar de aba~~ — resolvido na 6.3 (abaixo).
- O worker aquece só os módulos com análise de aquecimento; `Ancova`/`RegressionLogistic` não têm a sua (usam o módulo já carregado), então `/health → modules` não as lista.

---

# Fatia 6.3 — estado da aba Análise preservado (front, sem mudança no motor)

- `AnalysisSession` (`lib/analyses.ts`: análise escolhida, opções de cada análise, última execução) agora vive no `App`, **por dataset**; `AnalysisTab` recebe `session` + `onSession`. Trocar entre Dados / Consulta SQL / Análise, ou entre datasets, não perde nada; o resultado reaparece (vem do cache da API).
- e2e (`analyses.mjs`): após a regressão linear, vai a "Consulta SQL" e volta, e confere análise selecionada, variáveis marcadas e resultado.
- Verificado: `typecheck` e `vitest` (138) verdes. **O e2e novo NÃO foi executado** (Docker parado nesta sessão).

---

# Fatia 6.4 — Kruskal-Wallis, post hoc de Dunn e tabelas de frequência ✅

Sem mudança no motor (nada de rebuild do worker): os dois recursos já existem no JASP instalado, como **opções de funções já registradas**.

| Recurso | Onde | Opções JASP |
|---|---|---|
| **Kruskal-Wallis** (um teste por fator) | seção "Não paramétrico" da **ANOVA** | `kruskalWallisFactors` (= os fatores), `kruskalEffectSizeEstimates` + `kruskalEpsilon`/`kruskalEta`, `postHocTypeDunn` |
| **Post hoc de Dunn** (Bonferroni e Holm) | idem | `postHocTypeDunn` |
| **Tabelas de frequência** | **Estatísticas descritivas** (seção "Tabelas") | `frequencyTables` (variáveis nominais/ordinais; o seletor já aceitava essas) |

- Front: `kruskal`, `kruskalEffect` e `dunn` são toggles **locais**; `derive` monta as opções reais e só envia Dunn/efeito se o Kruskal estiver ligado (evita opção órfã). `parse` recupera os três de blocos salvos (ida e volta testada). A ANCOVA **não** tem Kruskal (o JASP só o oferece na ANOVA).
- A tabela de frequência do JASP termina com as linhas **Missing** e **Total**.

## Conferido contra o R puro
- `kruskal.test`: H, gl, p; ε² = H/(N−1) e η² de postos = (H−k+1)/(N−k) (fórmulas conferidas com a saída do JASP).
- Dunn: z, p, Bonferroni e Holm dos 28 pares, com a fórmula de Dunn **com correção de empates**, calculada em R.
- Frequência: n, % e % acumulada de uma coluna categórica derivada por SQL.

## Verificado
`pytest` 180 (3 novos), `vitest` 141 (3 novos), `e2e:all` = 6 suítes verdes (a de análises cobre Kruskal+Dunn e a tabela de frequência pela interface).
Armadilha do e2e: `run()` espera a primeira `table.apa-table`, que já pode ser a da execução ANTERIOR; ao trocar só uma opção, esperar por um texto próprio do novo resultado.

## Pendências
- Kruskal-Wallis só como parte da ANOVA (sem entrada própria no seletor; a tabela da ANOVA aparece junto).
- Sem gráficos de frequência (barras) nem frequências cruzadas além do qui-quadrado.
- ~~Verificação automática de pressupostos~~ — feita na 6.5 (abaixo).

---

# Fatia 6.5 — verificação automática de pressupostos ✅

Fecha o último item do "primeiro lote" da Fase 2 do PLAN. Só front + testes; **nada muda no motor**.

**Como funciona** (`lib/assumptions.ts`, `AnalysisRun`): depois que a análise pedida termina, a interface roda **em segundo plano** as mesmas opções **mais** os testes de pressuposto, lê as tabelas e mostra avisos em português acima do resultado (aba Análise). A saída que o usuário pediu não ganha tabelas extras; as caixas "Normalidade"/"Igualdade de variâncias" continuam desmarcadas. A segunda execução só começa depois da principal (não disputa worker) e falha em silêncio.

| Análise | O que é verificado | Aviso (α = 0,05) sugere |
|---|---|---|
| Teste t independente | Shapiro-Wilk nos **resíduos**; Levene (centrado na **mediana**) | Mann-Whitney; Welch |
| Teste t pareado | Shapiro-Wilk das **diferenças** | Wilcoxon |
| Teste t de uma amostra | Shapiro-Wilk | Wilcoxon |
| ANOVA | Levene (centrado na **média**) | Kruskal-Wallis ou transformar a variável |
| ANCOVA | Levene | interpretar com cautela / transformar |

Sem violação, uma nota informativa diz "nenhum alerta". Sem a tabela (ex.: ANOVA em blocos com 1 observação por célula, em que o JASP nem calcula o Levene) **não aparece nada**: melhor calar do que afirmar uma verificação que não ocorreu.

## Conferido contra o R puro (`pressupostos.csv`, `r_reference.json → pressupostos`)
Shapiro-Wilk dos resíduos (W, p), Levene com centro na mediana (t) e na média (ANOVA), F, p e gl. Descoberta: o JASP usa centros **diferentes** nas duas análises, e o Shapiro do t independente é dos resíduos (W = 0,797), não da variável inteira (W = 0,681).

## Verificado
`vitest` 149 (8 novos), `pytest` 181 (1 novo), `e2e:all` 6 suítes verdes (análises: avisos de t e ANOVA com números iguais ao R, ausência da tabela na saída, limpeza ao trocar de análise, caso sem alerta, caso sem Levene).
Armadilha: `docker cp <dir> <container>:/tmp/fx` quando `/tmp/fx` já existe copia para `/tmp/fx/<dir>` e o R roda com arquivos velhos (r_reference.json "não muda"); usar `docker cp <dir>/. <container>:/tmp/fx/`.

## Pendências
- Avisos só na aba Análise; blocos de relatório e tiles de dashboard não os mostram (decisão de produto: o relatório é a saída publicável).
- Sem verificação em correlação (normalidade bivariada), regressão (resíduos, multicolinearidade, homocedasticidade), logística e qui-quadrado (frequências esperadas < 5).
- Shapiro-Wilk é muito sensível com n grande: o aviso não considera o tamanho da amostra.

---

# Fatia 6.6 — versões bayesianas: testes t e ANOVA ✅

O catálogo passa de 10 para **14 análises**.

| Análise | Função JASP | Opções expostas |
|---|---|---|
| **t independente bayesiano** | `TTestBayesianIndependentSamples` (jaspTTests) | hipótese (bilateral/maior/menor), largura do prior de Cauchy (0,707), BF₁₀ / BF₀₁ / log(BF₁₀), descritivas, gráficos prior-posterior e robustez |
| **t pareado bayesiano** | `TTestBayesianPairedSamples` | idem (duas caixas "1ª/2ª medida" → `pairs`) |
| **t de uma amostra bayesiano** | `TTestBayesianOneSample` | idem + valor de referência |
| **ANOVA bayesiana** | `AnovaBayesian` (jaspAnova) | fatores, interações (opcional), prior dos efeitos fixos (r = 0,5), BF₁₀/BF₀₁/log, comparar com o melhor modelo ou com o nulo, BF de inclusão (todos os modelos / matched), estimativas a posteriori |

## Mudanças no motor
- `engine.R`: as 4 funções entram no registro fechado (os pacotes `BayesFactor` e `bridgesampling` já estavam na imagem). **`AnovaBayesian` entra em `PATCH_MODEL_TERMS`**: sem o remendo o JASP repovoa o modelo com a interação (5 modelos em vez de 4), como na ANOVA clássica.
- **A ANOVA bayesiana fixa a semente** (`setSeed: true, seed: 1`; o JASP por padrão não fixa) para que o mesmo pedido dê o mesmo resultado. Os testes t são determinísticos (integração numérica).
- **`init_jasp` desliga `reinstall.modules`.** Por padrão o jaspTools reinstalou TODOS os módulos a partir do fonte em cada partida do motor: ~1 min no melhor caso e, com os 2 workers (limite de 1,5 GB) ao mesmo tempo, as instalações expiraram e deixaram `jaspAnova` apagado no contêiner ("The installation of jaspAnova failed"; `/usr/local/lib/R/site-library/00LOCK-jaspAnova`). Os módulos já estão na imagem (install-modules.sh); a partida caiu de ~60 s para **~4 s**.

## Conferido contra o R (pacote BayesFactor, `r_reference.json → bayes`)
- `ttestBF` (rscale 0,707): independente, uma amostra (bilateral e unilateral = `nullInterval = c(0, Inf)`) e pareado; BF₀₁ = 1/BF₁₀ e log(BF₁₀) = log(BF₁₀).
- `anovaBF(produtividade ~ tratamento + bloco, rscaleFixed = 0,5)`: BF de cada modelo contra o nulo (tolerância 3%, Monte Carlo: ~0,3% no JASP e ~1% no BayesFactor). Atenção: a tabela do JASP vem relativa ao **melhor modelo**; a referência do R é relativa ao nulo (dividir pelo BF₁₀ do "Null model").
- Gráficos de prior/posterior e robustez voltam como imagens embutidas.
- Guarda no vitest: todo `id` do catálogo precisa estar no registro de `engine.R` (senão o worker responde 422).

## Verificado
`vitest` 152 (3 novos), `pytest` 185 (5 novos), `e2e:all` 6 suítes verdes (análises: t bayesiano com BF igual ao do R, BF₀₁ como inverso, ANOVA bayesiana aditiva sem interações e razão do melhor modelo contra o nulo).

## Pendências
- ~~Sem interpretação textual do fator de Bayes~~ — feita na 6.8 (abaixo). Continua sem estimativa de efeito a posteriori nos testes t.
- Sem t bayesiano com Wilcoxon (amostragem MCMC) nem priors informativos/Dienes, sem ANCOVA/medidas repetidas/correlação/regressão/qui-quadrado bayesianos (as funções existem no JASP instalado).
- ~~O seletor de análises tem 14 botões em lista única~~ — agrupado na 6.8 (abaixo).

---

# Fatia 6.7 — teste z de uma amostra ✅

O JASP não tem uma análise "Teste z" separada: ele é uma **opção do Teste t de uma amostra** (`zTest` + `zTestSd`, o desvio padrão populacional conhecido). Foi exposto ali, sem mudança no motor (nem rebuild do worker).

- Formulário: "Teste z (desvio padrão populacional conhecido)" entre os testes (desligado por padrão) e o campo "Desvio padrão populacional (σ)" (padrão 1, como no JASP), que só aparece com o teste ligado. O teste z vale sozinho (basta ao menos um de Student/Wilcoxon/z) e respeita a hipótese alternativa.
- Resultado: Z, p, diferença média, IC da diferença e d de Cohen = diferença/σ. Junto com o Student, a tabela traz uma linha por teste (sem IC/d); sozinho, traz IC e d.
- Conferido contra o R: Z = (média − μ₀)/(σ/√n), p bilateral e unilateral (`pnorm`), IC normal da diferença, d = diferença/σ (σ = 30, μ₀ = 200 sobre a produtividade).

## Verificado
`vitest` 153 (1 novo), `pytest` 186 (1 novo), `e2e:all` 6 suítes verdes.

## Pendências
- **Não há teste z de duas amostras nem de proporções no JASP instalado** (a comparação de duas médias com σ conhecido e o teste z de proporção não existem como análises). Se forem necessários: teste de proporção = `BinomialTest` (jaspFrequencies, exato) ou implementar fora do JASP (o que quebra a regra "motor = JASP real").
- O formulário do t de uma amostra não expõe opção de IC; o IC do JASP só aparece com `meanDifferenceCi`.

---

# Fatia 6.8 — seletor agrupado e interpretação do fator de Bayes ✅ (só front)

## Seletor agrupado
`ANALYSIS_GROUPS` (`lib/analyses.ts`): **Descritivas**, **Comparação de médias** (t ×3, ANOVA, ANCOVA), **Associação e predição** (correlação, regressões, qui-quadrado) e **Bayesianas**. Usado na aba Análise (títulos de grupo + botões, ainda `role="tab"`) e no bloco de relatório (`<optgroup>`). Guarda no vitest: cada análise do catálogo está em exatamente um grupo.

## Interpretação do fator de Bayes (`lib/bayes.ts`)
Acima do resultado, na aba Análise, uma nota por linha em português, com a classificação de Jeffreys adaptada por Lee & Wagenmakers (2013): 1–3 anedótica, 3–10 moderada, 10–30 forte, 30–100 muito forte, > 100 extrema; o inverso é a favor de H₀.
- **Testes t bayesianos**: "score: BF₁₀ = 4,36: evidência moderada a favor de H₁ (há diferença) (os dados são 4,36 vezes mais prováveis sob H₁ do que sob H₀)". A interpretação é sempre sobre BF₁₀: com BF₀₁ ou log(BF₁₀) na tabela, o valor é convertido. Com hipótese unilateral, fala de "H₁ (unilateral)".
- **ANOVA bayesiana**: uma nota por efeito, sobre o **BF de inclusão** ("bloco: BF de inclusão = 3,01: evidência moderada a favor de incluir o efeito no modelo"; interação mostrada como "A × B"). Só na escala BF₁₀ (em BF₀₁ o JASP muda o sentido da coluna e não interpretamos).
- Lê a tabela já exibida: **nenhuma execução extra**. `AnalysisRun` ganhou a prop `notes` (substitui `assumptions`) que liga os avisos de pressupostos e a interpretação juntos; só a aba Análise as usa.

## Verificado
`vitest` 176 (23 novos: limiares, escalas, formatação, notas, agrupamento), `pytest` 186, `e2e:all` 6 suítes verdes (grupos no seletor e no relatório; interpretação do t bayesiano com 4,36 = moderada; BF₀₁ na tabela mantém a nota em BF₁₀; BF de inclusão da ANOVA).
Armadilhas do e2e: `innerText` devolve o texto já em maiúsculas quando o CSS usa `text-transform` (usar `textContent`); a aba Análise é carregada sob demanda, então esperar um elemento dela antes de conferir.

## Pendências
- A interpretação do BF de inclusão não cobre `BF01`/`LogBF10`; a ANOVA bayesiana não interpreta a comparação entre modelos (melhor modelo × nulo).
- Faltam notas interpretativas para outras análises (ex.: tamanho de efeito de Cohen).

---

# Fatia 6.9 — ANOVA de medidas repetidas ✅

Catálogo: **15 análises** (grupo "Comparação de médias"). `AnovaRepeatedMeasures` (jaspAnova) entra no registro fechado do `engine.R` (rebuild do worker; **sem** remendo de `modelTerms`: o modelo completo, com a interação tempo × grupo, é o que se espera em medidas repetidas).

## Formulário
- **Formato largo**: uma coluna por medida. O usuário marca as colunas **na ordem dos níveis** (a ordem da marcação é a ordem dos níveis; a tela mostra "Ordem: t1 → t2 → t3", slot `ordered`). Os níveis do fator levam o nome das colunas.
- **Um fator intra-sujeito**, com nome livre (item novo `text`; ex.: "tempo"; não pode ser vazio nem igual a uma coluna escolhida). **Fatores entre-sujeitos** opcionais (delineamento misto).
- Esfericidade: teste de Mauchly e correções (nenhuma, Greenhouse-Geisser, Huynh-Feldt); estatísticas: descritivas, η² parcial, η² generalizado, ω²; comparações dois a dois dos níveis (Holm/Bonferroni; testes t pareados com erro **não agrupado**, df = n − 1).
- `derive` monta `repeatedMeasuresFactors`, `withinModelTerms`, `betweenModelTerms`, `effectSizeEstimates` e `postHocTerms`; `parse` recupera nome do fator e post hoc de blocos salvos (ida e volta testada).
- **Aviso automático de esfericidade** (mecanismo da 6.5): se Mauchly p < 0,05, a nota sugere Greenhouse-Geisser com o ε.

## Conferido contra o R puro (`medidas_repetidas.csv`: 24 sujeitos, 3 tempos, 2 grupos)
`aov(y ~ tempo * grupo + Error(sujeito/tempo))` (F, p, gl, SQ de tempo, grupo e interação); Mauchly (W, χ², gl, p), ε de Greenhouse-Geisser e de Huynh-Feldt calculados à mão a partir da covariância dos contrastes de Helmert (agrupada por grupo no misto); p corrigido = `pf(F, gl·ε, glres·ε)`; post hoc = `t.test(paired = TRUE)` + `p.adjust`; η² parcial = SQ/(SQ + SQres).

## Verificado
`vitest` 179 (3 novos + ordem do catálogo), `pytest` 189 (3 novos), `e2e:all` 6 suítes verdes (análises: ordem dos níveis, F/GG/HF/Mauchly iguais ao R, nota de esfericidade, delineamento misto, post hoc, nome do fator vazio).

## Pendências
- **Só um fator intra-sujeito** (o JASP aceita vários, com níveis combinados na ordem das colunas); sem contrastes, médias marginais, gráficos de perfil nem teste de Levene para os grupos (o Friedman foi feito na 6.10).
- O seletor de fatores entre-sujeitos oferece colunas de identificação (ex.: `sujeito`, 24 níveis); vale esconder colunas com tantos níveis quanto linhas.
- Formato longo (uma linha por medida) não é suportado: exige pivotar o dataset (SQL, aba Consulta SQL → "Salvar como dataset").

---

# Fatia 6.10 — teste de Friedman e post hoc de Conover ✅ (sem mudança no motor)

Friedman é **opção da `AnovaRepeatedMeasures`** (`friedmanWithinFactor`, `conoverTest`), então entra no formulário da 6.9, na seção "Não paramétrico" (nenhum rebuild do worker).

- **Teste de Friedman** (desligado por padrão): χ², gl, p e W de Kendall; **post hoc de Conover** (Bonferroni e Holm) só aparece com o Friedman ligado. `conover` e `friedman` são toggles locais; `derive` só envia `conoverTest` se o Friedman estiver ligado (sem opção órfã).
- **Ignora os grupos**: com o fator entre-sujeitos como `friedmanBetweenFactor` o Conover do JASP devolve `NaN` (verificado), então o teste vale para todos os sujeitos juntos (o rótulo avisa). Os fatores entre-sujeitos continuam valendo na ANOVA paramétrica da mesma execução.
- Conferido contra o R (`friedman.csv`: 20 sujeitos, 3 condições, empates): `friedman.test` (χ², gl, p), W = χ²/(n(k−1)), somas de postos, e o Conover pela fórmula de Conover (1999): t = (R_i − R_j)/√(2(n·ΣΣr² − ΣR_j²)/((n−1)(k−1))), gl = (n−1)(k−1), p bilateral + Bonferroni/Holm.
- Descoberta: na fixture degenerada da 6.9 (todo sujeito t1 < t2 < t3) o JASP dá W = 1 e t = ∞ no Conover; por isso o Friedman tem fixture própria.
- **Descoberta de produto**: colunas de inteiros com poucos valores distintos são inferidas como **ordinais** (aqui `c1`, 8 valores) e não aparecem como medidas repetidas (que exigem escalar). A fixture usa meio ponto (mesmos postos) para ficar escalar.

## Verificado
`vitest` 180 (1 novo), `pytest` 190 (1 novo), `e2e:all` 6 suítes verdes (análises: Friedman e Conover pela interface com os números do R).

## Pendências
- ~~**Dados ordinais inteiros (Likert) não entram como medidas repetidas**~~ — resolvido na 6.11 (abaixo). Texto original: é exatamente o público do Friedman. Resolver exige aceitar `ordinal` no slot e tratar no motor (`load_dataset` converte ordinais em fator; para o Friedman/RM deveriam ir como número) ou orientar o usuário a marcar a coluna como escalar na aba Dados. Hoje a mensagem só aparece quando não há nenhuma candidata.
- Friedman por grupo (estratificado) não é suportado.

---

# Fase 6.11 — dados ordinais numéricos (Likert) e correção da regressão com um preditor ✅

## Problema
Inteiros com poucos valores distintos (≤ 10, ex.: escala Likert 1–5) são inferidos como **ordinais** (`infer_measurement`) e **não apareciam** em nenhum campo "escalar" (t, ANOVA, ANCOVA, regressão, medidas repetidas…). O usuário só via "Nenhuma coluna escalar disponível", ou a coluna sumia da lista sem explicação.

## Decisão e prova
Antes de mexer no motor, conferi **cada papel escalar contra o R puro** com a coluna ordinal chegando ao worker como **fator**: t de uma amostra, pareado e independente, t bayesiano, ANOVA, ANCOVA (covariável), regressão linear (como covariável e como dependente), logística (covariável), medidas repetidas e Friedman. **Todos idênticos ao R.** Motivo: o JASP lê cada variável **pelo papel** que ela tem na análise (converte para numérico sozinho). Logo **a API e o motor não mudam** para isso, e relatórios/dashboards herdam o comportamento (as opções salvas já citam as colunas); o bloqueio era só o formulário.

## O que mudou
- `candidates()` (`lib/analyses.ts`): em campos que pedem **escalar** (e não aceitam ordinal), entram também colunas **ordinais com tipo numérico** (`ordinalAsScale`, `isNumericDtype`). Ordinal de **texto** (rótulos) e **nominal numérica** continuam fora; campos de fator, correlação e descritivas (que já aceitavam ordinal) não mudam.
- **Ordem:** as escalares genuínas vêm primeiro; o preenchimento automático nunca escolhe uma Likert antes de uma escalar.
- **Rótulo explícito** nas listas: "c1 (ordinal, 8 valores: tratada como escalar)".
- Consequência assumida: inteiros que são **códigos de grupo** (ex.: `tratamento` 1–8, `bloco`) também são oferecidos como covariável, com o rótulo acima; ao marcá-los como fator, somem da lista de covariáveis.

## Bug do motor encontrado no caminho (existia desde a Fase 2): regressão com UM preditor
`jaspTools` serializa as opções com `toJSON(auto_unbox = TRUE)`: `components: ["altura"]` chegava ao QML como o escalar `"altura"` e a **regressão linear e a logística com uma só covariável ficavam com o modelo VAZIO** (R² = 0, só o intercepto), **sem erro**. Nunca apareceu porque todos os testes usavam dois preditores. Correção em `engine.R` (`protect_components`: `I()` nos `components` de comprimento 1, que o `toJSON` não "desembrulha"; rebuild do worker). Agora `produtividade ~ altura`: R² = 0,0577, coeficientes iguais ao `lm`/`glm`.

## Verificado
`pytest` 196 (6 novos: regressão e logística com um preditor, e um teste por papel escalar com coluna Likert vs R), `vitest` 182 (2 novos), `e2e:all` 6 suítes verdes (análises: regressão com um preditor, Friedman/Conover e t de uma amostra sobre a coluna ordinal, rótulo, ordem e desaparecimento da lista).

## Pendências
- Todo inteiro com ≤ 10 valores é oferecido como candidato escalar: não há como distinguir "Likert" de "código de grupo". Alternativa futura: aviso na aba Dados.
- Regressão/logística com **fatores** de um nível só e `modelTerms` com mais de um bloco continuam sem teste.

