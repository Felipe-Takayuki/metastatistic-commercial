# Análises ESCRITAS PARA ESTA PLATAFORMA (R base, pacote `stats`), fora dos módulos JASP.
# Existem porque o JASP instalado não tem teste z de duas médias com σ conhecido nem teste z de proporções (o
# `zTestColumnComparison` do ContingencyTables só marca as células com letras, não devolve Z nem p; o BinomialTest é exato).
# A saída segue o formato do jaspResults (tabelas com `schema`/`data`/`footnotes` + `.meta`) para o front renderizar igual,
# e CADA tabela avisa que não vem de um módulo JASP. Fórmulas conferidas contra `prop.test` e `pnorm` nos testes de integração.

fld <- function(name, title, type = "number", format = NULL) {
  f <- list(name = name, title = title, type = type)
  if (!is.null(format)) f$format <- format
  f
}
ztab <- function(title, fields, data, notes = list()) {
  list(title = title, schema = list(fields = fields), data = unname(data),
       footnotes = c(list(list(symbol = "<em>Nota.</em>", text = "Análise calculada pelo motor da plataforma (R base), não por um módulo JASP.")), notes))
}

# valor-p e limites de um teste z segundo a hipótese alternativa
z_p <- function(z, alternative) switch(alternative,
  twoSided = 2 * pnorm(-abs(z)), greater = pnorm(z, lower.tail = FALSE), less = pnorm(z),
  bad_request("alternative must be twoSided, greater or less"))
z_ci <- function(est, se, level, alternative) {
  if (alternative == "twoSided") { q <- qnorm(1 - (1 - level) / 2); c(est - q * se, est + q * se) }
  else if (alternative == "greater") c(est - qnorm(level) * se, Inf)
  else c(-Inf, est + qnorm(level) * se)
}
check_alt <- function(alt) { if (!is.character(alt) || length(alt) != 1 || !(alt %in% c("twoSided", "greater", "less"))) bad_request("alternative must be twoSided, greater or less"); alt }
r_alt <- function(alt) c(twoSided = "two.sided", greater = "greater", less = "less")[[alt]]   # nomes do prop.test
as_num <- function(x) suppressWarnings(as.numeric(as.character(x)))   # ordinal numérica (Likert) chega como fator
opt_num <- function(o, key, default, lo = -Inf, hi = Inf, what = key) {
  v <- if (is.null(o[[key]])) default else o[[key]]
  if (!is.numeric(v) || length(v) != 1 || !is.finite(v) || v < lo || v > hi) bad_request(sprintf("%s must be a number between %s and %s", what, lo, hi))
  v
}
opt_chr <- function(o, key) { v <- o[[key]]; if (is.null(v) || length(v) == 0 || identical(v, "")) NULL else as.character(v[[1]]) }

