# Fase 8 (projeto) — transformações de dados, estilo Power Query ✅ fatias 8.1 a 8.4 (2026-11-06)

Plano completo (aprovado em 2026-11-06, ordem: 8.1+8.2 → 8.3 → 8.4 → 8.5 → 8.6). Feitas: **8.1 (base e passos de coluna/linha)**, **8.2 (colunas calculadas)**, **8.3 (por grupo e janela)** e **8.4 (reformatar e combinar, seção final)**.
Interface: aba **Transformar** (entre Dados e Consulta SQL), em http://localhost:8080 → Explorar.

## Como funciona
Uma **receita** é uma lista de passos (JSON) sobre um dataset de origem. O servidor a compila em **SQL com uma CTE por passo** (`__s0`, `__s1`…), roda no **mesmo sandbox das consultas do usuário** (só os datasets que ele lê, com filtro de linhas) e, ao salvar, passa por `derive.create_dataset_from_query` → Parquet novo. Por isso o resultado serve às análises do JASP (o motor R lê Parquet) e **herda as restrições de acesso da fase 7** sem código novo.
- O esquema (colunas e tipos reais) é descoberto passo a passo com `DESCRIBE` no DuckDB; os erros dizem o passo: `Passo 3 (sort): coluna não encontrada: 'nota1'`.
- Identificadores vão entre aspas duplas, valores viram literais tipados (número validado, data ISO, texto escapado). **Fórmula livre**: `sqlglot` + lista de permissões (operadores, CASE, ~30 funções escalares, CAST para número/texto/data); recusa subconsulta, agregação, janela, `*`, tabela qualificada, funções desconhecidas, vários comandos, tipos como STRUCT/INTERVAL.
- A receita fica guardada (`dataset_recipes`) com o dataset criado: a interface oferece **Reabrir receita**.

## Passos (18)
**Colunas**: escolher/remover, renomear, mudar tipo (valores inválidos viram vazios, `TRY_CAST`). **Linhas**: filtrar (14 operadores, E/OU, valor tipado pela coluna, vírgula decimal aceita), ordenar (vazios por último), remover duplicatas (mantém a 1ª e **a ordem original**), remover linhas vazias, preencher vazios (valor, média ou mediana, com aviso de que reduz a variância). **Nova coluna**: média/soma/mín./máx./contagem entre colunas (**ignora vazios**; opção "só linhas completas"), aritmética (÷0 → vazio), funções matemáticas (fora do domínio → vazio), condicional se/então/senão (tipos dos ramos checados), faixas (com rótulos automáticos ou próprios), substituir valores, texto (maiúsculas, minúsculas, aparar, tamanho), juntar colunas, parte de data (ano, trimestre, mês, dia, semana, dia da semana, ano-mês), fórmula livre.

## API
`POST /transforms/preview` (leitor) → prévia + `total_rows` + `sql` + esquema antes de cada passo · `POST /transforms/save` (editor; auditado; herda restrições; **preserva o nível de medida** que a pessoa escolheu na origem para colunas que seguem com mesmo nome e tipo) · `GET /transforms/recipes/{dataset_id}` (receita ou `null`; mesma resposta para "não existe" e "não pode ler").

## Decisões e armadilhas
- **`DISTINCT`/`QUALIFY` reordenam as linhas** (conferido no DuckDB): a remoção de duplicatas usa um índice oculto (`ROW_NUMBER() OVER ()`) para manter a ordem de aparição, que importa (colunas de bloco).
- **Sempre cria dataset novo**, nunca altera o original: as análises têm cache pelo id do dataset e as cópias filtradas por linha também; trocar o Parquet exigiria versionar os dados.
- **Receita salva por usuário com filtro de linhas** contém só as linhas dele (o derivado é restrito a ele e aos administradores, como na 7.4).
- Média entre colunas com `list_avg`: `list_avg([1, NULL, 3]) = 2`, enquanto `(a+b+c)/3` daria NULL.
- O rascunho de passos fica no `App` por dataset (não se perde ao trocar de aba); `GET /recipes` devolve 200+`null` em vez de 404 porque a interface pergunta a cada dataset aberto e o 404 poluiria o console.

