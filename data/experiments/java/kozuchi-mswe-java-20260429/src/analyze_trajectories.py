"""Trajectory-level analytics for the Multi-SWE Java run."""

from __future__ import annotations

import argparse
import warnings
from pathlib import Path

import pandas as pd
from scipy.stats import ConstantInputWarning, pointbiserialr, spearmanr

from utils import CSV_DIR, PHASES_ORDERED, bool_series, ensure_out_dirs, wilson_ci


API_CALL_BUCKETS: list[tuple[int, int, str]] = [
    (0, 400, "<400"),
    (400, 500, "400-499"),
    (500, 600, "500-599"),
    (600, 800, "600-799"),
    (800, 1200, "800-1199"),
    (1200, 10**9, "1200+"),
]


def _bucket(value: float, buckets: list[tuple[int, int, str]]) -> str:
    for lo, hi, label in buckets:
        if lo <= value < hi:
            return label
    return buckets[-1][2]


def _bucket_resolution(
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
        rows.append({"bucket": label, "n": n, "resolved": k, "rate": ci.p, "ci_lo": ci.lo, "ci_hi": ci.hi})
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
        ("all_with_full_traj", df[df["has_traj"]]),
        ("resolved", df[df["resolved"] & df["has_traj"]]),
        ("unresolved_with_full_traj", df[(~df["resolved"]) & df["has_traj"]]),
    ]:
        rec: dict[str, object] = {"group": label, "n": len(sub)}
        for col in cols:
            rec[f"{col}_mean"] = float(sub[col].mean()) if len(sub) else 0.0
            rec[f"{col}_p50"] = float(sub[col].median()) if len(sub) else 0.0
            rec[f"{col}_p95"] = float(sub[col].quantile(0.95)) if len(sub) else 0.0
        rows.append(rec)
    return pd.DataFrame(rows)


def _phase_distribution(df: pd.DataFrame) -> pd.DataFrame:
    has = df[df["has_traj"]]
    total_messages = sum(has[f"phase_{phase}_msgs"].sum() for phase in PHASES_ORDERED)
    rows: list[dict[str, object]] = []
    for phase in PHASES_ORDERED:
        messages = int(has[f"phase_{phase}_msgs"].sum())
        rows.append(
            {
                "phase": phase,
                "share_of_messages": messages / total_messages if total_messages else 0.0,
                "mean_msgs_per_instance": float(has[f"phase_{phase}_msgs"].mean()),
                "mean_steps_visited": float(has[f"phase_{phase}_steps"].mean()),
                "total_complete": int(has[f"phase_{phase}_complete"].sum()),
                "total_giveup": int(has[f"phase_{phase}_giveup"].sum()),
                "visited_rate": float(has[f"phase_{phase}_visited"].mean()),
            }
        )
    return pd.DataFrame(rows)


def _phase_giveup_rate(df: pd.DataFrame) -> pd.DataFrame:
    has = df[df["has_traj"]]
    n = len(has)
    rows: list[dict[str, object]] = []
    for phase in PHASES_ORDERED:
        k = int((has[f"phase_{phase}_giveup"] > 0).sum())
        ci = wilson_ci(k, n)
        rows.append(
            {
                "phase": phase,
                "instances_with_giveup": k,
                "n": n,
                "rate": ci.p,
                "ci_lo": ci.lo,
                "ci_hi": ci.hi,
            }
        )
    return pd.DataFrame(rows)


def _phase_resolution(df: pd.DataFrame) -> pd.DataFrame:
    has = df[df["has_traj"]]
    rows: list[dict[str, object]] = []
    for phase in PHASES_ORDERED:
        for label, sub in [("resolved", has[has["resolved"]]), ("unresolved", has[~has["resolved"]])]:
            rows.append(
                {
                    "phase": phase,
                    "group": label,
                    "mean_msgs": float(sub[f"phase_{phase}_msgs"].mean()) if len(sub) else 0.0,
                    "mean_giveups": float(sub[f"phase_{phase}_giveup"].mean()) if len(sub) else 0.0,
                    "mean_completes": float(sub[f"phase_{phase}_complete"].mean()) if len(sub) else 0.0,
                    "visited_rate": float(sub[f"phase_{phase}_visited"].mean()) if len(sub) else 0.0,
                }
            )
    return pd.DataFrame(rows)


def _correlations(df: pd.DataFrame) -> pd.DataFrame:
    has = df[df["has_traj"]].copy()
    has["resolved_int"] = has["resolved"].astype(int)
    rows: list[dict[str, object]] = []
    metrics = [
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
    ]
    for col in metrics:
        if col not in has.columns:
            continue
        x = has[col].astype(float)
        y = has["resolved_int"].astype(float)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ConstantInputWarning)
            rb, rb_p = pointbiserialr(y, x)
            sp, sp_p = spearmanr(x, y)
        rows.append(
            {
                "metric": col,
                "pointbiserial_r": float(rb),
                "pointbiserial_p": float(rb_p),
                "spearman_rho": float(sp),
                "spearman_p": float(sp_p),
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
    for col in ["resolved", "has_traj", "has_traj_file"]:
        df[col] = bool_series(df[col])

    _trajectory_stats(df).to_csv(args.output_dir / "trajectory_stats.csv", index=False)
    _bucket_resolution(df[df["has_traj"]], "api_calls", API_CALL_BUCKETS).to_csv(
        args.output_dir / "effort_buckets.csv", index=False
    )
    _phase_distribution(df).to_csv(args.output_dir / "phase_distribution.csv", index=False)
    _phase_giveup_rate(df).to_csv(args.output_dir / "phase_giveup_rate.csv", index=False)
    _phase_resolution(df).to_csv(args.output_dir / "phase_by_outcome.csv", index=False)
    _correlations(df).to_csv(args.output_dir / "effort_resolution_corr.csv", index=False)
    print(
        "[analyze_trajectories] wrote trajectory_stats.csv, effort_buckets.csv, "
        "phase_distribution.csv, phase_giveup_rate.csv, phase_by_outcome.csv, "
        "effort_resolution_corr.csv"
    )


if __name__ == "__main__":
    main()
