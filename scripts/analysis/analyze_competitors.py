"""Cross-experiment comparative analysis.

The user's request emphasises a focused comparison against
**other open-weight Qwen-family** systems and other open-weight
mid-size baselines, plus a survey context against the closed-source
frontier.  We materialise the following CSVs:

  * ``leaderboard.csv`` -- every submission in the leaderboard
    sorted by resolved-in-500 with Wilson CIs.
  * ``leaderboard_open_vs_closed.csv`` -- means / quartiles of the
    open-weight vs closed-weight model populations.
  * ``peers.csv`` -- a curated peer set covering Qwen-family,
    similar-sized open-weight systems, and SOTA closed systems.
  * ``mcnemar.csv`` -- pairwise McNemar exact tests Kozuchi vs
    each peer (over the 500-instance Verified set).
  * ``per_repo_vs_peers.csv`` -- per-repo resolution rate of
    Kozuchi against each curated peer.
  * ``unique_resolved.csv`` -- instances that Kozuchi solves but
    *no* peer in the curated set solves -- the "open-source unique
    contribution" set.

Curation policy:
  * Open-weight Qwen-family / mid-size: every entry whose
    ``submission_dir`` matches a hand-picked allow-list (these are
    the submissions the user explicitly cares about for ablation
    intuition).
  * Closed-weight frontier: top closed-source systems on
    Verified for context only -- never used for "ours-better"
    statistics in the paper.
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
    ensure_out_dirs,
    load_verified_instance_set,
    mcnemar_exact_p,
    repo_of,
    wilson_ci,
)


KOZUCHI_DIR = "20260326_kozuchi-mini-swe-agent_qwen3.5-27b"


# Curated comparator buckets.  The names are deliberately
# verbose because they show up directly in the paper's table.
OPEN_WEIGHT_PEERS: list[tuple[str, str, str]] = [
    # (submission_dir, short_name, family)
    (
        "20250901_entroPO_R2E_QwenCoder30BA3B_tts",
        "EntroPO+R2E (Qwen3-Coder-30B-A3B) +TTS",
        "Qwen-30B",
    ),
    (
        "20250901_entroPO_R2E_QwenCoder30BA3B",
        "EntroPO+R2E (Qwen3-Coder-30B-A3B)",
        "Qwen-30B",
    ),
    (
        "20250805_openhands-Qwen3-Coder-30B-A3B-Instruct",
        "OpenHands (Qwen3-Coder-30B-A3B)",
        "Qwen-30B",
    ),
    (
        "20250805_openhands-Qwen3-Coder-480B-A35B-Instruct",
        "OpenHands (Qwen3-Coder-480B-A35B)",
        "Qwen-480B",
    ),
    ("20250616_Skywork-SWE-32B+TTS_Bo8", "Skywork-SWE-32B +TTS(Bo8)", "Other-32B"),
    ("20250616_Skywork-SWE-32B", "Skywork-SWE-32B", "Other-32B"),
    ("20250629_deepswerl_r2eagent_tts", "DeepSWE-Preview +TTS(Bo16)", "DeepSeek-32B"),
    ("20250629_deepswerl_r2eagent", "DeepSWE-Preview", "DeepSeek-32B"),
    ("20250520_openhands_devstral_small", "OpenHands + Devstral-Small", "Devstral"),
    ("20250725_sweagent_devstral_small_2507", "SWE-agent + Devstral-Small (2507)", "Devstral"),
    ("20250511_sweagent_lm_32b", "SWE-agent + SWE-agent-LM-32B", "Other-32B"),
    ("20251110_frogboss-32b", "Frogboss-32B", "Other-32B"),
    ("20251110_frogmini-14b", "Frogmini-14B", "Other-14B"),
    ("20250728_zai_glm4-5", "Z.AI GLM-4.5", "GLM"),
    ("20250930_zai_glm4-6", "Z.AI GLM-4.6", "GLM"),
    ("20250716_openhands_kimi_k2", "OpenHands + Kimi-K2", "Kimi-K2"),
    ("20251014_Lingxi_kimi_k2", "Lingxi v1.5 + Kimi-K2", "Kimi-K2"),
]
CLOSED_FRONTIER: list[tuple[str, str, str]] = [
    ("20251127_openhands_claude-opus-4-5", "OpenHands + Claude-Opus-4.5", "Frontier"),
    ("20251215_livesweagent_claude-opus-4-5", "live-SWE + Claude-Opus-4.5", "Frontier"),
    ("20251205_sonar-foundation-agent_claude-opus-4-5", "Sonar + Claude-Opus-4.5", "Frontier"),
    ("20251103_sonar-foundation-agent_claude-sonnet-4-5", "Sonar + Claude-Sonnet-4.5", "Frontier"),
    ("20251120_livesweagent_gemini-3-pro-preview", "live-SWE + Gemini-3-Pro", "Frontier"),
    ("20250807_openhands_gpt5", "OpenHands + GPT-5", "Frontier"),
    ("20250524_openhands_claude_4_sonnet", "OpenHands + Claude-4-Sonnet", "Frontier"),
]


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


def _load_resolved_sets() -> dict[str, set[str]]:
    """Return {submission_dir -> set(resolved instance ids)}.

    We re-read the per-submission ``results.json`` so we can pivot
    without needing the (much larger) long-format CSV.
    """

    out: dict[str, set[str]] = {}
    for sub in sorted(EVAL_DIR.iterdir()):
        if not sub.is_dir():
            continue
        rj = sub / "results" / "results.json"
        if not rj.exists():
            continue
        data = json.loads(rj.read_text())
        out[sub.name] = set(data.get("resolved", []) or [])
    return out


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------


def _leaderboard(summary_csv: Path) -> pd.DataFrame:
    df = pd.read_csv(summary_csv)
    # Recompute Wilson CIs against the canonical N=500.
    rows: list[dict[str, object]] = []
    for _, r in df.iterrows():
        k = int(r["n_resolved_in_500"])
        ci = wilson_ci(k, N_VERIFIED)
        rows.append(
            dict(
                submission_dir=r["submission_dir"],
                name=r["name"],
                org=r.get("org"),
                os_model=r.get("os_model"),
                os_system=r.get("os_system"),
                resolved=k,
                rate=ci.p,
                ci_lo=ci.lo,
                ci_hi=ci.hi,
                n_no_generation=r.get("n_no_generation"),
                n_no_logs=r.get("n_no_logs"),
            )
        )
    return pd.DataFrame(rows).sort_values("resolved", ascending=False).reset_index(drop=True)


def _open_vs_closed(leader: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for label, mask in [
        ("open_weight (os_model=True)", leader["os_model"] == True),  # noqa: E712
        ("closed_weight (os_model=False)", leader["os_model"] == False),  # noqa: E712
        ("os_model=NA", leader["os_model"].isna()),
    ]:
        sub = leader[mask]
        rows.append(
            dict(
                bucket=label,
                n=len(sub),
                resolved_mean=float(sub["resolved"].mean()) if len(sub) else 0.0,
                resolved_p25=float(sub["resolved"].quantile(0.25)) if len(sub) else 0.0,
                resolved_p50=float(sub["resolved"].quantile(0.50)) if len(sub) else 0.0,
                resolved_p75=float(sub["resolved"].quantile(0.75)) if len(sub) else 0.0,
                resolved_max=float(sub["resolved"].max()) if len(sub) else 0.0,
                top_3=", ".join(sub.sort_values("resolved", ascending=False).head(3)["name"].tolist()),
            )
        )
    return pd.DataFrame(rows)


def _peers(
    leader: pd.DataFrame, resolved_sets: dict[str, set[str]]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Materialise peer table + McNemar test against Kozuchi."""

    if KOZUCHI_DIR not in resolved_sets:
        raise RuntimeError(f"Missing kozuchi: {KOZUCHI_DIR}")
    K = resolved_sets[KOZUCHI_DIR]
    verified = load_verified_instance_set()
    rows: list[dict[str, object]] = []
    mcnemar_rows: list[dict[str, object]] = []
    peer_set: list[tuple[str, str, str, str]] = (
        [(d, n, fam, "open") for d, n, fam in OPEN_WEIGHT_PEERS]
        + [(d, n, fam, "closed") for d, n, fam in CLOSED_FRONTIER]
    )
    # Add Kozuchi at the top so the table is self-comparable.
    peer_set.insert(0, (KOZUCHI_DIR, "Kozuchi mini-swe-agent + Qwen3.5-27B", "Qwen-27B", "open"))
    for sub_dir, name, family, weight_class in peer_set:
        if sub_dir not in resolved_sets:
            continue
        S = resolved_sets[sub_dir] & verified
        n_res = len(S)
        ci = wilson_ci(n_res, N_VERIFIED)
        rows.append(
            dict(
                submission_dir=sub_dir,
                name=name,
                family=family,
                weight_class=weight_class,
                resolved=n_res,
                rate=ci.p,
                ci_lo=ci.lo,
                ci_hi=ci.hi,
                gap_vs_kozuchi=len(K) - n_res,
            )
        )
        if sub_dir == KOZUCHI_DIR:
            continue
        # Paired contingency: a = both, b = K-only, c = peer-only,
        # d = neither.  McNemar uses (b, c).
        a = len(K & S)
        b = len(K - S)
        c = len(S - K)
        d = N_VERIFIED - a - b - c
        p = mcnemar_exact_p(b, c)
        mcnemar_rows.append(
            dict(
                peer=name,
                family=family,
                weight_class=weight_class,
                both=a,
                kozuchi_only=b,
                peer_only=c,
                neither=d,
                kozuchi_resolved=len(K),
                peer_resolved=n_res,
                gap=len(K) - n_res,
                mcnemar_p=p,
                significant_05=p < 0.05,
            )
        )
    peers_df = pd.DataFrame(rows)
    mc_df = pd.DataFrame(mcnemar_rows).sort_values("gap", ascending=False).reset_index(drop=True)
    return peers_df, mc_df


