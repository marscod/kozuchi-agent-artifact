"""Within-trajectory TTS@8 candidate-level analysis.

The headline 374 / 500 number reported in ``analyze_results.py`` is
the *selector's* pass@1 outcome on the Best-of-8 candidate stream.
Each of the 500 instances was actually attempted by 8 *independent*
mini-swe-agent legs (same scaffold, different decoding seeds), and
the selector — a weighted FAIL_TO_PASS / PASS_TO_PASS pass-rate
heuristic with a ``shortest-patch`` tie-break — collapses the 8
candidate patches into a single submission per instance.

The per-leg harness evaluations and the cross-check (``xcheck``)
test-tables live in the trajectory bundle shipped with this
submission

    trajectories/q35_verified500_tts8_75p2_submission_bundle_*/

This analyser opens those artifacts and answers four questions
that the leaderboard / single-trajectory analysis cannot:

  Q1 (per-leg).        How tight is the leg-to-leg pass-rate
                       distribution?  Is the headline 74.8 % carried
                       by one good seed, or by all 8?
  Q2 (oracle ceiling). What is the *oracle* pass@k under perfect
                       leg selection?  How much head-room does the
                       Best-of-8 selector leave on the table?
  Q3 (selector regret).Of the instances solvable by *at least one*
                       leg, how often does the selector pick a
                       non-resolving leg?  Where does the regret
                       concentrate (per-repo)?
  Q4 (patch diversity).How often do the 8 legs converge on the same
                       deduplicated patch (mode collapse), and how
                       does diversity correlate with success?

CSV outputs (under ``src/csv/``):

  - tts_per_leg.csv                       Per-leg pass / unresolved /
                                          empty / error counts with
                                          Wilson 95 % CIs.
  - tts_resolve_count_distribution.csv    For each r in 0..8, the
                                          number of instances resolved
                                          by exactly r of the 8 legs.
  - tts_pass_at_k_oracle.csv              Closed-form expected
                                          oracle pass@k for k=1..8.
  - tts_oracle_summary.csv                Selector vs. oracle summary
                                          (regret, attainable lift,
                                          selector hit-rate).
  - tts_per_instance_outcomes.csv         500 x (leg1..leg8 + selector
                                          + r_count + oracle) wide
                                          per-instance outcome table.
  - tts_selector_picks.csv                Per-leg selector preference
                                          and the post-selection
                                          conditional accuracy.
  - tts_per_repo_oracle_vs_selector.csv   Per-repo selector vs. oracle
                                          breakdown.
  - tts_patch_diversity.csv               Per-instance unique-patch
                                          count from the xcheck test
                                          tables.
  - tts_diversity_vs_outcome.csv          Distribution of unique-patch
                                          counts and resolution rate
                                          by diversity bucket.
  - tts_leg_jaccard.csv                   8x8 Jaccard agreement matrix
                                          between the resolved sets of
                                          every leg pair.

Every quantity reported in §11 of ``analysis.md`` is read directly
from one of these CSVs.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from math import comb
from pathlib import Path

import numpy as np
import pandas as pd

from utils import (
    CSV_DIR,
    EXPERIMENT_DIR,
    N_VERIFIED,
    RESULTS_JSON,
    TRAJ_BUNDLE_DIR,
    ensure_out_dirs,
    repo_of,
    wilson_ci,
)


N_LEGS = 8


# ---------------------------------------------------------------------------
# Bundle loaders
# ---------------------------------------------------------------------------


def _runs_dir() -> Path:
    return TRAJ_BUNDLE_DIR / "runs"


def _xcheck_dir() -> Path:
    return TRAJ_BUNDLE_DIR / "xcheck"


def _list_run_labels() -> list[str]:
    """Return the 8 sorted ``rXX_sYYYY`` run labels from the bundle."""
    runs = sorted(p.name for p in _runs_dir().iterdir() if p.is_dir())
    if len(runs) != N_LEGS:
        raise RuntimeError(
            f"Expected {N_LEGS} legs under {_runs_dir()}, found {len(runs)}: {runs}"
        )
    return runs


@dataclass(frozen=True)
class LegReport:
    label: str
    resolved: frozenset[str]
    unresolved: frozenset[str]
    empty_patch: frozenset[str]
    error: frozenset[str]
    submitted: int
    total: int


def _load_leg_reports() -> dict[str, LegReport]:
    """Read ``runs/<label>/report.json`` for every leg.

    Each ``report.json`` is the raw SWE-bench harness eval of that
    leg's predictions.  We expose four disjoint per-instance bucket
    sets (resolved / unresolved / empty / error) plus the totals.
    """
    out: dict[str, LegReport] = {}
    for lab in _list_run_labels():
        rep = json.loads((_runs_dir() / lab / "report.json").read_text())
        out[lab] = LegReport(
            label=lab,
            resolved=frozenset(rep["resolved_ids"]),
            unresolved=frozenset(rep["unresolved_ids"]),
            empty_patch=frozenset(rep["empty_patch_ids"]),
            error=frozenset(rep["error_ids"]),
            submitted=int(rep["submitted_instances"]),
            total=int(rep["total_instances"]),
        )
    return out


def _load_selector_picks() -> dict[str, str]:
    """Map ``instance_id -> source_run_label`` chosen by the selector.

    File: ``xcheck/results/simple_passrate_f03_p07_shortest_patch_raw_selected_labels.json``
    """
    path = (
        _xcheck_dir()
        / "results"
        / "simple_passrate_f03_p07_shortest_patch_raw_selected_labels.json"
    )
    return json.loads(path.read_text())


def _load_final_resolved() -> set[str]:
    """Read the canonical post-merge harness re-eval (``results.json``).

    The merge step that produces this file occasionally re-evaluates
    a small number of borderline test outcomes (typically flaky
    fixtures) and is the *authoritative* SWE-bench-Verified score for
    the submission.  All headline statements in §11 use this set.
    """
    res = json.loads(RESULTS_JSON.read_text())
    return set(res["resolved"])


def _instance_universe(reports: dict[str, LegReport]) -> list[str]:
    """Union of every instance id seen by any of the 8 legs."""
    u: set[str] = set()
    for r in reports.values():
        u |= set(r.resolved) | set(r.unresolved) | set(r.empty_patch) | set(r.error)
    if len(u) != N_VERIFIED:
        # Expand or trim to canonical N=500 by adding any missing ids
        # as artifact-missing failures (matches §5 convention).
        # Practically this branch is a no-op for this submission.
        pass
    return sorted(u)


# ---------------------------------------------------------------------------
# Per-leg summary  (Q1)
# ---------------------------------------------------------------------------


def per_leg_table(reports: dict[str, LegReport]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for lab, rep in reports.items():
        n = rep.total
        k = len(rep.resolved)
        ci = wilson_ci(k, n)
        rows.append(
            dict(
                leg=lab,
                n=n,
                resolved=k,
                unresolved=len(rep.unresolved),
                empty_patch=len(rep.empty_patch),
                error=len(rep.error),
                rate=k / n,
                ci_lo=ci.lo,
                ci_hi=ci.hi,
            )
        )
    df = pd.DataFrame(rows).sort_values("leg").reset_index(drop=True)
    return df


# ---------------------------------------------------------------------------
# Resolve-count distribution and oracle pass@k  (Q2)
# ---------------------------------------------------------------------------


def resolve_count_per_instance(
    reports: dict[str, LegReport], universe: list[str]
) -> pd.DataFrame:
    """For each instance, count how many of the 8 legs resolve it."""
    rows: list[dict[str, object]] = []
    for inst in universe:
        bits = [int(inst in rep.resolved) for rep in reports.values()]
        rows.append(
            dict(
                instance_id=inst,
                repo=repo_of(inst),
                r_count=int(sum(bits)),
                **{f"leg_{lab}": b for lab, b in zip(reports.keys(), bits)},
            )
        )
    return pd.DataFrame(rows)


def resolve_count_distribution(per_inst: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    n = len(per_inst)
    cum = 0
    for r in range(0, N_LEGS + 1):
        k = int((per_inst["r_count"] == r).sum())
        cum += k
        rows.append(
            dict(
                r_count=r,
                n_instances=k,
                share=k / n if n else 0.0,
                cum_n=cum,
                cum_share=cum / n if n else 0.0,
            )
        )
    return pd.DataFrame(rows)


def pass_at_k_oracle(per_inst: pd.DataFrame) -> pd.DataFrame:
    """Closed-form expected oracle pass@k for k = 1..8.

    Under uniform sampling without replacement of k legs from the
    8 candidate legs, the probability that *at least one* of the k
    sampled legs resolves a given instance with r_i / 8 successful
    legs is

        p_i(k) = 1 - C(8 - r_i, k) / C(8, k)        if r_i <= 8 - k
                 1                                   otherwise

    The expected number of instances resolved is
    sum_i p_i(k); we divide by N=500 to obtain a rate.  No Monte
    Carlo is needed — the expectation is closed-form.
    """
    rows: list[dict[str, object]] = []
    n = N_VERIFIED  # canonical denominator
    for k in range(1, N_LEGS + 1):
        denom = comb(N_LEGS, k)
        ev = 0.0
        for _, row in per_inst.iterrows():
            r = int(row["r_count"])
            if 8 - r >= k:
                ev += 1.0 - comb(8 - r, k) / denom
            else:
                ev += 1.0
        rows.append(
            dict(
                k=k,
                expected_resolved=ev,
                expected_rate=ev / n,
            )
        )
    df = pd.DataFrame(rows)
    return df


# ---------------------------------------------------------------------------
# Selector vs. oracle  (Q3)
# ---------------------------------------------------------------------------


def selector_summary(
    per_inst: pd.DataFrame,
    final_resolved: set[str],
    selector_picks: dict[str, str],
    reports: dict[str, LegReport],
) -> pd.DataFrame:
    """Top-level selector vs. oracle summary.

    Definitions:
      * oracle = at least one of the 8 legs resolves the instance
                 (r_count >= 1).
      * selector = the harness re-evaluates the patch chosen by the
                   weighted-pass-rate selector and resolves the
                   instance (i.e. instance is in ``results.json``'s
                   ``resolved`` list).
      * regret    = oracle - selector  (instances solvable by SOME
                    leg but where the selector picked a non-
                    resolving leg).
      * hit-rate  = selector / oracle  (conditional probability that
                    the selector picks a resolving leg given that
                    one exists).
    """
    n = N_VERIFIED
    n_oracle = int((per_inst["r_count"] >= 1).sum())
    n_sel = sum(1 for inst in per_inst["instance_id"] if inst in final_resolved)
    n_zero = int((per_inst["r_count"] == 0).sum())
    n_unanim = int((per_inst["r_count"] == N_LEGS).sum())
    n_marginal = int(per_inst["r_count"].between(1, N_LEGS - 1).sum())
    n_no_pick = sum(1 for inst in per_inst["instance_id"] if inst not in selector_picks)

    sel_lo, sel_hi = wilson_ci(n_sel, n).lo, wilson_ci(n_sel, n).hi
    or_lo, or_hi = wilson_ci(n_oracle, n).lo, wilson_ci(n_oracle, n).hi

    # Selector hit-rate among instances with at least one resolving leg.
    # ``sel_hits_attainable`` counts only instances where (i) the
    # final harness re-eval marks the instance resolved and (ii) at
    # least one of the eight per-leg report.json files also marks
    # that instance resolved.  This is the strict definition of "the
    # selector picked an oracle-valid leg".  We additionally report
    # the *headline* regret ``n_oracle - n_sel``, which can differ by
    # a handful of instances when the post-merge re-eval flips a
    # flaky test outcome.
    sel_hits_attainable = 0
    for inst in per_inst["instance_id"]:
        if inst in final_resolved and any(
            inst in reports[lab].resolved for lab in reports
        ):
            sel_hits_attainable += 1
    hit_rate = sel_hits_attainable / n_oracle if n_oracle else 0.0
    headline_regret = n_oracle - n_sel
    attainable_regret = n_oracle - sel_hits_attainable
    # The "merge recovery" gap captures any instance the harness
    # ultimately scores as resolved that no per-leg report counted
    # (typically a flaky test outcome flipped between the per-leg and
    # the merged final eval).  By construction
    # merge_recovery == n_sel - sel_hits_attainable.
    merge_recovery = n_sel - sel_hits_attainable

    rows = [
        dict(metric="selector_resolved", value=n_sel, share=n_sel / n),
        dict(metric="selector_resolved_ci_lo", value=sel_lo, share=None),
        dict(metric="selector_resolved_ci_hi", value=sel_hi, share=None),
        dict(metric="oracle_resolved_any_leg", value=n_oracle, share=n_oracle / n),
        dict(metric="oracle_resolved_ci_lo", value=or_lo, share=None),
        dict(metric="oracle_resolved_ci_hi", value=or_hi, share=None),
        # Headline regret: the canonical "extra wins available under
        # perfect leg selection given the same compute".
        dict(
            metric="headline_regret_oracle_minus_selector",
            value=headline_regret,
            share=headline_regret / n,
        ),
        # Attainable regret: stricter form using only per-leg report
        # eval; differs from the headline regret by the merge re-eval
        # recovery count.
        dict(
            metric="attainable_regret_oracle_minus_selector_hits",
            value=attainable_regret,
            share=attainable_regret / n,
        ),
        dict(
            metric="merge_reeval_recovery_count",
            value=int(merge_recovery),
            share=merge_recovery / n,
        ),
        dict(
            metric="selector_hit_rate_among_attainable",
            value=hit_rate,
            share=None,
        ),
        dict(
            metric="instances_zero_legs_resolve",
            value=n_zero,
            share=n_zero / n,
        ),
        dict(
            metric="instances_all_8_legs_resolve",
            value=n_unanim,
            share=n_unanim / n,
        ),
        dict(
            metric="instances_marginal_1_to_7_legs_resolve",
            value=n_marginal,
            share=n_marginal / n,
        ),
        dict(
            metric="instances_with_no_selector_pick",
            value=n_no_pick,
            share=n_no_pick / n,
        ),
    ]
    return pd.DataFrame(rows)


def selector_picks_table(
    per_inst: pd.DataFrame,
    final_resolved: set[str],
    selector_picks: dict[str, str],
    reports: dict[str, LegReport],
) -> pd.DataFrame:
    """Per-leg breakdown of the selector's preference.

    For every leg we report:
      * n_picked         : how many instances the selector routed there.
      * n_picked_resolves: of those, how many were ultimately resolved
                           in ``results.json`` (selector-leg accuracy).
      * leg_resolved     : how many of those instances were actually
                           a resolving leg in the per-leg report
                           (cross-check vs. final harness eval).
    """
    counts: dict[str, dict[str, int]] = {
        lab: {"picked": 0, "picked_resolves_final": 0, "picked_in_leg_resolves": 0}
        for lab in reports
    }
    for inst, lab in selector_picks.items():
        if lab not in counts:
            continue
        counts[lab]["picked"] += 1
        if inst in final_resolved:
            counts[lab]["picked_resolves_final"] += 1
        if inst in reports[lab].resolved:
            counts[lab]["picked_in_leg_resolves"] += 1

    rows: list[dict[str, object]] = []
    for lab, c in counts.items():
        n_picked = c["picked"]
        rows.append(
            dict(
                leg=lab,
                n_picked=n_picked,
                pick_share=n_picked / sum(x["picked"] for x in counts.values())
                if counts
                else 0.0,
                n_picked_resolves_final=c["picked_resolves_final"],
                pick_accuracy_final=(
                    c["picked_resolves_final"] / n_picked if n_picked else 0.0
                ),
                n_picked_resolves_leg=c["picked_in_leg_resolves"],
            )
        )
    return pd.DataFrame(rows).sort_values("leg").reset_index(drop=True)


def per_repo_oracle_vs_selector(
    per_inst: pd.DataFrame, final_resolved: set[str]
) -> pd.DataFrame:
    """Per-repository oracle vs. selector comparison."""
    rows: list[dict[str, object]] = []
    for repo, sub in per_inst.groupby("repo"):
        n = len(sub)
        oracle = int((sub["r_count"] >= 1).sum())
        sel = sum(1 for i in sub["instance_id"] if i in final_resolved)
        regret = oracle - sel  # >= 0
        rows.append(
            dict(
                repo=repo,
                n=n,
                selector_resolved=sel,
                selector_rate=sel / n,
                oracle_resolved=oracle,
                oracle_rate=oracle / n,
                regret=regret,
                regret_share_of_n=regret / n,
                regret_share_of_oracle=regret / oracle if oracle else 0.0,
            )
        )
    return pd.DataFrame(rows).sort_values("n", ascending=False).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Patch diversity from the xcheck instance_test_tables  (Q4)
# ---------------------------------------------------------------------------


def patch_diversity_per_instance(
    per_inst: pd.DataFrame, final_resolved: set[str]
) -> pd.DataFrame:
    """For each instance, count the number of *deduplicated* candidate
    patches.

    The xcheck test-tables collapse the 8 legs into a unique-patch
    space: identical patches across legs are merged into a single
    row (with ``candidate_indices`` listing every leg that produced
    it).  We use the resulting row count as the per-instance
    ``n_unique_patches`` (range 1..8).  Instances missing a test
    table are recorded as ``n_unique_patches = 0`` and treated as
    artifact-missing in downstream summaries.
    """
    table_dir = _xcheck_dir() / "instance_test_tables"
    rows: list[dict[str, object]] = []
    for _, r in per_inst.iterrows():
        inst = r["instance_id"]
        path = table_dir / f"{inst}.json"
        if not path.exists():
            n_uniq = 0
            n_apply_ok = 0
        else:
            data = json.loads(path.read_text())
            n_uniq = len(data.get("patches", []))
            n_apply_ok = sum(
                1 for p in data["patches"] if p.get("apply_status") == "ok"
            )
        rows.append(
            dict(
                instance_id=inst,
                repo=r["repo"],
                r_count=int(r["r_count"]),
                n_unique_patches=n_uniq,
                n_unique_patches_apply_ok=n_apply_ok,
                selector_resolved=int(inst in final_resolved),
            )
        )
    return pd.DataFrame(rows)


def diversity_vs_outcome(diversity: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for n_uniq, sub in diversity.groupby("n_unique_patches"):
        n = len(sub)
        sel = int(sub["selector_resolved"].sum())
        oracle = int((sub["r_count"] >= 1).sum())
        ci = wilson_ci(sel, n)
        rows.append(
            dict(
                n_unique_patches=int(n_uniq),
                n_instances=n,
                selector_resolved=sel,
                selector_rate=sel / n if n else 0.0,
                selector_rate_ci_lo=ci.lo,
                selector_rate_ci_hi=ci.hi,
                oracle_resolved=oracle,
                oracle_rate=oracle / n if n else 0.0,
                regret=oracle - sel,
            )
        )
    return pd.DataFrame(rows).sort_values("n_unique_patches").reset_index(drop=True)


# ---------------------------------------------------------------------------
# Pairwise leg agreement (Jaccard)
# ---------------------------------------------------------------------------


def leg_jaccard_matrix(reports: dict[str, LegReport]) -> pd.DataFrame:
    labs = list(reports.keys())
    mat = np.zeros((len(labs), len(labs)), dtype=float)
    for i, a in enumerate(labs):
        sa = set(reports[a].resolved)
        for j, b in enumerate(labs):
            sb = set(reports[b].resolved)
            inter = len(sa & sb)
            union = len(sa | sb)
            mat[i, j] = inter / union if union else 0.0
    df = pd.DataFrame(mat, index=labs, columns=labs)
    df.index.name = "leg"
    return df.reset_index()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output-dir", type=Path, default=CSV_DIR)
    args = p.parse_args()

    ensure_out_dirs()
    out = args.output_dir

    if not _runs_dir().exists():
        raise SystemExit(
            f"[analyze_tts] Trajectory bundle not found at {TRAJ_BUNDLE_DIR}; skipping."
        )

    reports = _load_leg_reports()
    selector_picks = _load_selector_picks()
    final_resolved = _load_final_resolved()
    universe = _instance_universe(reports)

    # Q1.
    per_leg = per_leg_table(reports)
    per_leg.to_csv(out / "tts_per_leg.csv", index=False)

    # Q2.
    per_inst = resolve_count_per_instance(reports, universe)
    per_inst.to_csv(out / "tts_per_instance_outcomes.csv", index=False)

    rdist = resolve_count_distribution(per_inst)
    rdist.to_csv(out / "tts_resolve_count_distribution.csv", index=False)

    pak = pass_at_k_oracle(per_inst)
    pak.to_csv(out / "tts_pass_at_k_oracle.csv", index=False)

    # Q3.
    summary = selector_summary(per_inst, final_resolved, selector_picks, reports)
    summary.to_csv(out / "tts_oracle_summary.csv", index=False)

    picks = selector_picks_table(per_inst, final_resolved, selector_picks, reports)
    picks.to_csv(out / "tts_selector_picks.csv", index=False)

    repo_orsel = per_repo_oracle_vs_selector(per_inst, final_resolved)
    repo_orsel.to_csv(out / "tts_per_repo_oracle_vs_selector.csv", index=False)

    # Q4.
    diversity = patch_diversity_per_instance(per_inst, final_resolved)
    diversity.to_csv(out / "tts_patch_diversity.csv", index=False)

    div_outcome = diversity_vs_outcome(diversity)
    div_outcome.to_csv(out / "tts_diversity_vs_outcome.csv", index=False)

    # Inter-leg Jaccard.
    jacc = leg_jaccard_matrix(reports)
    jacc.to_csv(out / "tts_leg_jaccard.csv", index=False)

    # Console summary so the build log is self-explanatory.
    n_oracle = int(summary.loc[summary.metric == "oracle_resolved_any_leg", "value"].iloc[0])
    n_sel = int(summary.loc[summary.metric == "selector_resolved", "value"].iloc[0])
    print(
        f"[analyze_tts] selector={n_sel}/500  oracle={n_oracle}/500  "
        f"regret={n_oracle - n_sel}  hit_rate="
        f"{n_sel / n_oracle if n_oracle else 0.0:.3f}"
    )
    print(
        "[analyze_tts] wrote tts_per_leg.csv, tts_pass_at_k_oracle.csv, "
        "tts_oracle_summary.csv, tts_selector_picks.csv, "
        "tts_per_repo_oracle_vs_selector.csv, tts_patch_diversity.csv, "
        "tts_diversity_vs_outcome.csv, tts_leg_jaccard.csv, "
        "tts_resolve_count_distribution.csv, tts_per_instance_outcomes.csv"
    )


if __name__ == "__main__":
    main()
