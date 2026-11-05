# Gera r_reference.json: os valores "de verdade" (R puro: stats::aov, TukeyHSD, cor.test, lm, chisq.test) sobre as fixtures.
# Reexecutar se as fixtures mudarem:
#   docker cp apps/api/tests/fixtures/. metastatistic-r-worker-1-1:/tmp/fx/ && docker exec metastatistic-r-worker-1-1 Rscript /tmp/fx/make_reference.R /tmp/fx
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
# --- catálogo 6.2: ANCOVA e regressão logística (dbc_raw + bloco; `nivel` = alto/baixo pela produtividade >= 196) ---
d$nivel <- factor(ifelse(d$produtividade >= 196, "alto", "baixo"))   # níveis alto < baixo: o glm modela P(baixo)
op <- options(contrasts = c("contr.sum", "contr.poly"))             # soma-zero: drop1 = SQ tipo II/III (sem interações, iguais)
anc <- function(f) { fa <- lm(f, data = d); dr <- drop1(fa, ~., test = "F"); k <- rownames(dr) != "<none>"
  list(terms = rownames(dr)[k], df = dr$Df[k], ss = dr$`Sum of Sq`[k], F = dr$`F value`[k], p = dr$`Pr(>F)`[k], resid_df = fa$df.residual, resid_ss = deviance(fa)) }
out$ancova_blocks <- anc(produtividade ~ tratamento + bloco + altura)
out$ancova_simple <- anc(produtividade ~ tratamento + altura)
options(op)
gm <- glm(nivel ~ altura + diametro, data = d, family = binomial); sg <- summary(gm)
cp <- suppressMessages(confint(gm)); cw <- confint.default(gm)
pr <- unname(predict(gm, type = "response")); pos <- d$nivel == "baixo"; predpos <- pr >= 0.5
auc <- (sum(rank(pr)[pos]) - sum(pos) * (sum(pos) + 1) / 2) / (sum(pos) * sum(!pos))
out$logit <- list(coefs = rownames(sg$coefficients), est = unname(sg$coefficients[, 1]), se = unname(sg$coefficients[, 2]), z = unname(sg$coefficients[, 3]), p = unname(sg$coefficients[, 4]),
  or = unname(exp(coef(gm))), lo_profile = unname(cp[, 1]), hi_profile = unname(cp[, 2]), lo_wald = unname(cw[, 1]), hi_wald = unname(cw[, 2]),
  deviance = deviance(gm), null_deviance = gm$null.deviance, df_resid = gm$df.residual, aic = AIC(gm), bic = BIC(gm), accuracy = mean(predpos == pos), auc = auc,
  obs_alto_pred_alto = sum(!pos & !predpos), obs_alto_pred_baixo = sum(!pos & predpos), obs_baixo_pred_alto = sum(pos & !predpos), obs_baixo_pred_baixo = sum(pos & predpos), n = nrow(d))
# --- catálogo 6.4: Kruskal-Wallis (+ Dunn com correção de empates, Bonferroni/Holm) e tabela de frequência ---
kw <- kruskal.test(produtividade ~ tratamento, data = d); N <- nrow(d); k <- nlevels(d$tratamento)
rk <- rank(d$produtividade); mr <- tapply(rk, d$tratamento, mean); ns <- tapply(rk, d$tratamento, length)
tie <- sum(table(d$produtividade)^3 - table(d$produtividade)); lv <- levels(d$tratamento)
dunn <- do.call(rbind, lapply(combn(k, 2, simplify = FALSE), function(ij) { i <- ij[1]; j <- ij[2]
  z <- (mr[i] - mr[j]) / sqrt((N * (N + 1) / 12 - tie / (12 * (N - 1))) * (1 / ns[i] + 1 / ns[j])); data.frame(contrast = paste(lv[i], "-", lv[j]), z = unname(z), p = 2 * pnorm(-abs(z))) }))
dunn$bonferroni <- pmin(1, p.adjust(dunn$p, "bonferroni")); dunn$holm <- p.adjust(dunn$p, "holm")
out$kruskal <- list(H = unname(kw$statistic), df = unname(kw$parameter), p = kw$p.value, epsilon = unname(kw$statistic) / (N - 1),
  eta = (unname(kw$statistic) - k + 1) / (N - k), dunn = lapply(seq_len(nrow(dunn)), function(i) as.list(dunn[i, ])))
fq <- table(d$nivel); out$freq <- list(levels = names(fq), n = as.vector(fq), percent = as.vector(fq) / sum(fq) * 100, cumulative = cumsum(as.vector(fq)) / sum(fq) * 100)
# --- catálogo 6.5: pressupostos (pressupostos.csv: grupo `controle` de variância mínima vs `tratado` assimétrico) ---
pr <- read.csv(file.path(dir, "pressupostos.csv")); pr$grupo <- factor(pr$grupo)
lev <- function(ctr) { z <- abs(pr$y - ave(pr$y, pr$grupo, FUN = ctr)); a <- anova(lm(z ~ pr$grupo)); list(F = a$`F value`[1], p = a$`Pr(>F)`[1], df1 = a$Df[1], df2 = a$Df[2]) }
sw <- shapiro.test(resid(lm(y ~ grupo, data = pr)))   # o JASP testa os RESÍDUOS no t independente
out$pressupostos <- list(levene_mean = lev(mean), levene_median = lev(median), shapiro_resid = list(W = unname(sw$statistic), p = sw$p.value))
out$meta <- list(r = R.version.string)
write(toJSON(out, auto_unbox = TRUE, digits = NA, pretty = TRUE), file.path(dir, "r_reference.json"))
cat("r_reference.json gerado com", R.version.string, "\n")