def _per_repo_vs_peers(
    resolved_sets: dict[str, set[str]],
) -> pd.DataFrame:
    """Per-repo resolution rate of Kozuchi vs each peer.

    The user wants insight into ``does another Qwen suffer where we
    don't?`` -- this table answers exactly that.
    """

    verified = load_verified_instance_set()
    repos: dict[str, list[str]] = {}
    for iid in verified:
        repos.setdefault(repo_of(iid), []).append(iid)
    peers = [(KOZUCHI_DIR, "Kozuchi")] + [(d, n) for d, n, _ in OPEN_WEIGHT_PEERS]
    rows: list[dict[str, object]] = []
    for repo, ids in repos.items():
        rec: dict[str, object] = dict(repo=repo, n=len(ids))
        for sub_dir, name in peers:
            S = resolved_sets.get(sub_dir, set())
            k = sum(1 for i in ids if i in S)
            rec[f"{name}_resolved"] = k
            rec[f"{name}_rate"] = k / len(ids) if ids else 0.0
        rows.append(rec)
    return pd.DataFrame(rows).sort_values("n", ascending=False).reset_index(drop=True)


def _unique_to_kozuchi(resolved_sets: dict[str, set[str]]) -> pd.DataFrame:
    """Instances Kozuchi solves but no curated open-weight peer solves.

    Distinct from "novel" -- a closed frontier model may also solve
    it -- but illustrates the gap that Kozuchi closes for the OS
    research community.
    """

    K = resolved_sets[KOZUCHI_DIR]
    union_open = set()
    for sub_dir, _, _ in OPEN_WEIGHT_PEERS:
        union_open |= resolved_sets.get(sub_dir, set())
    unique_open = sorted(K - union_open)
    union_all = union_open.copy()
    for sub_dir, _, _ in CLOSED_FRONTIER:
        union_all |= resolved_sets.get(sub_dir, set())
    truly_novel = sorted(K - union_all)
    rows = [dict(category="open_weight_only_unique", n=len(unique_open))]
    rows.extend({"category": "open_weight_only_unique_id", "instance_id": x} for x in unique_open)
    rows.append(dict(category="globally_novel", n=len(truly_novel)))
    rows.extend({"category": "globally_novel_id", "instance_id": x} for x in truly_novel)
    return pd.DataFrame(rows)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--summary-csv",
        type=Path,
        default=CSV_DIR / "competitors_summary.csv",
    )
    p.add_argument("--output-dir", type=Path, default=CSV_DIR)
    args = p.parse_args()

    ensure_out_dirs()
    leader = _leaderboard(args.summary_csv)
    leader.to_csv(args.output_dir / "leaderboard.csv", index=False)
    open_closed = _open_vs_closed(leader)
    open_closed.to_csv(args.output_dir / "leaderboard_open_vs_closed.csv", index=False)

    resolved_sets = _load_resolved_sets()
    peers, mc = _peers(leader, resolved_sets)
    peers.to_csv(args.output_dir / "peers.csv", index=False)
    mc.to_csv(args.output_dir / "mcnemar.csv", index=False)

    per_repo = _per_repo_vs_peers(resolved_sets)
    per_repo.to_csv(args.output_dir / "per_repo_vs_peers.csv", index=False)

    uniq = _unique_to_kozuchi(resolved_sets)
    uniq.to_csv(args.output_dir / "unique_resolved.csv", index=False)
    print(
        "[analyze_competitors] wrote leaderboard.csv, leaderboard_open_vs_closed.csv, "
        "peers.csv, mcnemar.csv, per_repo_vs_peers.csv, unique_resolved.csv"
    )


if __name__ == "__main__":
    main()
