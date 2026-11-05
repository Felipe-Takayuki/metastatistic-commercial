# Fase 2 — fatia 2.1: execução robusta de análises ✅ (2026-11-04)

Problema que motivou: o worker R era um processo único, de uma análise por vez e **sem tempo limite**. Uma análise lenta
bloqueava todas as outras, e uma análise travada (ou o R caindo) deixava o worker inútil para sempre. Isso apareceu como
travamento intermitente nos testes e2e.

## Arquitetura
```
navegador → API (FastAPI)
              ├─ cache de resultados (LRU 256 entradas / 64 MB) + deduplicação de pedidos idênticos em andamento
              └─ pool: fila FIFO (máx. 20 esperando, até 90 s) → worker 1 | worker 2 | …
                                                                  │
worker = supervisor R leve (plumber, NÃO carrega o JASP) ── callr ──▶ motor R filho (carrega o JASP)
         · tempo limite por análise (60 s): estourou → SIGKILL no motor, 504, motor novo aquece em segundo plano
         · motor caiu (falta de memória, segfault) → 500 `engine_crashed`, recriado sozinho
         · /health verifica de verdade e cura um motor morto ocioso
```
Cada worker atende **uma** análise por vez; paralelismo = nº de contêineres (hoje 2, cada um ~350 MB em repouso, limite 1 GB).

## Decisões (e o que foi descartado)
- **Fork do processo com JASP carregado NÃO funciona**: o Qt trava (`QThreadPipe: internal error`). Testado num contêiner descartável antes de construir qualquer coisa. Por isso o motor é um processo filho **iniciado do zero** (`callr::r_session`), não um fork.
- **Sem Redis/fila externa por enquanto**: uma API de processo único com fila em memória basta e é mais simples de testar. Se a API virar várias réplicas, a fila e o cache precisam ir para fora do processo.
- **Pedidos idênticos rodam uma vez**: a chave do cache inclui análise, dataset, opções, colunas lidas **e níveis de medida** (mudar nominal→ordinal invalida o resultado). Só resultados `complete` são cacheados; erros e timeouts não.
- **Cancelamento**: quem desiste enquanto espera na fila sai dela; quem desiste *depois* de enviado **não** libera o slot antes da hora (o worker continua rodando a análise). Se **todos** os interessados num resultado desistem, o trabalho é cancelado.
- **Reenvio seguro**: só falha de *conexão* (o pedido nunca chegou) é reenviada a outro worker; timeout de leitura não é reenviado (a análise pode estar rodando). Worker inalcançável fica 10 s fora de circulação; se todos caem, a fila é acordada com erro em vez de esperar 90 s.
- **Mensagens claras**: 429 fila cheia · 503 motor ocupado/indisponível · 504 "excedeu o limite de 60 s e foi interrompida" · 502 "o motor caiu… foi reiniciado". A interface, depois de 8 s esperando, mostra "N de M motores ocupados, K na fila".

## Verificado
- `pytest` 112 (API + integração), incluindo: concorrência nunca acima de 1 por worker, FIFO, fila cheia, espera longa, desistência na fila e durante a execução, reenvio, todos fora, cache/dedup/cancelamento/LRU, chave de cache.
- Contra a pilha real (2 workers): rajada de 6 análises → 2 ocupados + 4 na fila, todas corretas; 5 idênticas → 1 execução; a 6ª vem do cache; timeout forçado → 504, motor recriado sozinho e `/health` fiel; derrubar um worker → tudo continua funcionando, e ele é readmitido e volta a trabalhar.
- Motor morto **no meio** da análise (SIGKILL): `engine_crashed` em ~0,6 s, volta a `ready` sozinho em ~17 s, sem zumbis, memória estável (~350 MB) após várias reinicializações.
- `init: true` resolveu o encerramento lento (parada do contêiner: ~10 s → 0,2 s); `restart: unless-stopped` religa um supervisor morto.

## Bugs achados no caminho
- `poll_io` exige milissegundos **inteiros** (valor fracionário estourava só com prazos curtos). A exceção, ocorrendo depois de a chamada já ter sido enviada, **deixava a sessão em "R session busy" para sempre** → toda falha inesperada agora mata e recria o motor, nunca o reaproveita.
- Queda do motor vinha como erro de leitura genérico e o motor só era recriado na requisição seguinte (partida a frio de 11–21 s dentro dela) → agora é `engine_crashed` com recriação imediata.
- `/health` ficava preso em "warming" (nunca checava o fim do aquecimento) → agora confere sem bloquear.
- JSON inválido virava 500 do plumber → agora 400.
- Mensagens diferentes para o mesmo problema ("motor indisponível") conforme o caminho interno → unificadas.
- (Meus próprios testes) detector de PID que pegou o `tini` e matou o supervisor; rajadas que repetiam opções e vinham do cache sem eu perceber → as verificações passaram a provar o que dizem provar.

## Pendências conhecidas
- Aquecimento do motor após uma queda: ~15–20 s (a primeira análise depois disso espera o que faltar).
- Cada worker ainda é de uma análise por vez; análises longas e frequentes pedem mais contêineres (ou um pool de motores por contêiner).
- Cache e fila vivem na memória da API: reiniciar a API os limpa; várias réplicas da API não compartilham nada.
- O cache não conhece a versão do módulo JASP: trocar o módulo exige reiniciar a API (senão resultados antigos continuam sendo servidos).
- Sem progresso incremental (percentual) nem cancelamento explícito pelo usuário de uma análise já em execução.
- Limite de memória de 1 GB por worker: datasets enormes derrubam o motor (detectado e informado), em vez de rodar.
- Sem autenticação nem cotas por usuário: qualquer cliente pode encher a fila (limite global de 20).
