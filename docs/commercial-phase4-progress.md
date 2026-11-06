# Fase Comercial 4 — Orquestrador Estatístico e Engine B (Pure Python) ✅ CONCLUÍDA (2026-11-06)

Quarta fase da transformação comercial do **Metastatistic Commercial**. Introduz o microsserviço `stat-orchestrator` para despacho assíncrono com QoS e priorização VIP, cache determinístico de análises, roteamento inteligente entre motores (*Dual-Engine*) e o desenvolvimento do **Engine B comercial** em Python puro/SciPy (100% livre de código AGPL e compatível com as diretrizes da APA 7th).

---

## 1. O Que Foi Construído e Entregue

### 1.1 Microsserviço de Orquestração Estatística (`services/stat-orchestrator`)
Localizado na porta `8003`, desacopla completamente a execução matemática pesada da API de dados:

- **Fila Assíncrona com Priorização por Nível de Serviço (QoS)**:
  - Implementada com `asyncio.PriorityQueue` gerenciando instâncias de `Job`.
  - **Segregação de Prioridades**:
    - Prioridade 0 (VIP / Enterprise): requisições corporativas furam a fila e são atendidas imediatamente pelos workers disponíveis.
    - Prioridade 1 (Standard / Community / Team): requisições padrão processadas conforme capacidade concorrente.
  - Controle de concorrência com semáforo assíncrono (`concurrency_limit`).
  - Ciclo de vida completo dos jobs com status rastreável: `queued` ➔ `running` ➔ `completed` / `failed`.
- **Cache Determinístico LRU de Resultados (`cache.py`)**:
  - Geração de chave hash SHA-256 baseada na tupla determinística:
    ```json
    {
      "tenant_id": "...",
      "analysis": "...",
      "dataset_id": "...",
      "options": { ... },
      "columns": [ ... ]
    }
    ```
  - Duplo teto de limite: contagem máxima de entradas (padrão 256) e volume de memória em bytes (padrão 64 MB).
  - Evicção automática dos itens menos recentemente utilizados (*Least Recently Used*).
  - Métricas em tempo real de `hits`, `misses` e taxa de acerto expostas em `GET /analyses/status`.
- **Dual-Engine Router (`router.py`)**:
  - Mecanismo que seleciona dinamicamente qual motor deve processar a análise:
    - Modo `'py'` ou `'engine_b'`: direciona forçadamente para o motor Python puro.
    - Modo `'r'` ou `'engine_a'`: direciona para os workers legados de R/JASP.
    - Modo `'auto'` (padrão): se o cálculo estiver implementado no Engine B comercial, executa em Python; caso contrário, despacha com transparência para o Engine A.
- **APIs Síncronas e Assíncronas**:
  - `POST /analyses/run`: execução síncrona com timeout (aguarda o job completar ou puxa do cache).
  - `POST /jobs/submit`: submissão assíncrona não-bloqueante retornando `job_id`.
  - `GET /jobs/{job_id}`: consulta do estado de progresso e resultado.
  - `GET /analyses/status`: monitoramento da saúde dos motores, tamanho da fila e estatísticas do cache.

### 1.2 Engine B Comercial (Pure Python / SciPy / 100% Não-AGPL)
Implementação em `app/engines/python_engine.py` de algoritmos matemáticos e inferenciais com dependências estritamente comerciais (BSD / Apache / MIT: NumPy, SciPy, PyArrow):

- **Análises Suportadas Nativa e Fielmente**:
  1. **Estatísticas Descritivas (`descriptives`)**:
     - Cálculo de N válido, N faltante, Média, Mediana, Desvio Padrão, Variância, Erro Padrão da Média, Mínimo, Máximo, IQR (intervalo interquartil), Assimetria (*Skewness*) e Curtose (*Kurtosis*).
  2. **Teste t Independente (`ttest_independent`)**:
     - Suporte a Teste t de Student clássico e Teste de Welch (correção para variâncias desiguais).
     - Estatística $t$, graus de liberdade $df$, p-valor bicaudal, diferença de médias e Erro Padrão.
     - Tamanho do efeito: $d$ de Cohen e intervalo de confiança a 95%.
     - Tabela complementar de estatísticas de grupo (N, Média, DP, E.P.).
  3. **Teste t de Uma Amostra (`ttest_onesample`)**:
     - Comparação contra valor de teste $H_0$ hipotético configurável.
     - Estatística $t$, $df$, p-valor bicaudal, diferença média e $d$ de Cohen.
  4. **ANOVA One-Way (`anova`)**:
     - Decomposição em Soma de Quadrados (SS), Graus de Liberdade (df), Quadrado Médio (MS), Estatística $F$ de Snedecor e p-valor entre grupos (*Between Groups*) e dentro dos grupos (*Within Groups / Residual*).
  5. **Correlação de Pearson (`correlation`)**:
     - Matriz de correlação com coeficiente $r$ de Pearson, $p$-valor exato e limites inferior/superior de confiança a 95% via transformação $z$ de Fisher.
