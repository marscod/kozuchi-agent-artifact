"""Failure-mode analysis based on Multi-SWE Java report.json files."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from utils import CSV_DIR, bool_series, ensure_out_dirs


def _classify(row: pd.Series) -> str:
    if bool(row["resolved"]):
        return "resolved"
    if not bool(row["has_report"]):
        return "missing_report"
    if bool(row["patch_apply_failed"]):
        return "patch_apply_failed"
    if not bool(row["has_patch_diff"]):
        return "missing_patch"
    if bool(row["patch_is_empty"]):
        return "empty_patch"
    if bool(row["report_valid"]):
        return "report_valid_not_leaderboard_resolved"

    headline = str(row.get("report_error_headline", "") or "").lower()
    fix_total = (
        int(row.get("fix_patch_result_passed", 0) or 0)
        + int(row.get("fix_patch_result_failed", 0) or 0)
        + int(row.get("fix_patch_result_skipped", 0) or 0)
    )
    if fix_total == 0 or "no test results were captured" in headline:
        return "no_fix_test_results"
    if "no test cases transitioned" in headline:
        return "no_fixed_tests"
    if "before applying the fix patch, the test passed" in headline:
        return "regressed_passing_tests"
    if "anomalous pattern" in headline:
        return "anomalous_test_pattern"
    if int(row.get("fix_patch_result_failed", 0) or 0) > 0:
        return "remaining_test_failures"
    return "unresolved_other"


def _failure_modes(df: pd.DataFrame) -> pd.DataFrame:
    unresolved = df[~df["resolved"]]
    rows: list[dict[str, object]] = []
    for mode, sub in unresolved.groupby("failure_mode"):
        rows.append(
            {
                "failure_mode": mode,
                "n": len(sub),
                "share_of_unresolved": len(sub) / len(unresolved) if len(unresolved) else 0.0,
                "share_of_all": len(sub) / len(df) if len(df) else 0.0,
            }
        )
    return pd.DataFrame(rows).sort_values("n", ascending=False)


def _failure_modes_by_repo(df: pd.DataFrame) -> pd.DataFrame:
    unresolved = df[~df["resolved"]]
    rows: list[dict[str, object]] = []
    for (repo, mode), sub in unresolved.groupby(["repo", "failure_mode"]):
        repo_unresolved = unresolved[unresolved["repo"] == repo]
        rows.append(
            {
                "repo": repo,
                "failure_mode": mode,
                "n": len(sub),
                "repo_unresolved": len(repo_unresolved),
                "share_of_repo_unresolved": len(sub) / len(repo_unresolved)
                if len(repo_unresolved)
                else 0.0,
            }
        )
    return pd.DataFrame(rows).sort_values(["repo_unresolved", "repo", "n"], ascending=[False, True, False])


def _patch_apply_outcomes(df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for label, sub in [
        ("patch_apply_failed", df[df["patch_apply_failed"]]),
        ("patch_apply_not_failed", df[~df["patch_apply_failed"]]),
        ("missing_run_log", df[~df["has_fix_patch_run_log"]]),
    ]:
        rows.append(
            {
                "outcome": label,
                "n": len(sub),
                "resolved": int(sub["resolved"].sum()) if len(sub) else 0,
                "report_valid": int(sub["report_valid"].sum()) if len(sub) else 0,
            }
        )
    return pd.DataFrame(rows)


def _test_status_summary(df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for stage in ("run_result", "test_patch_result", "fix_patch_result"):
        for group, sub in [
            ("all", df),
            ("resolved", df[df["resolved"]]),
            ("unresolved", df[~df["resolved"]]),
            ("report_valid", df[df["report_valid"]]),
        ]:
            rows.append(
                {
                    "stage": stage,
                    "group": group,
                    "n": len(sub),
                    "passed_mean": float(sub[f"{stage}_passed"].mean()) if len(sub) else 0.0,
                    "failed_mean": float(sub[f"{stage}_failed"].mean()) if len(sub) else 0.0,
                    "skipped_mean": float(sub[f"{stage}_skipped"].mean()) if len(sub) else 0.0,
                    "passed_p50": float(sub[f"{stage}_passed"].median()) if len(sub) else 0.0,
                    "failed_p50": float(sub[f"{stage}_failed"].median()) if len(sub) else 0.0,
                    "skipped_p50": float(sub[f"{stage}_skipped"].median()) if len(sub) else 0.0,
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
        "has_report",
        "report_valid",
        "has_patch_diff",
        "patch_is_empty",
        "patch_apply_failed",
        "has_fix_patch_run_log",
    ]:
        df[col] = bool_series(df[col])

    df["failure_mode"] = df.apply(_classify, axis=1)
    _failure_modes(df).to_csv(args.output_dir / "failure_modes.csv", index=False)
    _failure_modes_by_repo(df).to_csv(args.output_dir / "failure_modes_by_repo.csv", index=False)
    _patch_apply_outcomes(df).to_csv(args.output_dir / "patch_apply_outcomes.csv", index=False)
    _test_status_summary(df).to_csv(args.output_dir / "test_status_summary.csv", index=False)
    df[
        [
            "instance_id",
            "repo",
            "difficulty",
            "resolved",
            "report_valid",
            "failure_mode",
            "report_error_headline",
            "patch_apply_failed",
            "patch_apply_error_headline",
        ]
    ].to_csv(args.output_dir / "failure_mode_per_instance.csv", index=False)
    print(
        "[analyze_failures] wrote failure_modes.csv, failure_modes_by_repo.csv, "
        "patch_apply_outcomes.csv, test_status_summary.csv, failure_mode_per_instance.csv"
    )


if __name__ == "__main__":
    main()
