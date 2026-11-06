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
# --- teste z de uma amostra (σ = 30 conhecido, μ0 = 200): z, p bilateral/unilateral, IC da diferença e d = diferença/σ ---
zs <- 30; zse <- zs / sqrt(length(d$produtividade)); zdiff <- mean(d$produtividade) - 200; zz <- zdiff / zse
out$ztest <- list(sd = zs, z = zz, p = 2 * pnorm(-abs(zz)), p_greater = pnorm(zz, lower.tail = FALSE), diff = zdiff, lo = zdiff - qnorm(0.975) * zse, hi = zdiff + qnorm(0.975) * zse, d = zdiff / zs)
# --- catálogo 6.6: versões bayesianas (pacote BayesFactor: prior Cauchy de largura 0,707; efeitos fixos da ANOVA r = 0,5) ---
suppressMessages(library(BayesFactor)); set.seed(1)
bfv <- function(x) extractBF(x)$bf
tt$group <- factor(tt$group)
eb <- extractBF(anovaBF(produtividade ~ tratamento + bloco, data = d, rscaleFixed = 0.5))
out$bayes <- list(indep = bfv(ttestBF(formula = score ~ group, data = tt, rscale = 0.707)),
  one = bfv(ttestBF(d$produtividade, mu = 200, rscale = 0.707)),
  one_nullint = bfv(ttestBF(d$produtividade, mu = 200, rscale = 0.707, nullInterval = c(0, Inf))),
  paired = bfv(ttestBF(d$altura, d$diametro, paired = TRUE, rscale = 0.707)),
  anova = list(models = rownames(eb), bf = eb$bf))
# --- catálogo 6.9: ANOVA de medidas repetidas (medidas_repetidas.csv: 24 sujeitos, 3 tempos, 2 grupos) ---
mr <- read.csv(file.path(dir, "medidas_repetidas.csv")); mr$grupo <- factor(mr$grupo); tms <- c("t1", "t2", "t3")
long <- reshape(mr, direction = "long", varying = tms, v.names = "y", timevar = "tempo", times = tms, idvar = "sujeito")
long$tempo <- factor(long$tempo); long$sujeito <- factor(long$sujeito)
stratum <- function(fit, name) { x <- summary(fit)[[name]][[1]]; rownames(x) <- trimws(rownames(x)); x }
row_of <- function(x, r) list(df = x[r, "Df"], ss = x[r, "Sum Sq"], F = x[r, "F value"], p = x[r, "Pr(>F)"])
# esfericidade: contrastes ortonormais (Helmert) das k medidas; S = covariância (agrupada por grupo, se houver) dos contrastes
sph <- function(Y, g = NULL) {
  k <- ncol(Y); n <- nrow(Y); C <- contr.helmert(k); C <- sweep(C, 2, sqrt(colSums(C^2)), "/"); Z <- Y %*% C
  grp <- if (is.null(g)) rep(1, n) else as.integer(g); G <- length(unique(grp)); dfe <- n - G
  S <- Reduce(`+`, lapply(unique(grp), function(u) crossprod(scale(Z[grp == u, , drop = FALSE], scale = FALSE)))) / dfe
  gg <- sum(diag(S))^2 / ((k - 1) * sum(diag(S %*% S)))
  hf <- min(1, (n * (k - 1) * gg - 2) / ((k - 1) * (dfe - (k - 1) * gg)))
  W <- det(S) / (sum(diag(S)) / (k - 1))^(k - 1)
  chi <- -(dfe - (2 * (k - 1)^2 + (k - 1) + 2) / (6 * (k - 1))) * log(W); dfc <- k * (k - 1) / 2 - 1
  list(W = W, chi = chi, df = dfc, p = pchisq(chi, dfc, lower.tail = FALSE), gg = gg, hf = hf, dfe = dfe)
}
corr_p <- function(Fv, d1, d2, eps) pf(Fv, d1 * eps, d2 * eps, lower.tail = FALSE)
f1 <- aov(y ~ tempo + Error(sujeito / tempo), data = long); w1 <- stratum(f1, "Error: sujeito:tempo"); t1 <- row_of(w1, "tempo"); s1 <- sph(as.matrix(mr[, tms]))
f2 <- aov(y ~ tempo * grupo + Error(sujeito / tempo), data = long); b2 <- stratum(f2, "Error: sujeito"); w2 <- stratum(f2, "Error: sujeito:tempo"); s2 <- sph(as.matrix(mr[, tms]), mr$grupo)
out$rm <- list(
  one = list(tempo = t1, resid = list(df = w1["Residuals", "Df"], ss = w1["Residuals", "Sum Sq"]), sph = s1, p_gg = corr_p(t1$F, t1$df, w1["Residuals", "Df"], s1$gg), p_hf = corr_p(t1$F, t1$df, w1["Residuals", "Df"], s1$hf)),
  mixed = list(grupo = row_of(b2, "grupo"), tempo = row_of(w2, "tempo"), inter = row_of(w2, "tempo:grupo"), sph = s2,
               p_gg_tempo = corr_p(row_of(w2, "tempo")$F, 2, w2["Residuals", "Df"], s2$gg), p_gg_inter = corr_p(row_of(w2, "tempo:grupo")$F, 2, w2["Residuals", "Df"], s2$gg)))
