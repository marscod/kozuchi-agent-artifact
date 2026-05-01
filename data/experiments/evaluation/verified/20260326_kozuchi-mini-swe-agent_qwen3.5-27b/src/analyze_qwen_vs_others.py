"""Cross-experiment trajectory analysis: Kozuchi vs. Qwen-family
peers and closed-source frontier systems.

This module is the answer to the question: *given that we have
trajectory-level data only for Kozuchi, what can we still learn
about how Kozuchi compares to other Qwen and closed agents on the
same Verified-500 test set?*

Strategy:
  * Build a wide outcome matrix of size (500, k) where rows are
    Verified instances, columns are systems.  Entries are the
    binary "resolved" outcomes recovered from each submission's
    ``results/results.json``.
  * For each instance derive two consensus signals:
      qwen_consensus     = #peers in the Qwen family (excluding
                           Kozuchi) that resolve it.  (Range 0..N_QWEN_PEERS.)
      frontier_consensus = #peers in the curated closed frontier
                           that resolve it.  (Range 0..N_FRONTIER.)
  * Stratify Kozuchi's per-instance trajectory metrics
    (api_calls, runtime, patch_churn, rework counters) by these
    consensus levels.  This gives us a *trajectory* answer to the
    *outcome* question -- "how hard is the instance for Kozuchi
    when the Qwen peer consensus is X?".
  * Identify two crucial sets:
      KOZUCHI_UNIQUE_SOLVES = resolved by Kozuchi, not by any Qwen peer.
      KOZUCHI_BLIND_SPOTS   = unresolved by Kozuchi, but resolved
                              by at least one Qwen peer.
  * Cross-tabulate the unresolved set by frontier consensus to
    surface the "frontier-only" instances vs the "globally hard"
    residual.

CSVs emitted (under ``src/csv/``):

  - qwen_outcome_matrix.csv         -- wide outcome matrix.
  - qwen_consensus_per_instance.csv -- consensus + Kozuchi metrics.
  - qwen_consensus_summary.csv      -- consensus distribution.
  - kozuchi_traj_by_qwen_consensus.csv
  - kozuchi_unique_solves.csv       -- 12 Kozuchi-only solves vs Qwen.
  - kozuchi_blindspots.csv          -- Kozuchi misses, peer resolves.
  - kozuchi_unresolved_strata.csv   -- failure stratification.
  - frontier_solve_share.csv        -- per-repo frontier solve share
                                       of Kozuchi's unresolved set.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from utils import (
    CSV_DIR,
    EVAL_DIR,
    N_VERIFIED,
    PHASES_ORDERED,
    ensure_out_dirs,
    load_verified_instance_set,
    repo_of,
)


KOZUCHI_DIR = "20260326_kozuchi-mini-swe-agent_qwen3.5-27b"


# Same curated comparator buckets as analyze_competitors.py, but
# specialised here for *family* clustering.
QWEN_PEERS: list[tuple[str, str]] = [
    ("20250805_openhands-Qwen3-Coder-480B-A35B-Instruct", "OpenHands (Qwen-480B)"),
    ("20250901_entroPO_R2E_QwenCoder30BA3B_tts", "EntroPO+R2E (Qwen-30B) +TTS"),
    ("20250901_entroPO_R2E_QwenCoder30BA3B", "EntroPO+R2E (Qwen-30B)"),
    ("20250805_openhands-Qwen3-Coder-30B-A3B-Instruct", "OpenHands (Qwen-30B)"),
]
FRONTIER_PEERS: list[tuple[str, str]] = [
    ("20251215_livesweagent_claude-opus-4-5", "live-SWE + Opus-4.5"),
    ("20251205_sonar-foundation-agent_claude-opus-4-5", "Sonar + Opus-4.5"),
    ("20251127_openhands_claude-opus-4-5", "OpenHands + Opus-4.5"),
    ("20251120_livesweagent_gemini-3-pro-preview", "live-SWE + Gemini-3-Pro"),
    ("20251103_sonar-foundation-agent_claude-sonnet-4-5", "Sonar + Sonnet-4.5"),
    ("20250807_openhands_gpt5", "OpenHands + GPT-5"),
    ("20250524_openhands_claude_4_sonnet", "OpenHands + Sonnet-4"),
]


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


def _load_resolved_set(sub_dir: str) -> set[str]:
    """Return the resolved instance set for one submission, or empty set."""

    p = EVAL_DIR / sub_dir / "results" / "results.json"
    if not p.exists():
        return set()
    return set(json.loads(p.read_text()).get("resolved") or [])


def _build_outcome_matrix(verified: list[str]) -> pd.DataFrame:
    """Wide table: instance_id x {kozuchi, qwen-peers..., frontier...}.

    Each cell is 0 / 1 (resolved).  We also include a ``repo``
    column for downstream grouping.
    """

    cols: dict[str, set[str]] = {KOZUCHI_DIR: _load_resolved_set(KOZUCHI_DIR)}
    for d, _ in QWEN_PEERS + FRONTIER_PEERS:
        cols[d] = _load_resolved_set(d)
    rows: list[dict[str, object]] = []
    for iid in verified:
        rec: dict[str, object] = {"instance_id": iid, "repo": repo_of(iid)}
        rec["kozuchi"] = int(iid in cols[KOZUCHI_DIR])
        for d, name in QWEN_PEERS:
            rec[f"qwen::{name}"] = int(iid in cols[d])
        for d, name in FRONTIER_PEERS:
            rec[f"frontier::{name}"] = int(iid in cols[d])
        rows.append(rec)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Consensus
# ---------------------------------------------------------------------------


def _add_consensus(matrix: pd.DataFrame) -> pd.DataFrame:
    qwen_cols = [c for c in matrix.columns if c.startswith("qwen::")]
    front_cols = [c for c in matrix.columns if c.startswith("frontier::")]
    matrix = matrix.copy()
    matrix["qwen_consensus"] = matrix[qwen_cols].sum(axis=1)
    matrix["frontier_consensus"] = matrix[front_cols].sum(axis=1)
    matrix["n_qwen_peers"] = len(qwen_cols)
    matrix["n_frontier_peers"] = len(front_cols)
    matrix["any_qwen_peer"] = (matrix["qwen_consensus"] > 0).astype(int)
    matrix["any_frontier"] = (matrix["frontier_consensus"] > 0).astype(int)
    matrix["unanimous_qwen_peer"] = (matrix["qwen_consensus"] == len(qwen_cols)).astype(int)
    matrix["unanimous_frontier"] = (matrix["frontier_consensus"] == len(front_cols)).astype(int)
    return matrix


def _consensus_summary(matrix: pd.DataFrame) -> pd.DataFrame:
    """Resolution rate as a function of qwen_consensus and frontier_consensus.

    Tells us, for each consensus bucket, what fraction of those
    instances Kozuchi also resolves.
    """

    rows: list[dict[str, object]] = []
    for ax_label, axis in [("qwen_consensus", "qwen_consensus"), ("frontier_consensus", "frontier_consensus")]:
        for k, sub in matrix.groupby(axis):
            rows.append(
                dict(
                    axis=ax_label,
                    consensus=int(k),
                    n_instances=len(sub),
                    kozuchi_resolved=int(sub["kozuchi"].sum()),
                    kozuchi_rate=float(sub["kozuchi"].mean()),
                )
            )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Trajectory join
# ---------------------------------------------------------------------------


def _kozuchi_traj_by_consensus(
    matrix: pd.DataFrame, traj: pd.DataFrame
) -> pd.DataFrame:
    """Mean Kozuchi trajectory metrics by qwen_consensus level.

    The columns we report are the standard trajectory features
    introduced in ``extract_metadata`` so that the table can be
    cross-referenced with the headline trajectory_stats.csv.
    """

    df = matrix.merge(
        traj[
            [
                "instance_id",
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
                "has_traj",
            ]
        ],
        on="instance_id",
        how="left",
    )
    df = df[df["has_traj"]]
    rows: list[dict[str, object]] = []
    for k, sub in df.groupby("qwen_consensus"):
        n = len(sub)
        rec = dict(
            qwen_consensus=int(k),
            n_kozuchi_attempts=n,
            kozuchi_resolved_rate=float(sub["kozuchi"].mean()),
        )
        for col in [
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
        ]:
            rec[f"{col}_mean"] = float(sub[col].mean())
            rec[f"{col}_p50"] = float(sub[col].median())
        rows.append(rec)
    # Also a same-table split by Kozuchi outcome (within consensus
    # level) so we can compare Kozuchi-only solves to common solves.
    rows_split: list[dict[str, object]] = []
    for (k, koz), sub in df.groupby(["qwen_consensus", "kozuchi"]):
        rec = dict(
            qwen_consensus=int(k),
            kozuchi_resolved=bool(koz),
            n=len(sub),
        )
        for col in ["api_calls", "runtime_sec", "patch_churn", "phase_VERIFY_PATCH_giveup"]:
            rec[f"{col}_p50"] = float(sub[col].median())
            rec[f"{col}_mean"] = float(sub[col].mean())
        rows_split.append(rec)
    return pd.DataFrame(rows), pd.DataFrame(rows_split)


# ---------------------------------------------------------------------------
# Unique solves and blind spots
# ---------------------------------------------------------------------------


def _unique_and_blind(
    matrix: pd.DataFrame, traj: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Two complementary tables:

    * ``unique`` -- instances Kozuchi resolves but no Qwen peer
      resolves.  Annotated with whether *any frontier* peer also
      resolves the instance, so we can isolate the truly globally
      novel set.
    * ``blind`` -- instances Kozuchi misses but at least one Qwen
      peer resolves.  Annotated with which peers and Kozuchi's
      failure mode (joined from ``failure_mode_per_instance.csv``
      if available, otherwise from the test-status fields in
      ``instances.csv``).
    """

    qwen_cols = [c for c in matrix.columns if c.startswith("qwen::")]
    front_cols = [c for c in matrix.columns if c.startswith("frontier::")]

    # Unique solves.
    unique_mask = (matrix["kozuchi"] == 1) & (matrix["qwen_consensus"] == 0)
    unique_df = matrix[unique_mask].copy()
    unique_df["any_frontier_resolves"] = (unique_df["frontier_consensus"] > 0).astype(int)
    unique_df["frontier_consensus"] = unique_df[front_cols].sum(axis=1)
    unique_df = unique_df.merge(
        traj[["instance_id", "api_calls", "patch_churn", "runtime_sec"]],
        on="instance_id",
        how="left",
    )
    unique_df = unique_df[
        [
            "instance_id",
            "repo",
            "frontier_consensus",
            "any_frontier_resolves",
            "api_calls",
            "patch_churn",
            "runtime_sec",
        ]
    ].sort_values(["any_frontier_resolves", "repo", "instance_id"]).reset_index(drop=True)

    # Blind spots.
    blind_mask = (matrix["kozuchi"] == 0) & (matrix["qwen_consensus"] > 0)
    blind_df = matrix[blind_mask].copy()
    # Compact "which qwen peers solved" string.
    short_names = [c.replace("qwen::", "") for c in qwen_cols]
    blind_df["qwen_solvers"] = blind_df[qwen_cols].apply(
        lambda r: ",".join(n for n, v in zip(short_names, r.values) if v == 1),
        axis=1,
    )
    blind_df = blind_df.merge(
        traj[
            [
                "instance_id",
                "api_calls",
                "patch_churn",
                "runtime_sec",
                "patch_successfully_applied",
                "FAIL_TO_PASS_failure",
                "PASS_TO_PASS_failure",
                "has_traj",
            ]
        ],
        on="instance_id",
        how="left",
    )
    blind_df = blind_df[
        [
            "instance_id",
            "repo",
            "qwen_consensus",
            "frontier_consensus",
            "qwen_solvers",
            "api_calls",
            "patch_churn",
            "runtime_sec",
            "FAIL_TO_PASS_failure",
            "PASS_TO_PASS_failure",
            "patch_successfully_applied",
            "has_traj",
        ]
    ].sort_values(["qwen_consensus", "repo"], ascending=[False, True]).reset_index(drop=True)
    return unique_df, blind_df


