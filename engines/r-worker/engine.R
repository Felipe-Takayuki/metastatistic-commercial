# Motor estatístico: roda DENTRO do processo filho (callr), nunca no supervisor.
# O supervisor (runner.R) só repassa pedidos e impõe tempo limite; se o motor travar ou cair, é morto e recriado.
suppressMessages(library(jaspTools))

MODULES_DIR <- Sys.getenv("JASP_MODULES_DIR")

# Lista FECHADA do que a plataforma expõe: análise -> módulo JASP que a implementa.
ANALYSIS_MODULE <- c(
  TTestIndependentSamples = "jaspTTests", TTestPairedSamples = "jaspTTests", TTestOneSample = "jaspTTests",
  TTestBayesianIndependentSamples = "jaspTTests", TTestBayesianPairedSamples = "jaspTTests", TTestBayesianOneSample = "jaspTTests",
  Anova = "jaspAnova", Ancova = "jaspAnova", AnovaBayesian = "jaspAnova", AnovaRepeatedMeasures = "jaspAnova",
  Correlation = "jaspRegression", RegressionLinear = "jaspRegression", RegressionLogistic = "jaspRegression",
  ContingencyTables = "jaspFrequencies",
  Descriptives = "jaspDescriptives"
)
ALLOWED_ANALYSES <- names(ANALYSIS_MODULE)

# Uma análise descartável por módulo: faz o jaspTools instalar/carregar o módulo uma única vez por processo.
WARM_SPECS <- list(
  TTestIndependentSamples = list(df = data.frame(y = c(1, 2, 3, 4, 5, 6), g = factor(rep(c("a", "b"), each = 3))),
                                 opts = list(dependent = "y", group = "g")),
  Anova = list(df = data.frame(y = c(1, 2, 3, 4, 5, 7), g = factor(rep(c("a", "b"), each = 3))),
               opts = list(dependent = "y", fixedFactors = "g", modelTerms = list(list(components = "g")))),
  Correlation = list(df = data.frame(a = c(1, 2, 3, 4, 5, 6), b = c(2, 1, 4, 3, 6, 5)), opts = list(variables = c("a", "b"))),
  ContingencyTables = list(df = data.frame(g = factor(c("a", "a", "b", "b", "a", "b")), h = factor(c("x", "y", "x", "y", "y", "x"))),
                           opts = list(rows = "g", columns = "h")),
  Descriptives = list(df = data.frame(a = c(1, 2, 3, 4, 5, 7)), opts = list(variables = "a"))
)

# ---- Remendo: respeitar o `modelTerms` pedido ------------------------------------------------------------------
# O jaspTools::runAnalysis passa as opções pelo motor de QML do JASP (jaspSyntax), e o controle `modelTerms` (lista de
# interação) REPOVOA o modelo com TODAS as interações a partir de `fixedFactors`, sobrescrevendo o que enviamos. Isso
# inviabiliza modelos aditivos (ex.: delineamento em blocos casualizados: 1 observação por célula + interação = resíduo 0).
# Depois do replay, devolvemos ao `modelTerms` o que o usuário pediu, traduzindo os nomes de colunas para os codificados
# que o bridge devolve (pela posição em fixedFactors/dependent/…). Se algo der errado, segue SEM o remendo (nunca quebra).
REQ <- new.env()   # estado da requisição em curso: modelTerms pedido e nomes originais das variáveis
NAME_OPTIONS <- c("dependent", "fixedFactors", "randomFactors", "covariates", "factors")
# Só onde o problema existe (Anova e Ancova: controle de interação com fatores). No RegressionLinear/RegressionLogistic, `modelTerms` é uma lista de MODELOS (blocos) e o QML a respeita.
PATCH_MODEL_TERMS <- c("Anova", "Ancova", "AnovaBayesian")

restore_model_terms <- function(parsed) {
  want <- REQ$modelTerms
  if (is.null(want) || length(want) == 0 || !is.character(parsed$options)) return(parsed)
  po <- jsonlite::fromJSON(parsed$options, simplifyVector = FALSE)
  map <- character()
  for (key in intersect(names(REQ$names), names(po))) {
    orig <- unlist(REQ$names[[key]]); enc <- unlist(po[[key]])
    if (length(orig) == length(enc) && length(orig) > 0) map[orig] <- enc
  }
  terms <- lapply(want, function(t) { t$components <- as.list(unname(map[unlist(t$components)])); t })   # mantém name/title etc.
  if (anyNA(unlist(lapply(terms, `[[`, "components")))) return(parsed)        # algum nome sem tradução: não mexe
  po$modelTerms <- terms
  parsed$options <- as.character(jsonlite::toJSON(po, auto_unbox = TRUE, digits = NA, null = "null"))
  parsed
}

