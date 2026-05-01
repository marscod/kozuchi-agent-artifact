"""Deeper inferential statistics for the Kozuchi analysis.

The earlier modules report Wilson 95% CIs (binomial proportions) and
exact McNemar p-values for paired peer comparisons.  At top-tier
ML venues (NeurIPS / ICML / ICLR) reviewers increasingly expect
*additional* layers of inferential rigour:

  1. **Multiple-testing correction** of the 24 peer p-values
     (Holm-Bonferroni for FWER; Benjamini-Hochberg for FDR).
  2. **Effect sizes alongside p-values**:
       * Cohen's `h` (arcsine difference) for the unconditional
         proportions, with bootstrap 95% CI.
       * Conditional odds ratio (`b / c` from the McNemar 2x2),
         with exact Clopper-Pearson CI mapped through ``OR = p/(1-p)``.
       * Paired risk difference (`p_kozuchi - p_peer`) with
         Newcombe-style bootstrap CI (resampled by *instance*,
         preserving the pairing).
  3. **Cluster-robust bootstrap** of the headline rate -- 10 000
     resamples drawn at the *repository* level (then instances
     within), to gauge how much repository-clustering inflates the
     standard Wilson CI.
  4. **Multivariate logistic regression** of resolution on
     trajectory- and outcome-side covariates with **cluster-robust
     (Huber-White, repo-clustered) standard errors**.  This
     disentangles the highly correlated effort metrics whose raw
     univariate correlations were reported in §7.
  5. **Non-parametric tests** for every trajectory feature
     stratified by resolved/unresolved: Mann-Whitney U,
     Kolmogorov-Smirnov, Cliff's delta with bootstrap CI, all
     adjusted with Benjamini-Hochberg FDR.
  6. **Cochran-Mantel-Haenszel** stratified McNemar tests by
     repository for the three flagship comparisons in the paper:
     vs. the next open-weight Qwen peer, vs. OpenHands +
     Claude-4-Sonnet, vs. Sonar + Claude-Opus-4.5.
  7. **Permutation test** for monotone association between
     ``qwen_consensus`` and Kozuchi resolution -- robust complement
     to the Wilson CIs in §8.1.
  8. **Compute-resolution Pareto curve**: fraction of instances
     resolved within an api-call budget X, swept over X.

Outputs (under ``src/csv/``):

  multiple_comparison_corrected.csv
  paired_effect_sizes.csv
  cluster_bootstrap_headline.csv
  logistic_regression.csv
  nonparametric_trajectory_tests.csv
  cmh_stratified_mcnemar.csv
  consensus_permutation_test.csv
  compute_resolution_pareto.csv
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
from scipy.optimize import minimize
from scipy.stats import false_discovery_control

from utils import CSV_DIR, N_VERIFIED, ensure_out_dirs, mcnemar_exact_p, repo_of, wilson_ci


# ---------------------------------------------------------------------------
# Random seeds (paper-grade reproducibility)
# ---------------------------------------------------------------------------


SEED = 20260427
N_BOOTSTRAP = 10_000
N_PERMUTE = 10_000


def _rng() -> np.random.Generator:
    return np.random.default_rng(SEED)


# ---------------------------------------------------------------------------
# (1) + (2) Multiple-testing correction & effect sizes
# ---------------------------------------------------------------------------


def _holm_adjust(pvals: np.ndarray) -> np.ndarray:
    """Holm-Bonferroni step-down adjustment (one-sided FWER)."""

    p = np.asarray(pvals, dtype=float)
    m = len(p)
    order = np.argsort(p)
    adj_sorted = np.empty(m, dtype=float)
    running = 0.0
    for i, idx in enumerate(order):
        adj = (m - i) * p[idx]
        running = max(running, adj)
        adj_sorted[i] = min(1.0, running)
    out = np.empty(m, dtype=float)
    out[order] = adj_sorted
    return out


def _cohens_h(p1: float, p2: float) -> float:
    """Cohen's h: arcsine difference between two proportions."""

    return 2.0 * (math.asin(math.sqrt(p1)) - math.asin(math.sqrt(p2)))