# ---------------------------------------------------------------------------
# Failure stratification by frontier consensus
# ---------------------------------------------------------------------------


def _unresolved_strata(matrix: pd.DataFrame) -> pd.DataFrame:
    """Stratify Kozuchi's 126 unresolved instances by external help.

    Buckets:
      * peer_qwen_solved        -- another Qwen peer resolves it.
      * frontier_only           -- no Qwen peer, >=1 frontier resolves it.
      * globally_hard           -- nobody (curated set) resolves it.
    """

    unresolved = matrix[matrix["kozuchi"] == 0].copy()
    rows: list[dict[str, object]] = []
    n_total = len(unresolved)
    pq = (unresolved["qwen_consensus"] > 0).sum()
    fo = ((unresolved["qwen_consensus"] == 0) & (unresolved["frontier_consensus"] > 0)).sum()
    gh = ((unresolved["qwen_consensus"] == 0) & (unresolved["frontier_consensus"] == 0)).sum()
    rows.append(dict(stratum="peer_qwen_solved", n=int(pq), share=int(pq) / max(1, n_total)))
    rows.append(dict(stratum="frontier_only", n=int(fo), share=int(fo) / max(1, n_total)))
    rows.append(dict(stratum="globally_hard", n=int(gh), share=int(gh) / max(1, n_total)))
    rows.append(dict(stratum="TOTAL", n=int(n_total), share=1.0))
    return pd.DataFrame(rows)


