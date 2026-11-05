# Supervisor HTTP (plumber) do worker. NÃO carrega o JASP: comanda um processo R filho persistente (callr) que o carrega.
#   - tempo limite por análise: estourou -> o filho é morto (SIGKILL) e recriado, e o worker segue vivo;
#   - isolamento: se o filho cair (segfault, falta de memória), o supervisor percebe, responde 500 e recria;
#   - o filho novo é aquecido em segundo plano logo após a morte do anterior (a próxima análise espera só o que faltar).
# (fork do processo com JASP carregado NÃO funciona: o Qt trava com "QThreadPipe: internal error".)
suppressMessages({ library(plumber); library(callr); library(jsonlite) })

DEFAULT_TIMEOUT_S <- as.numeric(Sys.getenv("ANALYSIS_TIMEOUT_S", "60"))
MAX_TIMEOUT_S     <- as.numeric(Sys.getenv("ANALYSIS_MAX_TIMEOUT_S", "300"))
WARMUP_TIMEOUT_S  <- 420   # vários módulos JASP são instalados/carregados a cada partida do motor

ENGINE <- new.env()
ENGINE$rs <- NULL          # sessão R filha
ENGINE$warming <- FALSE    # TRUE: sessão criada, aquecimento em andamento
ENGINE$restarts <- 0L
ENGINE$modules <- character()   # módulo/análise -> "ok" ou o motivo da falha no aquecimento

log_msg <- function(...) message(format(Sys.time(), "%H:%M:%S"), " [worker] ", ...)
now <- function() proc.time()[["elapsed"]]

# Espera o resultado de uma chamada já iniciada em `rs$call()`, com prazo. Nunca bloqueia além dele.
wait_call <- function(rs, timeout_s) {
  deadline <- now() + timeout_s
  repeat {
    left <- deadline - now()
    if (left <= 0) return(list(kind = "timeout"))
    ms <- as.integer(max(1, ceiling(min(left, 0.5) * 1000)))   # callr exige inteiro
    pr <- tryCatch(rs$poll_io(ms), error = function(e) NULL)
    if (is.null(pr)) return(list(kind = "crashed"))
    if (identical(unname(pr[["process"]]), "ready")) break
    if (!rs$is_alive()) return(list(kind = "crashed"))
  }
  res <- tryCatch(rs$read(), error = function(e) NULL)
  if (is.null(res)) return(list(kind = "crashed"))
  if (!is.null(res$error)) {
    # Quando o filho é morto (SIGKILL, falta de memória), o callr relata isso como erro de leitura.
    # Distingue: processo morto = queda (recria o motor); processo vivo = erro da função (sessão segue válida).
    dead <- !rs$is_alive()
    if (!dead) { Sys.sleep(0.1); dead <- !rs$is_alive() }   # o processo pode levar um instante para ser reconhecido como morto
    if (dead) return(list(kind = "crashed"))
    return(list(kind = "error", message = conditionMessage(res$error)))
  }
  list(kind = "ok", value = res$result)
}

kill_engine <- function() {
  if (!is.null(ENGINE$rs)) try(ENGINE$rs$kill(), silent = TRUE)
  ENGINE$rs <- NULL
  ENGINE$warming <- FALSE
}

warm_fn <- function() { source("/app/engine.R"); init_jasp() }   # devolve c(analise = "ok" | "FALHOU: ...")

# Guarda o resultado do aquecimento e deixa no log o que não subiu (as demais análises seguem funcionando).
note_warm <- function(result) {
  ENGINE$modules <- result
  bad <- names(result)[result != "ok"]
  if (length(bad)) for (a in bad) log_msg("aquecimento de ", a, ": ", result[[a]])
}

# Cria a sessão filha e DISPARA o aquecimento sem esperar.
spawn_engine <- function() {
  ENGINE$restarts <- ENGINE$restarts + 1L
  log_msg("iniciando motor (", ENGINE$restarts, ")")
  # stdout/stderr do motor: o Qt do JASP escreve muito aviso de QML por análise. Já se suspeitou de buffer cheio sem leitura
  # (escrita bloqueada em socket, CPU congelada), mas isso NUNCA foi provado: a reprodução mínima não trava e a config abaixo
  # passou 540 ANOVAs distintas (2 em paralelo) sem um único timeout. Não há dreno aqui de propósito; o teste de resistência
  # (tests/test_analyses_integration.py::test_endurance_*) é a guarda caso o travamento volte.
  rs <- callr::r_session$new(options = callr::r_session_options(stdout = NULL, stderr = NULL), wait = TRUE)
  rs$call(warm_fn)
  ENGINE$rs <- rs
  ENGINE$warming <- TRUE
}

# Garante um motor pronto (espera o aquecimento, se estiver em andamento). Devolve a sessão ou NULL.
ensure_engine <- function() {
  if (!is.null(ENGINE$rs) && !ENGINE$rs$is_alive()) { log_msg("motor morreu fora de uma análise; recriando"); kill_engine() }
  if (is.null(ENGINE$rs)) spawn_engine()
  if (ENGINE$warming) {
    out <- wait_call(ENGINE$rs, WARMUP_TIMEOUT_S)
    if (!identical(out$kind, "ok")) { log_msg("falha no aquecimento do motor: ", out$kind, " ", out$message %||% ""); kill_engine(); return(NULL) }
    ENGINE$warming <- FALSE
    note_warm(out$value)
    log_msg("motor pronto")
  }
  ENGINE$rs
}