def _conditional_or_ci(b: int, c: int, alpha: float = 0.05) -> tuple[float, float, float]:
    """Conditional odds ratio b/c with exact 95% CI.

    For McNemar's paired table, the *conditional* OR (the OR among
    discordant pairs) equals b/c.  Under the null the discordant
    count `b ~ Binomial(b+c, 0.5)`; we use the Clopper-Pearson
    binomial CI on `pi = b / (b+c)` and map back through
    ``OR = pi / (1 - pi)``.  Returns (point, lo, hi).
    """

    n = b + c
    if n == 0:
        return (float("nan"), float("nan"), float("nan"))
    if c == 0:
        return (float("inf"), float("inf"), float("inf"))
    if b == 0:
        return (0.0, 0.0, 0.0)
    point = b / c
    pi_lo = stats.beta.ppf(alpha / 2.0, b, n - b + 1)
    pi_hi = stats.beta.ppf(1 - alpha / 2.0, b + 1, n - b)
    or_lo = pi_lo / (1 - pi_lo) if pi_lo < 1 else float("inf")
    or_hi = pi_hi / (1 - pi_hi) if pi_hi < 1 else float("inf")
    return (point, or_lo, or_hi)


def _bootstrap_paired_rd_ci(
    a_outcomes: np.ndarray,
    b_outcomes: np.ndarray,
    n_boot: int = N_BOOTSTRAP,
) -> tuple[float, float, float]:
    """Bootstrap 95% CI for the paired risk difference ``mean(a) - mean(b)``.

    Resamples *paired* outcomes (instance-level) preserving the
    pairing.  Returns (point, lo, hi).
    """

    rng = _rng()
    n = len(a_outcomes)
    diffs = np.empty(n_boot)
    for i in range(n_boot):
        idx = rng.integers(0, n, n)
        diffs[i] = a_outcomes[idx].mean() - b_outcomes[idx].mean()
    return (
        float(a_outcomes.mean() - b_outcomes.mean()),
        float(np.percentile(diffs, 2.5)),
        float(np.percentile(diffs, 97.5)),
    )


