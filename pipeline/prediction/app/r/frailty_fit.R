#!/usr/bin/env Rscript
# Stage 2 of the Weibull AFT baseline: shared-frailty refit on the surviving features.
#
# Called ONCE per fit. If a `fold` column is present the cross-validation loop runs inside
# this script, so a k-fold CV costs one R process rather than k -- see cv.iter_fold_assignments
# on the Python side, which produces that column.
#
# Honesty note, repeated here because this is where it bites: frailtyPenal fits a shared
# gamma-frailty PROPORTIONAL HAZARDS model, not an AFT. Weibull is the one distribution that
# is both, so the caller converts beta_PH -> AFT time ratios via exp(-beta / shape). And
# frailtypack's "penalized likelihood" smooths the baseline hazard; it is NOT a covariate
# Lasso, which is exactly why selection has to happen in stage 1.
#
# Contract:
#   Rscript frailty_fit.R <data.csv> <out_dir>
# where data.csv has columns: row_id, t_failure, event, experiment_id, [fold], V1..Vp
# Features are passed as V1..Vp rather than their real names on purpose: real names contain
# characters R will not accept as symbols (e.g. "active-antimicrobial"), and the Python side
# holds the mapping.
#
# Writes: meta.csv, coef.csv, vcov.csv, and cv_pred.csv when folds were supplied.

suppressMessages(library(frailtypack))

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 2L) stop("usage: frailty_fit.R <data.csv> <out_dir>")
data_csv <- args[1L]
out_dir  <- args[2L]
dir.create(out_dir, showWarnings = FALSE, recursive = TRUE)

d <- read.csv(data_csv, stringsAsFactors = FALSE, check.names = FALSE)
feat <- grep("^V[0-9]+$", names(d), value = TRUE)

build_formula <- function(features) {
  rhs <- paste(c("cluster(experiment_id)", features), collapse = " + ")
  stats::as.formula(paste("Surv(t_failure, event) ~", rhs))
}

# Drop features with no variation in this particular training set: frailtyPenal cannot
# identify them and would fail the whole fit rather than the one column.
usable_features <- function(df, features) {
  keep <- vapply(features, function(f) length(unique(df[[f]])) > 1L, logical(1L))
  features[keep]
}

fit_one <- function(df, features) {
  f <- usable_features(df, features)
  if (length(f) == 0L) return(NULL)
  out <- try(
    frailtyPenal(build_formula(f), data = df, hazard = "Weibull", RandDist = "Gamma"),
    silent = TRUE
  )
  if (inherits(out, "try-error")) return(NULL)
  out$.features <- f
  out
}

# ---- full fit ------------------------------------------------------------------------

fit <- fit_one(d, feat)
if (is.null(fit)) stop("frailtyPenal failed to fit on the full dataset")

# shape.weib / scale.weib are length-2; [1] is the parameter, [2] is unused padding.
# Omitting [1] recycles and silently corrupts every downstream conversion.
shape <- as.numeric(fit$shape.weib)[1L]
scale <- as.numeric(fit$scale.weib)[1L]

write.csv(
  data.frame(
    key   = c("shape_weib", "scale_weib", "theta", "var_theta", "istop",
              "loglik", "n", "n_events", "n_groups"),
    value = c(shape, scale, as.numeric(fit$theta)[1L], as.numeric(fit$varTheta)[1L],
              as.numeric(fit$istop)[1L], as.numeric(fit$logLik)[1L],
              as.numeric(fit$n)[1L], sum(d$event), length(unique(d$experiment_id)))
  ),
  file.path(out_dir, "meta.csv"), row.names = FALSE
)

coefs <- fit$coef
names(coefs) <- fit$.features
vcov <- fit$varH               # covariance of the betas only (nvar x nvar)
se <- sqrt(diag(as.matrix(vcov)))

write.csv(
  data.frame(term = fit$.features, beta_ph = as.numeric(coefs), se = as.numeric(se)),
  file.path(out_dir, "coef.csv"), row.names = FALSE
)
vc <- as.data.frame(as.matrix(vcov))
names(vc) <- fit$.features
vc <- cbind(term = fit$.features, vc)
write.csv(vc, file.path(out_dir, "vcov.csv"), row.names = FALSE)

# ---- cross-validation, looped inside this one R call ---------------------------------

if ("fold" %in% names(d) && any(d$fold >= 0L)) {
  folds <- sort(unique(d$fold[d$fold >= 0L]))
  lp <- rep(NA_real_, nrow(d))
  for (k in folds) {
    tr <- d[d$fold != k, , drop = FALSE]
    te <- d[d$fold == k, , drop = FALSE]
    if (sum(tr$event) == 0L) next
    f <- fit_one(tr, feat)
    if (is.null(f) || as.numeric(f$istop)[1L] != 1) next
    Xte <- as.matrix(te[, f$.features, drop = FALSE])
    lp[d$fold == k] <- as.vector(Xte %*% as.numeric(f$coef))
  }
  write.csv(
    data.frame(row_id = d$row_id, fold = d$fold, lp_ph = lp),
    file.path(out_dir, "cv_pred.csv"), row.names = FALSE
  )
}

cat("frailty_fit.R: ok\n")
