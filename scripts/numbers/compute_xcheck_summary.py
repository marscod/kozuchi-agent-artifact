"""Summarize the cross-agent test (``xcheck``) selector outcome.

Reads the selector summary JSON and writes the headline numbers reported
in the manuscript: resolved_count, score_over_expected, tie_instances,
and a comparison against the no-op size-order baseline.
"""

from __future__ import annotations

import json

from _paths import (
    STATS_DIR,
    TRAJ_BUNDLE_MANIFEST,
    TRAJ_XCHECK_RESULT,
)


def load_selector_audit() -> dict:
    path = STATS_DIR / "selector_audit.json"
    return json.loads(path.read_text()) if path.exists() else {}


def main() -> None:
    STATS_DIR.mkdir(parents=True, exist_ok=True)
    summary = json.loads(TRAJ_XCHECK_RESULT.read_text())
    manifest = json.loads(TRAJ_BUNDLE_MANIFEST.read_text())
    audit = load_selector_audit()

    out = {
        "selector_family": summary.get("selector_family"),
        "f2p_weight": summary.get("f2p_weight"),
        "p2p_weight": summary.get("p2p_weight"),
        "tie_break": summary.get("tie_break"),
        "expected_count": summary.get("expected_count"),
        "selected_count": summary.get("selected_count"),
        "resolved_count": summary.get("resolved_count"),
        "unresolved_count": summary.get("unresolved_count"),
        "error_count": summary.get("error_count"),
        "score_over_expected": summary.get("score_over_expected"),
        "covered_over_expected": summary.get("covered_over_expected"),
        "tie_instances": summary.get("tie_instances"),
        "changed_from_order": summary.get("changed_from_order"),
        "order_baseline": summary.get("order_baseline"),
        "manifest_simple_passrate_result": manifest.get("simple_passrate_result"),
        "manifest_xcheck_input_file_count": manifest.get("xcheck_input_file_count"),
        "manifest_xcheck_table_count": manifest.get("xcheck_table_count"),
        "selector_audit": audit,
    }
    (STATS_DIR / "xcheck_summary.json").write_text(json.dumps(out, indent=2))

    order = out.get("order_baseline") or {}
    tie_audit = audit.get("tie_audit", {})
    matrix = audit.get("matrix_audit", {})
    tex = [
        "% Auto-generated: cross-agent selector vs. order baseline (internal Docker re-grade).",
        "% Source: trajectories/q35_.../xcheck/results/simple_passrate_f03_p07_shortest_patch_raw_75p2.json",
        "% Audit rows source: paper/final/stats/selector_audit.json",
        r"\resizebox{\columnwidth}{!}{%",
        r"\begin{tabular}{@{}lrlr@{}}",
        r"\toprule",
        r"Quantity & Value & Quantity & Value \\",
        r"\midrule",
        (
            f"Expected (Verified)               & {out['expected_count']} & "
            f"$w_{{B}}$                           & {out['f2p_weight']} \\\\"
        ),
        (
            f"Selected (covered)                & {out['selected_count']} & "
            f"$w_{{R}}$                           & {out['p2p_weight']} \\\\"
        ),
        (
            f"Resolved (xcheck selector)        & {out['resolved_count']} & "
            f"Tie epsilon                       & {summary.get('tie_score_eps', '?')} \\\\"
        ),
        (
            f"Score over expected (xcheck)      & {out['score_over_expected']:.3f} & "
            r"Tie-breaker                       & shortest\_patch\_raw \\"
        ),
        (
            f"Resolved (order baseline)         & {order.get('resolved_count', '?')} & "
            f"Tie-break applied               & "
            f"{tie_audit.get('tie_breaker_applied_to_instances', '?')}/"
            f"{matrix.get('table_count', '?')} \\\\"
        ),
        (
            f"Score over expected (order)       & {order.get('score_over_expected', '?')} & "
            f"Mean unique patches               & {matrix.get('unique_patch_count_mean', 0):.2f}/8 \\\\"
        ),
        (
            f"Tie instances                     & {out['tie_instances']} & "
            f"Matrix executions                 & {matrix.get('matrix_patch_suite_executions', 0):,} \\\\"
        ),
        f"Reordered by selector             & {out['changed_from_order']} &                                  & \\\\",
        r"\bottomrule",
        r"\end{tabular}%",
        r"}",
    ]
    (STATS_DIR / "xcheck_summary.tex").write_text("\n".join(tex) + "\n")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
