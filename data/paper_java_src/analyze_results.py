"""Compute headline and operational tables for the Multi-SWE Java run."""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

import pandas as pd

from utils import CSV_DIR, PHASES_ORDERED, bool_series, ensure_out_dirs, wilson_ci


BOOL_COLS = [
    "resolved",
    "has_report",
    "report_valid",
    "has_traj_file",
    "has_traj",
    "traj_is_stub",
    "has_patch_diff",
    "patch_is_empty",
    "patch_apply_failed",
    "patch_successfully_applied",
    "artefact_missing",
]


def _prepare(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in BOOL_COLS:
        if col in out.columns:
            out[col] = bool_series(out[col])
    return out


def _rate_row(metric: str, k: int, n: int) -> dict[str, object]:
    ci = wilson_ci(k, n)
    return {
        "metric": metric,
        "value": ci.p,
        "numerator": k,
        "denominator": n,
        "ci_lo": ci.lo,
        "ci_hi": ci.hi,
    }


def _headline(df: pd.DataFrame) -> pd.DataFrame:
    n = len(df)
    rows = [
        _rate_row("resolved_xcheck_at_8", int(df["resolved"].sum()), n),
        _rate_row("report_valid", int(df["report_valid"].sum()), n),
        _rate_row("report_coverage", int(df["has_report"].sum()), n),
        _rate_row("trajectory_file_coverage", int(df["has_traj_file"].sum()), n),
        _rate_row("full_trajectory_coverage", int(df["has_traj"].sum()), n),
        _rate_row("patch_coverage", int(df["has_patch_diff"].sum()), n),
        _rate_row("patch_apply_failure_rate", int(df["patch_apply_failed"].sum()), n),
        _rate_row(
            "report_valid_not_leaderboard_resolved",
            int((df["report_valid"] & ~df["resolved"]).sum()),
            n,
        ),
    ]
    return pd.DataFrame(rows)


def _group_rate(df: pd.DataFrame, group_col: str) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for value, sub in df.groupby(group_col, dropna=False):
        n = len(sub)
        k = int(sub["resolved"].sum())
        ci = wilson_ci(k, n)
        rows.append(
            {
                group_col: value,
                "n": n,
                "resolved": k,
                "rate": ci.p,
                "ci_lo": ci.lo,
                "ci_hi": ci.hi,
                "report_valid": int(sub["report_valid"].sum()),
                "full_trajs": int(sub["has_traj"].sum()),
                "patch_apply_failures": int(sub["patch_apply_failed"].sum()),
            }
        )
    return pd.DataFrame(rows).sort_values(["n", "resolved"], ascending=False)


def _operational(df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    rows.extend(
        [
            {"metric": "rows_in_csv", "value": len(df)},
            {"metric": "resolved", "value": int(df["resolved"].sum())},
            {"metric": "report_valid", "value": int(df["report_valid"].sum())},
            {"metric": "reports_present", "value": int(df["has_report"].sum())},
            {"metric": "trajectory_files_present", "value": int(df["has_traj_file"].sum())},
            {"metric": "full_trajectories_present", "value": int(df["has_traj"].sum())},
            {"metric": "stub_trajectories", "value": int(df["traj_is_stub"].sum())},
            {"metric": "patches_present", "value": int(df["has_patch_diff"].sum())},
            {"metric": "empty_patches", "value": int(df["patch_is_empty"].sum())},
            {"metric": "patch_apply_failures", "value": int(df["patch_apply_failed"].sum())},
            {
                "metric": "report_valid_not_leaderboard_resolved",
                "value": int((df["report_valid"] & ~df["resolved"]).sum()),
            },
        ]
    )

    for status, count in Counter(df["exit_status"].fillna("__MISSING__").astype(str)).items():
        rows.append({"metric": f"exit_status[{status}]", "value": int(count)})

    has = df[df["has_traj"]].copy()
    for col in [
        "api_calls",
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "runtime_sec",
        "n_messages",
        "n_bash_calls",
    ]:
        rows.append({"metric": f"{col}_mean", "value": float(has[col].mean())})
        rows.append({"metric": f"{col}_p50", "value": float(has[col].median())})
        rows.append({"metric": f"{col}_p95", "value": float(has[col].quantile(0.95))})
        rows.append({"metric": f"{col}_max", "value": float(has[col].max())})

    for phase in PHASES_ORDERED:
        rows.append(
            {
                "metric": f"phase_{phase}_visited_rate",
                "value": float(has[f"phase_{phase}_visited"].mean()),
            }
        )
        rows.append(
            {
                "metric": f"phase_{phase}_giveup_count",
                "value": int(has[f"phase_{phase}_giveup"].sum()),
            }
        )
        rows.append(
            {
                "metric": f"phase_{phase}_complete_count",
                "value": int(has[f"phase_{phase}_complete"].sum()),
            }
        )
    return pd.DataFrame(rows)


def _report_valid_vs_results(df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for report_valid in (False, True):
        for resolved in (False, True):
            sub = df[(df["report_valid"] == report_valid) & (df["resolved"] == resolved)]
            rows.append(
                {
                    "report_valid": report_valid,
                    "leaderboard_resolved": resolved,
                    "n": len(sub),
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
    df = _prepare(pd.read_csv(args.instances_csv))

    _headline(df).to_csv(args.output_dir / "headline.csv", index=False)
    _group_rate(df, "repo").to_csv(args.output_dir / "by_repo.csv", index=False)
    _group_rate(df, "difficulty").to_csv(args.output_dir / "by_difficulty.csv", index=False)
    _operational(df).to_csv(args.output_dir / "operational.csv", index=False)
    _report_valid_vs_results(df).to_csv(
        args.output_dir / "report_valid_vs_results.csv", index=False
    )
    print(
        "[analyze_results] wrote headline.csv, by_repo.csv, by_difficulty.csv, "
        "operational.csv, report_valid_vs_results.csv"
    )


if __name__ == "__main__":
    main()
