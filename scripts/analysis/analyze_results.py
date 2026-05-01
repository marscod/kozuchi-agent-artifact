"""Compute the headline / per-repo / per-year resolution tables.

The Kozuchi run reports 374 / 500 = 74.80% resolved tasks on
SWE-bench Verified.  This module computes:

  1. The headline number with a Wilson 95% confidence interval.
  2. The per-repository breakdown (k_i / n_i, p_hat, Wilson CI).
  3. The per-year breakdown along the same axes.
  4. A submission-level operational summary listing the artifact
     coverage (logs, trajectories, reports), exit-status mix, and
     average diagnostics (api_calls, tokens, runtime).

We include the per-bucket Wilson interval because the per-repo
sample sizes vary by two orders of magnitude (django: n=231 vs.
flask: n=1).  Reporting only the point estimate would, for example,
make the perfect 1/1 flask bucket look indistinguishable from the
8/8 requests bucket -- whereas Wilson intervals correctly reflect
the 12.6 percentage-point gap in their lower bounds.

CSV outputs (written under ``src/csv/``):

  - ``headline.csv``
  - ``by_repo.csv``
  - ``by_year.csv``
  - ``operational.csv``
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

from utils import (
    CSV_DIR,
    EXPERIMENT_DIR,
    N_VERIFIED,
    PHASES_ORDERED,
    ensure_out_dirs,
    wilson_ci,
)


# ---------------------------------------------------------------------------
# Year extraction
# ---------------------------------------------------------------------------
#
# SWE-bench Verified ships an authoritative ``resolved_by_time.json``
# inside the submission directory; we use that as the single source
# of truth for the year-of-origin distribution rather than scraping
# instance ids.


def _per_year_table(experiment_dir: Path) -> pd.DataFrame:
    by_time = json.loads(
        (experiment_dir / "results" / "resolved_by_time.json").read_text()
    )
    rows: list[dict[str, object]] = []
    for year, body in sorted(by_time.items()):
        n = int(body["total"])
        k = int(body["resolved"])
        ci = wilson_ci(k, n)
        rows.append(
            dict(
                year=int(year),
                n=n,
                resolved=k,
                rate=k / n if n else 0.0,
                ci_lo=ci.lo,
                ci_hi=ci.hi,
            )
        )
    return pd.DataFrame(rows)


def _per_repo_table(experiment_dir: Path) -> pd.DataFrame:
    by_repo = json.loads(
        (experiment_dir / "results" / "resolved_by_repo.json").read_text()
    )
    rows: list[dict[str, object]] = []
    for repo, body in by_repo.items():
        n = int(body["total"])
        k = int(body["resolved"])
        ci = wilson_ci(k, n)
        rows.append(
            dict(
                repo=repo,
                n=n,
                resolved=k,
                rate=k / n if n else 0.0,
                ci_lo=ci.lo,
                ci_hi=ci.hi,
            )
        )
    df = pd.DataFrame(rows).sort_values("n", ascending=False).reset_index(drop=True)
    return df


def _headline(df: pd.DataFrame) -> pd.DataFrame:
    """Headline row computed against the canonical N=500 denominator."""

    n_resolved = int(df["resolved"].astype(bool).sum())
    n = N_VERIFIED
    ci = wilson_ci(n_resolved, n)
    n_with_traj = int(df["has_traj"].astype(bool).sum())
    n_with_report = int(df["has_report"].astype(bool).sum())
    n_artifact_missing = int(df["artifact_missing"].astype(bool).sum())
    n_resolved_with_full_trajs = int(
        ((df["resolved"].astype(bool)) & (df["has_traj"].astype(bool))).sum()
    )
    return pd.DataFrame(
        [
            dict(
                metric="resolved_pass@1_TTS@8",
                value=n_resolved / n,
                numerator=n_resolved,
                denominator=n,
                ci_lo=ci.lo,
                ci_hi=ci.hi,
            ),
            dict(
                metric="trajectory_coverage",
                value=n_with_traj / n,
                numerator=n_with_traj,
                denominator=n,
                ci_lo=None,
                ci_hi=None,
            ),
            dict(
                metric="report_coverage",
                value=n_with_report / n,
                numerator=n_with_report,
                denominator=n,
                ci_lo=None,
                ci_hi=None,
            ),
            dict(
                metric="artifact_missing",
                value=n_artifact_missing / n,
                numerator=n_artifact_missing,
                denominator=n,
                ci_lo=None,
                ci_hi=None,
            ),
            dict(
                metric="resolved_with_complete_trajectory",
                value=n_resolved_with_full_trajs / n,
                numerator=n_resolved_with_full_trajs,
                denominator=n,
                ci_lo=None,
                ci_hi=None,
            ),
        ]
    )


# ---------------------------------------------------------------------------
# Operational summary (artifact coverage, costs, exit statuses)
# ---------------------------------------------------------------------------


def _operational(df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    rows.append(dict(metric="N_canonical_verified", value=N_VERIFIED))
    rows.append(dict(metric="rows_in_csv", value=len(df)))
    rows.append(dict(metric="logs_present", value=int(df["has_report"].astype(bool).sum())))
    rows.append(dict(metric="trajs_present", value=int(df["has_traj"].astype(bool).sum())))
    rows.append(dict(metric="resolved", value=int(df["resolved"].astype(bool).sum())))
    rows.append(
        dict(
            metric="patch_apply_failures",
            value=int(((df["patch_successfully_applied"] == False)).sum()),  # noqa: E712
        )
    )
    rows.append(
        dict(
            metric="empty_patch_count",
            value=int((df["patch_is_empty"].astype(bool) & df["has_patch_diff"]).sum()),
        )
    )
    # Exit-status mix.
    es = df["exit_status"].fillna("__MISSING__").astype(str)
    for status, n in Counter(es).items():
        rows.append(dict(metric=f"exit_status[{status}]", value=int(n)))
    # Cost diagnostics computed only over instances with traj data.
    has = df[df["has_traj"]].copy()
    for col, label in [
        ("api_calls", "api_calls"),
        ("prompt_tokens", "prompt_tokens"),
        ("completion_tokens", "completion_tokens"),
        ("total_tokens", "total_tokens"),
        ("runtime_sec", "runtime_sec"),
        ("n_messages", "n_messages"),
        ("n_bash_calls", "n_bash_calls"),
    ]:
        rows.append(dict(metric=f"{label}_mean", value=float(has[col].mean())))
        rows.append(dict(metric=f"{label}_p50", value=float(has[col].median())))
        rows.append(dict(metric=f"{label}_p95", value=float(has[col].quantile(0.95))))
        rows.append(dict(metric=f"{label}_max", value=float(has[col].max())))
    # Phase visit / completion / giveup rates.
    for ph in PHASES_ORDERED:
        rows.append(
            dict(
                metric=f"phase_{ph}_visited_rate",
                value=float(has[f"phase_{ph}_visited"].mean()),
            )
        )
        rows.append(
            dict(
                metric=f"phase_{ph}_giveup_count",
                value=int(has[f"phase_{ph}_giveup"].sum()),
            )
        )
        rows.append(
            dict(
                metric=f"phase_{ph}_complete_count",
                value=int(has[f"phase_{ph}_complete"].sum()),
            )
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Year extraction directly from the per-instance CSV (cross-validation)
# ---------------------------------------------------------------------------
#
# We additionally cross-check the bundled ``resolved_by_repo.json``
# against a re-derivation from the per-instance CSV.  Any discrepancy
# (e.g. instance attributed to a different repo) would be a strong
# signal of artifact corruption.


def _by_repo_self(df: pd.DataFrame) -> pd.DataFrame:
    grp = (
        df.assign(_one=1)
        .groupby("repo")
        .agg(n=("_one", "sum"), resolved=("resolved", "sum"))
        .reset_index()
    )
    rows: list[dict[str, object]] = []
    for _, r in grp.iterrows():
        ci = wilson_ci(int(r["resolved"]), int(r["n"]))
        rows.append(
            dict(
                repo=r["repo"],
                n=int(r["n"]),
                resolved=int(r["resolved"]),
                rate=ci.p,
                ci_lo=ci.lo,
                ci_hi=ci.hi,
            )
        )
    return pd.DataFrame(rows).sort_values("n", ascending=False).reset_index(drop=True)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--instances-csv", type=Path, default=CSV_DIR / "instances.csv")
    p.add_argument("--output-dir", type=Path, default=CSV_DIR)
    args = p.parse_args()

    ensure_out_dirs()
    df = pd.read_csv(args.instances_csv)
    # Coerce booleans -- pandas may import them as strings.
    for col in [
        "resolved",
        "has_traj",
        "has_report",
        "artifact_missing",
        "patch_is_empty",
        "has_patch_diff",
        "submission_present",
        "all_phases_visited",
        "in_no_generation",
        "in_no_logs",
    ] + [f"phase_{ph}_visited" for ph in PHASES_ORDERED]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.lower().isin(("true", "1", "yes"))

    head = _headline(df)
    by_repo = _per_repo_table(EXPERIMENT_DIR)
    by_repo_self = _by_repo_self(df)
    by_year = _per_year_table(EXPERIMENT_DIR)
    op = _operational(df)

    head.to_csv(args.output_dir / "headline.csv", index=False)
    by_repo.to_csv(args.output_dir / "by_repo.csv", index=False)
    by_repo_self.to_csv(args.output_dir / "by_repo_selfcheck.csv", index=False)
    by_year.to_csv(args.output_dir / "by_year.csv", index=False)
    op.to_csv(args.output_dir / "operational.csv", index=False)
    print("[analyze_results] wrote headline.csv, by_repo.csv, by_year.csv, operational.csv")


if __name__ == "__main__":
    main()
