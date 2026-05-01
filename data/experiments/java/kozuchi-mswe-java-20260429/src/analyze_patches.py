"""Patch-level analytics for the Multi-SWE Java run."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from utils import CSV_DIR, bool_series, ensure_out_dirs, wilson_ci


LOC_BUCKETS: list[tuple[int, int, str]] = [
    (0, 1, "0 (no diff)"),
    (1, 6, "1-5"),
    (6, 16, "6-15"),
    (16, 51, "16-50"),
    (51, 151, "51-150"),
    (151, 501, "151-500"),
    (501, 10**9, "501+"),
]

FILE_BUCKETS: list[tuple[int, int, str]] = [
    (0, 1, "0"),
    (1, 2, "1"),
    (2, 3, "2"),
    (3, 6, "3-5"),
    (6, 10**9, "6+"),
]


def _bucket(value: float, buckets: list[tuple[int, int, str]]) -> str:
    for lo, hi, label in buckets:
        if lo <= value < hi:
            return label
    return buckets[-1][2]


def _bucket_table(
    df: pd.DataFrame, col: str, buckets: list[tuple[int, int, str]]
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    bucketed = df.copy()
    bucketed["bucket"] = bucketed[col].fillna(0).apply(lambda v: _bucket(v, buckets))
    for _, _, label in buckets:
        sub = bucketed[bucketed["bucket"] == label]
        n = len(sub)
        k = int(sub["resolved"].sum())
        ci = wilson_ci(k, n)
        rows.append(
            {
                "bucket": label,
                "n": n,
                "resolved": k,
                "rate": ci.p,
                "ci_lo": ci.lo,
                "ci_hi": ci.hi,
                "report_valid": int(sub["report_valid"].sum()),
            }
        )
    return pd.DataFrame(rows)


def _summary(df: pd.DataFrame) -> pd.DataFrame:
    metrics = ["patch_added", "patch_removed", "patch_churn", "patch_hunks", "patch_files"]
    rows: list[dict[str, object]] = []
    for label, sub in [
        ("all", df),
        ("all_with_patch", df[df["has_patch_diff"]]),
        ("resolved", df[df["resolved"]]),
        ("unresolved_with_patch", df[(~df["resolved"]) & df["has_patch_diff"]]),
        ("patch_apply_failed", df[df["patch_apply_failed"]]),
    ]:
        rec: dict[str, object] = {"group": label, "n": len(sub)}
        for metric in metrics:
            rec[f"{metric}_mean"] = float(sub[metric].mean()) if len(sub) else 0.0
            rec[f"{metric}_p50"] = float(sub[metric].median()) if len(sub) else 0.0
            rec[f"{metric}_p95"] = float(sub[metric].quantile(0.95)) if len(sub) else 0.0
            rec[f"{metric}_max"] = float(sub[metric].max()) if len(sub) else 0.0
        rows.append(rec)
    return pd.DataFrame(rows)


def _per_repo_loc(df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for repo, sub in df.groupby("repo"):
        rows.append(
            {
                "repo": repo,
                "n": len(sub),
                "resolved": int(sub["resolved"].sum()),
                "rate": float(sub["resolved"].mean()),
                "churn_p50": float(sub["patch_churn"].median()),
                "churn_mean": float(sub["patch_churn"].mean()),
                "files_p50": float(sub["patch_files"].median()),
                "hunks_p50": float(sub["patch_hunks"].median()),
                "patch_apply_failures": int(sub["patch_apply_failed"].sum()),
            }
        )
    return pd.DataFrame(rows).sort_values("n", ascending=False)


def _by_difficulty(df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for difficulty, sub in df.groupby("difficulty"):
        rows.append(
            {
                "difficulty": difficulty,
                "n": len(sub),
                "resolved": int(sub["resolved"].sum()),
                "churn_p50": float(sub["patch_churn"].median()),
                "churn_mean": float(sub["patch_churn"].mean()),
                "files_p50": float(sub["patch_files"].median()),
                "hunks_p50": float(sub["patch_hunks"].median()),
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instances-csv", type=Path, default=CSV_DIR / "instances.csv")
    parser.add_argument("--output-dir", type=Path, default=CSV_DIR)
    args = parser.parse_args()

    ensure_out_dirs()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(args.instances_csv)
    for col in [
        "resolved",
        "report_valid",
        "has_patch_diff",
        "patch_is_empty",
        "patch_apply_failed",
    ]:
        df[col] = bool_series(df[col])

    _summary(df).to_csv(args.output_dir / "patch_summary.csv", index=False)
    _bucket_table(df, "patch_churn", LOC_BUCKETS).to_csv(
        args.output_dir / "patch_size_buckets.csv", index=False
    )
    _bucket_table(df, "patch_files", FILE_BUCKETS).to_csv(
        args.output_dir / "patch_files_buckets.csv", index=False
    )
    _per_repo_loc(df).to_csv(args.output_dir / "patch_repo_loc.csv", index=False)
    _by_difficulty(df).to_csv(args.output_dir / "patch_by_difficulty.csv", index=False)
    print(
        "[analyze_patches] wrote patch_summary.csv, patch_size_buckets.csv, "
        "patch_files_buckets.csv, patch_repo_loc.csv, patch_by_difficulty.csv"
    )


if __name__ == "__main__":
    main()