# --- Teste z de duas médias, desvios padrão populacionais CONHECIDOS ----------------------------------------------------
# z = (m1 - m2) / sqrt(σ1²/n1 + σ2²/n2); d = (m1 - m2) / sqrt((σ1² + σ2²)/2). Grupo 1 = 1º nível em ordem alfabética.
z_means <- function(df, o) {
  dep <- opt_chr(o, "dependent"); grp <- opt_chr(o, "group")
  if (is.null(dep) || is.null(grp)) bad_request("dependent and group are required")
  s1 <- opt_num(o, "sigma1", 1, 1e-12, 1e12, "sigma1"); s2 <- opt_num(o, "sigma2", 1, 1e-12, 1e12, "sigma2")
  alt <- check_alt(if (is.null(o$alternative)) "twoSided" else o$alternative); level <- opt_num(o, "ciLevel", 0.95, 0.5, 0.9999, "ciLevel")
  y <- as_num(df[[dep]]); g <- droplevels(factor(df[[grp]])); ok <- is.finite(y) & !is.na(g); y <- y[ok]; g <- droplevels(g[ok])
  if (nlevels(g) != 2) bad_request(sprintf("%s: the z test compares exactly 2 groups (found %d)", grp, nlevels(g)))
  lv <- levels(g); y1 <- y[g == lv[1]]; y2 <- y[g == lv[2]]; n1 <- length(y1); n2 <- length(y2)
  if (n1 < 1 || n2 < 1) bad_request("each group needs at least 1 observation")
  d <- mean(y1) - mean(y2); se <- sqrt(s1^2 / n1 + s2^2 / n2); z <- d / se; ci <- z_ci(d, se, level, alt)
  hyp <- switch(alt, twoSided = "diferente", greater = "maior", less = "menor")
  res <- list(".meta" = list(list(name = "ztest", type = "table", title = "Teste z para duas amostras")), ztest = ztab(
    "Teste z para duas amostras (σ conhecidos)",
    list(fld("v", "Variável", "string"), fld("g", "Comparação", "string"), fld("z", "z", "number", "dp:3"), fld("p", "p", "pvalue", "dp:3;p:.001"),
         fld("d", "Diferença média", "number", "dp:3"), fld("se", "EP da diferença", "number", "dp:3"),
         fld("lo", sprintf("IC %g%%: inferior", level * 100), "number", "dp:3"), fld("hi", sprintf("IC %g%%: superior", level * 100), "number", "dp:3"), fld("cd", "d de Cohen (σ combinado)", "number", "dp:3")),
    list(list(v = dep, g = sprintf("%s − %s", lv[1], lv[2]), z = z, p = z_p(z, alt), d = d, se = se, lo = ci[1], hi = ci[2], cd = d / sqrt((s1^2 + s2^2) / 2))),
    list(list(symbol = "<em>Nota.</em>", text = sprintf("Hipótese alternativa: média de %s %s da de %s. σ de %s = %s; σ de %s = %s (conhecidos).", lv[1], hyp, lv[2], lv[1], format(s1), lv[2], format(s2))))))
  if (isTRUE(o$descriptives)) {
    res[[".meta"]] <- c(res[[".meta"]], list(list(name = "desc", type = "table", title = "Estatísticas descritivas")))
    res$desc <- ztab("Estatísticas descritivas",
      list(fld("g", "Grupo", "string"), fld("n", "N", "integer"), fld("m", "Média", "number", "dp:3"), fld("sd", "Desvio padrão (amostral)", "number", "dp:3"), fld("sigma", "σ informado", "number", "dp:3")),
      list(list(g = lv[1], n = n1, m = mean(y1), sd = if (n1 > 1) sd(y1) else NaN, sigma = s1), list(g = lv[2], n = n2, m = mean(y2), sd = if (n2 > 1) sd(y2) else NaN, sigma = s2)))
  }
  res
}