prs <- combn(tms, 2, simplify = FALSE); tp <- lapply(prs, function(v) t.test(mr[[v[1]]], mr[[v[2]]], paired = TRUE))
pv <- vapply(tp, function(x) x$p.value, numeric(1))
out$rm$posthoc <- lapply(seq_along(prs), function(i) list(a = prs[[i]][1], b = prs[[i]][2], estimate = unname(tp[[i]]$estimate), t = unname(tp[[i]]$statistic), df = unname(tp[[i]]$parameter),
  se = unname(tp[[i]]$stderr), holm = p.adjust(pv, "holm")[i], bonferroni = p.adjust(pv, "bonferroni")[i]))
out$rm$one$partial_eta <- t1$ss / (t1$ss + w1["Residuals", "Sum Sq"])
# --- catálogo 6.10: Friedman + Conover (friedman.csv: 20 sujeitos, 3 condições, com empates) ---
fr <- read.csv(file.path(dir, "friedman.csv")); Yf <- as.matrix(fr[, c("c1", "c2", "c3")]); nf <- nrow(Yf); kf <- ncol(Yf)
ft <- friedman.test(Yf); Rk <- t(apply(Yf, 1, rank)); Rj <- colSums(Rk); A1 <- sum(Rk^2)
cden <- sqrt(2 * (nf * A1 - sum(Rj^2)) / ((nf - 1) * (kf - 1))); cdf <- (nf - 1) * (kf - 1)
cp <- combn(kf, 2, simplify = FALSE); cpt <- vapply(cp, function(ij) (Rj[ij[1]] - Rj[ij[2]]) / cden, numeric(1)); cpp <- 2 * pt(-abs(cpt), cdf)
out$friedman <- list(chi = unname(ft$statistic), df = unname(ft$parameter), p = ft$p.value, kendall = unname(ft$statistic) / (nf * (kf - 1)), rank_sums = unname(Rj),
  conover = lapply(seq_along(cp), function(i) list(a = colnames(Yf)[cp[[i]][1]], b = colnames(Yf)[cp[[i]][2]], t = cpt[i], df = cdf, p = cpp[i], bonferroni = p.adjust(cpp, "bonferroni")[i], holm = p.adjust(cpp, "holm")[i])))
# --- catálogo 6.11: ordinais numéricos (Likert) em papéis escalares: friedman.csv com c1 ORDINAL (inteiros, 8 valores) e c2/c3 escalares ---
lk <- fr; lk$grupo <- factor(ifelse(seq_len(nrow(lk)) %% 2 == 0, "a", "b")); lk$nivel <- factor(ifelse(lk$c3 >= 16, "alto", "baixo"))
ot <- t.test(lk$c1, mu = 10); pt_ <- t.test(lk$c1, lk$c2, paired = TRUE); it <- t.test(lk$c1 ~ lk$grupo, var.equal = TRUE)
an <- anova(lm(c1 ~ grupo, lk)); ac <- drop1(lm(c2 ~ grupo + c1, lk), ~., test = "F"); ack <- rownames(ac) != "<none>"
lr <- summary(lm(c2 ~ c1, lk)); lr2 <- summary(lm(c1 ~ c2, lk)); lg <- summary(glm(nivel ~ c1, data = lk, family = binomial))
lng <- data.frame(y = c(lk$c1, lk$c2, lk$c3), cond = factor(rep(c("c1", "c2", "c3"), each = nrow(lk))), id = factor(rep(seq_len(nrow(lk)), 3)))
out$ordinal <- list(
  onesample = list(t = unname(ot$statistic), df = unname(ot$parameter), p = ot$p.value, diff = unname(ot$estimate) - 10),
  paired = list(t = unname(pt_$statistic), df = unname(pt_$parameter), p = pt_$p.value),
  indep = list(t = unname(it$statistic), df = unname(it$parameter), p = it$p.value),
  anova = list(F = an$`F value`[1], p = an$`Pr(>F)`[1], df = an$Df[1]),
  ancova = list(terms = rownames(ac)[ack], F = ac$`F value`[ack], p = ac$`Pr(>F)`[ack]),
  reg_cov = list(est = unname(coef(lr)[, 1]), se = unname(coef(lr)[, 2]), p = unname(coef(lr)[, 4]), R2 = lr$r.squared),
  reg_dep = list(est = unname(coef(lr2)[, 1]), R2 = lr2$r.squared),
  logit = list(est = unname(coef(lg)[, 1]), se = unname(coef(lg)[, 2]), p = unname(coef(lg)[, 4])),
  rm = list(F = summary(aov(y ~ cond + Error(id / cond), lng))[[2]][[1]]$`F value`[1]),
  bayes_paired = bfv(ttestBF(lk$c1, lk$c2, paired = TRUE, rscale = 0.707)))