# Confere SEM bloquear se o aquecimento em segundo plano já terminou (o /health usa isto; senão o estado
# ficaria em "warming" até alguém pedir uma análise, e o health mentiria).
poll_warm <- function() {
  if (is.null(ENGINE$rs) || !ENGINE$warming) return(invisible())
  pr <- tryCatch(ENGINE$rs$poll_io(0L), error = function(e) NULL)
  if (is.null(pr) || !ENGINE$rs$is_alive()) { log_msg("motor morreu durante o aquecimento"); kill_engine(); return(invisible()) }
  if (identical(unname(pr[["process"]]), "ready")) {
    out <- wait_call(ENGINE$rs, 5)   # o resultado já está disponível
    if (identical(out$kind, "ok")) { ENGINE$warming <- FALSE; note_warm(out$value); log_msg("motor pronto") }
    else { log_msg("falha no aquecimento do motor: ", out$kind); kill_engine() }
  }
  invisible()
}

`%||%` <- function(a, b) if (is.null(a)) b else a

#* @plumber
function(pr) {
  pr$setErrorHandler(function(req, res, err) {
    msg <- conditionMessage(err)
    bad <- grepl("lexical error|parse error|premature EOF|unexpected", msg, ignore.case = TRUE)
    res$status <- if (bad) 400L else 500L
    list(status = "error", message = if (bad) "invalid JSON body" else "internal error")
  })
}

ensure_engine()   # aquece antes de aceitar tráfego (como antes: o worker só fica "pronto" quando o JASP está carregado)

#* @get /health
#* @serializer json list(auto_unbox = TRUE)
function() {
  # Saúde de verdade: se o motor morreu enquanto ninguém o usava, recria agora (aquece em segundo plano),
  # em vez de a próxima análise pagar a partida a frio.
  if (!is.null(ENGINE$rs) && !ENGINE$rs$is_alive()) {
    log_msg("motor morreu fora de uma análise (detectado no health); recriando")
    kill_engine(); spawn_engine()
  }
  poll_warm()
  state <- if (is.null(ENGINE$rs)) "cold" else if (ENGINE$warming) "warming" else "ready"
  list(status = "ok", engine = state, restarts = ENGINE$restarts, modules = as.list(ENGINE$modules))
}

#* @post /run
#* @serializer json list(auto_unbox = TRUE, digits = NA, null = "null", na = "null")
function(req, res) {
  reply <- function(code, body) { res$status <- code; body }
  body <- tryCatch(jsonlite::fromJSON(req$postBody, simplifyVector = FALSE), error = function(e) NULL)
  if (is.null(body) || !is.list(body)) return(reply(400L, list(status = "error", message = "invalid JSON body")))

  timeout_s <- suppressWarnings(as.numeric(body$timeout_s %||% DEFAULT_TIMEOUT_S))
  if (length(timeout_s) != 1 || is.na(timeout_s)) timeout_s <- DEFAULT_TIMEOUT_S
  timeout_s <- min(max(timeout_s, 0.05), MAX_TIMEOUT_S)   # teto: um cliente não pode pedir um limite absurdo
  body$timeout_s <- NULL

  rs <- ensure_engine()
  if (is.null(rs)) return(reply(503L, list(status = "error", code = "engine_unavailable", message = "the statistical engine could not start; try again shortly")))

  # Qualquer falha inesperada aqui deixaria a sessão num estado em que não se pode confiar ("R session busy"
  # em todas as chamadas seguintes): o motor é morto e recriado, nunca reaproveitado.
  out <- tryCatch({
    rs$call(function(b) run_request(b), list(b = body))
    wait_call(rs, timeout_s)
  }, error = function(e) list(kind = "supervisor_error", message = conditionMessage(e)))

  switch(out$kind,
    ok = reply(out$value$http, out$value$body),
    timeout = {
      log_msg("análise excedeu ", timeout_s, " s; matando o motor")
      kill_engine(); spawn_engine()      # o novo motor aquece em segundo plano
      reply(504L, list(status = "error", code = "timeout", message = sprintf("analysis exceeded the %g s limit and was stopped", timeout_s)))
    },
    crashed = {
      log_msg("motor caiu durante a análise; recriando")
      kill_engine(); spawn_engine()
      reply(500L, list(status = "error", code = "engine_crashed", message = "the statistical engine crashed while running this analysis (possibly out of memory); it was restarted"))
    },
    supervisor_error = {
      log_msg("erro inesperado no supervisor: ", out$message, "; recriando o motor")
      kill_engine(); spawn_engine()
      reply(500L, list(status = "error", code = "engine_error", message = "internal error while talking to the statistical engine; it was restarted"))
    },
    reply(500L, list(status = "error", message = out$message %||% "internal error")))
}
