# Gera r_reference.json: os valores "de verdade" (R puro: stats::aov, TukeyHSD, cor.test, lm, chisq.test) sobre as fixtures.
# Reexecutar se as fixtures mudarem:
#   docker cp apps/api/tests/fixtures metastatistic-r-worker-1-1:/tmp/fx && docker exec metastatistic-r-worker-1-1 Rscript /tmp/fx/make_reference.R /tmp/fx
#   docker cp metastatistic-r-worker-1-1:/tmp/fx/r_reference.json apps/api/tests/fixtures/r_reference.json
suppressMessages(library(jsonlite))
dir <- commandArgs(trailingOnly = TRUE)[1]
d <- read.csv(file.path(dir, "dbc_raw.csv")); d$bloco <- factor(((seq_len(nrow(d)) - 1) %% 4) + 1); d$tratamento <- factor(d$tratamento)
out <- list()
fit <- aov(produtividade ~ tratamento + bloco, data = d); a <- summary(fit)[[1]]
out$anova <- list(trat = list(df = a$Df[1], F = a$`F value`[1], p = a$`Pr(>F)`[1]), bloco = list(df = a$Df[2], F = a$`F value`[2], p = a$`Pr(>F)`[2]), resid = list(df = a$Df[3], ms = a$`Mean Sq`[3], ss = a$`Sum Sq`[3]))
tk <- TukeyHSD(fit, "tratamento")$tratamento
out$tukey <- lapply(seq_len(nrow(tk)), function(i) { p <- strsplit(rownames(tk)[i], "-")[[1]]; list(a = p[2], b = p[1], diff = -tk[i, "diff"], p = tk[i, "p adj"]) })
vars <- c("produtividade", "altura", "diametro"); pairs <- list(vars[1:2], vars[c(1, 3)], vars[2:3])
out$corr <- lapply(pairs, function(v) { x <- d[[v[1]]]; y <- d[[v[2]]]; pe <- cor.test(x, y); sp <- suppressWarnings(cor.test(x, y, method = "spearman", exact = FALSE))
  list(v1 = v[1], v2 = v[2], n = length(x), pearson = unname(pe$estimate), p_pearson = pe$p.value, lo = pe$conf.int[1], hi = pe$conf.int[2], spearman = unname(sp$estimate), p_spearman = sp$p.value) })
m <- lm(produtividade ~ altura + diametro, data = d); s <- summary(m); ci <- confint(m); fs <- s$fstatistic
out$reg <- list(R2 = s$r.squared, adjR2 = s$adj.r.squared, F = unname(fs[1]), p = pf(fs[1], fs[2], fs[3], lower.tail = FALSE), sigma = s$sigma, df_res = m$df.residual,
  coef = lapply(seq_len(nrow(s$coefficients)), function(i) list(est = s$coefficients[i, 1], se = s$coefficients[i, 2], t = s$coefficients[i, 3], p = s$coefficients[i, 4], lo = ci[i, 1], hi = ci[i, 2])))
tt <- read.csv(file.path(dir, "ttest.csv")); tt$faixa <- ifelse(tt$score < 9, "baixo", ifelse(tt$score < 11, "medio", "alto"))
tb <- table(tt$group, tt$faixa); ch <- suppressWarnings(chisq.test(tb, correct = FALSE)); ex <- ch$expected; ob <- as.matrix(tb)
g2 <- 2 * sum(ifelse(ob > 0, ob * log(ob / ex), 0)); n <- sum(ob)
out$chi <- list(X2 = unname(ch$statistic), df = unname(ch$parameter), p = ch$p.value, G2 = g2, p_g2 = pchisq(g2, ch$parameter, lower.tail = FALSE),
  V = sqrt(unname(ch$statistic) / (n * (min(dim(ob)) - 1))), n = n, expected = as.vector(ex), levels = colnames(ob))
fa <- read.csv(file.path(dir, "fatorial.csv")); fa$A <- factor(fa$A); fa$B <- factor(fa$B); fx <- summary(aov(y ~ A * B, data = fa))[[1]]
out$fatorial <- list(A = list(df = fx$Df[1], F = fx$`F value`[1], p = fx$`Pr(>F)`[1]), B = list(df = fx$Df[2], F = fx$`F value`[2], p = fx$`Pr(>F)`[2]),
  AB = list(df = fx$Df[3], F = fx$`F value`[3], p = fx$`Pr(>F)`[3]), resid = list(df = fx$Df[4], ms = fx$`Mean Sq`[4]))
fx2 <- summary(aov(y ~ A + B, data = fa))[[1]]   # modelo ADITIVO (sem interação): o JASP, por padrão, acrescentaria A:B
out$fatorial_add <- list(A = list(df = fx2$Df[1], F = fx2$`F value`[1], p = fx2$`Pr(>F)`[1]), B = list(df = fx2$Df[2], F = fx2$`F value`[2], p = fx2$`Pr(>F)`[2]), resid = list(df = fx2$Df[3], ms = fx2$`Mean Sq`[3]))
# --- catálogo 6.1: t pareado (altura x diametro), t de uma amostra (produtividade vs 200) e descritivas (produtividade) ---
pt <- t.test(d$altura, d$diametro, paired = TRUE); wt <- wilcox.test(d$altura, d$diametro, paired = TRUE)   # exato (como o JASP): sem empates e n < 50
dif <- d$altura - d$diametro
out$paired <- list(t = unname(pt$statistic), df = unname(pt$parameter), p = pt$p.value, mean_diff = unname(pt$estimate), lo = pt$conf.int[1], hi = pt$conf.int[2],
  d = mean(dif) / sd(dif), wilcoxon_p = wt$p.value, n = length(dif), p_greater = t.test(d$altura, d$diametro, paired = TRUE, alternative = "greater")$p.value)
ot <- t.test(d$produtividade, mu = 200); ow <- wilcox.test(d$produtividade, mu = 200); ol <- t.test(d$produtividade, mu = 200, alternative = "greater")
out$onesample <- list(t = unname(ot$statistic), df = unname(ot$parameter), p = ot$p.value, mean = unname(ot$estimate), lo = ot$conf.int[1], hi = ot$conf.int[2],
  d = (mean(d$produtividade) - 200) / sd(d$produtividade), wilcoxon_p = ow$p.value, p_greater = ol$p.value)
x <- d$produtividade
out$desc <- list(n = length(x), mean = mean(x), sd = sd(x), min = min(x), max = max(x), median = median(x), variance = var(x), se = sd(x) / sqrt(length(x)), sum = sum(x), range = max(x) - min(x))
out$meta <- list(r = R.version.string)
write(toJSON(out, auto_unbox = TRUE, digits = NA, pretty = TRUE), file.path(dir, "r_reference.json"))
cat("r_reference.json gerado com", R.version.string, "\n")