install_bridge_patch <- function() {
  ns <- asNamespace("jaspTools")
  orig <- get("parseOptionsThroughBridge", envir = ns)
  if (isTRUE(attr(orig, "model_terms_patch"))) return(invisible())
  patched <- function(name, options) {
    parsed <- orig(name, options)
    tryCatch(restore_model_terms(parsed), error = function(e) parsed)
  }
  attr(patched, "model_terms_patch") <- TRUE
  utils::assignInNamespace("parseOptionsThroughBridge", patched, ns = "jaspTools")
}

# Configura o jaspTools para TODOS os módulos e aquece cada um. Falha de um módulo NÃO derruba o motor
# (as demais análises seguem); o resultado por módulo volta ao supervisor, que registra no log.
init_jasp <- function() {
  setPkgOption("module.dirs", file.path(MODULES_DIR, unique(ANALYSIS_MODULE)))
  # Os módulos já foram instalados na imagem (install-modules.sh). Sem isto, o jaspTools reinstala TODOS a partir do fonte
  # em cada partida do motor: lento (~minutos com 2 workers) e, se a instalação for interrompida/falhar, deixa o módulo
  # apagado no contêiner (visto na 6.6: "The installation of jaspAnova failed").
  setPkgOption("reinstall.modules", FALSE)
  install_bridge_patch()
  vapply(names(WARM_SPECS), function(a) {
    tryCatch({
      w <- WARM_SPECS[[a]]
      o <- analysisOptions(a)
      for (nm in names(w$opts)) o[[nm]] <- w$opts[[nm]]
      invisible(runAnalysis(a, dataset = w$df, options = o, view = FALSE, quiet = TRUE))
      "ok"
    }, error = function(e) paste("FALHOU:", conditionMessage(e)))
  }, character(1))
}

DATA_DIR <- Sys.getenv("DATA_DIR", "/data")   # volume compartilhado (somente leitura aqui)

# Erro causado pelo pedido (-> HTTP 422), distinto de falha interna (-> 500).
bad_request <- function(msg) stop(structure(class = c("request_error", "error", "condition"),
                                            list(message = msg, call = NULL)))

# Nomes de opção válidos = defaults + nomes declarados em QUALQUER QML do módulo da análise.
# (analysisOptions() omite listas vazias, como `fixedFactors`; e muitos nomes vivem em componentes compartilhados
#  em `qml/common/`, como `modelTerms`.) É um conjunto maior que o estritamente válido, mas pega erros de digitação.
MODULE_NAMES <- new.env()
module_option_names <- function(module) {
  if (is.null(MODULE_NAMES[[module]])) {
    files <- list.files(file.path(MODULES_DIR, module, "inst", "qml"), pattern = "\\.qml$", recursive = TRUE, full.names = TRUE)
    MODULE_NAMES[[module]] <- unique(unlist(lapply(files, function(f) {
      txt <- paste(readLines(f, warn = FALSE), collapse = "\n")
      m <- regmatches(txt, gregexpr('name:\\s*"[^"]+"', txt))[[1]]
      sub('name:\\s*"([^"]+)"', "\\1", m)
    })))
  }
  MODULE_NAMES[[module]]
}
valid_option_names <- function(analysis, defaults) union(names(defaults), module_option_names(ANALYSIS_MODULE[[analysis]]))

# JSON -> o que o JASP espera: lista plana de escalares (["a","b"]) vira vetor atômico, em qualquer profundidade
# (ex.: modelTerms = [{"components": ["a","b"]}] -> list(list(components = c("a","b")))).
simplify_deep <- function(x) {
  if (!is.list(x)) return(x)
  x <- lapply(x, simplify_deep)
  if (length(x) > 0 && is.null(names(x)) && all(vapply(x, function(e) is.atomic(e) && length(e) == 1, logical(1))))
    return(unlist(x))
  x
}

# jaspTools serializa as opções com toJSON(auto_unbox = TRUE), que transforma um vetor de comprimento 1 em ESCALAR:
# `components: ["altura"]` chegava ao QML como `"altura"` e a regressão (linear e logística) com UM só preditor ficava com
# o modelo VAZIO (R² = 0, só o intercepto), sem erro. I() (AsIs) impede o desembrulho. Só os `components` dos termos de modelo.
protect_components <- function(x) {
  if (!is.list(x)) return(x)
  for (i in seq_along(x)) {
    if (identical(names(x)[i], "components") && is.atomic(x[[i]]) && length(x[[i]]) == 1) x[[i]] <- I(x[[i]])
    else x[[i]] <- protect_components(x[[i]])
  }
  x
}

