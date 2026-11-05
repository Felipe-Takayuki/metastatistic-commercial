# Fase 6 (projeto) — catálogo estatístico, fatia 6.1 ✅ (2026-11-05)

Corresponde ao "primeiro lote de análises" da Fase 2 do PLAN.md. Antes: teste t independente, ANOVA, correlação, regressão linear e qui-quadrado.
Agora o catálogo tem **8 análises** (aparecem no seletor da aba Análise, nos blocos de relatório e nos tiles de dashboard):

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
