# Fase 8 (projeto) — transformações de dados, estilo Power Query ✅ fatias 8.1 + 8.2 (2026-11-06)

Plano completo (aprovado em 2026-11-06, ordem: 8.1+8.2 → 8.3 → 8.4 → 8.5 → 8.6). Esta entrega junta **8.1 (base e passos de coluna/linha)** e **8.2 (colunas calculadas)**.
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
