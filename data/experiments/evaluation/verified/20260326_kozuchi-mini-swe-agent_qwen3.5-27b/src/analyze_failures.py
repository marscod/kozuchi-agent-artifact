"""Failure-mode analysis.

We classify the 126 unresolved Verified instances into four
mutually-exclusive failure modes:

  1. ``MISSING_ARTEFACT`` -- no traj/log on disk (5 instances).
     These are *operational* failures: the TTS@8 selector or the
     downstream evaluation harness lost the candidate set entirely.
  2. ``EMPTY_PATCH`` -- patch.diff is present but contains zero
     hunks; the agent submitted no code change.
  3. ``PATCH_DID_NOT_APPLY`` -- the SWE-bench harness rejected the
     diff (``patch_successfully_applied == False``).
  4. ``WRONG_FIX`` -- patch applied cleanly but the FAIL_TO_PASS
     bucket has at least one failing test (the agent's fix is
     incorrect).
  5. ``REGRESSION`` -- patch applied and passed FAIL_TO_PASS, but
     PASS_TO_PASS has at least one failure (the agent broke the
     existing test suite).

Each instance falls into exactly one bucket; we walk the rules in
order so that the most upstream failure wins.

We also compute a per-repository / per-year breakdown of these
buckets.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from utils import CSV_DIR, ensure_out_dirs, wilson_ci


FAILURE_BUCKETS = [
    "MISSING_ARTEFACT",
    "EMPTY_PATCH",
    "PATCH_DID_NOT_APPLY",
    "WRONG_FIX",
    "REGRESSION",
]


def _classify(row: pd.Series) -> str | None:
    if bool(row["resolved"]):
        return None
    if not bool(row["has_traj"]) or not bool(row["has_report"]):
        return "MISSING_ARTEFACT"
    if bool(row["patch_is_empty"]) or not bool(row["has_patch_diff"]):
        return "EMPTY_PATCH"
    if str(row["patch_successfully_applied"]).strip().lower() in {"false", "0", "no"}:
        return "PATCH_DID_NOT_APPLY"
    f2p_fail = int(row["FAIL_TO_PASS_failure"])
    p2p_fail = int(row["PASS_TO_PASS_failure"])
    if f2p_fail > 0:
        return "WRONG_FIX"
    if p2p_fail > 0:
        return "REGRESSION"
    return "WRONG_FIX"


def _bucket_summary(df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    n_total = len(df)
    n_unresolved = int((~df["resolved"]).sum())
    rows.append(
        dict(
            bucket="RESOLVED",
            n=int(df["resolved"].sum()),
            share_of_total=int(df["resolved"].sum()) / n_total,
            share_of_unresolved=0.0,
        )
    )
    df_unres = df[~df["resolved"]].copy()
    df_unres["failure_mode"] = df_unres.apply(_classify, axis=1)
    counts = df_unres["failure_mode"].value_counts()
    for b in FAILURE_BUCKETS:
        n = int(counts.get(b, 0))
        rows.append(
            dict(
                bucket=b,
                n=n,
                share_of_total=n / n_total,
                share_of_unresolved=n / n_unresolved if n_unresolved else 0.0,
            )
        )
    return pd.DataFrame(rows), df_unres


def _per_repo_failure(df_unres: pd.DataFrame, df_all: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for repo, sub_all in df_all.groupby("repo"):
        sub_un = df_unres[df_unres["repo"] == repo]
        rec: dict[str, object] = dict(
            repo=repo,
            n=len(sub_all),
            unresolved=len(sub_un),
        )
        for b in FAILURE_BUCKETS:
            rec[b] = int((sub_un["failure_mode"] == b).sum())
        rows.append(rec)
    return pd.DataFrame(rows).sort_values("n", ascending=False).reset_index(drop=True)


def _patch_apply_table(df: pd.DataFrame) -> pd.DataFrame:
    """Submission outcome conditional on the harness applying the patch.

    Captures the agent's *editing* skill independently of the
    repair-correctness of the proposed change.
    """

    has = df[df["has_traj"].astype(bool)].copy()
    rows: list[dict[str, object]] = []
    grp = has.groupby(has["patch_successfully_applied"].astype(str).str.lower())
    for key, sub in grp:
        n = len(sub)
        k = int(sub["resolved"].sum())
        ci = wilson_ci(k, n)
        rows.append(
            dict(
                patch_applied=key,
                n=n,
                resolved=k,
                rate=ci.p,
                ci_lo=ci.lo,
                ci_hi=ci.hi,
            )
        )
    return pd.DataFrame(rows)


def _test_status_table(df: pd.DataFrame) -> pd.DataFrame:
    """Distribution of FAIL_TO_PASS / PASS_TO_PASS counts.

    Useful for diagnosing how close the agent typically gets when
    it produces an *applied* but ultimately wrong patch.
    """

    rows: list[dict[str, object]] = []
    for label, sub in [
        ("all_with_report", df[df["has_report"].astype(bool)]),
        ("resolved", df[df["resolved"]]),
        (
            "unresolved_with_report",
            df[(~df["resolved"]) & df["has_report"].astype(bool)],
        ),
    ]:
        rec: dict[str, object] = dict(group=label, n=len(sub))
        for col in [
            "FAIL_TO_PASS_success",
            "FAIL_TO_PASS_failure",
            "PASS_TO_PASS_success",
            "PASS_TO_PASS_failure",
        ]:
            rec[f"{col}_mean"] = float(sub[col].mean()) if len(sub) else 0.0
            rec[f"{col}_p50"] = float(sub[col].median()) if len(sub) else 0.0
        rows.append(rec)
    return pd.DataFrame(rows)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--instances-csv", type=Path, default=CSV_DIR / "instances.csv")
    p.add_argument("--output-dir", type=Path, default=CSV_DIR)
    args = p.parse_args()

    ensure_out_dirs()
    df = pd.read_csv(args.instances_csv)
    for c in ["resolved", "has_traj", "has_report", "has_patch_diff", "patch_is_empty"]:
        df[c] = df[c].astype(str).str.lower().isin(("true", "1", "yes"))

    summary, df_unres = _bucket_summary(df)
    repo = _per_repo_failure(df_unres, df)
    apply = _patch_apply_table(df)
    tests = _test_status_table(df)

    summary.to_csv(args.output_dir / "failure_modes.csv", index=False)
    repo.to_csv(args.output_dir / "failure_modes_by_repo.csv", index=False)
    apply.to_csv(args.output_dir / "patch_apply_outcomes.csv", index=False)
    tests.to_csv(args.output_dir / "test_status_summary.csv", index=False)

    # Also persist the per-instance failure-mode tag so downstream
    # tools (e.g. figures) can join against it.
    out_iid = df.copy()
    out_iid["failure_mode"] = ""
    mask = ~out_iid["resolved"]
    out_iid.loc[mask, "failure_mode"] = out_iid.loc[mask].apply(_classify, axis=1)
    out_iid[["instance_id", "repo", "resolved", "failure_mode"]].to_csv(
        args.output_dir / "failure_mode_per_instance.csv", index=False
    )
    print(
        "[analyze_failures] wrote failure_modes.csv, failure_modes_by_repo.csv, "
        "patch_apply_outcomes.csv, test_status_summary.csv, failure_mode_per_instance.csv"
    )


if __name__ == "__main__":
    main()
