"""Patch-level analytics.

Builds the following CSVs from the per-instance table:

  * ``patch_summary.csv`` -- aggregate statistics over the 495
    submitted patches (mean / median / p95 of LOC, files, hunks),
    split by resolution outcome.
  * ``patch_size_buckets.csv`` -- patch size vs. resolution rate,
    binned into LOC churn buckets so we can see whether the agent
    is biased towards minimal patches.
  * ``patch_files_buckets.csv`` -- analogue of the above for the
    number of files touched.
  * ``patch_repo_loc.csv`` -- per-repository median patch churn,
    used in the per-repo discussion.

Patch metrics (LOC added / removed / churn, hunks, files) are
computed in :mod:`extract_metadata` directly from the unified diff;
this module only aggregates.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from utils import CSV_DIR, ensure_out_dirs, wilson_ci


# Patch-size bucket boundaries chosen so that each bucket is
# populated with at least ~30 patches in our run.  Reported in LOC
# churn (added + removed).
LOC_BUCKETS: list[tuple[int, int, str]] = [
    (0, 1, "0 (no diff)"),
    (1, 5, "1-4"),
    (5, 11, "5-10"),
    (11, 26, "11-25"),
    (26, 51, "26-50"),
    (51, 101, "51-100"),
    (101, 10**6, "101+"),
]
FILE_BUCKETS: list[tuple[int, int, str]] = [
    (0, 1, "0"),
    (1, 2, "1"),
    (2, 3, "2"),
    (3, 5, "3-4"),
    (5, 100, "5+"),
]


def _bucket(value: float, buckets: list[tuple[int, int, str]]) -> str:
    for lo, hi, lbl in buckets:
        if lo <= value < hi:
            return lbl
    return buckets[-1][2]


def _bucket_table(
    df: pd.DataFrame, col: str, buckets: list[tuple[int, int, str]]
) -> pd.DataFrame:
    """Bucketise ``col`` and report resolution rate per bucket with CIs."""

    df = df.copy()
    df["bucket"] = df[col].fillna(0).apply(lambda v: _bucket(v, buckets))
    rows: list[dict[str, object]] = []
    bucket_order = [b[2] for b in buckets]
    for label in bucket_order:
        sub = df[df["bucket"] == label]
        n = len(sub)
        k = int(sub["resolved"].astype(bool).sum())
        ci = wilson_ci(k, n)
        rows.append(
            dict(
                bucket=label,
                n=n,
                resolved=k,
                rate=ci.p,
                ci_lo=ci.lo,
                ci_hi=ci.hi,
            )
        )
    return pd.DataFrame(rows)


def _summary(df: pd.DataFrame) -> pd.DataFrame:
    """Mean / median / p95 of patch metrics, split by outcome."""

    metrics = ["patch_added", "patch_removed", "patch_churn", "patch_hunks", "patch_files"]
    rows: list[dict[str, object]] = []
    for label, subset in [
        ("all_with_patch", df[df["has_patch_diff"].astype(bool)]),
        ("resolved", df[df["resolved"].astype(bool) & df["has_patch_diff"].astype(bool)]),
        (
            "unresolved_with_patch",
            df[(~df["resolved"].astype(bool)) & df["has_patch_diff"].astype(bool)],
        ),
    ]:
        rec: dict[str, object] = dict(group=label, n=len(subset))
        for m in metrics:
            rec[f"{m}_mean"] = float(subset[m].mean()) if len(subset) else 0.0
            rec[f"{m}_p50"] = float(subset[m].median()) if len(subset) else 0.0
            rec[f"{m}_p95"] = float(subset[m].quantile(0.95)) if len(subset) else 0.0
            rec[f"{m}_max"] = float(subset[m].max()) if len(subset) else 0.0
        rows.append(rec)
    return pd.DataFrame(rows)


def _per_repo_loc(df: pd.DataFrame) -> pd.DataFrame:
    """Per-repository median patch churn, separately for resolved /
    unresolved -- useful when discussing where the agent struggles."""

    rows: list[dict[str, object]] = []
    for repo, sub in df.groupby("repo"):
        rec = dict(
            repo=repo,
            n=len(sub),
            resolved_n=int(sub["resolved"].astype(bool).sum()),
            churn_p50=float(sub["patch_churn"].median()),
            churn_mean=float(sub["patch_churn"].mean()),
            files_p50=float(sub["patch_files"].median()),
            hunks_p50=float(sub["patch_hunks"].median()),
        )
        res = sub[sub["resolved"].astype(bool)]
        unres = sub[~sub["resolved"].astype(bool) & sub["has_patch_diff"].astype(bool)]
        rec["resolved_churn_p50"] = (
            float(res["patch_churn"].median()) if len(res) else None
        )
        rec["unresolved_churn_p50"] = (
            float(unres["patch_churn"].median()) if len(unres) else None
        )
        rows.append(rec)
    return pd.DataFrame(rows).sort_values("n", ascending=False).reset_index(drop=True)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--instances-csv", type=Path, default=CSV_DIR / "instances.csv")
    p.add_argument("--output-dir", type=Path, default=CSV_DIR)
    args = p.parse_args()

    ensure_out_dirs()
    df = pd.read_csv(args.instances_csv)
    for col in ["resolved", "has_patch_diff", "patch_is_empty"]:
        df[col] = df[col].astype(str).str.lower().isin(("true", "1", "yes"))

    s = _summary(df)
    loc = _bucket_table(df, "patch_churn", LOC_BUCKETS)
    files_b = _bucket_table(df, "patch_files", FILE_BUCKETS)
    per_repo = _per_repo_loc(df)

    s.to_csv(args.output_dir / "patch_summary.csv", index=False)
    loc.to_csv(args.output_dir / "patch_size_buckets.csv", index=False)
    files_b.to_csv(args.output_dir / "patch_files_buckets.csv", index=False)
    per_repo.to_csv(args.output_dir / "patch_repo_loc.csv", index=False)
    print("[analyze_patches] wrote patch_summary.csv, patch_size_buckets.csv, patch_files_buckets.csv, patch_repo_loc.csv")


if __name__ == "__main__":
    main()