- **Formatação Rigorosa de Tabelas APA 7th**:
  - Todas as saídas são estruturadas com a árvore padrão:
    - `title`: Título formatado em itálico/estilo acadêmico APA.
    - `schema.fields`: Nomes técnicos, títulos com notação matemática ($t$, $df$, $p$, $d$, $F$, $r$) e formatação de casas decimais (`dp:2`, `dp:3`, `p:.001`).
    - `data`: Matriz de dados com valores numéricos de alta precisão.
    - `footnotes`: Notas de rodapé automáticas (*Nota.*) identificando a execução pelo Engine B comercial e esclarecendo níveis de significância ($*p < .05$, $**p < .01$, $***p < .001$).

### 1.3 Integração e Roteamento no API Gateway
- O `services/gateway` foi atualizado para despachar qualquer chamada em `/api/v1/analyses/*` e `/api/v1/jobs/*` diretamente para o `stat-orchestrator:8003`.
- O healthcheck agregado do gateway valida a disponibilidade do orquestrador analítico.

---

## 2. Decisões Tomadas e Armadilhas Contornadas

1. **Eliminação do Risco Jurídico de Contaminação AGPL-3.0**:
   - *Desafio*: Clientes de grande porte (bancos, seguradoras, pharma) exigem garantias contratuais de imunidade de propriedade intelectual (*clean IP indemnification*) e proíbem componentes sob licença AGPL em seus ambientes corporativos.
   - *Solução*: O Engine B foi escrito inteiramente em Python padrão com bibliotecas permissivas (SciPy, NumPy), sem importar nem vincular código do R ou JASP Desktop. Com o Dual-Engine Router, esses clientes podem operar configurando `DEFAULT_ENGINE=py`, obtendo uma pilha analítica 100% proprietária e comercialmente segura.
2. **Consistência de Schema JSON para o Frontend**:
   - *Desafio*: O frontend React já possuía componentes sofisticados de renderização de tabelas e notas compatíveis com o formato do JASP (`AnalysisTableAPA`).
   - *Solução*: O Engine B produz exatamente a mesma estrutura JSON (`schema`, `data`, `footnotes`) adotada pelo motor R. O frontend exibe os resultados com o mesmo rigor visual sem precisar de nenhuma linha de código condicional para diferenciar os motores.
3. **P-valores sem SciPy Instalado (Ambientes Ultra-Minimalistas)**:
   - *Desafio*: Em ambientes sem binários do SciPy compilados, a importação poderia falhar.
   - *Solução*: `python_engine.py` conta com aproximações matemáticas nativas para distribuições $t$ e normal via `math.erf` como fallback defensivo, embora o ambiente de produção utilize SciPy completo.

---

## 3. Verificação e Testes

A suíte completa de testes unitários e de integração foi executada com sucesso:

| Teste | Quantidade | Status | Detalhes |
|---|---|---|---|
| `stat-orchestrator` | **13 testes** | ✅ PASSOU | Cache determinístico (hits/misses/evicção), priorização de fila VIP, APA table builder, Engine B (descritivas, t-test independente, t-test uma amostra, ANOVA, correlação), Router ('auto', 'py', 'r'), rotas de API. |
| `gateway` | **7 testes** | ✅ PASSOU | Roteamento proxy para stat-orchestrator e healthcheck unificado. |
| `apps/api` | **330 testes** | ✅ PASSOU | Total compatibilidade com datasets e chamadas de persistência. |

---

## 4. Limitações Conhecidas

- Análises estatísticas bayesianas (ex.: Teste t Bayesiano, Fatores de Bayes $BF_{10}$) e modelos multivariados avançados (ex.: ANCOVA, Regressão Logística Multinomial) continuam delegados ao Engine A (R) através do roteador automático.
- A fila assíncrona do `stat-orchestrator` opera atualmente em memória de processo (`asyncio.PriorityQueue`). Para escalabilidade horizontal em múltiplos pods em cluster Kubernetes, ela será integrada a uma fila distribuída externa (RabbitMQ ou Redis Streams) na Fase 6.