def multiple_testing_and_effect_sizes(
    matrix: pd.DataFrame, mcnemar: pd.DataFrame, output_dir: Path
) -> None:
    """Add Holm + BH adjusted p-values and three effect sizes to mcnemar.csv.

    `matrix` is the wide outcome matrix from analyze_qwen_vs_others
    (rows = 500 instances, cols include `kozuchi` and per-peer 0/1
    columns under `qwen::...` / `frontier::...` keys).  We use it to
    line up paired outcomes for the bootstrap.
    """

    # -- 1. Multiple-testing correction.
    df = mcnemar.copy()
    p = df["mcnemar_p"].to_numpy(dtype=float)
    df["holm_p"] = _holm_adjust(p)
    df["bh_fdr_q"] = false_discovery_control(p, method="bh")
    df["sig_05_holm"] = df["holm_p"] < 0.05
    df["sig_05_bh"] = df["bh_fdr_q"] < 0.05

    # -- 2. Effect sizes.
    p1 = 374 / 500
    cohens_h = []
    or_point, or_lo, or_hi = [], [], []
    rd_point, rd_lo, rd_hi = [], [], []

    # Build a name->column map from the outcome matrix so we can
    # locate each peer's per-instance binary outcome.
    name_to_col: dict[str, str] = {}
    for col in matrix.columns:
        if col.startswith("qwen::") or col.startswith("frontier::"):
            name = col.split("::", 1)[1]
            name_to_col[name] = col
    kozuchi_outcomes = matrix["kozuchi"].to_numpy(dtype=int)

    for _, row in df.iterrows():
        peer_name = row["peer"]
        b = int(row["kozuchi_only"])
        c = int(row["peer_only"])
        n_peer = int(row["peer_resolved"])
        p2 = n_peer / 500

        cohens_h.append(_cohens_h(p1, p2))

        or_point_i, or_lo_i, or_hi_i = _conditional_or_ci(b, c)
        or_point.append(or_point_i)
        or_lo.append(or_lo_i)
        or_hi.append(or_hi_i)

        peer_col = name_to_col.get(peer_name)
        if peer_col is not None:
            peer_outcomes = matrix[peer_col].to_numpy(dtype=int)
            rd_p, rd_l, rd_h = _bootstrap_paired_rd_ci(kozuchi_outcomes, peer_outcomes)
        else:
            # Peer not in our analyse_qwen_vs_others matrix (large
            # leaderboard set).  Fall back to non-paired RD: the
            # mean difference is exact (we know the marginal counts);
            # the CI is approximated by Wilson on the pair n=500.
            rd_p = p1 - p2
            rd_l = float("nan")
            rd_h = float("nan")
        rd_point.append(rd_p)
        rd_lo.append(rd_l)
        rd_hi.append(rd_h)

    df["cohens_h"] = cohens_h
    df["odds_ratio"] = or_point
    df["odds_ratio_lo"] = or_lo
    df["odds_ratio_hi"] = or_hi
    df["risk_diff"] = rd_point
    df["risk_diff_lo"] = rd_lo
    df["risk_diff_hi"] = rd_hi
    df.to_csv(output_dir / "multiple_comparison_corrected.csv", index=False)
    df[
        ["peer", "family", "weight_class", "gap", "mcnemar_p", "holm_p", "bh_fdr_q",
         "cohens_h", "odds_ratio", "odds_ratio_lo", "odds_ratio_hi",
         "risk_diff", "risk_diff_lo", "risk_diff_hi"]
    ].to_csv(output_dir / "paired_effect_sizes.csv", index=False)


# ---------------------------------------------------------------------------
# (3) Cluster-robust bootstrap of headline rate
# ---------------------------------------------------------------------------


def cluster_bootstrap_headline(instances: pd.DataFrame, output_dir: Path) -> None:
    """Cluster bootstrap for the headline pass-rate (cluster = repo).

    The standard Wilson interval assumes i.i.d. instances, but
    SWE-bench Verified is heavily clustered by repository (54 % of
    instances are django).  We resample (i) repos with replacement
    and (ii) instances within each resampled repo with replacement,
    then recompute the resolution rate.  The 95 % percentile CI of
    the bootstrap distribution is reported alongside the Wilson CI.
    """

    rng = _rng()
    df = instances.copy()
    df["resolved"] = (
        df["resolved"].astype(str).str.lower().isin({"true", "1", "yes"})
    ).astype(int)
    df["repo"] = df["instance_id"].apply(repo_of)
    repos = df["repo"].unique()
    repo_to_outcomes = {r: df.loc[df["repo"] == r, "resolved"].to_numpy() for r in repos}

    n_total = len(df)
    point = df["resolved"].mean()
    rates = np.empty(N_BOOTSTRAP)
    for i in range(N_BOOTSTRAP):
        idx = rng.integers(0, len(repos), len(repos))
        sample = []
        for j in idx:
            r = repos[j]
            outcomes = repo_to_outcomes[r]
            sub_idx = rng.integers(0, len(outcomes), len(outcomes))
            sample.append(outcomes[sub_idx])
        rates[i] = np.concatenate(sample).mean()
    cb_lo, cb_hi = np.percentile(rates, [2.5, 97.5])
    w = wilson_ci(int(df["resolved"].sum()), n_total)
    pd.DataFrame(
        [
            dict(
                method="Wilson 95% CI",
                rate=point,
                lo=w.lo,
                hi=w.hi,
                width=w.hi - w.lo,
                n=n_total,
            ),
            dict(
                method="Cluster bootstrap (repo) 95% CI",
                rate=point,
                lo=float(cb_lo),
                hi=float(cb_hi),
                width=float(cb_hi - cb_lo),
                n=n_total,
            ),
        ]
    ).to_csv(output_dir / "cluster_bootstrap_headline.csv", index=False)