# --- regressão com UM preditor (o modelo ficava vazio: components de comprimento 1 virava escalar no JSON) ---
r1 <- summary(lm(produtividade ~ altura, data = d)); g1 <- summary(glm(nivel ~ altura, data = d, family = binomial))
out$one_predictor <- list(reg = list(est = unname(coef(r1)[, 1]), se = unname(coef(r1)[, 2]), p = unname(coef(r1)[, 4]), R2 = r1$r.squared, F = unname(r1$fstatistic[1])),
  logit = list(est = unname(coef(g1)[, 1]), se = unname(coef(g1)[, 2]), p = unname(coef(g1)[, 4])))
# --- catálogo 6.12: testes z (ttest.csv: score por grupo a/b; desfecho sim = score >= 10,5) ---
za <- tt$score[tt$group == "a"]; zb <- tt$score[tt$group == "b"]; zs1 <- 1.5; zs2 <- 2
zd <- mean(za) - mean(zb); zse <- sqrt(zs1^2 / length(za) + zs2^2 / length(zb)); zz <- zd / zse
out$z_means <- list(s1 = zs1, s2 = zs2, n1 = length(za), n2 = length(zb), m1 = mean(za), m2 = mean(zb), diff = zd, se = zse, z = zz, p = 2 * pnorm(-abs(zz)), p_greater = pnorm(zz, lower.tail = FALSE), p_less = pnorm(zz),
  lo = zd - qnorm(0.975) * zse, hi = zd + qnorm(0.975) * zse, lo_greater = zd - qnorm(0.95) * zse, d = zd / sqrt((zs1^2 + zs2^2) / 2))
resp <- tt$score >= 10.5; x1 <- sum(resp[tt$group == "a"]); n1 <- sum(tt$group == "a"); x2 <- sum(resp[tt$group == "b"]); n2 <- sum(tt$group == "b")
pt2 <- prop.test(c(x1, x2), c(n1, n2), correct = FALSE); pt2g <- prop.test(c(x1, x2), c(n1, n2), correct = FALSE, alternative = "greater")
out$z_props2 <- list(x1 = x1, n1 = n1, x2 = x2, n2 = n2, p1 = x1 / n1, p2 = x2 / n2, diff = x1 / n1 - x2 / n2, z = sign(x1 / n1 - x2 / n2) * sqrt(unname(pt2$statistic)), p = pt2$p.value, p_greater = pt2g$p.value,
  lo = pt2$conf.int[1], hi = pt2$conf.int[2])
ps1 <- prop.test(sum(resp), length(resp), p = 0.4, correct = FALSE)
out$z_props1 <- list(x = sum(resp), n = length(resp), ph = mean(resp), p0 = 0.4, z = sign(mean(resp) - 0.4) * sqrt(unname(ps1$statistic)), p = ps1$p.value, lo = ps1$conf.int[1], hi = ps1$conf.int[2])
# --- catálogo 6.13: diagnósticos de regressão (VIF, Durbin-Watson) com preditores correlacionados: altura2 = 2·altura + floor(produtividade) %% 3 ---
d$altura2 <- 2 * d$altura + floor(d$produtividade) %% 3
fitc <- lm(produtividade ~ altura + altura2, data = d); ec <- resid(fitc); r2c <- cor(d$altura, d$altura2)^2
fit0 <- lm(produtividade ~ altura + diametro, data = d); e0 <- resid(fit0)
out$diag <- list(vif_collinear = 1 / (1 - r2c), dw_collinear = sum(diff(ec)^2) / sum(ec^2), vif_ok = 1 / (1 - cor(d$altura, d$diametro)^2), dw_ok = sum(diff(e0)^2) / sum(e0^2))
# --- catálogo 6.14: t pareado com vários pares (inclui uma linha de base repetida em dois pares) ---
pp <- list(c("altura", "diametro"), c("produtividade", "altura2"), c("altura", "altura2"), c("produtividade", "altura"))
out$paired_multi <- lapply(pp, function(v) { tt_ <- t.test(d[[v[1]]], d[[v[2]]], paired = TRUE)
  list(a = v[1], b = v[2], t = unname(tt_$statistic), df = unname(tt_$parameter), p = tt_$p.value, diff = unname(tt_$estimate)) })