## Verificado
`pytest` 250 (+55 em `tests/test_transforms.py`: **cada passo conferido contra cálculo independente em Python** — média/soma/mín./máx./contagem entre colunas com vazios, aritmética, log/raiz/arredondar, faixas, condicional, texto, partes de data, mediana e média para preencher; encadeamento; 14 mensagens de erro; 15 fórmulas hostis recusadas; escape de identificadores e valores maliciosos; salvar + receita + nível de medida; leitor só vê a prévia; origem restrita fica oculta e o derivado herda; filtro de linhas vale na prévia, na contagem e no que é salvo; auditoria), `vitest` 234 (+26, `lib/transforms.test.ts`), `tsc`/`vite build` limpos e **`npm run e2e:transform`** (21 checagens em navegador real, sem o motor R: média entre colunas, filtro, fórmula com erro apontando o passo e corrigida, reordenar, Ver SQL, salvar, reabrir a receita, rascunho que sobrevive à troca de aba). O e2e passou contra uma pilha sem login; a captura do erro foi conferida visualmente.
**Não reexecutados** (Docker parado): integração com o motor R e `e2e:all` (a aba nova não altera as telas antigas além de um item de aba e um estado no `App`). **Não verificado**: uma análise do JASP sobre um dataset recém-transformado (o Parquet é gerado pelo mesmo caminho do "Salvar como dataset" da aba SQL, já coberto pelo motor real).

## Limites desta entrega
- Sem agrupar/resumir, pivotar, mesclar (join) e acrescentar: **8.4**. Sem média por grupo, percentual do total, ranking, acumulado e média móvel: **8.3**. Sem medidas salvas (8.5) nem construtor visual de gráficos (8.6).
- A prévia mostra as primeiras 100 linhas e roda a receita inteira a cada mudança (com debounce); em datasets muito grandes e receitas longas pode ficar lenta (limite de 30 s por consulta, como no SQL).
- Editar uma receita nunca altera um dataset já salvo: salva-se outro.
- Receitas aceitam até 50 passos; fórmulas até 500 caracteres.

---

# Fatia 8.3 — colunas por grupo e janela ✅

Seis passos novos, grupo "Por grupo e janela" do menu. **A linha continua sendo uma linha** (o número de linhas não muda): ela ganha o valor do seu grupo ou da sua vizinhança.

| Passo | O que calcula |
|---|---|
| **Estatística do grupo** (`group_stat`) | média, soma, mínimo, máximo, contagem, mediana, desvio padrão do grupo, repetido em cada linha. "Agrupar por" vazio = tabela inteira |
| **Percentual do total** (`pct_total`) | 100 × valor ÷ soma do grupo (soma 100 em cada grupo) |
| **Posição no ranking** (`rank`) | maior ou menor = 1ª; empates com buraco (1,2,2,4), sem buraco (1,2,2,3) ou desempatados pela ordem das linhas; vazio fica sem posição |
| **Padronizar** (`zscore`) | (valor − média do grupo) ÷ desvio amostral do grupo; grupo de 1 linha ou sem variação = vazio |
| **Acumulado ou média móvel** (`running`) | soma/média/mín./máx./contagem acumulada, ou móvel de n linhas (opção "vazio até a janela encher"), com ordem própria dentro do grupo |
| **Diferença ou variação** (`lag`) | diferença, variação % ou valor da linha n atrás, por grupo e ordem |

