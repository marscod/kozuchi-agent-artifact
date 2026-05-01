"""Peer leaderboard comparisons for the Multi-SWE Java run."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from utils import (
    CSV_DIR,
    EXPERIMENT_DIR,
    bool_series,
    load_all_ids,
    load_difficulty_map,
    mcnemar_exact_p,
    repo_of,
    wilson_ci,
)


def _leaderboard(summary: pd.DataFrame) -> pd.DataFrame:
    out = summary.copy()
    out = out.sort_values(["resolved_instances", "rate", "name"], ascending=[False, False, True])
    out.insert(0, "rank", range(1, len(out) + 1))
    return out


def _matrix(resolved: pd.DataFrame) -> pd.DataFrame:
    data = resolved.copy()
    data["resolved"] = bool_series(data["resolved"])
    return data.pivot(index="instance_id", columns="folder", values="resolved").fillna(False)


def _peers(summary: pd.DataFrame, resolved: pd.DataFrame) -> pd.DataFrame:
    target = EXPERIMENT_DIR.name
    mat = _matrix(resolved)
    ours = mat[target].astype(bool)
    rows: list[dict[str, object]] = []
    for _, peer in summary.iterrows():
        folder = peer["folder"]
        if folder == target or folder not in mat.columns:
            continue
        theirs = mat[folder].astype(bool)
        both = int((ours & theirs).sum())
        our_only = int((ours & ~theirs).sum())
        peer_only = int((~ours & theirs).sum())
        neither = int((~ours & ~theirs).sum())
        rows.append(
            {
                "folder": folder,
                "name": peer["name"],
                "peer_resolved": int(theirs.sum()),
                "our_resolved": int(ours.sum()),
                "delta_resolved": int(ours.sum()) - int(theirs.sum()),
                "both_resolved": both,
                "our_only": our_only,
                "peer_only": peer_only,
                "neither": neither,
                "mcnemar_p": mcnemar_exact_p(our_only, peer_only),
            }
        )
    return pd.DataFrame(rows).sort_values("delta_resolved", ascending=False)


def _per_repo_vs_peers(summary: pd.DataFrame, resolved: pd.DataFrame) -> pd.DataFrame:
    target = EXPERIMENT_DIR.name
    mat = _matrix(resolved)
    ours = mat[target].astype(bool)
    repos = {iid: repo_of(iid) for iid in mat.index}
    rows: list[dict[str, object]] = []
    for _, peer in summary.iterrows():
        folder = peer["folder"]
        if folder == target or folder not in mat.columns:
            continue
        theirs = mat[folder].astype(bool)
        for repo in sorted(set(repos.values())):
            ids = [iid for iid, r in repos.items() if r == repo]
            n = len(ids)
            our_k = int(ours.loc[ids].sum())
            peer_k = int(theirs.loc[ids].sum())
            rows.append(
                {
                    "folder": folder,
                    "name": peer["name"],
                    "repo": repo,
                    "n": n,
                    "our_resolved": our_k,
                    "peer_resolved": peer_k,
                    "our_rate": our_k / n if n else 0.0,
                    "peer_rate": peer_k / n if n else 0.0,
                    "delta_rate": (our_k - peer_k) / n if n else 0.0,
                }
            )
    return pd.DataFrame(rows)


def _unique_resolved(resolved: pd.DataFrame) -> pd.DataFrame:
    target = EXPERIMENT_DIR.name
    mat = _matrix(resolved)
    difficulty = load_difficulty_map()
    peer_cols = [c for c in mat.columns if c != target]
    rows: list[dict[str, object]] = []
    for instance_id in load_all_ids():
        ours = bool(mat.loc[instance_id, target])
        solved_by = [folder for folder in peer_cols if bool(mat.loc[instance_id, folder])]
        rows.append(
            {
                "instance_id": instance_id,
                "repo": repo_of(instance_id),
                "difficulty": difficulty.get(instance_id, "unknown"),
                "our_resolved": ours,
                "peer_solve_count": len(solved_by),
                "our_unique_resolve": ours and not solved_by,
                "solved_by_any_peer": bool(solved_by),
                "peer_folders": ";".join(solved_by),
            }
        )
    return pd.DataFrame(rows).sort_values(["our_unique_resolve", "peer_solve_count"], ascending=[False, True])


def _instance_solve_counts(resolved: pd.DataFrame) -> pd.DataFrame:
    mat = _matrix(resolved)
    difficulty = load_difficulty_map()
    rows: list[dict[str, object]] = []
    for instance_id in load_all_ids():
        count = int(mat.loc[instance_id].sum())
        ci = wilson_ci(count, len(mat.columns))
        rows.append(
            {
                "instance_id": instance_id,
                "repo": repo_of(instance_id),
                "difficulty": difficulty.get(instance_id, "unknown"),
                "models_resolved": count,
                "model_count": len(mat.columns),
                "solve_share": ci.p,
            }
        )
    return pd.DataFrame(rows).sort_values("models_resolved", ascending=False)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary-csv", type=Path, default=CSV_DIR / "competitors_summary.csv")
    parser.add_argument("--resolved-csv", type=Path, default=CSV_DIR / "competitors_resolved.csv")
    parser.add_argument("--output-dir", type=Path, default=CSV_DIR)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    summary = pd.read_csv(args.summary_csv)
    resolved = pd.read_csv(args.resolved_csv)

    leaderboard = _leaderboard(summary)
    peers = _peers(summary, resolved)
    per_repo = _per_repo_vs_peers(summary, resolved)
    unique = _unique_resolved(resolved)
    solve_counts = _instance_solve_counts(resolved)

    leaderboard.to_csv(args.output_dir / "leaderboard.csv", index=False)
    peers.to_csv(args.output_dir / "peers.csv", index=False)
    peers.to_csv(args.output_dir / "mcnemar.csv", index=False)
    per_repo.to_csv(args.output_dir / "per_repo_vs_peers.csv", index=False)
    unique.to_csv(args.output_dir / "unique_resolved.csv", index=False)
    solve_counts.to_csv(args.output_dir / "instance_solve_counts.csv", index=False)
    print(
        "[analyze_competitors] wrote leaderboard.csv, peers.csv, mcnemar.csv, "
        "per_repo_vs_peers.csv, unique_resolved.csv, instance_solve_counts.csv"
    )


if __name__ == "__main__":
    main()