def _frontier_solve_share(matrix: pd.DataFrame) -> pd.DataFrame:
    """Per-repo: what share of Kozuchi-unresolved instances does the
    closed frontier collectively solve?

    A high value means the residual is "solvable, but we didn't" --
    a small backbone-quality gap.  A low value means the corpus is
    genuinely hard for everyone.
    """

    unresolved = matrix[matrix["kozuchi"] == 0].copy()
    rows: list[dict[str, object]] = []
    for repo, sub in unresolved.groupby("repo"):
        n = len(sub)
        front_solved = int((sub["frontier_consensus"] > 0).sum())
        any_solved = int(((sub["qwen_consensus"] > 0) | (sub["frontier_consensus"] > 0)).sum())
        rows.append(
            dict(
                repo=repo,
                kozuchi_unresolved=n,
                frontier_solved=front_solved,
                any_peer_solved=any_solved,
                frontier_share=front_solved / n if n else 0.0,
                any_share=any_solved / n if n else 0.0,
            )
        )
    return pd.DataFrame(rows).sort_values("kozuchi_unresolved", ascending=False).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--instances-csv", type=Path, default=CSV_DIR / "instances.csv")
    p.add_argument("--output-dir", type=Path, default=CSV_DIR)
    args = p.parse_args()

    ensure_out_dirs()
    traj = pd.read_csv(args.instances_csv)
    for c in ["resolved", "has_traj"]:
        traj[c] = traj[c].astype(str).str.lower().isin(("true", "1", "yes"))

    verified = sorted(load_verified_instance_set())
    matrix = _build_outcome_matrix(verified)
    matrix = _add_consensus(matrix)

    matrix.to_csv(args.output_dir / "qwen_outcome_matrix.csv", index=False)

    consensus = _consensus_summary(matrix)
    consensus.to_csv(args.output_dir / "qwen_consensus_summary.csv", index=False)

    by_consensus, by_consensus_split = _kozuchi_traj_by_consensus(matrix, traj)
    by_consensus.to_csv(args.output_dir / "kozuchi_traj_by_qwen_consensus.csv", index=False)
    by_consensus_split.to_csv(
        args.output_dir / "kozuchi_traj_by_qwen_consensus_split.csv", index=False
    )

    unique_df, blind_df = _unique_and_blind(matrix, traj)
    unique_df.to_csv(args.output_dir / "kozuchi_unique_solves.csv", index=False)
    blind_df.to_csv(args.output_dir / "kozuchi_blindspots.csv", index=False)

    strata = _unresolved_strata(matrix)
    strata.to_csv(args.output_dir / "kozuchi_unresolved_strata.csv", index=False)

    fs = _frontier_solve_share(matrix)
    fs.to_csv(args.output_dir / "frontier_solve_share.csv", index=False)

    # Compact per-instance enriched table (just the most useful fields).
    enriched = matrix[
        ["instance_id", "repo", "kozuchi", "qwen_consensus", "frontier_consensus"]
    ].merge(
        traj[
            [
                "instance_id",
                "api_calls",
                "runtime_sec",
                "patch_churn",
                "phase_VERIFY_PATCH_giveup",
                "FAIL_TO_PASS_failure",
                "PASS_TO_PASS_failure",
            ]
        ],
        on="instance_id",
        how="left",
    )
    enriched.to_csv(args.output_dir / "qwen_consensus_per_instance.csv", index=False)

    print(
        "[analyze_qwen_vs_others] wrote qwen_outcome_matrix.csv, qwen_consensus_summary.csv, "
        "kozuchi_traj_by_qwen_consensus.csv, kozuchi_traj_by_qwen_consensus_split.csv, "
        "kozuchi_unique_solves.csv, kozuchi_blindspots.csv, kozuchi_unresolved_strata.csv, "
        "frontier_solve_share.csv, qwen_consensus_per_instance.csv"
    )


if __name__ == "__main__":
    main()