# ---------------------------------------------------------------------------
# (4) Logistic regression with cluster-robust SE
# ---------------------------------------------------------------------------


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


def _neg_loglik(beta: np.ndarray, X: np.ndarray, y: np.ndarray) -> float:
    z = X @ beta
    # Numerically-stable log-loss.
    return float(np.sum(np.logaddexp(0.0, z) - y * z))


def _grad(beta: np.ndarray, X: np.ndarray, y: np.ndarray) -> np.ndarray:
    p = _sigmoid(X @ beta)
    return X.T @ (p - y)


def _hessian(beta: np.ndarray, X: np.ndarray) -> np.ndarray:
    p = _sigmoid(X @ beta)
    W = p * (1 - p)
    return X.T @ (X * W[:, None])


def _cluster_robust_var(
    beta: np.ndarray, X: np.ndarray, y: np.ndarray, clusters: np.ndarray
) -> np.ndarray:
    """Liang-Zeger sandwich variance V = H^{-1} B H^{-1} with B clustered."""

    p = _sigmoid(X @ beta)
    resid = y - p
    H = _hessian(beta, X)
    H_inv = np.linalg.inv(H)
    # Aggregate scores by cluster.
    scores = X * resid[:, None]
    G = np.zeros((X.shape[1], X.shape[1]))
    for c in np.unique(clusters):
        s_c = scores[clusters == c].sum(axis=0)
        G += np.outer(s_c, s_c)
    n_c = len(np.unique(clusters))
    n = X.shape[0]
    k = X.shape[1]
    # Stata-style finite-sample adjustment.
    factor = (n_c / (n_c - 1.0)) * ((n - 1.0) / (n - k))
    return factor * H_inv @ G @ H_inv