# --- Teste z de proporções: uma amostra (contra p0) ou duas amostras (grupos) -----------------------------------------
# "Sucesso" = a 2ª categoria do desfecho em ordem alfabética (como a regressão logística); `invert` troca para a 1ª.
# Uma amostra: z = (p̂ − p0)/√(p0(1−p0)/n), IC de Wilson. Duas: z = (p̂1 − p̂2)/√(p̂(1−p̂)(1/n1 + 1/n2)) (p̂ agrupado), IC de Wald.
# z² é o X² de prop.test(correct = FALSE) nos dois casos.
z_props <- function(df, o) {
  out <- opt_chr(o, "outcome"); grp <- opt_chr(o, "group")
  if (is.null(out)) bad_request("outcome is required")
  alt <- check_alt(if (is.null(o$alternative)) "twoSided" else o$alternative); level <- opt_num(o, "ciLevel", 0.95, 0.5, 0.9999, "ciLevel")
  y <- factor(df[[out]]); ok <- !is.na(y) & (if (is.null(grp)) TRUE else !is.na(df[[grp]])); y <- droplevels(y[ok])
  if (nlevels(y) != 2) bad_request(sprintf("%s: the proportion test needs an outcome with exactly 2 categories (found %d)", out, nlevels(y)))
  success <- levels(y)[if (isTRUE(o$invert)) 1 else 2]; hit <- y == success
  hyp <- switch(alt, twoSided = "diferente", greater = "maior", less = "menor")
  if (is.null(grp)) {
    p0 <- opt_num(o, "p0", 0.5, 1e-9, 1 - 1e-9, "p0"); n <- length(hit); x <- sum(hit); ph <- x / n
    z <- (ph - p0) / sqrt(p0 * (1 - p0) / n); ci <- suppressWarnings(prop.test(x, n, p = p0, alternative = r_alt(alt), conf.level = level, correct = FALSE)$conf.int)
    notes <- list(list(symbol = "<em>Nota.</em>", text = sprintf("Sucesso = “%s”. Hipótese alternativa: a proporção é %s de %s. IC de Wilson.", success, hyp, format(p0))))
    if (n * p0 < 10 || n * (1 - p0) < 10) notes <- c(notes, list(list(symbol = "<em>Aviso.</em>", text = "n·p0 ou n·(1−p0) < 10: a aproximação normal pode ser imprecisa (considere o teste binomial exato).")))
    return(list(".meta" = list(list(name = "ztest", type = "table", title = "Teste z para uma proporção")), ztest = ztab("Teste z para uma proporção",
      list(fld("v", "Variável", "string"), fld("s", "Sucesso", "string"), fld("x", "Sucessos", "integer"), fld("n", "N", "integer"), fld("ph", "Proporção", "number", "dp:3"), fld("p0", "p₀", "number", "dp:3"),
           fld("z", "z", "number", "dp:3"), fld("p", "p", "pvalue", "dp:3;p:.001"), fld("lo", sprintf("IC %g%%: inferior", level * 100), "number", "dp:3"), fld("hi", sprintf("IC %g%%: superior", level * 100), "number", "dp:3")),
      list(list(v = out, s = success, x = x, n = n, ph = ph, p0 = p0, z = z, p = z_p(z, alt), lo = ci[1], hi = ci[2])), notes)))
  }
  g <- droplevels(factor(df[[grp]])[ok])
  if (nlevels(g) != 2) bad_request(sprintf("%s: the two-sample proportion test compares exactly 2 groups (found %d)", grp, nlevels(g)))
  lv <- levels(g); x1 <- sum(hit[g == lv[1]]); n1 <- sum(g == lv[1]); x2 <- sum(hit[g == lv[2]]); n2 <- sum(g == lv[2])
  if (n1 < 1 || n2 < 1) bad_request("each group needs at least 1 observation")
  p1 <- x1 / n1; p2 <- x2 / n2; pp <- (x1 + x2) / (n1 + n2); den <- sqrt(pp * (1 - pp) * (1 / n1 + 1 / n2))
  z <- if (den > 0) (p1 - p2) / den else NaN
  ci <- suppressWarnings(prop.test(c(x1, x2), c(n1, n2), alternative = r_alt(alt), conf.level = level, correct = FALSE)$conf.int)
  notes <- list(list(symbol = "<em>Nota.</em>", text = sprintf("Sucesso = “%s”. Hipótese alternativa: a proporção de %s é %s da de %s. z com proporção agrupada; IC de Wald da diferença.", success, lv[1], hyp, lv[2])))
  if (min(n1 * pp, n1 * (1 - pp), n2 * pp, n2 * (1 - pp)) < 5) notes <- c(notes, list(list(symbol = "<em>Aviso.</em>", text = "Alguma frequência esperada < 5: a aproximação normal pode ser imprecisa (considere o teste exato de Fisher).")))
  list(".meta" = list(list(name = "ztest", type = "table", title = "Teste z para duas proporções")), ztest = ztab("Teste z para duas proporções",
    list(fld("v", "Variável", "string"), fld("g", "Comparação", "string"), fld("p1", sprintf("Proporção (1º)"), "number", "dp:3"), fld("p2", "Proporção (2º)", "number", "dp:3"),
         fld("d", "Diferença", "number", "dp:3"), fld("z", "z", "number", "dp:3"), fld("p", "p", "pvalue", "dp:3;p:.001"),
         fld("lo", sprintf("IC %g%%: inferior", level * 100), "number", "dp:3"), fld("hi", sprintf("IC %g%%: superior", level * 100), "number", "dp:3")),
    list(list(v = out, g = sprintf("%s (%d/%d) − %s (%d/%d)", lv[1], x1, n1, lv[2], x2, n2), p1 = p1, p2 = p2, d = p1 - p2, z = z, p = z_p(z, alt), lo = ci[1], hi = ci[2])), notes))
}

CUSTOM_ANALYSES <- list(ZTestMeans = z_means, ZTestProportions = z_props)
CUSTOM_OPTIONS <- list(
  ZTestMeans = c("dependent", "group", "sigma1", "sigma2", "alternative", "ciLevel", "descriptives"),
  ZTestProportions = c("outcome", "group", "p0", "invert", "alternative", "ciLevel"))
