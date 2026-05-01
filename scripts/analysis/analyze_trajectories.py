"""Trajectory-level analytics.

Builds:

  * ``trajectory_stats.csv`` -- summary of api_calls / tokens /
    runtime / messages / bash calls by resolution outcome.
  * ``effort_buckets.csv`` -- resolution rate as a function of
    effort (api_calls bucket).  Designed to surface the "more steps
    do not necessarily mean more success" relationship.
  * ``phase_distribution.csv`` -- per-phase share of assistant
    messages and average rework events.
  * ``phase_giveup_rate.csv`` -- fraction of trajectories that emit
    at least one ``WORKFLOW: GIVEUP`` per phase, with Wilson CIs.
  * ``effort_resolution_corr.csv`` -- numerical correlations
    (Spearman / point-biserial) between effort and outcome.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import pointbiserialr, spearmanr

from utils import CSV_DIR, PHASES_ORDERED, ensure_out_dirs, wilson_ci


# Effort buckets sized so that each one contains at least ~30 instances.
API_CALL_BUCKETS: list[tuple[int, int, str]] = [
    (0, 200, "<200"),
    (200, 400, "200-399"),
    (400, 600, "400-599"),
    (600, 900, "600-899"),
    (900, 1300, "900-1299"),
    (1300, 10**6, "1300+"),
]


def _bucket(value: float, buckets: list[tuple[int, int, str]]) -> str:
    for lo, hi, lbl in buckets:
        if lo <= value < hi:
            return lbl
    return buckets[-1][2]


def _bucket_resolution(
    df: pd.DataFrame, col: str, buckets: list[tuple[int, int, str]]
) -> pd.DataFrame:
    df = df.copy()
    df["bucket"] = df[col].fillna(0).apply(lambda v: _bucket(v, buckets))
    rows: list[dict[str, object]] = []
    for _, _, label in buckets:
        sub = df[df["bucket"] == label]
        n = len(sub)
        k = int(sub["resolved"].astype(bool).sum())
        ci = wilson_ci(k, n)
        rows.append(dict(bucket=label, n=n, resolved=k, rate=ci.p, ci_lo=ci.lo, ci_hi=ci.hi))
    return pd.DataFrame(rows)


def _trajectory_stats(df: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "api_calls",
        "n_messages",
        "n_assistant",
        "n_user",
        "n_bash_calls",
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "runtime_sec",
    ]
    rows: list[dict[str, object]] = []
    for label, sub in [
        ("all_with_traj", df[df["has_traj"].astype(bool)]),
        ("resolved", df[df["resolved"].astype(bool)]),
        (
            "unresolved_with_traj",
            df[(~df["resolved"].astype(bool)) & df["has_traj"].astype(bool)],
        ),
    ]:
        rec: dict[str, object] = dict(group=label, n=len(sub))
        for c in cols:
            rec[f"{c}_mean"] = float(sub[c].mean()) if len(sub) else 0.0
            rec[f"{c}_p50"] = float(sub[c].median()) if len(sub) else 0.0
            rec[f"{c}_p95"] = float(sub[c].quantile(0.95)) if len(sub) else 0.0
        rows.append(rec)
    return pd.DataFrame(rows)


def _phase_distribution(df: pd.DataFrame) -> pd.DataFrame:
    """Per-phase average # of assistant messages and rework events."""

    has = df[df["has_traj"].astype(bool)]
    rows: list[dict[str, object]] = []
    total = sum(has[f"phase_{ph}_msgs"].sum() for ph in PHASES_ORDERED)
    for ph in PHASES_ORDERED:
        msgs = has[f"phase_{ph}_msgs"].sum()
        completes = has[f"phase_{ph}_complete"].sum()
        giveups = has[f"phase_{ph}_giveup"].sum()
        rows.append(
            dict(
                phase=ph,
                share_of_messages=float(msgs) / float(total) if total else 0.0,
                mean_msgs_per_instance=float(has[f"phase_{ph}_msgs"].mean()),
                mean_steps_visited=float(has[f"phase_{ph}_steps"].mean()),
                total_complete=int(completes),
                total_giveup=int(giveups),
                rework_factor=(int(completes) - len(has)) / max(1, len(has)),
            )
        )
    return pd.DataFrame(rows)