# --- catálogo 6.15: correlação, regressão, ANCOVA e qui-quadrado bayesianos ---
# Correlação (prior beta esticado, largura κ): BF10 analítico de Ly, Verhagen & Wagenmakers (2016) por integração numérica; o BayesFactor não tem BF de correlação.
hyp2f1 <- function(a, b, cc, z) { sm <- 1; tm <- 1; for (k in 0:20000) { tm <- tm * (a + k) * (b + k) / ((cc + k) * (k + 1)) * z; sm <- sm + tm; if (abs(tm) < 1e-17 * abs(sm)) break }; sm }
cor_bf10 <- function(x, y, kappa = 1) {
  n <- length(x); r <- cor(x, y); a <- 1 / kappa
  f <- function(rho) vapply(rho, function(q) (1 - q^2)^((n - 1) / 2) * (1 - q * r)^(-(n - 3 / 2)) * hyp2f1(1 / 2, 1 / 2, (2 * n - 1) / 2, (1 + q * r) / 2), numeric(1))
  integrate(function(q) dbeta((q + 1) / 2, a, a) / 2 * f(q), -1, 1, rel.tol = 1e-10)$value / f(0)
}
cvars <- c("produtividade", "altura", "diametro")
out$bayes_corr <- lapply(combn(3, 2, simplify = FALSE), function(ij) list(a = cvars[ij[1]], b = cvars[ij[2]], r = cor(d[[cvars[ij[1]]]], d[[cvars[ij[2]]]]), n = nrow(d),
  bf10 = cor_bf10(d[[cvars[ij[1]]]], d[[cvars[ij[2]]]]), bf10_k2 = cor_bf10(d[[cvars[ij[1]]]], d[[cvars[ij[2]]]], kappa = 2)))
# Regressão: BF de cada modelo contra o nulo (lmBF, JZS com r = 0,354)
rb <- function(f) extractBF(lmBF(f, data = d, rscaleCont = 0.354))$bf
out$bayes_reg <- list(altura = rb(produtividade ~ altura), diametro = rb(produtividade ~ diametro), both = rb(produtividade ~ altura + diametro))
# ANCOVA: tratamento (fator, r = 0,5) + altura (covariável, r = 0,354) contra o nulo
d$trat_f <- factor(d$tratamento)
ab <- function(f) extractBF(lmBF(f, data = d, rscaleFixed = 0.5, rscaleCont = 0.354))$bf
out$bayes_ancova <- list(trat = ab(produtividade ~ trat_f), altura = ab(produtividade ~ altura), both = ab(produtividade ~ trat_f + altura))
# Qui-quadrado (ttest.csv: grupo × faixa): BF10 por modelo amostral, prior de concentração 1
cbf <- function(...) extractBF(contingencyTableBF(tb, ...))$bf
out$bayes_chi <- list(poisson = cbf(sampleType = "poisson"), joint = cbf(sampleType = "jointMulti"),
  rows_fixed = cbf(sampleType = "indepMulti", fixedMargin = "rows"), cols_fixed = cbf(sampleType = "indepMulti", fixedMargin = "cols"))