## Decisões e armadilhas
- **Janela com `ORDER BY` reordena a saída no DuckDB** (conferido): todo passo de janela passa pelo índice oculto `__rn` e termina com `ORDER BY __rn`, então as linhas **nunca mudam de lugar**. O mesmo índice **desempata** acumulados e rankings, deixando-os determinísticos (empate na ordem escolhida = ordem original). `__rn` é nome reservado (o passo recusa uma coluna com esse nome, assim como a remoção de duplicatas).
- **`SUM` de inteiros vira `HUGEINT`, que o Parquet grava como `DOUBLE`** (conferido): a soma de colunas inteiras é convertida a `BIGINT` (soma por grupo, acumulada e também a "soma entre colunas" da 8.2), então a coluna continua inteira no dataset salvo.
- Soma/média/mín./máx. de **nada** (grupo só de vazios) é vazio, não 0; contagem é 0.
- **Média das médias** só é a média geral com grupos do mesmo tamanho: o formulário avisa. O resumo por grupo (uma linha por grupo) vem na 8.4.
- Valor vazio na coluna de grupo forma o seu próprio grupo (comportamento do `PARTITION BY`).

## Verificado
`pytest` 297 (+47 em `tests/test_transforms_window.py`, **cada passo contra cálculo independente em Python**: 7 estatísticas por grupo, tabela inteira e chave dupla, % do total somando 100, z-score com média 0 e desvio 1 por grupo, 3 métodos de ranking × 2 sentidos com empate e vazio, 5 acumulados, média móvel com e sem "janela cheia", ordem decrescente, `lag` (3 tipos × 1 e 2 linhas), encadeamento "média do grupo → desvio", janela depois de remover duplicatas e filtrar, 9 erros claros, limites, coluna `__rn`, salvar como dataset com tipos inteiros), `vitest` 238 (+4), `tsc` limpo e `e2e:transform` ampliado (média do grupo A = 6 e B = 6,5; ranking 1º/3º/sem posição; acumulado A = 9, 15, 23; ordem original preservada; descrições em português), passou em navegador real e a captura foi conferida.
**Não reexecutados** (Docker parado): integração com o motor R e `e2e:all`.

## Limites
- Sem **resumo por grupo** (uma linha por grupo), pivotar, mesclar e acrescentar: **8.4**. Sem medidas salvas (8.5) nem construtor visual de gráficos (8.6).
- Janela só por número de **linhas** (não por intervalo de tempo); sem média móvel centrada nem "ano contra ano".
- A coluna de ordem aceita até 5 critérios; "agrupar por" até 10 colunas.


---

# Fatia 8.4 — reformatar e combinar ✅

Cinco passos novos, grupo **"Reformatar e combinar"** do menu. Ao contrário da 8.3, aqui o **número de linhas muda** (resumir, pivotar, despivotar) ou entram **dados de outro dataset** (mesclar, acrescentar).

| Passo | O que faz |
|---|---|
| **Resumir por grupo** (`summarize`) | uma linha por grupo; 9 cálculos (nº de linhas, contagem, valores distintos, média, soma, mín., máx., mediana, desvio); sem grupo = a tabela vira uma linha |
| **Pivotar** (`pivot`, longo → largo) | cada valor distinto de uma coluna vira uma coluna; célula com mais de um valor usa "primeiro", soma, média, mín., máx. ou contagem; prefixo opcional |
| **Despivotar** (`unpivot`, largo → longo) | várias colunas viram pares (nome, valor); opção de descartar linhas sem valor |
| **Mesclar** (`join`) | ligar por 1 a 5 colunas com outro dataset: manter todas daqui (`left`), só as comuns (`inner`), todas (`full`) ou só as **sem** correspondência (`anti`); escolhe quais colunas trazer; sufixo se o nome já existir |
| **Acrescentar** (`append`) | empilha as linhas de outro dataset casando colunas **pelo nome**; coluna opcional "origem" com um rótulo para cada lado |