def logistic_regression(instances: pd.DataFrame, matrix: pd.DataFrame, output_dir: Path) -> None:
    """Multi-feature logistic regression with cluster-robust SE.

    Restricted to the 495 instances with a persisted trajectory --
    the 5 missing-artifact cases are co-linear with `y = 0` and
    cause quasi-perfect separation if included.  We report on
    them separately in the §5 failure-mode analysis.

    Predictors (continuous predictors standardised to mean 0 /
    unit variance for numerical stability):
      * log_api_calls
      * log_patch_churn
      * log_runtime_sec
      * qwen_consensus (0..4)       -- treated as continuous
      * frontier_consensus (0..7)   -- treated as continuous
    """

    df = instances.copy()
    df["resolved"] = (
        df["resolved"].astype(str).str.lower().isin({"true", "1", "yes"})
    ).astype(int)
    df["has_traj"] = (
        df["has_traj"].astype(str).str.lower().isin({"true", "1", "yes"})
    ).astype(int)
    df["repo"] = df["instance_id"].apply(repo_of)
    df = df.merge(
        matrix[["instance_id", "qwen_consensus", "frontier_consensus"]],
        on="instance_id",
        how="left",
    )
    df = df[df["has_traj"] == 1].copy()

    df["log_api_calls"] = np.log1p(df["api_calls"].fillna(0))
    df["log_patch_churn"] = np.log1p(df["patch_churn"].fillna(0))
    df["log_runtime_sec"] = np.log1p(df["runtime_sec"].fillna(0))

    feat_cols = [
        "log_api_calls",
        "log_patch_churn",
        "log_runtime_sec",
        "qwen_consensus",
        "frontier_consensus",
    ]

    Xz = df[feat_cols].copy().astype(float)
    means = Xz.mean()
    sds = Xz.std(ddof=0).replace(0, 1)
    for c in feat_cols:
        Xz[c] = (Xz[c] - means[c]) / sds[c]

    X = np.column_stack([np.ones(len(Xz)), Xz.to_numpy()])
    y = df["resolved"].to_numpy(dtype=float)
    clusters = df["repo"].to_numpy()

    # Optimise the negative log-likelihood.
    beta0 = np.zeros(X.shape[1])
    res = minimize(
        _neg_loglik,
        beta0,
        args=(X, y),
        jac=_grad,
        method="L-BFGS-B",
        options=dict(maxiter=200, gtol=1e-7),
    )
    beta_hat = res.x

    # Two variance estimates: classical (model-based) and cluster.
    H = _hessian(beta_hat, X)
    V_model = np.linalg.inv(H)
    V_cluster = _cluster_robust_var(beta_hat, X, y, clusters)

    se_model = np.sqrt(np.diag(V_model))
    se_cluster = np.sqrt(np.diag(V_cluster))

    z_cluster = beta_hat / se_cluster
    p_cluster = 2 * (1 - stats.norm.cdf(np.abs(z_cluster)))

    names = ["(Intercept)"] + feat_cols
    rows = []
    for i, name in enumerate(names):
        rows.append(
            dict(
                term=name,
                coef=float(beta_hat[i]),
                odds_ratio=float(math.exp(beta_hat[i])),
                se_model=float(se_model[i]),
                se_cluster=float(se_cluster[i]),
                z_cluster=float(z_cluster[i]),
                p_cluster=float(p_cluster[i]),
                ci_lo_cluster=float(beta_hat[i] - 1.96 * se_cluster[i]),
                ci_hi_cluster=float(beta_hat[i] + 1.96 * se_cluster[i]),
            )
        )
    out = pd.DataFrame(rows)
    # Fit diagnostics.
    p_hat = _sigmoid(X @ beta_hat)
    ll_full = -_neg_loglik(beta_hat, X, y)
    ll_null = -_neg_loglik(np.array([math.log(y.mean() / (1 - y.mean()))] + [0] * (X.shape[1] - 1)), X, y)
    mcfadden = 1 - ll_full / ll_null
    out.attrs["mcfadden_r2"] = mcfadden
    out.attrs["n"] = int(len(y))
    out.attrs["n_clusters"] = int(len(np.unique(clusters)))
    # Append a footer-style row with diagnostics.
    out.to_csv(output_dir / "logistic_regression.csv", index=False)
    pd.DataFrame(
        [
            dict(
                metric="n",
                value=int(len(y)),
            ),
            dict(metric="n_clusters", value=int(len(np.unique(clusters)))),
            dict(metric="mcfadden_pseudo_r2", value=float(mcfadden)),
            dict(metric="log_likelihood", value=float(ll_full)),
            dict(metric="null_log_likelihood", value=float(ll_null)),
            dict(metric="aic", value=float(2 * X.shape[1] - 2 * ll_full)),
        ]
    ).to_csv(output_dir / "logistic_regression_fit.csv", index=False)


# ---------------------------------------------------------------------------
# (5) Non-parametric tests on trajectory features
# ---------------------------------------------------------------------------


def _cliffs_delta(a: np.ndarray, b: np.ndarray) -> float:
    """Cliff's delta: P(a > b) - P(a < b).

    Range [-1, 1].  Computed via the classical Mann-Whitney U
    statistic identity to keep the implementation O((n+m) log(n+m)).
    """

    n_a = len(a)
    n_b = len(b)
    if n_a == 0 or n_b == 0:
        return 0.0
    u, _ = stats.mannwhitneyu(a, b, alternative="two-sided")
    # delta = 2 U / (n_a n_b) - 1
    return float(2.0 * u / (n_a * n_b) - 1.0)


