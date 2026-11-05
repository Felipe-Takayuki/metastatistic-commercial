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
- **Verificação automática de pressupostos** com avisos na saída continua pendente.