# Mescla opções do pedido sobre os defaults do QML da análise.
build_options <- function(analysis, overrides) {
  opts <- analysisOptions(analysis)
  unknown <- setdiff(names(overrides), valid_option_names(analysis, opts))
  if (length(unknown)) bad_request(sprintf("unknown option(s) for %s: %s", analysis, paste(unknown, collapse = ", ")))
  for (nm in names(overrides)) opts[[nm]] <- protect_components(simplify_deep(overrides[[nm]]))
  opts
}

# Lê só as colunas pedidas do Parquet do dataset e aplica o nível de medida:
# nominal/ordinal -> factor, scale -> numeric (é isso que o R/JASP usa para escolher o teste).
load_dataset <- function(dataset_id, columns, measurement) {
  if (!is.character(dataset_id) || length(dataset_id) != 1 || !grepl("^[0-9a-f]{32}$", dataset_id))
    bad_request("invalid dataset_id")                       # também impede path traversal
  path <- file.path(DATA_DIR, "datasets", paste0(dataset_id, ".parquet"))
  if (!file.exists(path)) bad_request(sprintf("dataset not found: %s", dataset_id))
  columns <- unlist(columns)
  if (length(columns) == 0) bad_request("no columns requested")
  df <- tryCatch(as.data.frame(nanoparquet::read_parquet(path, col_select = columns)),
                 error = function(e) bad_request(sprintf("cannot read columns: %s", conditionMessage(e))))
  for (col in names(df)) {
    level <- measurement[[col]]
    if (identical(level, "nominal") || identical(level, "ordinal")) df[[col]] <- factor(df[[col]])
    else if (identical(level, "scale")) df[[col]] <- as.numeric(df[[col]])
  }
  df
}

# Os gráficos do jaspResults vêm como caminho ("resources/_0_x.png") de um arquivo no disco do worker,
# inacessível ao cliente. Embute como data URI e apaga o arquivo (senão o temp cresce a cada análise).
JASP_TEMP <- file.path(path.expand("~"), ".local", "share", "JASP", "temp")
embed_plots <- function(node) {
  if (!is.list(node)) return(node)
  d <- node[["data"]]
  if (is.character(d) && length(d) == 1 && grepl("^resources/[^/]+\\.(png|svg)$", d)) {
    hits <- Sys.glob(file.path(JASP_TEMP, "*", "resources", basename(d)))
    if (length(hits)) {
      mime <- if (grepl("\\.svg$", d)) "image/svg+xml" else "image/png"
      raw  <- readBin(hits[1], "raw", file.size(hits[1]))
      node[["data"]] <- paste0("data:", mime, ";base64,", jsonlite::base64_enc(raw))
      unlink(hits)
    }
    return(node)
  }
  for (nm in names(node)) if (!identical(nm, ".meta") && !identical(nm, "schema")) node[[nm]] <- embed_plots(node[[nm]])
  node
}

# Entrada única do motor. Nunca lança: devolve dados puros (http + corpo) para o supervisor repassar.
run_request <- function(body) {
  analysis <- body$analysis
  if (!is.character(analysis) || length(analysis) != 1 || !(analysis %in% ALLOWED_ANALYSES))
    return(list(http = 422L, body = list(status = "error", message = sprintf("analysis not allowed: %s", paste(analysis, collapse = "")))))

  tryCatch({
    df   <- load_dataset(body$dataset_id, body$columns, body$measurement)
    opts <- build_options(analysis, body$options)
    REQ$modelTerms <- if (analysis %in% PATCH_MODEL_TERMS && "modelTerms" %in% names(body$options)) opts$modelTerms else NULL
    REQ$names <- opts[intersect(NAME_OPTIONS, names(opts))]
    on.exit({ REQ$modelTerms <- NULL; REQ$names <- NULL }, add = TRUE)
    out  <- runAnalysis(analysis, dataset = df, options = opts, view = FALSE, quiet = TRUE)
    list(http = 200L, body = list(status = out$status, results = embed_plots(out$results)))
  }, request_error = function(e) list(http = 422L, body = list(status = "error", message = conditionMessage(e))),
     error = function(e) {
       msg <- conditionMessage(e)
       # O JASP valida as opções contra os dados (ex.: "group: Maximum number of levels is 2"): erro do
       # usuário, não do servidor. O prefixo vem repetido; remove.
       if (grepl("^Error when parsing options", msg))
         return(list(http = 422L, body = list(status = "error", message = sub("^(Error when parsing options: ?)+", "", msg))))
       list(http = 500L, body = list(status = "error", message = msg))
     })
}