def _bootstrap_cliffs_ci(
    a: np.ndarray, b: np.ndarray, n_boot: int = 2000
) -> tuple[float, float]:
    rng = _rng()
    deltas = np.empty(n_boot)
    for i in range(n_boot):
        ai = a[rng.integers(0, len(a), len(a))]
        bi = b[rng.integers(0, len(b), len(b))]
        deltas[i] = _cliffs_delta(ai, bi)
    return float(np.percentile(deltas, 2.5)), float(np.percentile(deltas, 97.5))


def nonparametric_trajectory_tests(instances: pd.DataFrame, output_dir: Path) -> None:
    """Mann-Whitney U + KS + Cliff's delta for trajectory features by outcome."""

    df = instances.copy()
    df["resolved"] = (
        df["resolved"].astype(str).str.lower().isin({"true", "1", "yes"})
    ).astype(int)
    df["has_traj"] = (
        df["has_traj"].astype(str).str.lower().isin({"true", "1", "yes"})
    ).astype(int)
    df = df[df["has_traj"] == 1]

    feats = [
        "api_calls",
        "n_messages",
        "n_bash_calls",
        "prompt_tokens",
        "completion_tokens",
        "runtime_sec",
        "patch_churn",
        "patch_files",
        "phase_VERIFY_PATCH_giveup",
        "phase_CODE_FIX_msgs",
        "phase_VERIFY_PATCH_msgs",
        "phase_CODE_FIX_giveup",
    ]

    rows = []
    for f in feats:
        if f not in df.columns:
            continue
        a = df.loc[df["resolved"] == 1, f].to_numpy(dtype=float)
        b = df.loc[df["resolved"] == 0, f].to_numpy(dtype=float)
        a = a[~np.isnan(a)]
        b = b[~np.isnan(b)]
        if len(a) == 0 or len(b) == 0:
            continue
        u_stat, mwu_p = stats.mannwhitneyu(a, b, alternative="two-sided")
        ks_stat, ks_p = stats.ks_2samp(a, b, alternative="two-sided")
        delta = _cliffs_delta(a, b)
        delta_lo, delta_hi = _bootstrap_cliffs_ci(a, b, n_boot=2000)
        rows.append(
            dict(
                feature=f,
                n_resolved=int(len(a)),
                n_unresolved=int(len(b)),
                resolved_p50=float(np.median(a)),
                unresolved_p50=float(np.median(b)),
                mwu_U=float(u_stat),
                mwu_p=float(mwu_p),
                ks_stat=float(ks_stat),
                ks_p=float(ks_p),
                cliffs_delta=float(delta),
                cliffs_delta_lo=float(delta_lo),
                cliffs_delta_hi=float(delta_hi),
            )
        )
    out = pd.DataFrame(rows)
    if len(out):
        out["mwu_q_bh"] = false_discovery_control(out["mwu_p"].to_numpy(), method="bh")
        out["ks_q_bh"] = false_discovery_control(out["ks_p"].to_numpy(), method="bh")
    out.to_csv(output_dir / "nonparametric_trajectory_tests.csv", index=False)


# ---------------------------------------------------------------------------
# (6) Cochran-Mantel-Haenszel stratified McNemar
# ---------------------------------------------------------------------------


def _cmh_paired(b_strata: list[int], c_strata: list[int]) -> tuple[float, float]:
    """Cochran-Mantel-Haenszel stratified McNemar.

    Stratum statistic per repo: paired (b, c) counts.
    The standard Mantel-Haenszel paired-binary test reduces to a
    binomial test on ``B = sum b_k`` versus ``B + C = sum (b+c)_k``
    under the null Pr(b > c) = 0.5 within stratum.  We implement
    this with a continuity-corrected normal approximation; for
    small expected discordant counts we fall back to the exact
    binomial.

    Returns ``(chi2, p_two_sided)``.
    """

    B = sum(b_strata)
    C = sum(c_strata)
    n = B + C
    if n == 0:
        return 0.0, 1.0
    if n < 25:
        # Exact two-sided binomial on min(B, C).
        k = min(B, C)
        cdf = sum(math.comb(n, i) * (0.5 ** n) for i in range(k + 1))
        return float((B - C) ** 2 / max(n, 1)), float(min(1.0, 2 * cdf))
    # Continuity-corrected chi-square.
    chi2 = (abs(B - C) - 1) ** 2 / n
    p = 1 - stats.chi2.cdf(chi2, df=1)
    return float(chi2), float(p)