def _phase_giveup_rate(df: pd.DataFrame) -> pd.DataFrame:
    """Fraction of trajectories with >= 1 GIVEUP per phase, with Wilson CIs."""

    has = df[df["has_traj"].astype(bool)]
    n = len(has)
    rows: list[dict[str, object]] = []
    for ph in PHASES_ORDERED:
        k = int((has[f"phase_{ph}_giveup"] > 0).sum())
        ci = wilson_ci(k, n)
        rows.append(
            dict(
                phase=ph,
                instances_with_giveup=k,
                n=n,
                rate=ci.p,
                ci_lo=ci.lo,
                ci_hi=ci.hi,
            )
        )
    return pd.DataFrame(rows)


def _phase_resolution(df: pd.DataFrame) -> pd.DataFrame:
    """Average phase activity, split by resolution outcome.

    Helps reveal which phases discriminate most between resolved and
    unresolved trajectories.
    """

    has = df[df["has_traj"].astype(bool)]
    rows: list[dict[str, object]] = []
    for ph in PHASES_ORDERED:
        for label, sub in [
            ("resolved", has[has["resolved"].astype(bool)]),
            ("unresolved", has[~has["resolved"].astype(bool)]),
        ]:
            rows.append(
                dict(
                    phase=ph,
                    group=label,
                    mean_msgs=float(sub[f"phase_{ph}_msgs"].mean()),
                    mean_giveups=float(sub[f"phase_{ph}_giveup"].mean()),
                    mean_completes=float(sub[f"phase_{ph}_complete"].mean()),
                )
            )
    return pd.DataFrame(rows)


def _correlations(df: pd.DataFrame) -> pd.DataFrame:
    has = df[df["has_traj"].astype(bool)].copy()
    has["resolved_int"] = has["resolved"].astype(int)
    rows: list[dict[str, object]] = []
    for col in [
        "api_calls",
        "n_messages",
        "n_bash_calls",
        "prompt_tokens",
        "completion_tokens",
        "runtime_sec",
        "patch_churn",
        "patch_files",
        "patch_hunks",
        "phase_VERIFY_PATCH_giveup",
        "phase_VERIFY_PATCH_msgs",
        "phase_CODE_FIX_msgs",
    ]:
        if col not in has.columns:
            continue
        x = has[col].values.astype(float)
        y = has["resolved_int"].values.astype(float)
        rb, rb_p = pointbiserialr(y, x)
        sp, sp_p = spearmanr(x, y)
        rows.append(
            dict(
                metric=col,
                pointbiserial_r=float(rb),
                pointbiserial_p=float(rb_p),
                spearman_rho=float(sp),
                spearman_p=float(sp_p),
            )
        )
    return pd.DataFrame(rows)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--instances-csv", type=Path, default=CSV_DIR / "instances.csv")
    p.add_argument("--output-dir", type=Path, default=CSV_DIR)
    args = p.parse_args()

    ensure_out_dirs()
    df = pd.read_csv(args.instances_csv)
    for c in ["resolved", "has_traj"]:
        df[c] = df[c].astype(str).str.lower().isin(("true", "1", "yes"))

    stats = _trajectory_stats(df)
    eff = _bucket_resolution(df[df["has_traj"]], "api_calls", API_CALL_BUCKETS)
    phase_dist = _phase_distribution(df)
    phase_gv = _phase_giveup_rate(df)
    phase_res = _phase_resolution(df)
    corr = _correlations(df)

    stats.to_csv(args.output_dir / "trajectory_stats.csv", index=False)
    eff.to_csv(args.output_dir / "effort_buckets.csv", index=False)
    phase_dist.to_csv(args.output_dir / "phase_distribution.csv", index=False)
    phase_gv.to_csv(args.output_dir / "phase_giveup_rate.csv", index=False)
    phase_res.to_csv(args.output_dir / "phase_by_outcome.csv", index=False)
    corr.to_csv(args.output_dir / "effort_resolution_corr.csv", index=False)
    print(
        "[analyze_trajectories] wrote trajectory_stats.csv, effort_buckets.csv, "
        "phase_distribution.csv, phase_giveup_rate.csv, phase_by_outcome.csv, "
        "effort_resolution_corr.csv"
    )


if __name__ == "__main__":
    main()