## Decisões e armadilhas
- **Ordem determinística**: grupos saem na ordem em que aparecem (`MIN(__rn)`), despivotar vai linha a linha e coluna a coluna, mesclar mantém a ordem da esquerda (as só-da-direita do `full` vão ao fim) e acrescentar põe as linhas daqui antes das do outro. `GROUP BY`/`UNION ALL` sozinhos não garantem isso.
- **Mesclar não duplica linhas em silêncio**: se o outro dataset tem chave repetida, o passo **recusa** ("há N chave(s) repetida(s)…") até a pessoa marcar "permitir várias correspondências" ou remover as duplicatas. O `anti` não precisa de chave única. Chaves vazias nunca se ligam (como no SQL).
- **Tipos precisam ser compatíveis** (número/texto/data/booleano): chaves de tipos diferentes, colunas de mesmo nome com tipos diferentes no acrescentar e colunas de tipos diferentes no despivotar dão erro com a instrução "converta o tipo antes", em vez de uma conversão escondida.
- **Pivotar descobre as colunas consultando os dados** (valores distintos, no máximo **40**; acima disso pede para filtrar). Nomes novos que colidam (`a` e `A`) ou colidam com as colunas de identificação são recusados. Valores vazios na coluna de nomes são ignorados.
- **Soma de inteiros continua inteira** (BIGINT), no resumo e no pivô; soma de nada é vazio, não 0.
- **Acesso**: o outro dataset passa pelo mesmo sandbox do usuário. Se ele não pode ler, a mensagem é a mesma de "não existe" (não confirma que existe e não vaza colunas); se há filtro de linhas, o passo usa a **cópia filtrada**; e o dataset salvo **herda a restrição de todos os datasets citados no SQL** (já era assim por `derive.source_ids`, agora com teste: origem aberta + outro restrito → derivado restrito).
- `compile_step` ganhou um parâmetro `Ctx` (conexão do sandbox, CTEs já montadas, usuário) para os passos que olham fora da tabela corrente. Colunas reservadas novas: `__o`, `__k`, `__rr`.

## Verificado
`pytest` 320 (+23 em `tests/test_transforms_reshape.py`, **cada passo contra cálculo independente em Python**: 9 agregações por grupo, tabela inteira e chave dupla, pivô com `first`/soma/média/contagem e prefixo, ida e volta despivotar → pivotar, 4 tipos de mesclagem, duas chaves, colunas escolhidas com sufixo, chave repetida recusada/aceita, acrescentar com colunas faltantes e com coluna de origem, mensagens de erro, limite de 40 colunas, nomes colidindo, encadeamento + salvar + receita, **outro dataset ilegível não vaza e o derivado herda a restrição**, **filtro de linhas vale no outro dataset**), `vitest` 243 (+5), `tsc`/`vite build` limpos e `npm run e2e:transform` (**22 checagens novas em navegador real**: resumo, mesclar, despivotar, pivotar de volta, acrescentar com origem e salvar; captura conferida).
**Não reexecutados**: integração com o motor R (`RUN_INTEGRATION`) e `e2e:all` (a aba só ganhou itens de menu e formulários). **Não verificado**: análise do JASP sobre um dataset reformatado.

## Limites
- Pivotar não tem "ordem das novas colunas" (saem em ordem alfabética/numérica do valor) nem pivô com várias colunas de valores.
- Mesclar não oferece direita (`right`) nem anti da direita; para isso, inverta os datasets. Não casa colunas por "parecido" (só igualdade exata).
- Acrescentar só casa por nome (sem mapear nomes diferentes: renomeie antes).
- Pré-existente, visto no e2e: se um dataset é **apagado enquanto outra requisição monta o sandbox**, a consulta pode falhar com 500 (`queries._sandbox` cria uma view para cada dataset legível). Só aparece em corrida; não tratado aqui.
- **Falta (ordem aprovada)**: 8.5 medidas salvas (sem materializar) → 8.6 construtor visual → tile/bloco. **Antes da 8.6**, simplificar a geração de gráficos: criar gráfico/KPI **sem precisar escrever SQL** (pedido do usuário).