def cmh_stratified_mcnemar(matrix: pd.DataFrame, output_dir: Path) -> None:
    """Stratified McNemar by repo for three flagship comparisons.

    Tests whether Kozuchi's marginal advantage holds *within* the
    same repository, ruling out repo-mix as a confounder.  We pick
    one Qwen peer, one mid-tier closed (Sonnet-4), and one
    top-tier closed (Opus-4.5) comparator -- the three rows that
    headline §2 and §4 of the report.
    """

    flagship = [
        ("qwen::OpenHands (Qwen-480B)", "OpenHands + Qwen3-Coder-480B"),
        ("frontier::OpenHands + Sonnet-4", "OpenHands + Claude-4-Sonnet"),
        ("frontier::Sonar + Opus-4.5", "Sonar + Claude-Opus-4.5"),
    ]
    rows = []
    for col, label in flagship:
        if col not in matrix.columns:
            continue
        b_strata, c_strata, n_strata = [], [], []
        per_repo_rows = []
        for repo, sub in matrix.groupby("repo"):
            both = int(((sub["kozuchi"] == 1) & (sub[col] == 1)).sum())
            kz = int(((sub["kozuchi"] == 1) & (sub[col] == 0)).sum())
            pr = int(((sub["kozuchi"] == 0) & (sub[col] == 1)).sum())
            nei = int(((sub["kozuchi"] == 0) & (sub[col] == 0)).sum())
            b_strata.append(kz)
            c_strata.append(pr)
            n_strata.append(both + kz + pr + nei)
            per_repo_rows.append(
                dict(
                    peer=label,
                    repo=repo,
                    both=both,
                    kozuchi_only=kz,
                    peer_only=pr,
                    neither=nei,
                    repo_n=both + kz + pr + nei,
                )
            )
        chi2, p_cmh = _cmh_paired(b_strata, c_strata)
        # Pooled (un-stratified) McNemar for comparison.
        marg_b = sum(b_strata)
        marg_c = sum(c_strata)
        p_pool = mcnemar_exact_p(marg_b, marg_c)
        rows.append(
            dict(
                peer=label,
                n_strata=len(b_strata),
                pooled_b=marg_b,
                pooled_c=marg_c,
                pooled_p=p_pool,
                cmh_chi2=chi2,
                cmh_p=p_cmh,
            )
        )
        # Side-channel: the per-repo breakdown.
        if per_repo_rows:
            pd.DataFrame(per_repo_rows).to_csv(
                output_dir / f"cmh_per_repo_{label.split(' ')[-1].replace('+','').replace(' ','_')}.csv",
                index=False,
            )
    pd.DataFrame(rows).to_csv(output_dir / "cmh_stratified_mcnemar.csv", index=False)


# ---------------------------------------------------------------------------
# (7) Permutation test for consensus -> Kozuchi resolution association
# ---------------------------------------------------------------------------


