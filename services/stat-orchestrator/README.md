# Statistical Orchestrator Service (`stat-orchestrator`)

Microsserviço de orquestração estatística com suporte a Dual-Engine:
- **Engine A (R Worker Adapter)**: Encaminha requisições aos containers de workers R (`jaspTools` / `r-worker`).
- **Engine B (Pure Python / SciPy)**: Motor estatístico proprietário e comercialmente livre (100% não-AGPL), com formatação de tabelas e relatórios rigorosamente alinhados com a 7ª edição das normas APA (American Psychological Association).
- **Cache LRU Inteligente**: Armazenamento determinístico em memória indexado por tenant, análise, dataset e opções.
- **Fila Assíncrona com Prioridade**: Suporte a execução assíncrona com prioridades para clientes VIP Enterprise vs Standard e controle de concorrência.