# --- catálogo 6.16: ANCOVA (médias marginais ajustadas e post hoc de Tukey/Holm/Bonferroni) e logística passo a passo (AIC) ---
fa <- lm(produtividade ~ trat_f + altura, data = d)
ndl <- data.frame(trat_f = factor(levels(d$trat_f), levels = levels(d$trat_f)), altura = mean(d$altura)); Xl <- model.matrix(~ trat_f + altura, ndl); bet <- coef(fa); Vc <- vcov(fa)
lsm <- drop(Xl %*% bet); lsm_se <- sqrt(diag(Xl %*% Vc %*% t(Xl))); kk <- nrow(Xl); dfa <- fa$df.residual
pp <- combn(kk, 2, simplify = FALSE)
pest <- vapply(pp, function(ij) drop((Xl[ij[1], ] - Xl[ij[2], ]) %*% bet), numeric(1))
pse <- vapply(pp, function(ij) sqrt(drop((Xl[ij[1], ] - Xl[ij[2], ]) %*% Vc %*% (Xl[ij[1], ] - Xl[ij[2], ]))), numeric(1))
pt_ <- pest / pse; praw <- 2 * pt(-abs(pt_), dfa)
out$ancova_adj <- list(levels = levels(d$trat_f), lsmean = lsm, se = lsm_se, df = dfa, k = kk,
  pairs = lapply(seq_along(pp), function(i) list(a = levels(d$trat_f)[pp[[i]][1]], b = levels(d$trat_f)[pp[[i]][2]], est = pest[i], se = pse[i], t = pt_[i],
    tukey = ptukey(abs(pt_[i]) * sqrt(2), kk, dfa, lower.tail = FALSE), holm = p.adjust(praw, "holm")[i], bonferroni = p.adjust(praw, "bonferroni")[i])))
d$nivel_s <- factor(ifelse(d$altura + 5 * ((floor(d$produtividade) %% 7) - 3) >= 140, "alto", "baixo"))
fullg <- glm(nivel_s ~ altura + diametro + altura2, data = d, family = binomial); nulg <- glm(nivel_s ~ 1, data = d, family = binomial)
stp <- function(m) list(terms = attr(terms(m), "term.labels"), aic = AIC(m), est = unname(coef(m)), se = unname(summary(m)$coefficients[, 2]))
out$logit_steps <- list(backward = stp(step(fullg, direction = "backward", trace = 0)), forward = stp(step(nulg, scope = formula(fullg), direction = "forward", trace = 0)),
  stepwise = stp(step(nulg, scope = formula(fullg), direction = "both", trace = 0)))
# --- catálogo 6.17: ANOVA de medidas repetidas com DOIS fatores intra-sujeito (rm2.csv: A pre/pos × B b1/b2/b3; 1º fator varia mais devagar) ---
m2 <- read.csv(file.path(dir, "rm2.csv")); c2 <- c("a1b1", "a1b2", "a1b3", "a2b1", "a2b2", "a2b3"); n2 <- nrow(m2)
long2 <- data.frame(y = unlist(m2[c2]), A = factor(rep(c("pre", "pos"), each = 3 * n2), levels = c("pre", "pos")), B = factor(rep(rep(c("b1", "b2", "b3"), each = n2), 2)), id = factor(rep(m2$sujeito, 6)))
s2 <- summary(aov(y ~ A * B + Error(id / (A * B)), long2))
st2 <- function(nm, row) { x <- s2[[nm]][[1]]; rownames(x) <- trimws(rownames(x)); list(df = x[row, "Df"], ss = x[row, "Sum Sq"], F = x[row, "F value"], p = x[row, "Pr(>F)"], df_res = x["Residuals", "Df"], ss_res = x["Residuals", "Sum Sq"]) }
bavg <- list(b1 = (m2$a1b1 + m2$a2b1) / 2, b2 = (m2$a1b2 + m2$a2b2) / 2, b3 = (m2$a1b3 + m2$a2b3) / 2)
bp <- combn(c("b1", "b2", "b3"), 2, simplify = FALSE); btt <- lapply(bp, function(v) t.test(bavg[[v[1]]], bavg[[v[2]]], paired = TRUE)); braw <- vapply(btt, function(x) x$p.value, numeric(1))
out$rm2 <- list(n = n2, A = st2("Error: id:A", "A"), B = st2("Error: id:B", "B"), AB = st2("Error: id:A:B", "A:B"),
  posthoc_B = lapply(seq_along(bp), function(i) list(a = bp[[i]][1], b = bp[[i]][2], est = unname(btt[[i]]$estimate), t = unname(btt[[i]]$statistic), df = unname(btt[[i]]$parameter),
    holm = p.adjust(braw, "holm")[i], bonferroni = p.adjust(braw, "bonferroni")[i])))
out$meta <- list(r = R.version.string)
write(toJSON(out, auto_unbox = TRUE, digits = NA, pretty = TRUE), file.path(dir, "r_reference.json"))
cat("r_reference.json gerado com", R.version.string, "\n")