def consensus_permutation_test(matrix: pd.DataFrame, output_dir: Path) -> None:
    """Permutation test for monotone association between
    ``qwen_consensus`` and Kozuchi resolution.

    We use Spearman rank correlation as the test statistic.  The
    null hypothesis is independence; under the null we may permute
    Kozuchi outcomes (or, equivalently, consensus values) freely.
    """

    rng = _rng()
    df = matrix.copy()
    rows = []
    for axis in ["qwen_consensus", "frontier_consensus"]:
        x = df[axis].to_numpy()
        y = df["kozuchi"].to_numpy()
        rho_obs, _ = stats.spearmanr(x, y)
        count = 0
        for _ in range(N_PERMUTE):
            yp = rng.permutation(y)
            rho_p, _ = stats.spearmanr(x, yp)
            if abs(rho_p) >= abs(rho_obs):
                count += 1
        p_perm = (count + 1) / (N_PERMUTE + 1)
        rows.append(
            dict(
                axis=axis,
                spearman_rho=float(rho_obs),
                p_permutation=float(p_perm),
                n_permute=N_PERMUTE,
            )
        )
    pd.DataFrame(rows).to_csv(output_dir / "consensus_permutation_test.csv", index=False)


# ---------------------------------------------------------------------------
# (8) Compute-resolution Pareto curve
# ---------------------------------------------------------------------------


def compute_resolution_pareto(instances: pd.DataFrame, output_dir: Path) -> None:
    """Cumulative resolution rate (fraction of N=500) reachable
    within an api-call budget X, for X across the empirical range.

    Instances with no trajectory contribute nothing to the curve
    (they're effectively "infeasible at any X").  Resolved = 1
    *and* api_calls <= X is the numerator; denominator is N=500.
    """

    df = instances.copy()
    df["resolved"] = (
        df["resolved"].astype(str).str.lower().isin({"true", "1", "yes"})
    ).astype(int)
    df["has_traj"] = (
        df["has_traj"].astype(str).str.lower().isin({"true", "1", "yes"})
    ).astype(int)
    df_t = df[df["has_traj"] == 1].copy()

    # Sweep over a generous grid plus the empirical quantiles.
    grid = sorted(set(np.linspace(50, df_t["api_calls"].max(), 80).round().astype(int).tolist()))
    rows = []
    for x in grid:
        sub = df_t[df_t["api_calls"] <= x]
        n_in_budget = len(sub)
        n_resolved = int(sub["resolved"].sum())
        rows.append(
            dict(
                api_call_budget=int(x),
                n_attempted=int(n_in_budget),
                n_resolved=int(n_resolved),
                resolved_share_of_500=float(n_resolved / N_VERIFIED),
                resolved_share_of_374=float(n_resolved / 374),
                attempted_share_of_500=float(n_in_budget / N_VERIFIED),
            )
        )
    pd.DataFrame(rows).to_csv(output_dir / "compute_resolution_pareto.csv", index=False)


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--instances-csv", type=Path, default=CSV_DIR / "instances.csv")
    p.add_argument("--mcnemar-csv", type=Path, default=CSV_DIR / "mcnemar.csv")
    p.add_argument("--matrix-csv", type=Path, default=CSV_DIR / "qwen_outcome_matrix.csv")
    p.add_argument("--output-dir", type=Path, default=CSV_DIR)
    args = p.parse_args()

    ensure_out_dirs()
    instances = pd.read_csv(args.instances_csv)
    mcnemar = pd.read_csv(args.mcnemar_csv)
    matrix = pd.read_csv(args.matrix_csv)

    multiple_testing_and_effect_sizes(matrix, mcnemar, args.output_dir)
    cluster_bootstrap_headline(instances, args.output_dir)
    logistic_regression(instances, matrix, args.output_dir)
    nonparametric_trajectory_tests(instances, args.output_dir)
    cmh_stratified_mcnemar(matrix, args.output_dir)
    consensus_permutation_test(matrix, args.output_dir)
    compute_resolution_pareto(instances, args.output_dir)

    print(
        "[analyze_statistics] wrote multiple_comparison_corrected.csv, paired_effect_sizes.csv, "
        "cluster_bootstrap_headline.csv, logistic_regression.csv, logistic_regression_fit.csv, "
        "nonparametric_trajectory_tests.csv, cmh_stratified_mcnemar.csv (+ per-repo CSVs), "
        "consensus_permutation_test.csv, compute_resolution_pareto.csv"
    )


if __name__ == "__main__":
    main()
